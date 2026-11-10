"""docs/autos.html from data/results/autos/. Run: `uv run absrisk report autos`."""

from __future__ import annotations

import json
import sys
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd

from ..estimate import rd
from ..estimate.lender_gap import (MIN_AT_RISK, MIN_EVENTS, MIN_LOANS, bucket_ratios, pair_ratios,  # noqa: F401
                                   scale_900_lenders, usable_cells)
from ..estimate.survival import POOL_OFFSET
from .svg import forest_chart, line_chart, page, table

ORDINAL = {1: "second", 2: "third", 3: "fourth", 4: "fifth", 5: "sixth", 6: "seventh", 7: "eighth"}

SCOPE = ("These are loans inside public auto ABS trusts, not the lenders' whole books. A loan enters when the trust "
         "is formed or replenished and leaves when it pays off, is repurchased, or charges off; some sponsors drop "
         "paid-off loans from the file the month after payoff and others keep them, which the exit rule handles. "
         f"Age is months since origination, and a loan counts only from its {ORDINAL.get(POOL_OFFSET, 'first')} month in "
         "the trust: it had to be current to be sold in, so its first months there can hardly end in a charge-off. "
         "Scores are the score type the sponsor reports (FICO at most captives, a bureau score at Santander, VantageScore "
         "at Exeter for 98.9% of its pool) and are never refreshed after origination, so a 700 at Exeter and a 700 at "
         "Honda are close but not the same number.")

KIND = ("<b>What kind of claim each section makes.</b> Sections 2, 3 and 5 are descriptive: who defaults, at which "
        "lender, holding what fixed. Controls narrow a comparison, they do not make it causal, because a lender's "
        "borrowers differ in ways no field in the filing records. Section 4 is the only design here that could carry a "
        "causal sentence, and only at a cutoff that passes its screens.")


def _pool_window_note(hr: pd.DataFrame, summary: pd.DataFrame | None) -> str:
    """Why every b1 table counts a loan from its fourth month in the trust (REVIEW.md R2-1), from the hazard table's
    months-in-pool odds ratios and each deal's median age at entry."""
    p = hr[(hr["spec"] == "terms") & (hr["event"] == "chargeoff") & (hr["factor"] == "pool_b")].set_index("level")
    odds = ""
    if {"0-2", "3-5"} <= set(p.index):
        odds = (f": in the hazard model of section 3 the charge-off odds in a loan's first three months in the pool are "
                f"{p.loc['0-2', 'odds_ratio']:.2f} times a seasoned loan's, and in months 3 to 5 still "
                f"{p.loc['3-5', 'odds_ratio']:.2f} times")
    ages = ""
    if summary is not None and not summary.empty and "entry_age_median" in summary:
        by = summary.groupby("lender")["entry_age_median"].agg(["min", "max"]).sort_values("max")
        part = [f"{k} {int(r['min'])}" + (f" and {int(r['max'])}" if r["max"] != r["min"] else "")
                for k, r in by.iterrows()]
        ages = (f" A lender whose loans enter old spends much of its first year in the data inside that window. Median age "
                f"at entry, in months, one figure per deal: {escape(_join(part))}.")
    return (f"<p><b>The pool window.</b> A loan has to be current to be sold into a trust, so in its first months there it "
            f"can hardly charge off{odds}.{ages} So every curve and table in this section, and every lender ratio in the "
            f"summary above, counts a loan only from its {ORDINAL.get(POOL_OFFSET, 'first')} month in the trust; a loan that "
            f"leaves before then is not counted. That "
            f"removes most of the window; months 3 to 5 remain, so lenders whose loans enter old still look somewhat safer here "
            f"than they would if every loan were followed from origination. Until November 2026 the page counted loans from "
            f"their first month in the trust.</p>")


def _interpret_decomposition(att: pd.DataFrame) -> str:
    """Read the entry/roll split back as sentences, per lender, from the medians across score buckets."""
    if att.empty:
        return ""
    g = att.groupby("lender").agg(entry_share=("entry_share_of_gap", "median"), roll_ratio=("roll_ratio", "median"),
                                  entry_ratio=("entry_ratio", "median"), n=("lender", "size"))
    sel, roll = [], []
    for name, r in g.iterrows():
        if r["entry_share"] >= 0.7:
            sel.append(f"{name} (entry {r['entry_share']:.0%} of the gap, roll ratio {r['roll_ratio']:.2f})")
        elif r["entry_share"] <= 0.3:
            roll.append(f"{name} (roll ratio {r['roll_ratio']:.2f}, entry ratio {r['entry_ratio']:.2f})")
    out = ["<p>"]
    if sel:
        out.append(f"<b>For {escape(', '.join(n.split(' (')[0] for n in sel))} the advantage is selection.</b> "
                   f"Median across score buckets: {escape('; '.join(sel))}. Their borrowers are far less likely to fall 30 days "
                   f"behind at the same reported score, and once behind they charge off at close to the baseline lender's rate. "
                   f"There is no sign here of an account that borrowers protect: the protection would have to show up in the roll, "
                   f"and it does not. ")
    if roll:
        out.append(f"<b>For {escape(', '.join(n.split(' (')[0] for n in roll))} the difference sits in the roll instead.</b> "
                   f"Median: {escape('; '.join(roll))}. Borrowers reach 30 days late at close to the baseline rate but the outcome "
                   f"after that differs, which points at workout practice, repossession policy, or the value of the collateral to "
                   f"the borrower rather than at who was lent to. ")
    out.append("Neither pattern is a within-person comparison, so none of it measures how a borrower ranks two debts against each "
               "other. What it does rule out is the simplest version of the protection story for the lenders whose entire gap is "
               "entry: their accounts do not survive trouble better, they just meet trouble less often.</p>")
    return "".join(out)


def _skipped_sentence(results: Path) -> str:
    """What the entry/roll product leaves out: charge-offs never recorded 30 days late (R1-13)."""
    p = results / "b6_decomposition.csv"
    if not p.exists():
        return ""
    d = pd.read_csv(p)
    if "co_without_30_share" not in d:
        return ""
    d = d.dropna(subset=["co_without_30_share"]).set_index("lender")
    bad = d[~d["split_holds"].astype(bool)] if "split_holds" in d else d.iloc[0:0]
    rest = d.drop(index=bad.index)
    s = " It leaves out charge-offs never recorded 30 days late, bankruptcy-type events coded straight to charge-off: "
    if not bad.empty:
        s += (", ".join(f"{v:.0%} of {k}'s" for k, v in bad["co_without_30_share"].items())
              + f", so the split says little about {escape(', '.join(bad.index))}, and ")
    s += f"at most {rest['co_without_30_share'].max():.1%} at {'every lender' if bad.empty else 'every other lender'}"
    return escape(s) + "."


