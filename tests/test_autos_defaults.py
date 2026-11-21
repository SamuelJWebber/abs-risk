"""A buy-back of a loan that had been 90 days late is a default (REVIEW.md abs-A-1), and the lender gap is reported
for a fixed pair of lenders with loan age held fixed (abs-A-3).

The limit case: a sponsor that buys every bad loan back the month before it would be charged off. Its trust records
no charge-off at all, and on the trust's own loss definition its borrowers never default. Santander does a milder
version: in its fourth to sixth month in the pool about as many loans leave by buy-back at 120 days late as by
charge-off. Counting those as harmless exits made Santander's one-year figures 22% to 33% too low.
"""

from __future__ import annotations

import re
from html import unescape
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from absrisk.estimate import lender_gap, run_autos, survival
from absrisk.estimate.lender_gap import fixed_pair_ratios, mh_rate_ratio, usable_cells

REPO = Path(__file__).resolve().parents[1]
AUTOS = REPO / "data" / "results" / "autos"


def _loans() -> pd.DataFrame:
    return pd.DataFrame({
        "exit_type": pd.array(["chargeoff", "repurchase", "repurchase", "repurchase", "prepay", "censored"], dtype="string"),
        "max_dpd": pd.array([130, 136, 30, pd.NA, 0, 95], dtype="Int32")})


def test_only_a_buy_back_after_ninety_days_late_is_a_default():
    late = survival.late_repurchase(_loans())
    assert late.tolist() == [False, True, False, False, False, False]      # a current loan bought back is not; nor a late live one
    d = survival.as_defaults(_loans())
    assert d["exit_type"].tolist() == ["chargeoff", "chargeoff", "repurchase", "repurchase", "prepay", "censored"]
    assert d["exit_type_trust"].tolist() == _loans()["exit_type"].tolist() and d["late_repurchase"].tolist() == late.tolist()
    assert survival._event(d).tolist() == ["chargeoff", "chargeoff", "prepay", "prepay", "prepay", "censored"]


def test_the_definition_applies_once_and_can_be_undone():
    d = survival.as_defaults(_loans())
    assert survival.as_defaults(d) is d                                     # twice changes nothing
    back = survival.trust_loss(d)
    assert back["exit_type"].tolist() == _loans()["exit_type"].tolist() and "exit_type_trust" not in back
    assert survival.trust_loss(_loans())["exit_type"].tolist() == _loans()["exit_type"].tolist()
    no_dpd = _loans().drop(columns="max_dpd")
    assert not survival.late_repurchase(no_dpd).any()                       # without delinquency history nothing is reclassified


def test_mantel_haenszel_ratio_removes_a_difference_in_mix():
    # two strata; in each, lender a's rate is exactly twice b's; a is mostly in the high-rate stratum, b in the low
    pm_a, ev_a = np.array([9000.0, 1000.0]), np.array([360.0, 10.0])        # rates 0.04, 0.01
    pm_b, ev_b = np.array([1000.0, 9000.0]), np.array([20.0, 45.0])         # rates 0.02, 0.005
    crude = (ev_a.sum() / pm_a.sum()) / (ev_b.sum() / pm_b.sum())
    ratio, lo, hi = mh_rate_ratio(pm_a, ev_a, pm_b, ev_b)
    assert crude > 5 and ratio == pytest.approx(2.0, rel=1e-9) and lo < 2 < hi
    assert all(np.isnan(x) for x in mh_rate_ratio([100.0], [0.0], [100.0], [5.0]))      # no events on one side: no ratio
    r2, *_ = mh_rate_ratio([100.0, 0.0], [4.0, 9.0], [100.0, 50.0], [2.0, 9.0])        # a stratum one side lacks is dropped
    assert r2 == pytest.approx(2.0)


