from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlmodel import Session

from app.api.deps import get_current_user
from app.persistence.db import get_session
from app.persistence.tables import User

router = APIRouter()


@router.get("/health")
def read_health():
    """Public liveness probe (SE-018)."""
    return {"status": "ok"}


@router.head("/health")
def read_health_head() -> Response:
    """HEAD for probes and `curl -I` (GET body omitted)."""
    return Response(status_code=200)


@router.get("/health/ready")
def health_ready(
    _: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Authenticated readiness (DB connectivity)."""
    session.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}
