from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from librar.automation import ingestion_service
from librar.automation.ingestion_service import run_ingestion_pipeline
from librar.automation.watcher import BookFolderWatcher


class _DummyProc:
    def __init__(
        self,
        *,
        stdout: bytes = b"",
        stderr: bytes = b"",
        returncode: int = 0,
        delay_seconds: float = 0.0,
    ) -> None:
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode
        self._delay_seconds = delay_seconds
        self.killed = False

    async def communicate(self) -> tuple[bytes, bytes]:
        if self._delay_seconds > 0:
            await asyncio.sleep(self._delay_seconds)
        return self._stdout, self._stderr

    def kill(self) -> None:
        self.killed = True


def _ingest_payload(*, is_duplicate: bool = False) -> bytes:
    payload = {
        "path": "books/new-book.pdf",
        "processed": 1,
        "results": [
            {
                "source_path": "books/new-book.pdf",
                "title": "New Book",
                "author": "Someone",
                "format": "pdf",
                "chunk_count": 12,
                "is_duplicate": is_duplicate,
            }
        ],
        "errors": [],
    }
    return json.dumps(payload).encode("utf-8")


@pytest.mark.asyncio
async def test_pipeline_success_calls_ingest_and_both_indexers_sequentially() -> None:
    calls: list[tuple[Any, ...]] = []
    procs = [
        _DummyProc(stdout=_ingest_payload(is_duplicate=False)),
        _DummyProc(stdout=b"{}"),
        _DummyProc(stdout=b"{}"),
    ]

    async def _fake_exec(*args, **kwargs):
        calls.append(args)
        return procs.pop(0)

    with patch("librar.automation.ingestion_service.asyncio.create_subprocess_exec", new=AsyncMock(side_effect=_fake_exec)):
        result = await run_ingestion_pipeline(
            Path("books/new-book.pdf"),
            db_path=".librar-search.db",
            index_path=".librar-semantic.faiss",
            cache_file=".librar-ingestion-cache.json",
        )

    assert result.success is True
    assert result.is_duplicate is False
    assert len(calls) == 3

    ingest_call = calls[0]
    assert "librar.cli.ingest_books" in ingest_call
    assert "--path" in ingest_call
    ingest_path = Path(ingest_call[ingest_call.index("--path") + 1])
    assert ingest_path.name == "new-book.pdf"
    assert "--cache-file" in ingest_call
    assert ".librar-ingestion-cache.json" in ingest_call

    index_call = calls[1]
    assert "librar.cli.index_books" in index_call
    assert "--db-path" in index_call
    assert ".librar-search.db" in index_call

    semantic_call = calls[2]
    assert "librar.cli.index_semantic" in semantic_call
    assert "--db-path" in semantic_call
    assert ".librar-search.db" in semantic_call
    assert "--index-path" in semantic_call
    assert ".librar-semantic.faiss" in semantic_call


@pytest.mark.asyncio
async def test_pipeline_duplicate_skips_indexing_commands() -> None:
    calls: list[tuple[Any, ...]] = []
    procs = [_DummyProc(stdout=_ingest_payload(is_duplicate=True))]

    async def _fake_exec(*args, **kwargs):
        calls.append(args)
        return procs.pop(0)

    with patch("librar.automation.ingestion_service.asyncio.create_subprocess_exec", new=AsyncMock(side_effect=_fake_exec)):
        result = await run_ingestion_pipeline(
            Path("books/new-book.pdf"),
            db_path=".librar-search.db",
            index_path=".librar-semantic.faiss",
            cache_file=".librar-ingestion-cache.json",
        )

    assert result.success is True
    assert result.is_duplicate is True
    assert len(calls) == 1
    assert "librar.cli.ingest_books" in calls[0]


@pytest.mark.asyncio
async def test_pipeline_failure_returns_error_message() -> None:
    async def _fake_exec(*args, **kwargs):
        return _DummyProc(stderr=b"ingest failed", returncode=1)

    with patch("librar.automation.ingestion_service.asyncio.create_subprocess_exec", new=AsyncMock(side_effect=_fake_exec)):
        result = await run_ingestion_pipeline(
            Path("books/new-book.pdf"),
            db_path=".librar-search.db",
            index_path=".librar-semantic.faiss",
            cache_file=".librar-ingestion-cache.json",
        )

    assert result.success is False
    assert result.error is not None
    assert "ingest failed" in result.error


@pytest.mark.asyncio
async def test_pipeline_timeout_returns_error() -> None:
    original_run_cli_command = ingestion_service._run_cli_command

    async def _short_timeout_run_cli_command(*args: str, timeout_seconds: float = 60.0):
        return await original_run_cli_command(*args, timeout_seconds=0.01)

    async def _fake_exec(*args, **kwargs):
        return _DummyProc(delay_seconds=0.2)

    with patch("librar.automation.ingestion_service._run_cli_command", new=_short_timeout_run_cli_command):
        with patch("librar.automation.ingestion_service.asyncio.create_subprocess_exec", new=AsyncMock(side_effect=_fake_exec)):
            result = await run_ingestion_pipeline(
                Path("books/new-book.pdf"),
                db_path=".librar-search.db",
                index_path=".librar-semantic.faiss",
                cache_file=".librar-ingestion-cache.json",
            )

    assert result.success is False
    assert result.error is not None
    assert "Timed out" in result.error


@pytest.mark.asyncio
async def test_watcher_lifecycle_detects_file_and_stops_cleanly(tmp_path: Path) -> None:
    seen: list[Path] = []
    event = asyncio.Event()

    async def _callback(path: Path) -> None:
        seen.append(path)
        event.set()

    watcher = BookFolderWatcher(tmp_path, _callback, debounce_seconds=0.1)
    await watcher.start()

    test_file = tmp_path / "arrival.pdf"
    test_file.write_bytes(b"")

    await asyncio.wait_for(event.wait(), timeout=5.0)
    assert seen
    assert seen[0].name == "arrival.pdf"

    observer = watcher._observer
    assert observer is not None
    assert observer.is_alive()

    watcher.stop()

    assert not observer.is_alive()


@pytest.mark.asyncio
async def test_watcher_debounce_emits_single_callback_for_rapid_rewrites(tmp_path: Path) -> None:
    calls: list[Path] = []

    async def _callback(path: Path) -> None:
        calls.append(path)

    watcher = BookFolderWatcher(tmp_path, _callback, debounce_seconds=0.5)
    await watcher.start()

    test_file = tmp_path / "rapid.pdf"
    for i in range(3):
        test_file.write_text(f"version {i}", encoding="utf-8")
        await asyncio.sleep(0.1)
        if test_file.exists():
            test_file.unlink()

    test_file.write_text("final", encoding="utf-8")
    await asyncio.sleep(1.0)
    watcher.stop()

    assert len(calls) == 1
    assert calls[0].name == "rapid.pdf"
