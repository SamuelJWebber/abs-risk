"""The same-score lender gap on the autos page: which cells may be compared, which may divide, and how sure.

The autos page compares lenders inside one 20-point score bucket at a time: the highest one-year cumulative
charge-off over the lowest. Review round 2 (REVIEW.md R2-1) found the published 50 times inflated twice over:

- the curves counted a loan from its first month in the trust, when it can hardly charge off because it had to be
  current to be sold in. `survival.POOL_OFFSET` now counts it from its fourth month there;
- every one of the seven ratios divided by a cell with one to three charge-offs, and the lowest of several noisy
  small cells is biased low, which biases the ratio up. A cell now needs `MIN_EVENTS` charge-offs by the horizon
  before it can be the lower end of a ratio, and every ratio carries a percentile interval from resampling loans
  within each lender (`gap_table`).

The intervals hold the comparison fixed (which cells are usable and which may divide are decided once, on the
data) and let only the rates move. They carry no deal-to-deal luck: each lender here has one or two deals, and the
hazard model on the same page measures that spread separately (about 0.33 in log odds).
"""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

from . import survival

MIN_LOANS = 1500        # loans in the cell
MIN_AT_RISK = 250       # still under observation at the horizon: a cell can have many loans but few old enough
MIN_EVENTS = 10         # charge-offs by the horizon before a cell may be the lower end of a ratio
MIN_LENDERS = 3         # lenders with a usable cell before a bucket is compared at all
GAP_LO, GAP_HI = 660, 780          # the buckets 660-679 ... 780-799, where prime and subprime lenders overlap
# (name, horizon, lowest bucket, highest bucket). Until 2026-11-10 the page also had a 700-779 band at 12 months
# ("61 times"); it averaged each lender over the buckets it had, which for Exeter was one bucket and for Honda four,
# so it was not a comparison at one score. The bucket-by-bucket ratios cover that range.
BANDS = (("480-639", 24, 480, 620),)
N_BOOT = 500
EVENTS = "cum_chargeoff"

GAP_COLUMNS = ["stat", "variant", "horizon", "lo", "lender", "worst", "best", "worst_rate", "best_rate", "worst_events",
               "best_events", "rate", "events", "n", "ratio", "lo95", "hi95", "range_lo", "range_hi", "thin",
               "buckets", "pool_offset", "n_boot"]


def usable_cells(at: pd.DataFrame, cif: pd.DataFrame | None = None,
                 max_first_age: int | None = survival.MAX_FIRST_AGE,
                 min_risk_set: int = survival.MIN_RISK_SET) -> pd.DataFrame:
    """Cells with enough loans and enough of them still under observation at the horizon, with `lo` the bucket's
    lower edge as an integer.

    When `cif` is given (or `at` carries `first_age`), a cell whose first observed age with at least `min_risk_set`
    loans at risk exceeds `max_first_age` is excluded (REVIEW.md abs-A-4: Capital One's loans enter at age 11,
    Toyota's at 9 and Honda's at 6, so a '12-month' cell for Capital One or Toyota is two or four months of exposure)."""
    a = at[(at["score_b"].astype(str) != "none") & (at["n_loans"] >= MIN_LOANS) & (at["at_risk"] >= MIN_AT_RISK)].copy()
    if cif is not None and not cif.empty and "first_age" not in a:
        fa = first_age_table(cif, [c for c in ("orig_year", "lender", "score_b") if c in a and c in cif],
                             min_risk_set=min_risk_set)
        for k in fa.columns:
            if k != "first_age":
                a[k] = a[k].astype(str)
                fa[k] = fa[k].astype(str)
        a = a.merge(fa, on=[c for c in fa.columns if c != "first_age"], how="left")
    if max_first_age is not None and "first_age" in a:
        a = a[a["first_age"].notna() & (a["first_age"] <= max_first_age)].copy()
    a["lo"] = a["score_b"].astype(int)
    return a


