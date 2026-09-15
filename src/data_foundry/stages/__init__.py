# Stage functions refactored from the original 8 scripts (Option B): scrape, download, hash,
# covers, describe, translate. Pure/async, typed, read/write the medallion layers — no flat-file
# JSON, no print. Wired into the concrete work graph by pipeline.py.
# TODO(step-5): assembly (localized_catalog.json / universal_metadata.json) is not a "stage" here
# yet — it consumes quality.curate/dedup/report over the enriched works these stages produce.
