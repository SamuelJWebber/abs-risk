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

from datetime import date

from absrisk.cards import main
from absrisk.cards.parse import (
    AMEX_BEG_PRIN,
    CITI_FC_END,
    COLUMNS,
    Filing,
    ParseError,
    coverage,
    filing_dirs,
    parse_filing_dir,
    parse_raw,
    write_csv,
)
from absrisk.cards.tables import (
    Row,
    find_first,
    find_row,
    is_number_cell,
    join_wrapped,
    normalise,
    parse_date,
    strip_footnote,
)

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


# ---------------------------------------------------------------------------------------------
# Historical layout variants (design/cards-build.md, "Historical layout variants").
#
# One fixture per variant the parsers learned to read, copied whole from the 2019-2026 10-D corpus
# (`<slug>/<accession>/`, none over 5 MB so none is trimmed). They live under
# tests/fixtures/cards/historical/ so the six July-2026 fixtures above stay the only filings that
# `filing_dirs(FIX)` and the CLI tests see. Expected numbers are read off the fixture exhibit: rates
# are the printed percentages, delinquency shares the printed dollar rows over the printed
# denominator, exactly as EXPECTED above.

HIST = FIX / "historical"

HISTORICAL = {
    # --- Amex: the "Beginning Principal Receivable Balance, including any Additions, Removals, or
    # Adjustments of Principal Receivables during the Monthly Period" label wraps across up to three
    # <tr>s and the RR Donnelley template puts the number on whichever of them the wrap reached.
    "amex/0001193125-23-167627": dict(
        variant="amex label over 3 rows, number on the last",
        trust="amex", period_end="2023-05-31", source_file="d505830dex9901.htm",
        receivables_principal=26_354_990_068.68, gross_co_rate=0.015417, net_co_rate=0.010264,
        payment_rate=0.483131, yield_=0.290450, excess_spread=None,
        delinq_30plus_share=(54_798_571 + 36_653_631 + 33_856_305 + 48_326_485) / 27_686_720_852.55,
        delinq_90plus_share=(33_856_305 + 48_326_485) / 27_686_720_852.55,
        beginning_principal=26_084_238_625.84,
    ),
    "amex/0001193125-22-075677": dict(
        variant="amex label over 2 rows, number on the last",
        trust="amex", period_end="2022-02-28", source_file="d331218dex9901.htm",
        receivables_principal=24_202_773_571.89, gross_co_rate=0.013934, net_co_rate=0.008120,
        payment_rate=0.486748, yield_=0.286925, excess_spread=None,
        delinq_30plus_share=(45_016_252 + 27_902_104 + 23_560_288 + 36_914_521) / 25_193_096_460.11,
        delinq_90plus_share=(23_560_288 + 36_914_521) / 25_193_096_460.11,
        beginning_principal=24_432_764_658.33,
    ),
    "amex/0001193125-22-285473": dict(
        variant="amex label over 3 rows, number on the middle one",
        trust="amex", period_end="2022-10-31", source_file="d418888dex9901.htm",
        receivables_principal=26_001_655_865.57, gross_co_rate=0.011512, net_co_rate=0.006508,
        payment_rate=0.463166, yield_=0.275005, excess_spread=None,
        delinq_30plus_share=(51_575_747 + 33_520_437 + 26_236_445 + 36_402_373) / 27_181_607_511.02,
        delinq_90plus_share=(26_236_445 + 36_402_373) / 27_181_607_511.02,
        beginning_principal=25_577_299_616.32,
    ),
    "amex/0001193125-24-095520": dict(
        variant="amex label over 2 rows, number on the first (label continues after the number)",
        trust="amex", period_end="2024-03-31", source_file="d743992dex9901.htm",
        receivables_principal=25_897_054_632.53, gross_co_rate=0.019183, net_co_rate=0.013826,
        payment_rate=0.473313, yield_=0.299416, excess_spread=None,
        delinq_30plus_share=(69_686_474 + 49_607_373 + 39_984_376 + 61_074_236) / 27_325_077_670.84,
        delinq_90plus_share=(39_984_376 + 61_074_236) / 27_325_077_670.84,
        beginning_principal=25_412_846_674.27,
    ),
    # --- Citi: "Finance Charge Receivables&#151;End of Due Period" (cp1252 em dash as a numeric
    # character reference) and "Finance Charge Receivables-End of Due Period" (no spaces).
    "citi/0001193125-19-009574": dict(
        variant="citi finance-charge label with &#151; and no spaces around the dash",
        trust="citi", period_end="2018-12-26", source_file="d689236dex99.htm",
        receivables_principal=40_064_618_633, gross_co_rate=0.0255, net_co_rate=None,
        payment_rate=0.2723, yield_=0.2024, excess_spread=0.1476,
        delinq_30plus_share=(170_396_940 + 140_804_989 + 122_413_385 + 100_747_543 + 97_107_600)
        / (39_053_672_110 + 607_868_977 + 170_396_940 + 140_804_989 + 122_413_385 + 100_747_543 + 97_107_600),
        delinq_90plus_share=(122_413_385 + 100_747_543 + 97_107_600)
        / (39_053_672_110 + 607_868_977 + 170_396_940 + 140_804_989 + 122_413_385 + 100_747_543 + 97_107_600),
        finance_charge_receivables_end=491_301_073,
    ),
    "citi/0001193125-26-304533": dict(
        variant="citi finance-charge label written 'Receivables-End of Due Period'",
        trust="citi", period_end="2026-06-25", source_file="d347998dex99.htm",
        receivables_principal=19_165_697_102, gross_co_rate=0.0225, net_co_rate=None,
        payment_rate=0.4193, yield_=0.2464, excess_spread=0.1771,
        delinq_30plus_share=(74_558_348 + 55_824_914 + 49_227_351 + 44_511_392 + 39_048_865)
        / (19_650_337_445 + 229_166_540 + 74_558_348 + 55_824_914 + 49_227_351 + 44_511_392 + 39_048_865),
        delinq_90plus_share=(49_227_351 + 44_511_392 + 39_048_865)
        / (19_650_337_445 + 229_166_540 + 74_558_348 + 55_824_914 + 49_227_351 + 44_511_392 + 39_048_865),
        finance_charge_receivables_end=962_086_767,
    ),
    "citi/0001193125-22-221038": dict(
        variant="citi delinquency column rounded to 100.00% with the residual in 151-180, not Current",
        trust="citi", period_end="2022-07-26", source_file="d351916dex99.htm",
        receivables_principal=24_202_377_002, gross_co_rate=0.0119, net_co_rate=None,
        payment_rate=0.3564, yield_=0.1989, excess_spread=0.1557,
        delinq_30plus_share=(58_025_152 + 43_357_559 + 33_379_672 + 28_360_966 + 29_862_527)
        / (24_043_600_143 + 195_677_761 + 58_025_152 + 43_357_559 + 33_379_672 + 28_360_966 + 29_862_527),
        delinq_90plus_share=(33_379_672 + 28_360_966 + 29_862_527)
        / (24_043_600_143 + 195_677_761 + 58_025_152 + 43_357_559 + 33_379_672 + 28_360_966 + 29_862_527),
        finance_charge_receivables_end=254_300_544,
    ),
    # --- Chase: "Yield&#151;Finance Charge..." / "Yield-Finance Charge...", the wrapped item 6a, and
    # the payment-rate denominator (Average Pool Balance, which differs from the beginning balance
    # whenever the pool changes size mid-month).
    "chase/0001193125-21-117038": dict(
        variant="chase EX-99.3 yield label with &#151;",
        trust="chase", period_end="2021-03-31", source_file="d158147dex992.htm;d158147dex993.htm",
        receivables_principal=10_446_982_909.80, gross_co_rate=0.0269, net_co_rate=0.0203,
        payment_rate=0.4435, yield_=0.2207, excess_spread=0.1759,
        delinq_30plus_share=(25_578_880.25 + 18_930_324.26 + 16_893_241.17 + 16_211_949.30
                             + 17_404_961.36 + 0.0) / 10_691_563_753.53,
        delinq_90plus_share=(16_893_241.17 + 16_211_949.30 + 17_404_961.36 + 0.0) / 10_691_563_753.53,
        average_pool_balance=10_486_186_366.77,
    ),
    "chase/0001193125-26-013472": dict(
        variant="chase EX-99.3 yield label written 'Yield-Finance Charge, Fees & Interchange'",
        trust="chase", period_end="2025-12-31", source_file="d11799dex992.htm;d11799dex993.htm",
        receivables_principal=12_687_099_115.56, gross_co_rate=0.0195, net_co_rate=0.0159,
        payment_rate=0.5299, yield_=0.2496, excess_spread=0.1712,
        delinq_30plus_share=(31_749_388.85 + 22_978_002.60 + 18_064_498.64 + 18_162_910.62
                             + 17_179_571.93 + 59_440.22) / 12_850_274_707.51,
        delinq_90plus_share=(18_064_498.64 + 18_162_910.62 + 17_179_571.93 + 59_440.22) / 12_850_274_707.51,
        average_pool_balance=12_330_849_254.18,
    ),
    "chase/0001193125-20-144605": dict(
        variant="chase EX-99.2 item 6a label wrapped over two rows",
        trust="chase", period_end="2020-04-30", source_file="d931347dex992.htm;d931347dex993.htm",
        receivables_principal=11_840_852_443.04, gross_co_rate=0.0277, net_co_rate=0.0243,
        payment_rate=0.3214, yield_=0.1669, excess_spread=0.1120,
        delinq_30plus_share=(49_463_265.69 + 32_558_781.72 + 25_640_630.64 + 23_066_771.34
                             + 23_074_518.82 + 0.0) / 12_122_884_120.19,
        delinq_90plus_share=(25_640_630.64 + 23_066_771.34 + 23_074_518.82 + 0.0) / 12_122_884_120.19,
        average_pool_balance=12_876_414_724.63, principal_collections=4_138_454_898.09,
    ),
    "chase/0001193125-24-068525": dict(
        variant="chase payment rate on Average Pool Balance, which is not the beginning balance",
        trust="chase", period_end="2024-02-29", source_file="d785120dex992.htm;d785120dex993.htm",
        receivables_principal=12_603_990_267.64, gross_co_rate=0.0180, net_co_rate=0.0158,
        payment_rate=0.4599, yield_=0.2531, excess_spread=0.1758,
        delinq_30plus_share=(29_671_354.53 + 22_588_144.73 + 17_886_156.72 + 16_552_272.40
                             + 15_835_147.54 + 0.0) / 12_869_569_519.86,
        delinq_90plus_share=(17_886_156.72 + 16_552_272.40 + 15_835_147.54 + 0.0) / 12_869_569_519.86,
        average_pool_balance=9_692_388_151.01, principal_collections=4_457_843_039.87,
    ),
    # --- BofA: the footnote dagger on item 2 amounts, the three renderings of the item 6(b) label,
    # the charge-off table header without a space after the comma, and the 180+ percentage printed
    # without its "%" sign.
    "bofa/0001128250-19-000003": dict(
        variant="bofa item 2 amounts carry a footnote dagger; '(b) 60 + -Day Delinquency Rate'",
        trust="bofa", period_end="2018-12-31", source_file="ex99_1.htm",
        receivables_principal=29_034_121_756.60, gross_co_rate=0.0309, net_co_rate=0.0262,
        payment_rate=0.1861, yield_=0.1761, excess_spread=0.1103,
        delinq_30plus_share=(147_410_058.47 + 106_235_979.34 + 91_584_989.07 + 80_548_959.92
                             + 76_615_354.00 + 0.0) / 29_906_193_132.67,
        delinq_90plus_share=(91_584_989.07 + 80_548_959.92 + 76_615_354.00 + 0.0) / 29_906_193_132.67,
        beginning_principal=28_776_718_144.36,
    ),
    "bofa/0001128250-22-000081": dict(
        variant="bofa 180+ delinquency percentage printed without its % sign",
        trust="bofa", period_end="2022-06-30", source_file="ex99_1.htm",
        receivables_principal=13_645_535_428.66, gross_co_rate=0.0187, net_co_rate=0.0123,
        payment_rate=0.2762, yield_=0.1860, excess_spread=0.1408,
        delinq_30plus_share=(35_754_311.08 + 23_901_308.12 + 20_776_314.41 + 19_611_423.71
                             + 17_785_549.93 + 0.0) / 13_980_865_143.80,
        delinq_90plus_share=(20_776_314.41 + 19_611_423.71 + 17_785_549.93 + 0.0) / 13_980_865_143.80,
        beginning_principal=13_575_981_879.78,
    ),
    "bofa/0001128250-23-000057": dict(
        variant="bofa charge-off table headed 'March 31,2023' (no space after the comma)",
        trust="bofa", period_end="2023-03-31", source_file="ex99_1.htm",
        receivables_principal=13_653_082_091.07, gross_co_rate=0.0249, net_co_rate=0.0192,
        payment_rate=0.2753, yield_=0.2068, excess_spread=0.1504,
        delinq_30plus_share=(51_995_739.16 + 33_417_289.74 + 27_469_217.27 + 24_678_047.29
                             + 23_696_681.01 + 0.0) / 13_988_743_546.27,
        delinq_90plus_share=(27_469_217.27 + 24_678_047.29 + 23_696_681.01 + 0.0) / 13_988_743_546.27,
        beginning_principal=13_767_393_198.72, average_principal_thousands=13_595_884.0,
    ),
    "bofa/0001140361-25-038170": dict(
        variant="bofa '(b) 60 +- Day Delinquency Rate'",
        trust="bofa", period_end="2025-09-30", source_file="ef20056793_ex99-1.htm",
        receivables_principal=14_562_602_440.73, gross_co_rate=0.0304, net_co_rate=0.0246,
        payment_rate=0.2677, yield_=0.1960, excess_spread=0.1195,
        delinq_30plus_share=(58_280_452.97 + 42_410_271.28 + 35_227_093.03 + 33_063_259.90
                             + 31_390_052.27 + 0.0) / 14_927_804_286.20,
        delinq_90plus_share=(35_227_093.03 + 33_063_259.90 + 31_390_052.27 + 0.0) / 14_927_804_286.20,
        beginning_principal=14_656_367_920.30,
    ),
    # --- Synchrony: the rate header and its "i. Current" sub-row in two separate <table>s, and a
    # period date printed with a space inside it.
    "synchrony/0001104659-22-023437": dict(
        variant="synchrony rate header and 'i. Current' sub-row in separate tables",
        trust="synchrony", period_end="2022-01-31", source_file="tm225786d1_ex99-1.htm",
        receivables_principal=7_058_793_714.11, gross_co_rate=0.026355, net_co_rate=0.018508,
        payment_rate=0.252028, yield_=0.249135, excess_spread=0.1679,
        delinq_30plus_share=(37_182_147.59 + 27_812_112.14 + 22_360_054.85 + 18_876_147.75
                             + 15_711_952.14 + 0.0) / 7_273_073_246.58,
        delinq_90plus_share=(22_360_054.85 + 18_876_147.75 + 15_711_952.14 + 0.0) / 7_273_073_246.58,
        bop_principal=7_751_789_739.79,
    ),
    "synchrony/0001104659-20-022186": dict(
        variant="synchrony 'Monthly Period Ending: | 01 /31/2020' (space inside the date)",
        trust="synchrony", period_end="2020-01-31", source_file="tm207282d1_ex99-1.htm",
        receivables_principal=7_187_320_601.24, gross_co_rate=0.045007, net_co_rate=0.037777,
        payment_rate=0.218810, yield_=0.252185, excess_spread=0.1656,
        delinq_30plus_share=(55_802_503.42 + 41_592_855.32 + 35_716_352.10 + 33_414_314.62
                             + 28_358_318.90 + 0.0) / 7_487_729_309.34,
        delinq_90plus_share=(35_716_352.10 + 33_414_314.62 + 28_358_318.90 + 0.0) / 7_487_729_309.34,
        bop_principal=7_564_922_713.94,
    ),
}


