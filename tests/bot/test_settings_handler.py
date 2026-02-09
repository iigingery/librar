from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from telegram.ext import ConversationHandler

from librar.bot.handlers.settings import (
    SETTINGS_CALLBACK_EXCERPT_SIZE,
    SETTINGS_ENTER_EXCERPT_SIZE,
    SETTINGS_SELECT,
    build_settings_conversation_handler,
    settings_cancel,
    settings_choose_excerpt_size,
    settings_save_excerpt_size,
    settings_start,
)
from librar.bot.repository import BotRepository, DEFAULT_EXCERPT_SIZE


class DummyMessage:
    def __init__(self, text: str | None = None) -> None:
        self.text = text
        self.replies: list[dict[str, Any]] = []

    async def reply_text(self, text: str, reply_markup: Any = None) -> None:
        self.replies.append({"text": text, "reply_markup": reply_markup})


class DummyCallbackQuery:
    def __init__(self) -> None:
        self.answered = False
        self.edited_messages: list[str] = []

    async def answer(self) -> None:
        self.answered = True

    async def edit_message_text(self, text: str) -> None:
        self.edited_messages.append(text)


def _context(repository: BotRepository) -> SimpleNamespace:
    return SimpleNamespace(bot_data={"repository": repository})


def test_settings_start_prompts_with_current_value_and_short_callback(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"

    with BotRepository(db_path) as repository:
        message = DummyMessage()
        update = SimpleNamespace(
            message=message,
            callback_query=None,
            effective_user=SimpleNamespace(id=555),
        )

        state = asyncio.run(settings_start(update, _context(repository)))

    assert state == SETTINGS_SELECT
    assert len(message.replies) == 1
    reply = message.replies[0]
    assert str(DEFAULT_EXCERPT_SIZE) in reply["text"]
    keyboard = reply["reply_markup"].inline_keyboard
    callback_data = keyboard[0][0].callback_data
    assert callback_data == SETTINGS_CALLBACK_EXCERPT_SIZE
    assert len(callback_data) < 64


def test_settings_save_retries_on_invalid_input_then_persists_valid_value(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"

    with BotRepository(db_path) as repository:
        invalid_text_update = SimpleNamespace(
            message=DummyMessage("abc"),
            callback_query=None,
            effective_user=SimpleNamespace(id=777),
        )
        state_invalid_text = asyncio.run(
            settings_save_excerpt_size(invalid_text_update, _context(repository))
        )

        invalid_range_update = SimpleNamespace(
            message=DummyMessage("999"),
            callback_query=None,
            effective_user=SimpleNamespace(id=777),
        )
        state_invalid_range = asyncio.run(
            settings_save_excerpt_size(invalid_range_update, _context(repository))
        )

        valid_update = SimpleNamespace(
            message=DummyMessage("320"),
            callback_query=None,
            effective_user=SimpleNamespace(id=777),
        )
        state_valid = asyncio.run(settings_save_excerpt_size(valid_update, _context(repository)))

        persisted = repository.get_excerpt_size(777)

    assert state_invalid_text == SETTINGS_ENTER_EXCERPT_SIZE
    assert "Введите целое число" in invalid_text_update.message.replies[-1]["text"]

    assert state_invalid_range == SETTINGS_ENTER_EXCERPT_SIZE
    assert "вне диапазона" in invalid_range_update.message.replies[-1]["text"]

    assert state_valid == ConversationHandler.END
    assert persisted == 320
    assert "320" in valid_update.message.replies[-1]["text"]


def test_settings_choose_and_cancel_paths_complete_conversation(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"

    with BotRepository(db_path) as repository:
        callback = DummyCallbackQuery()
        choose_update = SimpleNamespace(
            message=None,
            callback_query=callback,
            effective_user=SimpleNamespace(id=888),
        )

        choose_state = asyncio.run(settings_choose_excerpt_size(choose_update, _context(repository)))

        cancel_message = DummyMessage()
        cancel_update_message = SimpleNamespace(
            message=cancel_message,
            callback_query=None,
            effective_user=SimpleNamespace(id=888),
        )
        cancel_message_state = asyncio.run(
            settings_cancel(cancel_update_message, _context(repository))
        )

        cancel_callback = DummyCallbackQuery()
        cancel_update_callback = SimpleNamespace(
            message=None,
            callback_query=cancel_callback,
            effective_user=SimpleNamespace(id=888),
        )
        cancel_callback_state = asyncio.run(
            settings_cancel(cancel_update_callback, _context(repository))
        )

    assert choose_state == SETTINGS_ENTER_EXCERPT_SIZE
    assert callback.answered is True
    assert "Введите новый размер" in callback.edited_messages[-1]

    assert cancel_message_state == ConversationHandler.END
    assert "не изменены" in cancel_message.replies[-1]["text"]

    assert cancel_callback_state == ConversationHandler.END
    assert cancel_callback.answered is True
    assert "не изменены" in cancel_callback.edited_messages[-1]


def test_build_settings_conversation_handler_registers_expected_states() -> None:
    handler = build_settings_conversation_handler()

    assert isinstance(handler, ConversationHandler)
    assert SETTINGS_SELECT in handler.states
    assert SETTINGS_ENTER_EXCERPT_SIZE in handler.states