def _cif_chart(cif: pd.DataFrame, lender: str, buckets: list[str], measure: str) -> str:
    series = []
    for b in buckets:
        s = cif[(cif["lender"] == lender) & (cif["score_b"].astype(str) == b)].sort_values("age")
        if s.empty or s["n_loans"].iloc[0] < 500:
            continue
        series.append({"name": f"{b} (n={int(s['n_loans'].iloc[0]):,})", "x": s["age"].tolist(), "y": s[measure].tolist()})
    return line_chart(series, y_label="cumulative charge-off", x_label="months since origination", title=f"{lender}")


def _lender_at_score_chart(at24: pd.DataFrame) -> str:
    """Cumulative charge-off at 24 months against score bucket, one line per lender, usable cells only."""
    a = usable_cells(at24)
    series = []
    for lender, g in a.groupby("lender"):
        g = g.sort_values("lo")
        series.append({"name": lender, "x": g["lo"].tolist(), "y": g["aj_chargeoff"].tolist()})
    return line_chart(series, y_label="charge-off by 24 months (AJ)", x_label="score bucket (lower edge)", title="Same score, different lender")


def _score_gradient(hr: pd.DataFrame, spec: str) -> float:
    """Charge-off odds of scores 500-599 over 760-839 (median bucket odds ratio in each band) in one specification."""
    s = hr[(hr["factor"] == "score_b") & (hr["event"] == "chargeoff") & (hr["spec"] == spec)].copy()
    s["lv"] = pd.to_numeric(s["level"], errors="coerce")
    s = s.dropna(subset=["lv"])
    lowb = s[(s["lv"] >= 500) & (s["lv"] <= 580)]["odds_ratio"].median()
    highb = s[(s["lv"] >= 760) & (s["lv"] <= 820)]["odds_ratio"].median()
    return lowb / highb if highb and highb == highb else float("nan")


def bandwidth_stability(bw: pd.DataFrame) -> pd.DataFrame:
    """Per (lender, cutoff, horizon): does the robust interval exclude zero, with one sign, at every bandwidth?"""
    if bw is None or bw.empty:
        return pd.DataFrame()
    rows = []
    for (lender, cutoff, horizon), g in bw.groupby(["lender", "cutoff", "horizon"]):
        g = g.dropna(subset=["ci_lo", "ci_hi"])
        if g.empty:
            continue
        pos, neg = (g["ci_lo"] > 0).all(), (g["ci_hi"] < 0).all()
        main = g.loc[(g["bw_mult"] - 1.0).abs().idxmin()]
        rows.append({"lender": lender, "cutoff": cutoff, "horizon": horizon, "n_bw": len(g), "est_main": main["estimate"],
                     "p_main": main["p_robust"], "est_min": g["estimate"].min(), "est_max": g["estimate"].max(),
                     "holds": bool(pos or neg)})
    return pd.DataFrame(rows)


def _lender_interval_sentence(li: pd.DataFrame | None, baseline: dict | None, fit: dict | None) -> str:
    """Which lenders are distinguishable from the baseline once the interval carries the deal-to-deal spread (R1-6)."""
    if li is None or li.empty:
        return ""
    t = li[(li["spec"] == "terms") & (li["event"] == "chargeoff")]
    if t.empty:
        return ""
    base = (baseline or {}).get("lender", "the baseline lender")
    clear = t[(t["lo95"] > 1) | (t["hi95"] < 1)].sort_values("odds_ratio")
    cover = t[(t["lo95"] <= 1) & (t["hi95"] >= 1)].sort_values("odds_ratio")
    info = ((fit or {}).get("terms", {}).get("deal_spread", {}) or {}).get("chargeoff", {})
    sd, dof = info.get("deal_shock_sd"), info.get("df")
    n1 = int((t["n_deals"] == 1).sum())
    parts = [f"Each lender's coefficient also carries the luck of its own deals, and {n1} of these lenders own a single "
             f"deal, so their clustered intervals measure only noise inside that deal."]
    if sd is not None and dof:
        parts.append(f" Measured where it can be, between the two deals of each lender that has two, the deal-to-deal spread is "
                     f"about {sd:.2f} in log odds ({dof} degrees of freedom).")
    parts.append(" With that spread added to each interval, "
                 + (f"{escape(', '.join(f'{r.lender} {r.odds_ratio:.2f} [{r.lo95:.2f}, {r.hi95:.2f}]' for r in clear.itertuples()))} "
                    f"remain{'s' if len(clear) == 1 else ''} distinguishable from {escape(str(base))}" if not clear.empty else
                    f"no lender is distinguishable from {escape(str(base))}")
                 + (f", and {escape(', '.join(f'{r.lender} {r.odds_ratio:.2f} [{r.lo95:.2f}, {r.hi95:.2f}]' for r in cover.itertuples()))} "
                    f"{'is' if len(cover) == 1 else 'are'} not." if not cover.empty else "."))
    return "".join(parts)


def _iv(r, fmt: str = "{:.0f}") -> str:
    """'(95% interval a to b)' for a row of b1_gap.csv, or '' when it has none."""
    lo, hi = r.get("lo95"), r.get("hi95")
    if lo is None or hi is None or lo != lo or hi != hi:
        return ""
    return f"(95% interval {fmt.format(lo)} to {fmt.format(hi)})"


def _join(xs: list[str]) -> str:
    xs = list(xs)
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1] if xs else ""


def gap_verb(main: dict, without_exeter: dict | None, gradient: float) -> str:
    """How the same-bucket lender gap compares with the score gradient inside one lender, said only as strongly as
    the intervals allow: 'more than' needs both the main median's interval and the median without Exeter (whose
    score is on another scale) clear above the gradient; 'less than' needs the main interval wholly below it."""
    lo, hi = main.get("lo95", np.nan), main.get("hi95", np.nan)
    if gradient != gradient or lo != lo or hi != hi:
        return "a great deal, beside"
    nx_lo = (without_exeter or {}).get("lo95", np.nan)
    if lo > gradient and (without_exeter is None or (nx_lo == nx_lo and nx_lo > gradient)):
        return "more than"
    if hi < gradient:
        return "less than"
    return "about as much as"


