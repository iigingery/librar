"""Async subprocess ingestion pipeline for automation workflows."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
from pathlib import Path
import sys


DEFAULT_PIPELINE_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True, slots=True)
class IngestionPipelineResult:
    success: bool
    title: str | None
    author: str | None
    format_name: str | None
    chunk_count: int
    is_duplicate: bool
    stage: str = "unknown"
    error: str | None = None


async def _run_cli_command(
    *args: str,
    timeout_seconds: float = DEFAULT_PIPELINE_TIMEOUT_SECONDS,
) -> tuple[bool, str, str]:
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        return False, "", f"Timed out after {int(timeout_seconds)}s: {' '.join(args)}"

    stdout_text = stdout_bytes.decode("utf-8", errors="replace")
    stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()

    if proc.returncode != 0:
        message = stderr_text or stdout_text.strip() or f"Command failed: {' '.join(args)}"
        return False, stdout_text, message

    return True, stdout_text, stderr_text


def _parse_ingest_payload(stdout_text: str) -> IngestionPipelineResult:
    try:
        payload = json.loads(stdout_text)
    except json.JSONDecodeError:
        return IngestionPipelineResult(
            success=False,
            title=None,
            author=None,
            format_name=None,
            chunk_count=0,
            is_duplicate=False,
            stage="ingest",
            error="ingest_books returned malformed JSON",
        )

    if not isinstance(payload, dict):
        return IngestionPipelineResult(
            success=False,
            title=None,
            author=None,
            format_name=None,
            chunk_count=0,
            is_duplicate=False,
            stage="ingest",
            error="ingest_books payload is not an object",
        )

    errors = payload.get("errors", [])
    if isinstance(errors, list) and errors:
        first_error = errors[0]
        if isinstance(first_error, dict) and "error" in first_error:
            error_text = str(first_error.get("error") or "Unknown ingestion error")
        else:
            error_text = str(first_error)
        return IngestionPipelineResult(
            success=False,
            title=None,
            author=None,
            format_name=None,
            chunk_count=0,
            is_duplicate=False,
            stage="ingest",
            error=error_text,
        )

    results = payload.get("results", [])
    if not isinstance(results, list) or not results:
        return IngestionPipelineResult(
            success=False,
            title=None,
            author=None,
            format_name=None,
            chunk_count=0,
            is_duplicate=False,
            stage="ingest",
            error="No ingestion result returned for file",
        )

    first = results[0]
    if not isinstance(first, dict):
        return IngestionPipelineResult(
            success=False,
            title=None,
            author=None,
            format_name=None,
            chunk_count=0,
            is_duplicate=False,
            stage="ingest",
            error="ingest_books result entry is invalid",
        )

    return IngestionPipelineResult(
        success=True,
        title=str(first.get("title")) if first.get("title") is not None else None,
        author=str(first.get("author")) if first.get("author") is not None else None,
        format_name=str(first.get("format")) if first.get("format") is not None else None,
        chunk_count=int(first.get("chunk_count") or 0),
        is_duplicate=bool(first.get("is_duplicate", False)),
        stage="ingest",
    )


async def run_ingestion_pipeline(
    file_path: Path,
    *,
    db_path: str,
    index_path: str,
    books_path: str,
    cache_file: str,
) -> IngestionPipelineResult:
    ingest_ok, ingest_stdout, ingest_error = await _run_cli_command(
        "-m",
        "librar.cli.ingest_books",
        "--path",
        str(file_path),
        "--cache-file",
        cache_file,
    )
    if not ingest_ok:
        return IngestionPipelineResult(
            success=False,
            title=None,
            author=None,
            format_name=None,
            chunk_count=0,
            is_duplicate=False,
            stage="ingest",
            error=ingest_error,
        )

    result = _parse_ingest_payload(ingest_stdout)
    if not result.success:
        return result

    if result.is_duplicate:
        return result

    index_ok, _, index_error = await _run_cli_command(
        "-m",
        "librar.cli.index_books",
        "--db-path",
        db_path,
        "--books-path",
        books_path,
    )
    if not index_ok:
        return IngestionPipelineResult(
            success=False,
            title=result.title,
            author=result.author,
            format_name=result.format_name,
            chunk_count=result.chunk_count,
            is_duplicate=False,
            stage="index_metadata",
            error=index_error,
        )

    semantic_ok, _, semantic_error = await _run_cli_command(
        "-m",
        "librar.cli.index_semantic",
        "--db-path",
        db_path,
        "--index-path",
        index_path,
    )
    if not semantic_ok:
        return IngestionPipelineResult(
            success=False,
            title=result.title,
            author=result.author,
            format_name=result.format_name,
            chunk_count=result.chunk_count,
            is_duplicate=False,
            stage="index_semantic",
            error=semantic_error,
        )

    return IngestionPipelineResult(
        success=result.success,
        title=result.title,
        author=result.author,
        format_name=result.format_name,
        chunk_count=result.chunk_count,
        is_duplicate=result.is_duplicate,
        stage="done",
    )
