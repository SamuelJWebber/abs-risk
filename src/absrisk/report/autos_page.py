"""docs/autos.html from data/results/autos/. Run: `uv run absrisk report autos`."""

from __future__ import annotations

import json
import sys
from datetime import date
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd

from ..estimate import rd
from .svg import CSS, forest_chart, line_chart, table

MIN_LOANS = 1500        # loans in the cell
MIN_AT_RISK = 250       # still under observation at the horizon: a cell can have many loans but few old enough

SCOPE = ("These are loans inside public auto ABS trusts, not the lenders' whole books. A loan enters when the trust "
         "is formed or replenished and leaves when it pays off, is repurchased, or charges off; some sponsors drop "
         "paid-off loans from the file the month after payoff and others keep them, which the exit rule handles. "
         "Age is months since origination, and a loan counts only from the month it is first seen in the trust. Scores "
         "are the score type the sponsor reports (FICO at most captives, a bureau score at Santander, VantageScore at "
         "Exeter for 98.9% of its pool) and are never refreshed after origination, so a 700 at Exeter and a 700 at Honda "
         "are close but not the same number.")

KIND = ("<b>What kind of claim each section makes.</b> Sections 2, 3 and 5 are descriptive: who defaults, at which "
        "lender, holding what fixed. Controls narrow a comparison, they do not make it causal, because a lender's "
        "borrowers differ in ways no field in the filing records. Section 4 is the only design here that could carry a "
        "causal sentence, and only at a cutoff that passes its screens.")


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


def usable_cells(at: pd.DataFrame) -> pd.DataFrame:
    """Cells with enough loans and enough of them still under observation at the horizon."""
    a = at[(at["score_b"].astype(str) != "none") & (at["n_loans"] >= MIN_LOANS) & (at["at_risk"] >= MIN_AT_RISK)].copy()
    a["lo"] = a["score_b"].astype(int)
    return a


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


def bucket_ratios(cells: pd.DataFrame, lo: int = 660, hi: int = 780, min_lenders: int = 3,
                  by: tuple[str, ...] = ()) -> pd.DataFrame:
    """Inside each score bucket (and each `by` group), highest over lowest charge-off across lenders.

    `cells` are usable cells at one horizon. Only buckets where at least `min_lenders` lenders have a cell count, so
    every ratio is a comparison at one score. Columns: by..., lo, n_lenders, worst, best, ratio."""
    c = cells[(cells["lo"] >= lo) & (cells["lo"] <= hi)]
    rows = []
    for keys, g in c.groupby(list(by) + ["lo"]):
        if g["lender"].nunique() < min_lenders:
            continue
        keys = keys if isinstance(keys, tuple) else (keys,)
        w, b = g.loc[g["aj_chargeoff"].idxmax()], g.loc[g["aj_chargeoff"].idxmin()]
        rows.append({**dict(zip(list(by) + ["lo"], keys)), "n_lenders": g["lender"].nunique(), "worst": w["lender"],
                     "best": b["lender"], "worst_rate": w["aj_chargeoff"], "best_rate": b["aj_chargeoff"],
                     "ratio": w["aj_chargeoff"] / b["aj_chargeoff"] if b["aj_chargeoff"] > 0 else np.nan})
    return pd.DataFrame(rows)


def pair_ratios(cohort_cells: pd.DataFrame, pooled_cells: pd.DataFrame) -> pd.DataFrame:
    """Same two lenders, same score bucket: their charge-off ratio inside one origination year against the pooled one.

    If a pooled lender gap were a vintage gap, the ratio inside a single year would sit nearer 1 than the pooled
    ratio. Both inputs are usable cells at one horizon; pairs whose lower rate is zero in either table are skipped,
    because a ratio over zero is not a number. Columns: orig_year, lo, higher, lower, within, pooled, within_over_pooled.
    """
    import itertools

    pooled = {(r.lender, r.lo): r.aj_chargeoff for r in pooled_cells.itertuples()}
    rows = []
    for (year, lo), g in cohort_cells.groupby(["orig_year", "lo"]):
        rates = dict(zip(g["lender"], g["aj_chargeoff"]))
        for a, b in itertools.permutations(rates, 2):
            pa, pb = pooled.get((a, lo)), pooled.get((b, lo))
            if not (rates[a] > rates[b] > 0) or pa is None or not pb:
                continue
            rows.append({"orig_year": year, "lo": lo, "higher": a, "lower": b, "within": rates[a] / rates[b],
                         "pooled": pa / pb, "within_over_pooled": (rates[a] / rates[b]) / (pa / pb)})
    return pd.DataFrame(rows)


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


