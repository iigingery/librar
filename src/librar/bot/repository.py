"""Repository primitives for Telegram bot settings and book listings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3

from librar.search.schema import apply_runtime_pragmas, ensure_schema


DEFAULT_EXCERPT_SIZE = 200
MIN_EXCERPT_SIZE = 50
MAX_EXCERPT_SIZE = 500


@dataclass(slots=True)
class BookListItem:
    id: int
    source_path: str
    title: str | None
    author: str | None
    format_name: str | None


@dataclass(slots=True)
class BookListPage:
    items: list[BookListItem]
    total: int
    limit: int
    offset: int


class BotRepository:
    """SQLite-backed storage facade for bot-specific data access."""

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

    def __enter__(self) -> "BotRepository":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def get_excerpt_size(self, user_id: int) -> int:
        row = self._connection.execute(
            "SELECT excerpt_size FROM user_settings WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            return DEFAULT_EXCERPT_SIZE
        return int(row["excerpt_size"])

    def set_excerpt_size(self, user_id: int, size: int) -> None:
        if not MIN_EXCERPT_SIZE <= size <= MAX_EXCERPT_SIZE:
            raise ValueError(
                f"excerpt_size must be between {MIN_EXCERPT_SIZE} and {MAX_EXCERPT_SIZE}"
            )

        with self._connection:
            self._connection.execute(
                """
                INSERT INTO user_settings (user_id, excerpt_size)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    excerpt_size = excluded.excerpt_size,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, size),
            )

    def list_books(self, limit: int, offset: int) -> BookListPage:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if offset < 0:
            raise ValueError("offset cannot be negative")

        total = int(self._connection.execute("SELECT COUNT(*) AS c FROM books").fetchone()["c"])
        rows = self._connection.execute(
            """
            SELECT id, source_path, title, author, format
            FROM books
            ORDER BY id ASC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
        items = [
            BookListItem(
                id=int(row["id"]),
                source_path=row["source_path"],
                title=row["title"],
                author=row["author"],
                format_name=row["format"],
            )
            for row in rows
        ]
        return BookListPage(items=items, total=total, limit=limit, offset=offset)
