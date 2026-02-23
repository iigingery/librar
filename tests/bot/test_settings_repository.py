from __future__ import annotations

from pathlib import Path

import pytest

from librar.bot.repository import (
    BotRepository,
    DEFAULT_EXCERPT_SIZE,
    DialogMessage,
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


def test_dialog_history_enforces_last_messages_limit(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"

    with BotRepository(db_path) as repository:
        for idx in range(6):
            repository.save_dialog_message(
                chat_id=11,
                user_id=22,
                role="user" if idx % 2 == 0 else "assistant",
                content=f"message-{idx}",
                limit=4,
            )

        history = repository.get_dialog_history(chat_id=11, user_id=22, limit=10)

    assert history == (
        DialogMessage(role="user", content="message-2"),
        DialogMessage(role="assistant", content="message-3"),
        DialogMessage(role="user", content="message-4"),
        DialogMessage(role="assistant", content="message-5"),
    )


def test_clear_dialog_history_removes_only_selected_chat_user(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"

    with BotRepository(db_path) as repository:
        repository.save_dialog_message(chat_id=11, user_id=22, role="user", content="a")
        repository.save_dialog_message(chat_id=11, user_id=22, role="assistant", content="b")
        repository.save_dialog_message(chat_id=11, user_id=99, role="user", content="c")

        removed = repository.clear_dialog_history(chat_id=11, user_id=22)

        target_history = repository.get_dialog_history(chat_id=11, user_id=22)
        other_user_history = repository.get_dialog_history(chat_id=11, user_id=99)

    assert removed == 2
    assert target_history == ()
    assert other_user_history == (DialogMessage(role="user", content="c"),)
