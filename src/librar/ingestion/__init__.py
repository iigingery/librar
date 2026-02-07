"""Ingestion package interfaces."""

from .ingestor import DocumentIngestor, IngestionError

__all__ = ["DocumentIngestor", "IngestionError"]
