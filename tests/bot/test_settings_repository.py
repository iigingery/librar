from __future__ import annotations

from pathlib import Path

import pytest

from librar.bot.repository import (
    BotRepository,
    DEFAULT_EXCERPT_SIZE,
    MAX_EXCERPT_SIZE,
    MIN_EXCERPT_SIZE,
)


def test_get_excerpt_size_returns_default_for_new_user(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"

    with BotRepository(db_path) as repository:
        assert repository.get_excerpt_size(101) == DEFAULT_EXCERPT_SIZE


def test_set_excerpt_size_upserts_existing_user_value(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"

    with BotRepository(db_path) as repository:
        repository.set_excerpt_size(42, 180)
        repository.set_excerpt_size(42, 260)

        assert repository.get_excerpt_size(42) == 260


def test_set_excerpt_size_validates_range(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"

    with BotRepository(db_path) as repository:
        with pytest.raises(ValueError):
            repository.set_excerpt_size(1, MIN_EXCERPT_SIZE - 1)

        with pytest.raises(ValueError):
            repository.set_excerpt_size(1, MAX_EXCERPT_SIZE + 1)


def test_list_books_returns_page_items_and_total_metadata(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"

    with BotRepository(db_path) as repository:
        repository.connection.executemany(
            """
            INSERT INTO books (source_path, title, author, format)
            VALUES (?, ?, ?, ?)
            """,
            [
                ("book-1.txt", "Book 1", "Author 1", "txt"),
                ("book-2.fb2", "Book 2", "Author 2", "fb2"),
                ("book-3.epub", "Book 3", "Author 3", "epub"),
            ],
        )
        repository.connection.commit()

        page = repository.list_books(limit=2, offset=1)

    assert page.total == 3
    assert page.limit == 2
    assert page.offset == 1
    assert [item.source_path for item in page.items] == ["book-2.fb2", "book-3.epub"]
