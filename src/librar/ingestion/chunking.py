"""Chunk builder for extracted documents with locator propagation."""

from __future__ import annotations

from dataclasses import dataclass

from razdel import sentenize

from librar.ingestion.models import DocumentBlock, ExtractedDocument, SourceRef


@dataclass(slots=True)
class TextChunk:
    """Normalized chunk ready for indexing with citation locator context."""

    text: str
    source: SourceRef


@dataclass(slots=True)
class _SentenceUnit:
    text: str
    start: int
    end: int


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


def _clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(value, upper))


def _split_sentences(text: str) -> list[_SentenceUnit]:
    sentences: list[_SentenceUnit] = []

    for match in sentenize(text):
        raw = text[match.start : match.stop]
        stripped = raw.strip()
        if not stripped:
            continue

        left_trim = len(raw) - len(raw.lstrip())
        right_trim = len(raw) - len(raw.rstrip())
        start = match.start + left_trim
        end = match.stop - right_trim
        sentences.append(_SentenceUnit(text=stripped, start=start, end=end))

    if sentences:
        return sentences

    fallback = text.strip()
    if not fallback:
        return []

    start = text.find(fallback)
    return [_SentenceUnit(text=fallback, start=start, end=start + len(fallback))]


def _build_chunk_windows(sentences: list[_SentenceUnit], max_chars: int, overlap_chars: int) -> list[list[_SentenceUnit]]:
    windows: list[list[_SentenceUnit]] = []
    index = 0

    while index < len(sentences):
        current: list[_SentenceUnit] = []
        current_len = 0
        cursor = index

        while cursor < len(sentences):
            sentence = sentences[cursor]
            addition = len(sentence.text) if not current else len(sentence.text) + 1

            if current and current_len + addition > max_chars:
                break

            current.append(sentence)
            current_len += addition
            cursor += 1

            if len(current) == 1 and len(sentence.text) > max_chars:
                break

        if not current:
            break

        windows.append(current)
        if cursor >= len(sentences):
            break

        overlap_len = 0
        next_index = cursor

        for overlap_index in range(cursor - 1, index, -1):
            overlap_sentence = sentences[overlap_index]
            addition = len(overlap_sentence.text) if overlap_len == 0 else len(overlap_sentence.text) + 1

            if overlap_len and overlap_len + addition > overlap_chars:
                break

            overlap_len += addition
            next_index = overlap_index

            if overlap_len >= overlap_chars:
                break

        index = next_index

    return windows


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

    for domain_blocks in _iter_domains(document.blocks):
        domain_text = " ".join(block.text for block in domain_blocks if block.text)
        if not domain_text:
            continue

        first_source = domain_blocks[0].source
        domain_start = first_source.char_start if first_source.char_start is not None else 0
        domain_end_candidates = [
            block.source.char_end
            for block in domain_blocks
            if block.source.char_end is not None
        ]
        domain_end = max(domain_end_candidates) if domain_end_candidates else domain_start + len(domain_text)
        domain_end = max(domain_end, domain_start)

        sentences = _split_sentences(domain_text)
        windows = _build_chunk_windows(sentences, max_chars=max_chars, overlap_chars=overlap_chars)

        for window in windows:
            chunk_text = " ".join(sentence.text for sentence in window)
            if not chunk_text:
                continue

            chunk_start = _clamp(domain_start + window[0].start, domain_start, domain_end)
            chunk_end = _clamp(domain_start + window[-1].end, chunk_start, domain_end)

            chunks.append(
                TextChunk(
                    text=chunk_text,
                    source=SourceRef(
                        page=first_source.page,
                        chapter=first_source.chapter,
                        item_id=first_source.item_id,
                        char_start=chunk_start,
                        char_end=chunk_end,
                    ),
                )
            )

    return chunks
