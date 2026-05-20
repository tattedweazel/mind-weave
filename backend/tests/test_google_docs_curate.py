"""Unit tests for Google Docs curation (mocked image fetch)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import Session

from app.domain.workflow_executor.google_docs_curate import (
    build_document_payload,
    truncate_google_docs_get_response,
)
from app.persistence.tables import User

_PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x01\x01\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _raw_with_image() -> dict:
    return {
        "documentId": "doc_img",
        "title": "Img doc",
        "revisionId": "r1",
        "tabs": [
            {
                "tabProperties": {"tabId": "t1", "title": "T1"},
                "documentTab": {
                    "body": {
                        "content": [
                            {
                                "paragraph": {
                                    "elements": [
                                        {
                                            "inlineObjectElement": {
                                                "inlineObjectId": "img_obj_1",
                                            }
                                        },
                                    ]
                                }
                            }
                        ]
                    },
                    "inlineObjects": {
                        "img_obj_1": {
                            "inlineObjectProperties": {
                                "embeddedObject": {
                                    "size": {
                                        "width": {"magnitude": 50, "unit": "PT"},
                                        "height": {"magnitude": 40, "unit": "PT"},
                                    },
                                    "imageProperties": {
                                        "contentUri": "https://example.com/img.png",
                                    },
                                }
                            }
                        }
                    },
                },
            }
        ],
    }


@pytest.mark.asyncio
async def test_build_document_payload_downloads_image(db_session: Session):
    uid = uuid.uuid4()
    db_session.add(User(id=uid, username=f"u_{uid.hex[:8]}", password_hash="h", is_admin=False))
    db_session.commit()

    with patch(
        "app.domain.workflow_executor.google_docs_curate.fetch_inline_image_bytes",
        new_callable=AsyncMock,
        return_value=_PNG_1X1,
    ):
        payload, errors = await build_document_payload(
            db_session,
            uid,
            "token",
            _raw_with_image(),
            document_id="doc_img",
        )
    db_session.commit()
    assert payload["image_count"] == 1
    assert not errors
    blocks = payload["tabs"][0]["body"]["blocks"]
    assert blocks[0]["images"][0]["artifact_id"]
    assert blocks[0]["images"][0]["mime_type"] == "image/png"


@pytest.mark.asyncio
async def test_build_document_payload_legacy_body_without_tabs(db_session: Session):
    uid = uuid.uuid4()
    db_session.add(User(id=uid, username=f"u_{uid.hex[:8]}", password_hash="h", is_admin=False))
    db_session.commit()
    raw = {
        "documentId": "legacy",
        "title": "Legacy",
        "body": {
            "content": [
                {
                    "paragraph": {
                        "elements": [{"textRun": {"content": "Legacy text\n"}}],
                    }
                }
            ]
        },
        "inlineObjects": {},
    }
    payload, _ = await build_document_payload(db_session, uid, "tok", raw, document_id="legacy")
    assert payload["tabs"][0]["body"]["blocks"][0]["text"] == "Legacy text"


def test_truncate_google_docs_get_response_small():
    raw = {"documentId": "x", "title": "T", "body": {"content": []}}
    out, truncated = truncate_google_docs_get_response(raw, max_json_chars=100_000)
    assert truncated is False
    assert out["title"] == "T"


def test_truncate_google_docs_get_response_huge():
    raw = {"documentId": "x", "title": "T", "body": {"content": ["x" * 500_000]}}
    out, truncated = truncate_google_docs_get_response(raw, max_json_chars=100)
    assert truncated is True
    assert out.get("_truncated") is True
