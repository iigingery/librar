"""CLI entrypoint for FTS5 text search queries."""

from __future__ import annotations

import argparse
import json

from librar.search.repository import SearchRepository
from librar.search.query import search_chunks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run text search against indexed SQLite FTS5 database")
    parser.add_argument("--db-path", default=".librar-search.db", help="SQLite database path")
    parser.add_argument("--query", required=True, help="Text query to search for")
    parser.add_argument("--limit", type=int, default=10, help="Maximum number of results")
    parser.add_argument(
        "--phrase-mode",
        action="store_true",
        help="Treat query as an exact phrase in addition to lemma phrase",
    )
    args = parser.parse_args(argv)
    query_text = args.query
    safe_limit = max(1, min(args.limit, 100))

    with SearchRepository(args.db_path) as repository:
        hits = search_chunks(
            repository.connection,
            query=query_text,
            limit=args.limit,
            phrase_mode=args.phrase_mode,
        )

    payload = {
        "query": query_text,
        "phrase_mode": args.phrase_mode,
        "limit": safe_limit,
        "results": [hit.to_dict() for hit in hits],
    }
    print(json.dumps(payload, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
