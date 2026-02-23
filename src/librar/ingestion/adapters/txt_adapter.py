"""TXT adapter with encoding detection and stable offsets."""

from __future__ import annotations

from pathlib import Path

from charset_normalizer import from_bytes

from librar.ingestion.models import DocumentBlock, ExtractedDocument, ExtractedMetadata, SourceRef
from librar.ingestion.normalization import normalize_whitespace

_HEADER_FIELDS = {
    "title": "title",
    "author": "author",
    "название": "title",
    "автор": "author",
}


class TXTAdapter:
    """Extract plain-text books with robust charset handling."""

    def supports(self, path: Path, sniffed_bytes: bytes | None = None) -> bool:
        if path.suffix.lower() == ".txt":
            return True
        if sniffed_bytes is None:
            return False

        if path.suffix.lower() in {".pdf", ".epub", ".fb2", ".fbz", ".zip"}:
            return False

        prefix = sniffed_bytes.lstrip()
        if prefix.startswith((b"%PDF-", b"PK\x03\x04", b"<?xml", b"<FictionBook")):
            return False

        return b"\x00" not in sniffed_bytes

    def extract(self, path: Path) -> ExtractedDocument:
        raw = path.read_bytes()
        encoding = self._detect_encoding(raw)
        text = raw.decode(encoding)
        metadata = self._extract_metadata(text, path)
        blocks = self._build_blocks(text)

        return ExtractedDocument(source_path=str(path), metadata=metadata, blocks=blocks)

    def _detect_encoding(self, raw: bytes) -> str:
        best = from_bytes(raw).best()
        if best and best.encoding:
            name = best.encoding.lower()
            if name in {"windows-1251", "cp1251"}:
                return "cp1251"
            return best.encoding

        for fallback in ("utf-8", "cp1251"):
            try:
                raw.decode(fallback)
                return fallback
            except UnicodeDecodeError:
                continue
        raise ValueError("Could not detect TXT encoding")

    def _extract_metadata(self, text: str, path: Path) -> ExtractedMetadata:
        title: str | None = None
        author: str | None = None
        for line in text.splitlines()[:20]:
            normalized = normalize_whitespace(line)
            if not normalized or ":" not in normalized:
                continue
            key, value = normalized.split(":", 1)
            field = _HEADER_FIELDS.get(key.strip().casefold())
            clean_value = normalize_whitespace(value)
            if not field or not clean_value:
                continue
            if field == "title" and not title:
                title = clean_value
            if field == "author" and not author:
                author = clean_value

        return ExtractedMetadata(title=title or path.stem, author=author, format_name="txt")

    def _build_blocks(self, text: str) -> list[DocumentBlock]:
        blocks: list[DocumentBlock] = []
        offset = 0

        for line_no, raw_line in enumerate(text.splitlines(keepends=True), start=1):
            line_text = raw_line.rstrip("\r\n")
            normalized = normalize_whitespace(line_text)
            line_start = offset
            line_end = line_start + len(line_text)
            offset += len(raw_line)
            if not normalized:
                continue

            blocks.append(
                DocumentBlock(
                    text=normalized,
                    source=SourceRef(item_id=f"line-{line_no}", char_start=line_start, char_end=line_end),
                )
            )

        return blocks
