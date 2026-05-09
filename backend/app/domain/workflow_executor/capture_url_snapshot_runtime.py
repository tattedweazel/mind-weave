"""Headless browser capture for ``capture_url_snapshot`` — Playwright, cache key, error shapes."""

from __future__ import annotations

import hashlib
import json
import re
import struct
import time
from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional, Tuple, cast
from urllib.parse import urlparse

_PNG_HDR = b"\x89PNG\r\n\x1a\n"


def _utc_rfc3339() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def compute_cache_key(
    url: str,
    full_page: bool,
    viewport_w: int,
    viewport_h: int,
    wait_until: str,
) -> str:
    u = url.strip()
    blo = json.dumps(
        {
            "url": u,
            "full_page": bool(full_page),
            "viewport_w": int(viewport_w),
            "viewport_h": int(viewport_h),
            "wait_until": str(wait_until).lower().strip(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(blo.encode("utf-8")).hexdigest()


def png_dimensions(png: bytes) -> Optional[Tuple[int, int]]:
    """Return (width, height) from a PNG by reading the IHDR chunk, or None if invalid."""
    if len(png) < 24 or not png.startswith(_PNG_HDR):
        return None
    # IHDR: length 13 at offset 8; width/height at 16, big-endian
    try:
        w, h = struct.unpack(">II", png[16:24])
        if w < 1 or h < 1:
            return None
        return (w, h)
    except struct.error:
        return None


def _error_data(*, err_type: str, message: str, retryable: bool, duration_ms: int) -> Dict[str, Any]:
    return {
        "error": {"type": err_type, "message": message, "retryable": retryable},
        "captured_at": _utc_rfc3339(),
        "duration_ms": duration_ms,
        "cached": False,
    }


def _normalize_url(url: str) -> Optional[str]:
    u = url.strip()
    if not u:
        return None
    p = urlparse(u)
    if p.scheme not in ("http", "https"):
        return None
    if not p.netloc:
        return None
    return u


def _classify_exception(exc: BaseException) -> tuple[str, bool]:
    name = type(exc).__name__
    mod = type(exc).__module__
    msg = str(exc) or name
    low = msg.lower()
    if mod.endswith("playwright._impl._errors") or "playwright" in mod:
        if "TargetClosed" in name or "Browser" in name and "close" in low:
            return "BROWSER_CLOSED", True
        if "Timeout" in name or "timeout" in low:
            return "NAVIGATION_TIMEOUT", True
    if "net::" in low or "err_" in low or "network" in low or "dns" in low or "econn" in low:
        return "NETWORK", True
    if "executable doesn't exist" in low or "chromium" in low and "install" in low:
        return "BROWSER_LAUNCH", False
    if "navigating" in low or "navigation" in low:
        return "NAVIGATION", True
    return "SCREENSHOT", True


def _truncate_message(msg: str, cap: int = 800) -> str:
    s = re.sub(r"\s+", " ", msg.strip())
    if len(s) <= cap:
        return s
    return s[: cap - 3] + "..."


async def perform_url_snapshot_capture(
    *,
    url: str,
    full_page: bool,
    viewport_width: int,
    viewport_height: int,
    wait_until: str,
    timeout_ms: int,
    max_png_bytes: int,
) -> Dict[str, Any]:
    """
    Return dict suitable for ``DictionaryNodeOutput.data``: success (image, final_url, …) or error block.

    On success, ``image`` is absent; caller attaches artifact id and dimensions from stored row.
    This function returns ``image`` placeholder with ``_png`` bytes key stripped before output — use ``bytes_out``.
    """
    t0 = time.perf_counter()

    u = _normalize_url(url)
    if u is None:
        return _error_data(
            err_type="INVALID_URL",
            message="URL must be a non-empty http or https URL",
            retryable=False,
            duration_ms=0,
        )

    wu = str(wait_until).lower().strip()
    if wu not in ("load", "domcontentloaded", "networkidle"):
        return _error_data(
            err_type="INVALID_WAIT",
            message=f"wait_until must be load, domcontentloaded, or networkidle (got {wait_until!r})",
            retryable=False,
            duration_ms=0,
        )

    if viewport_width < 1 or viewport_height < 1:
        return _error_data(
            err_type="INVALID_VIEWPORT",
            message="viewport width and height must be positive",
            retryable=False,
            duration_ms=0,
        )

    try:
        from playwright.async_api import async_playwright
    except ModuleNotFoundError:
        return _error_data(
            err_type="PLAYWRIGHT_MISSING",
            message=(
                "Playwright is not installed. Install the backend optional extra "
                "`url-snapshot` (e.g. `uv sync --extra url-snapshot` from `backend/`) "
                "then run `uv run playwright install chromium`. "
                "See docs/OPERATIONS.md#capture_url_snapshot--playwright."
            ),
            retryable=False,
            duration_ms=0,
        )

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    viewport={"width": int(viewport_width), "height": int(viewport_height)},
                )
                page = await context.new_page()
                to_ms = max(1000, int(timeout_ms))
                await page.goto(
                    u,
                    wait_until=cast(Literal["load", "domcontentloaded", "networkidle"], wu),
                    timeout=to_ms,
                )
                final_url = page.url
                png = await page.screenshot(
                    type="png",
                    full_page=bool(full_page),
                )
            finally:
                await browser.close()
    except Exception as exc:
        elapsed = int((time.perf_counter() - t0) * 1000)
        et, ret = _classify_exception(exc)
        return _error_data(
            err_type=et,
            message=_truncate_message(f"{et}: {exc}"),
            retryable=ret,
            duration_ms=elapsed,
        )

    if not isinstance(png, (bytes, bytearray)) or len(png) < 32:
        elapsed = int((time.perf_counter() - t0) * 1000)
        return _error_data(
            err_type="SCREENSHOT",
            message="Screenshot returned empty or invalid data",
            retryable=True,
            duration_ms=elapsed,
        )

    if len(png) > max_png_bytes:
        elapsed = int((time.perf_counter() - t0) * 1000)
        return _error_data(
            err_type="PAYLOAD_TOO_LARGE",
            message=f"PNG larger than {max_png_bytes} bytes",
            retryable=False,
            duration_ms=elapsed,
        )

    dims = png_dimensions(bytes(png))
    if dims is None:
        elapsed = int((time.perf_counter() - t0) * 1000)
        return _error_data(
            err_type="SCREENSHOT",
            message="Screenshot is not a valid PNG",
            retryable=True,
            duration_ms=elapsed,
        )
    width, height = dims

    elapsed = int((time.perf_counter() - t0) * 1000)
    return {
        "_png_bytes": bytes(png),
        "_width": width,
        "_height": height,
        "final_url": str(final_url),
        "captured_at": _utc_rfc3339(),
        "duration_ms": elapsed,
    }


def strip_internal_keys_for_output(data: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: v for k, v in data.items() if not k.startswith("_")}
    return out


def build_success_output_from_artifact(
    *,
    artifact_id: str,
    width: int,
    height: int,
    final_url: str,
    captured_at: str,
    duration_ms: int,
    cached: bool,
) -> Dict[str, Any]:
    return {
        "image": {
            "artifact_id": artifact_id,
            "mime_type": "image/png",
            "width": int(width),
            "height": int(height),
        },
        "final_url": final_url,
        "captured_at": captured_at,
        "duration_ms": int(duration_ms),
        "cached": bool(cached),
    }
