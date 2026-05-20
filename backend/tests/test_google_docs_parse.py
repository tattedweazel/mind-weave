"""Google Docs parse utility (no HTTP)."""

from app.domain.workflow_executor.google_docs_parse import (
    extract_document_payload,
    normalize_chunk_strategy,
    parse_document_payload_to_chunks,
)


def _sample_payload() -> dict:
    return {
        "document_id": "doc1",
        "title": "Sample",
        "tabs": [
            {
                "tab_id": "t0",
                "title": "Tab A",
                "body": {
                    "blocks": [
                        {"type": "paragraph", "text": "Hello tab A"},
                        {
                            "type": "table",
                            "rows": [[{"text": "cell1"}, {"text": "cell2"}]],
                        },
                    ]
                },
                "child_tabs": [
                    {
                        "tab_id": "t0c",
                        "title": "Child",
                        "body": {"blocks": [{"type": "paragraph", "text": "Nested"}]},
                    }
                ],
            },
            {
                "tab_id": "t1",
                "title": "Tab B",
                "body": {"blocks": [{"type": "paragraph", "text": "Tab B text"}]},
            },
        ],
    }


def test_normalize_chunk_strategy_defaults():
    assert normalize_chunk_strategy(None) == "structure"
    assert normalize_chunk_strategy("TAB") == "tab"
    assert normalize_chunk_strategy("unknown") == "structure"


def test_extract_document_payload_wrapper():
    inner = _sample_payload()
    wrapped = {"document_payload": inner}
    assert extract_document_payload(wrapped) == inner


def test_parse_structure_strategy():
    chunks = parse_document_payload_to_chunks(_sample_payload(), chunk_strategy="structure")
    kinds = [c["kind"] for c in chunks]
    assert "text" in kinds
    assert "table" in kinds
    assert all("chunk_id" in c and "tab_path" in c for c in chunks)


def test_parse_tab_strategy():
    chunks = parse_document_payload_to_chunks(_sample_payload(), chunk_strategy="tab")
    assert len(chunks) >= 2
    assert all(c["kind"] == "text" for c in chunks)


def test_parse_flat_strategy():
    chunks = parse_document_payload_to_chunks(_sample_payload(), chunk_strategy="flat")
    assert len(chunks) == 1
    assert chunks[0]["kind"] == "text"
    assert "Hello tab A" in chunks[0]["text"]
