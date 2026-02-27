"""Tests for v2.0 schema additions: language column and taxonomy/timeline tables."""

from __future__ import annotations

from pathlib import Path

from librar.search.repository import ChunkRow, SearchRepository


def test_books_table_has_language_column(tmp_path: Path) -> None:
    db_path = tmp_path / "schema_v2.db"

    with SearchRepository(db_path) as repo:
        cols = {
            row[1]
            for row in repo.connection.execute("PRAGMA table_info(books)")
        }

    assert "language" in cols


def test_taxonomy_and_timeline_tables_exist(tmp_path: Path) -> None:
    db_path = tmp_path / "schema_v2.db"

    with SearchRepository(db_path) as repo:
        tables = {
            row["name"]
            for row in repo.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

    for name in ("categories", "book_categories", "tags", "book_tags", "timeline_events"):
        assert name in tables, f"expected table '{name}' not found"


def test_ensure_schema_is_idempotent(tmp_path: Path) -> None:
    """Running ensure_schema twice must not raise (idempotent ALTER TABLE)."""
    db_path = tmp_path / "schema_v2.db"

    with SearchRepository(db_path):
        pass  # first open → runs ensure_schema

    with SearchRepository(db_path):
        pass  # second open → must not raise "duplicate column name" etc.


def test_language_is_stored_and_retrieved(tmp_path: Path) -> None:
    db_path = tmp_path / "schema_v2.db"

    with SearchRepository(db_path) as repo:
        repo.replace_book_chunks(
            source_path="kazakh.pdf",
            title="Казах китабы",
            author=None,
            format_name="pdf",
            language="kk",
            fingerprint="fp-kk",
            mtime_ns=1,
            chunks=[],
        )
        row = repo.connection.execute(
            "SELECT language FROM books WHERE source_path = ?",
            ("kazakh.pdf",),
        ).fetchone()

    assert row is not None
    assert row["language"] == "kk"


def test_language_update_on_reindex(tmp_path: Path) -> None:
    db_path = tmp_path / "schema_v2.db"

    with SearchRepository(db_path) as repo:
        repo.replace_book_chunks(
            source_path="book.pdf",
            title="Book",
            author=None,
            format_name="pdf",
            language="ru",
            fingerprint="fp-1",
            mtime_ns=1,
            chunks=[],
        )
        # Re-index with corrected language
        repo.replace_book_chunks(
            source_path="book.pdf",
            title="Book",
            author=None,
            format_name="pdf",
            language="en",
            fingerprint="fp-2",
            mtime_ns=2,
            chunks=[],
        )
        row = repo.connection.execute(
            "SELECT language FROM books WHERE source_path = ?",
            ("book.pdf",),
        ).fetchone()

    assert row["language"] == "en"


def test_timeline_events_foreign_key_cascade(tmp_path: Path) -> None:
    """Deleting a book must cascade-delete its timeline_events."""
    db_path = tmp_path / "schema_v2.db"

    with SearchRepository(db_path) as repo:
        conn = repo.connection
        repo.replace_book_chunks(
            source_path="tl.pdf",
            title="TL",
            author=None,
            format_name="pdf",
            language="ru",
            fingerprint="fp",
            mtime_ns=1,
            chunks=[],
        )
        book_id = conn.execute(
            "SELECT id FROM books WHERE source_path = ?", ("tl.pdf",)
        ).fetchone()["id"]

        conn.execute(
            """INSERT INTO timeline_events
               (book_id, year_from, year_to, event_text, confidence)
               VALUES (?, 1917, 1917, 'Революция', 0.9)""",
            (book_id,),
        )
        conn.commit()

        conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
        conn.commit()

        events = conn.execute(
            "SELECT id FROM timeline_events WHERE book_id = ?", (book_id,)
        ).fetchall()

    assert events == []
