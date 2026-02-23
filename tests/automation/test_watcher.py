from __future__ import annotations

import asyncio
import json
from pathlib import Path

from watchdog.events import FileCreatedEvent

from librar.automation.ingestion_service import IngestionPipelineResult, run_ingestion_pipeline
from librar.automation.watcher import BookFolderWatcher, DebouncedBookHandler


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


def test_debounced_handler_emits_only_once_for_same_path() -> None:
    async def _scenario() -> None:
        queue: asyncio.Queue[Path] = asyncio.Queue()
        handler = DebouncedBookHandler(
            loop=asyncio.get_running_loop(),
            queue=queue,
            debounce_seconds=0.2,
        )

        event = FileCreatedEvent("books/new-book.pdf")
        for _ in range(5):
            handler.on_created(event)
            await asyncio.sleep(0.05)

        emitted = await asyncio.wait_for(queue.get(), timeout=1.0)
        await asyncio.sleep(0.3)

        assert emitted.name == "new-book.pdf"
        assert queue.empty()
        handler.close()

    asyncio.run(_scenario())


def test_debounced_handler_pattern_filtering() -> None:
    async def _scenario() -> None:
        queue: asyncio.Queue[Path] = asyncio.Queue()
        handler = DebouncedBookHandler(
            loop=asyncio.get_running_loop(),
            queue=queue,
            debounce_seconds=0.05,
        )

        handler.dispatch(FileCreatedEvent("books/ok.pdf"))
        handler.dispatch(FileCreatedEvent("books/nope.jpg"))
        handler.dispatch(FileCreatedEvent("books/temp.tmp"))

        emitted = await asyncio.wait_for(queue.get(), timeout=1.0)
        await asyncio.sleep(0.1)

        assert emitted.name == "ok.pdf"
        assert queue.empty()
        handler.close()

    asyncio.run(_scenario())


def test_book_folder_watcher_start_stop_lifecycle(tmp_path: Path) -> None:
    async def _scenario() -> None:
        received: list[Path] = []

        async def _callback(path: Path) -> None:
            received.append(path)

        watcher = BookFolderWatcher(tmp_path, _callback, debounce_seconds=0.05)
        await watcher.start()

        assert watcher._observer is not None
        assert watcher._observer.is_alive()

        watcher.stop()

        assert watcher._observer is None
        assert watcher._consumer_task is None
        assert received == []

    asyncio.run(_scenario())


def test_ingestion_pipeline_result_dataclass_construction() -> None:
    result = IngestionPipelineResult(
        success=True,
        title="Test",
        author="Author",
        format_name="pdf",
        chunk_count=10,
        is_duplicate=False,
        error=None,
    )

    assert result.success is True
    assert result.title == "Test"
    assert result.chunk_count == 10


def test_run_ingestion_pipeline_success(monkeypatch) -> None:
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
                "is_duplicate": False,
            }
        ],
        "errors": [],
    }

    procs = [
        _DummyProc(stdout=json.dumps(payload).encode("utf-8"), returncode=0),
        _DummyProc(stdout=b"{}", returncode=0),
        _DummyProc(stdout=b"{}", returncode=0),
    ]
    calls: list[tuple[object, ...]] = []

    async def _fake_create_subprocess_exec(*args, **kwargs):
        calls.append(args)
        return procs.pop(0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)

    result = asyncio.run(
        run_ingestion_pipeline(
            Path("books/new-book.pdf"),
            db_path=".librar-search.db",
            index_path=".librar-semantic.faiss",
            books_path="books",
            cache_file=".librar-ingestion-cache.json",
        )
    )

    assert result.success is True
    assert result.title == "New Book"
    assert result.author == "Someone"
    assert result.format_name == "pdf"
    assert result.chunk_count == 12
    assert result.is_duplicate is False
    assert len(calls) == 3
    assert "librar.cli.ingest_books" in calls[0]
    assert "librar.cli.index_books" in calls[1]
    assert "librar.cli.index_semantic" in calls[2]


def test_run_ingestion_pipeline_failure_returns_error(monkeypatch) -> None:
    procs = [_DummyProc(stderr=b"ingest failed", returncode=1)]

    async def _fake_create_subprocess_exec(*args, **kwargs):
        return procs.pop(0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)

    result = asyncio.run(
        run_ingestion_pipeline(
            Path("books/new-book.pdf"),
            db_path=".librar-search.db",
            index_path=".librar-semantic.faiss",
            books_path="books",
            cache_file=".librar-ingestion-cache.json",
        )
    )

    assert result.success is False
    assert result.error is not None
    assert "ingest failed" in result.error
