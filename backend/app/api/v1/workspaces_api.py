"""Workspace, session, and streaming turn APIs."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from app.api.deps import get_current_user
from app.api.workspace_workflow_allowlist import validate_enabled_workflow_ids
from app.core.config import settings
from app.domain.schemas.workspace_api import (
    CompanionRead,
    TurnConfirmBody,
    TurnSubmitBody,
    WorkspaceBootstrapResponse,
    WorkspaceCreate,
    WorkspacePipelinePreviewResponse,
    WorkspaceRead,
    WorkspaceSessionCreate,
    WorkspaceSessionRead,
    WorkspaceTurnDetailRead,
    WorkspaceTurnRead,
    WorkspaceTurnTracesRead,
    WorkspaceUpdate,
)
from app.domain.schemas.workspace_contracts import InterpretationResult, RoutingPlan
from app.domain.services.companion_service import CompanionService
from app.domain.services.workspace_runtime_service import WorkspaceRuntimeService
from app.domain.services.workspace_service import WorkspaceService
from app.domain.workspace.companion_pipeline_config import validate_runtime_configuration_has_valid_pipeline
from app.domain.workspace.workspace_redaction import (
    redact_workspace_trace,
    sanitize_workspace_execution_for_console,
)
from app.persistence.db import get_session
from app.persistence.tables import GoogleWorkflowConnection, User, WorkspaceTurn

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def _ensure_workspace_enabled() -> None:
    if not getattr(settings, "WORKSPACE_ENABLED", True):
        raise HTTPException(status_code=404, detail="Workspace is disabled")


def _ensure_google_workflow_connection_owned(
    session: Session,
    user_id: uuid.UUID,
    connection_id: uuid.UUID,
) -> None:
    row = session.get(GoogleWorkflowConnection, connection_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(
            status_code=422,
            detail="Google workflow connection not found or not owned by this user.",
        )


@router.post("/bootstrap", response_model=WorkspaceBootstrapResponse)
def bootstrap_workspace(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Ensure companion, default workspace, and one active session exist."""
    _ensure_workspace_enabled()
    c_svc = CompanionService(session, current_user.id)
    companion = c_svc.get_or_create_companion()
    w_svc = WorkspaceService(session, current_user.id)
    ws = w_svc.get_or_create_default_workspace(companion)
    sess = w_svc.get_latest_session(ws.id)
    if not sess:
        sess = w_svc.create_session(ws.id, companion, title="Chat")

    return WorkspaceBootstrapResponse(
        companion=CompanionRead.model_validate(companion),
        workspace=WorkspaceRead.model_validate(ws),
        session=WorkspaceSessionRead.model_validate(sess),
    )


