from __future__ import annotations

import inspect
import re
from collections import namedtuple
from functools import lru_cache

from razdel import tokenize


_WORD_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё]+")


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


def normalize_text(text: str) -> str:
    return " ".join(_normalize_to_lemmas(text))


def normalize_query(query: str) -> str:
    return " ".join(_normalize_to_lemmas(query))