def first_age_table(cif: pd.DataFrame, by: list[str] = ["lender", "score_b"],
                    min_risk_set: int = survival.MIN_RISK_SET) -> pd.DataFrame:
    """Per cell in `cif`, the earliest age at which `at_risk >= min_risk_set` (`first_age`, nan if never reached)."""
    ok = cif[cif["at_risk"] >= max(int(min_risk_set), 1)]
    first = ok.groupby(by, observed=True)["age"].min().rename("first_age").reset_index()
    all_keys = cif[by].drop_duplicates()
    return all_keys.merge(first, on=by, how="left")


def blank_late_entry_cells(table: pd.DataFrame, cif: pd.DataFrame,
                           by: list[str] = ["lender", "score_b"],
                           cols: tuple[str, ...] = ("aj_chargeoff", "aj_lo95", "aj_hi95", "km_chargeoff"),
                           max_first_age: int = survival.MAX_FIRST_AGE,
                           min_risk_set: int = survival.MIN_RISK_SET) -> pd.DataFrame:
    """Blank cumulative-incidence columns in `table` for any cell whose first observed age in `cif` (with at least
    `min_risk_set` loans at risk) is past `max_first_age` (REVIEW.md abs-A-4). Also attaches `first_age`."""
    fa = first_age_table(cif, by=by, min_risk_set=min_risk_set)
    out = table.copy()
    join_keys = [k for k in by if k in out and k in fa]
    left_types = {k: out[k].dtype for k in join_keys}
    for k in join_keys:
        out[k] = out[k].astype(str)
        fa[k] = fa[k].astype(str)
    if "first_age" in out:
        out = out.drop(columns=["first_age"])
    out = out.merge(fa, on=join_keys, how="left")
    for k, dt in left_types.items():
        try:
            out[k] = out[k].astype(dt)
        except (ValueError, TypeError):
            pass
    late = out["first_age"].isna() | (out["first_age"] > max_first_age)
    for c in cols:
        if c in out:
            out.loc[late, c] = np.nan
    return out


def _events(cells: pd.DataFrame, min_events: int) -> pd.Series:
    if EVENTS in cells:
        return cells[EVENTS].astype(float)
    if min_events > 0:
        raise ValueError(f"cells carry no {EVENTS!r} column, so the {min_events}-charge-off rule cannot be applied")
    return pd.Series(np.inf, index=cells.index)


def scale_900_lenders(summary: pd.DataFrame | None) -> list[str]:
    """Lenders whose reported scores run past 850: the 250-900 auto-industry FICO scale (FICO Auto Score). A lender on
    the 300-850 scale cannot report a 900, so these are the lenders that can be compared on one scale (R1-8)."""
    if summary is None or summary.empty or "score_above_850_share" not in summary:
        return []
    # at least one loan in a thousand above 850: a handful of 851-854 scores (AmeriCredit's) is noise, not a scale
    w = summary.assign(above=summary["score_above_850_share"] * summary["n_loans"]).groupby("lender")[["above", "n_loans"]].sum()
    share = w["above"] / w["n_loans"]
    return sorted(share[share >= 0.001].index)


