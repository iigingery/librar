from __future__ import annotations

from pathlib import Path

import pymupdf

from librar.ingestion.adapters.pdf_adapter import PDFAdapter


def _build_pdf(path: Path, *, title: str | None, author: str | None) -> None:
    doc = pymupdf.open()
    page_one = doc.new_page()
    page_one.insert_text((72, 72), "First paragraph on page one.")
    page_one.insert_text((72, 120), "Second paragraph on page one.")

    page_two = doc.new_page()
    page_two.insert_text((72, 72), "Opening paragraph on page two.")

    metadata = {}
    if title:
        metadata["title"] = title
    if author:
        metadata["author"] = author
    if metadata:
        doc.set_metadata(metadata)

    doc.save(str(path))
    doc.close()


def test_pdf_adapter_extracts_ordered_page_blocks_and_metadata(tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    _build_pdf(pdf_path, title="Collected Works", author="Jane Doe")

    adapter = PDFAdapter()
    document = adapter.extract(pdf_path)

    assert adapter.supports(pdf_path, b"%PDF-1.7")
    assert document.metadata.title == "Collected Works"
    assert document.metadata.author == "Jane Doe"
    assert document.metadata.format == "pdf"
    assert document.blocks

    pages = [block.source.page for block in document.blocks]
    assert all(page is not None and page > 0 for page in pages)
    assert pages == sorted(pages)

    for block in document.blocks:
        assert block.text
        assert block.source.char_start is not None
        assert block.source.char_end is not None
        assert block.source.char_start < block.source.char_end


def test_pdf_adapter_falls_back_to_filename_for_missing_title(tmp_path: Path) -> None:
    pdf_path = tmp_path / "my-awesome_book.pdf"
    _build_pdf(pdf_path, title=None, author=None)

    document = PDFAdapter().extract(pdf_path)

    assert document.metadata.title == "My Awesome Book"
    assert document.metadata.author is None
