"""CLI for extracting and persisting temporal events from indexed books."""

from __future__ import annotations

import argparse
import json
import sqlite3

from librar.search.schema import apply_runtime_pragmas, ensure_schema
from librar.timeline.extractor import extract_temporal_spans
from librar.timeline.timeline_repository import TimelineRepository


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract and store timeline events from indexed books"
    )
    parser.add_argument(
        "--db-path",
        default=".librar-search.db",
        help="Path to the SQLite search database",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.6,
        help="Minimum confidence threshold for a temporal span (default: 0.6)",
    )
    args = parser.parse_args(argv)

    conn = sqlite3.connect(args.db_path)
    conn.row_factory = sqlite3.Row
    apply_runtime_pragmas(conn)
    ensure_schema(conn)

    timeline_repo = TimelineRepository(conn)
    books = conn.execute("SELECT id, title FROM books").fetchall()
    total_events = 0
    results = []

    for book in books:
        book_id = book["id"]
        chunks = conn.execute(
            "SELECT id, raw_text FROM chunks WHERE book_id = ? ORDER BY chunk_no",
            (book_id,),
        ).fetchall()

        book_events: list[tuple[int | None, object]] = []
        for chunk in chunks:
            chunk_id = chunk["id"]
            spans = extract_temporal_spans(chunk["raw_text"])
            for span in spans:
                if span.confidence >= args.min_confidence:
                    book_events.append((chunk_id, span))

        count = timeline_repo.replace_book_events(book_id, book_events)
        total_events += count
        results.append(
            {"book_id": book_id, "title": book["title"], "events": count}
        )

    conn.close()
    print(
        json.dumps(
            {"total_events": total_events, "books": results},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
