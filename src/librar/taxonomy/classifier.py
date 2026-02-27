"""Keyword-based book classifier using a JSON thesaurus."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_THESAURUS_PATH = Path(__file__).parent / "thesaurus.json"
_WORD_RE = re.compile(r"\b\w+\b", re.UNICODE)


@dataclass(slots=True)
class CategoryMatch:
    category_id: int
    name: str
    score: float


@lru_cache(maxsize=1)
def _load_thesaurus() -> dict:
    return json.loads(_THESAURUS_PATH.read_text(encoding="utf-8"))


def classify_text(
    text: str,
    *,
    top_n: int = 3,
    min_score: float = 0.01,
) -> list[CategoryMatch]:
    """Return top-N category matches for the given text.

    Scoring: (number of matched keywords) / (total unique words in text).
    Only categories with score >= *min_score* are returned.

    Parameters
    ----------
    text:
        Representative text sample for a book (e.g. first N chunks joined).
    top_n:
        Maximum number of categories to return.
    min_score:
        Minimum overlap score required for a category to be included.
    """
    if not text or not text.strip():
        return []

    thesaurus = _load_thesaurus()
    cats_by_id: dict[int, dict] = {c["id"]: c for c in thesaurus["categories"]}
    kw_by_cat: dict[int, list[str]] = {
        int(k): v for k, v in thesaurus["keywords"].items()
    }

    words = {w.lower() for w in _WORD_RE.findall(text)}
    total = max(len(words), 1)

    scores: dict[int, float] = {}
    for cat_id, keywords in kw_by_cat.items():
        matched = sum(1 for kw in keywords if kw.lower() in words)
        if matched > 0:
            scores[cat_id] = matched / total

    results = [
        CategoryMatch(
            category_id=cat_id,
            name=cats_by_id[cat_id]["name"],
            score=score,
        )
        for cat_id, score in sorted(scores.items(), key=lambda x: -x[1])
        if score >= min_score and cat_id in cats_by_id
    ]
    return results[:top_n]
