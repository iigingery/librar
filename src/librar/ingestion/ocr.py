"""Tesseract OCR integration for scanned PDF pages.

pytesseract and Pillow are soft dependencies: they are imported only inside
``_ocr_page()``.  If Tesseract is not installed the module still works —
the first scanned page logs a single warning, all subsequent scanned pages
are silently skipped (``OcrStatus.OCR_SKIPPED``), and embedded-text pages
are never affected.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

import pymupdf


logger = logging.getLogger(__name__)

# Minimum ratio of text characters to page area (pt²) to consider a page as
# having embedded text.  Pages below this threshold are candidates for OCR.
# At 72 DPI an A4 page is ~595×842 ≈ 501 000 pt², so threshold 0.001 fires
# OCR only on pages with fewer than ~500 embedded characters.
DEFAULT_COVERAGE_THRESHOLD = 0.001

_TESSERACT_LANG = "kaz+rus+tat+eng"

# Three-state flag tracking Tesseract availability for the current process.
#   None  — not yet probed
#   True  — Tesseract executed successfully at least once
#   False — Tesseract is not installed / not in PATH
_tesseract_available: bool | None = None


class OcrStatus(Enum):
    EMBEDDED = "embedded"       # page had sufficient embedded text, OCR skipped
    OCR_SUCCESS = "ocr_success"
    OCR_FAILED = "ocr_failed"   # Tesseract raised an unexpected exception
    OCR_EMPTY = "ocr_empty"     # Tesseract ran but returned no text
    OCR_SKIPPED = "ocr_skipped" # Tesseract not installed — OCR intentionally skipped


@dataclass(slots=True)
class PageOcrResult:
    page_index: int
    status: OcrStatus
    text: str
    reason: str | None = None


def _page_text_coverage(page: pymupdf.Page, text: str) -> float:
    """Return ratio of text character count to page area (chars / pt²)."""
    rect = page.rect
    area = rect.width * rect.height
    if area == 0:
        return 0.0
    return len(text) / area


def _is_scanned_page(page: pymupdf.Page, text: str, *, threshold: float) -> bool:
    """Return True when the page appears to lack embedded text."""
    return _page_text_coverage(page, text) < threshold


def _is_tesseract_not_found(exc: Exception) -> bool:
    """Return True when *exc* indicates that the Tesseract binary is missing."""
    # pytesseract raises pytesseract.TesseractNotFoundError, a subclass of
    # EnvironmentError.  We check by class name to avoid importing pytesseract
    # at module level (it's a soft dependency).
    if "TesseractNotFoundError" in type(exc).__name__:
        return True
    msg = str(exc).lower()
    return "tesseract is not installed" in msg or "tesseract is not in your path" in msg


def _ocr_page(page: pymupdf.Page) -> str:
    """Render *page* at 300 DPI and run Tesseract OCR.  Returns raw OCR text."""
    import io

    import pytesseract
    from PIL import Image

    # Render at 300 DPI; pymupdf base resolution is 72 DPI
    mat = pymupdf.Matrix(300 / 72, 300 / 72)
    pix = page.get_pixmap(matrix=mat, colorspace=pymupdf.csRGB)
    image = Image.open(io.BytesIO(pix.tobytes("png")))
    return pytesseract.image_to_string(
        image,
        lang=_TESSERACT_LANG,
        config="--oem 3 --psm 6",
    )


def extract_page_text(
    page: pymupdf.Page,
    page_index: int,
    *,
    coverage_threshold: float = DEFAULT_COVERAGE_THRESHOLD,
) -> PageOcrResult:
    """Return text for one page, falling back to OCR when embedded text is absent.

    When Tesseract is not installed:
    - The *first* scanned page logs a single ``WARNING`` and returns
      ``OcrStatus.OCR_SKIPPED``.
    - All *subsequent* scanned pages return ``OcrStatus.OCR_SKIPPED``
      immediately (no logging, no exception).

    Parameters
    ----------
    page:
        An open ``pymupdf.Page`` object.
    page_index:
        1-based page number (for diagnostic messages).
    coverage_threshold:
        Minimum chars/pt² ratio to consider a page as having real embedded
        text.  Below this value OCR is attempted.
    """
    global _tesseract_available

    embedded_text = page.get_text("text")

    if not _is_scanned_page(page, embedded_text, threshold=coverage_threshold):
        return PageOcrResult(
            page_index=page_index,
            status=OcrStatus.EMBEDDED,
            text=embedded_text,
        )

    # Fast path: we already know Tesseract is not available — skip silently.
    if _tesseract_available is False:
        return PageOcrResult(
            page_index=page_index,
            status=OcrStatus.OCR_SKIPPED,
            text=embedded_text,
        )

    # Scanned page — attempt OCR.
    try:
        ocr_text = _ocr_page(page).strip()
    except Exception as exc:
        if _is_tesseract_not_found(exc):
            _tesseract_available = False
            logger.warning(
                "Tesseract is not installed or not in PATH — OCR disabled for this run. "
                "Scanned pages will fall back to embedded text only. "
                "See README for optional Tesseract installation instructions."
            )
            return PageOcrResult(
                page_index=page_index,
                status=OcrStatus.OCR_SKIPPED,
                text=embedded_text,
            )
        # Any other OCR error (e.g. corrupted image, language pack missing).
        return PageOcrResult(
            page_index=page_index,
            status=OcrStatus.OCR_FAILED,
            text=embedded_text,
            reason=str(exc),
        )

    # Mark Tesseract as available on first successful call.
    _tesseract_available = True

    if not ocr_text:
        return PageOcrResult(
            page_index=page_index,
            status=OcrStatus.OCR_EMPTY,
            text=embedded_text,
            reason="Tesseract returned empty output",
        )

    return PageOcrResult(
        page_index=page_index,
        status=OcrStatus.OCR_SUCCESS,
        text=ocr_text,
    )
