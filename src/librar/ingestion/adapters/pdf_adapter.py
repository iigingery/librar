"""PDF adapter producing canonical extraction blocks with page locators."""

from __future__ import annotations

import logging
from pathlib import Path
import re

import pymupdf

from librar.ingestion.models import DocumentBlock, ExtractedDocument, ExtractedMetadata, SourceRef
from librar.ingestion.normalization import normalize_whitespace
from librar.ingestion.ocr import OcrStatus, extract_page_text

logger = logging.getLogger(__name__)

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
        from librar.ingestion.language_detection import detect_language

        with pymupdf.open(path) as doc:
            metadata = self._extract_metadata(path, doc)
            blocks = self._extract_blocks(doc)

        # PDF metadata rarely carries a language tag; always detect from text
        sample_text = " ".join(b.text for b in blocks[:30])
        language = detect_language(sample_text)
        metadata = ExtractedMetadata(
            title=metadata.title,
            author=metadata.author,
            language=language,
            format_name=metadata.format_name,
        )

        return ExtractedDocument(source_path=str(path), metadata=metadata, blocks=blocks)

    def _extract_metadata(self, path: Path, doc: pymupdf.Document) -> ExtractedMetadata:
        doc_metadata = doc.metadata or {}
        title = _first_non_empty(doc_metadata.get("title")) or _normalize_title_from_path(path)
        author = _first_non_empty(doc_metadata.get("author"))
        return ExtractedMetadata(title=title, author=author, format_name="pdf")

    def _extract_blocks(self, doc: pymupdf.Document) -> list[DocumentBlock]:
        extracted_blocks: list[DocumentBlock] = []

        for page_index, page in enumerate(doc, start=1):
            result = extract_page_text(page, page_index)

            if result.status == OcrStatus.EMBEDDED:
                # Use original block-level extraction to preserve reading order
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
            else:
                # OCR path or embedded fallback — treat as a single page block.
                # OCR_SKIPPED means Tesseract is not installed; the single
                # process-level warning was already emitted by ocr.py.
                if result.status == OcrStatus.OCR_FAILED:
                    logger.warning(
                        "OCR failed for page %d: %s", page_index, result.reason
                    )
                page_text = normalize_whitespace(result.text)
                if page_text:
                    extracted_blocks.append(
                        DocumentBlock(
                            text=page_text,
                            source=SourceRef(
                                page=page_index,
                                char_start=0,
                                char_end=len(page_text),
                            ),
                        )
                    )

        return extracted_blocks
