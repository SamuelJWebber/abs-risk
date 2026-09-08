"""Cumulative incidence of charge-off by months since origination, with prepayment as a competing risk.

Input: the `loans` table (analysis-plan §1a). Each loan contributes ages 1..months_observed, counted from
first_period (the first month the loan is seen in the trust, which is close to but not always the origination
month; the plan's B1 uses age since first observation and says so).

Two estimators per group:
  aj_chargeoff  Aalen-Johansen cumulative incidence: charge-off competes with prepay/repurchase/other/absent.
  km_chargeoff  Kaplan-Meier 1 - S(t) treating every other exit as censoring. Always >= aj. The gap is the
                prepayment effect; both are reported (plan B1).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

COMPETING = {"prepay", "repurchase", "other", "absent"}


def score_bucket(score: pd.Series, width: int = 20) -> pd.Series:
    """20-point buckets labelled by their lower edge; missing scores get 'none'."""
    lo = (score // width * width).astype("Int64")
    return lo.astype("string").fillna("none")


def _life_table(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Per age t: at risk at start of t, charge-offs at t, competing exits at t."""
    ages = np.arange(1, horizon + 1)
    exit_age = df["months_observed"].to_numpy()
    is_co = (df["exit_type"] == "chargeoff").to_numpy()
    is_comp = df["exit_type"].isin(COMPETING).to_numpy()
    # censored loans (exit_type == 'censored') leave the risk set after their last age without an event
    at_risk = np.array([(exit_age >= t).sum() for t in ages])
    d_co = np.array([((exit_age == t) & is_co).sum() for t in ages])
    d_comp = np.array([((exit_age == t) & is_comp).sum() for t in ages])
    return pd.DataFrame({"age": ages, "at_risk": at_risk, "d_chargeoff": d_co, "d_competing": d_comp})


def cumulative_incidence(loans: pd.DataFrame, by: list[str], horizon: int = 36) -> pd.DataFrame:
    """Long table: group columns, age, at_risk, d_chargeoff, d_competing, aj_chargeoff, km_chargeoff, n_loans."""
    out = []
    for keys, g in loans.groupby(by, dropna=False, observed=True):
        keys = keys if isinstance(keys, tuple) else (keys,)
        lt = _life_table(g, horizon)
        n = lt["at_risk"].to_numpy().astype(float)
        with np.errstate(divide="ignore", invalid="ignore"):
            h_co = np.where(n > 0, lt["d_chargeoff"] / n, 0.0)
            h_all = np.where(n > 0, (lt["d_chargeoff"] + lt["d_competing"]) / n, 0.0)
        s_all = np.cumprod(1 - h_all)                      # overall survival (no exit of any kind)
        s_prev = np.concatenate([[1.0], s_all[:-1]])
        aj = np.cumsum(s_prev * h_co)                       # Aalen-Johansen CIF for charge-off
        km = 1 - np.cumprod(1 - h_co)                       # KM treating competing exits as censoring
        lt["aj_chargeoff"] = aj
        lt["km_chargeoff"] = km
        lt["n_loans"] = len(g)
        for k, v in zip(by, keys):
            lt[k] = v
        out.append(lt)
    cols = by + ["age", "at_risk", "d_chargeoff", "d_competing", "aj_chargeoff", "km_chargeoff", "n_loans"]
    return pd.concat(out, ignore_index=True)[cols] if out else pd.DataFrame(columns=cols)


def incidence_at(cif: pd.DataFrame, by: list[str], age: int) -> pd.DataFrame:
    """Pick one horizon (e.g. 12 or 24 months) from the long table."""
    return cif[cif["age"] == age].drop(columns=["age"]).reset_index(drop=True)
