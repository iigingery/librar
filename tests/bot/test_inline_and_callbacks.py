"""Tests for inline query and callback pagination handlers."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from librar.bot.handlers.callbacks import books_page_callback, search_page_callback
from librar.bot.handlers.inline import inline_query_handler
from librar.bot.repository import BotRepository
from librar.bot.search_service import SearchResponse, SearchResult


class DummyInlineQuery:
    def __init__(self, query: str) -> None:
        self.query = query
        self.answers: list[list[Any]] = []

    async def answer(self, results: list[Any], cache_time: int = 30) -> None:
        self.answers.append(results)


class DummyCallbackQuery:
    def __init__(self, data: str) -> None:
        self.data = data
        self.answered = False
        self.edited_messages: list[dict[str, Any]] = []

    async def answer(self) -> None:
        self.answered = True

    async def edit_message_text(self, text: str, reply_markup: Any = None) -> None:
        self.edited_messages.append({"text": text, "reply_markup": reply_markup})


def _context(
    repository: BotRepository,
    db_path: str = ".librar-search.db",
    index_path: str = ".librar-semantic.faiss",
    page_size: int = 5,
    inline_result_limit: int = 20,
    inline_timeout_seconds: float = 25.0,
) -> SimpleNamespace:
    return SimpleNamespace(
        bot_data={
            "repository": repository,
            "db_path": db_path,
            "index_path": index_path,
            "page_size": page_size,
            "inline_result_limit": inline_result_limit,
            "inline_timeout_seconds": inline_timeout_seconds,
        },
        user_data={},
    )


def test_inline_handler_short_circuits_empty_query(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"

    with BotRepository(db_path) as repository:
        inline_query = DummyInlineQuery("")
        update = SimpleNamespace(
            inline_query=inline_query,
            effective_user=SimpleNamespace(id=123),
        )

        asyncio.run(inline_query_handler(update, _context(repository)))

    assert len(inline_query.answers) == 1
    assert len(inline_query.answers[0]) == 0


def test_inline_handler_returns_article_results_for_valid_query(tmp_path: Path, monkeypatch: Any) -> None:
    db_path = tmp_path / "search.db"

    mock_results = tuple(
        SearchResult(
            source_path=f"book_{i}.pdf",
            chunk_id=i,
            chunk_no=i,
            display=f"Book {i}, Page {i}",
            excerpt=f"Excerpt {i} content",
            title=f"Title {i}",
            author=f"Author {i}",
        )
        for i in range(3)
    )

    async def mock_search(**kwargs: Any) -> SearchResponse:
        del kwargs
        return SearchResponse(results=mock_results)

    monkeypatch.setattr("librar.bot.handlers.inline.search_hybrid_cli", mock_search)

    with BotRepository(db_path) as repository:
        inline_query = DummyInlineQuery("test query")
        update = SimpleNamespace(
            inline_query=inline_query,
            effective_user=SimpleNamespace(id=123),
        )

        asyncio.run(inline_query_handler(update, _context(repository)))

    assert len(inline_query.answers) == 1
    results = inline_query.answers[0]
    assert len(results) == 3
    assert all(hasattr(r, "id") for r in results)
    assert all(hasattr(r, "title") for r in results)
    assert "Book 0" in results[0].title


def test_inline_handler_handles_no_results(tmp_path: Path, monkeypatch: Any) -> None:
    db_path = tmp_path / "search.db"

    async def mock_search(**kwargs: Any) -> SearchResponse:
        del kwargs
        return SearchResponse(results=())

    monkeypatch.setattr("librar.bot.handlers.inline.search_hybrid_cli", mock_search)

    with BotRepository(db_path) as repository:
        inline_query = DummyInlineQuery("no results query")
        update = SimpleNamespace(
            inline_query=inline_query,
            effective_user=SimpleNamespace(id=123),
        )

        asyncio.run(inline_query_handler(update, _context(repository)))

    assert len(inline_query.answers) == 1
    results = inline_query.answers[0]
    assert len(results) == 1
    assert "не найдено" in results[0].title.lower() or "no" in results[0].title.lower()


def test_inline_handler_handles_timeout_safely(tmp_path: Path, monkeypatch: Any) -> None:
    db_path = tmp_path / "search.db"

    async def mock_search(**kwargs: Any) -> SearchResponse:
        del kwargs
        return SearchResponse(results=(), error="Search timed out", timed_out=True)

    monkeypatch.setattr("librar.bot.handlers.inline.search_hybrid_cli", mock_search)

    with BotRepository(db_path) as repository:
        inline_query = DummyInlineQuery("timeout query")
        update = SimpleNamespace(
            inline_query=inline_query,
            effective_user=SimpleNamespace(id=123),
        )

        asyncio.run(inline_query_handler(update, _context(repository)))

    assert len(inline_query.answers) == 1
    results = inline_query.answers[0]
    assert len(results) == 1
    assert "ошибка" in results[0].title.lower() or "error" in results[0].title.lower()


def test_inline_handler_caps_results_at_50(tmp_path: Path, monkeypatch: Any) -> None:
    db_path = tmp_path / "search.db"

    # Return 100 mock results
    mock_results = tuple(
        SearchResult(
            source_path=f"book_{i}.pdf",
            chunk_id=i,
            chunk_no=i,
            display=f"Book {i}",
            excerpt=f"Excerpt {i}",
        )
        for i in range(100)
    )

    async def mock_search(**kwargs: Any) -> SearchResponse:
        del kwargs
        return SearchResponse(results=mock_results)

    monkeypatch.setattr("librar.bot.handlers.inline.search_hybrid_cli", mock_search)

    with BotRepository(db_path) as repository:
        inline_query = DummyInlineQuery("many results")
        update = SimpleNamespace(
            inline_query=inline_query,
            effective_user=SimpleNamespace(id=123),
        )

        asyncio.run(inline_query_handler(update, _context(repository)))

    assert len(inline_query.answers) == 1
    results = inline_query.answers[0]
    assert len(results) == 50  # Capped at INLINE_MAX_RESULTS


def test_search_page_callback_navigates_pages_and_answers_query(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"

    mock_results = tuple(
        SearchResult(
            source_path=f"book_{i}.pdf",
            chunk_id=i,
            chunk_no=i,
            display=f"Book {i}, Page {i}",
            excerpt=f"Excerpt {i} content " * 20,
        )
        for i in range(10)
    )

    with BotRepository(db_path) as repository:
        ctx = _context(repository, page_size=5)
        ctx.user_data = {
            "search_results": mock_results,
            "search_query": "test query",
            "search_excerpt_size": 100,
        }

        # Navigate to page 1
        callback = DummyCallbackQuery("search_page_1")
        update = SimpleNamespace(callback_query=callback, effective_user=SimpleNamespace(id=123))

        asyncio.run(search_page_callback(update, ctx))

    assert callback.answered is True
    assert len(callback.edited_messages) == 1
    edited = callback.edited_messages[0]
    text = edited["text"]

    # Should show page 1 results (offset 5-9)
    assert "Book 5" in text
    assert "Book 9" in text
    assert "Book 0" not in text  # Page 0

    # Should have both navigation buttons
    assert edited["reply_markup"] is not None
    buttons = edited["reply_markup"].inline_keyboard[0]
    assert any("Предыдущая" in btn.text for btn in buttons)


def test_search_page_callback_handles_expired_results(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"

    with BotRepository(db_path) as repository:
        ctx = _context(repository)
        ctx.user_data = {}  # No stored results

        callback = DummyCallbackQuery("search_page_1")
        update = SimpleNamespace(callback_query=callback, effective_user=SimpleNamespace(id=123))

        asyncio.run(search_page_callback(update, ctx))

    assert callback.answered is True
    assert len(callback.edited_messages) == 1
    text = callback.edited_messages[0]["text"]
    assert "истекли" in text.lower() or "заново" in text.lower()


def test_books_page_callback_navigates_and_always_answers(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"

    with BotRepository(db_path) as repository:
        # Insert books
        conn = repository.connection
        for i in range(10):
            conn.execute(
                "INSERT INTO books (source_path, title, author, format) VALUES (?, ?, ?, ?)",
                (f"book_{i}.pdf", f"Title {i}", f"Author {i}", "pdf"),
            )
        conn.commit()

        ctx = _context(repository, page_size=5)
        ctx.user_data = {"books_page_offset": 0}

        # Navigate to page 1
        callback = DummyCallbackQuery("books_page_1")
        update = SimpleNamespace(callback_query=callback, effective_user=SimpleNamespace(id=123))

        asyncio.run(books_page_callback(update, ctx))

    assert callback.answered is True
    assert len(callback.edited_messages) == 1
    edited = callback.edited_messages[0]
    text = edited["text"]

    # Should show page 1 books (offset 5-9)
    assert "Title 5" in text
    assert "Title 9" in text
    assert "Title 0" not in text  # Page 0

    # Should have both navigation buttons
    assert edited["reply_markup"] is not None
    buttons = edited["reply_markup"].inline_keyboard[0]
    assert any("Предыдущая" in btn.text for btn in buttons)

    # Should update offset in user_data
    assert ctx.user_data["books_page_offset"] == 5


def test_books_page_callback_handles_invalid_page(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"

    with BotRepository(db_path) as repository:
        # Insert 5 books
        conn = repository.connection
        for i in range(5):
            conn.execute(
                "INSERT INTO books (source_path, title, format) VALUES (?, ?, ?)",
                (f"book_{i}.pdf", f"Title {i}", "pdf"),
            )
        conn.commit()

        ctx = _context(repository, page_size=5)

        # Try to navigate to page 10 (out of bounds)
        callback = DummyCallbackQuery("books_page_10")
        update = SimpleNamespace(callback_query=callback, effective_user=SimpleNamespace(id=123))

        asyncio.run(books_page_callback(update, ctx))

    assert callback.answered is True
    assert len(callback.edited_messages) == 1
    text = callback.edited_messages[0]["text"]
    assert "не существует" in text.lower()


def test_inline_handler_handles_missing_configuration(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"

    with BotRepository(db_path) as repository:
        inline_query = DummyInlineQuery("test query")
        update = SimpleNamespace(
            inline_query=inline_query,
            effective_user=SimpleNamespace(id=123),
        )
        ctx = _context(repository)
        del ctx.bot_data["index_path"]

        asyncio.run(inline_query_handler(update, ctx))

    assert len(inline_query.answers) == 1
    results = inline_query.answers[0]
    assert len(results) == 1
    assert "недоступ" in results[0].title.lower()
