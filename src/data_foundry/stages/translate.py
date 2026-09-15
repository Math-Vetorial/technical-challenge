"""Translate stage: title/description into the catalog's target languages via the injected
LLM provider. Inputs are cleaned with Step-2 normalization before being sent out.
"""

from __future__ import annotations

from data_foundry.llm.base import LLMProvider
from data_foundry.quality.normalize import clean_text

TARGET_LANGUAGES: tuple[str, ...] = ("en", "es", "fr")


async def translate_title(
    title: str, langs: tuple[str, ...], provider: LLMProvider
) -> dict[str, str | None]:
    cleaned = clean_text(title) or title
    return {lang: await provider.translate(cleaned, lang) for lang in langs}


async def translate_description(
    description: str | None, langs: tuple[str, ...], provider: LLMProvider
) -> dict[str, str | None]:
    cleaned = clean_text(description)
    if cleaned is None:
        return dict.fromkeys(langs)
    return {lang: await provider.translate(cleaned, lang) for lang in langs}
