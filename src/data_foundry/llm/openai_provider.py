"""Real, OpenAI-compatible provider — works against Ollama *and* OpenAI via
`LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL`. Only imported/used for `make run`; never in tests.

Design note (for the README): the `LLMProvider` Protocol decouples the pipeline from the vendor —
swapping Ollama <-> OpenAI <-> mock is an env change (`LLM_PROVIDER`), never a code change. For a
production rollout, the natural next steps are **structured outputs** (JSON/Pydantic-validated
responses instead of free text, so a malformed answer fails validation instead of silently
corrupting a downstream field) and a **gold-set regression check** (a small set of known works
whose expected description/translation shape is asserted on every model or prompt change). Not
needed for this challenge's plain-text prompts, but worth flagging as the productionization path.
"""

from __future__ import annotations

import openai

from data_foundry.config import Settings
from data_foundry.logging_setup import get_logger
from data_foundry.orchestrator.engine import TransientError

logger = get_logger(__name__)

# Connection/timeout/rate-limit failures are worth retrying; other API errors (auth, bad request)
# are not, so they propagate as-is rather than being wrapped.
_TRANSIENT_OPENAI_ERRORS: tuple[type[Exception], ...] = (openai.APIConnectionError, openai.RateLimitError)


def _format_meta(meta: dict[str, str] | None) -> str:
    if not meta:
        return ""
    parts = [f"- {k}: {v}" for k, v in meta.items() if v]
    if not parts:
        return ""
    return "\n\nDocument metadata:\n" + "\n".join(parts) + "\n"


class OpenAIProvider:
    def __init__(self, settings: Settings) -> None:
        self._client = openai.AsyncOpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key)
        self._model = settings.llm_model
        self._timeout = settings.request_timeout_s

    async def describe(self, images: list[str], title: str, meta: dict[str, str] | None = None) -> str | None:
        content: list[dict[str, object]] = [
            {
                "type": "text",
                "text": (
                    f"This document is titled '{title}'.{_format_meta(meta)}\n"
                    "Based on these pages and metadata, provide a concise description (2-3 sentences) "
                    "of what this document is about. Include the main topic, methodology if visible, "
                    "and key findings if apparent. Respond in Portuguese."
                ),
            },
            *(
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image}"}}
                for image in images
            ),
        ]
        return await self._complete(content)

    async def translate(self, text: str, target_lang: str) -> str | None:
        prompt = (
            f"Translate the following Portuguese text to {target_lang}. "
            f"Return ONLY the translated text, nothing else.\n\n{text}"
        )
        result = await self._complete(prompt)
        return result.strip("\"'") if result else result

    async def _complete(self, content: str | list[dict[str, object]]) -> str | None:
        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": content}],
                timeout=self._timeout,
            )
        except _TRANSIENT_OPENAI_ERRORS as exc:
            raise TransientError(f"LLM call failed: {exc}") from exc
        text = resp.choices[0].message.content
        return text.strip() or None if text else None