def bucket_ratios(cells: pd.DataFrame, lo: int = GAP_LO, hi: int = GAP_HI, min_lenders: int = MIN_LENDERS,
                  by: tuple[str, ...] = (), min_events: int = MIN_EVENTS) -> pd.DataFrame:
    """Inside each score bucket (and each `by` group), the highest charge-off over the lowest across lenders.

    `cells` are usable cells at one horizon. A bucket is compared only where at least `min_lenders` lenders have a
    cell, so every ratio is a comparison at one score. The lower end is the lowest cell of another lender with at
    least `min_events` charge-offs; a bucket without one keeps its row with no ratio. `thin` names the lenders that
    sit below that lower end on fewer charge-offs. Columns: by..., lo, n_lenders, worst, best, worst_rate,
    best_rate, worst_events, best_events, ratio, thin."""
    c = cells[(cells["lo"] >= lo) & (cells["lo"] <= hi)]
    rows = []
    for keys, g in c.groupby(list(by) + ["lo"]):
        if g["lender"].nunique() < min_lenders:
            continue
        keys = keys if isinstance(keys, tuple) else (keys,)
        ev = _events(g, min_events)
        w = g.loc[g["aj_chargeoff"].idxmax()]
        row = {**dict(zip(list(by) + ["lo"], keys)), "n_lenders": g["lender"].nunique(), "worst": w["lender"],
               "best": None, "worst_rate": float(w["aj_chargeoff"]), "best_rate": np.nan,
               "worst_events": float(ev[w.name]), "best_events": np.nan, "ratio": np.nan, "thin": ""}
        cand = g[(ev >= min_events) & (g["lender"] != w["lender"])]
        if not cand.empty:
            b = cand.loc[cand["aj_chargeoff"].idxmin()]
            thin = g[(g["aj_chargeoff"] < b["aj_chargeoff"]) & (ev < min_events)]["lender"]
            row.update(best=b["lender"], best_rate=float(b["aj_chargeoff"]), best_events=float(ev[b.name]),
                       ratio=float(w["aj_chargeoff"] / b["aj_chargeoff"]) if b["aj_chargeoff"] > 0 else np.nan,
                       thin=",".join(sorted(set(thin))))
        rows.append(row)
    cols = list(by) + ["lo", "n_lenders", "worst", "best", "worst_rate", "best_rate", "worst_events", "best_events",
                       "ratio", "thin"]
    return pd.DataFrame(rows, columns=cols)


def band_levels(cells: pd.DataFrame, lo: int, hi: int, min_events: int = MIN_EVENTS) -> tuple[pd.DataFrame, dict]:
    """Each lender's charge-off averaged over the buckets between `lo` and `hi` (lower edges) that every lender in
    the band has, so the averages are over the same scores, and the highest against the lowest lender whose cells
    there hold at least `min_events` charge-offs between them. `out['buckets']` names the common buckets."""
    band = cells[(cells["lo"] >= lo) & (cells["lo"] <= hi)]
    n_lenders = band["lender"].nunique()
    per_bucket = band.groupby("lo")["lender"].nunique()
    common = sorted(int(b) for b in per_bucket[per_bucket == n_lenders].index)
    band = band[band["lo"].isin(common)]
    ev = _events(band, min_events)
    g = (band.assign(_ev=ev).groupby("lender")
         .agg(rate=("aj_chargeoff", "mean"), events=("_ev", "sum"), n_buckets=("lo", "size"))
         .sort_values("rate", ascending=False))
    out = {"worst": None, "best": None, "worst_rate": np.nan, "best_rate": np.nan, "worst_events": np.nan,
           "best_events": np.nan, "ratio": np.nan, "thin": "", "n": int(len(g)),
           "buckets": ",".join(str(b) for b in common)}
    if len(g) < 2:
        return g, out
    worst = g.index[0]
    out.update(worst=worst, worst_rate=float(g.loc[worst, "rate"]), worst_events=float(g.loc[worst, "events"]))
    cand = g[(g["events"] >= min_events) & (g.index != worst)]
    if not cand.empty:
        best = cand["rate"].idxmin()
        out.update(best=best, best_rate=float(cand.loc[best, "rate"]), best_events=float(cand.loc[best, "events"]),
                   ratio=float(g.loc[worst, "rate"] / cand.loc[best, "rate"]) if cand.loc[best, "rate"] > 0 else np.nan,
                   thin=",".join(sorted(g[(g["rate"] < cand.loc[best, "rate"]) & (g["events"] < min_events)].index)))
    return g, out


