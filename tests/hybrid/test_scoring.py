from __future__ import annotations

import pytest

from librar.hybrid.scoring import (
    fuse_normalized_scores,
    normalize_keyword_ranks,
    normalize_semantic_scores,
    order_fused_scores,
)


def test_keyword_rank_normalization_inverts_lower_is_better() -> None:
    normalized = normalize_keyword_ranks({1: -10.0, 2: -4.0, 3: -1.0})

    assert normalized[1] > normalized[2] > normalized[3]
    assert normalized[1] == pytest.approx(1.0)
    assert normalized[3] == pytest.approx(0.0)


def test_semantic_score_normalization_keeps_higher_is_better() -> None:
    normalized = normalize_semantic_scores({1: 0.2, 2: 0.4, 3: 0.9})

    assert normalized[3] > normalized[2] > normalized[1]
    assert normalized[3] == pytest.approx(1.0)
    assert normalized[1] == pytest.approx(0.0)


def test_fusion_uses_alpha_weighting_and_exact_boost() -> None:
    keyword = {1: 1.0, 2: 0.0}
    semantic = {1: 0.0, 2: 1.0}

    mostly_semantic = fuse_normalized_scores(keyword, semantic, alpha=0.8)
    mostly_keyword = fuse_normalized_scores(keyword, semantic, alpha=0.2)
    boosted = fuse_normalized_scores(keyword, semantic, alpha=0.5, exact_match_ids={1}, exact_match_boost=0.2)

    assert mostly_semantic[2] > mostly_semantic[1]
    assert mostly_keyword[1] > mostly_keyword[2]
    assert boosted[1] > boosted[2]


def test_ordering_is_deterministic_on_equal_scores() -> None:
    fused = {10: 0.7, 11: 0.7, 12: 0.5}
    order = order_fused_scores(
        fused,
        tie_breakers={
            10: ("b", 2),
            11: ("a", 1),
            12: ("c", 3),
        },
    )

    assert order == [11, 10, 12]


def test_invalid_alpha_is_rejected() -> None:
    with pytest.raises(ValueError, match="alpha"):
        fuse_normalized_scores({1: 1.0}, {1: 1.0}, alpha=1.2)
