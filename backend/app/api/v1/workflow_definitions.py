"""
Workflow Definitions API
========================
CRUD endpoints for WorkflowDefinitions, plus a /run endpoint.

  GET    /api/v1/workflow-definitions/        — list all for current user
  POST   /api/v1/workflow-definitions/        — create
  GET    /api/v1/workflow-definitions/{id}    — get by ID
  PUT    /api/v1/workflow-definitions/{id}    — update (including graph)
  DELETE /api/v1/workflow-definitions/{id}    — delete
  POST   /api/v1/workflow-definitions/{id}/run — execute the DAG synchronously
  POST   /api/v1/workflow-definitions/{id}/runs — enqueue an async persisted run + SSE lifecycle
"""

import asyncio
import uuid
from collections.abc import Sequence
from typing import Any, List

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from sqlmodel import Session, col, select

from app.api.deps import get_current_user
from app.core.config import settings as app_settings
from app.core.logging import logger
from app.core.run_log_redaction import redact_error_for_api, redact_prompt_like
from app.domain.execution_limits import (
    parse_execution_limits_from_graph,
    resolve_execution_limits,
    resolved_execution_limits_to_json,
)
from app.domain.execution_preflight import evaluate_execution_preflight, preflight_http_detail
from app.domain.schemas import (
    WorkflowDefinitionCreate,
    WorkflowDefinitionListItem,
    WorkflowDefinitionRead,
    WorkflowDefinitionUpdate,
    WorkflowRunEnqueueResponse,
    WorkflowRunRequest,
    WorkflowRunResult,
)
from app.domain.services.workflow_definition_service import WorkflowDefinitionService
from app.domain.services.workflow_executor import WorkflowExecutor
from app.domain.user_settings import parse_execution_limits_prefs_from_settings
from app.domain.workflow_input_overrides import validate_input_overrides_for_workflow
from app.domain.workflow_output_overrides import validate_and_build_output_overrides
from app.domain.workflow_run_runner import execute_workflow_run_job
from app.persistence.db import get_session
from app.persistence.tables import NodeRunLog, User, WorkflowRun

router = APIRouter()


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
    try:
        graph_limits = parse_execution_limits_from_graph(wf.graph)
        run_limits = body.execution_limits if body else None
        user_lim = parse_execution_limits_prefs_from_settings(current_user.settings)
        eff_limits = resolve_execution_limits(
            app_settings,
            user_limits=user_lim,
            graph_limits=graph_limits,
            run_request_limits=run_limits,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        pre = evaluate_execution_preflight(
            wf.graph,
            eff_limits,
            acknowledge_preflight_warnings=bool(body and body.acknowledge_preflight_warnings),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if pre.hard_block_message:
        raise HTTPException(status_code=422, detail=preflight_http_detail(pre))
    if not pre.ok_without_ack:
        raise HTTPException(status_code=422, detail=preflight_http_detail(pre))

    executor = WorkflowExecutor(session, current_user.id)
    try:
        return await executor.run(
            wf,
            input_overrides=overrides,
            output_overrides_map=output_map,
            execution_time_zone=execution_tz or None,
            execution_limits=eff_limits,
        )
    except ValueError as exc:
        logger.error(f"run_workflow {id}: validation error — {exc}")
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error(f"run_workflow {id}: unexpected error — {exc}")
        raise HTTPException(status_code=500, detail="Workflow execution failed.")


@router.post("/{id}/runs", response_model=WorkflowRunEnqueueResponse)
async def enqueue_workflow_run(
    id: uuid.UUID,
    request: Request,
    body: WorkflowRunRequest | None = Body(default=None),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> WorkflowRunEnqueueResponse:
    """Validate the graph like ``/run``, persist a queued ``WorkflowRun``, and schedule execution.

    Stream lifecycle on ``GET /api/v1/workflow-runs/{run_id}/events`` (SSE).
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
            session,
            current_user.id,
            wf.graph,
            body.output_overrides if body else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        graph_limits = parse_execution_limits_from_graph(wf.graph)
        run_limits = body.execution_limits if body else None
        user_lim = parse_execution_limits_prefs_from_settings(current_user.settings)
        eff_limits = resolve_execution_limits(
            app_settings,
            user_limits=user_lim,
            graph_limits=graph_limits,
            run_request_limits=run_limits,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        pre = evaluate_execution_preflight(
            wf.graph,
            eff_limits,
            acknowledge_preflight_warnings=bool(body and body.acknowledge_preflight_warnings),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if pre.hard_block_message:
        raise HTTPException(status_code=422, detail=preflight_http_detail(pre))
    if not pre.ok_without_ack:
        raise HTTPException(status_code=422, detail=preflight_http_detail(pre))

    run_row = WorkflowRun(
        workflow_id=wf.id,
        started_by_user_id=current_user.id,
        status="queued",
        execution_limits_effective=resolved_execution_limits_to_json(eff_limits),
    )
    session.add(run_row)
    session.commit()
    session.refresh(run_row)

    hub_ready = getattr(request.app.state, "workflow_execution_hub", None)
    task_set = getattr(request.app.state, "workflow_background_tasks", None)
    if hub_ready is None or task_set is None:
        raise HTTPException(status_code=503, detail="Workflow execution is not initialized")

    coro = execute_workflow_run_job(
        workflow_id=wf.id,
        run_id=run_row.id,
        user_id=current_user.id,
        input_overrides=overrides if isinstance(overrides, dict) else None,
        output_overrides_map=output_map if output_map else None,
        execution_time_zone=execution_tz or None,
    )
    loop = asyncio.get_running_loop()
    bg_task = loop.create_task(coro)
    task_set.add(bg_task)
    await hub_ready.register_run_task(run_row.id, bg_task)

    def _on_done(t: asyncio.Task[object]) -> None:
        task_set.discard(t)
        asyncio.create_task(hub_ready.unregister_run_task(run_row.id))

    bg_task.add_done_callback(_on_done)

    return WorkflowRunEnqueueResponse(run_id=run_row.id, workflow_id=wf.id, status="queued")


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
