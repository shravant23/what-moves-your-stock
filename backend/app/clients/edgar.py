"""SEC EDGAR client.

Uses the official JSON APIs:
  - ticker -> CIK map:  https://www.sec.gov/files/company_tickers.json
  - filing index:       https://data.sec.gov/submissions/CIK##########.json
  - documents:          https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{doc}

All responses are cached in SQLite. Filed documents are immutable, so they
are cached forever and never re-fetched.
"""

import asyncio
import re
import warnings
from datetime import timedelta

import httpx
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

# Modern filings are inline-XBRL (XHTML); bs4's lxml HTML parser handles them
# fine but warns about the XML declaration.
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
from pydantic import BaseModel

from ..cache import cache_get, cache_get_json, cache_set, cache_set_json
from ..config import EDGAR_USER_AGENT

TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik10}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{doc}"

HEADERS = {
    "User-Agent": EDGAR_USER_AGENT,
    "Accept-Encoding": "gzip, deflate",
}

TICKER_MAP_TTL = timedelta(hours=24)
SUBMISSIONS_TTL = timedelta(hours=24)


class TickerNotFoundError(Exception):
    pass


class Filing(BaseModel):
    form: str  # "10-K" | "10-Q"
    accession: str  # dashless, e.g. "000083125925000008"
    primary_doc: str  # e.g. "fcx-20241231.htm"
    filing_date: str
    report_date: str
    cik: int
    url: str


async def _get(client: httpx.AsyncClient, url: str) -> httpx.Response:
    resp = await client.get(url, headers=HEADERS, timeout=60.0)
    resp.raise_for_status()
    # Stay well under EDGAR's 10 req/s courtesy limit.
    await asyncio.sleep(0.15)
    return resp


async def get_ticker_map(client: httpx.AsyncClient) -> dict:
    """{ticker -> {cik, title}} for every EDGAR-registered ticker."""
    cached = cache_get_json("edgar:ticker_map", TICKER_MAP_TTL)
    if cached is not None:
        return cached
    resp = await _get(client, TICKER_MAP_URL)
    raw = resp.json()  # {"0": {"cik_str": ..., "ticker": ..., "title": ...}, ...}
    mapping = {
        row["ticker"].upper(): {"cik": row["cik_str"], "title": row["title"]}
        for row in raw.values()
    }
    cache_set_json("edgar:ticker_map", mapping)
    return mapping


async def ticker_to_cik(client: httpx.AsyncClient, ticker: str) -> tuple[int, str]:
    """Return (cik, company_title). Raises TickerNotFoundError."""
    mapping = await get_ticker_map(client)
    entry = mapping.get(ticker.upper())
    if entry is None:
        raise TickerNotFoundError(f"Ticker {ticker!r} not found in EDGAR")
    return entry["cik"], entry["title"]


async def get_submissions(client: httpx.AsyncClient, cik: int) -> dict:
    cik10 = str(cik).zfill(10)
    key = f"edgar:submissions:{cik10}"
    cached = cache_get_json(key, SUBMISSIONS_TTL)
    if cached is not None:
        return cached
    resp = await _get(client, SUBMISSIONS_URL.format(cik10=cik10))
    data = resp.json()
    cache_set_json(key, data)
    return data


async def get_target_filings(client: httpx.AsyncClient, ticker: str) -> list[Filing]:
    """Latest 10-K plus the latest two 10-Qs for a ticker."""
    cik, _title = await ticker_to_cik(client, ticker)
    subs = await get_submissions(client, cik)
    recent = subs["filings"]["recent"]

    filings: list[Filing] = []
    wanted = {"10-K": 1, "10-Q": 2}
    for i, form in enumerate(recent["form"]):
        if wanted.get(form, 0) <= 0:
            continue
        accession = recent["accessionNumber"][i].replace("-", "")
        primary_doc = recent["primaryDocument"][i]
        if not primary_doc:
            continue
        filings.append(
            Filing(
                form=form,
                accession=accession,
                primary_doc=primary_doc,
                filing_date=recent["filingDate"][i],
                report_date=recent["reportDate"][i],
                cik=cik,
                url=ARCHIVE_URL.format(cik=cik, accession=accession, doc=primary_doc),
            )
        )
        wanted[form] -= 1
        if all(v <= 0 for v in wanted.values()):
            break
    return filings


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    # Inline-XBRL filings carry a hidden <ix:header> block of machine-readable
    # facts (element URIs, context refs) that pollutes the extracted text.
    for tag in soup.find_all(["ix:header", "ix:hidden", "ix:references", "ix:resources"]):
        tag.decompose()
    text = soup.get_text("\n")
    # Collapse runs of whitespace while keeping paragraph breaks readable.
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


async def get_filing_text(client: httpx.AsyncClient, filing: Filing) -> str:
    """Plain text of a filing's primary document. Cached forever — a filed
    document never changes."""
    key = f"edgar:doc:{filing.accession}:{filing.primary_doc}"
    cached = cache_get(key, ttl=None)
    if cached is not None:
        return cached
    resp = await _get(client, filing.url)
    text = _html_to_text(resp.text)
    cache_set(key, text)
    return text
