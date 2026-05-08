"""Resolve image artifact references and build OpenAI-style multimodal chat content parts."""

from __future__ import annotations

import base64
import re
from typing import Any, Dict, List, Optional, Sequence
from uuid import UUID

from sqlmodel import Session, col, select

from app.persistence.tables import UrlSnapshotArtifact

# PNG / JPEG / WebP magic (minimal validation; LM runtime may still reject)
_PNG_HDR = b"\x89PNG\r\n\x1a\n"


class MultimodalLLMInputError(ValueError):
    """Invalid multimodal inputs before provider call (maps to structured workflow errors)."""

    def __init__(self, *, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.message = message


_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _parse_uuid(raw: Any) -> Optional[UUID]:
    if raw is None:
        return None
    if isinstance(raw, UUID):
        return raw
    s = str(raw).strip()
    if not s or not _UUID_RE.match(s):
        return None
    try:
        return UUID(s)
    except ValueError:
        return None


def detect_image_mime(image_bytes: bytes) -> Optional[str]:
    if len(image_bytes) >= 8 and image_bytes.startswith(_PNG_HDR):
        return "image/png"
    if len(image_bytes) >= 3 and image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(image_bytes) >= 12 and image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return None


def normalize_images_input(raw: Any) -> List[UUID]:
    """Normalize workflow `images` input to a non-empty list of artifact UUIDs."""
    if raw is None:
        raise MultimodalLLMInputError(
            code="MISSING_IMAGE_INPUT",
            message="Multimodal LLM requires an images input.",
            retryable=False,
        )

    if isinstance(raw, dict):
        if isinstance(raw.get("image"), dict):
            raw = [raw["image"]]
        elif raw.get("artifact_id") is not None or raw.get("id") is not None:
            raw = [raw]
        else:
            raise MultimodalLLMInputError(
                code="MISSING_IMAGE_INPUT",
                message="Images input must be a list of image references or a snapshot-style object with an image field.",
                retryable=False,
            )

    if not isinstance(raw, list):
        raise MultimodalLLMInputError(
            code="MISSING_IMAGE_INPUT",
            message="Images input must be a list of image artifact references.",
            retryable=False,
        )

    if len(raw) == 0:
        raise MultimodalLLMInputError(
            code="MISSING_IMAGE_INPUT",
            message="At least one image artifact reference is required.",
            retryable=False,
        )

    ids: List[UUID] = []
    for i, item in enumerate(raw):
        aid: Any = None
        if isinstance(item, dict):
            inner = item.get("image")
            if isinstance(inner, dict):
                aid = inner.get("artifact_id") or inner.get("id")
            if aid is None:
                aid = item.get("artifact_id") or item.get("id")
        else:
            aid = item
        u = _parse_uuid(aid)
        if u is None:
            raise MultimodalLLMInputError(
                code="INVALID_IMAGE_REFERENCE",
                message=f"Invalid image artifact id at index {i}.",
                retryable=False,
            )
        ids.append(u)
    return ids


def build_openai_image_parts_from_artifacts(
    session: Session,
    user_id: UUID,
    artifact_ids: Sequence[UUID],
) -> List[Dict[str, Any]]:
    """Load user-owned snapshot artifacts and return OpenAI `content` parts (image_url)."""
    parts: List[Dict[str, Any]] = []
    for aid in artifact_ids:
        row = session.exec(
            select(UrlSnapshotArtifact).where(
                col(UrlSnapshotArtifact.id) == aid,
                col(UrlSnapshotArtifact.user_id) == user_id,
            )
        ).first()
        if row is None:
            raise MultimodalLLMInputError(
                code="INVALID_IMAGE_REFERENCE",
                message=f"No image artifact found for id {aid} (or not owned by this user).",
                retryable=False,
            )
        blob = row.image_bytes
        mime = detect_image_mime(blob)
        if mime is None:
            raise MultimodalLLMInputError(
                code="UNSUPPORTED_IMAGE_FORMAT",
                message=f"Artifact {aid} is not a supported PNG, JPEG, or WebP image.",
                retryable=False,
            )
        b64 = base64.standard_b64encode(blob).decode("ascii")
        parts.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
            }
        )
    return parts


def image_artifact_refs_for_log(artifact_ids: Sequence[UUID]) -> List[str]:
    return [str(u) for u in artifact_ids]
