"""CLI entrypoint for folder-based automatic ingestion."""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from dotenv import load_dotenv

from librar.automation.ingestion_service import run_ingestion_pipeline
from librar.automation.watcher import BookFolderWatcher


load_dotenv()

LOGGER = logging.getLogger(__name__)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Watch a folder and ingest books automatically")
    parser.add_argument("--watch-dir", required=True, help="Directory to watch for new books")
    parser.add_argument("--db-path", default=".librar-search.db", help="SQLite database path")
    parser.add_argument("--index-path", default=".librar-semantic.faiss", help="FAISS index file path")
    parser.add_argument(
        "--cache-file",
        default=".librar-ingestion-cache.json",
        help="Path to ingestion dedupe cache",
    )
    parser.add_argument("--debounce", type=float, default=2.0, help="Debounce delay in seconds")
    return parser.parse_args(argv)


async def _run_watcher(args: argparse.Namespace) -> int:
    watch_dir = Path(args.watch_dir)
    if not watch_dir.exists() or not watch_dir.is_dir():
        LOGGER.error("watch-dir must exist and be a directory: %s", watch_dir)
        return 2

    async def _on_new_file(file_path: Path) -> None:
        LOGGER.info("Detected new file: %s", file_path)
        result = await run_ingestion_pipeline(
            file_path,
            db_path=args.db_path,
            index_path=args.index_path,
            cache_file=args.cache_file,
        )
        if result.success:
            if result.is_duplicate:
                LOGGER.info("Skipped duplicate: %s", file_path.name)
                return
            LOGGER.info(
                "Ingested '%s' by %s (%s, %d chunks)",
                result.title or file_path.name,
                result.author or "unknown author",
                result.format_name or "unknown format",
                result.chunk_count,
            )
            return
        LOGGER.error("Ingestion failed for %s: %s", file_path, result.error or "unknown error")

    watcher = BookFolderWatcher(
        watch_dir=watch_dir,
        callback=_on_new_file,
        debounce_seconds=float(args.debounce),
    )

    await watcher.start()
    LOGGER.info("Watching %s (debounce %.1fs)", watch_dir, float(args.debounce))

    try:
        while True:
            await asyncio.sleep(1.0)
    finally:
        watcher.stop()
        LOGGER.info("Watcher stopped cleanly")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = _parse_args(argv)
    try:
        return asyncio.run(_run_watcher(args))
    except KeyboardInterrupt:
        LOGGER.info("Shutdown requested")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
