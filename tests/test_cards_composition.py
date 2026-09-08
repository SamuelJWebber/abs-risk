"""Prospectus composition tables for the seven trusts, the committed CSVs, and the tier crosswalk.

Expected values are the verbatim table cells of the fixture prospectuses (quoted in design/scout-cards.md
section C): shares are written as amount / total so each traces to the file.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from absrisk.cards import main
from absrisk.cards.composition import (
    COLUMNS,
    CROSSWALK_COLUMNS,
    TIERS,
    build_composition,
    build_crosswalk,
    parse_bucket,
    prospectus_files,
    read_csv,
    tier_shares,
    tier_weights,
)

FIX = Path(__file__).parent / "fixtures" / "cards"
REPO = Path(__file__).resolve().parents[1]

PROSPECTUS = {  # slug: (accession, file, as_of dates per table)
    "amex": ("0001193125-25-160041", "d938411d424b5.htm"),
    "comet": ("0001193125-26-302059", "d155768d424b5.htm"),
    "chase": ("0001193125-26-236451", "d53666d424b5.htm"),
    "citi": ("0001193125-25-144490", "d945716d424b2.htm"),
    "discover": ("0001193125-23-173892", "d460049d424b5.htm"),
    "synchrony": ("0001104659-26-092741", "tm2622401d3_424b5.htm"),
    "bofa": ("0000929638-26-001790", "ba424b5.htm"),
}
BUCKETS = {  # (fico, credit_limit, account_age) bucket counts, from the tables in design/scout-cards.md C1-C7
    "amex": (6, 9, 8), "comet": (5, 4, 7), "chase": (5, 7, 8), "citi": (11, 14, 7),
    "discover": (5, 4, 6), "synchrony": (4, 12, 12), "bofa": (5, 6, 8),
}
AS_OF = {
    "amex": {"fico": "2025-05-31", "credit_limit": "2025-05-31", "account_age": "2025-05-31"},
    "comet": {"fico": "2026-06-10", "credit_limit": "2026-06-10", "account_age": "2026-06-10"},
    "chase": {"fico": "2026-03-31", "credit_limit": "2026-03-31", "account_age": "2026-03-31"},
    "citi": {"fico": "2025-03-30", "credit_limit": "2025-03-26", "account_age": "2025-03-26"},
    "discover": {"fico": "2023-05-31", "credit_limit": "2023-05-31", "account_age": "2023-05-31"},
    "synchrony": {"fico": "2026-05-31", "credit_limit": "2026-05-31", "account_age": "2026-05-31"},
    "bofa": {"fico": "2026-04-01", "credit_limit": "2026-04-01", "account_age": "2026-04-01"},
}


@pytest.fixture(scope="module")
def built():
    rows, tabs = build_composition(FIX)
    return rows, tabs


def rows_of(rows, trust, table):
    return [r for r in rows if r["trust"] == trust and r["table"] == table]


def bucket(rows, trust, table, label):
    hits = [r for r in rows if r["trust"] == trust and r["table"] == table and r["bucket_label"] == label]
    assert len(hits) == 1, (trust, table, label, [r["bucket_label"] for r in rows_of(rows, trust, table)])
    return hits[0]


def test_seven_prospectuses_found():
    found = {t: (a, f.name) for t, a, f in prospectus_files(FIX)}
    assert found == PROSPECTUS


@pytest.mark.parametrize("trust", sorted(PROSPECTUS))
def test_bucket_counts_as_of_and_sums(built, trust):
    rows, _ = built
    for table, n in zip(("fico", "credit_limit", "account_age"), BUCKETS[trust]):
        rs = rows_of(rows, trust, table)
        assert len(rs) == n, (trust, table, [r["bucket_label"] for r in rs])
        assert {r["as_of"] for r in rs} == {AS_OF[trust][table]}
        assert {r["prospectus_accession"] for r in rs} == {PROSPECTUS[trust][0]}
        assert {r["prospectus_file"] for r in rs} == {PROSPECTUS[trust][1]}
        assert sum(r["share_receivables"] for r in rs) == pytest.approx(1.0, abs=1e-3)
        accts = [r["share_accounts"] for r in rs]
        if any(a is not None for a in accts):
            assert all(a is not None for a in accts)
            assert sum(accts) == pytest.approx(1.0, abs=1e-3)
        for r in rs:
            assert set(r) == set(COLUMNS)
            assert (r["score_type"] != "") == (table == "fico")


def test_frozen_shares(built):
    rows, _ = built
    # Amex C1: receivables only; 760 and above 14,960,364,284 of 26,797,475,459; NPSL line in the credit-limit table
    r = bucket(rows, "amex", "fico", "760 and above")
    assert (r["bucket_lo"], r["bucket_hi"]) == (760, None)
    assert r["share_receivables"] == pytest.approx(14_960_364_284 / 26_797_475_459)
    assert r["share_accounts"] is None and r["score_type"] == "FICO"
    r = bucket(rows, "amex", "credit_limit", "No Pre-Set Spending Limit (Pay Over Time)")
    assert (r["bucket_lo"], r["bucket_hi"]) == (None, None)
    assert r["share_receivables"] == pytest.approx(11_328_200_418 / 26_797_475_459)
    assert r["share_accounts"] == pytest.approx(3_582_110 / 13_609_288)
    assert bucket(rows, "amex", "credit_limit", "Less than $1,000.99")["bucket_hi"] == 1000
    assert bucket(rows, "amex", "credit_limit", "$1,001 to $5,000.99")["bucket_lo"] == 1001
    # COMET C2: consumer + small business combined by dollars
    r = bucket(rows, "comet", "fico", "Less than or equal to 600")
    assert (r["bucket_lo"], r["bucket_hi"]) == (None, 600)
    assert r["share_receivables"] == pytest.approx((1_195_773_490 + 62_380_752) / (21_309_300_918 + 1_801_672_011))
    assert "combined" in r["sample_note"]
    r = bucket(rows, "comet", "credit_limit", "Over $10,000.00")
    assert r["bucket_lo"] == 10001 and r["share_accounts"] == pytest.approx((3_263_399 + 177_713) / (8_680_448 + 525_279))
    # Chase C3: 5% random sample, receivables of the sample only
    r = bucket(rows, "chase", "fico", "720 and Above")
    assert r["share_receivables"] == pytest.approx(469_195_167 / 592_516_859)
    assert "SAMPLE" in r["sample_note"]
    assert bucket(rows, "chase", "credit_limit", "$0.01 to $5,000.00")["bucket_lo"] == 1
    # Citi C4: accounts and receivables, 11 buckets, '000' is unscored
    r = bucket(rows, "citi", "fico", "801+")
    assert (r["bucket_lo"], r["bucket_hi"]) == (801, None)
    assert r["share_accounts"] == pytest.approx(4_107_000 / 7_679_706)
    assert r["share_receivables"] == pytest.approx(5_882_168_485 / 21_412_889_398)
    r = bucket(rows, "citi", "fico", "000")
    assert (r["bucket_lo"], r["bucket_hi"]) == (None, None) and "unscored" in r["sample_note"]
    assert r["share_accounts"] == pytest.approx(628_038 / 7_679_706)
    assert bucket(rows, "citi", "fico", "640 to 660")["bucket_hi"] == 660
    # Discover C5: stale, $000s, seasoning table has percentages only
    r = bucket(rows, "discover", "fico", "720 and above")
    assert r["share_receivables"] == pytest.approx(16_995_179 / 25_035_844) and "STALE" in r["sample_note"]
    r = bucket(rows, "discover", "account_age", "60 Months or Greater")
    assert r["share_receivables"] == 1.0 and r["share_accounts"] == 1.0 and r["bucket_lo"] == 60
    # Synchrony C6: VantageScore; first bucket mixes unscored with <=599
    r = bucket(rows, "synchrony", "fico", "No score and/or less than or equal to 599*")
    assert r["score_type"] == "VantageScore" and (r["bucket_lo"], r["bucket_hi"]) == (None, 599)
    assert r["share_receivables"] == pytest.approx(708_664_528 / 11_489_137_310)
    r = bucket(rows, "synchrony", "account_age", "Over 120 Months")
    assert r["share_accounts"] == pytest.approx(2_832_117 / 9_777_270) and r["bucket_lo"] == 121
    # BofA C7: descending rows; Over 720 -> lo 721
    r = bucket(rows, "bofa", "fico", "Over 720")
    assert (r["bucket_lo"], r["bucket_hi"]) == (721, None)
    assert r["share_receivables"] == pytest.approx(10_386_401_725 / 14_557_481_374)
    assert bucket(rows, "bofa", "credit_limit", "$ 25,000.01 or More")["share_accounts"] == pytest.approx(1_279_457 / 4_774_134)


@pytest.mark.parametrize("label,kind,expect", [
    ("Less than 560", "fico", (None, 559)), ("560 -659", "fico", (560, 659)), ("760 and above", "fico", (760, None)),
    ("Refreshed FICO Unavailable", "fico", (None, None)), ("No score", "fico", (None, None)),
    ("Less than or equal to 600", "fico", (None, 600)), ("601-660", "fico", (601, 660)),
    ("Greater than 720", "fico", (721, None)), ("Over 720", "fico", (721, None)), ("801+", "fico", (801, None)),
    ("001 to 599", "fico", (1, 599)), ("000", "fico", (None, None)), ("Unscored", "fico", (None, None)),
    ("No score and/or less than or equal to 599*", "fico", (None, 599)),
    ("Less than $1,000.99", "credit_limit", (None, 1000)), ("$1,001 to $5,000.99", "credit_limit", (1001, 5000)),
    ("$25,001 or More(1)", "credit_limit", (25001, None)), ("$1,500.01-$5,000.00", "credit_limit", (1501, 5000)),
    ("Over $10,000.00", "credit_limit", (10001, None)), ("$0.01 to $5,000.00", "credit_limit", (1, 5000)),
    ("$50,000.01 or More", "credit_limit", (50001, None)), ("$ 5,000.01 - $ 10,000.00", "credit_limit", (5001, 10000)),
    ("Less than or equal to $ 5,000.00", "credit_limit", (None, 5000)), ("$10,000.01 or more", "credit_limit", (10001, None)),
    ("Not More than 11 Months", "account_age", (None, 11)), ("72 Months or More", "account_age", (72, None)),
    ("Over 6 Months to 12 Months", "account_age", (7, 12)), ("Over 60 Months", "account_age", (61, None)),
    ("Up to 6 Months", "account_age", (None, 6)), ("6 months or less", "account_age", (None, 6)),
    ("Over 6 to 12 months", "account_age", (7, 12)), ("Less Than 12 Months", "account_age", (None, 11)),
    ("60 Months or Greater", "account_age", (60, None)), ("Less than or equal to 6 Months", "account_age", (None, 6)),
])
def test_parse_bucket(label, kind, expect):
    lo, hi, _ = parse_bucket(label, kind)
    assert (lo, hi) == expect


def test_tier_weights_rule():
    w = tier_weights(560, 659)  # Amex bucket: 20 deep-subprime points, 40 subprime, 40 near-prime
    assert w == pytest.approx({"deep_subprime": 0.2, "subprime": 0.4, "near_prime": 0.4, "prime": 0, "prime_plus": 0,
                               "superprime": 0})
    assert tier_weights(660, 719) == pytest.approx({"prime": 1.0, **{n: 0 for n, _, _ in TIERS if n != "prime"}})
    w = tier_weights(720, None)  # clamped to 850: 80 prime_plus points, 51 superprime
    assert w["prime_plus"] == pytest.approx(80 / 131) and w["superprime"] == pytest.approx(51 / 131)
    assert sum(tier_weights(None, 599).values()) == pytest.approx(1.0)


def test_crosswalk_covers_every_bucket_and_tier_shares_sum_to_one(built):
    rows, _ = built
    xw = build_crosswalk(rows)
    assert list(xw[0]) == CROSSWALK_COLUMNS
    fico = [(r["trust"], r["bucket_label"]) for r in rows if r["table"] == "fico"]
    assert sorted({(x["trust"], x["bucket_label"]) for x in xw}) == sorted(set(fico))
    assert len(xw) == sum(BUCKETS[t][0] for t in BUCKETS) == 41
    for x in xw:
        s = sum(float(x[f"w_{n}"]) for n, _, _ in TIERS)
        if "unscored" in x["flags"].split(","):
            assert s == 0 and x["bucket_lo"] is None and x["bucket_hi"] is None
        else:
            assert s == pytest.approx(1.0, abs=1e-5)
            assert "uniform in score" in x["rule"]
        if x["trust"] == "amex":
            assert "amex_nonstandard_buckets" in x["flags"]
        if x["trust"] == "synchrony":
            assert "vantagescore" in x["flags"] and x["score_type"] == "VantageScore"
        if x["trust"] == "chase":
            assert "sample_5pct" in x["flags"]
        if x["trust"] == "discover":
            assert "stale_2023" in x["flags"]
    assert "includes_unscored" in next(x for x in xw if x["trust"] == "synchrony" and x["bucket_lo"] is None)["flags"]
    assert "straddle" in next(x for x in xw if x["trust"] == "amex" and x["bucket_lo"] == 700)["flags"]
    assert "straddle" not in next(x for x in xw if x["trust"] == "amex" and x["bucket_lo"] == 660)["flags"]
    shares = tier_shares(rows, xw)
    assert {t for t, _ in shares} == set(PROSPECTUS)
    assert ("citi", "accounts") in shares and ("amex", "accounts") not in shares
    for key, s in shares.items():
        assert sum(s[n] for n, _, _ in TIERS) == pytest.approx(1.0, abs=1e-9), key
        assert 0 <= s["unscored"] < 0.1
    assert shares[("citi", "accounts")]["unscored"] == pytest.approx(628_038 / 7_679_706)


def test_committed_csvs_match_fixtures(built):
    """data/cards_composition.csv and crosswalks/fico_buckets.csv are exactly what the fixtures produce."""
    rows, _ = built
    committed = read_csv(REPO / "data" / "cards_composition.csv")
    assert len(committed) == len(rows) == 153
    for a, b in zip(committed, rows):
        for k in COLUMNS:
            v = "" if b[k] is None else b[k]
            if isinstance(v, float):
                assert float(a[k]) == pytest.approx(v, abs=1e-12), (k, a)
            else:
                assert a[k] == str(v), (k, a)
    xw = read_csv(REPO / "crosswalks" / "fico_buckets.csv")
    built_xw = build_crosswalk(rows)
    assert len(xw) == len(built_xw)
    for a, b in zip(xw, built_xw):
        assert (a["trust"], a["bucket_label"], a["flags"], a["rule"]) == (b["trust"], b["bucket_label"], b["flags"], b["rule"])
        for n, _, _ in TIERS:
            assert float(a[f"w_{n}"]) == pytest.approx(b[f"w_{n}"], abs=1e-6)


def test_cli_composition(tmp_path, capsys):
    out, xw = tmp_path / "c.csv", tmp_path / "x.csv"
    assert main(["composition", "--raw", str(FIX), "--out", str(out), "--crosswalk", str(xw)]) == 0
    text = capsys.readouterr().out
    assert "153 rows" in text and "41 crosswalk rows" in text and "tier shares" in text
    assert len(read_csv(out)) == 153 and len(read_csv(xw)) == 41
