"""Canonical data structures shared by all ingestion adapters."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ExtractedMetadata:
    """Normalized metadata extracted from a source document."""

    title: str | None = None
    author: str | None = None
    language: str | None = None
    format: str | None = None


@dataclass(slots=True)
class SourceRef:
    """Locator information for mapping extracted text back to source."""

    page: int | None = None
    chapter: str | None = None
    item_id: str | None = None
    char_start: int | None = None
    char_end: int | None = None


@dataclass(slots=True)
class DocumentBlock:
    """A normalized text unit emitted by a parser adapter."""

    text: str
    source: SourceRef


@dataclass(slots=True)
class ExtractedDocument:
    """Canonical extraction output consumed by chunking and indexing."""

    source_path: str
    metadata: ExtractedMetadata = field(default_factory=ExtractedMetadata)
    blocks: list[DocumentBlock] = field(default_factory=list)
