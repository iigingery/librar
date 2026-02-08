"""Score normalization and fusion utilities for hybrid search."""

from __future__ import annotations

from collections.abc import Mapping


def _normalize(values: Mapping[int, float], *, higher_is_better: bool) -> dict[int, float]:
    if not values:
        return {}

    raw_values = list(values.values())
    minimum = min(raw_values)
    maximum = max(raw_values)

    if minimum == maximum:
        return {key: 1.0 for key in values}

    span = maximum - minimum
    if higher_is_better:
        return {key: (value - minimum) / span for key, value in values.items()}

    return {key: (maximum - value) / span for key, value in values.items()}


def normalize_keyword_ranks(keyword_ranks: Mapping[int, float]) -> dict[int, float]:
    """Normalize BM25/FTS ranks (lower is better) to [0..1] relevance."""

    return _normalize(keyword_ranks, higher_is_better=False)


def normalize_semantic_scores(semantic_scores: Mapping[int, float]) -> dict[int, float]:
    """Normalize semantic similarity scores (higher is better) to [0..1] relevance."""

    return _normalize(semantic_scores, higher_is_better=True)


def fuse_normalized_scores(
    keyword_scores: Mapping[int, float],
    semantic_scores: Mapping[int, float],
    *,
    alpha: float = 0.7,
    exact_match_ids: set[int] | None = None,
    exact_match_boost: float = 0.08,
) -> dict[int, float]:
    """Fuse normalized score maps into one comparable ranking score."""

    if not 0.0 <= alpha <= 1.0:
        raise ValueError("alpha must be between 0.0 and 1.0")
    if exact_match_boost < 0.0:
        raise ValueError("exact_match_boost cannot be negative")

    exact_set = exact_match_ids or set()
    chunk_ids = set(keyword_scores) | set(semantic_scores)
    fused: dict[int, float] = {}

    for chunk_id in chunk_ids:
        keyword_score = float(keyword_scores.get(chunk_id, 0.0))
        semantic_score = float(semantic_scores.get(chunk_id, 0.0))
        blended = (1.0 - alpha) * keyword_score + alpha * semantic_score

        if chunk_id in exact_set and keyword_score > 0.0:
            blended += exact_match_boost

        fused[chunk_id] = blended

    return fused


def order_fused_scores(
    fused_scores: Mapping[int, float],
    *,
    tie_breakers: Mapping[int, tuple[object, ...]] | None = None,
) -> list[int]:
    """Return deterministically ordered chunk ids by fused score."""

    tie_map = tie_breakers or {}
    return sorted(
        fused_scores,
        key=lambda chunk_id: (
            -float(fused_scores[chunk_id]),
            tie_map.get(chunk_id, (chunk_id,)),
            chunk_id,
        ),
    )
