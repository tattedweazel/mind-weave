"""Reattach to a running workflow's NDJSON event stream.

For long-running cloud transcriptions (``transcribe_file`` with ``assemblyai``), a client
may disconnect from the original ``run_stream`` before the run finishes. This endpoint
lets the client re-attach and observe the run's state — replaying persisted node logs as
NDJSON events, then tailing for new logs while the run is still active. It does NOT
attempt to live-resume the executor (the run continues independently in the DB while the
lifespan poller advances any pending transcription jobs).

Wire shape (one JSON object per line):

* ``{"event": "reattach_start", "run_id": "...", "status": "...", "replayed_count": N}``
* ``{"event": "node_end", "node_id": "...", "step_number": N, "status": "...", "result": ...}``
* ``{"event": "transcription_job_status", "job_id": "...", "node_id": "...", "status": "...", "provider": "..."}``
* ``{"event": "end", "status": "...", "result": {...}}``
"""

from __future__ import annotations

import asyncio
import json
import uuid
from time import perf_counter
from typing import Any, AsyncIterator, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from app.api.deps import get_current_user
from app.core.logging import logger
from app.persistence.db import get_session
from app.persistence.tables import NodeRunLog, TranscriptionJob, User, WorkflowRun

router = APIRouter()


_REATTACH_TAIL_INTERVAL_SECONDS = 1.5
_REATTACH_TAIL_MAX_DURATION_SECONDS = 60 * 60  # hard cap so a stuck run doesn't tie up a connection forever


def _serialize_node_log(row: NodeRunLog) -> dict[str, Any]:
    return {
        "event": "node_end",
        "node_id": row.node_id,
        "step_number": row.step_number,
        "status": row.status,
        "result": {
            "output": row.output_data,
            "error": row.error,
            "details": row.details,
            "latency_ms": row.latency_ms,
        },
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _serialize_transcription_job(row: TranscriptionJob) -> dict[str, Any]:
    return {
        "event": "transcription_job_status",
        "job_id": str(row.id),
        "run_id": str(row.run_id) if row.run_id else None,
        "node_id": row.node_id,
        "provider": row.provider,
        "status": row.status,
        "provider_error": row.provider_error,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }


def _serialize_run_end(run: WorkflowRun) -> dict[str, Any]:
    return {
        "event": "end",
        "result": {
            "run_id": str(run.id),
            "status": run.status,
            "updated_at": run.updated_at.isoformat() if run.updated_at else None,
        },
    }


@router.post("/workflow-runs/{run_id}/reattach-stream")
async def reattach_workflow_run_stream(
    run_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    preflight_session: Session = Depends(get_session),
) -> StreamingResponse:
    """Replay persisted run logs and tail new ones until the run reaches terminal state.

    Guarded by ``WorkflowRun.started_by_user_id == current_user.id``. Returns 404 for any
    run not owned by the caller (no enumeration leak). The streaming generator opens its
    own short-lived sessions on the configured engine so the request-scoped session does
    not have to live for the duration of the tail loop.
    """
    # Cheap pre-flight check before opening the streaming session — keeps 404s fast.
    run = preflight_session.get(WorkflowRun, run_id)
    if not run or run.started_by_user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Run not found")
    # Capture the active engine bind so tests that override `get_session` to point at a
    # different engine still work — at request-time the dep gives us the right engine,
    # while subsequent streaming sessions open against that same engine.
    stream_engine = preflight_session.get_bind()

    async def ndjson_stream() -> AsyncIterator[str]:
        t0 = perf_counter()
        seen_log_ids: set[uuid.UUID] = set()
        seen_job_states: dict[uuid.UUID, str] = {}

        with Session(stream_engine) as session:  # noqa: F841 — alias of preflight engine
            run_row = session.get(WorkflowRun, run_id)
            if run_row is None:
                yield json.dumps({"event": "error", "error": "Run vanished after open"}) + "\n"
                return

            # 1) Replay persisted node logs in deterministic order.
            initial_logs = list(
                session.exec(
                    select(NodeRunLog)
                    .where(NodeRunLog.run_id == run_id)
                    .order_by(NodeRunLog.created_at.asc(), NodeRunLog.id.asc())
                ).all()
            )
            yield json.dumps(
                {
                    "event": "reattach_start",
                    "run_id": str(run_id),
                    "status": run_row.status,
                    "replayed_count": len(initial_logs),
                },
            ) + "\n"
            for log_row in initial_logs:
                seen_log_ids.add(log_row.id)
                yield json.dumps(_serialize_node_log(log_row)) + "\n"

            # 2) Replay current transcription_jobs state for this run.
            jobs = list(
                session.exec(
                    select(TranscriptionJob)
                    .where(TranscriptionJob.run_id == run_id)
                    .where(TranscriptionJob.user_id == current_user.id)
                    .order_by(TranscriptionJob.created_at.asc())
                ).all()
            )
            for job in jobs:
                seen_job_states[job.id] = job.status
                yield json.dumps(_serialize_transcription_job(job)) + "\n"

            # 3) If the run is already terminal there's nothing to tail.
            if (run_row.status or "running") != "running":
                yield json.dumps(_serialize_run_end(run_row)) + "\n"
                return

            # 4) Tail loop: poll DB for new logs / job state changes and emit them.
            tail_started = perf_counter()
            poll_interval = max(0.25, float(_REATTACH_TAIL_INTERVAL_SECONDS))
            while True:
                if perf_counter() - tail_started > _REATTACH_TAIL_MAX_DURATION_SECONDS:
                    yield json.dumps(
                        {"event": "reattach_timeout", "run_id": str(run_id)},
                    ) + "\n"
                    return
                await asyncio.sleep(poll_interval)
                # Refresh persistent state.
                session.expire_all()
                # New node logs.
                new_logs = list(
                    session.exec(
                        select(NodeRunLog)
                        .where(NodeRunLog.run_id == run_id)
                        .order_by(NodeRunLog.created_at.asc(), NodeRunLog.id.asc())
                    ).all()
                )
                for log_row in new_logs:
                    if log_row.id in seen_log_ids:
                        continue
                    seen_log_ids.add(log_row.id)
                    yield json.dumps(_serialize_node_log(log_row)) + "\n"
                # Transcription job state changes.
                jobs_now = list(
                    session.exec(
                        select(TranscriptionJob)
                        .where(TranscriptionJob.run_id == run_id)
                        .where(TranscriptionJob.user_id == current_user.id)
                        .order_by(TranscriptionJob.created_at.asc())
                    ).all()
                )
                for job in jobs_now:
                    prev = seen_job_states.get(job.id)
                    if prev == job.status:
                        continue
                    seen_job_states[job.id] = job.status
                    yield json.dumps(_serialize_transcription_job(job)) + "\n"
                # Run terminal?
                run_now: Optional[WorkflowRun] = session.get(WorkflowRun, run_id)
                if run_now is None:
                    yield json.dumps({"event": "error", "error": "Run vanished during tail"}) + "\n"
                    return
                if (run_now.status or "running") != "running":
                    yield json.dumps(_serialize_run_end(run_now)) + "\n"
                    return

        logger.info(
            "reattach_stream complete run_id=%s elapsed_ms=%.1f",
            run_id,
            (perf_counter() - t0) * 1000,
        )

    return StreamingResponse(
        ndjson_stream(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
