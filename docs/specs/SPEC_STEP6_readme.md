# SPEC — Data Foundry Pipeline · Step 6: README + Architecture + Polish (the showcase)

> **How to use:** Give this to Claude Code in the repo. Say:
> *"Read CLAUDE.md and this spec. Implement Step 6: write the README (setup, architecture + diagram,
> design decisions & trade-offs), a short docs/ARCHITECTURE.md if useful, and polish the Make/Docker/
> env wiring. This is the deliverable's showcase — the challenge grades design decisions and trade-offs.
> Run the acceptance checks in §5 and show me the README before committing."*

Prereq: Steps 1–5 merged + the `cover_path` fix. This step is mostly writing + wiring; no new pipeline logic.

## 1. Why this step matters

The challenge's README requirements are explicit: **setup instructions (`make run` must work)**,
**architecture description or diagram**, and **design decisions and trade-offs**. The last one is where
most candidates lose points and we win — every non-obvious choice gets a one-line *why* and *what it
costs*. This README is the argument for the whole build.

## 2. README structure (write it in this order)

1. **Title + one-paragraph overview** — what the pipeline does (ingest + enrich Domínio Público books →
   two datasets), and the one-line thesis: *stages react to data availability; raw is immutable; every
   run is versioned and auditable.*
2. **Quickstart / Setup**
   - `make run` (full pipeline via Docker + Ollama) and `make test` (hermetic, offline).
   - The **offline path**: `LLM_PROVIDER=mock SOURCE=fixtures make ...` (or `uv run ...`) runs with no
     network/GPU — call this out, it's a strength.
   - Env vars table: `LLM_PROVIDER` (mock|openai), `LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL`, `SOURCE`
     (live|fixtures), the scale knobs (`DOWNLOAD_CONCURRENCY`, `LLM_CONCURRENCY`, `QUEUE_MAXSIZE`, …).
   - Individual stages: `make download` / `make hash` / … (note what needs prior state).
3. **Architecture** — prose + a **Mermaid diagram** (renders on GitHub). Show:
   - The medallion layers (raw → staging → curated) and what lives in each.
   - The event-driven flow: `scrape → [bounded queue] → worker pool → per-work fan-out
     (hash/cover/describe→translate) → barrier → assemble`.
   - Where the event bus + accumulator build the silver layer.
   - Versioned curated output + `latest` + manifest.
4. **The two output datasets** — their schemas and the **rationale for the split**
   (language-dependent vs invariant; normalization + a data contract; each evolves independently).
5. **Design decisions & trade-offs** — the heart. One short subsection each (see §3).
6. **Data quality** — what's handled (encoding/mojibake, sentinels, pt-BR number parsing, missing,
   dedup, quarantine) and the `quality_report.json`.
7. **Testing** — hermetic offline suite (mock + fixtures), the two-kinds-of-tests idea (code vs data),
   and the note that `test_outputs.py` was **repointed** from `data/output/` to `curated/latest/`
   (assertions preserved) — with the reason.
8. **Which target areas are covered** — a short table mapping the challenge's 5 areas
   (Event-Driven, Data Architecture, Versioning, Scalability, Data Quality) to where each lives. We did
   **all five**; say so.
9. **What I'd do differently at scale** — the honest forward-looking section (see §4).

## 3. Design decisions & trade-offs to capture (each = a couple of sentences, decision + why + cost)

- **Medallion layers (raw/staging/curated)** — immutable raw enables reprocessing + audit; cost is
  storage duplication. Why not one flat `output/`: you can't fix a curation bug six months later without
  the original.
- **Event-driven via a home-grown asyncio engine, not Airflow/Temporal/Prefect** — zero infra, one
  container, demonstrates backpressure directly. Trade-off: a real deployment would use a durable
  workflow engine (Temporal) or DAG scheduler (Airflow/Dagster) for cross-restart persistence, retries,
  and observability. *We chose the lightweight option deliberately.*
- **Bounded queue = backpressure; semaphores = rate limiting; retry with backoff+jitter** — why each,
  and that the LLM is the slow stage the backpressure protects memory against.
- **at-least-once + idempotent, resumable stages** — a crashed run re-runs safely and resumes; same
  principle as a production ingestion client.
- **`TransientError` contract** — the engine defines what's transient; stages translate their HTTP
  library's errors into it, keeping the engine decoupled from `httpx`/`curl_cffi`.
- **Option B refactor** — the 8 scripts became stage functions (single source of truth); individual
  steps stay runnable via the CLI.
- **Pluggable LLM + deterministic mock** — swap vendor via env (the JD's "AI-assisted workflows");
  the mock makes CI hermetic. Note the productionization: **structured outputs (JSON/Pydantic) + a
  gold-set error check** for reliability (not required by the plain-text prompts here, but the right
  next step).
- **Quality: quarantine over crash; dedup surfaces (never hides); never coerce garbage to 0** —
  correctness *and* robustness; a wrong number is worse than a missing one.
- **Pure Python for curation, not Pandas/DuckDB** — records are few and nested, not tabular; Pandas
  would be the tool for millions of flat rows. Tools chosen by shape + scale, not habit.
- **Versioned runs + manifest ("datasheet")** — reproducible + auditable: one file answers "what did
  this run produce and how clean was it?".
- **Consistency by construction** — dedup drops ids from both datasets together, so they always share
  one id set.

## 4. "At scale / what I'd do differently" (honest, senior-signal section)

- Durable orchestrator (Temporal/Airflow) for persistence + observability once runs outlive a process.
- A real store for staging/curated (object storage + a table format like Iceberg/Delta; DuckDB/Parquet
  for large tabular analysis) instead of JSON files.
- LLM reliability: structured outputs, a gold set with a measured error rate, confidence routing,
  LLM-as-a-judge for QA.
- Observability: metrics/traces on stage latency + failure rates; freshness/volume alerts.
- Dedup beyond exact hash: near-dup (MinHash/LSH) and entity resolution if the catalog grew.

## 5. Wiring polish + acceptance

- Ensure `.env.example` documents every env var used (LLM_PROVIDER, SOURCE, scale knobs).
- Makefile: `run`, `test`, `run --only <stage>` targets coherent; `make run` works via Docker/compose.
- `README.md` renders cleanly on GitHub (check the Mermaid block).

**Acceptance (report before committing):**
1. `uv run pytest -v` still fully green.
2. `README.md` covers all three required sections (setup / architecture+diagram / decisions+trade-offs)
   and the 5-areas mapping; Mermaid diagram present.
3. `make test` works from a clean checkout offline (mock + fixtures).
4. `ruff check` clean.
5. Show me the rendered README (or its full text) before committing.

## 6. Guardrails

- Accurate over impressive: the README must describe what the code *actually* does (e.g. event bus =
  functional now, but be honest that per-work fan-out is structured concurrency; backpressure is on the
  scrape→worker boundary).
- Conventional commit: `docs: README, architecture diagram, and design rationale`.
- After this: flip the GitHub repo to **public**, do a final `make run` against the live source for a
  real ≥10-book run, and you're done.
