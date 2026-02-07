"""Repository primitives for FTS-backed chunk persistence."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3

from librar.search.schema import apply_runtime_pragmas, ensure_schema, optimize_fts, rebuild_fts


@dataclass(slots=True)
class ChunkRow:
    chunk_no: int
    raw_text: str
    lemma_text: str
    page: int | None
    chapter: str | None
    item_id: str | None
    char_start: int | None
    char_end: int | None


@dataclass(slots=True)
class IndexStateRow:
    source_path: str
    book_id: int
    fingerprint: str
    mtime_ns: int


@dataclass(slots=True)
class ChunkTextRow:
    chunk_id: int
    book_id: int
    source_path: str
    chunk_no: int
    raw_text: str
    page: int | None
    chapter: str | None
    item_id: str | None
    char_start: int | None
    char_end: int | None


class SearchRepository:
    """Thin transactional layer over SQLite search schema."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._connection = sqlite3.connect(str(self._db_path))
        self._connection.row_factory = sqlite3.Row
        apply_runtime_pragmas(self._connection)
        ensure_schema(self._connection)

    @property
    def connection(self) -> sqlite3.Connection:
        return self._connection

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "SearchRepository":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def get_index_state(self, source_path: str) -> IndexStateRow | None:
        row = self._connection.execute(
            """
            SELECT source_path, book_id, fingerprint, mtime_ns
            FROM index_state
            WHERE source_path = ?
            """,
            (source_path,),
        ).fetchone()
        if row is None:
            return None
        return IndexStateRow(
            source_path=row["source_path"],
            book_id=row["book_id"],
            fingerprint=row["fingerprint"],
            mtime_ns=row["mtime_ns"],
        )

    def replace_book_chunks(
        self,
        *,
        source_path: str,
        title: str | None,
        author: str | None,
        format_name: str | None,
        fingerprint: str,
        mtime_ns: int,
        chunks: list[ChunkRow],
    ) -> int:
        """Replace one book's chunks and index state in one transaction."""

        with self._connection:
            self._connection.execute(
                """
                INSERT INTO books(source_path, title, author, format)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(source_path) DO UPDATE SET
                    title=excluded.title,
                    author=excluded.author,
                    format=excluded.format,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (source_path, title, author, format_name),
            )
            row = self._connection.execute(
                "SELECT id FROM books WHERE source_path = ?",
                (source_path,),
            ).fetchone()
            if row is None:
                raise RuntimeError(f"Book row missing after upsert: {source_path}")
            book_id = int(row["id"])

            self._connection.execute("DELETE FROM chunks WHERE book_id = ?", (book_id,))
            self._connection.executemany(
                """
                INSERT INTO chunks(
                    book_id,
                    chunk_no,
                    raw_text,
                    lemma_text,
                    page,
                    chapter,
                    item_id,
                    char_start,
                    char_end
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        book_id,
                        chunk.chunk_no,
                        chunk.raw_text,
                        chunk.lemma_text,
                        chunk.page,
                        chunk.chapter,
                        chunk.item_id,
                        chunk.char_start,
                        chunk.char_end,
                    )
                    for chunk in chunks
                ],
            )

            self._connection.execute(
                """
                INSERT INTO index_state(source_path, book_id, fingerprint, mtime_ns)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(source_path) DO UPDATE SET
                    book_id=excluded.book_id,
                    fingerprint=excluded.fingerprint,
                    mtime_ns=excluded.mtime_ns,
                    indexed_at=CURRENT_TIMESTAMP
                """,
                (source_path, book_id, fingerprint, mtime_ns),
            )

        return book_id

    def run_maintenance(self, command: str) -> None:
        if command == "optimize":
            optimize_fts(self._connection)
            return
        if command == "rebuild":
            rebuild_fts(self._connection)
            return
        raise ValueError(f"Unsupported maintenance command: {command}")

    def iter_chunks(self, *, limit: int | None = None, offset: int = 0) -> list[ChunkTextRow]:
        if offset < 0:
            raise ValueError("offset cannot be negative")

        if limit is None:
            rows = self._connection.execute(
                """
                SELECT
                    c.id AS chunk_id,
                    c.book_id AS book_id,
                    b.source_path AS source_path,
                    c.chunk_no AS chunk_no,
                    c.raw_text AS raw_text,
                    c.page AS page,
                    c.chapter AS chapter,
                    c.item_id AS item_id,
                    c.char_start AS char_start,
                    c.char_end AS char_end
                FROM chunks c
                JOIN books b ON b.id = c.book_id
                ORDER BY c.id ASC
                """
            ).fetchall()
        else:
            if limit <= 0:
                raise ValueError("limit must be positive")
            rows = self._connection.execute(
                """
                SELECT
                    c.id AS chunk_id,
                    c.book_id AS book_id,
                    b.source_path AS source_path,
                    c.chunk_no AS chunk_no,
                    c.raw_text AS raw_text,
                    c.page AS page,
                    c.chapter AS chapter,
                    c.item_id AS item_id,
                    c.char_start AS char_start,
                    c.char_end AS char_end
                FROM chunks c
                JOIN books b ON b.id = c.book_id
                ORDER BY c.id ASC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()

        return [
            ChunkTextRow(
                chunk_id=int(row["chunk_id"]),
                book_id=int(row["book_id"]),
                source_path=row["source_path"],
                chunk_no=int(row["chunk_no"]),
                raw_text=row["raw_text"],
                page=row["page"],
                chapter=row["chapter"],
                item_id=row["item_id"],
                char_start=row["char_start"],
                char_end=row["char_end"],
            )
            for row in rows
        ]

    def fetch_chunks_by_ids(self, chunk_ids: list[int]) -> list[ChunkTextRow]:
        if not chunk_ids:
            return []

        placeholders = ",".join("?" for _ in chunk_ids)
        rows = self._connection.execute(
            f"""
            SELECT
                c.id AS chunk_id,
                c.book_id AS book_id,
                b.source_path AS source_path,
                c.chunk_no AS chunk_no,
                c.raw_text AS raw_text,
                c.page AS page,
                c.chapter AS chapter,
                c.item_id AS item_id,
                c.char_start AS char_start,
                c.char_end AS char_end
            FROM chunks c
            JOIN books b ON b.id = c.book_id
            WHERE c.id IN ({placeholders})
            ORDER BY c.id ASC
            """,
            tuple(chunk_ids),
        ).fetchall()

        return [
            ChunkTextRow(
                chunk_id=int(row["chunk_id"]),
                book_id=int(row["book_id"]),
                source_path=row["source_path"],
                chunk_no=int(row["chunk_no"]),
                raw_text=row["raw_text"],
                page=row["page"],
                chapter=row["chapter"],
                item_id=row["item_id"],
                char_start=row["char_start"],
                char_end=row["char_end"],
            )
            for row in rows
        ]
