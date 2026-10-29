"""Deterministic orchestration loop (Agent.md §9).

Maximum flow:
  1. Accept normalized user input.
  2. Classify request (knowledge/conversation, memory, document retrieval,
     local action, scheduled action, unsupported or unsafe).
  3. Retrieve relevant local context.
  4. Request conversational response OR structured tool proposal.
  5. Validate proposal.
  6. Run policy evaluation.
  7. If required, show approval card (await user decision).
  8. Execute one approved action.
  9. Return structured result to the model.
 10. Produce final user-facing response.
 11. Persist the turn and audit metadata.
 12. Stop.

- Configurable max tool iterations (default 3).
- Loop prevention by hashing recent tool calls.
- No self-modification, permission escalation, or creation of new tools at
  runtime.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from jarvis.api.ollama import OllamaClient, OllamaError, _sanitize_tool_output
from jarvis.config import settings
from jarvis.orchestration.events import (
    AssistantErrorEvent,
    AssistantEvent,
    LatencyMetricEvent,
    StateTransitionEvent,
    StreamChunkEvent,
    ToolProposalEvent,
    ToolResultEvent,
    TranscriptEvent,
)
from jarvis.policy.engine import PolicyEngine, RiskLevel
from jarvis.state import AWAITING_APPROVAL, EXECUTING, IDLE, THINKING
from jarvis.telemetry.logger import get_logger
from jarvis.tools.registry import ToolRegistry, ToolResult

logger = get_logger("jarvis.orchestration")

# JSON schema the model must use for structured tool proposals.
TOOL_PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "tool_calls": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tool_id": {"type": "string"},
                    "arguments": {"type": "object"},
                },
                "required": ["tool_id", "arguments"],
                "additionalProperties": False,
            },
        },
        "text": {"type": "string"},
    },
    "required": ["tool_calls", "text"],
    "additionalProperties": False,
}

# Request categories (Agent.md §9 step 2).
CATEGORY_CONVERSATION = "conversation"
CATEGORY_KNOWLEDGE = "knowledge"
CATEGORY_MEMORY = "memory"
CATEGORY_DOCUMENT = "document_retrieval"
CATEGORY_LOCAL_ACTION = "local_action"
CATEGORY_SCHEDULED = "scheduled_action"
CATEGORY_UNSUPPORTED = "unsupported_or_unsafe"

DEFAULT_MAX_TOOL_ITERATIONS = 3


@dataclass
class ApprovalDecision:
    request_id: str
    decision: str  # "approved_once" | "remembered" | "denied" | "cancelled"


@dataclass
class TurnRecord:
    request_id: str
    conversation_id: str
    user_input: str
    category: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    final_response: str = ""
    error: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    started_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    completed_at: str | None = None


class Orchestrator:
    """Deterministic orchestration loop for a single assistant turn."""

    def __init__(
        self,
        ollama: OllamaClient,
        registry: ToolRegistry,
        policy: PolicyEngine,
        max_tool_iterations: int = DEFAULT_MAX_TOOL_ITERATIONS,
    ) -> None:
        self.ollama = ollama
        self.registry = registry
        self.policy = policy
        self.max_tool_iterations = max_tool_iterations
        self._approval_decision: ApprovalDecision | None = None
        self._approval_event = asyncio.Event()
        self._recent_calls: deque[str] = deque(maxlen=50)
        self._turn_store: dict[str, TurnRecord] = {}

    # ── public API -------------------------------------------------------

    def set_approval(self, request_id: str, decision: str) -> None:
        """Called by the API when the user responds to an approval card."""
        self._approval_decision = ApprovalDecision(request_id=request_id, decision=decision)
        self._approval_event.set()

    async def run_turn(
        self,
        user_input: str,
        conversation_id: str,
        request_id: str,
        model: str | None = None,
    ) -> AsyncIterator[AssistantEvent]:
        """Run one assistant turn, yielding typed events to the UI."""
        turn = TurnRecord(
            request_id=request_id,
            conversation_id=conversation_id,
            user_input=user_input,
            category=CATEGORY_CONVERSATION,
        )
        self._turn_store[request_id] = turn

        # Reset approval state for this turn.
        self._approval_decision = None
        self._approval_event.clear()

        try:
            # ── Step 1: accept input, transition to thinking ---------------
            yield StateTransitionEvent(
                from_state=IDLE,
                to_state=THINKING,
                request_id=request_id,
                conversation_id=conversation_id,
            )
            yield TranscriptEvent(
                role="user",
                text=user_input,
                is_final=True,
                turn_id=request_id,
            )

            # ── Step 2: classify request ----------------------------------
            category = self._classify(user_input)
            turn.category = category
            yield LatencyMetricEvent(
                name="total_turn",
                duration_ms=0.0,
                turn_id=request_id,
            )

            if category == CATEGORY_UNSUPPORTED:
                async for event in self._emit_unsupported(
                    request_id, conversation_id, turn
                ):
                    yield event
                return

            # ── Step 3: retrieve relevant local context -------------------
            context = self._retrieve_context(category, user_input)
            turn.context = context

            # ── Steps 4-10: deterministic loop ----------------------------
            final_response, loop_events = await self._run_loop(
                user_input=user_input,
                category=category,
                context=context,
                request_id=request_id,
                conversation_id=conversation_id,
                turn=turn,
                model=model,
            )
            turn.final_response = final_response
            for event in loop_events:
                yield event

            # ── Step 10 (cont.): produce final response -------------------
            if final_response:
                yield TranscriptEvent(
                    role="assistant",
                    text=final_response,
                    is_final=True,
                    turn_id=request_id,
                )

            # ── Step 11: persist turn + audit metadata --------------------
            turn.completed_at = datetime.now(UTC).isoformat()
            self._persist_turn(turn)

            # ── Step 12: stop, return to idle -----------------------------
            async for event in self._emit_idle_transition(
                request_id, conversation_id
            ):
                yield event

        except Exception as exc:  # noqa: BLE001 — turn-level safety net
            yield AssistantErrorEvent(
                code="internal_error",
                message="An internal error occurred while processing your request.",
                recoverable=True,
                retry_available=True,
                request_id=request_id,
                conversation_id=conversation_id,
            )
            self._complete_turn(turn, "", error=str(exc))
            async for event in self._emit_idle_transition(request_id, conversation_id):
                yield event

    # ── classification -----------------------------------------------------

    def _classify(self, user_input: str) -> str:
        """Heuristic request classification (Phase 3; may be LLM-based later).

        Not a security boundary — the policy engine enforces authorization.
        """
        text = user_input.lower()
        action_verbs = (
            "open ", "launch ", "start ", "create ", "write ", "update ",
            "copy ", "copy ", "remind ", "timer ", "notification ", "notify ",
        )
        if any(v in text for v in action_verbs):
            return CATEGORY_LOCAL_ACTION
        if "remember" in text or "memory" in text:
            return CATEGORY_MEMORY
        if "document" in text or "file" in text or "search" in text:
            return CATEGORY_DOCUMENT
        if "schedule" in text or "recurring" in text:
            return CATEGORY_SCHEDULED
        return CATEGORY_CONVERSATION

    def _retrieve_context(self, category: str, user_input: str) -> dict[str, Any]:
        """Step 3: retrieve local context using read-only tools."""
        context: dict[str, Any] = {}
        if category in (CATEGORY_MEMORY, CATEGORY_CONVERSATION):
            result = self.registry.execute("search_local_memories", {"query": user_input})
            context["memories"] = result.result if result.ok else {}
        if category in (CATEGORY_DOCUMENT, CATEGORY_KNOWLEDGE):
            result = self.registry.execute("search_indexed_documents", {"query": user_input})
            context["documents"] = result.result if result.ok else {}
        return context

    async def _resolve_model(self, requested: str | None) -> str | None:
        """Resolve which model to use: explicit request, config, then first installed.

        Skips embedding-style models for chat. Returns None when no model is
        available (caller emits a model_missing error, never a spoken error).
        """
        if requested:
            return requested
        if settings.ollama_chat_model:
            return settings.ollama_chat_model
        try:
            installed = await self.ollama.list_models()
        except Exception:  # noqa: BLE001 — best-effort fallback
            return None
        for name in installed:
            if "embed" not in name.lower():
                return name
        return installed[0] if installed else None

    # ── core loop ----------------------------------------------------------

    async def _run_loop(
        self,
        user_input: str,
        category: str,
        context: dict[str, Any],
        request_id: str,
        conversation_id: str,
        turn: TurnRecord,
        model: str | None = None,
    ) -> tuple[str, list[AssistantEvent]]:
        """Steps 4-10: at most `max_tool_iterations` tool rounds, then final answer.

        Returns (final_response, events) where events are yielded to the caller
        (run_turn) for streaming to the UI.
        """
        events: list[AssistantEvent] = []
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt(category, context)},
            {"role": "user", "content": user_input},
        ]

        final_response = ""

        resolved_model = await self._resolve_model(model)
        if resolved_model is None:
            events.append(
                AssistantErrorEvent(
                    code="model_missing",
                    message=(
                        "No language model is available. Pull a model with "
                        "'ollama pull qwen2.5:3b' (or set one in the backend .env "
                        "as JARVIS_OLLAMA_CHAT_MODEL) and select it on the "
                        "Models screen."
                    ),
                    recoverable=True,
                    retry_available=False,
                    request_id=request_id,
                    conversation_id=conversation_id,
                )
            )
            return "", events

        for iteration in range(self.max_tool_iterations + 1):
            if iteration > 0:
                # We've already executed a tool; feed result back and ask model again.
                pass

            # Decide conversational vs tool proposal based on category.
            if category in (
                CATEGORY_LOCAL_ACTION,
                CATEGORY_SCHEDULED,
                CATEGORY_MEMORY,
                CATEGORY_DOCUMENT,
            ):
                should_stop, tool_response = await self._handle_tool_category(
                    messages=messages,
                    category=category,
                    context=context,
                    request_id=request_id,
                    conversation_id=conversation_id,
                    turn=turn,
                    events=events,
                    model=resolved_model,
                )
                if should_stop:
                    final_response = tool_response
                    break
                continue

                continue

            # Conversational / knowledge category: stream a direct answer.
            final_response = await self._stream_conversational(
                messages,
                request_id,
                events,
                turn_id=request_id,
                model=resolved_model,
            )
            break

        return final_response or "", events

    async def _handle_tool_category(
        self,
        messages: list[dict[str, Any]],
        category: str,
        context: dict[str, Any],
        request_id: str,
        conversation_id: str,
        turn: TurnRecord,
        events: list[AssistantEvent],
        model: str | None = None,
    ) -> tuple[bool, str]:
        """Handle one tool-proposal iteration (Steps 4-9).

        Returns (should_stop, final_response). If should_stop is True, the
        caller should break out of the iteration loop. Otherwise the caller
        continues to the next iteration (tool result was fed back to model).
        """
        # ── Step 4: request a structured tool proposal ----------------------
        proposal = await self._request_tool_proposal(messages, request_id, model)
        turn.tool_calls.append(proposal)

        tool_calls = proposal.get("tool_calls", [])
        if not tool_calls:
            # Model chose not to call a tool; produce conversational answer.
            final_response = str(proposal.get("text", ""))
            events.append(
                TranscriptEvent(
                    role="assistant",
                    text=final_response,
                    is_final=False,
                    turn_id=request_id,
                )
            )
            return True, final_response

        # Execute at most one tool per iteration (deterministic).
        tool_call = tool_calls[0]
        tool_id = str(tool_call.get("tool_id", ""))
        args = tool_call.get("arguments", {})
        if not isinstance(args, dict):
            args = {}

        # ── Step 5: validate proposal --------------------------------------
        validation = self._validate_proposal(tool_id, args)
        if not validation.ok:
            events.append(
                ToolResultEvent(
                    tool_id=tool_id,
                    success=False,
                    error=validation.error,
                    duration_ms=0.0,
                    request_id=request_id,
                    conversation_id=conversation_id,
                    verdict="failed",
                )
            )
            # Feed error back to model and continue (one more chance).
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Tool proposal validation failed: {validation.error}. "
                        "Reply conversationally or propose a valid tool."
                    ),
                }
            )
            return False, ""

        # ── Step 6: policy evaluation --------------------------------------
        tool = self.registry.get(tool_id)
        definition = tool.definition if tool else None
        risk_level = (
            RiskLevel(int(definition.risk_level)) if definition else RiskLevel.LEVEL_3
        )
        category_name = (
            definition.permission_category if definition else "unknown"
        )
        policy_result = self.policy.evaluate(
            tool_id=tool_id,
            args=args,
            risk_level=risk_level,
            permission_category=category_name,
        )

        # Emit proposal event so the UI can show an approval card.
        events.append(
            ToolProposalEvent(
                tool_id=tool_id,
                arguments=args,
                risk_level=int(risk_level),
                reason=policy_result.reason,
                expected_effect=self._expected_effect(tool_id, args),
                request_id=request_id,
                conversation_id=conversation_id,
            )
        )

        # ── Step 7: approval --------------------------------------
        if policy_result.decision.value == "deny":
            events.append(
                ToolResultEvent(
                    tool_id=tool_id,
                    success=False,
                    error="denied by policy",
                    duration_ms=0.0,
                    request_id=request_id,
                    conversation_id=conversation_id,
                    verdict="failed",
                )
            )
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"The requested action '{tool_id}' was denied: "
                        f"{policy_result.reason}. Reply conversationally."
                    ),
                }
            )
            return False, ""

        if policy_result.decision.value == "require_approval":
            # Wait for the user's approval decision.
            events.append(
                StateTransitionEvent(
                    from_state=THINKING,
                    to_state=AWAITING_APPROVAL,
                    request_id=request_id,
                    conversation_id=conversation_id,
                )
            )
            decision = await self._await_approval(request_id)
            events.append(
                StateTransitionEvent(
                    from_state=AWAITING_APPROVAL,
                    to_state=THINKING,
                    request_id=request_id,
                    conversation_id=conversation_id,
                )
            )

            if decision.decision in ("denied", "cancelled"):
                events.append(
                    ToolResultEvent(
                        tool_id=tool_id,
                        success=False,
                        error=f"user {decision.decision}",
                        duration_ms=0.0,
                        request_id=request_id,
                        conversation_id=conversation_id,
                        verdict="failed",
                    )
                )
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"The user {decision.decision} the action '{tool_id}'. "
                            "Reply conversationally."
                        ),
                    }
                )
                return False, ""

            # approved_once or remembered → proceed.
            if decision.decision == "remembered" and policy_result.remembered_permission_id:
                pass  # permission already recorded by policy engine

        # ── Step 8: execute one approved action -------------------
        events.append(
            StateTransitionEvent(
                from_state=THINKING,
                to_state=EXECUTING,
                request_id=request_id,
                conversation_id=conversation_id,
            )
        )

        # Loop prevention: hash the tool call and reject repeats.
        call_hash = self._call_hash(tool_id, args)
        if call_hash in self._recent_calls:
            events.append(
                ToolResultEvent(
                    tool_id=tool_id,
                    success=False,
                    error="repeated tool call rejected (loop prevention)",
                    duration_ms=0.0,
                    request_id=request_id,
                    conversation_id=conversation_id,
                    verdict="failed",
                )
            )
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Repeated call to '{tool_id}' was rejected to prevent a loop. "
                        "Reply conversationally."
                    ),
                }
            )
            events.append(
                StateTransitionEvent(
                    from_state=EXECUTING,
                    to_state=THINKING,
                    request_id=request_id,
                    conversation_id=conversation_id,
                )
            )
            return False, ""
        self._recent_calls.append(call_hash)

        result = self.registry.execute(tool_id, args)
        turn.tool_results.append(
            {
                "tool_id": tool_id,
                "args": args,
                "ok": result.ok,
                "verdict": result.verdict,
                "error_code": result.error_code,
                "message": result.message,
                "duration_ms": result.duration_ms,
            }
        )

        events.append(
            ToolResultEvent(
                tool_id=tool_id,
                success=result.ok,
                result=result.result if result.ok else None,
                error=result.error_code or result.message,
                duration_ms=result.duration_ms,
                request_id=request_id,
                conversation_id=conversation_id,
                verdict=result.verdict or ("done" if result.ok else "failed"),
            )
        )
        events.append(
            StateTransitionEvent(
                from_state=EXECUTING,
                to_state=THINKING,
                request_id=request_id,
                conversation_id=conversation_id,
            )
        )

        # ── Step 9: return structured result to model -------------
        sanitized = self._sanitize_for_model(result)
        messages.append(
            {
                "role": "user",
                "content": (
                    f"Tool '{tool_id}' result: {json.dumps(sanitized)[:2000]}. "
                    "Verdict meanings: done = verified, speak as completed; "
                    "unverified = request sent but not confirmed — say you could "
                    "not confirm it, never claim success; failed = did not happen; "
                    "ask = nothing was done. "
                    "Produce the final user-facing answer."
                ),
            }
        )
        return False, ""

    # ── turn lifecycle helpers --------------------------------------------

    async def _emit_unsupported(
        self, request_id: str, conversation_id: str, turn: TurnRecord
    ) -> AsyncIterator[AssistantEvent]:
        """Yield events for an unsupported request, then complete the turn."""
        yield AssistantErrorEvent(
            code="unsupported_request",
            message="This request is not supported by JARVIS in this version.",
            recoverable=True,
            retry_available=False,
            request_id=request_id,
            conversation_id=conversation_id,
        )
        yield StateTransitionEvent(
            from_state=THINKING,
            to_state=IDLE,
            request_id=request_id,
            conversation_id=conversation_id,
        )
        self._complete_turn(turn, "", error="unsupported_request")

    async def _emit_idle_transition(
        self, request_id: str, conversation_id: str
    ) -> AsyncIterator[AssistantEvent]:
        """Yield the transition back to idle, logging persistence failures."""
        try:
            yield StateTransitionEvent(
                from_state=THINKING,
                to_state=IDLE,
                request_id=request_id,
                conversation_id=conversation_id,
            )
        except Exception as exc:  # noqa: BLE001 — persistence failure must not break the turn
            logger.warning("turn_persistence_failed", extra={"error": str(exc)})

    # ── helpers ------------------------------------------------------------


    def _system_prompt(self, category: str, context: dict[str, Any]) -> str:
        return (
            "You are JARVIS, a privacy-first local desktop assistant. "
            "You run entirely on the user's machine with Ollama. "
            f"Current request category: {category}. "
            "Available context: " + json.dumps(context)[:1000] + ". "
            "Rules: (1) Never pretend you performed an action you did not. "
            "(2) Every tool call must be approved by the user unless level 0. "
            "(3) Never execute shell, eval, or arbitrary commands. "
            "(4) Keep responses concise and helpful. "
            "(5) Every tool result carries a verdict you must speak honestly: "
            "'done' means checked and true — say it succeeded; "
            "'unverified' means the request went out but stayed unconfirmed — "
            "say so plainly, never claim success; "
            "'failed' means it did not happen — say why using the message; "
            "'ask' means nothing was done — say what is needed before acting; "
            "'started' means it is under way, outcome to follow — "
            "say so and do not claim completion. "
            "When proposing a tool, output ONLY the structured JSON per the schema. "
            "When answering conversationally, output plain text only."
        )

    async def _request_tool_proposal(
        self, messages: list[dict[str, Any]], request_id: str, model: str | None = None
    ) -> dict[str, Any]:
        """Step 4: request a structured tool proposal from the model."""
        try:
            proposal = await self.ollama.chat_structured(
                messages=messages,
                schema=TOOL_PLAN_SCHEMA,
                temperature=0.1,  # low temperature for action planning
                model=model,
            )
            return proposal if isinstance(proposal, dict) else {"tool_calls": [], "text": ""}
        except Exception:  # noqa: BLE001 — degrade to conversation
            return {"tool_calls": [], "text": "I'm unable to plan that action right now."}

    async def _stream_conversational(
        self,
        messages: list[dict[str, Any]],
        request_id: str,
        events: list[AssistantEvent],
        turn_id: str | None = None,
        model: str | None = None,
    ) -> str:
        """Step 10 (conversational branch): stream the assistant answer.

        Appends StreamChunkEvents to `events` and returns the full text.
        Failures emit an AssistantErrorEvent only — never speakable text —
        so error details cannot be read aloud as if they were the reply.
        """
        chunks: list[str] = []
        try:
            async for delta in self.ollama.chat_stream(
                messages=messages, temperature=0.2, model=model
            ):
                chunks.append(delta)
                events.append(StreamChunkEvent(delta=delta, turn_id=turn_id))
        except Exception as exc:  # noqa: BLE001 — degrade gracefully
            code = exc.error_code if isinstance(exc, OllamaError) else "internal_error"
            events.append(
                AssistantErrorEvent(
                    code=code,
                    message="I couldn't reach the language model. "
                    "Check that Ollama is running and a model is selected.",
                    recoverable=True,
                    retry_available=True,
                    request_id=request_id,
                )
            )
        return "".join(chunks)

    def _validate_proposal(self, tool_id: str, args: dict[str, Any]) -> _Validation:
        """Step 5: validate a tool proposal against the registry schema."""
        tool = self.registry.get(tool_id)
        if tool is None:
            return _Validation(ok=False, error=f"unknown tool: {tool_id}")
        definition = tool.definition
        input_schema = definition.input_schema
        # Required fields present.
        required = input_schema.get("required", [])
        if isinstance(required, list):
            for key in required:
                if key not in args:
                    return _Validation(ok=False, error=f"missing required argument: {key}")
        # Type/enum checks for declared properties.
        properties = input_schema.get("properties", {})
        if isinstance(properties, dict):
            for key, value in args.items():
                if key in properties:
                    prop = properties[key]
                    if not _check_arg(value, prop):
                        return _Validation(
                            ok=False,
                            error=f"argument '{key}' does not match schema",
                        )
                elif input_schema.get("additionalProperties") is False:
                    return _Validation(
                        ok=False,
                        error=f"additional argument not allowed: {key}",
                    )
        return _Validation(ok=True, error=None)

    def _expected_effect(self, tool_id: str, args: dict[str, Any]) -> str:
        tool = self.registry.get(tool_id)
        if tool is None:
            return "unknown tool"
        return tool.definition.description

    async def _await_approval(self, request_id: str) -> ApprovalDecision:
        """Wait for the UI to supply an approval decision."""
        self._approval_event.clear()
        await self._approval_event.wait()
        if self._approval_decision is None or self._approval_decision.request_id != request_id:
            return ApprovalDecision(request_id=request_id, decision="denied")
        return self._approval_decision

    def _call_hash(self, tool_id: str, args: dict[str, Any]) -> str:
        payload = json.dumps({"tool": tool_id, "args": args}, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def _sanitize_for_model(self, result: ToolResult) -> dict[str, Any]:
        """Step 9: sanitize tool output before returning to the model."""
        out = dict(result.result or {})
        # Redact/truncate any string values.
        for key, value in list(out.items()):
            if isinstance(value, str):
                out[key] = _sanitize_tool_output(value)
        out["ok"] = result.ok
        out["verdict"] = result.verdict or ("done" if result.ok else "failed")
        out["error_code"] = result.error_code
        out["message"] = result.message
        return out

    # ── persistence --------------------------------------------------------

    def _complete_turn(self, turn: TurnRecord, final_response: str, error: str | None) -> None:
        turn.final_response = final_response
        turn.error = error
        turn.completed_at = datetime.now(UTC).isoformat()
        self._persist_turn(turn)

    def _persist_turn(self, turn: TurnRecord) -> None:
        """Append the turn as a JSONL record (local conversation history)."""
        store_dir = os.path.join(os.path.expanduser("~"), ".jarvis", "conversations")
        os.makedirs(store_dir, exist_ok=True)
        path = os.path.join(store_dir, f"{turn.conversation_id}.jsonl")
        record = {
            "request_id": turn.request_id,
            "conversation_id": turn.conversation_id,
            "category": turn.category,
            "user_input": turn.user_input,
            "tool_calls": turn.tool_calls,
            "tool_results": turn.tool_results,
            "final_response": turn.final_response,
            "error": turn.error,
            "started_at": turn.started_at,
            "completed_at": turn.completed_at,
        }
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")

    def get_turn(self, request_id: str) -> TurnRecord | None:
        return self._turn_store.get(request_id)


@dataclass
class _Validation:
    ok: bool
    error: str | None = None


def _check_arg(value: Any, prop: dict[str, Any]) -> bool:
    expected_type = prop.get("type")
    if expected_type == "string":
        ok = isinstance(value, str)
    elif expected_type == "integer":
        ok = isinstance(value, int) and not isinstance(value, bool)
    elif expected_type == "number":
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
    elif expected_type == "boolean":
        ok = isinstance(value, bool)
    elif expected_type == "object":
        ok = isinstance(value, dict)
    elif expected_type == "array":
        ok = isinstance(value, list)
    else:
        ok = True
    return ok
