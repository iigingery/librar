"""SQLite schema and pragmas for text search indexing."""

from __future__ import annotations

import sqlite3


PRAGMA_BUSY_TIMEOUT_MS = 5000


def apply_runtime_pragmas(connection: sqlite3.Connection) -> None:
    """Apply runtime pragmas recommended for local indexing throughput."""

    connection.execute("PRAGMA journal_mode=WAL;")
    connection.execute(f"PRAGMA busy_timeout={PRAGMA_BUSY_TIMEOUT_MS};")
    connection.execute("PRAGMA synchronous=NORMAL;")
    connection.execute("PRAGMA foreign_keys=ON;")


def _add_column_if_missing(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    column_def: str,
) -> None:
    """Add a column to a table if it does not yet exist (idempotent)."""
    try:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_def}")
    except sqlite3.OperationalError as exc:
        if "duplicate column name" not in str(exc).lower():
            raise


def ensure_schema(connection: sqlite3.Connection) -> None:
    """Create search tables, FTS index, and sync triggers if missing."""

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY,
            source_path TEXT NOT NULL UNIQUE,
            title TEXT,
            author TEXT,
            format TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY,
            book_id INTEGER NOT NULL,
            chunk_no INTEGER NOT NULL,
            raw_text TEXT NOT NULL,
            lemma_text TEXT NOT NULL,
            page INTEGER,
            chapter TEXT,
            item_id TEXT,
            char_start INTEGER,
            char_end INTEGER,
            FOREIGN KEY(book_id) REFERENCES books(id) ON DELETE CASCADE,
            UNIQUE(book_id, chunk_no)
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            raw_text,
            lemma_text,
            content='chunks',
            content_rowid='id',
            tokenize='unicode61 remove_diacritics 2'
        );

        CREATE TABLE IF NOT EXISTS index_state (
            source_path TEXT PRIMARY KEY,
            book_id INTEGER NOT NULL,
            fingerprint TEXT NOT NULL,
            mtime_ns INTEGER NOT NULL,
            indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(book_id) REFERENCES books(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS semantic_index_state (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            model TEXT NOT NULL,
            dimension INTEGER NOT NULL,
            metric TEXT NOT NULL DEFAULT 'ip',
            index_path TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS semantic_chunk_state (
            chunk_id INTEGER PRIMARY KEY,
            vector_id INTEGER NOT NULL UNIQUE,
            model TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(chunk_id) REFERENCES chunks(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            excerpt_size INTEGER NOT NULL DEFAULT 200 CHECK(excerpt_size BETWEEN 50 AND 500),
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            parent_id INTEGER REFERENCES categories(id),
            description TEXT
        );

        CREATE TABLE IF NOT EXISTS book_categories (
            book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
            category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
            PRIMARY KEY (book_id, category_id)
        );

        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            tag_type TEXT NOT NULL CHECK(tag_type IN ('topic','region','period','entity')),
            UNIQUE(name, tag_type)
        );

        CREATE TABLE IF NOT EXISTS book_tags (
            book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
            tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
            PRIMARY KEY (book_id, tag_id)
        );

        CREATE TABLE IF NOT EXISTS timeline_events (
            id INTEGER PRIMARY KEY,
            book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
            chunk_id INTEGER REFERENCES chunks(id) ON DELETE SET NULL,
            year_from INTEGER,
            year_to INTEGER,
            decade INTEGER,
            century INTEGER,
            event_text TEXT NOT NULL,
            source_fragment TEXT,
            is_approximate INTEGER NOT NULL DEFAULT 0 CHECK(is_approximate IN (0,1)),
            confidence REAL NOT NULL DEFAULT 1.0
        );

        CREATE INDEX IF NOT EXISTS idx_chunks_book_id ON chunks(book_id);
        CREATE INDEX IF NOT EXISTS idx_index_state_book_id ON index_state(book_id);
        CREATE INDEX IF NOT EXISTS idx_semantic_chunk_state_model ON semantic_chunk_state(model);
        CREATE INDEX IF NOT EXISTS idx_semantic_chunk_state_vector_id ON semantic_chunk_state(vector_id);
        CREATE INDEX IF NOT EXISTS idx_books_language ON books(language);
        CREATE INDEX IF NOT EXISTS idx_timeline_year_from ON timeline_events(year_from);
        CREATE INDEX IF NOT EXISTS idx_timeline_book_id ON timeline_events(book_id);
        CREATE INDEX IF NOT EXISTS idx_book_categories_book_id ON book_categories(book_id);
        CREATE INDEX IF NOT EXISTS idx_book_tags_book_id ON book_tags(book_id);

        CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
            INSERT INTO chunks_fts(rowid, raw_text, lemma_text)
            VALUES (new.id, new.raw_text, new.lemma_text);
        END;

        CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
            INSERT INTO chunks_fts(chunks_fts, rowid, raw_text, lemma_text)
            VALUES ('delete', old.id, old.raw_text, old.lemma_text);
        END;

        CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
            INSERT INTO chunks_fts(chunks_fts, rowid, raw_text, lemma_text)
            VALUES ('delete', old.id, old.raw_text, old.lemma_text);
            INSERT INTO chunks_fts(rowid, raw_text, lemma_text)
            VALUES (new.id, new.raw_text, new.lemma_text);
        END;
        """
    )

    # Additive migrations: add columns to existing tables without breaking old DBs
    _add_column_if_missing(connection, "books", "language", "TEXT")


def optimize_fts(connection: sqlite3.Connection) -> None:
    """Run FTS optimize maintenance command."""

    connection.execute("INSERT INTO chunks_fts(chunks_fts) VALUES ('optimize');")


def rebuild_fts(connection: sqlite3.Connection) -> None:
    """Run FTS rebuild maintenance command."""

    connection.execute("INSERT INTO chunks_fts(chunks_fts) VALUES ('rebuild');")
