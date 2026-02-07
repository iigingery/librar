"""Ingestion adapter implementations and contracts."""

from .base import IngestionAdapter
from .epub_adapter import EPUBAdapter
from .pdf_adapter import PDFAdapter

__all__ = ["IngestionAdapter", "PDFAdapter", "EPUBAdapter"]
