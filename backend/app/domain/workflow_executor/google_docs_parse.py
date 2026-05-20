"""Parse curated google_docs document_payload into generic chunks (no I/O)."""

from __future__ import annotations

from typing import Any, Literal, Optional

ChunkStrategy = Literal["structure", "tab", "flat"]


def normalize_chunk_strategy(raw: Any) -> ChunkStrategy:
    s = str(raw or "structure").strip().lower()
    if s in ("tab", "flat", "structure"):
        return s  # type: ignore[return-value]
    return "structure"


def extract_document_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Accept skill output dict (document_payload key) or payload itself."""
    if "document_payload" in data and isinstance(data["document_payload"], dict):
        return data["document_payload"]
    if "tabs" in data or "document_id" in data:
        return data
    raise ValueError("Input is not a Google Docs document payload")


def _image_ref(img: dict[str, Any]) -> Optional[dict[str, Any]]:
    aid = img.get("artifact_id")
    if not isinstance(aid, str) or not aid.strip():
        return None
    return {
        "artifact_id": aid.strip(),
        "mime_type": img.get("mime_type") if isinstance(img.get("mime_type"), str) else "image/png",
        "width": int(img.get("width") or 1),
        "height": int(img.get("height") or 1),
    }


def _blocks_to_text(blocks: list[Any], *, max_chars: int) -> str:
    parts: list[str] = []
    for blk in blocks:
        if not isinstance(blk, dict):
            continue
        if blk.get("type") == "paragraph":
            t = blk.get("text")
            if isinstance(t, str) and t.strip():
                parts.append(t.strip())
        elif blk.get("type") == "table":
            for row in blk.get("rows") or []:
                row_parts: list[str] = []
                for cell in row:
                    if isinstance(cell, dict):
                        ct = cell.get("text")
                        if isinstance(ct, str) and ct.strip():
                            row_parts.append(ct.strip())
                if row_parts:
                    parts.append(" | ".join(row_parts))
    text = "\n\n".join(parts)
    if max_chars > 0 and len(text) > max_chars:
        return text[:max_chars]
    return text


def _iter_tabs(
    tabs: list[Any],
    path: list[str],
) -> list[tuple[dict[str, Any], list[str]]]:
    out: list[tuple[dict[str, Any], list[str]]] = []
    for tab in tabs:
        if not isinstance(tab, dict):
            continue
        title = tab.get("title")
        seg = title if isinstance(title, str) and title.strip() else (tab.get("tab_id") or "tab")
        seg_s = str(seg)
        new_path = path + [seg_s]
        out.append((tab, new_path))
        children = tab.get("child_tabs")
        if isinstance(children, list):
            out.extend(_iter_tabs(children, new_path))
    return out


def parse_document_payload_to_chunks(
    payload: dict[str, Any],
    *,
    chunk_strategy: ChunkStrategy = "structure",
    max_chunk_text_chars: int = 8000,
) -> list[dict[str, Any]]:
    """Emit generic chunk dicts from curated document_payload."""
    tabs = payload.get("tabs")
    if not isinstance(tabs, list):
        tabs = []
    doc_id = payload.get("document_id") if isinstance(payload.get("document_id"), str) else ""
    chunks: list[dict[str, Any]] = []
    seq = 0

    def next_chunk_id(kind: str, tab_path: list[str], suffix: str) -> str:
        path_s = "/".join(tab_path) if tab_path else "root"
        return f"{doc_id}:{path_s}:{kind}:{suffix}"

    def append_chunk(
        *,
        kind: str,
        tab_id: Optional[str],
        tab_title: Optional[str],
        tab_path: list[str],
        text: str = "",
        table: Optional[dict[str, Any]] = None,
        images: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        nonlocal seq
        entry: dict[str, Any] = {
            "chunk_id": next_chunk_id(kind, tab_path, str(seq)),
            "kind": kind,
            "tab_id": tab_id,
            "tab_title": tab_title,
            "tab_path": tab_path,
            "sequence_index": seq,
        }
        if kind == "text" and text:
            entry["text"] = text
        if kind == "table" and table is not None:
            entry["table"] = table
        if kind == "image" and images:
            entry["images"] = images
        chunks.append(entry)
        seq += 1

    if chunk_strategy == "flat":
        all_text_parts: list[str] = []
        for tab, path in _iter_tabs(tabs, []):
            body = tab.get("body")
            blocks = body.get("blocks") if isinstance(body, dict) else []
            if isinstance(blocks, list):
                all_text_parts.append(_blocks_to_text(blocks, max_chars=0))
        full = "\n\n".join(p for p in all_text_parts if p)
        if max_chunk_text_chars > 0 and len(full) > max_chunk_text_chars:
            full = full[:max_chunk_text_chars]
        append_chunk(
            kind="text",
            tab_id=None,
            tab_title=None,
            tab_path=[],
            text=full,
        )
        return chunks

    for tab, tab_path in _iter_tabs(tabs, []):
        tab_id = tab.get("tab_id") if isinstance(tab.get("tab_id"), str) else None
        tab_title = tab.get("title") if isinstance(tab.get("title"), str) else None
        body = tab.get("body")
        blocks = body.get("blocks") if isinstance(body, dict) else []
        if not isinstance(blocks, list):
            blocks = []

        if chunk_strategy == "tab":
            text = _blocks_to_text(blocks, max_chars=max_chunk_text_chars)
            append_chunk(
                kind="text",
                tab_id=tab_id,
                tab_title=tab_title,
                tab_path=tab_path,
                text=text,
            )
            continue

        # structure
        text_buf: list[str] = []
        for blk in blocks:
            if not isinstance(blk, dict):
                continue
            btype = blk.get("type")
            if btype == "paragraph":
                t = blk.get("text")
                imgs = blk.get("images")
                if isinstance(imgs, list):
                    refs = [_image_ref(i) for i in imgs if isinstance(i, dict)]
                    refs_ok = [r for r in refs if r]
                    if refs_ok and not (isinstance(t, str) and t.strip()):
                        append_chunk(
                            kind="image",
                            tab_id=tab_id,
                            tab_title=tab_title,
                            tab_path=tab_path,
                            images=refs_ok,
                        )
                        continue
                if isinstance(t, str) and t.strip():
                    text_buf.append(t.strip())
                if isinstance(imgs, list):
                    refs = [_image_ref(i) for i in imgs if isinstance(i, dict)]
                    refs_ok = [r for r in refs if r]
                    if refs_ok:
                        if text_buf:
                            combined = "\n\n".join(text_buf)
                            if max_chunk_text_chars > 0 and len(combined) > max_chunk_text_chars:
                                combined = combined[:max_chunk_text_chars]
                            append_chunk(
                                kind="text",
                                tab_id=tab_id,
                                tab_title=tab_title,
                                tab_path=tab_path,
                                text=combined,
                            )
                            text_buf = []
                        append_chunk(
                            kind="image",
                            tab_id=tab_id,
                            tab_title=tab_title,
                            tab_path=tab_path,
                            images=refs_ok,
                        )
            elif btype == "table":
                if text_buf:
                    combined = "\n\n".join(text_buf)
                    if max_chunk_text_chars > 0 and len(combined) > max_chunk_text_chars:
                        combined = combined[:max_chunk_text_chars]
                    append_chunk(
                        kind="text",
                        tab_id=tab_id,
                        tab_title=tab_title,
                        tab_path=tab_path,
                        text=combined,
                    )
                    text_buf = []
                rows_out: list[list[dict[str, Any]]] = []
                for row in blk.get("rows") or []:
                    row_cells: list[dict[str, Any]] = []
                    for cell in row:
                        if not isinstance(cell, dict):
                            continue
                        cell_entry: dict[str, Any] = {
                            "text": cell.get("text") if isinstance(cell.get("text"), str) else "",
                        }
                        cell_imgs = cell.get("images")
                        if isinstance(cell_imgs, list):
                            refs = [_image_ref(i) for i in cell_imgs if isinstance(i, dict)]
                            refs_ok = [r for r in refs if r]
                            if refs_ok:
                                cell_entry["images"] = refs_ok
                        row_cells.append(cell_entry)
                    if row_cells:
                        rows_out.append(row_cells)
                if rows_out:
                    append_chunk(
                        kind="table",
                        tab_id=tab_id,
                        tab_title=tab_title,
                        tab_path=tab_path,
                        table={"rows": rows_out},
                    )
        if text_buf:
            combined = "\n\n".join(text_buf)
            if max_chunk_text_chars > 0 and len(combined) > max_chunk_text_chars:
                combined = combined[:max_chunk_text_chars]
            append_chunk(
                kind="text",
                tab_id=tab_id,
                tab_title=tab_title,
                tab_path=tab_path,
                text=combined,
            )

    return chunks
