"""Tests for shared rendering helpers used by command and callback handlers."""

from __future__ import annotations

from types import SimpleNamespace

from librar.bot.handlers.renderers import (
    build_pagination_keyboard,
    render_books_page,
    render_search_page,
)


def test_render_search_page_keeps_legacy_text_shape() -> None:
    results = (
        SimpleNamespace(display="Book 1, Page 1", excerpt="Excerpt 1"),
        SimpleNamespace(display="Book 2, Page 2", excerpt="Excerpt 2"),
        SimpleNamespace(display="Book 3, Page 3", excerpt="Excerpt 3"),
    )

    text = render_search_page(
        results=results,
        search_query="космос",
        excerpt_size=200,
        page_num=0,
        page_size=2,
    )

    expected = (
        "Найдено 3 результатов для: космос\n\n"
        "1. Book 1, Page 1\nExcerpt 1...\n\n"
        "2. Book 2, Page 2\nExcerpt 2...\n\n"
    )
    assert text == expected


def test_render_books_page_keeps_legacy_text_shape() -> None:
    items = (
        SimpleNamespace(title="Title 1", author="Author 1", format_name="pdf"),
        SimpleNamespace(title=None, author=None, format_name=None),
    )

    text = render_books_page(items=items, total=2)

    expected = (
        "Всего книг: 2\n\n"
        "• Title 1 — Author 1 (pdf)\n"
        "• Без названия — Неизвестный автор (?)\n"
    )
    assert text == expected


def test_build_pagination_keyboard_buttons_match_legacy_contract() -> None:
    markup = build_pagination_keyboard(
        prefix="search_page",
        session_key="1:100",
        page_num=1,
        has_next=True,
    )

    assert markup is not None
    buttons = markup.inline_keyboard[0]
    assert [button.text for button in buttons] == ["← Предыдущая", "Следующая →"]
    assert [button.callback_data for button in buttons] == [
        "search_page_1:100_0",
        "search_page_1:100_2",
    ]


def test_build_pagination_keyboard_returns_none_when_no_buttons() -> None:
    assert build_pagination_keyboard(prefix="books_page", session_key=None, page_num=0, has_next=False) is None
