"""Async bridge from bot handlers to hybrid search CLI and RAG answer generation."""

from __future__ import annotations

import asyncio
import json
import ntpath
from dataclasses import dataclass
from pathlib import Path
import sys

from librar.semantic.config import SemanticSettings
from librar.semantic.openrouter import OpenRouterGenerator


DEFAULT_SEARCH_TIMEOUT_SECONDS = 25.0
DEFAULT_GENERATION_TEMPERATURE = 0.2
DEFAULT_GENERATION_MAX_TOKENS = 350
DEFAULT_MIN_RELEVANT_CHUNKS = 2
DEFAULT_MIN_TOTAL_RELEVANCE = 0.7
INSUFFICIENT_DATA_ANSWER = "В библиотеке нет достаточных данных по вопросу. Пожалуйста, переформулируйте запрос."


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


@dataclass(frozen=True, slots=True)
class AnswerSource:
    title: str
    author: str
    source_path: str
    location: str


@dataclass(frozen=True, slots=True)
class AnswerResult:
    answer: str
    sources: tuple[AnswerSource, ...]
    is_confirmed: bool
    prompt: str


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


def _format_location(result: SearchResult) -> str:
    if result.page is not None:
        return f"стр. {result.page}"
    return f"позиция {max(result.chunk_no, 0) + 1}"


def _build_prompt(
    *,
    query: str,
    results: tuple[SearchResult, ...],
    max_context_chars: int,
    history: tuple[tuple[str, str], ...] = (),
) -> str:
    fragments: list[str] = []
    current_len = 0
    for idx, result in enumerate(results, 1):
        location = _format_location(result)
        fragment = (
            f"[{idx}] title={result.title or 'Без названия'}; "
            f"author={result.author or 'Неизвестный автор'}; "
            f"source_path={result.source_path}; "
            f"location={location}\n"
            f"Фрагмент: {result.excerpt}"
        )
        if fragments and current_len + len(fragment) > max_context_chars:
            break
        fragments.append(fragment)
        current_len += len(fragment)

    context_block = "\n\n".join(fragments)
    history_block = "\n".join(
        f"- {role}: {message}"
        for role, message in history[-5:]
        if message.strip()
    )
    history_section = f"История диалога (последние релевантные реплики):\n{history_block}\n\n" if history_block else ""
    return (
        "Системная инструкция:\n"
        "Ты помощник библиотечного бота. Отвечай только на основе контекста ниже и никогда не используй внешние знания. "
        "Если контекста недостаточно, прямо напиши: 'Недостаточно данных в источниках'. "
        "Каждое утверждение подтверждай ссылками на фрагменты в формате [n].\n\n"
        f"{history_section}"
        f"Вопрос пользователя: {query}\n\n"
        f"Контекст:\n{context_block}"
    )


def _build_sources(results: tuple[SearchResult, ...]) -> tuple[AnswerSource, ...]:
    sources: list[AnswerSource] = []
    seen: set[tuple[str, str, str, str]] = set()

    for result in results:
        source = AnswerSource(
            title=result.title or "Без названия",
            author=result.author or "Неизвестный автор",
            source_path=result.source_path,
            location=_format_location(result),
        )
        key = (source.title, source.author, source.source_path, source.location)
        if key in seen:
            continue
        seen.add(key)
        sources.append(source)

    return tuple(sources)



def _has_sufficient_relevance(
    results: tuple[SearchResult, ...],
    *,
    min_chunks: int = DEFAULT_MIN_RELEVANT_CHUNKS,
    min_total_relevance: float = DEFAULT_MIN_TOTAL_RELEVANCE,
) -> bool:
    if min_chunks < 1:
        raise ValueError("min_chunks must be positive")
    if min_total_relevance < 0.0:
        raise ValueError("min_total_relevance cannot be negative")

    scored = tuple(result for result in results if result.hybrid_score is not None)
    if len(scored) < min_chunks:
        return False

    total = sum(float(result.hybrid_score or 0.0) for result in scored[:min_chunks])
    return total >= min_total_relevance

def _fallback_answer(*, prompt: str, results: tuple[SearchResult, ...]) -> AnswerResult:
    sources = _build_sources(results)
    if not sources:
        return AnswerResult(
            answer=INSUFFICIENT_DATA_ANSWER,
            sources=(),
            is_confirmed=False,
            prompt=prompt,
        )
    lead_excerpt = results[0].excerpt.strip()
    if not lead_excerpt:
        return AnswerResult(
            answer=INSUFFICIENT_DATA_ANSWER,
            sources=sources,
            is_confirmed=False,
            prompt=prompt,
        )
    return AnswerResult(answer=f"{lead_excerpt} [1]", sources=sources, is_confirmed=True, prompt=prompt)


async def answer_question(
    *,
    query: str,
    db_path: str | Path,
    index_path: str | Path,
    top_k: int,
    max_context_chars: int,
    chat_model: str,
    temperature: float = DEFAULT_GENERATION_TEMPERATURE,
    max_tokens: int = DEFAULT_GENERATION_MAX_TOKENS,
    timeout_seconds: float = DEFAULT_SEARCH_TIMEOUT_SECONDS,
    generator: OpenRouterGenerator | None = None,
    history: tuple[tuple[str, str], ...] = (),
) -> AnswerResult:
    response = await search_hybrid_cli(
        query=query,
        db_path=db_path,
        index_path=index_path,
        limit=top_k,
        timeout_seconds=timeout_seconds,
    )
    if response.error or not response.results:
        return AnswerResult(
            answer=INSUFFICIENT_DATA_ANSWER,
            sources=(),
            is_confirmed=False,
            prompt="",
        )

    selected = response.results[:top_k]
    if not _has_sufficient_relevance(selected):
        return AnswerResult(
            answer=INSUFFICIENT_DATA_ANSWER,
            sources=(),
            is_confirmed=False,
            prompt="",
        )

    prompt = _build_prompt(query=query, results=selected, max_context_chars=max_context_chars, history=history)
    semantic_settings = SemanticSettings.from_env()
    rag_generator = generator or OpenRouterGenerator(semantic_settings)

    try:
        answer_text = rag_generator.generate_text(
            prompt=prompt,
            model=chat_model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception:
        return _fallback_answer(prompt=prompt, results=selected)

    sources = _build_sources(selected)
    if not sources:
        return AnswerResult(
            answer=INSUFFICIENT_DATA_ANSWER,
            sources=(),
            is_confirmed=False,
            prompt=prompt,
        )
    return AnswerResult(answer=answer_text, sources=sources, is_confirmed=True, prompt=prompt)


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
