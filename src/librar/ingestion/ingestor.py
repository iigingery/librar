"""Routing entrypoint for ingestion adapters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from librar.ingestion.adapters.base import IngestionAdapter
from librar.ingestion.chunking import TextChunk, build_chunks
from librar.ingestion.dedupe import DedupeDecision, FingerprintRegistry, fingerprint_document
from librar.ingestion.models import ExtractedDocument


@dataclass(slots=True)
class IngestionError(Exception):
    """Domain error for adapter routing and extraction failures."""

    path: Path
    message: str

    def __str__(self) -> str:
        return f"{self.message} (path={self.path})"


@dataclass(slots=True)
class IngestionResult:
    """Integrated ingestion output for downstream indexing decisions."""

    document: ExtractedDocument
    chunks: list[TextChunk]
    dedupe: DedupeDecision


class DocumentIngestor:
    """Resolve the right adapter and return canonical extraction output."""

    def __init__(
        self,
        sniff_bytes: int = 4096,
        *,
        chunk_size: int = 600,
        chunk_overlap: int = 120,
        fingerprint_registry: FingerprintRegistry | None = None,
    ) -> None:
        self._sniff_bytes = sniff_bytes
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._adapter_map: dict[str, IngestionAdapter] = {}
        self._fingerprints = fingerprint_registry or FingerprintRegistry()

    @property
    def fingerprint_registry(self) -> FingerprintRegistry:
        """Expose fingerprint state for persistence across runs."""

        return self._fingerprints

    @property
    def adapter_map(self) -> dict[str, IngestionAdapter]:
        """Registered adapters keyed by adapter name."""

        return dict(self._adapter_map)

    def register_adapter(self, name: str, adapter: IngestionAdapter) -> None:
        """Register an adapter implementation by key."""

        if not name:
            raise ValueError("Adapter name cannot be empty")
        self._adapter_map[name] = adapter

    def ingest(self, path: str | Path) -> IngestionResult:
        """Ingest a file path and return extraction + chunks + dedupe decision."""

        source = Path(path)
        raw_bytes = self._read_bytes(source)
        sniffed = raw_bytes[: self._sniff_bytes]

        for adapter in self._adapter_map.values():
            if adapter.supports(source, sniffed):
                try:
                    extracted = adapter.extract(source)
                except Exception as exc:  # pragma: no cover - wrapper branch
                    raise IngestionError(source, f"Adapter extraction failed: {exc}") from exc

                if not isinstance(extracted, ExtractedDocument):
                    raise IngestionError(source, "Adapter returned non-canonical output")
                chunks = build_chunks(extracted, max_chars=self._chunk_size, overlap_chars=self._chunk_overlap)
                fingerprint = fingerprint_document(raw_bytes, extracted)
                dedupe = self._fingerprints.evaluate(fingerprint)
                return IngestionResult(document=extracted, chunks=chunks, dedupe=dedupe)

        raise IngestionError(source, "No adapter registered for file content")

    def _read_bytes(self, path: Path) -> bytes:
        """Read complete source payload for sniffing and fingerprinting."""

        try:
            return path.read_bytes()
        except OSError as exc:
            raise IngestionError(path, f"Failed to read source file: {exc}") from exc
