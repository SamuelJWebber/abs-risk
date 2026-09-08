"""Build the canned EDGAR responses under tests/fixtures/autos/edgar/ for tests/test_autos_fetch.py.

Run from the repo root:  python -m uv run python tests/fixtures/autos/tools/make_edgar_fixtures.py

Sources (all on disk from the scouting runs, design/scout-autos.md path shorthands R1, R2, R3):
- Santander depositor submissions JSON (R1) trimmed to the sdart261 / sdart251 ABS-EE rows plus two 10-D rows;
  its older page is hand-crafted (three sdart251 rows: lp/sp offering pool and the first post-closing filing)
  because the real older pages were never downloaded.
- CarMax 2026-2 trust submissions JSON (R1) trimmed to its ABS-EE rows.
- Honda depositor page: hand-crafted (an ABS-EE and its ABS-EE/A for one period, plus a second deal's rows).
- Exeter 2025-1: the R3 full-text search response for the Exeter shelf (entity list) and a hand-crafted trust
  submissions page.
- index-headers pages: the real one for 0001193125-26-303622 (R2), the rest from the SGML template it shows.
- EX-102 bodies: the parse fixtures under tests/fixtures/autos/<slug>/ (content is irrelevant to the fetcher;
  index.json sizes are computed from them so the idempotency check is exercised).

routes.json maps each URL (or "fts:<phrase>" for full-text searches) to a path relative to tests/fixtures/autos.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
FIX = ROOT / "tests/fixtures/autos"
EDGAR = FIX / "edgar"
R1 = ROOT / "data/raw/scout/edgar/autos"
R2 = ROOT / "data/raw/scout/edgar2/scout-edgar-second_pass-34192024913/autos"
R3 = ROOT / "data/raw/scout/edgar3/scout-edgar-second_pass-34192371366/autos"

ROUTES: dict[str, str] = {}
FIELDS = ["accessionNumber", "filingDate", "reportDate", "acceptanceDateTime", "act", "form", "fileNumber",
          "filmNumber", "items", "core_type", "size", "isXBRL", "isInlineXBRL", "isXBRLNumeric", "primaryDocument",
          "primaryDocDescription"]


def rel(p: Path) -> str:
    return p.relative_to(FIX).as_posix()


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1), encoding="utf-8")


def rows_of(sub: dict) -> list[dict]:
    r = sub["filings"]["recent"]
    n = len(r["accessionNumber"])
    return [{k: (r.get(k) or [None] * n)[i] for k in FIELDS} for i in range(n)]


def columns(rows: list[dict]) -> dict:
    return {k: [row.get(k) for row in rows] for k in FIELDS}


def row(acc, filing_date, period, form, doc, size, desc=None) -> dict:
    return {"accessionNumber": acc, "filingDate": filing_date, "reportDate": period, "acceptanceDateTime": "",
            "act": "34", "form": form, "fileNumber": "", "filmNumber": "", "items": "", "core_type": form,
            "size": size, "isXBRL": 0, "isInlineXBRL": 0, "isXBRLNumeric": 0, "primaryDocument": doc,
            "primaryDocDescription": desc or form}


HEADER_TEMPLATE = """<HTML><HEAD><TITLE>SEC EDGAR Submission {acc}</TITLE>
<!--
<SEC-HEADER>{acc}.hdr.sgml : {fdate}
<ACCESSION-NUMBER>{acc}
<TYPE>{form}
<PUBLIC-DOCUMENT-COUNT>3
<PERIOD>{period}
<FILING-DATE>{fdate}
<ABS-ASSET-CLASS>Auto loans
</SEC-HEADER>
-->
</HEAD><BODY>
<PRE>&lt;SEC-DOCUMENT&gt;{acc}-index.html : {fdate}
ACCESSION NUMBER:\t\t{acc}
CONFORMED SUBMISSION TYPE:\t{form}
CONFORMED PERIOD OF REPORT:\t{period}
&lt;DOCUMENT&gt;
&lt;TYPE&gt;{form}
&lt;SEQUENCE&gt;1
&lt;FILENAME&gt;{primary}
&lt;DESCRIPTION&gt;{form}
&lt;TEXT&gt;
<a href="{primary}">Document 1 - file: {primary}</a><br>
&lt;/DOCUMENT&gt;
{ex102_block}&lt;DOCUMENT&gt;
&lt;TYPE&gt;EX-103
&lt;SEQUENCE&gt;3
&lt;FILENAME&gt;{ex103}
&lt;DESCRIPTION&gt;EX-103
&lt;TEXT&gt;
<a href="{ex103}">Document 3 - RAW XML: {ex103}</a><br>
&lt;/DOCUMENT&gt;
&lt;/SEC-DOCUMENT&gt;</PRE></BODY></HTML>
"""
EX102_BLOCK = """&lt;DOCUMENT&gt;
&lt;TYPE&gt;EX-102
&lt;SEQUENCE&gt;2
&lt;FILENAME&gt;{ex102}
&lt;DESCRIPTION&gt;EX-102
&lt;TEXT&gt;
<a href="{ex102}">Document 2 - RAW XML: {ex102}</a><br>
&lt;/DOCUMENT&gt;
"""


def archive(cik10: str, acc: str, form: str, period: str, fdate: str, primary: str, ex102: str, body: Path,
            ex103: str = "exhibit103.xml", headers: str = "template") -> None:
    """index.json + index-headers.html for one filing; the EX-102 route points at `body`.

    headers: "template" (with an EX-102 TYPE line), "untyped" (no EX-102 TYPE line: forces the size fallback),
    "real" (copy the R2 page), or "missing" (no route at all: index-headers 404s, fallback to index.json).
    """
    folder = f"https://www.sec.gov/Archives/edgar/data/{int(cik10)}/{acc.replace('-', '')}/"
    d = EDGAR / "archives" / acc
    d.mkdir(parents=True, exist_ok=True)
    size = body.stat().st_size
    items = [
        {"last-modified": f"{fdate[:4]}-{fdate[4:6]}-{fdate[6:]} 11:00:00", "name": f"{acc}-index-headers.html",
         "type": "text.gif", "size": ""},
        {"last-modified": "", "name": f"{acc}-index.html", "type": "text.gif", "size": ""},
        {"last-modified": "", "name": primary, "type": "text.gif", "size": "15000"},
        {"last-modified": "", "name": ex102, "type": "text.gif", "size": str(size)},
        {"last-modified": "", "name": ex103, "type": "text.gif", "size": "17054"},
    ]
    write_json(d / "index.json", {"directory": {"item": items,
                                                "name": f"/Archives/edgar/data/{int(cik10)}/{acc.replace('-', '')}",
                                                "parent-dir": f"/Archives/edgar/data/{int(cik10)}"}})
    ROUTES[folder + "index.json"] = rel(d / "index.json")
    if headers == "real":
        src = R2 / "sdart-2026-1" / acc / f"{acc}-index-headers.html"
        (d / f"{acc}-index-headers.html").write_bytes(src.read_bytes())
    elif headers in ("template", "untyped"):
        block = EX102_BLOCK.format(ex102=ex102) if headers == "template" else ""
        (d / f"{acc}-index-headers.html").write_text(
            HEADER_TEMPLATE.format(acc=acc, form=form, period=period, fdate=fdate, primary=primary,
                                   ex102_block=block, ex103=ex103), encoding="utf-8")
    if headers != "missing":
        ROUTES[folder + f"{acc}-index-headers.html"] = rel(d / f"{acc}-index-headers.html")
    ROUTES[folder + ex102] = rel(body)


def main() -> None:
    sub_dir = EDGAR / "submissions"
    efts_dir = EDGAR / "efts"
    sd_jun, sd_jul = FIX / "sdart-2026-1/2026-06.xml", FIX / "sdart-2026-1/2026-07.xml"
    cm_jun, cm_jul = FIX / "carmax-2026-2/2026-06.xml", FIX / "carmax-2026-2/2026-07.xml"
    cp_jun, cp_jul = FIX / "copar-2025-1/2026-06.xml", FIX / "copar-2025-1/2026-07.xml"
    ex_jun = FIX / "exeter-2025-5/2026-06.xml"
    ty_jul = FIX / "toyota-2025-a/2026-07.xml"

    # ---- Santander depositor 0001383094: real recent page trimmed; hand-crafted older page
    real = json.loads((R1 / "santander-drive-auto-receivables-trust/submissions_0001383094.json")
                      .read_text(encoding="utf-8"))
    keep_acc = {"0001193125-26-045549", "0001193125-26-045529", "0001193125-26-106847", "0001193125-26-303622",
                "0001193125-26-352879",  # sdart261: lp, sp, first post-closing, June, July
                "0001193125-26-303594", "0001193125-26-352849",  # sdart251: June, July
                "0001193125-26-352870", "0001193125-26-352868"}  # two 10-D rows (form filter)
    rows = [r for r in rows_of(real) if r["accessionNumber"] in keep_acc]
    assert len(rows) == len(keep_acc), [r["accessionNumber"] for r in rows]
    older_name = "CIK0001383094-submissions-001.json"
    sub = {k: real[k] for k in ("cik", "entityType", "sic", "sicDescription", "name", "fiscalYearEnd",
                                "stateOfIncorporation")}
    sub["filings"] = {"recent": columns(rows),
                      "files": [{"name": older_name, "filingCount": 4, "filingFrom": "2022-09-15",
                                 "filingTo": "2025-04-13"}]}
    write_json(sub_dir / "CIK0001383094.json", sub)
    ROUTES["https://data.sec.gov/submissions/CIK0001383094.json"] = rel(sub_dir / "CIK0001383094.json")
    older_rows = [  # hand-crafted: accession numbers and sizes are invented, the naming follows the real shelf
        row("0001193125-25-030002", "2025-02-14", "2025-01-31", "ABS-EE", "sdart251absee_0212-1401lp.htm", 300000000),
        row("0001193125-25-030001", "2025-02-14", "2025-01-31", "ABS-EE", "sdart251absee_0212-1358sp.htm", 240000000),
        row("0001193125-25-060001", "2025-03-17", "2025-02-28", "ABS-EE", "sdart251absee_0311-1600.htm", 355000000),
        row("0001193125-25-060002", "2025-03-17", "2025-02-28", "10-D", "d123456d10d.htm", 200000),
    ]
    write_json(sub_dir / older_name, columns(older_rows))  # older pages are flat column arrays
    ROUTES["https://data.sec.gov/submissions/" + older_name] = rel(sub_dir / older_name)

    dep = "0001383094"
    archive(dep, "0001193125-26-045549", "ABS-EE", "20260131", "20260211", "sdart261absee_0210-1933lp.htm",
            "sdart261ex102_0210-1933lp.xml", sd_jun)
    archive(dep, "0001193125-26-045529", "ABS-EE", "20260131", "20260211", "sdart261absee_0210-1820sp.htm",
            "sdart261ex102_0210-1820sp.xml", sd_jul)  # smaller body
    archive(dep, "0001193125-26-106847", "ABS-EE", "20260228", "20260316", "sdart261absee_0311-1617.htm",
            "sdart261ex102.xml", sd_jun)
    archive(dep, "0001193125-26-303622", "ABS-EE", "20260630", "20260715", "sdart261absee_0708-2103.htm",
            "sdart261ex102.xml", sd_jun, ex103="sdart261ex103.xml", headers="real")
    archive(dep, "0001193125-26-352879", "ABS-EE", "20260731", "20260817", "sdart261absee_0810-1513.htm",
            "sdart261ex102.xml", sd_jul, headers="missing")
    archive(dep, "0001193125-26-303594", "ABS-EE", "20260630", "20260715", "sdart251absee_0708-2052.htm",
            "sdart251ex102.xml", cp_jun)
    archive(dep, "0001193125-26-352849", "ABS-EE", "20260731", "20260817", "sdart251_absee_0810-1405.htm",
            "sdart251ex102.xml", cp_jul)
    archive(dep, "0001193125-25-030002", "ABS-EE", "20250131", "20250214", "sdart251absee_0212-1401lp.htm",
            "sdart251ex102_0212-1401lp.xml", cp_jun)
    archive(dep, "0001193125-25-030001", "ABS-EE", "20250131", "20250214", "sdart251absee_0212-1358sp.htm",
            "sdart251ex102_0212-1358sp.xml", ex_jun)  # smaller
    archive(dep, "0001193125-25-060001", "ABS-EE", "20250228", "20250317", "sdart251absee_0311-1600.htm",
            "sdart251ex102.xml", cp_jul)

    # ---- CarMax 2026-2 trust 0002117307 (self-filed): real recent page trimmed to ABS-EE rows plus one 10-D
    real = json.loads((R1 / "carmax-auto-owner-trust/submissions_0002117307.json").read_text(encoding="utf-8"))
    rows = [r for r in rows_of(real) if r["form"] in ("ABS-EE", "10-D")][:6]
    sub = {k: real.get(k) for k in ("cik", "name")}
    sub["filings"] = {"recent": columns(rows), "files": []}
    write_json(sub_dir / "CIK0002117307.json", sub)
    ROUTES["https://data.sec.gov/submissions/CIK0002117307.json"] = rel(sub_dir / "CIK0002117307.json")
    bodies = [cm_jun, cm_jul, cm_jun, cm_jul, cm_jun, cm_jul]
    for i, r in enumerate([r for r in rows if r["form"] == "ABS-EE"]):
        # CarMax names its EX-102 `cart20262.xml` (no "102" in the name): the untyped page forces the size fallback
        archive("0002117307", r["accessionNumber"], "ABS-EE", r["reportDate"].replace("-", ""),
                r["filingDate"].replace("-", ""), r["primaryDocument"], "cart20262.xml", bodies[i],
                ex103="exhibit103november2021.xml", headers="untyped")

    # ---- Honda depositor 0000890975: hand-crafted (amendment for one period; a second deal for the prefix filter)
    rows = [
        row("0001193125-26-374999", "2026-08-31", "2026-07-31", "ABS-EE/A", "harot251abseea_0828-1757.htm", 180000000),
        row("0001193125-26-340001", "2026-08-17", "2026-07-31", "ABS-EE", "harot251absee_0812-1500.htm", 180000000),
        row("0001193125-26-375001", "2026-08-31", "2026-07-31", "ABS-EE/A", "harot252abseea_0828-1757.htm", 150000000),
        row("0001193125-26-300001", "2026-07-15", "2026-06-30", "ABS-EE", "harot251absee_0710-1500.htm", 181000000),
        row("0001193125-26-300002", "2026-07-15", "2026-06-30", "ABS-EE", "harot252absee_0710-1500.htm", 151000000),
    ]
    write_json(sub_dir / "CIK0000890975.json", {"cik": "0000890975", "name": "AMERICAN HONDA RECEIVABLES LLC",
                                                "filings": {"recent": columns(rows), "files": []}})
    ROUTES["https://data.sec.gov/submissions/CIK0000890975.json"] = rel(sub_dir / "CIK0000890975.json")
    archive("0000890975", "0001193125-26-374999", "ABS-EE/A", "20260731", "20260831",
            "harot251abseea_0828-1757.htm", "harot251ex102a.xml", ty_jul)
    archive("0000890975", "0001193125-26-340001", "ABS-EE", "20260731", "20260817",
            "harot251absee_0812-1500.htm", "harot251ex102.xml", ty_jul)
    archive("0000890975", "0001193125-26-300001", "ABS-EE", "20260630", "20260715",
            "harot251absee_0710-1500.htm", "harot251ex102.xml", ex_jun)
    # full-text search for the Honda trust name: trimmed R3 response (the 2025-1 hit and the entity list)
    real = json.loads((R3 / "_search/honda-auto-receivables.json").read_text(encoding="utf-8"))
    hits = [h for h in real["hits"]["hits"] if "0002052479" in h["_source"]["ciks"]]
    assert hits, "expected a Honda 2025-1 hit in the R3 search"
    write_json(efts_dir / "honda-2025-1.json", {"hits": {"total": {"value": len(hits)}, "hits": hits},
                                                "aggregations": real["aggregations"]})
    ROUTES["fts:Honda Auto Receivables 2025-1 Owner Trust"] = rel(efts_dir / "honda-2025-1.json")

    # ---- Exeter 2025-1: R3 search response (entity list carries the trust CIK) + hand-crafted trust page
    real = json.loads((R3 / "_search/exeter-automobile-receivables-trust.json").read_text(encoding="utf-8"))
    write_json(efts_dir / "exeter-2025-1.json", {"hits": {"total": real["hits"]["total"],
                                                          "hits": real["hits"]["hits"][:3]},
                                                 "aggregations": real["aggregations"]})
    ROUTES["fts:Exeter Automobile Receivables Trust 2025-1"] = rel(efts_dir / "exeter-2025-1.json")
    rows = [
        row("0000929638-26-003310", "2026-08-31", "2026-07-31", "ABS-EE", "eart2025-1_absee.htm", 90000000),
        row("0000929638-26-002760", "2026-07-30", "2026-06-30", "ABS-EE", "eart2025-1_absee.htm", 91000000),
        row("0000929638-26-002830", "2026-07-30", "2026-06-30", "10-D", "eart2025-1_10d.htm", 400000),
    ]
    write_json(sub_dir / "CIK0002049379.json", {"cik": "0002049379",
                                                "name": "Exeter Automobile Receivables Trust 2025-1",
                                                "filings": {"recent": columns(rows), "files": []}})
    ROUTES["https://data.sec.gov/submissions/CIK0002049379.json"] = rel(sub_dir / "CIK0002049379.json")
    archive("0002049379", "0000929638-26-003310", "ABS-EE", "20260731", "20260831", "eart2025-1_absee.htm",
            "eart2025-1_exhibit102.xml", ex_jun, ex103="eart2025-1_exhibit103.xml")
    archive("0002049379", "0000929638-26-002760", "ABS-EE", "20260630", "20260730", "eart2025-1_absee.htm",
            "eart2025-1_exhibit102.xml", ex_jun, ex103="eart2025-1_exhibit103.xml")

    write_json(EDGAR / "routes.json", dict(sorted(ROUTES.items())))
    print(f"{len(ROUTES)} routes")


if __name__ == "__main__":
    main()
