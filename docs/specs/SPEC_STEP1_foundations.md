# SPEC — Data Foundry Pipeline · Step 1: Foundations

> **How to use this file:** Give it to Claude Code inside the `foundry-tech-test` repo and say
> *"Implement this spec. It is Step 1 of 6. Do only what's in scope; do not build the orchestrator,
> the LLM stages, or the scraping logic yet — those are later steps."*
> Ask it to run the acceptance checks at the end and report results before committing.

---

## 0. Project context (the big picture — read once, don't build all of it now)

We are refactoring a naive sequential pipeline (`main.py` runs scripts `01→08` via subprocess,
dumping flat JSON into `data/output/`) into a proper **event-driven, medallion-layered, versioned,
resumable** data pipeline for the Domínio Público challenge.

The full target has **6 steps**. This spec is **Step 1 only**:

1. **Foundations** ← *this spec*: package structure, config, data layers, run/versioning, schemas, logging.
2. Domain + Data Quality (normalization, dedup, missing-data, validation, quality report).
3. Event-driven orchestrator + Scalability (async engine, bounded queues, semaphores, retry/backoff).
4. Pluggable LLM (mock/ollama/openai) + fixtures + offline tests.
5. Assembly + curated outputs + versioned snapshots.
6. README + architecture diagram + Docker/Make wiring.

**Design decision already made (Option B):** the 8 given scripts are *tools, not the solution*. Their
logic will be refactored into the package as stage functions in later steps; individual steps stay
runnable via a thin CLI. In Step 1 we DO NOT touch the scripts yet — we only build the scaffolding
they will later plug into.

**Contract that must never break:** the two final datasets `localized_catalog.json` and
`universal_metadata.json`, with the shapes defined in §4. The provided `tests/test_outputs.py` asserts
on these — we will keep those assertions meaningful (adjusting only paths, later, with a README note).

---

## 1. Goal of Step 1

Lay the foundation that every later step builds on, and **prove versioning works end-to-end** even
before any real stage exists. After Step 1, running the entrypoint must create a new immutable,
timestamped run directory with a manifest, and running it twice must NOT overwrite the first.

## 2. In scope / out of scope

**In scope (build now):**
- Package restructure + `pyproject.toml` deps.
- `config.py` — typed settings from env (pydantic-settings) + the three data-layer paths.
- `schemas.py` — Pydantic models for the domain + the two output records + the manifest.
- `run.py` — `RunContext`: run_id, versioned curated paths, `latest` pointer, manifest read/write.
- `logging_setup.py` — structured logging.
- `main.py` — minimal entrypoint that builds a `RunContext`, logs, writes a manifest. No stages yet.
- Unit tests for schemas + versioning.

**Out of scope (do NOT build yet):** scraping, downloading, hashing, LLM calls, the async
orchestrator/event bus, the quality transforms, assembling the real datasets. Leave `TODO(step-N)`
comments where those will plug in.

## 3. Target structure (create these files; leave later-step dirs empty with `__init__.py` + TODO)

```
src/data_foundry/
├─ __init__.py
├─ config.py            # Settings (pydantic-settings): env + layer paths + concurrency knobs
├─ schemas.py           # Pydantic models (domain, outputs, manifest)
├─ logging_setup.py     # get_logger(name) -> structured logger
├─ run.py               # RunContext + manifest
├─ paths.py             # small helpers for raw/staging/curated locations
├─ main.py              # entrypoint (python -m data_foundry)
├─ stages/              # (empty now) __init__.py + "# TODO(step-2/3): stage functions"
├─ orchestrator/        # (empty now) __init__.py + "# TODO(step-3): event bus + async engine"
├─ llm/                 # (empty now) __init__.py + "# TODO(step-4): pluggable providers"
└─ quality/             # (empty now) __init__.py + "# TODO(step-2): normalize/dedup/report"

data/
├─ raw/                 # bronze, immutable (created at runtime)
├─ staging/             # silver, normalized (created at runtime)
└─ curated/
   └─ runs/<run_id>/    # gold: the 2 datasets + manifest.json + quality_report.json (later)
   # plus a `latest` pointer to the newest run dir
```

## 4. Schemas (`schemas.py`) — the contracts

Use **Pydantic v2**. Make fields explicit; prefer `None` over missing. Add light validators where noted.

### 4.1 Intermediate / domain models (used by later stages)

- `RawListingEntry`: `code: str`, `title: str`, `author: str | None`, `source: str | None`,
  `format: str | None`, `size: str | None`, `accesses: str | None`. (Mirrors what the scraper yields;
  strings as-scraped — cleaning happens in Step 2.)
- `WorkDetail`: `code: str`, `category: str | None`, `language: str | None`, `institution: str | None`,
  `year: str | None`, `accesses: str | None`, `download_url: str | None`.

### 4.2 Output models — **the hard contract**

