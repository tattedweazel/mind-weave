"""Unit tests for capture_url_snapshot cache key and PNG header parsing (no Playwright)."""

from __future__ import annotations

import base64

import pytest

from app.domain.workflow_executor.capture_url_snapshot_runtime import (
    compute_cache_key,
    perform_url_snapshot_capture,
    png_dimensions,
)


def test_compute_cache_key_stable_order():
    a = compute_cache_key("https://a.com", True, 1280, 720, "load")
    b = compute_cache_key("https://a.com", True, 1280, 720, "load")
    assert a == b
    c = compute_cache_key("https://a.com", False, 1280, 720, "load")
    assert c != a


def test_png_dimensions_minimal():
    assert png_dimensions(b"notapng") is None
    # Minimal 1x1 RGBA PNG
    b64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+lmfkAAAAASUVORK5CYII="
    )
    onex1 = base64.b64decode(b64)
    d = png_dimensions(onex1)
    assert d is not None
    w, h = d
    assert w >= 1 and h >= 1


@pytest.mark.asyncio
async def test_perform_url_snapshot_invalid_url():
    r = await perform_url_snapshot_capture(
        url="not-a-url",
        full_page=True,
        viewport_width=100,
        viewport_height=100,
        wait_until="load",
        timeout_ms=5000,
        max_png_bytes=1_000_000,
    )
    assert "error" in r
    assert r["error"]["type"] == "INVALID_URL"


@pytest.mark.asyncio
async def test_perform_url_snapshot_invalid_wait():
    r = await perform_url_snapshot_capture(
        url="https://example.com",
        full_page=True,
        viewport_width=100,
        viewport_height=100,
        wait_until="bogus",
        timeout_ms=5000,
        max_png_bytes=1_000_000,
    )
    assert "error" in r
    assert r["error"]["type"] == "INVALID_WAIT"
