"""Current-user endpoints (workflow run list for Replays, etc.)."""

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, col, select

from app.api.deps import get_current_user
from app.domain.schemas import MyWorkflowRunRead
from app.persistence.db import get_session
from app.persistence.tables import User, WorkflowDefinition, WorkflowRun

router = APIRouter()


@router.get("/workflow-runs", response_model=list[MyWorkflowRunRead])
def list_my_workflow_runs(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[MyWorkflowRunRead]:
    """
    Runs started by the current user on workflows they own (for Explore / history UI).
    """
    stmt = (
        select(WorkflowRun, WorkflowDefinition.name)
        .join(
            WorkflowDefinition,
            WorkflowRun.workflow_id == WorkflowDefinition.id,  # type: ignore[arg-type]
        )
        .where(WorkflowDefinition.user_id == current_user.id)
        .where(WorkflowRun.started_by_user_id == current_user.id)
        .order_by(col(WorkflowRun.created_at).desc())
        .limit(limit)
    )
    rows = session.exec(stmt).all()
    return [
        MyWorkflowRunRead(
            id=run.id,
            workflow_id=run.workflow_id,
            workflow_name=name,
            status=run.status,
            created_at=run.created_at,
            updated_at=run.updated_at,
        )
        for run, name in rows
    ]