`LocalizedRecord`:
```
id: str                         # work identifier (the "code")
author: str | None
title:       LangField          # {pt, en, es, fr}
description: LangField          # {pt, en, es, fr}
```
where `LangField` is a model with `pt: str | None`, `en: str | None`, `es: str | None`, `fr: str | None`.
Validator: `title.pt` must be non-empty (a record without a PT title is invalid — surface it, don't drop silently).

`UniversalRecord`:
```
id: str
document_hash: str | None       # sha256 hex; validate 64-hex when present
cover_path: str | None
accesses: int | None            # parsed from "1.234"/"1,234" in Step 2
size_bytes: int | None
category: str | None
year: int | None                # parsed to int in Step 2; validate plausible range (e.g. 1400..current+1)
# optional expansion fields (challenge allows): language, institution, source, run_id
```

Provide `LocalizedCatalog = RootModel[list[LocalizedRecord]]` and
`UniversalMetadata = RootModel[list[UniversalRecord]]` (or equivalent) so the whole file validates,
plus a `dump_json(path)` helper that writes UTF-8, `ensure_ascii=False`, indent=2.

### 4.3 Manifest model (the "datasheet")

`RunManifest`:
```
run_id: str
started_at: datetime            # UTC, ISO-8601
finished_at: datetime | None
status: Literal["running","success","failed"]
git_sha: str | None
config_snapshot: dict           # settings with secrets redacted (never store LLM_API_KEY value)
source_url: str | None          # the Domínio Público list URL
counts: dict[str, int]          # discovered/downloaded/hashed/described/translated/covers/deduped/failed
quality: dict[str, Any]         # filled in Step 2 (missing %, duplicate groups, coverage)
outputs: dict[str, str]         # logical name -> relative path (filled in Step 5)
output_hashes: dict[str, str]   # logical name -> sha256 of the written file (Step 5)
tool_versions: dict[str, str]   # python, key libs
```

## 5. `config.py` — typed settings

- Use `pydantic-settings` `BaseSettings`, reading from env / `.env` (keep `python-dotenv` behavior).
- Fields (with sensible defaults):
  - LLM: `llm_base_url`, `llm_api_key` (**secret**), `llm_model`.
  - Paths: `data_dir` (default `<repo>/data`), derived `raw_dir`, `staging_dir`, `curated_dir`.
  - Source: `base_url`, `list_url` (move the existing constants here).
  - Scale knobs (used in Step 3, define now with defaults): `download_concurrency: int = 4`,
    `llm_concurrency: int = 2`, `request_timeout_s: int = 30`, `max_retries: int = 3`,
    `min_books: int = 10`.
- Add a `redacted()` method returning the settings as a dict with `llm_api_key` masked, for the manifest.
- Keep a module-level `settings = Settings()` for import convenience.

## 6. `run.py` — RunContext + versioning (the heart of Step 1)

- `run_id`: `f"{utc_now:%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"` (sortable + unique).
- `RunContext.create(settings)`:
  - computes `run_dir = curated_dir/"runs"/run_id`, creates it (and raw/staging dirs).
  - captures `git_sha` (via `git rev-parse --short HEAD`, tolerate failure → None).
  - builds an initial `RunManifest(status="running", ...)` and writes `run_dir/manifest.json`.
- Methods: `update_counts(**kw)`, `set_quality(dict)`, `record_output(name, path)` (also stores sha256),
  `finish(status)` (sets `finished_at`, rewrites manifest), and `write_manifest()`.
- **`latest` pointer:** after a successful `finish`, point `curated_dir/"latest"` at the new run dir.
  Prefer a real symlink; on failure (e.g. Windows) fall back to writing a `latest.txt` with the run_id.
  This is what tests and `make` will read from.
- **Immutability:** never write into a previous run's dir. Re-running always makes a new `run_id`.

## 7. `logging_setup.py`

- `get_logger(name)` returning a stdlib logger configured once with a structured format
  (e.g. `%(asctime)s %(levelname)s %(name)s %(message)s`, or key=value / JSON). Level from env
  `LOG_LEVEL` default INFO. No `print` in the new code.

## 8. `main.py`

- `python -m data_foundry` (add `__main__.py` or guard) must:
  1. build `Settings`, `RunContext.create(...)`,
  2. log "run started" with run_id,
  3. (placeholder) log that stages are not wired yet — `TODO(step-3)`,
  4. `ctx.finish("success")`, update `latest`,
  5. log where the manifest was written.
- No network, no LLM. It must succeed offline in <1s.

## 9. `pyproject.toml`

- Add deps: `pydantic>=2.7`, `pydantic-settings>=2.2`. Keep existing deps.
- Keep `ruff` + `pytest` in dev group. Ensure `uv sync` works.

## 10. Tests to add (must pass offline, no network/LLM)

- `tests/test_schemas.py`: a valid `LocalizedRecord`/`UniversalRecord` builds; a record with empty
  `title.pt` raises; a bad `document_hash` (non-64-hex) raises; `year` out of range raises;
  `accesses` accepts int and rejects garbage.
- `tests/test_versioning.py`: `RunContext.create` twice yields two different `run_id`s and two
  distinct run dirs; the first run's `manifest.json` is untouched after the second run; `latest`
  resolves to the newest run.
- Do **not** delete the provided `tests/test_outputs.py`. It will fail now (no outputs yet) — that's
  expected until Step 5. If Claude Code wants green CI in the meantime, it may mark those tests with
  `pytest.mark.skip(reason="outputs produced from Step 5")` **and leave a TODO to re-enable** — but do
  not weaken their assertions.

## 11. Acceptance criteria (run these, report before committing)

1. `uv sync` completes.
2. `uv run python -m data_foundry` runs offline, creates `data/curated/runs/<run_id>/manifest.json`
   with `status:"success"`, and sets `data/curated/latest`.
3. Running it **again** creates a **second** run dir; the first manifest is byte-for-byte unchanged;
   `latest` now points to the second.
4. `uv run pytest tests/test_schemas.py tests/test_versioning.py -v` is green.
5. `uv run ruff check src/ tests/` is clean.
6. `manifest.json` contains a redacted config (no raw `LLM_API_KEY` value), a `git_sha` (or null),
   and `tool_versions`.

## 12. Notes for the implementer

- Keep functions small and typed; this is graded on engineering quality.
- Prefer composition over cleverness. Leave clear `TODO(step-N)` seams — reviewers like seeing the plan.
- Do not over-build: no orchestrator, no async, no scraping in this step.
- Commit message suggestion: `feat: foundations — layered dirs, typed config, run versioning, schemas`.
