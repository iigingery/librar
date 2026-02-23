"""Command handlers for /start, /help, /search, /ask, and /books."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from librar.bot.handlers.common import (
    ConfigError,
    _resolve_command_result_limit,
    _resolve_db_path,
    _resolve_index_path,
    _resolve_page_size,
    _resolve_repository,
    _resolve_required,
)
from librar.bot.handlers.renderers import (
    build_pagination_keyboard,
    render_books_page,
    render_search_page,
)
from librar.bot.repository import DEFAULT_DIALOG_HISTORY_LIMIT
from librar.bot.search_service import AnswerSource, answer_question, search_hybrid_cli

logger = logging.getLogger(__name__)

SEARCH_TIPS = (
    "Подсказки:\n"
    "• сократите запрос\n"
    "• уберите редкие слова\n"
    "• попробуйте /ask"
)


def _format_answer_message(answer_text: str, sources: tuple[AnswerSource, ...], *, confirmed: bool) -> str:
    status_line = "✅ Подтверждённый ответ" if confirmed else "⚠️ Недостаточно данных"
    lines = [status_line, "", "Ответ", answer_text.strip() or "Недостаточно данных в источниках.", "", "Источники"]
    if not sources:
        lines.append("1. Источники не найдены")
        return "\n".join(lines)

    for idx, source in enumerate(sources, 1):
        lines.append(
            f"{idx}. {source.title} — {source.author}; {source.source_path}; {source.location}"
        )
    return "\n".join(lines)


def _resolve_chat_id(update: Update) -> int | None:
    chat = getattr(update, "effective_chat", None)
    if chat is not None:
        return int(chat.id)

    message = update.message
    if message is not None:
        chat_id = getattr(message, "chat_id", None)
        if chat_id is not None:
            return int(chat_id)

    user = getattr(update, "effective_user", None)
    if user is not None:
        return int(user.id)
    return None


def _build_session_key(chat_id: int, message_id: int) -> str:
    return f"{chat_id}:{message_id}"


def _cleanup_chat_sessions(
    sessions: dict[str, object],
    *,
    chat_id: int,
    active_session_key: str,
) -> None:
    chat_prefix = f"{chat_id}:"
    stale_keys = [key for key in sessions if key.startswith(chat_prefix) and key != active_session_key]
    for stale_key in stale_keys:
        sessions.pop(stale_key, None)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command with usage instructions."""
    del context
    if update.message is None:
        return

    text = (
        "Добро пожаловать в библиотечного бота!\n\n"
        "Используйте:\n"
        "• /search <запрос> — прямой поиск в личных сообщениях\n"
        "• /ask <вопрос> — ответ с подтверждением по источникам\n"
        "• @botname <запрос> — встроенный поиск в любом чате (inline mode)\n"
        "• /books — список всех книг в библиотеке\n"
        "• /settings — настройки размера отрывков\n"
        "• /help — справка по командам\n"
        "• /reset_context — очистить историю диалога\n\n"
        "Попробуйте: /search русская литература"
    )
    await update.message.reply_text(text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command with detailed usage guidance."""
    del context
    if update.message is None:
        return

    text = (
        "Справка по командам:\n\n"
        "/start — приветствие и основные команды\n"
        "/search <запрос> — поиск отрывков в библиотеке\n"
        "  Пример: /search космос\n\n"
        "/ask <вопрос> — RAG-ответ на основе найденных фрагментов\n"
        "  Пример: /ask Кто автор книги?\n\n"
        "/books — показать все книги с метаданными\n"
        "  Навигация: кнопки Предыдущая/Следующая\n\n"
        "/settings — изменить размер отрывков (50-500 символов)\n"
        "/reset_context — очистить историю диалога с ботом\n\n"
        "Inline mode:\n"
        "  В любом чате наберите @botname <запрос>\n"
        "  Выберите результат из списка\n\n"
        "Примечание: inline mode имеет лимит времени 30 секунд."
    )
    await update.message.reply_text(text)


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /search <query> command with paginated results."""
    if update.message is None:
        return

    user = getattr(update, "effective_user", None)
    if user is None:
        await update.message.reply_text("Не удалось определить пользователя.")
        return

    chat_id = _resolve_chat_id(update)
    if chat_id is None:
        await update.message.reply_text("Не удалось определить чат.")
        return

    query_text = " ".join(context.args or []).strip()
    if not query_text:
        await update.message.reply_text(
            "Использование: /search <запрос>\n\nПример: /search программирование"
        )
        return

    try:
        repository = _resolve_repository(context)
        db_path = _resolve_db_path(context)
        index_path = _resolve_index_path(context)
        limit = _resolve_command_result_limit(context)
        page_size = _resolve_page_size(context)
    except ConfigError as error:
        logger.error("/search failed due to configuration error: %s", error)
        await update.message.reply_text("Поиск временно недоступен. Попробуйте позже.")
        return

    excerpt_size = repository.get_excerpt_size(int(user.id))

    # Execute search via async gateway
    response = await search_hybrid_cli(
        query=query_text,
        db_path=db_path,
        index_path=index_path,
        limit=limit,
    )

    if response.timed_out:
        await update.message.reply_text(
            "Поиск превысил лимит времени.\n\n"
            f"{SEARCH_TIPS}"
        )
        return

    if response.error:
        await update.message.reply_text(f"Ошибка поиска: {response.error}")
        return

    if not response.results:
        await update.message.reply_text(
            f"Ничего не найдено по запросу: {query_text}\n\n"
            f"{SEARCH_TIPS}"
        )
        return

    # Store full results in user_data under session key for pagination
    search_sessions = context.user_data.setdefault("search_sessions", {})
    if not isinstance(search_sessions, dict):
        search_sessions = {}
        context.user_data["search_sessions"] = search_sessions

    message_id = int(getattr(update.message, "message_id", 0))
    session_key = _build_session_key(chat_id, message_id)
    search_sessions[session_key] = {
        "query": query_text,
        "results": response.results,
        "excerpt_size": excerpt_size,
    }
    _cleanup_chat_sessions(search_sessions, chat_id=chat_id, active_session_key=session_key)

    # Backward compatibility with legacy pagination storage
    context.user_data["search_query"] = query_text
    context.user_data["search_results"] = response.results
    context.user_data["search_excerpt_size"] = excerpt_size

    # Render first page
    total = len(response.results)
    text = render_search_page(
        results=response.results,
        search_query=query_text,
        excerpt_size=excerpt_size,
        page_num=0,
        page_size=page_size,
    )

    reply_markup = build_pagination_keyboard(
        prefix="search_page",
        session_key=session_key,
        page_num=0,
        has_next=total > page_size,
    )
    await update.message.reply_text(text, reply_markup=reply_markup)


async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /ask <question> command with retrieval-augmented answer."""
    if update.message is None:
        return

    query_text = " ".join(context.args or []).strip()
    if not query_text:
        await update.message.reply_text("Использование: /ask <вопрос>\n\nПример: /ask Кто автор книги?")
        return

    chat = getattr(update, "effective_chat", None)
    user = getattr(update, "effective_user", None)
    if chat is None or user is None:
        await update.message.reply_text("Не удалось определить чат или пользователя.")
        return

    try:
        repository = _resolve_repository(context)
        db_path = _resolve_db_path(context)
        index_path = _resolve_index_path(context)
        chat_model = str(_resolve_required(context, "openrouter_chat_model"))
        top_k = int(_resolve_required(context, "rag_top_k"))
        max_context_chars = int(_resolve_required(context, "rag_max_context_chars"))
    except ConfigError as error:
        logger.error("/ask failed due to configuration error: %s", error)
        await update.message.reply_text("Сервис ответов временно недоступен. Попробуйте позже.")
        return

    history_rows = repository.get_dialog_history(
        chat_id=int(chat.id),
        user_id=int(user.id),
        limit=DEFAULT_DIALOG_HISTORY_LIMIT,
    )
    history = tuple((row.role, row.content) for row in history_rows[-5:])

    answer_result = await answer_question(
        query=query_text,
        db_path=db_path,
        index_path=index_path,
        top_k=top_k,
        max_context_chars=max_context_chars,
        chat_model=chat_model,
        history=history,
    )

    repository.save_dialog_message(
        chat_id=int(chat.id),
        user_id=int(user.id),
        role="user",
        content=query_text,
        limit=DEFAULT_DIALOG_HISTORY_LIMIT,
    )
    repository.save_dialog_message(
        chat_id=int(chat.id),
        user_id=int(user.id),
        role="assistant",
        content=answer_result.answer,
        limit=DEFAULT_DIALOG_HISTORY_LIMIT,
    )

    formatted_answer = _format_answer_message(
        answer_result.answer,
        answer_result.sources,
        confirmed=answer_result.is_confirmed,
    )
    await update.message.reply_text(formatted_answer)


async def reset_context_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /reset_context command by clearing per-user dialog memory."""
    if update.message is None:
        return

    chat = getattr(update, "effective_chat", None)
    user = getattr(update, "effective_user", None)
    if chat is None or user is None:
        await update.message.reply_text("Не удалось определить чат или пользователя.")
        return

    try:
        repository = _resolve_repository(context)
    except ConfigError as error:
        logger.error("/reset_context failed due to configuration error: %s", error)
        await update.message.reply_text("Не удалось очистить историю. Попробуйте позже.")
        return

    removed = repository.clear_dialog_history(chat_id=int(chat.id), user_id=int(user.id))
    suffix = f" Удалено сообщений: {removed}." if removed else ""
    await update.message.reply_text(f"История диалога очищена.{suffix}")


async def books_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /books command with paginated book list."""
    if update.message is None:
        return

    chat_id = _resolve_chat_id(update)
    if chat_id is None:
        await update.message.reply_text("Не удалось определить чат.")
        return

    try:
        repository = _resolve_repository(context)
        page_size = _resolve_page_size(context)
    except ConfigError as error:
        logger.error("/books failed due to configuration error: %s", error)
        await update.message.reply_text("Список книг временно недоступен. Попробуйте позже.")
        return

    book_page = repository.list_books(limit=page_size, offset=0)

    if book_page.total == 0:
        await update.message.reply_text("Библиотека пуста.")
        return

    # Store pagination session state
    book_sessions = context.user_data.setdefault("book_sessions", {})
    if not isinstance(book_sessions, dict):
        book_sessions = {}
        context.user_data["book_sessions"] = book_sessions

    message_id = int(getattr(update.message, "message_id", 0))
    session_key = _build_session_key(chat_id, message_id)
    book_sessions[session_key] = {"created_from": message_id}
    _cleanup_chat_sessions(book_sessions, chat_id=chat_id, active_session_key=session_key)

    # Render first page
    text = render_books_page(items=book_page.items, total=book_page.total)

    reply_markup = build_pagination_keyboard(
        prefix="books_page",
        session_key=session_key,
        page_num=0,
        has_next=book_page.total > page_size,
    )
    await update.message.reply_text(text, reply_markup=reply_markup)


def build_command_handlers() -> list[CommandHandler]:
    """Build all command handlers."""
    return [
        CommandHandler("start", start_command),
        CommandHandler("help", help_command),
        CommandHandler("search", search_command),
        CommandHandler("ask", ask_command),
        CommandHandler("books", books_command),
        CommandHandler("reset_context", reset_context_command),
    ]
