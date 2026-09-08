"""docs/cards.html from data/results/cards/. Run: `uv run absrisk report cards`."""

from __future__ import annotations

import sys
from datetime import date
from html import escape
from pathlib import Path

import pandas as pd

from .svg import CSS, line_chart, table

SCOPE = ("Trust pools are selected, seasoned accounts, not the issuer's book. The FICO mix is a snapshot from the "
         "latest prospectus and is held fixed between prospectus dates. Charge-off bases differ by trust and are "
         "kept as reported. The residual is actual minus what the pool's score mix predicts under a stated "
         "loss-by-tier shape; it mixes underwriting, product, customer mix within a score band, pool selection and "
         "behaviour, and it cannot say which. Nothing here is a payment-hierarchy estimate.")


def build(results: Path, out: Path) -> Path:
    pred = pd.read_csv(results / "a1_predicted.csv")
    rank = pd.read_csv(results / "a1_ranking.csv") if (results / "a1_ranking.csv").exists() else pd.DataFrame()
    mix = pd.read_csv(results / "mix_by_trust.csv")
    panel = pd.read_csv(results / "a2_panel.csv") if (results / "a2_panel.csv").exists() else pd.DataFrame()
    shapes = pd.read_csv(Path("data/loss_shape.csv")) if Path("data/loss_shape.csv").exists() else pd.DataFrame()

    h = [f"<title>abs-risk cards</title><style>{CSS}</style><main>"]
    h.append("<h1>Card trusts: charge-off against what the score mix predicts</h1>")
    h.append(f"<p class='muted'>Built {date.today().isoformat()} from monthly 10-D reports and prospectus composition tables on EDGAR, "
             f"and CFPB card market report figure data. {pred['trust'].nunique()} trusts, {pred['period_end'].nunique()} months.</p>")
    h.append(f"<div class='note'>{escape(SCOPE)}</div>")

    h.append("<h2>1. Score mix by trust</h2>")
    cols = ["trust", "as_of", "basis", "score_type", "deep_subprime", "subprime", "near_prime", "prime", "prime_plus", "superprime"]
    cols = [c for c in cols if c in mix]
    h.append(table(mix.sort_values(["trust", "as_of"]), cols=cols, fmt={t: "{:.1%}" for t in ("deep_subprime", "subprime", "near_prime", "prime", "prime_plus", "superprime")}))
    if "error" in mix and mix["error"].notna().any():
        h.append("<p class='muted'>Not mapped: " + escape("; ".join(f"{r['trust']} ({r['error']})" for _, r in mix[mix['error'].notna()].iterrows())) + "</p>")

    h.append("<h2>2. The three loss-by-tier shapes</h2>")
    h.append("<p>Relative charge-off by tier, prime = 1. Consumer-level FICO odds (any account, 90+ days past due) are steep; "
             "card-level charge-off rates by FICO among accounts already issued are much flatter, because lenders size lines "
             "and price by score. Which shape is right for a pool decides its residual, so every result is shown under each.</p>")
    if not shapes.empty:
        w = shapes.pivot_table(index="tier", columns="shape_source", values="relative_loss").reindex(
            ["deep_subprime", "subprime", "near_prime", "prime", "prime_plus", "superprime"]).reset_index()
        h.append(table(w, fmt={c: "{:.2f}" for c in w.columns if c != "tier"}))

    h.append("<h2>3. Actual against predicted, by trust</h2>")
    h.append("<div class='grid2'>")
    for trust, g in pred.groupby("trust"):
        g = g.copy()
        g["t"] = pd.to_datetime(g["period_end"])
        x0 = g["t"].min()
        series = []
        a = g[g["shape_source"] == g["shape_source"].iloc[0]].sort_values("t")
        series.append({"name": "actual", "x": ((a["t"] - x0).dt.days / 30.4).round(1).tolist(), "y": a["actual"].tolist(), "color": "#1d1d1b"})
        for s, gs in g.groupby("shape_source"):
            gs = gs.sort_values("t")
            series.append({"name": f"predicted, {s}", "x": ((gs["t"] - x0).dt.days / 30.4).round(1).tolist(), "y": gs["predicted"].tolist()})
        h.append(line_chart(series, y_label="annualised gross charge-off", x_label=f"months from {x0.date()}", title=trust))
    h.append("</div>")

    h.append("<h2>4. Ranking by residual, under each shape</h2>")
    if not rank.empty:
        w = rank.pivot_table(index="trust", columns="shape_source", values="mean_residual").reset_index()
        r = rank.pivot_table(index="trust", columns="shape_source", values="rank").reset_index()
        h.append("<h3>Mean residual (actual minus predicted), percentage points of annualised charge-off</h3>")
        h.append(table(w, fmt={c: "{:+.2%}" for c in w.columns if c != "trust"}))
        h.append("<h3>Rank (1 = largest positive residual)</h3>")
        h.append(table(r))
        stable = (r.drop(columns="trust").nunique(axis=1) == 1).all()
        h.append(f"<p><b>{'The ranking is the same under every shape.' if stable else 'The ranking changes with the shape.'}</b> "
                 f"{'The ordering of trusts does not depend on which loss curve is assumed.' if stable else 'Which trust looks worse depends on the assumed loss curve, so no single ordering is reported as a finding.'}</p>")

    h.append("<h2>5. Panel regression</h2>")
    h.append("<p>Trust-month regression of the gross charge-off rate on tier shares with month fixed effects, then with trust fixed "
             "effects added. Driscoll-Kraay standard errors. With six trusts and slow-moving mixes, trust effects and mix are close to "
             "collinear; the first column identifies the mix gradient across trusts, the second only its within-trust movement.</p>")
    if not panel.empty and "term" in panel:
        w = panel.pivot_table(index="term", columns="spec", values=["coef", "se"]).reset_index()
        w.columns = ["term"] + [f"{a}_{b}" for a, b in w.columns[1:]]
        h.append(table(w, fmt={c: "{:+.3f}" for c in w.columns if c != "term"}))
    else:
        h.append("<p class='muted'>Not estimated in this build (see a2_panel.csv).</p>")

    h.append("<footer>Code and data: github.com/SamuelJWebber/abs-risk. Row labels, bases and prospectus tables per trust are in design/scout-cards.md.</footer></main>")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(h), encoding="utf-8")
    return out


def main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="absrisk report cards")
    ap.add_argument("--results", default="data/results/cards")
    ap.add_argument("--out", default="docs/cards.html")
    a = ap.parse_args(argv)
    p = build(Path(a.results), Path(a.out))
    print(f"wrote {p}", file=sys.stderr)
    return 0
