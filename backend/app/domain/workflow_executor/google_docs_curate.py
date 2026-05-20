"""Curate Google Docs API responses into workflow-facing document_payload."""

from __future__ import annotations

import json
import uuid
from copy import deepcopy
from typing import Any, Callable, Optional

from sqlmodel import Session

from app.core.config import settings
from app.core.text_noise import filter_text_noise
from app.domain.services.url_snapshot_cache_service import create_artifact
from app.domain.workflow_executor.capture_url_snapshot_runtime import png_dimensions
from app.integrations.google_docs import fetch_inline_image_bytes

GOOGLE_DOCS_LIST_MAX_FOR_DIAGNOSTICS = 1

ImageResolver = Callable[[str, dict[str, Any]], Optional[dict[str, Any]]]


def truncate_google_docs_get_response(
    raw: dict[str, Any],
    *,
    max_json_chars: int | None = None,
) -> tuple[dict[str, Any], bool]:
    """Shrink vendor JSON for skill_diagnostics when huge."""
    cap = max_json_chars or settings.GOOGLE_DOCS_GET_MAX_DIAGNOSTICS_JSON_CHARS
    try:
        blob = json.dumps(raw, ensure_ascii=False)
    except (TypeError, ValueError):
        return {"_truncated": True, "title": raw.get("title")}, True
    if len(blob) <= cap:
        return deepcopy(raw), False
    return {
        "documentId": raw.get("documentId"),
        "title": raw.get("title"),
        "revisionId": raw.get("revisionId"),
        "_truncated": True,
        "_original_json_chars": len(blob),
    }, True


def _clean_text(text: str, *, max_chars: int) -> tuple[str, bool]:
    cleaned, noise_truncated = filter_text_noise(text or "")
    if max_chars > 0 and len(cleaned) > max_chars:
        return cleaned[:max_chars], True
    return cleaned, bool(noise_truncated)


def _paragraph_text(paragraph: dict[str, Any], *, max_chars: int) -> tuple[str, bool]:
    parts: list[str] = []
    truncated = False
    for el in paragraph.get("elements") or []:
        if not isinstance(el, dict):
            continue
        tr = el.get("textRun")
        if isinstance(tr, dict) and isinstance(tr.get("content"), str):
            parts.append(tr["content"])
        # inlineObjectElement handled at structure walk
    raw = "".join(parts)
    return _clean_text(raw, max_chars=max_chars)


def _walk_structural_content(
    content: list[Any],
    *,
    max_chars: int,
    inline_objects: dict[str, Any],
    image_resolver: ImageResolver,
    blocks: list[dict[str, Any]],
) -> None:
    for item in content:
        if not isinstance(item, dict):
            continue
        if "paragraph" in item:
            para = item["paragraph"]
            if not isinstance(para, dict):
                continue
            text, tr = _paragraph_text(para, max_chars=max_chars)
            para_images: list[dict[str, Any]] = []
            for el in para.get("elements") or []:
                if not isinstance(el, dict):
                    continue
                ioe = el.get("inlineObjectElement")
                if not isinstance(ioe, dict):
                    continue
                oid = ioe.get("inlineObjectId")
                if isinstance(oid, str) and oid.strip():
                    resolved = image_resolver(oid.strip(), inline_objects)
                    if resolved:
                        para_images.append(resolved)
            if (text and text.strip()) or para_images:
                blk: dict[str, Any] = {"type": "paragraph", "text": text}
                if tr:
                    blk["text_truncated"] = True
                if para_images:
                    blk["images"] = para_images
                blocks.append(blk)
        elif "table" in item:
            table = item["table"]
            if not isinstance(table, dict):
                continue
            rows_out: list[list[dict[str, Any]]] = []
            for row in table.get("tableRows") or []:
                if not isinstance(row, dict):
                    continue
                cells_out: list[dict[str, Any]] = []
                for cell in row.get("tableCells") or []:
                    if not isinstance(cell, dict):
                        continue
                    cell_blocks: list[dict[str, Any]] = []
                    cell_content = cell.get("content")
                    if isinstance(cell_content, list):
                        _walk_structural_content(
                            cell_content,
                            max_chars=max_chars,
                            inline_objects=inline_objects,
                            image_resolver=image_resolver,
                            blocks=cell_blocks,
                        )
                    cell_text_parts = [
                        b.get("text", "")
                        for b in cell_blocks
                        if b.get("type") == "paragraph" and isinstance(b.get("text"), str)
                    ]
                    cell_images: list[dict[str, Any]] = []
                    for b in cell_blocks:
                        for img in b.get("images") or []:
                            if isinstance(img, dict):
                                cell_images.append(img)
                    joined, cell_tr = _clean_text("\n".join(cell_text_parts), max_chars=max_chars)
                    cell_entry: dict[str, Any] = {"text": joined}
                    if cell_tr:
                        cell_entry["text_truncated"] = True
                    if cell_images:
                        cell_entry["images"] = cell_images
                    cells_out.append(cell_entry)
                if cells_out:
                    rows_out.append(cells_out)
            if rows_out:
                blocks.append({"type": "table", "rows": rows_out})
        elif "sectionBreak" in item:
            blocks.append({"type": "section_break"})
        elif "tableOfContents" in item:
            blocks.append({"type": "table_of_contents"})


