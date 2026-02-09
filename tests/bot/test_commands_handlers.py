"""Tests for command handlers (/start, /help, /search, /books)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from librar.bot.handlers.commands import books_command, help_command, search_command, start_command
from librar.bot.repository import BotRepository
from librar.bot.search_service import SearchResponse, SearchResult


class DummyMessage:
    def __init__(self, text: str | None = None) -> None:
        self.text = text
        self.replies: list[dict[str, Any]] = []

    async def reply_text(self, text: str, reply_markup: Any = None) -> None:
        self.replies.append({"text": text, "reply_markup": reply_markup})


def _context(
    repository: BotRepository,
    db_path: str = ".librar-search.db",
    index_path: str = ".librar-semantic.faiss",
    page_size: int = 5,
    command_result_limit: int = 10,
) -> SimpleNamespace:
    return SimpleNamespace(
        bot_data={
            "repository": repository,
            "db_path": db_path,
            "index_path": index_path,
            "page_size": page_size,
            "command_result_limit": command_result_limit,
        },
        user_data={},
        args=[],
    )


def test_start_command_includes_usage_instructions(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"

    with BotRepository(db_path) as repository:
        message = DummyMessage()
        update = SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=123),
        )

        asyncio.run(start_command(update, _context(repository)))

    assert len(message.replies) == 1
    reply_text = message.replies[0]["text"]
    assert "/search" in reply_text
    assert "inline mode" in reply_text or "@botname" in reply_text
    assert "/books" in reply_text
    assert "/help" in reply_text


def test_help_command_includes_detailed_guidance(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"

    with BotRepository(db_path) as repository:
        message = DummyMessage()
        update = SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=123),
        )

        asyncio.run(help_command(update, _context(repository)))

    assert len(message.replies) == 1
    reply_text = message.replies[0]["text"]
    assert "/start" in reply_text
    assert "/search" in reply_text
    assert "/books" in reply_text
    assert "/settings" in reply_text
    assert "inline" in reply_text.lower()


def test_search_command_prompts_for_missing_query(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"

    with BotRepository(db_path) as repository:
        message = DummyMessage()
        update = SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=123),
        )
        ctx = _context(repository)
        ctx.args = []

        asyncio.run(search_command(update, ctx))

    assert len(message.replies) == 1
    reply_text = message.replies[0]["text"]
    assert "Использование" in reply_text or "/search" in reply_text


def test_search_command_handles_no_results(tmp_path: Path, monkeypatch: Any) -> None:
    db_path = tmp_path / "search.db"

    async def mock_search(**kwargs: Any) -> SearchResponse:
        del kwargs
        return SearchResponse(results=())

    monkeypatch.setattr("librar.bot.handlers.commands.search_hybrid_cli", mock_search)

    with BotRepository(db_path) as repository:
        message = DummyMessage()
        update = SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=123),
        )
        ctx = _context(repository)
        ctx.args = ["test", "query"]

        asyncio.run(search_command(update, ctx))

    assert len(message.replies) == 1
    reply_text = message.replies[0]["text"]
    assert "не найдено" in reply_text.lower()


def test_search_command_renders_results_with_pagination(tmp_path: Path, monkeypatch: Any) -> None:
    db_path = tmp_path / "search.db"

    mock_results = tuple(
        SearchResult(
            source_path=f"book_{i}.pdf",
            chunk_id=i,
            chunk_no=i,
            display=f"Book {i}, Page {i}",
            excerpt=f"Sample excerpt from chunk {i} " * 10,
            title=f"Title {i}",
        )
        for i in range(7)
    )

    async def mock_search(**kwargs: Any) -> SearchResponse:
        del kwargs
        return SearchResponse(results=mock_results)

    monkeypatch.setattr("librar.bot.handlers.commands.search_hybrid_cli", mock_search)

    with BotRepository(db_path) as repository:
        message = DummyMessage()
        update = SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=123),
        )
        ctx = _context(repository, page_size=5)
        ctx.args = ["test"]

        asyncio.run(search_command(update, ctx))

    assert len(message.replies) == 1
    reply = message.replies[0]
    reply_text = reply["text"]

    # Should show first page results
    assert "Book 0" in reply_text
    assert "Book 4" in reply_text
    assert "Book 6" not in reply_text  # Page 2

    # Should have pagination keyboard
    assert reply["reply_markup"] is not None
    buttons = reply["reply_markup"].inline_keyboard[0]
    assert any("Следующая" in btn.text for btn in buttons)

    # Should store results in user_data
    assert "search_results" in ctx.user_data
    assert len(ctx.user_data["search_results"]) == 7


def test_search_command_handles_timeout(tmp_path: Path, monkeypatch: Any) -> None:
    db_path = tmp_path / "search.db"

    async def mock_search(**kwargs: Any) -> SearchResponse:
        del kwargs
        return SearchResponse(results=(), error="Search timed out", timed_out=True)

    monkeypatch.setattr("librar.bot.handlers.commands.search_hybrid_cli", mock_search)

    with BotRepository(db_path) as repository:
        message = DummyMessage()
        update = SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=123),
        )
        ctx = _context(repository)
        ctx.args = ["test"]

        asyncio.run(search_command(update, ctx))

    assert len(message.replies) == 1
    reply_text = message.replies[0]["text"]
    # Timeout goes through error path with timed_out=True
    assert "превысил" in reply_text.lower() or "лимит" in reply_text.lower()


def test_books_command_lists_metadata_with_pagination(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"

    with BotRepository(db_path) as repository:
        # Insert books into repository
        conn = repository.connection
        for i in range(7):
            conn.execute(
                """
                INSERT INTO books (source_path, title, author, format)
                VALUES (?, ?, ?, ?)
                """,
                (f"book_{i}.pdf", f"Title {i}", f"Author {i}", "pdf"),
            )
        conn.commit()

        message = DummyMessage()
        update = SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=123),
        )
        ctx = _context(repository, page_size=5)

        asyncio.run(books_command(update, ctx))

    assert len(message.replies) == 1
    reply = message.replies[0]
    reply_text = reply["text"]

    # Should show first page books
    assert "Title 0" in reply_text
    assert "Author 0" in reply_text
    assert "Title 4" in reply_text
    assert "Title 6" not in reply_text  # Page 2

    # Should show total count
    assert "7" in reply_text

    # Should have pagination keyboard
    assert reply["reply_markup"] is not None
    buttons = reply["reply_markup"].inline_keyboard[0]
    assert any("Следующая" in btn.text for btn in buttons)


def test_books_command_handles_empty_library(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"

    with BotRepository(db_path) as repository:
        message = DummyMessage()
        update = SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=123),
        )

        asyncio.run(books_command(update, _context(repository)))

    assert len(message.replies) == 1
    reply_text = message.replies[0]["text"]
    assert "пуста" in reply_text.lower()
