"""Redact Workspace replay traces for storage (align with run_log_redaction patterns)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.run_log_redaction import redact_error_for_api, redact_prompt_like


def redact_workspace_trace(obj: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Return a copy safe to persist in workspace_replays."""
    if obj is None:
        return None
    return redact_prompt_like(dict(obj))


def sanitize_workspace_execution_for_console(obj: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Capability status/errors/outputs for Workspace Console (URLs stripped from errors)."""
    if obj is None:
        return None
    payload = obj.get("payload") if isinstance(obj, dict) else None
    if not isinstance(payload, dict):
        return {"execution_summary": None, "capability_results": []}
    raw_results = payload.get("capability_results") or []
    slim: List[Dict[str, Any]] = []
    for r in raw_results[:32]:
        if not isinstance(r, dict):
            continue
        err = r.get("error")
        if isinstance(err, str):
            err = redact_error_for_api(err)
        val = r.get("validation")
        if isinstance(val, dict):
            val = redact_prompt_like(dict(val))
        raw_output = r.get("output")
        out = redact_prompt_like(raw_output) if raw_output is not None else None
        slim.append(
            {
                "capability_key": r.get("capability_key"),
                "status": r.get("status"),
                "error": err,
                "validation": val,
                "output": out,
            }
        )
    return {
        "execution_summary": redact_prompt_like(payload.get("execution_summary"))
        if isinstance(payload.get("execution_summary"), dict)
        else payload.get("execution_summary"),
        "capability_results": slim,
    }
