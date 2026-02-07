"""Chunk builder for extracted documents with locator propagation."""

from __future__ import annotations

from dataclasses import dataclass

from librar.ingestion.models import DocumentBlock, ExtractedDocument, SourceRef


@dataclass(slots=True)
class TextChunk:
    """Normalized chunk ready for indexing with citation locator context."""

    text: str
    source: SourceRef


def _domain_key(block: DocumentBlock) -> tuple[int | None, str | None, str | None]:
    source = block.source
    return (source.page, source.chapter, source.item_id)


def _iter_domains(blocks: list[DocumentBlock]) -> list[list[DocumentBlock]]:
    if not blocks:
        return []

    domains: list[list[DocumentBlock]] = []
    current: list[DocumentBlock] = []
    current_key: tuple[int | None, str | None, str | None] | None = None

    for block in blocks:
        key = _domain_key(block)
        if current and key != current_key:
            domains.append(current)
            current = []
        current.append(block)
        current_key = key

    if current:
        domains.append(current)
    return domains


def build_chunks(
    document: ExtractedDocument,
    *,
    max_chars: int = 500,
    overlap_chars: int = 100,
) -> list[TextChunk]:
    """Split extracted blocks into deterministic, locator-aware chunks."""

    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if overlap_chars < 0:
        raise ValueError("overlap_chars cannot be negative")
    if overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be smaller than max_chars")

    chunks: list[TextChunk] = []
    stride = max_chars - overlap_chars

    for domain_blocks in _iter_domains(document.blocks):
        domain_text = " ".join(block.text for block in domain_blocks if block.text)
        if not domain_text:
            continue

        first_source = domain_blocks[0].source
        domain_start = first_source.char_start if first_source.char_start is not None else 0

        start = 0
        while start < len(domain_text):
            end = min(len(domain_text), start + max_chars)
            chunk_text = domain_text[start:end].strip()
            if chunk_text:
                trimmed_left = len(domain_text[start:end]) - len(domain_text[start:end].lstrip())
                trimmed_right = len(domain_text[start:end]) - len(domain_text[start:end].rstrip())
                source_start = domain_start + start + trimmed_left
                source_end = domain_start + end - trimmed_right

                chunks.append(
                    TextChunk(
                        text=chunk_text,
                        source=SourceRef(
                            page=first_source.page,
                            chapter=first_source.chapter,
                            item_id=first_source.item_id,
                            char_start=source_start,
                            char_end=source_end,
                        ),
                    )
                )

            if end == len(domain_text):
                break
            start += stride

    return chunks
