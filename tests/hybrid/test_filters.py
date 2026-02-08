from __future__ import annotations

from pathlib import Path

import numpy as np

from librar.search.query import search_chunks
from librar.search.repository import ChunkRow, SearchRepository
from librar.semantic.query import SemanticQueryService
from librar.semantic.semantic_repository import SemanticRepository
from librar.semantic.vector_store import FaissVectorStore


class _FixedEmbedder:
    model = "test-semantic-model"

    def __init__(self, vector: list[float]) -> None:
        self._vector = np.asarray(vector, dtype=np.float32)

    def embed_query(self, query: str) -> np.ndarray:
        assert query
        return self._vector


def _seed(repo: SearchRepository, source_path: str, *, author: str, format_name: str, text: str) -> int:
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
                raw_text=text,
                lemma_text=text.lower(),
                page=1,
                chapter="ch-1",
                item_id=None,
                char_start=0,
                char_end=len(text),
            )
        ],
    )
    row = repo.connection.execute(
        """
        SELECT c.id AS chunk_id
        FROM chunks c
        JOIN books b ON b.id = c.book_id
        WHERE b.source_path = ?
        """,
        (source_path,),
    ).fetchone()
    assert row is not None
    return int(row["chunk_id"])


def test_text_and_semantic_filters_align(tmp_path: Path) -> None:
    db_path = tmp_path / "hybrid.db"
    index_path = tmp_path / "hybrid.faiss"

    with SearchRepository(db_path) as repo:
        keep_id = _seed(
            repo,
            "keep.fb2",
            author="Nisargadatta Maharaj",
            format_name="fb2",
            text="книга о духовной практике и внимании",
        )
        skip_id = _seed(
            repo,
            "skip.txt",
            author="Another Author",
            format_name="txt",
            text="книга о духовной практике и внимании",
        )

        text_hits = search_chunks(
            repo.connection,
            query="книга",
            author_filter="mahar",
            format_filter="fb2",
            limit=10,
        )

        semantic_repo = SemanticRepository(repo.connection)
        semantic_repo.upsert_index_state(
            model="test-semantic-model",
            dimension=3,
            metric="ip",
            index_path=str(index_path),
        )
        semantic_repo.upsert_chunk_state(
            chunk_id=keep_id,
            vector_id=keep_id,
            model="test-semantic-model",
            fingerprint="keep",
        )
        semantic_repo.upsert_chunk_state(
            chunk_id=skip_id,
            vector_id=skip_id,
            model="test-semantic-model",
            fingerprint="skip",
        )

        vector_store = FaissVectorStore(index_path, dimension=3, metric="ip")
        vector_store.add_or_replace(
            vector_ids=[keep_id, skip_id],
            vectors=[[1.0, 0.0, 0.0], [0.8, 0.2, 0.0]],
        )
        vector_store.save()

        semantic_service = SemanticQueryService(
            search_repository=repo,
            semantic_repository=semantic_repo,
            vector_store=vector_store,
            embedder=_FixedEmbedder([1.0, 0.0, 0.0]),
        )
        semantic_hits = semantic_service.search(
            query="spiritual growth",
            author_filter="mahar",
            format_filter="fb2",
            limit=10,
        )

    assert len(text_hits) == 1
    assert text_hits[0].source_path == "keep.fb2"
    assert text_hits[0].author == "Nisargadatta Maharaj"
    assert text_hits[0].format_name == "fb2"

    assert len(semantic_hits) == 1
    assert semantic_hits[0].source_path == "keep.fb2"
    assert semantic_hits[0].author == "Nisargadatta Maharaj"
    assert semantic_hits[0].format_name == "fb2"
