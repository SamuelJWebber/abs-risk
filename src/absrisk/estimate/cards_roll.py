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

Averages over months are geometric (the mean of the logs, exponentiated). The identity holds month by month, so it
then holds for the averages too: a trust's average entry x progression x conversion is its average charge-off rate
exactly, and the three shares of its log gap against the baseline sum to one. Arithmetic means of each factor do
not multiply back (they missed by up to 1.7%), which left the shares summing to 0.99-1.02 (REVIEW.md R1-5).

Caveats carried in the output: these are stocks, not flows, so the ratios are steady-state approximations;
delinquency bucket edges differ by trust (only 30+ and 90+ are comparable); annualisation conventions differ, so
the monthly rate divides the reported annual rate by the trust's own convention. Conversion divides a flow by a
stock that builds before the charge-offs it leads to, so it tends to fall while delinquency is rising and to rise
while it is falling, whatever borrowers do; that matters for any comparison across the cycle.
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


FACTORS = ("co_monthly", "entry", "progression", "conversion")


def _gmeans(d: pd.DataFrame, by: str = "trust") -> pd.DataFrame:
    """Geometric mean of each factor per group, over the months where all four are positive (so all four average the
    same months and the identity carries over)."""
    ok = d[list(FACTORS)].gt(0).all(axis=1)
    d = d[ok]
    logs = np.log(d[list(FACTORS)])
    g = logs.groupby(d[by]).mean().apply(np.exp)
    g.insert(0, "months", d.groupby(by).size())
    return g


