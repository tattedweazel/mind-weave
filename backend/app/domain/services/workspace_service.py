"""Workspace and session CRUD."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlmodel import Session, select

from app.persistence.tables import Companion, Workspace, WorkspaceSession

DEFAULT_WORKSPACE_NAME = "Companion Chat"

_WORKSPACE_PATCH_KEYS = frozenset(
    {
        "name",
        "runtime_configuration",
        "ui_configuration",
        "interaction_configuration",
        "enabled_workflow_ids",
        "interpretation_model",
        "default_google_workflow_connection_id",
    }
)


class WorkspaceService:
    def __init__(self, session: Session, user_id: uuid.UUID):
        self.session = session
        self.user_id = user_id

    def list_workspaces(self) -> List[Workspace]:
        return list(
            self.session.exec(
                select(Workspace)
                .where(Workspace.owner_user_id == self.user_id)
                .order_by(Workspace.updated_at.desc())  # type: ignore[union-attr]
            ).all()
        )

    def get_workspace(self, workspace_id: uuid.UUID) -> Optional[Workspace]:
        return self.session.exec(
            select(Workspace).where(Workspace.id == workspace_id, Workspace.owner_user_id == self.user_id)
        ).first()

    def get_or_create_default_workspace(self, companion: Companion) -> Workspace:
        first = self.session.exec(
            select(Workspace)
            .where(Workspace.owner_user_id == self.user_id)
            .order_by(Workspace.updated_at.desc())  # type: ignore[union-attr]
            .limit(1)
        ).first()
        if first:
            return first
        return self.create_default_workspace(companion)

    def create_default_workspace(self, companion: Companion) -> Workspace:
        now = datetime.now(timezone.utc)
        ws = Workspace(
            owner_user_id=self.user_id,
            name=DEFAULT_WORKSPACE_NAME,
            runtime_configuration={"staged_turn_loop": True, "companion_enabled": True},
            ui_configuration={"layout": "chat"},
            interaction_configuration={"streaming_delivery": True},
            enabled_workflow_ids=[],
            created_at=now,
            updated_at=now,
        )
        self.session.add(ws)
        self.session.commit()
        self.session.refresh(ws)
        return ws

    def create_workspace(
        self,
        *,
        name: str,
        runtime_configuration: Optional[dict] = None,
        ui_configuration: Optional[dict] = None,
        interaction_configuration: Optional[dict] = None,
        enabled_workflow_ids: Optional[list[str]] = None,
        interpretation_model: Optional[str] = None,
        default_google_workflow_connection_id: Optional[uuid.UUID] = None,
    ) -> Workspace:
        now = datetime.now(timezone.utc)
        im = (interpretation_model or "").strip() or None
        ws = Workspace(
            owner_user_id=self.user_id,
            name=name,
            runtime_configuration=runtime_configuration or {},
            ui_configuration=ui_configuration or {},
            interaction_configuration=interaction_configuration or {},
            enabled_workflow_ids=list(enabled_workflow_ids) if enabled_workflow_ids is not None else [],
            interpretation_model=im,
            default_google_workflow_connection_id=default_google_workflow_connection_id,
            created_at=now,
            updated_at=now,
        )
        self.session.add(ws)
        self.session.commit()
        self.session.refresh(ws)
        return ws

    def patch_workspace(self, workspace_id: uuid.UUID, patch: Dict[str, Any]) -> Optional[Workspace]:
        """Apply only keys present in ``patch`` (e.g. from ``model_dump(exclude_unset=True)``)."""
        ws = self.get_workspace(workspace_id)
        if not ws:
            return None
        for k, v in patch.items():
            if k not in _WORKSPACE_PATCH_KEYS:
                continue
            if k == "enabled_workflow_ids":
                ws.enabled_workflow_ids = list(v) if v is not None else []
            elif k == "interpretation_model":
                ws.interpretation_model = (str(v).strip() or None) if v is not None else None
            else:
                setattr(ws, k, v)
        ws.updated_at = datetime.now(timezone.utc)
        self.session.add(ws)
        self.session.commit()
        self.session.refresh(ws)
        return ws

    def update_workspace(
        self,
        workspace_id: uuid.UUID,
        *,
        name: Optional[str] = None,
        runtime_configuration: Optional[dict] = None,
        ui_configuration: Optional[dict] = None,
        interaction_configuration: Optional[dict] = None,
        enabled_workflow_ids: Optional[list[str]] = None,
    ) -> Optional[Workspace]:
        patch: Dict[str, Any] = {}
        if name is not None:
            patch["name"] = name
        if runtime_configuration is not None:
            patch["runtime_configuration"] = runtime_configuration
        if ui_configuration is not None:
            patch["ui_configuration"] = ui_configuration
        if interaction_configuration is not None:
            patch["interaction_configuration"] = interaction_configuration
        if enabled_workflow_ids is not None:
            patch["enabled_workflow_ids"] = enabled_workflow_ids
        if not patch:
            ws = self.get_workspace(workspace_id)
            return ws
        return self.patch_workspace(workspace_id, patch)

    def get_session(self, workspace_id: uuid.UUID, session_id: uuid.UUID) -> Optional[WorkspaceSession]:
        ws = self.get_workspace(workspace_id)
        if not ws:
            return None
        return self.session.exec(
            select(WorkspaceSession).where(
                WorkspaceSession.id == session_id,
                WorkspaceSession.workspace_id == workspace_id,
            )
        ).first()

    def get_latest_session(self, workspace_id: uuid.UUID) -> Optional[WorkspaceSession]:
        """Return the most-recently-updated session for a workspace (ownership already validated)."""
        return self.session.exec(
            select(WorkspaceSession)
            .where(WorkspaceSession.workspace_id == workspace_id)
            .order_by(WorkspaceSession.updated_at.desc())  # type: ignore[union-attr]
            .limit(1)
        ).first()

    def list_sessions(self, workspace_id: uuid.UUID) -> List[WorkspaceSession]:
        if not self.get_workspace(workspace_id):
            return []
        return list(
            self.session.exec(
                select(WorkspaceSession)
                .where(WorkspaceSession.workspace_id == workspace_id)
                .order_by(WorkspaceSession.updated_at.desc())  # type: ignore[union-attr]
            ).all()
        )

    def create_session(self, workspace_id: uuid.UUID, companion: Companion, title: str = "Chat") -> WorkspaceSession:
        ws = self.get_workspace(workspace_id)
        if not ws:
            raise ValueError("Workspace not found")
        now = datetime.now(timezone.utc)
        sess = WorkspaceSession(
            workspace_id=workspace_id,
            companion_id=companion.id,
            title=title,
            status="active",
            turn_count=0,
            transient_state={},
            active_summary="",
            last_turn_at=None,
            created_at=now,
            updated_at=now,
        )
        self.session.add(sess)
        self.session.commit()
        self.session.refresh(sess)
        return sess
