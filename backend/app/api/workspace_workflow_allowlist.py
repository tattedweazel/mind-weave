"""Validate Workspace / Companion enabled workflow ID lists."""

from __future__ import annotations

import uuid
from typing import Iterable, Optional

from fastapi import HTTPException
from sqlmodel import Session

from app.domain.services.workflow_definition_service import WorkflowDefinitionService


def validate_enabled_workflow_ids(
    session: Session,
    user_id: uuid.UUID,
    ids: Optional[Iterable[uuid.UUID | str]],
) -> None:
    """Raise 422 if any id is not a workflow the user may access."""
    if not ids:
        return
    svc = WorkflowDefinitionService(session, user_id)
    for raw in ids:
        try:
            wid = uuid.UUID(str(raw))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"Invalid workflow id: {raw!r}") from exc
        if svc.get_workflow(wid) is None:
            raise HTTPException(status_code=422, detail=f"Unknown or inaccessible workflow: {wid}")
