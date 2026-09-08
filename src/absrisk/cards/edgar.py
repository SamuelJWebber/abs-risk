"""EDGAR conventions used by the card fetcher (same ones as scripts/scout/edgar_scout.py, with the session
injected so tests can serve fixtures instead of touching sec.gov).

- submissions API: https://data.sec.gov/submissions/CIK##########.json, with older filings on the pages
  listed under filings.files (https://data.sec.gov/submissions/<name>).
- filing folder:  https://www.sec.gov/Archives/edgar/data/<cik int>/<accession without dashes>/
  index.json lists the documents; <accession>-index-headers.html maps exhibit TYPE to FILENAME.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

SUBMISSIONS = "https://data.sec.gov/submissions/"
ARCHIVES = "https://www.sec.gov/Archives/edgar/data/"
FILING_KEYS = ["form", "filingDate", "reportDate", "accessionNumber", "primaryDocument", "primaryDocDescription"]


class FetchError(RuntimeError):
    pass


@dataclass(frozen=True)
class FilingRef:
    cik: str
    form: str
    filing_date: str
    report_date: str
    accession: str
    primary_document: str
    description: str = ""


def get_bytes(session, url: str) -> bytes:
    r = session.get(url)
    if r.status_code != 200:
        raise FetchError(f"HTTP {r.status_code} for {url}: {r.content[:200]!r}")
    return r.content


def get_json(session, url: str, cache: Path | None = None) -> dict:
    data = get_bytes(session, url)
    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(data)
    return json.loads(data.decode("utf-8"))


def submissions(session, cik10: str, cache_dir: Path | None = None) -> dict:
    return get_json(session, f"{SUBMISSIONS}CIK{cik10}.json",
                    cache_dir / f"submissions_{cik10}.json" if cache_dir else None)


def _page_filings(page: dict, cik10: str) -> list[FilingRef]:
    n = len(page["form"])
    out = []
    for i in range(n):
        g = {k: (page.get(k) or [""] * n)[i] for k in FILING_KEYS}
        out.append(FilingRef(cik10, g["form"], g["filingDate"], g["reportDate"], g["accessionNumber"],
                             g["primaryDocument"], g["primaryDocDescription"]))
    return out


def all_filings(session, cik10: str, cache_dir: Path | None = None, since: str = "") -> list[FilingRef]:
    """Every filing on the recent page plus the older pages listed in filings.files, newest first.

    Older pages are fetched only when their date range reaches past `since`.
    """
    sub = submissions(session, cik10, cache_dir)
    out = _page_filings(sub["filings"]["recent"], cik10)
    for f in sub["filings"].get("files", []):
        if since and f.get("filingTo", "") < since:
            continue
        page = get_json(session, SUBMISSIONS + f["name"], cache_dir / f["name"] if cache_dir else None)
        out.extend(_page_filings(page, cik10))
    out.sort(key=lambda x: (x.filing_date, x.accession), reverse=True)
    return out


def folder_url(cik10: str, accession: str) -> str:
    return f"{ARCHIVES}{int(cik10)}/{accession.replace('-', '')}/"


def filing_index(session, cik10: str, accession: str, cache: Path | None = None) -> dict:
    return get_json(session, folder_url(cik10, accession) + "index.json", cache)


def index_headers(session, cik10: str, accession: str, cache: Path | None = None) -> str:
    data = get_bytes(session, folder_url(cik10, accession) + f"{accession}-index-headers.html")
    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(data)
    return data.decode("utf-8", errors="replace")


def exhibit_types(index_headers_html: str) -> dict[str, str]:
    """{file name: exhibit TYPE} from the index-headers page (the <TYPE>/<FILENAME> pairs)."""
    out: dict[str, str] = {}
    text = index_headers_html.replace("&lt;", "<").replace("&gt;", ">")
    for m in re.finditer(r"<TYPE>([^<\s]+).*?<FILENAME>([^<\s]+)", text, re.S):
        out[m.group(2)] = m.group(1).upper()
    return out


def header_field(index_headers_html: str, tag: str) -> str | None:
    m = re.search(rf"<{tag}>(\S+)", index_headers_html.replace("&lt;", "<").replace("&gt;", ">"))
    return m.group(1) if m else None


def is_document(name: str, accession: str) -> bool:
    """A filing document worth keeping: .htm/.html/.txt, not an index page, not the full-submission text file."""
    n = name.lower()
    if n.endswith("-index.htm") or n.endswith("-index.html") or n.endswith("-index-headers.html") or n == "index.json":
        return False
    if n == f"{accession.lower()}.txt":
        return False
    return n.endswith((".htm", ".html", ".txt"))
