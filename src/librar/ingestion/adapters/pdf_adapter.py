"""PDF adapter producing canonical extraction blocks with page locators."""

from __future__ import annotations

from pathlib import Path
import re

import pymupdf

from librar.ingestion.models import DocumentBlock, ExtractedDocument, ExtractedMetadata, SourceRef
from librar.ingestion.normalization import normalize_whitespace

_PDF_MAGIC = b"%PDF-"
_TITLE_SPLIT_RE = re.compile(r"[._\-]+")


def _normalize_title_from_path(path: Path) -> str:
    stem = _TITLE_SPLIT_RE.sub(" ", path.stem)
    return normalize_whitespace(stem).title()


def _first_non_empty(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = normalize_whitespace(value)
    return cleaned or None


class PDFAdapter:
    """Extract paragraph-like blocks from PDF pages in stable order."""

    def supports(self, path: Path, sniffed_bytes: bytes | None = None) -> bool:
        if path.suffix.lower() == ".pdf":
            return True
        if sniffed_bytes is None:
            return False
        return sniffed_bytes.startswith(_PDF_MAGIC)

    def extract(self, path: Path) -> ExtractedDocument:
        with pymupdf.open(path) as doc:
            metadata = self._extract_metadata(path, doc)
            blocks = self._extract_blocks(doc)
        return ExtractedDocument(source_path=str(path), metadata=metadata, blocks=blocks)

    def _extract_metadata(self, path: Path, doc: pymupdf.Document) -> ExtractedMetadata:
        doc_metadata = doc.metadata or {}
        title = _first_non_empty(doc_metadata.get("title")) or _normalize_title_from_path(path)
        author = _first_non_empty(doc_metadata.get("author"))
        return ExtractedMetadata(title=title, author=author, format="pdf")

    def _extract_blocks(self, doc: pymupdf.Document) -> list[DocumentBlock]:
        extracted_blocks: list[DocumentBlock] = []

        for page_index, page in enumerate(doc, start=1):
            page_blocks = page.get_text("blocks")
            ordered_blocks = sorted(page_blocks, key=lambda row: (row[1], row[0], row[5]))
            page_char_offset = 0

            for block in ordered_blocks:
                block_text = normalize_whitespace(block[4])
                if not block_text:
                    continue

                start = page_char_offset
                end = start + len(block_text)
                page_char_offset = end + 1

                extracted_blocks.append(
                    DocumentBlock(
                        text=block_text,
                        source=SourceRef(page=page_index, char_start=start, char_end=end),
                    )
                )

        return extracted_blocks
