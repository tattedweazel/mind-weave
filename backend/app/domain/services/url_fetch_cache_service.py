"""Persistence for workflow fetch_url response cache (per user, deterministic key)."""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from sqlmodel import Session, select

from app.domain.workflow_executor.fetch_url_runtime import merge_cached_response, strip_cached_flag_for_storage
from app.persistence.tables import UrlFetchCache, utc_now


def get_cached_payload(session: Session, user_id: uuid.UUID, cache_key: str) -> Optional[Dict[str, Any]]:
    row = session.exec(
        select(UrlFetchCache).where(
            UrlFetchCache.user_id == user_id,
            UrlFetchCache.cache_key == cache_key,
        )
    ).first()
    if row is None:
        return None
    return merge_cached_response(dict(row.payload))


def upsert_success_cache(
    session: Session,
    user_id: uuid.UUID,
    cache_key: str,
    success_payload: Dict[str, Any],
) -> None:
    to_store = strip_cached_flag_for_storage(success_payload)
    row = session.exec(
        select(UrlFetchCache).where(
            UrlFetchCache.user_id == user_id,
            UrlFetchCache.cache_key == cache_key,
        )
    ).first()
    now = utc_now()
    if row is None:
        session.add(UrlFetchCache(user_id=user_id, cache_key=cache_key, payload=to_store, updated_at=now))
    else:
        row.payload = to_store
        row.updated_at = now
    session.flush()
