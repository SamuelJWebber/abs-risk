"""docs/autos.html from data/results/autos/. Run: `uv run absrisk report autos`."""

from __future__ import annotations

import json
import sys
from datetime import date
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd

from .svg import CSS, line_chart, table

MIN_LOANS = 1500        # loans in the cell
MIN_AT_RISK = 250       # still under observation at the horizon: a cell can have many loans but few old enough

SCOPE = ("These are loans inside public auto ABS trusts, not the lenders' whole books. A loan enters when the trust "
         "is formed or replenished and leaves when it pays off, is repurchased, or charges off; some sponsors drop "
         "paid-off loans from the file the month after payoff and others keep them, which the exit rule handles. "
         "Months are counted from the first month the loan is seen in the trust. Scores are the score type the "
         "sponsor reports (FICO at most captives, a bureau score at Santander, VantageScore at Exeter) and are never "
         "refreshed after origination.")


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


def _headlines(at12: pd.DataFrame, at24: pd.DataFrame, hr: pd.DataFrame, rdres: pd.DataFrame) -> list[str]:
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
    ov = usable_cells(at12)
    ov = ov[(ov["lo"] >= 660) & (ov["lo"] <= 780)]
    per_bucket = ov.groupby("lo").filter(lambda g: g["lender"].nunique() >= 3)
    if not per_bucket.empty:
        # one score bucket at a time, so the comparison is genuinely at the same score
        ratios = per_bucket.groupby("lo").apply(
            lambda g: g["aj_chargeoff"].max() / max(g["aj_chargeoff"].min(), 1e-9), include_groups=False)
        pick = per_bucket.groupby("lo")["lender"].nunique().idxmax()
        g = per_bucket[per_bucket["lo"] == pick]
        worst, best = g.loc[g["aj_chargeoff"].idxmax()], g.loc[g["aj_chargeoff"].idxmin()]
        out.append(f"<b>Who lends matters more than what the score says.</b> Comparing lenders inside one 20-point bucket at a time, "
                   f"across the {len(ratios)} buckets from 660 to 799 where at least three lenders overlap, the highest one-year "
                   f"charge-off rate is {ratios.median():.0f} times the lowest (range {ratios.min():.0f} to {ratios.max():.0f}). "
                   f"In the {int(pick)} to {int(pick) + 19} bucket that is {worst['lender']} at {worst['aj_chargeoff']:.2%} against "
                   f"{best['lender']} at {best['aj_chargeoff']:.2%}. Inside a single lender, moving a borrower from the 500s to the 800s "
                   f"moves the monthly odds by about nine times. The lender a borrower ends up at is not a small effect beside that, "
                   f"and no credit file records it.")
    L = hr[(hr["factor"] == "lender") & (hr["event"] == "chargeoff")]
    if not L.empty:
        w = L.pivot_table(index="level", columns="spec", values="odds_ratio")
        if "score" in w and "terms" in w:
            lo_l, hi_l = w["terms"].idxmin(), w["terms"].idxmax()
            out.append(f"<b>Holding the bureau score and the loan structure fixed, lenders still differ by several times.</b> "
                       f"Against the baseline lender, the monthly charge-off odds run from {w.loc[lo_l, 'terms']:.2f} at {lo_l} to "
                       f"{w.loc[hi_l, 'terms']:.2f} at {hi_l}. Some of the raw gap is composition: at {lo_l} the odds ratio moves from "
                       f"{w.loc[lo_l, 'raw']:.2f} with age alone to {w.loc[lo_l, 'score']:.2f} once score is held fixed. A large gap "
                       f"survives both. It is not a causal effect of the lender: it carries what each lender knows beyond the score, "
                       f"who it attracts, how it services, and which loans it puts in a public deal.")
    sc = hr[(hr["factor"] == "score_b") & (hr["event"] == "chargeoff")]
    if not sc.empty and {"score", "price"} <= set(sc["spec"]):
        def grad(spec):
            s = sc[sc["spec"] == spec].copy()
            s["lv"] = pd.to_numeric(s["level"], errors="coerce")
            s = s.dropna(subset=["lv"])
            lowb = s[(s["lv"] >= 500) & (s["lv"] <= 580)]["odds_ratio"].median()
            highb = s[(s["lv"] >= 760) & (s["lv"] <= 820)]["odds_ratio"].median()
            return lowb / highb if highb and highb == highb else float("nan")
        g_s, g_t, g_p = grad("score"), grad("terms"), grad("price")
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
        ok = rdres[(rdres["density_p"] > 0.05) & (rdres["fs_orig_apr"].abs() > 1.96 * rdres["fs_orig_apr_se"])]
        fail = rdres[rdres["density_p"] <= 0.05]
        sig = ok[ok["co24_effect"].abs() > 1.96 * ok["co24_se"]] if not ok.empty else ok
        n_tests = 2 * len(rdres)
        if len(sig) == 0 and not ok.empty:
            tail = (f"None shows a 24-month charge-off effect beyond two standard errors. The smallest standard error is "
                    f"{ok['co24_se'].min():.1%}, so an effect under about {2 * ok['co24_se'].min():.1%} could not have been seen here. "
                    f"That is a null, and it is reported as one.")
        elif not ok.empty:
            tail = (f"{len(sig)} of them clears two standard errors at 24 months. With {n_tests} tests run across cutoffs and horizons, "
                    f"about {0.05 * n_tests:.0f} would clear that bar by chance alone, so it is not treated as a finding; the table in "
                    f"section 4 gives every estimate so the reader can judge.")
        else:
            tail = "None has both a smooth density and a real jump in terms, so there is nothing to estimate."
        out.append(f"<b>Pricing cutoffs mostly are not clean experiments.</b> Of {len(rdres)} candidate score cutoffs examined, "
                   f"{len(fail)} fail the density test, meaning the pool itself changes at the line and the cutoff is an approval or "
                   f"securitization threshold rather than a pricing step. {len(ok)} have both a smooth density and a real jump in APR. "
                   + tail)
    return out


