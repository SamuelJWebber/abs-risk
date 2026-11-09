"""Track A panel regression (analysis-plan §4).

panel_regression      trust-month regression of the gross charge-off rate on tier shares with month fixed
                      effects, with and without trust fixed effects, Driscoll-Kraay standard errors.
identification        what those two specifications can identify from the tier shares they are given.

The shape-times-level residual lives in run_cards.py (`mix_by_trust`, `predicted`), which reads the bucket-to-tier
mapping from crosswalks/fico_buckets.csv. An older crosswalk path here (tier_mix_by_trust, predict_by_trust) was
never called by the analysis and was removed on 2026-11-09 (REVIEW.md R1-1).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TIERS = ["deep_subprime", "subprime", "near_prime", "prime", "prime_plus", "superprime"]


def panel_regression(monthly: pd.DataFrame, mix_monthly: pd.DataFrame, rate_col: str = "gross_co_rate", maxlags: int = 6):
    """OLS of the charge-off rate on tier shares (superprime omitted) with month FE, then also trust FE.

    Driscoll-Kraay standard errors (statsmodels 'hac-groupsum' over time). Returns both fits and a tidy table.
    mix_monthly: trust, period_end, tier columns (already interpolated to months).
    """
    import statsmodels.api as sm

    df = monthly.merge(mix_monthly, on=["trust", "period_end"], how="inner").dropna(subset=[rate_col])
    df["period_end"] = pd.to_datetime(df["period_end"])
    df = df.sort_values(["period_end", "trust"]).reset_index(drop=True)
    y = df[rate_col].to_numpy(dtype=float)
    X0 = df[[t for t in TIERS if t != "superprime"]].astype(float)
    month_d = pd.get_dummies(df["period_end"].dt.strftime("%Y-%m"), prefix="m", drop_first=True, dtype=float)
    trust_d = pd.get_dummies(df["trust"], prefix="trust", drop_first=True, dtype=float)
    time_idx = df["period_end"].rank(method="dense").astype(int).to_numpy() - 1
    diag = identification(df, list(X0.columns))
    fits = {}
    for name, X in (("month_fe", pd.concat([X0, month_d], axis=1)), ("month_and_trust_fe", pd.concat([X0, month_d, trust_d], axis=1))):
        X = sm.add_constant(X, has_constant="add")
        fits[name] = sm.OLS(y, X).fit(cov_type="hac-groupsum", cov_kwds={"time": time_idx, "maxlags": maxlags})
    rows = []
    for name, r in fits.items():
        status, note = diag[name]
        hide = status == "not identified"          # the solver still returns numbers; they mean nothing
        for c in [t for t in TIERS[:-1]] + [c for c in r.params.index if c.startswith("trust_")]:
            rows.append({"spec": name, "term": c, "coef": np.nan if hide else float(r.params[c]),
                         "se": np.nan if hide else float(r.bse[c]), "p": np.nan if hide else float(r.pvalues[c]),
                         "status": status, "note": note})
    return fits, pd.DataFrame(rows)


def identification(df: pd.DataFrame, tier_cols: list[str]) -> dict[str, tuple[str, str]]:
    """What the two panel specifications can identify, given how the tier shares vary.

    The tier shares come from prospectus snapshots, so they vary across trusts and, only when a trust has more than one
    snapshot in the data, within a trust. With month FE, the tier coefficients are identified off the distinct
    trust-level mixes: with no more distinct mixes than tier parameters plus one, the model reproduces each trust's
    mean exactly and the "gradient" is a re-expression of the trust means, not an estimate of anything (saturated).
    With trust FE added, only within-trust movement in the mix identifies them; none means not identified at all.
    Returns {spec: (status, note)} with status in {"identified", "saturated", "not identified"}.
    """
    n_trusts = df["trust"].nunique()
    k = len(tier_cols)
    n_mix = len(df[tier_cols].round(12).drop_duplicates())
    within = int((df.groupby("trust")[tier_cols].nunique() > 1).any(axis=1).sum())
    out = {}
    if n_mix <= k + 1:
        out["month_fe"] = ("saturated", f"{n_mix} distinct tier mixes across {n_trusts} trusts for {k} tier coefficients "
                                        f"plus an intercept: the fit reproduces each trust's mean exactly, so the coefficients "
                                        f"re-express the trust means and are not a mix gradient")
    else:
        out["month_fe"] = ("identified", f"{n_mix} distinct tier mixes for {k} tier coefficients plus an intercept")
    if within == 0:
        out["month_and_trust_fe"] = ("not identified", f"no trust's mix changes over the sample (one prospectus snapshot "
                                                       f"each), so the tier shares are collinear with the trust effects")
    elif n_mix - n_trusts < k:
        out["month_and_trust_fe"] = ("not identified", f"{within} trust(s) change mix within the sample, giving "
                                                       f"{n_mix - n_trusts} within-trust mix steps for {k} tier coefficients")
    else:
        out["month_and_trust_fe"] = ("identified", f"{n_mix - n_trusts} within-trust mix steps for {k} tier coefficients")
    return out
