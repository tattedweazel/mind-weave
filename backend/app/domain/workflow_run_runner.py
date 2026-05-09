"""Background execution task for POST /workflow-definitions/{id}/runs."""

from __future__ import annotations

import contextlib
import uuid
from typing import Any

from app.core.logging import logger
from app.core.workflow_execution_hub import WorkflowExecutionHub
from app.domain.services.workflow_executor import WorkflowExecutor
from app.persistence.tables import WorkflowDefinition, WorkflowRun, utc_now


def _workflow_job_session_cm() -> Any:
    """Match ``workflow_definitions._app_db_session`` (honors test dependency overrides)."""
    from app.main import app as mindweave_app
    from app.persistence.db import get_session as get_session_fn

    factory = mindweave_app.dependency_overrides.get(get_session_fn, get_session_fn)
    gen = factory()
    session = next(gen)

    class _Closer:
        def close(self) -> None:
            with contextlib.suppress(StopIteration):
                next(gen)

    return session, _Closer()


async def execute_workflow_run_job(
    *,
    workflow_id: uuid.UUID,
    run_id: uuid.UUID,
    user_id: uuid.UUID,
    input_overrides: dict[str, Any] | None,
    output_overrides_map: dict[str, Any] | None,
    execution_time_zone: str | None,
) -> None:
    from app.main import app as mindweave_app

    hub: WorkflowExecutionHub = mindweave_app.state.workflow_execution_hub  # type: ignore[union-attr]
    fanout = await hub.get_or_create_fanout(run_id)

    session, closer = _workflow_job_session_cm()
    try:
        wf_row = session.get(WorkflowDefinition, workflow_id)
        run_record = session.get(WorkflowRun, run_id)
        if wf_row is None or run_record is None:
            logger.error("scheduled run missing workflow=%s run=%s", workflow_id, run_id)
            return

        run_record.status = "running"
        if run_record.started_at is None:
            run_record.started_at = utc_now()
        session.add(run_record)
        session.commit()

        async def sse_publish(en: str, payload: dict[str, object]) -> int:
            return await fanout.publish(en, payload)

        async def sse_raw(line: str) -> None:
            await fanout.publish_raw(line)

        executor = WorkflowExecutor(session, user_id)
        await executor.execute_scheduled_run(
            wf_row,
            persist_run_record=run_record,
            input_overrides=input_overrides,
            output_overrides_map=output_overrides_map,
            execution_time_zone=execution_time_zone,
            sse_publish=sse_publish,
            sse_raw=sse_raw,
        )
    except Exception:
        logger.exception("workflow scheduled run crashed workflow_id=%s run_id=%s", workflow_id, run_id)
        try:
            run_record = session.get(WorkflowRun, run_id)
            if run_record and (run_record.status or "") not in {"completed", "failed"}:
                run_record.status = "failed"
                run_record.completed_at = utc_now()
                session.add(run_record)
                session.commit()
        except Exception:
            logger.exception("failed to persist failed status for run_id=%s", run_id)
    finally:
        closer.close()
