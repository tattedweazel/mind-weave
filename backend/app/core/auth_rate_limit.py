"""
In-process rate limiting for auth POST endpoints (SE-007) and workflow
execution POSTs (`/run`, `/run_stream`, SE-029).

Uses a fixed window per client IP — no third-party dependency. For multi-worker
deployments, put a reverse proxy or Redis-based limiter in front instead.
"""

from __future__ import annotations

import re
import time
from collections import defaultdict
from collections.abc import Awaitable
from typing import Callable, Pattern, Union

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

# Exact path string or regex.fullmatch against normalized path (leading rule wins).
PathSpec = Union[str, Pattern[str]]
RateLimitRule = tuple[str, PathSpec, int, float]


def parse_per_minute_limit(spec: str) -> tuple[int, float]:
    """Parse strings like ``30/minute`` -> (30 requests, 60 second window)."""
    spec = spec.strip()
    m = re.match(r"^(\d+)\s*/\s*minute$", spec, re.IGNORECASE)
    if not m:
        raise ValueError(f"Invalid rate limit {spec!r}: expected '<integer>/minute', e.g. '30/minute'")
    return (int(m.group(1)), 60.0)


def build_auth_rate_limit_rules(
    login_limit: str,
    register_limit: str,
    refresh_limit: str,
    google_session_limit: str,
) -> list[RateLimitRule]:
    """Return (method, path_spec, max_hits, window_seconds) for each auth route."""
    paths = (
        (login_limit, "POST", "/api/v1/auth/login"),
        (register_limit, "POST", "/api/v1/auth/register"),
        (refresh_limit, "POST", "/api/v1/auth/refresh"),
        (google_session_limit, "POST", "/api/v1/auth/google/session"),
    )
    out: list[RateLimitRule] = []
    for spec, method, path in paths:
        n, w = parse_per_minute_limit(spec)
        out.append((method, path, n, w))
    return out


def build_workflow_run_rate_limit_rules(limit_spec: str) -> list[RateLimitRule]:
    """Rate limit POST .../run and .../run_stream per client IP (shared bucket, SE-029)."""
    n, w = parse_per_minute_limit(limit_spec)
    wf_pat = re.compile(r"^/api/v1/workflow-definitions/[^/]+/(?:run|run_stream)$")
    return [("POST", wf_pat, n, w)]


def build_workspace_turn_stream_rate_limit_rules(limit_spec: str) -> list[RateLimitRule]:
    """Rate limit Workspace turn stream + capability confirm-stream per client IP (same budget each)."""
    n, w = parse_per_minute_limit(limit_spec)
    stream_pat = re.compile(r"^/api/v1/workspaces/[^/]+/sessions/[^/]+/turns/stream$")
    confirm_pat = re.compile(r"^/api/v1/workspaces/[^/]+/sessions/[^/]+/turns/confirm-stream$")
    return [
        ("POST", stream_pat, n, w),
        ("POST", confirm_pat, n, w),
    ]


class AuthEndpointRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        rules: list[RateLimitRule],
        clock: Callable[[], float] | None = None,
    ):
        super().__init__(app)
        self._rules = rules
        self._clock = clock or time.monotonic
        self._hits: dict[tuple[str, str, str], list[float]] = defaultdict(list)

    @staticmethod
    def _client_ip(request: Request) -> str:
        if request.client:
            return request.client.host or "unknown"
        return "unknown"

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        path = request.url.path.rstrip("/") or "/"
        method = request.method.upper()
        ip = self._client_ip(request)
        now = self._clock()

        for rule_method, path_spec, limit, window in self._rules:
            if method != rule_method.upper():
                continue
            if isinstance(path_spec, Pattern):
                if path_spec.fullmatch(path) is None:
                    continue
                # One counter per IP for all URLs matched by this rule (not per workflow id).
                key = (ip, method, path_spec.pattern)
            else:
                if path != path_spec.rstrip("/"):
                    continue
                key = (ip, method, path)
            bucket = self._hits[key]
            cutoff = now - window
            bucket[:] = [t for t in bucket if t > cutoff]
            if len(bucket) >= limit:
                return JSONResponse(
                    {"detail": "Too many requests"},
                    status_code=429,
                )
            bucket.append(now)
            break

        return await call_next(request)
