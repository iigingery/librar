from __future__ import annotations

import re
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from librar.ingestion.adapters.fb2_adapter import FB2Adapter

_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")


def _pick_fb2_fixture() -> Path:
    fixtures = sorted(Path("books").glob("*.fb2"))
    if not fixtures:
        raise AssertionError("Expected at least one .fb2 fixture in books/")
    return fixtures[0]


def test_fb2_adapter_extracts_raw_fb2_with_russian_text() -> None:
    fixture = _pick_fb2_fixture()
    adapter = FB2Adapter()

    result = adapter.extract(fixture)

    assert result.metadata.format == "fb2"
    assert result.metadata.title
    assert result.blocks
    joined = " ".join(block.text for block in result.blocks)
    assert _CYRILLIC_RE.search(joined)


def test_fb2_adapter_extracts_zipped_fb2_payload() -> None:
    fixture = _pick_fb2_fixture()
    adapter = FB2Adapter()

    with TemporaryDirectory() as tmp:
        zipped = Path(tmp) / "fixture.fb2.zip"
        with ZipFile(zipped, "w") as archive:
            archive.writestr("book.fb2", fixture.read_bytes())

        result = adapter.extract(zipped)

    assert result.metadata.format == "fb2"
    assert result.metadata.title
    assert any(block.source.item_id for block in result.blocks)
    assert _CYRILLIC_RE.search(" ".join(block.text for block in result.blocks))


def test_fb2_adapter_reads_file_from_cyrillic_path(tmp_path: Path) -> None:
    fixture = _pick_fb2_fixture()
    adapter = FB2Adapter()

    cyrillic_dir = tmp_path / "русская_папка"
    cyrillic_dir.mkdir()
    copied = cyrillic_dir / "книга_пример.fb2"
    copied.write_bytes(fixture.read_bytes())

    result = adapter.extract(copied)

    assert result.blocks
    assert _CYRILLIC_RE.search(" ".join(block.text for block in result.blocks))
