from __future__ import annotations

from pathlib import Path

import pytest

from librar.semantic.vector_store import FaissVectorStore, VectorStoreError


def test_vector_store_create_save_reload_and_search(tmp_path: Path) -> None:
    index_path = tmp_path / "semantic.faiss"

    store = FaissVectorStore(index_path, dimension=3, metric="ip")
    store.add_or_replace(
        vector_ids=[10, 11],
        vectors=[
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
        ],
    )
    store.save()

    reloaded = FaissVectorStore(index_path, dimension=3, metric="ip")
    hits = reloaded.search([1.0, 0.0, 0.0], top_k=2)

    assert reloaded.ntotal == 2
    assert [hit.vector_id for hit in hits] == [10, 11]
    assert hits[0].score >= hits[1].score


def test_vector_store_replace_existing_id_keeps_total_size(tmp_path: Path) -> None:
    index_path = tmp_path / "semantic.faiss"
    store = FaissVectorStore(index_path, dimension=3, metric="ip")
    store.add_or_replace(vector_ids=[10, 11], vectors=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    store.add_or_replace(vector_ids=[10], vectors=[[0.0, 0.0, 1.0]])

    hits = store.search([0.0, 0.0, 1.0], top_k=2)
    assert store.ntotal == 2
    assert hits[0].vector_id == 10


def test_vector_store_reports_corrupted_index_file(tmp_path: Path) -> None:
    broken_path = tmp_path / "broken.faiss"
    broken_path.write_bytes(b"this-is-not-a-faiss-index")

    with pytest.raises(VectorStoreError, match="Failed to load FAISS index"):
        FaissVectorStore(broken_path, dimension=3, metric="ip")
