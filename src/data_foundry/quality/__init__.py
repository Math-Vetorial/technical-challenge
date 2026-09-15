"""Data-quality backbone: normalize, curate, dedup, report — all pure, offline-testable.

Why pure Python here, not Pandas/DuckDB? The records are small (tens of works) and nested
(a localized record has `title{pt,en,es,fr}`), not naturally tabular. Pure typed functions stay
clearer and lighter at this scale; Pandas/DuckDB would earn their keep if this were millions of
flat rows. Tools follow shape and scale, not habit.

TODO(step-3): the orchestrator wires these into the live scrape/download/hash/describe/
translate/cover flow, one work at a time.
"""
