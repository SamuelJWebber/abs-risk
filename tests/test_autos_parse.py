"""parse.py against the real-cut EX-102 fixtures (tests/fixtures/autos/<slug>/<period>.xml, made by
tests/fixtures/autos/tools/make_fixtures.py from the scouting files listed in design/scout-autos.md section 2)."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from absrisk.autos.parse import (
    LOAN_MONTH_COLUMNS, ORIGINATION_KEYS, ParseError, detect_pti_scale, file_period, iter_loan_months,
    iter_records, parse_date, parse_month, score_value,
)

FIX = Path(__file__).parent / "fixtures" / "autos"
FIXTURES = {  # slug -> (lender, [periods])
    "sdart-2026-1": ("santander", ["2026-06", "2026-07"]),
    "carmax-2026-2": ("carmax", ["2026-06", "2026-07"]),
    "copar-2025-1": ("capone", ["2026-06", "2026-07"]),
    "exeter-2025-5": ("exeter", ["2026-06"]),
    "amcar-2024-1": ("americredit", ["2026-07"]),
    "toyota-2025-a": ("toyota", ["2026-07"]),
    "ford-2025-a": ("ford", ["2026-07"]),
}
ALL = [(slug, lender, p) for slug, (lender, ps) in FIXTURES.items() for p in ps]


def fixture(slug: str, period: str) -> Path:
    return FIX / slug / f"{period}.xml"


def raw_count(path: Path, pattern: str) -> int:
    return len(re.findall(pattern, path.read_text(encoding="utf-8")))


@pytest.mark.parametrize("slug,lender,period", ALL)
def test_every_fixture_streams_with_all_fields(slug, lender, period):
    path = fixture(slug, period)
    info: dict = {}
    rows = list(iter_loan_months(path, slug, lender, info))
    assert info["n_records"] == len(rows) == raw_count(path, r"<assets>")
    assert info["n_periods_other"] == 0
    y, m = period.split("-")
    assert info["period"].year == int(y) and info["period"].month == int(m)
    assert file_period(path) == info["period"]
    stubs = 0
    for r in rows:
        assert set(LOAN_MONTH_COLUMNS) <= set(r) and set(ORIGINATION_KEYS) <= set(r)
        assert r["deal"] == slug and r["asset_id"] and r["period"] == info["period"]
        if r["orig_amount"] is None:  # Ford's recovery-only stubs on closed loans (scout-autos 3, 11)
            stubs += 1
            assert slug == "ford-2025-a" and r["balance_end"] is None and r["recovered_amount"] > 0
            continue
        assert r["orig_month"] is not None and r["orig_month"].day == 1
        # 0% APR is common on rate-subvented loans (subvented = 1): 236 of SDART's 300 oldest, 237 of Ford's
        assert r["orig_amount"] > 0 and 0 <= r["orig_apr"] < 1 and r["orig_term"] > 0
    assert stubs == (2 if slug == "ford-2025-a" else 0)
    assert len({r["asset_id"] for r in rows}) == len(rows), "assetNumber is unique within a file (scout-autos 2)"
    assert info["n_apr_gt_1"] == 0, "rates are fractions everywhere (scout-autos 6.4)"
    assert info["n_pti_gt_1_after"] <= 0.02 * len(rows)


@pytest.mark.parametrize("slug,lender,period", ALL)
def test_fixture_is_under_2mb(slug, lender, period):
    assert fixture(slug, period).stat().st_size < 2 * 1024 * 1024


def test_copar_pti_is_percent_and_divided_by_100():
    """scout-autos 6.1: Capital One reports PTI in percent (median 4.95-5.61); everyone else a fraction."""
    path = fixture("copar-2025-1", "2026-06")
    scale = detect_pti_scale(path, "capone")
    assert scale["pti_rule"] == "issuer+median" and scale["pti_sample_median_raw"] > 1
    assert detect_pti_scale(path, None)["pti_rule"] == "median"  # the median rule alone catches it
    raw_first = float(re.search(r"<paymentToIncomePercentage>([^<]+)<", path.read_text(encoding="utf-8")).group(1))
    rows = list(iter_loan_months(path, "copar-2025-1", "capone"))
    assert rows[0]["pti"] == pytest.approx(raw_first / 100)
    assert all(r["pti"] is not None and r["pti"] < 1 for r in rows)
    assert 0.02 < sorted(r["pti"] for r in rows)[len(rows) // 2] < 0.12


@pytest.mark.parametrize("slug,lender,period", [t for t in ALL if t[0] != "copar-2025-1"])
def test_other_issuers_pti_is_a_fraction_and_left_alone(slug, lender, period):
    scale = detect_pti_scale(fixture(slug, period), lender)
    assert scale["pti_rule"] is None and scale["pti_divisor"] == 1.0
    assert scale["pti_sample_median_raw"] < 0.2


def test_santander_score_zero_becomes_null():
    """scout-autos 6.3: Santander encodes "no score" as a literal 0."""
    path = fixture("sdart-2026-1", "2026-06")
    n_zero = raw_count(path, r"<obligorCreditScore>0</obligorCreditScore>")
    assert n_zero == 1  # what the cut holds (tools/hand_count.py: score_zero_month1)
    rows = list(iter_loan_months(path, "sdart-2026-1", "santander"))
    nulls = [r for r in rows if r["score"] is None]
    assert len(nulls) == n_zero
    assert all(r["score_type"] == "Bureau" for r in rows)  # verbatim
    assert all(isinstance(r["score"], int) and 300 <= r["score"] <= 900 for r in rows if r["score"] is not None)


def test_exeter_score_zero_becomes_null():
    path = fixture("exeter-2025-5", "2026-06")
    n_zero = raw_count(path, r"<obligorCreditScore>0</obligorCreditScore>")
    rows = list(iter_loan_months(path, "exeter-2025-5", "exeter"))
    assert n_zero > 0 and sum(r["score"] is None for r in rows) == n_zero
    assert {r["score_type"] for r in rows} == {"Consumer Credit Bureau"}


@pytest.mark.parametrize("raw,expected", [
    ("638", 638), ("0", None), ("", None), (None, None), ("None", None), ("N/A", None), ("-1", None), ("7.0", 7),
])
def test_score_value_encodings(raw, expected):
    """The three "no score" encodings of scout-autos 6.3 (0; type "None" with a non-numeric value; empty)."""
    assert score_value(raw) == expected


def test_repeated_subvented_keeps_the_first_value():
    """scout-autos 6.7: `subvented` appears twice in 53% of Ford records (and in Santander's oldest loans as
    `1` then `98`); a dict-per-record parser would keep the last."""
    path = fixture("ford-2025-a", "2026-07")
    text = path.read_text(encoding="utf-8")
    pairs = re.findall(r"<subvented>([^<]*)</subvented>\s*<subvented>([^<]*)</subvented>", text)
    assert len(pairs) > 50 and any(a != b for a, b in pairs)
    info: dict = {}
    rows = list(iter_loan_months(path, "ford-2025-a", "ford", info))
    assert info["dup_counts"]["subvented"] == len(pairs)
    by_id = {r["asset_id"]: r for r in rows}
    for rec_text in re.findall(r"<assets>(.*?)</assets>", text, re.S):
        m = re.search(r"<subvented>([^<]*)</subvented>", rec_text)
        aid = re.search(r"<assetNumber>([^<]*)<", rec_text).group(1).strip()
        assert by_id[aid]["subvented"] == (m.group(1).strip() if m else None)

    sd = fixture("sdart-2026-1", "2026-06")
    rows = list(iter_loan_months(sd, "sdart-2026-1", "santander"))
    from collections import Counter

    assert Counter(r["subvented"] for r in rows) == {"0": 56, "1": 243, "98": 1}  # tools/hand_count.py
    raw = list(iter_records(sd))
    assert sum(1 for r in raw if "__dups" in r) == 242


def test_ford_commercial_obligors_flagged():
    """scout-autos 6.9 and 4a: Ford's "Commercial Bureau" records (1-670 score scale, no PTI) are flagged."""
    path = fixture("ford-2025-a", "2026-07")
    n_comm = raw_count(path, r"<obligorCreditScoreType>Commercial Bureau</obligorCreditScoreType>")
    assert n_comm == 12
    info: dict = {}
    rows = list(iter_loan_months(path, "ford-2025-a", "ford", info))
    comm = [r for r in rows if r["commercial"]]
    assert len(comm) == n_comm == info["n_commercial"]
    assert all(r["score_type"] == "Commercial Bureau" for r in comm)
    assert all(r["pti"] is None for r in comm)
    consumer = [r for r in rows if not r["commercial"] and r["score"] is not None]
    assert min(r["score"] for r in consumer) >= 300


