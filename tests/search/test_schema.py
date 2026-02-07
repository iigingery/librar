from __future__ import annotations

from pathlib import Path

from librar.search.repository import ChunkRow, SearchRepository


def test_schema_initialization_creates_expected_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"

    with SearchRepository(db_path) as repo:
        table_rows = repo.connection.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
        ).fetchall()
        table_names = {row["name"] for row in table_rows}

        assert "books" in table_names
        assert "chunks" in table_names
        assert "index_state" in table_names
        assert "chunks_fts" in table_names
        assert "semantic_index_state" in table_names
        assert "semantic_chunk_state" in table_names


def test_fts_is_queryable_with_external_content_sync(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"

    with SearchRepository(db_path) as repo:
        repo.replace_book_chunks(
            source_path="book-a.txt",
            title="Book A",
            author="Author A",
            format_name="txt",
            fingerprint="fp-a",
            mtime_ns=1,
            chunks=[
                ChunkRow(
                    chunk_no=0,
                    raw_text="Привет книги и книжный мир",
                    lemma_text="привет книга и книжный мир",
                    page=None,
                    chapter=None,
                    item_id=None,
                    char_start=0,
                    char_end=25,
                )
            ],
        )

        row = repo.connection.execute(
            """
            SELECT c.raw_text
            FROM chunks_fts f
            JOIN chunks c ON c.id = f.rowid
            WHERE chunks_fts MATCH 'lemma_text:книга'
            """
        ).fetchone()

        assert row is not None
        assert "книги" in row["raw_text"]


def test_index_state_persists_and_updates(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"

    with SearchRepository(db_path) as repo:
        repo.replace_book_chunks(
            source_path="book-a.txt",
            title="Book A",
            author="Author A",
            format_name="txt",
            fingerprint="fp-1",
            mtime_ns=100,
            chunks=[],
        )
        state = repo.get_index_state("book-a.txt")
        assert state is not None
        assert state.fingerprint == "fp-1"
        assert state.mtime_ns == 100

        repo.replace_book_chunks(
            source_path="book-a.txt",
            title="Book A v2",
            author="Author A",
            format_name="txt",
            fingerprint="fp-2",
            mtime_ns=200,
            chunks=[],
        )
        updated = repo.get_index_state("book-a.txt")
        assert updated is not None
        assert updated.fingerprint == "fp-2"
        assert updated.mtime_ns == 200


def test_maintenance_hooks_are_available(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"

    with SearchRepository(db_path) as repo:
        repo.run_maintenance("optimize")
        repo.run_maintenance("rebuild")
