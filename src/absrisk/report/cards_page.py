"""docs/cards.html from data/results/cards/. Run: `uv run absrisk report cards`."""

from __future__ import annotations

import sys
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd

from ..estimate import cards_roll
from ..shape.level import data_dir
from .svg import line_chart, page, table

STRESS_ORDER = ("pre-covid 2019", "stimulus 2020-21", "normalising 2022-23H1", "squeeze 2023H2 on")

SCOPE = ("Trust pools are selected, seasoned accounts, not the issuer's book. Charge-off bases differ by trust and are "
         "kept as reported. The residual is actual minus what the pool's score mix predicts under a stated "
         "loss-by-tier shape; it mixes underwriting, product, customer mix within a score band, pool selection and "
         "behaviour, and it cannot say which. In principle it says whether a trust loses more than its score mix "
         "predicts, by how many points, and since when. Here the number of points depends on which loss curve is "
         "assumed (section 4), so the page reports a sign only where every curve agrees, and the years in which it held. "
         "It cannot say why. Nothing here is a payment-hierarchy estimate.")


def _snapshot_note(pred: pd.DataFrame, mix: pd.DataFrame) -> str:
    """How the score mix and the industry level are applied over time, stated from the prediction table (R1-7)."""
    if pred.empty or "mix_extrapolated" not in pred:
        return ""
    one = pred[pred["shape_source"] == pred["shape_source"].iloc[0]]
    first = pd.to_datetime(one["period_end"]).min()
    ok = mix.dropna(subset=["as_of"]) if "as_of" in mix else pd.DataFrame()
    dates = pd.to_datetime(ok["as_of"]) if not ok.empty else pd.Series(dtype="datetime64[ns]")
    n_snap = ok.groupby("trust")["as_of"].nunique() if not ok.empty else pd.Series(dtype=int)
    snap = ("one prospectus snapshot per trust" if not n_snap.empty and (n_snap == 1).all()
            else "the prospectus snapshots in the composition table")
    parts = [f"The score mix is {snap}, dated {dates.min():%B %Y} to {dates.max():%B %Y}, applied to every month since "
             f"{first:%B %Y}. So {one['mix_extrapolated'].mean():.0%} of trust-months are predicted from a snapshot dated after "
             f"them, and when a trust files a new prospectus every earlier month's prediction for it changes."]
    if "level_year_clamped" in one and one["level_year_clamped"].any():
        cl = one[one["level_year_clamped"]]
        yrs = sorted(pd.to_datetime(cl["period_end"]).dt.year.unique())
        last_level = int(cl["level_year"].max())
        span = f"{yrs[0]}" if len(yrs) == 1 else f"{yrs[0]}-{str(yrs[-1])[-2:]}"
        parts.append(f" The CFPB industry level runs to {last_level}, so months in {span} use the {last_level} level "
                     f"({one['level_year_clamped'].mean():.0%} of trust-months).")
    return "".join(parts)


