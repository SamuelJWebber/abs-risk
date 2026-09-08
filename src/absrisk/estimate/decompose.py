"""Split a lender's charge-off advantage into entry and roll (design/methods.md §7).

The question this exists for: when Toyota loses less than Santander at the same bureau score, is it because
Toyota's borrowers are less likely to get into trouble at all (selection), or because a borrower in trouble at
Toyota is less likely to be charged off (prioritisation, or collections, or the collateral)?

Two stages, each a competing-risks problem on the same loans:

  entry   time from origination to the first month 30+ days past due.
          Competing exit: leaving the pool (payoff, repurchase) while current.
  roll    for loans that reach 30+, time from that month to charge-off.
          Competing exit: curing and then leaving, or still alive at the end of observation.

A lender whose whole advantage is in `entry` is selecting better borrowers on the dimension that matters.
A lender whose advantage persists in `roll` is holding an account its borrowers protect, or is collecting
harder, or is holding collateral the borrower needs. This distinguishes selection from the rest; it does not
separate prioritisation from collections, and nothing here observes one person across two lenders.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .survival import _counts, _curves, _month_index, ages, score_bucket


def stage_frames(loans: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Two frames with (entry_age, exit_age, event) columns: one for entry to 30+, one for the roll to charge-off."""
    a = ages(loans)
    om = _month_index(loans["orig_month"])
    d30 = _month_index(loans["first_30_period"]) if "first_30_period" in loans else pd.Series(pd.NA, index=loans.index, dtype="Int64")
    age30 = (d30 - om).astype("Float64")

    # --- stage 1: origination -> first 30+ ---
    hit = age30.notna() & (age30 >= a["entry_age"])
    e1 = pd.DataFrame({
        "entry_age": a["entry_age"],
        "exit_age": np.where(hit, age30.fillna(0).astype(float), a["exit_age"]),
        "event": np.where(hit, "chargeoff",                       # reuse the label: "the event" is reaching 30+
                          np.where(a["event"] == "censored", "censored", "prepay")),
    }, index=loans.index)
    e1["exit_age"] = e1[["entry_age", "exit_age"]].max(axis=1).astype(int)

    # --- stage 2: first 30+ -> charge-off, only for loans that reached 30+ ---
    idx = loans.index[hit]
    ever = loans.loc[idx]
    a2 = a.loc[idx]
    start = age30.loc[idx].astype(float)
    is_co = (ever["exit_type"] == "chargeoff").to_numpy()
    end = np.where(is_co, a2["exit_age"].to_numpy(), a2["exit_age"].to_numpy())
    e2 = pd.DataFrame({
        "entry_age": np.zeros(len(idx), dtype=int),                # clock restarts at the month of first 30+
        "exit_age": np.maximum(end - start.to_numpy(), 0).astype(int),
        "event": np.where(is_co, "chargeoff", np.where(a2["event"].to_numpy() == "censored", "censored", "prepay")),
    }, index=idx)
    return e1, e2


def _cif(frame: pd.DataFrame, horizon: int) -> np.ndarray:
    at_risk, d_ev, d_comp = _counts(frame["entry_age"].to_numpy(), frame["exit_age"].to_numpy(),
                                    frame["event"].to_numpy(), horizon)
    return _curves(at_risk, d_ev, d_comp)[0]


def decompose(loans: pd.DataFrame, by: list[str], entry_horizon: int = 24, roll_horizon: int = 12,
              min_loans: int = 1500, min_ever30: int = 100) -> pd.DataFrame:
    """Per group: P(reach 30+ by entry_horizon), P(charge off within roll_horizon of first 30+), and their product.

    The product is a decomposition of the charge-off rate into a rate of getting into trouble and a rate of
    trouble becoming a loss. Groups too small at either stage are returned with nulls rather than dropped, so
    the reader sees why a cell is missing.
    """
    e1_all, e2_all = stage_frames(loans)
    rows = []
    for keys, g in loans.groupby(by, dropna=False, observed=True):
        keys = keys if isinstance(keys, tuple) else (keys,)
        e1 = e1_all.loc[g.index]
        e2 = e2_all.loc[e2_all.index.intersection(g.index)]
        rec = dict(zip(by, keys))
        rec["n_loans"] = len(g)
        rec["n_ever30"] = len(e2)
        rec["entry_rate"] = float(_cif(e1, entry_horizon)[-1]) if len(g) >= min_loans else np.nan
        rec["roll_rate"] = float(_cif(e2, roll_horizon)[-1]) if len(e2) >= min_ever30 else np.nan
        rec["implied"] = rec["entry_rate"] * rec["roll_rate"] if rec["entry_rate"] == rec["entry_rate"] and rec["roll_rate"] == rec["roll_rate"] else np.nan
        rows.append(rec)
    return pd.DataFrame(rows)


def attribute(dec: pd.DataFrame, group: str, baseline: str) -> pd.DataFrame:
    """How much of each group's log gap against `baseline` comes from entry and how much from roll.

    log(implied_g / implied_b) = log(entry_g / entry_b) + log(roll_g / roll_b)
    The two shares sum to 1 whenever the total gap is not zero. A share near 1 for entry means selection;
    a large roll share means the advantage is in what happens after trouble starts.
    """
    d = dec.dropna(subset=["implied"]).set_index(group)
    if baseline not in d.index:
        return pd.DataFrame()
    b = d.loc[baseline]
    out = []
    for name, r in d.iterrows():
        le, lr = np.log(r["entry_rate"] / b["entry_rate"]), np.log(r["roll_rate"] / b["roll_rate"])
        tot = le + lr
        out.append({group: name, "entry_rate": r["entry_rate"], "roll_rate": r["roll_rate"], "implied": r["implied"],
                    "entry_ratio": r["entry_rate"] / b["entry_rate"], "roll_ratio": r["roll_rate"] / b["roll_rate"],
                    "total_ratio": r["implied"] / b["implied"],
                    "entry_share_of_gap": le / tot if abs(tot) > 1e-9 else np.nan,
                    "roll_share_of_gap": lr / tot if abs(tot) > 1e-9 else np.nan,
                    "n_loans": r["n_loans"], "n_ever30": r["n_ever30"]})
    return pd.DataFrame(out).sort_values("total_ratio")


def by_score_and_group(loans: pd.DataFrame, group: str = "lender", **kw) -> pd.DataFrame:
    """The decomposition inside 20-point score buckets, so the comparison is at the same score."""
    df = loans.copy()
    df["score_b"] = score_bucket(df["score"])
    return decompose(df, by=[group, "score_b"], **kw)
