"""CLI entrypoint for startup semantic indexing."""

from __future__ import annotations

import argparse
import json

from dotenv import load_dotenv

load_dotenv()

from librar.semantic.indexer import SemanticIndexer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Index semantic embeddings into a FAISS vector store")
    parser.add_argument("--db-path", default=".librar-search.db", help="SQLite database path")
    parser.add_argument("--index-path", default=".librar-semantic.faiss", help="FAISS index file path")
    parser.add_argument("--batch-size", type=int, default=32, help="Embedding batch size")
    args = parser.parse_args(argv)

    with SemanticIndexer.from_db_path(
        db_path=args.db_path,
        index_path=args.index_path,
        batch_size=args.batch_size,
    ) as indexer:
        stats = indexer.index_chunks()

    print(json.dumps(stats.to_dict(), ensure_ascii=True, indent=2))
    return 0 if stats.errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