def pair_ratios(cohort_cells: pd.DataFrame, pooled_cells: pd.DataFrame, min_events: int = MIN_EVENTS) -> pd.DataFrame:
    """Same two lenders, same score bucket: their charge-off ratio inside one origination year against the pooled one.

    If a pooled lender gap were a vintage gap, the ratio inside a single year would sit nearer 1 than the pooled
    ratio. Both inputs are usable cells at one horizon. A pair counts only when the lower lender's cell holds at
    least `min_events` charge-offs both inside the year and pooled, so no ratio divides by a handful of events (or by
    zero). Columns: orig_year, lo, higher, lower, within, pooled, within_over_pooled."""
    pev = _events(pooled_cells, min_events)
    pooled = {(r.lender, r.lo): (r.aj_chargeoff, e) for r, e in zip(pooled_cells.itertuples(), pev)}
    cev = _events(cohort_cells, min_events)
    rows = []
    for (year, lo), g in cohort_cells.assign(_ev=cev).groupby(["orig_year", "lo"]):
        rates = dict(zip(g["lender"], g["aj_chargeoff"]))
        evs = dict(zip(g["lender"], g["_ev"]))
        for a, b in itertools.permutations(rates, 2):
            pa, pb = pooled.get((a, lo)), pooled.get((b, lo))
            if not (rates[a] > rates[b] > 0) or pa is None or pb is None or not pb[0] > 0:
                continue
            if evs[b] < min_events or pb[1] < min_events:
                continue
            rows.append({"orig_year": year, "lo": lo, "higher": a, "lower": b, "within": rates[a] / rates[b],
                         "pooled": pa[0] / pb[0], "within_over_pooled": (rates[a] / rates[b]) / (pa[0] / pb[0])})
    return pd.DataFrame(rows, columns=["orig_year", "lo", "higher", "lower", "within", "pooled", "within_over_pooled"])


# ----------------------------------------------------------------------------- life tables for many groups at once


class Clock:
    """Per-loan survival clock (`survival.ages` with a pool offset) as arrays, for `group_life_tables`."""

    def __init__(self, loans: pd.DataFrame, pool_offset: int = survival.POOL_OFFSET):
        a = survival.ages(loans, pool_offset=pool_offset)
        self.entry = a["entry_age"].to_numpy(dtype=np.int64)
        self.exit = a["exit_age"].to_numpy(dtype=np.int64)
        ev = a["event"].to_numpy()
        self.co = ev == "chargeoff"
        self.comp = ev == "prepay"
        self.keep = self.exit >= self.entry
        self.pool_offset = pool_offset


def group_life_tables(gid: np.ndarray, n_groups: int, clock: Clock, horizon: int, w: np.ndarray | None = None,
                      min_risk_set: int = survival.MIN_RISK_SET):
    """At-risk counts, charge-offs and Aalen-Johansen charge-off incidence for every group at ages 0..horizon, with
    one bincount per quantity instead of a loop over groups. Same estimator as `survival.cumulative_incidence`.
    `gid` is the group of each loan (-1: in no group); `w` optional loan weights; `min_risk_set` suppresses hazard
    at ages where fewer than that many loans are at risk (REVIEW.md abs-A-7). Returns (at_risk, d_co, aj), each
    of shape (n_groups, horizon + 1)."""
    w = np.ones(len(gid)) if w is None else np.asarray(w, dtype=float)
    ok = clock.keep & (gid >= 0) & (w > 0)
    W = horizon + 2
    e = np.clip(clock.entry[ok], 0, horizon + 1)
    x = np.clip(clock.exit[ok], 0, horizon + 1)
    g, ww = gid[ok].astype(np.int64), w[ok]
    size = n_groups * W
    entered = np.cumsum(np.bincount(g * W + e, weights=ww, minlength=size).reshape(n_groups, W), axis=1)[:, :horizon + 1]
    left = np.cumsum(np.bincount(g * W + x, weights=ww, minlength=size).reshape(n_groups, W), axis=1)
    exited_before = np.concatenate([np.zeros((n_groups, 1)), left[:, :horizon]], axis=1)
    at_risk = entered - exited_before
    co, cp = clock.co[ok], clock.comp[ok]
    d_co = np.bincount(g[co] * W + x[co], weights=ww[co], minlength=size).reshape(n_groups, W)[:, :horizon + 1]
    d_cp = np.bincount(g[cp] * W + x[cp], weights=ww[cp], minlength=size).reshape(n_groups, W)[:, :horizon + 1]
    g_totals = np.bincount(g, weights=ww, minlength=n_groups)[:, None]
    floor = np.where(g_totals >= max(int(min_risk_set), 1), max(int(min_risk_set), 1), 1.0)
    enough = at_risk >= floor
    with np.errstate(divide="ignore", invalid="ignore"):
        h_co = np.where(enough, d_co / at_risk, 0.0)
        h_all = np.where(enough, (d_co + d_cp) / at_risk, 0.0)
    s = np.cumprod(1 - h_all, axis=1)
    s_prev = np.concatenate([np.ones((n_groups, 1)), s[:, :-1]], axis=1)
    return at_risk, d_co, np.cumsum(s_prev * h_co, axis=1)


