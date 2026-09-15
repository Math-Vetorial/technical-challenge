import pytest
from pydantic import ValidationError

from data_foundry.schemas import LangField, LocalizedRecord, UniversalRecord


def test_localized_record_valid():
    record = LocalizedRecord(
        id="obra123",
        author="Machado de Assis",
        title=LangField(pt="Dom Casmurro", en="Dom Casmurro"),
        description=LangField(pt="Um romance."),
    )
    assert record.id == "obra123"
    assert record.title.pt == "Dom Casmurro"


def test_localized_record_requires_pt_title():
    with pytest.raises(ValidationError):
        LocalizedRecord(id="obra123", title=LangField(en="Only English"))

    with pytest.raises(ValidationError):
        LocalizedRecord(id="obra123", title=LangField(pt="  "))


def test_universal_record_valid():
    record = UniversalRecord(
        id="obra123",
        document_hash="a" * 64,
        year=1899,
        accesses=42,
    )
    assert record.document_hash == "a" * 64
    assert record.accesses == 42


def test_universal_record_rejects_bad_document_hash():
    with pytest.raises(ValidationError):
        UniversalRecord(id="obra123", document_hash="not-a-hash")

    with pytest.raises(ValidationError):
        UniversalRecord(id="obra123", document_hash="a" * 63)


@pytest.mark.parametrize("year", [999, 3000])
def test_universal_record_rejects_year_out_of_range(year):
    with pytest.raises(ValidationError):
        UniversalRecord(id="obra123", year=year)


def test_universal_record_accesses_accepts_int_rejects_garbage():
    assert UniversalRecord(id="obra123", accesses=10).accesses == 10
    assert UniversalRecord(id="obra123", accesses="10").accesses == 10

    with pytest.raises(ValidationError):
        UniversalRecord(id="obra123", accesses="not-a-number")