@router.get("/", response_model=List[WorkspaceRead])
def list_workspaces(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _ensure_workspace_enabled()
    rows = WorkspaceService(session, current_user.id).list_workspaces()
    return [WorkspaceRead.model_validate(r) for r in rows]


@router.post("/", response_model=WorkspaceRead, status_code=status.HTTP_201_CREATED)
def create_workspace(
    data: WorkspaceCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _ensure_workspace_enabled()
    validate_enabled_workflow_ids(session, current_user.id, data.enabled_workflow_ids)
    try:
        validate_runtime_configuration_has_valid_pipeline(data.runtime_configuration)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if data.default_google_workflow_connection_id is not None:
        _ensure_google_workflow_connection_owned(
            session,
            current_user.id,
            data.default_google_workflow_connection_id,
        )
    ws = WorkspaceService(session, current_user.id).create_workspace(
        name=data.name,
        runtime_configuration=data.runtime_configuration,
        ui_configuration=data.ui_configuration,
        interaction_configuration=data.interaction_configuration,
        enabled_workflow_ids=data.enabled_workflow_ids,
        interpretation_model=data.interpretation_model,
        default_google_workflow_connection_id=data.default_google_workflow_connection_id,
    )
    return WorkspaceRead.model_validate(ws)


@router.get("/{workspace_id}", response_model=WorkspaceRead)
def get_workspace(
    workspace_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _ensure_workspace_enabled()
    ws = WorkspaceService(session, current_user.id).get_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    return WorkspaceRead.model_validate(ws)


@router.get("/{workspace_id}/pipeline/preview", response_model=WorkspacePipelinePreviewResponse)
def get_workspace_pipeline_preview(
    workspace_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Return merged system prompts and resolved models for Companion pipeline stages."""
    _ensure_workspace_enabled()
    w_svc = WorkspaceService(session, current_user.id)
    ws = w_svc.get_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    companion = CompanionService(session, current_user.id).get_or_create_companion()
    rt = WorkspaceRuntimeService(session, current_user.id)
    data = rt.build_pipeline_preview(workspace=ws, companion=companion)
    return WorkspacePipelinePreviewResponse.model_validate(data)


@router.put("/{workspace_id}", response_model=WorkspaceRead)
def update_workspace(
    workspace_id: uuid.UUID,
    data: WorkspaceUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _ensure_workspace_enabled()
    patch = data.model_dump(exclude_unset=True)
    if "enabled_workflow_ids" in patch:
        validate_enabled_workflow_ids(session, current_user.id, patch["enabled_workflow_ids"])
    if "default_google_workflow_connection_id" in patch and patch["default_google_workflow_connection_id"] is not None:
        _ensure_google_workflow_connection_owned(
            session,
            current_user.id,
            patch["default_google_workflow_connection_id"],
        )
    if "runtime_configuration" in patch:
        try:
            validate_runtime_configuration_has_valid_pipeline(patch.get("runtime_configuration"))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    ws = WorkspaceService(session, current_user.id).patch_workspace(workspace_id, patch)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    return WorkspaceRead.model_validate(ws)


@router.get("/{workspace_id}/sessions", response_model=List[WorkspaceSessionRead])
def list_sessions(
    workspace_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _ensure_workspace_enabled()
    rows = WorkspaceService(session, current_user.id).list_sessions(workspace_id)
    return [WorkspaceSessionRead.model_validate(r) for r in rows]


@router.post("/{workspace_id}/sessions", response_model=WorkspaceSessionRead, status_code=status.HTTP_201_CREATED)
def create_session(
    workspace_id: uuid.UUID,
    body: WorkspaceSessionCreate | None = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _ensure_workspace_enabled()
    title = body.title if body else "Chat"
    c_svc = CompanionService(session, current_user.id)
    companion = c_svc.get_or_create_companion()
    w_svc = WorkspaceService(session, current_user.id)
    try:
        sess = w_svc.create_session(workspace_id, companion, title=title)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return WorkspaceSessionRead.model_validate(sess)


@router.get("/{workspace_id}/sessions/{session_id}/turns", response_model=List[WorkspaceTurnRead])
def list_turns(
    workspace_id: uuid.UUID,
    session_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _ensure_workspace_enabled()
    w_svc = WorkspaceService(session, current_user.id)
    if not w_svc.get_session(workspace_id, session_id):
        raise HTTPException(status_code=404, detail="Session not found.")
    rows = list(
        session.exec(
            select(WorkspaceTurn).where(WorkspaceTurn.session_id == session_id).order_by(WorkspaceTurn.turn_index.asc())  # type: ignore[union-attr]
        ).all()
    )
    return [WorkspaceTurnRead.model_validate(r) for r in rows]


@router.get(
    "/{workspace_id}/sessions/{session_id}/turns/{turn_id}",
    response_model=WorkspaceTurnDetailRead,
)
def get_workspace_turn_detail(
    workspace_id: uuid.UUID,
    session_id: uuid.UUID,
    turn_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Return one turn with redacted interpretation/routing/execution/composition/delivery traces."""
    _ensure_workspace_enabled()
    w_svc = WorkspaceService(session, current_user.id)
    if not w_svc.get_session(workspace_id, session_id):
        raise HTTPException(status_code=404, detail="Session not found.")
    row = session.exec(
        select(WorkspaceTurn).where(
            WorkspaceTurn.id == turn_id,
            WorkspaceTurn.session_id == session_id,
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Turn not found.")
    traces = WorkspaceTurnTracesRead(
        interpretation_result=redact_workspace_trace(row.interpretation_result),
        routing_plan=redact_workspace_trace(row.routing_plan),
        execution_results=sanitize_workspace_execution_for_console(row.execution_results),
        process_results=redact_workspace_trace(row.process_results),
        composition_result=redact_workspace_trace(row.composition_result),
        delivered_response=redact_workspace_trace(row.delivered_response),
    )
    return WorkspaceTurnDetailRead(
        id=row.id,
        session_id=row.session_id,
        turn_index=row.turn_index,
        trace_id=row.trace_id,
        user_input=row.user_input,
        outcome_type=row.outcome_type,
        created_at=row.created_at,
        traces=traces,
    )


@router.post("/{workspace_id}/sessions/{session_id}/turns/stream")
async def stream_turn(
    workspace_id: uuid.UUID,
    session_id: uuid.UUID,
    body: TurnSubmitBody,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _ensure_workspace_enabled()
    c_svc = CompanionService(session, current_user.id)
    w_svc = WorkspaceService(session, current_user.id)
    companion = c_svc.get_or_create_companion()
    ws = w_svc.get_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    sess = w_svc.get_session(workspace_id, session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found.")

    rt = WorkspaceRuntimeService(session, current_user.id)

    async def gen():
        async for line in rt.run_turn_stream(
            workspace=ws,
            session=sess,
            companion=companion,
            user_message=body.message,
        ):
            yield line

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/{workspace_id}/sessions/{session_id}/turns/confirm-stream")
async def stream_confirm_capability_turn(
    workspace_id: uuid.UUID,
    session_id: uuid.UUID,
    body: TurnConfirmBody,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _ensure_workspace_enabled()
    c_svc = CompanionService(session, current_user.id)
    w_svc = WorkspaceService(session, current_user.id)
    companion = c_svc.get_or_create_companion()
    ws = w_svc.get_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    sess = w_svc.get_session(workspace_id, session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found.")

    rt = WorkspaceRuntimeService(session, current_user.id)
    try:
        proposal = rt._load_capability_proposal(sess, body.proposal_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not body.cancel:
        rp = RoutingPlan.model_validate(proposal["routing_plan"])
        allowed = rt._allowed_capability_keys(ws, companion)
        for s in rp.payload.selected_capabilities:
            if s.capability_key not in allowed:
                rt._clear_capability_proposal(sess)
                sess.updated_at = datetime.now(timezone.utc)
                session.add(sess)
                session.commit()
                raise HTTPException(
                    status_code=400,
                    detail="A workflow is no longer enabled on this workspace or companion.",
                )
        interp_result = InterpretationResult.model_validate(proposal["interpretation_result"])
        try:
            rt._validate_confirm_capability_bindings(interp_result.payload, rp.payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    async def gen():
        async for line in rt.run_confirm_capability_stream(
            workspace=ws,
            session=sess,
            companion=companion,
            proposal_id=body.proposal_id,
            cancel=body.cancel,
        ):
            yield line

    return StreamingResponse(gen(), media_type="text/event-stream")
