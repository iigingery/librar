from __future__ import annotations

import pytest

from librar.semantic.config import DEFAULT_OPENROUTER_BASE_URL, SemanticSettings


def test_settings_load_from_env_with_default_base_url() -> None:
    settings = SemanticSettings.from_env(
        {
            "OPENROUTER_API_KEY": "sk-or-v1-test",
            "OPENROUTER_EMBEDDING_MODEL": "openai/text-embedding-3-small",
        }
    )

    assert settings.api_key == "sk-or-v1-test"
    assert settings.model == "openai/text-embedding-3-small"
    assert settings.base_url == DEFAULT_OPENROUTER_BASE_URL


def test_settings_missing_required_vars_fail_fast() -> None:
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        SemanticSettings.from_env({"OPENROUTER_EMBEDDING_MODEL": "qwen/qwen3-embedding-0.6b"})

    with pytest.raises(ValueError, match="OPENROUTER_EMBEDDING_MODEL"):
        SemanticSettings.from_env({"OPENROUTER_API_KEY": "sk-or-v1-test"})


def test_settings_validate_base_url() -> None:
    with pytest.raises(ValueError, match="OPENROUTER_BASE_URL"):
        SemanticSettings.from_env(
            {
                "OPENROUTER_API_KEY": "sk-or-v1-test",
                "OPENROUTER_EMBEDDING_MODEL": "openai/text-embedding-3-small",
                "OPENROUTER_BASE_URL": "openrouter.ai/api/v1",
            }
        )
