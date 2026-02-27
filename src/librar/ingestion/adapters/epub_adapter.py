"""EPUB adapter preserving reading-order chapter/item boundaries."""

from __future__ import annotations

from pathlib import Path
import re

import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup

from librar.ingestion.models import DocumentBlock, ExtractedDocument, ExtractedMetadata, SourceRef
from librar.ingestion.normalization import normalize_whitespace

_TITLE_SPLIT_RE = re.compile(r"[._\-]+")

# Map common DC language tag values to ISO 639-1 codes
_EPUB_LANG_MAP: dict[str, str] = {
    "ru": "ru", "rus": "ru", "russian": "ru",
    "kk": "kk", "kaz": "kk", "kazakh": "kk",
    "tt": "tt", "tat": "tt", "tatar": "tt",
    "en": "en", "eng": "en", "english": "en",
}


def _normalize_epub_language(raw: str | None) -> str | None:
    """Map a raw DC language tag to an ISO 639-1 code, or return None."""
    if not raw:
        return None
    return _EPUB_LANG_MAP.get(raw.strip().lower())


def _normalize_title_from_path(path: Path) -> str:
    stem = _TITLE_SPLIT_RE.sub(" ", path.stem)
    return normalize_whitespace(stem).title()


def _first_non_empty(values: list[tuple[str, dict[str, str]]] | None) -> str | None:
    if not values:
        return None
    for value, _attrs in values:
        cleaned = normalize_whitespace(value)
        if cleaned:
            return cleaned
    return None


def _item_blocks(xhtml: bytes) -> list[str]:
    soup = BeautifulSoup(xhtml, "xml")
    body = soup.body or soup

    parts: list[str] = []
    for node in body.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote"]):
        text = normalize_whitespace(node.get_text(" ", strip=True))
        if text:
            parts.append(text)

    if parts:
        return parts

    fallback = normalize_whitespace(body.get_text(" ", strip=True))
    return [fallback] if fallback else []


def _chapter_label(item: epub.EpubHtml, extracted_parts: list[str]) -> str:
    if item.title:
        title = normalize_whitespace(item.title)
        if title:
            return title
    if extracted_parts:
        return extracted_parts[0]
    return item.get_id()


class EPUBAdapter:
    """Extract text from EPUB document items in spine order."""

    def supports(self, path: Path, sniffed_bytes: bytes | None = None) -> bool:
        if path.suffix.lower() == ".epub":
            return True
        if sniffed_bytes is None:
            return False
        return sniffed_bytes.startswith(b"PK\x03\x04")

    def extract(self, path: Path) -> ExtractedDocument:
        from librar.ingestion.language_detection import detect_language

        book = epub.read_epub(str(path))
        metadata = self._extract_metadata(path, book)
        blocks = self._extract_blocks(book)

        # If DC metadata didn't yield a recognized ISO language, detect from text
        if not metadata.language:
            sample_text = " ".join(b.text for b in blocks[:30])
            detected = detect_language(sample_text)
            metadata = ExtractedMetadata(
                title=metadata.title,
                author=metadata.author,
                language=detected,
                format_name=metadata.format_name,
            )

        return ExtractedDocument(source_path=str(path), metadata=metadata, blocks=blocks)

    def _extract_metadata(self, path: Path, book: epub.EpubBook) -> ExtractedMetadata:
        title = _first_non_empty(book.get_metadata("DC", "title")) or _normalize_title_from_path(path)
        author = _first_non_empty(book.get_metadata("DC", "creator"))
        raw_language = _first_non_empty(book.get_metadata("DC", "language"))
        language = _normalize_epub_language(raw_language)
        return ExtractedMetadata(title=title, author=author, language=language, format_name="epub")

    def _extract_blocks(self, book: epub.EpubBook) -> list[DocumentBlock]:
        extracted_blocks: list[DocumentBlock] = []

        for spine_entry in book.spine:
            item_id = spine_entry[0] if isinstance(spine_entry, tuple) else spine_entry
            item = book.get_item_with_id(item_id)
            if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
                continue

            text_parts = _item_blocks(item.get_content())
            if not text_parts:
                continue

            chapter = _chapter_label(item, text_parts)
            item_char_offset = 0

            for part in text_parts:
                start = item_char_offset
                end = start + len(part)
                item_char_offset = end + 1

                extracted_blocks.append(
                    DocumentBlock(
                        text=part,
                        source=SourceRef(
                            chapter=chapter,
                            item_id=item.get_id(),
                            char_start=start,
                            char_end=end,
                        ),
                    )
                )

        return extracted_blocks
