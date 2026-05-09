"""
Workflow Definitions API
========================
CRUD endpoints for WorkflowDefinitions, plus a /run endpoint.

  GET    /api/v1/workflow-definitions/        — list all for current user
  POST   /api/v1/workflow-definitions/        — create
  GET    /api/v1/workflow-definitions/{id}    — get by ID
  PUT    /api/v1/workflow-definitions/{id}    — update (including graph)
  DELETE /api/v1/workflow-definitions/{id}    — delete
  POST   /api/v1/workflow-definitions/{id}/run — execute the DAG
"""

import contextlib
import json
import uuid
from collections.abc import AsyncIterator, Sequence
from typing import Any, List

from fastapi import APIRouter, Body, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlmodel import Session, col, select

from app.api.deps import get_current_user
from app.core.logging import logger
from app.core.run_log_redaction import redact_error_for_api, redact_prompt_like
from app.domain.schemas import (
    WorkflowDefinitionCreate,
    WorkflowDefinitionListItem,
    WorkflowDefinitionRead,
    WorkflowDefinitionUpdate,
    WorkflowRunRequest,
    WorkflowRunResult,
)
from app.domain.services.workflow_definition_service import WorkflowDefinitionService
from app.domain.services.workflow_executor import WorkflowExecutor
from app.domain.workflow_input_overrides import validate_input_overrides_for_workflow
from app.domain.workflow_output_overrides import validate_and_build_output_overrides
from app.persistence.db import get_session
from app.persistence.tables import NodeRunLog, User, WorkflowDefinition, WorkflowRun

router = APIRouter()


@contextlib.contextmanager
def _app_db_session() -> Any:
    """Use the same session factory as ``Depends(get_session)`` (including test overrides)."""
    from app.main import app
    from app.persistence.db import get_session as get_session_fn

    factory = app.dependency_overrides.get(get_session_fn, get_session_fn)
    g = factory()
    session = next(g)
    try:
        yield session
    finally:
        try:
            next(g)
        except StopIteration:
            pass


def _serialize_run_logs(logs: Sequence[NodeRunLog]) -> list[dict[str, Any]]:
    """Serialize node run logs; redact prompt-like fields without destroying `output_explorer` / `skill_explorer`.

    `redact_prompt_like` treats any key named `summary` as sensitive, but `details.output_explorer.summary`
    is UI metadata (see docs/OUTPUT_EXPLORER_UI.md). Those explorer blobs are built from at-rest-safe
    output and are re-attached after redacting the rest of `details`.
    """
    out: list[dict[str, Any]] = []
    for log in logs:
        created = log.created_at
        raw_det = dict(log.details) if log.details else {}
        output_explorer = raw_det.pop("output_explorer", None)
        skill_explorer = raw_det.pop("skill_explorer", None)
        details_for_api = redact_prompt_like(raw_det)
        if output_explorer is not None:
            details_for_api["output_explorer"] = output_explorer
        if skill_explorer is not None:
            details_for_api["skill_explorer"] = skill_explorer
        out.append(
            {
                "id": log.id,
                "run_id": log.run_id,
                "node_id": log.node_id,
                "step_number": log.step_number,
                "status": log.status,
                "output_data": redact_prompt_like(log.output_data),
                "error": redact_error_for_api(log.error),
                "latency_ms": log.latency_ms,
                "details": details_for_api,
                "created_at": created,
            }
        )
    return out


