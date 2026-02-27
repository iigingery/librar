"""Tests for the OCR pipeline (graceful degradation, coverage logic, flag states)."""

from __future__ import annotations

import importlib
import sys

import pymupdf
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reload_ocr():
    """Import ocr module fresh, resetting the module-level flag."""
    for key in list(sys.modules.keys()):
        if key == "librar.ingestion.ocr":
            del sys.modules[key]
    import librar.ingestion.ocr as ocr_mod
    return ocr_mod


def _blank_page() -> tuple[pymupdf.Document, pymupdf.Page]:
    doc = pymupdf.open()
    page = doc.new_page()
    return doc, page


def _text_page() -> tuple[pymupdf.Document, pymupdf.Page]:
    """Create a page with many lines of embedded ASCII text."""
    doc = pymupdf.open()
    page = doc.new_page()
    # Insert text at several Y positions to ensure coverage ratio exceeds
    # the DEFAULT_COVERAGE_THRESHOLD of 0.001 (chars / pt²).
    # Page area ≈ 595 × 842 ≈ 501 000 pt²; we need > 502 chars.
    for y_pos in range(72, 700, 18):
        page.insert_text((50, y_pos), "A" * 100)
    return doc, page


# ---------------------------------------------------------------------------
# Coverage threshold
# ---------------------------------------------------------------------------

def test_coverage_zero_for_blank_page() -> None:
    ocr = _reload_ocr()
    doc, page = _blank_page()
    coverage = ocr._page_text_coverage(page, "")
    doc.close()
    assert coverage == 0.0


def test_coverage_positive_for_text_page() -> None:
    ocr = _reload_ocr()
    doc, page = _text_page()
    text = page.get_text("text")
    coverage = ocr._page_text_coverage(page, text)
    doc.close()
    assert coverage > 0.0


def test_blank_page_is_scanned() -> None:
    ocr = _reload_ocr()
    doc, page = _blank_page()
    assert ocr._is_scanned_page(page, "", threshold=0.001)
    doc.close()


def test_text_page_is_not_scanned() -> None:
    ocr = _reload_ocr()
    doc, page = _text_page()
    text = page.get_text("text")
    assert not ocr._is_scanned_page(page, text, threshold=0.001)
    doc.close()


# ---------------------------------------------------------------------------
# Embedded path
# ---------------------------------------------------------------------------

def test_text_page_returns_embedded_status() -> None:
    ocr = _reload_ocr()
    doc, page = _text_page()
    result = ocr.extract_page_text(page, page_index=1)
    doc.close()
    assert result.status == ocr.OcrStatus.EMBEDDED
    assert result.text.strip()


# ---------------------------------------------------------------------------
# TesseractNotFoundError detection
# ---------------------------------------------------------------------------

def test_is_tesseract_not_found_by_class_name() -> None:
    ocr = _reload_ocr()

    class TesseractNotFoundError(Exception):
        pass

    assert ocr._is_tesseract_not_found(TesseractNotFoundError("anything"))


def test_is_tesseract_not_found_by_message() -> None:
    ocr = _reload_ocr()
    exc = Exception("tesseract is not installed or it's not in your PATH")
    assert ocr._is_tesseract_not_found(exc)


def test_is_tesseract_not_found_other_error() -> None:
    ocr = _reload_ocr()
    assert not ocr._is_tesseract_not_found(Exception("some other failure"))


# ---------------------------------------------------------------------------
# OCR_SKIPPED behaviour when Tesseract is absent
# ---------------------------------------------------------------------------

def test_first_scanned_page_logs_single_warning_when_tesseract_missing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    ocr = _reload_ocr()
    assert ocr._tesseract_available is None  # fresh state

    class TesseractNotFoundError(Exception):
        pass

    def _fake_ocr_page(_page):
        raise TesseractNotFoundError("tesseract is not installed or it's not in your PATH")

    doc, page = _blank_page()
    import logging

    with caplog.at_level(logging.WARNING, logger="librar.ingestion.ocr"):
        # Monkeypatch _ocr_page so we don't need Tesseract installed
        orig = ocr._ocr_page
        ocr._ocr_page = _fake_ocr_page
        try:
            result = ocr.extract_page_text(page, page_index=1)
        finally:
            ocr._ocr_page = orig
    doc.close()

    assert result.status == ocr.OcrStatus.OCR_SKIPPED
    assert ocr._tesseract_available is False
    # Exactly one warning was emitted
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "Tesseract" in warnings[0].message


def test_subsequent_scanned_pages_skip_silently_when_flag_false(
    caplog: pytest.LogCaptureFixture,
) -> None:
    ocr = _reload_ocr()
    ocr._tesseract_available = False  # simulate "already detected missing"

    import logging

    doc = pymupdf.open()
    with caplog.at_level(logging.WARNING, logger="librar.ingestion.ocr"):
        results = []
        for _ in range(5):
            page = doc.new_page()
            results.append(ocr.extract_page_text(page, page_index=1))
    doc.close()

    for r in results:
        assert r.status == ocr.OcrStatus.OCR_SKIPPED

    # No new warnings emitted (flag was already False before the loop)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings == []


# ---------------------------------------------------------------------------
# OCR_FAILED for unexpected errors
# ---------------------------------------------------------------------------

def test_unexpected_ocr_error_returns_ocr_failed() -> None:
    ocr = _reload_ocr()
    assert ocr._tesseract_available is None

    def _fake_ocr_page(_page):
        raise RuntimeError("Unexpected internal error")

    doc, page = _blank_page()
    orig = ocr._ocr_page
    ocr._ocr_page = _fake_ocr_page
    try:
        result = ocr.extract_page_text(page, page_index=1)
    finally:
        ocr._ocr_page = orig
    doc.close()

    assert result.status == ocr.OcrStatus.OCR_FAILED
    assert "Unexpected internal error" in (result.reason or "")
    # Flag should remain None (not set to False for non-TesseractNotFoundError)
    assert ocr._tesseract_available is None


# ---------------------------------------------------------------------------
# OcrStatus enum completeness
# ---------------------------------------------------------------------------

def test_all_expected_statuses_present() -> None:
    ocr = _reload_ocr()
    expected = {"embedded", "ocr_success", "ocr_failed", "ocr_empty", "ocr_skipped"}
    actual = {s.value for s in ocr.OcrStatus}
    assert expected == actual
