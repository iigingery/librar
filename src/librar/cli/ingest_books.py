"""CLI command for adapter-driven ingestion with dedupe reporting."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from librar.ingestion.adapters import build_default_adapters
from librar.ingestion.dedupe import FingerprintRegistry
from librar.ingestion.ingestor import DocumentIngestor, IngestionError

_SUPPORTED_SUFFIXES = {".pdf", ".epub", ".fb2", ".fbz", ".txt"}


def _is_supported(path: Path) -> bool:
    suffixes = [part.lower() for part in path.suffixes]
    if not suffixes:
        return False
    if suffixes[-1] in _SUPPORTED_SUFFIXES:
        return True
    return suffixes[-2:] == [".fb2", ".zip"]


def _collect_inputs(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    if target.is_dir():
        return sorted(path for path in target.rglob("*") if path.is_file() and _is_supported(path))
    return []


def _load_registry(cache_path: Path) -> FingerprintRegistry:
    registry = FingerprintRegistry()
    if not cache_path.exists():
        return registry

    data = json.loads(cache_path.read_text(encoding="utf-8"))
    registry.seed(
        binary_hashes=set(data.get("binary_hashes", [])),
        normalized_text_hashes=set(data.get("normalized_text_hashes", [])),
    )
    return registry


def _save_registry(cache_path: Path, registry: FingerprintRegistry) -> None:
    cache_path.write_text(json.dumps(registry.snapshot(), ensure_ascii=False, indent=2), encoding="utf-8")


def _build_ingestor(registry: FingerprintRegistry) -> DocumentIngestor:
    ingestor = DocumentIngestor(fingerprint_registry=registry)
    for name, adapter in build_default_adapters().items():
        ingestor.register_adapter(name, adapter)
    return ingestor


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest books and emit chunk/dedupe status")
    parser.add_argument("--path", required=True, help="Source file or directory")
    parser.add_argument(
        "--cache-file",
        default=".librar-ingestion-cache.json",
        help="Path to persisted dedupe fingerprint cache",
    )
    args = parser.parse_args(argv)

    source_path = Path(args.path)
    cache_path = Path(args.cache_file)
    files = _collect_inputs(source_path)

    registry = _load_registry(cache_path)
    ingestor = _build_ingestor(registry)

    results: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []

    for file_path in files:
        try:
            ingested = ingestor.ingest(file_path)
        except IngestionError as exc:
            errors.append({"source_path": str(file_path), "error": str(exc)})
            continue

        results.append(
            {
                "source_path": ingested.document.source_path,
                "title": ingested.document.metadata.title,
                "author": ingested.document.metadata.author,
                "format": ingested.document.metadata.format,
                "chunk_count": len(ingested.chunks),
                "is_duplicate": ingested.dedupe.is_duplicate,
                "duplicate_reason": ingested.dedupe.reason,
            }
        )

    _save_registry(cache_path, ingestor.fingerprint_registry)

    payload = {
        "path": str(source_path),
        "processed": len(results),
        "results": results,
        "errors": errors,
    }
    print(json.dumps(payload, ensure_ascii=True, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
