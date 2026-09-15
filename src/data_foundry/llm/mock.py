"""Deterministic, offline LLM provider. No network, no GPU, no randomness.

Same input -> same output, always. This is what makes `make test` (and `SOURCE=fixtures` runs)
hermetic: no flaky assertions on real model output, no external dependency in CI.
"""

from __future__ import annotations


class MockProvider:
    async def describe(self, images: list[str], title: str, meta: dict[str, str] | None = None) -> str | None:
        if not images:
            return None
        code = (meta or {}).get("code", "?")
        return f"[mock-description] {title} (obra {code})"

    async def translate(self, text: str, target_lang: str) -> str | None:
        if not text:
            return None
        return f"[{target_lang}] {text}"
