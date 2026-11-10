"""Honest inference on the autos page: few deals, sparse levels, charge-offs that skip delinquency.

R1-6: lender intervals clustered over ten deals, four lenders owning one deal each. In a simulation with deal-level
shocks the clustered interval covered the truth less than half the time for a single-deal lender.
R1-9: score buckets and origination quarters with no events printed odds ratios near 1e-10, p near 1e-200.
R1-13: the entry/roll split silently left out charge-offs never recorded 30 days late (75% of Capital One's).
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from absrisk.estimate import decompose, hazard

REPO = Path(__file__).resolve().parents[1]
AUTOS = REPO / "data" / "results" / "autos"
DEALS = list("ABCDEEFFGG")        # lenders A-D own one deal, E and F two, G (the baseline) two
LENDERS = list("ABCDEF")


def _sim_cells(rng, shock_sd=0.3, n_cells=40, n=400):
    """The review's design: one row per cell, a five-level covariate, a shock per deal and no lender effect at all."""
    u = rng.normal(0, shock_sd, len(DEALS))
    rows = []
    for d, lender in enumerate(DEALS):
        xb = rng.integers(0, 5, n_cells)
        p = 1 / (1 + np.exp(4 - 0.5 * (xb - 2) / 2 - u[d]))
        k = rng.binomial(n, p)
        kp = rng.binomial(n - k, 0.05)
        rows += [{"deal": f"{lender}{d}", "lender": lender, "x": str(xb[i]), "exposure": n, "d_chargeoff": int(k[i]),
                  "d_prepay": int(kp[i])} for i in range(n_cells)]
    return pd.DataFrame(rows)


def test_deal_spread_intervals_cover_where_clustered_ones_do_not():
    pytest.importorskip("statsmodels")
    warnings.filterwarnings("ignore")
    rng = np.random.default_rng(3)
    base = {"lender": "G", "x": "2"}
    est, se_cl, se_h, cov_cl, cov_h = [], [], [], [], []
    for _ in range(60):
        cells = _sim_cells(rng)
        res = hazard.fit_hazards(cells, factors=["x", "lender"], cluster="deal", baseline=base)
        hr = hazard.hazard_ratios(res["chargeoff"], "lender", t_df=res["design_info"]["t_df"]).set_index("level").loc[LENDERS]
        tab, info = hazard.deal_spread_intervals(cells, ["x", "lender"], base, events=("chargeoff",))
        tab = tab.set_index("lender").loc[LENDERS]
        est.append(np.log(hr["odds_ratio"].to_numpy()))
        se_cl.append(res["chargeoff"].bse[[f"lender={x}" for x in LENDERS]].to_numpy())
        se_h.append(tab["se"].to_numpy())
        cov_cl.append(((hr["lo95"] <= 1) & (hr["hi95"] >= 1)).to_numpy())     # true odds ratio is 1 for every lender
        cov_h.append(((tab["lo95"] <= 1) & (tab["hi95"] >= 1)).to_numpy())
    assert info["chargeoff"]["df"] == 3                  # E, F and G each contribute one degree of freedom
    sd = np.std(est, axis=0)
    single = slice(0, 4)
    assert (np.mean(se_cl, axis=0)[single] / sd[single]).mean() < 0.45      # the problem: about a third
    assert (np.mean(se_h, axis=0)[single] / sd[single]).mean() > 0.65       # the fix: most of it
    assert np.mean(cov_cl, axis=0)[single].mean() < 0.65                   # clustered: covers about half the time
    assert np.mean(cov_h, axis=0)[single].mean() > 0.85                    # deal spread with t critical values
    assert np.mean(cov_h, axis=0)[4:].mean() > 0.85


def test_t_critical_values_widen_clustered_intervals():
    pytest.importorskip("statsmodels")
    rng = np.random.default_rng(0)
    cells = _sim_cells(rng)
    res = hazard.fit_hazards(cells, factors=["x", "lender"], cluster="deal", baseline={"lender": "G", "x": "2"})
    assert res["design_info"]["t_df"] == 9 and "t(9)" in res["design_info"]["cov_type"]
    z = hazard.hazard_ratios(res["chargeoff"], "x").set_index("level")
    t = hazard.hazard_ratios(res["chargeoff"], "x", t_df=9).set_index("level")
    ratio = np.log(t["hi95"] / t["odds_ratio"]) / np.log(z["hi95"] / z["odds_ratio"])
    assert np.allclose(ratio, 2.2621571627409915 / 1.959963984540054)


def test_merge_sparse_edges_folds_thin_ends_into_neighbours():
    counts = {"360": 6, "380": 20, "400": 167, "420": 532, "440": 1500, "860": 900, "880": 600, "900": 115}
    labels = pd.Series([k for k, n in counts.items() for _ in range(n)])
    out = hazard.merge_sparse_edges(labels, list(counts), min_n=500)
    assert set(out[labels.isin(["360", "380", "400", "420"])]) == {"420"}
    assert set(out[labels.isin(["880", "900"])]) == {"880"} and set(out[labels == "860"]) == {"860"}
    q = pd.Series(["2017Q2"] * 5 + ["2017Q4"] * 4 + ["2018Q2"] * 1762 + ["2026Q1"] * 900)
    mq = hazard.merge_sparse_edges(q, ["2017Q2", "2017Q4", "2018Q2", "2026Q1"], min_n=500, tag=("<=", ">="))
    assert set(mq[:9]) == {"<=2018Q2"} and set(mq[q == "2026Q1"]) == {"2026Q1"}


