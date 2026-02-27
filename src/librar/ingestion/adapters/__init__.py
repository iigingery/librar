"""Ingestion adapter implementations and contracts."""

import logging

from .base import IngestionAdapter

logger = logging.getLogger(__name__)

try:
    from .pdf_adapter import PDFAdapter
except ImportError:
    PDFAdapter = None
    logger.warning("PDF support unavailable: install 'pymupdf'")

try:
    from .epub_adapter import EPUBAdapter
except ImportError:
    EPUBAdapter = None
    logger.warning("EPUB support unavailable: install 'EbookLib'")

try:
    from .fb2_adapter import FB2Adapter
except ImportError:
    FB2Adapter = None
    logger.warning("FB2 support unavailable: install 'lxml'")

try:
    from .txt_adapter import TXTAdapter
except ImportError:
    TXTAdapter = None
    logger.warning("TXT support unavailable: install 'charset-normalizer'")


def build_default_adapters() -> dict[str, IngestionAdapter]:
    """Return the default format adapter map for phase-1 ingestion."""
    adapters: dict[str, IngestionAdapter] = {}
    if PDFAdapter is not None:
        adapters["pdf"] = PDFAdapter()
    if EPUBAdapter is not None:
        adapters["epub"] = EPUBAdapter()
    if FB2Adapter is not None:
        adapters["fb2"] = FB2Adapter()
    if TXTAdapter is not None:
        adapters["txt"] = TXTAdapter()
    return adapters


__all__ = [
    "IngestionAdapter",
    "PDFAdapter",
    "EPUBAdapter",
    "FB2Adapter",
    "TXTAdapter",
    "build_default_adapters",
]
