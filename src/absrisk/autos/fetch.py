"""List every ABS-EE (and ABS-EE/A) filing of a deal and download each filing's EX-102 asset-data XML.

EDGAR conventions and helper functions follow scripts/scout/edgar_scout.py (fts, submissions, filing_index,
exhibit_files_by_type, download_ex102, folder_url), re-implemented here with an injectable session so tests run
against canned responses and never touch EDGAR (CLAUDE.md). Every request goes through absrisk.http.make_session()
unless a session is injected.

Rules, each cited to design/scout-autos.md:

- Where the filings live (section 11, "Design inputs for the fetcher"): depositor-filed shelves (Santander
  1383094, Capital One 1133438, Honda 890975, Toyota's depositor, Nissan, Hyundai, World Omni, Ally, Carvana,
  Mercedes, VW, Harley) keep many deals in one submissions JSON, so the deal's filings are picked by the
  primary-document prefix (`sdart261`, `copart251`, `harot251`); self-filed trusts (CarMax, Exeter, AmeriCredit,
  GM Financial, Ford, BMW, the Toyota trusts) use every ABS-EE under the trust CIK.
- Older submissions pages (`filings.files[].name`) are walked when present (section 1b: SDART's depositor has
  three older pages; a 2025 deal's first filings sit there).
- One filing per reporting period (section 6 items 10 and 11): prefer the amendment (ABS-EE/A) when one exists,
  else the largest EX-102; the initial offering-pool variants (lp/sp/mp, largepool/smallpool) share a period and
  the largest is kept, flagged `offering_pool` so the panel builder can start at the first post-closing filing.
- The EX-102 is identified by exhibit type from the filing's index-headers page, falling back to the largest .xml
  whose name does not contain "103" (section 7: names share no pattern; CarMax's and Ford's contain no "102").
- Raw XML plus index.json and the index-headers page are stored under raw/<deal>/<accession>/; the manifest
  records deal, accession, form, filing date, period, file, size, sha256 and URL (section 11). Idempotent: a file
  already present with the size index.json reports is not downloaded again.
- A blank CIK is resolved on the runner by exact-phrase full-text search on the trust name (efts); a blank
  doc_prefix for a depositor-filed deal is derived from the primary-document name of an ABS-EE hit for that trust
  (the part before "absee").
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable
from urllib.parse import quote

from .deals import Deal

log = logging.getLogger(__name__)

ABSEE_FORMS = ("ABS-EE", "ABS-EE/A")
SUBMISSIONS = "https://data.sec.gov/submissions/"
EFTS = "https://efts.sec.gov/LATEST/search-index"
ARCHIVES = "https://www.sec.gov/Archives/edgar/data/"
CHUNK = 1 << 20


@dataclass
class Filing:
    accession: str
    form: str
    filing_date: str
    period: str
    primary_document: str
    size: int | None = None
    source: str = ""
    offering_pool: bool = False
    reason: str = ""
    superseded: list[str] = field(default_factory=list)


class FetchError(RuntimeError):
    pass


# ---------------------------------------------------------------- HTTP helpers (session injected)

def get(session, url: str, dest: Path | None = None, stream: bool = False) -> bytes | None:
    """GET one URL; save it to `dest` if given; return the bytes (b"" when streamed) or None on a non-200."""
    r = session.get(url, stream=stream)
    if r.status_code != 200:
        log.warning("GET %s -> HTTP %s", url, r.status_code)
        return None
    if dest is not None:
        dest.parent.mkdir(parents=True, exist_ok=True)
    if stream:
        assert dest is not None
        tmp = dest.with_suffix(dest.suffix + ".part")
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(CHUNK):
                if chunk:
                    f.write(chunk)
        tmp.replace(dest)
        return b""
    data = r.content
    if dest is not None:
        dest.write_bytes(data)
    return data


def get_cached(session, url: str, dest: Path) -> bytes | None:
    """Filings are immutable, so an index page already on disk is reused without a request."""
    if dest.exists() and dest.stat().st_size > 0:
        return dest.read_bytes()
    return get(session, url, dest)


def get_json(session, url: str, dest: Path, cached: bool = False) -> dict | None:
    data = get_cached(session, url, dest) if cached else get(session, url, dest)
    if data is None:
        return None
    return json.loads(data.decode("utf-8"))


# ---------------------------------------------------------------- EDGAR conventions (from scripts/scout/edgar_scout.py)

def fts(session, query: str, forms: str, dest: Path, startdt: str = "2015-01-01", enddt: str = "2030-12-31",
        page: int = 1) -> dict | None:
    q = quote('"' + query + '"')
    url = f"{EFTS}?q={q}&forms={forms}&dateRange=custom&startdt={startdt}&enddt={enddt}&page={page}"
    return get_json(session, url, dest)


def entities_from_fts(d: dict | None) -> list[tuple[str, str, int]]:
    """[(cik10, display name, doc_count)] sorted by doc count."""
    out = []
    for b in (d or {}).get("aggregations", {}).get("entity_filter", {}).get("buckets", []):
        m = re.search(r"\(CIK (\d+)\)", b["key"])
        if m:
            out.append((m.group(1).zfill(10), b["key"], b["doc_count"]))
    return sorted(out, key=lambda x: -x[2])


def submissions(session, cik10: str, dest: Path) -> dict | None:
    return get_json(session, f"{SUBMISSIONS}CIK{cik10}.json", dest)


def filings_from_page(page: dict, source: str) -> list[Filing]:
    """Rows of one submissions page. The main page nests them under filings.recent; older pages are flat."""
    r = page["filings"]["recent"] if "filings" in page else page
    n = len(r.get("accessionNumber", []))

    def col(k: str) -> list:
        v = r.get(k)
        return v if v is not None else [None] * n

    out = []
    for i in range(n):
        size = col("size")[i]
        out.append(Filing(
            accession=col("accessionNumber")[i], form=col("form")[i] or "", filing_date=col("filingDate")[i] or "",
            period=col("reportDate")[i] or "", primary_document=col("primaryDocument")[i] or "",
            size=int(size) if size not in (None, "") else None, source=source,
        ))
    return out


def all_filings(session, cik10: str, dest_dir: Path) -> list[Filing]:
    """Every filing on the main submissions page plus every older page listed in filings.files."""
    main = submissions(session, cik10, dest_dir / f"submissions_{cik10}.json")
    if main is None:
        raise FetchError(f"submissions JSON for CIK {cik10} unavailable")
    rows = filings_from_page(main, f"CIK{cik10}.json")
    for f in main.get("filings", {}).get("files", []) or []:
        name = f["name"]
        page = get_json(session, SUBMISSIONS + name, dest_dir / name)
        if page is None:
            raise FetchError(f"older submissions page {name} unavailable")
        rows.extend(filings_from_page(page, name))
    return rows


def folder_url(cik10: str, acc: str) -> str:
    return f"{ARCHIVES}{int(cik10)}/{acc.replace('-', '')}/"


def filing_index(session, cik10: str, acc: str, dest: Path) -> dict | None:
    return get_json(session, folder_url(cik10, acc) + "index.json", dest, cached=True)


def exhibit_files_by_type(session, cik10: str, acc: str, dest_dir: Path) -> dict[str, list[str]]:
    """Exhibit TYPE (EX-102, EX-103, ...) -> file names, from the filing's index-headers page (SGML pattern
    `<TYPE>EX-102 ... <FILENAME>x.xml`, HTML-escaped in the page body)."""
    url = folder_url(cik10, acc) + f"{acc}-index-headers.html"
    data = get_cached(session, url, dest_dir / f"{acc}-index-headers.html")
    if data is None:
        return {}
    text = data.decode("utf-8", "replace").replace("&lt;", "<").replace("&gt;", ">")
    out: dict[str, list[str]] = {}
    for m in re.finditer(r"<TYPE>([^<\s]+)\s.*?<FILENAME>([^<\s]+)", text, re.S):
        out.setdefault(m.group(1).upper(), []).append(m.group(2))
    return out


def index_headers_period(dest_dir: Path, acc: str) -> str:
    """`<PERIOD>YYYYMMDD` from a saved index-headers page, as YYYY-MM-DD; '' if absent."""
    p = dest_dir / f"{acc}-index-headers.html"
    if not p.exists():
        return ""
    m = re.search(r"<PERIOD>(\d{8})", p.read_text(encoding="utf-8", errors="replace"))
    return f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}" if m else ""


def pick_ex102(types: dict[str, list[str]], index: dict | None) -> tuple[str | None, int | None]:
    """The EX-102 file name and its size from index.json. Exhibit type first; else the largest non-103 .xml."""
    sizes: dict[str, int] = {}
    for it in (index or {}).get("directory", {}).get("item", []):
        try:
            sizes[it["name"]] = int(it.get("size") or 0)
        except (TypeError, ValueError):
            sizes[it["name"]] = 0
    names = types.get("EX-102", [])
    if names:
        name = max(names, key=lambda n: sizes.get(n, 0)) if len(names) > 1 else names[0]
        return name, sizes.get(name)
    cands = [n for n in sizes if n.lower().endswith(".xml") and "103" not in n.lower()]
    if not cands:
        return None, None
    name = max(cands, key=lambda n: sizes[n])
    return name, sizes[name]


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def download_ex102(session, cik10: str, acc: str, dest_dir: Path, previous: dict | None = None) -> dict:
    """Fetch one filing's EX-102 into dest_dir (with index.json and index-headers). Returns a manifest entry.

    Skips the download when the file is already present with the size index.json reports; reuses the previous
    manifest's sha256 in that case.
    """
    types = exhibit_files_by_type(session, cik10, acc, dest_dir)
    index = filing_index(session, cik10, acc, dest_dir / "index.json")
    name, size = pick_ex102(types, index)
    entry: dict = {"accession": acc, "file": None, "size": None, "sha256": None, "url": None,
                   "ex102_by_type": bool(types.get("EX-102")), "skipped": False}
    if name is None:
        entry["error"] = "no EX-102 found (no exhibit type and no .xml candidate)"
        log.error("%s: %s", acc, entry["error"])
        return entry
    url = folder_url(cik10, acc) + name
    target = dest_dir / name
    entry.update({"file": f"{acc}/{name}", "url": url})
    if target.exists() and size and target.stat().st_size == size:
        entry["skipped"] = True
        entry["size"] = size
        prev_sha = (previous or {}).get("sha256") if (previous or {}).get("size") == size else None
        entry["sha256"] = prev_sha or sha256_of(target)
        log.info("%s: %s present (%d bytes), skipped", acc, name, size)
        return entry
    if get(session, url, target, stream=True) is None:
        entry["error"] = f"download failed: {url}"
        return entry
    got = target.stat().st_size
    if size and got != size:
        target.unlink(missing_ok=True)
        entry["error"] = f"size mismatch: index.json says {size}, got {got}"
        log.error("%s: %s", acc, entry["error"])
        return entry
    entry["size"] = got
    entry["sha256"] = sha256_of(target)
    log.info("%s: downloaded %s (%d bytes)", acc, name, got)
    return entry


# ---------------------------------------------------------------- deal resolution and filing selection

POOL_SUFFIX = re.compile(r"\d(lp|sp|mp)$")
POOL_WORD = re.compile(r"(large|small|medium|mid)[_-]?pool")


def is_pool_variant(primary_document: str) -> bool:
    """Offering-pool naming seen so far (scout-autos section 2): `...1933lp.htm` / `...1820sp.htm` /
    `...1940lp.xml` at Santander and Capital One; `largepool` / `smallpool` at CarMax."""
    stem = primary_document.lower().rsplit(".", 1)[0]
    return bool(POOL_SUFFIX.search(stem) or POOL_WORD.search(stem))


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def resolve_deal(session, deal: Deal, dest_dir: Path) -> dict:
    """Decide which CIK's submissions to list and which primary-document prefix to filter on.

    Returns {"filer_cik", "doc_prefix", "how"} and saves any search response under dest_dir/_resolve/.
    """
    filer = deal.cik or deal.depositor_cik
    prefix = deal.doc_prefix
    how: list[str] = []
    if not filer:
        if not deal.name:
            raise FetchError(f"{deal.deal}: no cik, no depositor_cik and no name to search for")
        d = fts(session, deal.name, "ABS-EE", dest_dir / "_resolve" / "fts_absee.json")
        want = _norm(deal.name)
        ents = entities_from_fts(d)
        exact = [e for e in ents if _norm(e[1].split("(CIK")[0]) == want]
        loose = [e for e in ents if want in _norm(e[1])]
        pick = (exact or loose or [None])[0]
        if pick is None:
            raise FetchError(f"{deal.deal}: full-text search for {deal.name!r} found no matching entity: {ents[:5]}")
        filer = pick[0]
        how.append(f"cik {filer} from full-text search entity {pick[1]!r}")
    depositor_filed = bool(deal.depositor_cik) and filer == deal.depositor_cik
    if depositor_filed and not prefix:
        if not deal.name:
            raise FetchError(f"{deal.deal}: depositor-filed deal needs a doc_prefix or a name to derive it from")
        d = fts(session, deal.name, "ABS-EE", dest_dir / "_resolve" / "fts_prefix.json")
        want = _norm(deal.name)
        for h in (d or {}).get("hits", {}).get("hits", []):
            src = h.get("_source", {})
            if deal.depositor_cik.lstrip("0") not in [c.lstrip("0") for c in src.get("ciks", [])]:
                continue
            if not any(_norm(n.split("(CIK")[0]) == want for n in src.get("display_names", [])):
                continue
            doc = h["_id"].split(":", 1)[1].lower()
            m = re.match(r"([a-z0-9]+?)[_-]?absee", doc)
            if m:
                prefix = m.group(1)
                how.append(f"doc_prefix {prefix!r} from full-text hit {h['_id']}")
                break
        if not prefix:
            raise FetchError(f"{deal.deal}: could not derive a doc_prefix from full-text search hits")
    return {"filer_cik": filer, "doc_prefix": prefix, "depositor_filed": depositor_filed, "how": how}


def select_filings(filings: list[Filing], doc_prefix: str = "",
                   ex102_size: Callable[[Filing], int | None] | None = None) -> list[Filing]:
    """ABS-EE and ABS-EE/A rows, prefix-filtered, one per reporting period, in period order."""
    rows = [f for f in filings if f.form in ABSEE_FORMS]
    if doc_prefix:
        rows = [f for f in rows if f.primary_document.lower().startswith(doc_prefix.lower())]
    groups: dict[str, list[Filing]] = {}
    for f in rows:
        groups.setdefault(f.period or f"acc:{f.accession}", []).append(f)
    chosen: list[Filing] = []
    for key in sorted(groups):
        group = groups[key]
        amendments = [f for f in group if f.form == "ABS-EE/A"]
        pool_named = any(is_pool_variant(f.primary_document) for f in group)
        if amendments:
            pick = max(amendments, key=lambda f: (f.filing_date, f.accession))
            pick.reason = f"amendment ({len(group)} filings for the period)"
        elif len(group) == 1:
            pick = group[0]
            pick.reason = "only filing for the period"
        else:
            sizes = {}
            for f in group:
                s = ex102_size(f) if ex102_size else None
                sizes[f.accession] = s if s else (f.size or 0)
            pick = max(group, key=lambda f: (sizes[f.accession], f.filing_date, f.accession))
            pick.reason = f"largest of {len(group)} pool variants"
        pick.offering_pool = pool_named or (len(group) > 1 and not amendments)
        pick.superseded = [f.accession for f in group if f is not pick]
        chosen.append(pick)
    chosen.sort(key=lambda f: (f.period, f.filing_date, f.accession))
    return chosen


# ---------------------------------------------------------------- one deal

def fetch_deal(deal: Deal, raw_root: str | Path, session=None) -> dict:
    """List, select and download every EX-102 of one deal into raw_root/<deal>/; write and return the manifest."""
    if session is None:
        from ..http import make_session

        session = make_session()
    dest = Path(raw_root) / deal.deal
    dest.mkdir(parents=True, exist_ok=True)
    res = resolve_deal(session, deal, dest)
    filer, prefix = res["filer_cik"], res["doc_prefix"]
    filings = all_filings(session, filer, dest / "submissions")
    candidates = [f for f in filings if f.form in ABSEE_FORMS
                  and (not prefix or f.primary_document.lower().startswith(prefix))]
    (dest / "listing.json").write_text(json.dumps([asdict(f) for f in candidates], indent=1), encoding="utf-8")

    def ex102_size(f: Filing) -> int | None:
        types = exhibit_files_by_type(session, filer, f.accession, dest / f.accession)
        idx = filing_index(session, filer, f.accession, dest / f.accession / "index.json")
        return pick_ex102(types, idx)[1]

    chosen = select_filings(candidates, prefix, ex102_size)
    previous: dict[str, dict] = {}
    mf = dest / "manifest.json"
    if mf.exists():
        try:
            previous = {e["accession"]: e for e in json.loads(mf.read_text(encoding="utf-8")).get("filings", [])}
        except (ValueError, KeyError):
            previous = {}
    entries = []
    for f in chosen:
        e = download_ex102(session, filer, f.accession, dest / f.accession, previous.get(f.accession))
        period = f.period or index_headers_period(dest / f.accession, f.accession)
        entries.append({
            "deal": deal.deal, "accession": f.accession, "form": f.form, "filing_date": f.filing_date,
            "period": period, "primary_document": f.primary_document, "offering_pool": f.offering_pool,
            "reason": f.reason, "superseded": f.superseded, **e,
        })
    manifest = {
        "deal": deal.deal, "lender": deal.lender, "filer_cik": filer, "doc_prefix": prefix, "resolution": res,
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_candidates": len(candidates), "n_filings": len(entries),
        "n_downloaded": sum(1 for e in entries if e.get("file") and not e.get("skipped") and not e.get("error")),
        "n_skipped": sum(1 for e in entries if e.get("skipped")),
        "n_errors": sum(1 for e in entries if e.get("error")),
        "filings": entries,
    }
    mf.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    log.info("%s: %d filings (%d downloaded, %d skipped, %d errors)", deal.deal, len(entries),
             manifest["n_downloaded"], manifest["n_skipped"], manifest["n_errors"])
    return manifest
