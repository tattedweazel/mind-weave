"""Tests for Workspace pipeline preview API, validation on PUT, and stage SSE events."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest

from app.domain.schemas.workspace_contracts import (
    CompositionPayload,
    IntentPayload,
    InterpretationPayload,
    ResponsePayloadContent,
    TurnOutcomeType,
)
from app.domain.services.workspace_runtime_service import WorkspaceRuntimeService
from app.domain.workspace.companion_pipeline_config import COMPANION_PIPELINE_KEY


async def _deterministic_session_summary(self, *, workspace, companion, session_row, turn_digest):
    _, stored_max, _ = self._session_memory_limits(workspace)
    prev = (session_row.active_summary or "").strip()
    session_row.active_summary = WorkspaceRuntimeService._deterministic_summary_merge(prev, turn_digest, stored_max)
    session_row.updated_at = datetime.now(timezone.utc)
    self.session.add(session_row)
    self.session.commit()
    self.session.refresh(session_row)


@pytest.fixture
def patch_workspace_llm(monkeypatch):
    """Avoid real LM Studio calls (same behavior as ``test_workspace_api``)."""

    async def fake_interpret(self, user_message, workspace, companion, *args, **kwargs):
        return InterpretationPayload(
            intent=IntentPayload(key="chat", summary=user_message[:120]),
            outcome_type=TurnOutcomeType.respond_directly,
            confidence=0.99,
            candidate_capabilities=[],
        )

    async def fake_compose(self, **kwargs):
        return (
            CompositionPayload(
                response_payload=ResponsePayloadContent(
                    response_type="conversational",
                    content="Hello back from test.",
                    structured_blocks=[],
                ),
                memory_candidates=[],
                debug={},
            ),
            [],
        )

    monkeypatch.setattr(WorkspaceRuntimeService, "_interpret", fake_interpret)
    monkeypatch.setattr(WorkspaceRuntimeService, "_compose_and_memory", fake_compose)
    monkeypatch.setattr(WorkspaceRuntimeService, "_refresh_active_summary", _deterministic_session_summary)


def _sse_events(stream_text: str) -> list[dict]:
    out: list[dict] = []
    for line in stream_text.split("\n"):
        if line.startswith("data: "):
            out.append(json.loads(line[6:].strip()))
    return out


def test_put_workspace_rejects_invalid_companion_pipeline(client):
    data = client.post("/api/v1/workspaces/bootstrap").json()
    wid = data["workspace"]["id"]
    bad = {
        "runtime_configuration": {
            COMPANION_PIPELINE_KEY: {
                "version": 1,
                "post_compose": [
                    {"id": "dup", "system_prompt": "a"},
                    {"id": "dup", "system_prompt": "b"},
                ],
            }
        }
    }
    r = client.put(f"/api/v1/workspaces/{wid}", json=bad)
    assert r.status_code == 422


def test_pipeline_preview_endpoint(client):
    data = client.post("/api/v1/workspaces/bootstrap").json()
    wid = data["workspace"]["id"]
    r = client.get(f"/api/v1/workspaces/{wid}/pipeline/preview")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "interpret_system" in body
    assert "compose_system" in body
    assert "session_summary_system" in body
    assert "models" in body
    assert body["models"].get("interpret") is None or isinstance(body["models"].get("interpret"), str)
    assert isinstance(body["post_compose"], list)


def test_pipeline_preview_uses_default_interpret_base(client):
    from app.domain.services.workspace_runtime_service import DEFAULT_INTERPRET_BASE_PROMPT

    data = client.post("/api/v1/workspaces/bootstrap").json()
    wid = data["workspace"]["id"]
    r = client.get(f"/api/v1/workspaces/{wid}/pipeline/preview")
    assert r.status_code == 200
    body = r.json()
    assert DEFAULT_INTERPRET_BASE_PROMPT[:80] in body["interpret_system"]


def test_pipeline_preview_uses_custom_interpret_base(client):
    from app.domain.services.workspace_runtime_service import DEFAULT_INTERPRET_BASE_PROMPT

    data = client.post("/api/v1/workspaces/bootstrap").json()
    wid = data["workspace"]["id"]
    custom_base = "You are a custom classifier. Follow the schema."
    rc = {
        COMPANION_PIPELINE_KEY: {
            "version": 1,
            "stages": {
                "interpret": {
                    "enabled": True,
                    "system_prompt_base": custom_base,
                }
            },
        }
    }
    r = client.put(f"/api/v1/workspaces/{wid}", json={"runtime_configuration": rc})
    assert r.status_code == 200
    r = client.get(f"/api/v1/workspaces/{wid}/pipeline/preview")
    assert r.status_code == 200
    body = r.json()
    assert custom_base in body["interpret_system"]
    assert DEFAULT_INTERPRET_BASE_PROMPT[:80] not in body["interpret_system"]


def test_stream_turn_includes_stage_events(client, patch_workspace_llm):
    data = client.post("/api/v1/workspaces/bootstrap").json()
    wid = data["workspace"]["id"]
    sid = uuid.UUID(data["session"]["id"])
    with client.stream(
        "POST",
        f"/api/v1/workspaces/{wid}/sessions/{sid}/turns/stream",
        json={"message": "Hi"},
    ) as resp:
        assert resp.status_code == 200
        text = "".join(resp.iter_text())
    events = _sse_events(text)
    stages = [e for e in events if e.get("event") == "stage"]
    assert stages
    labels = {(e.get("stage"), e.get("status")) for e in stages}
    assert ("interpret", "started") in labels
    assert ("interpret", "completed") in labels
    assert ("compose", "started") in labels
    assert ("compose", "completed") in labels
    assert ("session_summary", "completed") in labels
