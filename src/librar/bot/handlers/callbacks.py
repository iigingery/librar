"""Callback handlers for pagination (Next/Previous buttons)."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from librar.bot.handlers.common import _resolve_page_size, _resolve_repository


async def search_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle search pagination callbacks (search_page_<session>_N)."""
    query = update.callback_query
    if query is None or query.data is None:
        return

    # Always answer callback to clear loading state
    await query.answer()

    # Parse session key and page number from callback_data
    try:
        _, _, rest = query.data.partition("search_page_")
        if "_" in rest:
            session_key, page_num_raw = rest.rsplit("_", 1)
            page_num = int(page_num_raw)
        else:
            session_key = None
            page_num = int(rest)
    except ValueError:
        await query.edit_message_text("Ошибка навигации.")
        return

    # Retrieve stored search results from user_data by session
    results = None
    search_query = None
    excerpt_size = 200
    search_sessions = context.user_data.get("search_sessions")

    if session_key is not None and isinstance(search_sessions, dict):
        search_session = search_sessions.get(session_key)
        if isinstance(search_session, dict):
            results = search_session.get("results")
            search_query = search_session.get("query")
            excerpt_size = search_session.get("excerpt_size", 200)

    # Backward compatibility with legacy storage
    if results is None or search_query is None:
        results = context.user_data.get("search_results")
        search_query = context.user_data.get("search_query")
        excerpt_size = context.user_data.get("search_excerpt_size", 200)

    if results is None or search_query is None:
        await query.edit_message_text("Результаты поиска истекли. Выполните /search заново.")
        return

    # Remove stale sessions for the same chat, keep only active session
    chat = getattr(update, "effective_chat", None)
    if chat is not None and isinstance(search_sessions, dict) and session_key is not None:
        chat_prefix = f"{int(chat.id)}:"
        stale_keys = [key for key in search_sessions if key.startswith(chat_prefix) and key != session_key]
        for stale_key in stale_keys:
            search_sessions.pop(stale_key, None)

    page_size = _resolve_page_size(context)
    total = len(results)
    offset = page_num * page_size

    # Validate page bounds
    if offset < 0 or offset >= total:
        await query.edit_message_text("Страница не существует.")
        return

    # Render page
    page_results = results[offset : offset + page_size]
    text = f"Найдено {total} результатов для: {search_query}\n\n"

    for idx, result in enumerate(page_results, offset + 1):
        excerpt = result.excerpt[:excerpt_size] if len(result.excerpt) > excerpt_size else result.excerpt
        text += f"{idx}. {result.display}\n{excerpt}...\n\n"

    # Build navigation buttons
    buttons = []
    if page_num > 0:
        callback_data = (
            f"search_page_{session_key}_{page_num - 1}" if session_key is not None else f"search_page_{page_num - 1}"
        )
        buttons.append(InlineKeyboardButton("← Предыдущая", callback_data=callback_data))
    if offset + page_size < total:
        callback_data = (
            f"search_page_{session_key}_{page_num + 1}" if session_key is not None else f"search_page_{page_num + 1}"
        )
        buttons.append(InlineKeyboardButton("Следующая →", callback_data=callback_data))

    if buttons:
        reply_markup = InlineKeyboardMarkup([buttons])
        await query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await query.edit_message_text(text)


async def books_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle books pagination callbacks (books_page_<session>_N)."""
    query = update.callback_query
    if query is None or query.data is None:
        return

    # Always answer callback to clear loading state
    await query.answer()

    # Parse session key and page number from callback_data
    try:
        _, _, rest = query.data.partition("books_page_")
        if "_" in rest:
            session_key, page_num_raw = rest.rsplit("_", 1)
            page_num = int(page_num_raw)
        else:
            session_key = None
            page_num = int(rest)
    except ValueError:
        await query.edit_message_text("Ошибка навигации.")
        return

    book_sessions = context.user_data.get("book_sessions")
    if session_key is not None and (not isinstance(book_sessions, dict) or session_key not in book_sessions):
        await query.edit_message_text("Сессия списка книг истекла. Выполните /books заново.")
        return

    # Remove stale sessions for the same chat, keep only active session
    chat = getattr(update, "effective_chat", None)
    if chat is not None and isinstance(book_sessions, dict) and session_key is not None:
        chat_prefix = f"{int(chat.id)}:"
        stale_keys = [key for key in book_sessions if key.startswith(chat_prefix) and key != session_key]
        for stale_key in stale_keys:
            book_sessions.pop(stale_key, None)

    repository = _resolve_repository(context)
    page_size = _resolve_page_size(context)
    offset = page_num * page_size

    # Fetch book page
    book_page = repository.list_books(limit=page_size, offset=offset)

    # Validate page bounds
    if offset < 0 or (offset >= book_page.total and book_page.total > 0):
        await query.edit_message_text("Страница не существует.")
        return

    if book_page.total == 0:
        await query.edit_message_text("Библиотека пуста.")
        return

    # Backward compatibility with legacy offset storage
    context.user_data["books_page_offset"] = offset

    # Render page
    text = f"Всего книг: {book_page.total}\n\n"
    for item in book_page.items:
        title = item.title or "Без названия"
        author = item.author or "Неизвестный автор"
        format_name = item.format_name or "?"
        text += f"• {title} — {author} ({format_name})\n"

    # Build navigation buttons
    buttons = []
    if page_num > 0:
        callback_data = (
            f"books_page_{session_key}_{page_num - 1}" if session_key is not None else f"books_page_{page_num - 1}"
        )
        buttons.append(InlineKeyboardButton("← Предыдущая", callback_data=callback_data))
    if offset + page_size < book_page.total:
        callback_data = (
            f"books_page_{session_key}_{page_num + 1}" if session_key is not None else f"books_page_{page_num + 1}"
        )
        buttons.append(InlineKeyboardButton("Следующая →", callback_data=callback_data))

    if buttons:
        reply_markup = InlineKeyboardMarkup([buttons])
        await query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await query.edit_message_text(text)


def build_callback_handlers() -> list[CallbackQueryHandler]:
    """Build all callback query handlers."""
    return [
        CallbackQueryHandler(search_page_callback, pattern=r"^search_page_(?:.+_)?\d+$"),
        CallbackQueryHandler(books_page_callback, pattern=r"^books_page_(?:.+_)?\d+$"),
    ]
