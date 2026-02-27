"""Tesseract OCR integration for scanned PDF pages.

pytesseract and Pillow are soft dependencies: they are imported only inside
``_ocr_page()``.  If Tesseract is not installed the module still works — scanned
pages fall back to whatever sparse embedded text pymupdf found.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import pymupdf


# Minimum ratio of text characters to page area (pt²) to consider a page as
# having embedded text.  Pages below this threshold are candidates for OCR.
# At 72 DPI an A4 page is ~595×842 ≈ 501 000 pt², so threshold 0.001 fires
# OCR only on pages with fewer than ~500 embedded characters.
DEFAULT_COVERAGE_THRESHOLD = 0.001

_TESSERACT_LANG = "kaz+rus+tat+eng"


class OcrStatus(Enum):
    EMBEDDED = "embedded"       # page had sufficient embedded text, OCR skipped
    OCR_SUCCESS = "ocr_success"
    OCR_FAILED = "ocr_failed"   # Tesseract raised an exception
    OCR_EMPTY = "ocr_empty"     # Tesseract ran but returned no text


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
    embedded_text = page.get_text("text")

    if not _is_scanned_page(page, embedded_text, threshold=coverage_threshold):
        return PageOcrResult(
            page_index=page_index,
            status=OcrStatus.EMBEDDED,
            text=embedded_text,
        )

    # Scanned page — attempt OCR
    try:
        ocr_text = _ocr_page(page).strip()
    except Exception as exc:
        return PageOcrResult(
            page_index=page_index,
            status=OcrStatus.OCR_FAILED,
            text=embedded_text,   # fall back to (sparse) embedded text
            reason=str(exc),
        )

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
