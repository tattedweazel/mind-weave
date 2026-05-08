"""Persistence for capture_url_snapshot: artifacts (PNG bytes) and per-user cache key mapping."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlmodel import Session, select

from app.persistence.tables import UrlSnapshotArtifact, UrlSnapshotCache, utc_now


def get_cache_artifact(
    session: Session, user_id: uuid.UUID, cache_key: str
) -> Optional[UrlSnapshotArtifact]:
    row = session.exec(
        select(UrlSnapshotCache).where(
            UrlSnapshotCache.user_id == user_id,
            UrlSnapshotCache.cache_key == cache_key,
        )
    ).first()
    if row is None:
        return None
    return session.get(UrlSnapshotArtifact, row.artifact_id)


def _delete_artifact_if_exists(session: Session, artifact_id: Optional[uuid.UUID]) -> None:
    if artifact_id is None:
        return
    art = session.get(UrlSnapshotArtifact, artifact_id)
    if art is not None:
        session.delete(art)


def create_artifact(
    session: Session,
    user_id: uuid.UUID,
    image_bytes: bytes,
    width: int,
    height: int,
    final_url: str = "",
    mime_type: str = "image/png",
) -> UrlSnapshotArtifact:
    now = utc_now()
    art = UrlSnapshotArtifact(
        user_id=user_id,
        image_bytes=image_bytes,
        mime_type=mime_type,
        width=width,
        height=height,
        final_url=final_url,
        created_at=now,
        updated_at=now,
    )
    session.add(art)
    session.flush()
    return art


def upsert_cache(
    session: Session,
    user_id: uuid.UUID,
    cache_key: str,
    new_artifact: UrlSnapshotArtifact,
) -> None:
    row = session.exec(
        select(UrlSnapshotCache).where(
            UrlSnapshotCache.user_id == user_id,
            UrlSnapshotCache.cache_key == cache_key,
        )
    ).first()
    now = utc_now()
    if row is None:
        session.add(
            UrlSnapshotCache(
                user_id=user_id,
                cache_key=cache_key,
                artifact_id=new_artifact.id,
                updated_at=now,
            )
        )
        return

    old_aid = row.artifact_id
    if old_aid != new_artifact.id:
        _delete_artifact_if_exists(session, old_aid)
    row.artifact_id = new_artifact.id
    row.updated_at = now
    session.add(row)
    session.flush()
