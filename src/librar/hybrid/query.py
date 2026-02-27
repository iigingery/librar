"""Hybrid query orchestration across keyword and semantic engines."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Protocol

from librar.hybrid.scoring import (
    fuse_normalized_scores,
    normalize_keyword_ranks,
    normalize_semantic_scores,
    order_fused_scores,
    filter_relevant_scores,
)
from librar.search.query import SearchFilters, SearchHit, search_chunks
from librar.search.repository import SearchRepository
from librar.semantic.config import SemanticSettings
from librar.semantic.openrouter import OpenRouterEmbedder
from librar.semantic.query import SemanticQueryService, SemanticSearchHit
from librar.semantic.semantic_repository import SemanticRepository
from librar.semantic.vector_store import FaissVectorStore


_WORD_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё]+")
_MULTISPACE_RE = re.compile(r"\s+")
_RU_STOPWORDS = {
    "а",
    "без",
    "был",
    "была",
    "были",
    "быть",
    "в",
    "во",
    "вы",
    "где",
    "да",
    "для",
    "до",
    "его",
    "ее",
    "если",
    "же",
    "за",
    "и",
    "из",
    "или",
    "как",
    "когда",
    "кто",
    "ли",
    "мне",
    "мы",
    "на",
    "не",
    "но",
    "о",
    "об",
    "от",
    "по",
    "при",
    "про",
    "с",
    "со",
    "так",
    "то",
    "только",
    "ты",
    "у",
    "уже",
    "что",
    "чтобы",
    "я",
    "здравствуйте",
    "подскажите",
    "пожалуйста",
    "давно",
    "пытаюсь",
    "понять",
    "можете",
    "помочь",
    "найти",
    "книге",
    "книгу",
    "автор",
    "подробно",
    "обычной",
    "ежедневной",
}
_DOMAIN_STEMS = ("практ", "вниман", "наблюд", "мысл", "тишин", "медитац", "внутрен")


@dataclass(frozen=True, slots=True)
class QueryRewrite:
    normalized_query: str
    search_query: str
    key_terms: tuple[str, ...]


class _SemanticSearcher(Protocol):
    def search(
        self,
        *,
        query: str,
        limit: int,
        author_filter: str | None = None,
        format_filter: str | None = None,
        candidate_limit: int | None = None,
    ) -> list[SemanticSearchHit]:
        ...


@dataclass(slots=True)
class HybridSearchHit:
    source_path: str
    title: str | None
    author: str | None
    format_name: str | None
    chunk_id: int
    chunk_no: int
    page: int | None
    chapter: str | None
    item_id: str | None
    char_start: int | None
    char_end: int | None
    excerpt: str
    keyword_rank: float | None
    semantic_score: float | None
    hybrid_score: float
    display: str

    def to_dict(self) -> dict[str, str | int | float | None]:
        return {
            "source_path": self.source_path,
            "title": self.title,
            "author": self.author,
            "format": self.format_name,
            "chunk_id": self.chunk_id,
            "chunk_no": self.chunk_no,
            "page": self.page,
            "chapter": self.chapter,
            "item_id": self.item_id,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "excerpt": self.excerpt,
            "keyword_rank": self.keyword_rank,
            "semantic_score": self.semantic_score,
            "hybrid_score": self.hybrid_score,
            "display": self.display,
        }


def _normalized_source_path(source_path: str) -> str:
    path = Path(source_path)
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    else:
        path = path.resolve()
    return str(path).replace("/", "\\").casefold()


def _location_text(hit: SearchHit | SemanticSearchHit) -> str:
    if hit.page is not None:
        return f"page {hit.page}"
    if hit.chapter:
        return hit.chapter
    if hit.char_start is not None and hit.char_end is not None:
        return f"position {hit.char_start}-{hit.char_end}"
    return "position unknown"


def _display_text(hit: SearchHit | SemanticSearchHit, *, excerpt: str) -> str:
    title = hit.title or Path(hit.source_path).name
    location = _location_text(hit)
    return f"{title} — {location} — {excerpt}"


def _exact_match_ids(text_hits: list[SearchHit], *, query: str, phrase_mode: bool) -> set[int]:
    normalized_query = query.lower().replace("ё", "е").strip()
    terms = [term for term in _WORD_RE.findall(normalized_query) if term]
    exact_ids: set[int] = set()

    for hit in text_hits:
        haystack = hit.excerpt.lower().replace("ё", "е")
        if phrase_mode:
            if normalized_query and normalized_query in haystack:
                exact_ids.add(hit.chunk_id)
            continue
        if terms and all(term in haystack for term in terms):
            exact_ids.add(hit.chunk_id)

    return exact_ids


def _rewrite_query(query: str) -> QueryRewrite:
    normalized = _MULTISPACE_RE.sub(" ", query.strip())
    words = [word.casefold() for word in _WORD_RE.findall(normalized)]
    long_question = len(words) >= 18 or len(normalized) >= 170

    filtered: list[str] = []
    seen_terms: set[str] = set()
    for word in words:
        if len(word) < 4 or word in _RU_STOPWORDS or word in seen_terms:
            continue
        filtered.append(word)
        seen_terms.add(word)

    domain_terms = [word for word in filtered if any(stem in word for stem in _DOMAIN_STEMS)]
    other_terms = [word for word in filtered if word not in domain_terms]
    key_terms = tuple((domain_terms + other_terms)[:8])

    if long_question and key_terms:
        search_query = " ".join(key_terms[:3])
    else:
        search_query = normalized
    return QueryRewrite(normalized_query=normalized, search_query=search_query, key_terms=key_terms)


def _rerank_score(
    *,
    fused_score: float,
    candidate: SearchHit | SemanticSearchHit,
    query_terms: set[str],
    key_terms: set[str],
) -> float:
    haystack = " ".join(part for part in (candidate.title or "", candidate.chapter or "", candidate.excerpt) if part).casefold()
    haystack_terms = {token for token in _WORD_RE.findall(haystack) if token and token not in _RU_STOPWORDS}
    if not haystack_terms:
        return fused_score

    query_overlap = len(query_terms & haystack_terms) / max(1, len(query_terms))
    key_overlap = len(key_terms & haystack_terms) / max(1, len(key_terms)) if key_terms else 0.0
    return fused_score + (0.2 * query_overlap) + (0.25 * key_overlap)


def build_llm_context(
    results: list[HybridSearchHit],
    *,
    max_context_chars: int,
    max_chunks: int = 8,
    max_per_source: int = 2,
) -> list[HybridSearchHit]:
    """Select hybrid chunks for LLM context with source diversity and size limit."""
    if max_context_chars <= 0 or max_chunks <= 0:
        return []

    buckets: dict[str, list[HybridSearchHit]] = {}
    source_order: list[str] = []
    for hit in results:
        source_key = _normalized_source_path(hit.source_path)
        if source_key not in buckets:
            buckets[source_key] = []
            source_order.append(source_key)
        if len(buckets[source_key]) < max_per_source:
            buckets[source_key].append(hit)

    selected: list[HybridSearchHit] = []
    used_chars = 0
    for round_no in range(max_per_source):
        for source_key in source_order:
            source_hits = buckets[source_key]
            if round_no >= len(source_hits):
                continue
            candidate = source_hits[round_no]
            candidate_size = len(candidate.excerpt.strip()) + 140
            if selected and used_chars + candidate_size > max_context_chars:
                return selected
            selected.append(candidate)
            used_chars += candidate_size
            if len(selected) >= max_chunks:
                return selected
    return selected


class HybridQueryService:
    """Merges keyword and semantic candidates into one ranked hybrid list."""

    def __init__(
        self,
        *,
        search_repository: SearchRepository,
        semantic_searcher: _SemanticSearcher,
        owns_repository: bool = False,
    ) -> None:
        self._search_repository = search_repository
        self._semantic_searcher = semantic_searcher
        self._owns_repository = owns_repository

    @classmethod
    def from_db_path(
        cls,
        *,
        db_path: str | Path,
        index_path: str | Path,
        settings: SemanticSettings | None = None,
    ) -> "HybridQueryService":
        search_repository = SearchRepository(db_path)
        semantic_repository = SemanticRepository(search_repository.connection)
        index_state = semantic_repository.get_index_state()
        if index_state is None:
            search_repository.close()
            raise RuntimeError("Semantic index is not initialized. Run semantic indexing before hybrid queries.")

        resolved_settings = settings or SemanticSettings.from_env()
        if index_state.model != resolved_settings.model:
            search_repository.close()
            raise RuntimeError(
                "Semantic index model mismatch: "
                f"indexed='{index_state.model}', configured='{resolved_settings.model}'. "
                "Reindex with `python -m librar.cli.index_semantic`."
            )
        vector_store = FaissVectorStore(index_path, dimension=index_state.dimension, metric=index_state.metric)
        embedder = OpenRouterEmbedder(resolved_settings)
        semantic_service = SemanticQueryService(
            search_repository=search_repository,
            semantic_repository=semantic_repository,
            vector_store=vector_store,
            embedder=embedder,
        )
        return cls(
            search_repository=search_repository,
            semantic_searcher=semantic_service,
            owns_repository=True,
        )

    def close(self) -> None:
        if self._owns_repository:
            self._search_repository.close()

    def __enter__(self) -> "HybridQueryService":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def search(
        self,
        *,
        query: str,
        limit: int = 10,
        alpha: float = 0.7,
        author_filter: str | None = None,
        format_filter: str | None = None,
        filters: SearchFilters | None = None,
        phrase_mode: bool = False,
        candidate_limit: int = 64,
    ) -> list[HybridSearchHit]:
        rewritten = _rewrite_query(query)
        query_text = rewritten.normalized_query
        if not query_text:
            return []
        safe_limit = max(1, min(limit, 100))
        branch_limit = max(safe_limit, candidate_limit)

        text_hits = search_chunks(
            self._search_repository.connection,
            query=rewritten.search_query,
            limit=branch_limit,
            phrase_mode=phrase_mode,
            author_filter=author_filter,
            format_filter=format_filter,
            filters=filters,
        )
        semantic_hits = self._semantic_searcher.search(
            query=rewritten.search_query,
            limit=branch_limit,
            author_filter=author_filter,
            format_filter=format_filter,
            candidate_limit=branch_limit,
        )

        text_by_id = {hit.chunk_id: hit for hit in text_hits}
        semantic_by_id = {hit.chunk_id: hit for hit in semantic_hits}
        if not text_by_id and not semantic_by_id:
            return []

        keyword_ranks = {chunk_id: hit.rank for chunk_id, hit in text_by_id.items()}
        semantic_scores = {chunk_id: hit.score for chunk_id, hit in semantic_by_id.items()}

        keyword_norm = normalize_keyword_ranks(keyword_ranks)
        semantic_norm = normalize_semantic_scores(semantic_scores)
        exact_ids = _exact_match_ids(text_hits, query=query_text, phrase_mode=phrase_mode)
        fused = fuse_normalized_scores(
            keyword_norm,
            semantic_norm,
            alpha=alpha,
            exact_match_ids=exact_ids,
            exact_match_boost=0.45,
        )
        fused = filter_relevant_scores(fused)
        if not fused:
            return []

        tie_breakers: dict[int, tuple[object, ...]] = {}
        for chunk_id in fused:
            base = text_by_id.get(chunk_id) or semantic_by_id.get(chunk_id)
            if base is None:
                continue
            tie_breakers[chunk_id] = (
                _normalized_source_path(base.source_path),
                base.chunk_no,
                base.char_start if base.char_start is not None else -1,
                chunk_id,
            )

        ordered_ids = order_fused_scores(fused, tie_breakers=tie_breakers)
        query_terms = {term.casefold() for term in _WORD_RE.findall(query_text) if term and term not in _RU_STOPWORDS}
        key_terms = set(rewritten.key_terms)
        reranked = sorted(
            ordered_ids,
            key=lambda chunk_id: (
                -_rerank_score(
                    fused_score=float(fused[chunk_id]),
                    candidate=text_by_id.get(chunk_id) or semantic_by_id[chunk_id],
                    query_terms=query_terms,
                    key_terms=key_terms,
                ),
                tie_breakers.get(chunk_id, ()),
            ),
        )

        results: list[HybridSearchHit] = []
        for chunk_id in reranked:
            keyword_hit = text_by_id.get(chunk_id)
            semantic_hit = semantic_by_id.get(chunk_id)
            base = keyword_hit or semantic_hit
            if base is None:
                continue

            if keyword_hit is not None:
                excerpt_source = keyword_hit.excerpt
            elif semantic_hit is not None:
                excerpt_source = semantic_hit.excerpt
            else:
                excerpt_source = ""

            excerpt = excerpt_source.strip()
            display = _display_text(base, excerpt=excerpt)
            results.append(
                HybridSearchHit(
                    source_path=base.source_path,
                    title=base.title,
                    author=base.author,
                    format_name=base.format_name,
                    chunk_id=chunk_id,
                    chunk_no=base.chunk_no,
                    page=base.page,
                    chapter=base.chapter,
                    item_id=base.item_id,
                    char_start=base.char_start,
                    char_end=base.char_end,
                    excerpt=excerpt,
                    keyword_rank=keyword_hit.rank if keyword_hit else None,
                    semantic_score=semantic_hit.score if semantic_hit else None,
                    hybrid_score=float(fused[chunk_id]),
                    display=display,
                )
            )
            if len(results) >= safe_limit:
                break

        return results
