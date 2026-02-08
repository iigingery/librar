from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from librar.hybrid.query import HybridQueryService
from librar.search.repository import ChunkRow, SearchRepository
from librar.semantic.query import SemanticSearchHit


def _seed_chunk(
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
                page=12,
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
class _SemanticStub:
    hits: list[SemanticSearchHit]

    def search(self, **kwargs) -> list[SemanticSearchHit]:
        limit = int(kwargs.get("limit", 10))
        return self.hits[:limit]


def test_hybrid_acceptance_merges_exact_and_semantic_evidence(tmp_path: Path) -> None:
    db_path = tmp_path / "hybrid.db"

    with SearchRepository(db_path) as repo:
        exact_id = _seed_chunk(
            repo,
            source_path="books\\exact.fb2",
            title="Exact Book",
            author="Author A",
            format_name="fb2",
            raw_text="туманная книга раскрывает путь практики",
            lemma_text="туманный книга раскрывать путь практика",
        )
        semantic_only_id = _seed_chunk(
            repo,
            source_path="books\\semantic.fb2",
            title="Semantic Book",
            author="Author B",
            format_name="fb2",
            raw_text="развитие души идет через внимательность",
            lemma_text="развитие душа идти через внимательность",
        )

        semantic = _SemanticStub(
            hits=[
                SemanticSearchHit(
                    source_path="books\\semantic.fb2",
                    title="Semantic Book",
                    author="Author B",
                    format_name="fb2",
                    chunk_id=semantic_only_id,
                    chunk_no=0,
                    page=12,
                    chapter="ch-1",
                    item_id=None,
                    char_start=0,
                    char_end=40,
                    score=0.99,
                    excerpt="развитие души идет через внимательность",
                )
            ]
        )

        service = HybridQueryService(search_repository=repo, semantic_searcher=semantic)
        results = service.search(query="туманная книга", limit=10, alpha=0.7)

    assert len(results) >= 2
    assert results[0].chunk_id == exact_id
    assert any(row.chunk_id == semantic_only_id for row in results)


def test_hybrid_acceptance_enforces_filters_and_output_contract(tmp_path: Path) -> None:
    db_path = tmp_path / "hybrid.db"

    with SearchRepository(db_path) as repo:
        keep_id = _seed_chunk(
            repo,
            source_path="books\\keep.fb2",
            title="Keep Book",
            author="Nisargadatta Maharaj",
            format_name="fb2",
            raw_text="книга о духовной дисциплине",
            lemma_text="книга о духовный дисциплина",
        )
        _seed_chunk(
            repo,
            source_path="books\\skip.txt",
            title="Skip Book",
            author="Other Author",
            format_name="txt",
            raw_text="книга о духовной дисциплине",
            lemma_text="книга о духовный дисциплина",
        )

        semantic = _SemanticStub(hits=[])
        service = HybridQueryService(search_repository=repo, semantic_searcher=semantic)
        results = service.search(
            query="книга",
            limit=10,
            author_filter="mahar",
            format_filter="fb2",
            alpha=0.6,
        )

    assert len(results) == 1
    row = results[0]
    assert row.chunk_id == keep_id
    assert row.author == "Nisargadatta Maharaj"
    assert row.format_name == "fb2"
    assert "—" in row.display
    assert row.display.startswith("Keep Book — page 12 —")
