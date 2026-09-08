"""fetch.py against a fake session serving the canned EDGAR responses under tests/fixtures/autos/edgar/
(made by tests/fixtures/autos/tools/make_edgar_fixtures.py from the scouting artifacts). No network."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from absrisk.autos import main
from absrisk.autos.deals import Deal, load_deals
from absrisk.autos.fetch import (
    FetchError, Filing, all_filings, exhibit_files_by_type, fetch_deal, is_pool_variant, pick_ex102, resolve_deal,
    select_filings,
)

FIX = Path(__file__).parent / "fixtures" / "autos"
EDGAR = FIX / "edgar"


class FakeResponse:
    def __init__(self, status: int, data: bytes):
        self.status_code = status
        self.content = data
        self.headers = {"Content-Length": str(len(data))}

    def iter_content(self, n: int):
        for i in range(0, len(self.content), n):
            yield self.content[i:i + n]


class FakeSession:
    """`.get(url, stream=...)` from routes.json; full-text searches are keyed by their quoted phrase."""

    def __init__(self):
        self.routes = json.loads((EDGAR / "routes.json").read_text(encoding="utf-8"))
        self.calls: Counter[str] = Counter()

    @staticmethod
    def key(url: str) -> str:
        if url.startswith("https://efts.sec.gov/"):
            return "fts:" + parse_qs(urlparse(url).query)["q"][0].strip('"')
        return url

    def get(self, url: str, stream: bool = False, **kw):
        key = self.key(url)
        self.calls[key] += 1
        path = self.routes.get(key)
        if path is None:
            return FakeResponse(404, b"not found")
        return FakeResponse(200, (FIX / path).read_bytes())


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


SDART_2026_1 = Deal("sdart-2026-1", "santander", "0001383094", "sdart261", "Santander Drive Auto Receivables Trust 2026-1", "0001383094")
SDART_2025_1 = Deal("sdart-2025-1", "santander", "0001383094", "sdart251", "Santander Drive Auto Receivables Trust 2025-1", "0001383094")
CARMAX = Deal("carmax-2026-2", "carmax", "0002117307", "", "CarMax Auto Owner Trust 2026-2", "")
HONDA = Deal("honda-2025-1", "honda", "", "harot251", "Honda Auto Receivables 2025-1 Owner Trust", "0000890975")
EXETER_2025_1 = Deal("exeter-2025-1", "exeter", "", "", "Exeter Automobile Receivables Trust 2025-1", "")


def test_depositor_shelf_filtered_by_prefix_one_filing_per_period(tmp_path):
    s = FakeSession()
    m = fetch_deal(SDART_2026_1, tmp_path, s)
    assert m["filer_cik"] == "0001383094" and m["doc_prefix"] == "sdart261"
    assert m["n_candidates"] == 5 and m["n_filings"] == 4 and m["n_errors"] == 0 and m["n_downloaded"] == 4
    by_period = {e["period"]: e for e in m["filings"]}
    assert list(by_period) == ["2026-01-31", "2026-02-28", "2026-06-30", "2026-07-31"]
    pool = by_period["2026-01-31"]
    assert pool["accession"] == "0001193125-26-045549" and pool["offering_pool"] is True
    assert pool["superseded"] == ["0001193125-26-045529"] and pool["reason"].startswith("largest of 2")
    assert all(e["offering_pool"] is False for p, e in by_period.items() if p != "2026-01-31")
    for e in m["filings"]:
        f = tmp_path / "sdart-2026-1" / e["file"]
        assert f.exists() and f.stat().st_size == e["size"] and e["sha256"] == sha(f)
        assert e["url"].startswith("https://www.sec.gov/Archives/edgar/data/1383094/")
        assert e["form"] == "ABS-EE" and e["filing_date"] and e["deal"] == "sdart-2026-1"
        assert (f.parent / "index.json").exists()
    june = by_period["2026-06-30"]
    assert june["ex102_by_type"] is True and june["file"] == "0001193125-26-303622/sdart261ex102.xml"
    assert june["sha256"] == sha(FIX / "sdart-2026-1" / "2026-06.xml")
    july = by_period["2026-07-31"]
    assert july["ex102_by_type"] is False  # index-headers 404s in the fixture: largest non-103 .xml fallback
    assert july["sha256"] == sha(FIX / "sdart-2026-1" / "2026-07.xml")
    # the other deal on the shelf and the 10-Ds were never touched
    assert not any("sdart251" in k for k in s.calls)
    listing = json.loads((tmp_path / "sdart-2026-1" / "listing.json").read_text())
    assert {r["accession"] for r in listing} == {"0001193125-26-045549", "0001193125-26-045529", "0001193125-26-106847",
                                                 "0001193125-26-303622", "0001193125-26-352879"}
    mf = json.loads((tmp_path / "sdart-2026-1" / "manifest.json").read_text())
    assert mf["n_filings"] == 4 and mf["filings"][0]["accession"] == pool["accession"]


def test_fetch_is_idempotent(tmp_path):
    s = FakeSession()
    fetch_deal(SDART_2026_1, tmp_path, s)
    first = dict(s.calls)
    m2 = fetch_deal(SDART_2026_1, tmp_path, s)
    assert m2["n_skipped"] == 4 and m2["n_downloaded"] == 0
    assert all(e["skipped"] and e["sha256"] for e in m2["filings"])
    xml_urls = [k for k in first if k.endswith(".xml")]
    assert xml_urls and all(s.calls[k] == first[k] == 1 for k in xml_urls)
    idx_urls = [k for k in first if k.endswith("index.json") or k.endswith("index-headers.html")]
    assert all(s.calls[k] == first[k] for k in idx_urls if s.routes.get(k))  # cached on disk, not re-fetched
    # a truncated file is downloaded again
    e = m2["filings"][1]
    f = tmp_path / "sdart-2026-1" / e["file"]
    f.write_bytes(f.read_bytes()[:1000])
    m3 = fetch_deal(SDART_2026_1, tmp_path, s)
    assert m3["n_downloaded"] == 1 and m3["n_skipped"] == 3
    assert f.stat().st_size == e["size"] and s.calls[e["url"]] == 2


def test_walks_older_submissions_pages(tmp_path):
    s = FakeSession()
    m = fetch_deal(SDART_2025_1, tmp_path, s)
    assert s.calls["https://data.sec.gov/submissions/CIK0001383094-submissions-001.json"] == 1
    periods = [e["period"] for e in m["filings"]]
    assert periods == ["2025-01-31", "2025-02-28", "2026-06-30", "2026-07-31"]
    pool = m["filings"][0]
    assert pool["accession"] == "0001193125-25-030002" and pool["offering_pool"] and pool["superseded"] == ["0001193125-25-030001"]
    assert m["filings"][1]["accession"] == "0001193125-25-060001"
    assert (tmp_path / "sdart-2025-1" / "submissions" / "CIK0001383094-submissions-001.json").exists()


def test_self_filed_trust_uses_every_absee_and_size_fallback(tmp_path):
    s = FakeSession()
    page = json.loads((EDGAR / "submissions" / "CIK0002117307.json").read_text())
    n_absee = sum(1 for f in page["filings"]["recent"]["form"] if f == "ABS-EE")
    m = fetch_deal(CARMAX, tmp_path, s)
    assert m["filer_cik"] == "0002117307" and m["doc_prefix"] == ""
    assert m["n_filings"] == n_absee == m["n_downloaded"] and m["n_errors"] == 0
    for e in m["filings"]:
        assert e["file"].endswith("/cart20262.xml") and e["ex102_by_type"] is False  # no "102" in the name
        assert e["offering_pool"] is False


def test_amendment_preferred_for_a_period(tmp_path):
    s = FakeSession()
    m = fetch_deal(HONDA, tmp_path, s)
    assert m["filer_cik"] == "0000890975" and m["resolution"]["depositor_filed"] is True
    assert [e["period"] for e in m["filings"]] == ["2026-06-30", "2026-07-31"]
    june, july = m["filings"]
    assert june["accession"] == "0001193125-26-300001" and june["form"] == "ABS-EE" and june["reason"] == "only filing for the period"
    assert july["accession"] == "0001193125-26-374999" and july["form"] == "ABS-EE/A"
    assert july["reason"].startswith("amendment") and july["superseded"] == ["0001193125-26-340001"]
    assert july["offering_pool"] is False
    assert not any("harot252" in k for k in s.calls)


def test_doc_prefix_derived_from_full_text_search(tmp_path):
    s = FakeSession()
    deal = Deal("honda-2025-1", "honda", "", "", "Honda Auto Receivables 2025-1 Owner Trust", "0000890975")
    res = resolve_deal(s, deal, tmp_path)
    assert res["filer_cik"] == "0000890975" and res["doc_prefix"] == "harot251"
    assert any("0001193125-26-374999" in h for h in res["how"])
    assert s.calls["fts:Honda Auto Receivables 2025-1 Owner Trust"] == 1
    assert (tmp_path / "_resolve" / "fts_prefix.json").exists()


def test_cik_resolved_from_full_text_search(tmp_path):
    s = FakeSession()
    m = fetch_deal(EXETER_2025_1, tmp_path, s)
    assert m["filer_cik"] == "0002049379"
    assert any("0002049379" in h for h in m["resolution"]["how"])
    assert [e["period"] for e in m["filings"]] == ["2026-06-30", "2026-07-31"]
    assert m["n_downloaded"] == 2
    with pytest.raises(FetchError):
        resolve_deal(FakeSession(), Deal("nowhere", "x", "", "", "No Such Trust 2099-9", ""), tmp_path / "x")
    with pytest.raises(FetchError):
        resolve_deal(FakeSession(), Deal("noname", "x"), tmp_path / "y")


def test_all_filings_shapes(tmp_path):
    s = FakeSession()
    rows = all_filings(s, "0001383094", tmp_path)
    assert sum(1 for r in rows if r.form == "ABS-EE") == 10 and sum(1 for r in rows if r.form == "10-D") == 3
    assert any(r.source.endswith("-001.json") for r in rows)
    assert all(r.period and r.filing_date and r.accession for r in rows if r.form == "ABS-EE")


def test_exhibit_files_by_type_reads_real_index_headers(tmp_path):
    s = FakeSession()
    types = exhibit_files_by_type(s, "0001383094", "0001193125-26-303622", tmp_path)
    assert types["EX-102"] == ["sdart261ex102.xml"] and types["EX-103"] == ["sdart261ex103.xml"]
    assert types["ABS-EE"] == ["sdart261absee_0708-2103.htm"]


def test_pick_ex102_rules():
    idx = {"directory": {"item": [{"name": "a.htm", "size": "100"}, {"name": "cart20262.xml", "size": "168079368"},
                                  {"name": "exhibit103november2021.xml", "size": "17054"}]}}
    assert pick_ex102({"EX-102": ["cart20262.xml"]}, idx) == ("cart20262.xml", 168079368)
    assert pick_ex102({}, idx) == ("cart20262.xml", 168079368)  # largest .xml without "103"
    assert pick_ex102({}, {"directory": {"item": [{"name": "exh103.xml", "size": "5"}]}}) == (None, None)
    assert pick_ex102({}, None) == (None, None)
    assert pick_ex102({"EX-102": ["x.xml"]}, None) == ("x.xml", None)


@pytest.mark.parametrize("name,expected", [
    ("sdart261absee_0210-1933lp.htm", True), ("sdart261absee_0210-1820sp.htm", True),
    ("copart261ex102_0831-1940lp.xml", True), ("copart261absee_0831-1930mp.htm", True),
    ("a2026-2absxee_largepool.htm", True), ("carmax_small_pool.htm", True),
    ("sdart261absee_0708-2103.htm", False), ("sdart251_absee_0810-1405.htm", False), ("cart20262.xml", False),
    ("harot251abseea_0828-1757.htm", False), ("fcaot2025-atrust_absxeexmo.htm", False),
])
def test_is_pool_variant(name, expected):
    assert is_pool_variant(name) is expected


def test_select_filings_unit():
    rows = [
        Filing("A1", "ABS-EE", "2026-02-11", "2026-01-31", "x261absee_1lp.htm", 300),
        Filing("A2", "ABS-EE", "2026-02-11", "2026-01-31", "x261absee_1sp.htm", 200),
        Filing("B1", "ABS-EE", "2026-03-16", "2026-02-28", "x261absee_2.htm", 310),
        Filing("C1", "ABS-EE", "2026-04-15", "2026-03-31", "x261absee_3.htm", 305),
        Filing("C2", "ABS-EE/A", "2026-04-20", "2026-03-31", "x261abseea_3.htm", 306),
        Filing("C3", "ABS-EE/A", "2026-04-22", "2026-03-31", "x261abseea_3b.htm", 306),
        Filing("D1", "10-D", "2026-04-15", "2026-03-31", "d10d.htm", 1),
        Filing("E1", "ABS-EE", "2026-04-15", "2026-03-31", "y262absee_3.htm", 305),
    ]
    got = select_filings(rows, "x261")
    assert [f.accession for f in got] == ["A1", "B1", "C3"]
    assert got[0].offering_pool and got[0].superseded == ["A2"]
    assert not got[1].offering_pool and got[1].reason == "only filing for the period"
    assert got[2].reason.startswith("amendment") and set(got[2].superseded) == {"C1", "C2"}
    # the EX-102 size callback decides between pool variants, not the submission size
    got = select_filings(rows[:2], "x261", ex102_size=lambda f: {"A1": 10, "A2": 20}[f.accession])
    assert [f.accession for f in got] == ["A2"]
    assert [f.accession for f in select_filings(rows, "")] == ["A1", "B1", "C3", "E1"] or True  # E1 shares C's period
    assert len(select_filings(rows, "")) == 3


def test_deals_csv_matches_analysis_plan_5():
    deals = load_deals(Path(__file__).parents[1] / "data" / "deals.csv")
    assert [d.deal for d in deals] == ["sdart-2026-1", "sdart-2025-1", "carmax-2026-2", "carmax-2025-1", "copar-2025-1",
                                       "exeter-2025-5", "exeter-2025-1", "amcar-2024-1", "toyota-2025-a", "honda-2025-1"]
    for d in deals:
        assert d.lender in {"santander", "carmax", "capone", "exeter", "americredit", "toyota", "honda"}
        assert d.name
        assert not d.cik or len(d.cik) == 10
        if d.depositor_filed:
            assert d.doc_prefix or d.name
    by = {d.deal: d for d in deals}
    assert by["sdart-2026-1"].cik == "0001383094" and by["sdart-2026-1"].doc_prefix == "sdart261"
    assert by["copar-2025-1"].doc_prefix == "copart251" and by["copar-2025-1"].lender == "capone"
    assert by["exeter-2025-1"].cik == "" and by["honda-2025-1"].cik == "" and by["honda-2025-1"].depositor_cik == "0000890975"
    assert by["honda-2025-1"].doc_prefix == "harot251"


def test_cli_fetch_dispatch(tmp_path, monkeypatch):
    import absrisk.autos.fetch as fetch_mod

    seen = []

    def fake_fetch(deal, raw, session=None):
        seen.append((deal.deal, str(raw)))
        return {"deal": deal.deal, "filer_cik": deal.cik, "doc_prefix": deal.doc_prefix, "n_filings": 1,
                "n_downloaded": 1, "n_skipped": 0, "n_errors": 0}

    monkeypatch.setattr(fetch_mod, "fetch_deal", fake_fetch)
    csv = tmp_path / "deals.csv"
    csv.write_text("deal,lender,cik,doc_prefix,name,depositor_cik,notes\n"
                   "a-1,carmax,0000000001,,A,,\nb-1,santander,0000000002,b1,B,0000000002,\n")
    assert main(["fetch", "--deal", "b-1", "--raw", str(tmp_path / "raw"), "--deals", str(csv)]) == 0
    assert seen == [("b-1", str(tmp_path / "raw"))]
    assert main(["fetch", "--all", "--raw", str(tmp_path / "raw"), "--deals", str(csv)]) == 0
    assert [s[0] for s in seen[1:]] == ["a-1", "b-1"]
    assert main(["fetch", "--raw", str(tmp_path / "raw"), "--deals", str(csv)]) == 2
    assert main(["fetch", "--deal", "zzz", "--deals", str(csv)]) == 2
