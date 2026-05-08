"""
Structure Service
=================
CRUD operations for Structures, scoped to the requesting user.
System-level structures (user_id=None) are visible to all users.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlmodel import Session, or_, select

from app.domain.schemas import StructureCreate, StructureUpdate
from app.persistence.tables import Structure


class StructureService:
    """Scoped CRUD service for Structures."""

    def __init__(self, session: Session, user_id: Optional[uuid.UUID] = None):
        self.session = session
        self.user_id = user_id

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_structure(self, id: uuid.UUID) -> Optional[Structure]:
        """Return a Structure by ID (user-owned or system-level)."""
        return self.session.exec(
            select(Structure).where(
                Structure.id == id,
                or_(Structure.user_id == self.user_id, Structure.user_id == None),  # noqa: E711
            )
        ).first()

    def get_structure_by_name(self, name: str) -> Optional[Structure]:
        """Return a Structure by name (user-owned or system-level)."""
        return self.session.exec(
            select(Structure).where(
                Structure.name == name,
                or_(Structure.user_id == self.user_id, Structure.user_id == None),  # noqa: E711
            )
        ).first()

    def list_structures(self) -> List[Structure]:
        """Return all Structures visible to this user."""
        return list(
            self.session.exec(
                select(Structure).where(
                    or_(Structure.user_id == self.user_id, Structure.user_id == None)  # noqa: E711
                )
            ).all()
        )

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def create_structure(self, data: StructureCreate) -> Structure:
        """Create and persist a new Structure owned by this user."""
        structure = Structure(**data.model_dump(), user_id=self.user_id)  # json_schema from model
        self.session.add(structure)
        self.session.commit()
        self.session.refresh(structure)
        return structure

    def update_structure(self, id: uuid.UUID, data: StructureUpdate) -> Optional[Structure]:
        """Update a user-owned Structure. System structures cannot be updated."""
        structure = self.get_structure(id)
        if not structure or structure.user_id != self.user_id:
            return None

        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(structure, key, value)
        structure.updated_at = datetime.now(timezone.utc)

        self.session.add(structure)
        self.session.commit()
        self.session.refresh(structure)
        return structure

    def delete_structure(self, id: uuid.UUID) -> bool:
        """Delete a user-owned Structure. Returns False if not found or not owned."""
        structure = self.get_structure(id)
        if not structure or structure.user_id != self.user_id:
            return False
        self.session.delete(structure)
        self.session.commit()
        return True
