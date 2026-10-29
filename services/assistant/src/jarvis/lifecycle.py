"""Sidecar lifecycle management (Agent.md Phase 2).

Handles:
- Startup dependency checks (Ollama health, model availability)
- Sidecar state machine (booting -> checking_dependencies -> idle/offline/degraded/error)
- Graceful shutdown on SIGTERM/SIGINT
- Uptime tracking
- Crash-recovery logging (no secrets)
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import signal
import time
from dataclasses import dataclass, field

from jarvis.api.ollama import OllamaClient
from jarvis.config import settings
from jarvis.state import (
    BOOTING,
    CHECKING_DEPENDENCIES,
    DEGRADED,
    ERROR,
    IDLE,
    OFFLINE,
    StateMachine,
    TransitionResult,
)
from jarvis.telemetry.logger import get_logger, log_event

logger = get_logger("jarvis.lifecycle")


@dataclass
class DependencyCheck:
    name: str
    ok: bool
    detail: str = ""
    error_code: str = ""


@dataclass
class SidecarLifecycle:
    """Manages the sidecar process lifecycle."""

    state_machine: StateMachine = field(default_factory=StateMachine)
    start_time: float | None = None
    ollama_client: OllamaClient | None = None
    dependency_checks: list[DependencyCheck] = field(default_factory=list)
    _shutdown_requested: bool = False

    # ------------------------------------------------------------------ start
    def start(self) -> TransitionResult:
        """Boot the sidecar: record start time, enter booting state."""
        self.start_time = time.time()
        result = self.state_machine.transition(CHECKING_DEPENDENCIES)
        if not result.ok:
            log_event(
                "jarvis.lifecycle",
                "start_rejected",
                level="error",
                details={
                    "from": result.from_state,
                    "to": CHECKING_DEPENDENCIES,
                    "error": result.error_code,
                },
            )
        return result

    # --------------------------------------------------------------- deps
    def check_dependencies(self) -> TransitionResult:
        """Run startup dependency checks. Returns transition to idle/degraded/error."""
        checks: list[DependencyCheck] = []

        # Ollama health
        ollama_ok, ollama_detail, ollama_code = self._check_ollama()
        checks.append(DependencyCheck("ollama", ollama_ok, ollama_detail, ollama_code))

        self.dependency_checks = checks
        critical_ok = all(c.ok for c in checks if c.name == "ollama")

        if critical_ok:
            result = self.state_machine.transition(IDLE)
        elif any(c.ok for c in checks):
            result = self.state_machine.transition(DEGRADED)
        else:
            result = self.state_machine.transition(ERROR)

        log_event(
            "jarvis.lifecycle",
            "dependency_check",
            level="info" if result.ok else "warn",
            details={
                "to": result.to_state,
                "checks": [{"name": c.name, "ok": c.ok, "detail": c.detail} for c in checks],
            },
        )
        return result

    def _check_ollama(self) -> tuple[bool, str, str]:
        """Check Ollama availability. Returns (ok, detail, error_code)."""
        if self.ollama_client is None:
            self.ollama_client = OllamaClient(
                base_url=settings.ollama_base_url,
                timeout_s=settings.ollama_timeout_s,
            )
        try:
            # Run the async health_check in a separate thread to avoid
            # "asyncio.run() cannot be called from a running event loop"
            # when uvicorn's event loop is already active.
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run, self.ollama_client.health_check()
                )
                healthy = future.result()
        except Exception as exc:  # noqa: BLE001 — report, don't crash
            return False, f"ollama check failed: {exc}", "ollama_check_error"
        else:
            if healthy:
                return True, "ollama reachable", ""
            return False, "ollama not reachable", "ollama_unavailable"

    # --------------------------------------------------------------- health
    def health_summary(self) -> dict[str, object]:
        """Return a sanitized health summary (no secrets, no conversation content)."""
        uptime_ms = None
        if self.start_time is not None:
            uptime_ms = (time.time() - self.start_time) * 1000
        return {
            "status": self.state_machine.state,
            "uptime_ms": uptime_ms,
            "ollama_healthy": any(
                c.name == "ollama" and c.ok for c in self.dependency_checks
            ),
            "dependency_checks": [
                {"name": c.name, "ok": c.ok, "detail": c.detail}
                for c in self.dependency_checks
            ],
        }

    # --------------------------------------------------------------- shutdown
    def request_shutdown(self) -> None:
        """Signal that shutdown has been requested (graceful)."""
        self._shutdown_requested = True
        log_event("jarvis.lifecycle", "shutdown_requested", level="info")

    def is_shutdown_requested(self) -> bool:
        return self._shutdown_requested

    def shutdown(self) -> TransitionResult:
        """Graceful shutdown: transition to offline."""
        result = self.state_machine.transition(OFFLINE)
        log_event(
            "jarvis.lifecycle",
            "shutdown",
            level="info",
            details={"to": result.to_state, "ok": result.ok},
        )
        return result

    # --------------------------------------------------------------- crash
    def record_crash(self, exc: BaseException) -> None:
        """Log a crash (sanitized, no secrets) and move to error state."""
        log_event(
            "jarvis.lifecycle",
            "crash",
            level="error",
            details={"error_type": type(exc).__name__, "message": str(exc)[:200]},
        )
        self.state_machine.transition(ERROR)

    # --------------------------------------------------------------- restart
    def restart(self) -> TransitionResult:
        """Restart the sidecar: reset state and re-run dependency checks."""
        log_event("jarvis.lifecycle", "restart", level="info")
        self.start_time = time.time()
        self.dependency_checks = []
        self._shutdown_requested = False
        self.state_machine = StateMachine(initial_state=BOOTING)
        return self.state_machine.transition(CHECKING_DEPENDENCIES)

    # --------------------------------------------------------------- signals
    def install_signal_handlers(self) -> None:
        """Install graceful shutdown handlers for SIGTERM and SIGINT."""

        def _handler(signum: int, frame: object) -> None:  # noqa: ARG001
            log_event(
                "jarvis.lifecycle",
                "signal_received",
                level="warn",
                details={"signal": signum},
            )
            self.request_shutdown()

        try:
            signal.signal(signal.SIGTERM, _handler)
        except (AttributeError, OSError):
            pass  # SIGTERM not available on all platforms
        try:
            signal.signal(signal.SIGINT, _handler)
        except (AttributeError, OSError):
            pass


# Singleton used by the API app and main entry point.
lifecycle = SidecarLifecycle()
