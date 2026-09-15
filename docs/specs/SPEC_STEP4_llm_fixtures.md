# SPEC — Data Foundry Pipeline · Step 4: Pluggable LLM + Fixtures + Offline Tests

> **How to use:** Give this to Claude Code in the repo. Say:
> *"Read CLAUDE.md and this spec. Implement Step 4 only: the real LLM provider abstraction
> (mock + openai-compatible), tiny PDF fixtures, and a fixtures-backed offline mode so the pipeline
> runs end-to-end with NO network/GPU. Do NOT assemble the two final datasets (Step 5). Run the
> acceptance checks in §7 and show me the results before committing."*

Prereq: Steps 1–3 merged, plus the small `TransientError` retry fix. Build on them.

## 1. Goal

Make the pipeline **runnable and testable with zero external dependencies**, and make the LLM a
**swappable component** (the JD's "AI-assisted workflows, swappable via env"). After Step 4, `make test`
runs the whole enrichment flow offline over fixture PDFs with a deterministic mock LLM; `make run` uses
a real OpenAI-compatible endpoint (Ollama or OpenAI) via env.

## 2. In scope / out of scope

**In scope:**
- `llm/mock.py` — `MockProvider`: deterministic, offline `describe` + `translate`.
- `llm/openai_provider.py` — `OpenAIProvider`: async, OpenAI-compatible (works for Ollama *and* OpenAI
  via `LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL`). Vision describe + text translate.
- `llm/factory.py` — `get_provider(settings)` selecting by `LLM_PROVIDER` env (`mock` | `openai`).
- `tests/fixtures/` — 2–3 tiny valid PDFs (generate with PyMuPDF: one page, a title + a line of text)
  and a small recorded listing-HTML snippet for scrape-parsing tests. Committed (allowed under
  `tests/fixtures/`).
- **Fixtures-backed offline source** so scrape/download don't hit the network in tests: a
  `SOURCE=fixtures` mode (or injected source) where `scrape_listing` yields entries from the fixtures
  and `download_pdf` copies the fixture PDF into `data/raw/pdfs/`. Keep the real network source as
  default (`SOURCE=live`).
- Integration test: run `pipeline.run(...)` fully offline (mock LLM + fixtures) and assert the per-work
  enrichment (hash, cover, description, translations) is produced deterministically for ≥3 works, with
  no network.
- `.env.example`: add `LLM_PROVIDER=mock` and `SOURCE=fixtures` (documented), keeping the real examples.

**Out of scope:** assembling `localized_catalog.json` / `universal_metadata.json` and un-skipping
`test_outputs.py` (Step 5); README (Step 6). Leave `TODO(step-5)` seams.

## 3. `MockProvider` (deterministic, offline)

- `describe(pdf_path_or_images, raw, detail) -> str` → a **deterministic** string derived from the
  title + code, e.g. `f"[mock-description] {raw.title} (obra {raw.code})"`. No randomness — same input,
  same output (so tests can assert exact values and it stands in for a real description).
- `translate(text, target_lang) -> str` → deterministic, e.g. `f"[{target_lang}] {text}"`. Preserves
  `None`/empty in → `None` out.
- Fast, no I/O. This is what makes CI hermetic.

## 4. `OpenAIProvider` (real, for `make run`)

- Use `openai.AsyncOpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key)`.
- `describe`: render page(s) to PNG (reuse the covers/describe rendering), send as image_url content
  (vision), model `settings.llm_model`, timeout `settings.request_timeout_s`. Return text or `None` on
  error (let the stage/engine handle retry).
- `translate`: text prompt (reuse the existing prompt shape from the old scripts), return text or `None`.
- Do **not** call it in tests. Just importable and wired for `make run`.
- Design note for the README: the provider Protocol decouples the pipeline from the vendor — swap
  Ollama↔OpenAI↔mock via env, no code change. Mention that for production reliability you'd add
  **structured outputs** (JSON/Pydantic-validated) and a **gold-set error check** — reference it as the
  productionization, even if the challenge's plain-text prompts don't require it yet.

## 5. `get_provider(settings)`

- `LLM_PROVIDER=mock` → `MockProvider()`; `openai` (default for real runs) → `OpenAIProvider(settings)`.
- `pipeline.run` uses `provider or get_provider(settings)` so tests inject `MockProvider` and `make run`
  gets the real one. Tests should default to mock (via env or explicit injection).

## 6. Fixtures + offline source

- `tests/fixtures/pdfs/`: generate 2–3 minimal PDFs at test-collection time (a `conftest.py` fixture
  using PyMuPDF) OR commit tiny pre-made ones. Each has a distinct title so enrichment differs.
- `tests/fixtures/listing.html`: a trimmed real-shape listing table for `parse_listing` unit tests.
- The `fixtures` source: `scrape_listing` yields `RawListingEntry` objects built from the fixture set;
  `download_pdf` copies the fixture file into `data/raw/pdfs/<code>.pdf` idempotently. Selected by
  `settings.source == "fixtures"`. Add `source: str = "live"` to `Settings`.

## 7. Tests + acceptance

- `tests/test_mock_provider.py`: `describe`/`translate` deterministic; `None`/empty handled.
- `tests/test_scrape_parse.py`: `parse_listing(fixtures/listing.html)` yields the expected entries
  (offline).
- `tests/test_pipeline_offline.py`: `await pipeline.run(settings(source=fixtures, provider=mock),
  limit=3)` completes with `status="success"`, produces deterministic hash/cover/description/
  translations for the 3 works, makes **no network call**, and writes a manifest with the right counts.
- `factory` returns the right provider per env.

**Acceptance (run and report before committing):**
1. `uv run pytest -v` — all Steps 1–4 tests green offline (`test_outputs.py` still skipped until Step 5).
2. `LLM_PROVIDER=mock SOURCE=fixtures uv run python -m data_foundry run --limit 3` runs end-to-end with
   no network/GPU, exits success, manifest counts reflect 3 works enriched.
3. `uv run ruff check` clean on new code.
4. Confirm `OpenAIProvider` imports and `get_provider` selects correctly (without calling the network).

## 8. Guardrails (from CLAUDE.md)

- Provider is the only place that knows the LLM vendor. Mock is deterministic and hermetic.
- Fixtures are tiny and live under `tests/fixtures/` (the only data committed).
- Don't weaken `test_outputs.py`. Async/typed/no-print. Conventional commit:
  `feat: pluggable LLM providers (mock/openai) + fixtures + offline pipeline test`.
