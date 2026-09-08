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


def _counts(entry: np.ndarray, exit_: np.ndarray, ev: np.ndarray, horizon: int, w: np.ndarray | None = None):
    """Vectorised life table counts per age 0..horizon: at risk, charge-offs, competing exits. `w` = loan weights."""
    w = np.ones(len(entry)) if w is None else w
    H = horizon + 1
    e = np.clip(entry, 0, H)                       # entries at or beyond H never count
    x = np.clip(exit_, 0, H)
    entered = np.cumsum(np.bincount(e, weights=w, minlength=H + 1))[:H]          # entered by age t (entry <= t)
    exited_before = np.concatenate([[0.0], np.cumsum(np.bincount(x, weights=w, minlength=H + 1))[:H - 1]])  # exit < t
    at_risk = entered - exited_before
    d_co = np.bincount(x[ev == "chargeoff"], weights=w[ev == "chargeoff"], minlength=H + 1)[:H]
    d_comp = np.bincount(x[ev == "prepay"], weights=w[ev == "prepay"], minlength=H + 1)[:H]
    return at_risk, d_co, d_comp


def _curves(at_risk, d_co, d_comp):
    n = at_risk.astype(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        h_co = np.where(n > 0, d_co / n, 0.0)
        h_all = np.where(n > 0, (d_co + d_comp) / n, 0.0)
    s_all = np.cumprod(1 - h_all)                      # overall survival (no exit of any kind)
    s_prev = np.concatenate([[1.0], s_all[:-1]])
    aj = np.cumsum(s_prev * h_co)                       # Aalen-Johansen CIF for charge-off
    km = 1 - np.cumprod(1 - h_co)                       # KM treating competing exits as censoring
    return aj, km


def _life_table(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Per age t (months since origination): at risk during t, charge-offs at t, competing exits at t.

    A loan is at risk at age t when entry_age <= t <= exit_age; its event, if any, happens at exit_age.
    """
    a = ages(df)
    at_risk, d_co, d_comp = _counts(a["entry_age"].to_numpy(), a["exit_age"].to_numpy(), a["event"].to_numpy(), horizon)
    return pd.DataFrame({"age": np.arange(0, horizon + 1), "at_risk": at_risk.astype(int),
                         "d_chargeoff": d_co.astype(int), "d_competing": d_comp.astype(int)})


def cumulative_incidence(loans: pd.DataFrame, by: list[str], horizon: int = 36, n_boot: int = 0, seed: int = 0,
                         max_entry_age: int | None = None) -> pd.DataFrame:
    """Long table: group columns, age, at_risk, d_chargeoff, d_competing, aj_chargeoff, km_chargeoff, n_loans,
    entry_age_median, and with n_boot > 0 the percentile bootstrap band aj_lo95 / aj_hi95 (resampling loans).

    max_entry_age keeps only loans first observed at or before that age since origination (a fresh-entrant cut:
    seasoned entrants are survivors, and survivor selection can differ by lender)."""
    rng = np.random.default_rng(seed)
    out = []
    a_all = ages(loans)
    if max_entry_age is not None:
        keep = a_all["entry_age"] <= max_entry_age
        loans, a_all = loans[keep], a_all[keep]
    for keys, g in loans.groupby(by, dropna=False, observed=True):
        keys = keys if isinstance(keys, tuple) else (keys,)
        a = a_all.loc[g.index]
        entry, exit_, ev = a["entry_age"].to_numpy(), a["exit_age"].to_numpy(), a["event"].to_numpy()
        at_risk, d_co, d_comp = _counts(entry, exit_, ev, horizon)
        aj, km = _curves(at_risk, d_co, d_comp)
        lt = pd.DataFrame({"age": np.arange(0, horizon + 1), "at_risk": at_risk.astype(int),
                           "d_chargeoff": d_co.astype(int), "d_competing": d_comp.astype(int),
                           "aj_chargeoff": aj, "km_chargeoff": km})
        if n_boot > 0 and len(g) > 1:
            reps = np.empty((n_boot, horizon + 1))
            for b in range(n_boot):
                w = rng.multinomial(len(g), np.full(len(g), 1.0 / len(g))).astype(float)
                ar, dc, dp = _counts(entry, exit_, ev, horizon, w)
                reps[b] = _curves(ar, dc, dp)[0]
            lt["aj_lo95"] = np.percentile(reps, 2.5, axis=0)
            lt["aj_hi95"] = np.percentile(reps, 97.5, axis=0)
        else:
            lt["aj_lo95"] = np.nan
            lt["aj_hi95"] = np.nan
        lt["n_loans"] = len(g)
        lt["entry_age_median"] = float(np.median(entry)) if len(entry) else np.nan
        for k, v in zip(by, keys):
            lt[k] = v
        out.append(lt)
    cols = by + ["age", "at_risk", "d_chargeoff", "d_competing", "aj_chargeoff", "aj_lo95", "aj_hi95", "km_chargeoff",
                 "n_loans", "entry_age_median"]
    return pd.concat(out, ignore_index=True)[cols] if out else pd.DataFrame(columns=cols)


def incidence_at(cif: pd.DataFrame, by: list[str], age: int) -> pd.DataFrame:
    """Pick one horizon (e.g. 12 or 24 months) from the long table."""
    return cif[cif["age"] == age].drop(columns=["age"]).reset_index(drop=True)