def _gap_sentences(gap: pd.DataFrame, hr: pd.DataFrame, summary: pd.DataFrame | None) -> list[str]:
    """The same-score lender comparison, every ratio with its interval, from b1_gap.csv (REVIEW.md R2-1)."""
    out = []
    g = gap.copy()
    for name, h, *_ in (("480-639", 24),):
        band = g[(g["stat"] == "band") & (g["variant"] == name)]
        lv = g[(g["stat"] == "band_level") & (g["variant"] == name)].sort_values("rate", ascending=False)
        if band.empty or len(lv) < 2:
            continue
        b = band.iloc[0]
        bk = [int(x) for x in str(b["buckets"]).split(",") if x and x != "nan"]
        span = f"{bk[0]} to {bk[-1] + 19}" if bk else name.replace("-", " to ")
        levels = ", ".join(f"{r.lender} {r.rate:.1%}" for r in lv.itertuples())
        ratio = (f"Highest against lowest: {b['ratio']:.1f} times {_iv(b, '{:.1f}')}." if b["ratio"] == b["ratio"]
                 else "No second lender there has ten charge-offs, so no ratio is given.")
        out.append(f"<b>Deep in subprime, scores {span}.</b> Charge-off by {h} months, averaged over the buckets every "
                   f"subprime lender has there: {escape(levels)}. {ratio} Cells need at least {MIN_LOANS:,} loans and "
                   f"{MIN_AT_RISK} still under observation at {h} months.")
    med = g[(g["stat"] == "median") & (g["variant"] == "all")]
    buckets = g[(g["stat"] == "bucket") & (g["variant"] == "all")]
    if med.empty or med.iloc[0]["ratio"] != med.iloc[0]["ratio"]:
        return out
    m = med.iloc[0].to_dict()
    rated = buckets.dropna(subset=["ratio"])
    pick = rated.loc[rated["n"].idxmax()]
    g_s = _score_gradient(hr, "score")
    nx = g[(g["stat"] == "median") & (g["variant"] == "without_exeter")]
    nxd = nx.iloc[0].to_dict() if not nx.empty else None
    verb = gap_verb(m, nxd, g_s)
    lo_b, hi_b = int(rated["lo"].min()), int(rated["lo"].max()) + 19
    thin = sorted({t for v in rated["thin"].fillna("") for t in str(v).split(",") if t})
    thin_s = (f" In some of these buckets {escape(_join(thin))} sit{'s' if len(thin) == 1 else ''} lower still, on fewer than "
              f"{MIN_EVENTS} charge-offs each by twelve months, which is too few to divide by." if thin else "")
    dropped = buckets[buckets["ratio"].isna()]
    drop_s = (f" The {_join([f'{int(x)}' for x in dropped['lo']])} bucket{'s have' if len(dropped) > 1 else ' has'} three "
              f"lenders but no second one with {MIN_EVENTS} charge-offs, so no ratio." if len(dropped) else "")
    within = (f" Inside a single lender, moving a borrower from scores 500-599 to 760-839 moves the monthly odds by about "
              f"{g_s:.0f} times (section 3, score specification)." if g_s == g_s else "")
    checks = []
    if nxd is not None and nxd["ratio"] == nxd["ratio"]:
        ex_top = buckets[buckets["worst"] == "exeter"]["lo"].astype(int).tolist()
        moved = not (m["lo95"] <= nxd["ratio"] <= m["hi95"])
        checks.append(f"without Exeter, whose score is VantageScore rather than FICO, the median is {nxd['ratio']:.0f} times "
                      f"{_iv(nxd)} across {int(nxd['n'])} buckets"
                      + (f", outside the interval above: Exeter is the highest lender in the "
                         f"{_join([str(x) for x in ex_top])} bucket{'s' if len(ex_top) > 1 else ''}, so part of the gap is "
                         f"a comparison across score scales" if moved and ex_top else ""))
    s9 = g[(g["stat"] == "median") & (g["variant"] == "scale_900")]
    s900 = scale_900_lenders(summary)
    if not s9.empty and s9.iloc[0]["ratio"] == s9.iloc[0]["ratio"] and s900:
        s9d = s9.iloc[0].to_dict()
        b9 = g[(g["stat"] == "bucket") & (g["variant"] == "scale_900")].dropna(subset=["ratio"]).sort_values("lo")
        bx = g[(g["stat"] == "bucket") & (g["variant"] == "without_exeter")].dropna(subset=["ratio"]).sort_values("lo")
        identical = len(b9) == len(bx) and len(b9) and np.allclose(b9["ratio"].to_numpy(), bx["ratio"].to_numpy())
        others = sorted(set(summary["lender"]) - set(s900)) if summary is not None else []
        checks.append(f"keeping only the {len(s900)} lenders whose scores run past 850, the 250-900 auto-industry scale "
                      f"({escape(', '.join(s900))}), the median is {s9d['ratio']:.0f} times {_iv(s9d)}"
                      + (f"; {escape(' and '.join(others))} top out at 850 or just above, and the result is the same as "
                         f"without Exeter alone, because the other lender off that scale is never the highest or the lowest "
                         f"lender with enough charge-offs" if identical and others else ""))
    pr = g[(g["stat"] == "pairs") & (g["variant"] == "vintage")]
    if not pr.empty and pr.iloc[0]["ratio"] == pr.iloc[0]["ratio"]:
        p = pr.iloc[0].to_dict()
        checks.append(f"comparing the same two lenders in the same bucket inside a single origination year, the ratio is "
                      f"{p['ratio']:.2f} of the pooled one {_iv(p, '{:.2f}')}, median over {int(p['n'])} pairs (section 2)")
    off = g[g["stat"] == "offset"].set_index("variant")
    pool_s = ""
    if "pool_offset_0" in off.index and off.loc["pool_offset_0", "ratio"] == off.loc["pool_offset_0", "ratio"]:
        o0 = off.loc["pool_offset_0"]
        o6 = off.loc["pool_offset_6"] if "pool_offset_6" in off.index else None
        pool_s = (f" Counting each loan from its first month in the trust instead, as this page did until November 2026, the "
                  f"median under the same rule is {o0['ratio']:.0f} times"
                  + (f", and from its seventh month {o6['ratio']:.0f}" if o6 is not None and o6["ratio"] == o6["ratio"] else "")
                  + ". The page then printed 50 times, because every one of its ratios divided by a cell with one to three "
                    "charge-offs.")
    out.append(f"<b>Who lends matters {verb} what the score says.</b> Comparing lenders inside one 20-point bucket at a time, "
               f"across the {int(m['n'])} buckets from {lo_b} to {hi_b} where at least three lenders overlap and a second lender "
               f"has {MIN_EVENTS} or more charge-offs by twelve months, the highest one-year charge-off rate is a median "
               f"{m['ratio']:.0f} times the lowest {_iv(m)}; the bucket ratios run from {m['range_lo']:.0f} to "
               f"{m['range_hi']:.0f}. In the {int(pick['lo'])} to {int(pick['lo']) + 19} bucket that is {escape(str(pick['worst']))} "
               f"at {pick['worst_rate']:.2%} against {escape(str(pick['best']))} at {pick['best_rate']:.2%}.{thin_s}{drop_s}"
               f"{within}{pool_s}"
               + (" Checks: " + "; ".join(checks) + "." if checks else "")
               + " The intervals resample loans within each lender, so they carry no deal-to-deal luck, which section 3 "
                 "measures separately. The lender a borrower ends up at is not recorded in any credit file. This is a "
                 "description of who defaults where, not an effect of the lender.")
    return out


