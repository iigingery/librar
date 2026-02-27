"""Tests for pre-revolutionary Russian orthography normalization."""

from __future__ import annotations

from librar.search.prerev_normalization import (
    has_prerev_characters,
    normalize_prerev_to_modern,
)


# ---------------------------------------------------------------------------
# has_prerev_characters
# ---------------------------------------------------------------------------

def test_detects_yat() -> None:
    assert has_prerev_characters("Сѣверъ")


def test_detects_fita() -> None:
    assert has_prerev_characters("Ѳеодоръ")


def test_detects_decimal_i() -> None:
    assert has_prerev_characters("міръ")


def test_detects_izhitsa() -> None:
    assert has_prerev_characters("мѵро")


def test_modern_text_has_no_prerev_chars() -> None:
    assert not has_prerev_characters("Север")
    assert not has_prerev_characters("Обычный современный текст")


def test_empty_string_has_no_prerev_chars() -> None:
    assert not has_prerev_characters("")


# ---------------------------------------------------------------------------
# normalize_prerev_to_modern: character mappings
# ---------------------------------------------------------------------------

def test_yat_maps_to_ye() -> None:
    result = normalize_prerev_to_modern("Сѣверъ")
    assert "е" in result
    assert "ѣ" not in result


def test_fita_maps_to_ef() -> None:
    result = normalize_prerev_to_modern("Ѳеодоръ")
    assert "ф" in result.lower()
    assert "ѳ" not in result


def test_decimal_i_maps_to_i() -> None:
    result = normalize_prerev_to_modern("міръ")
    assert "и" in result
    assert "і" not in result


def test_izhitsa_maps_to_i() -> None:
    result = normalize_prerev_to_modern("мѵро")
    assert "и" in result
    assert "ѵ" not in result


# ---------------------------------------------------------------------------
# normalize_prerev_to_modern: terminal hard sign
# ---------------------------------------------------------------------------

def test_strips_terminal_hard_sign() -> None:
    result = normalize_prerev_to_modern("Сѣверъ")
    assert not result.endswith("ъ")


def test_does_not_strip_internal_hard_sign() -> None:
    # "съезд" — internal ъ must be preserved
    result = normalize_prerev_to_modern("съезд")
    assert "ъ" in result


# ---------------------------------------------------------------------------
# normalize_prerev_to_modern: modern text is unchanged
# ---------------------------------------------------------------------------

def test_modern_text_is_returned_unchanged() -> None:
    text = "Обычный современный текст без устаревших букв"
    assert normalize_prerev_to_modern(text) == text


def test_empty_string_is_returned_unchanged() -> None:
    assert normalize_prerev_to_modern("") == ""
