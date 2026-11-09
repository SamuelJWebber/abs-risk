"""Golden checks for Track B: auto loans in checks/golden.yaml traced from the EX-102 text to the committed tables.

REVIEW.md bigger improvement 8: PLAN section 4 promised golden checks for both tracks; only cards had them. Each
entry names one loan record in a fixture cut verbatim from a filing. The XML is read here with a plain regex, not
with absrisk.autos, so a parser bug cannot hide inside the expected values; the test checks that the printed text
implies the expected values, and that data/autos/<deal>.parquet carries them.
"""

from __future__ import annotations

import calendar
import re
from functools import lru_cache
from pathlib import Path

import pandas as pd
import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
FIX = REPO / "tests" / "fixtures" / "autos"
GOLDEN = yaml.safe_load((REPO / "checks" / "golden.yaml").read_text(encoding="utf-8"))["autos_loans"]
REC = re.compile(r"<assets>(.*?)</assets>", re.S)


def _field(rec: str, name: str) -> str | None:
    m = re.search(rf"<{name}>([^<]*)</{name}>", rec)
    return m.group(1).strip() if m else None


@lru_cache(maxsize=None)
def _records(deal: str, fixture: str) -> dict[str, str]:
    text = (FIX / deal / fixture).read_text(encoding="utf-8")
    return {_field(r, "assetNumber"): r for r in REC.findall(text)}


@lru_cache(maxsize=None)
def _loans(deal: str) -> pd.DataFrame:
    return pd.read_parquet(REPO / "data" / "autos" / f"{deal}.parquet").set_index("asset_id")


def _id(g: dict) -> str:
    return f"{g['deal']}-{g['asset']}-{'exit' if 'zeroBalanceCode' in g['printed'] else 'orig'}"


def _month_end(mm_yyyy: str) -> str:
    m, y = (int(x) for x in mm_yyyy.split("/"))
    return f"{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"


def test_one_origination_golden_per_committed_deal_with_a_fixture():
    orig = {g["deal"] for g in GOLDEN if "originalLoanAmount" in g["printed"]}
    with_fixture = {p.parent.name for p in FIX.glob("*/*.xml")} & {p.stem for p in (REPO / "data" / "autos").glob("*.parquet")}
    assert orig == with_fixture
    assert sum("zeroBalanceCode" in g["printed"] for g in GOLDEN) >= 2


@pytest.mark.parametrize("g", GOLDEN, ids=_id)
def test_golden_record_is_printed_in_the_filing(g):
    rec = _records(g["deal"], g["fixture"]).get(g["asset"])
    assert rec is not None, f"asset {g['asset']} not in {g['deal']}/{g['fixture']}"
    for name, printed in g["printed"].items():
        assert _field(rec, name) == printed, (name, _field(rec, name))


@pytest.mark.parametrize("g", GOLDEN, ids=_id)
def test_printed_values_imply_the_expected_ones(g):
    p, e = g["printed"], g["expect"]
    if "originalLoanAmount" in p:
        m, y = p["originationDate"].split("/")
        assert e["orig_month"] == f"{int(y):04d}-{int(m):02d}-01"
        assert float(p["originalLoanAmount"]) == pytest.approx(e["orig_amount"], abs=0.005)
        assert int(p["originalLoanTerm"]) == e["orig_term"]
        assert float(p["originalInterestRatePercentage"]) == pytest.approx(e["orig_apr"], abs=1e-9)   # a fraction as filed
        assert int(p["obligorCreditScore"]) == e["score"]
    if "zeroBalanceCode" in p:
        assert p["zeroBalanceCode"] == "4" and e["exit_type"] == "chargeoff"     # code 4: charged off
        assert e["exit_period"] == _month_end(p["zeroBalanceEffectiveDate"])
        if "chargeoff_amount" in e:
            assert float(p["chargedoffPrincipalAmount"]) == pytest.approx(e["chargeoff_amount"], abs=0.005)


@pytest.mark.parametrize("g", GOLDEN, ids=_id)
def test_committed_loans_table_carries_the_golden_record(g):
    loans = _loans(g["deal"])
    assert g["asset"] in loans.index, f"{g['asset']} not in data/autos/{g['deal']}.parquet"
    row = loans.loc[g["asset"]]
    assert row["deal"] == g["deal"]
    for k, v in g["expect"].items():
        got = row[k]
        if k in ("orig_month", "exit_period"):
            assert str(pd.Timestamp(got).date()) == v, (k, got)
        elif isinstance(v, float):
            assert float(got) == pytest.approx(v, abs=1e-6), (k, got)
        elif isinstance(v, int):
            assert int(got) == v, (k, got)
        else:
            assert str(got) == v, (k, got)
