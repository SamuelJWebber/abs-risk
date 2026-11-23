"""Reviews abs-A-4, abs-A-5, abs-A-7, abs-B-3 and abs-B-5:

- abs-A-7: no hazard is estimated from a risk set under `survival.MIN_RISK_SET` = 50 loans (`survival._curves` and
  `lender_gap.group_life_tables`). A single event in a tiny early or late risk set cannot jump the Aalen-Johansen or
  Kaplan-Meier curve.
- abs-A-4: cells whose first observed age (with at least `MIN_RISK_SET` loans at risk) is past `survival.MAX_FIRST_AGE`
  = 6 months (Capital One 11, Toyota 9, Honda 7 after the pool offset; against 3 to 5 at Exeter, CarMax, Santander and
  AmeriCredit) have their cumulative rates blanked on the autos page (`lender_gap.blank_late_entry_cells`) and are
  excluded from `usable_cells(at, cif=cif)` rather than printed as full 12- or 24-month rates.
- abs-A-5 and abs-B-3: the autos and conclusions pages and `design/methods.md` disclose the prospectus shelf-selection
  rules (CarMax CAOT selected from its core portfolio with FICO >= 650 while non-core / lower-credit obligors go to
  CarMax Select; Exeter EART pools since 2025-2 excluding bureau score >= 640 and proprietary score >= 240, which go
  to Exeter Select), Exeter's 20-point VantageScore-over-FICO gap (582 vs 562 weighted average), and CarMax's
  co-borrower score averaging (proven on the committed CarMax 2026-2 XML fixture).
"""

from __future__ import annotations

import re
from html import unescape
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from absrisk.autos.parse import iter_records, score_value
from absrisk.estimate import lender_gap, survival
from absrisk.estimate.lender_gap import blank_late_entry_cells, first_age_table, usable_cells

REPO = Path(__file__).resolve().parents[1]
AUTOS = REPO / "data" / "results" / "autos"
FIX = REPO / "tests" / "fixtures" / "autos"


def _deal_at_age(n: int, entry_age: int, n_co: int = 0, lender: str = "a", score: int = 700,
                 pool_offset: int = 0) -> pd.DataFrame:
    """n loans entering at `entry_age` (before `pool_offset`), observed for 16 months, with `n_co` charging off in the
    first month they count in the risk set."""
    first = pd.Timestamp("2025-01-31")
    orig = (first.to_period("M") - entry_age).to_timestamp()
    d = pd.DataFrame({
        "deal": f"{lender}-1", "lender": lender,
        "asset_id": [f"{lender}-{entry_age}-{i}" for i in range(n)],
        "score": score, "orig_month": orig, "first_period": first,
        "last_period": pd.Timestamp("2026-04-30"), "months_observed": 16,
        "exit_type": "censored", "exit_period": pd.NaT, "zb_date": pd.NaT,
    })
    if n_co > 0:
        d.loc[:n_co - 1, "exit_type"] = "chargeoff"
        co_month = (first.to_period("M") + pool_offset).to_timestamp(how="end").normalize()
        d.loc[:n_co - 1, "exit_period"] = co_month
    return d


