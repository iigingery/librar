"""Repository primitives for Telegram bot settings and book listings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3

from librar.search.schema import apply_runtime_pragmas, ensure_schema


DEFAULT_EXCERPT_SIZE = 200
MIN_EXCERPT_SIZE = 50
MAX_EXCERPT_SIZE = 500
DEFAULT_DIALOG_HISTORY_LIMIT = 20


@dataclass(slots=True)
class DialogMessage:
    role: str
    content: str


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
        self._ensure_bot_schema()

    def _ensure_bot_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS dialog_history (
                id INTEGER PRIMARY KEY,
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_dialog_history_chat_user_id
            ON dialog_history(chat_id, user_id, id);
            """
        )

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

    def save_dialog_message(
        self,
        *,
        chat_id: int,
        user_id: int,
        role: str,
        content: str,
        limit: int = DEFAULT_DIALOG_HISTORY_LIMIT,
    ) -> None:
        if role not in {"user", "assistant"}:
            raise ValueError("role must be either 'user' or 'assistant'")
        if limit < 1:
            raise ValueError("limit must be positive")

        normalized = content.strip()
        if not normalized:
            return

        with self._connection:
            self._connection.execute(
                """
                INSERT INTO dialog_history (chat_id, user_id, role, content)
                VALUES (?, ?, ?, ?)
                """,
                (chat_id, user_id, role, normalized),
            )
            self._connection.execute(
                """
                DELETE FROM dialog_history
                WHERE chat_id = ?
                  AND user_id = ?
                  AND id NOT IN (
                      SELECT id FROM dialog_history
                      WHERE chat_id = ? AND user_id = ?
                      ORDER BY id DESC
                      LIMIT ?
                  )
                """,
                (chat_id, user_id, chat_id, user_id, limit),
            )

    def get_dialog_history(
        self,
        *,
        chat_id: int,
        user_id: int,
        limit: int = DEFAULT_DIALOG_HISTORY_LIMIT,
    ) -> tuple[DialogMessage, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")

        rows = self._connection.execute(
            """
            SELECT role, content
            FROM dialog_history
            WHERE chat_id = ? AND user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (chat_id, user_id, limit),
        ).fetchall()

        return tuple(
            DialogMessage(role=row["role"], content=row["content"])
            for row in reversed(rows)
        )

    def clear_dialog_history(self, *, chat_id: int, user_id: int) -> int:
        with self._connection:
            cursor = self._connection.execute(
                "DELETE FROM dialog_history WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id),
            )
        return int(cursor.rowcount)
