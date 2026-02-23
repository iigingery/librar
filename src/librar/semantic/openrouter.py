"""OpenRouter embedding client used by semantic indexing and query flows."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Callable, Sequence

import numpy as np

from librar.semantic.config import SemanticSettings


_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


@dataclass(slots=True)
class EmbeddingRequestError(RuntimeError):
    """Domain error raised for failed embedding requests or invalid responses."""

    model: str
    stage: str
    message: str

    def __str__(self) -> str:
        return f"{self.message} (model={self.model}, stage={self.stage})"


@dataclass(slots=True)
class GenerationRequestError(RuntimeError):
    """Domain error raised for failed text generation requests."""

    model: str
    message: str

    def __str__(self) -> str:
        return f"{self.message} (model={self.model})"


def _build_default_client(settings: SemanticSettings) -> Any:
    try:
        from openai import OpenAI
    except Exception as exc:  # pragma: no cover - environment-dependent
        raise EmbeddingRequestError(
            model=settings.model,
            stage="client_init",
            message=f"OpenAI SDK unavailable for OpenRouter client: {exc}",
        ) from exc

    return OpenAI(api_key=settings.api_key, base_url=settings.base_url)


def _is_retryable(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code in _RETRYABLE_STATUS_CODES:
        return True

    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True

    return type(exc).__name__ in {
        "RateLimitError",
        "APITimeoutError",
        "APIConnectionError",
        "InternalServerError",
    }


def _extract_vectors(response: Any, *, expected_count: int, model: str, stage: str) -> np.ndarray:
    data = getattr(response, "data", None)
    if not isinstance(data, list):
        raise EmbeddingRequestError(model=model, stage=stage, message="Embeddings response missing list 'data'")
    if len(data) != expected_count:
        raise EmbeddingRequestError(
            model=model,
            stage=stage,
            message=f"Embeddings response count mismatch: expected {expected_count}, got {len(data)}",
        )

    vectors: list[list[float]] = []
    dimension: int | None = None

    for item in data:
        embedding = getattr(item, "embedding", None)
        if embedding is None and isinstance(item, dict):
            embedding = item.get("embedding")
        if not isinstance(embedding, (list, tuple)) or len(embedding) == 0:
            raise EmbeddingRequestError(model=model, stage=stage, message="Embedding row missing numeric vector")

        numeric = [float(value) for value in embedding]
        if dimension is None:
            dimension = len(numeric)
        elif len(numeric) != dimension:
            raise EmbeddingRequestError(
                model=model,
                stage=stage,
                message=f"Embedding dimension mismatch: expected {dimension}, got {len(numeric)}",
            )

        vectors.append(numeric)

    return np.asarray(vectors, dtype=np.float32)


class OpenRouterEmbedder:
    """OpenRouter embeddings wrapper with response validation and retry semantics."""

    def __init__(
        self,
        settings: SemanticSettings,
        *,
        client: Any | None = None,
        max_retries: int = 2,
        retry_base_seconds: float = 0.25,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        if retry_base_seconds < 0:
            raise ValueError("retry_base_seconds cannot be negative")

        self._settings = settings
        self._client = client or _build_default_client(settings)
        self._max_retries = max_retries
        self._retry_base_seconds = retry_base_seconds
        self._sleep = sleep

    @property
    def model(self) -> str:
        return self._settings.model

    def embed_query(self, query: str) -> np.ndarray:
        query_text = query.strip()
        if not query_text:
            raise ValueError("query cannot be empty")
        vectors = self.embed_texts([query_text], stage="query")
        return vectors[0]

    def embed_texts(self, texts: Sequence[str], *, stage: str = "chunks") -> np.ndarray:
        payload = [text.strip() for text in texts if text and text.strip()]
        if not payload:
            raise ValueError("texts cannot be empty")

        response = self._request_embeddings(payload, stage=stage)
        return _extract_vectors(response, expected_count=len(payload), model=self._settings.model, stage=stage)

    def _request_embeddings(self, payload: list[str], *, stage: str) -> Any:
        attempts = self._max_retries + 1
        last_error: Exception | None = None

        for attempt in range(attempts):
            try:
                return self._client.embeddings.create(model=self._settings.model, input=payload)
            except Exception as exc:  # pragma: no cover - covered via tests with stubs
                last_error = exc
                should_retry = attempt < self._max_retries and _is_retryable(exc)
                if not should_retry:
                    break
                delay = self._retry_base_seconds * (2**attempt)
                self._sleep(delay)

        detail = str(last_error) if last_error is not None else "unknown OpenRouter error"
        raise EmbeddingRequestError(
            model=self._settings.model,
            stage=stage,
            message=f"Embedding request failed after {attempts} attempt(s): {detail}",
        ) from last_error


class OpenRouterGenerator:
    """OpenRouter text generation wrapper with basic validation and retries."""

    def __init__(
        self,
        settings: SemanticSettings,
        *,
        client: Any | None = None,
        max_retries: int = 2,
        retry_base_seconds: float = 0.25,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        if retry_base_seconds < 0:
            raise ValueError("retry_base_seconds cannot be negative")

        self._settings = settings
        self._client = client or _build_default_client(settings)
        self._max_retries = max_retries
        self._retry_base_seconds = retry_base_seconds
        self._sleep = sleep

    def generate_text(
        self,
        *,
        prompt: str,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 350,
    ) -> str:
        prompt_text = prompt.strip()
        if not prompt_text:
            raise ValueError("prompt cannot be empty")
        if not model.strip():
            raise ValueError("model cannot be empty")
        if max_tokens < 1:
            raise ValueError("max_tokens must be >= 1")

        response = self._request_generation(
            prompt=prompt_text,
            model=model.strip(),
            temperature=temperature,
            max_tokens=max_tokens,
        )

        choices = getattr(response, "choices", None)
        if not isinstance(choices, list) or not choices:
            raise GenerationRequestError(model=model, message="Generation response missing choices")

        first = choices[0]
        message = getattr(first, "message", None)
        content = getattr(message, "content", None) if message is not None else None
        if content is None and isinstance(first, dict):
            message_dict = first.get("message", {})
            if isinstance(message_dict, dict):
                content = message_dict.get("content")

        if isinstance(content, list):
            content = "".join(str(part.get("text", "")) for part in content if isinstance(part, dict))

        text = str(content or "").strip()
        if not text:
            raise GenerationRequestError(model=model, message="Generation response returned empty text")
        return text

    def _request_generation(self, *, prompt: str, model: str, temperature: float, max_tokens: int) -> Any:
        attempts = self._max_retries + 1
        last_error: Exception | None = None

        for attempt in range(attempts):
            try:
                return self._client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "Отвечай на русском языке."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except Exception as exc:  # pragma: no cover - covered via tests with stubs
                last_error = exc
                should_retry = attempt < self._max_retries and _is_retryable(exc)
                if not should_retry:
                    break
                delay = self._retry_base_seconds * (2**attempt)
                self._sleep(delay)

        detail = str(last_error) if last_error is not None else "unknown OpenRouter error"
        raise GenerationRequestError(
            model=model,
            message=f"Generation request failed after {attempts} attempt(s): {detail}",
        ) from last_error
