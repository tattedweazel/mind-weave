"""Google Docs API helpers — mock httpx in tests."""

from __future__ import annotations

import re
from typing import Any, cast
from urllib.parse import quote, unquote

import httpx

DOCS_API_BASE = "https://docs.googleapis.com/v1"

# docs.google.com/document/d/{id}/...
_DOCS_URL_RE = re.compile(
    r"(?:https?://)?(?:docs\.google\.com/document/d/|drive\.google\.com/file/d/)([a-zA-Z0-9_-]+)",
)
# Bare document id (typical length 40+)
_DOC_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{10,}$")


class GoogleDocsUrlParseError(ValueError):
    """Could not extract a document id from user input."""


def parse_google_docs_url_or_id(raw: str) -> str:
    """
    Resolve a Google Docs document id from a pasted URL or raw id string.
    Raises GoogleDocsUrlParseError when no id can be determined.
    """
    s = unquote((raw or "").strip())
    if not s:
        raise GoogleDocsUrlParseError("Document URL or ID is required")
    m = _DOCS_URL_RE.search(s)
    if m:
        return m.group(1)
    if _DOC_ID_RE.match(s):
        return s
    raise GoogleDocsUrlParseError(
        "Expected a Google Docs URL (docs.google.com/document/d/...) or document id"
    )


async def docs_get_document(
    access_token: str,
    document_id: str,
    *,
    include_tabs_content: bool = True,
) -> dict[str, Any]:
    """GET documents/{documentId} — returns raw API JSON."""
    doc_id = quote(str(document_id).strip(), safe="")
    params: dict[str, Any] = {}
    if include_tabs_content:
        params["includeTabsContent"] = "true"
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{DOCS_API_BASE}/documents/{doc_id}",
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=120.0,
        )
        r.raise_for_status()
        return cast(dict[str, Any], r.json())


async def fetch_inline_image_bytes(access_token: str, content_uri: str) -> bytes:
    """Authenticated GET for a Docs inline image contentUri."""
    uri = (content_uri or "").strip()
    if not uri:
        raise ValueError("Empty image content URI")
    async with httpx.AsyncClient() as client:
        r = await client.get(
            uri,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=60.0,
            follow_redirects=True,
        )
        r.raise_for_status()
        return r.content
