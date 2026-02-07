from __future__ import annotations

from librar.search.normalize import normalize_query, normalize_text


def test_normalize_text_lemmatizes_russian_word_forms() -> None:
    assert normalize_text("книга книги КНИГУ") == "книга книга книга"


def test_normalize_text_handles_mixed_punctuation_and_yo_folding() -> None:
    assert normalize_text("Книга, книги! Книгу? Ёжик и ёлки.") == "книга книга книга ежик и елка"


def test_text_and_query_paths_share_same_normalization_contract() -> None:
    source = "Книги о Ёжике и книге"
    assert normalize_text(source) == normalize_query(source)


def test_normalization_is_idempotent() -> None:
    source = "  Книга, книги и  КНИГУ  "
    once = normalize_text(source)
    twice = normalize_text(once)

    assert once == twice
