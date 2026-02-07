"""Runtime configuration for semantic indexing and retrieval."""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Mapping


DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


@dataclass(frozen=True, slots=True)
class SemanticSettings:
    """Validated OpenRouter settings used by semantic modules."""

    api_key: str
    model: str
    base_url: str = DEFAULT_OPENROUTER_BASE_URL

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "SemanticSettings":
        source: Mapping[str, str] = os.environ if environ is None else environ

        api_key = source.get("OPENROUTER_API_KEY", "").strip()
        model = source.get("OPENROUTER_EMBEDDING_MODEL", "").strip()
        base_url = source.get("OPENROUTER_BASE_URL", DEFAULT_OPENROUTER_BASE_URL).strip()

        missing: list[str] = []
        if not api_key:
            missing.append("OPENROUTER_API_KEY")
        if not model:
            missing.append("OPENROUTER_EMBEDDING_MODEL")

        if missing:
            missing_text = ", ".join(missing)
            raise ValueError(f"Missing required semantic environment variables: {missing_text}")

        if not base_url:
            raise ValueError("OPENROUTER_BASE_URL cannot be empty")
        if not (base_url.startswith("http://") or base_url.startswith("https://")):
            raise ValueError("OPENROUTER_BASE_URL must start with http:// or https://")

        return cls(api_key=api_key, model=model, base_url=base_url.rstrip("/"))
