"""Regression tests for verdict-checked tools (E5).

Covers the E5 findings: ToolRegistry.execute() used to rebuild ToolResult
WITHOUT the verdict field (silently discarding tool-set verdicts); stubs
reported ok=True with did-nothing payloads; ListRunningApplications was an
empty stub; the orchestrator prompt had no verdict-speaking rules.

Hermetic: no live Ollama, no UI, no real side effects (open_application is
only tested against the allowlist gate + delegation verdict, never launched).
"""

from __future__ import annotations

from typing import Any

from jarvis.orchestration.orchestrator import Orchestrator
from jarvis.policy.engine import PolicyEngine, RiskLevel
from jarvis.providers.base import MockOllamaProvider as MockOllama
from jarvis.tools.registry import (
    Tool,
    ToolDefinition,
    ToolRegistry,
    ToolResult,
    build_default_registry,
)


def _definition(tool_id: str) -> ToolDefinition:
    return ToolDefinition(
        id=tool_id,
        description="test tool",
        input_schema={"type": "object", "properties": {}},
        result_schema={"type": "object"},
        risk_level=RiskLevel.LEVEL_1,
        permission_category="test",
        timeout_s=5.0,
    )


class _UnverifiedTool(Tool):
    """Test double: reports ok=True but verdict unverified."""

    def execute(self, args: dict[str, Any]) -> ToolResult:
        del args
        return ToolResult(
            tool_id=self.definition.id,
            ok=True,
            result={"note": "could not confirm"},
            verdict="unverified",
        )


def test_execute_preserves_tool_verdict() -> None:
    registry = ToolRegistry()
    registry.register(_UnverifiedTool(_definition("probe_unverified")))
    result = registry.execute("probe_unverified", {})
    assert result.verdict == "unverified"
    assert result.ok is True


def test_execute_default_verdict_done_when_ok() -> None:
    registry = build_default_registry()
    result = registry.execute("get_current_datetime", {})
    assert result.ok is True
    assert result.verdict == "done"


def test_list_running_applications_is_real() -> None:
    registry = build_default_registry()
    result = registry.execute("list_running_applications", {})
    assert result.ok is True, result
    apps = result.result.get("applications")
    assert isinstance(apps, list) and len(apps) > 0
    assert result.verdict == "done"


def test_memory_stub_verdict_unverified() -> None:
    registry = build_default_registry()
    result = registry.execute("search_local_memories", {"query": "test"})
    assert result.verdict == "unverified"
    assert result.message


def test_clipboard_read_verdict_ask() -> None:
    registry = build_default_registry()
    result = registry.execute("get_clipboard_text", {})
    assert result.verdict == "ask"
    assert result.message


def test_open_application_delegates_with_started_verdict() -> None:
    registry = build_default_registry()
    result = registry.execute("open_application", {"name": "notepad"})
    assert result.ok is True
    assert result.verdict == "started"
    assert result.message


def test_open_url_delegates_with_started_verdict() -> None:
    registry = build_default_registry()
    result = registry.execute("open_url", {"url": "https://example.com"})
    assert result.ok is True
    assert result.verdict == "started"


def test_notification_stub_verdict_started() -> None:
    registry = build_default_registry()
    result = registry.execute("show_desktop_notification", {"title": "t", "body": "b"})
    assert result.verdict == "started"


def test_scheduler_stub_verdict_ask() -> None:
    registry = build_default_registry()
    result = registry.execute("create_reminder", {"text": "x", "at": "tomorrow"})
    assert result.verdict == "ask"


def test_system_prompt_has_verdict_speaking_rules() -> None:
    orchestrator = Orchestrator(
        ollama=MockOllama(), registry=ToolRegistry(), policy=PolicyEngine()
    )
    prompt = orchestrator._system_prompt("conversation", {})
    for word in ("done", "unverified", "failed", "ask", "started"):
        assert word in prompt
    assert "never claim success" in prompt
