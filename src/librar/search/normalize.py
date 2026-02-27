from __future__ import annotations

import inspect
import re
from collections import namedtuple
from functools import lru_cache

from razdel import tokenize

from librar.search.prerev_normalization import (
    has_prerev_characters,
    normalize_prerev_to_modern,
)


_WORD_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁёѣѳіѵЪъ\u0400-\u04FF]+")


def _ensure_pymorphy2_compat() -> None:
    if hasattr(inspect, "getargspec"):
        return

    arg_spec = namedtuple("ArgSpec", ["args", "varargs", "keywords", "defaults"])

    def _getargspec(func):
        spec = inspect.getfullargspec(func)
        return arg_spec(spec.args, spec.varargs, spec.varkw, spec.defaults)

    inspect.getargspec = _getargspec


@lru_cache(maxsize=1)
def _get_analyzer():
    _ensure_pymorphy2_compat()
    import pymorphy2

    return pymorphy2.MorphAnalyzer()


def _normalize_to_lemmas(text: str) -> list[str]:
    """Lemmatize text using pymorphy2 (Russian morphology)."""
    analyzer = _get_analyzer()
    lemmas: list[str] = []

    for token in tokenize(text.lower().replace("ё", "е")):
        value = token.text.strip()
        if not value or not _WORD_RE.fullmatch(value):
            continue

        parses = analyzer.parse(value)
        lemma = parses[0].normal_form if parses else value
        lemmas.append(lemma.replace("ё", "е"))

    return lemmas


def _normalize_russian(text: str) -> list[str]:
    """Lemmatize Russian text, handling pre-revolutionary orthography."""
    working = text
    if has_prerev_characters(working):
        working = normalize_prerev_to_modern(working)
    return _normalize_to_lemmas(working)


def _normalize_kazakh_or_tatar(text: str) -> list[str]:
    """Minimal tokenization for Kazakh/Tatar — no stemming applied.

    The FTS5 unicode61 tokenizer handles further normalization at query
    time.  Returns lowercased word tokens only.
    """
    tokens: list[str] = []
    for token in tokenize(text.lower()):
        value = token.text.strip()
        if value and re.match(r"[\w]+", value, re.UNICODE):
            tokens.append(value)
    return tokens


def _normalize_english(text: str) -> list[str]:
    """Simple lowercase tokenization for English."""
    tokens: list[str] = []
    for token in tokenize(text.lower()):
        value = token.text.strip()
        if value and _WORD_RE.fullmatch(value):
            tokens.append(value)
    return tokens


def normalize_text(text: str, *, language: str = "ru") -> str:
    """Return space-joined lemma tokens for the given language.

    Parameters
    ----------
    text:
        The raw text to normalize.
    language:
        ISO 639-1 code.  Supported: ``'ru'``, ``'kk'``, ``'tt'``, ``'en'``.
        Unknown codes fall back to Russian morphology.
    """
    if language in ("kk", "tt"):
        tokens = _normalize_kazakh_or_tatar(text)
    elif language == "en":
        tokens = _normalize_english(text)
    else:
        tokens = _normalize_russian(text)
    return " ".join(tokens)


def normalize_query(query: str, *, language: str = "ru") -> str:
    """Normalize a search query using language-appropriate rules."""
    return normalize_text(query, language=language)
