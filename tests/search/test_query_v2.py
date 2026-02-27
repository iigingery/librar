"""Tests for v2.0 search enhancements: SearchFilters and snippet markers."""

from __future__ import annotations

from pathlib import Path

from librar.search.query import SearchFilters, search_chunks
from librar.search.repository import ChunkRow, SearchRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_book(
    repo: SearchRepository,
    *,
    source_path: str,
    text: str,
    lemma_text: str,
    language: str = "ru",
    author: str = "tester",
    format_name: str = "txt",
) -> int:
    """Insert a single-chunk book and return its book_id."""
    repo.replace_book_chunks(
        source_path=source_path,
        title=source_path,
        author=author,
        format_name=format_name,
        language=language,
        fingerprint=f"fp-{source_path}",
        mtime_ns=1,
        chunks=[
            ChunkRow(
                chunk_no=0,
                raw_text=text,
                lemma_text=lemma_text,
                page=1,
                chapter=None,
                item_id=None,
                char_start=0,
                char_end=len(text),
            )
        ],
    )
    row = repo.connection.execute(
        "SELECT id FROM books WHERE source_path = ?", (source_path,)
    ).fetchone()
    return int(row["id"])


# ---------------------------------------------------------------------------
# Language filter
# ---------------------------------------------------------------------------


def test_language_filter_includes_matching_book(tmp_path: Path) -> None:
    db_path = tmp_path / "q2.db"

    with SearchRepository(db_path) as repo:
        # Two books with Russian text but different language tags.
        # The filter must include only the one with language="kk".
        _insert_book(
            repo,
            source_path="kk.txt",
            text="история книга",
            lemma_text="история книга",
            language="kk",
        )
        _insert_book(
            repo,
            source_path="ru.txt",
            text="история книга",
            lemma_text="история книга",
            language="ru",
        )

        hits = search_chunks(
            repo.connection,
            query="история",
            filters=SearchFilters(language="kk"),
            limit=10,
        )

    assert hits
    assert all(h.source_path == "kk.txt" for h in hits)


def test_language_filter_excludes_other_language(tmp_path: Path) -> None:
    db_path = tmp_path / "q2.db"

    with SearchRepository(db_path) as repo:
        _insert_book(
            repo,
            source_path="ru.txt",
            text="книга о природе и жизни",
            lemma_text="книга о природа и жизнь",
            language="ru",
        )
        _insert_book(
            repo,
            source_path="en.txt",
            text="book about nature and life",
            lemma_text="book about nature and life",
            language="en",
        )

        hits = search_chunks(
            repo.connection,
            query="книга",
            filters=SearchFilters(language="en"),
            limit=10,
        )

    # The Russian "книга" is not in the English book, so no hits
    assert all(h.source_path == "en.txt" for h in hits) or hits == []


def test_no_filters_returns_all_languages(tmp_path: Path) -> None:
    db_path = tmp_path / "q2.db"

    with SearchRepository(db_path) as repo:
        _insert_book(
            repo,
            source_path="ru.txt",
            text="книга о природе",
            lemma_text="книга о природа",
            language="ru",
        )
        _insert_book(
            repo,
            source_path="kk.txt",
            text="книга туралы",
            lemma_text="книга туралы",
            language="kk",
        )

        hits_no_filter = search_chunks(
            repo.connection, query="книга", limit=10
        )
        hits_ru_filter = search_chunks(
            repo.connection,
            query="книга",
            filters=SearchFilters(language="ru"),
            limit=10,
        )

    assert len(hits_no_filter) == 2
    assert len(hits_ru_filter) == 1
    assert hits_ru_filter[0].source_path == "ru.txt"


# ---------------------------------------------------------------------------
# Period (year) filter
# ---------------------------------------------------------------------------


def test_year_filter_matches_overlapping_event(tmp_path: Path) -> None:
    db_path = tmp_path / "q2.db"

    with SearchRepository(db_path) as repo:
        book_id = _insert_book(
            repo,
            source_path="history.txt",
            text="революция произошла в 1917 году",
            lemma_text="революция произойти в 1917 год",
        )
        repo.connection.execute(
            """INSERT INTO timeline_events
               (book_id, year_from, year_to, event_text, confidence)
               VALUES (?, 1905, 1922, 'Революционный период', 0.9)""",
            (book_id,),
        )
        repo.connection.commit()

        hits = search_chunks(
            repo.connection,
            query="революция",
            filters=SearchFilters(year_from=1910, year_to=1920),
            limit=10,
        )

    assert hits
    assert hits[0].source_path == "history.txt"


