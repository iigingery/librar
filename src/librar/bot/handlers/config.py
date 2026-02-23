"""Shared bot handler configuration resolvers."""

from __future__ import annotations

from telegram.ext import ContextTypes

from librar.bot.repository import BotRepository


class ConfigError(RuntimeError):
    """Raised when required handler configuration is missing or invalid."""


def resolve_repository(context: ContextTypes.DEFAULT_TYPE) -> BotRepository:
    repository = context.bot_data.get("repository")
    if repository is None:
        raise ConfigError("Bot repository missing from context.bot_data['repository']")
    if not isinstance(repository, BotRepository):
        raise ConfigError("context.bot_data['repository'] must be a BotRepository")
    return repository


def resolve_required(context: ContextTypes.DEFAULT_TYPE, key: str) -> object:
    value = context.bot_data.get(key)
    if value is None:
        raise ConfigError(f"{key} missing from context.bot_data['{key}']")
    return value

