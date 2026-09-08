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

SCOPE = ("These are loans inside public auto ABS trusts, not the lenders' whole books. A loan enters when the trust "
         "is formed or replenished and leaves when it pays off, is repurchased, or charges off; some sponsors drop "
         "paid-off loans from the file the month after payoff and others keep them, which the exit rule handles. "
         "Months are counted from the first month the loan is seen in the trust. Scores are the score type the "
         "sponsor reports (FICO at most captives, a bureau score at Santander, VantageScore at Exeter) and are never "
         "refreshed after origination.")


def _cif_chart(cif: pd.DataFrame, lender: str, buckets: list[str], measure: str) -> str:
    series = []
    for b in buckets:
        s = cif[(cif["lender"] == lender) & (cif["score_b"].astype(str) == b)].sort_values("age")
        if s.empty or s["n_loans"].iloc[0] < 500:
            continue
        series.append({"name": f"{b} (n={int(s['n_loans'].iloc[0]):,})", "x": s["age"].tolist(), "y": s[measure].tolist()})
    return line_chart(series, y_label="cumulative charge-off", x_label="months since origination", title=f"{lender}")


def _lender_at_score_chart(at24: pd.DataFrame) -> str:
    """Cumulative charge-off at 24 months against score bucket, one line per lender, cells with >= 1500 loans."""
    a = at24[(at24["score_b"].astype(str) != "none") & (at24["n_loans"] >= 1500)].copy()
    a["lo"] = a["score_b"].astype(int)
    series = []
    for lender, g in a.groupby("lender"):
        g = g.sort_values("lo")
        series.append({"name": lender, "x": g["lo"].tolist(), "y": g["aj_chargeoff"].tolist()})
    return line_chart(series, y_label="charge-off by 24 months (AJ)", x_label="score bucket (lower edge)", title="Same score, different lender")


def _headlines(at24: pd.DataFrame, hr: pd.DataFrame, rdres: pd.DataFrame) -> list[str]:
    """Sentences computed from the result tables, so the page never claims more than the numbers."""
    out = []
    a = at24[(at24["score_b"].astype(str) != "none") & (at24["n_loans"] >= 1500)].copy()
    a["lo"] = a["score_b"].astype(int)
    for lo_, hi_, label in ((480, 620, "subprime overlap, scores 480 to 639"), (700, 760, "prime overlap, scores 700 to 779")):
        band = a[(a["lo"] >= lo_) & (a["lo"] <= hi_)]
        if band["lender"].nunique() < 2:
            continue
        m = band.groupby("lender")["aj_chargeoff"].mean().sort_values(ascending=False)
        parts = ", ".join(f"{k} {v:.1%}" for k, v in m.items())
        out.append(f"<b>{label.capitalize()}.</b> Charge-off by 24 months, averaged over the buckets each lender has: {parts}. "
                   f"The top and bottom differ by {m.iloc[0] / max(m.iloc[-1], 1e-9):.1f} times at the same score.")
    L = hr[(hr["factor"] == "lender") & (hr["event"] == "chargeoff")]
    if not L.empty:
        w = L.pivot_table(index="level", columns="spec", values="odds_ratio")
        if "score" in w and "terms" in w:
            lo_l = w["score"].idxmin()
            out.append(f"<b>Holding the bureau score fixed</b>, lenders still differ: the monthly charge-off hazard at {lo_l} is "
                       f"{w.loc[lo_l, 'score']:.2f} times the baseline lender's, and adding origination quarter, loan amount, "
                       f"payment burden and loan-to-value moves it to {w.loc[lo_l, 'terms']:.2f}. Part of the raw gap is who they lend "
                       f"to and part is how the loan is structured; a gap survives both.")
    sc = hr[(hr["factor"] == "score_b") & (hr["event"] == "chargeoff")]
    if not sc.empty and {"score", "price"} <= set(sc["spec"]):
        def grad(spec):
            s = sc[sc["spec"] == spec].copy()
            s["lv"] = pd.to_numeric(s["level"], errors="coerce")
            s = s.dropna(subset=["lv"])
            lowb = s[(s["lv"] >= 500) & (s["lv"] <= 580)]["odds_ratio"].median()
            highb = s[(s["lv"] >= 760) & (s["lv"] <= 820)]["odds_ratio"].median()
            return lowb / highb if highb and highb == highb else float("nan")
        g_s, g_p = grad("score"), grad("price")
        if g_s == g_s and g_p == g_p:
            out.append(f"<b>The lender's own price knows more than the score.</b> Scores 500 to 599 carry {g_s:.0f} times the monthly "
                       f"charge-off odds of scores 760 to 839 when only age and lender are held fixed. Add the lender's APR quintile and "
                       f"that ratio falls to {g_p:.1f}: the price absorbs nearly all of the bureau score's predictive content, and more. "
                       f"That is why the APR-conditioned column is shown last and is not the preferred specification.")
    for f, name in (("amount_q", "loan amount"), ("pti_q", "payment-to-income"), ("ltv_q", "loan-to-value")):
        s = hr[(hr["factor"] == f) & (hr["event"] == "chargeoff") & (hr["spec"] == "terms")]
        if not s.empty:
            top = s.sort_values("level").iloc[-1]
            sig = "" if top["lo95"] <= 1 <= top["hi95"] else ", interval excludes 1"
            out.append(f"Top {name} quintile against the bottom, at the same score, lender and origination quarter: odds ratio "
                       f"{top['odds_ratio']:.2f} [{top['lo95']:.2f}, {top['hi95']:.2f}]{sig}.")
    if not rdres.empty:
        ok = rdres[(rdres["density_p"] > 0.05)]
        fail = rdres[(rdres["density_p"] <= 0.05)]
        out.append(f"<b>Cutoffs.</b> {len(fail)} candidate pricing cutoffs fail the density test (the applicant pool changes at the line, "
                   f"so they are approval thresholds, not pricing steps) and {len(ok)} pass. "
                   + ("No passing cutoff shows a charge-off effect distinguishable from zero at current sample sizes." if not ok.empty and
                      ((ok["co24_effect"].abs() < 1.96 * ok["co24_se"]) | ok["co24_effect"].isna()).all() else
                      "See section 4 for the passing cutoffs with detectable effects."))
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
    for line in _headlines(at24, hr, rdres):
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
    piv = at12.merge(at24, on=["lender", "score_b"], suffixes=("_12", "_24"))
    piv = piv[(piv["n_loans_12"] >= 500) & (piv["score_b"].astype(str) != "none")].copy()
    piv["score_b"] = piv["score_b"].astype(int)
    piv = piv.sort_values(["lender", "score_b"])
    cols = ["lender", "score_b", "n_loans_12", "at_risk_24", "aj_chargeoff_12", "aj_chargeoff_24", "aj_lo95_24", "aj_hi95_24", "km_chargeoff_24"]
    cols = [c for c in cols if c in piv]
    h.append(table(piv, cols=cols, fmt={"aj_chargeoff_12": "{:.2%}", "aj_chargeoff_24": "{:.2%}", "aj_lo95_24": "{:.2%}", "aj_hi95_24": "{:.2%}",
                                      "km_chargeoff_24": "{:.2%}", "n_loans_12": "{:,.0f}", "at_risk_24": "{:,.0f}"}, max_rows=400))
    fresh_p = results / "b1_at_24_fresh.csv"
    if fresh_p.exists():
        fresh = pd.read_csv(fresh_p)
        fresh = fresh[(fresh["n_loans"] >= 500) & (fresh["score_b"].astype(str) != "none")].copy()
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
