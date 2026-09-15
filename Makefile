.PHONY: setup setup-ollama ollama-up ollama-pull run run-local run-all download hash describe translate translate-descriptions covers test lint

ollama-up:
	docker compose up -d ollama

ollama-pull:
	docker compose exec ollama ollama pull gemma4:e2b

setup:
	uv sync --group dev

setup-ollama: setup ollama-up ollama-pull

run:
	docker compose up --build pipeline

run-local:
	uv run python -m data_foundry run

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

# TODO(step-5): localized-catalog / universal-metadata (assembly) aren't stages yet — they'll
# consume quality.curate/dedup/report once per-work state is persisted to data/staging/.

run-all: download hash describe translate translate-descriptions covers

test:
	uv run pytest tests/ -v

lint:
	uv run ruff check --fix src/ tests/
	uv run ruff format src/ tests/
