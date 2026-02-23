"""Tests for command handlers (/start, /help, /search, /ask, /books)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from librar.bot.handlers.commands import (
    ask_command,
    books_command,
    help_command,
    reset_context_command,
    search_command,
    start_command,
)
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
            "openrouter_chat_model": "openai/gpt-4o-mini",
            "rag_top_k": 3,
            "rag_max_context_chars": 2000,
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
    assert "/ask" in reply_text
    assert "/books" in reply_text


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
    assert "/ask" in reply_text
    assert "/settings" in reply_text


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

    assert "Book 0" in reply_text
    assert "Book 4" in reply_text
    assert "Book 6" not in reply_text
    assert reply["reply_markup"] is not None
    assert "search_results" in ctx.user_data


def test_ask_command_calls_answer_question_and_formats_sources(tmp_path: Path, monkeypatch: Any) -> None:
    db_path = tmp_path / "search.db"

    async def mock_answer_question(**kwargs: Any) -> Any:
        del kwargs
        return SimpleNamespace(
            answer="Подтвержденный ответ [1]",
            is_confirmed=True,
            sources=(
                SimpleNamespace(
                    title="Книга",
                    author="Автор",
                    source_path="books/book.pdf",
                    location="стр. 10",
                ),
            ),
        )

    monkeypatch.setattr("librar.bot.handlers.commands.answer_question", mock_answer_question)

    with BotRepository(db_path) as repository:
        message = DummyMessage()
        update = SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=123),
            effective_chat=SimpleNamespace(id=777),
        )
        ctx = _context(repository)
        ctx.args = ["Кто", "автор?"]

        asyncio.run(ask_command(update, ctx))

    assert len(message.replies) == 1
    reply_text = message.replies[0]["text"]
    assert "Подтверждённый ответ" in reply_text
    assert "Подтвержденный ответ [1]" in reply_text
    assert "Источники" in reply_text
    assert "стр. 10" in reply_text


def test_reset_context_command_clears_saved_dialog_history(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"

    with BotRepository(db_path) as repository:
        repository.save_dialog_message(chat_id=777, user_id=123, role="user", content="Привет")
        repository.save_dialog_message(chat_id=777, user_id=123, role="assistant", content="Здравствуйте")

        message = DummyMessage()
        update = SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=123),
            effective_chat=SimpleNamespace(id=777),
        )

        asyncio.run(reset_context_command(update, _context(repository)))

        history = repository.get_dialog_history(chat_id=777, user_id=123)

    assert len(message.replies) == 1
    assert "очищена" in message.replies[0]["text"].lower()
    assert history == ()


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


def test_search_command_handles_missing_configuration(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"

    with BotRepository(db_path) as repository:
        message = DummyMessage()
        update = SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=123),
            effective_chat=SimpleNamespace(id=555),
        )
        ctx = _context(repository)
        ctx.args = ["test"]
        del ctx.bot_data["db_path"]

        asyncio.run(search_command(update, ctx))

    assert "временно недоступен" in message.replies[-1]["text"].lower()


def test_ask_command_handles_missing_configuration(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"

    with BotRepository(db_path) as repository:
        message = DummyMessage()
        update = SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=123),
            effective_chat=SimpleNamespace(id=777),
        )
        ctx = _context(repository)
        ctx.args = ["Кто", "автор?"]
        del ctx.bot_data["openrouter_chat_model"]

        asyncio.run(ask_command(update, ctx))

    assert "временно недоступен" in message.replies[-1]["text"].lower()


def test_books_command_handles_missing_configuration(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"

    with BotRepository(db_path) as repository:
        message = DummyMessage()
        update = SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=123),
            effective_chat=SimpleNamespace(id=555),
        )
        ctx = _context(repository)
        del ctx.bot_data["page_size"]

        asyncio.run(books_command(update, ctx))

    assert "временно недоступен" in message.replies[-1]["text"].lower()
