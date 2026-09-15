# CLAUDE.md — Project Memory

> Read this first, every session. It is the persistent context for this repo.

## What this repo is

Solution to the **TRACTIAN Data Foundry / Data Engineering challenge**: take the 8 given
"building-block" scripts (scrape, download, hash, describe via vision LLM, translate, covers,
assemble) and turn them into a **real pipeline** that ingests and enriches public-domain books from
Domínio Público, producing **two JSON datasets**.

The challenge grades **pipeline design and engineering decisions, not the scripts**. The ground-truth
requirements are in `docs/challenge.md`. Per-step build instructions are in `docs/specs/`.

## The mission

Replace the naive sequential runner (`main.py` calling scripts `01→08` via subprocess into a flat
`data/output/`) with an **event-driven, medallion-layered, versioned, resumable** pipeline.

We are tackling **all 5 target areas**: Data Architecture, Data Quality, Versioning, Scalability,
Event-Driven.

## Target architecture (the big picture)

- **Medallion layers:**
  - `data/raw/` — bronze, **immutable**. Scraped HTML, downloaded PDFs, raw detail metadata. Never mutated.
  - `data/staging/` — silver. Normalized, schema-validated per-work records.
  - `data/curated/` — gold. The two final datasets, per versioned run.
- **Event-driven orchestration:** stages react to data availability via an in-process event bus +
  bounded async queues, not a hardcoded 01→08 order. `PdfDownloaded` fans out to hash/cover/describe
  in parallel per work; assembly runs at a barrier when all works are processed.
- **Scalability:** async I/O for download + LLM; **bounded queues = backpressure**; **semaphores =
  rate limiting** (per-resource concurrency); resumable/idempotent stages (skip work already done).
- **Versioning:** every run gets a `run_id` (UTC timestamp + short uuid). Outputs go to
  `data/curated/runs/<run_id>/` with a `latest` pointer. A `manifest.json` per run (our "datasheet")
  records inputs, counts, quality metrics, config (secrets redacted), git sha. **Re-runs never overwrite.**
- **Data quality:** encoding/mojibake normalization, dedup by `document_hash` and `cover_hash`,
  missing-data handling, **validation as-code (Pydantic)** that fails fast, plus a `quality_report.json`.

## The output contract (NEVER break this)

Two files, shapes fixed by the challenge (may be **expanded**, never shrunk):

- `localized_catalog.json` (language-dependent): `id`, `author`, `title{pt,en,es,fr}`,
  `description{pt,en,es,fr}`.
- `universal_metadata.json` (language-independent): `id`, `document_hash`, `cover_path`, access count,
  file size, `category`, `year`.

Rationale for the split (put this in the README): language-varying fields vs invariants are separated so
each evolves independently (add a language without touching universal metadata; recompute a hash without
touching translations). It's normalization + a data contract.

## Key decisions already made

- **Refactor (Option B):** the 8 scripts are *tools, not the solution*. Refactor their logic into the
  package as stage functions; keep individual steps runnable via a thin CLI (`make download` etc. call
  the new code path). Do not keep duplicated flat-file scripts.
- **LLM is pluggable + offline-mockable:** a provider abstraction with `mock` (deterministic, offline —
  so `make test` runs with no GPU/network), `ollama`, and `openai` backends, swappable via env.

## How we build — 6 steps, one at a time

1. **Foundations** — package structure, typed config, data layers, run/versioning, schemas, logging.
2. **Domain + Data Quality** — normalization, dedup, missing-data, validation, quality report.
3. **Event-driven orchestrator + Scalability** — async engine, bounded queues, semaphores, retry/backoff;
   scripts become stage functions.
4. **Pluggable LLM + fixtures + offline tests** — mock/ollama/openai provider, sample PDFs, `make test` green offline.
5. **Assembly + curated outputs** — the two datasets into versioned run dirs + `latest` + manifest.
6. **README + architecture diagram + Docker/Make wiring.**

**Work only on the step whose spec you were given.** Leave `TODO(step-N)` seams for later steps. Do not
over-build ahead of the current spec.

## Conventions & guardrails

- Python **3.12+**, fully **type-hinted**. **Pydantic v2** for schemas/validation. **uv** for deps,
  **ruff** for lint/format. Structured logging via `logging_setup.get_logger` — **no `print`** in new code.
- Small, composable, testable functions. Engineering quality is the grade.
- **Never commit secrets.** `.env` stays gitignored; only `.env.example` is committed. When new data
  layers are added, extend `.gitignore` with `data/raw/`, `data/staging/`, `data/curated/` (commit only
  tiny test fixtures under `tests/fixtures/`).
- **Do not weaken the provided `tests/test_outputs.py` assertions.** They may be temporarily skipped
  (with a TODO) until Step 5 produces outputs, or repointed to the curated path — but keep their intent
  (min 10 works, `id`+`title.pt`, `id`+`document_hash`, cross-dataset consistency). Document any change
  in the README.
- Run acceptance checks + `ruff check` + `pytest` before committing. Use conventional commits
  (`feat:`, `chore:`, `test:`, `docs:`).

## Runbook

- `uv sync` — install deps
- `uv run python -m data_foundry run` — run the pipeline (offline-capable with the mock LLM; `--only STAGE` / `--limit N` supported)
- `make test` / `uv run pytest -v` — tests
- `make run` — full pipeline via Docker (Ollama), for the real enrichment run
