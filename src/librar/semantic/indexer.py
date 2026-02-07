"""Incremental semantic indexing over existing chunk corpus."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from pathlib import Path
import time
from typing import Protocol, Sequence

import numpy as np

from librar.search.repository import SearchRepository
from librar.semantic.config import SemanticSettings
from librar.semantic.openrouter import OpenRouterEmbedder
from librar.semantic.semantic_repository import SemanticRepository
from librar.semantic.vector_store import FaissVectorStore


class _BatchEmbedder(Protocol):
    model: str

    def embed_texts(self, texts: Sequence[str], *, stage: str = "chunks") -> np.ndarray:
        ...


@dataclass(slots=True)
class SemanticIndexStats:
    scanned_chunks: int = 0
    embedded_chunks: int = 0
    skipped_unchanged: int = 0
    errors: int = 0
    duration_ms: int = 0
    model: str = ""
    error_details: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, int | str | list[dict[str, str]]]:
        return {
            "scanned_chunks": self.scanned_chunks,
            "embedded_chunks": self.embedded_chunks,
            "skipped_unchanged": self.skipped_unchanged,
            "errors": self.errors,
            "duration_ms": self.duration_ms,
            "model": self.model,
            "error_details": self.error_details,
        }


@dataclass(slots=True)
class _PendingChunk:
    chunk_id: int
    raw_text: str
    fingerprint: str


def _semantic_fingerprint(text: str, model: str) -> str:
    payload = f"{model}\n{text}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class SemanticIndexer:
    """Builds and updates semantic vectors for existing chunks."""

    def __init__(
        self,
        *,
        search_repository: SearchRepository,
        semantic_repository: SemanticRepository,
        embedder: _BatchEmbedder,
        index_path: str | Path,
        batch_size: int = 32,
        metric: str = "ip",
        vector_store: FaissVectorStore | None = None,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")

        self._search_repository = search_repository
        self._semantic_repository = semantic_repository
        self._embedder = embedder
        self._index_path = Path(index_path)
        self._batch_size = batch_size
        self._metric = metric
        self._vector_store = vector_store

    @classmethod
    def from_db_path(
        cls,
        *,
        db_path: str | Path,
        index_path: str | Path,
        settings: SemanticSettings | None = None,
        batch_size: int = 32,
    ) -> "SemanticIndexer":
        search_repository = SearchRepository(db_path)
        semantic_repository = SemanticRepository(search_repository.connection)

        resolved_settings = settings or SemanticSettings.from_env()
        embedder = OpenRouterEmbedder(resolved_settings)

        vector_store: FaissVectorStore | None = None
        index_state = semantic_repository.get_index_state()
        if index_state is not None and index_state.model == resolved_settings.model:
            vector_store = FaissVectorStore(index_path, dimension=index_state.dimension, metric=index_state.metric)

        return cls(
            search_repository=search_repository,
            semantic_repository=semantic_repository,
            embedder=embedder,
            index_path=index_path,
            batch_size=batch_size,
            metric=index_state.metric if index_state is not None else "ip",
            vector_store=vector_store,
        )

    def close(self) -> None:
        self._search_repository.close()

    def __enter__(self) -> "SemanticIndexer":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def index_chunks(self) -> SemanticIndexStats:
        started = time.perf_counter()
        stats = SemanticIndexStats(model=self._embedder.model)

        chunks = self._search_repository.iter_chunks()
        stats.scanned_chunks = len(chunks)

        pending: list[_PendingChunk] = []
        for chunk in chunks:
            fingerprint = _semantic_fingerprint(chunk.raw_text, self._embedder.model)
            current_state = self._semantic_repository.get_chunk_state(
                chunk_id=chunk.chunk_id,
                model=self._embedder.model,
            )
            if current_state is not None and current_state.fingerprint == fingerprint:
                stats.skipped_unchanged += 1
                continue
            pending.append(_PendingChunk(chunk_id=chunk.chunk_id, raw_text=chunk.raw_text, fingerprint=fingerprint))

        for start in range(0, len(pending), self._batch_size):
            batch = pending[start : start + self._batch_size]
            texts = [item.raw_text for item in batch]

            try:
                vectors = self._embedder.embed_texts(texts, stage="chunks")
            except Exception as exc:
                stats.errors += len(batch)
                stats.error_details.append(
                    {
                        "stage": "embed_texts",
                        "chunk_ids": ",".join(str(item.chunk_id) for item in batch),
                        "error": str(exc),
                    }
                )
                continue

            if vectors.shape[0] != len(batch):
                stats.errors += len(batch)
                stats.error_details.append(
                    {
                        "stage": "embed_texts",
                        "chunk_ids": ",".join(str(item.chunk_id) for item in batch),
                        "error": f"Embedding count mismatch: expected {len(batch)}, got {vectors.shape[0]}",
                    }
                )
                continue

            store = self._ensure_vector_store(dimension=vectors.shape[1])
            vector_ids = [item.chunk_id for item in batch]
            store.add_or_replace(vector_ids=vector_ids, vectors=vectors)

            for item in batch:
                self._semantic_repository.upsert_chunk_state(
                    chunk_id=item.chunk_id,
                    vector_id=item.chunk_id,
                    model=self._embedder.model,
                    fingerprint=item.fingerprint,
                )

            stats.embedded_chunks += len(batch)

        if self._vector_store is not None:
            self._vector_store.save()
            self._semantic_repository.upsert_index_state(
                model=self._embedder.model,
                dimension=self._vector_store.dimension,
                metric=self._vector_store.metric,
                index_path=str(self._index_path),
            )

        stats.duration_ms = int((time.perf_counter() - started) * 1000)
        return stats

    def _ensure_vector_store(self, *, dimension: int) -> FaissVectorStore:
        if self._vector_store is None:
            self._vector_store = FaissVectorStore(
                self._index_path,
                dimension=dimension,
                metric=self._metric,
            )
            return self._vector_store

        if self._vector_store.dimension != dimension:
            raise ValueError(
                f"Embedding dimension mismatch for vector store: expected {self._vector_store.dimension}, got {dimension}"
            )
        return self._vector_store
