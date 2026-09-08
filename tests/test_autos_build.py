"""build.py on the two-month fixtures (Santander, CarMax, Capital One June+July 2026) and on a synthetic file set
that exercises the exit rule's edge cases.

Expected numbers come from tests/fixtures/autos/tools/hand_count.py, an independent regex count over the fixture
text; they are frozen here rather than recomputed so a parser bug cannot move both sides."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from absrisk.autos import main
from absrisk.autos.build import LOANS_COLUMNS, LOANS_SCHEMA, build_deal, build_loans, files_from_manifest, write_loans
from absrisk.autos.deals import Deal
from absrisk.autos.parse import LOAN_MONTH_COLUMNS

FIX = Path(__file__).parent / "fixtures" / "autos"

# tools/hand_count.py output, 2026-09-08
HAND = {
    "sdart-2026-1": {"n_loans": 300, "months_observed": {1: 44, 2: 256},
                     "exit_type_counts": {"prepay": 156, "censored": 144}, "exit_code_counts": {"1": 156},
                     "n_max_dpd_ge30": 7},
    "carmax-2026-2": {"n_loans": 300, "months_observed": {2: 300},
                      "exit_type_counts": {"censored": 279, "prepay": 21}, "exit_code_counts": {"1": 21},
                      "n_max_dpd_ge30": 5},
    "copar-2025-1": {"n_loans": 300, "months_observed": {2: 300},
                     "exit_type_counts": {"censored": 249, "prepay": 51}, "exit_code_counts": {"1": 51},
                     "n_max_dpd_ge30": 0},
}
LENDER = {"sdart-2026-1": "santander", "carmax-2026-2": "carmax", "copar-2025-1": "capone"}


def two_months(slug: str) -> list[Path]:
    return [FIX / slug / "2026-06.xml", FIX / slug / "2026-07.xml"]


@pytest.fixture(scope="module")
def built():
    out = {}
    for slug, lender in LENDER.items():
        out[slug] = build_loans(Deal(slug, lender, "0001234567"), two_months(slug))
    return out


@pytest.mark.parametrize("slug", list(HAND))
def test_schema_is_exactly_analysis_plan_1a(built, slug):
    df = built[slug]
    assert list(df.columns) == LOANS_COLUMNS
    assert LOANS_COLUMNS[:34] == [
        "deal", "lender", "cik", "asset_id", "first_period", "last_period", "orig_month", "orig_amount", "orig_apr",
        "orig_term", "pti", "score", "score_type", "score_missing", "vehicle_value", "ltv", "new_used", "state",
        "income_verified", "employment_verified", "subvented", "commercial", "exit_period", "exit_type", "exit_code",
        "months_observed", "max_dpd", "first_30_period", "first_60_period", "first_90_period", "chargeoff_amount",
        "recovered_amount", "bal_first", "bal_last",
    ]
    assert LOANS_COLUMNS[34:] == ["zb_date"]  # the one addition, see build.py docstring
    assert str(df["first_period"].dtype).startswith("datetime64")
    assert str(df["score"].dtype) == "Int32" and str(df["orig_term"].dtype) == "Int32"
    assert df["commercial"].dtype == bool and df["score_missing"].dtype == bool
    assert df["orig_apr"].dtype == "float64" and df["pti"].dtype == "float64"
    assert (df["deal"] == slug).all() and (df["lender"] == LENDER[slug]).all() and (df["cik"] == "0001234567").all()


@pytest.mark.parametrize("slug", list(HAND))
def test_persistence_and_exit_rule_match_hand_count(built, slug):
    df = built[slug]
    h = HAND[slug]
    d = df.attrs["diagnostics"]
    assert len(df) == d["n_loans"] == h["n_loans"]
    assert df["asset_id"].is_unique
    assert df["months_observed"].value_counts().to_dict() == h["months_observed"]
    assert df["exit_type"].value_counts().to_dict() == h["exit_type_counts"] == d["exit_type_counts"]
    assert df["exit_code"].value_counts().to_dict() == h["exit_code_counts"] == d["exit_code_counts"]
    assert int((df["max_dpd"] >= 30).sum()) == h["n_max_dpd_ge30"]
    assert d["first_period"] == "2026-06-30" and d["last_period"] == "2026-07-31" and d["n_files"] == 2
    assert d["n_gaps"] == 0 and d["n_added_after_first_file"] == 0
    assert d["share_absent_without_code"] == 0.0  # every dropped loan carried a payoff code the month before
    assert (df["first_period"] == pd.Timestamp("2026-06-30")).all()


def test_santander_drops_payoffs_the_month_after(built):
    """scout-autos 5b: SDART reports code 1 in the payoff month and drops the loan the next month."""
    df = built["sdart-2026-1"]
    gone = df[df["last_period"] == pd.Timestamp("2026-06-30")]
    assert len(gone) == 44
    assert (gone["exit_type"] == "prepay").all() and (gone["exit_period"] == pd.Timestamp("2026-06-30")).all()
    assert (gone["exit_code"] == "1").all()
    kept = df[df["last_period"] == pd.Timestamp("2026-07-31")]
    assert kept["exit_type"].value_counts().to_dict() == {"censored": 144, "prepay": 112}
    july_exits = kept[kept["exit_type"] == "prepay"]
    assert (july_exits["exit_period"] == pd.Timestamp("2026-07-31")).all()
    assert (july_exits["zb_date"] == pd.Timestamp("2026-07-01")).all()
    assert (july_exits["bal_last"] == 0).all()


def test_keep_all_issuers_keep_closed_loans(built):
    """scout-autos 5b: CarMax and Capital One keep paid-off loans in every later file."""
    for slug in ("carmax-2026-2", "copar-2025-1"):
        df = built[slug]
        assert (df["months_observed"] == 2).all()
        closed = df[df["exit_type"] == "prepay"]
        # a loan paid off before June carries its code in both files: exit_period is the first file seen,
        # zb_date the true payoff month (build.py docstring)
        assert (closed["zb_date"] <= closed["exit_period"]).all()
        assert closed["zb_date"].min() < pd.Timestamp("2026-06-01")
        assert (closed["exit_period"] == pd.Timestamp("2026-06-30")).sum() > 0
        assert (closed["exit_period"] == pd.Timestamp("2026-07-31")).sum() > 0  # July's new payoffs


def test_static_fields_and_derived_columns(built):
    df = built["copar-2025-1"]
    assert (df["pti"] < 1).all() and 0.02 < df["pti"].median() < 0.12  # percent divided by 100
    assert df["score"].between(700, 900).all() and not df["score_missing"].any()
    assert (df["score_type"] == "FICO").all()
    assert df["ltv"].notna().all() and (df["ltv"] == df["orig_amount"] / df["vehicle_value"]).all()
    assert df["orig_month"].dt.day.eq(1).all()
    assert (df["orig_apr"] < 0.3).all()
    assert df["state"].str.len().eq(2).all()
    assert not df["commercial"].any()
    sd = built["sdart-2026-1"]
    assert sd["score_missing"].sum() == 1 and sd.loc[sd["score_missing"], "score"].isna().all()
    assert sd["subvented"].value_counts().to_dict() == {"0": 56, "1": 243, "98": 1}


def test_write_loans_parquet_roundtrip(built, tmp_path):
    df = built["sdart-2026-1"]
    pq_path, js_path = write_loans(df, tmp_path, "sdart-2026-1")
    t = pq.read_table(pq_path)
    assert t.schema.names == LOANS_COLUMNS
    assert t.schema.equals(LOANS_SCHEMA)
    assert t.num_rows == 300
    assert t.column("exit_period").to_pylist()[0] in (None, date(2026, 6, 30), date(2026, 7, 31))
    back = pd.read_parquet(pq_path)
    assert back["exit_type"].value_counts().to_dict() == HAND["sdart-2026-1"]["exit_type_counts"]
    diag = json.loads(js_path.read_text(encoding="utf-8"))
    assert diag["n_loans"] == 300 and diag["exit_type_counts"] == HAND["sdart-2026-1"]["exit_type_counts"]
    assert diag["files"][0]["period"] == "2026-06-30" and diag["files"][0]["sha256"]
    assert diag["retention_rule"].startswith("keeps charge-offs")


def test_loan_months_parquet_has_exactly_1b_columns(tmp_path):
    df = build_loans(Deal("carmax-2026-2", "carmax"), two_months("carmax-2026-2"), loan_months_dir=tmp_path / "lm")
    files = sorted((tmp_path / "lm").glob("*.parquet"))
    assert [f.name for f in files] == ["2026-06-30.parquet", "2026-07-31.parquet"]
    t = pq.read_table(files[0])
    assert t.schema.names == LOAN_MONTH_COLUMNS
    assert t.num_rows == 300
    assert str(t.schema.field("period").type) == "date32[day]"
    assert t.column("dpd").null_count == 16  # CarMax omits delinquency for zero-balance loans (scout-autos 6.6)
    assert df.attrs["diagnostics"]["n_loan_months"] == 600


def _synthetic(tmp_path: Path) -> list[Path]:
    """Four loans over three months to pin the exit rule's branches (analysis-plan 1a):
    A: code 4 in month 2 and still present in month 3 -> chargeoff, exit month 2
    B: present months 1-2, absent month 3, never a code -> absent, exit month 2
    C: present month 1, absent month 2, back in month 3 with code 3 -> the earlier event wins: absent, exit month 1
    D: present all three months, no code -> censored
    E: appears in month 2 with code 99 -> other, exit month 2 (added after the first file)
    """
    def rec(aid, period, extra="", dpd=0):
        return (f"<assets><assetNumber>{aid}</assetNumber><reportingPeriodEndingDate>{period}</reportingPeriodEndingDate>"
                f"<originationDate>01/2024</originationDate><originalLoanAmount>1000</originalLoanAmount>"
                f"<originalLoanTerm>60</originalLoanTerm><originalInterestRatePercentage>0.1</originalInterestRatePercentage>"
                f"<obligorCreditScoreType>Bureau</obligorCreditScoreType><obligorCreditScore>650</obligorCreditScore>"
                f"<paymentToIncomePercentage>0.1</paymentToIncomePercentage><vehicleValueAmount>0</vehicleValueAmount>"
                f"<reportingPeriodActualEndBalanceAmount>900</reportingPeriodActualEndBalanceAmount>"
                f"<currentDelinquencyStatus>{dpd}</currentDelinquencyStatus>{extra}</assets>")

    months = {
        "01-31-2026": [rec("A", "01-31-2026"), rec("B", "01-31-2026"), rec("C", "01-31-2026"), rec("D", "01-31-2026")],
        "02-28-2026": [rec("A", "02-28-2026", "<zeroBalanceCode>4</zeroBalanceCode><zeroBalanceEffectiveDate>02/2026</zeroBalanceEffectiveDate><chargedoffPrincipalAmount>800</chargedoffPrincipalAmount>"),
                       rec("B", "02-28-2026", dpd=45), rec("D", "02-28-2026"),
                       rec("E", "02-28-2026", "<zeroBalanceCode>99</zeroBalanceCode>")],
        "03-31-2026": [rec("A", "03-31-2026", "<zeroBalanceCode>4</zeroBalanceCode><recoveredAmount>50</recoveredAmount>"),
                       rec("C", "03-31-2026", "<zeroBalanceCode>3</zeroBalanceCode>"), rec("D", "03-31-2026")],
    }
    paths = []
    for i, (p, recs) in enumerate(months.items()):
        f = tmp_path / f"m{i}.xml"
        f.write_text('<?xml version="1.0"?><assetData xmlns="http://www.sec.gov/edgar/document/absee/autoloan/assetdata">'
                     + "".join(recs) + "</assetData>", encoding="utf-8")
        paths.append(f)
    return paths


def test_exit_rule_edge_cases(tmp_path):
    paths = _synthetic(tmp_path)
    df = build_loans(Deal("syn", "santander"), list(reversed(paths))).set_index("asset_id")  # order is fixed by period
    assert df.loc["A", "exit_type"] == "chargeoff" and df.loc["A", "exit_period"] == pd.Timestamp("2026-02-28")
    assert df.loc["A", "exit_code"] == "4" and df.loc["A", "chargeoff_amount"] == 800 and df.loc["A", "recovered_amount"] == 50
    assert df.loc["A", "months_observed"] == 3 and df.loc["A", "zb_date"] == pd.Timestamp("2026-02-01")
    assert df.loc["B", "exit_type"] == "absent" and df.loc["B", "exit_period"] == pd.Timestamp("2026-02-28")
    assert pd.isna(df.loc["B", "exit_code"]) and df.loc["B", "max_dpd"] == 45
    assert df.loc["B", "first_30_period"] == pd.Timestamp("2026-02-28") and pd.isna(df.loc["B", "first_60_period"])
    assert df.loc["C", "exit_type"] == "absent" and df.loc["C", "exit_period"] == pd.Timestamp("2026-01-31")
    assert df.loc["D", "exit_type"] == "censored" and pd.isna(df.loc["D", "exit_period"])
    assert df.loc["E", "exit_type"] == "other" and df.loc["E", "exit_code"] == "99"
    assert df.loc["E", "first_period"] == pd.Timestamp("2026-02-28")
    assert df["ltv"].isna().all()  # vehicle value 0 -> null
    diag = build_loans(Deal("syn", "santander"), paths).attrs["diagnostics"]
    assert diag["exit_type_counts"] == {"chargeoff": 1, "absent": 2, "censored": 1, "other": 1}
    assert diag["n_absent_without_code"] == 2 and diag["share_absent_without_code"] == 0.4
    assert diag["n_gaps"] == 1 and diag["n_added_after_first_file"] == 1


def test_same_period_twice_fails_loudly(tmp_path):
    f = FIX / "carmax-2026-2" / "2026-06.xml"
    with pytest.raises(ValueError, match="share period"):
        build_loans(Deal("carmax-2026-2", "carmax"), [f, f])


def test_build_deal_from_manifest_and_cli(tmp_path):
    """build_deal reads the fetcher's manifest, skips the offering pool, and the CLI wires it."""
    raw = tmp_path / "raw" / "carmax-2026-2"
    for acc, period, name in [("A-1", "2026-05-31", "pool.xml"), ("A-2", "2026-06-30", "cart20262.xml"),
                              ("A-3", "2026-07-31", "cart20262.xml")]:
        (raw / acc).mkdir(parents=True)
        src = FIX / "carmax-2026-2" / ("2026-06.xml" if period != "2026-07-31" else "2026-07.xml")
        (raw / acc / name).write_bytes(src.read_bytes())
    manifest = {"deal": "carmax-2026-2", "filings": [
        {"accession": "A-1", "period": "2026-05-31", "file": "A-1/pool.xml", "offering_pool": True},
        {"accession": "A-3", "period": "2026-07-31", "file": "A-3/cart20262.xml", "offering_pool": False},
        {"accession": "A-2", "period": "2026-06-30", "file": "A-2/cart20262.xml", "offering_pool": False},
    ]}
    (raw / "manifest.json").write_text(json.dumps(manifest))
    files = files_from_manifest(raw)
    assert [f.parent.name for f in files] == ["A-2", "A-3"]
    assert [f.parent.name for f in files_from_manifest(raw, include_offering_pool=True)] == ["A-1", "A-2", "A-3"]

    deals_csv = tmp_path / "deals.csv"
    deals_csv.write_text("deal,lender,cik,doc_prefix,name,depositor_cik,notes\n"
                         "carmax-2026-2,carmax,0002117307,,CarMax Auto Owner Trust 2026-2,,\n")
    rc = main(["build", "--deal", "carmax-2026-2", "--raw", str(tmp_path / "raw"), "--out", str(tmp_path / "out"),
               "--deals", str(deals_csv), "--loan-months", "--panel", str(tmp_path / "panel")])
    assert rc == 0
    t = pq.read_table(tmp_path / "out" / "carmax-2026-2.parquet")
    assert t.num_rows == 300 and t.schema.names == LOANS_COLUMNS
    assert (tmp_path / "out" / "carmax-2026-2.diagnostics.json").exists()
    assert sorted(p.name for p in (tmp_path / "panel" / "carmax-2026-2").glob("*.parquet")) == ["2026-06-30.parquet", "2026-07-31.parquet"]
    df = build_deal(Deal("carmax-2026-2", "carmax", "0002117307"), tmp_path / "raw", tmp_path / "out2")
    assert df.attrs["diagnostics"]["n_files"] == 2
