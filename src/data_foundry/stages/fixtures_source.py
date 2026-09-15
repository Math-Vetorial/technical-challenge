"""The `SOURCE=fixtures` offline source: no network, replays `tests/fixtures/pdfs/` instead of
scraping dominiopublico.mec.gov.br. Selected by `scrape.scrape_listing`/`fetch_detail` and
`download.download_pdf` when `settings.source == "fixtures"` — see those modules.

The listing/detail data below is a small, self-contained catalog describing the committed PDF
fixtures; it does not come from `tests/fixtures/listing.html` (that snippet is only for the
`parse_listing` unit test, a separate concern from this runtime source).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from data_foundry.config import REPO_ROOT
from data_foundry.schemas import RawListingEntry, WorkDetail

FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
FIXTURE_PDFS_DIR = FIXTURES_DIR / "pdfs"


@dataclass(frozen=True, slots=True)
class FixtureWork:
    code: str
    title: str
    author: str
    category: str
    language: str
    year: str
    pdf_filename: str


FIXTURE_WORKS: tuple[FixtureWork, ...] = (
    FixtureWork(
        code="fixture-001",
        title="A Cidade e as Serras",
        author="Eça de Queirós",
        category="Romance",
        language="Português",
        year="1901",
        pdf_filename="book-001.pdf",
    ),
    FixtureWork(
        code="fixture-002",
        title="Memórias Póstumas de Brás Cubas",
        author="Machado de Assis",
        category="Romance",
        language="Português",
        year="1881",
        pdf_filename="book-002.pdf",
    ),
    FixtureWork(
        code="fixture-003",
        title="Iracema",
        author="José de Alencar",
        category="Romance",
        language="Português",
        year="1865",
        pdf_filename="book-003.pdf",
    ),
)

_BY_CODE: dict[str, FixtureWork] = {work.code: work for work in FIXTURE_WORKS}


def list_fixture_entries(limit: int | None = None) -> list[RawListingEntry]:
    works = FIXTURE_WORKS if limit is None else FIXTURE_WORKS[:limit]
    return [
        RawListingEntry(code=work.code, title=work.title, author=work.author, source="fixture catalog")
        for work in works
    ]


def fixture_detail(code: str) -> WorkDetail:
    work = _BY_CODE[code]
    return WorkDetail(code=work.code, category=work.category, language=work.language, year=work.year)


def fixture_pdf_path(code: str) -> Path:
    return FIXTURE_PDFS_DIR / _BY_CODE[code].pdf_filename
