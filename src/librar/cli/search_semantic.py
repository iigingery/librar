"""CLI entrypoint for semantic vector search queries."""

from __future__ import annotations

import argparse
import json
import time
from typing import Sequence

from librar.semantic.query import SemanticQueryService


def run_search(
    service: SemanticQueryService,
    *,
    query: str,
    limit: int,
    repeats: int = 1,
) -> tuple[list[dict[str, str | int | float | None]], list[float]]:
    times_ms: list[float] = []
    payload_rows: list[dict[str, str | int | float | None]] = []

    run_count = max(1, repeats)
    for _ in range(run_count):
        started = time.perf_counter()
        hits = service.search(query=query, limit=limit)
        elapsed = (time.perf_counter() - started) * 1000
        times_ms.append(round(elapsed, 2))
        payload_rows = [hit.to_dict() for hit in hits]

    return payload_rows, times_ms


def within_latency_threshold(durations_ms: Sequence[float], *, threshold_ms: float = 2000.0) -> bool:
    return all(value <= threshold_ms for value in durations_ms)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run semantic search against FAISS vector index")
    parser.add_argument("--db-path", default=".librar-search.db", help="SQLite database path")
    parser.add_argument("--index-path", default=".librar-semantic.faiss", help="FAISS index file path")
    parser.add_argument("--query", required=True, help="Semantic query text")
    parser.add_argument("--limit", type=int, default=10, help="Maximum number of results")
    parser.add_argument("--measure-ms", action="store_true", help="Include repeated latency measurements")
    parser.add_argument("--repeats", type=int, default=1, help="How many repeated query runs to measure")
    args = parser.parse_args(argv)

    safe_limit = max(1, min(args.limit, 100))

    with SemanticQueryService.from_db_path(
        db_path=args.db_path,
        index_path=args.index_path,
    ) as service:
        results, timings = run_search(
            service,
            query=args.query,
            limit=safe_limit,
            repeats=args.repeats if args.measure_ms else 1,
        )

    payload: dict[str, object] = {
        "query": args.query,
        "limit": safe_limit,
        "results": results,
    }

    if args.measure_ms:
        payload["measurements_ms"] = timings
        payload["duration_ms"] = timings[-1] if timings else 0.0
        payload["latency_threshold_ms"] = 2000.0
        payload["latency_within_threshold"] = within_latency_threshold(timings, threshold_ms=2000.0)

    print(json.dumps(payload, ensure_ascii=True, indent=2))

    if args.measure_ms and not within_latency_threshold(timings, threshold_ms=2000.0):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
