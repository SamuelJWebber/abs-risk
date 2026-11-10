"""The same-score lender gap on the autos page (REVIEW.md R2-1).

The limit case: a lender whose loans all enter its trust at age 12. A loan must be current to be sold in, so by age
12 that lender's charge-off is near zero whoever its borrowers are. The page divided by such cells, each holding one to
three charge-offs, and printed 50 times. Now every b1 table counts a loan from its fourth month in the trust, a cell
needs ten charge-offs to be the lower end of a ratio, and every ratio carries a resampling interval.
"""

from __future__ import annotations

import glob
import re
from html import unescape
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from absrisk.estimate import lender_gap, survival
from absrisk.estimate.lender_gap import band_levels, bucket_ratios, pair_ratios, usable_cells

REPO = Path(__file__).resolve().parents[1]
AUTOS = REPO / "data" / "results" / "autos"


def _deal(n: int, entry_age: int, co_pool_month: int | None, lender: str = "a", score: int = 700) -> pd.DataFrame:
    """n loans entering one trust at `entry_age`, observed eight months; with `co_pool_month` each charges off that many
    months after entering, else each is still running at the end."""
    first = pd.Timestamp("2025-06-30")
    orig = (first.to_period("M") - entry_age).to_timestamp()
    d = pd.DataFrame({"deal": f"{lender}-1", "lender": lender, "asset_id": [str(i) for i in range(n)], "score": score,
                      "orig_month": orig, "first_period": first, "last_period": pd.Timestamp("2026-01-31"),
                      "months_observed": 8, "exit_type": "censored", "exit_period": pd.NaT, "zb_date": pd.NaT})
    if co_pool_month is not None:
        d["exit_type"] = "chargeoff"
        d["exit_period"] = (first.to_period("M") + co_pool_month).to_timestamp(how="end").normalize()
    return d


def test_pool_offset_moves_entry_and_leaves_exit():
    d = _deal(5, entry_age=12, co_pool_month=1)
    a0, a3 = survival.ages(d), survival.ages(d, pool_offset=3)
    assert (a0["entry_age"] == 12).all() and (a0["exit_age"] == 13).all()
    assert (a3["entry_age"] == 15).all() and (a3["exit_age"] == 13).all()     # left before it counted


def test_charge_offs_inside_the_pool_window_are_not_events():
    early = _deal(400, entry_age=12, co_pool_month=1)                 # every loan charges off in its second pool month
    at0 = survival.incidence_at(survival.cumulative_incidence(early, by=["lender"], horizon=20), ["lender"], 20)
    at3 = survival.incidence_at(survival.cumulative_incidence(early, by=["lender"], horizon=20, pool_offset=3),
                                ["lender"], 20)
    assert at0["aj_chargeoff"].iloc[0] == pytest.approx(1.0) and at0["cum_chargeoff"].iloc[0] == 400
    assert at3["aj_chargeoff"].iloc[0] == 0 and at3["cum_chargeoff"].iloc[0] == 0 and at3["at_risk"].iloc[0] == 0
    late = _deal(400, entry_age=12, co_pool_month=4)                  # after the window: still counted
    at3 = survival.incidence_at(survival.cumulative_incidence(late, by=["lender"], horizon=20, pool_offset=3),
                                ["lender"], 20)
    assert at3["aj_chargeoff"].iloc[0] == pytest.approx(1.0)


def test_one_pass_life_tables_equal_the_per_group_estimator():
    rng = np.random.default_rng(4)
    parts = []
    for i, lender in enumerate("abc"):
        for j in range(300):
            d = _deal(1, entry_age=int(rng.integers(0, 15)), co_pool_month=int(rng.integers(0, 8)) if rng.random() < 0.3
                      else None, lender=lender, score=int(rng.choice([640, 660, 700])))
            parts.append(d.assign(asset_id=f"{lender}{j}"))
    loans = pd.concat(parts, ignore_index=True)
    loans["score_b"] = survival.score_bucket(loans["score"])
    for k in (0, 3):
        one = lender_gap.cells_frame(loans, ["lender", "score_b"], 12, pool_offset=k).sort_values(["lender", "score_b"])
        ref = survival.incidence_at(survival.cumulative_incidence(loans, by=["lender", "score_b"], horizon=12, pool_offset=k),
                                    ["lender", "score_b"], 12).sort_values(["lender", "score_b"])
        assert np.allclose(one["aj_chargeoff"].to_numpy(), ref["aj_chargeoff"].to_numpy(), atol=1e-12)
        assert (one["at_risk"].to_numpy() == ref["at_risk"].to_numpy()).all()
        assert (one["cum_chargeoff"].to_numpy() == ref["cum_chargeoff"].to_numpy()).all()