@pytest.fixture(scope="module")
def historical() -> dict[str, dict]:
    return {k: parse_filing_dir(HIST / k, v["trust"]) for k, v in HISTORICAL.items()}


@pytest.mark.parametrize("key", sorted(HISTORICAL))
def test_historical_variant_frozen_values(historical, key):
    """Every historical layout variant parses, and to the numbers printed in that filing."""
    e, r = HISTORICAL[key], historical[key]
    assert set(r) == set(COLUMNS)
    assert (r["trust"], r["period_end"], r["source_accession"], r["source_file"]) == (
        e["trust"], e["period_end"], key.split("/")[1], e["source_file"])
    assert r["receivables_principal"] == pytest.approx(e["receivables_principal"], abs=0.01)
    for k in ("gross_co_rate", "net_co_rate", "payment_rate", "excess_spread"):
        if e[k] is None:
            assert r[k] is None, k
        else:
            assert r[k] == pytest.approx(e[k], abs=1e-9), k
    assert r["yield"] == pytest.approx(e["yield_"], abs=1e-9)
    assert r["delinq_30plus_share"] == pytest.approx(e["delinq_30plus_share"], abs=5e-9)
    assert r["delinq_90plus_share"] == pytest.approx(e["delinq_90plus_share"], abs=5e-9)
    j = json.loads(r["row_labels_json"])
    assert all(c.endswith(" ok") for c in j["checks"]), j["checks"]
    for k, v in e.items():   # any input the variant is about (denominators, wrapped-label numbers)
        if k in j["inputs"]:
            assert j["inputs"][k] == pytest.approx(v, abs=0.01), k


