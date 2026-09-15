from data_foundry.quality.dedup import (
    dedup_by_document_hash,
    find_duplicate_covers,
    find_duplicate_groups,
)
from data_foundry.schemas import UniversalRecord


def test_find_duplicate_groups_has_stable_canonical():
    groups = find_duplicate_groups({"a": "hash1", "b": "hash1", "c": "hash2", "d": None})

    assert len(groups) == 1
    group = groups[0]
    assert group.hash == "hash1"
    assert group.ids == ["a", "b"]
    assert group.canonical == "a"


def test_find_duplicate_groups_ignores_null_hashes():
    assert find_duplicate_groups({"a": None, "b": None}) == []


def test_dedup_by_document_hash_keeps_only_canonical():
    records = [
        UniversalRecord(id="a", document_hash="a" * 64),
        UniversalRecord(id="b", document_hash="a" * 64),
        UniversalRecord(id="c", document_hash="b" * 64),
        UniversalRecord(id="d", document_hash=None),
    ]

    deduped, groups = dedup_by_document_hash(records)

    assert {r.id for r in deduped} == {"a", "c", "d"}
    assert len(groups) == 1
    assert groups[0].ids == ["a", "b"]
    assert groups[0].canonical == "a"


def test_find_duplicate_covers_is_informational_only():
    groups = find_duplicate_covers({"a": "coverhash1", "b": "coverhash1", "c": None})

    assert len(groups) == 1
    assert groups[0].ids == ["a", "b"]
    assert groups[0].canonical == "a"
