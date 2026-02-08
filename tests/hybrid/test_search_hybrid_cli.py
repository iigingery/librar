from __future__ import annotations

import json

from librar.cli.search_hybrid import main as search_hybrid_main
from librar.hybrid.query import HybridQueryService, HybridSearchHit


class _StubService:
    def __init__(self, hits: list[HybridSearchHit]) -> None:
        self._hits = hits
        self.last_kwargs: dict[str, object] | None = None

    def __enter__(self) -> "_StubService":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def search(self, **kwargs) -> list[HybridSearchHit]:
        self.last_kwargs = kwargs
        limit = int(kwargs.get("limit", 10))
        return self._hits[:limit]


def _hit(chunk_id: int, title: str, score: float) -> HybridSearchHit:
    return HybridSearchHit(
        source_path=f"books\\{title}.fb2",
        title=title,
        author="Author",
        format_name="fb2",
        chunk_id=chunk_id,
        chunk_no=0,
        page=1,
        chapter="ch-1",
        item_id=None,
        char_start=0,
        char_end=20,
        excerpt="example excerpt",
        keyword_rank=-1.5,
        semantic_score=0.8,
        hybrid_score=score,
        display=f"{title} — page 1 — example excerpt",
    )


def test_hybrid_cli_returns_machine_readable_output(monkeypatch, capsys: object) -> None:
    stub = _StubService([_hit(10, "A", 0.91), _hit(11, "B", 0.73)])
    monkeypatch.setattr(
        HybridQueryService,
        "from_db_path",
        classmethod(lambda cls, *, db_path, index_path: stub),
    )

    exit_code = search_hybrid_main(
        [
            "--db-path",
            "tmp/search.db",
            "--index-path",
            "tmp/semantic.faiss",
            "--query",
            "spiritual growth",
            "--limit",
            "5",
            "--alpha",
            "0.65",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["query"] == "spiritual growth"
    assert payload["alpha"] == 0.65
    assert payload["limit"] == 5
    assert payload["results"][0]["hybrid_score"] >= payload["results"][1]["hybrid_score"]
    assert "display" in payload["results"][0]


def test_hybrid_cli_passes_filters_and_phrase_mode(monkeypatch, capsys: object) -> None:
    stub = _StubService([_hit(10, "Only", 0.88)])
    monkeypatch.setattr(
        HybridQueryService,
        "from_db_path",
        classmethod(lambda cls, *, db_path, index_path: stub),
    )

    exit_code = search_hybrid_main(
        [
            "--db-path",
            "tmp/search.db",
            "--index-path",
            "tmp/semantic.faiss",
            "--query",
            "книга",
            "--author",
            "mahar",
            "--format",
            "fb2",
            "--phrase-mode",
            "--candidate-limit",
            "77",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["phrase_mode"] is True
    assert payload["author_filter"] == "mahar"
    assert payload["format_filter"] == "fb2"
    assert stub.last_kwargs is not None
    assert stub.last_kwargs["author_filter"] == "mahar"
    assert stub.last_kwargs["format_filter"] == "fb2"
    assert stub.last_kwargs["phrase_mode"] is True
    assert stub.last_kwargs["candidate_limit"] == 77


def test_hybrid_cli_validates_alpha_range(capsys: object) -> None:
    exit_code = search_hybrid_main(
        [
            "--db-path",
            "tmp/search.db",
            "--index-path",
            "tmp/semantic.faiss",
            "--query",
            "q",
            "--alpha",
            "1.5",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert "alpha" in payload["error"]