def _grouping(loans: pd.DataFrame, by: list[str]) -> tuple[np.ndarray, pd.DataFrame]:
    keys = loans[by].astype(str)
    codes, uniq = pd.factorize(pd.MultiIndex.from_frame(keys))
    frame = pd.DataFrame(list(uniq), columns=by)
    frame["n_loans"] = np.bincount(codes[codes >= 0], minlength=len(frame))
    frame["gid"] = np.arange(len(frame))
    return codes.astype(np.int64), frame


def _cells_at(frame: pd.DataFrame, at_risk, d_co, aj, h: int) -> pd.DataFrame:
    c = frame.copy()
    c["at_risk"] = at_risk[:, h]
    c[EVENTS] = d_co[:, :h + 1].sum(axis=1)
    c["aj_chargeoff"] = aj[:, h]
    return c


# ----------------------------------------------------------------------------- the table behind the page


def _gap_stats(c12: pd.DataFrame, c24: pd.DataFrame, k12: pd.DataFrame | None, s900: list[str]) -> list[dict]:
    """Every ratio the page prints, from usable cells at 12 and 24 months (and cohort cells at 12)."""
    out: list[dict] = []
    variants = [("all", c12), ("without_exeter", c12[c12["lender"] != "exeter"])]
    if len(s900) >= 3:
        variants.append(("scale_900", c12[c12["lender"].isin(s900)]))
    for name, c in variants:
        br = bucket_ratios(c)
        for r in br.itertuples():
            out.append({"stat": "bucket", "variant": name, "horizon": 12, "lo": int(r.lo), "worst": r.worst,
                        "best": r.best, "worst_rate": r.worst_rate, "best_rate": r.best_rate,
                        "worst_events": r.worst_events, "best_events": r.best_events, "n": int(r.n_lenders),
                        "ratio": r.ratio, "thin": r.thin})
        ok = br["ratio"].dropna()
        out.append({"stat": "median", "variant": name, "horizon": 12, "n": int(len(ok)),
                    "ratio": float(ok.median()) if len(ok) else np.nan,
                    "range_lo": float(ok.min()) if len(ok) else np.nan, "range_hi": float(ok.max()) if len(ok) else np.nan})
    for name, h, lo, hi in BANDS:
        levels, r = band_levels(c24 if h == 24 else c12, lo, hi)
        for lender, lv in levels.iterrows():
            out.append({"stat": "band_level", "variant": name, "horizon": h, "lender": lender, "rate": lv["rate"],
                        "events": lv["events"], "n": int(lv["n_buckets"])})
        out.append({"stat": "band", "variant": name, "horizon": h, **{k: r[k] for k in (
            "worst", "best", "worst_rate", "best_rate", "worst_events", "best_events", "ratio", "thin", "n", "buckets")}})
    if k12 is not None and not k12.empty:
        pr = pair_ratios(k12, c12)
        big = pr[pr["pooled"] >= 10]
        out.append({"stat": "pairs", "variant": "vintage", "horizon": 12, "n": int(len(pr)),
                    "ratio": float(np.exp(np.log(pr["within_over_pooled"]).median())) if len(pr) else np.nan})
        for name, col in (("pairs_big_within", "within"), ("pairs_big_pooled", "pooled")):
            out.append({"stat": name, "variant": "vintage", "horizon": 12, "n": int(len(big)),
                        "ratio": float(big[col].median()) if len(big) else np.nan})
    return out


