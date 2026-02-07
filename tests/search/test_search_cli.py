from __future__ import annotations

import json
from pathlib import Path

from librar.cli.index_books import main as index_books_main
from librar.cli.search_text import main as search_text_main


def _write_txt(path: Path, *, title: str, body: str) -> None:
    path.write_text(f"Title: {title}\nAuthor: Tester\n\n{body}\n", encoding="utf-8")


def test_cli_returns_ranked_json_results_with_locators(tmp_path: Path, capsys: object) -> None:
    books_dir = tmp_path / "books"
    books_dir.mkdir()
    _write_txt(books_dir / "a.txt", title="A", body="книга книга книга в одном фрагменте")
    _write_txt(books_dir / "b.txt", title="B", body="тут слово книга встречается один раз")

    db_path = tmp_path / "search.db"
    assert index_books_main(["--books-path", str(books_dir), "--db-path", str(db_path)]) == 0
    capsys.readouterr()

    exit_code = search_text_main(["--db-path", str(db_path), "--query", "книга", "--limit", "5"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["query"] == "книга"
    assert payload["limit"] == 5
    assert payload["phrase_mode"] is False
    assert len(payload["results"]) >= 2

    first = payload["results"][0]
    second = payload["results"][1]
    assert first["source_path"].endswith("a.txt")
    assert first["rank"] <= second["rank"]
    assert isinstance(first["excerpt"], str) and first["excerpt"]
    assert "char_start" in first
    assert "char_end" in first


def test_cli_phrase_mode_and_morphology_recall(tmp_path: Path, capsys: object) -> None:
    books_dir = tmp_path / "books"
    books_dir.mkdir()
    _write_txt(books_dir / "phrase.txt", title="Phrase", body="туманная книга лежит на столе")
    _write_txt(books_dir / "morph.txt", title="Morph", body="в комнате стоят старые книги")

    db_path = tmp_path / "search.db"
    assert index_books_main(["--books-path", str(books_dir), "--db-path", str(db_path)]) == 0
    capsys.readouterr()

    phrase_exit = search_text_main(
        [
            "--db-path",
            str(db_path),
            "--query",
            "туманная книга",
            "--phrase-mode",
            "--limit",
            "3",
        ]
    )
    phrase_payload = json.loads(capsys.readouterr().out)

    morph_exit = search_text_main(["--db-path", str(db_path), "--query", "книга", "--limit", "3"])
    morph_payload = json.loads(capsys.readouterr().out)

    assert phrase_exit == 0
    assert morph_exit == 0

    assert phrase_payload["phrase_mode"] is True
    assert phrase_payload["results"]
    assert phrase_payload["results"][0]["source_path"].endswith("phrase.txt")

    paths = [row["source_path"] for row in morph_payload["results"]]
    assert any(path.endswith("morph.txt") for path in paths)
