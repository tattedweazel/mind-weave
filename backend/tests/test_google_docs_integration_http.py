"""HTTP layer tests for google_docs integration (mocked httpx)."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.integrations.google_docs import (
    GoogleDocsUrlParseError,
    docs_get_document,
    fetch_inline_image_bytes,
    parse_google_docs_url_or_id,
)


@pytest.mark.asyncio
async def test_docs_get_document():
    fake = {"documentId": "abc", "title": "Hi"}
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = fake
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.integrations.google_docs.httpx.AsyncClient", return_value=mock_client):
        out = await docs_get_document("tok", "abc", include_tabs_content=True)
    assert out == fake
    mock_client.get.assert_called_once()
    call_kwargs = mock_client.get.call_args
    assert "includeTabsContent" in str(call_kwargs)


@pytest.mark.asyncio
async def test_fetch_inline_image_bytes():
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.content = b"imgbytes"
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.integrations.google_docs.httpx.AsyncClient", return_value=mock_client):
        data = await fetch_inline_image_bytes("tok", "https://example.com/x")
    assert data == b"imgbytes"


@pytest.mark.asyncio
async def test_fetch_inline_image_bytes_empty_uri():
    with pytest.raises(ValueError):
        await fetch_inline_image_bytes("tok", "")