def _headlines(gap: pd.DataFrame | None, hr: pd.DataFrame, rdres: pd.DataFrame, baseline: dict | None = None,
               bw: pd.DataFrame | None = None, summary: pd.DataFrame | None = None,
               li: pd.DataFrame | None = None, fit: dict | None = None) -> list[str]:
    """Sentences computed from the result tables, so the page never claims more than the numbers."""
    out = _gap_sentences(gap, hr, summary) if gap is not None and not gap.empty else []
    L = hr[(hr["factor"] == "lender") & (hr["event"] == "chargeoff")]
    if not L.empty:
        w = L.pivot_table(index="level", columns="spec", values="odds_ratio")
        if "score" in w and "terms" in w:
            base_l = (baseline or {}).get("lender", "the baseline lender")
            lo_l, hi_l = w["terms"].idxmin(), w["terms"].idxmax()
            out.append(f"<b>Holding the bureau score and the loan structure fixed, lenders still differ by several times.</b> "
                       f"Against the baseline lender, the monthly charge-off odds run from {w.loc[lo_l, 'terms']:.2f} at {lo_l} to "
                       f"{w.loc[hi_l, 'terms']:.2f} at {hi_l}. Some of the raw gap is composition: at {lo_l} the odds ratio moves from "
                       f"{w.loc[lo_l, 'raw']:.2f} with age alone to {w.loc[lo_l, 'score']:.2f} once score is held fixed. A large gap "
                       f"survives both. In the terms column, against {escape(str(base_l))}: "
                       f"{escape(', '.join(f'{k} {v:.2f}' for k, v in w['terms'].sort_values().items()))}. "
                       f"It is not a causal effect of the lender: it carries what each lender knows beyond the score, "
                       f"who it attracts, how it services, and which loans it puts in a public deal. "
                       + _lender_interval_sentence(li, baseline, fit))
    sc = hr[(hr["factor"] == "score_b") & (hr["event"] == "chargeoff")]
    if not sc.empty and {"score", "price"} <= set(sc["spec"]):
        g_s, g_t, g_p = _score_gradient(hr, "score"), _score_gradient(hr, "terms"), _score_gradient(hr, "price")
        if g_s == g_s and g_p == g_p and g_t == g_t:
            share = 1 - (np.log(g_p) / np.log(g_t)) if g_t > 1 and g_p > 0 else float("nan")
            out.append(f"<b>The lender's own price carries part of what the score carries.</b> Scores 500 to 599 have {g_s:.1f} times "
                       f"the monthly charge-off odds of scores 760 to 839 with age and lender held fixed, {g_t:.1f} times once loan "
                       f"structure is held fixed too, and {g_p:.1f} times once the lender's APR quintile is added. So price removes "
                       f"about {share:.0%} of the score gradient that is left after loan structure, in log odds. Price is set by the "
                       f"lender from its own read of the borrower, so that column answers a narrower question and is not the "
                       f"preferred specification.")
    for f, name in (("amount_q", "loan amount"), ("pti_q", "payment-to-income"), ("ltv_q", "loan-to-value")):
        s = hr[(hr["factor"] == f) & (hr["event"] == "chargeoff") & (hr["spec"] == "terms")]
        if not s.empty:
            top = s.sort_values("level").iloc[-1]
            sig = "" if top["lo95"] <= 1 <= top["hi95"] else ", interval excludes 1"
            out.append(f"Top {name} quintile against the bottom, at the same score, lender and origination quarter: odds ratio "
                       f"{top['odds_ratio']:.2f} [{top['lo95']:.2f}, {top['hi95']:.2f}]{sig}.")
    if not rdres.empty:
        ok = rdres[rd.usable(rdres)]
        fail = rdres[rdres["density_p"] <= 0.05]
        sig = ok[ok["co24_effect"].abs() > 1.96 * ok["co24_se"]] if not ok.empty else ok
        n_tests = 2 * len(rdres)
        if len(sig) == 0 and not ok.empty:
            tail = (f"None shows a 24-month charge-off effect beyond two standard errors. The smallest standard error is "
                    f"{ok['co24_se'].min():.1%}, so an effect under about {2 * ok['co24_se'].min():.1%} could not have been seen here. "
                    f"That is a null, and it is reported as one.")
        elif not ok.empty:
            robust = ""
            if bw is not None and not bw.empty and "p_robust" in bw:
                main = bw[(bw["bw_mult"] - 1.0).abs() < 1e-9]
                n_rob = int((main["p_robust"] < 0.05).sum())
                robust = (f" With the bias-corrected robust intervals rdrobust reports, {n_rob} of {len(main)} cutoff-and-horizon "
                          f"estimates clear zero at the optimal bandwidth.")
            tail = (f"{len(sig)} of them clears two conventional standard errors at 24 months. With {n_tests} tests run across "
                    f"cutoffs and horizons, about {0.05 * n_tests:.0f} would clear that bar by chance alone, so it is not treated as "
                    f"a finding; the table in section 4 gives every estimate so the reader can judge.{robust}")
        else:
            tail = "None has both a smooth density and a real jump in terms, so there is nothing to estimate."
        st = bandwidth_stability(bw) if bw is not None else pd.DataFrame()
        if not st.empty:
            n_hold = int(st["holds"].sum())
            g = bw.dropna(subset=["ci_lo", "ci_hi"])
            clears = (g["ci_lo"] > 0) | (g["ci_hi"] < 0)
            main_bw = (g["bw_mult"] - 1.0).abs() < 1e-9
            n_main, k_main = int(main_bw.sum()), int(clears[main_bw].sum())
            n_off, k_off = int((~main_bw).sum()), int(clears[~main_bw].sum())
            off = g[~main_bw & clears]
            if "at the optimal bandwidth" not in tail:
                tail += (f" With robust intervals, {k_main} of {n_main} cutoff-and-horizon estimates clear zero at the MSE-optimal "
                         f"bandwidth.")
            tail += (f" Across the {n_off} refits at 0.5, 0.75, 1.5 and 2 times that bandwidth, {k_off} clear zero"
                     + (f" ({escape('; '.join(f'{r.lender} {r.cutoff:.0f} at {r.horizon} months, {r.bw_mult:g} times' for r in off.itertuples()))})"
                        if k_off else "")
                     + f", about the {0.05 * n_off:.0f} that chance alone would give at the 5% level, and {n_hold} of {len(st)} stay "
                       f"clear at every bandwidth. This is the only causal design on the page, and its answer is a null.")
        out.append(f"<b>Pricing cutoffs mostly are not clean experiments.</b> Of {len(rdres)} candidate score cutoffs examined, "
                   f"{len(fail)} fail the density test, meaning the pool itself changes at the line and the cutoff is an approval or "
                   f"securitization threshold rather than a pricing step. {len(ok)} have both a smooth density and a real jump in APR "
                   f"or loan amount. "
                   + tail)
    return out


