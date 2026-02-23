from __future__ import annotations

import asyncio
import json

from librar.bot.search_service import SearchResult, answer_question, search_hybrid_cli


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
    assert len(response.results) == 2
    assert response.results[0].chunk_id == 7
    assert response.results[0].display == "Mystic — page 1 — first"
    assert response.results[1].chunk_id == 8


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


def test_search_hybrid_cli_nonzero_exit_returns_error(monkeypatch) -> None:
    proc = _DummyProc(stderr=b"boom", returncode=2)

    async def _fake_create_subprocess_exec(*args, **kwargs):
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)

    response = asyncio.run(search_hybrid_cli(query="bad", timeout_seconds=1.0))

    assert response.results == ()
    assert response.error is not None
    assert "exit code 2" in response.error
    assert "boom" in response.error


def test_search_hybrid_cli_malformed_json_returns_error(monkeypatch) -> None:
    proc = _DummyProc(stdout=b"{not-json", returncode=0)

    async def _fake_create_subprocess_exec(*args, **kwargs):
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)

    response = asyncio.run(search_hybrid_cli(query="broken", timeout_seconds=1.0))

    assert response.results == ()
    assert response.error == "Hybrid CLI returned malformed JSON"


def test_answer_question_without_results_is_marked_as_insufficient() -> None:
    result = answer_question(query="Кто автор?", results=())

    assert result.is_confirmed is False
    assert result.sources == ()
    assert "Недостаточно данных" in result.answer


def test_answer_question_builds_sources_from_metadata() -> None:
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
        ),
    )

    result = answer_question(query="Кто автор?", results=search_results)

    assert result.is_confirmed is True
    assert len(result.sources) == 1
    assert result.sources[0].title == "Тестовая книга"
    assert result.sources[0].author == "Иван Иванов"
    assert result.sources[0].source_path == "books/book.pdf"
    assert result.sources[0].location == "стр. 12"
    assert "Отвечай только на основе контекста" in result.prompt
