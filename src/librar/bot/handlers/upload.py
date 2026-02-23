"""Telegram document upload handler for book ingestion."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from telegram import Update
from telegram.error import NetworkError, TimedOut
from telegram.ext import ContextTypes, MessageHandler, filters

from librar.automation.ingestion_service import run_ingestion_pipeline


logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 50 * 1024 * 1024
SUPPORTED_EXTENSIONS = {".pdf", ".epub", ".fb2", ".txt"}
def _is_supported_extension(file_name: str) -> bool:
    return Path(file_name).suffix.lower() in SUPPORTED_EXTENSIONS


async def handle_book_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Validate, download, and ingest a user-uploaded document."""
    message = update.message
    if message is None or message.document is None:
        return

    document = message.document

    if document.file_size is not None and document.file_size > MAX_FILE_SIZE:
        await message.reply_text("Файл слишком большой. Максимальный размер: 50 МБ")
        return

    original_name = document.file_name or ""
    safe_name = Path(original_name).name
    if not _is_supported_extension(safe_name):
        await message.reply_text("Неподдерживаемый формат. Поддерживаются: PDF, EPUB, FB2, TXT")
        return

    status_msg = await message.reply_text("Загружаю и обрабатываю книгу...")
    books_path = Path(str(context.bot_data.get("books_path", "books")))
    target_path = books_path / safe_name
    target_path.parent.mkdir(parents=True, exist_ok=True)

    for attempt in range(2):
        try:
            if attempt == 1:
                logger.warning("Retrying upload download after transient network failure: %s", safe_name)

            telegram_file = await document.get_file()
            await telegram_file.download_to_drive(target_path)

            result = await run_ingestion_pipeline(
                target_path,
                db_path=str(context.bot_data["db_path"]),
                index_path=str(context.bot_data["index_path"]),
                books_path=str(books_path),
                cache_file=".librar-ingestion-cache.json",
            )

            if result.is_duplicate:
                await status_msg.edit_text("Эта книга уже есть в библиотеке.")
                return

            if result.success:
                await status_msg.edit_text(
                    "\n".join(
                        [
                            "Книга добавлена!",
                            "",
                            f"Название: {result.title or 'Без названия'}",
                            f"Автор: {result.author or 'Неизвестный автор'}",
                            f"Формат: {result.format_name or '-'}",
                            f"Отрывков: {result.chunk_count}",
                        ]
                    )
                )
                return

            await status_msg.edit_text(f"Ошибка обработки: {result.error or 'Неизвестная ошибка'}")
            return
        except (NetworkError, TimedOut) as error:
            logger.warning("Network error during upload handling (attempt %s/2): %s", attempt + 1, error)
            if attempt == 0:
                await asyncio.sleep(2)
                continue
            await status_msg.edit_text("Ошибка сети при загрузке файла. Попробуйте снова позже.")
            return
        except Exception:
            logger.exception("Unexpected error while handling upload: %s", safe_name)
            await status_msg.edit_text("Не удалось обработать файл. Попробуйте снова позже.")
            return


def build_upload_handler() -> MessageHandler:
    """Build document upload message handler."""
    upload_filter = (
        filters.Document.PDF
        | filters.Document.TXT
        | filters.Document.FileExtension("epub")
        | filters.Document.FileExtension("fb2")
    )
    return MessageHandler(upload_filter, handle_book_upload)
