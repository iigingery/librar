"""CLI entrypoint for Phase-2 startup text indexing."""

from __future__ import annotations

import argparse
import json

from librar.search.indexer import SearchIndexer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Index books into SQLite FTS5 storage")
    parser.add_argument("--books-path", default="books", help="Directory containing books to index")
    parser.add_argument("--db-path", default=".librar-search.db", help="SQLite database path")
    args = parser.parse_args(argv)

    with SearchIndexer.from_db_path(args.db_path) as indexer:
        stats = indexer.index_books(args.books_path)

    print(json.dumps(stats.to_dict(), ensure_ascii=True, indent=2))
    return 0 if stats.errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