def _pool(lender: str, n: int, hazard: float, seed: int, months: int = 26) -> pd.DataFrame:
    """n loans at score 700 entering a trust at origination and followed `months` months, charging off at a constant
    monthly hazard."""
    rng = np.random.default_rng(seed)
    first = pd.Timestamp("2024-01-31")
    t = rng.geometric(hazard, n)                                             # month of charge-off, 1-based
    co = t <= months - 1
    exit_period = [(first.to_period("M") + int(k)).to_timestamp(how="end").normalize() if c else pd.NaT for k, c in zip(t, co)]
    return pd.DataFrame({"deal": f"{lender}-1", "lender": lender, "asset_id": [f"{lender}{i}" for i in range(n)],
                         "score": 700, "orig_month": first.to_period("M").to_timestamp(), "first_period": first,
                         "last_period": (first.to_period("M") + months - 1).to_timestamp(how="end").normalize(),
                         "months_observed": np.where(co, t + 1, months), "exit_type": np.where(co, "chargeoff", "censored"),
                         "exit_period": exit_period, "zb_date": pd.NaT, "max_dpd": 0})


def test_fixed_pair_ratio_recovers_a_known_hazard_ratio_in_both_years():
    loans = pd.concat([_pool("exeter", 20000, 0.008, 1), _pool("carmax", 60000, 0.002, 2)], ignore_index=True)
    p = fixed_pair_ratios(loans, pairs=(("exeter", "carmax"),))
    assert list(p["window"]) == ["year one", "year two"] and set(p["matched"]) == {"score"}
    for r in p.itertuples():
        assert r.lo95 < 4.0 < r.hi95 and 3.3 < r.ratio < 4.8, r
        assert r.events_higher > 100 and r.events_lower > 100
    assert (p["age_lo"].tolist(), p["age_hi"].tolist()) == ([4, 13], [12, 24])


def test_counting_buy_backs_moves_the_lender_that_makes_them_and_no_other():
    a = _pool("santander", 30000, 0.004, 3)
    b = _pool("carmax", 60000, 0.002, 4)
    # a third of santander's charge-offs become buy-backs of 120-day-late loans instead
    co = np.flatnonzero((a["exit_type"] == "chargeoff").to_numpy())
    swap = co[::3]
    a.loc[swap, "exit_type"] = "repurchase"
    a.loc[swap, "max_dpd"] = 125
    loans = pd.concat([a, b], ignore_index=True)
    d = fixed_pair_ratios(survival.as_defaults(loans), pairs=(("santander", "carmax"),)).set_index("window")["ratio"]
    t = fixed_pair_ratios(survival.trust_loss(loans), pairs=(("santander", "carmax"),)).set_index("window")["ratio"]
    assert d["year one"] == pytest.approx(2.0, rel=0.2)
    assert t["year one"] == pytest.approx(d["year one"] * 2 / 3, rel=0.08)   # the trust-loss figure is a third too low


# ----------------------------------------------------------------------------- the committed results


@pytest.fixture(scope="module")
def late():
    return pd.read_csv(AUTOS / "b1_late_repurchase.csv").set_index("deal")


def test_committed_buy_back_profile_is_santander_alone(late):
    s = late[late["lender"] == "santander"]
    assert len(s) == 2 and (s["late_share_of_repurchases"] > 0.8).all()
    assert int(s["n_late_repurchase"].sum()) > 1000
    assert (s["late_pool_month_median"].between(4, 6)).all()                # they leave in the fourth to sixth month
    rest = late[(late["lender"] != "santander") & (late["n_repurchase"] > 0)]
    assert (rest["late_share_of_repurchases"] < 0.1).all()
    assert (late["defaults_over_chargeoffs"].drop(index=s.index) < 1.01).all()


def test_committed_santander_cells_rise_and_others_do_not():
    d = usable_cells(pd.read_csv(AUTOS / "b1_at_12.csv"))[["lender", "score_b", "aj_chargeoff", "cum_chargeoff"]]
    t = pd.read_csv(AUTOS / "b1_at_12_trust_loss.csv")[["lender", "score_b", "aj_chargeoff", "cum_chargeoff"]]
    d["score_b"], t["score_b"] = d["score_b"].astype(str), t["score_b"].astype(str)
    m = d.merge(t, on=["lender", "score_b"], suffixes=("", "_trust"))
    up = m["aj_chargeoff"] / m["aj_chargeoff_trust"] - 1
    san = m["lender"] == "santander"
    assert san.sum() >= 7 and up[san].min() > 0.2 and up[san].max() < 1.2
    listed = san & m["score_b"].isin(["480", "560", "660", "680", "700", "720", "740"])     # the review's seven cells: +28% to +49%
    assert 0.25 < up[listed].min() and up[listed].max() < 0.52
    assert up[~san & (m["aj_chargeoff_trust"] > 0)].abs().max() < 0.03
    c660 = m[san & (m["score_b"] == "660")].iloc[0]                         # the review's cell: 151 charge-offs, 197 defaults
    assert (c660["cum_chargeoff_trust"], c660["cum_chargeoff"]) == (151, 197)
    assert c660["aj_chargeoff_trust"] == pytest.approx(0.0539, abs=5e-4) and c660["aj_chargeoff"] == pytest.approx(0.0725, abs=5e-4)


