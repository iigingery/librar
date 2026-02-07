"""SQLite persistence helpers for semantic vector metadata."""

from __future__ import annotations

from dataclasses import dataclass
import sqlite3


@dataclass(slots=True)
class SemanticIndexState:
    model: str
    dimension: int
    metric: str
    index_path: str


@dataclass(slots=True)
class SemanticChunkState:
    chunk_id: int
    vector_id: int
    model: str
    fingerprint: str


class SemanticRepository:
    """Persistence layer for semantic index metadata and chunk mappings."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def get_index_state(self) -> SemanticIndexState | None:
        row = self._connection.execute(
            """
            SELECT model, dimension, metric, index_path
            FROM semantic_index_state
            WHERE id = 1
            """
        ).fetchone()
        if row is None:
            return None

        return SemanticIndexState(
            model=row["model"],
            dimension=int(row["dimension"]),
            metric=row["metric"],
            index_path=row["index_path"],
        )

    def upsert_index_state(self, *, model: str, dimension: int, metric: str, index_path: str) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO semantic_index_state(id, model, dimension, metric, index_path)
                VALUES(1, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    model=excluded.model,
                    dimension=excluded.dimension,
                    metric=excluded.metric,
                    index_path=excluded.index_path,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (model, dimension, metric, index_path),
            )

    def get_chunk_state(self, *, chunk_id: int, model: str) -> SemanticChunkState | None:
        row = self._connection.execute(
            """
            SELECT chunk_id, vector_id, model, fingerprint
            FROM semantic_chunk_state
            WHERE chunk_id = ? AND model = ?
            """,
            (chunk_id, model),
        ).fetchone()
        if row is None:
            return None

        return SemanticChunkState(
            chunk_id=int(row["chunk_id"]),
            vector_id=int(row["vector_id"]),
            model=row["model"],
            fingerprint=row["fingerprint"],
        )

    def upsert_chunk_state(self, *, chunk_id: int, vector_id: int, model: str, fingerprint: str) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO semantic_chunk_state(chunk_id, vector_id, model, fingerprint)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(chunk_id) DO UPDATE SET
                    vector_id=excluded.vector_id,
                    model=excluded.model,
                    fingerprint=excluded.fingerprint,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (chunk_id, vector_id, model, fingerprint),
            )

    def list_chunk_states(self, *, model: str) -> list[SemanticChunkState]:
        rows = self._connection.execute(
            """
            SELECT chunk_id, vector_id, model, fingerprint
            FROM semantic_chunk_state
            WHERE model = ?
            ORDER BY chunk_id ASC
            """,
            (model,),
        ).fetchall()

        return [
            SemanticChunkState(
                chunk_id=int(row["chunk_id"]),
                vector_id=int(row["vector_id"]),
                model=row["model"],
                fingerprint=row["fingerprint"],
            )
            for row in rows
        ]

    def delete_chunk_states_not_in(self, *, model: str, chunk_ids: set[int]) -> int:
        with self._connection:
            if not chunk_ids:
                cursor = self._connection.execute(
                    "DELETE FROM semantic_chunk_state WHERE model = ?",
                    (model,),
                )
                return int(cursor.rowcount)

            placeholders = ",".join("?" for _ in chunk_ids)
            params: tuple[object, ...] = (model, *sorted(chunk_ids))
            cursor = self._connection.execute(
                f"""
                DELETE FROM semantic_chunk_state
                WHERE model = ?
                  AND chunk_id NOT IN ({placeholders})
                """,
                params,
            )
            return int(cursor.rowcount)