def _key(r: dict) -> tuple:
    return (r["stat"], r["variant"], r.get("lo"), r.get("lender"))


def gap_table(loans: pd.DataFrame, s900: list[str] | None = None, pool_offset: int = survival.POOL_OFFSET,
              n_boot: int = N_BOOT, seed: int = 0, sensitivity_offsets: tuple[int, ...] = (0, 6)) -> pd.DataFrame:
    """b1_gap.csv: every lender ratio on the autos page, with a 95% percentile interval from `n_boot` resamples of
    loans within each lender, and the median same-bucket ratio under other pool offsets (stat 'offset').

    The usable cells and the cells allowed to divide are fixed from the data; a replicate only moves the rates."""
    df = loans.copy()
    df["score_b"] = survival.score_bucket(df["score"])
    has_year = "orig_month" in df
    if has_year:
        df["orig_year"] = pd.to_datetime(df["orig_month"]).dt.year.astype("Int64").astype(str)
    s900 = list(s900 or [])
    clock = Clock(df, pool_offset)
    g1, f1 = _grouping(df, ["lender", "score_b"])
    ar, dc, aj = group_life_tables(g1, len(f1), clock, 24)
    c12 = usable_cells(_cells_at(f1, ar, dc, aj, 12))
    c24 = usable_cells(_cells_at(f1, ar, dc, aj, 24))
    k12 = None
    if has_year:
        g2, f2 = _grouping(df, ["orig_year", "lender", "score_b"])
        ar2, dc2, aj2 = group_life_tables(g2, len(f2), clock, 12)
        k12 = usable_cells(_cells_at(f2, ar2, dc2, aj2, 12))
    point = _gap_stats(c12, c24, k12, s900)
    reps: dict[tuple, list[float]] = {_key(r): [] for r in point}
    if n_boot > 0:
        rng = np.random.default_rng(seed)
        codes, _ = pd.factorize(df["lender"])
        by_lender = [np.flatnonzero(codes == i) for i in range(codes.max() + 1)]
        for _ in range(n_boot):
            w = np.empty(len(df))
            for ix in by_lender:
                w[ix] = np.bincount(rng.integers(0, len(ix), len(ix)), minlength=len(ix))
            _, _, ajb = group_life_tables(g1, len(f1), clock, 24, w)
            r12, r24 = c12.copy(), c24.copy()
            r12["aj_chargeoff"] = ajb[r12["gid"].to_numpy(), 12]
            r24["aj_chargeoff"] = ajb[r24["gid"].to_numpy(), 24]
            rk = None
            if k12 is not None:
                _, _, ajk = group_life_tables(g2, len(f2), clock, 12, w)
                rk = k12.copy()
                rk["aj_chargeoff"] = ajk[rk["gid"].to_numpy(), 12]
            got = {_key(r): r.get("ratio") for r in _gap_stats(r12, r24, rk, s900)}
            for k in reps:
                v = got.get(k)
                reps[k].append(np.nan if v is None else float(v))
    rows = []
    for r in point:
        val = r.get("ratio")
        lo95 = hi95 = np.nan
        if val is not None and np.isfinite(val):
            v = np.array(reps[_key(r)], dtype=float)
            v = v[np.isfinite(v)]
            if len(v):
                lo95, hi95 = (float(x) for x in np.percentile(v, [2.5, 97.5]))
        rows.append({**r, "lo95": lo95, "hi95": hi95, "pool_offset": pool_offset, "n_boot": n_boot})
    for k in sensitivity_offsets:
        if k == pool_offset:
            continue
        ck = Clock(df, k)
        a, d, j = group_life_tables(g1, len(f1), ck, 12)
        br = bucket_ratios(usable_cells(_cells_at(f1, a, d, j, 12)))
        ok = br["ratio"].dropna()
        rows.append({"stat": "offset", "variant": f"pool_offset_{k}", "horizon": 12, "n": int(len(ok)),
                     "ratio": float(ok.median()) if len(ok) else np.nan,
                     "range_lo": float(ok.min()) if len(ok) else np.nan, "range_hi": float(ok.max()) if len(ok) else np.nan,
                     "pool_offset": k, "n_boot": 0})
    return pd.DataFrame(rows).reindex(columns=GAP_COLUMNS)


