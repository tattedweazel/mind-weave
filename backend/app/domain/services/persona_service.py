"""
Persona Service
===============
CRUD operations for Personas, scoped to the requesting user.
System-level personas (user_id=None) are visible to all users but can only
be modified by the process that seeds them.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlmodel import Session, or_, select

from app.domain.schemas import PersonaCreate, PersonaUpdate
from app.persistence.tables import Persona
from app.prompting.personas import DefaultPersonas


class PersonaService:
    """Scoped CRUD service for Personas."""

    def __init__(self, session: Session, user_id: Optional[uuid.UUID] = None):
        self.session = session
        self.user_id = user_id

    # ------------------------------------------------------------------
    # Startup seeding
    # ------------------------------------------------------------------

    def initialize_default_personas(self) -> None:
        """Seed system personas on startup if they don't already exist."""
        for entry in DefaultPersonas:
            data = entry.value
            existing = self.session.exec(select(Persona).where(Persona.name == data["name"])).first()
            if not existing:
                self.session.add(Persona(**data))
        self.session.commit()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_persona(self, id: uuid.UUID) -> Optional[Persona]:
        """Return a Persona by ID (user-owned or system-level)."""
        return self.session.exec(
            select(Persona).where(
                Persona.id == id,
                or_(Persona.user_id == self.user_id, Persona.user_id == None),  # noqa: E711
            )
        ).first()

    def get_persona_by_name(self, name: str) -> Optional[Persona]:
        """Return a Persona by name (user-owned or system-level)."""
        return self.session.exec(
            select(Persona).where(
                Persona.name == name,
                or_(Persona.user_id == self.user_id, Persona.user_id == None),  # noqa: E711
            )
        ).first()

    def list_personas(self) -> List[Persona]:
        """Return all Personas visible to this user."""
        return list(
            self.session.exec(
                select(Persona).where(
                    or_(Persona.user_id == self.user_id, Persona.user_id == None)  # noqa: E711
                )
            ).all()
        )

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def create_persona(self, data: PersonaCreate) -> Persona:
        """Create and persist a new Persona owned by this user."""
        persona = Persona(**data.model_dump(), user_id=self.user_id)
        self.session.add(persona)
        self.session.commit()
        self.session.refresh(persona)
        return persona

    def update_persona(self, id: uuid.UUID, data: PersonaUpdate) -> Optional[Persona]:
        """Update a user-owned Persona. System personas cannot be updated."""
        persona = self.get_persona(id)
        if not persona or persona.user_id != self.user_id:
            return None

        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(persona, key, value)
        persona.updated_at = datetime.now(timezone.utc)

        self.session.add(persona)
        self.session.commit()
        self.session.refresh(persona)
        return persona

    def delete_persona(self, id: uuid.UUID) -> bool:
        """Delete a user-owned Persona. Returns False if not found or not owned."""
        persona = self.get_persona(id)
        if not persona or persona.user_id != self.user_id:
            return False
        self.session.delete(persona)
        self.session.commit()
        return True