def _ratios(g: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """Each factor over the highest-loss trust's, and each factor's share of the log gap (the shares sum to one)."""
    base = g["co_monthly"].idxmax()
    out = g.copy()
    for c in FACTORS:
        out[f"{c}_ratio"] = g[c] / g.loc[base, c]
    with np.errstate(divide="ignore", invalid="ignore"):
        tot = np.log(out["co_monthly_ratio"])
        for c in ("entry", "progression", "conversion"):
            out[f"{c}_share_of_gap"] = np.where(np.abs(tot) > 1e-9, np.log(out[f"{c}_ratio"]) / tot, np.nan)
    return out, base


def by_trust(st: pd.DataFrame, since: str | None = None) -> pd.DataFrame:
    """Per trust: geometric-mean entry, progression, conversion and charge-off over its months, the ratio of each to
    the trust with the highest loss rate, and each factor's share of the log gap (summing to one)."""
    d = st if since is None else st[st["period_end"] >= pd.Timestamp(since)]
    g = _gmeans(d)
    span = d.groupby("trust")["period_end"].agg(["min", "max"]).rename(columns={"min": "first", "max": "last"})
    g, base = _ratios(g)
    g = span.join(g).reset_index()
    g = g[["trust", "months", "first", "last", *FACTORS,
           *[c for c in g.columns if c.endswith(("_ratio", "_share_of_gap"))]]]
    g.attrs["baseline"] = base
    return g.sort_values("co_monthly")


def stress_test(st: pd.DataFrame, periods: dict[str, tuple[str, str]]) -> pd.DataFrame:
    """Each stage per trust in named periods (geometric means), with ratios against that period's highest-loss trust.

    The named periods are calendar labels. Whether delinquency was actually higher in one than another is in the
    `entry` column (each trust's 30+ share in the period), which a reader must check before calling one of them a
    squeeze; `regimes` splits months by delinquency itself.
    """
    rows = []
    for name, (a, b) in periods.items():
        w = st[(st["period_end"] >= pd.Timestamp(a)) & (st["period_end"] <= pd.Timestamp(b))]
        if w.empty:
            continue
        g, base = _ratios(_gmeans(w))
        g = g.reset_index()
        g.insert(0, "period", name)
        g["baseline"] = base
        rows.append(g)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def delinquency_index(st: pd.DataFrame) -> pd.Series:
    """Per month: the mean across trusts of each trust's 30+ share over its own average 30+ share. One is an ordinary
    month for these pools; 1.2 is a month with a fifth more balances 30 days late than usual. Dividing by each trust's
    own average keeps the high-delinquency trusts from setting the index alone."""
    rel = st["entry"] / st.groupby("trust")["entry"].transform("mean")
    month = pd.to_datetime(st["period_end"]).dt.to_period("M")       # Citi's months end on the 25th or 26th
    return rel.groupby(month).mean().sort_index()


def regimes(st: pd.DataFrame) -> pd.DataFrame:
    """The stages in tight against loose months, where tight means the delinquency index is above its median.

    This is the direction test defined by the data instead of by calendar labels (REVIEW.md R1-4): a card that
    borrowers pay first should see its conversion ratio fall in the tight months. Columns as `stress_test`, with
    `regime` in place of `period`, plus the regime's average delinquency index, the median that splits them, and
    the number of calendar month-ends in the regime.
    """
    idx = delinquency_index(st)
    med = float(idx.median())
    tight = set(idx.index[idx > med])
    in_tight = pd.to_datetime(st["period_end"]).dt.to_period("M").isin(tight).to_numpy()
    rows = []
    for name, mask in (("loose", ~in_tight), ("tight", in_tight)):
        w = st[mask]
        if w.empty:
            continue
        g, base = _ratios(_gmeans(w))
        g = g.reset_index()
        g.insert(0, "regime", name)
        g["baseline"] = base
        sel = idx.index.isin(tight) if name == "tight" else ~idx.index.isin(tight)
        g["index_mean"] = float(idx[sel].mean())
        g["index_median"] = med
        g["calendar_months"] = int(sel.sum())
        rows.append(g)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _classify(moves: pd.Series, tol: float) -> dict[str, list[str]]:
    return {"fell": sorted(moves[moves < -tol].index), "rose": sorted(moves[moves > tol].index),
            "flat": sorted(moves[moves.abs() <= tol].index)}


def direction_summary(stress: pd.DataFrame, regimes_df: pd.DataFrame, order: list[str], tol: float = 0.05) -> dict:
    """The facts the direction test rests on, computed once so both pages say the same thing.

    Prioritisation predicts that a card borrowers pay first sees its conversion ratio (against the highest-loss
    trust) fall when money is tight. Two versions of "tight":
      regime       months with the delinquency index above its median against months below it;
      tightenings  consecutive named periods across which every trust's 30+ share rose (a period label alone does
                   not make a squeeze: in this corpus the 'squeeze' has lower delinquency than 2019).
    A move smaller than `tol` in the ratio counts as flat. `verdict` is 'priority' when the non-baseline trusts'
    ratios all fell in the tight regime, 'against' when none fell and at least one rose, else 'mixed'.
    """
    out: dict = {"tol": tol, "regime": None, "tightenings": [], "endpoints": None, "verdict": "mixed"}
    if regimes_df is not None and not regimes_df.empty and {"loose", "tight"} <= set(regimes_df["regime"]):
        w = regimes_df.pivot_table(index="trust", columns="regime", values="conversion_ratio")
        base = str(regimes_df["baseline"].iloc[0])
        moves = (w["tight"] - w["loose"]).drop(index=base, errors="ignore").dropna()
        ix = regimes_df.drop_duplicates("regime").set_index("regime")
        out["regime"] = {"baseline": base, "moves": moves.to_dict(), "loose": w["loose"].to_dict(),
                         "tight": w["tight"].to_dict(), "index_loose": float(ix.loc["loose", "index_mean"]),
                         "index_tight": float(ix.loc["tight", "index_mean"]),
                         "months": int(ix.loc["tight", "calendar_months"] + ix.loc["loose", "calendar_months"]),
                         **_classify(moves, tol)}
        r = out["regime"]
        if moves.size and not r["rose"] and not r["flat"]:
            out["verdict"] = "priority"
        elif moves.size and not r["fell"] and r["rose"]:
            out["verdict"] = "against"
    if stress is not None and not stress.empty and len(order) >= 2:
        conv = stress.pivot_table(index="trust", columns="period", values="conversion_ratio").reindex(columns=order)
        ent = stress.pivot_table(index="trust", columns="period", values="entry").reindex(columns=order)
        for a, b in zip(order, order[1:]):
            up = (ent[b] / ent[a]).dropna()
            if up.empty or not (up > 1).all():
                continue
            mv = (conv[b] - conv[a]).dropna()
            mv = mv[mv.index != stress.loc[stress["period"] == b, "baseline"].iloc[0]]
            out["tightenings"].append({"from": a, "to": b, "rise_min": float(up.min()), "rise_max": float(up.max()),
                                       "moves": mv.to_dict(), **_classify(mv, tol)})
        first, last = order[0], order[-1]
        ratio = (ent[last] / ent[first]).dropna()
        out["endpoints"] = {"from": first, "to": last, "ratio_min": float(ratio.min()), "ratio_max": float(ratio.max()),
                            "tighter": bool((ratio > 1).all()), "looser": bool((ratio < 1).all())}
    return out
