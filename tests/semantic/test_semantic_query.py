from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from librar.search.repository import ChunkRow, SearchRepository
from librar.semantic.config import SemanticSettings
from librar.semantic.query import SemanticQueryService
from librar.semantic.semantic_repository import SemanticRepository
from librar.semantic.vector_store import FaissVectorStore


def _seed_book(
    repo: SearchRepository,
    source_path: str,
    body: str,
    *,
    author: str = "tester",
    format_name: str = "txt",
) -> None:
    repo.replace_book_chunks(
        source_path=source_path,
        title=source_path,
        author=author,
        format_name=format_name,
        fingerprint=f"fp-{source_path}",
        mtime_ns=1,
        chunks=[
            ChunkRow(
                chunk_no=0,
                raw_text=body,
                lemma_text=body.lower(),
                page=1,
                chapter="ch-1",
                item_id=None,
                char_start=0,
                char_end=len(body),
            )
        ],
    )


def _chunk_id(repo: SearchRepository, source_path: str) -> int:
    row = repo.connection.execute(
        """
        SELECT c.id AS chunk_id
        FROM chunks c
        JOIN books b ON b.id = c.book_id
        WHERE b.source_path = ?
        LIMIT 1
        """,
        (source_path,),
    ).fetchone()
    assert row is not None
    return int(row["chunk_id"])


class _FixedEmbedder:
    model = "test-semantic-model"

    def __init__(self, vector: list[float]) -> None:
        self._vector = np.asarray(vector, dtype=np.float32)

    def embed_query(self, query: str) -> np.ndarray:
        assert query
        return self._vector


@dataclass
class _StubHit:
    vector_id: int
    score: float


class _StubVectorStore:
    def __init__(self, hits: list[_StubHit]) -> None:
        self._hits = hits

    def search(self, query_vector: np.ndarray, *, top_k: int = 10) -> list[_StubHit]:
        return self._hits[:top_k]


def test_semantic_query_returns_ranked_chunk_results(tmp_path: Path) -> None:
    db_path = tmp_path / "semantic.db"
    index_path = tmp_path / "semantic.faiss"

    with SearchRepository(db_path) as repo:
        _seed_book(repo, "book-a.txt", "Развитие души происходит через практику и служение.")
        _seed_book(repo, "book-b.txt", "Техническое руководство по алгоритмам и структурам данных.")
        chunk_a = _chunk_id(repo, "book-a.txt")
        chunk_b = _chunk_id(repo, "book-b.txt")

        semantic_repo = SemanticRepository(repo.connection)
        semantic_repo.upsert_index_state(
            model="test-semantic-model",
            dimension=3,
            metric="ip",
            index_path=str(index_path),
        )
        semantic_repo.upsert_chunk_state(
            chunk_id=chunk_a,
            vector_id=chunk_a,
            model="test-semantic-model",
            fingerprint="a",
        )
        semantic_repo.upsert_chunk_state(
            chunk_id=chunk_b,
            vector_id=chunk_b,
            model="test-semantic-model",
            fingerprint="b",
        )

        vector_store = FaissVectorStore(index_path, dimension=3, metric="ip")
        vector_store.add_or_replace(
            vector_ids=[chunk_a, chunk_b],
            vectors=[
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
            ],
        )
        vector_store.save()

        service = SemanticQueryService(
            search_repository=repo,
            semantic_repository=semantic_repo,
            vector_store=vector_store,
            embedder=_FixedEmbedder([1.0, 0.0, 0.0]),
        )

        hits = service.search(query="spiritual growth", limit=2)

        assert len(hits) == 2
        assert hits[0].source_path == "book-a.txt"
        assert hits[0].score >= hits[1].score
        assert "Развитие души" in hits[0].excerpt
        assert hits[0].title == "book-a.txt"
        assert hits[0].author == "tester"
        assert hits[0].format_name == "txt"