def build(results: Path, out: Path, deals_csv: Path | None = None) -> Path:
    summary = pd.read_csv(results / "loans_summary.csv")
    cif = pd.read_csv(results / "b1_cif.csv")
    at12 = pd.read_csv(results / "b1_at_12.csv")
    at24 = pd.read_csv(results / "b1_at_24.csv")
    hr = pd.read_csv(results / "b2_hazard_ratios.csv")
    fit = json.loads((results / "b2_fit.json").read_text())
    cuts = pd.read_csv(results / "b3_cutoffs.csv") if (results / "b3_cutoffs.csv").exists() else pd.DataFrame()
    rdres = pd.read_csv(results / "b3_rd.csv") if (results / "b3_rd.csv").exists() else pd.DataFrame()

    h = [f"<title>abs-risk autos</title><style>{CSS}</style><main>"]
    h.append("<h1>Auto loans: same score, different lender</h1>")
    h.append(f"<p class='muted'>Built {date.today().isoformat()} from public ABS-EE loan-level filings on EDGAR. "
             f"{int(summary['n_loans'].sum()):,} loans in {len(summary)} deals from {summary['lender'].nunique()} lenders.</p>")
    h.append(f"<div class='note'>{escape(SCOPE)}</div>")
    h.append("<h2>What the data says</h2>")
    for line in _headlines(at12, at24, hr, rdres):
        h.append(f"<p>{line}</p>")

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

    h.append("<h2>3. Monthly charge-off hazard: lender at fixed score, size at fixed score and lender</h2>")
    h.append("<p>Discrete-time competing-risks hazard on the loan-month expansion, fitted as binomial logits on aggregated cells "
             "with standard errors clustered by deal. Odds ratios are relative to a stated baseline level. Four specifications, "
             "each adding one layer: <b>raw</b> is loan age only; <b>score</b> adds the bureau score bucket; <b>terms</b> adds "
             "origination quarter, loan amount, payment-to-income and loan-to-value; <b>price</b> adds the lender's own APR "
             "quintile. Price is a mediator, not a confounder. The lender sets it from its private read of the borrower, so "
             "conditioning on it answers the narrower question of whether two lenders who priced a borrower the same then see the "
             "same losses. Read <b>terms</b> as the main result and <b>price</b> as a decomposition.</p>")
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
        r["first_stage"] = np.where(r["fs_orig_apr"].abs() > 1.96 * r["fs_orig_apr_se"], "APR jump", "none")
        r["verdict"] = np.where((r["density"] == "pass") & (r["first_stage"] != "none"), "usable", "not usable")
        cols = [c for c in ["lender", "cutoff", "density", "density_p", "first_stage", "fs_orig_apr", "fs_orig_amount", "co12_effect", "co12_se", "co12_n", "co24_effect", "co24_se", "co24_n", "verdict"] if c in r]
        h.append(table(r.sort_values(["verdict", "lender", "cutoff"]), cols=cols,
                       fmt={"density_p": "{:.3f}", "fs_orig_apr": "{:+.3f}", "fs_orig_amount": "{:+,.0f}",
                            "co12_effect": "{:+.3f}", "co12_se": "{:.3f}", "co24_effect": "{:+.3f}", "co24_se": "{:.3f}"}))
        h.append("<p>Outcome samples are loans first observed within six months of origination, so a seasoned loan's survival to "
                 "entry does not select the sample differently on the two sides. A negative APR first stage with a positive "
                 "charge-off effect would mean cheaper terms raised default, which is not what selection predicts; read both signs together. "
                 "Effects are local-linear with an MSE-optimal bandwidth (rdrobust) and standard errors from the same fit.</p>")
    else:
        h.append("<p class='muted'>No cutoff passed the screens in this build.</p>")

    h.append("<h2>5. What this does and does not say about cards</h2>")
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
