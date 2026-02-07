"""FAISS-backed vector persistence and retrieval primitives."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np


@dataclass(slots=True)
class VectorSearchHit:
    vector_id: int
    score: float


@dataclass(slots=True)
class VectorStoreError(RuntimeError):
    message: str

    def __str__(self) -> str:
        return self.message


def _to_vectors_array(vectors: np.ndarray | Sequence[Sequence[float]], *, dimension: int) -> np.ndarray:
    array = np.asarray(vectors, dtype=np.float32)
    if array.ndim != 2:
        raise ValueError("vectors must be a 2D array")
    if array.shape[1] != dimension:
        raise ValueError(f"vector dimension mismatch: expected {dimension}, got {array.shape[1]}")
    if array.shape[0] == 0:
        raise ValueError("vectors cannot be empty")
    return np.ascontiguousarray(array)


def _to_query_array(query_vector: np.ndarray | Sequence[float], *, dimension: int) -> np.ndarray:
    array = np.asarray(query_vector, dtype=np.float32)
    if array.ndim != 1:
        raise ValueError("query_vector must be a 1D array")
    if array.shape[0] != dimension:
        raise ValueError(f"query dimension mismatch: expected {dimension}, got {array.shape[0]}")
    return np.ascontiguousarray(array.reshape(1, -1))


class FaissVectorStore:
    """Thin persistence wrapper around an ID-mapped FAISS index."""

    def __init__(self, index_path: str | Path, *, dimension: int, metric: str = "ip") -> None:
        if dimension <= 0:
            raise ValueError("dimension must be positive")
        if metric not in {"ip", "l2"}:
            raise ValueError("metric must be 'ip' or 'l2'")

        self._index_path = Path(index_path)
        self._dimension = dimension
        self._metric = metric
        self._faiss = self._import_faiss()
        self._index = self._load_or_create_index()

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def metric(self) -> str:
        return self._metric

    @property
    def index_path(self) -> Path:
        return self._index_path

    @property
    def ntotal(self) -> int:
        return int(self._index.ntotal)

    def add_or_replace(self, *, vector_ids: Sequence[int], vectors: np.ndarray | Sequence[Sequence[float]]) -> None:
        ids = np.asarray(vector_ids, dtype=np.int64)
        if ids.ndim != 1:
            raise ValueError("vector_ids must be a 1D sequence")
        if ids.size == 0:
            raise ValueError("vector_ids cannot be empty")
        if len(set(int(value) for value in ids.tolist())) != int(ids.size):
            raise ValueError("vector_ids cannot contain duplicates in one operation")

        rows = _to_vectors_array(vectors, dimension=self._dimension)
        if rows.shape[0] != ids.shape[0]:
            raise ValueError("vector_ids count must match vectors row count")

        if self._metric == "ip":
            self._faiss.normalize_L2(rows)

        self._index.remove_ids(ids)
        self._index.add_with_ids(rows, ids)

    def search(self, query_vector: np.ndarray | Sequence[float], *, top_k: int = 10) -> list[VectorSearchHit]:
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        if self.ntotal == 0:
            return []

        query = _to_query_array(query_vector, dimension=self._dimension)
        if self._metric == "ip":
            self._faiss.normalize_L2(query)

        limit = min(top_k, self.ntotal)
        scores, ids = self._index.search(query, limit)

        hits: list[VectorSearchHit] = []
        for score, vector_id in zip(scores[0], ids[0]):
            if int(vector_id) < 0:
                continue
            hits.append(VectorSearchHit(vector_id=int(vector_id), score=float(score)))
        return hits

    def save(self) -> None:
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._index_path.with_suffix(self._index_path.suffix + ".tmp")
        self._faiss.write_index(self._index, str(tmp_path))
        tmp_path.replace(self._index_path)

    def _import_faiss(self) -> Any:
        try:
            import faiss
        except Exception as exc:  # pragma: no cover - environment-dependent
            raise VectorStoreError(f"FAISS is required for semantic vectors: {exc}") from exc
        return faiss

    def _load_or_create_index(self) -> Any:
        if self._index_path.exists():
            try:
                index = self._faiss.read_index(str(self._index_path))
            except Exception as exc:
                raise VectorStoreError(f"Failed to load FAISS index '{self._index_path}': {exc}") from exc
            if int(index.d) != self._dimension:
                raise VectorStoreError(
                    f"FAISS index dimension mismatch at '{self._index_path}': expected {self._dimension}, got {index.d}"
                )
            return index

        base = self._faiss.IndexFlatIP(self._dimension) if self._metric == "ip" else self._faiss.IndexFlatL2(self._dimension)
        return self._faiss.IndexIDMap2(base)
