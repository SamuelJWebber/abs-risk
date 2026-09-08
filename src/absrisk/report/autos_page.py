"""docs/autos.html from data/results/autos/. Run: `uv run absrisk report autos`."""

from __future__ import annotations

import json
import sys
from datetime import date
from html import escape
from pathlib import Path

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
    h.append("<p>Discrete-time competing-risks hazard on the loan-month expansion, fitted as binomial logits on aggregated "
             "cells with standard errors clustered by deal. Odds ratios are relative to the first level of each factor. "
             "Three specifications: raw (age only), score only, and full (score, cohort quarter, loan amount, payment-to-income, "
             "loan-to-value and APR quintiles). The move from raw to full is how much of a lender's gap is composition.</p>")
    for factor, title in (("lender", "Lender, charge-off"), ("amount_q", "Loan amount quintile, charge-off"), ("pti_q", "Payment-to-income quintile, charge-off"),
                          ("score_b", "Score bucket, charge-off")):
        sub = hr[(hr["factor"] == factor) & (hr["event"] == "chargeoff")]
        if sub.empty:
            continue
        w = sub.pivot_table(index="level", columns="spec", values="odds_ratio").reset_index()
        w = w[["level"] + [c for c in ("raw", "score_only", "full") if c in w]]
        h.append(f"<h3>{title}</h3>")
        h.append(table(w, fmt={c: "{:.2f}" for c in w.columns if c != "level"}))
    sub = hr[(hr["factor"] == "lender") & (hr["event"] == "prepay") & (hr["spec"] == "full")]
    if not sub.empty:
        h.append("<h3>Lender, prepayment (full specification)</h3>")
        h.append(table(sub[["level", "odds_ratio", "lo95", "hi95", "p"]], fmt={"odds_ratio": "{:.2f}", "lo95": "{:.2f}", "hi95": "{:.2f}", "p": "{:.3f}"}))
    h.append(f"<p class='muted'>Full specification: {int(fit.get('full', {}).get('n_cells', 0)):,} cells, "
             f"{int(fit.get('full', {}).get('n_exposure', 0)):,} loan-months.</p>")

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
        cols = [c for c in ["lender", "cutoff", "density_method", "density_p", "fs_orig_apr", "fs_orig_amount", "co12_effect", "co12_se", "co12_n", "co24_effect", "co24_se", "co24_n"] if c in rdres]
        h.append(table(rdres, cols=cols, fmt={"density_p": "{:.3f}", "fs_orig_apr": "{:+.3f}", "fs_orig_amount": "{:+,.0f}",
                                             "co12_effect": "{:+.3f}", "co12_se": "{:.3f}", "co24_effect": "{:+.3f}", "co24_se": "{:.3f}"}))
        h.append("<p>A positive charge-off effect with a negative APR first stage would mean the cheaper terms above the line "
                 "raised default, which is not what selection predicts; read the sign of both together.</p>")
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