# ----------------------------------------------------------------------------- two named lenders, loan age held fixed

# The highest-over-lowest median above changes with which low lender happens to hold ten charge-offs (13 with an
# eleven-event floor, 8 with ten-point buckets, 17 with 25-point ones: REVIEW.md abs-A-3). A fixed pair of lenders,
# pooled over score bucket and month of age, does not have that knife edge, and it shows what the median hides: the
# gap between the same two lenders roughly halves from a loan's first year to its second.
PAIRS = (("exeter", "carmax"), ("santander", "carmax"))
PAIR_WINDOWS = (("year one", 4, 12), ("year two", 13, 24))      # months since origination, inclusive
PAIR_LO, PAIR_HI = 660, 740                                     # buckets 660-679 ... 740-759, where all three lend
STRUCTURE_BINS = {"ltv": [0, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5, 9], "pti": [-1, 0.04, 0.06, 0.08, 0.10, 0.12, 0.15, 9],
                  "orig_term": [0, 48, 60, 66, 72, 75, 99]}
PAIR_COLUMNS = ["window", "age_lo", "age_hi", "higher", "lower", "matched", "ratio", "lo95", "hi95", "events_higher",
                "events_lower", "months_higher", "months_lower", "strata", "pool_offset"]


def mh_rate_ratio(pm_a, ev_a, pm_b, ev_b) -> tuple[float, float, float]:
    """Mantel-Haenszel rate ratio of a over b across strata, with a 95% interval from the Greenland-Robins variance of
    its log. Inputs are per-stratum loan-months at risk and events; strata where either side has no exposure carry no
    comparison and are dropped. Returns (ratio, lo95, hi95), all nan when either side has no event."""
    pm_a, ev_a, pm_b, ev_b = (np.asarray(x, dtype=float) for x in (pm_a, ev_a, pm_b, ev_b))
    ok = (pm_a > 0) & (pm_b > 0)
    pm_a, ev_a, pm_b, ev_b = pm_a[ok], ev_a[ok], pm_b[ok], ev_b[ok]
    total = pm_a + pm_b
    num, den = float((ev_a * pm_b / total).sum()), float((ev_b * pm_a / total).sum())
    if not (num > 0 and den > 0):
        return float("nan"), float("nan"), float("nan")
    var = float(((ev_a + ev_b) * pm_a * pm_b / total ** 2).sum()) / (num * den)
    ratio, half = num / den, 1.959964 * np.sqrt(var)
    return ratio, ratio * float(np.exp(-half)), ratio * float(np.exp(half))


def _loan_months(df: pd.DataFrame, clock: Clock, keys: list[str], age_lo: int, age_hi: int) -> pd.DataFrame:
    """Loan-months at risk and events per (lender, age, keys) for ages age_lo..age_hi on `clock`."""
    idx = np.flatnonzero(clock.keep)
    e, x, co = clock.entry[idx], clock.exit[idx], clock.co[idx]
    base = df.iloc[idx][["lender", *keys]].reset_index(drop=True)
    out = []
    for t in range(age_lo, age_hi + 1):
        at_risk = (e <= t) & (x >= t)
        b = base[at_risk].copy()
        b["age"] = t
        b["months"] = 1.0
        b["events"] = (co[at_risk] & (x[at_risk] == t)).astype(float)
        out.append(b.groupby(["lender", "age", *keys], dropna=False, observed=True)[["months", "events"]].sum().reset_index())
    return pd.concat(out, ignore_index=True)


