"""Broadcast Message utility: streaming ack path mocked — no external services."""

from __future__ import annotations

import time
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.domain.services.workflow_executor import WorkflowExecutor
from app.domain.workflow_executor.workflow_input_pending import (
    BroadcastAckWaitKey,
    complete_taken_broadcast_ack_wait,
    take_broadcast_ack_wait,
)
from app.persistence.tables import User, WorkflowDefinition, WorkflowRun
from tests.executor_scheduled_helpers import execute_scheduled_collect_sse
from tests.workflow_sse_legacy import iter_sse_pairs_as_ndjson

_BROADCAST_GRAPH = {
    "nodes": [
        {"id": "s", "kind": "start", "label": "S", "data": {"required_inputs": []}, "position": {}},
        {
            "id": "bc",
            "kind": "utility",
            "utility_type": "broadcast_message",
            "label": "Broadcast",
            "data": {
                "severity": "notice",
                "required_inputs": [
                    {"key": "message", "type": "string", "value": "Hello broadcast"},
                    {"key": "title", "type": "string", "value": "Title"},
                ],
            },
            "position": {},
        },
        {
            "id": "n_stop",
            "kind": "stop",
            "label": "Stop",
            "data": {"required_outputs": [{"key": "output", "type": "string"}]},
            "position": {},
        },
    ],
    "edges": [
        {"source": "s", "target": "bc"},
        {"source": "bc", "target": "n_stop", "source_handle": "output", "target_handle": "output"},
    ],
}


@pytest.mark.asyncio
async def test_broadcast_run_stream_emits_input_required_and_completes(db_session: Session) -> None:
    uid = uuid.uuid4()
    db_session.add(User(id=uid, username=f"bc_{uid.hex[:8]}", password_hash="h", is_admin=False))
    wf_uuid = uuid.uuid4()
    db_session.add(
        WorkflowDefinition(id=wf_uuid, user_id=uid, name="broadcast stream", graph=_BROADCAST_GRAPH),
    )
    db_session.commit()
    wf = db_session.get(WorkflowDefinition, wf_uuid)
    assert wf is not None

    run_uid = uuid.uuid4()
    db_session.add(
        WorkflowRun(
            id=run_uid,
            workflow_id=wf.id,
            started_by_user_id=uid,
            status="queued",
        )
    )
    db_session.commit()
    persist = db_session.get(WorkflowRun, run_uid)
    assert persist is not None

    ex = WorkflowExecutor(db_session, uid)

    def _complete_broadcast_ack(en: str, pl: dict[str, Any]) -> None:
        if en == "input_required" and pl.get("kind") == "broadcast_message" and str(pl.get("node_id")) == "bc":
            segments = pl.get("segments")
            assert isinstance(segments, list) and len(segments) >= 1
            assert segments[0].get("body") == "Hello broadcast"
            k = BroadcastAckWaitKey(
                run_id=uuid.UUID(str(pl["run_id"])),
                node_id="bc",
                for_loop_id=None,
                iteration=0,
            )
            fut = take_broadcast_ack_wait(k)
            assert fut is not None
            assert complete_taken_broadcast_ack_wait(fut)

    _, sse = await execute_scheduled_collect_sse(
        ex, wf, persist_run_record=persist, on_sse_event=_complete_broadcast_ack
    )

    saw_input = False
    bc_end_ok = False
    end_ok = False
    t0 = time.monotonic()
    for ev in iter_sse_pairs_as_ndjson(sse):
        if ev.get("event") == "input_required" and ev.get("node_id") == "bc":
            assert time.monotonic() - t0 < 5.0
            saw_input = True
        if ev.get("event") == "node_end" and ev.get("node_id") == "bc":
            out = (ev.get("result") or {}).get("output") or {}
            if out.get("kind") == "string" and out.get("text") == "Hello broadcast":
                bc_end_ok = True
        if ev.get("event") == "end" and (ev.get("result") or {}).get("status") == "ok":
            end_ok = True
    assert saw_input and bc_end_ok and end_ok


@pytest.mark.asyncio
async def test_broadcast_ack_endpoint(client: TestClient, db_session: Session) -> None:
    user = db_session.exec(select(User).where(User.username == "testuser")).first()
    assert user is not None
    wf_uuid = uuid.uuid4()
    db_session.add(
        WorkflowDefinition(id=wf_uuid, user_id=user.id, name="broadcast ack api", graph=_BROADCAST_GRAPH),
    )
    db_session.commit()

    run_uid = uuid.uuid4()
    db_session.add(
        WorkflowRun(
            id=run_uid,
            workflow_id=wf_uuid,
            started_by_user_id=user.id,
            status="running",
        )
    )
    db_session.commit()

    from app.domain.workflow_executor.workflow_input_pending import register_broadcast_ack_wait

    key = BroadcastAckWaitKey(run_id=run_uid, node_id="bc", for_loop_id=None, iteration=0)
    register_broadcast_ack_wait(key)

    r = client.post(
        f"/api/v1/workflow-runs/{run_uid}/broadcast-ack",
        data={"node_id": "bc", "for_loop_iteration": 0},
    )
    assert r.status_code == 204
