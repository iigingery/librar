"""Text normalization helpers used during ingestion and dedupe."""

from __future__ import annotations

import re
import unicodedata

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_whitespace(text: str) -> str:
    """Collapse repeated whitespace and trim boundaries."""

    return _WHITESPACE_RE.sub(" ", text).strip()


def normalize_text(text: str) -> str:
    """Produce stable text for comparisons and hashing."""

    normalized = unicodedata.normalize("NFKC", text)
    return normalize_whitespace(normalized).casefold()