def test_a_level_with_no_events_gets_no_odds_ratio():
    pytest.importorskip("statsmodels")
    rng = np.random.default_rng(1)
    cells = _sim_cells(rng)
    cells.loc[cells["x"] == "4", "d_chargeoff"] = 0
    res = hazard.fit_hazards(cells, factors=["x", "lender"], cluster="deal", baseline={"lender": "G", "x": "2"})
    ev = cells.groupby("x")["d_chargeoff"].sum().to_dict()
    hr = hazard.hazard_ratios(res["chargeoff"], "x", events=ev).set_index("level")
    assert np.isnan(hr.loc["4", "odds_ratio"]) and hr.loc["4", "note"] == "no events"
    assert hr.drop(index="4")["odds_ratio"].notna().all()


def test_committed_hazard_table_has_no_degenerate_levels():
    h = pd.read_csv(AUTOS / "b2_hazard_ratios.csv")
    bad = h[(h["odds_ratio"] < 1e-3) | (h["odds_ratio"] > 1e3)]
    assert bad.empty, bad[["spec", "event", "factor", "level", "odds_ratio"]].to_string()


def test_committed_lender_intervals_are_wider_for_single_deal_lenders():
    li = pd.read_csv(AUTOS / "b2_lender_intervals.csv")
    hr = pd.read_csv(AUTOS / "b2_hazard_ratios.csv")
    t = li[(li["spec"] == "terms") & (li["event"] == "chargeoff")].set_index("lender")
    c = hr[(hr["spec"] == "terms") & (hr["event"] == "chargeoff") & (hr["factor"] == "lender")].set_index("level")
    assert set(t.index) == set(c.index)
    assert np.allclose(t["odds_ratio"], c.loc[t.index, "odds_ratio"], rtol=1e-6)    # same point estimate
    one = t[t["n_deals"] == 1]
    assert len(one) >= 1
    assert ((one["hi95"] / one["lo95"]) > (c.loc[one.index, "hi95"] / c.loc[one.index, "lo95"])).all()


def _loans_with_bankruptcy_chargeoffs() -> pd.DataFrame:
    n = 4000
    rng = np.random.default_rng(5)
    orig = pd.Timestamp("2024-01-01")
    d = pd.DataFrame({"deal": "x-1", "lender": np.where(np.arange(n) < n // 2, "a", "b"), "score": 700,
                      "orig_month": orig, "first_period": pd.Timestamp("2024-02-29"),
                      "last_period": pd.Timestamp("2026-01-31"), "months_observed": 24, "exit_type": "censored"})
    co = rng.random(n) < 0.1
    d.loc[co, "exit_type"] = "chargeoff"
    d["exit_period"] = pd.NaT
    d.loc[co, "exit_period"] = pd.Timestamp("2025-01-31")
    d["first_30_period"] = pd.NaT
    late = co & (d["lender"] == "a")                      # lender a: every charge-off was 30+ first
    d.loc[late, "first_30_period"] = pd.Timestamp("2024-10-31")
    return d                                              # lender b: no charge-off ever recorded 30+ late


def test_decomposition_reports_charge_offs_that_skip_delinquency():
    dec = decompose.decompose(_loans_with_bankruptcy_chargeoffs(), by=["lender"], min_loans=100, min_ever30=10)
    dec = dec.set_index("lender")
    assert dec.loc["a", "co_without_30_share"] == 0 and bool(dec.loc["a", "split_holds"])
    assert dec.loc["b", "co_without_30_share"] == 1 and not bool(dec.loc["b", "split_holds"])


def test_committed_entry_roll_tables_carry_the_skipped_share():
    att = pd.read_csv(AUTOS / "b6_attribution.csv").set_index("lender")
    assert "co_without_30_share" in att
    assert att.loc["capone", "co_without_30_share"] > 0.5 and not bool(att.loc["capone", "split_holds"])
    others = att.drop(index="capone")
    assert (others["co_without_30_share"] < 0.1).all()


def test_terms_without_one_lender_drops_it_and_keeps_the_others(tmp_path):
    pytest.importorskip("statsmodels")
    from absrisk.estimate import run_autos
    from tests.test_estimate import make_loans

    loans = pd.concat([make_loans(n=8000, seed=s, lender=l).assign(deal=f"{l}-1") for s, l in ((1, "exeter"), (2, "a"), (3, "b"))],
                      ignore_index=True)
    t = run_autos.run_b2_without(loans, tmp_path)
    assert t is not None and (tmp_path / "b2_terms_without_exeter.csv").exists()
    lenders = set(t.loc[t["factor"] == "lender", "level"]) | set(t["baseline_lender"])
    assert lenders == {"a", "b"}
    assert run_autos.run_b2_without(loans[loans["lender"] != "exeter"], tmp_path / "none") is None
