"""10-D parsers on the six fixture filings (July 2026 data, filed 2026-08-17).

Every expected number below is copied from the fixture exhibit itself (the same rows are quoted in
design/scout-cards.md section B). Delinquency shares are written as the ratio of the printed dollar rows so
the test traces to the filing, not to a parser output.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from absrisk.cards import main
from absrisk.cards.parse import COLUMNS, ParseError, coverage, filing_dirs, parse_filing_dir, parse_raw, write_csv

FIX = Path(__file__).parent / "fixtures" / "cards"

# design/scout-cards.md B1..B7, verbatim rows of the fixture exhibits
EXPECTED = {
    "amex": dict(
        period_end="2026-07-31", accession="0001104659-26-097714", source_file="tm2623074d1_ex99-01.htm",
        receivables_principal=24_930_085_370.00, gross_co_rate=0.018640, net_co_rate=0.011114,
        co_basis="ending", co_annualisation="x365_over_days", payment_rate=0.507944, yield_=0.317408,
        delinq_30plus_share=171_238_503 / 26_171_740_833.37,
        delinq_90plus_share=(32_094_421 + 45_924_272) / 26_171_740_833.37,
        excess_spread=None,
    ),
    "comet": dict(
        period_end="2026-07-31", accession="0001163321-26-000025", source_file="exhibit9912002-ccjuly2026.htm",
        receivables_principal=23_264_569_372.71, gross_co_rate=0.0296, net_co_rate=0.0180,
        co_basis="beginning", co_annualisation="x12", payment_rate=0.4798, yield_=0.2709,
        delinq_30plus_share=382_345_966.72 / 23_558_216_188.81,
        delinq_90plus_share=(69_632_603.08 + 61_529_720.87 + 62_710_282.09) / 23_558_216_188.81,
        excess_spread=None,
    ),
    "chase": dict(
        period_end="2026-07-31", accession="0001193125-26-353171", source_file="d169887dex992.htm;d169887dex993.htm",
        receivables_principal=11_728_896_182.88, gross_co_rate=0.0202, net_co_rate=0.0158,
        co_basis="average", co_annualisation="x12", payment_rate=0.5356, yield_=0.2441,
        delinq_30plus_share=96_066_475.94 / 11_878_609_412.54,
        delinq_90plus_share=(15_749_407.73 + 15_858_053.30 + 16_436_974.16 + 0.0) / 11_878_609_412.54,
        excess_spread=0.1663,
    ),
    "citi": dict(
        period_end="2026-07-28", accession="0001193125-26-353756", source_file="d138267dex99.htm",
        receivables_principal=19_119_983_665, gross_co_rate=0.0190, net_co_rate=None,
        co_basis="invested_amount", co_annualisation="actual_365", payment_rate=0.4384, yield_=0.2341,
        delinq_30plus_share=(76_269_089 + 57_536_794 + 48_137_590 + 40_781_279 + 42_241_217)
        / (19_406_570_793 + 252_230_180 + 76_269_089 + 57_536_794 + 48_137_590 + 40_781_279 + 42_241_217),
        delinq_90plus_share=(48_137_590 + 40_781_279 + 42_241_217)
        / (19_406_570_793 + 252_230_180 + 76_269_089 + 57_536_794 + 48_137_590 + 40_781_279 + 42_241_217),
        excess_spread=0.1683,
    ),
    "synchrony": dict(
        period_end="2026-07-31", accession="0001104659-26-097449", source_file="tm2622590d1_ex99-1.htm",
        receivables_principal=10_893_543_177.22, gross_co_rate=0.053437, net_co_rate=0.041142,
        co_basis="beginning", co_annualisation="x12", payment_rate=0.252915, yield_=0.283297,
        delinq_30plus_share=(86_159_844.94 + 65_961_598.03 + 58_196_184.32 + 49_793_308.75 + 49_779_111.10 + 0.0)
        / 11_404_850_598.69,
        delinq_90plus_share=(58_196_184.32 + 49_793_308.75 + 49_779_111.10 + 0.0) / 11_404_850_598.69,
        excess_spread=0.1657,
    ),
    "bofa": dict(
        period_end="2026-07-31", accession="0001140361-26-033313", source_file="ef20079972_ex99-1.htm",
        receivables_principal=14_216_676_954.68, gross_co_rate=0.0274, net_co_rate=0.0213,
        co_basis="average", co_annualisation="x12", payment_rate=0.2848, yield_=0.1977,
        delinq_30plus_share=(53_530_346.30 + 38_603_265.99 + 30_561_350.43 + 30_216_475.88 + 31_042_931.55 + 38_779.50)
        / 14_552_256_361.78,
        delinq_90plus_share=(30_561_350.43 + 30_216_475.88 + 31_042_931.55 + 38_779.50) / 14_552_256_361.78,
        excess_spread=0.1266,
    ),
}


def fixture_dir(slug: str) -> Path:
    return FIX / slug / EXPECTED[slug]["accession"]


@pytest.fixture(scope="module")
def parsed() -> dict[str, dict]:
    return {slug: parse_filing_dir(fixture_dir(slug), slug) for slug in EXPECTED}


@pytest.mark.parametrize("slug", sorted(EXPECTED))
def test_frozen_values(parsed, slug):
    e = EXPECTED[slug]
    r = parsed[slug]
    assert set(r) == set(COLUMNS)
    assert r["trust"] == slug
    assert r["period_end"] == e["period_end"]
    assert r["source_accession"] == e["accession"]
    assert r["source_file"] == e["source_file"]
    assert r["co_basis"] == e["co_basis"]
    assert r["co_annualisation"] == e["co_annualisation"]
    assert r["receivables_principal"] == pytest.approx(e["receivables_principal"], abs=0.01)
    for k in ("gross_co_rate", "net_co_rate", "payment_rate", "excess_spread"):
        if e[k] is None:
            assert r[k] is None, k
        else:
            assert r[k] == pytest.approx(e[k], abs=1e-9), k
    assert r["yield"] == pytest.approx(e["yield_"], abs=1e-9)
    # shares are rounded to 8 decimals in the output row, so the bound is half a unit of the 8th decimal
    assert r["delinq_30plus_share"] == pytest.approx(e["delinq_30plus_share"], abs=5e-9)
    assert r["delinq_90plus_share"] == pytest.approx(e["delinq_90plus_share"], abs=5e-9)
    assert 0 < r["delinq_90plus_share"] < r["delinq_30plus_share"] < 0.05


@pytest.mark.parametrize("slug", sorted(EXPECTED))
def test_recompute_self_check_recorded(parsed, slug):
    """Printed rate vs recomputed-from-dollars rate, within 1e-4, for every trust that prints the dollars."""
    j = json.loads(parsed[slug]["row_labels_json"])
    assert all(c.endswith(" ok") for c in j["checks"]), j["checks"]
    if slug == "citi":
        assert "gross_co_rate" not in j["recomputed"]
        assert "net_co_rate" in j["null_reasons"]
    else:
        for k in ("gross_co_rate", "net_co_rate"):
            assert abs(j["printed"][k] - j["recomputed"][k]) <= 1e-4, (k, j["printed"][k], j["recomputed"][k])
    # every null column carries a reason, every non-null rate carries the label it came from
    r = parsed[slug]
    for k in ("gross_co_rate", "net_co_rate", "payment_rate", "yield", "excess_spread"):
        if r[k] is None:
            assert k in j["null_reasons"]
        else:
            assert j["labels"].get(k), k
    assert j["edgar_period"] == r["period_end"]


def test_amex_annualisation_is_365_over_days(parsed):
    j = json.loads(parsed["amex"]["row_labels_json"])
    i = j["inputs"]
    assert i["days_in_period"] == 31
    assert i["defaulted_amount"] * 365 / 31 / i["ending_principal"] == pytest.approx(0.018640, abs=5e-7)
    # x12 on beginning principal would NOT reproduce the printed rate (design/scout-cards.md B1)
    assert abs(i["defaulted_amount"] * 12 / i["beginning_principal"] - 0.018640) > 1e-4


def test_delinquency_basis_flags_nearest_cuts(parsed):
    assert "NEAREST CUT" in parsed["citi"]["delinq_basis"]
    for slug in ("amex", "comet", "chase", "synchrony", "bofa"):
        assert "NEAREST CUT" not in parsed[slug]["delinq_basis"]
        assert "exact" in parsed[slug]["delinq_basis"]


def test_bofa_dollars_in_thousands_and_investor_rates_kept(parsed):
    i = json.loads(parsed["bofa"]["row_labels_json"])["inputs"]
    assert i["total_charge_offs_thousands"] == 32_369
    assert i["average_principal_thousands"] == 14_183_450
    assert i["investor_interest_gross_default_rate"] == pytest.approx(0.0271)


def test_wrong_trust_fails_loudly():
    with pytest.raises(ParseError):
        parse_filing_dir(fixture_dir("amex"), "chase")


def test_parse_raw_and_csv(tmp_path):
    rows, errors = parse_raw(FIX)
    assert errors == []
    assert [r["trust"] for r in rows] == sorted(EXPECTED)
    assert [d.name for _, d in filing_dirs(FIX)] == [EXPECTED[s]["accession"] for s in
                                                     ("amex", "comet", "chase", "citi", "synchrony", "bofa")]
    out = tmp_path / "cards_monthly.csv"
    write_csv(rows, out)
    back = list(csv.DictReader(open(out, newline="", encoding="utf-8")))
    assert list(back[0]) == COLUMNS
    assert back[0]["trust"] == "amex" and back[0]["excess_spread"] == ""
    assert float(back[1]["gross_co_rate"]) == pytest.approx(0.0274)
    table = coverage(rows)
    assert "2026" in table and table.count("\n") == 6


def test_cli_parse(tmp_path, capsys):
    out = tmp_path / "m.csv"
    assert main(["parse", "--raw", str(FIX), "--out", str(out)]) == 0
    assert "6 rows" in capsys.readouterr().out
    assert sum(1 for _ in open(out, encoding="utf-8")) == 7
