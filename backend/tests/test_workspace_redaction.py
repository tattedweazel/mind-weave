"""Tests for Workspace Console execution sanitization."""

from __future__ import annotations

from app.domain.workspace.workspace_redaction import sanitize_workspace_execution_for_console


def _make_execution(capability_results: list) -> dict:
    return {"payload": {"capability_results": capability_results, "execution_summary": {"total": 1}}}


def test_none_returns_none():
    assert sanitize_workspace_execution_for_console(None) is None


def test_missing_payload_returns_empty():
    result = sanitize_workspace_execution_for_console({})
    assert result == {"execution_summary": None, "capability_results": []}


def test_non_dict_payload_returns_empty():
    result = sanitize_workspace_execution_for_console({"payload": "not-a-dict"})
    assert result == {"execution_summary": None, "capability_results": []}


def test_output_included_and_redacted():
    obj = _make_execution([
        {
            "capability_key": "wf:abc",
            "status": "success",
            "error": None,
            "validation": {},
            "output": {
                "node_id": "stop1",
                "kind": "list",
                "data": [
                    {"id": "msg-1", "subject": "Hello", "snippet": "Preview"},
                    {"id": "msg-2", "subject": "World", "snippet": "More"},
                ],
            },
        }
    ])
    result = sanitize_workspace_execution_for_console(obj)
    cap = result["capability_results"][0]
    assert cap["capability_key"] == "wf:abc"
    assert cap["status"] == "success"
    out = cap["output"]
    assert out is not None
    assert out["node_id"] == "stop1"
    assert out["kind"] == "list"
    for item in out["data"]:
        assert item["id"].startswith("msg-")
        assert item["subject"] == "[redacted]"
        assert item["snippet"] == "[redacted]"


def test_output_none_stays_none():
    obj = _make_execution([
        {"capability_key": "wf:x", "status": "error", "error": "boom", "output": None}
    ])
    result = sanitize_workspace_execution_for_console(obj)
    assert result["capability_results"][0]["output"] is None


def test_output_absent_becomes_none():
    obj = _make_execution([
        {"capability_key": "wf:y", "status": "success"}
    ])
    result = sanitize_workspace_execution_for_console(obj)
    assert result["capability_results"][0]["output"] is None


def test_error_urls_stripped():
    obj = _make_execution([
        {
            "capability_key": "wf:z",
            "status": "error",
            "error": "Failed at https://api.google.com/v1/messages: 401",
        }
    ])
    result = sanitize_workspace_execution_for_console(obj)
    err = result["capability_results"][0]["error"]
    assert "https://" not in err
    assert "[url]" in err


def test_validation_redacted():
    obj = _make_execution([
        {
            "capability_key": "wf:v",
            "status": "error",
            "validation": {"prompt": "secret system prompt", "passed": False},
        }
    ])
    result = sanitize_workspace_execution_for_console(obj)
    val = result["capability_results"][0]["validation"]
    assert val["prompt"] == "[redacted]"
    assert val["passed"] is False


def test_caps_at_32_results():
    caps = [{"capability_key": f"wf:{i}", "status": "success"} for i in range(50)]
    obj = _make_execution(caps)
    result = sanitize_workspace_execution_for_console(obj)
    assert len(result["capability_results"]) == 32


def test_skips_non_dict_results():
    obj = _make_execution(["not-a-dict", {"capability_key": "wf:ok", "status": "success"}])
    result = sanitize_workspace_execution_for_console(obj)
    assert len(result["capability_results"]) == 1
    assert result["capability_results"][0]["capability_key"] == "wf:ok"


def test_execution_summary_dict_redacted():
    obj = {
        "payload": {
            "capability_results": [],
            "execution_summary": {"total": 1, "prompt": "sensitive"},
        }
    }
    result = sanitize_workspace_execution_for_console(obj)
    assert result["execution_summary"]["total"] == 1
    assert result["execution_summary"]["prompt"] == "[redacted]"


def test_execution_summary_non_dict_passed_through():
    obj = {
        "payload": {
            "capability_results": [],
            "execution_summary": "simple string",
        }
    }
    result = sanitize_workspace_execution_for_console(obj)
    assert result["execution_summary"] == "simple string"
