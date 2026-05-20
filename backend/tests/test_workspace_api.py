"""Tests for Companion / Workspace APIs (LLM calls mocked via runtime patches)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlmodel import Session, select

from app.core.config import settings
from app.domain.schemas.outputs import StopNodeOutput
from app.domain.schemas.workflow_run import NodeRunResult, WorkflowRunResult
from app.domain.schemas.workspace_contracts import (
    CandidateCapability,
    CapabilityRunResult,
    CompositionPayload,
    ExecutionPayload,
    IntentPayload,
    InterpretationPayload,
    ResponsePayloadContent,
    TurnOutcomeType,
)
from app.domain.services.workflow_executor import WorkflowExecutor
from app.domain.services.workspace_runtime_service import WorkspaceRuntimeService
from app.persistence.tables import (
    Companion,
    GoogleWorkflowConnection,
    User,
    Workspace,
    WorkspaceSession,
    WorkspaceTurn,
)
from app.providers.base import ProviderResponse


async def deterministic_workspace_session_summary_refresh(
    self,
    *,
    workspace,
    companion,
    session_row,
    turn_digest,
):
    """Avoid real LLM for `_refresh_active_summary` in tests that complete a persisted turn."""
    _, stored_max, _ = self._session_memory_limits(workspace)
    prev = (session_row.active_summary or "").strip()
    session_row.active_summary = WorkspaceRuntimeService._deterministic_summary_merge(prev, turn_digest, stored_max)
    session_row.updated_at = datetime.now(timezone.utc)
    self.session.add(session_row)
    self.session.commit()
    self.session.refresh(session_row)


_MINIMAL_GRAPH = {
    "nodes": [
        {
            "id": "n_start",
            "kind": "start",
            "label": "Start",
            "data": {"text": ""},
            "position": {"x": 0, "y": 0},
        },
        {
            "id": "n_str",
            "kind": "primitive",
            "primitive_type": "string",
            "label": "S",
            "data": {"text": "x"},
            "position": {"x": 0, "y": 0},
        },
        {
            "id": "n_stop",
            "kind": "stop",
            "label": "Stop",
            "data": {"required_outputs": [{"key": "output", "type": "string"}]},
            "position": {"x": 100, "y": 0},
        },
    ],
    "edges": [
        {"source": "n_start", "target": "n_str"},
        {"source": "n_str", "target": "n_stop"},
    ],
}


@pytest.fixture
def patch_workspace_llm(monkeypatch):
    """Avoid real LM Studio calls for workspace runtime."""

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
    monkeypatch.setattr(
        WorkspaceRuntimeService,
        "_refresh_active_summary",
        deterministic_workspace_session_summary_refresh,
    )


@pytest.fixture
def patch_workspace_session_summary_refresh(monkeypatch):
    """Use with custom `_interpret` / `_compose` patches when the turn persists (confirm-stream)."""
    monkeypatch.setattr(
        WorkspaceRuntimeService,
        "_refresh_active_summary",
        deterministic_workspace_session_summary_refresh,
    )


def _sse_events(stream_text: str) -> list[dict]:
    out: list[dict] = []
    for line in stream_text.split("\n"):
        if line.startswith("data: "):
            out.append(json.loads(line[6:].strip()))
    return out


def test_workspace_bootstrap_and_stream_turn(client, patch_workspace_llm, db_session: Session):
    r = client.post("/api/v1/workspaces/bootstrap")
    assert r.status_code == 200, r.text
    data = r.json()
    assert "companion" in data and "workspace" in data and "session" in data
    wid = data["workspace"]["id"]
    sid = uuid.UUID(data["session"]["id"])

    with client.stream(
        "POST",
        f"/api/v1/workspaces/{wid}/sessions/{sid}/turns/stream",
        json={"message": "Hi companion"},
    ) as resp:
        assert resp.status_code == 200
        text = "".join(resp.iter_text())
    assert "token" in text
    assert "done" in text

    turns = list(db_session.exec(select(WorkspaceTurn).where(WorkspaceTurn.session_id == sid)).all())
    assert len(turns) == 1
    assert turns[0].user_input == "Hi companion"


def test_two_workspace_sessions_have_independent_active_summary(client, patch_workspace_llm, db_session: Session):
    """Session memory (`active_summary`) is scoped per `workspace_sessions` row, not shared across ids."""
    data = client.post("/api/v1/workspaces/bootstrap").json()
    wid = data["workspace"]["id"]
    sid_a = uuid.UUID(data["session"]["id"])

    r_b = client.post(f"/api/v1/workspaces/{wid}/sessions", json={"title": "Thread B"})
    assert r_b.status_code == 201, r_b.text
    sid_b = uuid.UUID(r_b.json()["id"])

    marker_a = "UNIQUE_SESSION_A_MARKER_XYZ"
    marker_b = "UNIQUE_SESSION_B_MARKER_QRS"

    with client.stream(
        "POST",
        f"/api/v1/workspaces/{wid}/sessions/{sid_a}/turns/stream",
        json={"message": marker_a},
    ) as resp:
        assert resp.status_code == 200
        _ = "".join(resp.iter_text())

    with client.stream(
        "POST",
        f"/api/v1/workspaces/{wid}/sessions/{sid_b}/turns/stream",
        json={"message": marker_b},
    ) as resp:
        assert resp.status_code == 200
        _ = "".join(resp.iter_text())

    db_session.expire_all()
    sess_a = db_session.get(WorkspaceSession, sid_a)
    sess_b = db_session.get(WorkspaceSession, sid_b)
    assert sess_a is not None and sess_b is not None
    sum_a = sess_a.active_summary or ""
    sum_b = sess_b.active_summary or ""
    assert marker_a in sum_a
    assert marker_b in sum_b
    assert marker_a not in sum_b
    assert marker_b not in sum_a


def test_companion_get(client, patch_workspace_llm):
    client.post("/api/v1/workspaces/bootstrap")
    r = client.get("/api/v1/companion/")
    assert r.status_code == 200
    assert r.json()["name"]


def test_companion_put_partial_and_clear_persona(client, patch_workspace_llm, db_session: Session):
    client.post("/api/v1/workspaces/bootstrap")
    g = client.get("/api/v1/companion/").json()
    assert g.get("persona_id") is not None

    r = client.put("/api/v1/companion/", json={"name": "Q", "persona_id": None})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Q"
    assert body["persona_id"] is None

    row = db_session.exec(select(Companion).where(Companion.owner_user_id == uuid.UUID(body["owner_user_id"]))).first()
    assert row is not None
    assert row.persona_id is None
    assert row.name == "Q"


def test_workspace_disabled_returns_404(client, monkeypatch):
    disabled = settings.model_copy(update={"WORKSPACE_ENABLED": False})
    monkeypatch.setattr("app.api.v1.companion_api.settings", disabled)
    monkeypatch.setattr("app.api.v1.workspaces_api.settings", disabled)
    r = client.get("/api/v1/companion/")
    assert r.status_code == 404


def test_workspace_put_enabled_workflow_ids_and_rejects_unknown(client, patch_workspace_llm):
    wf = client.post(
        "/api/v1/workflow-definitions/",
        json={"name": "Ws Test WF", "graph": _MINIMAL_GRAPH},
    )
    assert wf.status_code == 201
    wf_id = wf.json()["id"]

    data = client.post("/api/v1/workspaces/bootstrap").json()
    wid = data["workspace"]["id"]
    assert data["workspace"]["enabled_workflow_ids"] == []

    r = client.put(f"/api/v1/workspaces/{wid}", json={"enabled_workflow_ids": [wf_id]})
    assert r.status_code == 200, r.text
    assert r.json()["enabled_workflow_ids"] == [wf_id]

    g = client.get(f"/api/v1/workspaces/{wid}")
    assert g.status_code == 200
    assert g.json()["enabled_workflow_ids"] == [wf_id]

    bad = client.put(f"/api/v1/workspaces/{wid}", json={"enabled_workflow_ids": [str(uuid.uuid4())]})
    assert bad.status_code == 422


def test_capability_proposal_no_turn_until_confirm(client, db_session: Session, monkeypatch):
    wf = client.post(
        "/api/v1/workflow-definitions/",
        json={"name": "Invoke Me", "graph": _MINIMAL_GRAPH},
    )
    assert wf.status_code == 201
    wf_id = wf.json()["id"]
    wf_uuid = uuid.UUID(wf_id)

    async def fake_interpret(self, user_message, workspace, companion, *args, **kwargs):
        return InterpretationPayload(
            intent=IntentPayload(key="run_wf", summary="run"),
            outcome_type=TurnOutcomeType.invoke_capabilities,
            confidence=0.95,
            candidate_capabilities=[
                CandidateCapability(
                    capability_key=f"wf:{wf_uuid}",
                    confidence=0.95,
                    input_bindings={"user_input": "hi"},
                )
            ],
        )

    monkeypatch.setattr(WorkspaceRuntimeService, "_interpret", fake_interpret)

    data = client.post("/api/v1/workspaces/bootstrap").json()
    wid = data["workspace"]["id"]
    sid = uuid.UUID(data["session"]["id"])
    assert client.put(f"/api/v1/workspaces/{wid}", json={"enabled_workflow_ids": [wf_id]}).status_code == 200
    assert client.put("/api/v1/companion/", json={"enabled_workflow_ids": [wf_id]}).status_code == 200

    with client.stream(
        "POST",
        f"/api/v1/workspaces/{wid}/sessions/{sid}/turns/stream",
        json={"message": "run the workflow"},
    ) as resp:
        assert resp.status_code == 200
        text = "".join(resp.iter_text())

    events = _sse_events(text)
    assert any(e.get("event") == "capability_proposal" for e in events)
    done = next(e for e in events if e.get("event") == "done")
    assert done.get("phase") == "proposal"
    assert done.get("proposal_id")

    turns = list(db_session.exec(select(WorkspaceTurn).where(WorkspaceTurn.session_id == sid)).all())
    assert len(turns) == 0

    sess = db_session.get(WorkspaceSession, sid)
    assert sess is not None
    assert (sess.transient_state or {}).get("capability_proposal", {}).get("id") == done["proposal_id"]


def test_confirm_capability_stream_runs_executor(
    client, db_session: Session, monkeypatch, patch_workspace_session_summary_refresh
):
    wf = client.post(
        "/api/v1/workflow-definitions/",
        json={"name": "Confirm Me", "graph": _MINIMAL_GRAPH},
    )
    assert wf.status_code == 201
    wf_id = wf.json()["id"]
    wf_uuid = uuid.UUID(wf_id)

    async def fake_interpret(self, user_message, workspace, companion, *args, **kwargs):
        return InterpretationPayload(
            intent=IntentPayload(key="run_wf", summary="run"),
            outcome_type=TurnOutcomeType.invoke_capabilities,
            confidence=0.95,
            candidate_capabilities=[
                CandidateCapability(
                    capability_key=f"wf:{wf_uuid}",
                    confidence=0.95,
                    input_bindings={"user_input": "bound"},
                )
            ],
        )

    monkeypatch.setattr(WorkspaceRuntimeService, "_interpret", fake_interpret)

    overrides_seen: list[dict] = []

    async def fake_run(
        self,
        workflow,
        input_overrides=None,
        output_overrides_map=None,
        execution_stack=None,
        execution_time_zone=None,
    ):
        overrides_seen.append(dict(input_overrides or {}))
        return WorkflowRunResult(
            workflow_id=workflow.id,
            status="ok",
            node_results=[
                NodeRunResult(
                    node_id="n_stop",
                    status="ok",
                    output=StopNodeOutput(node_id="n_stop", text="final"),
                    step_number=3,
                ),
            ],
        )

    monkeypatch.setattr(WorkflowExecutor, "run", fake_run)

    async def fake_compose(self, **kwargs):
        return (
            CompositionPayload(
                response_payload=ResponsePayloadContent(
                    response_type="conversational",
                    content="OK from compose.",
                    structured_blocks=[],
                ),
                memory_candidates=[],
                debug={},
            ),
            [],
        )

    monkeypatch.setattr(WorkspaceRuntimeService, "_compose_and_memory", fake_compose)

    data = client.post("/api/v1/workspaces/bootstrap").json()
    wid = data["workspace"]["id"]
    sid = uuid.UUID(data["session"]["id"])
    assert client.put(f"/api/v1/workspaces/{wid}", json={"enabled_workflow_ids": [wf_id]}).status_code == 200
    assert client.put("/api/v1/companion/", json={"enabled_workflow_ids": [wf_id]}).status_code == 200

    with client.stream(
        "POST",
        f"/api/v1/workspaces/{wid}/sessions/{sid}/turns/stream",
        json={"message": "go"},
    ) as resp:
        text = "".join(resp.iter_text())
    proposal_id = next(e for e in _sse_events(text) if e.get("event") == "done")["proposal_id"]

    with client.stream(
        "POST",
        f"/api/v1/workspaces/{wid}/sessions/{sid}/turns/confirm-stream",
        json={"proposal_id": proposal_id, "cancel": False},
    ) as resp2:
        assert resp2.status_code == 200
        text2 = "".join(resp2.iter_text())
    assert "done" in text2
    done2 = next(e for e in _sse_events(text2) if e.get("event") == "done")
    assert done2.get("phase") == "completed"
    assert done2.get("turn_id")

    assert overrides_seen and overrides_seen[0].get("user_input") == "bound"

    turns = list(db_session.exec(select(WorkspaceTurn).where(WorkspaceTurn.session_id == sid)).all())
    assert len(turns) == 1

    sess = db_session.get(WorkspaceSession, sid)
    assert sess is not None
    assert "capability_proposal" not in (sess.transient_state or {})


def test_confirm_runs_same_workflow_twice_with_distinct_bindings(
    client, db_session: Session, monkeypatch, patch_workspace_session_summary_refresh
):
    wf = client.post(
        "/api/v1/workflow-definitions/",
        json={"name": "Twice Me", "graph": _MINIMAL_GRAPH},
    )
    assert wf.status_code == 201
    wf_id = wf.json()["id"]
    wf_uuid = uuid.UUID(wf_id)

    async def fake_interpret(self, user_message, workspace, companion, *args, **kwargs):
        return InterpretationPayload(
            intent=IntentPayload(key="run_wf", summary="run"),
            outcome_type=TurnOutcomeType.invoke_capabilities,
            confidence=0.95,
            candidate_capabilities=[
                CandidateCapability(
                    capability_key=f"wf:{wf_uuid}",
                    confidence=0.9,
                    input_bindings={"user_input": "first_run"},
                ),
                CandidateCapability(
                    capability_key=f"wf:{wf_uuid}",
                    confidence=0.85,
                    input_bindings={"user_input": "second_run"},
                ),
            ],
        )

    monkeypatch.setattr(WorkspaceRuntimeService, "_interpret", fake_interpret)

    overrides_seen: list[dict] = []

    async def fake_run(
        self,
        workflow,
        input_overrides=None,
        output_overrides_map=None,
        execution_stack=None,
        execution_time_zone=None,
    ):
        overrides_seen.append(dict(input_overrides or {}))
        return WorkflowRunResult(
            workflow_id=workflow.id,
            status="ok",
            node_results=[
                NodeRunResult(
                    node_id="n_stop",
                    status="ok",
                    output=StopNodeOutput(node_id="n_stop", text="final"),
                    step_number=3,
                ),
            ],
        )

    monkeypatch.setattr(WorkflowExecutor, "run", fake_run)

    async def fake_compose(self, **kwargs):
        return (
            CompositionPayload(
                response_payload=ResponsePayloadContent(
                    response_type="conversational",
                    content="OK.",
                    structured_blocks=[],
                ),
                memory_candidates=[],
                debug={},
            ),
            [],
        )

    monkeypatch.setattr(WorkspaceRuntimeService, "_compose_and_memory", fake_compose)

    data = client.post("/api/v1/workspaces/bootstrap").json()
    wid = data["workspace"]["id"]
    sid = uuid.UUID(data["session"]["id"])
    assert client.put(f"/api/v1/workspaces/{wid}", json={"enabled_workflow_ids": [wf_id]}).status_code == 200
    assert client.put("/api/v1/companion/", json={"enabled_workflow_ids": [wf_id]}).status_code == 200

    with client.stream(
        "POST",
        f"/api/v1/workspaces/{wid}/sessions/{sid}/turns/stream",
        json={"message": "go"},
    ) as resp:
        text = "".join(resp.iter_text())
    proposal_id = next(e for e in _sse_events(text) if e.get("event") == "done")["proposal_id"]

    with client.stream(
        "POST",
        f"/api/v1/workspaces/{wid}/sessions/{sid}/turns/confirm-stream",
        json={"proposal_id": proposal_id, "cancel": False},
    ) as resp2:
        assert resp2.status_code == 200
        text2 = "".join(resp2.iter_text())
    assert next(e for e in _sse_events(text2) if e.get("event") == "done").get("phase") == "completed"

    assert len(overrides_seen) == 2
    assert overrides_seen[0].get("user_input") == "first_run"
    assert overrides_seen[1].get("user_input") == "second_run"


def test_confirm_cancel_clears_proposal_no_turn(client, db_session: Session, monkeypatch):
    wf = client.post(
        "/api/v1/workflow-definitions/",
        json={"name": "Cancel Me", "graph": _MINIMAL_GRAPH},
    )
    wf_id = wf.json()["id"]
    wf_uuid = uuid.UUID(wf_id)

    async def fake_interpret(self, user_message, workspace, companion, *args, **kwargs):
        return InterpretationPayload(
            intent=IntentPayload(key="run_wf", summary="run"),
            outcome_type=TurnOutcomeType.invoke_capabilities,
            confidence=0.95,
            candidate_capabilities=[
                CandidateCapability(capability_key=f"wf:{wf_uuid}", confidence=0.9, input_bindings={})
            ],
        )

    monkeypatch.setattr(WorkspaceRuntimeService, "_interpret", fake_interpret)

    data = client.post("/api/v1/workspaces/bootstrap").json()
    wid = data["workspace"]["id"]
    sid = uuid.UUID(data["session"]["id"])
    client.put(f"/api/v1/workspaces/{wid}", json={"enabled_workflow_ids": [wf_id]})
    client.put("/api/v1/companion/", json={"enabled_workflow_ids": [wf_id]})

    with client.stream(
        "POST",
        f"/api/v1/workspaces/{wid}/sessions/{sid}/turns/stream",
        json={"message": "go"},
    ) as resp:
        text = "".join(resp.iter_text())
    proposal_id = next(e for e in _sse_events(text) if e.get("event") == "done")["proposal_id"]

    with client.stream(
        "POST",
        f"/api/v1/workspaces/{wid}/sessions/{sid}/turns/confirm-stream",
        json={"proposal_id": proposal_id, "cancel": True},
    ) as resp2:
        assert resp2.status_code == 200

    turns = list(db_session.exec(select(WorkspaceTurn).where(WorkspaceTurn.session_id == sid)).all())
    assert len(turns) == 0
    sess = db_session.get(WorkspaceSession, sid)
    assert (sess.transient_state or {}).get("capability_proposal") is None


def test_confirm_stream_rejects_bad_proposal_id(client, patch_workspace_llm):
    data = client.post("/api/v1/workspaces/bootstrap").json()
    wid = data["workspace"]["id"]
    sid = data["session"]["id"]
    r = client.post(
        f"/api/v1/workspaces/{wid}/sessions/{sid}/turns/confirm-stream",
        json={"proposal_id": str(uuid.uuid4()), "cancel": False},
    )
    assert r.status_code == 400


def test_workflow_failure_summary_lists_failed_nodes():
    wid = uuid.uuid4()
    res = WorkflowRunResult(
        workflow_id=wid,
        status="partial",
        node_results=[
            NodeRunResult(node_id="a", status="ok", output=None, step_number=1),
            NodeRunResult(node_id="bad_node", status="error", error="Something broke", step_number=2),
        ],
    )
    msg, steps = WorkspaceRuntimeService._workflow_failure_summary(res)
    assert "partial" in msg
    assert "bad_node" in msg
    assert "Something broke" in msg
    assert steps == [{"node_id": "bad_node", "error": "Something broke"}]


@pytest.mark.asyncio
async def test_compose_llm_failure_avoids_echoing_user_message(db_session: Session, monkeypatch):
    """When compose LLM fails, do not use intent.summary if it equals the user line (interpret fallback)."""
    user = db_session.exec(select(User)).first()
    assert user is not None
    svc = WorkspaceRuntimeService(db_session, user.id)

    class BoomProvider:
        async def chat(self, *args, **kwargs):
            raise RuntimeError("simulated LM failure")

    async def boom_lm():
        return BoomProvider()

    monkeypatch.setattr(svc, "_lm_provider", boom_lm)
    ws = Workspace(id=uuid.uuid4(), owner_user_id=user.id, name="EchoTest")
    companion = Companion(id=uuid.uuid4(), owner_user_id=user.id)
    um = "my user line"
    same_summary = InterpretationPayload(
        intent=IntentPayload(key="chat", summary=um),
        outcome_type=TurnOutcomeType.respond_directly,
    )
    c1, _ = await svc._compose_and_memory(
        user_message=um,
        companion=companion,
        workspace=ws,
        interpretation=same_summary,
        execution=None,
        outcome=TurnOutcomeType.respond_directly,
    )
    assert c1.response_payload.content != um
    assert "AI service" in c1.response_payload.content

    diff_summary = InterpretationPayload(
        intent=IntentPayload(key="chat", summary="Short summary from interpret"),
        outcome_type=TurnOutcomeType.respond_directly,
    )
    c2, _ = await svc._compose_and_memory(
        user_message=um,
        companion=companion,
        workspace=ws,
        interpretation=diff_summary,
        execution=None,
        outcome=TurnOutcomeType.respond_directly,
    )
    assert c2.response_payload.content == "Short summary from interpret"


@pytest.mark.asyncio
async def test_compose_prompt_uses_structured_output_label(db_session: Session, monkeypatch):
    """Compose user block must use structured_output= (not output_preview=); system instructs summarization."""
    user = db_session.exec(select(User)).first()
    assert user is not None
    svc = WorkspaceRuntimeService(db_session, user.id)

    captured: list = []

    class CaptureProvider:
        async def chat(self, messages, options=None):
            captured.extend(messages)
            return ProviderResponse(
                raw_text='{"reply_text":"Done","memory_candidates":[]}',
                parsed={"reply_text": "Done", "memory_candidates": []},
                provider_name="lmstudio",
                usage=None,
            )

    async def fake_lm():
        return CaptureProvider()

    monkeypatch.setattr(svc, "_lm_provider", fake_lm)
    ws = Workspace(id=uuid.uuid4(), owner_user_id=user.id, name="ComposePromptTest")
    companion = Companion(id=uuid.uuid4(), owner_user_id=user.id)
    interp = InterpretationPayload(
        intent=IntentPayload(key="tools", summary="Check email"),
        outcome_type=TurnOutcomeType.invoke_capabilities,
    )
    execution = ExecutionPayload(
        capability_results=[
            CapabilityRunResult(
                capability_key="wf:11111111-1111-1111-1111-111111111111",
                status="success",
                output={"messages": [{"subject": "Hi"}]},
                validation={"passed": True},
            )
        ],
        execution_summary={"total_capabilities": 1, "successful": 1, "failed": 0},
    )
    await svc._compose_and_memory(
        user_message="What email?",
        companion=companion,
        workspace=ws,
        interpretation=interp,
        execution=execution,
        outcome=TurnOutcomeType.invoke_capabilities,
    )
    assert len(captured) >= 2
    system = captured[0]["content"]
    user_content = captured[1]["content"]
    assert "output_preview=" not in user_content
    assert "structured_output=" in user_content
    assert "plain language" in system.lower()
    assert "do not echo" in system.lower()


@pytest.mark.asyncio
async def test_interpret_system_includes_temporal_context(db_session: Session, monkeypatch):
    user = db_session.exec(select(User)).first()
    assert user is not None
    svc = WorkspaceRuntimeService(db_session, user.id)

    captured: list = []

    class CaptureProvider:
        async def chat(self, messages, options=None):
            captured.extend(messages)
            return ProviderResponse(
                raw_text='{"intent":{"key":"chat","summary":"Hi"},"outcome_type":"respond_directly","confidence":0.9}',
                parsed={
                    "intent": {"key": "chat", "summary": "Hi"},
                    "outcome_type": "respond_directly",
                    "confidence": 0.9,
                    "candidate_capabilities": [],
                    "normalized_inputs": {},
                },
                provider_name="lmstudio",
                usage=None,
            )

    async def fake_lm():
        return CaptureProvider()

    monkeypatch.setattr(svc, "_lm_provider", fake_lm)
    ws = Workspace(id=uuid.uuid4(), owner_user_id=user.id, name="InterpretClockTest")
    companion = Companion(id=uuid.uuid4(), owner_user_id=user.id)
    await svc._interpret("Hello", ws, companion)
    assert len(captured) >= 2
    system = captured[0]["content"]
    assert "Temporal context" in system
    assert "Current time (UTC):" in system
    assert "+00:00" in system


def test_get_workspace_turn_detail(client, patch_workspace_llm):
    data = client.post("/api/v1/workspaces/bootstrap").json()
    wid = data["workspace"]["id"]
    sid = data["session"]["id"]
    with client.stream(
        "POST",
        f"/api/v1/workspaces/{wid}/sessions/{sid}/turns/stream",
        json={"message": "Hi detail"},
    ) as resp:
        assert resp.status_code == 200
    turns = client.get(f"/api/v1/workspaces/{wid}/sessions/{sid}/turns").json()
    assert len(turns) == 1
    tid = turns[0]["id"]
    r = client.get(f"/api/v1/workspaces/{wid}/sessions/{sid}/turns/{tid}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user_input"] == "Hi detail"
    assert "traces" in body
    traces = body["traces"]
    assert "interpretation_result" in traces
    assert "process_results" in traces
    assert "composition_result" in traces
    assert "delivered_response" in traces


def test_get_workspace_turn_detail_not_found(client, patch_workspace_llm):
    data = client.post("/api/v1/workspaces/bootstrap").json()
    wid = data["workspace"]["id"]
    sid = data["session"]["id"]
    r = client.get(f"/api/v1/workspaces/{wid}/sessions/{sid}/turns/{uuid.uuid4()}")
    assert r.status_code == 404


def test_partial_workflow_error_in_execution_trace(
    client, db_session: Session, monkeypatch, patch_workspace_session_summary_refresh
):
    wf = client.post(
        "/api/v1/workflow-definitions/",
        json={"name": "Partial WF", "graph": _MINIMAL_GRAPH},
    )
    wf_id = wf.json()["id"]
    wf_uuid = uuid.UUID(wf_id)

    async def fake_interpret(self, user_message, workspace, companion, *args, **kwargs):
        return InterpretationPayload(
            intent=IntentPayload(key="run_wf", summary="run"),
            outcome_type=TurnOutcomeType.invoke_capabilities,
            confidence=0.95,
            candidate_capabilities=[
                CandidateCapability(
                    capability_key=f"wf:{wf_uuid}",
                    confidence=0.95,
                    input_bindings={"user_input": "hi"},
                )
            ],
        )

    monkeypatch.setattr(WorkspaceRuntimeService, "_interpret", fake_interpret)

    async def fake_compose(self, **kwargs):
        return (
            CompositionPayload(
                response_payload=ResponsePayloadContent(
                    response_type="conversational",
                    content="Done.",
                    structured_blocks=[],
                ),
                memory_candidates=[],
                debug={},
            ),
            [],
        )

    monkeypatch.setattr(WorkspaceRuntimeService, "_compose_and_memory", fake_compose)

    async def fake_run(
        self,
        workflow,
        input_overrides=None,
        output_overrides_map=None,
        execution_stack=None,
        execution_time_zone=None,
    ):
        return WorkflowRunResult(
            workflow_id=workflow.id,
            status="partial",
            node_results=[
                NodeRunResult(
                    node_id="n_stop",
                    status="ok",
                    output=StopNodeOutput(node_id="n_stop", text="x"),
                    step_number=1,
                ),
                NodeRunResult(
                    node_id="n_bad",
                    status="error",
                    error="Gmail rate limited",
                    step_number=2,
                ),
            ],
        )

    monkeypatch.setattr(WorkflowExecutor, "run", fake_run)

    data = client.post("/api/v1/workspaces/bootstrap").json()
    wid = data["workspace"]["id"]
    sid = uuid.UUID(data["session"]["id"])
    client.put(f"/api/v1/workspaces/{wid}", json={"enabled_workflow_ids": [wf_id]})
    client.put("/api/v1/companion/", json={"enabled_workflow_ids": [wf_id]})

    with client.stream(
        "POST",
        f"/api/v1/workspaces/{wid}/sessions/{sid}/turns/stream",
        json={"message": "go"},
    ) as resp:
        text = "".join(resp.iter_text())
    proposal_id = next(e for e in _sse_events(text) if e.get("event") == "done")["proposal_id"]

    with client.stream(
        "POST",
        f"/api/v1/workspaces/{wid}/sessions/{sid}/turns/confirm-stream",
        json={"proposal_id": proposal_id, "cancel": False},
    ) as resp2:
        assert resp2.status_code == 200

    turns = client.get(f"/api/v1/workspaces/{wid}/sessions/{sid}/turns").json()
    tid = turns[0]["id"]
    detail = client.get(f"/api/v1/workspaces/{wid}/sessions/{sid}/turns/{tid}").json()
    ex = detail["traces"]["execution_results"]
    assert ex is not None, detail
    caps = ex.get("capability_results") or []
    assert len(caps) >= 1, ex
    err0 = caps[0].get("error") or ""
    assert "Gmail rate limited" in err0, err0
    val = caps[0].get("validation") or {}
    failed = val.get("failed_steps") or []
    assert any(s.get("node_id") == "n_bad" for s in failed)


def test_workspace_put_interpretation_model_round_trip(client, patch_workspace_llm):
    data = client.post("/api/v1/workspaces/bootstrap").json()
    wid = data["workspace"]["id"]
    r = client.put(f"/api/v1/workspaces/{wid}", json={"interpretation_model": "custom-planning-id"})
    assert r.status_code == 200, r.text
    assert r.json()["interpretation_model"] == "custom-planning-id"
    g = client.get(f"/api/v1/workspaces/{wid}")
    assert g.json()["interpretation_model"] == "custom-planning-id"


def test_confirm_stream_400_when_missing_required_start_inputs(client, monkeypatch):
    wf = client.post(
        "/api/v1/workflow-definitions/",
        json={"name": "Missing Slots WF", "graph": _MINIMAL_GRAPH},
    )
    assert wf.status_code == 201
    wf_id = wf.json()["id"]
    wf_uuid = uuid.UUID(wf_id)

    async def fake_interpret(self, user_message, workspace, companion, *args, **kwargs):
        return InterpretationPayload(
            intent=IntentPayload(key="run_wf", summary="run"),
            outcome_type=TurnOutcomeType.invoke_capabilities,
            confidence=0.95,
            candidate_capabilities=[
                CandidateCapability(
                    capability_key=f"wf:{wf_uuid}",
                    confidence=0.95,
                    input_bindings={},
                )
            ],
        )

    monkeypatch.setattr(WorkspaceRuntimeService, "_interpret", fake_interpret)

    data = client.post("/api/v1/workspaces/bootstrap").json()
    wid = data["workspace"]["id"]
    sid = uuid.UUID(data["session"]["id"])
    assert client.put(f"/api/v1/workspaces/{wid}", json={"enabled_workflow_ids": [wf_id]}).status_code == 200
    assert client.put("/api/v1/companion/", json={"enabled_workflow_ids": [wf_id]}).status_code == 200

    with client.stream(
        "POST",
        f"/api/v1/workspaces/{wid}/sessions/{sid}/turns/stream",
        json={"message": "run the workflow"},
    ) as resp:
        assert resp.status_code == 200
        text = "".join(resp.iter_text())
    proposal_id = next(e for e in _sse_events(text) if e.get("event") == "done")["proposal_id"]

    r = client.post(
        f"/api/v1/workspaces/{wid}/sessions/{sid}/turns/confirm-stream",
        json={"proposal_id": proposal_id, "cancel": False},
    )
    assert r.status_code == 400
    assert "user_input" in r.json()["detail"]


def test_capability_proposal_includes_missing_start_metadata(client, monkeypatch):
    wf = client.post(
        "/api/v1/workflow-definitions/",
        json={"name": "Slots WF", "graph": _MINIMAL_GRAPH},
    )
    assert wf.status_code == 201
    wf_id = wf.json()["id"]
    wf_uuid = uuid.UUID(wf_id)

    async def fake_interpret(self, user_message, workspace, companion, *args, **kwargs):
        return InterpretationPayload(
            intent=IntentPayload(key="run_wf", summary="run"),
            outcome_type=TurnOutcomeType.invoke_capabilities,
            confidence=0.95,
            candidate_capabilities=[
                CandidateCapability(
                    capability_key=f"wf:{wf_uuid}",
                    confidence=0.95,
                    input_bindings={},
                )
            ],
        )

    monkeypatch.setattr(WorkspaceRuntimeService, "_interpret", fake_interpret)

    data = client.post("/api/v1/workspaces/bootstrap").json()
    wid = data["workspace"]["id"]
    sid = uuid.UUID(data["session"]["id"])
    assert client.put(f"/api/v1/workspaces/{wid}", json={"enabled_workflow_ids": [wf_id]}).status_code == 200
    assert client.put("/api/v1/companion/", json={"enabled_workflow_ids": [wf_id]}).status_code == 200

    with client.stream(
        "POST",
        f"/api/v1/workspaces/{wid}/sessions/{sid}/turns/stream",
        json={"message": "run the workflow"},
    ) as resp:
        assert resp.status_code == 200
        text = "".join(resp.iter_text())

    cap_ev = next(e for e in _sse_events(text) if e.get("event") == "capability_proposal")
    caps = cap_ev.get("capabilities") or []
    assert len(caps) == 1
    assert caps[0].get("missing_start_binding_keys") == ["user_input"]
    slots = caps[0].get("start_slots") or []
    assert any(s.get("key") == "user_input" for s in slots)


@pytest.mark.asyncio
async def test_interpret_prefers_workspace_model(db_session: Session, monkeypatch):
    user = db_session.exec(select(User).where(User.username == "testuser")).first()
    assert user is not None
    companion = Companion(owner_user_id=user.id)
    db_session.add(companion)
    db_session.commit()
    db_session.refresh(companion)
    ws = Workspace(
        owner_user_id=user.id,
        name="Interp Model WS",
        interpretation_model="workspace-routing-model",
    )
    db_session.add(ws)
    db_session.commit()
    db_session.refresh(ws)

    captured: list[dict] = []

    class _Prov:
        async def chat(self, messages, options=None):
            captured.append(dict(options or {}))
            return ProviderResponse(
                raw_text="",
                parsed={
                    "intent": {"key": "chat", "summary": "x"},
                    "outcome_type": "respond_directly",
                    "confidence": 1.0,
                },
                provider_name="test",
            )

    svc = WorkspaceRuntimeService(db_session, user.id)

    async def _lm():
        return _Prov()

    monkeypatch.setattr(svc, "_lm_provider", _lm)
    await svc._interpret("hello", ws, companion)
    assert captured and captured[0].get("model") == "workspace-routing-model"


@pytest.mark.asyncio
async def test_interpret_falls_back_to_companion_model(db_session: Session, monkeypatch):
    user = db_session.exec(select(User).where(User.username == "testuser")).first()
    assert user is not None
    companion = Companion(owner_user_id=user.id)
    db_session.add(companion)
    db_session.commit()
    db_session.refresh(companion)
    ws = Workspace(
        owner_user_id=user.id,
        name="Interp Fallback WS",
        interpretation_model=None,
    )
    db_session.add(ws)
    db_session.commit()
    db_session.refresh(ws)

    captured: list[dict] = []

    class _Prov:
        async def chat(self, messages, options=None):
            captured.append(dict(options or {}))
            return ProviderResponse(
                raw_text="",
                parsed={
                    "intent": {"key": "chat", "summary": "x"},
                    "outcome_type": "respond_directly",
                    "confidence": 1.0,
                },
                provider_name="test",
            )

    svc = WorkspaceRuntimeService(db_session, user.id)

    async def _lm():
        return _Prov()

    monkeypatch.setattr(svc, "_lm_provider", _lm)
    monkeypatch.setattr(svc, "_companion_model", lambda c: "persona-model-id")
    await svc._interpret("hello", ws, companion)
    assert captured and captured[0].get("model") == "persona-model-id"