def _cells(rows):
    df = pd.DataFrame(rows, columns=["lender", "score_b", "aj_chargeoff", "cum_chargeoff"])
    df["n_loans"], df["at_risk"] = 5000, 1000
    return usable_cells(df)


def test_a_cell_with_few_charge_offs_cannot_be_the_lower_end():
    cells = _cells([("x", "700", 0.050, 200), ("y", "700", 0.001, 2), ("z", "700", 0.005, 30)])
    r = bucket_ratios(cells).iloc[0]
    assert r["worst"] == "x" and r["best"] == "z" and r["ratio"] == pytest.approx(10.0) and r["thin"] == "y"
    assert bucket_ratios(cells, min_events=0).iloc[0]["ratio"] == pytest.approx(50.0)     # what the page used to print
    alone = _cells([("x", "720", 0.050, 200), ("y", "720", 0.001, 2), ("z", "720", 0.002, 4)])
    r = bucket_ratios(alone).iloc[0]
    assert np.isnan(r["ratio"]) and r["best"] is None                 # no second lender with ten: no ratio at all


def test_the_rule_needs_the_event_counts():
    cells = _cells([("x", "700", 0.05, 200), ("y", "700", 0.01, 20), ("z", "700", 0.02, 30)]).drop(columns="cum_chargeoff")
    with pytest.raises(ValueError, match="charge-off rule"):
        bucket_ratios(cells)


def test_band_levels_average_over_the_buckets_every_lender_has():
    cells = _cells([("x", "580", 0.30, 500), ("x", "600", 0.20, 500), ("y", "600", 0.10, 400), ("y", "620", 0.01, 50)])
    levels, r = band_levels(cells, 580, 620)
    assert r["buckets"] == "600" and levels.loc["x", "rate"] == pytest.approx(0.20)
    assert r["worst"] == "x" and r["best"] == "y" and r["ratio"] == pytest.approx(2.0)


def test_pair_ratios_need_ten_charge_offs_in_the_lower_lender_both_ways():
    pooled = _cells([("x", "700", 0.040, 100), ("y", "700", 0.004, 40), ("z", "700", 0.002, 3)])
    within = _cells([("x", "700", 0.030, 60), ("y", "700", 0.006, 12), ("z", "700", 0.001, 1)]).assign(orig_year=2024)
    pr = pair_ratios(within, pooled)
    assert pr[["higher", "lower"]].values.tolist() == [["x", "y"]]
    assert pr.iloc[0]["within_over_pooled"] == pytest.approx(0.5)


# ----------------------------------------------------------------------------- the committed results


@pytest.fixture(scope="module")
def gap():
    p = AUTOS / "b1_gap.csv"
    assert p.exists(), "data/results/autos/b1_gap.csv missing: run `absrisk analyze autos`"
    return pd.read_csv(p)


def test_no_committed_ratio_divides_by_fewer_than_ten_charge_offs(gap):
    rated = gap[gap["stat"].isin(["bucket", "band"]) & gap["ratio"].notna()]
    assert len(rated) >= 5
    assert (rated["best_events"] >= lender_gap.MIN_EVENTS).all(), rated[["stat", "variant", "lo", "best", "best_events"]]
    assert (gap["pool_offset"].dropna() >= 0).all() and set(gap.loc[gap["stat"] != "offset", "pool_offset"]) == {survival.POOL_OFFSET}


def test_every_committed_ratio_carries_an_interval(gap):
    rated = gap[gap["stat"].isin(["bucket", "median", "band", "pairs"]) & gap["ratio"].notna()]
    assert rated["lo95"].notna().all() and rated["hi95"].notna().all()
    assert (rated["lo95"] <= rated["hi95"]).all()
    assert (gap.loc[gap["ratio"].notna() & (gap["stat"] != "offset"), "n_boot"] >= 200).all()


def test_committed_b1_tables_count_from_the_fourth_month_in_the_pool(gap):
    at12 = pd.read_csv(AUTOS / "b1_at_12.csv")
    assert "cum_chargeoff" in at12 and (AUTOS / "b1_at_12_fresh.csv").exists()
    cells = usable_cells(at12)
    main = gap[(gap["stat"] == "median") & (gap["variant"] == "all")].iloc[0]
    assert main["ratio"] == pytest.approx(bucket_ratios(cells)["ratio"].median(), rel=1e-12)


