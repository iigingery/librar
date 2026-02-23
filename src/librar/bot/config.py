"""Runtime configuration for Telegram bot modules."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Mapping


DEFAULT_DB_PATH = ".librar-search.db"
DEFAULT_INDEX_PATH = ".librar-semantic.faiss"
DEFAULT_INLINE_TIMEOUT_SECONDS = 25.0
DEFAULT_INLINE_RESULT_LIMIT = 20
DEFAULT_COMMAND_RESULT_LIMIT = 10
DEFAULT_PAGE_SIZE = 5
DEFAULT_OPENROUTER_CHAT_MODEL = "openai/gpt-4o-mini"
DEFAULT_RAG_TOP_K = 5
DEFAULT_RAG_MAX_CONTEXT_CHARS = 6000


def _parse_positive_int(*, name: str, raw_value: str, minimum: int = 1) -> int:
    value = int(raw_value)
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


def _parse_positive_float(*, name: str, raw_value: str, minimum: float = 0.001) -> float:
    value = float(raw_value)
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


@dataclass(frozen=True, slots=True)
class BotSettings:
    """Validated Telegram bot runtime settings."""

    token: str
    db_path: Path
    index_path: Path
    inline_timeout_seconds: float = DEFAULT_INLINE_TIMEOUT_SECONDS
    inline_result_limit: int = DEFAULT_INLINE_RESULT_LIMIT
    command_result_limit: int = DEFAULT_COMMAND_RESULT_LIMIT
    page_size: int = DEFAULT_PAGE_SIZE
    openrouter_chat_model: str = DEFAULT_OPENROUTER_CHAT_MODEL
    rag_top_k: int = DEFAULT_RAG_TOP_K
    rag_max_context_chars: int = DEFAULT_RAG_MAX_CONTEXT_CHARS

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "BotSettings":
        source: Mapping[str, str] = os.environ if environ is None else environ

        token = source.get("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            raise ValueError("Missing required bot environment variable: TELEGRAM_BOT_TOKEN")

        db_path_raw = source.get("LIBRAR_DB_PATH", DEFAULT_DB_PATH).strip()
        if not db_path_raw:
            raise ValueError("LIBRAR_DB_PATH cannot be empty")

        index_path_raw = source.get("LIBRAR_INDEX_PATH", DEFAULT_INDEX_PATH).strip()
        if not index_path_raw:
            raise ValueError("LIBRAR_INDEX_PATH cannot be empty")

        timeout_raw = source.get("TELEGRAM_INLINE_TIMEOUT_SECONDS", str(DEFAULT_INLINE_TIMEOUT_SECONDS)).strip()
        inline_limit_raw = source.get("TELEGRAM_INLINE_RESULT_LIMIT", str(DEFAULT_INLINE_RESULT_LIMIT)).strip()
        command_limit_raw = source.get("TELEGRAM_COMMAND_RESULT_LIMIT", str(DEFAULT_COMMAND_RESULT_LIMIT)).strip()
        page_size_raw = source.get("TELEGRAM_PAGE_SIZE", str(DEFAULT_PAGE_SIZE)).strip()
        chat_model_raw = source.get("OPENROUTER_CHAT_MODEL", DEFAULT_OPENROUTER_CHAT_MODEL).strip()
        rag_top_k_raw = source.get("RAG_TOP_K", str(DEFAULT_RAG_TOP_K)).strip()
        rag_max_context_chars_raw = source.get("RAG_MAX_CONTEXT_CHARS", str(DEFAULT_RAG_MAX_CONTEXT_CHARS)).strip()

        if not timeout_raw:
            raise ValueError("TELEGRAM_INLINE_TIMEOUT_SECONDS cannot be empty")
        if not inline_limit_raw:
            raise ValueError("TELEGRAM_INLINE_RESULT_LIMIT cannot be empty")
        if not command_limit_raw:
            raise ValueError("TELEGRAM_COMMAND_RESULT_LIMIT cannot be empty")
        if not page_size_raw:
            raise ValueError("TELEGRAM_PAGE_SIZE cannot be empty")
        if not chat_model_raw:
            raise ValueError("OPENROUTER_CHAT_MODEL cannot be empty")
        if not rag_top_k_raw:
            raise ValueError("RAG_TOP_K cannot be empty")
        if not rag_max_context_chars_raw:
            raise ValueError("RAG_MAX_CONTEXT_CHARS cannot be empty")

        inline_timeout_seconds = _parse_positive_float(
            name="TELEGRAM_INLINE_TIMEOUT_SECONDS",
            raw_value=timeout_raw,
            minimum=0.1,
        )
        inline_result_limit = _parse_positive_int(
            name="TELEGRAM_INLINE_RESULT_LIMIT",
            raw_value=inline_limit_raw,
            minimum=1,
        )
        command_result_limit = _parse_positive_int(
            name="TELEGRAM_COMMAND_RESULT_LIMIT",
            raw_value=command_limit_raw,
            minimum=1,
        )
        page_size = _parse_positive_int(
            name="TELEGRAM_PAGE_SIZE",
            raw_value=page_size_raw,
            minimum=1,
        )
        rag_top_k = _parse_positive_int(
            name="RAG_TOP_K",
            raw_value=rag_top_k_raw,
            minimum=1,
        )
        rag_max_context_chars = _parse_positive_int(
            name="RAG_MAX_CONTEXT_CHARS",
            raw_value=rag_max_context_chars_raw,
            minimum=100,
        )

        return cls(
            token=token,
            db_path=Path(db_path_raw),
            index_path=Path(index_path_raw),
            inline_timeout_seconds=inline_timeout_seconds,
            inline_result_limit=inline_result_limit,
            command_result_limit=command_result_limit,
            page_size=page_size,
            openrouter_chat_model=chat_model_raw,
            rag_top_k=rag_top_k,
            rag_max_context_chars=rag_max_context_chars,
        )
