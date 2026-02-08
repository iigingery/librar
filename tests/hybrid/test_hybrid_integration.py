"""Acceptance tests for hybrid search requirements SRCH-04, SRCH-05, SRCH-06."""

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
    page: int | None = None,
    chapter: str | None = None,
    char_start: int | None = None,
    char_end: int | None = None,
) -> int:
    """Seed a single chunk into the database and return its chunk_id."""
    if char_start is None:
        char_start = 0
    if char_end is None:
        char_end = len(raw_text)

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
                page=page,
                chapter=chapter,
                item_id=None,
                char_start=char_start,
                char_end=char_end,
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
    """Stub semantic searcher for testing without live embeddings."""
    hits: list[SemanticSearchHit]

    def search(self, **kwargs) -> list[SemanticSearchHit]:
        limit = int(kwargs.get("limit", 10))
        return self.hits[:limit]


# ============================================================================
# SRCH-04: Hybrid search — merge text and semantic with ranking
# ============================================================================

def test_srch04_hybrid_merges_exact_and_semantic_candidates(tmp_path: Path) -> None:
    """SRCH-04: Verify hybrid results contain both exact and semantic matches in one ranked list."""
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
            page=12,
        )
        semantic_only_id = _seed_chunk(
            repo,
            source_path="books\\semantic.fb2",
            title="Semantic Book",
            author="Author B",
            format_name="fb2",
            raw_text="развитие души идет через внимательность",
            lemma_text="развитие душа идти через внимательность",
            page=15,
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
                    page=15,
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

    # Assert merged result composition
    assert len(results) >= 2, "Expected at least 2 results (exact + semantic)"

    # Exact match should be prioritized (comes first)
    assert results[0].chunk_id == exact_id, "Exact match should rank first"
    assert results[0].keyword_rank is not None, "Exact match should have keyword_rank"

    # Semantic-only result should also be present
    semantic_result = next((r for r in results if r.chunk_id == semantic_only_id), None)
    assert semantic_result is not None, "Semantic-only match should be included"
    assert semantic_result.semantic_score is not None, "Semantic match should have semantic_score"


def test_srch04_hybrid_ranking_is_deterministic_and_repeatable(tmp_path: Path) -> None:
    """SRCH-04: Verify hybrid ranking produces deterministic ordering across identical queries."""
    db_path = tmp_path / "hybrid.db"

    with SearchRepository(db_path) as repo:
        chunk_a = _seed_chunk(
            repo,
            source_path="books\\a.fb2",
            title="Book A",
            author="Author A",
            format_name="fb2",
            raw_text="духовная практика требует внимания и терпения",
            lemma_text="духовный практика требовать внимание и терпение",
            page=10,
        )
        chunk_b = _seed_chunk(
            repo,
            source_path="books\\b.fb2",
            title="Book B",
            author="Author B",
            format_name="fb2",
            raw_text="практика медитации развивает внутреннее спокойствие",
            lemma_text="практика медитация развивать внутренний спокойствие",
            page=20,
        )

        semantic = _SemanticStub(
            hits=[
                SemanticSearchHit(
                    source_path="books\\a.fb2",
                    title="Book A",
                    author="Author A",
                    format_name="fb2",
                    chunk_id=chunk_a,
                    chunk_no=0,
                    page=10,
                    chapter=None,
                    item_id=None,
                    char_start=0,
                    char_end=46,
                    score=0.85,
                    excerpt="духовная практика требует внимания и терпения",
                ),
                SemanticSearchHit(
                    source_path="books\\b.fb2",
                    title="Book B",
                    author="Author B",
                    format_name="fb2",
                    chunk_id=chunk_b,
                    chunk_no=0,
                    page=20,
                    chapter=None,
                    item_id=None,
                    char_start=0,
                    char_end=52,
                    score=0.82,
                    excerpt="практика медитации развивает внутреннее спокойствие",
                ),
            ]
        )

        service = HybridQueryService(search_repository=repo, semantic_searcher=semantic)

        # Run same query twice
        results1 = service.search(query="практика", limit=10, alpha=0.7)
        results2 = service.search(query="практика", limit=10, alpha=0.7)

    # Verify deterministic ordering
    assert len(results1) == len(results2)
    for idx, (r1, r2) in enumerate(zip(results1, results2)):
        assert r1.chunk_id == r2.chunk_id, f"Result order differs at position {idx}"
        assert r1.hybrid_score == r2.hybrid_score, f"Hybrid score differs at position {idx}"


def test_srch04_hybrid_merges_overlapping_candidates(tmp_path: Path) -> None:
    """SRCH-04: Verify chunks appearing in both branches are merged correctly with combined scores."""
    db_path = tmp_path / "hybrid.db"

    with SearchRepository(db_path) as repo:
        overlap_id = _seed_chunk(
            repo,
            source_path="books\\overlap.fb2",
            title="Overlap Book",
            author="Author",
            format_name="fb2",
            raw_text="практика внимательности ведет к освобождению",
            lemma_text="практика внимательность вести к освобождение",
            page=5,
        )

        semantic = _SemanticStub(
            hits=[
                SemanticSearchHit(
                    source_path="books\\overlap.fb2",
                    title="Overlap Book",
                    author="Author",
                    format_name="fb2",
                    chunk_id=overlap_id,
                    chunk_no=0,
                    page=5,
                    chapter=None,
                    item_id=None,
                    char_start=0,
                    char_end=45,
                    score=0.95,
                    excerpt="практика внимательности ведет к освобождению",
                )
            ]
        )

        service = HybridQueryService(search_repository=repo, semantic_searcher=semantic)
        results = service.search(query="практика внимательности", limit=10, alpha=0.7)

    assert len(results) == 1, "Duplicate chunk should appear once"
    result = results[0]
    assert result.chunk_id == overlap_id
    # Both scores should be present for overlapping chunk
    assert result.keyword_rank is not None, "Overlapping chunk should have keyword_rank"
    assert result.semantic_score is not None, "Overlapping chunk should have semantic_score"
    # Hybrid score should reflect both contributions
    assert result.hybrid_score > 0.0, "Hybrid score should be positive"


# ============================================================================
# SRCH-05: Filter by author and format
# ============================================================================

def test_srch05_author_filter_restricts_results(tmp_path: Path) -> None:
    """SRCH-05: Verify author filter correctly restricts results to matching authors."""
    db_path = tmp_path / "hybrid.db"

    with SearchRepository(db_path) as repo:
        keep_id = _seed_chunk(
            repo,
            source_path="books\\keep.fb2",
            title="Keep Book",
            author="Nisargadatta Maharaj",
            format_name="fb2",
            raw_text="книга о духовной дисциплине и практике",
            lemma_text="книга о духовный дисциплина и практика",
            page=12,
        )
        _seed_chunk(
            repo,
            source_path="books\\skip.txt",
            title="Skip Book",
            author="Other Author",
            format_name="txt",
            raw_text="книга о духовной дисциплине и практике",
            lemma_text="книга о духовный дисциплина и практика",
            page=5,
        )

        semantic = _SemanticStub(hits=[])
        service = HybridQueryService(search_repository=repo, semantic_searcher=semantic)
        results = service.search(
            query="книга",
            limit=10,
            author_filter="mahar",
            alpha=0.6,
        )

    assert len(results) == 1, "Author filter should restrict to one result"
    assert results[0].chunk_id == keep_id
    assert results[0].author == "Nisargadatta Maharaj"


def test_srch05_format_filter_restricts_results(tmp_path: Path) -> None:
    """SRCH-05: Verify format filter correctly restricts results to matching formats."""
    db_path = tmp_path / "hybrid.db"

    with SearchRepository(db_path) as repo:
        keep_id = _seed_chunk(
            repo,
            source_path="books\\keep.fb2",
            title="FB2 Book",
            author="Author",
            format_name="fb2",
            raw_text="медитация на дыхание успокаивает ум",
            lemma_text="медитация на дыхание успокаивать ум",
            page=8,
        )
        _seed_chunk(
            repo,
            source_path="books\\skip.epub",
            title="EPUB Book",
            author="Author",
            format_name="epub",
            raw_text="медитация на дыхание успокаивает ум",
            lemma_text="медитация на дыхание успокаивать ум",
            chapter="Chapter 1",
        )

        semantic = _SemanticStub(hits=[])
        service = HybridQueryService(search_repository=repo, semantic_searcher=semantic)
        results = service.search(
            query="медитация",
            limit=10,
            format_filter="fb2",
            alpha=0.6,
        )

    assert len(results) == 1, "Format filter should restrict to one result"
    assert results[0].chunk_id == keep_id
    assert results[0].format_name == "fb2"


def test_srch05_combined_author_and_format_filters(tmp_path: Path) -> None:
    """SRCH-05: Verify combined author and format filters work together correctly."""
    db_path = tmp_path / "hybrid.db"

    with SearchRepository(db_path) as repo:
        keep_id = _seed_chunk(
            repo,
            source_path="books\\keep.fb2",
            title="Keep Book",
            author="Nisargadatta Maharaj",
            format_name="fb2",
            raw_text="осознанность пронизывает каждое действие",
            lemma_text="осознанность пронизывать каждый действие",
            page=42,
        )
        _seed_chunk(
            repo,
            source_path="books\\wrong_author.fb2",
            title="Wrong Author FB2",
            author="Another Author",
            format_name="fb2",
            raw_text="осознанность пронизывает каждое действие",
            lemma_text="осознанность пронизывать каждый действие",
            page=10,
        )
        _seed_chunk(
            repo,
            source_path="books\\wrong_format.txt",
            title="Wrong Format",
            author="Nisargadatta Maharaj",
            format_name="txt",
            raw_text="осознанность пронизывает каждое действие",
            lemma_text="осознанность пронизывать каждый действие",
            chapter="Section 1",
        )

        semantic = _SemanticStub(hits=[])
        service = HybridQueryService(search_repository=repo, semantic_searcher=semantic)
        results = service.search(
            query="осознанность",
            limit=10,
            author_filter="mahar",
            format_filter="fb2",
            alpha=0.6,
        )

    assert len(results) == 1, "Combined filters should restrict to one result"
    assert results[0].chunk_id == keep_id
    assert results[0].author == "Nisargadatta Maharaj"
    assert results[0].format_name == "fb2"


# ============================================================================
# SRCH-06: Output format with title, location, excerpt
# ============================================================================

def test_srch06_output_includes_required_display_fields(tmp_path: Path) -> None:
    """SRCH-06: Verify output includes all required fields for display rendering."""
    db_path = tmp_path / "hybrid.db"

    with SearchRepository(db_path) as repo:
        chunk_id = _seed_chunk(
            repo,
            source_path="books\\test.fb2",
            title="Test Book",
            author="Test Author",
            format_name="fb2",
            raw_text="Это тестовый текст для проверки отображения",
            lemma_text="это тестовый текст для проверка отображение",
            page=99,
        )

        semantic = _SemanticStub(hits=[])
        service = HybridQueryService(search_repository=repo, semantic_searcher=semantic)
        results = service.search(query="тестовый", limit=10, alpha=0.6)

    assert len(results) == 1
    result = results[0]

    # Verify all required fields are present
    assert result.title is not None, "Result must include title"
    assert result.source_path is not None, "Result must include source_path"
    assert result.excerpt is not None, "Result must include excerpt"
    assert result.display is not None, "Result must include display string"

    # Verify display format
    assert result.title == "Test Book"
    # FTS may add highlighting brackets, so check that base text is present
    assert "тестовый" in result.excerpt, "Excerpt should contain the query term"
    assert "текст" in result.excerpt, "Excerpt should contain surrounding context"
    assert "—" in result.display, "Display should contain separator"
    assert result.display.count("—") >= 2, "Display should have title — location — excerpt format"


def test_srch06_display_format_for_page_based_location(tmp_path: Path) -> None:
    """SRCH-06: Verify display format correctly shows page-based location."""
    db_path = tmp_path / "hybrid.db"

    with SearchRepository(db_path) as repo:
        _seed_chunk(
            repo,
            source_path="books\\pdf_book.pdf",
            title="PDF Book",
            author="PDF Author",
            format_name="pdf",
            raw_text="Content from a PDF document",
            lemma_text="content from a pdf document",
            page=42,
        )

        semantic = _SemanticStub(hits=[])
        service = HybridQueryService(search_repository=repo, semantic_searcher=semantic)
        results = service.search(query="content", limit=10, alpha=0.6)

    assert len(results) == 1
    result = results[0]
    assert result.page == 42
    assert "page 42" in result.display, "Display should show page number"
    assert result.display.startswith("PDF Book — page 42 —")


def test_srch06_display_format_for_chapter_based_location(tmp_path: Path) -> None:
    """SRCH-06: Verify display format correctly shows chapter-based location."""
    db_path = tmp_path / "hybrid.db"

    with SearchRepository(db_path) as repo:
        _seed_chunk(
            repo,
            source_path="books\\epub_book.epub",
            title="EPUB Book",
            author="EPUB Author",
            format_name="epub",
            raw_text="Content from an EPUB chapter",
            lemma_text="content from an epub chapter",
            chapter="Chapter 3: The Journey",
        )

        semantic = _SemanticStub(hits=[])
        service = HybridQueryService(search_repository=repo, semantic_searcher=semantic)
        results = service.search(query="content", limit=10, alpha=0.6)

    assert len(results) == 1
    result = results[0]
    assert result.chapter == "Chapter 3: The Journey"
    assert "Chapter 3: The Journey" in result.display, "Display should show chapter name"


def test_srch06_display_format_for_position_based_location(tmp_path: Path) -> None:
    """SRCH-06: Verify display format correctly shows position-based location when no page/chapter."""
    db_path = tmp_path / "hybrid.db"

    with SearchRepository(db_path) as repo:
        _seed_chunk(
            repo,
            source_path="books\\text_file.txt",
            title="Text File",
            author="Text Author",
            format_name="txt",
            raw_text="Content from a text file",
            lemma_text="content from a text file",
            char_start=100,
            char_end=124,
        )

        semantic = _SemanticStub(hits=[])
        service = HybridQueryService(search_repository=repo, semantic_searcher=semantic)
        results = service.search(query="content", limit=10, alpha=0.6)

    assert len(results) == 1
    result = results[0]
    assert result.char_start == 100
    assert result.char_end == 124
    assert "position 100-124" in result.display, "Display should show char position range"


def test_srch06_output_contract_fields_match_to_dict(tmp_path: Path) -> None:
    """SRCH-06: Verify to_dict() output includes all contract fields for downstream rendering."""
    db_path = tmp_path / "hybrid.db"

    with SearchRepository(db_path) as repo:
        _seed_chunk(
            repo,
            source_path="books\\contract.fb2",
            title="Contract Book",
            author="Contract Author",
            format_name="fb2",
            raw_text="Проверка контракта вывода",
            lemma_text="проверка контракт вывод",
            page=7,
        )

        semantic = _SemanticStub(
            hits=[
                SemanticSearchHit(
                    source_path="books\\contract.fb2",
                    title="Contract Book",
                    author="Contract Author",
                    format_name="fb2",
                    chunk_id=1,  # Will be replaced by actual ID
                    chunk_no=0,
                    page=7,
                    chapter=None,
                    item_id=None,
                    char_start=0,
                    char_end=26,
                    score=0.88,
                    excerpt="Проверка контракта вывода",
                )
            ]
        )

        service = HybridQueryService(search_repository=repo, semantic_searcher=semantic)
        results = service.search(query="контракт", limit=10, alpha=0.7)

    assert len(results) >= 1
    result = results[0]
    result_dict = result.to_dict()

    # Verify all expected fields are in dict
    required_fields = [
        "source_path", "title", "author", "format", "chunk_id", "chunk_no",
        "page", "chapter", "item_id", "char_start", "char_end", "excerpt",
        "keyword_rank", "semantic_score", "hybrid_score", "display"
    ]
    for field in required_fields:
        assert field in result_dict, f"Output contract missing field: {field}"

    # Verify display field is ready for rendering
    assert isinstance(result_dict["display"], str)
    assert len(result_dict["display"]) > 0
