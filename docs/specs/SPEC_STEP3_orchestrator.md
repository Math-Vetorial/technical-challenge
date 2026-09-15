# SPEC — Data Foundry Pipeline · Step 3: Event-Driven Orchestrator + Scalability

> **How to use:** Give this to Claude Code in the repo. Say:
> *"Read CLAUDE.md and this spec. Implement Step 3 only. Build the async event-driven engine and
> refactor the scripts into stage functions (Option B). Do NOT build the real LLM providers or fixtures
> (Step 4) or assemble the two final datasets (Step 5) — LLM stages call an injected provider Protocol
> that is stubbed here. Test the ENGINE with synthetic fake stages. Run the acceptance checks in §9 and
> show me the results before committing."*

Prereq: Steps 1–2 merged (config, schemas, run/versioning, logging, quality functions). Build on them.

---

## 1. Goal

Replace the naive sequential runner with an **event-driven, async pipeline** where stages react to data
availability, with **bounded concurrency (backpressure)**, **rate limiting (semaphores)**, and **retry
with backoff** — and refactor the 8 scripts' logic into clean **stage functions** (Option B). This is
the "Event-Driven" + "Scalability" delivery. The engine must be **unit-testable offline with fake
stages** (no real network/LLM).

## 2. Mental model

Each **work** (book) flows through stages independently, reacting to events:

```
scrape (paginated) ──WorkDiscovered──▶ download ──PdfDownloaded──▶ ┌─ hash ───────Hashed────────┐
   [semaphore: net]                     [semaphore: net,           ├─ cover ──────CoverExtracted─┤
                                          retry+backoff]           └─ describe ──Described──▶ translate_desc
 scrape ─────────────────────────────────────────────▶ translate_title                         │
                                                                                                ▼
                                 (barrier: all works reached a terminal state) ──▶ [Step 5: assemble]
```

- Stages communicate via **events on an async bus** and/or **bounded `asyncio.Queue`s**.
- A work that fails a stage emits `WorkFailed` (logged + counted) and **does not stop other works**.
- `describe` / `translate_*` call an injected LLM **provider Protocol** — the concrete providers are
  Step 4. In Step 3 inject a trivial stub.

## 3. In scope / out of scope

**In scope (build now):**
- `orchestrator/events.py` — event dataclasses + a small async pub/sub bus (or typed queue wiring).
- `orchestrator/engine.py` — the async engine: bounded queues, per-resource semaphores, retry/backoff,
  per-item failure isolation, run completion (barrier), wired to `RunContext` counts.
- `stages/` — refactor script logic into stage functions (Option B):
  `scrape.py`, `download.py`, `hash.py`, `covers.py`, `describe.py`, `translate.py`.
- `llm/base.py` — the `LLMProvider` Protocol (`describe(images, title, meta) -> str | None`,
  `translate(text, target_lang) -> str | None`) + a `StubProvider` for tests. (Real providers = Step 4.)
- `pipeline.py` — `run(settings, limit=None, only=None)` building a `RunContext`, starting the engine,
  finishing the run. New `main.py` calls it.
- A thin CLI so individual steps stay runnable (`python -m data_foundry run [--only STAGE] [--limit N]`);
  point the Makefile targets (`download`, `hash`, …) at it.
- Resumability/idempotency: each stage **skips work already done** (output exists in raw/staging by
  path/hash) so a re-run resumes instead of redoing.
- Engine unit tests with fake stages.

**Out of scope (do NOT build):** real `ollama`/`openai` providers, PDF fixtures, full offline
`make test` of the whole pipeline (Step 4); assembling `localized_catalog.json` /
`universal_metadata.json` (Step 5); README/diagram (Step 6). Leave `TODO(step-4/5)` seams.

## 4. `events.py`

- Typed event objects (dataclasses), each carrying at least `work_id` and the payload it unlocks:
  `WorkDiscovered(raw: RawListingEntry)`, `PdfDownloaded(work_id, pdf_path)`,
  `Hashed(work_id, sha256)`, `CoverExtracted(work_id, cover_path, cover_hash)`,
  `Described(work_id, description)`, `TitleTranslated(work_id, lang, text)`,
  `DescriptionTranslated(work_id, lang, text)`, `WorkFailed(work_id, stage, error)`.
- A minimal **async event bus**: `subscribe(event_type, handler)` + `publish(event)`, backed by
  `asyncio` tasks. (Alternative acceptable: explicit bounded `asyncio.Queue`s between stages — pick one,
  keep it simple and typed.)

## 5. `engine.py` — the scalability core

- **Bounded queues = backpressure:** every inter-stage queue has a `maxsize` (from settings). If a slow
  stage (LLM) can't keep up, upstream stages block on `put()` instead of exploding memory. Explain this
  in a comment.
- **Semaphores = rate limiting:** one `asyncio.Semaphore(settings.download_concurrency)` around network
  I/O and one `asyncio.Semaphore(settings.llm_concurrency)` around LLM calls. No stage exceeds its budget.
- **Retry with backoff + jitter:** a helper `async def with_retry(fn, *, max_retries, base_delay)` doing
  exponential backoff **with jitter** (avoids thundering herd), retrying transient errors only; on final
  failure it raises so the caller emits `WorkFailed`.
- **Per-item isolation:** a failing work is caught at the stage boundary → `WorkFailed` (logged +
  `ctx.update_counts(failed=…)`), the engine keeps processing the rest.
