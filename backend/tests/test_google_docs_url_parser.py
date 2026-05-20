"""Google Docs URL / document id parsing."""

import pytest

from app.integrations.google_docs import GoogleDocsUrlParseError, parse_google_docs_url_or_id


def test_parse_raw_document_id():
    doc_id = "1a2b3c4d5e6f7g8h9i0jklmnop"
    assert parse_google_docs_url_or_id(doc_id) == doc_id


def test_parse_docs_google_url():
    doc_id = "abc123XYZ"
    url = f"https://docs.google.com/document/d/{doc_id}/edit?usp=sharing"
    assert parse_google_docs_url_or_id(url) == doc_id


def test_parse_drive_file_url():
    doc_id = "driveDocId99"
    url = f"https://drive.google.com/file/d/{doc_id}/view"
    assert parse_google_docs_url_or_id(url) == doc_id


def test_parse_empty_raises():
    with pytest.raises(GoogleDocsUrlParseError):
        parse_google_docs_url_or_id("   ")


def test_parse_invalid_raises():
    with pytest.raises(GoogleDocsUrlParseError):
        parse_google_docs_url_or_id("short")
