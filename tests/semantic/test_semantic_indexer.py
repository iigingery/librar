from __future__ import annotations

from pathlib import Path

import numpy as np

from librar.search.repository import ChunkRow, SearchRepository
from librar.semantic.indexer import SemanticIndexer
from librar.semantic.semantic_repository import SemanticRepository


class _FakeEmbedder:
    model = "test-semantic-model"

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed_texts(self, texts: list[str], *, stage: str = "chunks") -> np.ndarray:
        self.calls.append(list(texts))
        vectors: list[list[float]] = []
        for text in texts:
            checksum = float(sum(ord(char) for char in text) % 101)
            vectors.append([float(len(text)), float(text.count(" ") + 1), checksum])
        return np.asarray(vectors, dtype=np.float32)


def _seed_book(repo: SearchRepository, source_path: str, body: str) -> None:
    repo.replace_book_chunks(
        source_path=source_path,
        title=source_path,
        author="tester",
        format_name="txt",
        fingerprint=f"fp-{source_path}",
        mtime_ns=1,
        chunks=[
            ChunkRow(
                chunk_no=0,
                raw_text=body,
                lemma_text=body.lower(),
                page=1,
                chapter="c1",
                item_id=None,
                char_start=0,
                char_end=len(body),
            )
        ],
    )


def test_first_run_embeds_all_chunks_and_persists_state(tmp_path: Path) -> None:
    db_path = tmp_path / "semantic.db"
    index_path = tmp_path / "semantic.faiss"

    with SearchRepository(db_path) as repo:
        _seed_book(repo, "book-a.txt", "Развитие души начинается с практики.")
        _seed_book(repo, "book-b.txt", "Духовный рост требует дисциплины и труда.")

        semantic_repo = SemanticRepository(repo.connection)
        embedder = _FakeEmbedder()
        indexer = SemanticIndexer(
            search_repository=repo,
            semantic_repository=semantic_repo,
            embedder=embedder,
            index_path=index_path,
            batch_size=4,
        )

        stats = indexer.index_chunks()

        assert stats.scanned_chunks == 2
        assert stats.embedded_chunks == 2
        assert stats.skipped_unchanged == 0
        assert stats.errors == 0
        assert stats.model == "test-semantic-model"
        assert index_path.exists()

        index_state = semantic_repo.get_index_state()
        assert index_state is not None
        assert index_state.model == "test-semantic-model"
        assert index_state.dimension == 3

        chunk_states = semantic_repo.list_chunk_states(model="test-semantic-model")
        assert len(chunk_states) == 2


def test_second_run_skips_unchanged_and_only_reembeds_changed_chunks(tmp_path: Path) -> None:
    db_path = tmp_path / "semantic.db"
    index_path = tmp_path / "semantic.faiss"

    with SearchRepository(db_path) as repo:
        _seed_book(repo, "book-a.txt", "Путь роста души начинается с тишины.")
        _seed_book(repo, "book-b.txt", "Практика укрепляет духовную устойчивость.")

        semantic_repo = SemanticRepository(repo.connection)
        embedder = _FakeEmbedder()
        indexer = SemanticIndexer(
            search_repository=repo,
            semantic_repository=semantic_repo,
            embedder=embedder,
            index_path=index_path,
            batch_size=8,
        )

        first = indexer.index_chunks()
        assert first.embedded_chunks == 2

        second = indexer.index_chunks()
        assert second.scanned_chunks == 2
        assert second.embedded_chunks == 0
        assert second.skipped_unchanged == 2
        assert second.errors == 0

        _seed_book(repo, "book-a.txt", "Путь роста души начинается с терпения и молитвы.")

        third = indexer.index_chunks()
        assert third.scanned_chunks == 2
        assert third.embedded_chunks == 1
        assert third.skipped_unchanged == 1
        assert third.errors == 0

        assert len(embedder.calls) == 2
