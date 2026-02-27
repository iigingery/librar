"""Language detection for multilingual document ingestion (kk/ru/tt/en)."""

from __future__ import annotations

from functools import lru_cache

_LINGUA_TO_ISO: dict[str, str] = {
    "KAZAKH": "kk",
    "RUSSIAN": "ru",
    "TATAR": "tt",
    "ENGLISH": "en",
}
_SUPPORTED_LANGUAGES = frozenset(_LINGUA_TO_ISO.values())
_FALLBACK_LANGUAGE = "ru"


@lru_cache(maxsize=1)
def _get_detector():
    from lingua import Language, LanguageDetectorBuilder

    return (
        LanguageDetectorBuilder.from_languages(
            Language.KAZAKH,
            Language.RUSSIAN,
            Language.TATAR,
            Language.ENGLISH,
        )
        .with_minimum_relative_distance(0.1)
        .build()
    )


def detect_language(text: str, *, sample_chars: int = 3000) -> str:
    """Return ISO 639-1 language code for *text*.

    Uses up to *sample_chars* characters from the start of *text* for
    speed.  Falls back to ``"ru"`` when detection is inconclusive or the
    detected language is not in the supported set.
    """
    if not text:
        return _FALLBACK_LANGUAGE

    sample = text[:sample_chars].strip()
    if not sample:
        return _FALLBACK_LANGUAGE

    detector = _get_detector()
    result = detector.detect_language_of(sample)
    if result is None:
        return _FALLBACK_LANGUAGE

    iso = _LINGUA_TO_ISO.get(result.name.upper(), _FALLBACK_LANGUAGE)
    return iso if iso in _SUPPORTED_LANGUAGES else _FALLBACK_LANGUAGE