def _cohort_section(c12: pd.DataFrame, c24: pd.DataFrame | None, pooled12: pd.DataFrame | None = None) -> list[str]:
    """TASKS B3 by origination cohort: the lender comparison inside one origination year at a time."""
    h = ["<h3>Inside one origination year at a time</h3>",
         "<p>A lender's public pools hold one or two vintages, and vintages differ across the industry, so a pooled lender "
         "gap could be a vintage gap. Here each comparison is inside one origination year and one 20-point bucket. Same "
         f"cell rule as above: at least {MIN_LOANS:,} loans and {MIN_AT_RISK} still observed at the horizon.</p>"]
    u = usable_cells(c12)
    if u.empty:
        return h + ["<p class='muted'>No cell meets the rule inside a single origination year.</p>"]
    years = u.groupby("orig_year")["lender"].nunique().sort_values(ascending=False)
    top = int(years.index[0])
    g = u[u["orig_year"] == top]
    series = []
    for lender, gl in g.groupby("lender"):
        gl = gl.sort_values("lo")
        series.append({"name": lender, "x": gl["lo"].tolist(), "y": gl["aj_chargeoff"].tolist()})
    h.append(line_chart(series, y_label="charge-off by 12 months (AJ)", x_label="score bucket (lower edge)",
                        title=f"Loans originated in {top}: same score, same vintage, different lender"))
    if pooled12 is not None and not pooled12.empty:
        pr = pair_ratios(u, usable_cells(pooled12))
        if not pr.empty:
            shrink = float(np.exp(np.log(pr["within_over_pooled"]).median()))
            h.append(f"<p>The test: take two lenders that both have a cell in the same bucket inside one origination year, and "
                     f"compare their charge-off ratio there with their ratio when every vintage is pooled. If the pooled gap "
                     f"were a vintage gap, the ratio inside the year would sit nearer one. Over {len(pr)} such pairs the "
                     f"within-year ratio is a median {shrink:.2f} of the pooled ratio. A pair counts only when the lower "
                     f"lender has at least {MIN_EVENTS} charge-offs both inside the year and pooled. Largest pooled gaps "
                     f"first:</p>")
            h.append(table(pr.sort_values("pooled", ascending=False),
                           cols=["orig_year", "lo", "higher", "lower", "within", "pooled", "within_over_pooled"],
                           fmt={"within": "{:.1f}", "pooled": "{:.1f}", "within_over_pooled": "{:.2f}"}, max_rows=25))
    t = u.copy()
    if c24 is not None and not c24.empty:
        k24 = usable_cells(c24)[["orig_year", "lender", "score_b", "aj_chargeoff", "at_risk"]].rename(
            columns={"aj_chargeoff": "aj_chargeoff_24", "at_risk": "at_risk_24"})
        k24["score_b"] = k24["score_b"].astype(str)
        t["score_b"] = t["score_b"].astype(str)
        t = t.merge(k24, on=["orig_year", "lender", "score_b"], how="left")
    t = t.sort_values(["orig_year", "lender", "lo"])
    cols = [c for c in ["orig_year", "lender", "lo", "n_loans", "at_risk", "aj_chargeoff", "aj_lo95", "aj_hi95",
                        "at_risk_24", "aj_chargeoff_24"] if c in t]
    h.append("<h3>Every usable cell, by origination year (12 months; 24 where enough loans reach it)</h3>")
    h.append(table(t, cols=cols, fmt={"aj_chargeoff": "{:.2%}", "aj_lo95": "{:.2%}", "aj_hi95": "{:.2%}",
                                      "aj_chargeoff_24": "{:.2%}", "n_loans": "{:,.0f}", "at_risk": "{:,.0f}",
                                      "at_risk_24": "{:,.0f}"}, max_rows=400))
    return h


def _terms_forest(hr: pd.DataFrame, baseline: dict, li: pd.DataFrame | None = None) -> str:
    """Chart 2 (TASKS B4): terms-specification charge-off odds ratios with 95% intervals. Quintile intervals are clustered
    by deal with t(9) critical values; lender intervals carry the deal-to-deal spread when b2_lender_intervals.csv
    has them (R1-6), because a clustered interval for a single-deal lender measures within-deal noise only."""
    t = hr[(hr["spec"] == "terms") & (hr["event"] == "chargeoff")].copy()
    if li is not None and not li.empty:
        h = li[(li["spec"] == "terms") & (li["event"] == "chargeoff")].set_index("lender")
        m = (t["factor"] == "lender") & t["level"].isin(h.index)
        t.loc[m, "lo95"] = t.loc[m, "level"].map(h["lo95"])
        t.loc[m, "hi95"] = t.loc[m, "level"].map(h["hi95"])
    rows = []
    blocks = (("lender", f"Lender (against {baseline.get('lender', 'baseline')})"),
              ("amount_q", "Loan amount quintile (against the lowest)"),
              ("pti_q", "Payment-to-income quintile (against the lowest)"),
              ("ltv_q", "Loan-to-value quintile (against the lowest)"))
    for factor, group in blocks:
        f = t[t["factor"] == factor].copy()
        if f.empty:
            continue
        f = f.sort_values("odds_ratio") if factor == "lender" else f.sort_values("level")
        for r in f.itertuples():
            label = r.level if factor == "lender" else f"quintile {int(float(r.level)) + 1}"
            rows.append({"label": label, "est": r.odds_ratio, "lo": r.lo95, "hi": r.hi95, "group": group})
    if not rows:
        return ""
    return ("<p>Chart 2. The <b>terms</b> specification, with lender, score bucket, loan age and origination quarter "
            "held fixed alongside the other two loan-structure measures. Descriptive with controls: each bar compares loans "
            "that differ in one recorded field, not borrowers assigned to it.</p>"
            + forest_chart(rows, title="Monthly charge-off odds ratios, terms specification (95% intervals)")
            + "<p class='muted'>Lender intervals include the deal-to-deal spread; quintile intervals are clustered by deal "
              "with t(9) critical values.</p>")


