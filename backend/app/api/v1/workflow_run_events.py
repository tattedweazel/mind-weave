"""SSE event stream and snapshot for workflow runs (replaces NDJSON run_stream + reattach).

All synchronous DB access uses short-lived sessions inside ``asyncio.to_thread``. The test
client and scheduled ``WorkflowExecutor`` share one asyncio loop; blocking the loop with ORM
I/O deadlocks concurrent ``GET …/events`` iterations and ``iter_bytes()`` consumers.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Iterable
from datetime import datetime
from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlmodel import Session, col, select

from app.api.deps import get_current_user
from app.core.workflow_execution_hub import (
    SSE_KEEPALIVE_INTERVAL_SEC,
    WorkflowRunFanout,
    sse_comment_keepalive,
)
from app.domain.schemas import NodeRunResult, WorkflowRunResult, WorkflowRunSnapshotRead
import app.persistence.db as persistence_db
from app.persistence.db import get_session
from app.persistence.tables import NodeRunLog, TranscriptionJob, User, WorkflowRun

router = APIRouter()


_TAIL_POLL_SECONDS = 1.5
_TAIL_MAX_SECONDS = 60 * 60


def _aggregate_executor_status(results: Iterable[NodeRunResult]) -> str:
    statuses = {r.status for r in results}
    if statuses == {"ok"}:
        return "ok"
    if "ok" in statuses:
        return "partial"
    return "error"


def fetch_ordered_run_logs(session: Session, run_id: uuid.UUID) -> list[NodeRunLog]:
    return list(
        session.exec(
            select(NodeRunLog)
            .where(NodeRunLog.run_id == run_id)
            .order_by(
                col(NodeRunLog.step_number).asc().nulls_last(),
                col(NodeRunLog.created_at).asc(),
                col(NodeRunLog.id).asc(),
            )
        ).all()
    )


def build_workflow_run_result_from_logs(*, workflow_id: uuid.UUID, logs: list[NodeRunLog]) -> WorkflowRunResult:
    node_results: list[NodeRunResult] = []
    for log in logs:
        safe_out = dict(log.output_data) if isinstance(log.output_data, dict) else log.output_data
        node_results.append(
            NodeRunResult.model_construct(
                node_id=log.node_id,
                status=log.status,  # type: ignore[arg-type]
                output=safe_out,
                error=log.error,
                latency_ms=log.latency_ms,
                details=dict(log.details) if log.details else {},
                step_number=log.step_number,
            )
        )
    overall = _aggregate_executor_status(node_results)
    return WorkflowRunResult(workflow_id=workflow_id, status=overall, node_results=node_results)  # type: ignore[arg-type]


def transcription_job_sse_payload(job: TranscriptionJob) -> dict[str, object]:
    return {
        "transcription_job_id": str(job.id),
        "run_id": str(job.run_id) if job.run_id else None,
        "node_id": job.node_id,
        "provider": job.provider,
        "status": job.status,
        "provider_job_id": job.provider_job_id,
        "provider_error": job.provider_error,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


def run_status_is_sse_active(run: WorkflowRun | None) -> bool:
    if run is None:
        return False
    return run_status_token_is_sse_active(run.status)


def run_status_token_is_sse_active(token: str | None) -> bool:
    if not token:
        return False
    st = token.strip()
    return st in {"queued", "running"}


def node_log_sse_payload(*, wf_id: str, run_id_str: str, log_row: NodeRunLog) -> tuple[str, dict[str, object]]:
    ev_done = "node.completed" if (log_row.status or "") == "ok" else "node.failed"
    nr = NodeRunResult.model_construct(
        node_id=log_row.node_id,
        status=log_row.status,  # type: ignore[arg-type]
        output=dict(log_row.output_data) if isinstance(log_row.output_data, dict) else log_row.output_data,
        error=log_row.error,
        latency_ms=log_row.latency_ms,
        details=dict(log_row.details) if log_row.details else {},
        step_number=log_row.step_number,
    )
    payload: dict[str, object] = {
        "workflow_id": wf_id,
        "run_id": run_id_str,
        "node_id": log_row.node_id,
        "result": nr.model_dump(mode="json", serialize_as_any=True),
    }
    return ev_done, payload


def _job_fingerprint(job: TranscriptionJob) -> tuple[str, str | None, str | None]:
    ta = job.updated_at.isoformat() if getattr(job, "updated_at", None) else ""
    ca = job.completed_at.isoformat() if job.completed_at else None
    return (job.status or "", ta, ca)


def _merge_replay_middle(
    *,
    wf_id_str: str,
    run_id_str: str,
    logs: list[NodeRunLog],
    jobs: list[TranscriptionJob],
) -> list[tuple[str, dict[str, object]]]:
    """Interleave persisted node completions and transcription snapshots by created_at."""

    items: list[tuple[datetime, int, tuple[str, dict[str, object]]]] = []
    for i, lg in enumerate(logs):
        ev_done, payload = node_log_sse_payload(wf_id=wf_id_str, run_id_str=run_id_str, log_row=lg)
        items.append((lg.created_at, i, (ev_done, payload)))
    base = len(logs)
    for j, job in enumerate(jobs):
        pj = dict(transcription_job_sse_payload(job))
        pj["workflow_id"] = wf_id_str
        pj["run_id"] = run_id_str
        items.append((job.created_at, base + j, ("transcription_job_status", pj)))
    items.sort(key=lambda t: (t[0], t[1]))
    return [t[2] for t in items]


def _blocking_terminal_event_tuples(
    *,
    run_id: uuid.UUID,
    workflow_id: uuid.UUID,
    wf_str: str,
    rid_str: str,
    status_token: str | None,
) -> list[tuple[str, dict[str, object]]]:
    st = (status_token or "").strip()
    payloads: list[tuple[str, dict[str, object]]] = []
    if st == "completed":
        with Session(persistence_db.engine) as db:
            wf_json = build_workflow_run_result_from_logs(
                workflow_id=workflow_id,
                logs=fetch_ordered_run_logs(db, run_id),
            ).model_dump(mode="json", serialize_as_any=True)
        payloads.append(("workflow.completed", {"workflow_id": wf_str, "run_id": rid_str, "result": wf_json}))
    elif st == "failed":
        tpl: dict[str, object] = {
            "workflow_id": wf_str,
            "run_id": rid_str,
            "error": "Workflow run failed",
        }
        with Session(persistence_db.engine) as db:
            logs_for_body = fetch_ordered_run_logs(db, run_id)
        if logs_for_body:
            tpl["result"] = build_workflow_run_result_from_logs(
                workflow_id=workflow_id,
                logs=logs_for_body,
            ).model_dump(mode="json", serialize_as_any=True)
        payloads.append(("workflow.failed", tpl))
    return payloads


def _blocking_load_tail_bundle(
    run_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[WorkflowRun | None, list[NodeRunLog], list[TranscriptionJob]]:
    """Return `(None,[],[])` when the run row is absent or belongs to another user."""
    with Session(persistence_db.engine) as db:
        db.expire_all()
        rr = db.get(WorkflowRun, run_id)
        if rr is None or rr.started_by_user_id != user_id:
            return None, [], []
        logs = list(
            db.exec(
                select(NodeRunLog)
                .where(NodeRunLog.run_id == run_id)
                .order_by(col(NodeRunLog.created_at).asc(), col(NodeRunLog.id).asc())
            ).all()
        )
        jobs = list(
            db.exec(
                select(TranscriptionJob)
                .where(TranscriptionJob.run_id == run_id)
                .where(TranscriptionJob.user_id == user_id)
                .order_by(col(TranscriptionJob.created_at).asc())
            ).all()
        )
        return rr, logs, jobs


async def _emit_replay_live(
    fanout: WorkflowRunFanout,
    *,
    run_id_uuid: uuid.UUID,
    wf_id_uuid: uuid.UUID,
    wf_id_str: str,
    rid_str: str,
    seq_floor: int,
    logs: list[NodeRunLog],
    jobs: list[TranscriptionJob],
    status_token: str | None,
) -> tuple[str, bool, set[uuid.UUID], dict[uuid.UUID, tuple[str, str, str | None]]]:
    """Emit synthetic workflow.started, replay middle, optionally terminal events."""

    await fanout.bump_seq_floor(seq_floor)

    terminal_emitted = False
    chunks: list[str] = []

    chunks.append(await fanout.replay_event_chunk("workflow.started", {"workflow_id": wf_id_str, "run_id": rid_str}))
    merged = _merge_replay_middle(wf_id_str=wf_id_str, run_id_str=rid_str, logs=logs, jobs=jobs)
    for evn, payload in merged:
        chunks.append(await fanout.replay_event_chunk(evn, payload))

    sent_log_ids: set[uuid.UUID] = {lg.id for lg in logs}
    job_snap: dict[uuid.UUID, tuple[str, str, str | None]] = {}
    for j in jobs:
        job_snap[j.id] = _job_fingerprint(j)

    if not run_status_token_is_sse_active(status_token):
        payloads = await asyncio.to_thread(
            _blocking_terminal_event_tuples,
            run_id=run_id_uuid,
            workflow_id=wf_id_uuid,
            wf_str=wf_id_str,
            rid_str=rid_str,
            status_token=status_token,
        )
        if payloads:
            for evn, pl in payloads:
                chunks.append(await fanout.replay_event_chunk(evn, pl))
            terminal_emitted = True

    out = "".join(chunks)
    return out, terminal_emitted, sent_log_ids, job_snap


@router.get("/workflow-runs/{run_id}", response_model=WorkflowRunSnapshotRead)
def get_workflow_run_snapshot(
    run_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> WorkflowRunSnapshotRead:
    run_row = session.get(WorkflowRun, run_id)
    if run_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow run not found")
    if run_row.started_by_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow run not found")
    return WorkflowRunSnapshotRead(
        run_id=run_row.id,
        workflow_id=run_row.workflow_id,
        status=run_row.status,
        last_event_seq=run_row.last_event_seq,
        created_at=run_row.created_at,
        updated_at=run_row.updated_at,
        started_at=run_row.started_at,
        completed_at=run_row.completed_at,
    )


def _sse_response_headers() -> dict[str, str]:
    return {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }


@router.get("/workflow-runs/{run_id}/events")
async def stream_workflow_run_events(
    request: Request,
    run_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    hub = request.app.state.workflow_execution_hub  # type: ignore[union-attr]

    rid_str = str(run_id)

    def _blocking_visibility() -> tuple[WorkflowRun | None,]:
        with Session(persistence_db.engine) as db:
            return (db.get(WorkflowRun, run_id),)

    (initial_run,) = await asyncio.to_thread(_blocking_visibility)
    if initial_run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow run not found")
    if initial_run.started_by_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow run not found")

    wf_id_uuid = initial_run.workflow_id
    wf_id_str = str(wf_id_uuid)

    async def event_stream() -> AsyncIterator[bytes]:
        fanout = await hub.get_or_create_fanout(run_id)
        q = await fanout.subscribe()
        deadline = perf_counter() + _TAIL_MAX_SECONDS
        last_yield = perf_counter()
        terminal_emitted = False
        replay_initialized = False
        sent_log_ids: set[uuid.UUID] = set()
        job_snap: dict[uuid.UUID, tuple[str, str, str | None]] = {}

        async def refill_from_db() -> str | None:
            nonlocal terminal_emitted, replay_initialized, sent_log_ids, job_snap
            run_row, logs, jobs = await asyncio.to_thread(_blocking_load_tail_bundle, run_id, current_user.id)
            # User mismatch or vanished run mid-stream → end politely
            if run_row is None:
                return None

            status_token = run_row.status
            seq_floor = int(run_row.last_event_seq or 0)

            if not replay_initialized:
                replay_out, terminal_emitted, sent_log_ids, job_snap = await _emit_replay_live(
                    fanout,
                    run_id_uuid=run_id,
                    wf_id_uuid=wf_id_uuid,
                    wf_id_str=wf_id_str,
                    rid_str=rid_str,
                    seq_floor=seq_floor,
                    logs=logs,
                    jobs=jobs,
                    status_token=status_token,
                )
                replay_initialized = True
                return replay_out

            chunks: list[str] = []

            await fanout.bump_seq_floor(seq_floor)

            for lg in logs:
                if lg.id in sent_log_ids:
                    continue
                evn, payload = node_log_sse_payload(wf_id=wf_id_str, run_id_str=rid_str, log_row=lg)
                chunks.append(await fanout.replay_event_chunk(evn, payload))
                sent_log_ids.add(lg.id)

            for job in jobs:
                fp = _job_fingerprint(job)
                prev = job_snap.get(job.id)
                if prev == fp:
                    continue
                pj = dict(transcription_job_sse_payload(job))
                pj["workflow_id"] = wf_id_str
                pj["run_id"] = rid_str
                chunks.append(await fanout.replay_event_chunk("transcription_job_status", pj))
                job_snap[job.id] = fp

            if not run_status_token_is_sse_active(status_token) and not terminal_emitted:
                payloads = await asyncio.to_thread(
                    _blocking_terminal_event_tuples,
                    run_id=run_id,
                    workflow_id=wf_id_uuid,
                    wf_str=wf_id_str,
                    rid_str=rid_str,
                    status_token=status_token,
                )
                for evn, pl in payloads:
                    chunks.append(await fanout.replay_event_chunk(evn, pl))
                terminal_emitted = bool(payloads)

            return "".join(chunks)

        def pending_queue_bytes_and_closed() -> tuple[list[bytes], bool]:
            out: list[bytes] = []
            closed = False
            while True:
                try:
                    m = q.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if m is None:
                    closed = True
                    break
                out.append(m.encode("utf-8") if isinstance(m, str) else m)
            return out, closed

        try:
            first = await refill_from_db()
            if first is None:
                return
            yield first.encode("utf-8")
            last_yield = perf_counter()
            pending, closed = pending_queue_bytes_and_closed()
            for blob in pending:
                yield blob
                last_yield = perf_counter()
            if closed:
                return

            while True:
                if perf_counter() >= deadline:
                    pl = {"workflow_id": wf_id_str, "run_id": rid_str, "error": "events tail timeout exceeded"}
                    yield (await fanout.replay_event_chunk("workflow.events_timeout", pl)).encode("utf-8")
                    break

                if terminal_emitted:
                    break

                try:
                    msg = await asyncio.wait_for(q.get(), timeout=_TAIL_POLL_SECONDS)
                except asyncio.TimeoutError:
                    if perf_counter() - last_yield >= SSE_KEEPALIVE_INTERVAL_SEC:
                        await fanout.publish_raw(sse_comment_keepalive())
                    polled = await refill_from_db()
                    if polled:
                        yield polled.encode("utf-8")
                        last_yield = perf_counter()
                    elif polled is None:
                        break
                    if terminal_emitted:
                        break
                    pending, closed = pending_queue_bytes_and_closed()
                    for blob in pending:
                        yield blob
                        last_yield = perf_counter()
                    if closed:
                        break
                    continue

                if msg is None:
                    break
                yield msg.encode("utf-8") if isinstance(msg, str) else msg
                last_yield = perf_counter()
                pending, closed = pending_queue_bytes_and_closed()
                for blob in pending:
                    yield blob
                    last_yield = perf_counter()
                if closed:
                    break

        finally:
            await fanout.unsubscribe(q)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=_sse_response_headers(),
    )