def test_historical_fixtures_are_separate_from_the_july_2026_set():
    """The historical fixtures must not leak into the six-filing fixture root the CLI tests use."""
    assert [d.name for _, d in filing_dirs(FIX)] == [EXPECTED[s]["accession"] for s in
                                                     ("amex", "comet", "chase", "citi", "synchrony", "bofa")]
    rows, errors = parse_raw(HIST)
    assert errors == []
    assert len(rows) == len(HISTORICAL)
    assert {(r["trust"], r["source_accession"]) for r in rows} == {
        (v["trust"], k.split("/")[1]) for k, v in HISTORICAL.items()}


def test_amex_wrapped_beginning_balance_label_is_verified(historical):
    """All four Amex wrap shapes produce the same complete label and the number the filing prints."""
    for key in ("amex/0001193125-23-167627", "amex/0001193125-22-075677",
                "amex/0001193125-22-285473", "amex/0001193125-24-095520"):
        i = json.loads(historical[key]["row_labels_json"])["inputs"]
        assert i["beginning_principal"] == pytest.approx(HISTORICAL[key]["beginning_principal"], abs=0.01)
        # x365/days on the ending balance still reproduces the printed gross rate in every shape
        assert i["defaulted_amount"] * 365 / i["days_in_period"] / i["ending_principal"] == pytest.approx(
            historical[key]["gross_co_rate"], abs=1e-6)


