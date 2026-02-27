"""Tests for the keyword-based book classifier."""

from __future__ import annotations

from librar.taxonomy.classifier import CategoryMatch, classify_text


# ---------------------------------------------------------------------------
# Basic matching
# ---------------------------------------------------------------------------

def test_kazakh_history_text_is_classified() -> None:
    text = (
        "история казахстан летопись архив событие казах степь батыр алаш жуз"
    )
    matches = classify_text(text, min_score=0.001)
    names = [m.name for m in matches]
    assert any("казахстан" in n.lower() or "история" in n.lower() for n in names)


def test_religion_text_matches_religion_category() -> None:
    text = "ислам мечеть коран намаз ураза рамадан хадис мулла"
    matches = classify_text(text, top_n=5, min_score=0.001)
    names = [m.name.lower() for m in matches]
    assert any("религия" in n for n in names)


def test_language_text_matches_language_category() -> None:
    text = "язык грамматика морфология синтаксис лексика диалект словарь алфавит"
    matches = classify_text(text, top_n=5, min_score=0.001)
    names = [m.name.lower() for m in matches]
    assert any("язык" in n for n in names)


# ---------------------------------------------------------------------------
# Score ordering
# ---------------------------------------------------------------------------

def test_results_are_ordered_by_descending_score() -> None:
    text = " ".join(
        ["история", "казахстан", "летопись", "казах", "степь", "алаш"] * 5
        + ["культура"]
    )
    matches = classify_text(text, top_n=5, min_score=0.001)
    scores = [m.score for m in matches]
    assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# top_n and min_score limits
# ---------------------------------------------------------------------------

def test_top_n_limits_result_count() -> None:
    text = " ".join(
        ["история", "казахстан", "культура", "язык", "ислам", "политика"] * 10
    )
    matches = classify_text(text, top_n=2, min_score=0.001)
    assert len(matches) <= 2


def test_min_score_filters_low_matches() -> None:
    # One religious keyword among many unrelated words → score is very low
    # 1 matched keyword / 50 total words = 0.02, well below 0.9
    filler = ["слово", "текст", "буква", "знак", "строка"] * 10
    text = "ислам " + " ".join(filler)
    matches = classify_text(text, top_n=5, min_score=0.9)
    assert matches == []


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_text_returns_empty() -> None:
    assert classify_text("") == []


def test_whitespace_only_returns_empty() -> None:
    assert classify_text("   \n\t  ") == []


def test_no_keyword_match_returns_empty() -> None:
    # Gibberish has no matches
    assert classify_text("zzz xxx yyy qqq", min_score=0.0001) == []


def test_return_type_is_category_match() -> None:
    text = "история казахстан летопись"
    matches = classify_text(text, min_score=0.001)
    for m in matches:
        assert isinstance(m, CategoryMatch)
        assert isinstance(m.category_id, int)
        assert isinstance(m.name, str)
        assert 0.0 < m.score <= 1.0
