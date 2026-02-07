from __future__ import annotations

from pathlib import Path

from librar.ingestion.adapters.base import IngestionAdapter
from librar.ingestion.models import DocumentBlock, ExtractedDocument, ExtractedMetadata, SourceRef
from librar.ingestion.normalization import normalize_text, normalize_whitespace


class _StubAdapter:
    def supports(self, path: Path, sniffed_bytes: bytes | None = None) -> bool:
        return path.suffix == ".txt"

    def extract(self, path: Path) -> ExtractedDocument:
        return ExtractedDocument(
            source_path=str(path),
            metadata=ExtractedMetadata(title="t", author="a", format="txt"),
            blocks=[
                DocumentBlock(
                    text="Hello",
                    source=SourceRef(page=1, chapter="Intro", item_id="ch1", char_start=0, char_end=5),
                )
            ],
        )


def test_source_ref_covers_locator_fields() -> None:
    ref = SourceRef(page=12, chapter="One", item_id="item-1", char_start=10, char_end=20)

    assert ref.page == 12
    assert ref.chapter == "One"
    assert ref.item_id == "item-1"
    assert ref.char_start == 10
    assert ref.char_end == 20


def test_document_schema_uses_canonical_models() -> None:
    document = ExtractedDocument(
        source_path="books/sample.epub",
        metadata=ExtractedMetadata(title="Sample", author="Author", format="epub"),
        blocks=[DocumentBlock(text="Body", source=SourceRef(page=3))],
    )

    assert document.source_path == "books/sample.epub"
    assert document.metadata.title == "Sample"
    assert isinstance(document.blocks[0].source, SourceRef)


def test_adapter_contract_matches_protocol() -> None:
    adapter = _StubAdapter()

    assert isinstance(adapter, IngestionAdapter)
    assert adapter.supports(Path("note.txt"))
    assert adapter.extract(Path("note.txt")).metadata.format == "txt"


def test_normalization_helpers_are_stable() -> None:
    assert normalize_whitespace("  one\n\t two   ") == "one two"
    assert normalize_text("  Те\u0301КСТ\n ") == "те\u0301кст"
