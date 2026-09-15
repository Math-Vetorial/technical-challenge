# SPEC — Data Foundry Pipeline · Step 2: Domain + Data Quality

> **How to use:** Give this to Claude Code in the repo. Say:
> *"Read CLAUDE.md and this spec. Implement Step 2 only. These are pure, unit-tested functions on
> synthetic inputs — do NOT wire them into scraping/orchestration (that's Step 3), and do NOT build
> the LLM or the async engine. Run the acceptance checks in §8 and show me the results before committing."*

Prereq: Step 1 is merged (config, schemas, run/versioning, logging). Build on it.

---

## 1. Goal

Give the pipeline its **data-quality backbone**: pure functions that turn messy scraped strings into
clean, typed, validated records — and a **quality report** that quantifies what was wrong. This is the
area we lead with; make it rigorous and well-tested. Everything here is **pure and offline-testable**
(no network, no LLM, no orchestration).

## 2. In scope / out of scope

**In scope (build now):**
- `quality/normalize.py` — encoding fix, whitespace, sentinel→None, localized-int parsing, year parsing, language-code normalization.
- `quality/curate.py` — turn `RawListingEntry` + `WorkDetail` into validated records; **quarantine** invalid ones instead of raising.
- `quality/dedup.py` — detect duplicate works by `document_hash` and duplicate covers by `cover_hash`; pick a canonical, mark the rest.
- `quality/report.py` — build a `QualityReport` (schema below): counts, missing-per-field, duplicate groups, coverage, quarantined.
- Extend `schemas.py` with the models Step 2 needs (below).
- Unit tests for every function, on synthetic inputs.

**Out of scope (do NOT build):** scraping/download, the async orchestrator/event bus, LLM providers,
assembling the two final datasets, fixtures of real PDFs. Leave `TODO(step-3/4/5)` seams. The
functions here take plain Python inputs; wiring them into the live flow is Step 3.

## 3. New/updated files

```
src/data_foundry/quality/
├─ __init__.py
├─ normalize.py     # field-level cleaners (pure)
├─ curate.py        # record-level: raw -> validated | quarantined
├─ dedup.py         # duplicate detection by content hash
└─ report.py        # QualityReport builder
src/data_foundry/schemas.py   # add: EnrichedWork, QuarantinedRecord, QualityReport, DuplicateGroup
tests/test_normalize.py
tests/test_curate.py
tests/test_dedup.py
tests/test_report.py
```

## 4. `normalize.py` — field cleaners (each pure, typed, individually tested)

- `fix_encoding(s: str) -> str` — repair mojibake (e.g. `SÃ£o` → `São`). Use **ftfy** (`ftfy.fix_text`);
  add `ftfy` to deps. Idempotent: fixing already-clean text is a no-op.
- `clean_text(s: str | None) -> str | None` — strip, collapse internal whitespace, replace non-breaking
  spaces (`\xa0`) with normal spaces, then `fix_encoding`. Returns `None` if the result is empty.
- `SENTINELS = {"", "-", "--", "n/a", "na", "null", "none", "\xa0", "sem informação"}` (case-insensitive).
  `null_if_sentinel(s: str | None) -> str | None` — map sentinels to `None`.
- `parse_int_locale(s: str | None) -> int | None` — parse counts like `"1.234"`, `"1,234"`, `"1 234"`,
  `"12.345 acessos"` → `12345`. Strip non-digits after removing thousands separators; return `None` on
  no digits. **Do not** silently turn garbage into 0.
- `parse_year(s: str | None) -> int | None` — extract a plausible 4-digit year (`_MIN_YEAR..now+1`) from
  strings like `"2005"`, `"Ano: 2005"`, `"2005."`. Return `None` if none found or out of range.
- `normalize_lang(s: str | None) -> str | None` — map `"Português"/"portugues"/"pt-BR"` → `"pt"`,
  English/Inglês → `"en"`, etc.; unknown → the cleaned original (don't drop information).

## 5. `curate.py` — record-level curation (raw → validated | quarantined)

- `build_localized(raw: RawListingEntry, title_translations, description, desc_translations) ->
  LocalizedRecord` — assemble a `LocalizedRecord`, cleaning `title.pt`/`author` via `normalize`.
- `build_universal(raw, detail: WorkDetail, doc_hash, cover_path, size_bytes, run_id) ->
  UniversalRecord` — assemble a `UniversalRecord`, parsing `accesses`/`year`, cleaning `category`,
  normalizing `language`.
- `curate_works(...) -> CurateResult` — the orchestrating pure function: for each work, try to build +
  validate both records; on `pydantic.ValidationError`, append a `QuarantinedRecord`
  (`id`, `reason`, `raw` payload) instead of raising. Returns `CurateResult(localized: list,
  universal: list, quarantined: list)`. **This is the “fail fast without crashing the run” pattern** —
  one bad work is quarantined, the run continues.

## 6. `dedup.py`

- `find_duplicate_groups(items: dict[str, str | None]) -> list[DuplicateGroup]` — given `{id: hash}`,
  group ids that share a non-null hash into `DuplicateGroup(hash, ids, canonical)` where `canonical`
  is the first id (stable). Ids with null hash are ignored.
- `dedup_by_document_hash(universal: list[UniversalRecord]) -> tuple[list[UniversalRecord],
  list[DuplicateGroup]]` — keep the canonical of each group, drop the rest (a book downloaded twice is
  one work); return the deduped list + the groups (for the report). **Never mutate silently** — the
  groups are surfaced in the quality report.
- Also expose duplicate cover detection by `cover_hash` (covers reused across works are informational,
  not dropped).

## 7. `report.py` + schemas

Add to `schemas.py`:
- `QuarantinedRecord`: `id: str`, `reason: str`, `raw: dict[str, Any]`.
- `DuplicateGroup`: `hash: str`, `ids: list[str]`, `canonical: str`.
- `QualityReport`:
  ```
  total_works: int
  valid_works: int
  quarantined: list[QuarantinedRecord]
  duplicate_document_groups: list[DuplicateGroup]
  duplicate_cover_groups: list[DuplicateGroup]
  missing_by_field: dict[str, int]         # field -> count of records missing it
  coverage: dict[str, float]               # e.g. {"description_pt": 0.9, "title_en": 0.8, "cover": 1.0}
  ```
- `build_quality_report(curate_result, doc_groups, cover_groups) -> QualityReport` — compute
  missing-by-field and coverage over the valid records (title/description per language, cover,
  document_hash, year, category…). Coverage = fraction non-null.

Provide `dump_json(report, path)` reuse so a run can later write `quality_report.json` (Step 5 wires
this into the RunContext via `set_quality(...)`; here just make it buildable and dumpable).

## 8. Tests (all offline, synthetic inputs) + acceptance

Write focused tests:
- `test_normalize.py`: `fix_encoding("SÃ£o Paulo") == "São Paulo"`; `fix_encoding` idempotent;
  `null_if_sentinel("N/A") is None`; `parse_int_locale("1.234") == 1234` and `("12.345 acessos") ==
  12345` and `("abc") is None`; `parse_year("Ano: 2005") == 2005`, `parse_year("9999") is None`;
  `clean_text("  a\xa0 b ") == "a b"`.
- `test_curate.py`: a well-formed work yields valid records; a work with empty PT title is
  **quarantined, not raised**, and appears in `CurateResult.quarantined` with a reason.
- `test_dedup.py`: two ids sharing a hash form one group with a stable canonical; the deduped universal
  list keeps only the canonical; null hashes are ignored.
- `test_report.py`: coverage and missing-by-field are computed correctly on a small synthetic set;
  quarantined + duplicate groups are carried through.

**Acceptance (run and report before committing):**
1. `uv sync` (now includes `ftfy`).
2. `uv run pytest -v` — all Step 1 + Step 2 tests green (the provided `test_outputs.py` stays skipped).
3. `uv run ruff check src/data_foundry/quality tests/test_normalize.py tests/test_curate.py
   tests/test_dedup.py tests/test_report.py` — clean (new code only; legacy-script BLE001 debt stays as-is).
4. Demonstrate the quarantine path: a short snippet (or a test) showing one invalid work quarantined
   while the rest curate successfully — the run does not crash.

## 9. Design notes (put the reasoning in code comments / for the README later)

- **Why pure Python, not Pandas/DuckDB here?** The records are small (tens of works) and **nested**
  (localized has `title{pt,en,es,fr}`), not naturally tabular. Pure typed functions are clearer and
  lighter. Pandas/DuckDB would be the tool if this were millions of flat rows — note this trade-off in
  the README. (Shows you pick tools by shape+scale, not habit.)
- **Quarantine over crash:** validation-as-code fails fast per record, but a single bad work must not
  kill the run — it's isolated and surfaced in the report. Correctness *and* robustness.
- **Never silently coerce:** garbage → `None`, not `0`. A wrong number is worse than a missing one.
- **Dedup surfaces, doesn't hide:** dropped duplicates are always reported, never silently removed.

## 10. Guardrails (from CLAUDE.md)

- Type everything; no `print`; small functions; conventional commit (`feat: data quality — normalize,
  curate, dedup, quality report`).
- Do not touch the 8 legacy scripts. Do not weaken `test_outputs.py`. Leave `TODO(step-3)` where these
  functions will be called by the orchestrator.
