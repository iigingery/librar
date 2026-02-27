"""Tests for the language detection module (without lingua installed)."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch


def _make_lingua_stub(detected_name: str | None) -> types.ModuleType:
    """Build a minimal lingua stub that returns a fixed detection result."""
    lingua = types.ModuleType("lingua")

    class Language:
        KAZAKH = "kk"
        RUSSIAN = "ru"
        TATAR = "tt"
        ENGLISH = "en"

    class _Result:
        def __init__(self, name: str) -> None:
            self.name = name

    class _Builder:
        def from_languages(self, *_):
            return self

        def with_minimum_relative_distance(self, _):
            return self

        def build(self):
            return self

        def detect_language_of(self, _text: str):
            if detected_name is None:
                return None
            return _Result(detected_name)

    class LanguageDetectorBuilder:
        @staticmethod
        def from_languages(*_args):
            return _Builder()

    lingua.Language = Language
    lingua.LanguageDetectorBuilder = LanguageDetectorBuilder
    return lingua


def _import_fresh(stub: types.ModuleType):
    """Return a freshly-imported detect_language with the given lingua stub."""
    # Remove cached module so the lru_cache'd detector is rebuilt
    for key in list(sys.modules.keys()):
        if "language_detection" in key:
            del sys.modules[key]

    sys.modules["lingua"] = stub
    from librar.ingestion.language_detection import detect_language

    return detect_language


def test_detects_russian() -> None:
    lingua_stub = _make_lingua_stub("RUSSIAN")
    detect = _import_fresh(lingua_stub)
    assert detect("длинный текст на русском языке") == "ru"


def test_detects_kazakh() -> None:
    lingua_stub = _make_lingua_stub("KAZAKH")
    detect = _import_fresh(lingua_stub)
    assert detect("қазақ тіліндегі ұзын мәтін") == "kk"


def test_detects_tatar() -> None:
    lingua_stub = _make_lingua_stub("TATAR")
    detect = _import_fresh(lingua_stub)
    assert detect("татар телендәге озын текст") == "tt"


def test_detects_english() -> None:
    lingua_stub = _make_lingua_stub("ENGLISH")
    detect = _import_fresh(lingua_stub)
    assert detect("a long english text for detection") == "en"


def test_empty_string_returns_fallback() -> None:
    lingua_stub = _make_lingua_stub("RUSSIAN")
    detect = _import_fresh(lingua_stub)
    assert detect("") == "ru"


def test_whitespace_only_returns_fallback() -> None:
    lingua_stub = _make_lingua_stub("RUSSIAN")
    detect = _import_fresh(lingua_stub)
    assert detect("   \n\t  ") == "ru"


def test_none_result_returns_fallback() -> None:
    # Detector returns None (inconclusive)
    lingua_stub = _make_lingua_stub(None)
    detect = _import_fresh(lingua_stub)
    assert detect("some text") == "ru"


def test_unknown_language_name_returns_fallback() -> None:
    lingua_stub = _make_lingua_stub("UZBEK")
    detect = _import_fresh(lingua_stub)
    assert detect("matn") == "ru"


def test_sample_chars_limits_input() -> None:
    """detect_language must only pass the first sample_chars chars to the detector."""
    calls: list[str] = []

    lingua_stub = _make_lingua_stub("RUSSIAN")

    class _CapturingBuilder:
        def from_languages(self, *_):
            return self

        def with_minimum_relative_distance(self, _):
            return self

        def build(self):
            return self

        def detect_language_of(self, text: str):
            calls.append(text)

            class _Res:
                name = "RUSSIAN"

            return _Res()

    class CapturingDetectorBuilder:
        @staticmethod
        def from_languages(*_args):
            return _CapturingBuilder()

    lingua_stub.LanguageDetectorBuilder = CapturingDetectorBuilder

    detect = _import_fresh(lingua_stub)
    long_text = "а" * 10_000
    detect(long_text, sample_chars=100)

    assert calls and len(calls[-1]) <= 100
