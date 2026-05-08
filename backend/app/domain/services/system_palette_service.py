"""
System palette service
======================
CRUD for app-wide theme presets. Built-ins (`user_id` NULL, `slug` set) mirror workflow preset slugs.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlmodel import Session, or_, select

from app.domain.schemas import SystemPaletteCreate, SystemPaletteUpdate
from app.domain.system_palette_defaults import BUILTIN_SYSTEM_PALETTES
from app.persistence.tables import SystemPalette


class SystemPaletteService:
    """Scoped CRUD for system palettes."""

    def __init__(self, session: Session, user_id: Optional[uuid.UUID] = None):
        self.session = session
        self.user_id = user_id

    def initialize_builtin_system_palettes(self) -> None:
        """Seed or sync built-in themes (user_id NULL). Idempotent by slug / legacy name."""
        dirty = False
        now = datetime.now(timezone.utc)
        for builtin in BUILTIN_SYSTEM_PALETTES:
            by_slug = self.session.exec(
                select(SystemPalette).where(
                    SystemPalette.slug == builtin.slug,
                    SystemPalette.user_id == None,  # noqa: E711
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
                select(SystemPalette).where(
                    SystemPalette.name == builtin.name,
                    SystemPalette.user_id == None,  # noqa: E711
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
                SystemPalette(
                    user_id=None,
                    name=builtin.name,
                    slug=builtin.slug,
                    colors=dict(builtin.colors),
                )
            )
            dirty = True
        if dirty:
            self.session.commit()

    def get_system_palette(self, id: uuid.UUID) -> Optional[SystemPalette]:
        return self.session.exec(
            select(SystemPalette).where(
                SystemPalette.id == id,
                or_(
                    SystemPalette.user_id == self.user_id,
                    SystemPalette.user_id == None,  # noqa: E711
                ),
            )
        ).first()

    def get_builtin_system_palette_by_slug(self, slug: str) -> Optional[SystemPalette]:
        return self.session.exec(
            select(SystemPalette).where(
                SystemPalette.slug == slug,
                SystemPalette.user_id == None,  # noqa: E711
            )
        ).first()

    def list_system_palettes(self) -> List[SystemPalette]:
        return list(
            self.session.exec(
                select(SystemPalette).where(
                    or_(
                        SystemPalette.user_id == self.user_id,
                        SystemPalette.user_id == None,  # noqa: E711
                    )
                )
            ).all()
        )

    def create_system_palette(self, data: SystemPaletteCreate) -> SystemPalette:
        row = SystemPalette(**data.model_dump(), user_id=self.user_id, slug=None)
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def update_system_palette(self, id: uuid.UUID, data: SystemPaletteUpdate) -> Optional[SystemPalette]:
        row = self.get_system_palette(id)
        if not row or row.user_id != self.user_id:
            return None
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(row, key, value)
        row.updated_at = datetime.now(timezone.utc)
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def delete_system_palette(self, id: uuid.UUID) -> bool:
        row = self.get_system_palette(id)
        if not row or row.user_id != self.user_id:
            return False
        self.session.delete(row)
        self.session.commit()
        return True
