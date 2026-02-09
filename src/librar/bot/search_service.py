"""Async bridge from bot handlers to hybrid search CLI."""

from __future__ import annotations

import asyncio
import json
import ntpath
from dataclasses import dataclass
from pathlib import Path
import sys


DEFAULT_SEARCH_TIMEOUT_SECONDS = 25.0


@dataclass(frozen=True, slots=True)
class SearchResult:
    source_path: str
    chunk_id: int
    chunk_no: int
    display: str
    excerpt: str
    title: str | None = None
    author: str | None = None
    format_name: str | None = None
    page: int | None = None
    chapter: str | None = None
    hybrid_score: float | None = None


@dataclass(frozen=True, slots=True)
class SearchResponse:
    results: tuple[SearchResult, ...]
    error: str | None = None
    timed_out: bool = False


def _normalize_source_path(source_path: str) -> str:
    cleaned = source_path.strip().replace("/", "\\")
    cwd = str(Path.cwd()).replace("/", "\\")
    if ntpath.isabs(cleaned):
        normalized = ntpath.normpath(cleaned)
    else:
        normalized = ntpath.normpath(ntpath.join(cwd, cleaned))
    return normalized.casefold()


def _to_int(value: object, *, default: int = -1) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_optional_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _to_optional_float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _parse_results(raw_results: object) -> list[SearchResult]:
    if not isinstance(raw_results, list):
        raise ValueError("Invalid search payload: 'results' must be a list")

    parsed: list[SearchResult] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        source_path = str(item.get("source_path", "")).strip()
        display = str(item.get("display", "")).strip()
        excerpt = str(item.get("excerpt", "")).strip()
        if not source_path or not display:
            continue
        parsed.append(
            SearchResult(
                source_path=source_path,
                chunk_id=_to_int(item.get("chunk_id")),
                chunk_no=_to_int(item.get("chunk_no"), default=0),
                display=display,
                excerpt=excerpt,
                title=str(item.get("title")) if item.get("title") is not None else None,
                author=str(item.get("author")) if item.get("author") is not None else None,
                format_name=str(item.get("format")) if item.get("format") is not None else None,
                page=_to_optional_int(item.get("page")),
                chapter=str(item.get("chapter")) if item.get("chapter") is not None else None,
                hybrid_score=_to_optional_float(item.get("hybrid_score")),
            )
        )
    return parsed


def _dedupe_results(results: list[SearchResult]) -> tuple[SearchResult, ...]:
    deduped: list[SearchResult] = []
    seen: set[tuple[str, int]] = set()
    for result in results:
        key = (_normalize_source_path(result.source_path), result.chunk_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(result)
    return tuple(deduped)


async def search_hybrid_cli(
    *,
    query: str,
    db_path: str | Path = ".librar-search.db",
    index_path: str | Path = ".librar-semantic.faiss",
    limit: int = 20,
    timeout_seconds: float = DEFAULT_SEARCH_TIMEOUT_SECONDS,
) -> SearchResponse:
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "librar.cli.search_hybrid",
        "--db-path",
        str(db_path),
        "--index-path",
        str(index_path),
        "--query",
        query,
        "--limit",
        str(limit),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        return SearchResponse(results=(), error="Search timed out", timed_out=True)

    stdout_text = stdout_bytes.decode("utf-8", errors="replace")
    stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()

    if proc.returncode != 0:
        message = f"Hybrid CLI failed with exit code {proc.returncode}"
        if stderr_text:
            message = f"{message}: {stderr_text}"
        return SearchResponse(results=(), error=message)

    try:
        payload = json.loads(stdout_text)
    except json.JSONDecodeError:
        return SearchResponse(results=(), error="Hybrid CLI returned malformed JSON")

    if not isinstance(payload, dict):
        return SearchResponse(results=(), error="Hybrid CLI payload is not an object")

    if payload.get("error"):
        return SearchResponse(results=(), error=str(payload["error"]))

    try:
        parsed = _parse_results(payload.get("results", []))
    except ValueError as exc:
        return SearchResponse(results=(), error=str(exc))

    return SearchResponse(results=_dedupe_results(parsed))
