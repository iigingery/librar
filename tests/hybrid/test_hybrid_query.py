from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from librar.hybrid.query import HybridQueryService
from librar.search.repository import ChunkRow, SearchRepository
from librar.semantic.query import SemanticSearchHit


def _insert_single_chunk(
    repo: SearchRepository,
    *,
    source_path: str,
    title: str,
    author: str,
    format_name: str,
    raw_text: str,
    lemma_text: str,
) -> int:
    repo.replace_book_chunks(
        source_path=source_path,
        title=title,
        author=author,
        format_name=format_name,
        fingerprint=f"fp-{source_path}",
        mtime_ns=1,
        chunks=[
            ChunkRow(
                chunk_no=0,
                raw_text=raw_text,
                lemma_text=lemma_text,
                page=1,
                chapter="ch-1",
                item_id=None,
                char_start=0,
                char_end=len(raw_text),
            )
        ],
    )
    row = repo.connection.execute(
        """
        SELECT c.id AS chunk_id
        FROM chunks c
        JOIN books b ON b.id = c.book_id
        WHERE b.source_path = ?
        """,
        (source_path,),
    ).fetchone()
    assert row is not None
    return int(row["chunk_id"])


@dataclass
class _StubSemanticSearcher:
    hits: list[SemanticSearchHit]
    last_kwargs: dict[str, object] | None = None

    def search(
        self,
        *,
        query: str,
        limit: int,
        author_filter: str | None = None,
        format_filter: str | None = None,
        candidate_limit: int | None = None,
    ) -> list[SemanticSearchHit]:
        self.last_kwargs = {
            "query": query,
            "limit": limit,
            "author_filter": author_filter,
            "format_filter": format_filter,
            "candidate_limit": candidate_limit,
        }
        return self.hits[:limit]


def test_hybrid_merges_keyword_and_semantic_with_exact_priority(tmp_path: Path) -> None:
    db_path = tmp_path / "hybrid.db"

    with SearchRepository(db_path) as repo:
        exact_id = _insert_single_chunk(
            repo,
            source_path="books\\exact.fb2",
            title="Exact",
            author="Author A",
            format_name="fb2",
            raw_text="туманная книга стоит на полке",
            lemma_text="туманный книга стоять на полка",
        )
        semantic_only_id = _insert_single_chunk(
            repo,
            source_path="books\\semantic.fb2",
            title="Semantic",
            author="Author B",
            format_name="fb2",
            raw_text="развитие души и духовная практика важны",
            lemma_text="развитие душа и духовный практика важный",
        )

        semantic_stub = _StubSemanticSearcher(
            hits=[
                SemanticSearchHit(
                    source_path=str((tmp_path / "books" / "semantic.fb2").resolve()),
                    title="Semantic",
                    author="Author B",
                    format_name="fb2",
                    chunk_id=semantic_only_id,
                    chunk_no=0,
                    page=1,
                    chapter="ch-1",
                    item_id=None,
                    char_start=0,
                    char_end=42,
                    score=0.98,
                    excerpt="развитие души и духовная практика важны",
                )
            ]
        )

        service = HybridQueryService(search_repository=repo, semantic_searcher=semantic_stub)
        results = service.search(query="туманная книга", limit=5, alpha=0.7)

    assert len(results) >= 2
    assert results[0].chunk_id == exact_id
    assert any(row.chunk_id == semantic_only_id for row in results)
    assert results[0].display.count("—") >= 2


def test_hybrid_propagates_filters_to_both_branches(tmp_path: Path) -> None:
    db_path = tmp_path / "hybrid.db"

    with SearchRepository(db_path) as repo:
        keep_id = _insert_single_chunk(
            repo,
            source_path="books\\keep.fb2",
            title="Keep",
            author="Nisargadatta Maharaj",
            format_name="fb2",
            raw_text="книга о практике",
            lemma_text="книга о практика",
        )
        _insert_single_chunk(
            repo,
            source_path="books\\skip.txt",
            title="Skip",
            author="Other",
            format_name="txt",
            raw_text="книга о практике",
            lemma_text="книга о практика",
        )

        semantic_stub = _StubSemanticSearcher(hits=[])
        service = HybridQueryService(search_repository=repo, semantic_searcher=semantic_stub)
        results = service.search(
            query="книга",
            limit=10,
            author_filter="mahar",
            format_filter="fb2",
            alpha=0.6,
        )

    assert len(results) == 1
    assert results[0].chunk_id == keep_id
    assert semantic_stub.last_kwargs is not None
    assert semantic_stub.last_kwargs["author_filter"] == "mahar"
    assert semantic_stub.last_kwargs["format_filter"] == "fb2"
