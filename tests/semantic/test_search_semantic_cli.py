from __future__ import annotations

from dataclasses import dataclass
import json

import librar.cli.search_semantic as search_semantic_cli
from librar.cli.search_semantic import main as search_semantic_main
from librar.semantic.query import SemanticQueryService


@dataclass
class _StubHit:
    source_path: str
    chunk_id: int
    chunk_no: int
    page: int | None
    chapter: str | None
    item_id: str | None
    char_start: int | None
    char_end: int | None
    score: float
    excerpt: str

    def to_dict(self) -> dict[str, str | int | float | None]:
        return {
            "source_path": self.source_path,
            "chunk_id": self.chunk_id,
            "chunk_no": self.chunk_no,
            "page": self.page,
            "chapter": self.chapter,
            "item_id": self.item_id,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "score": self.score,
            "excerpt": self.excerpt,
        }


class _StubService:
    def __init__(self, hits: list[_StubHit]) -> None:
        self._hits = hits

    def __enter__(self) -> "_StubService":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def search(self, *, query: str, limit: int) -> list[_StubHit]:
        assert query
        return self._hits[:limit]


def test_search_semantic_cli_returns_ranked_json(monkeypatch, capsys: object) -> None:
    stub = _StubService(
        [
            _StubHit("book-a.txt", 10, 0, 1, None, None, 0, 30, 0.91, "A"),
            _StubHit("book-b.txt", 11, 0, 2, None, None, 0, 30, 0.72, "B"),
        ]
    )
    monkeypatch.setattr(
        SemanticQueryService,
        "from_db_path",
        classmethod(lambda cls, *, db_path, index_path: stub),
    )

    exit_code = search_semantic_main(
        [
            "--db-path",
            "tmp/search.db",
            "--index-path",
            "tmp/semantic.faiss",
            "--query",
            "spiritual growth",
            "--limit",
            "5",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["query"] == "spiritual growth"
    assert payload["limit"] == 5
    assert [row["source_path"] for row in payload["results"]] == ["book-a.txt", "book-b.txt"]
    assert payload["results"][0]["score"] >= payload["results"][1]["score"]


def test_search_semantic_cli_measure_mode_includes_latency_fields(monkeypatch, capsys: object) -> None:
    stub = _StubService([_StubHit("book-a.txt", 10, 0, 1, None, None, 0, 30, 0.88, "A")])
    monkeypatch.setattr(
        SemanticQueryService,
        "from_db_path",
        classmethod(lambda cls, *, db_path, index_path: stub),
    )
    monkeypatch.setattr(
        search_semantic_cli,
        "run_search",
        lambda service, *, query, limit, repeats: ([row.to_dict() for row in stub.search(query=query, limit=limit)], [120.0, 150.0]),
    )

    exit_code = search_semantic_main(
        [
            "--db-path",
            "tmp/search.db",
            "--index-path",
            "tmp/semantic.faiss",
            "--query",
            "spiritual growth",
            "--measure-ms",
            "--repeats",
            "2",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["measurements_ms"] == [120.0, 150.0]
    assert payload["duration_ms"] == 150.0
    assert payload["latency_threshold_ms"] == 2000.0
    assert payload["latency_within_threshold"] is True