def test_amex_wrapped_label_join_must_match_the_full_label():
    """join_wrapped refuses a join that does not reproduce the whole label."""
    f = Filing(HIST / "amex/0001193125-23-167627", "amex")
    ex = f.find_exhibit(r"Trust Totals", r"Annualized Default Rate, Net of Recoveries", r"Monthly Payment Rate")
    rs = f.rows(ex)
    row = find_row(rs, AMEX_BEG_PRIN[0], table=find_row(rs, r"^Number of days in Monthly Period").table)
    assert not row.numbers()                      # the anchor row carries no number in this filing
    assert join_wrapped(rs, row, AMEX_BEG_PRIN[1]).first() == pytest.approx(26_084_238_625.84, abs=0.01)
    with pytest.raises(ParseError):
        join_wrapped(rs, row, r"^Ending Principal Receivables Balance$")
    with pytest.raises(ParseError):               # not enough rows to complete the label
        join_wrapped(rs, row, AMEX_BEG_PRIN[1], max_rows=1)


def test_chase_payment_rate_denominator_is_the_average_pool_balance(historical):
    """Feb-2024: the pool grew mid-month, so beginning != average and only average reproduces 45.99%."""
    r = historical["chase/0001193125-24-068525"]
    i = json.loads(r["row_labels_json"])["inputs"]
    assert i["beginning_principal"] != pytest.approx(i["average_pool_balance"], abs=1.0)
    assert i["principal_collections"] / i["average_pool_balance"] == pytest.approx(0.4599, abs=1e-4)
    assert abs(i["principal_collections"] / i["beginning_principal"] - 0.4599) > 1e-2


