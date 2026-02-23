"""Conversation flow for /settings excerpt-size updates."""

from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from librar.bot.handlers.config import ConfigError, resolve_repository
from librar.bot.repository import DEFAULT_EXCERPT_SIZE, MAX_EXCERPT_SIZE, MIN_EXCERPT_SIZE


logger = logging.getLogger(__name__)

SETTINGS_SELECT, SETTINGS_ENTER_EXCERPT_SIZE = range(2)
SETTINGS_CALLBACK_EXCERPT_SIZE = "set_excerpt"


async def settings_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        logger.warning("/settings skipped: missing message update")
        return ConversationHandler.END

    try:
        repository = resolve_repository(context)
    except ConfigError as error:
        logger.error("/settings failed due to configuration error: %s", error)
        await update.message.reply_text("Настройки временно недоступны. Попробуйте позже.")
        return ConversationHandler.END
    user = update.effective_user
    current_size = DEFAULT_EXCERPT_SIZE if user is None else repository.get_excerpt_size(int(user.id))

    reply_markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton(text="Изменить размер отрывка", callback_data=SETTINGS_CALLBACK_EXCERPT_SIZE)]]
    )
    await update.message.reply_text(
        (
            "Текущий размер отрывка: "
            f"{current_size} символов.\n\n"
            f"Выберите действие или отправьте /cancel. Диапазон: {MIN_EXCERPT_SIZE}-{MAX_EXCERPT_SIZE}."
        ),
        reply_markup=reply_markup,
    )
    return SETTINGS_SELECT


async def settings_choose_excerpt_size(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    del context
    query = update.callback_query
    if query is None:
        logger.warning("settings_choose_excerpt_size skipped: missing callback_query update")
        return ConversationHandler.END

    await query.answer()
    await query.edit_message_text(
        text=(
            f"Введите новый размер отрывка ({MIN_EXCERPT_SIZE}-{MAX_EXCERPT_SIZE}) "
            "или отправьте /cancel."
        )
    )
    return SETTINGS_ENTER_EXCERPT_SIZE


async def settings_save_excerpt_size(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        logger.warning("settings_save_excerpt_size skipped: missing message update")
        return ConversationHandler.END

    try:
        repository = resolve_repository(context)
    except ConfigError as error:
        logger.error("settings_save_excerpt_size failed due to configuration error: %s", error)
        await update.message.reply_text("Не удалось сохранить настройку. Попробуйте позже.")
        return ConversationHandler.END
    user = update.effective_user
    text = (update.message.text or "").strip()

    try:
        size = int(text)
    except ValueError:
        await update.message.reply_text(
            "Введите целое число от "
            f"{MIN_EXCERPT_SIZE} до {MAX_EXCERPT_SIZE}. Попробуйте снова или /cancel."
        )
        return SETTINGS_ENTER_EXCERPT_SIZE

    if not MIN_EXCERPT_SIZE <= size <= MAX_EXCERPT_SIZE:
        await update.message.reply_text(
            "Значение вне диапазона. Введите число от "
            f"{MIN_EXCERPT_SIZE} до {MAX_EXCERPT_SIZE} или /cancel."
        )
        return SETTINGS_ENTER_EXCERPT_SIZE

    if user is None:
        await update.message.reply_text("Не удалось определить пользователя. Попробуйте снова.")
        return ConversationHandler.END

    repository.set_excerpt_size(int(user.id), size)
    await update.message.reply_text(f"Готово. Новый размер отрывка: {size} символов.")
    return ConversationHandler.END


async def settings_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    del context
    if update.callback_query is not None:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Настройки не изменены.")
    else:
        if update.message is None:
            logger.warning("settings_cancel skipped: missing message and callback_query updates")
            return ConversationHandler.END
        await update.message.reply_text("Настройки не изменены.")
    return ConversationHandler.END


def build_settings_conversation_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("settings", settings_start)],
        states={
            SETTINGS_SELECT: [
                CallbackQueryHandler(
                    settings_choose_excerpt_size,
                    pattern=f"^{SETTINGS_CALLBACK_EXCERPT_SIZE}$",
                )
            ],
            SETTINGS_ENTER_EXCERPT_SIZE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, settings_save_excerpt_size)
            ],
        },
        fallbacks=[CommandHandler("cancel", settings_cancel)],
    )
