"""Automation services for folder-based ingestion workflows."""

from librar.automation.ingestion_service import IngestionPipelineResult, run_ingestion_pipeline
from librar.automation.watcher import BookFolderWatcher, DebouncedBookHandler

__all__ = [
    "BookFolderWatcher",
    "DebouncedBookHandler",
    "IngestionPipelineResult",
    "run_ingestion_pipeline",
]
