"""Pre-revolutionary Russian orthography normalization.

Maps archaic Cyrillic characters to their modern equivalents for use in the
``lemma_text`` FTS field.  The ``raw_text`` field MUST always preserve the
original — never call these functions on ``raw_text``.
"""

from __future__ import annotations

import re

# Character-level substitution map (pre-revolutionary → modern)
#   ѣ (U+0463) → е  (yat → ye)
#   ѳ (U+0473) → ф  (fita → ef)
#   і (U+0456) → и  (Cyrillic і, not Latin i → i)
#   ѵ (U+0475) → и  (izhitsa → i)
_PREREV_TRANS = str.maketrans(
    "\u0463\u0473\u0456\u0475",  # ѣ ѳ і ѵ
    "\u0435\u0444\u0438\u0438",  # е ф и и
)

# Terminal hard sign (ъ) at a word boundary — strip it
_TERMINAL_HARD_SIGN_RE = re.compile(r"\u044a\b")

# Detection pattern — does this text contain any pre-revolutionary characters?
_PREREV_CHARS_RE = re.compile(r"[\u0463\u0473\u0456\u0475]")


def has_prerev_characters(text: str) -> bool:
    """Return True if *text* contains pre-revolutionary Cyrillic characters."""
    return bool(_PREREV_CHARS_RE.search(text))


def normalize_prerev_to_modern(text: str) -> str:
    """Map pre-revolutionary chars to modern equivalents and strip terminal ъ.

    Only call this function when building ``lemma_text``.
    """
    result = text.translate(_PREREV_TRANS)
    return _TERMINAL_HARD_SIGN_RE.sub("", result)
