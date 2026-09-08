"""Track A estimators (analysis-plan §4).

predict_by_trust      shape-times-level predicted charge-off per trust-month, under each shape, and the residual.
panel_regression      trust-month regression of the gross charge-off rate on tier shares with month fixed
                      effects, with and without trust fixed effects, Driscoll-Kraay standard errors.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TIERS = ["deep_subprime", "subprime", "near_prime", "prime", "prime_plus", "superprime"]


def tier_mix_by_trust(composition: pd.DataFrame, crosswalk: pd.DataFrame) -> pd.DataFrame:
    """Tier shares per (trust, as_of) from the prospectus FICO table and the bucket crosswalk.

    crosswalk columns: trust, bucket_lo, bucket_hi, tier, weight (share of the bucket assigned to the tier).
    composition rows with table == 'fico' carry share_receivables (preferred) or share_accounts.
    """
    f = composition[composition["table"] == "fico"].copy()
    f["share"] = f["share_receivables"].fillna(f["share_accounts"])
    m = f.merge(crosswalk, on=["trust", "bucket_lo", "bucket_hi"], how="left", validate="m:m")
    if m["tier"].isna().any():
        missing = m[m["tier"].isna()][["trust", "bucket_lo", "bucket_hi"]].drop_duplicates()
        raise ValueError(f"buckets without a crosswalk row:\n{missing}")
    m["w"] = m["share"] * m["weight"]
    mix = m.pivot_table(index=["trust", "as_of", "score_type"], columns="tier", values="w", aggfunc="sum", fill_value=0.0)
    for t in TIERS:
        if t not in mix:
            mix[t] = 0.0
    mix = mix[TIERS]
    mix = mix.div(mix.sum(axis=1), axis=0)
    return mix.reset_index()


def predict_by_trust(monthly: pd.DataFrame, mix: pd.DataFrame, shapes: pd.DataFrame, level: pd.DataFrame,
                     rate_col: str = "gross_co_rate") -> pd.DataFrame:
    """For each trust-month and shape: predicted = level(year) * sum(mix * relative_loss), residual = actual - predicted.

    `level` must carry, per year and shape_source, the calibrated multiplier `level` (absrisk.shape does this).
    The mix used is the latest prospectus as-of on or before the month; months before the first as-of use it too
    (flagged `mix_extrapolated`).
    """
    m = monthly.copy()
    m["period_end"] = pd.to_datetime(m["period_end"])
    m["year"] = m["period_end"].dt.year
    out = []
    for trust, g in m.groupby("trust"):
        mx = mix[mix["trust"] == trust].sort_values("as_of")
        if mx.empty:
            continue
        mx["as_of"] = pd.to_datetime(mx["as_of"])
        g = g.sort_values("period_end")
        merged = pd.merge_asof(g, mx, left_on="period_end", right_on="as_of", direction="backward", by="trust")
        first = mx.iloc[0]
        extrap = merged["as_of"].isna()
        for t in TIERS:
            merged.loc[extrap, t] = first[t]
        merged["mix_extrapolated"] = extrap
        for src, sh in shapes.groupby("shape_source"):
            rl = sh.set_index("tier")["relative_loss"]
            if rl.isna().any():
                continue
            lv = level[level["shape_source"] == src].set_index("year")["level"]
            weighted = sum(merged[t] * float(rl[t]) for t in TIERS)
            pred = merged["year"].map(lv) * weighted
            out.append(pd.DataFrame({"trust": trust, "period_end": merged["period_end"], "shape_source": src,
                                     "actual": merged[rate_col].to_numpy(), "predicted": pred.to_numpy(),
                                     "residual": merged[rate_col].to_numpy() - pred.to_numpy(),
                                     "mix_extrapolated": merged["mix_extrapolated"].to_numpy()}))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


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
    fits = {}
    for name, X in (("month_fe", pd.concat([X0, month_d], axis=1)), ("month_and_trust_fe", pd.concat([X0, month_d, trust_d], axis=1))):
        X = sm.add_constant(X, has_constant="add")
        fits[name] = sm.OLS(y, X).fit(cov_type="hac-groupsum", cov_kwds={"time": time_idx, "maxlags": maxlags})
    rows = []
    for name, r in fits.items():
        for t in TIERS[:-1]:
            rows.append({"spec": name, "term": t, "coef": float(r.params[t]), "se": float(r.bse[t]), "p": float(r.pvalues[t])})
        for c in r.params.index:
            if c.startswith("trust_"):
                rows.append({"spec": name, "term": c, "coef": float(r.params[c]), "se": float(r.bse[c]), "p": float(r.pvalues[c])})
    return fits, pd.DataFrame(rows)
