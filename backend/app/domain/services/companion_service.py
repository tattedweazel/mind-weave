"""Companion CRUD and lazy creation (one per user)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlmodel import Session, select

from app.persistence.tables import Companion, CompanionMemoryEntry, Persona

DEFAULT_COMPANION_NAME = "Companion"


class CompanionService:
    def __init__(self, session: Session, user_id: uuid.UUID):
        self.session = session
        self.user_id = user_id

    def get_companion(self) -> Optional[Companion]:
        return self.session.exec(select(Companion).where(Companion.owner_user_id == self.user_id)).first()

    def get_or_create_companion(self) -> Companion:
        row = self.get_companion()
        if row:
            return row
        default_persona = self.session.exec(
            select(Persona).where(Persona.name == "default", Persona.user_id == None)  # noqa: E711
        ).first()
        pid = default_persona.id if default_persona else None
        now = datetime.now(timezone.utc)
        row = Companion(
            owner_user_id=self.user_id,
            name=DEFAULT_COMPANION_NAME,
            description="",
            persona_id=pid,
            identity_profile={},
            default_mode="default",
            available_modes=["default"],
            enabled_workflow_ids=[],
            memory_policy={"approval_required": True},
            created_at=now,
            updated_at=now,
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def apply_companion_patch(self, patch: Dict[str, Any]) -> Companion:
        """Apply only keys present in ``patch`` (from Pydantic ``model_dump(exclude_unset=True)``).

        Allows ``persona_id`` to be set to ``None`` to clear the link.
        """
        allowed = {
            "name",
            "description",
            "persona_id",
            "identity_profile",
            "default_mode",
            "available_modes",
            "enabled_workflow_ids",
            "memory_policy",
        }
        c = self.get_or_create_companion()
        for key, value in patch.items():
            if key not in allowed:
                continue
            if key == "persona_id":
                c.persona_id = value
            elif key == "name":
                c.name = value
            elif key == "description":
                c.description = value
            elif key == "identity_profile":
                c.identity_profile = value if isinstance(value, dict) else {}
            elif key == "default_mode":
                c.default_mode = value
            elif key == "available_modes":
                c.available_modes = value if isinstance(value, list) else []
            elif key == "enabled_workflow_ids":
                c.enabled_workflow_ids = value if isinstance(value, list) else []
            elif key == "memory_policy":
                c.memory_policy = value if isinstance(value, dict) else {}
        c.updated_at = datetime.now(timezone.utc)
        self.session.add(c)
        self.session.commit()
        self.session.refresh(c)
        return c

    def list_memory_entries(
        self,
        *,
        approval_status: Optional[str] = None,
    ) -> List[CompanionMemoryEntry]:
        c = self.get_or_create_companion()
        q = select(CompanionMemoryEntry).where(CompanionMemoryEntry.companion_id == c.id)
        if approval_status:
            q = q.where(CompanionMemoryEntry.approval_status == approval_status)
        q = q.order_by(CompanionMemoryEntry.created_at.desc())  # type: ignore[union-attr]
        return list(self.session.exec(q).all())

    def set_memory_approval(self, memory_id: uuid.UUID, *, approved: bool) -> Optional[CompanionMemoryEntry]:
        c = self.get_or_create_companion()
        row = self.session.exec(
            select(CompanionMemoryEntry).where(
                CompanionMemoryEntry.id == memory_id,
                CompanionMemoryEntry.companion_id == c.id,
            )
        ).first()
        if not row:
            return None
        if row.approval_status != "proposed":
            return None
        row.approval_status = "approved" if approved else "rejected"
        row.updated_at = datetime.now(timezone.utc)
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row
