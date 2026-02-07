from __future__ import annotations

import json
from pathlib import Path

from librar.cli.index_books import main as index_cli_main
from librar.search.indexer import SearchIndexer


def _write_txt(path: Path, *, title: str, body: str) -> None:
    path.write_text(f"Title: {title}\nAuthor: Tester\n\n{body}\n", encoding="utf-8")


def test_first_run_indexes_all_books(tmp_path: Path) -> None:
    books_dir = tmp_path / "books"
    books_dir.mkdir()
    _write_txt(books_dir / "a.txt", title="A", body="Книги и книга в одном тексте.")
    _write_txt(books_dir / "b.txt", title="B", body="Другая книга и еще текст.")

    db_path = tmp_path / "search.db"
    with SearchIndexer.from_db_path(db_path) as indexer:
        stats = indexer.index_books(books_dir)

        assert stats.scanned == 2
        assert stats.indexed == 2
        assert stats.skipped_unchanged == 0
        assert stats.errors == 0

        row = indexer._repository.connection.execute(
            "SELECT COUNT(*) AS c FROM chunks WHERE lemma_text != ''"
        ).fetchone()
        assert row is not None
        assert int(row["c"]) > 0


def test_second_run_indexes_only_changed_and_new_books(tmp_path: Path) -> None:
    books_dir = tmp_path / "books"
    books_dir.mkdir()
    a_path = books_dir / "a.txt"
    b_path = books_dir / "b.txt"
    _write_txt(a_path, title="A", body="Первый текст про книгу.")
    _write_txt(b_path, title="B", body="Второй текст про книги.")

    db_path = tmp_path / "search.db"
    with SearchIndexer.from_db_path(db_path) as indexer:
        first = indexer.index_books(books_dir)
        assert first.indexed == 2

        second = indexer.index_books(books_dir)
        assert second.scanned == 2
        assert second.indexed == 0
        assert second.skipped_unchanged == 2
        assert second.errors == 0

        _write_txt(a_path, title="A", body="Первый текст изменен и стал длиннее.")
        _write_txt(books_dir / "c.txt", title="C", body="Новая книга появляется на третьем запуске.")

        third = indexer.index_books(books_dir)
        assert third.scanned == 3
        assert third.indexed == 2
        assert third.skipped_unchanged == 1
        assert third.errors == 0

        counts = indexer._repository.connection.execute(
            """
            SELECT b.source_path, COUNT(*) AS chunk_count
            FROM chunks c
            JOIN books b ON b.id = c.book_id
            GROUP BY b.source_path
            ORDER BY b.source_path
            """
        ).fetchall()
        by_path = {row["source_path"]: int(row["chunk_count"]) for row in counts}
        assert set(by_path) == {str(a_path), str(b_path), str(books_dir / "c.txt")}
        assert all(count > 0 for count in by_path.values())


def test_cli_returns_structured_incremental_stats(tmp_path: Path, capsys: object) -> None:
    books_dir = tmp_path / "books"
    books_dir.mkdir()
    _write_txt(books_dir / "one.txt", title="One", body="Книга для проверки CLI.")

    db_path = tmp_path / "search.db"

    first_exit = index_cli_main(["--books-path", str(books_dir), "--db-path", str(db_path)])
    first_payload = json.loads(capsys.readouterr().out)

    second_exit = index_cli_main(["--books-path", str(books_dir), "--db-path", str(db_path)])
    second_payload = json.loads(capsys.readouterr().out)

    assert first_exit == 0
    assert second_exit == 0

    assert first_payload["scanned"] == 1
    assert first_payload["indexed"] == 1
    assert first_payload["skipped_unchanged"] == 0
    assert first_payload["errors"] == 0
    assert first_payload["duration_ms"] >= 0

    assert second_payload["scanned"] == 1
    assert second_payload["indexed"] == 0
    assert second_payload["skipped_unchanged"] == 1
    assert second_payload["errors"] == 0
