"""Run the Track A estimators and write results under data/results/cards/.

Inputs: data/cards_monthly.csv (A1), data/cards_composition.csv and crosswalks/fico_buckets.csv (A2),
data/loss_shape.csv and data/ccmr_level.csv (A3).
Outputs:
  mix_by_trust.csv        tier shares per trust and prospectus as-of date: the FICO table mapped through the committed
                          crosswalk, unscored balances dropped and the rest renormalised (`unscored` says how much)
  a1_predicted.csv        per trust-month and shape: actual, predicted, residual, mix_extrapolated
  a1_ranking.csv          mean residual per trust under each shape, and the rank; the ranking-stability check
  a1_straddle.csv         the same ranking with every straddling bucket put wholly in its lowest or its highest tier,
                          the sensitivity PLAN section 2 promised for the straddle rule
  a2_panel.csv            panel regression coefficients (month FE; month + trust FE), Driscoll-Kraay SEs
  a3_stages.csv           per trust-month: entry (30+), progression (90+/30+), conversion (charge-off/90+)
  a3_by_trust.csv         geometric means per trust, ratios to the highest-loss trust, shares of the log gap
  a3_stress.csv           the same in four named calendar periods, with each period's 30+ share
  a3_regimes.csv          the same in months of above- against below-median delinquency (the direction test)
Run: `uv run absrisk analyze cards [--series ccip]`.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from ..shape import TIERS, default_shapes, load_level, predict_chargeoff
from . import cards as cards_est
from . import cards_roll

STRESS_PERIODS = {
    "pre-covid 2019": ("2019-01-01", "2020-02-29"),
    "stimulus 2020-21": ("2020-04-01", "2021-12-31"),
    "normalising 2022-23H1": ("2022-01-01", "2023-06-30"),
    "squeeze 2023H2 on": ("2023-07-01", "2030-12-31"),
}


SCORE_MIN, SCORE_MAX = 300, 850
DEFAULT_CROSSWALK = "crosswalks/fico_buckets.csv"
WEIGHTS = [f"w_{t}" for t in TIERS]


def mix_by_trust(composition: pd.DataFrame, crosswalk: pd.DataFrame) -> pd.DataFrame:
    """Tier shares per (trust, as_of): the prospectus FICO table mapped through the committed crosswalk.

    `crosswalk` is crosswalks/fico_buckets.csv, which `absrisk cards composition` writes from the straddle rule
    (`composition.build_crosswalk`); the analysis reads it rather than re-deriving the mapping, so the file is the
    one place a bucket is assigned to tiers. Unscored buckets carry weight zero there: their balances are dropped,
    the scored ones renormalised, and the dropped share is reported in `unscored`. Receivables shares are used where
    the table gives them, else accounts. A FICO bucket without a crosswalk row raises; a table with no scored
    bucket at all gets an `error` row, because a tier mix cannot be made from nothing.
    """
    xw = crosswalk.copy()
    xw["bucket_label"] = xw["bucket_label"].astype(str)
    xw = xw.drop_duplicates(["trust", "bucket_label"]).set_index(["trust", "bucket_label"])
    rows = []
    fico = composition[composition["table"] == "fico"]
    for (trust, as_of), g in fico.groupby(["trust", "as_of"]):
        share_col = "share_receivables" if g["share_receivables"].notna().any() else "share_accounts"
        g = g.dropna(subset=[share_col])
        keys = list(zip(g["trust"], g["bucket_label"].astype(str)))
        missing = [k for k in keys if k not in xw.index]
        if missing:
            raise ValueError(f"crosswalk has no row for {missing}; rerun `absrisk cards composition`")
        w = xw.loc[keys, WEIGHTS].to_numpy(dtype=float)
        flags = sorted({f for v in xw.loc[keys, "flags"].fillna("") for f in str(v).split(",") if f}) if "flags" in xw else []
        share = g[share_col].to_numpy(dtype=float)
        scored = w.sum(axis=1) > 0
        mass = (share[:, None] * w).sum(axis=0)
        clamped = []
        for lo, hi in zip(g["bucket_lo"], g["bucket_hi"]):
            if pd.notna(lo) and int(lo) < SCORE_MIN:
                clamped.append(f"{int(lo)}->{SCORE_MIN}")
            if pd.notna(hi) and int(hi) > SCORE_MAX:
                clamped.append(f"{int(hi)}->{SCORE_MAX}")
        notes = sorted({str(n).split("; bucket: ")[0] for n in g["sample_note"].dropna()}) if "sample_note" in g else []
        base = {"trust": trust, "as_of": as_of, "basis": share_col, "clamped_edges": ";".join(clamped),
                "score_type": ",".join(sorted(g["score_type"].dropna().astype(str).unique())),
                "unscored": float(share[~scored].sum()), "mapping_flags": ",".join(flags), "sample_note": ";".join(notes)}
        if mass.sum() <= 0:
            rows.append({**base, "error": "no scored bucket: every balance is unscored"})
            continue
        rows.append({**base, **{t: float(v) for t, v in zip(TIERS, mass / mass.sum())}})
    return pd.DataFrame(rows)


def predicted(monthly: pd.DataFrame, mix: pd.DataFrame, shapes: pd.DataFrame, level: pd.DataFrame, series: str,
              rate_col: str = "gross_co_rate") -> pd.DataFrame:
    m = monthly.dropna(subset=[rate_col]).copy()
    m["period_end"] = pd.to_datetime(m["period_end"])
    years = sorted(level.loc[level["series"] == series, "year"].unique())
    out = []
    shape_names = [s for s in shapes["shape_source"].unique() if shapes.loc[shapes["shape_source"] == s, "relative_loss"].notna().all()]
    for trust, g in m.groupby("trust"):
        mx = mix[(mix["trust"] == trust) & mix.get("error", pd.Series(dtype=object)).isna()] if "error" in mix else mix[mix["trust"] == trust]
        if mx.empty:
            continue
        mx = mx.assign(as_of=pd.to_datetime(mx["as_of"])).sort_values("as_of")
        g = g.sort_values("period_end")
        merged = pd.merge_asof(g, mx, left_on="period_end", right_on="as_of", direction="backward", by="trust")
        extrap = merged["as_of"].isna()
        for t in TIERS:
            merged.loc[extrap, t] = float(mx.iloc[0][t])
        for _, r in merged.iterrows():
            year = int(r["period_end"].year)
            year_used = min(max(year, years[0]), years[-1])   # clamp to the CFPB level years
            mixd = {t: float(r[t]) for t in TIERS}
            for s in shape_names:
                pred = predict_chargeoff(mixd, year_used, s, series, shapes=shapes, level=level)
                out.append({"trust": trust, "period_end": r["period_end"].date(), "shape_source": s, "series": series,
                            "actual": float(r[rate_col]), "predicted": float(pred), "residual": float(r[rate_col]) - float(pred),
                            "mix_as_of": None if pd.isna(r["as_of"]) else r["as_of"].date(), "mix_extrapolated": bool(extrap.loc[r.name]),
                            "level_year": year_used, "level_year_clamped": year_used != year})
    return pd.DataFrame(out)


def _undated(summary: str) -> str:
    """statsmodels stamps each summary with the wall-clock date and time; blank them so a rebuild of unchanged inputs
    writes an unchanged file."""
    import re

    summary = re.sub(r"(Date:\s+)\w{3}, \d{2} \w{3} \d{4}", lambda m: m.group(1) + "-".ljust(16), summary)
    return re.sub(r"(Time:\s+)\d{2}:\d{2}:\d{2}", lambda m: m.group(1) + "-".rjust(8), summary)


STRADDLE_RULES = ("uniform", "lower", "upper")


def crosswalk_under(crosswalk: pd.DataFrame, rule: str) -> pd.DataFrame:
    """The crosswalk under another straddle rule. 'uniform' is the committed rule (a bucket spread over its tiers in
    proportion to the scores each holds); 'lower' puts every straddling bucket wholly in the lowest tier it touches,
    'upper' in the highest. The two bound any rule that keeps a bucket's balances inside the bucket's own edges."""
    if rule == "uniform":
        return crosswalk
    if rule not in STRADDLE_RULES:
        raise ValueError(f"unknown straddle rule {rule!r}")
    xw = crosswalk.copy()
    w = xw[WEIGHTS].to_numpy(dtype=float, copy=True)
    for i in range(len(w)):
        nz = np.flatnonzero(w[i] > 0)
        if len(nz) > 1:
            j = nz[0] if rule == "lower" else nz[-1]
            w[i] = 0.0
            w[i, j] = 1.0
    xw[WEIGHTS] = w
    return xw


def straddle_sensitivity(monthly: pd.DataFrame, composition: pd.DataFrame, crosswalk: pd.DataFrame,
                         shapes: pd.DataFrame, level: pd.DataFrame, series: str, rate_col: str) -> pd.DataFrame:
    """Mean residual and rank per trust and shape under each straddle rule."""
    out = []
    for rule in STRADDLE_RULES:
        mix = mix_by_trust(composition, crosswalk_under(crosswalk, rule))
        pred = predicted(monthly, mix, shapes, level, series, rate_col)
        if pred.empty:
            continue
        r = ranking(pred)
        r.insert(0, "straddle_rule", rule)
        out.append(r[["straddle_rule", "shape_source", "trust", "mean_residual", "rank"]])
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def ranking(pred: pd.DataFrame) -> pd.DataFrame:
    r = pred.groupby(["shape_source", "trust"]).agg(mean_residual=("residual", "mean"), mean_actual=("actual", "mean"),
                                                  mean_predicted=("predicted", "mean"), n_months=("residual", "size")).reset_index()
    r["rank"] = r.groupby("shape_source")["mean_residual"].rank(ascending=False, method="min").astype(int)
    return r.sort_values(["shape_source", "rank"])


def monthly_mix(mix: pd.DataFrame, monthly: pd.DataFrame) -> pd.DataFrame:
    """Tier shares per trust-month: step function of the prospectus as-of dates (backward fill), no interpolation."""
    m = monthly[["trust", "period_end"]].drop_duplicates().copy()
    m["period_end"] = pd.to_datetime(m["period_end"])
    out = []
    for trust, g in m.groupby("trust"):
        mx = mix[mix["trust"] == trust]
        if mx.empty or ("error" in mx and mx["error"].notna().all()):
            continue
        mx = mx.assign(as_of=pd.to_datetime(mx["as_of"])).sort_values("as_of")
        merged = pd.merge_asof(g.sort_values("period_end"), mx, left_on="period_end", right_on="as_of", direction="backward", by="trust")
        for t in TIERS:
            merged[t] = merged[t].fillna(float(mx.iloc[0][t]))
        out.append(merged[["trust", "period_end"] + list(TIERS)])
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=["trust", "period_end", *TIERS])


def main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="absrisk analyze cards")
    ap.add_argument("--monthly", default="data/cards_monthly.csv")
    ap.add_argument("--composition", default="data/cards_composition.csv")
    ap.add_argument("--crosswalk", default=DEFAULT_CROSSWALK, help="bucket-to-tier weights (absrisk cards composition)")
    ap.add_argument("--out", default="data/results/cards")
    ap.add_argument("--series", default="ccip", choices=["ccip", "ccp"])
    ap.add_argument("--rate", default="gross_co_rate")
    a = ap.parse_args(argv)
    warnings.filterwarnings("ignore")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    monthly = pd.read_csv(a.monthly)
    composition = pd.read_csv(a.composition)
    crosswalk = pd.read_csv(a.crosswalk)
    shapes, level = default_shapes(), load_level()
    mix = mix_by_trust(composition, crosswalk)
    mix.to_csv(out / "mix_by_trust.csv", index=False)
    pred = predicted(monthly, mix, shapes, level, a.series, a.rate)
    pred.to_csv(out / "a1_predicted.csv", index=False)
    if not pred.empty:
        ranking(pred).to_csv(out / "a1_ranking.csv", index=False)
        straddle_sensitivity(monthly, composition, crosswalk, shapes, level, a.series, a.rate).to_csv(
            out / "a1_straddle.csv", index=False)
    # A3: the loss rate factors exactly into entry x progression x conversion; where a trust's advantage sits
    # separates "its accounts rarely get into trouble" from "its accounts survive trouble".
    try:
        st = cards_roll.stages(monthly, a.rate)
        st.to_csv(out / "a3_stages.csv", index=False)
        bt = cards_roll.by_trust(st)
        bt.to_csv(out / "a3_by_trust.csv", index=False)
        cards_roll.stress_test(st, STRESS_PERIODS).to_csv(out / "a3_stress.csv", index=False)
        cards_roll.regimes(st).to_csv(out / "a3_regimes.csv", index=False)
    except Exception as e:  # noqa: BLE001
        (out / "a3_stages.csv").write_text(f"not computed: {e}\n")

    mm = monthly_mix(mix, monthly)
    try:
        fits, tidy = cards_est.panel_regression(monthly.assign(period_end=pd.to_datetime(monthly["period_end"])), mm, rate_col=a.rate)
        # ten significant digits: the saturated fit is exact up to the solver, and solver noise in the last digits
        # should not turn an unchanged rebuild into a diff
        tidy.to_csv(out / "a2_panel.csv", index=False, float_format="%.10g")
        (out / "a2_panel_summary.txt").write_text(_undated("\n\n".join(f"== {k} ==\n{v.summary()}" for k, v in fits.items())))
    except Exception as e:  # noqa: BLE001
        (out / "a2_panel.csv").write_text(f"not estimated: {e}\n")
    print(f"wrote {out}: {len(pred)} trust-month-shape rows, {mix['trust'].nunique() if not mix.empty else 0} trusts with a mix", file=sys.stderr)
    return 0
