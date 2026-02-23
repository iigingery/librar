from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

from librar.bot.search_service import INSUFFICIENT_DATA_ANSWER, SearchResult, answer_question, search_hybrid_cli


class _DummyProc:
    def __init__(self, *, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0, delay_seconds: float = 0.0) -> None:
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode
        self._delay_seconds = delay_seconds
        self.killed = False

    async def communicate(self) -> tuple[bytes, bytes]:
        if self._delay_seconds:
            await asyncio.sleep(self._delay_seconds)
        return self._stdout, self._stderr

    def kill(self) -> None:
        self.killed = True


class _DummyGenerator:
    def __init__(self, response_text: str = "Ответ [1]", *, fail: bool = False) -> None:
        self.response_text = response_text
        self.fail = fail
        self.calls: list[dict[str, Any]] = []

    def generate_text(self, *, prompt: str, model: str, temperature: float, max_tokens: int) -> str:
        self.calls.append(
            {
                "prompt": prompt,
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        if self.fail:
            raise RuntimeError("generation failed")
        return self.response_text


def test_search_hybrid_cli_parses_json_and_dedupes_paths(monkeypatch) -> None:
    payload = {
        "results": [
            {
                "source_path": "books\\mystic.fb2",
                "chunk_id": 7,
                "chunk_no": 0,
                "display": "Mystic — page 1 — first",
                "excerpt": "first",
                "title": "Mystic",
            },
            {
                "source_path": "C:\\Users\\USER\\Desktop\\librar\\books\\mystic.fb2",
                "chunk_id": 7,
                "chunk_no": 0,
                "display": "Mystic duplicate — page 1 — first",
                "excerpt": "first",
                "title": "Mystic",
            },
            {
                "source_path": "books\\mystic.fb2",
                "chunk_id": 8,
                "chunk_no": 1,
                "display": "Mystic — page 2 — second",
                "excerpt": "second",
                "title": "Mystic",
            },
        ]
    }

    proc = _DummyProc(stdout=json.dumps(payload).encode("utf-8"), returncode=0)

    async def _fake_create_subprocess_exec(*args, **kwargs):
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)

    response = asyncio.run(search_hybrid_cli(query="mystic", timeout_seconds=1.0))

    assert response.error is None
    assert response.timed_out is False
    assert len(response.results) == 3
    assert response.results[0].chunk_id == 7
    assert response.results[0].display == "Mystic — page 1 — first"
    assert response.results[2].chunk_id == 8


def test_search_hybrid_cli_timeout_returns_safe_empty_response(monkeypatch) -> None:
    proc = _DummyProc(returncode=0, delay_seconds=0.1)

    async def _fake_create_subprocess_exec(*args, **kwargs):
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)

    response = asyncio.run(search_hybrid_cli(query="slow", timeout_seconds=0.01))

    assert response.results == ()
    assert response.timed_out is True
    assert response.error == "Search timed out"
    assert proc.killed is True


def test_answer_question_uses_top_k_and_generation(monkeypatch) -> None:
    search_results = tuple(
        SearchResult(
            source_path=f"books/book_{i}.pdf",
            chunk_id=i,
            chunk_no=i,
            display=f"Book {i}",
            excerpt=f"Фрагмент {i}",
            title=f"Книга {i}",
            author=f"Автор {i}",
            page=i + 1,
            hybrid_score=0.8 - i * 0.05,
        )
        for i in range(4)
    )

    async def _fake_search_hybrid_cli(**kwargs: Any):
        del kwargs
        return SimpleNamespace(results=search_results, error=None, timed_out=False)

    monkeypatch.setattr("librar.bot.search_service.search_hybrid_cli", _fake_search_hybrid_cli)
    monkeypatch.setattr(
        "librar.bot.search_service.SemanticSettings.from_env",
        lambda: SimpleNamespace(api_key="k", model="embed-model", base_url="https://openrouter.ai/api/v1"),
    )

    generator = _DummyGenerator("Подтвержденный ответ [1]")

    result = asyncio.run(
        answer_question(
            query="Кто автор?",
            db_path=".librar-search.db",
            index_path=".librar-semantic.faiss",
            top_k=2,
            max_context_chars=500,
            chat_model="openai/gpt-4o-mini",
            generator=generator,
        )
    )

    assert result.is_confirmed is True
    assert result.answer == "Подтвержденный ответ [1]"
    assert len(result.sources) == 2
    assert "Системная инструкция" in generator.calls[0]["prompt"]
    assert "[1]" in generator.calls[0]["prompt"]
    assert "[3]" not in generator.calls[0]["prompt"]


