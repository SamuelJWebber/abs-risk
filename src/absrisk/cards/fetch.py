"""Download every 10-D (and the latest 424B prospectus) for the six live card master trusts.

Layout: data/raw/cards/<slug>/<accession>/<documents> + manifest.json, and
        data/raw/cards/<slug>/prospectus/<accession>/<primary document> + manifest.json.
Idempotent: a filing whose manifest lists every file at its recorded size is not fetched again.
Every request goes through absrisk.http.make_session() (User-Agent, 5/s cap, retries); this module
never touches the network in tests, which inject a fake session serving fixtures.

Filer-agent changes rename exhibits (design/scout-cards.md section A); nothing here or in the parser
depends on a file name. The manifest records each document's exhibit TYPE from the index-headers page.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from . import edgar
from .edgar import FilingRef

PROSPECTUS_FORMS = ("424B5", "424B2", "424B3", "424B7")
TEN_D_FORMS = ("10-D", "10-D/A")


@dataclass(frozen=True)
class Trust:
    slug: str
    name: str
    cik: str  # issuing-entity CIK, 10 digits (design/scout-cards.md, Trust register)


TRUSTS: dict[str, Trust] = {
    "amex": Trust("amex", "American Express Credit Account Master Trust", "0001003509"),
    "comet": Trust("comet", "Capital One Multi-asset Execution Trust", "0001163321"),
    "chase": Trust("chase", "Chase Issuance Trust", "0001174821"),
    "citi": Trust("citi", "Citibank Credit Card Issuance Trust", "0001108348"),
    "synchrony": Trust("synchrony", "Synchrony Card Issuance Trust", "0001724789"),
    "bofa": Trust("bofa", "BA Credit Card Trust", "0001128250"),
}


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def list_10d(session, trust: Trust, since: str, cache_dir: Path | None = None) -> list[FilingRef]:
    """10-D and 10-D/A filings of the trust with filing_date >= since, newest first."""
    fl = edgar.all_filings(session, trust.cik, cache_dir, since=since)
    return [f for f in fl if f.form in TEN_D_FORMS and f.filing_date >= since]


def latest_prospectus(session, trust: Trust, cache_dir: Path | None = None) -> FilingRef | None:
    fl = edgar.all_filings(session, trust.cik, cache_dir, since="2015-01-01")
    for f in fl:
        if f.form in PROSPECTUS_FORMS:
            return f
    return None


def is_complete(dest: Path) -> bool:
    m = dest / "manifest.json"
    if not m.exists():
        return False
    try:
        man = json.loads(m.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    for f in man.get("files", []):
        p = dest / f["name"]
        if not p.exists() or p.stat().st_size != f["size"]:
            return False
    return bool(man.get("files"))


def fetch_filing(session, trust: Trust, filing: FilingRef, dest: Path, force: bool = False) -> dict:
    """Download every document of one filing into dest/ and write manifest.json. Returns the manifest."""
    dest = Path(dest)
    if not force and is_complete(dest):
        return json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
    dest.mkdir(parents=True, exist_ok=True)
    idx = edgar.filing_index(session, trust.cik, filing.accession, dest / "index.json")
    headers = edgar.index_headers(session, trust.cik, filing.accession, dest / f"{filing.accession}-index-headers.html")
    types = edgar.exhibit_types(headers)
    period = edgar.header_field(headers, "PERIOD") or ""
    period_iso = f"{period[:4]}-{period[4:6]}-{period[6:]}" if len(period) == 8 else filing.report_date
    files = []
    for it in idx["directory"]["item"]:
        name = it["name"]
        if not edgar.is_document(name, filing.accession):
            continue
        out = dest / name
        expected = int(it.get("size") or 0)
        if not (out.exists() and expected and out.stat().st_size == expected):
            out.write_bytes(edgar.get_bytes(session, edgar.folder_url(trust.cik, filing.accession) + name))
        files.append({"name": name, "type": types.get(name, ""), "size": out.stat().st_size, "sha256": sha256(out)})
    if not files:
        raise edgar.FetchError(f"{trust.slug} {filing.accession}: no documents in the filing index")
    manifest = {
        "slug": trust.slug, "trust": trust.name, "cik": trust.cik, "form": filing.form, "accession": filing.accession,
        "filing_date": filing.filing_date, "period": period_iso, "primary_document": filing.primary_document,
        "url": edgar.folder_url(trust.cik, filing.accession), "files": files,
        "fetched": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


def fetch_prospectus(session, trust: Trust, filing: FilingRef, dest: Path, force: bool = False) -> dict:
    """Download the prospectus primary document only (the 424B is one large file)."""
    dest = Path(dest)
    if not force and is_complete(dest):
        return json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / filing.primary_document
    out.write_bytes(edgar.get_bytes(session, edgar.folder_url(trust.cik, filing.accession) + filing.primary_document))
    manifest = {
        "slug": trust.slug, "trust": trust.name, "cik": trust.cik, "form": filing.form, "accession": filing.accession,
        "filing_date": filing.filing_date, "period": filing.report_date, "primary_document": filing.primary_document,
        "url": edgar.folder_url(trust.cik, filing.accession),
        "files": [{"name": out.name, "type": filing.form, "size": out.stat().st_size, "sha256": sha256(out)}],
        "fetched": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


def fetch_trust(session, trust: Trust, raw: Path, since: str = "2019-01-01", force: bool = False,
                prospectus: bool = True, limit: int | None = None) -> dict:
    """All 10-Ds since `since` plus the latest prospectus for one trust. Returns a summary dict."""
    base = Path(raw) / trust.slug
    base.mkdir(parents=True, exist_ok=True)
    filings = list_10d(session, trust, since, cache_dir=base)
    (base / "filings_10D.json").write_text(json.dumps([f.__dict__ for f in filings], indent=1), encoding="utf-8")
    log(f"{trust.slug}: {len(filings)} 10-D filings since {since}")
    done, skipped, errors = 0, 0, []
    for f in filings[:limit]:
        dest = base / f.accession
        try:
            if not force and is_complete(dest):
                skipped += 1
                continue
            fetch_filing(session, trust, f, dest, force=force)
            done += 1
        except Exception as e:  # noqa: BLE001 - one bad filing must not stop the run; it is reported
            errors.append({"accession": f.accession, "error": f"{type(e).__name__}: {e}"})
            log(f"{trust.slug} {f.accession}: {e}")
    summary = {"slug": trust.slug, "n_filings": len(filings), "fetched": done, "skipped": skipped, "errors": errors}
    if prospectus:
        p = latest_prospectus(session, trust, cache_dir=base)
        if p is None:
            summary["prospectus"] = None
        else:
            try:
                fetch_prospectus(session, trust, p, base / "prospectus" / p.accession, force=force)
                summary["prospectus"] = {"accession": p.accession, "filing_date": p.filing_date, "form": p.form}
            except Exception as e:  # noqa: BLE001
                summary["prospectus"] = {"accession": p.accession, "error": f"{type(e).__name__}: {e}"}
                log(f"{trust.slug} prospectus {p.accession}: {e}")
    return summary


def fetch_all(session, raw: Path, trusts: list[str] | None = None, since: str = "2019-01-01", force: bool = False,
              prospectus: bool = True, limit: int | None = None) -> list[dict]:
    out = []
    for slug in trusts or list(TRUSTS):
        if slug not in TRUSTS:
            raise KeyError(f"unknown trust {slug!r}; known: {sorted(TRUSTS)}")
        out.append(fetch_trust(session, TRUSTS[slug], raw, since=since, force=force, prospectus=prospectus, limit=limit))
    (Path(raw) / "fetch_summary.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out
