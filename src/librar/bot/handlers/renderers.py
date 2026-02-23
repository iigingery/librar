"""Shared rendering utilities for paginated bot messages."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


class _SearchResultLike(Protocol):
    display: str
    excerpt: str


class _BookListItemLike(Protocol):
    title: str | None
    author: str | None
    format_name: str | None


def render_search_page(
    *,
    results: Sequence[_SearchResultLike],
    search_query: str,
    excerpt_size: int,
    page_num: int,
    page_size: int,
) -> str:
    """Render text for a single search results page."""
    total = len(results)
    offset = page_num * page_size
    page_results = results[offset : offset + page_size]

    text = f"Найдено {total} результатов для: {search_query}\n\n"
    for idx, result in enumerate(page_results, offset + 1):
        excerpt = result.excerpt[:excerpt_size] if len(result.excerpt) > excerpt_size else result.excerpt
        text += f"{idx}. {result.display}\n{excerpt}...\n\n"
    return text


def render_books_page(*, items: Sequence[_BookListItemLike], total: int) -> str:
    """Render text for a single books page."""
    text = f"Всего книг: {total}\n\n"
    for item in items:
        title = item.title or "Без названия"
        author = item.author or "Неизвестный автор"
        format_name = item.format_name or "?"
        text += f"• {title} — {author} ({format_name})\n"
    return text


def build_pagination_keyboard(
    *,
    prefix: str,
    session_key: str | None,
    page_num: int,
    has_next: bool,
) -> InlineKeyboardMarkup | None:
    """Build previous/next pagination keyboard for callback pages."""
    buttons: list[InlineKeyboardButton] = []

    if page_num > 0:
        callback_data = (
            f"{prefix}_{session_key}_{page_num - 1}" if session_key is not None else f"{prefix}_{page_num - 1}"
        )
        buttons.append(InlineKeyboardButton("← Предыдущая", callback_data=callback_data))

    if has_next:
        callback_data = (
            f"{prefix}_{session_key}_{page_num + 1}" if session_key is not None else f"{prefix}_{page_num + 1}"
        )
        buttons.append(InlineKeyboardButton("Следующая →", callback_data=callback_data))

    if not buttons:
        return None

    return InlineKeyboardMarkup([buttons])
