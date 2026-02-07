from __future__ import annotations

from pathlib import Path

from librar.search.query import search_chunks
from librar.search.repository import ChunkRow, SearchRepository


def _insert_book(repo: SearchRepository, *, source_path: str, text: str, lemma_text: str) -> None:
    repo.replace_book_chunks(
        source_path=source_path,
        title=source_path,
        author="tester",
        format_name="txt",
        fingerprint=f"fp-{source_path}",
        mtime_ns=1,
        chunks=[
            ChunkRow(
                chunk_no=0,
                raw_text=text,
                lemma_text=lemma_text,
                page=1,
                chapter="ch-1",
                item_id=None,
                char_start=0,
                char_end=len(text),
            )
        ],
    )


def test_exact_phrase_query_hits_raw_text_phrase(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"

    with SearchRepository(db_path) as repo:
        _insert_book(
            repo,
            source_path="exact.txt",
            text="Туманная книга стоит на полке.",
            lemma_text="туманный книга стоять на полка",
        )
        _insert_book(
            repo,
            source_path="other.txt",
            text="Книга может быть туманной, но слова разделены.",
            lemma_text="книга мочь быть туманный но слово разделить",
        )

        hits = search_chunks(repo.connection, query="туманная книга", phrase_mode=True, limit=5)

    assert hits
    assert hits[0].source_path == "exact.txt"
    assert "Туманная книга" in hits[0].excerpt


def test_lemma_query_finds_inflected_forms(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"

    with SearchRepository(db_path) as repo:
        _insert_book(
            repo,
            source_path="forms.txt",
            text="В библиотеке много книги и редкие книги тоже.",
            lemma_text="в библиотека много книга и редкий книга тоже",
        )

        hits = search_chunks(repo.connection, query="книга", limit=5)

    assert hits
    assert any(hit.source_path == "forms.txt" for hit in hits)


def test_results_are_sorted_by_rank_then_rowid(tmp_path: Path) -> None:
    db_path = tmp_path / "search.db"

    with SearchRepository(db_path) as repo:
        _insert_book(
            repo,
            source_path="high.txt",
            text="книга книга книга книга",
            lemma_text="книга книга книга книга",
        )
        _insert_book(
            repo,
            source_path="low.txt",
            text="книга встречается один раз",
            lemma_text="книга встречаться один раз",
        )

        hits = search_chunks(repo.connection, query="книга", limit=5)

    assert len(hits) == 2
    assert hits[0].rank <= hits[1].rank
    assert hits[0].source_path == "high.txt"
