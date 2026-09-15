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

    # LLM — consumed by llm/factory.get_provider; swap vendors via LLM_PROVIDER, no code change
    llm_provider: str = "openai"  # "mock" | "openai" (openai-compatible: Ollama or OpenAI itself)
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"
    llm_model: str = "gemma4:e2b"

    # Source — "live" scrapes dominiopublico.mec.gov.br; "fixtures" replays tests/fixtures/ for a
    # fully offline run (no network/GPU) — see stages/fixtures_source.py.
    source: str = "live"
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

    # Scale knobs — consumed by the async orchestrator (orchestrator/engine.py, pipeline.py)
    download_concurrency: int = 4
    llm_concurrency: int = 2
    request_timeout_s: int = 30
    max_retries: int = 3
    min_books: int = 10
    queue_maxsize: int = 16
    retry_base_delay_s: float = 0.5

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
        """Settings as a plain dict, safe to embed in a run's manifest: the LLM secret masked,
        and the local layer paths relativized to the repo root (or just the layer name, if a
        path lives elsewhere, e.g. a test's tmp_path) — the manifest is an auditable datasheet,
        not a record of whichever machine happened to run it.
        """
        data = self.model_dump(mode="json")
        if data.get("llm_api_key"):
            data["llm_api_key"] = "***redacted***"
        for key in ("data_dir", "raw_dir", "staging_dir", "curated_dir"):
            path = Path(data[key])
            try:
                data[key] = str(path.relative_to(REPO_ROOT))
            except ValueError:
                data[key] = path.name
        return data


settings = Settings()
