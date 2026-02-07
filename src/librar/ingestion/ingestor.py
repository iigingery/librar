"""Routing entrypoint for ingestion adapters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from librar.ingestion.adapters.base import IngestionAdapter
from librar.ingestion.models import ExtractedDocument


@dataclass(slots=True)
class IngestionError(Exception):
    """Domain error for adapter routing and extraction failures."""

    path: Path
    message: str

    def __str__(self) -> str:
        return f"{self.message} (path={self.path})"


class DocumentIngestor:
    """Resolve the right adapter and return canonical extraction output."""

    def __init__(self, sniff_bytes: int = 4096) -> None:
        self._sniff_bytes = sniff_bytes
        self._adapter_map: dict[str, IngestionAdapter] = {}

    @property
    def adapter_map(self) -> dict[str, IngestionAdapter]:
        """Registered adapters keyed by adapter name."""

        return dict(self._adapter_map)

    def register_adapter(self, name: str, adapter: IngestionAdapter) -> None:
        """Register an adapter implementation by key."""

        if not name:
            raise ValueError("Adapter name cannot be empty")
        self._adapter_map[name] = adapter

    def ingest(self, path: str | Path) -> ExtractedDocument:
        """Ingest a file path using content-aware adapter dispatch."""

        source = Path(path)
        sniffed = self._sniff(source)

        for adapter in self._adapter_map.values():
            if adapter.supports(source, sniffed):
                try:
                    extracted = adapter.extract(source)
                except Exception as exc:  # pragma: no cover - wrapper branch
                    raise IngestionError(source, f"Adapter extraction failed: {exc}") from exc

                if not isinstance(extracted, ExtractedDocument):
                    raise IngestionError(source, "Adapter returned non-canonical output")
                return extracted

        raise IngestionError(source, "No adapter registered for file content")

    def _sniff(self, path: Path) -> bytes:
        """Read a leading byte window for content-aware matching."""

        try:
            with path.open("rb") as file_obj:
                return file_obj.read(self._sniff_bytes)
        except OSError as exc:
            raise IngestionError(path, f"Failed to read source file: {exc}") from exc
