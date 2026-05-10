"""
Palette Service
===============
CRUD operations for Palettes, scoped to the requesting user.
System-level palettes (user_id=None) are visible to all users.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlmodel import Session, or_, select

from app.domain.palette_defaults import (
    BUILTIN_WORKFLOW_PALETTES,
    DEFAULT_PALETTE_NAME,
    DEFAULT_PALETTE_SLUG,
)
from app.domain.schemas import PaletteCreate, PaletteUpdate
from app.domain.schemas.palettes import PalettePublic, build_palette_public
from app.domain.workflow_palette_validate import normalize_strict_write
from app.persistence.tables import Palette


class PaletteService:
    """Scoped CRUD service for Palettes."""

    def __init__(self, session: Session, user_id: Optional[uuid.UUID] = None):
        self.session = session
        self.user_id = user_id

    @staticmethod
    def palette_public(row: Palette) -> PalettePublic:
        return build_palette_public(
            id=row.id,
            user_id=row.user_id,
            name=row.name,
            slug=row.slug,
            colors=dict(row.colors or {}),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    # ------------------------------------------------------------------
    # Startup seeding
    # ------------------------------------------------------------------

    def initialize_builtin_palettes(self) -> None:
        """
        Seed or sync built-in system palettes (user_id NULL).

        - Match by `slug` first; update name and colors from SSOT only when changed.
        - Else match legacy row by `name` (slug null); set slug + colors.
        - Else insert. System presets are not user-editable via API.
        """
        dirty = False
        now = datetime.now(timezone.utc)
        for builtin in BUILTIN_WORKFLOW_PALETTES:
            by_slug = self.session.exec(
                select(Palette).where(
                    Palette.slug == builtin.slug,
                    Palette.user_id == None,  # noqa: E711
                )
            ).first()
            if by_slug:
                target_colors = dict(builtin.colors)
                if by_slug.name == builtin.name and by_slug.colors == target_colors:
                    continue
                by_slug.name = builtin.name
                by_slug.colors = target_colors
                by_slug.updated_at = now
                self.session.add(by_slug)
                dirty = True
                continue

            legacy = self.session.exec(
                select(Palette).where(
                    Palette.name == builtin.name,
                    Palette.user_id == None,  # noqa: E711
                )
            ).first()
            if legacy:
                legacy.slug = builtin.slug
                legacy.colors = dict(builtin.colors)
                legacy.updated_at = now
                self.session.add(legacy)
                dirty = True
                continue

            self.session.add(
                Palette(
                    user_id=None,
                    name=builtin.name,
                    slug=builtin.slug,
                    colors=dict(builtin.colors),
                )
            )
            dirty = True
        if dirty:
            self.session.commit()

    def initialize_default_palette(self) -> None:
        """Backward-compatible alias for startup / tests."""
        self.initialize_builtin_palettes()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_palette(self, id: uuid.UUID) -> Optional[Palette]:
        """Return a Palette by ID (user-owned or system-level)."""
        return self.session.exec(
            select(Palette).where(
                Palette.id == id,
                or_(Palette.user_id == self.user_id, Palette.user_id == None),  # noqa: E711
            )
        ).first()

    def get_system_palette_by_slug(self, slug: str) -> Optional[Palette]:
        """Return a system palette by slug (any authenticated user may read)."""
        return self.session.exec(
            select(Palette).where(
                Palette.slug == slug,
                Palette.user_id == None,  # noqa: E711
            )
        ).first()

    def get_default_palette(self) -> Optional[Palette]:
        """Return the system default palette."""
        by_slug = self.get_system_palette_by_slug(DEFAULT_PALETTE_SLUG)
        if by_slug:
            return by_slug
        return self.session.exec(
            select(Palette).where(
                Palette.name == DEFAULT_PALETTE_NAME,
                Palette.user_id == None,  # noqa: E711
            )
        ).first()

    def list_palettes(self) -> List[Palette]:
        """Return all Palettes visible to this user (user-owned + system-level)."""
        return list(
            self.session.exec(
                select(Palette).where(
                    or_(Palette.user_id == self.user_id, Palette.user_id == None)  # noqa: E711
                )
            ).all()
        )

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def create_palette(self, data: PaletteCreate) -> Palette:
        """Create and persist a new Palette owned by this user."""
        normed = normalize_strict_write(data.colors)
        palette = Palette(
            user_id=self.user_id,
            name=data.name.strip(),
            slug=None,
            colors=normed,
        )
        self.session.add(palette)
        self.session.commit()
        self.session.refresh(palette)
        return palette

    def update_palette(self, id: uuid.UUID, data: PaletteUpdate) -> Optional[Palette]:
        """Update a user-owned Palette. System palettes cannot be updated."""
        palette = self.get_palette(id)
        if not palette or palette.user_id != self.user_id:
            return None

        payload = data.model_dump(exclude_unset=True)
        if "name" in payload and payload["name"] is not None:
            palette.name = str(payload["name"]).strip()
        if "colors" in payload and payload["colors"] is not None:
            merged = dict(palette.colors or {})
            merged.update(payload["colors"])
            palette.colors = normalize_strict_write(merged)
        palette.updated_at = datetime.now(timezone.utc)

        self.session.add(palette)
        self.session.commit()
        self.session.refresh(palette)
        return palette

    def delete_palette(self, id: uuid.UUID) -> bool:
        """Delete a user-owned Palette. Returns False if not found or not owned."""
        palette = self.get_palette(id)
        if not palette or palette.user_id != self.user_id:
            return False
        self.session.delete(palette)
        self.session.commit()
        return True