def _without_exeter(results: Path, hr: pd.DataFrame) -> str:
    """The terms specification without Exeter, whose score is VantageScore, next to the full one (HANDOFF open item)."""
    p = results / "b2_terms_without_exeter.csv"
    if not p.exists():
        return ""
    x = pd.read_csv(p)
    full = hr[(hr["spec"] == "terms") & (hr["event"] == "chargeoff")]

    def top(d, f):
        s = d[d["factor"] == f]
        return s.sort_values("level").iloc[-1] if not s.empty else None
    parts = []
    for f, name in (("amount_q", "loan amount"), ("pti_q", "payment-to-income"), ("ltv_q", "loan-to-value")):
        a, b = top(full, f), top(x, f)
        if a is not None and b is not None:
            parts.append(f"{name} {b['odds_ratio']:.2f} (all lenders {a['odds_ratio']:.2f})")
    lx = x[x["factor"] == "lender"].set_index("level")["odds_ratio"]
    lf = full[full["factor"] == "lender"].set_index("level")["odds_ratio"]
    both = [k for k in lx.index if k in lf.index]
    lend = ", ".join(f"{k} {lx[k]:.2f} ({lf[k]:.2f})" for k in sorted(both, key=lambda k: lx[k]))
    ratios = {k: lx[k] / lf[k] for k in both}
    for f in ("amount_q", "pti_q", "ltv_q"):
        a, b = top(full, f), top(x, f)
        if a is not None and b is not None:
            ratios[f] = b["odds_ratio"] / a["odds_ratio"]
    worst = max(ratios, key=lambda k: abs(np.log(ratios[k]))) if ratios else None
    verdict = ("" if worst is None else
               f" The largest move is {worst} by a factor of {ratios[worst]:.2f}"
               + (", so the one lender on a different score scale does not drive these estimates." if abs(np.log(ratios[worst])) < np.log(1.25)
                  else ", so leaving out the lender on a different score scale matters for that estimate."))
    return (f"<p class='muted'>Without Exeter, whose score is VantageScore rather than FICO, the terms specification gives, "
            f"top quintile against bottom: {escape('; '.join(parts))}. Lenders against "
            f"{escape(str(x['baseline_lender'].iloc[0]))}, with all lenders in brackets: {escape(lend)}.{escape(verdict)}</p>")


def _bandwidth_section(bw: pd.DataFrame | None) -> list[str]:
    """TASKS B5 bandwidth sensitivity: the charge-off effect at 0.5-2x the MSE-optimal bandwidth, usable cutoffs."""
    if bw is None or bw.empty:
        return []
    h = ["<h3>Bandwidth sensitivity at the usable cutoffs</h3>",
         "<p>Each usable cutoff refitted at 0.5, 0.75, 1, 1.5 and 2 times its MSE-optimal bandwidth, with the bias-corrected "
         "robust interval at each. A real effect keeps its sign and stays clear of zero as the window widens and narrows; "
         "one that appears at a single bandwidth is noise.</p>"]
    st = bandwidth_stability(bw)
    if not st.empty:
        h.append(table(st.sort_values(["lender", "cutoff", "horizon"]),
                       cols=["lender", "cutoff", "horizon", "n_bw", "est_main", "p_main", "est_min", "est_max", "holds"],
                       fmt={"cutoff": "{:.0f}", "est_main": "{:+.3f}", "p_main": "{:.3f}", "est_min": "{:+.3f}",
                            "est_max": "{:+.3f}"}))
    b = bw.sort_values(["lender", "cutoff", "horizon", "bw_mult"])
    h.append(table(b, cols=["lender", "cutoff", "horizon", "bw_mult", "bandwidth", "estimate", "ci_lo", "ci_hi", "p_robust",
                            "n_left", "n_right"],
                   fmt={"cutoff": "{:.0f}", "bw_mult": "{:.2f}", "bandwidth": "{:.1f}", "estimate": "{:+.3f}",
                        "ci_lo": "{:+.3f}", "ci_hi": "{:+.3f}", "p_robust": "{:.3f}", "n_left": "{:,.0f}",
                        "n_right": "{:,.0f}"}, max_rows=400))
    return h


