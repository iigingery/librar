"""Command handlers for /start, /help, /search, /ask, and /books."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, ContextTypes

from librar.bot.repository import BotRepository, DEFAULT_DIALOG_HISTORY_LIMIT
from librar.bot.search_service import AnswerSource, answer_question, search_hybrid_cli


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


def _resolve_page_size(context: ContextTypes.DEFAULT_TYPE) -> int:
    page_size = context.bot_data.get("page_size")
    if page_size is None:
        raise RuntimeError("page_size missing from context.bot_data['page_size']")
    return int(page_size)


def _resolve_command_result_limit(context: ContextTypes.DEFAULT_TYPE) -> int:
    limit = context.bot_data.get("command_result_limit")
    if limit is None:
        raise RuntimeError("command_result_limit missing from context.bot_data['command_result_limit']")
    return int(limit)


def _resolve_chat_model(context: ContextTypes.DEFAULT_TYPE) -> str:
    model = context.bot_data.get("openrouter_chat_model")
    if model is None:
        raise RuntimeError("openrouter_chat_model missing from context.bot_data['openrouter_chat_model']")
    return str(model)


def _resolve_rag_top_k(context: ContextTypes.DEFAULT_TYPE) -> int:
    top_k = context.bot_data.get("rag_top_k")
    if top_k is None:
        raise RuntimeError("rag_top_k missing from context.bot_data['rag_top_k']")
    return int(top_k)


def _resolve_rag_max_context_chars(context: ContextTypes.DEFAULT_TYPE) -> int:
    max_chars = context.bot_data.get("rag_max_context_chars")
    if max_chars is None:
        raise RuntimeError("rag_max_context_chars missing from context.bot_data['rag_max_context_chars']")
    return int(max_chars)


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

    user = update.effective_user
    if user is None:
        await update.message.reply_text("Не удалось определить пользователя.")
        return

    query = " ".join(context.args or []).strip()
    if not query:
        await update.message.reply_text(
            "Использование: /search <запрос>\n\nПример: /search программирование"
        )
        return

    repository = _resolve_repository(context)
    db_path = _resolve_db_path(context)
    index_path = _resolve_index_path(context)
    limit = _resolve_command_result_limit(context)
    page_size = _resolve_page_size(context)

    excerpt_size = repository.get_excerpt_size(int(user.id))

    # Execute search via async gateway
    response = await search_hybrid_cli(
        query=query,
        db_path=db_path,
        index_path=index_path,
        limit=limit,
    )

    if response.timed_out:
        await update.message.reply_text("Поиск превысил лимит времени. Попробуйте упростить запрос.")
        return

    if response.error:
        await update.message.reply_text(f"Ошибка поиска: {response.error}")
        return

    if not response.results:
        await update.message.reply_text(f"Ничего не найдено по запросу: {query}")
        return

    # Store full results in user_data for pagination
    context.user_data["search_query"] = query
    context.user_data["search_results"] = response.results
    context.user_data["search_excerpt_size"] = excerpt_size

    # Render first page
    total = len(response.results)
    page_results = response.results[:page_size]
    text = f"Найдено {total} результатов для: {query}\n\n"

    for idx, result in enumerate(page_results, 1):
        excerpt = result.excerpt[:excerpt_size] if len(result.excerpt) > excerpt_size else result.excerpt
        text += f"{idx}. {result.display}\n{excerpt}...\n\n"

    # Build pagination keyboard if more results exist
    if total > page_size:
        keyboard = [[InlineKeyboardButton("Следующая →", callback_data="search_page_1")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text)


async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /ask <question> command with retrieval-augmented answer."""
    if update.message is None:
        return

    query = " ".join(context.args or []).strip()
    if not query:
        await update.message.reply_text("Использование: /ask <вопрос>\n\nПример: /ask Кто автор книги?")
        return

    chat = update.effective_chat
    user = update.effective_user
    if chat is None or user is None:
        await update.message.reply_text("Не удалось определить чат или пользователя.")
        return

    repository = _resolve_repository(context)
    db_path = _resolve_db_path(context)
    index_path = _resolve_index_path(context)
    chat_model = _resolve_chat_model(context)
    top_k = _resolve_rag_top_k(context)
    max_context_chars = _resolve_rag_max_context_chars(context)

    history_rows = repository.get_dialog_history(
        chat_id=int(chat.id),
        user_id=int(user.id),
        limit=DEFAULT_DIALOG_HISTORY_LIMIT,
    )
    history = tuple((row.role, row.content) for row in history_rows[-5:])

    answer_result = await answer_question(
        query=query,
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
        content=query,
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

    chat = update.effective_chat
    user = update.effective_user
    if chat is None or user is None:
        await update.message.reply_text("Не удалось определить чат или пользователя.")
        return

    repository = _resolve_repository(context)
    removed = repository.clear_dialog_history(chat_id=int(chat.id), user_id=int(user.id))
    suffix = f" Удалено сообщений: {removed}." if removed else ""
    await update.message.reply_text(f"История диалога очищена.{suffix}")


async def books_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /books command with paginated book list."""
    if update.message is None:
        return

    repository = _resolve_repository(context)
    page_size = _resolve_page_size(context)

    book_page = repository.list_books(limit=page_size, offset=0)

    if book_page.total == 0:
        await update.message.reply_text("Библиотека пуста.")
        return

    # Store pagination state
    context.user_data["books_page_offset"] = 0

    # Render first page
    text = f"Всего книг: {book_page.total}\n\n"
    for item in book_page.items:
        title = item.title or "Без названия"
        author = item.author or "Неизвестный автор"
        format_name = item.format_name or "?"
        text += f"• {title} — {author} ({format_name})\n"

    # Build pagination keyboard if more books exist
    if book_page.total > page_size:
        keyboard = [[InlineKeyboardButton("Следующая →", callback_data="books_page_1")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text)


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
