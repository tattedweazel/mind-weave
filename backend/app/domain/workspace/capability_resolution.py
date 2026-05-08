"""Resolve Workspace capability keys of the form ``wf:{uuid}`` to workflow-backed specs."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlmodel import Session

from app.domain.services.workflow_definition_service import WorkflowDefinitionService
from app.domain.workspace.capabilities import CapabilitySpec

WF_CAPABILITY_PREFIX = "wf:"


def workflow_capability_key(workflow_id: uuid.UUID) -> str:
    return f"{WF_CAPABILITY_PREFIX}{workflow_id}"


def parse_workflow_id_from_capability_key(key: str) -> Optional[uuid.UUID]:
    if not key.startswith(WF_CAPABILITY_PREFIX):
        return None
    raw = key[len(WF_CAPABILITY_PREFIX) :]
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None


def resolve_capability_for_user(session: Session, user_id: uuid.UUID, key: str) -> Optional[CapabilitySpec]:
    """Return a workflow CapabilitySpec if the user may access the workflow; else None."""
    wf_id = parse_workflow_id_from_capability_key(key)
    if wf_id is None:
        return None
    svc = WorkflowDefinitionService(session, user_id)
    wf = svc.get_workflow(wf_id)
    if wf is None:
        return None
    desc = (wf.description or "").strip()
    return CapabilitySpec(
        capability_key=key,
        display_name=wf.name,
        description=desc or wf.name,
        backing="workflow",
        workflow_id=wf.id,
    )
