"""One row per trust-month: a statement filed twice must not become two rows in cards_monthly.

The 2019-2026 corpus holds five such pairs (bofa 2018-12 and 2020-05, citi 2019-09 and 2019-10, comet
2019-02): the same monthly statement on two accessions, identical numbers. Two rows for one month overstate
coverage and break month-over-month differences, so `parse_raw` keeps the filing that supersedes (an
amendment over an original, then the later filing date) and records the other in `row_labels_json`.

The duplicate here is built from a real fixture: the July 2026 BA filing copied under a second accession with
a 10-D/A manifest, which is the shape of the corpus pairs.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from absrisk.cards.parse import COLUMNS, parse_raw

FIX = Path(__file__).parent / "fixtures" / "cards"
BOFA = FIX / "bofa" / "0001140361-26-033313"          # 10-D, filed 2026-08-17, period 2026-07-31
AMEND = "0001140361-26-034001"                        # invented accession for the copy


def _copy_filing(src: Path, raw: Path, trust: str, accession: str, **manifest) -> Path:
    dest = raw / trust / accession
    shutil.copytree(src, dest)
    m = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
    m.update(accession=accession, **manifest)
    (dest / "manifest.json").write_text(json.dumps(m, indent=1), encoding="utf-8")
    return dest


@pytest.fixture()
def raw_with_amendment(tmp_path):
    raw = tmp_path / "raw"
    shutil.copytree(BOFA, raw / "bofa" / BOFA.name)
    _copy_filing(BOFA, raw, "bofa", AMEND, form="10-D/A", filing_date="2026-08-29")
    return raw


def test_same_statement_twice_is_one_row(raw_with_amendment):
    rows, errors = parse_raw(raw_with_amendment, ("bofa",))
    assert errors == []
    assert [(r["trust"], r["period_end"]) for r in rows] == [("bofa", "2026-07-31")]


def test_amendment_supersedes_and_original_is_recorded(raw_with_amendment):
    (row,), _ = parse_raw(raw_with_amendment, ("bofa",))
    assert row["source_accession"] == AMEND
    audit = json.loads(row["row_labels_json"])
    assert audit["superseded"] == [{"accession": BOFA.name, "form": "10-D", "filing_date": "2026-08-17",
                                    "identical": True}]
    assert audit["filing"] == {"accession": AMEND, "form": "10-D/A", "filing_date": "2026-08-29"}
    assert audit["checks"] and audit["inputs"]          # the parser's own audit trail is kept intact


def test_later_plain_refiling_supersedes(tmp_path):
    """Two plain 10-Ds of one statement (bofa 2020-05 in the corpus, filed by two agents): later date wins."""
    raw = tmp_path / "raw"
    _copy_filing(BOFA, raw, "bofa", "0001128250-26-000004", filing_date="2026-08-20")   # later, sorts first
    shutil.copytree(BOFA, raw / "bofa" / BOFA.name)
    (row,), errors = parse_raw(raw, ("bofa",))
    assert errors == []
    assert row["source_accession"] == "0001128250-26-000004"
    assert [s["accession"] for s in json.loads(row["row_labels_json"])["superseded"]] == [BOFA.name]


def _row(acc: str, **vals) -> dict:
    r = {k: None for k in COLUMNS}
    r.update(trust="citi", period_end="2019-09-25", gross_co_rate=0.0261, payment_rate=0.2696,
             source_accession=acc, source_file=f"{acc}.htm", row_labels_json=json.dumps({"checks": ["ok"]}))
    r.update(vals)
    return r


def test_conflicting_plain_filings_keep_the_later_and_log_it():
    """Different numbers for one month without an amendment is unexpected: kept, but logged as an error."""
    from absrisk.cards.parse import dedupe_rows

    rows = [_row("0001193125-19-267586"), _row("0001193125-19-302272", gross_co_rate=0.0270)]
    meta = {"0001193125-19-267586": {"form": "10-D", "filing_date": "2019-10-15"},
            "0001193125-19-302272": {"form": "10-D", "filing_date": "2019-11-20"}}
    kept, errors = dedupe_rows(rows, meta)
    assert [r["source_accession"] for r in kept] == ["0001193125-19-302272"]
    assert kept[0]["gross_co_rate"] == 0.0270
    sup = json.loads(kept[0]["row_labels_json"])["superseded"]
    assert sup == [{"accession": "0001193125-19-267586", "form": "10-D", "filing_date": "2019-10-15",
                    "identical": False, "differs": ["gross_co_rate"]}]
    assert len(errors) == 1
    trust, acc, msg = errors[0]
    assert (trust, acc) == ("citi", "0001193125-19-267586")
    assert "DuplicateMonth" in msg and "0001193125-19-302272" in msg and "gross_co_rate" in msg


def test_conflicting_amendment_is_expected_and_not_an_error():
    from absrisk.cards.parse import dedupe_rows

    rows = [_row("0001193125-19-267586"), _row("0001193125-19-302272", gross_co_rate=0.0270)]
    meta = {"0001193125-19-267586": {"form": "10-D", "filing_date": "2019-10-15"},
            "0001193125-19-302272": {"form": "10-D/A", "filing_date": "2019-11-20"}}
    kept, errors = dedupe_rows(rows, meta)
    assert errors == [] and kept[0]["source_accession"] == "0001193125-19-302272"


def test_committed_monthly_table_has_one_row_per_trust_month():
    """The committed data/cards_monthly.csv, as the refresh workflow writes it. Held five duplicate months until the
    2026-11-09 refresh (run 42691131162) regenerated it through dedupe_rows."""
    import csv

    path = Path(__file__).resolve().parents[1] / "data" / "cards_monthly.csv"
    with open(path, newline="", encoding="utf-8") as fh:
        keys = [(r["trust"], r["period_end"]) for r in csv.DictReader(fh)]
    assert keys, "data/cards_monthly.csv is empty"
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    assert dupes == []


def test_unique_months_pass_through_untouched():
    from absrisk.cards.parse import dedupe_rows

    rows = [_row("a", period_end="2019-08-26"), _row("b")]
    kept, errors = dedupe_rows(rows, {})
    assert kept == rows and errors == []
