"""Where a card trust's low loss rate comes from: entry, progression, or conversion (design/methods.md §7).

The monthly charge-off rate factors exactly, with no modelling at all, into three ratios:

    monthly charge-off rate
        =  (30+ share)                      entry:        how much of the book is in trouble
        x  (90+ share / 30+ share)          progression:  how much of that trouble deepens
        x  (monthly charge-off / 90+ share) conversion:   how much deep trouble becomes a loss

Each factor is a share of receivables from the trust's own monthly report, so the identity holds by
construction and the only judgement is how to read it.

- A trust whose low loss rate is all **entry** has accounts that rarely go delinquent. That is selection: it
  lent to people who do not miss payments, or it lent them amounts they can carry.
- A trust with a low **conversion** rate has accounts that go 90 days late and still do not charge off. That is
  the observable signature of borrowers curing deep delinquency, which is what "people pay this card first"
  would look like at the trust level. It is equally the signature of harder collections, more generous
  re-aging, or a different charge-off policy.

Neither reading is a within-person comparison, so this cannot measure how one borrower ranks two cards. It can
say whether an issuer's advantage lives before trouble or after it, which the loss rate alone cannot.

Caveats carried in the output: these are stocks, not flows, so the ratios are steady-state approximations;
delinquency bucket edges differ by trust (only 30+ and 90+ are comparable); annualisation conventions differ, so
the monthly rate divides the reported annual rate by the trust's own convention.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

ANNUALISATION = {"x12": 12.0, "x365_over_days": 365.0 / 30.4, "actual_365": 365.0 / 30.4}


def monthly_rate(row: pd.Series) -> float:
    """The reported annualised charge-off rate expressed per month, using the trust's own convention."""
    f = ANNUALISATION.get(str(row.get("co_annualisation", "x12")), 12.0)
    return float(row["gross_co_rate"]) / f


def stages(monthly: pd.DataFrame, rate_col: str = "gross_co_rate") -> pd.DataFrame:
    """Per trust-month: entry, progression, conversion, and the identity check."""
    d = monthly.dropna(subset=[rate_col, "delinq_30plus_share", "delinq_90plus_share"]).copy()
    d["period_end"] = pd.to_datetime(d["period_end"])
    d["co_monthly"] = d.apply(monthly_rate, axis=1)
    d["entry"] = d["delinq_30plus_share"]
    d["progression"] = d["delinq_90plus_share"] / d["delinq_30plus_share"].replace(0, np.nan)
    d["conversion"] = d["co_monthly"] / d["delinq_90plus_share"].replace(0, np.nan)
    d["identity"] = d["entry"] * d["progression"] * d["conversion"]
    d["identity_error"] = (d["identity"] - d["co_monthly"]).abs()
    return d[["trust", "period_end", "co_monthly", "entry", "progression", "conversion", "identity",
              "identity_error", "delinq_30plus_share", "delinq_90plus_share", rate_col]]


def by_trust(st: pd.DataFrame, since: str | None = None) -> pd.DataFrame:
    """Trust averages of each stage, plus the ratio against the trust with the highest loss rate."""
    d = st if since is None else st[st["period_end"] >= pd.Timestamp(since)]
    g = d.groupby("trust").agg(months=("period_end", "size"), first=("period_end", "min"), last=("period_end", "max"),
                               co_monthly=("co_monthly", "mean"), entry=("entry", "mean"),
                               progression=("progression", "mean"), conversion=("conversion", "mean")).reset_index()
    base = g.loc[g["co_monthly"].idxmax(), "trust"]
    b = g.set_index("trust").loc[base]
    for c in ("co_monthly", "entry", "progression", "conversion"):
        g[f"{c}_ratio"] = g[c] / b[c]
    with np.errstate(divide="ignore", invalid="ignore"):
        tot = np.log(g["co_monthly_ratio"])
        g["entry_share_of_gap"] = np.where(np.abs(tot) > 1e-9, np.log(g["entry_ratio"]) / tot, np.nan)
        g["progression_share_of_gap"] = np.where(np.abs(tot) > 1e-9, np.log(g["progression_ratio"]) / tot, np.nan)
        g["conversion_share_of_gap"] = np.where(np.abs(tot) > 1e-9, np.log(g["conversion_ratio"]) / tot, np.nan)
    g.attrs["baseline"] = base
    return g.sort_values("co_monthly")


def stress_test(st: pd.DataFrame, periods: dict[str, tuple[str, str]]) -> pd.DataFrame:
    """Each stage per trust in named periods, to see whether the gaps widen when households are squeezed.

    If borrowers rank their debts, a favoured card's conversion advantage should widen in a squeeze and narrow
    when households are flush. Fixed selection predicts a flat ratio across periods.
    """
    rows = []
    for name, (a, b) in periods.items():
        w = st[(st["period_end"] >= pd.Timestamp(a)) & (st["period_end"] <= pd.Timestamp(b))]
        if w.empty:
            continue
        g = w.groupby("trust").agg(months=("period_end", "size"), entry=("entry", "mean"),
                                   progression=("progression", "mean"), conversion=("conversion", "mean"),
                                   co_monthly=("co_monthly", "mean")).reset_index()
        base = g.loc[g["co_monthly"].idxmax(), "trust"]
        b_ = g.set_index("trust").loc[base]
        for c in ("entry", "progression", "conversion", "co_monthly"):
            g[f"{c}_ratio"] = g[c] / b_[c]
        g.insert(0, "period", name)
        g["baseline"] = base
        rows.append(g)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
