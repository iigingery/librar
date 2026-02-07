from __future__ import annotations

from pathlib import Path

from librar.ingestion.adapters.fb2_adapter import FB2Adapter
from librar.ingestion.adapters.txt_adapter import TXTAdapter
from librar.ingestion.ingestor import DocumentIngestor


def _write_fb2(path: Path, *, title: str, author: str, body_text: str) -> None:
    path.write_text(
        f"""<?xml version=\"1.0\" encoding=\"utf-8\"?>
<FictionBook>
  <description>
    <title-info>
      <book-title>{title}</book-title>
      <author><first-name>{author}</first-name></author>
      <lang>ru</lang>
    </title-info>
  </description>
  <body>
    <section><p>{body_text}</p></section>
  </body>
</FictionBook>
""",
        encoding="utf-8",
    )


def _configured_ingestor() -> DocumentIngestor:
    ingestor = DocumentIngestor(chunk_size=80, chunk_overlap=20)
    ingestor.register_adapter("txt", TXTAdapter())
    ingestor.register_adapter("fb2", FB2Adapter())
    return ingestor


def test_dedupe_flags_binary_match_for_repeated_file(tmp_path: Path) -> None:
    source = tmp_path / "book.txt"
    source.write_text("Title: Alpha\n\nShared content appears here.", encoding="utf-8")

    ingestor = _configured_ingestor()
    first = ingestor.ingest(source)
    second = ingestor.ingest(source)

    assert first.dedupe.is_duplicate is False
    assert first.dedupe.reason is None
    assert second.dedupe.is_duplicate is True
    assert second.dedupe.reason == "binary-match"


def test_dedupe_flags_normalized_content_match_across_formats(tmp_path: Path) -> None:
    txt_source = tmp_path / "text-book.txt"
    txt_source.write_text("Title: Text\n\nShared duplicate body for checking.", encoding="utf-8")

    fb2_source = tmp_path / "book.fb2"
    _write_fb2(
        fb2_source,
        title="FB2",
        author="Автор",
        body_text="Shared duplicate body for checking.",
    )

    ingestor = _configured_ingestor()
    first = ingestor.ingest(txt_source)
    second = ingestor.ingest(fb2_source)

    assert first.dedupe.is_duplicate is False
    assert second.dedupe.is_duplicate is True
    assert second.dedupe.reason == "normalized-content-match"


def test_dedupe_does_not_collide_for_distinct_books(tmp_path: Path) -> None:
    first_book = tmp_path / "first.txt"
    second_book = tmp_path / "second.txt"
    first_book.write_text("Title: First\n\nUnique first story.", encoding="utf-8")
    second_book.write_text("Title: Second\n\nCompletely different second story.", encoding="utf-8")

    ingestor = _configured_ingestor()
    first = ingestor.ingest(first_book)
    second = ingestor.ingest(second_book)

    assert first.dedupe.is_duplicate is False
    assert second.dedupe.is_duplicate is False
    assert second.document.metadata.title == "Second"