def _independent_median(k: int, min_events: int) -> float:
    """The page's median same-bucket ratio recomputed from the committed parquet without absrisk: the reviewer's
    round-2 snippet (REVIEW.md R2-1), with each loan counted from k months after it entered its trust, cells usable at
    1,500 loans and 250 at risk at twelve months on that clock, and a lower end needing `min_events` charge-offs."""
    d = pd.concat(pd.read_parquet(f) for f in sorted(glob.glob(str(REPO / "data" / "autos" / "*.parquet"))))
    d = d[~d["commercial"].fillna(False).astype(bool)].reset_index(drop=True)

    def mi(s):
        t = pd.to_datetime(s)
        return t.dt.year * 12 + t.dt.month
    fp, om, lp = mi(d.first_period), mi(d.orig_month), mi(d.last_period)
    ev = np.where(d.exit_type == "chargeoff", "co",
                  np.where(d.exit_type.isin(["prepay", "repurchase", "other", "absent"]), "x", "c"))
    ex = mi(d.zb_date).where(d.zb_date.notna(), mi(d.exit_period)).fillna(fp + d.months_observed - 1).where(ev != "c", lp)
    lag = pd.Series(0, index=d.index)
    for _, g in d.groupby("deal"):
        first = g.first_period == g.first_period.min()
        if ((ex[g.index] < fp[g.index]) & first & (ev[g.index] != "c")).any():
            lag[g.index[first]] = 1
    e0 = (fp - lag - om).clip(lower=0).to_numpy()
    x0 = (e0 + (ex - (fp - lag)).clip(lower=0)).to_numpy()

    def aj12(m):
        e, x, v = e0[m] + k, x0[m], ev[m]
        e, x, v = e[x >= e], x[x >= e], v[x >= e]
        n = np.array([((e <= t) & (x >= t)).sum() for t in range(13)])
        co = np.array([((x == t) & (v == "co")).sum() for t in range(13)])
        out = np.array([((x == t) & (v != "c")).sum() for t in range(13)])
        s = np.concatenate([[1.0], np.cumprod(1 - out / np.maximum(n, 1))[:-1]])
        return (s * co / np.maximum(n, 1)).sum(), n[-1], co.sum()

    b = (d.score // 20 * 20).to_numpy()
    ratios = []
    for lo in range(660, 800, 20):
        cells = {}
        for lender in sorted(d.lender.unique()):
            m = (b == lo) & (d.lender == lender).to_numpy()
            if m.sum() >= 1500:
                rate, at_risk, events = aj12(m)
                if at_risk >= 250:
                    cells[lender] = (rate, events)
        if len(cells) < 3:
            continue
        worst = max(cells, key=lambda x: cells[x][0])
        low = [v[0] for lender, v in cells.items() if lender != worst and v[1] >= min_events]
        if low and min(low) > 0:
            ratios.append(cells[worst][0] / min(low))
    return float(np.median(ratios))


@pytest.mark.slow
def test_the_headline_median_rederives_from_the_parquet_without_absrisk(gap):
    main = gap[(gap["stat"] == "median") & (gap["variant"] == "all")].iloc[0]
    assert _independent_median(survival.POOL_OFFSET, lender_gap.MIN_EVENTS) == pytest.approx(main["ratio"], rel=1e-9)
    off0 = gap[(gap["stat"] == "offset") & (gap["variant"] == "pool_offset_0")].iloc[0]
    assert _independent_median(0, lender_gap.MIN_EVENTS) == pytest.approx(off0["ratio"], rel=1e-9)


def test_the_autos_page_prints_the_gap_with_its_interval(gap):
    t = unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", (REPO / "docs" / "autos.html").read_text(encoding="utf-8"))))
    main = gap[(gap["stat"] == "median") & (gap["variant"] == "all")].iloc[0]
    assert (f"the highest one-year charge-off rate is a median {main['ratio']:.0f} times the lowest "
            f"(95% interval {main['lo95']:.0f} to {main['hi95']:.0f})") in t
    assert "survives the obvious objection" not in t and "61 times" not in t
    assert "fourth month in the trust" in t and "The pool window." in t
    assert "Charge-off by 12 months" in t                                # the fresh-entrant cut at 12 months too
