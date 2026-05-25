"""CRUD API for Sandbox definition resources."""

from __future__ import annotations

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api.deps import get_current_user
from app.domain.schemas.sandbox_definitions import (
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
from app.domain.services.sandbox_definition_service import (
    CreatureDefinitionService,
    FixtureDefinitionService,
    ItemDefinitionService,
    RegionDefinitionService,
    TerrainDefinitionService,
)
from app.persistence.db import get_session
from app.persistence.tables import User

router = APIRouter(prefix="/sandbox-definitions", tags=["sandbox-definitions"])


def _duplicate_name_error() -> HTTPException:
    return HTTPException(status_code=400, detail="A definition with that name already exists.")


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Definition not found.")


def _workflow_error(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


# --- Items ---


@router.get("/items", response_model=List[ItemDefinitionRead])
def list_item_definitions(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    return ItemDefinitionService(session, current_user.id).list_reads()


@router.post("/items", response_model=ItemDefinitionRead, status_code=status.HTTP_201_CREATED)
def create_item_definition(
    data: ItemDefinitionCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    svc = ItemDefinitionService(session, current_user.id)
    if svc.get_by_name(data.name):
        raise _duplicate_name_error()
    return svc.create(data)


@router.get("/items/{id}", response_model=ItemDefinitionRead)
def get_item_definition(
    id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    row = ItemDefinitionService(session, current_user.id).get(id)
    if not row:
        raise _not_found()
    return ItemDefinitionService.read_factory(row)


@router.put("/items/{id}", response_model=ItemDefinitionRead)
def update_item_definition(
    id: uuid.UUID,
    data: ItemDefinitionUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    svc = ItemDefinitionService(session, current_user.id)
    if data.name:
        existing = svc.get_by_name(data.name)
        if existing and existing.id != id:
            raise _duplicate_name_error()
    updated = svc.update(id, data)
    if not updated:
        raise _not_found()
    return updated


@router.delete("/items/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item_definition(
    id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    if not ItemDefinitionService(session, current_user.id).delete(id):
        raise _not_found()


# --- Terrain ---


@router.get("/terrain", response_model=List[TerrainDefinitionRead])
def list_terrain_definitions(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    return TerrainDefinitionService(session, current_user.id).list_reads()


@router.post("/terrain", response_model=TerrainDefinitionRead, status_code=status.HTTP_201_CREATED)
def create_terrain_definition(
    data: TerrainDefinitionCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    svc = TerrainDefinitionService(session, current_user.id)
    if svc.get_by_name(data.name):
        raise _duplicate_name_error()
    return svc.create(data)


@router.get("/terrain/{id}", response_model=TerrainDefinitionRead)
def get_terrain_definition(
    id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    row = TerrainDefinitionService(session, current_user.id).get(id)
    if not row:
        raise _not_found()
    return TerrainDefinitionService.read_factory(row)


@router.put("/terrain/{id}", response_model=TerrainDefinitionRead)
def update_terrain_definition(
    id: uuid.UUID,
    data: TerrainDefinitionUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    svc = TerrainDefinitionService(session, current_user.id)
    if data.name:
        existing = svc.get_by_name(data.name)
        if existing and existing.id != id:
            raise _duplicate_name_error()
    updated = svc.update(id, data)
    if not updated:
        raise _not_found()
    return updated


@router.delete("/terrain/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_terrain_definition(
    id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    if not TerrainDefinitionService(session, current_user.id).delete(id):
        raise _not_found()


# --- Fixtures ---


@router.get("/fixtures", response_model=List[FixtureDefinitionRead])
def list_fixture_definitions(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    return FixtureDefinitionService(session, current_user.id).list_reads()


@router.post("/fixtures", response_model=FixtureDefinitionRead, status_code=status.HTTP_201_CREATED)
def create_fixture_definition(
    data: FixtureDefinitionCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    svc = FixtureDefinitionService(session, current_user.id)
    if svc.get_by_name(data.name):
        raise _duplicate_name_error()
    try:
        return svc.create(data)
    except ValueError as exc:
        raise _workflow_error(exc) from exc


@router.get("/fixtures/{id}", response_model=FixtureDefinitionRead)
def get_fixture_definition(
    id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    row = FixtureDefinitionService(session, current_user.id).get(id)
    if not row:
        raise _not_found()
    return FixtureDefinitionService.read_factory(row)


@router.put("/fixtures/{id}", response_model=FixtureDefinitionRead)
def update_fixture_definition(
    id: uuid.UUID,
    data: FixtureDefinitionUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    svc = FixtureDefinitionService(session, current_user.id)
    if data.name:
        existing = svc.get_by_name(data.name)
        if existing and existing.id != id:
            raise _duplicate_name_error()
    try:
        updated = svc.update(id, data)
    except ValueError as exc:
        raise _workflow_error(exc) from exc
    if not updated:
        raise _not_found()
    return updated


@router.delete("/fixtures/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_fixture_definition(
    id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    if not FixtureDefinitionService(session, current_user.id).delete(id):
        raise _not_found()


# --- Creatures ---


@router.get("/creatures", response_model=List[CreatureDefinitionRead])
def list_creature_definitions(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    return CreatureDefinitionService(session, current_user.id).list_reads()


@router.post("/creatures", response_model=CreatureDefinitionRead, status_code=status.HTTP_201_CREATED)
def create_creature_definition(
    data: CreatureDefinitionCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    svc = CreatureDefinitionService(session, current_user.id)
    if svc.get_by_name(data.name):
        raise _duplicate_name_error()
    try:
        return svc.create(data)
    except ValueError as exc:
        raise _workflow_error(exc) from exc


@router.get("/creatures/{id}", response_model=CreatureDefinitionRead)
def get_creature_definition(
    id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    row = CreatureDefinitionService(session, current_user.id).get(id)
    if not row:
        raise _not_found()
    return CreatureDefinitionService.read_factory(row)


@router.put("/creatures/{id}", response_model=CreatureDefinitionRead)
def update_creature_definition(
    id: uuid.UUID,
    data: CreatureDefinitionUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    svc = CreatureDefinitionService(session, current_user.id)
    if data.name:
        existing = svc.get_by_name(data.name)
        if existing and existing.id != id:
            raise _duplicate_name_error()
    try:
        updated = svc.update(id, data)
    except ValueError as exc:
        raise _workflow_error(exc) from exc
    if not updated:
        raise _not_found()
    return updated


@router.delete("/creatures/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_creature_definition(
    id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    if not CreatureDefinitionService(session, current_user.id).delete(id):
        raise _not_found()


# --- Regions ---


@router.get("/regions", response_model=List[RegionDefinitionRead])
def list_region_definitions(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    return RegionDefinitionService(session, current_user.id).list_reads()


@router.post("/regions", response_model=RegionDefinitionRead, status_code=status.HTTP_201_CREATED)
def create_region_definition(
    data: RegionDefinitionCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    svc = RegionDefinitionService(session, current_user.id)
    if svc.get_by_name(data.name):
        raise _duplicate_name_error()
    try:
        return svc.create(data)
    except ValueError as exc:
        raise _workflow_error(exc) from exc


@router.get("/regions/{id}", response_model=RegionDefinitionRead)
def get_region_definition(
    id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    row = RegionDefinitionService(session, current_user.id).get(id)
    if not row:
        raise _not_found()
    return RegionDefinitionService.read_factory(row)


@router.put("/regions/{id}", response_model=RegionDefinitionRead)
def update_region_definition(
    id: uuid.UUID,
    data: RegionDefinitionUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    svc = RegionDefinitionService(session, current_user.id)
    if data.name:
        existing = svc.get_by_name(data.name)
        if existing and existing.id != id:
            raise _duplicate_name_error()
    try:
        updated = svc.update(id, data)
    except ValueError as exc:
        raise _workflow_error(exc) from exc
    if not updated:
        raise _not_found()
    return updated


@router.delete("/regions/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_region_definition(
    id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    if not RegionDefinitionService(session, current_user.id).delete(id):
        raise _not_found()
