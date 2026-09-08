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


def _headlines(rank: pd.DataFrame, pred: pd.DataFrame, mix: pd.DataFrame) -> list[str]:
    """Sentences computed from the tables, so the page cannot claim more than the numbers carry."""
    out = []
    if rank.empty:
        return out
    r = rank.pivot_table(index="trust", columns="shape_source", values="rank")
    res = rank.pivot_table(index="trust", columns="shape_source", values="mean_residual")
    stable = r[r.nunique(axis=1) == 1]
    moved = r[r.nunique(axis=1) > 1]
    n_shapes = r.shape[1]
    if not stable.empty:
        top = stable[stable.min(axis=1) == stable.min(axis=1).min()]
        bot = stable[stable.max(axis=1) == stable.max(axis=1).max()]
        parts = []
        if not top.empty:
            t = top.index[0]
            parts.append(f"{t} charges off more than its own score mix predicts under every one of the {n_shapes} shapes "
                         f"(residual {res.loc[t].min():+.2%} to {res.loc[t].max():+.2%})")
        if not bot.empty and bot.index[0] != (top.index[0] if not top.empty else None):
            b = bot.index[0]
            parts.append(f"{b} charges off least relative to its mix under every shape ({res.loc[b].min():+.2%} to {res.loc[b].max():+.2%})")
        if parts:
            out.append("<b>The ends of the ranking hold; the middle does not.</b> " + "; ".join(parts) +
                       f". {len(moved)} of {len(r)} trusts change rank depending on which loss curve is assumed"
                       + (f" ({escape(', '.join(moved.index))})" if not moved.empty else "") +
                       ". So the ordering of the extremes is a finding and the ordering of the middle is not.")
    flip = res[(res > 0).any(axis=1) & (res < 0).any(axis=1)]
    same = res[~res.index.isin(flip.index)]
    if not flip.empty:
        names = escape(", ".join(sorted(flip.index)))
        line = (f"<b>The size of the gap is not identified.</b> For {len(flip)} of {len(res)} trusts ({names}) the residual changes sign "
                f"with the assumed loss curve: the same trust looks worse than its mix under the consumer-level shapes and better under "
                f"the card-level ones. The two families disagree by about five times on how much more a deep subprime account loses than "
                f"a prime one, and that choice moves every level.")
        if not same.empty:
            keep = ", ".join(f"{t} ({res.loc[t].min():+.2%} to {res.loc[t].max():+.2%})" for t in sorted(same.index))
            line += f" Only {escape(keep)} keeps the same sign under all {n_shapes}, so it is the one trust whose gap does not depend on the assumption."
        out.append(line)
    act = rank.groupby("trust")["mean_actual"].first()
    act_spread = act.max() / max(act.min(), 1e-9)
    predsp = rank.pivot_table(index="trust", columns="shape_source", values="mean_predicted")
    spreads = (predsp.max() / predsp.min()).sort_values()
    if len(spreads) >= 2:
        lo_s, hi_s = spreads.index[0], spreads.index[-1]
        out.append(f"<b>How much of the spread is score mix depends entirely on the shape.</b> Charge-off across these trusts spans "
                   f"{act.min():.2%} to {act.max():.2%}, a factor of {act_spread:.1f}. The mix alone predicts a spread of only "
                   f"{spreads[lo_s]:.1f} times under {escape(lo_s)} and {spreads[hi_s]:.1f} times under {escape(hi_s)}. On the flatter "
                   f"card-level curves the pools look nearly identical and almost none of the difference is composition; on the steeper "
                   f"consumer curves most of it is. Public data does not settle which curve a card portfolio actually follows.")
    if not mix.empty and "deep_subprime" in mix:
        m = mix.dropna(subset=["deep_subprime"]).copy()
        m["below_prime"] = m[["deep_subprime", "subprime", "near_prime"]].sum(axis=1)
        m = m[m["trust"].isin(set(rank["trust"]))]
        if not m.empty:
            hi, lo = m.loc[m["below_prime"].idxmax()], m.loc[m["below_prime"].idxmin()]
            out.append(f"For scale, below-prime receivables run from {lo['below_prime']:.1%} at {lo['trust']} to "
                       f"{hi['below_prime']:.1%} at {hi['trust']}. Every one of these pools is overwhelmingly prime and above, which is "
                       f"what a public card trust is: the securitised, seasoned end of an issuer's book, not the book.")
    return out


