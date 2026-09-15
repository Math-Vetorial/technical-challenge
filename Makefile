.PHONY: setup setup-ollama ollama-up ollama-pull run run-local run-offline run-all download hash describe translate translate-descriptions covers test lint

ollama-up:
	docker compose up -d ollama

ollama-pull:
	docker compose exec ollama ollama pull gemma4:e2b

setup:
	uv sync --group dev
	test -f .env || cp .env.example .env

setup-ollama: setup ollama-up ollama-pull

run:
	docker compose up --build pipeline

run-local:
	uv run python -m data_foundry run

# Fully offline: no network, no GPU. Deterministic mock LLM + committed/generated PDF fixtures —
# the same env `make test` uses, just driving the CLI end-to-end instead of pytest.
run-offline:
	LLM_PROVIDER=mock SOURCE=fixtures uv run python -m data_foundry run --limit 12

download:
	uv run python -m data_foundry run --only download

hash:
	uv run python -m data_foundry run --only hash

describe:
	uv run python -m data_foundry run --only describe

translate:
	uv run python -m data_foundry run --only translate

translate-descriptions:
	uv run python -m data_foundry run --only translate-descriptions

covers:
	uv run python -m data_foundry run --only covers

# Assembly (the two datasets + quality report) isn't a standalone `--only` target — it always
# runs as the last step of a full `run`/`run-local`/`run-offline`, right after the barrier.

run-all: download hash describe translate translate-descriptions covers

test:
	uv run pytest tests/ -v

lint:
	uv run ruff check --fix src/ tests/
	uv run ruff format src/ tests/