def test_missing_delinquency_element_is_null_not_zero():
    """scout-autos 6.6: AmeriCredit, CarMax and Toyota omit currentDelinquencyStatus for (some) zero-balance
    loans; an absent element must come through as null, never as 0. CarMax omits it for paid-off loans (code 1)
    and Toyota for charge-offs (code 4), scout-autos 4d."""
    for slug, lender, period, code in [("amcar-2024-1", "americredit", "2026-07", None),
                                       ("carmax-2026-2", "carmax", "2026-06", "1"),
                                       ("toyota-2025-a", "toyota", "2026-07", "4")]:
        path = fixture(slug, period)
        n_records = raw_count(path, r"<assets>")
        n_with = raw_count(path, r"<currentDelinquencyStatus>[^<]*</currentDelinquencyStatus>")
        rows = list(iter_loan_months(path, slug, lender))
        assert sum(r["dpd"] is None for r in rows) == n_records - n_with
        if code:
            assert all(r["dpd"] is None for r in rows if r["zb_code"] == code)
            assert n_records - n_with > 0
    sd = list(iter_loan_months(fixture("sdart-2026-1", "2026-06"), "sdart-2026-1", "santander"))
    assert all(r["dpd"] is not None for r in sd)  # Santander always carries it (scout-autos 3)


