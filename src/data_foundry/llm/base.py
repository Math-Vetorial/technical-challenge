"""The LLM provider seam: stages depend on this Protocol, never on a concrete client.

`llm.mock.MockProvider` (deterministic, offline) and `llm.openai_provider.OpenAIProvider`
(OpenAI-compatible: Ollama or OpenAI) both implement it; `llm.factory.get_provider` selects
between them via `settings.llm_provider`.
"""

from __future__ import annotations

from typing import Protocol


class LLMProvider(Protocol):
    async def describe(self, images: list[str], title: str, meta: dict[str, str] | None = None) -> str | None: ...

    async def translate(self, text: str, target_lang: str) -> str | None: ...
