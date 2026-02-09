"""Production Telegram bot entrypoint with handler registration and polling."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
import sys

from dotenv import load_dotenv
from telegram.ext import Application

load_dotenv()

from librar.bot.config import BotSettings
from librar.automation.ingestion_service import run_ingestion_pipeline
from librar.automation.watcher import BookFolderWatcher
from librar.bot.handlers.callbacks import build_callback_handlers
from librar.bot.handlers.commands import build_command_handlers
from librar.bot.handlers.inline import build_inline_handler
from librar.bot.handlers.settings import build_settings_conversation_handler
from librar.bot.handlers.upload import build_upload_handler
from librar.bot.repository import BotRepository


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def build_application(settings: BotSettings) -> Application:
    """Build PTB Application with all handlers registered."""
    # Initialize shared bot repository
    repository = BotRepository(settings.db_path)

    # Build application with token
    application = Application.builder().token(settings.token).build()

    # Store shared dependencies in bot_data
    application.bot_data["repository"] = repository
    application.bot_data["db_path"] = str(settings.db_path)
    application.bot_data["index_path"] = str(settings.index_path)
    application.bot_data["inline_timeout_seconds"] = settings.inline_timeout_seconds
    application.bot_data["inline_result_limit"] = settings.inline_result_limit
    application.bot_data["command_result_limit"] = settings.command_result_limit
    application.bot_data["page_size"] = settings.page_size

    # Register all handlers in correct order
    # 1. Settings conversation (highest priority for /settings command)
    application.add_handler(build_settings_conversation_handler())

    # 2. Command handlers (/start, /help, /search, /books)
    for handler in build_command_handlers():
        application.add_handler(handler)

    # 3. Inline query handler (@botname queries)
    application.add_handler(build_inline_handler())

    # 4. Document upload handler (book file uploads)
    application.add_handler(build_upload_handler())

    # 5. Callback query handlers (pagination)
    for handler in build_callback_handlers():
        application.add_handler(handler)

    logger.info("Registered all handlers: settings, commands, inline, upload, callbacks")
    return application


async def run_bot(settings: BotSettings) -> None:
    """Run bot with polling and graceful shutdown."""
    application = build_application(settings)
    watcher: BookFolderWatcher | None = None

    # Initialize application
    await application.initialize()
    logger.info("Bot initialized. Starting polling...")

    # Start polling with explicit allowed updates
    await application.start()
    updater = application.updater
    if updater is None:
        raise RuntimeError("Bot updater is not initialized")

    await updater.start_polling(
        allowed_updates=["message", "inline_query", "callback_query"]
    )

    watch_dir = Path(os.environ.get("LIBRAR_WATCH_DIR", "books"))

    async def _on_new_book(file_path: Path) -> None:
        logger.info("Watcher detected new book: %s", file_path)
        result = await run_ingestion_pipeline(
            file_path,
            db_path=str(settings.db_path),
            index_path=str(settings.index_path),
            cache_file=".librar-ingestion-cache.json",
        )
        if result.is_duplicate:
            logger.info("Skipped duplicate from watcher: %s", file_path.name)
            return
        if result.success:
            logger.info(
                "Ingested from watcher: %s by %s (%s chunks)",
                result.title,
                result.author,
                result.chunk_count,
            )
            return
        logger.error("Watcher ingestion failed for %s: %s", file_path.name, result.error)

    if watch_dir.exists() and watch_dir.is_dir():
        watcher = BookFolderWatcher(watch_dir=watch_dir, callback=_on_new_book)
        await watcher.start()
        logger.info("Folder watcher started for %s", watch_dir)
    else:
        logger.warning("Watch directory does not exist, watcher disabled: %s", watch_dir)

    logger.info("Bot polling started. Press Ctrl+C to stop.")

    # Wait for stop signal
    try:
        # Keep running until interrupted
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Received stop signal. Shutting down...")

    # Graceful shutdown
    await updater.stop()

    if watcher is not None:
        try:
            watcher.stop()
            logger.info("Folder watcher stopped cleanly.")
        except Exception:
            logger.exception("Failed to stop folder watcher cleanly")

    await application.stop()
    await application.shutdown()

    # Close repository connection
    repository = application.bot_data.get("repository")
    if isinstance(repository, BotRepository):
        repository.close()

    logger.info("Bot stopped cleanly.")


def main() -> None:
    """Main entrypoint for Telegram bot."""
    try:
        settings = BotSettings.from_env()
        logger.info(
            f"Loaded bot config: db={settings.db_path}, "
            f"index={settings.index_path}, "
            f"inline_timeout={settings.inline_timeout_seconds}s"
        )
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    try:
        asyncio.run(run_bot(settings))
    except KeyboardInterrupt:
        logger.info("Bot interrupted by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()
