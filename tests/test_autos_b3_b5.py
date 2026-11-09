"""The 2026-11-09 additions to Track B, on synthetic data with known answers.

B3 by origination cohort (`run_b1_cohort`, `bucket_ratios`), B4 chart 2 (`forest_chart`), and B5 bandwidth
sensitivity (`rd.usable`, `rd.rd_bandwidth_sensitivity`, `bandwidth_stability`). Nothing here touches EDGAR.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from absrisk.estimate import rd, run_autos
from absrisk.report.autos_page import bandwidth_stability, bucket_ratios, usable_cells
from absrisk.report.svg import forest_chart
from tests.test_estimate import make_loans


def test_usable_needs_smooth_density_and_a_first_stage_in_rate_or_amount():
    r = pd.DataFrame({
        "density_p":       [0.50, 0.50, 0.50, 0.01, 0.50],
        "fs_orig_apr":     [-0.010, 0.001, 0.001, -0.010, 0.001],
        "fs_orig_apr_se":  [0.002, 0.002, 0.002, 0.002, 0.002],
        "fs_orig_amount":  [10.0, 2500.0, 100.0, 2500.0, np.nan],
        "fs_orig_amount_se": [300.0, 300.0, 300.0, 300.0, np.nan],
    })
    # APR only; amount only; neither; bunching despite both; neither with a missing amount fit
    assert rd.usable(r).tolist() == [True, True, False, False, False]


def test_bandwidth_sensitivity_recovers_a_jump_at_every_bandwidth():
    pytest.importorskip("rdrobust")
    rng = np.random.default_rng(7)
    n = 40000
    x = rng.uniform(560, 720, n).round()
    y = 0.2 - 0.001 * (x - 640) + 0.05 * (x >= 640) + rng.normal(0, 0.05, n)
    df = pd.DataFrame({"score": x, "y": y})
    s = rd.rd_bandwidth_sensitivity(df, "y", 640)
    assert s["bw_mult"].tolist() == list(rd.BANDWIDTH_MULTS)
    assert (s["error"] == "").all()
    assert (abs(s["estimate"] - 0.05) < 0.01).all()
    assert (s["ci_lo"] > 0).all()
    main = rd.rd_estimate(df, "y", 640).iloc[0]                  # the rdrobust row at the MSE-optimal bandwidth
    one = s[s["bw_mult"] == 1.0].iloc[0]
    assert one["estimate"] == pytest.approx(main["estimate"]) and one["bandwidth"] == pytest.approx(main["bandwidth"])
    widths = s["bandwidth"].to_numpy()
    assert np.allclose(widths / widths[2], rd.BANDWIDTH_MULTS)


def test_bandwidth_stability_needs_every_bandwidth_clear_of_zero():
    bw = pd.DataFrame({
        "lender": ["a"] * 5 + ["b"] * 5, "cutoff": [640.0] * 10, "horizon": [24] * 10,
        "bw_mult": [0.5, 0.75, 1.0, 1.5, 2.0] * 2,
        "estimate": [0.05, 0.05, 0.05, 0.05, 0.05, 0.03, 0.03, 0.03, 0.03, 0.03],
        "ci_lo":    [0.01, 0.02, 0.02, 0.03, 0.03, 0.01, 0.01, 0.005, 0.002, -0.001],
        "ci_hi":    [0.09, 0.08, 0.08, 0.07, 0.07, 0.05, 0.05, 0.05, 0.05, 0.06],
        "p_robust": [0.01] * 10,
    })
    st = bandwidth_stability(bw).set_index("lender")
    assert bool(st.loc["a", "holds"]) is True
    assert bool(st.loc["b", "holds"]) is False                    # loses significance at the widest bandwidth
    assert st.loc["a", "est_main"] == 0.05 and st.loc["a", "n_bw"] == 5


def _cells(rows):
    df = pd.DataFrame(rows, columns=["orig_year", "lender", "score_b", "aj_chargeoff"])
    df["n_loans"], df["at_risk"] = 5000, 1000
    return usable_cells(df)


def test_bucket_ratios_compare_only_inside_one_bucket_and_year():
    cells = _cells([
        (2024, "x", "700", 0.050), (2024, "y", "700", 0.005), (2024, "z", "700", 0.010),
        (2024, "x", "720", 0.040), (2024, "y", "720", 0.004),                       # two lenders: skipped
        (2025, "x", "700", 0.020), (2025, "y", "700", 0.010), (2025, "z", "700", 0.004),
    ])
    pooled = bucket_ratios(cells)                                 # 2024 and 2025 cells mixed inside bucket 700
    assert pooled["lo"].tolist() == [700]
    by_year = bucket_ratios(cells, by=("orig_year",)).set_index("orig_year")
    assert by_year.loc[2024, "ratio"] == pytest.approx(10.0) and by_year.loc[2024, "worst"] == "x"
    assert by_year.loc[2025, "ratio"] == pytest.approx(5.0) and by_year.loc[2025, "best"] == "z"


def test_bucket_ratio_over_a_zero_rate_is_not_a_number():
    cells = _cells([(2024, "x", "700", 0.01), (2024, "y", "700", 0.0), (2024, "z", "700", 0.002)])
    assert np.isnan(bucket_ratios(cells)["ratio"].iloc[0])


def test_pair_ratios_compare_the_same_two_lenders_inside_and_across_vintages():
    from absrisk.report.autos_page import pair_ratios

    pooled = _cells([(0, "x", "700", 0.040), (0, "y", "700", 0.004), (0, "z", "700", 0.0)])
    within = _cells([(2024, "x", "700", 0.030), (2024, "y", "700", 0.006), (2024, "z", "700", 0.001)])
    pr = pair_ratios(within, pooled)
    # x over y only: every pair with z is skipped because z's pooled rate is zero
    assert pr[["higher", "lower"]].values.tolist() == [["x", "y"]]
    r = pr.iloc[0]
    assert r["within"] == pytest.approx(5.0) and r["pooled"] == pytest.approx(10.0)
    assert r["within_over_pooled"] == pytest.approx(0.5)


def test_cohort_cut_splits_by_origination_year(tmp_path):
    a = make_loans(n=6000, seed=21, lender="alpha")
    b = make_loans(n=6000, seed=22, h_co=0.03, lender="alpha")
    b["orig_month"] = pd.Timestamp("2024-03-01")
    loans = pd.concat([a, b], ignore_index=True)
    loans["asset_id"] = np.arange(len(loans)).astype(str)
    run_autos.run_b1_cohort(loans, tmp_path, n_boot=20)
    at12 = pd.read_csv(tmp_path / "b1_cohort_at_12.csv")
    assert set(at12["orig_year"]) == {2024, 2025}
    assert {"lender", "score_b", "aj_chargeoff", "aj_lo95", "n_loans"} <= set(at12.columns)
    # the 2024 vintage was built with three times the charge-off hazard
    rate = at12[at12["score_b"].astype(str) == "620"].set_index("orig_year")["aj_chargeoff"]
    assert rate[2024] > 2 * rate[2025]
    assert (tmp_path / "b1_cohort_at_24.csv").exists()


def test_driver_writes_bandwidths_only_for_usable_cutoffs(tmp_path):
    pytest.importorskip("rdrobust")
    rdres = pd.DataFrame({"lender": ["alpha", "alpha"], "cutoff": [640.0, 700.0], "density_p": [0.4, 0.001],
                          "fs_orig_apr": [-0.04, -0.04], "fs_orig_apr_se": [0.002, 0.002],
                          "fs_orig_amount": [0.0, 0.0], "fs_orig_amount_se": [100.0, 100.0]})
    rdres.to_csv(tmp_path / "b3_rd.csv", index=False)
    loans = make_loans(n=40000, seed=31, lender="alpha")
    out = run_autos.run_b3_bandwidths(loans, tmp_path)
    assert (tmp_path / "b3_rd_bandwidths.csv").exists()
    assert set(out["cutoff"]) == {640.0}                          # 700 fails the density screen
    assert set(out["horizon"]) <= {12, 24} and len(out) % len(rd.BANDWIDTH_MULTS) == 0


def test_forest_chart_draws_rows_and_skips_bad_values():
    svg = forest_chart([
        {"label": "honda", "est": 0.16, "lo": 0.11, "hi": 0.23, "group": "Lender"},
        {"label": "exeter", "est": 1.13, "lo": 1.00, "hi": 1.28, "group": "Lender"},
        {"label": "broken", "est": 0.0, "lo": 0.0, "hi": 0.1, "group": "Lender"},
        {"label": "quintile 5", "est": 4.33, "lo": 3.48, "hi": 5.38, "group": "LTV"},
    ], title="t")
    assert svg.startswith("<svg") and svg.count("<circle") == 3 and "broken" not in svg
    assert ">Lender<" in svg and ">LTV<" in svg
    assert forest_chart([]).startswith("<p")
