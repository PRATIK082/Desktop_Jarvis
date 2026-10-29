"""JARVIS AI sidecar entry point.

Starts the FastAPI app on 127.0.0.1 with a per-launch ephemeral port and auth
token (passed by the Tauri host via JARVIS_* environment variables). Installs
graceful shutdown signal handlers and runs startup dependency checks.
"""

from __future__ import annotations

import signal
import sys

import uvicorn

from jarvis.api.app import create_app
from jarvis.config import settings
from jarvis.lifecycle import lifecycle
from jarvis.telemetry.logger import get_logger, log_event

logger = get_logger("jarvis.main")
app = create_app()


def _install_signal_handlers() -> None:
    """Install graceful shutdown handlers."""

    def _handler(signum, frame):  # noqa: ARG001
        log_event(
            "jarvis.main",
            "signal_received",
            level="warn",
            details={"signal": signum},
        )
        lifecycle.request_shutdown()

    try:
        signal.signal(signal.SIGTERM, _handler)
    except (AttributeError, OSError):
        pass
    try:
        signal.signal(signal.SIGINT, _handler)
    except (AttributeError, OSError):
        pass


def main() -> None:
    # Install signal handlers for graceful shutdown.
    _install_signal_handlers()
    lifecycle.install_signal_handlers()

    # Boot -> checking_dependencies.
    result = lifecycle.start()
    if not result.ok:
        log_event(
            "jarvis.main",
            "start_failed",
            level="error",
            details={"error": result.error_code, "message": result.message},
        )

    log_event(
        "jarvis.main",
        "starting",
        level="info",
        details={
            "host": settings.host,
            "port": settings.port,
            "auth_token_set": bool(settings.auth_token),
        },
    )

    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
        access_log=False,  # structured logging via jarvis.telemetry instead
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log_event("jarvis.main", "keyboard_interrupt", level="info")
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001 — crash recovery boundary
        lifecycle.record_crash(exc)
        logger.exception("sidecar crashed")
        sys.exit(1)
