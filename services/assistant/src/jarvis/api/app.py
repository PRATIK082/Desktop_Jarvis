"""FastAPI application factory.

Exposes:
- GET /health            (authenticated) — sidecar + Ollama health, uptime
- WebSocket /events      (authenticated) — streamed assistant events to UI
- POST /v1/chat          (authenticated) — typed chat entry point (Phase 3)
- POST /v1/shutdown      (authenticated) — graceful shutdown
- POST /v1/restart       (authenticated) — restart sidecar + re-check deps
- GET /v1/logs           (authenticated) — recent sanitized logs

All routes require the per-launch ephemeral auth token.
Sidecar binds to 127.0.0.1 only; never exposes an unauthenticated network service.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from jarvis.api.ollama import OllamaClient
from jarvis.api.security import (
    PayloadSizeMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
)
from jarvis.audio.providers import get_audio_status
from jarvis.config import settings
from jarvis.engines import get_engine_status
from jarvis.lifecycle import lifecycle
from jarvis.orchestration import Orchestrator, event_to_dict
from jarvis.orchestration.events import AssistantErrorEvent
from jarvis.policy.engine import PolicyEngine
from jarvis.telemetry.logger import get_logger, log_event
from jarvis.tools.registry import ToolRegistry, build_default_registry

logger = get_logger("jarvis.api")

_ollama_client: OllamaClient | None = None  # noqa: PLW0603 — module-level singleton
_registry: ToolRegistry | None = None  # noqa: PLW0603 — module-level singleton
_policy: PolicyEngine | None = None  # noqa: PLW0603 — module-level singleton
_orchestrator: Orchestrator | None = None  # noqa: PLW0603 — module-level singleton


class ChatRequest(BaseModel):
    user_input: str
    conversation_id: str
    request_id: str
    model: str | None = None


class SelectModelRequest(BaseModel):
    model: str


def _get_ollama() -> OllamaClient:
    global _ollama_client  # noqa: PLW0603 — module-level singleton
    if _ollama_client is None:
        _ollama_client = OllamaClient(
            base_url=settings.ollama_base_url,
            timeout_s=settings.ollama_timeout_s,
        )
    return _ollama_client


def _get_registry() -> ToolRegistry:
    global _registry  # noqa: PLW0603 — module-level singleton
    if _registry is None:
        _registry = build_default_registry()
    return _registry


def _get_policy() -> PolicyEngine:
    global _policy  # noqa: PLW0603 — module-level singleton
    if _policy is None:
        _policy = PolicyEngine()
    return _policy


def _get_orchestrator() -> Orchestrator:
    global _orchestrator  # noqa: PLW0603 — module-level singleton
    if _orchestrator is None:
        _orchestrator = Orchestrator(
            ollama=_get_ollama(),
            registry=_get_registry(),
            policy=_get_policy(),
            max_tool_iterations=3,
        )
    return _orchestrator


def _verify_token(authorization: str | None) -> None:
    token = _bearer(authorization)
    if token != settings.auth_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing sidecar auth token",
        )


def _bearer(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[len("bearer ") :]
    return authorization


def _auth_token(
    authorization: str | None = None,
    header: str | None = Header(default=None, alias="Authorization"),
) -> str | None:
    """Resolve the sidecar token from the Authorization header or ?authorization=.

    The UI sends `Authorization: Bearer <token>` on every REST fetch; older
    callers pass ?authorization= in the query string. Header wins when both
    are present. WebSocket /events keeps its own ?token= param (untouched).
    """
    return header if header is not None else authorization


def create_app() -> FastAPI:
    app = FastAPI(
        title="JARVIS AI Sidecar",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
    )

    _configure_cors(app)
    _configure_security(app)
    _configure_startup(app)
    _configure_health(app)
    _configure_events(app)
    _configure_chat(app)
    _configure_models(app)
    _configure_shutdown(app)
    _configure_restart(app)
    _configure_logs(app)

    return app


def _configure_cors(app: FastAPI) -> None:
    # CORS restricted to loopback dev origins + Tauri webview schemes only.
    # The Vite dev server runs on 127.0.0.1:5173, so the bare "http://127.0.0.1"
    # origin alone never matches and every fetch (/health, /v1/models, /v1/chat)
    # fails CORS while the WebSocket (no preflight) connects fine.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "tauri://localhost",
            "https://tauri.localhost",
        ],
        allow_origin_regex=r"https?://(127\.0\.0\.1|localhost)(:\d+)?",
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["authorization", "content-type"],
    )


def _configure_security(app: FastAPI) -> None:
    # Security middleware: rate limiting, payload size limits, security headers (CSP).
    # Order matters: PayloadSizeMiddleware first (reject large bodies early),
    # then RateLimitMiddleware, then SecurityHeadersMiddleware last.
    app.add_middleware(PayloadSizeMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)


def _configure_startup(app: FastAPI) -> None:
    @app.on_event("startup")
    async def _startup() -> None:
        result = lifecycle.check_dependencies()
        if not result.ok:
            log_event(
                "jarvis.api",
                "startup_degraded",
                level="warn",
                details={"to": result.to_state, "error": result.error_code},
            )

        # Warm up STT/TTS providers off the request path (first-use latency).
        def _warm_up() -> None:
            try:
                from jarvis.audio.pipeline import VoicePipeline  # noqa: PLC0415

                asyncio.run(VoicePipeline(_get_orchestrator()).warm_up_providers())
            except Exception as exc:  # noqa: BLE001 — warm-up is best-effort
                log_event(
                    "jarvis.api",
                    "audio_warmup_skipped",
                    level="debug",
                    details={"error": str(exc)},
                )

        threading.Thread(target=_warm_up, daemon=True).start()


def _configure_health(app: FastAPI) -> None:
    @app.get("/health")
    async def health(token: str | None = Depends(_auth_token)) -> dict[str, object]:
        _verify_token(token)
        summary = lifecycle.health_summary()
        # Refresh Ollama health on each request.
        try:
            ollama_ok = await _get_ollama().health_check()
            summary["ollama_healthy"] = ollama_ok
        except Exception:  # noqa: BLE001 — health check is best-effort
            summary["ollama_healthy"] = False
        summary["engine"] = get_engine_status()
        try:
            summary["audio"] = get_audio_status()
        except Exception:  # noqa: BLE001 — audio status is best-effort
            summary["audio"] = {
                "stt_provider": settings.stt_provider,
                "tts_provider": settings.tts_provider,
            }
        return summary


def _configure_events(app: FastAPI) -> None:
    @app.websocket("/events")
    async def events(websocket: WebSocket, token: str | None = None) -> None:
        _verify_token(token)
        await websocket.accept()
        orchestrator = _get_orchestrator()
        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    msg = json.loads(raw)
                except (ValueError, TypeError):
                    continue
                if not isinstance(msg, dict):
                    continue
                mtype = msg.get("type")
                if mtype == "user_input":
                    text = str(msg.get("text", ""))
                    conversation_id = str(msg.get("conversation_id", "web-turn"))
                    request_id = str(msg.get("request_id", ""))
                    if not text.strip() or not request_id:
                        continue
                    try:
                        ws_model = msg.get("model")
                        async for event in orchestrator.run_turn(
                            user_input=text,
                            conversation_id=conversation_id,
                            request_id=request_id,
                            model=str(ws_model) if ws_model else None,
                        ):
                            await websocket.send_text(json.dumps(event_to_dict(event)))
                    except Exception:  # noqa: BLE001 — per-turn safety net, logged below
                        logger.exception("ws_turn_failed")
                elif mtype == "approval":
                    try:
                        orchestrator.set_approval(
                            str(msg.get("request_id", "")),
                            str(msg.get("decision", "")),
                        )
                    except (ValueError, TypeError, AttributeError):
                        continue
        except WebSocketDisconnect:
            return


def _configure_chat(app: FastAPI) -> None:
    @app.post("/v1/chat")
    async def chat(
        token: str | None = Depends(_auth_token),
        body: ChatRequest | None = None,
    ) -> dict[str, object]:
        _verify_token(token)
        if body is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="request body required",
            )
        orchestrator = _get_orchestrator()
        try:
            events = [
                event_to_dict(event)
                async for event in orchestrator.run_turn(
                    user_input=body.user_input,
                    conversation_id=body.conversation_id,
                    request_id=body.request_id,
                    model=body.model,
                )
            ]
        except Exception as exc:  # noqa: BLE001 — chat-level safety net
            logger.exception(
                "chat_turn_failed",
                extra={"request_id": body.request_id, "error": str(exc)},
            )
            events = [
                event_to_dict(
                    AssistantErrorEvent(
                        code="internal_error",
                        message="An internal error occurred while processing your request.",
                        recoverable=True,
                        retry_available=True,
                        request_id=body.request_id,
                        conversation_id=body.conversation_id,
                    )
                )
            ]
        return {
            "status": "ok",
            "request_id": body.request_id,
            "events": events,
            "count": len(events),
        }


def _configure_models(app: FastAPI) -> None:
    @app.get("/v1/models")
    async def models(token: str | None = Depends(_auth_token)) -> dict[str, object]:
        _verify_token(token)
        try:
            installed = await _get_ollama().list_models()
            healthy = True
        except Exception:  # noqa: BLE001 — models listing is best-effort
            installed = []
            healthy = False
        return {
            "models": installed,
            "selected": settings.ollama_chat_model or "",
            "healthy": healthy,
        }

    @app.post("/v1/models/select")
    async def select_model(
        token: str | None = Depends(_auth_token),
        body: SelectModelRequest | None = None,
    ) -> dict[str, object]:
        _verify_token(token)
        if body is None or not body.model.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="model name required",
            )
        name = body.model.strip()
        try:
            installed = await _get_ollama().list_models()
        except Exception:  # noqa: BLE001 — selection proceeds best-effort
            installed = []
        if installed and name not in installed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"model not installed: {name}",
            )
        settings.ollama_chat_model = name
        return {"status": "ok", "selected": name}


def _configure_shutdown(app: FastAPI) -> None:
    @app.post("/v1/shutdown")
    async def shutdown(token: str | None = Depends(_auth_token)) -> dict[str, object]:
        _verify_token(token)
        lifecycle.request_shutdown()
        result = lifecycle.shutdown()
        return {
            "status": "shutting_down" if result.ok else "shutdown_failed",
            "ok": result.ok,
        }


def _configure_restart(app: FastAPI) -> None:
    @app.post("/v1/restart")
    async def restart(token: str | None = Depends(_auth_token)) -> dict[str, object]:
        _verify_token(token)
        result = lifecycle.restart()
        if result.ok:
            result = lifecycle.check_dependencies()
        return {
            "status": "restarting" if result.ok else "restart_failed",
            "ok": result.ok,
            "state": lifecycle.state_machine.state,
        }


def _configure_logs(app: FastAPI) -> None:
    @app.get("/v1/logs")
    async def logs(
        token: str | None = Depends(_auth_token),
        lines: int = 50,
    ) -> dict[str, object]:
        _verify_token(token)
        # Read the rotating log file tail (sanitized by the logger already).
        log_path = os.path.join("logs", "jarvis.log")
        result: list[str] = []
        try:
            with open(log_path, encoding="utf-8") as fh:
                all_lines = fh.readlines()
                result = all_lines[-max(1, min(lines, 500)) :]
        except FileNotFoundError:
            result = ["no log file yet"]
        except OSError:
            result = ["could not read logs"]
        return {"lines": result, "count": len(result)}