def _headlines(at12: pd.DataFrame, at24: pd.DataFrame, hr: pd.DataFrame, rdres: pd.DataFrame,
               cohort12: pd.DataFrame | None = None, baseline: dict | None = None,
               bw: pd.DataFrame | None = None) -> list[str]:
    """Sentences computed from the result tables, so the page never claims more than the numbers."""
    out = []
    for at, horizon, lo_, hi_, label in ((at24, 24, 480, 620, "Deep in subprime, scores 480 to 639"),
                                         (at12, 12, 700, 760, "Where subprime and prime lenders overlap, scores 700 to 779")):
        band = usable_cells(at)
        band = band[(band["lo"] >= lo_) & (band["lo"] <= hi_)]
        if band["lender"].nunique() < 2:
            continue
        m = band.groupby("lender")["aj_chargeoff"].mean().sort_values(ascending=False)
        parts = ", ".join(f"{k} {v:.2%}" for k, v in m.items())
        out.append(f"<b>{label}.</b> Charge-off by {horizon} months, averaged over the buckets each lender has: {parts}. "
                   f"Highest against lowest, at the same bureau score: {m.iloc[0] / max(m.iloc[-1], 1e-9):.0f} times. "
                   f"Cells need at least {MIN_LOANS:,} loans and {MIN_AT_RISK} still under observation at {horizon} months.")
    # one score bucket at a time, so the comparison is genuinely at the same score
    ratios = bucket_ratios(usable_cells(at12))
    if not ratios.empty:
        pick = ratios.loc[ratios["n_lenders"].idxmax()]
        g_s = _score_gradient(hr, "score")
        within = (f"Inside a single lender, moving a borrower from scores 500-599 to 760-839 moves the monthly odds by about "
                  f"{g_s:.0f} times (section 3, score specification). " if g_s == g_s else "")
        nx = bucket_ratios(usable_cells(at12[at12["lender"] != "exeter"]))
        robust, meds, names = [], [], []
        if not nx.empty:
            names.append("score scale")
            meds.append(nx["ratio"].median())
            robust.append(f"leaving out Exeter, whose score is VantageScore rather than FICO, the median is {meds[-1]:.0f} "
                          f"times across {len(nx)} buckets (range {nx['ratio'].min():.0f} to {nx['ratio'].max():.0f})")
        ok = []
        if not nx.empty:
            ok.append(meds[-1] >= 3)
        if cohort12 is not None and not cohort12.empty:
            pr = pair_ratios(usable_cells(cohort12), usable_cells(at12))
            if not pr.empty:
                names.append("vintage")
                shrink = float(np.exp(np.log(pr["within_over_pooled"]).median()))
                big = pr[pr["pooled"] >= 10]
                ok.append(shrink >= 0.5)
                tail_big = (f"; the {len(big)} pairs more than ten times apart pooled are {big['within'].median():.0f} times apart "
                            f"inside the year against {big['pooled'].median():.0f} pooled" if len(big) else "")
                robust.append(f"comparing the same two lenders in the same bucket inside a single origination year, the ratio is "
                              f"{shrink:.2f} of the pooled one (median over {len(pr)} pairs{tail_big}; section 2)")
        if robust:
            what = " and ".join(names)
            lead = (f"It survives the obvious objection{'s' if len(names) > 1 else ''}, {what}: " if all(ok) else
                    f"Checking {what} moves it: ")
            rob = lead + "; ".join(robust) + ". "
        else:
            rob = ""
        out.append(f"<b>Who lends matters more than what the score says.</b> Comparing lenders inside one 20-point bucket at a time, "
                   f"across the {len(ratios)} buckets from 660 to 799 where at least three lenders overlap, the highest one-year "
                   f"charge-off rate is {ratios['ratio'].median():.0f} times the lowest (range {ratios['ratio'].min():.0f} to "
                   f"{ratios['ratio'].max():.0f}). In the {int(pick['lo'])} to {int(pick['lo']) + 19} bucket that is {pick['worst']} at "
                   f"{pick['worst_rate']:.2%} against {pick['best']} at {pick['best_rate']:.2%}. {rob}{within}The lender a borrower "
                   f"ends up at is not a small effect beside that, and no credit file records it. This is a description of who "
                   f"defaults where, not an effect of the lender.")
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
                       f"who it attracts, how it services, and which loans it puts in a public deal.")
    sc = hr[(hr["factor"] == "score_b") & (hr["event"] == "chargeoff")]
    if not sc.empty and {"score", "price"} <= set(sc["spec"]):
        g_s, g_t, g_p = _score_gradient(hr, "score"), _score_gradient(hr, "terms"), _score_gradient(hr, "price")
        if g_s == g_s and g_p == g_p:
            share = 1 - (np.log(g_p) / np.log(g_s)) if g_s > 1 and g_p > 0 else float("nan")
            out.append(f"<b>The lender's own price carries much of what the score carries.</b> Scores 500 to 599 have {g_s:.0f} times "
                       f"the monthly charge-off odds of scores 760 to 839 with age and lender held fixed, {g_t:.0f} times once loan "
                       f"structure is held fixed too, and {g_p:.1f} times once the lender's APR quintile is added. Adding price removes "
                       f"about {share:.0%} of the remaining score gradient in log odds. Price is set by the lender from its own read of "
                       f"the borrower, so that column answers a narrower question and is not the preferred specification.")
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
            tail += (f" Refitting each usable cutoff at 0.5, 0.75, 1.5 and 2 times its bandwidth, {n_hold} of {len(st)} "
                     f"cutoff-and-horizon estimates keep a robust interval that excludes zero at every bandwidth"
                     + (": " + escape(", ".join(f"{r.lender} {r.cutoff:.0f} at {r.horizon} months ({r.est_main:+.1%})"
                                                for r in st[st["holds"]].itertuples())) if n_hold else "")
                     + ". This is the only causal design on the page, and its answer is a null.")
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
                     f"within-year ratio is a median {shrink:.2f} of the pooled ratio. Pairs where the lower lender has no "
                     f"charge-offs are left out. Largest pooled gaps first:</p>")
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


