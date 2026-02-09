"""Callback handlers for pagination (Next/Previous buttons)."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from librar.bot.repository import BotRepository


def _resolve_repository(context: ContextTypes.DEFAULT_TYPE) -> BotRepository:
    repository = context.bot_data.get("repository")
    if repository is None:
        raise RuntimeError("Bot repository missing from context.bot_data['repository']")
    if not isinstance(repository, BotRepository):
        raise TypeError("context.bot_data['repository'] must be a BotRepository")
    return repository


def _resolve_page_size(context: ContextTypes.DEFAULT_TYPE) -> int:
    page_size = context.bot_data.get("page_size")
    if page_size is None:
        raise RuntimeError("page_size missing from context.bot_data['page_size']")
    return int(page_size)


async def search_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle search pagination callbacks (search_page_N)."""
    query = update.callback_query
    if query is None or query.data is None:
        return

    # Always answer callback to clear loading state
    await query.answer()

    # Parse page number from callback_data
    try:
        page_num = int(query.data.replace("search_page_", ""))
    except ValueError:
        await query.edit_message_text("Ошибка навигации.")
        return

    # Retrieve stored search results from user_data
    results = context.user_data.get("search_results")
    search_query = context.user_data.get("search_query")
    excerpt_size = context.user_data.get("search_excerpt_size", 200)

    if results is None or search_query is None:
        await query.edit_message_text("Результаты поиска истекли. Выполните /search заново.")
        return

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
        buttons.append(InlineKeyboardButton("← Предыдущая", callback_data=f"search_page_{page_num - 1}"))
    if offset + page_size < total:
        buttons.append(InlineKeyboardButton("Следующая →", callback_data=f"search_page_{page_num + 1}"))

    if buttons:
        reply_markup = InlineKeyboardMarkup([buttons])
        await query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await query.edit_message_text(text)


async def books_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle books pagination callbacks (books_page_N)."""
    query = update.callback_query
    if query is None or query.data is None:
        return

    # Always answer callback to clear loading state
    await query.answer()

    # Parse page number from callback_data
    try:
        page_num = int(query.data.replace("books_page_", ""))
    except ValueError:
        await query.edit_message_text("Ошибка навигации.")
        return

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

    # Update stored offset
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
        buttons.append(InlineKeyboardButton("← Предыдущая", callback_data=f"books_page_{page_num - 1}"))
    if offset + page_size < book_page.total:
        buttons.append(InlineKeyboardButton("Следующая →", callback_data=f"books_page_{page_num + 1}"))

    if buttons:
        reply_markup = InlineKeyboardMarkup([buttons])
        await query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await query.edit_message_text(text)


def build_callback_handlers() -> list[CallbackQueryHandler]:
    """Build all callback query handlers."""
    return [
        CallbackQueryHandler(search_page_callback, pattern=r"^search_page_\d+$"),
        CallbackQueryHandler(books_page_callback, pattern=r"^books_page_\d+$"),
    ]
