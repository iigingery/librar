"""Inline query handler for @botname search from any chat."""

from __future__ import annotations

import logging

from telegram import InlineQueryResultArticle, InputTextMessageContent, Update
from telegram.ext import ContextTypes, InlineQueryHandler

from librar.bot.handlers.common import (
    ConfigError,
    _resolve_db_path,
    _resolve_index_path,
    _resolve_inline_result_limit,
    _resolve_repository,
    _resolve_required,
)
from librar.bot.search_service import search_hybrid_cli


logger = logging.getLogger(__name__)

INLINE_MAX_RESULTS = 50
INLINE_DESCRIPTION_LIMIT = 200


def _build_search_tips_line() -> str:
    return "Подсказки: сократите запрос, уберите редкие слова, попробуйте /ask"


async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline queries (@botname <query>) with timeout/error safety."""
    if update.inline_query is None:
        return

    query_text = update.inline_query.query.strip()
    user = update.effective_user

    # Short-circuit empty query
    if not query_text:
        await update.inline_query.answer([])
        return

    try:
        repository = _resolve_repository(context)
        db_path = _resolve_db_path(context)
        index_path = _resolve_index_path(context)
        limit = _resolve_inline_result_limit(context)
        timeout = float(_resolve_required(context, "inline_timeout_seconds"))
    except ConfigError as error:
        logger.error("Inline query failed due to configuration error: %s", error)
        error_article = InlineQueryResultArticle(
            id="config_error",
            title="Сервис временно недоступен",
            description="Параметры поиска не настроены",
            input_message_content=InputTextMessageContent(
                message_text="⚠️ Сервис поиска временно недоступен. Попробуйте позже."
            ),
        )
        await update.inline_query.answer([error_article], cache_time=0)
        return

    # Get user excerpt size for descriptions
    excerpt_size = 100  # Default for inline
    if user is not None:
        excerpt_size = repository.get_excerpt_size(int(user.id))

    # Execute search with timeout protection
    response = await search_hybrid_cli(
        query=query_text,
        db_path=db_path,
        index_path=index_path,
        limit=limit,
        timeout_seconds=timeout,
    )

    # Handle errors with safe fallback
    if response.error or response.timed_out:
        error_article = InlineQueryResultArticle(
            id="error",
            title="Ошибка поиска",
            description=(response.error if response.error else "Поиск превысил лимит времени")[:INLINE_DESCRIPTION_LIMIT],
            input_message_content=InputTextMessageContent(
                message_text=(
                    f"⚠️ {response.error if response.error else 'Timeout'}\n\n"
                    f"{_build_search_tips_line()}"
                )
            ),
        )
        await update.inline_query.answer([error_article], cache_time=0)
        return

    # No results
    if not response.results:
        no_results_article = InlineQueryResultArticle(
            id="no_results",
            title="Ничего не найдено",
            description=_build_search_tips_line()[:INLINE_DESCRIPTION_LIMIT],
            input_message_content=InputTextMessageContent(
                message_text=(
                    f"Ничего не найдено по запросу: {query_text}\n\n"
                    f"{_build_search_tips_line()}"
                )
            ),
        )
        await update.inline_query.answer([no_results_article], cache_time=10)
        return

    # Build article results (capped at 50 for Telegram limits)
    articles: list[InlineQueryResultArticle] = []
    for idx, result in enumerate(response.results[:INLINE_MAX_RESULTS]):
        # Truncate excerpt to user-preferred size
        excerpt = result.excerpt[:excerpt_size] if len(result.excerpt) > excerpt_size else result.excerpt

        # Build description with metadata
        description_parts = [excerpt]
        if result.title:
            description_parts.append(f"[{result.title}]")
        if result.author:
            description_parts.append(f"({result.author})")

        description = " ".join(description_parts)[:INLINE_DESCRIPTION_LIMIT]

        # Build message content
        message_parts = [f"📖 {result.display}\n", excerpt]
        if result.hybrid_score is not None:
            message_parts.append(f"\n\n[Релевантность: {result.hybrid_score:.2f}]")

        message_text = "".join(message_parts)

        articles.append(
            InlineQueryResultArticle(
                id=f"result_{idx}_{result.chunk_id}",
                title=result.display,
                description=description,
                input_message_content=InputTextMessageContent(message_text=message_text),
            )
        )

    await update.inline_query.answer(articles, cache_time=30)


def build_inline_handler() -> InlineQueryHandler:
    """Build inline query handler."""
    return InlineQueryHandler(inline_query_handler)