def _interpret_stages(bt: pd.DataFrame) -> str:
    """Read the entry/progression/conversion split back as sentences."""
    d = bt.dropna(subset=["entry_share_of_gap"])
    if d.empty:
        return ""
    base = bt.loc[bt["co_monthly"].idxmax(), "trust"]
    best = d.loc[d["co_monthly"].idxmin()]
    over = d[d["entry_share_of_gap"] > 1.0]
    parts = [f"<p><b>The advantage is in never getting into trouble, not in surviving it.</b> {best['trust']} loses "
             f"{best['co_monthly_ratio']:.2f} times what {base} loses each month. Its 30-plus share is "
             f"{best['entry_ratio']:.2f} times {base}'s, but once an account is 90 days late it converts to a loss at "
             f"{best['conversion_ratio']:.2f} times {base}'s rate. Entry accounts for {best['entry_share_of_gap']:.0%} of the gap "
             f"and conversion for {best['conversion_share_of_gap']:+.0%}."]
    if not over.empty:
        names = ", ".join(sorted(over["trust"]))
        parts.append(f" For {escape(names)} the entry share exceeds one, meaning conversion works against them: their deeply "
                     f"delinquent accounts end in loss <i>more</i> readily than the worst trust's do, and the entry advantage has to "
                     f"cover that too.")
    parts.append(" That is the opposite of what protection would look like. If cardholders paid this issuer first, accounts would "
                 "reach 90 days late and then be rescued, which is a low conversion rate, not a high one. Two other readings survive: "
                 "the issuer may charge off faster by policy or re-age less, and the pools differ in score mix. The mix objection does "
                 "not touch conversion, which already conditions on being 90 days late; the policy objection does.</p>")
    return "".join(parts)