def test_bofa_footnote_dagger_is_stripped_from_the_amount(historical):
    """Dec-2018 prints '$ | 28,776,718,144.36 <sup>&#8224;</sup>' for item 2(b)."""
    i = json.loads(historical["bofa/0001128250-19-000003"]["row_labels_json"])["inputs"]
    assert i["beginning_principal"] == pytest.approx(28_776_718_144.36, abs=0.01)
    assert i["ending_total_receivables"] == pytest.approx(29_906_193_132.67, abs=0.01)


@pytest.mark.parametrize("key,carrier", [("bofa/0001128250-19-000003", "30-59"),
                                         ("bofa/0001128250-23-000057", "30-59"),
                                         ("bofa/0001140361-25-038170", "no row"),
                                         ("citi/0001193125-22-221038", "151-180 days delinquent"),
                                         ("citi/0001193125-19-009574", "Current")])
def test_printed_delinquency_column_is_reproduced_exactly(historical, key, carrier):
    """The printed percentage column equals the half-up rounding of the dollar shares with the
    column's leftover unit in exactly one row - checked, not tolerated."""
    checks = json.loads(historical[key]["row_labels_json"])["checks"]
    line = next(c for c in checks if c.startswith("delinq_rounding:"))
    assert f"carried by {carrier}" in line, line