def test_min_risk_set_suppresses_hazard_from_thin_early_risk_set():
    """abs-A-7: 29 early entrants with 1 default at age 5 must not add a 1/29 jump before 2,000 loans enter at age 6."""
    thin_early = _deal_at_age(29, entry_age=5, n_co=1, lender="amcar", score=480)
    main_wave = _deal_at_age(2000, entry_age=6, n_co=20, lender="amcar", score=480)
    loans = pd.concat([thin_early, main_wave], ignore_index=True)
    loans["score_b"] = survival.score_bucket(loans["score"])

    cif_guarded = survival.cumulative_incidence(loans, by=["lender", "score_b"], horizon=12, pool_offset=0)
    cif_unguarded = survival.cumulative_incidence(loans, by=["lender", "score_b"], horizon=12, pool_offset=0,
                                                  min_risk_set=1)
    age5_g = cif_guarded[cif_guarded["age"] == 5].iloc[0]
    age5_u = cif_unguarded[cif_unguarded["age"] == 5].iloc[0]
    assert age5_g["at_risk"] == 29 and age5_g["d_chargeoff"] == 1
    assert age5_g["aj_chargeoff"] == 0.0 and age5_g["km_chargeoff"] == 0.0
    assert age5_u["aj_chargeoff"] == pytest.approx(1 / 29)

    at12_g = survival.incidence_at(cif_guarded, ["lender", "score_b"], 12).iloc[0]["aj_chargeoff"]
    at12_u = survival.incidence_at(cif_unguarded, ["lender", "score_b"], 12).iloc[0]["aj_chargeoff"]
    assert at12_g == pytest.approx(20 / 2028)
    assert at12_u - at12_g > 0.03

    # group_life_tables applies the exact same floor
    one = lender_gap.cells_frame(loans, ["lender", "score_b"], 12, pool_offset=0)
    assert one["aj_chargeoff"].iloc[0] == pytest.approx(at12_g, abs=1e-12)


def test_blank_late_entry_cells_blanks_lenders_first_observed_past_cutoff():
    """abs-A-4: Capital One (first observed at 11), Toyota (9) and Honda (7 once thin age-6 risk sets are excluded)
    are blanked when max_first_age=6, while Exeter (3) and CarMax (4) are kept."""
    exeter = _deal_at_age(2000, entry_age=3, n_co=80, lender="exeter", score=700)
    carmax = _deal_at_age(2000, entry_age=4, n_co=15, lender="carmax", score=700)
    honda_thin6 = _deal_at_age(32, entry_age=6, n_co=0, lender="honda", score=700)
    honda_main7 = _deal_at_age(2000, entry_age=7, n_co=3, lender="honda", score=700)
    toyota = _deal_at_age(2000, entry_age=9, n_co=3, lender="toyota", score=700)
    capone = _deal_at_age(2000, entry_age=11, n_co=1, lender="capone", score=700)
    loans = pd.concat([exeter, carmax, honda_thin6, honda_main7, toyota, capone], ignore_index=True)
    loans["score_b"] = survival.score_bucket(loans["score"])

    cif = survival.cumulative_incidence(loans, by=["lender", "score_b"], horizon=12, pool_offset=0)
    at12 = survival.incidence_at(cif, ["lender", "score_b"], 12)

    fa = first_age_table(cif).set_index("lender")["first_age"].to_dict()
    assert fa == {"exeter": 3, "carmax": 4, "honda": 7, "toyota": 9, "capone": 11}

    blanked = blank_late_entry_cells(at12, cif).set_index("lender")
    for kept in ("exeter", "carmax"):
        assert blanked.loc[kept, "aj_chargeoff"] > 0
    for late in ("honda", "toyota", "capone"):
        assert np.isnan(blanked.loc[late, "aj_chargeoff"])
        assert np.isnan(blanked.loc[late, "km_chargeoff"])

    u = usable_cells(at12, cif=cif)
    assert sorted(u["lender"].unique()) == ["carmax", "exeter"]