- **Completion:** the run finishes when every discovered work has reached a terminal state (all
  enrichment done or failed). Update `RunContext` counts as events flow
  (discovered/downloaded/hashed/described/translated/covers/failed).
- Concurrency primitives from `asyncio` only (no external orchestrator dependency — that's the point:
  a lightweight, self-contained event-driven engine).

## 6. `stages/` — refactor the scripts (Option B)

Extract the **pure logic** from each script into a typed stage function; drop the flat-file JSON I/O and
`print`s (use `get_logger`). Stages read/write the **medallion layers**, not `data/output/`.

- `scrape.py`: `async def scrape_listing(settings, limit) -> AsyncIterator[RawListingEntry]` — paginated
  (respect `first`/`skip`/`pagina` params); also `fetch_detail(code) -> WorkDetail`. Keep the
  curl-cffi→Playwright fallback. Write raw listing HTML + parsed entries to `data/raw/`.
- `download.py`: `async def download_pdf(work, settings) -> Path` — resilient client: **cursor/offset
  handled by scrape**; here retry+backoff, timeout, write PDF to `data/raw/pdfs/<code>.pdf`
  **idempotently** (skip if present). This is the resilient-ingestion piece.
- `hash.py`: `def sha256_pdf(path) -> str` (reuse Step-1/2 hashing).
- `covers.py`: `def extract_cover(pdf_path, out_dir) -> tuple[Path, str]` (cover PNG + image hash),
  idempotent by image hash.
- `describe.py`: `async def describe(work, provider: LLMProvider) -> str | None` — renders page(s),
  calls `provider.describe(...)`. Provider injected.
- `translate.py`: `async def translate_title / translate_description(text, langs, provider)` — provider
  injected. Uses Step-2 normalization on inputs where relevant.

Each stage is **idempotent**: check the layer for existing output before doing work (resumable runs).

## 7. `pipeline.py` + CLI + Makefile

- `async def run(settings, *, limit=None, only=None) -> RunContext` — create `RunContext`, build the
  event graph, run the engine to completion, `ctx.finish("success"/"failed")`. Returns the context.
- `__main__` / CLI: `python -m data_foundry run [--only STAGE] [--limit N]`. `--only` runs a single stage
  over already-available data (for debugging / the individual `make` targets).
- Update `main.py` to call `pipeline.run(...)` (via `asyncio.run`). Update Makefile `download`/`hash`/…
  targets to call `python -m data_foundry run --only <stage>`; keep `run` = full pipeline.

## 8. Settings already present (from Step 1) — use them

`download_concurrency`, `llm_concurrency`, `request_timeout_s`, `max_retries`, `min_books`. Add if
needed: `queue_maxsize: int = 16`, `retry_base_delay_s: float = 0.5`.

## 9. Tests (engine tested offline with FAKE stages) + acceptance

The engine must be provable without network/LLM. Write:
- `tests/test_engine.py`:
  - **Concurrency cap:** a fake stage that records how many run simultaneously never exceeds the
    semaphore limit.
  - **Retry+backoff:** a fake stage that fails N-1 times then succeeds is retried and eventually
    succeeds; one that always fails ends as `WorkFailed` without crashing the run.
  - **Per-item isolation:** among many works, one that always fails does not stop the others from
    completing.
  - **Backpressure:** with a tiny `queue_maxsize` and a slow consumer, a fast producer blocks rather
    than growing unbounded (assert queue never exceeds maxsize, or that producer awaited).
- `tests/test_stages.py` (offline-only slices): `sha256_pdf` on tiny bytes; `extract_cover` on a
  minimal in-memory PDF generated with PyMuPDF (if feasible) — otherwise mark `TODO(step-4)` for
  fixture-based tests. Do not hit the network.

**Acceptance (run and report before committing):**
1. `uv run pytest -v` — all Steps 1–3 tests green (`test_outputs.py` still skipped).
2. Engine tests demonstrate: concurrency capped, retry works, one failure isolated, backpressure holds.
3. `uv run ruff check` clean on new code (legacy-script BLE001 debt only).
4. `python -m data_foundry run --limit 0` (or a dry/discovery-only mode) runs offline without error and
   updates a run manifest — prove the wiring holds even with no LLM/network. (If a fully offline run
   isn't possible until fixtures exist, demonstrate the engine via the tests and say so.)

## 10. Design notes (for the README later)

- **Why a home-grown async event bus instead of Airflow/Temporal/Prefect?** For this scope, a
  self-contained `asyncio` engine has zero infra, is trivial to run in one container, and *demonstrates*
  the event-driven + backpressure concepts directly. Note the trade-off: a real deployment at scale
  would use a durable workflow engine (Temporal) or a DAG scheduler (Airflow/Dagster) for persistence,
  retries across process restarts, and observability — call this out explicitly. (Shows you know the
  managed option and chose the lightweight one deliberately.)
- **at-least-once + idempotency:** stages are idempotent and resumable, so a crashed run re-runs safely
  and picks up where it left off — the same principle as a production ingestion client.
- **Backpressure matters** because the LLM stage is the slow one; bounding queues stops the fast
  scraper from exhausting memory while the LLM catches up.

## 11. Guardrails (from CLAUDE.md)

- Async/typed/small functions; no `print`; structured logging. Provider is a Protocol (Step 4 implements).
- Idempotent, resumable stages; raw layer immutable.
- Don't weaken `test_outputs.py`. Conventional commit:
  `feat: event-driven async engine + stage refactor (scalability)`.
