"""Batch and incremental indexing orchestrator over ingestion output."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from pathlib import Path
import time

from librar.ingestion.adapters import build_default_adapters
from librar.ingestion.ingestor import DocumentIngestor, IngestionError
from librar.search.normalize import normalize_text
from librar.search.repository import ChunkRow, SearchRepository

_SUPPORTED_SUFFIXES = {".pdf", ".epub", ".fb2", ".fbz", ".txt"}


@dataclass(slots=True)
class IndexRunStats:
    scanned: int = 0
    indexed: int = 0
    skipped_unchanged: int = 0
    errors: int = 0
    duration_ms: int = 0
    error_details: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, int | list[dict[str, str]]]:
        return {
            "scanned": self.scanned,
            "indexed": self.indexed,
            "skipped_unchanged": self.skipped_unchanged,
            "errors": self.errors,
            "duration_ms": self.duration_ms,
            "error_details": self.error_details,
        }


def _is_supported(path: Path) -> bool:
    suffixes = [part.lower() for part in path.suffixes]
    if not suffixes:
        return False
    if suffixes[-1] in _SUPPORTED_SUFFIXES:
        return True
    return suffixes[-2:] == [".fb2", ".zip"]


def _collect_inputs(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    if target.is_dir():
        return sorted(path for path in target.rglob("*") if path.is_file() and _is_supported(path))
    return []


def _fingerprint(raw_bytes: bytes) -> str:
    return hashlib.sha256(raw_bytes).hexdigest()


class SearchIndexer:
    """Indexes source books into SQLite chunks + FTS with incremental updates."""

    def __init__(self, repository: SearchRepository, ingestor: DocumentIngestor) -> None:
        self._repository = repository
        self._ingestor = ingestor

    @classmethod
    def from_db_path(cls, db_path: str | Path) -> "SearchIndexer":
        repository = SearchRepository(db_path)
        ingestor = DocumentIngestor()
        for name, adapter in build_default_adapters().items():
            ingestor.register_adapter(name, adapter)
        return cls(repository=repository, ingestor=ingestor)

    def close(self) -> None:
        self._repository.close()

    def __enter__(self) -> "SearchIndexer":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def index_books(self, books_path: str | Path) -> IndexRunStats:
        started = time.perf_counter()
        stats = IndexRunStats()
        files = _collect_inputs(Path(books_path))
        stats.scanned = len(files)

        for file_path in files:
            source_path = str(file_path)
            try:
                raw_bytes = file_path.read_bytes()
                fingerprint = _fingerprint(raw_bytes)
                mtime_ns = file_path.stat().st_mtime_ns
                state = self._repository.get_index_state(source_path)
                if state is not None and state.fingerprint == fingerprint:
                    stats.skipped_unchanged += 1
                    continue

                ingested = self._ingestor.ingest(file_path)
                chunk_rows = [
                    ChunkRow(
                        chunk_no=chunk_no,
                        raw_text=chunk.text,
                        lemma_text=normalize_text(chunk.text),
                        page=chunk.source.page,
                        chapter=chunk.source.chapter,
                        item_id=chunk.source.item_id,
                        char_start=chunk.source.char_start,
                        char_end=chunk.source.char_end,
                    )
                    for chunk_no, chunk in enumerate(ingested.chunks)
                ]

                self._repository.replace_book_chunks(
                    source_path=source_path,
                    title=ingested.document.metadata.title,
                    author=ingested.document.metadata.author,
                    format_name=ingested.document.metadata.format,
                    fingerprint=fingerprint,
                    mtime_ns=mtime_ns,
                    chunks=chunk_rows,
                )
                stats.indexed += 1
            except (IngestionError, OSError) as exc:
                stats.errors += 1
                stats.error_details.append({"source_path": source_path, "error": str(exc)})

        stats.duration_ms = int((time.perf_counter() - started) * 1000)
        return stats
