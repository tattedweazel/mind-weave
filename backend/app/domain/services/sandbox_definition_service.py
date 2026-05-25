"""CRUD services for Sandbox definition resources."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Generic, List, Optional, Type, TypeVar

from sqlmodel import Session, SQLModel, or_, select

from app.domain.schemas.sandbox_definitions import (
    BUILTIN_BALL_ID,
    BUILTIN_BALL_SLUG,
    BUILTIN_FOOD_ID,
    BUILTIN_FOOD_SLUG,
    BUILTIN_WALL_ID,
    BUILTIN_WALL_SLUG,
    CreatureDefinitionCreate,
    CreatureDefinitionRead,
    CreatureDefinitionUpdate,
    FixtureDefinitionCreate,
    FixtureDefinitionRead,
    FixtureDefinitionUpdate,
    ItemDefinitionCreate,
    ItemDefinitionRead,
    ItemDefinitionUpdate,
    RegionDefinitionCreate,
    RegionDefinitionRead,
    RegionDefinitionUpdate,
    TerrainDefinitionCreate,
    TerrainDefinitionRead,
    TerrainDefinitionUpdate,
)
from app.domain.services.workflow_definition_service import WorkflowDefinitionService
from app.persistence.tables import (
    CreatureDefinition,
    FixtureDefinition,
    ItemDefinition,
    RegionDefinition,
    TerrainDefinition,
)

T = TypeVar("T", bound=SQLModel)


def _validate_workflow_id(session: Session, user_id: Optional[uuid.UUID], workflow_id: str) -> None:
    try:
        wf_uuid = uuid.UUID(workflow_id)
    except ValueError as exc:
        raise ValueError(f"invalid workflow_id: {workflow_id}") from exc
    wf = WorkflowDefinitionService(session, user_id).get_workflow(wf_uuid)
    if not wf:
        raise ValueError(f"workflow not found: {workflow_id}")


class _DefinitionServiceBase(Generic[T]):
    model: Type[T]
    read_factory: Callable[[T], Any]

    def __init__(self, session: Session, user_id: Optional[uuid.UUID] = None):
        self.session = session
        self.user_id = user_id

    def _visible_filter(self):
        return or_(self.model.user_id == self.user_id, self.model.user_id == None)  # noqa: E711

    def get(self, id: uuid.UUID) -> Optional[T]:
        return self.session.exec(
            select(self.model).where(self.model.id == id, self._visible_filter())
        ).first()

    def get_by_name(self, name: str) -> Optional[T]:
        return self.session.exec(
            select(self.model).where(self.model.name == name, self._visible_filter())
        ).first()

    def list_all(self) -> List[T]:
        return list(self.session.exec(select(self.model).where(self._visible_filter())).all())

    def list_reads(self) -> List[Any]:
        return [self.read_factory(row) for row in self.list_all()]

    def delete(self, id: uuid.UUID) -> bool:
        row = self.get(id)
        if not row or row.user_id != self.user_id:
            return False
        self.session.delete(row)
        self.session.commit()
        return True


def _item_read(row: ItemDefinition) -> ItemDefinitionRead:
    meta = row.custom_metadata if isinstance(row.custom_metadata, dict) else {}
    return ItemDefinitionRead(
        id=str(row.id),
        user_id=str(row.user_id) if row.user_id else None,
        name=row.name,
        label=row.label,
        custom_metadata=dict(meta),
        default_color=row.default_color,
        shape=row.shape,  # type: ignore[arg-type]
        pickable=row.pickable,
        is_system=row.is_system,
        builtin_slug=row.builtin_slug,
    )


class ItemDefinitionService(_DefinitionServiceBase[ItemDefinition]):
    model = ItemDefinition
    read_factory = staticmethod(_item_read)

    def create(self, data: ItemDefinitionCreate) -> ItemDefinitionRead:
        row = ItemDefinition(**data.model_dump(), user_id=self.user_id)
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return _item_read(row)

    def update(self, id: uuid.UUID, data: ItemDefinitionUpdate) -> Optional[ItemDefinitionRead]:
        row = self.get(id)
        if not row or row.user_id != self.user_id:
            return None
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(row, key, value)
        row.updated_at = datetime.now(timezone.utc)
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return _item_read(row)


def item_definition_probe_maps(
    session: Session, user_id: Optional[uuid.UUID]
) -> ItemDefinitionProbeMaps:
    """Maps for cell-probe item summaries (labels and definition defaults)."""
    from app.domain.sandbox.item_helpers import ItemDefinitionDefaults, ItemDefinitionProbeMaps

    rows = ItemDefinitionService(session, user_id).list_all()
    labels: dict[str, str] = {}
    defaults: dict[str, ItemDefinitionDefaults] = {}
    for row in rows:
        key = str(row.id)
        labels[key] = row.label or row.name
        defaults[key] = ItemDefinitionDefaults(
            default_color=row.default_color,
            custom_metadata=dict(row.custom_metadata or {}),
            pickable=bool(row.pickable),
        )
    return ItemDefinitionProbeMaps(labels=labels, defaults=defaults)


def item_definition_label_map(session: Session, user_id: Optional[uuid.UUID]) -> dict[str, str]:
    """Map item definition id → display label for cell-probe summaries."""
    return item_definition_probe_maps(session, user_id).labels


def fixture_definition_color_map(
    session: Session, user_id: Optional[uuid.UUID]
) -> dict[str, str]:
    """Map fixture definition id → color for cell-probe fixture summaries."""
    rows = FixtureDefinitionService(session, user_id).list_all()
    out: dict[str, str] = {}
    for row in rows:
        if row.color:
            out[str(row.id)] = row.color
    return out


def _terrain_read(row: TerrainDefinition) -> TerrainDefinitionRead:
    return TerrainDefinitionRead(
        id=str(row.id),
        user_id=str(row.user_id) if row.user_id else None,
        name=row.name,
        label=row.label,
        default_color=row.default_color,
        shape=row.shape,  # type: ignore[arg-type]
        is_system=row.is_system,
        builtin_slug=row.builtin_slug,
    )


class TerrainDefinitionService(_DefinitionServiceBase[TerrainDefinition]):
    model = TerrainDefinition
    read_factory = staticmethod(_terrain_read)

    def create(self, data: TerrainDefinitionCreate) -> TerrainDefinitionRead:
        row = TerrainDefinition(**data.model_dump(), user_id=self.user_id)
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return _terrain_read(row)

    def update(self, id: uuid.UUID, data: TerrainDefinitionUpdate) -> Optional[TerrainDefinitionRead]:
        row = self.get(id)
        if not row or row.user_id != self.user_id:
            return None
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(row, key, value)
        row.updated_at = datetime.now(timezone.utc)
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return _terrain_read(row)


def _fixture_read(row: FixtureDefinition) -> FixtureDefinitionRead:
    return FixtureDefinitionRead(
        id=str(row.id),
        user_id=str(row.user_id) if row.user_id else None,
        name=row.name,
        label=row.label,
        workflow_id=row.workflow_id,
        color=row.color,
        is_system=row.is_system,
        builtin_slug=row.builtin_slug,
    )


class FixtureDefinitionService(_DefinitionServiceBase[FixtureDefinition]):
    model = FixtureDefinition
    read_factory = staticmethod(_fixture_read)

    def create(self, data: FixtureDefinitionCreate) -> FixtureDefinitionRead:
        _validate_workflow_id(self.session, self.user_id, data.workflow_id)
        row = FixtureDefinition(**data.model_dump(), user_id=self.user_id)
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return _fixture_read(row)

    def update(self, id: uuid.UUID, data: FixtureDefinitionUpdate) -> Optional[FixtureDefinitionRead]:
        row = self.get(id)
        if not row or row.user_id != self.user_id:
            return None
        if data.workflow_id is not None:
            _validate_workflow_id(self.session, self.user_id, data.workflow_id)
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(row, key, value)
        row.updated_at = datetime.now(timezone.utc)
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return _fixture_read(row)


def _creature_read(row: CreatureDefinition) -> CreatureDefinitionRead:
    from app.domain.schemas.sandbox import InventoryItem

    inv_raw = row.default_inventory or []
    inventory = [InventoryItem.model_validate(x) for x in inv_raw]
    return CreatureDefinitionRead(
        id=str(row.id),
        user_id=str(row.user_id) if row.user_id else None,
        name=row.name,
        label=row.label,
        workflow_id=row.workflow_id,
        default_color=row.default_color,
        default_facing=row.default_facing,  # type: ignore[arg-type]
        default_inventory=inventory,
        is_system=row.is_system,
        builtin_slug=row.builtin_slug,
    )


class CreatureDefinitionService(_DefinitionServiceBase[CreatureDefinition]):
    model = CreatureDefinition
    read_factory = staticmethod(_creature_read)

    def create(self, data: CreatureDefinitionCreate) -> CreatureDefinitionRead:
        _validate_workflow_id(self.session, self.user_id, data.workflow_id)
        payload = data.model_dump()
        payload["default_inventory"] = [x.model_dump() for x in data.default_inventory]
        row = CreatureDefinition(**payload, user_id=self.user_id)
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return _creature_read(row)

    def update(self, id: uuid.UUID, data: CreatureDefinitionUpdate) -> Optional[CreatureDefinitionRead]:
        row = self.get(id)
        if not row or row.user_id != self.user_id:
            return None
        if data.workflow_id is not None:
            _validate_workflow_id(self.session, self.user_id, data.workflow_id)
        updates = data.model_dump(exclude_unset=True)
        if "default_inventory" in updates and updates["default_inventory"] is not None:
            updates["default_inventory"] = [
                x.model_dump() if hasattr(x, "model_dump") else x for x in updates["default_inventory"]
            ]
        for key, value in updates.items():
            setattr(row, key, value)
        row.updated_at = datetime.now(timezone.utc)
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return _creature_read(row)


def _region_read(row: RegionDefinition) -> RegionDefinitionRead:
    from app.domain.schemas.sandbox import RegionTriggerConfig

    trigger = RegionTriggerConfig.model_validate(row.trigger or {})
    return RegionDefinitionRead(
        id=str(row.id),
        user_id=str(row.user_id) if row.user_id else None,
        name=row.name,
        label=row.label,
        color=row.color,
        trigger=trigger,
        is_system=row.is_system,
        builtin_slug=row.builtin_slug,
    )


class RegionDefinitionService(_DefinitionServiceBase[RegionDefinition]):
    model = RegionDefinition
    read_factory = staticmethod(_region_read)

    def create(self, data: RegionDefinitionCreate) -> RegionDefinitionRead:
        if data.trigger.workflow_id:
            _validate_workflow_id(self.session, self.user_id, data.trigger.workflow_id)
        row = RegionDefinition(
            name=data.name,
            label=data.label,
            color=data.color,
            trigger=data.trigger.model_dump(),
            user_id=self.user_id,
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return _region_read(row)

    def update(self, id: uuid.UUID, data: RegionDefinitionUpdate) -> Optional[RegionDefinitionRead]:
        row = self.get(id)
        if not row or row.user_id != self.user_id:
            return None
        updates = data.model_dump(exclude_unset=True)
        if "trigger" in updates and updates["trigger"] is not None:
            trigger = updates["trigger"]
            if hasattr(trigger, "model_dump"):
                trigger = trigger.model_dump()
            if trigger.get("workflow_id"):
                _validate_workflow_id(self.session, self.user_id, trigger["workflow_id"])
            updates["trigger"] = trigger
        for key, value in updates.items():
            setattr(row, key, value)
        row.updated_at = datetime.now(timezone.utc)
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return _region_read(row)


def seed_default_definitions(session: Session) -> None:
    """Insert system item/terrain seeds if missing (idempotent by id or builtin_slug)."""
    from sqlmodel import select

    seeds: list[tuple[type, dict[str, Any]]] = [
        (
            ItemDefinition,
            {
                "id": uuid.UUID(BUILTIN_FOOD_ID),
                "name": "Food",
                "label": "Food",
                "custom_metadata": {"energy": 48},
                "shape": "circle",
                "pickable": True,
                "is_system": True,
                "builtin_slug": BUILTIN_FOOD_SLUG,
            },
        ),
        (
            ItemDefinition,
            {
                "id": uuid.UUID(BUILTIN_BALL_ID),
                "name": "Ball",
                "label": "Ball",
                "default_color": "#EF4444",
                "shape": "circle",
                "pickable": True,
                "is_system": True,
                "builtin_slug": BUILTIN_BALL_SLUG,
            },
        ),
        (
            TerrainDefinition,
            {
                "id": uuid.UUID(BUILTIN_WALL_ID),
                "name": "Wall",
                "label": "Wall",
                "shape": "rect",
                "is_system": True,
                "builtin_slug": BUILTIN_WALL_SLUG,
            },
        ),
    ]
    pending: list[tuple[type, dict[str, Any]]] = []
    for model, fields in seeds:
        seed_id = fields["id"]
        slug = fields.get("builtin_slug")
        if session.get(model, seed_id) is not None:
            continue
        if slug is not None:
            existing_by_slug = session.exec(select(model).where(model.builtin_slug == slug)).first()
            if existing_by_slug is not None:
                continue
        pending.append((model, fields))
    for model, fields in pending:
        session.add(model(**fields))
    if pending:
        session.commit()
