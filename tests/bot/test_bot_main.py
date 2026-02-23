"""Smoke tests for bot application bootstrap and handler registration."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    InlineQueryHandler,
)

from librar.bot.config import BotSettings
from librar.bot.main import build_application
from librar.bot.repository import BotRepository


@pytest.fixture
def mock_settings(tmp_path: Path) -> BotSettings:
    """Minimal valid settings for application bootstrap."""
    return BotSettings(
        token="test_bot_token_12345",
        db_path=tmp_path / "test.db",
        index_path=tmp_path / "test.faiss",
        inline_timeout_seconds=25.0,
        inline_result_limit=20,
        command_result_limit=10,
        page_size=5,
        openrouter_chat_model="openai/gpt-4o-mini",
        rag_top_k=5,
        rag_max_context_chars=6000,
    )


def test_build_application_registers_all_handler_types(mock_settings: BotSettings) -> None:
    """Verify application registers commands, inline, callbacks, and settings conversation."""
    app = build_application(mock_settings)

    assert isinstance(app, Application)
    assert len(app.handlers[0]) > 0  # Default group has handlers

    handlers = app.handlers[0]

    # Check for ConversationHandler (settings)
    conv_handlers = [h for h in handlers if isinstance(h, ConversationHandler)]
    assert len(conv_handlers) == 1, "Expected exactly one ConversationHandler for /settings"

    # Check for CommandHandlers (start, help, search, ask, books)
    cmd_handlers = [h for h in handlers if isinstance(h, CommandHandler)]
    # At least 5: /start, /help, /search, /ask, /books (settings entry also uses CommandHandler inside ConversationHandler)
    assert len(cmd_handlers) >= 5, "Expected at least 5 standalone CommandHandlers"

    # Check for InlineQueryHandler
    inline_handlers = [h for h in handlers if isinstance(h, InlineQueryHandler)]
    assert len(inline_handlers) == 1, "Expected exactly one InlineQueryHandler"

    # Check for CallbackQueryHandlers (pagination)
    callback_handlers = [h for h in handlers if isinstance(h, CallbackQueryHandler)]
    assert len(callback_handlers) >= 2, "Expected at least 2 CallbackQueryHandlers for pagination"


def test_build_application_stores_dependencies_in_bot_data(mock_settings: BotSettings) -> None:
    """Verify bot_data contains repository, db_path, index_path, and config values."""
    app = build_application(mock_settings)

    assert "repository" in app.bot_data
    assert isinstance(app.bot_data["repository"], BotRepository)

    assert app.bot_data["db_path"] == str(mock_settings.db_path)
    assert app.bot_data["index_path"] == str(mock_settings.index_path)
    assert app.bot_data["inline_timeout_seconds"] == mock_settings.inline_timeout_seconds
    assert app.bot_data["inline_result_limit"] == mock_settings.inline_result_limit
    assert app.bot_data["command_result_limit"] == mock_settings.command_result_limit
    assert app.bot_data["page_size"] == mock_settings.page_size
    assert app.bot_data["openrouter_chat_model"] == mock_settings.openrouter_chat_model
    assert app.bot_data["rag_top_k"] == mock_settings.rag_top_k
    assert app.bot_data["rag_max_context_chars"] == mock_settings.rag_max_context_chars


def test_build_application_uses_provided_token(mock_settings: BotSettings) -> None:
    """Verify application uses token from settings."""
    app = build_application(mock_settings)

    # Application.bot.token is accessible after builder
    assert app.bot.token == mock_settings.token


def test_bot_settings_from_env_fails_fast_on_missing_token() -> None:
    """Verify BotSettings.from_env raises ValueError when TELEGRAM_BOT_TOKEN is missing."""
    empty_env: dict[str, str] = {}

    with pytest.raises(ValueError, match="Missing required bot environment variable: TELEGRAM_BOT_TOKEN"):
        BotSettings.from_env(empty_env)


def test_bot_settings_from_env_fails_fast_on_empty_token() -> None:
    """Verify BotSettings.from_env raises ValueError when TELEGRAM_BOT_TOKEN is empty/whitespace."""
    whitespace_env = {"TELEGRAM_BOT_TOKEN": "   "}

    with pytest.raises(ValueError, match="Missing required bot environment variable: TELEGRAM_BOT_TOKEN"):
        BotSettings.from_env(whitespace_env)


def test_bot_settings_from_env_uses_defaults_for_optional_config() -> None:
    """Verify BotSettings uses default values when optional env vars are missing."""
    minimal_env = {"TELEGRAM_BOT_TOKEN": "valid_token_123"}

    settings = BotSettings.from_env(minimal_env)

    assert settings.token == "valid_token_123"
    assert settings.db_path == Path(".librar-search.db")
    assert settings.index_path == Path(".librar-semantic.faiss")
    assert settings.inline_timeout_seconds == 25.0
    assert settings.inline_result_limit == 20
    assert settings.command_result_limit == 10
    assert settings.page_size == 5
    assert settings.openrouter_chat_model == "openai/gpt-4o-mini"
    assert settings.rag_top_k == 5
    assert settings.rag_max_context_chars == 6000


def test_bot_settings_from_env_parses_custom_config_values() -> None:
    """Verify BotSettings correctly parses custom environment values."""
    custom_env = {
        "TELEGRAM_BOT_TOKEN": "custom_token",
        "LIBRAR_DB_PATH": "custom.db",
        "LIBRAR_INDEX_PATH": "custom.faiss",
        "TELEGRAM_INLINE_TIMEOUT_SECONDS": "30.5",
        "TELEGRAM_INLINE_RESULT_LIMIT": "50",
        "TELEGRAM_COMMAND_RESULT_LIMIT": "15",
        "TELEGRAM_PAGE_SIZE": "8",
        "OPENROUTER_CHAT_MODEL": "openai/gpt-4o-mini",
        "RAG_TOP_K": "7",
        "RAG_MAX_CONTEXT_CHARS": "4500",
    }

    settings = BotSettings.from_env(custom_env)

    assert settings.token == "custom_token"
    assert settings.db_path == Path("custom.db")
    assert settings.index_path == Path("custom.faiss")
    assert settings.inline_timeout_seconds == 30.5
    assert settings.inline_result_limit == 50
    assert settings.command_result_limit == 15
    assert settings.page_size == 8
    assert settings.openrouter_chat_model == "openai/gpt-4o-mini"
    assert settings.rag_top_k == 7
    assert settings.rag_max_context_chars == 4500


def test_bot_settings_from_env_rejects_invalid_numeric_values() -> None:
    """Verify BotSettings validation rejects negative/zero/non-numeric config values."""
    invalid_timeout_env = {
        "TELEGRAM_BOT_TOKEN": "token",
        "TELEGRAM_INLINE_TIMEOUT_SECONDS": "-1.0",
    }

    with pytest.raises(ValueError, match="must be >="):
        BotSettings.from_env(invalid_timeout_env)

    invalid_limit_env = {
        "TELEGRAM_BOT_TOKEN": "token",
        "TELEGRAM_INLINE_RESULT_LIMIT": "0",
    }

    with pytest.raises(ValueError, match="must be >="):
        BotSettings.from_env(invalid_limit_env)

    non_numeric_env = {
        "TELEGRAM_BOT_TOKEN": "token",
        "TELEGRAM_PAGE_SIZE": "not_a_number",
    }

    with pytest.raises(ValueError):
        BotSettings.from_env(non_numeric_env)


def test_build_application_cleanup_closes_repository(mock_settings: BotSettings) -> None:
    """Verify repository can be properly closed after application shutdown."""
    app = build_application(mock_settings)
    repository = app.bot_data["repository"]

    assert isinstance(repository, BotRepository)

    # Repository should be usable before close
    # After close, it should not raise (close is idempotent)
    repository.close()
    repository.close()  # Should not raise on second close
