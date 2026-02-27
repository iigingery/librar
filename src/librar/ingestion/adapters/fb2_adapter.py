"""FB2 adapter with raw and zipped container support."""

from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

from lxml import etree

from librar.ingestion.models import DocumentBlock, ExtractedDocument, ExtractedMetadata, SourceRef
from librar.ingestion.normalization import normalize_whitespace

_ZIP_MAGIC = b"PK\x03\x04"

# Map FB2 <lang> tag values to ISO 639-1 codes
_FB2_LANG_MAP: dict[str, str] = {
    "ru": "ru", "rus": "ru", "russian": "ru",
    "kk": "kk", "kaz": "kk", "kazakh": "kk",
    "tt": "tt", "tat": "tt", "tatar": "tt",
    "en": "en", "eng": "en", "english": "en",
}


def _normalize_fb2_language(raw: str | None) -> str | None:
    """Map a raw FB2 <lang> tag to an ISO 639-1 code, or return None."""
    if not raw:
        return None
    return _FB2_LANG_MAP.get(raw.strip().lower())


class FB2Adapter:
    """Extract text and metadata from FictionBook sources."""

    def supports(self, path: Path, sniffed_bytes: bytes | None = None) -> bool:
        suffixes = [part.lower() for part in path.suffixes]
        if suffixes and suffixes[-1] in {".fb2", ".fbz"}:
            return True
        if suffixes[-2:] == [".fb2", ".zip"]:
            return True
        if sniffed_bytes and sniffed_bytes.startswith(_ZIP_MAGIC):
            return path.suffix.lower() in {".zip", ".fbz"}
        return False

    def extract(self, path: Path) -> ExtractedDocument:
        from librar.ingestion.language_detection import detect_language

        xml_bytes = self._read_fb2_payload(path)
        parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False)
        root = etree.fromstring(xml_bytes, parser=parser)

        metadata = self._extract_metadata(root, path)
        blocks = self._extract_blocks(root)

        # If the FB2 <lang> tag didn't yield a recognized ISO language, detect from text
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

    def _read_fb2_payload(self, path: Path) -> bytes:
        raw = path.read_bytes()
        if self._is_zipped(path, raw):
            return self._extract_from_zip(raw)
        return raw

    def _is_zipped(self, path: Path, raw: bytes) -> bool:
        if raw.startswith(_ZIP_MAGIC):
            return True
        suffix = path.suffix.lower()
        return suffix in {".zip", ".fbz"}

    def _extract_from_zip(self, raw: bytes) -> bytes:
        from io import BytesIO

        with ZipFile(BytesIO(raw), "r") as archive:
            candidates = [name for name in archive.namelist() if not name.endswith("/")]
            fb2_name = next((name for name in candidates if name.lower().endswith(".fb2")), None)
            target = fb2_name or (candidates[0] if candidates else None)
            if not target:
                raise ValueError("Zipped FB2 container has no readable files")
            return archive.read(target)

    def _extract_metadata(self, root: etree._Element, path: Path) -> ExtractedMetadata:
        title = self._first_text(root.xpath("//*[local-name()='title-info']/*[local-name()='book-title']"))
        author = self._extract_author(root)
        raw_language = self._first_text(root.xpath("//*[local-name()='title-info']/*[local-name()='lang']"))
        language = _normalize_fb2_language(raw_language)

        return ExtractedMetadata(
            title=title or path.stem,
            author=author,
            language=language,
            format_name="fb2",
        )

    def _extract_author(self, root: etree._Element) -> str | None:
        authors = root.xpath("//*[local-name()='title-info']/*[local-name()='author']")
        names: list[str] = []
        for author in authors:
            first = self._first_text(author.xpath("./*[local-name()='first-name']"))
            middle = self._first_text(author.xpath("./*[local-name()='middle-name']"))
            last = self._first_text(author.xpath("./*[local-name()='last-name']"))
            full = normalize_whitespace(" ".join(part for part in [first, middle, last] if part))
            if full:
                names.append(full)
        return ", ".join(names) if names else None

    def _extract_blocks(self, root: etree._Element) -> list[DocumentBlock]:
        sections = root.xpath("//*[local-name()='body']//*[local-name()='section']")
        blocks: list[DocumentBlock] = []
        offset = 0

        if not sections:
            text = normalize_whitespace(" ".join(root.itertext()))
            if text:
                blocks.append(DocumentBlock(text=text, source=SourceRef(item_id="body-1", char_start=0, char_end=len(text))))
            return blocks

        for index, section in enumerate(sections, start=1):
            chapter = self._first_text(section.xpath("./*[local-name()='title']"))
            text = normalize_whitespace(" ".join(section.itertext()))
            if not text:
                continue

            start = offset
            end = start + len(text)
            blocks.append(
                DocumentBlock(
                    text=text,
                    source=SourceRef(chapter=chapter, item_id=f"section-{index}", char_start=start, char_end=end),
                )
            )
            offset = end

        return blocks

    def _first_text(self, nodes: list[object]) -> str | None:
        for node in nodes:
            if hasattr(node, "itertext"):
                text = normalize_whitespace(" ".join(node.itertext()))
            else:
                text = normalize_whitespace(str(node))
            if text:
                return text
        return None