def build(results: Path, out: Path, deals_csv: Path | None = None) -> Path:
    summary = pd.read_csv(results / "loans_summary.csv")
    cif = pd.read_csv(results / "b1_cif.csv")
    at12 = pd.read_csv(results / "b1_at_12.csv")
    at24 = pd.read_csv(results / "b1_at_24.csv")
    hr = pd.read_csv(results / "b2_hazard_ratios.csv")
    fit = json.loads((results / "b2_fit.json").read_text())
    cuts = pd.read_csv(results / "b3_cutoffs.csv") if (results / "b3_cutoffs.csv").exists() else pd.DataFrame()
    rdres = pd.read_csv(results / "b3_rd.csv") if (results / "b3_rd.csv").exists() else pd.DataFrame()
    bw = pd.read_csv(results / "b3_rd_bandwidths.csv") if (results / "b3_rd_bandwidths.csv").exists() else None
    li = pd.read_csv(results / "b2_lender_intervals.csv") if (results / "b2_lender_intervals.csv").exists() else None
    c12p, c24p = results / "b1_cohort_at_12.csv", results / "b1_cohort_at_24.csv"
    cohort12 = pd.read_csv(c12p) if c12p.exists() else None
    cohort24 = pd.read_csv(c24p) if c24p.exists() else None
    gap = pd.read_csv(results / "b1_gap.csv") if (results / "b1_gap.csv").exists() else None

    h = ["<h1>Auto loans: same score, different lender</h1>"]
    last = pd.Period(str(summary["last_period"].max())[:7])
    h.append(f"<p class='muted'><b>Data through {last.strftime('%B %Y')}.</b> Public ABS-EE loan-level filings on EDGAR: "
             f"{int(summary['n_loans'].sum()):,} loans in {len(summary)} deals from {summary['lender'].nunique()} lenders.</p>")
    h.append(f"<div class='note'>{escape(SCOPE)}</div>")
    h.append("<h2>What the data says</h2>")
    for line in _headlines(gap, hr, rdres, baseline=fit.get("baseline"), bw=bw, summary=summary, li=li, fit=fit):
        h.append(f"<p>{line}</p>")
    h.append(f"<div class='note'>{KIND}</div>")

    h.append("<h2>1. The deals</h2>")
    h.append(table(summary, cols=["deal", "lender", "n_loans", "first_period", "last_period", "score_type", "score_median",
                                  "score_missing_share", "apr_median", "pti_median", "share_chargeoff", "share_prepay", "share_absent", "share_censored"],
                   fmt={"score_missing_share": "{:.1%}", "apr_median": "{:.1%}", "pti_median": "{:.2f}", "share_chargeoff": "{:.1%}",
                        "share_prepay": "{:.1%}", "share_absent": "{:.1%}", "share_censored": "{:.1%}", "n_loans": "{:,.0f}"}))

    h.append("<h2>2. Cumulative charge-off by score bucket, by lender</h2>")
    h.append("<p>Age is months since origination, with delayed entry: a loan counts in the risk set only at ages it was "
             "actually observed in the trust. Aalen-Johansen cumulative incidence treats prepayment and repurchase as competing "
             "exits; the Kaplan-Meier version treats them as censoring and is always higher. Buckets are 20 points wide, labelled "
             "by the lower edge; cells with fewer than 500 loans are not drawn. Bands are 95 percent percentile bootstrap over loans.</p>")
    h.append(_pool_window_note(hr, summary))
    h.append(_lender_at_score_chart(at24))
    buckets = sorted({str(b) for b in cif["score_b"].unique() if str(b) != "none"}, key=lambda s: int(s))
    h.append("<div class='grid2'>")
    for lender in sorted(cif["lender"].unique()):
        h.append(_cif_chart(cif, lender, buckets, "aj_chargeoff"))
    h.append("</div>")
    h.append("<h3>At 24 months, with bootstrap bands</h3>")
    keep = usable_cells(at24)[["lender", "score_b"]]
    piv = at12.merge(at24, on=["lender", "score_b"], suffixes=("_12", "_24")).merge(keep, on=["lender", "score_b"])
    piv["score_b"] = piv["score_b"].astype(int)
    piv = piv.sort_values(["lender", "score_b"])
    cols = ["lender", "score_b", "n_loans_12", "at_risk_24", "aj_chargeoff_12", "aj_chargeoff_24", "aj_lo95_24", "aj_hi95_24", "km_chargeoff_24"]
    cols = [c for c in cols if c in piv]
    h.append(table(piv, cols=cols, fmt={"aj_chargeoff_12": "{:.2%}", "aj_chargeoff_24": "{:.2%}", "aj_lo95_24": "{:.2%}", "aj_hi95_24": "{:.2%}",
                                      "km_chargeoff_24": "{:.2%}", "n_loans_12": "{:,.0f}", "at_risk_24": "{:,.0f}"}, max_rows=400))
    fresh_p, fresh12_p = results / "b1_at_24_fresh.csv", results / "b1_at_12_fresh.csv"
    if fresh_p.exists() or fresh12_p.exists():
        h.append("<h3>Fresh entrants only (first seen within six months of origination)</h3>")
        h.append("<p>Seasoned loans enter a pool only because they survived to entry, and that survivor selection can differ by "
                 "lender. This cut drops them. Where it agrees with the tables above, seasoning is not driving the comparison. "
                 "It cannot settle the comparison on its own: lenders whose loans enter old have few fresh entrants, so many of "
                 "their cells fall below the cell rule here.</p>")
        for p, hz in ((fresh12_p, 12), (fresh_p, 24)):
            if not p.exists():
                continue
            fresh = usable_cells(pd.read_csv(p))
            if fresh.empty:
                h.append(f"<p class='muted'>At {hz} months no fresh-entrant cell meets the rule.</p>")
                continue
            fresh["score_b"] = fresh["score_b"].astype(int)
            cols = [c for c in ["lender", "score_b", "n_loans", "at_risk", "cum_chargeoff", "aj_chargeoff", "aj_lo95", "aj_hi95"]
                    if c in fresh]
            h.append(f"<p>Charge-off by {hz} months, {fresh['lender'].nunique()} lenders "
                     f"({escape(', '.join(sorted(fresh['lender'].unique())))}):</p>")
            h.append(table(fresh.sort_values(["lender", "score_b"]), cols=cols,
                           fmt={"aj_chargeoff": "{:.2%}", "aj_lo95": "{:.2%}", "aj_hi95": "{:.2%}", "n_loans": "{:,.0f}",
                                "at_risk": "{:,.0f}", "cum_chargeoff": "{:,.0f}"}, max_rows=400))

    if cohort12 is not None and not cohort12.empty:
        h.extend(_cohort_section(cohort12, cohort24, at12))

    h.append("<h2>3. Monthly charge-off hazard: lender at fixed score, size at fixed score and lender</h2>")
    h.append("<p>Discrete-time competing-risks hazard on the loan-month expansion, fitted as binomial logits on aggregated cells "
             "with standard errors clustered by deal and t critical values on nine degrees of freedom (ten deals); lender "
             "intervals also carry the deal-to-deal spread (headline above). Odds ratios are relative to a stated baseline level. Four specifications, "
             "each adding one layer: <b>raw</b> is loan age only; <b>score</b> adds the bureau score bucket; <b>terms</b> adds "
             "origination quarter, loan amount, payment-to-income and loan-to-value; <b>price</b> adds the lender's own APR "
             "quintile. Price is a mediator, not a confounder. The lender sets it from its private read of the borrower, so "
             "conditioning on it answers the narrower question of whether two lenders who priced a borrower the same then see the "
             "same losses. Read <b>terms</b> as the main result and <b>price</b> as a decomposition.</p>")
    h.append(_terms_forest(hr, fit.get("baseline", {}), li))
    h.append(_without_exeter(results, hr))
    for factor, title in (("lender", "Lender, charge-off"), ("amount_q", "Loan amount quintile, charge-off"), ("pti_q", "Payment-to-income quintile, charge-off"),
                          ("ltv_q", "Loan-to-value quintile, charge-off"), ("apr_q", "APR quintile, charge-off"),
                          ("score_b", "Score bucket, charge-off")):
        sub = hr[(hr["factor"] == factor) & (hr["event"] == "chargeoff")]
        if sub.empty:
            continue
        w = sub.pivot_table(index="level", columns="spec", values="odds_ratio").reset_index()
        w = w[["level"] + [c for c in ("raw", "score", "terms", "price") if c in w]]
        h.append(f"<h3>{title}</h3>")
        h.append(table(w, fmt={c: "{:.2f}" for c in w.columns if c != "level"}))
    sub = hr[(hr["factor"] == "lender") & (hr["event"] == "prepay") & (hr["spec"] == "terms")]
    if not sub.empty:
        h.append("<h3>Lender, prepayment (terms specification)</h3>")
        h.append("<p>The competing exit. A loan that pays off cannot later charge off, so a lender whose borrowers refinance or "
                 "trade in faster will show lower cumulative losses for that reason alone; the Aalen-Johansen curves above already "
                 "account for it, and these are the same differences in the hazard. Intervals and p-values include the "
                 "deal-to-deal spread.</p>")
        pp = li[(li["spec"] == "terms") & (li["event"] == "prepay")] if li is not None and not li.empty else pd.DataFrame()
        if not pp.empty:
            h.append(table(pp.sort_values("odds_ratio"), cols=["lender", "n_deals", "odds_ratio", "lo95", "hi95", "p"],
                           fmt={"odds_ratio": "{:.2f}", "lo95": "{:.2f}", "hi95": "{:.2f}", "p": "{:.3f}"}))
        else:
            h.append(table(sub[["level", "odds_ratio", "lo95", "hi95", "p"]], fmt={"odds_ratio": "{:.2f}", "lo95": "{:.2f}", "hi95": "{:.2f}", "p": "{:.3f}"}))
    base = fit.get("baseline", {})
    h.append(f"<p class='muted'>Baseline levels: {escape(', '.join(f'{k}={v}' for k, v in base.items()))}. "
             f"Terms specification: {int(fit.get('terms', {}).get('n_cells', 0)):,} cells, "
             f"{int(fit.get('terms', {}).get('n_exposure', 0)):,} loan-months, {escape(str(fit.get('terms', {}).get('cov_type', '')))}.</p>")

    h.append("<h2>4. Regression discontinuity at lender pricing cutoffs</h2>")
    h.append("<p>Where a lender's APR or loan amount jumps at a score, loans just above and below the line are alike except "
             "for the terms they got. A cutoff counts only if the jump exists (first stage), the score density does not pile "
             "up on one side (McCrary test), and it is not a known securitization floor. Charge-off effects are local-linear "
             "with an MSE-optimal bandwidth and bias-corrected robust confidence intervals.</p>")
    if not cuts.empty:
        flagged = cuts[cuts["flag"]].sort_values(["lender", "var", "cutoff"])
        h.append("<h3>Candidate cutoffs (flagged jumps)</h3>")
        h.append(table(flagged, cols=["lender", "var", "cutoff", "left", "right", "jump", "t", "n_left", "n_right", "known_selection"],
                       fmt={"left": "{:.4g}", "right": "{:.4g}", "jump": "{:.4g}", "t": "{:.1f}"}))
    if not rdres.empty:
        h.append("<h3>Estimates at the chosen cutoffs</h3>")
        r = rdres.copy()
        r["density"] = np.where(r["density_p"] > 0.05, "pass", "FAIL: bunching")
        apr = r["fs_orig_apr"].abs() > 1.96 * r["fs_orig_apr_se"]
        amt = r["fs_orig_amount"].abs() > 1.96 * r["fs_orig_amount_se"]
        r["first_stage"] = np.select([apr & amt, apr, amt], ["APR and amount", "APR", "amount"], "none")
        r["verdict"] = np.where(rd.usable(r), "usable", "not usable")
        cols = [c for c in ["lender", "cutoff", "density", "density_p", "first_stage", "fs_orig_apr", "fs_orig_amount", "co12_effect", "co12_se", "co12_n", "co24_effect", "co24_se", "co24_n", "verdict"] if c in r]
        h.append(table(r.sort_values(["verdict", "lender", "cutoff"]), cols=cols,
                       fmt={"density_p": "{:.3f}", "fs_orig_apr": "{:+.3f}", "fs_orig_amount": "{:+,.0f}",
                            "co12_effect": "{:+.3f}", "co12_se": "{:.3f}", "co24_effect": "{:+.3f}", "co24_se": "{:.3f}"}))
        h.append("<p>Outcome samples are loans first observed within six months of origination, so a seasoned loan's survival to "
                 "entry does not select the sample differently on the two sides. A negative APR first stage with a positive "
                 "charge-off effect would mean cheaper terms raised default, which is not what selection predicts; read both signs together. "
                 "Effects are local-linear with an MSE-optimal bandwidth (rdrobust) and standard errors from the same fit.</p>")
        h.extend(_bandwidth_section(bw))
    else:
        h.append("<p class='muted'>No cutoff passed the screens in this build.</p>")

    dec_p, att_p = results / "b6_by_score.csv", results / "b6_attribution_by_score.csv"
    if dec_p.exists() and att_p.exists():
        dec, att = pd.read_csv(dec_p), pd.read_csv(att_p)
        att = att[att["n_ever30"] >= 100]
        h.append("<h2>5. Selection or protection: where in the process the advantage sits</h2>")
        h.append("<p>A lender that loses less at the same score is either picking borrowers who do not get into trouble, or "
                 "holding an account that survives trouble better. Those are different claims and the level of charge-off cannot "
                 "separate them, so the gap is split into two stages: <b>entry</b>, the chance of reaching 30 days past due within "
                 "24 months of origination, and <b>roll</b>, the chance of charging off within 12 months of first reaching 30 days. "
                 "Their product approximates the charge-off rate, and the log gap against the baseline lender splits between them."
                 + _skipped_sentence(results) + "</p>")
        h.append("<div class='note'>The roll comparison is the more trustworthy of the two. It conditions on an observed behaviour, "
                 "being 30 days late, rather than on a score, so it is not disturbed by the fact that these lenders report different "
                 "score types on different scales. The entry comparison is partly contaminated by that scale difference; the roll "
                 "comparison is not.</div>")
        h.append("<h3>Entry rate: reaching 30 days past due within 24 months</h3>")
        e = dec.pivot_table(index="score_b", columns="lender", values="entry_rate").reset_index()
        h.append(table(e, fmt={c: "{:.1%}" for c in e.columns if c != "score_b"}))
        h.append("<h3>Roll rate: charging off within 12 months of first being 30 days late</h3>")
        r = dec.pivot_table(index="score_b", columns="lender", values="roll_rate").reset_index()
        h.append(table(r, fmt={c: "{:.1%}" for c in r.columns if c != "score_b"}))
        h.append("<h3>Share of the same-score gap that is entry</h3>")
        h.append("<p>One means the whole difference is who gets into trouble, which is selection. Zero means the whole difference is "
                 "what happens after trouble starts. Cells need at least 100 loans that ever reached 30 days.</p>")
        s = att.pivot_table(index="score_b", columns="lender", values="entry_share_of_gap").reset_index()
        h.append(table(s, fmt={c: "{:.2f}" for c in s.columns if c != "score_b"}))
        h.append(_interpret_decomposition(att))
    h.append("<h2>6. What this does and does not say about cards</h2>")
    h.append("<p>Nothing here observes a person's card and auto loan together, so it says nothing about which one they pay "
             "first. It says how default varies with lender and loan size at a fixed score in one product where the loan-level "
             "data is public. The score-shape of default from section 2 is one of the three candidate shapes used on the cards page.</p>")
    h.append("<footer>Code and data: <a href='https://github.com/SamuelJWebber/abs-risk'>github.com/SamuelJWebber/abs-risk</a>. "
             "Every number traces to a filing accession recorded in the build manifest. What each estimate can carry: "
             "<a href='https://github.com/SamuelJWebber/abs-risk/blob/main/design/methods.md'>design/methods.md</a>.</footer>")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page("abs-risk autos", "".join(h), current="autos.html"), encoding="utf-8")
    return out


def main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="absrisk report autos")
    ap.add_argument("--results", default="data/results/autos")
    ap.add_argument("--out", default="docs/autos.html")
    a = ap.parse_args(argv)
    p = build(Path(a.results), Path(a.out))
    print(f"wrote {p}", file=sys.stderr)
    return 0
