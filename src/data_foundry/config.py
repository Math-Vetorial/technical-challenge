"""Typed settings for the pipeline (env / .env backed)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM — TODO(step-4): consumed by the pluggable provider abstraction (mock/ollama/openai)
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"
    llm_model: str = "gemma4:e2b"

    # Source — TODO(step-2/3): consumed by the scraping/download stage
    base_url: str = "https://dominiopublico.mec.gov.br/pesquisa"
    list_url: str = (
        "https://dominiopublico.mec.gov.br/pesquisa/ResultadoPesquisaObraForm.do?"
        "first=10&skip=0&ds_titulo=&co_autor=&no_autor="
        "&co_categoria=41&pagina=1&select_action=Submit"
        "&co_midia=2&co_obra=&co_idioma="
        "&colunaOrdenar=NU_PAGE_HITS&ordem=desc"
    )

    # Layers — bronze/silver/gold roots
    data_dir: Path = REPO_ROOT / "data"

    # Scale knobs — TODO(step-3): consumed by the async orchestrator
    download_concurrency: int = 4
    llm_concurrency: int = 2
    request_timeout_s: int = 30
    max_retries: int = 3
    min_books: int = 10

    @computed_field  # type: ignore[prop-decorator]
    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def staging_dir(self) -> Path:
        return self.data_dir / "staging"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def curated_dir(self) -> Path:
        return self.data_dir / "curated"

    def redacted(self) -> dict[str, Any]:
        """Settings as a plain dict with the LLM secret masked, safe for a manifest."""
        data = self.model_dump(mode="json")
        if data.get("llm_api_key"):
            data["llm_api_key"] = "***redacted***"
        return data


settings = Settings()

# TODO(step-2/3): scripts/ still import these flat constants directly; drop them once the
# scripts' logic is refactored into stages/ and they consume `settings` instead.
BASE_URL = settings.base_url
LIST_URL = settings.list_url
DATA_DIR = settings.data_dir
PDF_DIR = settings.data_dir / "pdfs"
OUTPUT_DIR = settings.data_dir / "output"
LLM_BASE_URL = settings.llm_base_url
LLM_API_KEY = settings.llm_api_key
LLM_MODEL = settings.llm_model