def _terms_forest(hr: pd.DataFrame, baseline: dict) -> str:
    """Chart 2 (TASKS B4): terms-specification charge-off odds ratios with 95% intervals, clustered by deal."""
    t = hr[(hr["spec"] == "terms") & (hr["event"] == "chargeoff")]
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
            + forest_chart(rows, title="Monthly charge-off odds ratios, terms specification (95% intervals, clustered by deal)"))


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
    c12p, c24p = results / "b1_cohort_at_12.csv", results / "b1_cohort_at_24.csv"
    cohort12 = pd.read_csv(c12p) if c12p.exists() else None
    cohort24 = pd.read_csv(c24p) if c24p.exists() else None

    h = [f"<title>abs-risk autos</title><style>{CSS}</style><main>"]
    h.append("<h1>Auto loans: same score, different lender</h1>")
    h.append(f"<p class='muted'>Built {date.today().isoformat()} from public ABS-EE loan-level filings on EDGAR. "
             f"{int(summary['n_loans'].sum()):,} loans in {len(summary)} deals from {summary['lender'].nunique()} lenders.</p>")
    h.append(f"<div class='note'>{escape(SCOPE)}</div>")
    h.append("<h2>What the data says</h2>")
    for line in _headlines(at12, at24, hr, rdres, cohort12=cohort12, baseline=fit.get("baseline"), bw=bw):
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
    fresh_p = results / "b1_at_24_fresh.csv"
    if fresh_p.exists():
        fresh = usable_cells(pd.read_csv(fresh_p))
        fresh["score_b"] = fresh["score_b"].astype(int)
        h.append("<h3>Fresh entrants only (first seen within six months of origination)</h3>")
        h.append("<p>Seasoned loans enter a pool only because they survived to entry, and that survivor selection can differ by "
                 "lender. This cut drops them. Where it agrees with the table above, seasoning is not driving the comparison.</p>")
        h.append(table(fresh.sort_values(["lender", "score_b"]), cols=["lender", "score_b", "n_loans", "at_risk", "aj_chargeoff", "aj_lo95", "aj_hi95"],
                       fmt={"aj_chargeoff": "{:.2%}", "aj_lo95": "{:.2%}", "aj_hi95": "{:.2%}", "n_loans": "{:,.0f}", "at_risk": "{:,.0f}"}, max_rows=400))

    if cohort12 is not None and not cohort12.empty:
        h.extend(_cohort_section(cohort12, cohort24, at12))

    h.append("<h2>3. Monthly charge-off hazard: lender at fixed score, size at fixed score and lender</h2>")
    h.append("<p>Discrete-time competing-risks hazard on the loan-month expansion, fitted as binomial logits on aggregated cells "
             "with standard errors clustered by deal. Odds ratios are relative to a stated baseline level. Four specifications, "
             "each adding one layer: <b>raw</b> is loan age only; <b>score</b> adds the bureau score bucket; <b>terms</b> adds "
             "origination quarter, loan amount, payment-to-income and loan-to-value; <b>price</b> adds the lender's own APR "
             "quintile. Price is a mediator, not a confounder. The lender sets it from its private read of the borrower, so "
             "conditioning on it answers the narrower question of whether two lenders who priced a borrower the same then see the "
             "same losses. Read <b>terms</b> as the main result and <b>price</b> as a decomposition.</p>")
    h.append(_terms_forest(hr, fit.get("baseline", {})))
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
                 "account for it, and these are the same differences in the hazard.</p>")
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
                 "Their product is the charge-off rate, so the log gap against the baseline lender splits cleanly between them.</p>")
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
    h.append("<footer>Code and data: github.com/SamuelJWebber/abs-risk. Every number traces to a filing accession recorded in the build manifest.</footer></main>")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(h), encoding="utf-8")
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
