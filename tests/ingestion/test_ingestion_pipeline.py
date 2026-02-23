from __future__ import annotations

import json
from pathlib import Path
import shutil

import pymupdf
from ebooklib import epub

from librar.cli.ingest_books import main as ingest_cli_main
from librar.ingestion.adapters import build_default_adapters
from librar.ingestion.ingestor import DocumentIngestor


def _build_pdf(path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "PDF pipeline content sample.")
    doc.save(str(path))
    doc.close()


def _build_epub(path: Path) -> None:
    book = epub.EpubBook()
    book.set_identifier("pipeline-epub")
    book.set_title("Pipeline EPUB")
    book.set_language("ru")
    chapter = epub.EpubHtml(title="Chapter 1", file_name="c1.xhtml", lang="ru")
    chapter.content = (
        "<html><body>"
        "<p>EPUB pipeline content sample.</p>"
        "<p>Another sentence for readability.</p>"
        "<p>Second paragraph keeps sentence boundaries clear for overlap behavior.</p>"
        "<p>Third paragraph finishes the chapter for deterministic chunking tests.</p>"
        "</body></html>"
    )
    book.add_item(chapter)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", chapter]
    book.toc = (chapter,)
    epub.write_epub(str(path), book)


def _build_txt(path: Path) -> None:
    path.write_text("Title: Pipeline TXT\nAuthor: Test\n\nTXT pipeline content sample.", encoding="utf-8")


def _seed_fb2_from_books(path: Path) -> None:
    fixtures = sorted(Path("books").glob("*.fb2"))
    if not fixtures:
        raise AssertionError("Expected FB2 fixtures in books/")
    shutil.copyfile(fixtures[0], path)


def _configured_ingestor() -> DocumentIngestor:
    ingestor = DocumentIngestor(chunk_size=120, chunk_overlap=20)
    for name, adapter in build_default_adapters().items():
        ingestor.register_adapter(name, adapter)
    return ingestor


def test_default_registry_contains_all_four_adapters() -> None:
    adapters = build_default_adapters()

    assert set(adapters) == {"pdf", "epub", "fb2", "txt"}


def test_ingestion_pipeline_handles_pdf_epub_fb2_txt(tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    epub_path = tmp_path / "sample.epub"
    txt_path = tmp_path / "sample.txt"
    fb2_path = tmp_path / "sample.fb2"

    _build_pdf(pdf_path)
    _build_epub(epub_path)
    _build_txt(txt_path)
    _seed_fb2_from_books(fb2_path)

    ingestor = _configured_ingestor()
    results = [
        ingestor.ingest(pdf_path),
        ingestor.ingest(epub_path),
        ingestor.ingest(fb2_path),
        ingestor.ingest(txt_path),
    ]

    formats = {result.document.metadata.format for result in results}
    assert formats == {"pdf", "epub", "fb2", "txt"}
    assert all(result.chunks for result in results)
    assert all(result.document.metadata.title for result in results)


def test_cli_reports_duplicate_on_repeated_run(tmp_path: Path, capsys: object) -> None:
    source = tmp_path / "book.txt"
    source.write_text("Title: Repeat\n\nCLI duplicate test body.", encoding="utf-8")
    cache = tmp_path / "ingest-cache.json"

    exit_code_first = ingest_cli_main(["--path", str(source), "--cache-file", str(cache)])
    output_first = capsys.readouterr().out
    payload_first = json.loads(output_first)

    exit_code_second = ingest_cli_main(["--path", str(source), "--cache-file", str(cache)])
    output_second = capsys.readouterr().out
    payload_second = json.loads(output_second)

    assert exit_code_first == 0
    assert exit_code_second == 0
    assert payload_first["results"][0]["is_duplicate"] is False
    assert payload_second["results"][0]["is_duplicate"] is True
    assert payload_second["results"][0]["duplicate_reason"] in {"binary-match", "normalized-content-match"}


def test_cli_ignores_invalid_cache_and_continues_ingestion(tmp_path: Path, capsys: object, caplog: object) -> None:
    source = tmp_path / "book.txt"
    source.write_text("Title: Corrupted cache\n\nCLI should continue.", encoding="utf-8")
    cache = tmp_path / "ingest-cache.json"
    cache.write_text("{invalid-json", encoding="utf-8")

    exit_code = ingest_cli_main(["--path", str(source), "--cache-file", str(cache)])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["processed"] == 1
    assert payload["results"][0]["is_duplicate"] is False
    assert "Failed to load ingestion cache" in caplog.text


def test_ingestor_outputs_sentence_safe_chunks_for_multi_block_epub(tmp_path: Path) -> None:
    epub_path = tmp_path / "sentence-safe.epub"
    _build_epub(epub_path)

    ingestor = _configured_ingestor()
    result = ingestor.ingest(epub_path)
    content_chunks = [chunk for chunk in result.chunks if chunk.text != "Pipeline EPUB Chapter 1"]

    assert len(result.document.blocks) >= 4
    assert len(result.chunks) >= 3
    assert all(chunk.text[0].isupper() for chunk in content_chunks)
    assert all(chunk.text.endswith(".") for chunk in content_chunks)
    assert "Another sentence for readability." in content_chunks[0].text
    assert "Another sentence for readability." in content_chunks[1].text