def test_bofa_missing_percent_sign_is_recorded(historical):
    notes = json.loads(historical["bofa/0001128250-22-000081"]["row_labels_json"])["notes"]
    assert "without its % sign" in notes["delinq_180+"]
    assert "delinq_180+" not in json.loads(
        historical["bofa/0001128250-23-000057"]["row_labels_json"])["notes"]


def test_dates_with_internal_spacing_parse():
    """Formatting only: a missing space after the comma, and a space inside a numeric date."""
    assert parse_date("March 31,2023") == date(2023, 3, 31)
    assert parse_date("01 /31/2020") == date(2020, 1, 31)
    assert parse_date("02 /29/2020") == date(2020, 2, 29)
    assert parse_date("July 31, 2026") == date(2026, 7, 31)
    with pytest.raises(ParseError):
        parse_date("no date here")


def test_cp1252_numeric_references_and_footnotes_normalise():
    """&#151; (cp1252 em dash) reaches lxml as U+0097; a dagger hanging off a number is dropped."""
    assert normalise("ReceivablesEnd") == "Receivables-End"
    assert normalise("YieldFinance") == "Yield-Finance"
    assert strip_footnote("28,776,718,144.36 †") == "28,776,718,144.36"
    assert strip_footnote("0.30% †") == "0.30%"
    assert strip_footnote("Total*") == "Total*"        # not a number once the mark is removed
    assert not is_number_cell("28,776,718,144.36 †")      # the mark is dropped when cells are built,
    assert is_number_cell(strip_footnote("28,776,718,144.36 †"))   # not inside is_number_cell


def test_find_first_tries_variants_in_order_and_fails_loudly():
    rs = [Row(0, 0, ["Finance Charge Receivables-End of Due Period", "$", "962,086,767"])]
    assert find_first(rs, CITI_FC_END).dollars() == 962_086_767
    with pytest.raises(ParseError):
        find_first(rs, (r"^Nothing Like This$", r"^Nor This$"))
