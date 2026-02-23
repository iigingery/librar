"""CLI entrypoint for hybrid (keyword + semantic) search."""

from __future__ import annotations

import argparse
import json

from dotenv import load_dotenv

load_dotenv()

from librar.hybrid.query import HybridQueryService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run hybrid search over keyword and semantic indexes")
    parser.add_argument("--db-path", default=".librar-search.db", help="SQLite database path")
    parser.add_argument("--index-path", default=".librar-semantic.faiss", help="FAISS index file path")
    parser.add_argument("--query", required=True, help="Hybrid query text")
    parser.add_argument("--limit", type=int, default=10, help="Maximum number of returned results")
    parser.add_argument("--alpha", type=float, default=0.7, help="Semantic weighting in [0.0, 1.0]")
    parser.add_argument("--author", default=None, help="Optional author filter (substring, case-insensitive)")
    parser.add_argument("--format", default=None, help="Optional format filter (exact, case-insensitive)")
    parser.add_argument("--phrase-mode", action="store_true", help="Enable exact phrase preference in keyword branch")
    parser.add_argument("--candidate-limit", type=int, default=64, help="Per-branch candidate retrieval size before fusion")
    args = parser.parse_args(argv)

    query_text = args.query
    safe_limit = max(1, min(args.limit, 100))
    safe_candidate_limit = max(safe_limit, args.candidate_limit)

    if not 0.0 <= args.alpha <= 1.0:
        payload = {
            "error": "alpha must be between 0.0 and 1.0",
            "alpha": args.alpha,
        }
        print(json.dumps(payload, ensure_ascii=True, indent=2))
        return 2

    with HybridQueryService.from_db_path(db_path=args.db_path, index_path=args.index_path) as service:
        hits = service.search(
            query=query_text,
            limit=safe_limit,
            alpha=args.alpha,
            author_filter=args.author,
            format_filter=args.format,
            phrase_mode=args.phrase_mode,
            candidate_limit=safe_candidate_limit,
        )

    payload = {
        "query": query_text,
        "limit": safe_limit,
        "alpha": args.alpha,
        "phrase_mode": args.phrase_mode,
        "author_filter": args.author,
        "format_filter": args.format,
        "results": [hit.to_dict() for hit in hits],
    }
    print(json.dumps(payload, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
