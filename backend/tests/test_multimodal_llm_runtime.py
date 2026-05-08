"""Unit tests for multimodal LLM image normalization (no DB, no HTTP)."""

import uuid

import pytest

from app.domain.workflow_executor.multimodal_llm_runtime import (
    MultimodalLLMInputError,
    detect_image_mime,
    normalize_images_input,
)

_MINI_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_detect_image_mime_png():
    assert detect_image_mime(_MINI_PNG) == "image/png"


def test_detect_image_mime_unknown():
    assert detect_image_mime(b"not an image") is None


def test_normalize_images_from_snapshot_shape():
    aid = uuid.uuid4()
    ids = normalize_images_input({"image": {"artifact_id": str(aid), "mime_type": "image/png"}})
    assert ids == [aid]


def test_normalize_images_list():
    a, b = uuid.uuid4(), uuid.uuid4()
    ids = normalize_images_input([{"artifact_id": str(a)}, {"artifact_id": str(b)}])
    assert ids == [a, b]


def test_normalize_images_list_of_capture_url_snapshot_outputs():
    """Wiring List(images) from multiple snapshots — each element is the full skill output dict."""
    aid = uuid.uuid4()
    row = [
        {
            "image": {
                "artifact_id": str(aid),
                "mime_type": "image/png",
                "width": 1280,
                "height": 2569,
            },
            "final_url": "https://books.toscrape.com/",
            "captured_at": "2026-04-23T18:45:00.494384Z",
            "duration_ms": 0,
            "cached": True,
        }
    ]
    ids = normalize_images_input(row)
    assert ids == [aid]


def test_normalize_images_list_mixed_snapshot_and_plain_refs():
    a, b = uuid.uuid4(), uuid.uuid4()
    ids = normalize_images_input(
        [
            {"image": {"artifact_id": str(a), "mime_type": "image/png"}},
            {"artifact_id": str(b)},
        ]
    )
    assert ids == [a, b]


def test_normalize_images_empty_list_raises():
    with pytest.raises(MultimodalLLMInputError) as ei:
        normalize_images_input([])
    assert ei.value.code == "MISSING_IMAGE_INPUT"


def test_normalize_images_none_raises():
    with pytest.raises(MultimodalLLMInputError) as ei:
        normalize_images_input(None)
    assert ei.value.code == "MISSING_IMAGE_INPUT"
