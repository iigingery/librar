"""Tests for Telegram upload handler validation and ingestion flow."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from librar.automation.ingestion_service import IngestionPipelineResult
from librar.bot.handlers.upload import handle_book_upload


def _build_update_context(document: Any) -> tuple[SimpleNamespace, SimpleNamespace, SimpleNamespace, Any]:
    status_message = SimpleNamespace(edit_text=AsyncMock())
    message = SimpleNamespace(document=document, reply_text=AsyncMock(return_value=status_message))
    update = SimpleNamespace(message=message)
    context = SimpleNamespace(bot_data={"db_path": "test.db", "index_path": "test.faiss"})
    return update, context, message, status_message


@pytest.mark.asyncio
async def test_upload_rejects_large_file_without_download() -> None:
    document = SimpleNamespace(file_size=60 * 1024 * 1024, file_name="big.pdf", get_file=AsyncMock())
    update, context, message, _ = _build_update_context(document)

    await handle_book_upload(update, context)

    message.reply_text.assert_awaited_once_with("Файл слишком большой. Максимальный размер: 50 МБ")
    document.get_file.assert_not_called()


@pytest.mark.asyncio
async def test_upload_rejects_unsupported_extension() -> None:
    document = SimpleNamespace(file_size=1024, file_name="photo.jpg", get_file=AsyncMock())
    update, context, message, _ = _build_update_context(document)

    await handle_book_upload(update, context)

    message.reply_text.assert_awaited_once_with(
        "Неподдерживаемый формат. Поддерживаются: PDF, EPUB, FB2, TXT"
    )
    document.get_file.assert_not_called()


@pytest.mark.asyncio
async def test_upload_success_flow_shows_book_details(monkeypatch: pytest.MonkeyPatch) -> None:
    downloaded_to: list[Path] = []
    telegram_file = SimpleNamespace(download_to_drive=AsyncMock(side_effect=lambda path: downloaded_to.append(path)))
    document = SimpleNamespace(file_size=10_000, file_name="book.epub", get_file=AsyncMock(return_value=telegram_file))
    update, context, message, status_message = _build_update_context(document)

    async def fake_pipeline(file_path: Path, **kwargs: Any) -> IngestionPipelineResult:
        assert kwargs["db_path"] == "test.db"
        assert kwargs["index_path"] == "test.faiss"
        assert kwargs["cache_file"] == ".librar-ingestion-cache.json"
        assert file_path == Path("books") / "book.epub"
        return IngestionPipelineResult(
            success=True,
            title="Тестовая книга",
            author="Автор",
            format_name="epub",
            chunk_count=42,
            is_duplicate=False,
            error=None,
        )

    monkeypatch.setattr("librar.bot.handlers.upload.run_ingestion_pipeline", fake_pipeline)

    await handle_book_upload(update, context)

    assert message.reply_text.await_count == 1
    message.reply_text.assert_awaited_with("Загружаю и обрабатываю книгу...")
    document.get_file.assert_awaited_once()
    telegram_file.download_to_drive.assert_awaited_once()
    assert downloaded_to == [Path("books") / "book.epub"]

    status_message.edit_text.assert_awaited_once()
    sent_text = status_message.edit_text.await_args.args[0]
    assert "Книга добавлена!" in sent_text
    assert "Название: Тестовая книга" in sent_text
    assert "Автор: Автор" in sent_text
    assert "Отрывков: 42" in sent_text


@pytest.mark.asyncio
async def test_upload_duplicate_book_message(monkeypatch: pytest.MonkeyPatch) -> None:
    telegram_file = SimpleNamespace(download_to_drive=AsyncMock())
    document = SimpleNamespace(file_size=2000, file_name="dup.fb2", get_file=AsyncMock(return_value=telegram_file))
    update, context, _, status_message = _build_update_context(document)

    async def fake_pipeline(file_path: Path, **kwargs: Any) -> IngestionPipelineResult:
        del file_path, kwargs
        return IngestionPipelineResult(
            success=True,
            title=None,
            author=None,
            format_name="fb2",
            chunk_count=0,
            is_duplicate=True,
            error=None,
        )

    monkeypatch.setattr("librar.bot.handlers.upload.run_ingestion_pipeline", fake_pipeline)

    await handle_book_upload(update, context)

    status_message.edit_text.assert_awaited_once_with("Эта книга уже есть в библиотеке.")


@pytest.mark.asyncio
async def test_upload_ingestion_failure_shows_error(monkeypatch: pytest.MonkeyPatch) -> None:
    telegram_file = SimpleNamespace(download_to_drive=AsyncMock())
    document = SimpleNamespace(file_size=2000, file_name="bad.txt", get_file=AsyncMock(return_value=telegram_file))
    update, context, _, status_message = _build_update_context(document)

    async def fake_pipeline(file_path: Path, **kwargs: Any) -> IngestionPipelineResult:
        del file_path, kwargs
        return IngestionPipelineResult(
            success=False,
            title=None,
            author=None,
            format_name=None,
            chunk_count=0,
            is_duplicate=False,
            error="pipeline failed",
        )

    monkeypatch.setattr("librar.bot.handlers.upload.run_ingestion_pipeline", fake_pipeline)

    await handle_book_upload(update, context)

    status_message.edit_text.assert_awaited_once_with("Ошибка обработки: pipeline failed")


@pytest.mark.asyncio
async def test_upload_allows_none_file_size(monkeypatch: pytest.MonkeyPatch) -> None:
    telegram_file = SimpleNamespace(download_to_drive=AsyncMock())
    document = SimpleNamespace(file_size=None, file_name="book.txt", get_file=AsyncMock(return_value=telegram_file))
    update, context, _, status_message = _build_update_context(document)

    async def fake_pipeline(file_path: Path, **kwargs: Any) -> IngestionPipelineResult:
        del file_path, kwargs
        return IngestionPipelineResult(
            success=True,
            title="Book",
            author="Author",
            format_name="txt",
            chunk_count=5,
            is_duplicate=False,
            error=None,
        )

    monkeypatch.setattr("librar.bot.handlers.upload.run_ingestion_pipeline", fake_pipeline)

    await handle_book_upload(update, context)

    document.get_file.assert_awaited_once()
    status_message.edit_text.assert_awaited_once()
