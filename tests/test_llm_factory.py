"""`get_provider` selects the right implementation per `settings.llm_provider` — no network call
is made just by constructing a provider (client construction is lazy in both SDKs)."""

from __future__ import annotations

import pytest

from data_foundry.config import Settings
from data_foundry.llm.factory import get_provider
from data_foundry.llm.mock import MockProvider
from data_foundry.llm.openai_provider import OpenAIProvider


def test_get_provider_returns_mock():
    settings = Settings(llm_provider="mock")
    assert isinstance(get_provider(settings), MockProvider)


def test_get_provider_returns_openai():
    settings = Settings(llm_provider="openai", llm_base_url="http://localhost:11434/v1", llm_api_key="ollama")
    provider = get_provider(settings)
    assert isinstance(provider, OpenAIProvider)


def test_get_provider_rejects_unknown_value():
    settings = Settings(llm_provider="not-a-real-provider")
    with pytest.raises(ValueError, match="not-a-real-provider"):
        get_provider(settings)