def test_dates_and_zero_balance_fields():
    path = fixture("exeter-2025-5", "2026-06")
    rows = list(iter_loan_months(path, "exeter-2025-5", "exeter"))
    closed = [r for r in rows if r["zb_code"]]
    assert {r["zb_code"] for r in closed} <= {"1", "3", "4"}  # codes seen (scout-autos 3)
    assert all(r["zb_date"] is not None and r["zb_date"].day == 1 for r in closed)
    assert all(r["zb_date"] <= r["period"] for r in closed)
    co = [r for r in closed if r["zb_code"] == "4"]
    assert co and all(r["chargeoff_amount"] is not None for r in co)
    assert any(r["chargeoff_amount"] > 0 for r in co)  # some code-4 loans report 0.00 (recovered in full?)
    assert all(r["dpd"] == 0 for r in closed)  # Exeter resets delinquency at zero balance (scout-autos 4d)
    open_ = [r for r in rows if not r["zb_code"]]
    assert all(r["zb_date"] is None and r["balance_end"] is not None for r in open_)


def test_date_helpers():
    assert parse_month("01/2020") == date(2020, 1, 1)
    assert parse_month("12/2025") == date(2025, 12, 1)
    assert parse_month("2025-12") is None and parse_month("") is None and parse_month(None) is None
    assert parse_date("06-30-2026") == date(2026, 6, 30)
    assert parse_date("06/30/2026") is None
    assert parse_month("01/2026") > parse_month("12/2025")  # scout-autos 6.5: string order would say otherwise


def test_servicing_flag_and_repossession():
    rows = list(iter_loan_months(fixture("exeter-2025-5", "2026-06"), "exeter-2025-5", "exeter"))
    assert {r["servicing_flag"] for r in rows} <= {None, "modified", "extended", "modified+extended"}
    assert any(r["repossessed"] is True for r in rows) and any(r["repossessed"] is False for r in rows)


def test_not_an_ex102_fails_loudly(tmp_path):
    bad = tmp_path / "bad.xml"
    bad.write_text('<?xml version="1.0"?><other><assets><assetNumber>1</assetNumber></assets></other>')
    with pytest.raises(ParseError):
        list(iter_loan_months(bad, "x"))
    nested = tmp_path / "nested.xml"
    nested.write_text('<?xml version="1.0"?><assetData><assets><assetNumber>1</assetNumber><a><b>1</b></a></assets></assetData>')
    with pytest.raises(ParseError):
        list(iter_records(nested))
