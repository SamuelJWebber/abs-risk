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


def _month_index(s: pd.Series) -> pd.Series:
    d = pd.to_datetime(s)
    return (d.dt.year * 12 + d.dt.month).astype("Int64")


def ages(loans: pd.DataFrame) -> pd.DataFrame:
    """The survival clock: age in months since origination, with delayed entry.

    entry_age  age at which the loan comes under observation (the deal's pool cutoff month, or the loan's own
               first month when it was added later). Loans in ABS pools are seasoned at entry, so risk sets must
               only count a loan at ages it was actually observed (left truncation).
    exit_age   age at the exit event (zb_date when the sponsor gives it, else the first period with a code), or
               at the last observed period for censored loans.
    event      'chargeoff', 'prepay' (all competing exits pooled), or 'censored'.

    Pool cutoff: the first file of a deal often carries exits dated the month before its period end (the loan
    left between the cutoff and the first report). Per deal, if any exit in the first file is dated before that
    period, every loan present in the first file is taken to have entered one month earlier.
    Falls back to entry_age 0 and exit_age = months_observed when the date columns are absent (synthetic tests).
    """
    if "first_period" not in loans or "orig_month" not in loans:
        exit_age = loans["months_observed"].to_numpy().astype(int)
        return pd.DataFrame({"entry_age": np.zeros(len(loans), dtype=int), "exit_age": exit_age,
                             "event": _event(loans)}, index=loans.index)
    fp = _month_index(loans["first_period"])
    om = _month_index(loans["orig_month"])
    lp = _month_index(loans["last_period"]) if "last_period" in loans else fp + loans["months_observed"].astype("Int64") - 1
    ev = pd.Series(_event(loans), index=loans.index)
    ex_month = pd.Series(pd.NA, index=loans.index, dtype="Int64")
    if "exit_period" in loans:
        ex_month = _month_index(loans["exit_period"])
    if "zb_date" in loans:
        zb = _month_index(loans["zb_date"])
        ex_month = zb.where(zb.notna(), ex_month)
    ex_month = ex_month.fillna(fp + loans["months_observed"].astype("Int64") - 1)   # no exit date: last month seen
    ex_month = ex_month.where(ev != "censored", lp)
    # pool cutoff lag per deal: one month when the first file already carries exits dated before its period
    lag = pd.Series(0, index=loans.index, dtype="Int64")
    if "deal" in loans:
        for deal, g in loans.groupby("deal"):
            first = g["first_period"].min()
            in_first = g["first_period"] == first
            exits_before = (ex_month[g.index] < fp[g.index]) & in_first & (ev[g.index] != "censored")
            if exits_before.any():
                lag[g.index[in_first]] = 1
    entry_month = fp - lag
    entry_age = (entry_month - om).clip(lower=0)
    exit_age = entry_age + (ex_month - entry_month).clip(lower=0)
    return pd.DataFrame({"entry_age": entry_age.fillna(0).astype(int), "exit_age": exit_age.fillna(entry_age.fillna(0)).astype(int),
                         "event": ev}, index=loans.index)


def _event(loans: pd.DataFrame) -> np.ndarray:
    et = loans["exit_type"].astype(str).to_numpy()
    return np.where(et == "chargeoff", "chargeoff", np.where(np.isin(et, list(COMPETING)), "prepay", "censored"))


def _life_table(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Per age t (months since origination): at risk during t, charge-offs at t, competing exits at t.

    A loan is at risk at age t when entry_age <= t <= exit_age; its event, if any, happens at exit_age.
    """
    ages_ = np.arange(0, horizon + 1)
    a = ages(df)
    entry = a["entry_age"].to_numpy()
    exit_ = a["exit_age"].to_numpy()
    ev = a["event"].to_numpy()
    is_co = ev == "chargeoff"
    is_comp = ev == "prepay"
    at_risk = np.array([((entry <= t) & (exit_ >= t)).sum() for t in ages_])
    d_co = np.array([((exit_ == t) & is_co).sum() for t in ages_])
    d_comp = np.array([((exit_ == t) & is_comp).sum() for t in ages_])
    return pd.DataFrame({"age": ages_, "at_risk": at_risk, "d_chargeoff": d_co, "d_competing": d_comp})


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
        lt["entry_age_median"] = float(ages(g)["entry_age"].median())
        for k, v in zip(by, keys):
            lt[k] = v
        out.append(lt)
    cols = by + ["age", "at_risk", "d_chargeoff", "d_competing", "aj_chargeoff", "km_chargeoff", "n_loans", "entry_age_median"]
    return pd.concat(out, ignore_index=True)[cols] if out else pd.DataFrame(columns=cols)


def incidence_at(cif: pd.DataFrame, by: list[str], age: int) -> pd.DataFrame:
    """Pick one horizon (e.g. 12 or 24 months) from the long table."""
    return cif[cif["age"] == age].drop(columns=["age"]).reset_index(drop=True)