def _sign_by_year(pred: pd.DataFrame) -> pd.DataFrame:
    """Per trust and calendar year: '+' if the mean residual is positive under every shape, '-' if negative under
    every shape, '+/-' if the shapes disagree. This is the page's 'since when'."""
    p = pred.assign(year=pd.to_datetime(pred["period_end"]).dt.year)
    g = p.groupby(["trust", "year", "shape_source"])["residual"].mean().unstack("shape_source")
    sign = pd.Series(np.where((g > 0).all(axis=1), "+", np.where((g < 0).all(axis=1), "-", "+/-")), index=g.index)
    return sign.unstack("year")


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
    prog = f"{bt['progression'].min():.2f} to {bt['progression'].max():.2f}" if "progression" in bt else ""
    parts = [f"<p><b>The advantage is in never getting into trouble, not in surviving it.</b> {best['trust']} loses "
             f"{best['co_monthly_ratio']:.2f} times what {base} loses each month. Its 30-plus share is "
             f"{best['entry_ratio']:.2f} times {base}'s, but once an account is 90 days late it converts to a loss at "
             f"{best['conversion_ratio']:.2f} times {base}'s rate. Entry accounts for {best['entry_share_of_gap']:.0%} of the "
             f"gap, progression for {best['progression_share_of_gap']:+.0%} and conversion for "
             f"{best['conversion_share_of_gap']:+.0%}." + (f" Progression barely differs between trusts ({prog} of 30-day-late "
                                                          f"balances reach 90 days), so the story is in the other two." if prog else "")]
    if not over.empty:
        names = ", ".join(sorted(over["trust"]))
        parts.append(f" For {escape(names)} the entry share exceeds one, meaning conversion works against them: their deeply "
                     f"delinquent accounts end in loss <i>more</i> readily than the worst trust's do, and the entry advantage has to "
                     f"cover that too.")
    parts.append(" That is the opposite of what protection would look like. If cardholders paid this issuer first, accounts would "
                 "reach 90 days late and then be rescued, which is a low conversion rate, not a high one. Two other readings survive: "
                 "the issuer may charge off faster by policy or re-age less, and the pools differ in score mix. The mix objection does "
                 "not touch conversion, which already conditions on being 90 days late; the policy objection does.")
    low_conv = d.loc[d["conversion"].idxmin(), "trust"] if "conversion" in d else None
    if low_conv is not None and low_conv != best["trust"]:
        parts.append(f" The trust whose 90-day-late balances convert least is {escape(str(low_conv))}, not the lowest-loss trust, so "
                     f"the ordering by surviving trouble does not match the ordering by losing least.")
    parts.append("</p>")
    return "".join(parts)


def _names(xs, moves: dict | None = None) -> str:
    """'a (-0.10), b (+0.02) and c', or 'none'."""
    if not xs:
        return "none"
    items = [f"{x} ({moves[x]:+.2f})" if moves is not None else str(x) for x in xs]
    return escape(items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1])


def direction_sentences(d: dict, best: str | None = None) -> list[str]:
    """The direction test in sentences, from `cards_roll.direction_summary`. Used by the cards and conclusions pages,
    so the two cannot disagree about it."""
    out = []
    r = d.get("regime")
    tol = d.get("tol", 0.05)
    if r:
        n = r["months"] // 2
        line = (f"Split the {r['months']} months by the trusts' own delinquency. In the {n} months when it ran above its median "
                f"({r['index_tight']:.2f} times each trust's usual 30-plus share, against {r['index_loose']:.2f} in the other "
                f"{r['months'] - n}), the conversion ratio against {escape(r['baseline'])} fell for "
                f"{_names(r['fell'], r['moves'])}, rose for {_names(r['rose'], r['moves'])}, and moved by less than "
                f"{tol:.2f} for {_names(r['flat'])}.")
        if best and best in r["loose"]:
            mv = r["moves"].get(best, float("nan"))
            line += (f" For {escape(best)}, the lowest-loss trust, it went from {r['loose'][best]:.2f} in loose months to "
                     f"{r['tight'][best]:.2f} in tight ones: {'the direction prioritisation predicts' if mv < 0 else 'the wrong way for prioritisation'}"
                     f", while staying {'above' if r['tight'][best] > 1 else 'below'} {escape(r['baseline'])}'s 1.00.")
        out.append(line)
    ts = d.get("tightenings", [])
    if ts:
        for t in ts:
            out.append(f"Of the named periods, the step from {escape(t['from'])} to {escape(t['to'])} raised every trust's 30-plus "
                       f"share (by {t['rise_min'] - 1:.0%} to {t['rise_max'] - 1:.0%}). Across it the conversion ratio fell for "
                       f"{_names(t['fell'], t['moves'])}, rose for {_names(t['rose'], t['moves'])}, and was flat for "
                       f"{_names(t['flat'])}.")
    elif d.get("endpoints") is not None:
        out.append("No step between the named periods raised every trust's 30-plus share, so none of them is a clean squeeze.")
    e = d.get("endpoints")
    if e and not e["tighter"]:
        out.append(f"The first and last named periods are not a tightening: every trust's 30-plus share is "
                   f"{'lower' if e['looser'] else 'not uniformly higher'} in {escape(e['to'])} than in {escape(e['from'])} "
                   f"({e['ratio_min']:.2f} to {e['ratio_max']:.2f} times). Until November 2026 this page compared exactly those two "
                   f"and read the result as a test of prioritisation; it was not one.")
    v = d.get("verdict", "mixed")
    if v == "mixed":
        out.append("<b>So the direction test is mixed.</b> The moves either way are small beside the level gap above, and conversion "
                   "divides a flow by a stock that builds ahead of the charge-offs, which lowers it whenever delinquency is rising, "
                   "whoever is paid first. The level comparison carries the argument; this test neither confirms nor overturns it.")
    elif v == "priority":
        out.append("<b>The direction test leans towards prioritisation:</b> every trust's conversion ratio fell in the tight months. "
                   "Conversion falls mechanically while delinquency builds, so this is weak evidence, but it is the predicted sign.")
    else:
        out.append("<b>The direction test goes against prioritisation:</b> no trust's conversion ratio fell in the tight months.")
    return out


