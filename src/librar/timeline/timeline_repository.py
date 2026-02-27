"""Repository for timeline event persistence."""

from __future__ import annotations

import sqlite3

from librar.timeline.extractor import TemporalSpan


class TimelineRepository:
    """Thin persistence layer for the timeline_events table."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection

    def replace_book_events(
        self,
        book_id: int,
        events: list[tuple[int | None, TemporalSpan]],
    ) -> int:
        """Replace all timeline events for one book.

        Parameters
        ----------
        book_id:
            The ID of the book in the ``books`` table.
        events:
            List of ``(chunk_id, span)`` tuples.  ``chunk_id`` may be None
            when the chunk cannot be identified.

        Returns
        -------
        int
            Number of events inserted.
        """
        self._conn.execute(
            "DELETE FROM timeline_events WHERE book_id = ?", (book_id,)
        )
        rows = [
            (
                book_id,
                chunk_id,
                span.year_from,
                span.year_to,
                span.decade,
                span.century,
                span.source_fragment,   # event_text
                span.source_fragment,   # source_fragment
                1 if span.is_approximate else 0,
                span.confidence,
            )
            for chunk_id, span in events
        ]
        if rows:
            self._conn.executemany(
                """
                INSERT INTO timeline_events(
                    book_id, chunk_id, year_from, year_to, decade, century,
                    event_text, source_fragment, is_approximate, confidence
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        self._conn.commit()
        return len(rows)

    def query_by_period(
        self,
        year_from: int,
        year_to: int,
        *,
        limit: int = 50,
    ) -> list[sqlite3.Row]:
        """Return timeline events whose year range overlaps [year_from, year_to]."""
        return self._conn.execute(
            """
            SELECT te.*, b.title, b.author, b.source_path
            FROM timeline_events te
            JOIN books b ON b.id = te.book_id
            WHERE te.year_from <= ? AND te.year_to >= ?
            ORDER BY te.year_from ASC, te.confidence DESC
            LIMIT ?
            """,
            (year_to, year_from, limit),
        ).fetchall()
