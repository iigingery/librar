from __future__ import annotations

from pathlib import Path

from librar.search.repository import ChunkRow, SearchRepository
from librar.semantic.semantic_repository import SemanticRepository


def _seed_chunk(repo: SearchRepository, source_path: str, chunk_no: int) -> int:
    return repo.replace_book_chunks(
        source_path=source_path,
        title=source_path,
        author="tester",
        format_name="txt",
        fingerprint=f"fp-{source_path}-{chunk_no}",
        mtime_ns=1,
        chunks=[
            ChunkRow(
                chunk_no=chunk_no,
                raw_text=f"Chunk {chunk_no} text",
                lemma_text=f"chunk {chunk_no} text",
                page=1,
                chapter="ch-1",
                item_id=None,
                char_start=0,
                char_end=12,
            )
        ],
    )


def _first_chunk_id(repo: SearchRepository, source_path: str) -> int:
    row = repo.connection.execute(
        """
        SELECT c.id AS chunk_id
        FROM chunks c
        JOIN books b ON b.id = c.book_id
        WHERE b.source_path = ?
        ORDER BY c.id ASC
        LIMIT 1
        """,
        (source_path,),
    ).fetchone()
    assert row is not None
    return int(row["chunk_id"])


def test_semantic_index_state_persists_across_reopen(tmp_path: Path) -> None:
    db_path = tmp_path / "semantic.db"

    with SearchRepository(db_path) as repo:
        semantic = SemanticRepository(repo.connection)
        assert semantic.get_index_state() is None
        semantic.upsert_index_state(
            model="openai/text-embedding-3-small",
            dimension=1536,
            metric="ip",
            index_path=".librar-semantic.faiss",
        )

    with SearchRepository(db_path) as repo:
        semantic = SemanticRepository(repo.connection)
        state = semantic.get_index_state()
        assert state is not None
        assert state.model == "openai/text-embedding-3-small"
        assert state.dimension == 1536
        assert state.metric == "ip"
        assert state.index_path == ".librar-semantic.faiss"


def test_chunk_state_upsert_and_cleanup(tmp_path: Path) -> None:
    db_path = tmp_path / "semantic.db"

    with SearchRepository(db_path) as repo:
        _seed_chunk(repo, "book-a.txt", 0)
        _seed_chunk(repo, "book-b.txt", 0)
        chunk_a = _first_chunk_id(repo, "book-a.txt")
        chunk_b = _first_chunk_id(repo, "book-b.txt")

        semantic = SemanticRepository(repo.connection)
        semantic.upsert_chunk_state(
            chunk_id=chunk_a,
            vector_id=100,
            model="openai/text-embedding-3-small",
            fingerprint="a-v1",
        )
        semantic.upsert_chunk_state(
            chunk_id=chunk_b,
            vector_id=101,
            model="openai/text-embedding-3-small",
            fingerprint="b-v1",
        )

        updated = semantic.get_chunk_state(chunk_id=chunk_a, model="openai/text-embedding-3-small")
        assert updated is not None
        assert updated.vector_id == 100

        semantic.upsert_chunk_state(
            chunk_id=chunk_a,
            vector_id=200,
            model="openai/text-embedding-3-small",
            fingerprint="a-v2",
        )
        updated_again = semantic.get_chunk_state(chunk_id=chunk_a, model="openai/text-embedding-3-small")
        assert updated_again is not None
        assert updated_again.vector_id == 200
        assert updated_again.fingerprint == "a-v2"

        removed = semantic.delete_chunk_states_not_in(
            model="openai/text-embedding-3-small",
            chunk_ids={chunk_a},
        )
        assert removed == 1
        states = semantic.list_chunk_states(model="openai/text-embedding-3-small")
        assert [state.chunk_id for state in states] == [chunk_a]