def test_answer_question_falls_back_when_generation_fails(monkeypatch) -> None:
    search_results = (
        SearchResult(
            source_path="books/book.pdf",
            chunk_id=1,
            chunk_no=4,
            display="Book",
            excerpt="Автор книги — Иван Иванов.",
            title="Тестовая книга",
            author="Иван Иванов",
            page=12,
            hybrid_score=0.8,
        ),
        SearchResult(
            source_path="books/book.pdf",
            chunk_id=2,
            chunk_no=5,
            display="Book",
            excerpt="Дополнительный подтверждающий фрагмент.",
            title="Тестовая книга",
            author="Иван Иванов",
            page=13,
            hybrid_score=0.75,
        ),
    )

    async def _fake_search_hybrid_cli(**kwargs: Any):
        del kwargs
        return SimpleNamespace(results=search_results, error=None, timed_out=False)

    monkeypatch.setattr("librar.bot.search_service.search_hybrid_cli", _fake_search_hybrid_cli)
    monkeypatch.setattr(
        "librar.bot.search_service.SemanticSettings.from_env",
        lambda: SimpleNamespace(api_key="k", model="embed-model", base_url="https://openrouter.ai/api/v1"),
    )

    result = asyncio.run(
        answer_question(
            query="Кто автор?",
            db_path=".librar-search.db",
            index_path=".librar-semantic.faiss",
            top_k=2,
            max_context_chars=500,
            chat_model="openai/gpt-4o-mini",
            generator=_DummyGenerator(fail=True),
        )
    )

    assert result.is_confirmed is True
    assert "Иван Иванов" in result.answer
    assert result.sources[0].location == "стр. 12"


def test_answer_question_returns_template_when_relevance_is_insufficient(monkeypatch) -> None:
    search_results = (
        SearchResult(
            source_path="books/book.pdf",
            chunk_id=1,
            chunk_no=0,
            display="Book",
            excerpt="Нерелевантный отрывок.",
            title="Тестовая книга",
            author="Автор",
            page=1,
            hybrid_score=0.15,
        ),
        SearchResult(
            source_path="books/book.pdf",
            chunk_id=2,
            chunk_no=1,
            display="Book",
            excerpt="Ещё один нерелевантный отрывок.",
            title="Тестовая книга",
            author="Автор",
            page=2,
            hybrid_score=0.2,
        ),
    )

    async def _fake_search_hybrid_cli(**kwargs: Any):
        del kwargs
        return SimpleNamespace(results=search_results, error=None, timed_out=False)

    monkeypatch.setattr("librar.bot.search_service.search_hybrid_cli", _fake_search_hybrid_cli)

    result = asyncio.run(
        answer_question(
            query="Сложный вопрос",
            db_path=".librar-search.db",
            index_path=".librar-semantic.faiss",
            top_k=2,
            max_context_chars=500,
            chat_model="openai/gpt-4o-mini",
            generator=_DummyGenerator(),
        )
    )

    assert result.is_confirmed is False
    assert result.sources == ()
    assert result.answer == INSUFFICIENT_DATA_ANSWER


def test_answer_question_returns_template_when_too_few_scored_chunks(monkeypatch) -> None:
    search_results = (
        SearchResult(
            source_path="books/book.pdf",
            chunk_id=1,
            chunk_no=0,
            display="Book",
            excerpt="Один фрагмент.",
            title="Тестовая книга",
            author="Автор",
            page=1,
            hybrid_score=0.95,
        ),
    )

    async def _fake_search_hybrid_cli(**kwargs: Any):
        del kwargs
        return SimpleNamespace(results=search_results, error=None, timed_out=False)

    monkeypatch.setattr("librar.bot.search_service.search_hybrid_cli", _fake_search_hybrid_cli)

    result = asyncio.run(
        answer_question(
            query="Сложный вопрос",
            db_path=".librar-search.db",
            index_path=".librar-semantic.faiss",
            top_k=2,
            max_context_chars=500,
            chat_model="openai/gpt-4o-mini",
            generator=_DummyGenerator(),
        )
    )

    assert result.is_confirmed is False
    assert result.sources == ()
    assert result.answer == INSUFFICIENT_DATA_ANSWER
