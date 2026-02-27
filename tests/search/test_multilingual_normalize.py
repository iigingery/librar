"""Tests for language-conditional text normalization."""

from __future__ import annotations

from librar.search.normalize import normalize_query, normalize_text


# ---------------------------------------------------------------------------
# Russian (default)
# ---------------------------------------------------------------------------

def test_russian_lemmatizes_inflected_forms() -> None:
    result = normalize_text("книга книги КНИГУ", language="ru")
    assert result == "книга книга книга"


def test_russian_is_default_when_language_omitted() -> None:
    assert normalize_text("книга") == normalize_text("книга", language="ru")


def test_russian_yo_folding() -> None:
    result = normalize_text("Ёжик и ёлки", language="ru")
    assert "ё" not in result


def test_russian_prerev_text_is_normalized_for_lemma() -> None:
    # Pre-revolutionary ѣ must be mapped before lemmatization
    result = normalize_text("Сѣверъ", language="ru")
    assert "ѣ" not in result
    assert "ъ" not in result.split()[-1] if result else True


# ---------------------------------------------------------------------------
# Kazakh / Tatar (passthrough tokenization, no stemming)
# ---------------------------------------------------------------------------

def test_kazakh_is_lowercased() -> None:
    result = normalize_text("КІТАП кітаптар", language="kk")
    assert "кітап" in result


def test_tatar_is_lowercased() -> None:
    result = normalize_text("КИТАП китаплар", language="tt")
    assert "китап" in result


def test_kazakh_returns_tokens_not_empty() -> None:
    result = normalize_text("тарих мәдениет", language="kk")
    assert result.strip() != ""


# ---------------------------------------------------------------------------
# English
# ---------------------------------------------------------------------------

def test_english_is_lowercased() -> None:
    result = normalize_text("Books and Libraries", language="en")
    assert result == "books and libraries"


def test_english_query_matches_normalize_text() -> None:
    assert normalize_text("History Books", language="en") == normalize_query(
        "History Books", language="en"
    )


# ---------------------------------------------------------------------------
# Unknown language falls back to Russian
# ---------------------------------------------------------------------------

def test_unknown_language_code_falls_back_to_russian() -> None:
    # Should not raise; falls back to pymorphy2
    result = normalize_text("книги", language="zz")
    assert "книга" in result


# ---------------------------------------------------------------------------
# normalize_query mirrors normalize_text
# ---------------------------------------------------------------------------

def test_normalize_query_uses_same_language_dispatch() -> None:
    for lang in ("ru", "kk", "tt", "en"):
        text = "история"
        assert normalize_text(text, language=lang) == normalize_query(
            text, language=lang
        )