def test_semantic_query_fails_if_index_not_initialized(tmp_path: Path) -> None:
    db_path = tmp_path / "semantic.db"

    with SearchRepository(db_path) as repo:
        _seed_book(repo, "book-a.txt", "Развитие души через труд.")

        service = SemanticQueryService(
            search_repository=repo,
            semantic_repository=SemanticRepository(repo.connection),
            vector_store=_StubVectorStore([]),
            embedder=_FixedEmbedder([1.0, 0.0, 0.0]),
        )

        with pytest.raises(RuntimeError, match="not initialized"):
            service.search(query="spiritual growth", limit=5)


def test_semantic_query_skips_missing_chunk_mappings(tmp_path: Path) -> None:
    db_path = tmp_path / "semantic.db"

    with SearchRepository(db_path) as repo:
        _seed_book(repo, "book-a.txt", "Развитие души через практику.")
        semantic_repo = SemanticRepository(repo.connection)
        semantic_repo.upsert_index_state(
            model="test-semantic-model",
            dimension=3,
            metric="ip",
            index_path="unused.faiss",
        )

        service = SemanticQueryService(
            search_repository=repo,
            semantic_repository=semantic_repo,
            vector_store=_StubVectorStore([_StubHit(vector_id=9999, score=0.9)]),
            embedder=_FixedEmbedder([1.0, 0.0, 0.0]),
        )

        hits = service.search(query="spiritual growth", limit=5)
        assert hits == []


def test_semantic_query_supports_author_and_format_filters(tmp_path: Path) -> None:
    db_path = tmp_path / "semantic.db"
    index_path = tmp_path / "semantic.faiss"

    with SearchRepository(db_path) as repo:
        _seed_book(
            repo,
            "allowed.fb2",
            "Развитие души через практику и внимание.",
            author="Nisargadatta Maharaj",
            format_name="fb2",
        )
        _seed_book(
            repo,
            "blocked.txt",
            "Развитие души через дисциплину.",
            author="Other Author",
            format_name="txt",
        )
        chunk_a = _chunk_id(repo, "allowed.fb2")
        chunk_b = _chunk_id(repo, "blocked.txt")

        semantic_repo = SemanticRepository(repo.connection)
        semantic_repo.upsert_index_state(
            model="test-semantic-model",
            dimension=3,
            metric="ip",
            index_path=str(index_path),
        )
        semantic_repo.upsert_chunk_state(
            chunk_id=chunk_a,
            vector_id=chunk_a,
            model="test-semantic-model",
            fingerprint="a",
        )
        semantic_repo.upsert_chunk_state(
            chunk_id=chunk_b,
            vector_id=chunk_b,
            model="test-semantic-model",
            fingerprint="b",
        )

        vector_store = FaissVectorStore(index_path, dimension=3, metric="ip")
        vector_store.add_or_replace(
            vector_ids=[chunk_a, chunk_b],
            vectors=[[1.0, 0.0, 0.0], [0.9, 0.1, 0.0]],
        )
        vector_store.save()

        service = SemanticQueryService(
            search_repository=repo,
            semantic_repository=semantic_repo,
            vector_store=vector_store,
            embedder=_FixedEmbedder([1.0, 0.0, 0.0]),
        )

        hits = service.search(
            query="spiritual growth",
            limit=10,
            author_filter="mahar",
            format_filter="fb2",
        )

    assert len(hits) == 1
    assert hits[0].source_path == "allowed.fb2"
    assert hits[0].author == "Nisargadatta Maharaj"
    assert hits[0].format_name == "fb2"


def test_semantic_from_db_path_fails_on_model_mismatch(tmp_path: Path) -> None:
    db_path = tmp_path / "semantic.db"
    index_path = tmp_path / "semantic.faiss"

    with SearchRepository(db_path) as repo:
        semantic_repo = SemanticRepository(repo.connection)
        semantic_repo.upsert_index_state(
            model="indexed-model",
            dimension=3,
            metric="ip",
            index_path=str(index_path),
        )

    settings = SemanticSettings(
        api_key="test-key",
        model="configured-model",
        base_url="https://openrouter.ai/api/v1",
    )

    with pytest.raises(RuntimeError, match="model mismatch"):
        SemanticQueryService.from_db_path(
            db_path=db_path,
            index_path=index_path,
            settings=settings,
        )
