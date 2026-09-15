"""The LLM provider seam: stages depend on this Protocol, never on a concrete client.

TODO(step-4): implement `mock` (deterministic, offline), `ollama`, and `openai` providers here,
selected via settings. `StubProvider` below exists only to exercise the Step-3 engine/stages
end-to-end without a real model — it is not one of those three.
"""

from __future__ import annotations

from typing import Protocol


class LLMProvider(Protocol):
    async def describe(self, images: list[str], title: str, meta: dict[str, str] | None = None) -> str | None: ...

    async def translate(self, text: str, target_lang: str) -> str | None: ...


class StubProvider:
    """Trivial deterministic stub: no network, no model. For Step-3 wiring/tests only."""

    async def describe(self, images: list[str], title: str, meta: dict[str, str] | None = None) -> str | None:
        return f"[stub description of '{title}']" if images else None

    async def translate(self, text: str, target_lang: str) -> str | None:
        return f"[{target_lang}] {text}"
