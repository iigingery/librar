"""Repository for taxonomy categories and book classifications."""

from __future__ import annotations

import sqlite3


class TaxonomyRepository:
    """Thin persistence layer for the taxonomy tables."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection

    def seed_categories_from_thesaurus(self, categories: list[dict]) -> None:
        """Insert or update categories from a thesaurus definition (idempotent)."""
        for cat in categories:
            self._conn.execute(
                """
                INSERT INTO categories(id, name, parent_id, description)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    parent_id=excluded.parent_id,
                    description=excluded.description
                """,
                (cat["id"], cat["name"], cat.get("parent_id"), cat.get("description")),
            )
        self._conn.commit()

    def assign_book_categories(self, book_id: int, category_ids: list[int]) -> None:
        """Replace a book's category assignments."""
        self._conn.execute(
            "DELETE FROM book_categories WHERE book_id = ?", (book_id,)
        )
        if category_ids:
            self._conn.executemany(
                "INSERT OR IGNORE INTO book_categories(book_id, category_id) VALUES(?, ?)",
                [(book_id, cat_id) for cat_id in category_ids],
            )
        self._conn.commit()

    def get_books_by_category(self, category_id: int) -> list[int]:
        """Return all book IDs assigned to a category."""
        rows = self._conn.execute(
            "SELECT book_id FROM book_categories WHERE category_id = ?",
            (category_id,),
        ).fetchall()
        return [row[0] for row in rows]
