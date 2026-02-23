"""Backward-compatible exports for handler configuration resolvers."""

from __future__ import annotations

from librar.bot.handlers.common import ConfigError, _resolve_repository as resolve_repository
from librar.bot.handlers.common import _resolve_required as resolve_required

__all__ = ["ConfigError", "resolve_repository", "resolve_required"]
