"""The `SOURCE=fixtures` offline source: no network, replays `tests/fixtures/pdfs/` instead of
scraping dominiopublico.mec.gov.br. Selected by `scrape.scrape_listing`/`fetch_detail` and
`download.download_pdf` when `settings.source == "fixtures"` — see those modules.

The listing/detail data below is a small, self-contained catalog describing the fixture PDFs; it
does not come from `tests/fixtures/listing.html` (that snippet is only for the `parse_listing`
unit test, a separate concern from this runtime source).

3 curated, real-title works are committed under `tests/fixtures/pdfs/`. Requests for more than
that (e.g. `--limit 12`, or the ≥10-works offline integration test) are padded with synthetic
works whose tiny PDFs are generated on first use via PyMuPDF and cached under
`tests/fixtures/pdfs/_generated/` (gitignored — never committed, per the "don't commit 10
binaries" guidance) instead of created ahead of time.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pymupdf

from data_foundry.config import REPO_ROOT
from data_foundry.schemas import RawListingEntry, WorkDetail

FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
FIXTURE_PDFS_DIR = FIXTURES_DIR / "pdfs"
GENERATED_PDFS_DIR = FIXTURE_PDFS_DIR / "_generated"

_SYNTHETIC_PREFIX = "fixture-synth-"


@dataclass(frozen=True, slots=True)
class FixtureWork:
    code: str
    title: str
    author: str
    category: str
    language: str
    year: str
    pdf_filename: str


CURATED_FIXTURE_WORKS: tuple[FixtureWork, ...] = (
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

_CURATED_BY_CODE: dict[str, FixtureWork] = {work.code: work for work in CURATED_FIXTURE_WORKS}


def _synthetic_fixture_work(n: int) -> FixtureWork:
    code = f"{_SYNTHETIC_PREFIX}{n:03d}"
    return FixtureWork(
        code=code,
        title=f"Obra Sintética {n:03d}",
        author="Autor Sintético",
        category="Ficção",
        language="Português",
        year="2000",
        pdf_filename=f"{code}.pdf",
    )


def _find(code: str) -> FixtureWork:
    work = _CURATED_BY_CODE.get(code)
    if work is not None:
        return work
    if code.startswith(_SYNTHETIC_PREFIX):
        return _synthetic_fixture_work(int(code[len(_SYNTHETIC_PREFIX) :]))
    raise KeyError(f"unknown fixture work code: {code!r}")


def _all_fixture_works(count: int) -> list[FixtureWork]:
    works = list(CURATED_FIXTURE_WORKS[: min(count, len(CURATED_FIXTURE_WORKS))])
    n = 1
    while len(works) < count:
        works.append(_synthetic_fixture_work(n))
        n += 1
    return works


def _ensure_synthetic_pdf(work: FixtureWork) -> Path:
    path = GENERATED_PDFS_DIR / work.pdf_filename
    if not path.exists():
        GENERATED_PDFS_DIR.mkdir(parents=True, exist_ok=True)
        doc = pymupdf.open()
        try:
            page = doc.new_page()
            page.insert_text((72, 100), work.title, fontsize=18)
            page.insert_text((72, 140), f"Um texto de teste para {work.title}.", fontsize=11)
            doc.save(str(path))
        finally:
            doc.close()
    return path


def list_fixture_entries(limit: int | None = None) -> list[RawListingEntry]:
    count = len(CURATED_FIXTURE_WORKS) if limit is None else limit
    works = _all_fixture_works(count)
    return [
        RawListingEntry(code=work.code, title=work.title, author=work.author, source="fixture catalog")
        for work in works
    ]


def fixture_detail(code: str) -> WorkDetail:
    work = _find(code)
    return WorkDetail(code=work.code, category=work.category, language=work.language, year=work.year)


def fixture_pdf_path(code: str) -> Path:
    work = _find(code)
    if code.startswith(_SYNTHETIC_PREFIX):
        return _ensure_synthetic_pdf(work)
    return FIXTURE_PDFS_DIR / work.pdf_filename
