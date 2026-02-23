from __future__ import annotations

from pathlib import Path

from ebooklib import epub

from librar.ingestion.adapters.epub_adapter import EPUBAdapter


def _build_epub(path: Path, *, title: str | None, author: str | None) -> None:
    book = epub.EpubBook()
    book.set_identifier("book-id")
    if title:
        book.set_title(title)
    if author:
        book.add_author(author)
    book.set_language("ru")

    chapter_one = epub.EpubHtml(title="Chapter One", file_name="chapter_1.xhtml", lang="en")
    chapter_one.content = """
    <html><body>
      <h1>Chapter One</h1>
      <p>First paragraph.</p>
      <p>Second paragraph.</p>
    </body></html>
    """

    chapter_two = epub.EpubHtml(title="Chapter Two", file_name="chapter_2.xhtml", lang="en")
    chapter_two.content = """
    <html><body>
      <h1>Chapter Two</h1>
      <p>Only paragraph in chapter two.</p>
    </body></html>
    """

    book.add_item(chapter_one)
    book.add_item(chapter_two)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    book.toc = (chapter_one, chapter_two)
    book.spine = ["nav", chapter_one, chapter_two]
    epub.write_epub(str(path), book)


def test_epub_adapter_preserves_chapter_boundaries_and_order(tmp_path: Path) -> None:
    epub_path = tmp_path / "ordered.epub"
    _build_epub(epub_path, title="Epub Sample", author="John Smith")

    adapter = EPUBAdapter()
    document = adapter.extract(epub_path)

    assert adapter.supports(epub_path, b"PK\x03\x04")
    assert document.metadata.title == "Epub Sample"
    assert document.metadata.author == "John Smith"
    assert document.metadata.format_name == "epub"
    assert document.blocks

    chapter_sequence = [block.source.chapter for block in document.blocks]
    assert chapter_sequence.count("Chapter One") >= 2
    assert chapter_sequence.count("Chapter Two") >= 1

    item_ids = [block.source.item_id for block in document.blocks]
    first_chapter_index = chapter_sequence.index("Chapter One")
    second_chapter_index = chapter_sequence.index("Chapter Two")
    assert second_chapter_index > first_chapter_index
    assert item_ids[first_chapter_index] != item_ids[second_chapter_index]

    starts_by_item: dict[str, list[int]] = {}
    for block in document.blocks:
        assert block.source.item_id is not None
        assert block.source.char_start is not None
        assert block.source.char_end is not None
        starts_by_item.setdefault(block.source.item_id, []).append(block.source.char_start)

    for starts in starts_by_item.values():
        assert starts == sorted(starts)
        assert starts[0] == 0


def test_epub_adapter_falls_back_to_filename_for_missing_metadata(tmp_path: Path) -> None:
    epub_path = tmp_path / "mystic_collection.epub"
    _build_epub(epub_path, title=None, author=None)

    document = EPUBAdapter().extract(epub_path)

    assert document.metadata.title == "Mystic Collection"
    assert document.metadata.author is None
