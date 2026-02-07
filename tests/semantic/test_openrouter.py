from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import numpy as np
import pytest

from librar.semantic.config import SemanticSettings
from librar.semantic.openrouter import EmbeddingRequestError, OpenRouterEmbedder


def _response(vectors: list[list[float]]) -> SimpleNamespace:
    return SimpleNamespace(data=[SimpleNamespace(embedding=vector) for vector in vectors])


@dataclass
class _HttpError(Exception):
    status_code: int
    detail: str

    def __str__(self) -> str:
        return self.detail


class _FakeEmbeddingsAPI:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, list[str]]] = []

    def create(self, *, model: str, input: list[str]) -> object:
        self.calls.append((model, input))
        if not self._responses:
            raise RuntimeError("No fake response configured")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class _FakeClient:
    def __init__(self, responses: list[object]) -> None:
        self.embeddings = _FakeEmbeddingsAPI(responses)


def _settings() -> SemanticSettings:
    return SemanticSettings(
        api_key="sk-or-v1-test",
        model="openai/text-embedding-3-small",
        base_url="https://openrouter.ai/api/v1",
    )


def test_embed_texts_returns_float32_vectors_on_success() -> None:
    client = _FakeClient([_response([[0.1, 0.2], [0.3, 0.4]])])
    embedder = OpenRouterEmbedder(_settings(), client=client)

    vectors = embedder.embed_texts(["alpha", "beta"])

    assert vectors.dtype == np.float32
    assert vectors.shape == (2, 2)
    assert client.embeddings.calls == [("openai/text-embedding-3-small", ["alpha", "beta"])]


def test_embedder_retries_on_transient_error_then_succeeds() -> None:
    delays: list[float] = []
    client = _FakeClient(
        [
            _HttpError(status_code=429, detail="rate limited"),
            _response([[1.0, 0.0, 0.0]]),
        ]
    )
    embedder = OpenRouterEmbedder(
        _settings(),
        client=client,
        max_retries=2,
        retry_base_seconds=0.5,
        sleep=delays.append,
    )

    vector = embedder.embed_query("книга")

    assert vector.shape == (3,)
    assert delays == [0.5]
    assert len(client.embeddings.calls) == 2


def test_embedder_raises_on_terminal_failures() -> None:
    delays: list[float] = []
    client = _FakeClient(
        [
            _HttpError(status_code=500, detail="temporary"),
            _HttpError(status_code=500, detail="still failing"),
            _HttpError(status_code=500, detail="final failure"),
        ]
    )
    embedder = OpenRouterEmbedder(
        _settings(),
        client=client,
        max_retries=2,
        retry_base_seconds=0.1,
        sleep=delays.append,
    )

    with pytest.raises(EmbeddingRequestError, match="openai/text-embedding-3-small"):
        embedder.embed_texts(["развитие души"], stage="chunks")

    assert delays == [0.1, 0.2]
    assert len(client.embeddings.calls) == 3
