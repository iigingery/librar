"""Ingestion adapter implementations and contracts."""

from .base import IngestionAdapter
from .epub_adapter import EPUBAdapter
from .fb2_adapter import FB2Adapter
from .pdf_adapter import PDFAdapter
from .txt_adapter import TXTAdapter


def build_default_adapters() -> dict[str, IngestionAdapter]:
    """Return the default format adapter map for phase-1 ingestion."""

    return {
        "pdf": PDFAdapter(),
        "epub": EPUBAdapter(),
        "fb2": FB2Adapter(),
        "txt": TXTAdapter(),
    }

__all__ = [
    "IngestionAdapter",
    "PDFAdapter",
    "EPUBAdapter",
    "FB2Adapter",
    "TXTAdapter",
    "build_default_adapters",
]
