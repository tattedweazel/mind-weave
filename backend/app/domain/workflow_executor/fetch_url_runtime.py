"""HTTP fetch for workflow ``fetch_url`` skill — httpx, cache key, response / error shapes."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.domain.workflow_executor.helpers import _format_exception

FETCH_METHODS = frozenset({"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"})


def normalize_headers(raw: Any) -> Dict[str, str]:
    if not raw or not isinstance(raw, dict):
        return {}
    out: Dict[str, str] = {}
    for k, v in raw.items():
        if k is None:
            continue
        ks = str(k).strip()
        if not ks:
            continue
        out[ks] = str(v) if v is not None else ""
    return dict(sorted(out.items()))


def compute_cache_key(url: str, method: str, headers: Dict[str, str]) -> str:
    u = url.strip()
    m = method.upper().strip()
    h = normalize_headers(headers)
    blob = json.dumps({"url": u, "method": m, "headers": h}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _utc_rfc3339() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _error_block(
    *,
    err_type: str,
    message: str,
    retryable: bool,
    duration_ms: int,
) -> Dict[str, Any]:
    return {
        "error": {"type": err_type, "message": message, "retryable": retryable},
        "fetched_at": _utc_rfc3339(),
        "duration_ms": duration_ms,
        "cached": False,
    }


def _response_headers_to_str_map(response: httpx.Response) -> Dict[str, str]:
    # Lowercase keys for stable downstream use (perception / JSON)
    return {str(k).lower(): str(v) for k, v in response.headers.items()}


async def perform_http_fetch(
    *,
    url: str,
    method: str,
    headers: Optional[Dict[str, str]],
    timeout_ms: Optional[int],
    max_body_bytes: Optional[int],
) -> Dict[str, Any]:
    """Return output.data-shaped dict: success fields or ``error`` object (step still succeeds)."""
    m = method.upper().strip()
    if m not in FETCH_METHODS:
        return _error_block(
            err_type="INVALID_METHOD",
            message=f"Unsupported HTTP method: {method!r}",
            retryable=False,
            duration_ms=0,
        )
    u = url.strip()
    if not u:
        return _error_block(
            err_type="INVALID_URL",
            message="URL is empty",
            retryable=False,
            duration_ms=0,
        )

    hdrs = normalize_headers(headers) if headers else {}
    timeout_s = (timeout_ms if timeout_ms is not None else settings.FETCH_URL_DEFAULT_TIMEOUT_MS) / 1000.0
    cap = max_body_bytes if max_body_bytes is not None else settings.FETCH_URL_MAX_BODY_BYTES

    t0 = time.perf_counter()

    timeout = httpx.Timeout(timeout_s)
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=timeout) as client:
            try:
                async with client.stream(
                    m,
                    u,
                    headers=hdrs or None,
                    follow_redirects=True,
                ) as response:
                    chunks: List[bytes] = []
                    total = 0
                    async for part in response.aiter_bytes():
                        total += len(part)
                        if total > cap:
                            elapsed_ms = int((time.perf_counter() - t0) * 1000)
                            return _error_block(
                                err_type="BODY_TOO_LARGE",
                                message=f"Response body exceeds {cap} bytes",
                                retryable=False,
                                duration_ms=elapsed_ms,
                            )
                        chunks.append(part)
                    body_bytes = b"".join(chunks)
                    enc = response.encoding or "utf-8"
                    try:
                        body_text = body_bytes.decode(enc, errors="replace")
                    except LookupError:
                        body_text = body_bytes.decode("utf-8", errors="replace")
                    elapsed_ms = int((time.perf_counter() - t0) * 1000)
                    return {
                        "status_code": response.status_code,
                        "final_url": str(response.url),
                        "headers": _response_headers_to_str_map(response),
                        "body": body_text,
                        "fetched_at": _utc_rfc3339(),
                        "duration_ms": elapsed_ms,
                        "cached": False,
                    }
            except httpx.InvalidURL as e:
                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                return _error_block(
                    err_type="INVALID_URL",
                    message=str(e) or "Invalid URL",
                    retryable=False,
                    duration_ms=elapsed_ms,
                )
            except httpx.TimeoutException as e:
                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                return _error_block(
                    err_type="TIMEOUT",
                    message=_format_exception(e),
                    retryable=True,
                    duration_ms=elapsed_ms,
                )
            except httpx.ConnectError as e:
                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                return _error_block(
                    err_type="CONNECTION",
                    message=_format_exception(e),
                    retryable=True,
                    duration_ms=elapsed_ms,
                )
            except httpx.NetworkError as e:
                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                return _error_block(
                    err_type="CONNECTION",
                    message=_format_exception(e),
                    retryable=True,
                    duration_ms=elapsed_ms,
                )
            except httpx.RequestError as e:
                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                msg = _format_exception(e)
                if "ssl" in msg.lower() or "tls" in msg.lower() or "certificate" in msg.lower():
                    err_t = "TLS"
                    retry = False
                else:
                    err_t = "UNKNOWN"
                    retry = True
                return _error_block(
                    err_type=err_t,
                    message=msg,
                    retryable=retry,
                    duration_ms=elapsed_ms,
                )
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return _error_block(
            err_type="UNKNOWN",
            message=_format_exception(e),
            retryable=False,
            duration_ms=elapsed_ms,
        )


def strip_cached_flag_for_storage(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Persist cache row without ``cached`` so reads can force ``cached: True``."""
    out = dict(payload)
    out["cached"] = False
    return out


def merge_cached_response(stored: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(stored)
    out["cached"] = True
    return out
