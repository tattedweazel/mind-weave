"""Ingest image bytes into ``url_snapshot_artifacts``-compatible metadata (no pixel transforms)."""

from __future__ import annotations

from typing import Optional, Tuple

from app.domain.workflow_executor.capture_url_snapshot_runtime import png_dimensions
from app.domain.workflow_executor.multimodal_llm_runtime import detect_image_mime

_SUPPORTED_MIMES = frozenset({"image/png", "image/jpeg", "image/webp"})


class ImageIngestError(ValueError):
    """Invalid or unsupported image bytes."""


def jpeg_dimensions(data: bytes) -> Optional[Tuple[int, int]]:
    """Return (width, height) from the first SOF0–SOF3 / SOF5–SOF7 / SOF9–SOF11 segment, or None."""
    n = len(data)
    i = 0
    while i < n - 1:
        if data[i] != 0xFF or i + 1 >= n:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            if i + 9 >= n:
                return None
            h = (data[i + 5] << 8) | data[i + 6]
            w = (data[i + 7] << 8) | data[i + 8]
            if w < 1 or h < 1:
                return None
            return (w, h)
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7 or marker == 0x01:
            i += 2
            continue
        if marker == 0xFF:
            i += 1
            continue
        if i + 3 >= n:
            break
        seg_len = (data[i + 2] << 8) | data[i + 3]
        if seg_len < 2 or i + 1 + seg_len > n:
            i += 2
            continue
        i += 2 + seg_len
    return None


def webp_dimensions(data: bytes) -> Optional[Tuple[int, int]]:
    """Return (width, height) from a WebP container, or None."""
    if len(data) < 30 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return None
    offset = 12
    n = len(data)
    while offset + 8 <= n:
        chunk_id = data[offset : offset + 4]
        chunk_size = int.from_bytes(data[offset + 4 : offset + 8], "little")
        payload_start = offset + 8
        pay_end = min(payload_start + chunk_size, n)
        pay = data[payload_start:pay_end]
        if chunk_id == b"VP8 " and len(pay) >= 10 and pay[:3] == b"\x9d\x01\x2a":
            w = int.from_bytes(pay[6:8], "little") & 0x3FFF
            h = int.from_bytes(pay[8:10], "little") & 0x3FFF
            if w >= 1 and h >= 1:
                return (w, h)
        if chunk_id == b"VP8L" and len(pay) >= 5 and pay[0] == 0x2F:
            bits = int.from_bytes(pay[1:5], "little")
            w = (bits & 0x3FFF) + 1
            h = ((bits >> 14) & 0x3FFF) + 1
            if w >= 1 and h >= 1:
                return (w, h)
        if chunk_id == b"VP8X" and len(pay) >= 10:
            w = 1 + int.from_bytes(pay[4:7], "little")
            h = 1 + int.from_bytes(pay[7:10], "little")
            if w >= 1 and h >= 1:
                return (w, h)
        # RIFF subchunks are padded to even size
        padded = chunk_size + (chunk_size & 1)
        offset = payload_start + padded
    return None


def image_dimensions(mime: str, data: bytes) -> Optional[Tuple[int, int]]:
    if mime == "image/png":
        return png_dimensions(data)
    if mime == "image/jpeg":
        return jpeg_dimensions(data)
    if mime == "image/webp":
        return webp_dimensions(data)
    return None


def validate_and_measure_image_bytes(data: bytes) -> Tuple[str, int, int]:
    """
    Return (mime_type, width, height) for supported PNG, JPEG, or WebP.
    Raises ImageIngestError on failure.
    """
    if not data:
        raise ImageIngestError("Empty file.")
    mime = detect_image_mime(data)
    if mime is None or mime not in _SUPPORTED_MIMES:
        raise ImageIngestError("Only PNG, JPEG, and WebP images are supported.")
    dims = image_dimensions(mime, data)
    if dims is None:
        raise ImageIngestError("Could not read image dimensions (file may be truncated or invalid).")
    w, h = dims
    return (mime, w, h)
