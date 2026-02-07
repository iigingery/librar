from __future__ import annotations

from librar.ingestion.chunking import build_chunks
from librar.ingestion.models import DocumentBlock, ExtractedDocument, ExtractedMetadata, SourceRef


def _doc_with_blocks(blocks: list[DocumentBlock]) -> ExtractedDocument:
    return ExtractedDocument(source_path="books/sample.txt", metadata=ExtractedMetadata(format="txt"), blocks=blocks)


def test_chunking_preserves_locator_domain_and_boundaries() -> None:
    document = _doc_with_blocks(
        [
            DocumentBlock(text="alpha beta gamma", source=SourceRef(page=1, chapter="One", item_id="item-1", char_start=0, char_end=16)),
            DocumentBlock(text="delta epsilon", source=SourceRef(page=1, chapter="One", item_id="item-1", char_start=17, char_end=30)),
            DocumentBlock(text="new chapter text", source=SourceRef(page=1, chapter="Two", item_id="item-2", char_start=0, char_end=16)),
        ]
    )

    chunks = build_chunks(document, max_chars=40, overlap_chars=10)

    assert len(chunks) == 2
    assert chunks[0].source.chapter == "One"
    assert chunks[0].source.item_id == "item-1"
    assert chunks[0].source.char_start == 0
    assert chunks[0].source.char_end is not None
    assert chunks[1].source.chapter == "Two"
    assert chunks[1].source.item_id == "item-2"
    assert "new chapter text" in chunks[1].text


def test_chunking_applies_overlap_with_deterministic_offsets() -> None:
    document = _doc_with_blocks(
        [
            DocumentBlock(
                text="Alpha one. Beta two is longer. Gamma three. Delta four.",
                source=SourceRef(page=3, chapter=None, item_id="page-3", char_start=10, char_end=63),
            )
        ]
    )

    chunks = build_chunks(document, max_chars=40, overlap_chars=12)

    assert [chunk.text for chunk in chunks] == [
        "Alpha one. Beta two is longer.",
        "Beta two is longer. Gamma three.",
        "Gamma three. Delta four.",
    ]
    assert chunks[0].source.char_start == 10
    assert chunks[1].source.char_start == 21
    assert chunks[2].source.char_start == 41


def test_chunk_edges_follow_sentence_boundaries() -> None:
    document = _doc_with_blocks(
        [
            DocumentBlock(
                text="First full sentence. Second complete sentence. Third ending sentence.",
                source=SourceRef(page=5, chapter="C", item_id="id-5", char_start=100, char_end=170),
            )
        ]
    )

    chunks = build_chunks(document, max_chars=45, overlap_chars=15)

    assert chunks
    assert all(chunk.text.endswith(".") for chunk in chunks)
    assert all(not chunk.text.startswith("ull") for chunk in chunks)
    assert all(chunk.source.char_start >= 100 for chunk in chunks)
    assert all(chunk.source.char_end is not None and chunk.source.char_end <= 170 for chunk in chunks)
