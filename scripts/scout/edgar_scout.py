"""EDGAR scouting run, meant for a GitHub Actions runner (this project's home ISP is blocked by the SEC edge).

Track A (cards): for each card master trust, find its EDGAR entities, list 10-D history, download the latest
10-D with every exhibit, and the latest 424B prospectus primary document.
Track B (autos): find which auto ABS issuers file ABS-EE, download the latest EX-102 loan-level XML for three
issuers across the credit spectrum plus the prior month for one, profile them, and test asset-number persistence.

Everything lands under OUT (default scout_out/), with manifest.json recording every URL, path, size and status.
Each step is isolated: a failure is recorded and the run continues.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import traceback
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from absrisk.http import make_session  # noqa: E402

OUT = Path(os.environ.get("SCOUT_OUT", "scout_out"))
SESSION = make_session()
MANIFEST: dict = {"started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "downloads": [], "errors": [], "notes": []}
HERE = Path(__file__).resolve().parent

CARD_TRUSTS = {
    "amex": "American Express Credit Account Master Trust",
    "comet": "Capital One Multi-asset Execution Trust",
    "chase": "Chase Issuance Trust",
    "citi": "Citibank Credit Card Issuance Trust",
    "discover": "Discover Card Execution Note Trust",
    "synchrony": "Synchrony Card Issuance Trust",
    "bofa": "BA Credit Card Trust",
}

AUTO_CANDIDATES = [
    "Santander Drive Auto Receivables Trust", "Drive Auto Receivables Trust", "Santander Consumer Auto Receivables Trust",
    "AmeriCredit Automobile Receivables Trust", "GM Financial Consumer Automobile Receivables Trust",
    "CarMax Auto Owner Trust", "Ally Auto Receivables Trust", "Capital One Prime Auto Receivables Trust",
    "Ford Credit Auto Owner Trust", "Toyota Auto Receivables", "Honda Auto Receivables Owner Trust",
    "Nissan Auto Receivables", "Hyundai Auto Receivables Trust", "World Omni Auto Receivables Trust",
    "Exeter Automobile Receivables Trust", "Fifth Third Auto Trust", "Harley-Davidson Motorcycle Trust",
    "Mercedes-Benz Auto Receivables Trust", "BMW Vehicle Owner Trust", "Volkswagen Auto Loan Enhanced Trust",
    "USAA Auto Owner Trust", "Carvana Auto Receivables Trust", "Westlake Automobile Receivables Trust",
    "DT Auto Owner Trust", "Flagship Credit Auto Trust", "Bank of America Auto Trust", "Chase Auto Owner Trust",
    "GLS Auto Receivables Issuer Trust", "CPS Auto Receivables Trust", "American Credit Acceptance Receivables Trust",
    "Credit Acceptance Auto Loan Trust", "Prestige Auto Receivables Trust", "United Auto Credit Securitization Trust",
    "First Investors Auto Owner Trust", "Foursight Capital Automobile Receivables Trust", "Lendbuzz Securitization Trust",
    "Tricolor Auto Securitization Trust", "Arivo Acceptance Auto Loan Receivables Trust",
    "Santander Retail Auto Lease Trust", "Exeter Select Auto Receivables Trust",
]
# Three across the spectrum, with fallbacks in order.
AUTO_PICKS = [
    ("subprime", ["Santander Drive Auto Receivables Trust", "Drive Auto Receivables Trust",
                  "Exeter Automobile Receivables Trust", "AmeriCredit Automobile Receivables Trust"]),
    ("mid", ["CarMax Auto Owner Trust", "AmeriCredit Automobile Receivables Trust",
             "World Omni Auto Receivables Trust", "Carvana Auto Receivables Trust"]),
    ("prime", ["Capital One Prime Auto Receivables Trust", "Toyota Auto Receivables",
               "Honda Auto Receivables Owner Trust", "Ally Auto Receivables Trust"]),
]


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def record(url, dest, status, size=None, note=""):
    MANIFEST["downloads"].append({"url": url, "path": str(dest), "status": status, "size": size, "note": note})


def get(url: str, dest: Path, stream: bool = False) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = SESSION.get(url, stream=stream)
    except Exception as e:  # noqa: BLE001
        record(url, dest, f"error {e}")
        log("GET", url, "->", e)
        return False
    if r.status_code != 200:
        body = r.content[:400] if not stream else b""
        record(url, dest, r.status_code, note=body.decode("utf-8", "replace")[:200])
        log("GET", url, "-> HTTP", r.status_code)
        return False
    if stream:
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    else:
        dest.write_bytes(r.content)
    size = dest.stat().st_size
    record(url, dest, 200, size)
    log("GET", url, "->", size, "bytes")
    return True


def get_json(url: str, dest: Path):
    if get(url, dest):
        return json.loads(dest.read_text(encoding="utf-8"))
    return None


def fts(query: str, forms: str, dest: Path, startdt="2023-01-01", enddt="2026-12-31", page=1):
    q = quote('"' + query + '"')
    url = (f"https://efts.sec.gov/LATEST/search-index?q={q}&forms={forms}"
           f"&dateRange=custom&startdt={startdt}&enddt={enddt}&page={page}")
    return get_json(url, dest)


def entities_from_fts(d) -> list[tuple[str, str, int]]:
    """[(cik10, display name, doc_count)] sorted by doc count."""
    out = []
    for b in (d or {}).get("aggregations", {}).get("entity_filter", {}).get("buckets", []):
        m = re.search(r"\(CIK (\d+)\)", b["key"])
        if m:
            out.append((m.group(1).zfill(10), b["key"], b["doc_count"]))
    return sorted(out, key=lambda x: -x[2])


def submissions(cik10: str, dest: Path):
    return get_json(f"https://data.sec.gov/submissions/CIK{cik10}.json", dest)


def filings(sub: dict) -> list[dict]:
    r = sub["filings"]["recent"]
    keys = ["form", "filingDate", "reportDate", "accessionNumber", "primaryDocument", "primaryDocDescription"]
    n = len(r["form"])
    return [{k: (r.get(k) or [""] * n)[i] for k in keys} for i in range(n)]


def filing_index(cik10: str, acc: str, dest: Path):
    acc_nd = acc.replace("-", "")
    return get_json(f"https://www.sec.gov/Archives/edgar/data/{int(cik10)}/{acc_nd}/index.json", dest)


def folder_url(cik10: str, acc: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik10)}/{acc.replace('-', '')}/"


def download_filing(cik10: str, acc: str, dest_dir: Path, name_filter=None, stream=False) -> list[Path]:
    idx = filing_index(cik10, acc, dest_dir / "index.json")
    got: list[Path] = []
    if not idx:
        return got
    for it in idx["directory"]["item"]:
        name = it["name"]
        if name.endswith("-index.htm") or name.endswith("-index.html") or name == "index.json":
            continue
        if name_filter and not name_filter(name):
            continue
        if get(folder_url(cik10, acc) + name, dest_dir / name, stream=stream):
            got.append(dest_dir / name)
    return got


# ---------------------------------------------------------------- Track A: cards

def scout_cards():
    summary = {}
    for slug, name in CARD_TRUSTS.items():
        try:
            summary[slug] = scout_one_trust(slug, name)
        except Exception:  # noqa: BLE001
            MANIFEST["errors"].append({"step": f"cards/{slug}", "trace": traceback.format_exc()})
            log("ERROR cards", slug, traceback.format_exc())
    (OUT / "cards").mkdir(parents=True, exist_ok=True)
    (OUT / "cards" / "summary.json").write_text(json.dumps(summary, indent=1, default=str))


def scout_one_trust(slug: str, name: str) -> dict:
    base = OUT / "cards" / slug
    d = fts(name, "10-D", base / "fts_10D.json", startdt="2025-01-01")
    ents = entities_from_fts(d)
    out: dict = {"query": name, "entities_10D": ents, "entities": {}}
    for cik10, disp, cnt in ents[:2]:
        sub = submissions(cik10, base / f"submissions_{cik10}.json")
        if not sub:
            continue
        fl = filings(sub)
        tend = [f for f in fl if f["form"] == "10-D"]
        pros = [f for f in fl if f["form"] in ("424B5", "424B2", "424B3")]
        ent: dict = {
            "name": sub.get("name"), "cik": cik10,
            "n_10D_recent_page": len(tend),
            "n_10D_since_2024": sum(1 for f in tend if f["filingDate"] >= "2024-01-01"),
            "latest_10D": tend[0] if tend else None, "earliest_10D_recent_page": tend[-1] if tend else None,
            "older_pages": sub["filings"].get("files", []),
            "prospectus_recent": pros[:5],
        }
        if tend:
            acc = tend[0]["accessionNumber"]
            docs = download_filing(cik10, acc, base / "10D" / acc)
            ent["latest_10D_files"] = [str(p.relative_to(OUT)) for p in docs]
        if pros:
            acc = pros[0]["accessionNumber"]
            pd = pros[0]["primaryDocument"]
            dest = base / "prospectus" / acc / pd
            if get(folder_url(cik10, acc) + pd, dest, stream=True):
                ent["prospectus_file"] = str(dest.relative_to(OUT))
        else:
            d2 = fts(name, "424B5,424B2", base / f"fts_424B_{cik10}.json", startdt="2015-01-01")
            hits = (d2 or {}).get("hits", {}).get("hits", [])
            hits = [h for h in hits if cik10 in h["_source"].get("ciks", [])]
            hits.sort(key=lambda h: h["_source"]["file_date"], reverse=True)
            if hits:
                h = hits[0]["_source"]
                acc = h["adsh"]
                fname = hits[0]["_id"].split(":", 1)[1]
                dest = base / "prospectus" / acc / fname
                if get(folder_url(cik10, acc) + fname, dest, stream=True):
                    ent["prospectus_file"] = str(dest.relative_to(OUT))
                    ent["prospectus_via_fts"] = {"file_date": h["file_date"], "form": h["form"]}
        out["entities"][cik10] = ent
    return out


# ---------------------------------------------------------------- Track B: autos

def scout_autos():
    base = OUT / "autos"
    base.mkdir(parents=True, exist_ok=True)
    issuers = {}
    for name in AUTO_CANDIDATES:
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        try:
            d = fts(name, "ABS-EE", base / "_search" / f"{slug}.json", startdt="2025-01-01")
            hits = (d or {}).get("hits", {}).get("hits", [])
            issuers[name] = {
                "total": (d or {}).get("hits", {}).get("total", {}).get("value"),
                "entities": entities_from_fts(d)[:6],
                "latest_hits": [{"file_date": h["_source"]["file_date"], "period": h["_source"].get("period_ending"),
                                 "ciks": h["_source"]["ciks"], "names": h["_source"]["display_names"],
                                 "adsh": h["_source"]["adsh"]}
                                for h in sorted(hits, key=lambda h: h["_source"]["file_date"], reverse=True)[:3]],
            }
        except Exception:  # noqa: BLE001
            MANIFEST["errors"].append({"step": f"autos/search/{name}", "trace": traceback.format_exc()})
    (base / "issuers.json").write_text(json.dumps(issuers, indent=1))

    picks = {}
    first_pair_done = False
    for segment, names in AUTO_PICKS:
        for name in names:
            info = issuers.get(name) or {}
            if not info.get("latest_hits"):
                continue
            try:
                res = scout_one_auto(segment, name, info, base, want_prior=not first_pair_done)
                if res:
                    picks[segment] = res
                    first_pair_done = first_pair_done or bool(res.get("prior"))
                    break
            except Exception:  # noqa: BLE001
                MANIFEST["errors"].append({"step": f"autos/pick/{name}", "trace": traceback.format_exc()})
                log("ERROR autos", name, traceback.format_exc())
    (base / "picks.json").write_text(json.dumps(picks, indent=1, default=str))


def is_ex102(name: str) -> bool:
    """Fallback name test only; prefer exhibit_files_by_type (CarMax names its EX-102 'cart20262.xml')."""
    n = name.lower()
    return n.endswith(".xml") and ("102" in n) and not n.endswith("_htm.xml")


def exhibit_files_by_type(cik10: str, acc: str, dest_dir: Path) -> dict[str, list[str]]:
    """Map exhibit TYPE (EX-102, EX-103, ...) to file names, from the filing's index-headers page."""
    acc_nd = acc.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{int(cik10)}/{acc_nd}/{acc}-index-headers.html"
    dest = dest_dir / f"{acc}-index-headers.html"
    if not get(url, dest):
        return {}
    text = dest.read_text(encoding="utf-8", errors="replace")
    out: dict[str, list[str]] = {}
    for m in re.finditer(r"<TYPE>([^<\s]+).*?<FILENAME>([^<\s]+)", text, re.S):
        out.setdefault(m.group(1).upper(), []).append(m.group(2))
    return out


