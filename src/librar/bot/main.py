"""Production Telegram bot entrypoint with handler registration and polling."""

from __future__ import annotations

import asyncio
import logging
import sys

from telegram.ext import Application

from librar.bot.config import BotSettings
from librar.bot.handlers.callbacks import build_callback_handlers
from librar.bot.handlers.commands import build_command_handlers
from librar.bot.handlers.inline import build_inline_handler
from librar.bot.handlers.settings import build_settings_conversation_handler
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

    # 4. Callback query handlers (pagination)
    for handler in build_callback_handlers():
        application.add_handler(handler)

    logger.info("Registered all handlers: commands, inline, callbacks, settings")
    return application


async def run_bot(settings: BotSettings) -> None:
    """Run bot with polling and graceful shutdown."""
    application = build_application(settings)

    # Initialize application
    await application.initialize()
    logger.info("Bot initialized. Starting polling...")

    # Start polling with explicit allowed updates
    await application.start()
    await application.updater.start_polling(
        allowed_updates=["message", "inline_query", "callback_query"]
    )

    logger.info("Bot polling started. Press Ctrl+C to stop.")

    # Wait for stop signal
    try:
        # Keep running until interrupted
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Received stop signal. Shutting down...")

    # Graceful shutdown
    await application.updater.stop()
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
