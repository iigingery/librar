"""CLI for running keyword-based thematic classification over all indexed books."""

from __future__ import annotations

import argparse
import json
import sqlite3

from librar.search.schema import apply_runtime_pragmas, ensure_schema
from librar.taxonomy.classifier import classify_text, _load_thesaurus
from librar.taxonomy.taxonomy_repository import TaxonomyRepository


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Classify indexed books by thematic keywords"
    )
    parser.add_argument(
        "--db-path",
        default=".librar-search.db",
        help="Path to the SQLite search database",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.01,
        help="Minimum keyword overlap score for a category match (default: 0.01)",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=3,
        help="Maximum categories per book (default: 3)",
    )
    args = parser.parse_args(argv)

    conn = sqlite3.connect(args.db_path)
    conn.row_factory = sqlite3.Row
    apply_runtime_pragmas(conn)
    ensure_schema(conn)

    taxonomy_repo = TaxonomyRepository(conn)
    thesaurus = _load_thesaurus()
    taxonomy_repo.seed_categories_from_thesaurus(thesaurus["categories"])

    books = conn.execute("SELECT id, title FROM books").fetchall()
    results = []

    for book in books:
        book_id = book["id"]
        chunk_rows = conn.execute(
            "SELECT raw_text FROM chunks WHERE book_id = ? ORDER BY chunk_no LIMIT 20",
            (book_id,),
        ).fetchall()
        sample = " ".join(row["raw_text"] for row in chunk_rows)

        matches = classify_text(sample, top_n=args.top_n, min_score=args.min_score)
        category_ids = [m.category_id for m in matches]
        taxonomy_repo.assign_book_categories(book_id, category_ids)

        results.append(
            {
                "book_id": book_id,
                "title": book["title"],
                "categories": [
                    {"id": m.category_id, "name": m.name, "score": round(m.score, 4)}
                    for m in matches
                ],
            }
        )

    conn.close()
    print(
        json.dumps(
            {"classified": len(results), "results": results},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
