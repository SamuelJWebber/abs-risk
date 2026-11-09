"""Discrete-time competing-risks hazard (analysis-plan §2, B2).

Each loan contributes one row per month of age (1..months_observed). In its last month it has an event:
charge-off, prepay (prepay + repurchase + other + absent), or none (censored). The month-by-month event is
modelled with two binomial logits on aggregated cells, which is the standard discrete-time competing-risks
approximation and scales to tens of millions of loan-months:

    P(chargeoff at t | at risk at t) = logit^-1(age + months in pool + score buckets + lender + cohort + controls)
    P(prepay    at t | at risk at t) = same form

Months in pool (time since the loan entered the trust) is there because a loan must be current to be sold into a
trust, so a charge-off in its first months in the pool is nearly impossible whatever its age: 0.03% a month in the
first three months against about 1% after nine at Santander's 2025-1 deal. A young deal is all early months, so
without this factor its lender looked safer and two deals of one lender looked further apart than they are (the
deal-to-deal spread fell from 0.21 to 0.14 in log odds in the score specification once it was added).

Continuous controls are binned into quantile groups so rows aggregate; standard errors are clustered by deal.
The lender coefficients at fixed score bucket are the "same score, different lender" answer; the loan-size and
payment-burden bins at fixed score and lender are the "how much does size matter" answer.

Inference with ten deals (REVIEW.md R1-6). Clustering by deal with ten clusters understates widths, so clustered
intervals use t(G-1) critical values. For a lender that owns one deal it is worse than that: the lender dummy
coincides with one cluster, the cluster's score for it is zero at the MLE, and the sandwich carries no between-deal
variance at all, so the interval measures within-deal noise only (about a third of the true spread in a simulation).
`deal_spread_intervals` gives lender intervals that add the deal-to-deal spread, estimated from the lenders that own
two deals, with t critical values on its few degrees of freedom.

Sparse edge levels (REVIEW.md R1-9): a score bucket or origination quarter with a handful of loans and no events
produced odds ratios near 1e-10 with p near 1e-200. `merge_sparse_edges` folds levels at either end of a factor into
their neighbours until each end level has `MIN_LEVEL_LOANS` loans, and `hazard_ratios` blanks any level that still
has no events.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .survival import ages, score_bucket

AGE_BINS = [-1, 3, 6, 9, 12, 18, 24, 36, 48, 60, 10**6]
AGE_LABELS = ["0-3", "4-6", "7-9", "10-12", "13-18", "19-24", "25-36", "37-48", "49-60", "61+"]
POOL_BINS = [-1, 2, 5, 8, 10**6]
POOL_LABELS = ["0-2", "3-5", "6-8", "9+"]
MIN_LEVEL_LOANS = 500


def merge_sparse_edges(labels: pd.Series, order: list[str], min_n: int = MIN_LEVEL_LOANS,
                       tag: tuple[str, str] = ("", "")) -> pd.Series:
    """Fold the sparse levels at each end of an ordered factor into the nearest level that makes the run reach
    `min_n` loans. The merged bottom run takes the label of its highest level, the top run that of its lowest, each
    with an optional prefix from `tag` (('<=', '>=') for quarters; score buckets keep a bare number so the page can
    still read them as numbers). Levels not in `order` (such as 'none') are left alone."""
    counts = labels.value_counts()
    order = [o for o in order if counts.get(o, 0) > 0]
    if len(order) < 3:
        return labels
    mapping: dict[str, str] = {}
    run, n = [], 0
    for lv in order:                                          # bottom edge
        run.append(lv)
        n += int(counts.get(lv, 0))
        if n >= min_n:
            break
    if len(run) > 1:
        mapping.update({lv: tag[0] + run[-1] for lv in run})
    top, n = [], 0
    for lv in reversed(order):                                # top edge
        if lv in mapping:
            break
        top.append(lv)
        n += int(counts.get(lv, 0))
        if n >= min_n:
            break
    if len(top) > 1:
        mapping.update({lv: tag[1] + top[-1] for lv in top})
    return labels.map(lambda v: mapping.get(v, v)) if mapping else labels


def expand_loan_months(loans: pd.DataFrame, keep: list[str]) -> pd.DataFrame:
    """One row per loan per observed age (entry_age..exit_age, months since origination) with the loan's fixed
    attributes and event flags at exit_age. Delayed entry: a loan contributes no rows before it was observed."""
    a = ages(loans)
    entry = a["entry_age"].to_numpy()
    exit_ = a["exit_age"].to_numpy()
    ev = a["event"].to_numpy()
    m = (exit_ - entry + 1).astype(int)
    idx = np.repeat(np.arange(len(loans)), m)
    age = np.concatenate([np.arange(e, x + 1) for e, x in zip(entry, exit_)]) if len(m) else np.array([], dtype=int)
    base = loans.iloc[idx][keep].reset_index(drop=True)
    base["age"] = age
    base["pool"] = age - np.repeat(entry, m)                     # months since the loan entered the trust
    last = age == np.repeat(exit_, m)
    ev_rep = ev[idx]
    base["ev_chargeoff"] = (last & (ev_rep == "chargeoff")).astype(int)
    base["ev_prepay"] = (last & (ev_rep == "prepay")).astype(int)
    return base


def add_design_columns(loans: pd.DataFrame, control_bins: int = 5) -> pd.DataFrame:
    """Categorical versions of the covariates the hazard model uses."""
    df = loans.copy()
    df["score_b"] = score_bucket(df["score"])
    numeric = sorted((s for s in df["score_b"].dropna().unique() if str(s).isdigit()), key=int)
    df["score_b"] = merge_sparse_edges(df["score_b"].astype(str), [str(s) for s in numeric])
    df["cohort_q"] = pd.to_datetime(df["orig_month"]).dt.to_period("Q").astype(str)
    df["cohort_q"] = merge_sparse_edges(df["cohort_q"], sorted(df["cohort_q"].unique()), tag=("<=", ">="))
    for col, name in (("orig_amount", "amount_q"), ("pti", "pti_q"), ("ltv", "ltv_q"), ("orig_apr", "apr_q")):
        if col in df:
            x = df[col].astype(float)
            try:
                df[name] = pd.qcut(x, control_bins, labels=False, duplicates="drop").astype("Int64").astype("string").fillna("none")
            except ValueError:
                df[name] = "none"
    return df


def aggregate_cells(loan_months: pd.DataFrame, cells: list[str]) -> pd.DataFrame:
    """Collapse loan-months to cells: exposures, charge-off events, prepay events. Loan age (`age_b`) and months in
    pool (`pool_b`) are always cell keys, so any specification can use them."""
    lm = loan_months.copy()
    lm["age_b"] = pd.cut(lm["age"], AGE_BINS, labels=AGE_LABELS, right=True).astype(str)
    pool = lm["pool"] if "pool" in lm else lm["age"]
    lm["pool_b"] = pd.cut(pool, POOL_BINS, labels=POOL_LABELS, right=True).astype(str)
    cells = [c for c in cells if c not in ("age_b", "pool_b")]
    g = lm.groupby(cells + ["age_b", "pool_b"], dropna=False, observed=True)
    out = g.agg(exposure=("age", "size"), d_chargeoff=("ev_chargeoff", "sum"), d_prepay=("ev_prepay", "sum")).reset_index()
    return out


def fit_hazards(cells_df: pd.DataFrame, factors: list[str], cluster: str = "deal", baseline: dict | None = None):
    """Two binomial GLMs (logit link) on aggregated cells with cluster-robust SEs.

    Returns {"chargeoff": result, "prepay": result, "design_info": {...}}. Coefficients are log-odds relative to
    the baseline level of each factor (first level in sorted order unless `baseline` names one).
    """
    import statsmodels.api as sm

    X = _dummies(cells_df, factors, baseline or {})
    X = sm.add_constant(X, has_constant="add")
    groups = cells_df[cluster].astype("category").cat.codes.to_numpy() if cluster in cells_df else None
    res = {}
    # cluster-robust covariance needs more cells than parameters and more than one cluster; otherwise plain
    # model-based errors, and the design_info says so
    n_params = X.shape[1]
    robust = groups is not None and len(np.unique(groups)) > 1 and len(cells_df) > n_params + 1
    for event in ("chargeoff", "prepay"):
        y = cells_df[f"d_{event}"].to_numpy(dtype=float)
        n = cells_df["exposure"].to_numpy(dtype=float)
        endog = np.column_stack([y, n - y])
        model = sm.GLM(endog, X, family=sm.families.Binomial())
        if robust:
            res[event] = model.fit(cov_type="cluster", cov_kwds={"groups": groups})
        else:
            res[event] = model.fit()
    n_clusters = int(len(np.unique(groups))) if groups is not None else 0
    res["design_info"] = {"columns": list(X.columns), "n_cells": len(cells_df), "n_params": int(n_params),
                          "n_exposure": float(cells_df["exposure"].sum()), "n_clusters": n_clusters,
                          "cov_type": (f"cluster by {cluster} ({n_clusters} clusters), t({n_clusters - 1}) critical values"
                                       if robust else "model-based (design too small for clustering)"),
                          "t_df": n_clusters - 1 if robust else None}
    return res


def hazard_ratios(result, prefix: str, t_df: int | None = None, events: dict | None = None) -> pd.DataFrame:
    """Odds ratios with 95% intervals for the dummies of one factor.

    `t_df`: use t(t_df) instead of normal critical values and p-values (clustered fits with few clusters).
    `events`: {level: number of events}; a level with none gets no odds ratio, interval or p-value, and the note
    'no events', instead of an odds ratio near zero with a p-value near 1e-200."""
    from scipy import stats

    params, se = result.params, result.bse
    rows = []
    for name in params.index:
        if not name.startswith(prefix + "="):
            continue
        level = name.split("=", 1)[1]
        b, s = float(params[name]), float(se[name])
        if t_df:
            q, p = float(stats.t.ppf(0.975, t_df)), float(2 * stats.t.sf(abs(b / s), t_df)) if s > 0 else float("nan")
        else:
            q, p = 1.959963984540054, float(result.pvalues[name])
        row = {"level": level, "odds_ratio": float(np.exp(b)), "lo95": float(np.exp(b - q * s)),
               "hi95": float(np.exp(b + q * s)), "p": p, "note": ""}
        if events is not None and events.get(level, 0) == 0:
            row.update(odds_ratio=np.nan, lo95=np.nan, hi95=np.nan, p=np.nan, note="no events")
        rows.append(row)
    return pd.DataFrame(rows, columns=["level", "odds_ratio", "lo95", "hi95", "p", "note"])


def deal_spread_intervals(cells_df: pd.DataFrame, factors: list[str], baseline: dict, events=("chargeoff", "prepay"),
                          lender: str = "lender", deal: str = "deal") -> tuple[pd.DataFrame, dict]:
    """Lender odds ratios with intervals that include the deal-to-deal spread (REVIEW.md R1-6).

    A lender's coefficient carries the luck of its particular deals. With one deal per lender that luck cannot be
    seen in the lender's own data, so it is measured where it can be: among the lenders that own two or more deals.

    1. Refit the same specification with a dummy per deal in place of the lender dummies, model-based covariance
       with a Pearson (quasi-binomial) scale. Each deal effect is then its lender's effect plus that deal's shock.
    2. Between-deal variance of the shock: the spread of the deal effects inside each multi-deal lender, minus the
       part sampling noise explains, pooled over lenders (method of moments, truncated at zero); its degrees of
       freedom are the number of deals beyond the first in each such lender.
    3. For each lender's coefficient in the lender-dummy fit (the published point estimate), the variance is its
       model-based variance plus the shock variance times the sum of squared deal weights on both sides of the
       comparison (one deal: weight one; several: each deal's share of the lender's events, which is how the
       lender-dummy fit pools them). Intervals and p-values use t with Satterthwaite degrees of freedom.

    This assumes deal shocks are alike across lenders, which is what makes a single-deal lender's interval honest
    at all; it is stated on the page. Returns (table, info).
    """
    import statsmodels.api as sm
    from scipy import stats

    base_lender = str(baseline[lender])
    lender_of = cells_df.groupby(deal)[lender].agg(lambda s: str(s.iloc[0])).to_dict()
    deals_of: dict[str, list[str]] = {}
    for d, l in sorted(lender_of.items()):
        deals_of.setdefault(l, []).append(d)
    expo = cells_df.groupby(deal)["exposure"].sum()
    base_deal = max(deals_of[base_lender], key=lambda d: float(expo.get(d, 0)))
    f_deal = [deal if f == lender else f for f in factors]
    Xd = sm.add_constant(_dummies(cells_df, f_deal, {**baseline, deal: base_deal}), has_constant="add")
    Xl = sm.add_constant(_dummies(cells_df, factors, baseline), has_constant="add")
    n = cells_df["exposure"].to_numpy(dtype=float)
    rows, info = [], {"baseline_lender": base_lender, "baseline_deal": base_deal, "deals": deals_of}
    for ev in events:
        y = cells_df[f"d_{ev}"].to_numpy(dtype=float)
        endog = np.column_stack([y, n - y])
        rd = sm.GLM(endog, Xd, family=sm.families.Binomial()).fit(scale="X2")
        rl = sm.GLM(endog, Xl, family=sm.families.Binomial()).fit(scale="X2")
        names = list(Xd.columns)
        col = {d: names.index(f"{deal}={d}") if f"{deal}={d}" in names else None for d in lender_of}
        V = rd.cov_params().to_numpy()

        def vec(weights: dict) -> np.ndarray:
            a = np.zeros(len(names))
            for d, w in weights.items():
                if col[d] is not None:
                    a[col[d]] += w
            return a

        ss, dof, contrasts = 0.0, 0, {}
        for l, ds in deals_of.items():
            if len(ds) < 2:
                continue
            eff = np.array([rd.params.iloc[col[d]] if col[d] is not None else 0.0 for d in ds])
            centred = eff - eff.mean()
            sampling = 0.0
            for i, _ in enumerate(ds):
                w = {d2: (1.0 if j == i else 0.0) - 1.0 / len(ds) for j, d2 in enumerate(ds)}
                a = vec(w)
                sampling += float(a @ V @ a)
            ss += float((centred ** 2).sum()) - sampling
            dof += len(ds) - 1
            contrasts[l] = [float(x) for x in eff]
        sigma2 = max(ss / dof, 0.0) if dof else float("nan")
        info[ev] = {"deal_shock_sd": float(np.sqrt(sigma2)) if sigma2 == sigma2 else None, "df": dof,
                    "deal_effects_within_lender": contrasts, "pearson_scale": float(rd.scale)}
        dev = cells_df.groupby(deal)[f"d_{ev}"].sum()

        def wsq(l: str) -> float:
            ds = deals_of[l]
            tot = float(sum(dev.get(d, 0) for d in ds))
            if len(ds) == 1 or tot <= 0:
                return 1.0 / len(ds) if tot <= 0 else 1.0
            return float(sum((dev.get(d, 0) / tot) ** 2 for d in ds))

        for l, ds in sorted(deals_of.items()):
            if l == base_lender or f"{lender}={l}" not in rl.params.index:
                continue
            b = float(rl.params[f"{lender}={l}"])
            v_model = float(rl.bse[f"{lender}={l}"]) ** 2
            v_deal = sigma2 * (wsq(l) + wsq(base_lender)) if sigma2 == sigma2 else float("nan")
            se = float(np.sqrt(v_model + v_deal))
            t_df = (dof * (1 + v_model / v_deal) ** 2) if v_deal and v_deal > 0 else float("inf")
            q = float(stats.t.ppf(0.975, t_df)) if np.isfinite(t_df) else 1.959963984540054
            p = float(2 * (stats.t.sf(abs(b / se), t_df) if np.isfinite(t_df) else stats.norm.sf(abs(b / se))))
            rows.append({"event": ev, "lender": l, "n_deals": len(ds), "odds_ratio": float(np.exp(b)),
                         "se_model": float(np.sqrt(v_model)), "deal_shock_sd": float(np.sqrt(sigma2)),
                         "weight_sq": wsq(l) + wsq(base_lender), "se": se, "t_df": t_df,
                         "lo95": float(np.exp(b - q * se)), "hi95": float(np.exp(b + q * se)), "p": p})
    return pd.DataFrame(rows), info


def _dummies(df: pd.DataFrame, factors: list[str], baseline: dict) -> pd.DataFrame:
    cols = {}
    for f in factors:
        levels = sorted(df[f].astype(str).unique())
        base = baseline.get(f, levels[0])
        if base not in levels:
            base = levels[0]
        for lv in levels:
            if lv == base:
                continue
            cols[f"{f}={lv}"] = (df[f].astype(str) == lv).astype(float).to_numpy()
    return pd.DataFrame(cols, index=df.index)