@router.get("/", response_model=List[WorkflowDefinitionListItem])
def list_workflows(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Return all WorkflowDefinitions owned by the current user (slim, without graph)."""
    return WorkflowDefinitionService(session, current_user.id).list_workflows()


@router.post("/", response_model=WorkflowDefinitionRead, status_code=status.HTTP_201_CREATED)
def create_workflow(
    data: WorkflowDefinitionCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Create a new WorkflowDefinition."""
    try:
        return WorkflowDefinitionService(session, current_user.id).create_workflow(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{id}", response_model=WorkflowDefinitionRead)
def get_workflow(
    id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Return a single WorkflowDefinition by ID."""
    wf = WorkflowDefinitionService(session, current_user.id).get_workflow(id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return wf


@router.put("/{id}", response_model=WorkflowDefinitionRead)
def update_workflow(
    id: uuid.UUID,
    data: WorkflowDefinitionUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Update an existing WorkflowDefinition (name, description, or graph)."""
    try:
        wf = WorkflowDefinitionService(session, current_user.id).update_workflow(id, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return wf


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workflow(
    id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Delete a WorkflowDefinition."""
    success = WorkflowDefinitionService(session, current_user.id).delete_workflow(id)
    if not success:
        raise HTTPException(status_code=404, detail="Workflow not found")


@router.post("/{id}/run", response_model=WorkflowRunResult)
async def run_workflow(
    id: uuid.UUID,
    body: WorkflowRunRequest | None = Body(default=None),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Execute a WorkflowDefinition and return the per-node results.

    Optional body.input_overrides: Dict[key, value] for required inputs that are null.
    Optional body.output_overrides: Dict[node_id, value] for forced node outputs (skips execution).
    Returns 422 for structural errors (cycles).
    Returns 200 even when some nodes fail — check each NodeRunResult.status.
    """
    svc = WorkflowDefinitionService(session, current_user.id)
    wf = svc.get_workflow(id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    svc.claim_orphan_if_needed(wf)

    overrides = body.input_overrides if body else None
    execution_tz = body.execution_time_zone.strip() if body and body.execution_time_zone else None
    try:
        validate_input_overrides_for_workflow(wf.graph, overrides)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        output_map = validate_and_build_output_overrides(
            session, current_user.id, wf.graph, body.output_overrides if body else None
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    executor = WorkflowExecutor(session, current_user.id)
    try:
        return await executor.run(
            wf,
            input_overrides=overrides,
            output_overrides_map=output_map,
            execution_time_zone=execution_tz or None,
        )
    except ValueError as exc:
        logger.error(f"run_workflow {id}: validation error — {exc}")
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error(f"run_workflow {id}: unexpected error — {exc}")
        raise HTTPException(status_code=500, detail="Workflow execution failed.")


@router.post("/{id}/run_stream")
async def run_workflow_stream(
    id: uuid.UUID,
    body: WorkflowRunRequest | None = Body(default=None),
    current_user: User = Depends(get_current_user),
):
    """
    Execute a WorkflowDefinition and stream the per-node results as NDJSON.
    Optional body.input_overrides for required inputs that are null.
    Optional body.output_overrides for forced node outputs.

    The DB session for execution is **opened inside the response body coroutine** and held for
    the full stream. ``Depends(get_session)`` must not be used for the executor: with
    ``StreamingResponse``, request-scoped sessions from a ``yield`` dependency can be closed
    as soon as the route returns, before the async body runs — the client then receives no NDJSON
    until errors or long timeouts (e.g. voice input appears to hang on "Running").
    """
    overrides = body.input_overrides if body else None
    execution_tz = body.execution_time_zone.strip() if body and body.execution_time_zone else None

    with _app_db_session() as _prepare_session:
        svc = WorkflowDefinitionService(_prepare_session, current_user.id)
        wf = svc.get_workflow(id)
        if not wf:
            raise HTTPException(status_code=404, detail="Workflow not found")
        svc.claim_orphan_if_needed(wf)
        try:
            validate_input_overrides_for_workflow(wf.graph, overrides)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        try:
            output_map = validate_and_build_output_overrides(
                _prepare_session,
                current_user.id,
                wf.graph,
                body.output_overrides if body else None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    wf_id = id

    async def ndjson_stream() -> AsyncIterator[str]:
        with _app_db_session() as stream_session:
            wf_row = stream_session.get(WorkflowDefinition, wf_id)
            if not wf_row:
                yield (
                    json.dumps(
                        {"event": "error", "error": "Workflow not found after validation."},
                    )
                    + "\n"
                )
                return
            executor = WorkflowExecutor(stream_session, current_user.id)
            async for chunk in executor.run_stream(
                wf_row,
                input_overrides=overrides if isinstance(overrides, dict) else None,
                output_overrides_map=output_map,
                execution_time_zone=execution_tz or None,
            ):
                yield chunk

    return StreamingResponse(
        ndjson_stream(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{id}/runs", response_model=List[WorkflowRun])
def get_workflow_runs(
    id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Retrieve all runs for a specific workflow."""
    wf = WorkflowDefinitionService(session, current_user.id).get_workflow(id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    runs = session.exec(
        select(WorkflowRun)
        .where(WorkflowRun.workflow_id == id)
        .where(WorkflowRun.started_by_user_id == current_user.id)
        .order_by(col(WorkflowRun.created_at).desc())
        .limit(50)
    ).all()
    return runs


@router.get("/{id}/runs/{run_id}/logs")
def get_workflow_run_logs(
    id: uuid.UUID,
    run_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Retrieve node run logs with prompt-like fields redacted from JSON (SE-016)."""
    wf = WorkflowDefinitionService(session, current_user.id).get_workflow(id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    run = session.get(WorkflowRun, run_id)
    if not run or run.workflow_id != id:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.started_by_user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Run not found")

    logs = session.exec(
        select(NodeRunLog)
        .where(NodeRunLog.run_id == run_id)
        .order_by(col(NodeRunLog.step_number).asc().nulls_last(), col(NodeRunLog.created_at).asc())
    ).all()
    return _serialize_run_logs(logs)


@router.delete("/{id}/runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workflow_run(
    id: uuid.UUID,
    run_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a workflow run and its node logs (only runs started by the current user)."""
    wf = WorkflowDefinitionService(session, current_user.id).get_workflow(id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    run = session.get(WorkflowRun, run_id)
    if not run or run.workflow_id != id:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.started_by_user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Run not found")

    for log in session.exec(select(NodeRunLog).where(NodeRunLog.run_id == run_id)).all():
        session.delete(log)
    session.delete(run)
    session.commit()
