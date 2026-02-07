"""Shared adapter contract for per-format ingestion parsers."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from librar.ingestion.models import ExtractedDocument


@runtime_checkable
class IngestionAdapter(Protocol):
    """Protocol that every format adapter must implement."""

    def supports(self, path: Path, sniffed_bytes: bytes | None = None) -> bool:
        """Return True when this adapter can parse the given file."""

    def extract(self, path: Path) -> ExtractedDocument:
        """Extract and normalize a document into the canonical schema."""
