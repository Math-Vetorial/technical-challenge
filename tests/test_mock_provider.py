"""MockProvider: deterministic, offline. No network, no GPU."""

from __future__ import annotations

import asyncio

from data_foundry.llm.mock import MockProvider


def test_describe_is_deterministic_and_includes_title_and_code():
    async def scenario() -> None:
        provider = MockProvider()
        result_1 = await provider.describe(["b64image"], "Dom Casmurro", {"code": "obra42"})
        result_2 = await provider.describe(["b64image"], "Dom Casmurro", {"code": "obra42"})

        assert result_1 == result_2
        assert "Dom Casmurro" in result_1
        assert "obra42" in result_1

    asyncio.run(scenario())


def test_describe_returns_none_without_images():
    async def scenario() -> None:
        provider = MockProvider()
        assert await provider.describe([], "Dom Casmurro") is None

    asyncio.run(scenario())


def test_describe_handles_missing_meta():
    async def scenario() -> None:
        provider = MockProvider()
        result = await provider.describe(["b64image"], "Dom Casmurro")
        assert result == "[mock-description] Dom Casmurro (obra ?)"

    asyncio.run(scenario())


def test_translate_is_deterministic():
    async def scenario() -> None:
        provider = MockProvider()
        result_1 = await provider.translate("Um romance.", "en")
        result_2 = await provider.translate("Um romance.", "en")

        assert result_1 == result_2 == "[en] Um romance."

    asyncio.run(scenario())


def test_translate_preserves_empty_as_none():
    async def scenario() -> None:
        provider = MockProvider()
        assert await provider.translate("", "en") is None

    asyncio.run(scenario())
