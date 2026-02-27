"""Tests for the temporal expression extractor."""

from __future__ import annotations

from librar.timeline.extractor import TemporalSpan, extract_temporal_spans


# ---------------------------------------------------------------------------
# Year ranges
# ---------------------------------------------------------------------------

def test_extracts_year_range_with_dash() -> None:
    spans = extract_temporal_spans("Война продолжалась 1914-1918.")
    range_spans = [s for s in spans if s.year_from == 1914 and s.year_to == 1918]
    assert range_spans
    assert range_spans[0].confidence >= 0.9


def test_extracts_year_range_with_endash() -> None:
    spans = extract_temporal_spans("Период 1917–1922 годов.")
    range_spans = [s for s in spans if s.year_from == 1917 and s.year_to == 1922]
    assert range_spans


def test_year_range_normalizes_reversed_order() -> None:
    spans = extract_temporal_spans("В 1922–1917 гг.")
    # Extractor should swap so year_from <= year_to
    range_spans = [s for s in spans if s.year_from is not None and s.year_to is not None]
    for s in range_spans:
        assert s.year_from <= s.year_to


# ---------------------------------------------------------------------------
# Single years
# ---------------------------------------------------------------------------

def test_extracts_single_year() -> None:
    spans = extract_temporal_spans("В 1917 году произошла революция.")
    year_spans = [s for s in spans if s.year_from == 1917 and s.year_to == 1917]
    assert year_spans


def test_single_year_confidence_is_high() -> None:
    spans = extract_temporal_spans("В 1991 году распался СССР.")
    year_spans = [s for s in spans if s.year_from == 1991]
    assert year_spans
    assert year_spans[0].confidence >= 0.8


def test_non_year_numbers_produce_no_spans() -> None:
    # 42 and 7 are not in the 1000–2029 range
    spans = extract_temporal_spans("В ящике было 42 книги и 7 журналов.")
    assert spans == []


# ---------------------------------------------------------------------------
# Decades
# ---------------------------------------------------------------------------

def test_extracts_full_decade() -> None:
    spans = extract_temporal_spans("В 1840-е годы произошли важные события.")
    decade_spans = [s for s in spans if s.decade == 1840]
    assert decade_spans
    assert decade_spans[0].is_approximate is True
    assert decade_spans[0].year_from == 1840
    assert decade_spans[0].year_to == 1849


def test_decade_confidence_is_moderate() -> None:
    spans = extract_temporal_spans("В 1900-е годах.")
    decade_spans = [s for s in spans if s.decade == 1900]
    assert decade_spans
    assert decade_spans[0].confidence <= 0.8


# ---------------------------------------------------------------------------
# Roman numeral centuries
# ---------------------------------------------------------------------------

def test_extracts_roman_century_xix() -> None:
    spans = extract_temporal_spans("В XIX веке развивалась культура.")
    century_spans = [s for s in spans if s.century == 19]
    assert century_spans
    assert century_spans[0].year_from == 1801
    assert century_spans[0].year_to == 1900


def test_extracts_roman_century_xx() -> None:
    spans = extract_temporal_spans("В XX столетии произошли войны.")
    century_spans = [s for s in spans if s.century == 20]
    assert century_spans
    assert century_spans[0].year_from == 1901
    assert century_spans[0].year_to == 2000


def test_century_is_marked_approximate() -> None:
    spans = extract_temporal_spans("В XIX веке.")
    assert all(s.is_approximate for s in spans if s.century)


# ---------------------------------------------------------------------------
# Approximate markers
# ---------------------------------------------------------------------------

def test_approx_marker_sets_flag() -> None:
    spans = extract_temporal_spans("Около 1850 года был построен город.")
    year_spans = [s for s in spans if s.year_from == 1850]
    assert year_spans
    assert year_spans[0].is_approximate is True


def test_no_approx_marker_flag_is_false() -> None:
    spans = extract_temporal_spans("В 1917 году.")
    year_spans = [s for s in spans if s.year_from == 1917]
    assert year_spans
    assert year_spans[0].is_approximate is False


# ---------------------------------------------------------------------------
# Overlap deduplication
# ---------------------------------------------------------------------------

def test_range_takes_priority_over_single_year() -> None:
    # "1914-1918" should be extracted as a range; 1914 and 1918 individually
    # must NOT also appear as separate single-year spans at the same position.
    spans = extract_temporal_spans("Первая мировая война: 1914–1918.")
    range_spans = [s for s in spans if s.year_from == 1914 and s.year_to == 1918]
    single_1914 = [s for s in spans if s.year_from == 1914 and s.year_to == 1914]
    single_1918 = [s for s in spans if s.year_from == 1918 and s.year_to == 1918]
    assert range_spans
    # The range positions should cover the individual year positions
    assert not single_1914
    assert not single_1918


# ---------------------------------------------------------------------------
# TemporalSpan fields
# ---------------------------------------------------------------------------

def test_source_fragment_preserves_matched_text() -> None:
    spans = extract_temporal_spans("В 1917 году.")
    year_spans = [s for s in spans if s.year_from == 1917]
    assert year_spans
    assert "1917" in year_spans[0].source_fragment


def test_return_type_is_temporal_span() -> None:
    spans = extract_temporal_spans("В 1917 году.")
    for s in spans:
        assert isinstance(s, TemporalSpan)
        assert s.year_from is not None or s.century is not None or s.decade is not None


def test_empty_text_returns_empty_list() -> None:
    assert extract_temporal_spans("") == []


def test_no_temporal_text_returns_empty_list() -> None:
    assert extract_temporal_spans("Это текст без дат и годов.") == []