def download_ex102(cik10: str, acc: str, dest_dir: Path) -> list[Path]:
    """Download the EX-102 asset-level XML of one ABS-EE filing, identified by exhibit type."""
    types = exhibit_files_by_type(cik10, acc, dest_dir)
    names = types.get("EX-102", [])
    if not names:
        return download_filing(cik10, acc, dest_dir, name_filter=is_ex102, stream=True)
    got = []
    for name in names:
        if get(folder_url(cik10, acc) + name, dest_dir / name, stream=True):
            got.append(dest_dir / name)
    return got


def second_pass(spec_path: Path):
    """Fetch an explicit list of ABS-EE filings and profile them; compare listed pairs.

    spec: {"fetch": [{"slug": ..., "cik": ..., "accession": ..., "note": ...}],
           "pairs": [{"slug": ..., "earlier": accession, "later": accession}]}
    """
    spec = json.loads(spec_path.read_text())
    base = OUT / "autos"
    results: dict = {"fetched": [], "pairs": []}
    paths: dict[str, Path] = {}
    for item in spec.get("fetch", []):
        cik10, acc, slug = str(item["cik"]).zfill(10), item["accession"], item["slug"]
        try:
            files_ = download_ex102(cik10, acc, base / slug / acc)
            if files_:
                prof = base / slug / acc / "profile.json"
                run([sys.executable, str(HERE / "analyze_ex102.py"), str(files_[0]), str(prof)])
                paths[acc] = files_[0]
                results["fetched"].append({**item, "file": str(files_[0].relative_to(OUT)), "profile": str(prof.relative_to(OUT))})
            else:
                results["fetched"].append({**item, "file": None})
        except Exception:  # noqa: BLE001
            MANIFEST["errors"].append({"step": f"second_pass/{slug}/{acc}", "trace": traceback.format_exc()})
    for pair in spec.get("pairs", []):
        a, b = paths.get(pair["earlier"]), paths.get(pair["later"])
        if a and b:
            cmp = base / pair["slug"] / f"persistence_{pair['earlier']}_{pair['later']}.json"
            run([sys.executable, str(HERE / "compare_assets.py"), str(a), str(b), str(cmp)])
            results["pairs"].append({**pair, "compare": str(cmp.relative_to(OUT))})
        else:
            results["pairs"].append({**pair, "compare": None})
    (base / "second_pass_results.json").write_text(json.dumps(results, indent=1, default=str))


