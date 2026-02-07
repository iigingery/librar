from __future__ import annotations

import platform
import inspect
from collections import namedtuple
from importlib.metadata import PackageNotFoundError, version

import pytest


def _pkg_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "not-installed"


def _runtime_versions() -> str:
    return (
        f"python={platform.python_version()}, "
        f"pymorphy2={_pkg_version('pymorphy2')}, "
        f"pymorphy2-dicts-ru={_pkg_version('pymorphy2-dicts-ru')}, "
        f"razdel={_pkg_version('razdel')}"
    )


def _ensure_pymorphy2_compat() -> None:
    if hasattr(inspect, "getargspec"):
        return

    arg_spec = namedtuple("ArgSpec", ["args", "varargs", "keywords", "defaults"])

    def _getargspec(func):
        spec = inspect.getfullargspec(func)
        return arg_spec(spec.args, spec.varargs, spec.varkw, spec.defaults)

    inspect.getargspec = _getargspec


def test_pymorphy2_morph_analyzer_parses_russian_word_forms() -> None:
    try:
        _ensure_pymorphy2_compat()
        import pymorphy2

        analyzer = pymorphy2.MorphAnalyzer()
        parses = analyzer.parse("книги")
    except Exception as exc:  # pragma: no cover - explicit runtime guard
        pytest.fail(f"pymorphy2 runtime smoke test failed ({_runtime_versions()}): {exc}")

    assert parses, "MorphAnalyzer.parse('книги') returned no parses"
    assert any(parse.normal_form == "книга" for parse in parses)