def test_committed_gap_tables_agree_with_the_review_on_both_definitions():
    g = pd.read_csv(AUTOS / "b1_gap.csv")
    t = pd.read_csv(AUTOS / "b1_gap_trust_loss.csv")

    def med(x, variant="all"):
        return x[(x["stat"] == "median") & (x["variant"] == variant)].iloc[0]
    # the headline median does not move; its range and the without-Exeter check do
    assert med(g)["ratio"] == pytest.approx(med(t)["ratio"], rel=1e-9)
    assert med(t)["range_lo"] == pytest.approx(9.0, abs=0.1) and med(g)["range_lo"] == pytest.approx(11.6, abs=0.1)
    assert med(t, "without_exeter")["ratio"] == pytest.approx(9.4, abs=0.1)
    assert med(g, "without_exeter")["ratio"] == pytest.approx(13.4, abs=0.1)
    assert med(g)["lo95"] <= med(g, "without_exeter")["ratio"] <= med(g)["hi95"]     # no longer outside the interval


def test_committed_fixed_pairs_match_a_rebuild_from_the_loan_tables():
    p = pd.read_csv(AUTOS / "b1_fixed_pairs.csv")
    assert set(p["definition"]) == {"default", "trust_loss"} and set(p["matched"]) == {"score", "score and structure"}
    assert (p["lo95"] < p["ratio"]).all() and (p["ratio"] < p["hi95"]).all() and (p["events_lower"] >= 50).all()
    k = p.set_index(["definition", "matched", "window", "higher"])["ratio"]
    assert k["default", "score", "year one", "santander"] > k["trust_loss", "score", "year one", "santander"] * 1.2
    assert k["default", "score", "year two", "santander"] == pytest.approx(k["trust_loss", "score", "year two", "santander"], rel=0.02)
    assert k["default", "score", "year one", "exeter"] == pytest.approx(k["trust_loss", "score", "year one", "exeter"], rel=0.02)
    # the gap for a fixed pair narrows from the first year to the second
    for lender in ("exeter", "santander"):
        assert k["default", "score", "year two", lender] < 0.7 * k["default", "score", "year one", lender]
    loans = run_autos.load_loans(REPO / "data" / "autos")
    assert "exit_type_trust" in loans and int(loans["late_repurchase"].sum()) > 1000
    rebuilt = fixed_pair_ratios(loans).set_index(["matched", "window", "higher"])["ratio"]
    for (matched, window, higher), v in rebuilt.items():
        assert v == pytest.approx(k["default", matched, window, higher], rel=1e-9)


def test_the_autos_page_prints_the_pairs_and_the_buy_backs():
    t = unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", (REPO / "docs" / "autos.html").read_text(encoding="utf-8"))))
    p = pd.read_csv(AUTOS / "b1_fixed_pairs.csv")
    r = p[(p["definition"] == "default") & (p["matched"] == "score") & (p["window"] == "year one") & (p["higher"] == "santander")].iloc[0]
    assert f"santander {r['ratio']:.1f} times ({r['lo95']:.1f} to {r['hi95']:.1f})" in t
    assert "Santander's buy-backs are defaults." in t
    assert "A default on this page is a charge-off, or a buy-back of a loan that had been 90 or more days late" in t
    assert "Counting charge-offs alone" in t and "What counting buy-backs changes" in t
    late = pd.read_csv(AUTOS / "b1_late_repurchase.csv")
    s = late[late["lender"] == "santander"]
    assert f"{int(s['n_late_repurchase'].sum()):,} of the {int(s['n_repurchase'].sum()):,} loans it repurchased" in t