def scout_one_auto(segment: str, name: str, info: dict, base: Path, want_prior: bool) -> dict | None:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    latest = info["latest_hits"][0]
    cik10 = latest["ciks"][0].zfill(10)
    sub = submissions(cik10, base / slug / f"submissions_{cik10}.json")
    if not sub:
        return None
    absee = [f for f in filings(sub) if f["form"] == "ABS-EE"]
    if not absee:
        return None
    res: dict = {"segment": segment, "issuer_query": name, "trust": sub.get("name"), "cik": cik10,
                 "n_ABSEE_recent_page": len(absee), "absee_range": [absee[-1]["filingDate"], absee[0]["filingDate"]],
                 "older_pages": sub["filings"].get("files", [])}
    acc = absee[0]["accessionNumber"]
    files_ = download_ex102(cik10, acc, base / slug / acc)
    if not files_:
        idx_path = base / slug / acc / "index.json"
        idx = json.loads(idx_path.read_text()) if idx_path.exists() else None
        res["latest_index_items"] = [it["name"] for it in (idx or {}).get("directory", {}).get("item", [])]
        return res
    res["latest"] = {"accession": acc, "filingDate": absee[0]["filingDate"], "file": str(files_[0].relative_to(OUT))}
    prof = base / slug / acc / "profile.json"
    run([sys.executable, str(HERE / "analyze_ex102.py"), str(files_[0]), str(prof)])
    res["latest"]["profile"] = str(prof.relative_to(OUT))
    if want_prior and len(absee) > 1:
        acc2 = absee[1]["accessionNumber"]
        files2 = download_ex102(cik10, acc2, base / slug / acc2)
        if files2:
            res["prior"] = {"accession": acc2, "filingDate": absee[1]["filingDate"], "file": str(files2[0].relative_to(OUT))}
            cmp = base / slug / "asset_persistence.json"
            run([sys.executable, str(HERE / "compare_assets.py"), str(files2[0]), str(files_[0]), str(cmp)])
            res["prior"]["compare"] = str(cmp.relative_to(OUT))
    return res


def run(cmd):
    log("RUN", " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    log(r.stderr[-2000:])
    if r.returncode != 0:
        MANIFEST["errors"].append({"step": " ".join(cmd), "stderr": r.stderr[-4000:]})


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    probe = OUT / "probe_submissions.json"
    ok = get("https://data.sec.gov/submissions/CIK0001163321.json", probe)
    MANIFEST["notes"].append(f"probe data.sec.gov ok={ok}")
    mode = os.environ.get("SCOUT_MODE", "full")
    if not ok:
        MANIFEST["notes"].append("EDGAR blocked from this runner too; aborting after probe")
    elif mode == "second_pass":
        second_pass(HERE / "second_pass.json")
    else:
        scout_cards()
        scout_autos()
    MANIFEST["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (OUT / "manifest.json").write_text(json.dumps(MANIFEST, indent=1, default=str))
    log("done; errors:", len(MANIFEST["errors"]))


if __name__ == "__main__":
    main()
