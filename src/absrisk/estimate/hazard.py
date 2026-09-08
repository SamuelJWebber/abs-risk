"""Discrete-time competing-risks hazard (analysis-plan §2, B2).

Each loan contributes one row per month of age (1..months_observed). In its last month it has an event:
charge-off, prepay (prepay + repurchase + other + absent), or none (censored). The month-by-month event is
modelled with two binomial logits on aggregated cells, which is the standard discrete-time competing-risks
approximation and scales to tens of millions of loan-months:

    P(chargeoff at t | at risk at t) = logit^-1(age dummies + score buckets + lender + cohort + controls)
    P(prepay    at t | at risk at t) = same form

Continuous controls are binned into quantile groups so rows aggregate; standard errors are clustered by deal.
The lender coefficients at fixed score bucket are the "same score, different lender" answer; the loan-size and
payment-burden bins at fixed score and lender are the "how much does size matter" answer.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .survival import ages, score_bucket

AGE_BINS = [-1, 3, 6, 9, 12, 18, 24, 36, 48, 60, 10**6]
AGE_LABELS = ["0-3", "4-6", "7-9", "10-12", "13-18", "19-24", "25-36", "37-48", "49-60", "61+"]


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
    last = age == np.repeat(exit_, m)
    ev_rep = ev[idx]
    base["ev_chargeoff"] = (last & (ev_rep == "chargeoff")).astype(int)
    base["ev_prepay"] = (last & (ev_rep == "prepay")).astype(int)
    return base


def add_design_columns(loans: pd.DataFrame, control_bins: int = 5) -> pd.DataFrame:
    """Categorical versions of the covariates the hazard model uses."""
    df = loans.copy()
    df["score_b"] = score_bucket(df["score"])
    df["cohort_q"] = pd.to_datetime(df["orig_month"]).dt.to_period("Q").astype(str)
    for col, name in (("orig_amount", "amount_q"), ("pti", "pti_q"), ("ltv", "ltv_q"), ("orig_apr", "apr_q")):
        if col in df:
            x = df[col].astype(float)
            try:
                df[name] = pd.qcut(x, control_bins, labels=False, duplicates="drop").astype("Int64").astype("string").fillna("none")
            except ValueError:
                df[name] = "none"
    return df


def aggregate_cells(loan_months: pd.DataFrame, cells: list[str]) -> pd.DataFrame:
    """Collapse loan-months to cells: exposures, charge-off events, prepay events."""
    lm = loan_months.copy()
    lm["age_b"] = pd.cut(lm["age"], AGE_BINS, labels=AGE_LABELS, right=True).astype(str)
    g = lm.groupby(cells + ["age_b"], dropna=False, observed=True)
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
    res["design_info"] = {"columns": list(X.columns), "n_cells": len(cells_df), "n_params": int(n_params),
                          "n_exposure": float(cells_df["exposure"].sum()),
                          "cov_type": "cluster by " + cluster if robust else "model-based (design too small for clustering)"}
    return res


def hazard_ratios(result, prefix: str) -> pd.DataFrame:
    """Odds ratios with 95% intervals for the dummies of one factor."""
    params = result.params
    ci = result.conf_int()
    rows = []
    for name in params.index:
        if name.startswith(prefix + "="):
            rows.append({"level": name.split("=", 1)[1], "odds_ratio": float(np.exp(params[name])),
                         "lo95": float(np.exp(ci.loc[name, 0])), "hi95": float(np.exp(ci.loc[name, 1])),
                         "p": float(result.pvalues[name])})
    return pd.DataFrame(rows)


def _dummies(df: pd.DataFrame, factors: list[str], baseline: dict) -> pd.DataFrame:
    cols = {}
    for f in factors:
        levels = sorted(df[f].astype(str).unique())
        base = baseline.get(f, levels[0])
        for lv in levels:
            if lv == base:
                continue
            cols[f"{f}={lv}"] = (df[f].astype(str) == lv).astype(float).to_numpy()
    return pd.DataFrame(cols, index=df.index)
