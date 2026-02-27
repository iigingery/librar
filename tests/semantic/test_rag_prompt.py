"""Tests for the structured RAG system prompt used by OpenRouterGenerator."""

from __future__ import annotations

from types import SimpleNamespace

from librar.semantic.openrouter import (
    OpenRouterGenerator,
    _RAG_SYSTEM_PROMPT,
)
from librar.semantic.config import SemanticSettings


# ---------------------------------------------------------------------------
# Prompt content
# ---------------------------------------------------------------------------


def test_rag_prompt_is_non_empty_string() -> None:
    assert isinstance(_RAG_SYSTEM_PROMPT, str)
    assert len(_RAG_SYSTEM_PROMPT) > 0


def test_rag_prompt_contains_brief_answer_header() -> None:
    assert "**Краткий ответ:**" in _RAG_SYSTEM_PROMPT


def test_rag_prompt_contains_detailed_explanation_header() -> None:
    assert "**Подробное объяснение:**" in _RAG_SYSTEM_PROMPT


def test_rag_prompt_contains_sources_header() -> None:
    assert "**Источники:**" in _RAG_SYSTEM_PROMPT


def test_rag_prompt_instructs_to_use_only_context() -> None:
    # Must instruct the model to answer only from provided context.
    prompt_lower = _RAG_SYSTEM_PROMPT.lower()
    assert "контекст" in prompt_lower or "context" in prompt_lower


# ---------------------------------------------------------------------------
# Generator uses the prompt as system message
# ---------------------------------------------------------------------------


class _FakeChatCompletionsAPI:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if not self._responses:
            raise RuntimeError("No fake response configured")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class _FakeGeneratorClient:
    def __init__(self, responses: list[object]) -> None:
        self.chat = SimpleNamespace(completions=_FakeChatCompletionsAPI(responses))


def _settings() -> SemanticSettings:
    return SemanticSettings(
        api_key="sk-or-v1-test",
        model="openai/gpt-4o-mini",
        base_url="https://openrouter.ai/api/v1",
    )


def _ok_response(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
    )


def test_generator_sends_rag_prompt_as_system_message() -> None:
    client = _FakeGeneratorClient([_ok_response("Краткий ответ: текст.")])
    generator = OpenRouterGenerator(_settings(), client=client)

    generator.generate_text(prompt="Тестовый вопрос", model="openai/gpt-4o-mini")

    assert len(client.chat.completions.calls) == 1
    call_kwargs = client.chat.completions.calls[0]
    messages = call_kwargs["messages"]
    assert isinstance(messages, list)
    system_messages = [m for m in messages if m["role"] == "system"]
    assert system_messages, "No system message was sent"
    assert system_messages[0]["content"] == _RAG_SYSTEM_PROMPT


def test_generator_user_message_contains_prompt() -> None:
    client = _FakeGeneratorClient([_ok_response("Ответ на вопрос.")])
    generator = OpenRouterGenerator(_settings(), client=client)

    generator.generate_text(prompt="Что произошло в 1917?", model="openai/gpt-4o-mini")

    call_kwargs = client.chat.completions.calls[0]
    messages = call_kwargs["messages"]
    user_messages = [m for m in messages if m["role"] == "user"]
    assert user_messages
    assert "1917" in user_messages[0]["content"]
