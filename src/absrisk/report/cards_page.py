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

SCOPE = ("Trust pools are selected, seasoned accounts, not the issuer's book. Every trust is compared on its net "
         "charge-off rate, losses after recoveries, because that is the only rate all six print: Citi's monthly report "
         "gives no gross rate. Until November 2026 this page labelled Citi's net rate gross and set it against the "
         "other five trusts' gross rates. Annualisation bases differ by trust and are kept as reported. "
         "The residual is actual minus what the pool's score mix predicts under a stated "
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


def _straddle_note(results: Path) -> str:
    """The straddle-rule sensitivity PLAN section 2 promised, read from a1_straddle.csv."""
    p = results / "a1_straddle.csv"
    if not p.exists():
        return ""
    s = pd.read_csv(p)
    if s.empty or "uniform" not in set(s["straddle_rule"]):
        return ""
    base = s[s["straddle_rule"] == "uniform"].set_index(["shape_source", "trust"])
    lines = []
    moved_rank = set()
    worst = 0.0
    for rule in ("lower", "upper"):
        alt = s[s["straddle_rule"] == rule].set_index(["shape_source", "trust"])
        if alt.empty:
            continue
        d = (alt["mean_residual"] - base.loc[alt.index, "mean_residual"]).abs()
        worst = max(worst, float(d.max()))
        moved_rank |= {t for (sh, t), rk in alt["rank"].items() if rk != base.loc[(sh, t), "rank"]}
    every = s.groupby("trust")["rank"].nunique()
    fixed = sorted(every[every == 1].index)
    lines.append("<p><b>The straddle rule.</b> Buckets that straddle a tier edge are spread uniformly in score. Putting every "
                 "such bucket wholly in its lowest tier, or wholly in its highest, bounds any rule that keeps a bucket's balances "
                 f"inside its own edges. Under those bounds the mean residuals move by up to {worst * 100:.2f} percentage points, "
                 "most under the steep consumer-level shapes, and "
                 + (f"the rank changes for {escape(', '.join(sorted(moved_rank)))} under at least one shape"
                    if moved_rank else "no trust's rank changes under any shape")
                 + (f"; {escape(', '.join(fixed))} keep{'s' if len(fixed) == 1 else ''} the same rank under every shape and every "
                    f"rule." if fixed else "; no trust keeps one rank under every shape and every rule.")
                 + " So the straddle rule is a second assumption, beside the loss curve, that moves the size of a residual; "
                   "the sign and rank statements above are made under the uniform rule. Every rank is in a1_straddle.csv.</p>")
    return "".join(lines)


# Citi's gross charge-offs over its net losses by year, from the loss experience table of its prospectus
# 0001193125-25-144490 (2022, 2023, 2024 and the first quarter of 2025: 1.47, 1.27, 1.21, 1.25). tests/test_citi_net.py
# recomputes the 2024 figure from the committed copy of that prospectus.
CITI_GROSS_OVER_NET = (1.21, 1.47)
# Bounds used for a trust with no gross rate: its net rate itself, which is a floor in every month because recoveries
# cannot be negative, and the highest yearly ratio the prospectus reports. The prospectus covers 2022 to early 2025
# only, so the upper bound is an assumption in other years and the floor is not.
GROSS_BOUNDS = (1.0, CITI_GROSS_OVER_NET[1])


def _basis_note(results: Path) -> str:
    """Net trust rates against a gross industry level: how far that sets every residual low (REVIEW.md abs-B-1)."""
    p = results / "a1_basis.csv"
    if not p.exists():
        return ""
    b = pd.read_csv(p)
    both = b.dropna(subset=["net_over_gross"])
    none = sorted(b.loc[b["months_gross"] == 0, "trust"])
    if both.empty:
        return ""
    line = ("<p><b>Net against a gross benchmark.</b> The CFPB industry rate behind every prediction counts balances charged "
            "off before recoveries, and the trusts are measured after them. At the "
            f"{len(both)} trusts that print both rates, net is {both['net_over_gross'].min():.0%} to "
            f"{both['net_over_gross'].max():.0%} of gross, a gap of {both['gross_minus_net'].min() * 100:.2f} to "
            f"{both['gross_minus_net'].max() * 100:.2f} percentage points. So each residual here sits lower than a "
            "gross-against-gross one by about that much. The ranking compares like with like. A positive residual is safe; a "
            "negative one smaller than that gap is not a finding.")
    if none:
        line += (f" {escape(', '.join(none))} print{'s' if len(none) == 1 else ''} no gross rate at all: its prospectus puts gross "
                 f"charge-offs at {CITI_GROSS_OVER_NET[0]:.2f} to {CITI_GROSS_OVER_NET[1]:.2f} times net losses by year, 2022 to "
                 "early 2025." if none == ["citi"] else f" {escape(', '.join(none))} print no gross rate at all.")
    return line + "</p>"


def _year_fraction(t: pd.Series) -> list[float]:
    """A month-end as a fraction of the calendar: 2019-01-31 is 2019 + 1/12, so whole years fall on round ticks."""
    t = pd.to_datetime(t)
    return (t.dt.year + (t.dt.month - 1) / 12 + t.dt.day / t.dt.days_in_month / 12).round(4).tolist()


def _gross_bounds(mean_net_residual, mean_net_actual, mean_gross_residual):
    """The residual against the CFPB level like for like, that is on the gross rate: the trust's own gross residual
    where it prints a gross rate (both bounds equal), else its net residual (a floor: gross is never below net) and
    its net residual plus its net rate times the highest gross-over-net excess its prospectus reports
    (`GROSS_BOUNDS`). Works on arrays."""
    has = mean_gross_residual == mean_gross_residual
    lo = np.where(has, mean_gross_residual, mean_net_residual + mean_net_actual * (GROSS_BOUNDS[0] - 1))
    hi = np.where(has, mean_gross_residual, mean_net_residual + mean_net_actual * (GROSS_BOUNDS[1] - 1))
    return lo, hi


def _gross_residuals(rank: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(low, high) mean residual on the gross basis per trust and shape, from a1_ranking.csv."""
    r = rank.copy()
    if "mean_residual_gross" not in r:
        r["mean_residual_gross"] = np.nan
    lo, hi = _gross_bounds(r["mean_residual"].to_numpy(float), r["mean_actual"].to_numpy(float),
                           r["mean_residual_gross"].to_numpy(float))
    r["lo"], r["hi"] = lo, hi
    return (r.pivot_table(index="trust", columns="shape_source", values="lo"),
            r.pivot_table(index="trust", columns="shape_source", values="hi"))


def _sign_by_year(pred: pd.DataFrame) -> pd.DataFrame:
    """Per trust and calendar year: '+' if the mean gross-basis residual is positive under every shape, '-' if negative
    under every shape, '+/-' if the shapes disagree (or, for a trust with no gross rate, if the low and the high bound
    on it disagree). This is the page's 'since when'."""
    p = pred.assign(year=pd.to_datetime(pred["period_end"]).dt.year)
    if "residual_gross" not in p:
        p["residual_gross"] = np.nan
    g = p.groupby(["trust", "year", "shape_source"]).agg(
        net=("residual", "mean"), actual=("actual", "mean"),
        gross=("residual_gross", lambda x: x.mean() if x.notna().all() else np.nan))
    lo, hi = _gross_bounds(g["net"].to_numpy(float), g["actual"].to_numpy(float), g["gross"].to_numpy(float))
    lo = pd.Series(lo, index=g.index).unstack("shape_source")
    hi = pd.Series(hi, index=g.index).unstack("shape_source")
    pos, neg = (lo > 0).all(axis=1) & (hi > 0).all(axis=1), (lo < 0).all(axis=1) & (hi < 0).all(axis=1)
    sign = pd.Series(np.where(pos, "+", np.where(neg, "-", "+/-")), index=lo.index)
    return sign.unstack("year")


# A statement about one trust that rests on how its pool is calibrated, beyond the loss curve and the straddle rule.
# Review round 2 (REVIEW.md R2-2) measured this one on data through September 2026.
PRODUCT_NOTE = {
    "synchrony": ("One more assumption sits under that sign, and the curves do not cover it: synchrony's pool is set against "
                  "the general-purpose industry level like the other five, though about a quarter of its receivables are "
                  "private label cards, which charge off at roughly twice the general-purpose rate industry-wide. A review "
                  "on 2026-11-09 found the sign survives at that blend and reverses if the whole pool is treated as private "
                  "label."),
}


def ends(cells: pd.DataFrame) -> dict:
    """Who sits at the top and the bottom of the ranking across `cells`, and how often. A cell is one loss curve under
    one straddle rule (a1_straddle.csv), or one loss curve when the frame has no straddle_rule column (a1_ranking.csv).
    Keys: n (cells), n_trusts, top, top_n, bottom, bottom_n, pos (cells with a positive residual, per trust), moved
    (trusts whose rank is not the same in every cell), res_min, res_max (per trust)."""
    keys = [k for k in ("straddle_rule", "shape_source") if k in cells]
    n = int(cells.groupby(keys).ngroups)
    nt = int(cells["trust"].nunique())
    first = cells[cells["rank"] == 1]["trust"].value_counts()
    last = cells[cells["rank"] == nt]["trust"].value_counts()
    g = cells.groupby("trust")
    return {"n": n, "n_trusts": nt, "top": str(first.idxmax()), "top_n": int(first.max()),
            "bottom": str(last.idxmax()), "bottom_n": int(last.max()),
            "pos": g["mean_residual"].apply(lambda x: int((x > 0).sum())),
            "moved": sorted(g["rank"].nunique()[lambda x: x > 1].index),
            "res_min": g["mean_residual"].min(), "res_max": g["mean_residual"].max(),
            "words": "combinations of loss curve and straddle rule" if "straddle_rule" in cells else "loss curves"}


def ends_sentence(e: dict) -> str:
    """The headline about the ends of the ranking, saying 'every' only where the count is every cell."""
    n = e["n"]
    if e["top_n"] == n and e["bottom_n"] == n:
        lead = "The ends of the ranking hold under every assumption; the middle does not."
        close = "So the ordering of the extremes is a finding and the ordering of the middle is not."
    elif e["top_n"] > n / 2 and e["bottom_n"] > n / 2:
        lead = "The ends of the ranking hold under most assumptions, not under all of them."
        close = "So the two ends are close to a finding, not quite one, and the ordering between them is not a finding at all."
    else:
        lead = "Neither end of the ranking holds across the assumptions."
        close = "So no part of the ordering is a finding."

    def count(k):
        return f"all {n}" if k == n else f"{k}"
    t, b = e["top"], e["bottom"]
    body = (f"Across the {n} {e['words']} (section 4), {escape(t)} has the largest residual in {count(e['top_n'])} and "
            f"{escape(b)} the smallest in {count(e['bottom_n'])}; {len(e['moved'])} of {e['n_trusts']} trusts change rank "
            f"somewhere among them.")
    if e["pos"].get(t, 0) == n:
        body += (f" {escape(t)} loses more than its own score mix predicts in all {n}: its residual is "
                 f"{e['res_min'][t]:+.2%} to {e['res_max'][t]:+.2%} after recoveries, so it is positive before them too.")
    out = f"<b>{lead}</b> {body} {close}"
    if t in PRODUCT_NOTE and e["pos"].get(t, 0) == n:
        out += " " + PRODUCT_NOTE[t]
    return out


def _headlines(rank: pd.DataFrame, pred: pd.DataFrame, mix: pd.DataFrame, straddle: pd.DataFrame | None = None) -> list[str]:
    """Sentences computed from the tables, so the page cannot claim more than the numbers carry."""
    out = []
    if rank.empty:
        return out
    r = rank.pivot_table(index="trust", columns="shape_source", values="rank")
    res = rank.pivot_table(index="trust", columns="shape_source", values="mean_residual")
    glo, ghi = _gross_residuals(rank)          # the level against the CFPB's gross rate, like for like
    n_shapes = r.shape[1]
    cells = straddle if straddle is not None and not straddle.empty and "uniform" in set(straddle["straddle_rule"]) else rank
    out.append(ends_sentence(ends(cells)))
    # signs are read on the gross rate, because the CFPB level each prediction is calibrated to is gross
    keeps = ((glo > 0).all(axis=1) & (ghi > 0).all(axis=1)) | ((glo < 0).all(axis=1) & (ghi < 0).all(axis=1))
    flip = glo[~keeps]
    same = glo[keeps]
    if not flip.empty:
        names = escape(", ".join(sorted(flip.index)))
        line = (f"<b>The size of the gap is not identified.</b> Measured like for like against the CFPB's gross industry rate, "
                f"for {len(flip)} of {len(res)} trusts ({names}) the residual changes sign "
                f"with the assumed loss curve: the same trust looks worse than its mix under the consumer-level shapes and better under "
                f"the card-level ones. The two families disagree by about five times on how much more a deep subprime account loses than "
                f"a prime one, and that choice moves every level.")
        if not same.empty:
            keep = ", ".join(f"{t} ({glo.loc[t].min():+.2%} to {ghi.loc[t].max():+.2%})" for t in sorted(same.index))
            one = len(same) == 1
            line += (f" Only {escape(keep)} keep{'s' if one else ''} the same sign under all {n_shapes}, so "
                     f"{'it is the one trust' if one else 'they are the only trusts'} whose sign does not depend on the loss curve.")
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


def _interpret_stages(bt: pd.DataFrame, ceil: pd.DataFrame | None = None) -> str:
    """Read the entry/progression/conversion split back as sentences, and say what conversion cannot carry."""
    d = bt.dropna(subset=["entry_share_of_gap"])
    if d.empty:
        return ""
    base = bt.loc[bt["co_monthly"].idxmax(), "trust"]
    best = d.loc[d["co_monthly"].idxmin()]
    prog = f"{bt['progression'].min():.2f} to {bt['progression'].max():.2f}" if "progression" in bt else ""
    parts = [f"<p><b>The low-loss trusts have far fewer late balances. What happens to an account once it is late, these "
             f"filings cannot say.</b> {best['trust']} loses {best['co_monthly_ratio']:.2f} times what {base} loses each month, "
             f"and its 30-plus share is {best['entry_ratio']:.2f} times {base}'s. Entry accounts for "
             f"{best['entry_share_of_gap']:.0%} of the gap, progression for {best['progression_share_of_gap']:+.0%} and "
             f"conversion for {best['conversion_share_of_gap']:+.0%}."
             + (f" Progression barely differs between trusts ({prog} of 30-day-late balances are 90 days late)." if prog else "")
             + " Fewer late balances is what selection predicts. It is also what a card that people pay first would show, "
               "because paying it first keeps it from falling behind. So the entry gap is large and real, and it does not "
               "separate the two stories.</p>"]
    parts.append(_ceiling_paragraph(ceil))
    return "".join(parts)


def _ceiling_paragraph(ceil: pd.DataFrame | None) -> str:
    """Why conversion is not the fate of late accounts, from a3_ceiling.csv (REVIEW.md abs-A-2, abs-B-2)."""
    lead = ("<p><b>Conversion is not the fate of late accounts.</b> It divides every charge-off in the month by the balances "
            "then 90 days late, and a charge-off need not have been among them. The prospectuses state the policy: an account "
            "is written off at about 180 days late, or sooner when the cardholder is bankrupt or has died (American Express, "
            "Citi, Chase and Synchrony each say so in the prospectuses used here).")
    tail = (" So conversion mixes losses that aged through delinquency with losses that did not, in a proportion no monthly "
            "report gives, and it cannot show whether late accounts are rescued more or less often at one trust than at "
            "another. Until November 2026 this page read a conversion ratio above one as the opposite of protection. That "
            "reading is withdrawn.</p>")
    if ceil is None or ceil.empty:
        return lead + tail
    c = ceil.set_index("trust")
    one = c[c["bucket_months"] == 1].sort_values("chargeoff_over_one_month", ascending=False)
    mid = " The monthly reports show how often the sooner route is taken."
    if not one.empty and one.iloc[0]["chargeoff_over_one_month"] > 1:
        t, r = one.index[0], one.iloc[0]
        mid += (f" An account can reach the 180-day write-off only from the last delinquency bucket of the month before, yet "
                f"{escape(str(t))} wrote off {r['chargeoff_over_one_month']:.2f} times the dollars that were in that bucket a "
                f"month earlier, over {int(r['months'])} months, and more than the bucket held in "
                f"{r['share_months_above_one']:.0%} of them. At least {r['min_share_not_aged']:.0%} of its charge-offs "
                f"therefore never aged through late delinquency.")
        rest = [f"{escape(str(k))} {v['min_share_not_aged']:.0%}" for k, v in one.iloc[1:].iterrows()
                if v["min_share_not_aged"] > 0]
        if rest:
            mid += f" The same lower bound elsewhere: {', '.join(rest)}."
    two = c[c["bucket_months"] > 1]
    for t, r in two.iterrows():
        mid += (f" {escape(str(t))} prints its last {int(r['bucket_months'])} monthly cohorts as one bucket "
                f"({escape(str(r['bucket']))} days): its charge-offs were {r['chargeoff_over_bucket']:.2f} of the whole bucket, "
                f"which is {r['chargeoff_over_one_month']:.2f} times one cohort if the cohorts are equal, a lower bound of "
                f"{r['min_share_not_aged']:.0%}.")
    net = sorted(c.index[c["basis"] == "net"])
    mid += (" The bucket counts finance charges and fees and the charge-off is principal only, so each ratio understates."
            + (f" {escape(', '.join(net))} is on its net rate, which understates further." if net else ""))
    cols = ["trust", "basis", "bucket", "months", "chargeoff_over_bucket", "chargeoff_over_one_month",
            "share_months_above_one", "min_share_not_aged"]
    tab = table(ceil.sort_values("chargeoff_over_one_month", ascending=False), cols=cols,
                fmt={"chargeoff_over_bucket": "{:.2f}", "chargeoff_over_one_month": "{:.2f}",
                     "share_months_above_one": "{:.0%}", "min_share_not_aged": "{:.0%}"})
    return lead + mid + "</p>" + tab + "<p>" + tail[1:]


def _names(xs, moves: dict | None = None) -> str:
    """'a (-0.10), b (+0.02) and c', or 'no trust'."""
    if not xs:
        return "no trust"
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
    weak = ("Conversion divides a flow by a stock that builds ahead of the charge-offs, which lowers it whenever delinquency is "
            "rising, whoever is paid first, and it moves with the share of charge-offs that never aged through late "
            "delinquency. So this test is weak evidence in either direction and settles nothing on its own.")
    if v == "mixed":
        out.append("<b>So the direction test is mixed.</b> The moves either way are small. " + weak)
    elif v == "priority":
        out.append("<b>Every trust's conversion ratio fell in the tight months,</b> the sign prioritisation predicts. " + weak)
    else:
        out.append("<b>No trust's conversion ratio fell in the tight months,</b> which is not the sign prioritisation "
                   "predicts. " + weak)
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
    straddle_p = results / "a1_straddle.csv"
    straddle = pd.read_csv(straddle_p) if straddle_p.exists() else None
    for line in _headlines(rank, pred, mix, straddle):
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
        series = []
        a = g[g["shape_source"] == g["shape_source"].iloc[0]].sort_values("t")
        # the text colour, so the actual line shows in both themes (REVIEW.md R2-5)
        series.append({"name": "actual", "x": _year_fraction(a["t"]), "y": a["actual"].tolist(), "color": "fg"})
        for s, gs in g.groupby("shape_source"):
            gs = gs.sort_values("t")
            series.append({"name": f"predicted, {s}", "x": _year_fraction(gs["t"]), "y": gs["predicted"].tolist()})
        h.append(line_chart(series, y_label="annualised net charge-off", x_label="year", title=trust,
                            x_fmt="{:.0f}"))
    h.append("</div>")

    h.append("<h2>4. Ranking by residual, under each shape</h2>")
    if not rank.empty:
        w = rank.pivot_table(index="trust", columns="shape_source", values="mean_residual").reset_index()
        r = rank.pivot_table(index="trust", columns="shape_source", values="rank").reset_index()
        h.append(_basis_note(results))
        h.append("<h3>Mean residual (actual net minus predicted), percentage points of annualised charge-off</h3>")
        h.append(table(w, fmt={c: "{:+.2%}" for c in w.columns if c != "trust"}))
        glo, ghi = _gross_residuals(rank)
        gt = []
        for t in glo.index:
            if np.allclose(glo.loc[t], ghi.loc[t]):
                gt.append({"trust": t, **glo.loc[t].to_dict()})
            else:
                gt.append({"trust": f"{t}, at its net rate (a floor)", **glo.loc[t].to_dict()})
                gt.append({"trust": f"{t}, gross at {GROSS_BOUNDS[1]:.2f} times net", **ghi.loc[t].to_dict()})
        gt = pd.DataFrame(gt)
        h.append("<h3>The same on the gross rate, like for like with the CFPB level</h3>")
        h.append("<p>The trust's own gross rate minus the prediction, for the trusts that print one. A trust that prints only a "
                 "net rate is shown twice: at that net rate, which is a floor because gross is never below net, and at the "
                 "highest yearly gross-over-net ratio its prospectus reports. Every statement about a sign on this page is "
                 "read from this table.</p>")
        h.append(table(gt, fmt={c: "{:+.2%}" for c in gt.columns if c != "trust"}))
        h.append("<h3>Rank (1 = largest positive residual)</h3>")
        h.append(table(r))
        stable = (r.drop(columns="trust").nunique(axis=1) == 1).all()
        if stable:
            h.append("<p><b>The ranking is the same under every shape.</b> The ordering of trusts does not depend on which "
                     "loss curve is assumed.</p>")
        else:
            held = r.set_index("trust").nunique(axis=1) == 1
            h.append(f"<p><b>The ranking changes with the shape.</b> "
                     + (f"Under the uniform straddle rule, {escape(', '.join(sorted(held[held].index)))} "
                        f"keep{'s' if held.sum() == 1 else ''} the same rank under every shape and the others move. The next "
                        f"paragraph widens the rule, and the headline counts both.</p>"
                        if held.any() else "No trust keeps one rank under every shape.</p>"))
        h.append(_straddle_note(results))
        sy = _sign_by_year(pred)
        if not sy.empty:
            always = [t for t in sy.index if (sy.loc[t].dropna() == "+").all()]
            h.append("<h3>Since when: the sign of each year's mean residual under every shape</h3>")
            h.append("<p>Read on the gross rate, like for like with the CFPB level. + means the trust lost more than its mix "
                     "predicts under every shape that year, - less under every shape, +/- that the shapes disagree, or for a "
                     "trust with no gross rate that the low and high bounds on it do." + (f" {escape(', '.join(always))} is above its prediction under every "
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
                 "<b>progression</b> (90+ / 30+) &nbsp;x&nbsp; <b>conversion</b> (monthly net charge-off / 90+)</p>")
        h.append("<p>The split is exact arithmetic. What it can carry is narrower than this page used to claim: <b>entry</b> shows "
                 "how much of a trust's advantage is fewer late balances, and <b>conversion</b> does not show what becomes of an "
                 "account once it is late, for the reason given under the table.</p>")
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
        ceil_p = results / "a3_ceiling.csv"
        h.append(_interpret_stages(bt, pd.read_csv(ceil_p) if ceil_p.exists() else None))
        if stress_p.exists():
            sdf = pd.read_csv(stress_p)
            reg = pd.read_csv(regimes_p) if regimes_p.exists() else pd.DataFrame()
            if not sdf.empty:
                order = [p for p in STRESS_ORDER if p in set(sdf["period"])]
                best = str(bt.loc[bt["co_monthly"].idxmin(), "trust"])
                h.append("<h3>The direction test: does conversion fall when money is tight?</h3>")
                h.append("<p>If borrowers rank their debts, the ranking should bite hardest when money is tight, so a protected "
                         "card's late accounts should be rescued more often then and its conversion ratio should <i>fall</i>. "
                         "It needs months that really were tight, so they are picked by the trusts' own delinquency: each "
                         "trust's 30-plus share over its own average, averaged across trusts. Conversion is a blunt instrument "
                         "for this, as the paragraph above says, so read the result as a description.</p>")
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
    h.append("<p>Trust-month regression of the net charge-off rate on tier shares with month fixed effects, then with trust fixed "
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
