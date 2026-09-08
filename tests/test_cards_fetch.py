"""Fetcher logic without EDGAR: a fake session serves fixture files by URL.

Listing uses a trimmed real Synchrony submissions JSON plus two synthetic older pages
(tests/fixtures/cards/edgar); downloading uses the Synchrony 10-D fixture directory.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from absrisk.cards import edgar
from absrisk.cards.edgar import FetchError, FilingRef, exhibit_types, header_field, is_document
from absrisk.cards.fetch import TRUSTS, fetch_filing, fetch_prospectus, fetch_trust, is_complete, latest_prospectus, list_10d

FIX = Path(__file__).parent / "fixtures" / "cards"
EDGAR_FIX = FIX / "edgar"
SYN = TRUSTS["synchrony"]
ACC = "0001104659-26-097449"
FILING_DIR = FIX / "synchrony" / ACC


class Resp:
    def __init__(self, content: bytes, status: int = 200):
        self.content, self.status_code = content, status


class FakeSession:
    """Serves submissions pages from EDGAR_FIX and filing documents from the fixture filing directory."""

    def __init__(self, extra: dict[str, bytes] | None = None):
        self.calls: list[str] = []
        self.extra = extra or {}

    def get(self, url: str, **kw):
        self.calls.append(url)
        if url in self.extra:
            return Resp(self.extra[url])
        name = url.rsplit("/", 1)[1]
        for base in (EDGAR_FIX, FILING_DIR):
            p = base / name
            if p.exists():
                return Resp(p.read_bytes())
        if name.startswith("CIK") and name.endswith(".json"):
            p = EDGAR_FIX / name.replace("CIK0001724789.json", "submissions_0001724789.json")
            if p.exists():
                return Resp(p.read_bytes())
        return Resp(b"not here", 404)


def test_trust_register_uses_issuing_entity_ciks():
    assert {t.cik for t in TRUSTS.values()} == {"0001003509", "0001163321", "0001174821", "0001108348",
                                                "0001724789", "0001128250"}
    assert edgar.folder_url(SYN.cik, ACC) == "https://www.sec.gov/Archives/edgar/data/1724789/000110465926097449/"


def test_list_10d_merges_pages_and_filters_since(tmp_path):
    s = FakeSession()
    fl = list_10d(s, SYN, "2019-01-01", cache_dir=tmp_path)
    assert [f.accession for f in fl] == ["0001104659-26-097449", "0001104659-26-083732", "0001104659-26-073676",
                                         "0001144204-19-008800", "0001144204-19-002200"]
    assert all(f.form == "10-D" for f in fl)
    assert fl[0].filing_date == "2026-08-17" and fl[0].report_date == "2026-07-31"
    assert fl[0].primary_document == "tm2622590d1_10d.htm"
    # the page whose filingTo predates `since` is never requested; the other older page is
    assert not any("submissions-001" in u for u in s.calls)
    assert any("submissions-002" in u for u in s.calls)
    assert (tmp_path / "submissions_0001724789.json").exists()
    assert (tmp_path / "CIK0001724789-submissions-002.json").exists()
    # with an earlier `since`, the 2018 page is fetched and its filings included
    fl2 = list_10d(FakeSession(), SYN, "2018-01-01")
    assert len(fl2) == 7 and fl2[-1].accession == "0001144204-18-059330"


def test_latest_prospectus():
    p = latest_prospectus(FakeSession(), SYN)
    assert p.form == "424B5" and p.accession == "0001104659-26-092741" and p.primary_document == "tm2622401d3_424b5.htm"


def test_exhibit_types_and_header_fields():
    html = (FILING_DIR / f"{ACC}-index-headers.html").read_text(encoding="utf-8", errors="replace")
    assert exhibit_types(html) == {"tm2622590d1_10d.htm": "10-D", "tm2622590d1_ex99-1.htm": "EX-99.1"}
    assert header_field(html, "PERIOD") == "20260731"
    assert header_field(html, "FILING-DATE") == "20260817"


def test_is_document_rules():
    assert is_document("tm2622590d1_ex99-1.htm", ACC)
    assert is_document("b414012_10d.txt", "0001125282-06-004108")  # early-years plain-text primaries are kept
    assert not is_document(f"{ACC}.txt", ACC)  # full submission text file duplicates every exhibit
    assert not is_document(f"{ACC}-index.htm", ACC)
    assert not is_document(f"{ACC}-index-headers.html", ACC)
    assert not is_document("index.json", ACC)
    assert not is_document("image0.jpg", ACC)
    assert not is_document("ex101.xml", ACC)


def test_fetch_filing_writes_documents_and_manifest_idempotently(tmp_path):
    ref = FilingRef(SYN.cik, "10-D", "2026-08-17", "2026-07-31", ACC, "tm2622590d1_10d.htm", "FORM 10-D")
    # index.json with an extra image and the full-submission text file, to prove they are skipped
    idx = json.loads((FILING_DIR / "index.json").read_text(encoding="utf-8"))
    idx["directory"]["item"].append({"name": "image0.jpg", "type": "image2.gif", "size": "123"})
    url = edgar.folder_url(SYN.cik, ACC)
    s = FakeSession({url + "index.json": json.dumps(idx).encode()})
    dest = tmp_path / "synchrony" / ACC
    m = fetch_filing(s, SYN, ref, dest)
    assert [f["name"] for f in m["files"]] == ["tm2622590d1_10d.htm", "tm2622590d1_ex99-1.htm"]
    assert [f["type"] for f in m["files"]] == ["10-D", "EX-99.1"]
    assert m["period"] == "2026-07-31" and m["filing_date"] == "2026-08-17" and m["slug"] == "synchrony"
    assert m["files"][1]["size"] == 262145 and len(m["files"][1]["sha256"]) == 64
    assert (dest / "manifest.json").exists() and (dest / "index.json").exists()
    assert not (dest / "image0.jpg").exists() and not (dest / f"{ACC}.txt").exists()
    assert (dest / "tm2622590d1_ex99-1.htm").stat().st_size == 262145
    assert is_complete(dest)
    downloaded = [u for u in s.calls if u.startswith(url)]
    assert len(downloaded) == 4  # index.json, index-headers, two documents
    # second run: nothing is requested
    s2 = FakeSession()
    m2 = fetch_filing(s2, SYN, ref, dest)
    assert s2.calls == [] and m2["files"] == m["files"]
    # a truncated document breaks completeness and is re-fetched by --force
    (dest / "tm2622590d1_10d.htm").write_bytes(b"x")
    assert not is_complete(dest)
    fetch_filing(FakeSession({url + "index.json": json.dumps(idx).encode()}), SYN, ref, dest, force=True)
    assert (dest / "tm2622590d1_10d.htm").stat().st_size == 53293


def test_fetch_filing_http_error_is_raised(tmp_path):
    ref = FilingRef(SYN.cik, "10-D", "2026-08-17", "2026-07-31", "0001104659-26-000000", "x.htm")
    with pytest.raises(FetchError):
        fetch_filing(FakeSession(), SYN, ref, tmp_path / "x")


def test_fetch_prospectus(tmp_path):
    ref = FilingRef(SYN.cik, "424B5", "2026-08-07", "", "0001104659-26-092741", "tm2622401d3_424b5.htm", "424B5")
    src = FIX / "synchrony" / "prospectus" / ref.accession / ref.primary_document
    s = FakeSession({edgar.folder_url(SYN.cik, ref.accession) + ref.primary_document: src.read_bytes()})
    m = fetch_prospectus(s, SYN, ref, tmp_path / "p")
    assert m["files"][0]["name"] == ref.primary_document and m["files"][0]["size"] == src.stat().st_size
    assert (tmp_path / "p" / ref.primary_document).exists()
    assert fetch_prospectus(FakeSession(), SYN, ref, tmp_path / "p")["accession"] == ref.accession  # no refetch


def test_fetch_trust_end_to_end_with_limit(tmp_path):
    """One trust, newest filing only; the other listed filings are absent from the fake EDGAR and are reported."""
    ref_url = edgar.folder_url(SYN.cik, "0001104659-26-092741") + "tm2622401d3_424b5.htm"
    s = FakeSession({ref_url: b"<html>prospectus</html>"})
    summary = fetch_trust(s, SYN, tmp_path, since="2019-01-01", limit=2)
    assert summary["n_filings"] == 5 and summary["fetched"] == 1 and summary["skipped"] == 0
    assert [e["accession"] for e in summary["errors"]] == ["0001104659-26-083732"]  # not in the fixtures: HTTP 404
    assert summary["prospectus"]["accession"] == "0001104659-26-092741"
    assert (tmp_path / "synchrony" / ACC / "manifest.json").exists()
    assert (tmp_path / "synchrony" / "prospectus" / "0001104659-26-092741" / "manifest.json").exists()
    assert (tmp_path / "synchrony" / "filings_10D.json").exists()
