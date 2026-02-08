"""FTS5 query builder and result mapping for text search."""

from __future__ import annotations

from dataclasses import dataclass
import re
import sqlite3

from razdel import tokenize

from librar.search.normalize import normalize_query


_WORD_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё]+")


@dataclass(slots=True)
class SearchHit:
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
    rank: float
    excerpt: str

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
            "rank": self.rank,
            "excerpt": self.excerpt,
        }


def _extract_terms(text: str) -> list[str]:
    terms: list[str] = []
    for token in tokenize(text.lower().replace("ё", "е")):
        value = token.text.strip()
        if value and _WORD_RE.fullmatch(value):
            terms.append(value)
    return terms


def _quoted(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def build_match_expression(query: str, *, phrase_mode: bool = False) -> str:
    raw_terms = _extract_terms(query)
    lemma_terms = normalize_query(query).split()

    if not raw_terms and not lemma_terms:
        return ""

    if phrase_mode:
        expressions: list[str] = []
        if raw_terms:
            expressions.append(f"raw_text:{_quoted(' '.join(raw_terms))}")
        if lemma_terms:
            expressions.append(f"lemma_text:{_quoted(' '.join(lemma_terms))}")
        return " OR ".join(f"({expression})" for expression in expressions)

    expressions = []
    if raw_terms:
        raw_and = " AND ".join(f"raw_text:{_quoted(term)}" for term in raw_terms)
        expressions.append(f"({raw_and})")
    if lemma_terms:
        lemma_and = " AND ".join(f"lemma_text:{_quoted(term)}" for term in lemma_terms)
        expressions.append(f"({lemma_and})")
    return " OR ".join(expressions)


def search_chunks(
    connection: sqlite3.Connection,
    *,
    query: str,
    limit: int = 10,
    phrase_mode: bool = False,
    author_filter: str | None = None,
    format_filter: str | None = None,
) -> list[SearchHit]:
    match_expression = build_match_expression(query, phrase_mode=phrase_mode)
    if not match_expression:
        return []

    safe_limit = max(1, min(limit, 100))
    where_clauses = ["chunks_fts MATCH ?"]
    params: list[object] = [match_expression]

    if author_filter and author_filter.strip():
        where_clauses.append("LOWER(COALESCE(b.author, '')) LIKE ?")
        params.append(f"%{author_filter.strip().lower()}%")

    if format_filter and format_filter.strip():
        where_clauses.append("LOWER(COALESCE(b.format, '')) = ?")
        params.append(format_filter.strip().lower())

    sql = f"""
        SELECT
            b.source_path AS source_path,
            b.title AS title,
            b.author AS author,
            b.format AS format_name,
            c.id AS chunk_id,
            c.chunk_no AS chunk_no,
            c.page AS page,
            c.chapter AS chapter,
            c.item_id AS item_id,
            c.char_start AS char_start,
            c.char_end AS char_end,
            c.raw_text AS raw_text,
            bm25(chunks_fts, 1.5, 1.0) AS rank,
            snippet(chunks_fts, 0, '[', ']', ' ... ', 24) AS excerpt
        FROM chunks_fts
        JOIN chunks c ON c.id = chunks_fts.rowid
        JOIN books b ON b.id = c.book_id
        WHERE {' AND '.join(where_clauses)}
        ORDER BY rank ASC, c.id ASC
        LIMIT ?
    """
    params.append(safe_limit)
    rows = connection.execute(sql, tuple(params)).fetchall()

    return [
        SearchHit(
            source_path=row["source_path"],
            title=row["title"],
            author=row["author"],
            format_name=row["format_name"],
            chunk_id=int(row["chunk_id"]),
            chunk_no=int(row["chunk_no"]),
            page=row["page"],
            chapter=row["chapter"],
            item_id=row["item_id"],
            char_start=row["char_start"],
            char_end=row["char_end"],
            rank=float(row["rank"]),
            excerpt=row["excerpt"] or row["raw_text"],
        )
        for row in rows
    ]