def test_year_filter_excludes_non_matching_period(tmp_path: Path) -> None:
    db_path = tmp_path / "q2.db"

    with SearchRepository(db_path) as repo:
        book_id = _insert_book(
            repo,
            source_path="ancient.txt",
            text="история древних времен",
            lemma_text="история древний время",
        )
        repo.connection.execute(
            """INSERT INTO timeline_events
               (book_id, year_from, year_to, event_text, confidence)
               VALUES (?, 1200, 1400, 'Средние века', 0.8)""",
            (book_id,),
        )
        repo.connection.commit()

        hits = search_chunks(
            repo.connection,
            query="история",
            filters=SearchFilters(year_from=1900, year_to=2000),
            limit=10,
        )

    assert hits == []


# ---------------------------------------------------------------------------
# Category filter
# ---------------------------------------------------------------------------


def test_category_filter_includes_categorised_book(tmp_path: Path) -> None:
    db_path = tmp_path / "q2.db"

    with SearchRepository(db_path) as repo:
        book_id = _insert_book(
            repo,
            source_path="science.txt",
            text="физика и математика",
            lemma_text="физика и математика",
        )
        # Insert a category and link it
        repo.connection.execute(
            "INSERT INTO categories (name) VALUES ('science')"
        )
        cat_id = repo.connection.execute(
            "SELECT id FROM categories WHERE name = 'science'"
        ).fetchone()["id"]
        repo.connection.execute(
            "INSERT INTO book_categories (book_id, category_id) VALUES (?, ?)",
            (book_id, cat_id),
        )
        repo.connection.commit()

        hits = search_chunks(
            repo.connection,
            query="физика",
            filters=SearchFilters(category_ids=[cat_id]),
            limit=10,
        )

    assert hits
    assert hits[0].source_path == "science.txt"


def test_category_filter_excludes_uncategorised_book(tmp_path: Path) -> None:
    db_path = tmp_path / "q2.db"

    with SearchRepository(db_path) as repo:
        _insert_book(
            repo,
            source_path="other.txt",
            text="физика и математика",
            lemma_text="физика и математика",
        )
        # Insert a category that is NOT linked to any book
        repo.connection.execute(
            "INSERT INTO categories (name) VALUES ('history')"
        )
        cat_id = repo.connection.execute(
            "SELECT id FROM categories WHERE name = 'history'"
        ).fetchone()["id"]
        repo.connection.commit()

        hits = search_chunks(
            repo.connection,
            query="физика",
            filters=SearchFilters(category_ids=[cat_id]),
            limit=10,
        )

    assert hits == []


# ---------------------------------------------------------------------------
# Tag filter
# ---------------------------------------------------------------------------


def test_tag_filter_includes_tagged_book(tmp_path: Path) -> None:
    db_path = tmp_path / "q2.db"

    with SearchRepository(db_path) as repo:
        book_id = _insert_book(
            repo,
            source_path="tagged.txt",
            text="важная книга о культуре",
            lemma_text="важный книга о культура",
        )
        repo.connection.execute(
            "INSERT INTO tags (name, tag_type) VALUES ('культура', 'topic')"
        )
        tag_id = repo.connection.execute(
            "SELECT id FROM tags WHERE name = 'культура'"
        ).fetchone()["id"]
        repo.connection.execute(
            "INSERT INTO book_tags (book_id, tag_id) VALUES (?, ?)",
            (book_id, tag_id),
        )
        repo.connection.commit()

        hits = search_chunks(
            repo.connection,
            query="книга",
            filters=SearchFilters(tag="культура"),
            limit=10,
        )

    assert hits
    assert hits[0].source_path == "tagged.txt"


# ---------------------------------------------------------------------------
# Snippet markers
# ---------------------------------------------------------------------------


def test_excerpt_uses_guillemet_markers(tmp_path: Path) -> None:
    db_path = tmp_path / "q2.db"

    with SearchRepository(db_path) as repo:
        # raw_text must contain the exact search token so FTS5 snippet highlights it.
        _insert_book(
            repo,
            source_path="snip.txt",
            text="книга рассматривает различные темы.",
            lemma_text="книга рассматривать различный тема",
        )

        hits = search_chunks(repo.connection, query="книга", limit=5)

    assert hits
    excerpt = hits[0].excerpt
    # FTS5 snippet uses « and » as highlight markers
    assert "«" in excerpt or "»" in excerpt


# ---------------------------------------------------------------------------
# Empty / None filters are no-ops
# ---------------------------------------------------------------------------


def test_empty_search_filters_does_not_restrict_results(tmp_path: Path) -> None:
    db_path = tmp_path / "q2.db"

    with SearchRepository(db_path) as repo:
        _insert_book(
            repo,
            source_path="a.txt",
            text="книга о поэзии",
            lemma_text="книга о поэзия",
            language="ru",
        )

        hits_no_filters = search_chunks(repo.connection, query="книга", limit=10)
        hits_empty_filters = search_chunks(
            repo.connection,
            query="книга",
            filters=SearchFilters(),
            limit=10,
        )

    assert len(hits_no_filters) == len(hits_empty_filters)
