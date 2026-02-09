"""Inline query handler for @botname search from any chat."""

from __future__ import annotations

from telegram import InlineQueryResultArticle, InputTextMessageContent, Update
from telegram.ext import ContextTypes, InlineQueryHandler

from librar.bot.repository import BotRepository
from librar.bot.search_service import search_hybrid_cli


INLINE_MAX_RESULTS = 50


def _resolve_repository(context: ContextTypes.DEFAULT_TYPE) -> BotRepository:
    repository = context.bot_data.get("repository")
    if repository is None:
        raise RuntimeError("Bot repository missing from context.bot_data['repository']")
    if not isinstance(repository, BotRepository):
        raise TypeError("context.bot_data['repository'] must be a BotRepository")
    return repository


def _resolve_db_path(context: ContextTypes.DEFAULT_TYPE) -> str:
    db_path = context.bot_data.get("db_path")
    if db_path is None:
        raise RuntimeError("db_path missing from context.bot_data['db_path']")
    return str(db_path)


def _resolve_index_path(context: ContextTypes.DEFAULT_TYPE) -> str:
    index_path = context.bot_data.get("index_path")
    if index_path is None:
        raise RuntimeError("index_path missing from context.bot_data['index_path']")
    return str(index_path)


def _resolve_inline_result_limit(context: ContextTypes.DEFAULT_TYPE) -> int:
    limit = context.bot_data.get("inline_result_limit")
    if limit is None:
        raise RuntimeError("inline_result_limit missing from context.bot_data['inline_result_limit']")
    return int(limit)


def _resolve_inline_timeout(context: ContextTypes.DEFAULT_TYPE) -> float:
    timeout = context.bot_data.get("inline_timeout_seconds")
    if timeout is None:
        raise RuntimeError("inline_timeout_seconds missing from context.bot_data['inline_timeout_seconds']")
    return float(timeout)


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

    repository = _resolve_repository(context)
    db_path = _resolve_db_path(context)
    index_path = _resolve_index_path(context)
    limit = _resolve_inline_result_limit(context)
    timeout = _resolve_inline_timeout(context)

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
            description=response.error if response.error else "Поиск превысил лимит времени",
            input_message_content=InputTextMessageContent(
                message_text=f"⚠️ {response.error if response.error else 'Timeout'}"
            ),
        )
        await update.inline_query.answer([error_article], cache_time=0)
        return

    # No results
    if not response.results:
        no_results_article = InlineQueryResultArticle(
            id="no_results",
            title="Ничего не найдено",
            description=f"Попробуйте другой запрос: {query_text}",
            input_message_content=InputTextMessageContent(
                message_text=f"Ничего не найдено по запросу: {query_text}"
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

        description = " ".join(description_parts)[:200]  # Telegram description limit

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
