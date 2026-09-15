# SPEC — Data Foundry Pipeline · Step 5: Staging Persistence + Assembly + Curated Outputs

> **How to use:** Give this to Claude Code in the repo. Say:
> *"Read CLAUDE.md and this spec. Implement Step 5 only: make the event bus functional (subscribers
> persist per-work state to data/staging/), assemble the two final datasets + quality report into the
> versioned curated run dir, wire it into pipeline.run and the manifest, and re-enable test_outputs.py.
> Run the acceptance checks in §8 and show me the results before committing."*

Prereq: Steps 1–4 merged. Build on them.

## 1. Goal

Turn the enriched, in-flight work data into the **two contract datasets**, produced into a **versioned
curated run** with a **quality report** and a complete **manifest** — and make the **event bus
functional** (it drives staging persistence instead of being decorative). After Step 5, a run produces
`localized_catalog.json`, `universal_metadata.json`, and `quality_report.json` under
`data/curated/runs/<run_id>/`, `latest` points at it, and `test_outputs.py` passes.

## 2. In scope / out of scope

**In scope:**
- **Staging persistence via event subscribers** — the bus becomes functional (see §3).
- `stages/assemble.py` — curate → dedup → build the two datasets + quality report (see §4).
- Wire assembly into `pipeline.run` after the enrichment barrier; write curated outputs + manifest
  fields (see §5).
- Re-enable `tests/test_outputs.py` repointed at `curated/latest`, keeping its assertions; make the
  offline test path reach ≥10 works (see §6).

**Out of scope:** README / architecture diagram / Docker polish (Step 6). Leave those for last.

## 3. Make the event bus functional — staging persistence (the coherence fix)

Add a `staging/accumulator.py` with a `WorkAccumulator` that **subscribes to the enrichment events** and
builds one `EnrichedWork` per work in memory:
- `WorkDiscovered` → create `EnrichedWork(raw=…)`; `PdfDownloaded` → set `pdf_path`;
  `Hashed` → set `document_hash`; `CoverExtracted` → set `cover_path`/`cover_hash`;
  `Described` → set `description`; `TitleTranslated` → `title_translations[lang]=text`;
  `DescriptionTranslated` → `description_translations[lang]=text`; also stash the `WorkDetail`.
- After the pipeline barrier (all works terminal), `flush()` writes each `EnrichedWork` to
  `data/staging/works/<code>.json` (silver layer, schema-validated). This is what assembly reads.

This makes the reactive stages genuinely **event-driven** (subscribers react to `Hashed`/`Described`/…
to build state), and produces the silver layer. In-memory dict is safe (single-threaded asyncio);
flush is idempotent (overwrite the per-work staging file).

`pipeline.run` wires it: `acc = WorkAccumulator(); acc.subscribe_to(bus)` before processing; after the
barrier, `acc.flush(settings.staging_dir)`; pass the accumulated works to assembly.

## 4. `stages/assemble.py` — build the two datasets (refactor of scripts 07/08)

- `assemble(works: list[EnrichedWork], run_id) -> AssembleResult` where `AssembleResult` carries
  `localized: LocalizedCatalog`, `universal: UniversalMetadata`, `quality: QualityReport`.
- Steps, reusing Step-2 quality code:
  1. `curate_works(works, run_id)` → valid `LocalizedRecord`/`UniversalRecord` lists + quarantined.
  2. `dedup_by_document_hash(universal)` → deduped universal + document duplicate groups; also compute
     cover duplicate groups from `{id: cover_hash}`.
  3. Keep localized records aligned to the deduped universal ids (drop localized records whose id was
     dropped as a duplicate, so the two datasets stay **consistent** — same id set).
  4. `build_quality_report(curate_result, doc_groups, cover_groups)` → `QualityReport`.
  5. Validate the whole datasets through `LocalizedCatalog(...)` / `UniversalMetadata(...)` (RootModel).
- The two datasets must have the **exact same set of ids** (the provided `test_outputs.py` asserts this).

## 5. Wire into `pipeline.run` + curated outputs + manifest

