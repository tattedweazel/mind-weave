"""Expose server defaults and ceilings for workflow execution limits (SPA validation)."""

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.core.config import settings
from app.domain.execution_limits import execution_limits_ceiling_snapshot, execution_limits_default_snapshot
from app.persistence.tables import User

router = APIRouter(prefix="/workflow-execution-limits", tags=["workflow-execution-limits"])


@router.get("/", response_model=dict)
def get_workflow_execution_limits(_current_user: User = Depends(get_current_user)) -> dict:
    """Return deployment defaults and hard ceilings for graph/run execution_limits overrides."""
    return {
        "defaults": execution_limits_default_snapshot(settings),
        "ceilings": execution_limits_ceiling_snapshot(settings),
    }
