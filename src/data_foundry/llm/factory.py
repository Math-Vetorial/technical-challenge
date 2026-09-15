"""Selects the concrete `LLMProvider` by `settings.llm_provider` — the only place in the pipeline
that knows which vendor is behind the description/translation calls.
"""

from __future__ import annotations

from data_foundry.config import Settings
from data_foundry.llm.base import LLMProvider
from data_foundry.llm.mock import MockProvider
from data_foundry.llm.openai_provider import OpenAIProvider


def get_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "mock":
        return MockProvider()
    if settings.llm_provider == "openai":
        return OpenAIProvider(settings)
    raise ValueError(f"unknown LLM_PROVIDER: {settings.llm_provider!r} (expected 'mock' or 'openai')")
