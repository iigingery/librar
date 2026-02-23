from __future__ import annotations

from pathlib import Path

from librar.ingestion.adapters.txt_adapter import TXTAdapter


def test_txt_adapter_decodes_utf8_and_extracts_headers(tmp_path: Path) -> None:
    sample = tmp_path / "book_utf8.txt"
    sample.write_text("Title: Луна\nAuthor: Александр\n\nПервая строка\nВторая строка\n", encoding="utf-8")

    result = TXTAdapter().extract(sample)

    assert result.metadata.format_name == "txt"
    assert result.metadata.title == "Луна"
    assert result.metadata.author == "Александр"
    assert [block.text for block in result.blocks[-2:]] == ["Первая строка", "Вторая строка"]


def test_txt_adapter_decodes_cp1251_and_emits_offsets(tmp_path: Path) -> None:
    sample = tmp_path / "book_cp1251.txt"
    raw = "Название: Путь\nАвтор: Ирина\n\nПривет мир\nТихий лес\n".encode("cp1251")
    sample.write_bytes(raw)

    result = TXTAdapter().extract(sample)

    assert result.metadata.title == "Путь"
    assert result.metadata.author == "Ирина"
    assert result.blocks
    for block in result.blocks:
        assert block.source.char_start is not None
        assert block.source.char_end is not None
        assert block.source.char_end >= block.source.char_start
        assert block.source.item_id and block.source.item_id.startswith("line-")


def test_txt_adapter_reads_cyrillic_windows_style_path(tmp_path: Path) -> None:
    cyrillic_dir = tmp_path / "тексты_проверка"
    cyrillic_dir.mkdir()
    sample = cyrillic_dir / "книга_путь.txt"
    sample.write_bytes("Название: Свет\n\nТонкая тропа\n".encode("cp1251"))

    result = TXTAdapter().extract(sample)

    assert result.metadata.title == "Свет"
    assert result.blocks
    assert any("Тонкая" in block.text for block in result.blocks)
