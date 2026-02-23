"""Shared bot handler context resolvers."""

from __future__ import annotations

from telegram.ext import ContextTypes

from librar.bot.repository import BotRepository


class ConfigError(RuntimeError):
    """Raised when required handler configuration is missing or invalid."""


def _resolve_repository(context: ContextTypes.DEFAULT_TYPE) -> BotRepository:
    repository = context.bot_data.get("repository")
    if repository is None:
        raise ConfigError("Bot repository missing from context.bot_data['repository']")
    if not isinstance(repository, BotRepository):
        raise ConfigError("context.bot_data['repository'] must be a BotRepository")
    return repository


def _resolve_required(context: ContextTypes.DEFAULT_TYPE, key: str) -> object:
    value = context.bot_data.get(key)
    if value is None:
        raise ConfigError(f"{key} missing from context.bot_data['{key}']")
    return value


def _resolve_db_path(context: ContextTypes.DEFAULT_TYPE) -> str:
    return str(_resolve_required(context, "db_path"))


def _resolve_index_path(context: ContextTypes.DEFAULT_TYPE) -> str:
    return str(_resolve_required(context, "index_path"))


def _resolve_page_size(context: ContextTypes.DEFAULT_TYPE) -> int:
    return int(_resolve_required(context, "page_size"))


def _resolve_inline_result_limit(context: ContextTypes.DEFAULT_TYPE) -> int:
    return int(_resolve_required(context, "inline_result_limit"))


def _resolve_command_result_limit(context: ContextTypes.DEFAULT_TYPE) -> int:
    return int(_resolve_required(context, "command_result_limit"))