def test_committed_cif_respects_min_risk_set_and_autos_page_blanks_late_lenders():
    """Seen on the data: in committed b1_cif.csv no age with at_risk < 50 moves aj_chargeoff in any usable cell, and in
    docs/autos.html the 24-month cell table blanks Capital One, Toyota and Honda cells whose first observed age is past 6."""
    cif = pd.read_csv(AUTOS / "b1_cif.csv")
    cif = cif.sort_values(["lender", "score_b", "age"])
    cif["prev_aj"] = cif.groupby(["lender", "score_b"])["aj_chargeoff"].shift(1).fillna(0.0)
    thin = cif[(cif["n_loans"] >= survival.MIN_RISK_SET) & (cif["at_risk"] > 0) & (cif["at_risk"] < survival.MIN_RISK_SET)]
    assert len(thin) > 0
    assert np.allclose(thin["aj_chargeoff"].to_numpy(), thin["prev_aj"].to_numpy(), atol=1e-12)

    at12 = pd.read_csv(AUTOS / "b1_at_12.csv")
    at24 = pd.read_csv(AUTOS / "b1_at_24.csv")
    b12 = blank_late_entry_cells(at12, cif)
    b24 = blank_late_entry_cells(at24, cif)
    for lender, expected_first_age in (("capone", 11), ("toyota", 9), ("honda", 7)):
        sub12 = b12[b12["lender"] == lender]
        sub24 = b24[b24["lender"] == lender]
        assert int(sub12["first_age"].median()) == expected_first_age
        assert sub12[sub12["first_age"] > survival.MAX_FIRST_AGE]["aj_chargeoff"].isna().all()
        assert sub24[sub24["first_age"] > survival.MAX_FIRST_AGE]["aj_chargeoff"].isna().all()
    for lender in ("exeter", "carmax", "santander", "americredit"):
        u12 = usable_cells(at12[at12["lender"] == lender], cif=cif)
        assert not u12.empty and u12["aj_chargeoff"].notna().all()


def test_carmax_fixture_proves_co_borrower_half_point_scores_are_averaged_and_truncated():
    """abs-A-5: CarMax's prospectus states that a joint loan's score is the average of each obligor's FICO score.
    The committed CarMax 2026-2 XML fixture carries co-obligor records with `.5` scores, which `score_value` truncates."""
    xml = FIX / "carmax-2026-2" / "2026-06.xml"
    records = list(iter_records(xml))
    co = [r for r in records if r.get("coObligorIndicator", "").lower() == "true"]
    solo = [r for r in records if r.get("coObligorIndicator", "").lower() == "false"]
    half_co = [r for r in co if ".5" in r.get("obligorCreditScore", "")]
    half_solo = [r for r in solo if ".5" in r.get("obligorCreditScore", "")]
    assert len(co) >= 80 and len(half_co) >= 35
    assert len(half_solo) == 0                                          # only co-obligor records carry a half-point average
    assert 0.25 < len(half_co) / len(co) < 0.60
    sample = half_co[0]["obligorCreditScore"]
    assert sample.endswith(".5") and score_value(sample) == int(float(sample))


def test_pages_and_methods_disclose_shelf_selection_co_borrower_averaging_and_first_age_blanking():
    """abs-A-4, abs-A-5, abs-A-7, abs-B-3 and abs-B-5 on docs/autos.html, docs/conclusions.html and design/methods.md."""
    autos = unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", (REPO / "docs" / "autos.html").read_text(encoding="utf-8"))))
    concl = unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", (REPO / "docs" / "conclusions.html").read_text(encoding="utf-8"))))
    methods = (REPO / "design" / "methods.md").read_text(encoding="utf-8")
    deals = (REPO / "data" / "deals.csv").read_text(encoding="utf-8")
    scout = (REPO / "design" / "scout-autos.md").read_text(encoding="utf-8")

    for text in (autos, concl, methods):
        assert "core portfolio" in text
        assert "CarMax Select" in text
        assert "Exeter Select" in text
        assert "650" in text and "640" in text and "240" in text
        assert "2025-2" in text

    for text in (autos, methods):
        assert "582" in text and "562" in text                          # Exeter VantageScore vs FICO weighted averages
        assert "half-point" in text                                     # CarMax co-obligor score averaging
        assert f"fewer than {survival.MIN_RISK_SET} loans at risk" in text or f"MIN_RISK_SET` = {survival.MIN_RISK_SET}" in text
        assert "blanked" in text

    assert "since 2025-4" not in deals and "since 2025-2" in deals      # abs-B-5
    assert "since 2025-4" not in scout and "since 2025-2" in scout
