from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from librar.ingestion.adapters.base import IngestionAdapter
from librar.ingestion.ingestor import DocumentIngestor, IngestionError
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


def test_ingestor_registers_adapters_and_returns_canonical_type() -> None:
    ingestor = DocumentIngestor()
    adapter = _StubAdapter()
    ingestor.register_adapter("txt", adapter)

    with TemporaryDirectory() as tmp:
        sample = Path(tmp) / "note.txt"
        sample.write_text("hello", encoding="utf-8")

        result = ingestor.ingest(sample)

    assert "txt" in ingestor.adapter_map
    assert isinstance(result.document, ExtractedDocument)
    assert result.document.metadata.format == "txt"
    assert result.chunks
    assert result.dedupe.is_duplicate is False


def test_ingestor_error_includes_source_path_context() -> None:
    ingestor = DocumentIngestor()

    with TemporaryDirectory() as tmp:
        sample = Path(tmp) / "note.unknown"
        sample.write_text("content", encoding="utf-8")

        try:
            ingestor.ingest(sample)
            raised = None
        except IngestionError as err:
            raised = err

    assert raised is not None
    assert str(sample) in str(raised)