def _inline_objects_for_tab(tab: dict[str, Any], document_inline: dict[str, Any]) -> dict[str, Any]:
    doc_tab = tab.get("documentTab")
    if isinstance(doc_tab, dict):
        io = doc_tab.get("inlineObjects")
        if isinstance(io, dict):
            return io
    return document_inline if isinstance(document_inline, dict) else {}


def _curate_tab_body(
    tab: dict[str, Any],
    *,
    document_inline: dict[str, Any],
    max_chars: int,
    image_resolver: ImageResolver,
) -> dict[str, Any]:
    doc_tab = tab.get("documentTab")
    if not isinstance(doc_tab, dict):
        return {"blocks": []}
    body = doc_tab.get("body")
    if not isinstance(body, dict):
        return {"blocks": []}
    content = body.get("content")
    if not isinstance(content, list):
        return {"blocks": []}
    inline_objects = _inline_objects_for_tab(tab, document_inline)
    blocks: list[dict[str, Any]] = []
    _walk_structural_content(
        content,
        max_chars=max_chars,
        inline_objects=inline_objects,
        image_resolver=image_resolver,
        blocks=blocks,
    )
    return {"blocks": blocks}


def _curate_tabs_tree(
    tabs: list[Any],
    *,
    document_inline: dict[str, Any],
    max_chars: int,
    image_resolver: ImageResolver,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for tab in tabs:
        if not isinstance(tab, dict):
            continue
        props = tab.get("tabProperties")
        tab_id = None
        title = None
        if isinstance(props, dict):
            tab_id = props.get("tabId")
            title = props.get("title")
        entry: dict[str, Any] = {
            "tab_id": tab_id if isinstance(tab_id, str) else None,
            "title": title if isinstance(title, str) else None,
            "body": _curate_tab_body(
                tab,
                document_inline=document_inline,
                max_chars=max_chars,
                image_resolver=image_resolver,
            ),
        }
        child = tab.get("childTabs")
        if isinstance(child, list) and child:
            entry["child_tabs"] = _curate_tabs_tree(
                child,
                document_inline=document_inline,
                max_chars=max_chars,
                image_resolver=image_resolver,
            )
        out.append(entry)
    return out


def _embedded_image_meta(inline_obj: dict[str, Any]) -> tuple[Optional[str], int, int]:
    """Return (content_uri, width, height) from an InlineObject."""
    props = inline_obj.get("inlineObjectProperties")
    if not isinstance(props, dict):
        return None, 1, 1
    emb = props.get("embeddedObject")
    if not isinstance(emb, dict):
        return None, 1, 1
    w, h = 1, 1
    size = emb.get("size")
    if isinstance(size, dict):
        for dim_key, fallback in (("width", 100), ("height", 100)):
            d = size.get(dim_key)
            if isinstance(d, dict) and isinstance(d.get("magnitude"), (int, float)):
                # PT → rough px for metadata (display only)
                val = max(1, int(float(d["magnitude"]) * 1.33))
                if dim_key == "width":
                    w = val
                else:
                    h = val
    img = emb.get("imageProperties")
    uri = None
    if isinstance(img, dict) and isinstance(img.get("contentUri"), str):
        uri = img["contentUri"]
    if not uri and isinstance(emb.get("image"), dict):
        inner = emb["image"]
        if isinstance(inner.get("contentUri"), str):
            uri = inner["contentUri"]
    return uri, w, h


def _guess_mime(image_bytes: bytes, content_uri: str) -> str:
    u = content_uri.lower()
    if ".png" in u or image_bytes.startswith(b"\x89PNG"):
        return "image/png"
    if ".gif" in u or image_bytes[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if ".webp" in u or (len(image_bytes) > 12 and image_bytes[8:12] == b"WEBP"):
        return "image/webp"
    if ".jpg" in u or ".jpeg" in u or image_bytes.startswith(b"\xff\xd8"):
        return "image/jpeg"
    return "image/png"


async def build_document_payload(
    session: Session,
    user_id: uuid.UUID,
    access_token: str,
    raw_document: dict[str, Any],
    *,
    document_id: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Curate vendor document JSON and download inline images into url_snapshot_artifacts.
    Returns (document_payload, fetch_errors).
    """
    max_chars = settings.GOOGLE_DOCS_MAX_TEXT_CHARS_PER_FIELD
    max_images = settings.GOOGLE_DOCS_MAX_INLINE_IMAGES_PER_RUN
    max_image_bytes = settings.GOOGLE_DOCS_MAX_INLINE_IMAGE_BYTES
    fetch_errors: list[dict[str, Any]] = []
    images_downloaded = 0
    resolved_artifacts: dict[str, dict[str, Any]] = {}

    doc_inline = raw_document.get("inlineObjects")
    if not isinstance(doc_inline, dict):
        doc_inline = {}

    def image_resolver(object_id: str, inline_objects: dict[str, Any]) -> Optional[dict[str, Any]]:
        if object_id in resolved_artifacts:
            return resolved_artifacts[object_id]
        obj = inline_objects.get(object_id)
        if not isinstance(obj, dict):
            return {"_pending": True, "object_id": object_id, "error": "Inline object not found"}
        uri, w, h = _embedded_image_meta(obj)
        if not uri:
            return {"_pending": True, "object_id": object_id, "error": "No image content URI"}
        return {
            "_pending": True,
            "content_uri": uri,
            "width": w,
            "height": h,
            "object_id": object_id,
        }

    tabs_raw = raw_document.get("tabs")
    tabs_curated: list[dict[str, Any]] = []
    if isinstance(tabs_raw, list) and tabs_raw:
        tabs_curated = _curate_tabs_tree(
            tabs_raw,
            document_inline=doc_inline,
            max_chars=max_chars,
            image_resolver=image_resolver,
        )
    else:
        # Legacy single body
        legacy_tab = {"documentTab": {"body": raw_document.get("body"), "inlineObjects": doc_inline}}
        tabs_curated = [
            {
                "tab_id": None,
                "title": None,
                "body": _curate_tab_body(
                    legacy_tab,
                    document_inline=doc_inline,
                    max_chars=max_chars,
                    image_resolver=image_resolver,
                ),
            }
        ]

    pending_by_oid: dict[str, dict[str, Any]] = {}

    def collect_pending_from_blocks(blocks: list[dict[str, Any]]) -> None:
        for blk in blocks:
            if not isinstance(blk, dict):
                continue
            for img in blk.get("images") or []:
                if isinstance(img, dict) and img.get("_pending") and isinstance(img.get("object_id"), str):
                    pending_by_oid.setdefault(img["object_id"], img)
            if blk.get("type") == "table":
                for row in blk.get("rows") or []:
                    for cell in row:
                        for img in cell.get("images") or []:
                            if (
                                isinstance(img, dict)
                                and img.get("_pending")
                                and isinstance(img.get("object_id"), str)
                            ):
                                pending_by_oid.setdefault(img["object_id"], img)

    def walk_tabs_for_pending(tabs: list[dict[str, Any]]) -> None:
        for t in tabs:
            body = t.get("body")
            if isinstance(body, dict):
                collect_pending_from_blocks(body.get("blocks") or [])
            children = t.get("child_tabs")
            if isinstance(children, list):
                walk_tabs_for_pending(children)

    walk_tabs_for_pending(tabs_curated)

    for oid, img in pending_by_oid.items():
        if images_downloaded >= max_images:
            fetch_errors.append({"inline_object_id": oid, "error": "Max inline images per run exceeded"})
            continue
        uri = img.get("content_uri")
        if not isinstance(uri, str) or not uri.strip():
            err = img.get("error") or "No image content URI"
            fetch_errors.append({"inline_object_id": oid, "error": str(err)})
            continue
        w = int(img.get("width") or 1)
        h = int(img.get("height") or 1)
        try:
            image_bytes = await fetch_inline_image_bytes(access_token, uri)
        except Exception as e:
            fetch_errors.append({"inline_object_id": oid, "error": str(e)[:500]})
            continue
        if len(image_bytes) > max_image_bytes:
            fetch_errors.append(
                {
                    "inline_object_id": oid,
                    "error": f"Image exceeds max bytes ({max_image_bytes})",
                }
            )
            continue
        mime = _guess_mime(image_bytes, uri)
        dims = png_dimensions(image_bytes) if mime == "image/png" else None
        width, height = (dims if dims else (w, h))
        final_url = f"google_docs:{document_id}:{oid}"
        art = create_artifact(
            session,
            user_id,
            image_bytes,
            width=width,
            height=height,
            final_url=final_url,
            mime_type=mime,
        )
        images_downloaded += 1
        resolved_artifacts[oid] = {
            "artifact_id": str(art.id),
            "mime_type": mime,
            "width": width,
            "height": height,
            "inline_object_id": oid,
        }

    def resolve_images_in_blocks(blocks: list[dict[str, Any]]) -> None:
        for blk in blocks:
            if not isinstance(blk, dict):
                continue
            if blk.get("images"):
                resolved_imgs = []
                for img in blk["images"]:
                    if not isinstance(img, dict):
                        continue
                    oid = img.get("object_id") or img.get("inline_object_id")
                    if isinstance(oid, str) and oid in resolved_artifacts:
                        resolved_imgs.append(resolved_artifacts[oid])
                if resolved_imgs:
                    blk["images"] = resolved_imgs
                else:
                    blk.pop("images", None)
            if blk.get("type") == "table":
                for row in blk.get("rows") or []:
                    for cell in row:
                        if cell.get("images"):
                            resolved = []
                            for img in cell["images"]:
                                oid = img.get("object_id") if isinstance(img, dict) else None
                                if isinstance(oid, str) and oid in resolved_artifacts:
                                    resolved.append(resolved_artifacts[oid])
                            if resolved:
                                cell["images"] = resolved
                            else:
                                cell.pop("images", None)

    def walk_resolve(tabs: list[dict[str, Any]]) -> None:
        for t in tabs:
            body = t.get("body")
            if isinstance(body, dict):
                resolve_images_in_blocks(body.get("blocks") or [])
            children = t.get("child_tabs")
            if isinstance(children, list):
                walk_resolve(children)

    walk_resolve(tabs_curated)

    def count_tabs(tabs: list[dict[str, Any]]) -> int:
        n = 0
        for t in tabs:
            n += 1
            n += count_tabs(t.get("child_tabs") or [])
        return n

    payload: dict[str, Any] = {
        "document_id": document_id,
        "title": raw_document.get("title") if isinstance(raw_document.get("title"), str) else "",
        "revision_id": raw_document.get("revisionId"),
        "tabs": tabs_curated,
        "tab_count": count_tabs(tabs_curated),
        "image_count": images_downloaded,
        "fetch_errors": fetch_errors,
    }
    return payload, fetch_errors