def build(results: Path, out: Path) -> Path:
    pred = pd.read_csv(results / "a1_predicted.csv")
    rank = pd.read_csv(results / "a1_ranking.csv") if (results / "a1_ranking.csv").exists() else pd.DataFrame()
    mix = pd.read_csv(results / "mix_by_trust.csv")
    panel = pd.read_csv(results / "a2_panel.csv") if (results / "a2_panel.csv").exists() else pd.DataFrame()
    shape_csv = data_dir() / "loss_shape.csv"            # the repo's data folder, wherever the command runs from
    shapes = pd.read_csv(shape_csv) if shape_csv.exists() else pd.DataFrame()

    h = ["<h1>Card trusts: charge-off against what the score mix predicts</h1>"]
    months = pd.to_datetime(pred["period_end"])
    h.append(f"<p class='muted'><b>Data through {months.max():%B %Y}.</b> Monthly 10-D reports and prospectus composition tables "
             f"on EDGAR, and CFPB card market report figure data: {pred['trust'].nunique()} trusts, "
             f"{months.dt.to_period('M').nunique()} calendar months, {months.min():%B %Y} to {months.max():%B %Y}.</p>")
    h.append(f"<div class='note'>{escape(SCOPE)} {escape(_snapshot_note(pred, mix))}</div>")
    h.append("<h2>What the data says</h2>")
    for line in _headlines(rank, pred, mix):
        h.append(f"<p>{line}</p>")

    h.append("<h2>1. Score mix by trust</h2>")
    h.append("<p>Each prospectus bucket is spread over the six CFPB tiers uniformly in score, as written in "
             "crosswalks/fico_buckets.csv; the analysis reads that file and nothing else for the mapping.")
    if "unscored" in mix and mix["unscored"].notna().any():
        u = mix.dropna(subset=["unscored"])
        lo_u, hi_u = u.loc[u["unscored"].idxmin()], u.loc[u["unscored"].idxmax()]
        h.append(f" Balances with no score ({lo_u['unscored']:.2%} at {escape(str(lo_u['trust']))} to "
                 f"{hi_u['unscored']:.2%} at {escape(str(hi_u['trust']))}) cannot be placed on the scale, so they are dropped "
                 f"and the scored balances renormalised.")
        if "mapping_flags" in mix:
            mixed = sorted(mix.loc[mix["mapping_flags"].fillna("").str.contains("includes_unscored"), "trust"])
            if mixed:
                h.append(f" {escape(', '.join(mixed))} print{'s' if len(mixed) == 1 else ''} unscored accounts inside the lowest "
                         f"score bucket rather than on a row of their own, so there they stay in that bucket's score range.")
    h.append("</p>")
    cols = ["trust", "as_of", "basis", "score_type", "clamped_edges", "unscored", "deep_subprime", "subprime", "near_prime", "prime", "prime_plus", "superprime"]
    cols = [c for c in cols if c in mix]
    h.append(table(mix.sort_values(["trust", "as_of"]), cols=cols, fmt={"unscored": "{:.2%}", **{t: "{:.1%}" for t in ("deep_subprime", "subprime", "near_prime", "prime", "prime_plus", "superprime")}}))
    if "error" in mix and mix["error"].notna().any():
        h.append("<p class='muted'>Not mapped: " + escape("; ".join(f"{r['trust']} ({r['error']})" for _, r in mix[mix['error'].notna()].iterrows())) + "</p>")

    n_shapes = shapes.dropna(subset=["relative_loss"])["shape_source"].nunique() if not shapes.empty else 0
    words = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}
    h.append(f"<h2>2. The {words.get(n_shapes, n_shapes)} loss-by-tier shapes</h2>")
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
        if stable:
            h.append("<p><b>The ranking is the same under every shape.</b> The ordering of trusts does not depend on which "
                     "loss curve is assumed.</p>")
        else:
            held = r.set_index("trust").nunique(axis=1) == 1
            h.append(f"<p><b>The ranking changes with the shape in the middle, not at the ends.</b> "
                     f"{escape(', '.join(sorted(held[held].index)))} keep{'s' if held.sum() == 1 else ''} the same rank under every "
                     f"shape; the others move. So the ordering of the trusts that hold their place is reported as a finding and "
                     f"the ordering of the rest is not.</p>")
        sy = _sign_by_year(pred)
        if not sy.empty:
            always = [t for t in sy.index if (sy.loc[t].dropna() == "+").all()]
            h.append("<h3>Since when: the sign of each year's mean residual under every shape</h3>")
            h.append("<p>+ means the trust lost more than its mix predicts under every shape that year, - less under every "
                     "shape, +/- that the shapes disagree." + (f" {escape(', '.join(always))} is above its prediction under every "
                     f"shape in every year since {int(sy.columns.min())}." if always else "") + "</p>")
            h.append(table(sy.reset_index()))

    bt_p, stress_p, regimes_p = results / "a3_by_trust.csv", results / "a3_stress.csv", results / "a3_regimes.csv"
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
        cols = ["trust", "months", "co_monthly", "entry", "progression", "conversion", "entry_ratio", "progression_ratio",
                "conversion_ratio", "entry_share_of_gap", "progression_share_of_gap", "conversion_share_of_gap"]
        cols = [c for c in cols if c in bt]
        h.append(table(bt, cols=cols, fmt={"co_monthly": "{:.3%}", "entry": "{:.2%}", "progression": "{:.3f}", "conversion": "{:.1%}",
                                          "entry_ratio": "{:.2f}", "progression_ratio": "{:.2f}", "conversion_ratio": "{:.2f}",
                                          "entry_share_of_gap": "{:+.2f}", "progression_share_of_gap": "{:+.2f}",
                                          "conversion_share_of_gap": "{:+.2f}"}))
        h.append("<p class='muted'>Each column is a geometric mean over the trust's months, so entry x progression x conversion is "
                 "co_monthly exactly and the three shares of the gap sum to one. Ratios and shares are against the trust with the "
                 "highest loss rate.</p>")
        h.append(_interpret_stages(bt))
        if stress_p.exists():
            sdf = pd.read_csv(stress_p)
            reg = pd.read_csv(regimes_p) if regimes_p.exists() else pd.DataFrame()
            if not sdf.empty:
                order = [p for p in STRESS_ORDER if p in set(sdf["period"])]
                best = str(bt.loc[bt["co_monthly"].idxmin(), "trust"])
                h.append("<h3>The direction test: does conversion fall when money is tight?</h3>")
                h.append("<p>If borrowers rank their debts, the ranking should bite hardest when money is tight, so a protected "
                         "card's 90-day-late accounts should be rescued more often then and its conversion ratio should "
                         "<i>fall</i>. This is the one place the two stories make opposite predictions about a direction, rather than "
                         "about a level. It needs months that really were tight, so they are picked by the trusts' own delinquency: "
                         "each trust's 30-plus share over its own average, averaged across trusts.</p>")
                if not reg.empty:
                    w = reg.pivot_table(index="trust", columns="regime", values="conversion_ratio").reindex(columns=["loose", "tight"])
                    w["move"] = w["tight"] - w["loose"]
                    h.append(table(w.reset_index(), fmt={"loose": "{:.2f}", "tight": "{:.2f}", "move": "{:+.2f}"}))
                d = cards_roll.direction_summary(sdf, reg, order)
                h.append("<p>" + " ".join(direction_sentences(d, best)) + "</p>")
                h.append("<h3>The same ratios in four named periods, with the delinquency in each</h3>")
                e = sdf.pivot_table(index="trust", columns="period", values="entry").reindex(columns=order).reset_index()
                h.append("<p>30-plus share of balances (geometric mean over the period's months):</p>")
                h.append(table(e, fmt={c: "{:.2%}" for c in e.columns if c != "trust"}))
                w = sdf.pivot_table(index="trust", columns="period", values="conversion_ratio").reindex(columns=order).reset_index()
                h.append("<p>Conversion ratio against the period's highest-loss trust:</p>")
                h.append(table(w, fmt={c: "{:.2f}" for c in w.columns if c != "trust"}))
    h.append("<h2>6. Panel regression</h2>")
    h.append("<p>Trust-month regression of the gross charge-off rate on tier shares with month fixed effects, then with trust fixed "
             "effects added, Driscoll-Kraay standard errors. Whether either can say anything depends on how the tier shares vary, "
             "and they come from prospectus snapshots: one per trust in this build.</p>")
    if not panel.empty and "status" in panel:
        st = panel.drop_duplicates("spec")[["spec", "status", "note"]]
        for r in st.itertuples():
            h.append(f"<p><b>{escape(r.spec)}: {escape(r.status)}.</b> {escape(str(r.note))}.</p>")
        ok = set(st.loc[st["status"] == "identified", "spec"])
        if ok:
            w = panel[panel["spec"].isin(ok)].pivot_table(index="term", columns="spec", values=["coef", "se"]).reset_index()
            w.columns = ["term"] + [f"{a}_{b}" for a, b in w.columns[1:]]
            h.append(table(w, fmt={c: "{:+.3f}" for c in w.columns if c != "term"}))
        else:
            h.append("<p>So this section has no coefficient to report. A score-mix gradient across card trusts needs more trusts "
                     "than tiers, or mixes that move within a trust over time; six trusts with one snapshot each give neither. "
                     "The shape-times-level residual (section 3) and the stage decomposition (section 5) do not depend on it. "
                     "The fitted numbers are in a2_panel.csv for anyone who wants to see what a saturated fit looks like.</p>")
        h.append("<p class='muted'>Until 2026-11-09 this section printed both columns as estimates, including trust-effect "
                 "coefficients in the billions from the unidentified specification.</p>")
    elif not panel.empty and "term" in panel:
        h.append("<p class='muted'>This build's a2_panel.csv predates the identification check; re-run "
                 "<code>absrisk analyze cards</code>.</p>")
    else:
        h.append("<p class='muted'>Not estimated in this build (see a2_panel.csv).</p>")

    h.append("<footer>Code and data: <a href='https://github.com/SamuelJWebber/abs-risk'>github.com/SamuelJWebber/abs-risk</a>. "
             "Row labels, bases and prospectus tables per trust are in design/scout-cards.md.</footer>")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page("abs-risk cards", "".join(h), current="cards.html"), encoding="utf-8")
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
