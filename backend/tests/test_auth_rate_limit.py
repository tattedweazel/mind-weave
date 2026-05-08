"""Auth endpoint rate limit (in-process, no slowapi)."""

import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.core.auth_rate_limit import (
    AuthEndpointRateLimitMiddleware,
    build_auth_rate_limit_rules,
    build_workflow_run_rate_limit_rules,
    parse_per_minute_limit,
)


def test_parse_per_minute_limit():
    assert parse_per_minute_limit("30/minute") == (30, 60.0)
    assert parse_per_minute_limit(" 7 / minute ") == (7, 60.0)


def test_parse_invalid_raises():
    with pytest.raises(ValueError, match="Invalid rate limit"):
        parse_per_minute_limit("bogus")


def test_build_rules_paths():
    rules = build_auth_rate_limit_rules("1/minute", "2/minute", "3/minute", "4/minute")
    assert ("POST", "/api/v1/auth/login", 1, 60.0) in rules


def test_workflow_run_middleware_429_and_shared_bucket_per_ip():
    """POST run/run_stream share one counter per IP (not per workflow id)."""

    async def ok(_):
        return PlainTextResponse("ok")

    p1 = "/api/v1/workflow-definitions/11111111-1111-1111-1111-111111111111/run"
    p2 = "/api/v1/workflow-definitions/22222222-2222-2222-2222-222222222222/run"
    inner = Starlette(
        routes=[
            Route(p1, ok, methods=["POST"]),
            Route(p2, ok, methods=["POST"]),
        ]
    )
    app = AuthEndpointRateLimitMiddleware(
        inner,
        rules=build_workflow_run_rate_limit_rules("1/minute"),
        clock=lambda: 3000.0,
    )
    client = TestClient(app)
    assert client.post(p1).status_code == 200
    assert client.post(p2).status_code == 429


def test_middleware_returns_429_after_limit():
    async def ok(_):
        return PlainTextResponse("ok")

    inner = Starlette(routes=[Route("/api/v1/auth/login", ok, methods=["POST"])])
    app = AuthEndpointRateLimitMiddleware(
        inner,
        rules=[("POST", "/api/v1/auth/login", 1, 60.0)],
        clock=lambda: 1000.0,
    )
    client = TestClient(app)
    assert client.post("/api/v1/auth/login").status_code == 200
    assert client.post("/api/v1/auth/login").status_code == 429
