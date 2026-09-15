"""Duplicate detection by content hash.

**Dedup surfaces, doesn't hide**: dropped duplicates are always reported via `DuplicateGroup`,
never silently removed.
"""

from __future__ import annotations

from collections import defaultdict

from data_foundry.schemas import DuplicateGroup, UniversalRecord


def find_duplicate_groups(items: dict[str, str | None]) -> list[DuplicateGroup]:
    """Group ids sharing a non-null hash. `canonical` is the first id seen (stable)."""
    ids_by_hash: dict[str, list[str]] = defaultdict(list)
    for item_id, hash_value in items.items():
        if hash_value is None:
            continue
        ids_by_hash[hash_value].append(item_id)

    return [
        DuplicateGroup(hash=hash_value, ids=ids, canonical=ids[0])
        for hash_value, ids in ids_by_hash.items()
        if len(ids) > 1
    ]


def dedup_by_document_hash(
    universal: list[UniversalRecord],
) -> tuple[list[UniversalRecord], list[DuplicateGroup]]:
    """Keep the canonical record of each document_hash group; a book downloaded twice is one work."""
    groups = find_duplicate_groups({record.id: record.document_hash for record in universal})
    dropped_ids = {work_id for group in groups for work_id in group.ids if work_id != group.canonical}
    deduped = [record for record in universal if record.id not in dropped_ids]
    return deduped, groups


def find_duplicate_covers(cover_hashes: dict[str, str | None]) -> list[DuplicateGroup]:
    """Covers reused across works — informational only, never dropped."""
    return find_duplicate_groups(cover_hashes)