def fixed_pair_ratios(loans: pd.DataFrame, pairs=PAIRS, windows=PAIR_WINDOWS, lo: int = PAIR_LO, hi: int = PAIR_HI,
                      pool_offset: int = survival.POOL_OFFSET) -> pd.DataFrame:
    """b1_fixed_pairs.csv: for each named pair of lenders and each age window, the Mantel-Haenszel ratio of their
    monthly default rates with the 20-point score bucket and the month of age held fixed (`matched` = 'score'), and
    with loan-to-value, payment-to-income, term and new or used held fixed too ('score and structure').

    A loan-month counts when the loan is under observation at that age on the pool-offset clock; the event is the
    one `survival.ages` reports, so pass the loans through `survival.as_defaults` or `survival.trust_loss` first."""
    df = loans.copy()
    df["sb"] = (pd.to_numeric(df["score"], errors="coerce") // 20 * 20)
    names = sorted({n for p in pairs for n in p})
    df = df[df["lender"].isin(names) & (df["sb"] >= lo) & (df["sb"] <= hi)].reset_index(drop=True)
    cols = PAIR_COLUMNS
    if df.empty:
        return pd.DataFrame(columns=cols)
    structure = []
    for c, edges in STRUCTURE_BINS.items():
        if c in df:
            df[c + "_b"] = pd.cut(pd.to_numeric(df[c], errors="coerce"), edges, labels=False)
            structure.append(c + "_b")
    if "new_used" in df:
        df["nu"] = df["new_used"].astype(str)
        structure.append("nu")
    clock = Clock(df, pool_offset)
    rows = []
    for name, a_lo, a_hi in windows:
        tab = _loan_months(df, clock, ["sb", *structure], a_lo, a_hi)
        for matched, keys in (("score", ["sb"]), ("score and structure", ["sb", *structure])):
            if matched != "score" and not structure:
                continue
            t = tab.dropna(subset=keys).groupby(["lender", "age", *keys], observed=True)[["months", "events"]].sum()
            for higher, lower in pairs:
                if higher not in t.index.get_level_values(0) or lower not in t.index.get_level_values(0):
                    continue
                j = t.loc[higher].join(t.loc[lower], lsuffix="_a", rsuffix="_b", how="inner")
                ratio, lo95, hi95 = mh_rate_ratio(j["months_a"], j["events_a"], j["months_b"], j["events_b"])
                rows.append({"window": name, "age_lo": a_lo, "age_hi": a_hi, "higher": higher, "lower": lower,
                             "matched": matched, "ratio": ratio, "lo95": lo95, "hi95": hi95,
                             "events_higher": float(j["events_a"].sum()), "events_lower": float(j["events_b"].sum()),
                             "months_higher": float(j["months_a"].sum()), "months_lower": float(j["months_b"].sum()),
                             "strata": int(len(j)), "pool_offset": pool_offset})
    return pd.DataFrame(rows, columns=cols)


def cells_frame(loans: pd.DataFrame, by: list[str], horizon: int, pool_offset: int = survival.POOL_OFFSET,
                min_risk_set: int = survival.MIN_RISK_SET) -> pd.DataFrame:
    """Cells at one horizon from `group_life_tables` (no bootstrap): by..., n_loans, at_risk, cum_chargeoff,
    aj_chargeoff. A check on `survival.cumulative_incidence`, which computes the same numbers one group at a time."""
    df = loans.copy()
    if "score_b" in by and "score_b" not in df:
        df["score_b"] = survival.score_bucket(df["score"])
    g, f = _grouping(df, by)
    a, d, j = group_life_tables(g, len(f), Clock(df, pool_offset), horizon, min_risk_set=min_risk_set)
    return _cells_at(f, a, d, j, horizon).drop(columns="gid")
