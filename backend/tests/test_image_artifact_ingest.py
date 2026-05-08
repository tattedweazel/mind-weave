"""image_artifact_ingest: MIME and dimensions (no transforms)."""

from __future__ import annotations

import pytest

from app.domain.workflow_executor.image_artifact_ingest import (
    ImageIngestError,
    validate_and_measure_image_bytes,
)

_MINI_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_validate_png_1x1():
    mime, w, h = validate_and_measure_image_bytes(_MINI_PNG)
    assert mime == "image/png"
    assert w == 1 and h == 1


def test_validate_rejects_empty():
    with pytest.raises(ImageIngestError, match="Empty"):
        validate_and_measure_image_bytes(b"")


def test_validate_rejects_random_bytes():
    with pytest.raises(ImageIngestError, match="Only PNG"):
        validate_and_measure_image_bytes(b"hello world not an image")
