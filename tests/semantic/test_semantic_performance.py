from __future__ import annotations

from dataclasses import dataclass
import json

import librar.cli.search_semantic as search_semantic_cli
from librar.cli.search_semantic import main as search_semantic_main
from librar.cli.search_semantic import run_search, within_latency_threshold
from librar.semantic.query import SemanticQueryService


@dataclass
class _StubHit:
    value: str = "hit"

    def to_dict(self) -> dict[str, str]:
        return {"value": self.value}


class _StubService:
    def __enter__(self) -> "_StubService":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def search(self, *, query: str, limit: int) -> list[_StubHit]:
        assert query
        return [_StubHit() for _ in range(min(limit, 1))]


def test_run_search_records_repeated_latency_measurements(monkeypatch) -> None:
    timeline = iter([0.0, 0.25, 0.25, 0.60, 0.60, 0.90])
    monkeypatch.setattr(search_semantic_cli.time, "perf_counter", lambda: next(timeline))

    results, measurements = run_search(_StubService(), query="semantic", limit=3, repeats=3)

    assert results == [{"value": "hit"}]
    assert measurements == [250.0, 350.0, 300.0]
    assert within_latency_threshold(measurements, threshold_ms=2000.0) is True


def test_latency_threshold_flags_slow_queries() -> None:
    assert within_latency_threshold([1900.0, 1999.0], threshold_ms=2000.0) is True
    assert within_latency_threshold([1900.0, 2100.0], threshold_ms=2000.0) is False


def test_cli_returns_nonzero_when_latency_threshold_exceeded(monkeypatch, capsys: object) -> None:
    stub_service = _StubService()
    monkeypatch.setattr(
        SemanticQueryService,
        "from_db_path",
        classmethod(lambda cls, *, db_path, index_path: stub_service),
    )
    monkeypatch.setattr(search_semantic_cli, "run_search", lambda service, *, query, limit, repeats: ([{"value": "hit"}], [2300.0]))

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
            "1",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert payload["latency_within_threshold"] is False
    assert payload["measurements_ms"] == [2300.0]