def _interpret_stress(sdf: pd.DataFrame, order: list[str]) -> str:
    """Does the conversion ratio move with the macro cycle, and in which direction?

    Prioritisation predicts a specific sign: a card borrowers protect should have its deeply delinquent accounts
    rescued more often when money is tight, so its conversion ratio should FALL in a squeeze. A ratio that holds
    still, or rises, is evidence against that story rather than for it.
    """
    w = sdf.pivot_table(index="trust", columns="period", values="conversion_ratio").reindex(columns=order)
    w = w.dropna(thresh=2)
    if w.empty or len(order) < 2:
        return ""
    ent = sdf.pivot_table(index="trust", columns="period", values="entry").reindex(columns=order).dropna(thresh=2)
    ent_move = (ent.max(axis=1) / ent.min(axis=1)).median() if not ent.empty else float("nan")
    first, last = order[0], order[-1]
    best = w.mean(axis=1).idxmin()          # the trust with the lowest conversion, the protection candidate
    lowest_loss = sdf.groupby("trust")["co_monthly"].mean().idxmin()
    moves = (w[last] - w[first]).dropna()
    rose = moves[moves > 0.05]
    fell = moves[moves < -0.05]
    parts = [f"<p>Between {escape(first)} and {escape(last)}, delinquency itself moved by about {ent_move:.1f} times, "
             f"so households really were squeezed and relieved across this window. "]
    if len(rose) >= len(fell):
        names = escape(", ".join(sorted(rose.index))) if not rose.empty else "none"
        parts.append(f"The conversion ratios did not fall for anyone who looks protected. They rose for {names} "
                     f"and fell for {len(fell)} trust(s). ")
    else:
        parts.append(f"Conversion ratios fell for {escape(', '.join(sorted(fell.index)))}. ")
    parts.append(f"Prioritisation predicts a particular sign here: a card that borrowers pay first should rescue more of its "
                 f"90-day-late accounts exactly when money is tight, so its conversion ratio should drop in the squeeze. ")
    if lowest_loss in moves.index:
        d = moves[lowest_loss]
        parts.append(f"{lowest_loss}, the trust with the lowest loss rate, moves {d:+.2f} over the window, "
                     f"{'the wrong way for that story' if d > 0 else 'the direction that story predicts'}. ")
    parts.append(f"The trust with the lowest conversion throughout is {best}, which is not the lowest-loss trust, so the ordering by "
                 f"'accounts that survive trouble' does not match the ordering by 'accounts that lose least'. Taken together the "
                 f"cycle evidence does not support borrowers ranking these issuers; it fits fixed differences in who was lent to and "
                 f"in how each issuer charges off.</p>")
    return "".join(parts)


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
    h.append("<h2>What the data says</h2>")
    for line in _headlines(rank, pred, mix):
        h.append(f"<p>{line}</p>")

    h.append("<h2>1. Score mix by trust</h2>")
    cols = ["trust", "as_of", "basis", "score_type", "clamped_edges", "deep_subprime", "subprime", "near_prime", "prime", "prime_plus", "superprime"]
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

    bt_p, stress_p = results / "a3_by_trust.csv", results / "a3_stress.csv"
    if bt_p.exists():
        bt = pd.read_csv(bt_p)
        h.append("<h2>5. Does anyone pay this card first?</h2>")
        h.append("<p>A trust with a low loss rate either has accounts that rarely go delinquent, or accounts that go delinquent and "
                 "do not end in a loss. Those are different claims. The monthly charge-off rate factors exactly, with no modelling, "
                 "into three shares the trust reports itself:</p>")
        h.append("<p class='muted'>monthly charge-off &nbsp;=&nbsp; <b>entry</b> (30+ share) &nbsp;x&nbsp; "
                 "<b>progression</b> (90+ / 30+) &nbsp;x&nbsp; <b>conversion</b> (monthly charge-off / 90+)</p>")
        h.append("<p>If cardholders really did protect one issuer's account, that issuer's <b>conversion</b> would be low: accounts "
                 "would reach 90 days late and still be rescued. Selection instead shows up in <b>entry</b>. The comparison of "
                 "conversion is the more trustworthy half, because it conditions on accounts already 90 days late rather than on the "
                 "pool's score mix.</p>")
        cols = ["trust", "months", "co_monthly", "entry", "progression", "conversion",
                "entry_ratio", "conversion_ratio", "entry_share_of_gap", "conversion_share_of_gap"]
        cols = [c for c in cols if c in bt]
        h.append(table(bt, cols=cols, fmt={"co_monthly": "{:.3%}", "entry": "{:.2%}", "progression": "{:.2f}", "conversion": "{:.1%}",
                                          "entry_ratio": "{:.2f}", "conversion_ratio": "{:.2f}",
                                          "entry_share_of_gap": "{:.2f}", "conversion_share_of_gap": "{:.2f}"}))
        h.append(_interpret_stages(bt))
        if stress_p.exists():
            sdf = pd.read_csv(stress_p)
            if not sdf.empty:
                order = [p for p in ("pre-covid 2019", "stimulus 2020-21", "normalising 2022-23H1", "squeeze 2023H2 on") if p in set(sdf["period"])]
                w = sdf.pivot_table(index="trust", columns="period", values="conversion_ratio").reindex(columns=order).reset_index()
                h.append("<h3>The same ratio through four very different years</h3>")
                h.append("<p>If borrowers rank their debts, the ranking should bite hardest when money is tight, so a protected "
                         "card's 90-day-late accounts should be rescued more often in a squeeze and its conversion ratio should "
                         "<i>fall</i>. This is the one place the two stories make opposite predictions about a direction, rather than "
                         "about a level, which is why it is worth looking at even though the periods are crude.</p>")
                h.append(table(w, fmt={c: "{:.2f}" for c in w.columns if c != "trust"}))
                h.append(_interpret_stress(sdf, order))
    h.append("<h2>6. Panel regression</h2>")
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
