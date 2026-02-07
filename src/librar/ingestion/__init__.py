"""Ingestion package interfaces."""

from .ingestor import DocumentIngestor, IngestionError, IngestionResult

__all__ = ["DocumentIngestor", "IngestionError", "IngestionResult"]
