"""Debounced folder watcher with asyncio queue bridge."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
import threading
from typing import Awaitable, Callable

from watchdog.events import PatternMatchingEventHandler
from watchdog.observers import Observer


LOGGER = logging.getLogger(__name__)


class DebouncedBookHandler(PatternMatchingEventHandler):
    def __init__(
        self,
        *,
        loop: asyncio.AbstractEventLoop,
        queue: asyncio.Queue[Path],
        debounce_seconds: float = 2.0,
    ) -> None:
        super().__init__(
            patterns=["*.pdf", "*.epub", "*.fb2", "*.txt"],
            ignore_patterns=["*.tmp", "*.part", ".*", "*~"],
            ignore_directories=True,
            case_sensitive=False,
        )
        self._loop = loop
        self._queue = queue
        self._debounce_seconds = debounce_seconds
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def _emit_path(self, raw_path: str) -> None:
        path = Path(raw_path)
        self._loop.call_soon_threadsafe(self._queue.put_nowait, path)

    def on_created(self, event) -> None:  # type: ignore[override]
        path = event.src_path
        with self._lock:
            existing = self._timers.pop(path, None)
            if existing is not None:
                existing.cancel()

            timer = threading.Timer(self._debounce_seconds, self._emit_path, args=(path,))
            timer.daemon = True
            self._timers[path] = timer
            timer.start()

    def close(self) -> None:
        with self._lock:
            timers = list(self._timers.values())
            self._timers.clear()
        for timer in timers:
            timer.cancel()


class BookFolderWatcher:
    def __init__(
        self,
        watch_dir: str | Path,
        callback: Callable[[Path], Awaitable[None]],
        debounce_seconds: float = 2.0,
    ) -> None:
        self._watch_dir = Path(watch_dir)
        self._callback = callback
        self._debounce_seconds = debounce_seconds
        self._queue: asyncio.Queue[Path] | None = None
        self._handler: DebouncedBookHandler | None = None
        self._observer: Observer | None = None
        self._consumer_task: asyncio.Task[None] | None = None

    async def _consume(self) -> None:
        assert self._queue is not None
        while True:
            path = await self._queue.get()
            try:
                await self._callback(path)
            except Exception:  # pragma: no cover
                LOGGER.exception("Watcher callback failed for %s", path)
            finally:
                self._queue.task_done()

    async def start(self) -> None:
        if self._observer is not None:
            return
        if not self._watch_dir.exists() or not self._watch_dir.is_dir():
            raise ValueError(f"Watch directory does not exist or is not a directory: {self._watch_dir}")

        loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue()
        self._handler = DebouncedBookHandler(
            loop=loop,
            queue=self._queue,
            debounce_seconds=self._debounce_seconds,
        )

        observer = Observer()
        observer.schedule(self._handler, str(self._watch_dir), recursive=False)
        observer.start()
        self._observer = observer
        self._consumer_task = asyncio.create_task(self._consume())

    def stop(self) -> None:
        observer = self._observer
        if observer is not None:
            observer.stop()
            observer.join(timeout=5.0)
            self._observer = None

        if self._handler is not None:
            self._handler.close()
            self._handler = None

        if self._consumer_task is not None:
            self._consumer_task.cancel()
            self._consumer_task = None