After the enrichment barrier and `acc.flush(...)`:
- `result = assemble(acc.works(), ctx.run_id)`.
- Write into `ctx.run_dir`:
  - `localized_catalog.json` ← `dump_json(result.localized, …)`
  - `universal_metadata.json` ← `dump_json(result.universal, …)`
  - `quality_report.json` ← `dump_json(result.quality, …)`
- Record them in the manifest: `ctx.record_output("localized_catalog", path)` (stores rel path +
  sha256), same for the other two; `ctx.set_quality(result.quality.model_dump())`;
  `ctx.update_counts(valid_works=…, quarantined=…, duplicates=…)`.
- `ctx.finish("success")` (updates `latest`). On any assembly exception, `ctx.finish("failed")` and
  re-raise.
- For `--only` and `limit==0`, keep current behavior (no assembly).

## 6. Re-enable `tests/test_outputs.py`

- Remove the module-level skip. **Repoint** `OUTPUT_DIR` from `data/output/` to
  `data/curated/latest/` (resolve the symlink/`latest.txt`). Keep MIN_ENTRIES=10 and **all assertions**
  (id+title.pt, id+document_hash, `loc_ids == uni_ids == cat_ids`). Note the path change in the README.
- Its `cat_ids` check reads `catalog.json` today; adapt to the curated datasets (compare
  `localized ids == universal ids`; drop the `catalog.json` leg or point it at a staging catalog if you
  keep one). Do not weaken the intent (both datasets consistent, ≥10, required fields present).
- **Reach ≥10 offline:** add a `conftest.py` fixture that runs the offline pipeline
  (`LLM_PROVIDER=mock`, `SOURCE=fixtures`) with **≥10 generated works** (generate 10+ tiny PDFs via
  PyMuPDF at test time; don't commit 10 binaries) into a temp/`latest` curated run, so `test_outputs.py`
  validates a real assembled output offline. Document that `make run` produces the same shape from ≥10
  real books.

## 7. Design notes (for the README)

- **The bus is now functional and event-driven:** subscribers react to enrichment events to build the
  silver layer; the bounded queue is the backpressure boundary. Say this plainly — no overselling.
- **Consistency by construction:** dedup drops duplicate ids from *both* datasets together, so
  `localized` and `universal` always share one id set — the invariant the tests check.
- **Everything auditable:** the manifest records output paths + sha256 + the quality report + counts;
  a reviewer can answer "what did this run produce and how clean was it?" from one file.

## 8. Tests + acceptance

- `tests/test_assemble.py`: given synthetic `EnrichedWork`s (incl. one invalid → quarantined, and a
  duplicate document_hash pair), `assemble` yields consistent id sets, drops the duplicate from both
  datasets, and reports it; quarantined surfaced in the quality report.
- `tests/test_staging.py`: the accumulator builds a correct `EnrichedWork` from a sequence of events and
  flushes valid staging JSON.
- `test_outputs.py`: green against the offline ≥10 run.

**Acceptance (run and report before committing):**
1. `uv run pytest -v` — **all green, including `test_outputs.py`** (no skips left, or only justified ones).
2. `LLM_PROVIDER=mock SOURCE=fixtures uv run python -m data_foundry run --limit 12` produces
   `data/curated/runs/<run_id>/{localized_catalog,universal_metadata,quality_report}.json`, `latest`
   points at it, and the manifest has `outputs`, `output_hashes`, `quality`, and counts filled.
3. Re-running produces a **new** run dir; the previous one is byte-identical (versioning intact).
4. `uv run ruff check` clean.
5. Show a snippet of `localized_catalog.json` + `universal_metadata.json` + the manifest so we can eyeball
   the contract.

## 9. Guardrails (from CLAUDE.md)

- The two datasets are the contract — same id set, shapes per CLAUDE.md (expanded ok, never shrunk).
- Bus subscribers do the staging persistence (functional, not decorative). Async/typed/no-print.
- Conventional commit: `feat: staging persistence + dataset assembly + curated versioned outputs`.
