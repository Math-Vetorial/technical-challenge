"""Scrape stage: paginated catalog listing + per-work detail page.

curl-cffi first (fast, no browser), Playwright as a fallback for when the site fronts a JS
challenge. Both are synchronous libraries, so calls run in a thread (`asyncio.to_thread`) to keep
the event loop free for other works' I/O.

TODO(step-5): persist the raw listing HTML/entries under `data/raw/` so a run can be replayed
without re-scraping; Step 3 only needs the parsed entries flowing through the engine.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

from data_foundry.config import Settings
from data_foundry.logging_setup import get_logger
from data_foundry.schemas import RawListingEntry, WorkDetail

logger = get_logger(__name__)

_SESSION = cffi_requests.Session(impersonate="chrome")
_PAGE_SIZE = 10

_DETAIL_FIELD_MAP = {
    "Título:": "title",
    "Autor:": "author",
    "Categoria:": "category",
    "Idioma:": "language",
    "Instituição:/Parceiro": "institution",
    "Ano da Tese": "year",
    "Acessos:": "accesses",
}


def _fetch_page_sync(url: str, timeout: int) -> str | None:
    try:
        resp = _SESSION.get(url, timeout=timeout)
        if resp.status_code == 200 and "challenge" not in resp.text[:500].lower():
            return resp.text
    except Exception as exc:  # noqa: BLE001 - any client failure falls through to the browser fallback
        logger.warning("curl-cffi fetch failed url=%s error=%s", url, exc)
    return _fetch_page_playwright_sync(url, timeout)


def _fetch_page_playwright_sync(url: str, timeout: int) -> str | None:
    from playwright.sync_api import (
        sync_playwright,  # heavy import, only needed on this fallback path
    )

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
            html = page.content()
            browser.close()
            return html
    except Exception as exc:  # noqa: BLE001 - a browser-launch/navigation failure means "no page"
        logger.warning("playwright fetch failed url=%s error=%s", url, exc)
    return None


async def fetch_page(url: str, settings: Settings) -> str | None:
    return await asyncio.to_thread(_fetch_page_sync, url, settings.request_timeout_s)


def _with_page_params(list_url: str, *, skip: int, pagina: int) -> str:
    parsed = urlparse(list_url)
    params = parse_qs(parsed.query)
    params["skip"] = [str(skip)]
    params["pagina"] = [str(pagina)]
    return urlunparse(parsed._replace(query=urlencode(params, doseq=True)))


def parse_listing(html: str) -> list[RawListingEntry]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="res")
    tbody = table.find("tbody") if table else None
    if tbody is None:
        return []

    entries: list[RawListingEntry] = []
    for row in tbody.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 6:
            continue
        link = cells[2].find("a")
        if not link:
            continue
        href = link.get("href", "")
        code = href.split("co_obra=")[-1].strip("'\" ") if "co_obra=" in href else None
        title = link.get_text(strip=True)
        if not (code and title):
            continue
        entries.append(
            RawListingEntry(
                code=code,
                title=title,
                author=cells[3].get_text(strip=True) or None,
                source=cells[4].get_text(strip=True) or None,
                format=cells[5].get_text(strip=True) or None,
                size=cells[6].get_text(strip=True) if len(cells) > 6 else None,
                accesses=cells[7].get_text(strip=True) if len(cells) > 7 else None,
            )
        )
    return entries


async def scrape_listing(settings: Settings, limit: int | None = None) -> AsyncIterator[RawListingEntry]:
    """Yield works page by page until the listing is exhausted or `limit` is reached."""
    yielded = 0
    page = 1
    while limit is None or yielded < limit:
        skip = (page - 1) * _PAGE_SIZE
        url = _with_page_params(settings.list_url, skip=skip, pagina=page)
        html = await fetch_page(url, settings)
        if not html:
            logger.warning("listing page fetch failed page=%s", page)
            return
        entries = parse_listing(html)
        if not entries:
            return
        for entry in entries:
            if limit is not None and yielded >= limit:
                return
            yield entry
            yielded += 1
        page += 1


def _parse_detail_page(html: str) -> dict[str, str]:
    matches = re.findall(r'class="detalhe\d"[^>]*>(.*?)</td>', html, re.DOTALL)
    clean = [BeautifulSoup(m, "html.parser").get_text(strip=True) for m in matches]

    metadata: dict[str, str] = {}
    current_field: str | None = None
    for text in clean:
        matched = next((key for label, key in _DETAIL_FIELD_MAP.items() if label in text), None)
        if matched:
            current_field = matched
        elif current_field and text and text != "\xa0":
            metadata.setdefault(current_field, text)
            current_field = None
    return metadata


def _find_download_url(html: str, base_url: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "download" not in href.lower():
            continue
        if href.startswith("../"):
            return href.replace("../", "https://dominiopublico.mec.gov.br/")
        if href.startswith("/"):
            return f"https://dominiopublico.mec.gov.br{href}"
        if not href.startswith("http"):
            return f"{base_url}/{href}"
        return href
    return None


async def fetch_detail(code: str, settings: Settings) -> WorkDetail:
    detail_url = f"{settings.base_url}/DetalheObraForm.do?select_action=&co_obra={code}"
    html = await fetch_page(detail_url, settings)
    if not html:
        return WorkDetail(code=code)

    metadata = _parse_detail_page(html)
    return WorkDetail(
        code=code,
        category=metadata.get("category"),
        language=metadata.get("language"),
        institution=metadata.get("institution"),
        year=metadata.get("year"),
        accesses=metadata.get("accesses"),
        download_url=_find_download_url(html, settings.base_url),
    )
