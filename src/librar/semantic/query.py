"""Semantic query execution over OpenRouter embeddings and FAISS vectors."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from librar.search.repository import SearchRepository
from librar.semantic.config import SemanticSettings
from librar.semantic.openrouter import OpenRouterEmbedder
from librar.semantic.semantic_repository import SemanticRepository
from librar.semantic.vector_store import FaissVectorStore


class _QueryEmbedder(Protocol):
    model: str

    def embed_query(self, query: str) -> np.ndarray:
        ...


class _VectorSearcher(Protocol):
    def search(self, query_vector: np.ndarray, *, top_k: int = 10):
        ...


@dataclass(slots=True)
class SemanticSearchHit:
    source_path: str
    chunk_id: int
    chunk_no: int
    page: int | None
    chapter: str | None
    item_id: str | None
    char_start: int | None
    char_end: int | None
    score: float
    excerpt: str

    def to_dict(self) -> dict[str, str | int | float | None]:
        return {
            "source_path": self.source_path,
            "chunk_id": self.chunk_id,
            "chunk_no": self.chunk_no,
            "page": self.page,
            "chapter": self.chapter,
            "item_id": self.item_id,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "score": self.score,
            "excerpt": self.excerpt,
        }


class SemanticQueryService:
    """Retrieves semantic results by embedding a query and searching vectors."""

    def __init__(
        self,
        *,
        search_repository: SearchRepository,
        semantic_repository: SemanticRepository,
        vector_store: _VectorSearcher,
        embedder: _QueryEmbedder,
    ) -> None:
        self._search_repository = search_repository
        self._semantic_repository = semantic_repository
        self._vector_store = vector_store
        self._embedder = embedder

    @classmethod
    def from_db_path(
        cls,
        *,
        db_path: str | Path,
        index_path: str | Path,
        settings: SemanticSettings | None = None,
    ) -> "SemanticQueryService":
        search_repository = SearchRepository(db_path)
        semantic_repository = SemanticRepository(search_repository.connection)

        resolved_settings = settings or SemanticSettings.from_env()
        index_state = semantic_repository.get_index_state()
        if index_state is None:
            search_repository.close()
            raise RuntimeError("Semantic index is not initialized. Run `python -m librar.cli.index_semantic` first.")

        vector_store = FaissVectorStore(index_path, dimension=index_state.dimension, metric=index_state.metric)
        embedder = OpenRouterEmbedder(resolved_settings)
        return cls(
            search_repository=search_repository,
            semantic_repository=semantic_repository,
            vector_store=vector_store,
            embedder=embedder,
        )

    def close(self) -> None:
        self._search_repository.close()

    def __enter__(self) -> "SemanticQueryService":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def search(self, *, query: str, limit: int = 10) -> list[SemanticSearchHit]:
        query_text = query.strip()
        if not query_text:
            return []
        if limit <= 0:
            raise ValueError("limit must be positive")

        index_state = self._semantic_repository.get_index_state()
        if index_state is None:
            raise RuntimeError("Semantic index is not initialized. Run semantic indexing first.")

        query_vector = self._embedder.embed_query(query_text)
        vector_hits = self._vector_store.search(query_vector, top_k=limit)
        if not vector_hits:
            return []

        chunk_ids = [int(hit.vector_id) for hit in vector_hits]
        chunks = self._search_repository.fetch_chunks_by_ids(chunk_ids)
        by_id = {chunk.chunk_id: chunk for chunk in chunks}

        results: list[SemanticSearchHit] = []
        for hit in vector_hits:
            chunk = by_id.get(int(hit.vector_id))
            if chunk is None:
                continue

            excerpt = chunk.raw_text.strip()
            if len(excerpt) > 300:
                excerpt = excerpt[:297].rstrip() + "..."

            results.append(
                SemanticSearchHit(
                    source_path=chunk.source_path,
                    chunk_id=chunk.chunk_id,
                    chunk_no=chunk.chunk_no,
                    page=chunk.page,
                    chapter=chunk.chapter,
                    item_id=chunk.item_id,
                    char_start=chunk.char_start,
                    char_end=chunk.char_end,
                    score=float(hit.score),
                    excerpt=excerpt,
                )
            )

        return results
