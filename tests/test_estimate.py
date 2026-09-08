"""Estimators checked on synthetic loans with known hazards."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from absrisk.estimate import rd, survival


def make_loans(n=20000, seed=1, h_co=0.01, h_pre=0.02, horizon=36, lender="a", score_mean=620):
    rng = np.random.default_rng(seed)
    score = rng.normal(score_mean, 60, n).round().clip(400, 850)
    # monthly hazards: charge-off falls with score, prepay constant
    hco = h_co * np.exp(-(score - 620) / 100)
    t_co = rng.geometric(np.clip(hco, 1e-6, 0.5))
    t_pre = rng.geometric(h_pre, n)
    t_cens = rng.integers(12, horizon + 1, n)
    t = np.minimum.reduce([t_co, t_pre, t_cens])
    exit_type = np.where(t == t_co, "chargeoff", np.where(t == t_pre, "prepay", "censored"))
    return pd.DataFrame({
        "deal": f"{lender}-2025-1", "lender": lender, "asset_id": np.arange(n).astype(str),
        "score": score.astype(int), "orig_amount": rng.lognormal(10, 0.3, n), "orig_apr": 0.30 - 0.0003 * (score - 400),
        "orig_term": 72, "pti": rng.uniform(0.05, 0.2, n), "ltv": rng.uniform(0.8, 1.3, n),
        "orig_month": pd.Timestamp("2025-01-01"), "months_observed": t, "exit_type": exit_type,
    })


def test_cumulative_incidence_orders_and_bounds():
    loans = make_loans()
    loans["score_b"] = survival.score_bucket(loans["score"])
    cif = survival.cumulative_incidence(loans, by=["lender"], horizon=36)
    assert (cif["aj_chargeoff"].diff().fillna(0) >= -1e-12).all()          # CIF is non-decreasing
    assert (cif["km_chargeoff"] >= cif["aj_chargeoff"] - 1e-12).all()       # KM treats prepay as censoring, so >= AJ
    assert cif["aj_chargeoff"].iloc[-1] < 1.0
    # with prepay hazard 0.02 and charge-off ~0.01 near 620, the 12-month AJ should sit near 1 - exp(-12*0.01) scaled by survival
    at12 = survival.incidence_at(cif, ["lender"], 12)["aj_chargeoff"].iloc[0]
    assert 0.05 < at12 < 0.15


def test_cumulative_incidence_by_score_bucket_is_decreasing_in_score():
    loans = make_loans(n=60000)
    loans["score_b"] = survival.score_bucket(loans["score"])
    cif = survival.incidence_at(survival.cumulative_incidence(loans, by=["score_b"], horizon=24), ["score_b"], 24)
    cif = cif[cif["n_loans"] > 1500].copy()
    cif["lo"] = cif["score_b"].astype(int)
    cif = cif.sort_values("lo")
    # Spearman-like check: charge-off incidence falls with score in the well-populated buckets
    assert np.corrcoef(cif["lo"], cif["aj_chargeoff"])[0, 1] < -0.9


def test_find_cutoffs_detects_an_apr_jump():
    loans = make_loans(n=80000)
    loans["orig_apr"] = np.where(loans["score"] >= 640, loans["orig_apr"] - 0.04, loans["orig_apr"])  # 4-point drop at 640
    cands = rd.find_cutoffs(loans, var="orig_apr", lo=560, hi=720, step=5, h=25, min_n=100)
    flagged = cands[cands["flag"]]
    assert 640 in set(flagged["cutoff"])
    best = cands.loc[cands["t"].abs().idxmax()]
    assert best["cutoff"] == 640 and abs(best["jump"] + 0.04) < 0.01


def test_density_test_passes_without_bunching_and_flags_bunching():
    rng = np.random.default_rng(3)
    smooth = rng.normal(640, 60, 50000).round()
    r = rd.density_test(smooth, c=640, h=25)
    assert r["p"] > 0.01
    bunched = np.concatenate([smooth, np.full(6000, 641.0)])
    r2 = rd.density_test(bunched, c=640, h=25)
    assert r2["p"] < 0.01


def test_rd_estimate_recovers_a_jump():
    rng = np.random.default_rng(5)
    n = 100000
    x = rng.uniform(560, 720, n).round()
    y = 0.2 - 0.001 * (x - 640) + 0.05 * (x >= 640) + rng.normal(0, 0.05, n)
    df = pd.DataFrame({"score": x, "y": y})
    est = rd.rd_estimate(df, outcome="y", c=640, bandwidths=(15, 25, 40))
    ll = est[est["method"] == "local-linear"]
    assert (abs(ll["estimate"] - 0.05) < 0.01).all()


def test_outcome_by_horizon():
    loans = pd.DataFrame({"months_observed": [5, 12, 20, 12], "exit_type": ["chargeoff", "censored", "prepay", "chargeoff"]})
    y = rd.outcome_by_horizon(loans, 12)
    assert list(y.fillna(-1)) == [1.0, 0.0, 0.0, 1.0]


def test_hazard_fit_recovers_lender_gap():
    pytest.importorskip("statsmodels")
    from absrisk.estimate import hazard

    a = make_loans(n=30000, seed=7, h_co=0.01, lender="a")
    b = make_loans(n=30000, seed=8, h_co=0.02, lender="b")   # lender b has twice the charge-off hazard at every score
    loans = pd.concat([a, b], ignore_index=True)
    loans = hazard.add_design_columns(loans)
    lm = hazard.expand_loan_months(loans, keep=["deal", "lender", "score_b", "cohort_q", "amount_q"])
    cells = hazard.aggregate_cells(lm, cells=["deal", "lender", "score_b", "cohort_q", "amount_q"])
    res = hazard.fit_hazards(cells, factors=["age_b", "score_b", "lender", "amount_q"], cluster="deal")
    hr = hazard.hazard_ratios(res["chargeoff"], "lender")
    assert len(hr) == 1 and 1.7 < hr["odds_ratio"].iloc[0] < 2.3
