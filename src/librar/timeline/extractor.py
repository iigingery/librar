"""Temporal expression extraction from text (primarily Russian-language).

Patterns are applied in priority order — ranges first, then single years,
decades, centuries.  Overlapping matches are deduplicated via covered-span
tracking.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(slots=True)
class TemporalSpan:
    """Extracted temporal reference normalized to a year range."""

    year_from: int | None
    year_to: int | None
    decade: int | None       # e.g. 1840 for "1840-е годы"
    century: int | None      # e.g. 19 for "XIX век"
    source_fragment: str     # the matched text as it appeared
    is_approximate: bool
    confidence: float


# ---------------------------------------------------------------------------
# Pattern library
# ---------------------------------------------------------------------------

# Year range: "1914–1918", "1917-1922"
_YEAR_RANGE_RE = re.compile(
    r"\b(1[0-9]{3}|20[0-2][0-9])[\s]*[-–—][\s]*(1[0-9]{3}|20[0-2][0-9])\b"
)

# Four-digit year: "в 1917 году", "после 1825"
_YEAR_RE = re.compile(r"\b(1[0-9]{3}|20[0-2][0-9])\b")

# Full decade: "1840-е годы", "1840-х годах", "в 1840-е"
_DECADE_FULL_RE = re.compile(
    r"\b(1[0-9]{2}0)[-–]?е(?:[\s\-]+год[аы]?)?\b", re.IGNORECASE
)

# Roman numeral centuries: "XIX век", "XVIII–XIX вв.", "XX столетие"
_ROMAN_CENTURY_RE = re.compile(
    r"\b(X{0,3}(?:IX|IV|V?I{0,3}))"
    r"(?:[\s]*[-–—][\s]*(X{0,3}(?:IX|IV|V?I{0,3})))?"
    r"[\s]+(?:вв?\.?|в(?:ека?|\.)|столетии?)\b",
    re.IGNORECASE,
)

# Approximate markers in Russian
_APPROX_WORDS_RE = re.compile(
    r"\b(около|примерно|приблизительно|ок\.|кон\.|нач\.|сер\.)\b",
    re.IGNORECASE,
)

_ROMAN_VALUES = {
    "I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000,
}


def _roman_to_int(roman: str) -> int:
    roman = roman.upper().strip()
    total = 0
    prev = 0
    for ch in reversed(roman):
        val = _ROMAN_VALUES.get(ch, 0)
        if val < prev:
            total -= val
        else:
            total += val
        prev = val
    return total


def _century_to_year_range(century: int) -> tuple[int, int]:
    """Convert 1-based century number to (year_from, year_to)."""
    return (century - 1) * 100 + 1, century * 100


def _has_approx_context(text: str, match_start: int, *, window: int = 30) -> bool:
    """Return True if an approximation marker precedes the match."""
    context = text[max(0, match_start - window): match_start]
    return bool(_APPROX_WORDS_RE.search(context))


def _is_covered(start: int, end: int, covered: set[tuple[int, int]]) -> bool:
    for cs, ce in covered:
        if start < ce and end > cs:
            return True
    return False


def extract_temporal_spans(text: str) -> list[TemporalSpan]:
    """Extract all temporal references from *text* and return normalized spans.

    Patterns are applied in priority order: ranges first, then single
    years, decades, centuries.  Overlapping positions are skipped.
    """
    spans: list[TemporalSpan] = []
    covered: set[tuple[int, int]] = set()

    # 1. Year ranges (highest confidence)
    for m in _YEAR_RANGE_RE.finditer(text):
        if _is_covered(m.start(), m.end(), covered):
            continue
        y1, y2 = int(m.group(1)), int(m.group(2))
        if y1 > y2:
            y1, y2 = y2, y1
        spans.append(
            TemporalSpan(
                year_from=y1,
                year_to=y2,
                decade=None,
                century=None,
                source_fragment=m.group(0),
                is_approximate=_has_approx_context(text, m.start()),
                confidence=0.95,
            )
        )
        covered.add((m.start(), m.end()))

    # 2. Single years
    for m in _YEAR_RE.finditer(text):
        if _is_covered(m.start(), m.end(), covered):
            continue
        year = int(m.group(1))
        spans.append(
            TemporalSpan(
                year_from=year,
                year_to=year,
                decade=None,
                century=None,
                source_fragment=m.group(0),
                is_approximate=_has_approx_context(text, m.start()),
                confidence=0.9,
            )
        )
        covered.add((m.start(), m.end()))

    # 3. Full decades: "1840-е годы"
    for m in _DECADE_FULL_RE.finditer(text):
        if _is_covered(m.start(), m.end(), covered):
            continue
        decade_start = int(m.group(1))
        spans.append(
            TemporalSpan(
                year_from=decade_start,
                year_to=decade_start + 9,
                decade=decade_start,
                century=None,
                source_fragment=m.group(0),
                is_approximate=True,
                confidence=0.7,
            )
        )
        covered.add((m.start(), m.end()))

    # 4. Roman numeral centuries
    for m in _ROMAN_CENTURY_RE.finditer(text):
        if _is_covered(m.start(), m.end(), covered):
            continue
        century_from = _roman_to_int(m.group(1))
        if century_from == 0:
            continue
        century_to_str = m.group(2)
        century_to = _roman_to_int(century_to_str) if century_to_str else century_from

        y_from, _ = _century_to_year_range(century_from)
        _, y_to = _century_to_year_range(century_to)

        spans.append(
            TemporalSpan(
                year_from=y_from,
                year_to=y_to,
                decade=None,
                century=century_from,
                source_fragment=m.group(0),
                is_approximate=True,
                confidence=0.6,
            )
        )
        covered.add((m.start(), m.end()))

    return spans
