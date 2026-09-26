"""Tunnel-ready security: headers, API-docs toggle, per-IP rate limiting.

Everything here is env-gated and inert by default, so plain LAN use is
unchanged. The Cloudflare day looks like this:

    TUNNEL_MODE=true   # preset for life behind a Cloudflare Tunnel

which flips the secure defaults: /docs off (unless DOCS_ENABLED=true),
HSTS on (TLS is terminated at Cloudflare), and the container entrypoint
trusts the tunnel's proxy headers so rate limiting sees real client IPs.

Knobs (all optional):
    TUNNEL_MODE=true|false      default false
    DOCS_ENABLED=true|false     default: on normally, off in tunnel mode
    RATE_LIMIT_PER_MINUTE=N     per-IP cap on /api/* (default 1200, 0 disables)
"""

from __future__ import annotations

import os
import time
from collections import deque

from fastapi import Request
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware

_DOC_PATHS = ("/docs", "/redoc", "/openapi.json")
_HEALTH_PATHS = ("/api/health",)


def _env_flag(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def tunnel_mode() -> bool:
    return _env_flag("TUNNEL_MODE", False)


def docs_enabled() -> bool:
    """API docs on by default; off in tunnel mode unless explicitly enabled."""
    return _env_flag("DOCS_ENABLED", not tunnel_mode())


def rate_limit_per_minute() -> int:
    try:
        return max(0, int(os.environ.get("RATE_LIMIT_PER_MINUTE", "1200")))
    except ValueError:
        return 1200


def _client_ip(request: Request) -> str:
    # In tunnel mode uvicorn runs with --proxy-headers, so client.host is real.
    return request.client.host if request.client else "unknown"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Sensible headers on every response; also gates /docs when disabled."""

    async def dispatch(self, request: Request, call_next):
        if request.url.path in _DOC_PATHS and not docs_enabled():
            resp: PlainTextResponse = PlainTextResponse("Not Found", status_code=404)
        else:
            resp = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "SAMEORIGIN"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if tunnel_mode():
            # TLS is terminated at Cloudflare in tunnel mode.
            resp.headers["Strict-Transport-Security"] = "max-age=31536000"
        return resp


class RateLimitMiddleware(BaseHTTPMiddleware):
    """In-memory per-IP sliding-window limiter for /api/* (health exempt)."""

    def __init__(self, app, exempt_paths: tuple[str, ...] = _HEALTH_PATHS):
        super().__init__(app)
        self.exempt = exempt_paths
        self._hits: dict[str, deque[float]] = {}

    async def dispatch(self, request: Request, call_next):
        limit = rate_limit_per_minute()
        path = request.url.path
        if limit and path.startswith("/api/") and path not in self.exempt:
            now = time.monotonic()
            bucket = self._hits.setdefault(_client_ip(request), deque())
            while bucket and bucket[0] <= now - 60:
                bucket.popleft()
            if len(bucket) >= limit:
                return JSONResponse(
                    {"detail": "Rate limit exceeded, slow down."},
                    status_code=429,
                    headers={"Retry-After": "60"},
                )
            bucket.append(now)
            if len(self._hits) > 10_000:  # pathological IP count; start over
                self._hits.clear()
        return await call_next(request)
