"""Security middleware for the JARVIS sidecar (Agent.md §15).

Provides:
- Payload-size limits (DoS protection via oversized requests)
- Rate limiting on expensive routes (in-memory, per-IP)
- Strict Content Security Policy (no remote scripts)
- Request ID tracking
- Security headers
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from collections.abc import Callable
from typing import Any, cast

from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from jarvis.config import settings
from jarvis.telemetry.logger import get_logger, log_event

logger = get_logger("jarvis.security")

# Maximum request body size in bytes (default 1 MB). Chat requests are small
# JSON payloads; anything larger is rejected to prevent DoS.
MAX_REQUEST_BODY: int = getattr(settings, "max_request_body_bytes", 1_048_576)

# Rate limit configuration: (max_requests, window_seconds)
RATE_LIMITS: dict[str, tuple[int, int]] = {
    "/v1/chat": (30, 60),        # 30 chat requests per minute
    "/v1/shutdown": (5, 60),     # 5 shutdowns per minute
    "/v1/restart": (5, 60),      # 5 restarts per minute
    "/v1/logs": (60, 60),        # 60 log reads per minute
}

# In-memory rate limiter state: path -> { client_id -> deque of timestamps }
_rate_limits: dict[str, dict[str, deque[float]]] = defaultdict(
    lambda: defaultdict(deque)
)


def _client_id(request: Request) -> str:
    """Best-effort client identifier for rate limiting.

    Since the sidecar binds to 127.0.0.1 only, all clients are local. We use
    the request header `x-forwarded-for` if present (set by a trusted proxy),
    otherwise fall back to a constant. In production behind a reverse proxy
    this would be the real client IP.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return "local"


def _is_rate_limited(path: str, client_id: str) -> bool:
    now = time.monotonic()
    window = RATE_LIMITS.get(path)
    if window is None:
        return False
    max_requests, window_s = window
    timestamps = _rate_limits[path][client_id]
    # Evict timestamps outside the window.
    cutoff = now - window_s
    while timestamps and timestamps[0] < cutoff:
        timestamps.popleft()
    if len(timestamps) >= max_requests:
        return True
    timestamps.append(now)
    return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    """In-memory rate limiter for expensive routes."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Any]
    ) -> Response:
        path = request.url.path
        if path in RATE_LIMITS:
            client = _client_id(request)
            if _is_rate_limited(path, client):
                log_event(
                    "jarvis.security",
                    "rate_limit_exceeded",
                    level="warn",
                    details={"path": path, "client": client},
                )
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": "rate_limit_exceeded",
                        "message": "Too many requests. Please slow down.",
                    },
                )
        return cast(Response, await call_next(request))


class PayloadSizeMiddleware(BaseHTTPMiddleware):
    """Rejects request bodies larger than MAX_REQUEST_BODY."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Any]
    ) -> Response:
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                size = int(content_length)
            except ValueError:
                size = 0
            if size > MAX_REQUEST_BODY:
                log_event(
                    "jarvis.security",
                    "payload_too_large",
                    level="warn",
                    details={"path": request.url.path, "size": size},
                )
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={
                        "error": "payload_too_large",
                        "message": "Request body too large.",
                    },
                )
        return cast(Response, await call_next(request))


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Strict security headers including CSP."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Any]
    ) -> Response:
        response = await call_next(request)
        # Content-Security-Policy: no remote scripts, same-origin only.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self' ws://127.0.0.1:8765; "
            "frame-ancestors 'none';"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        # Request ID for tracing.
        request_id = request.headers.get("x-request-id")
        if not request_id:
            request_id = str(uuid.uuid4())
        response.headers["x-request-id"] = request_id
        return cast(Response, response)
