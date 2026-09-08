"""Run the Track A estimators and write results under data/results/cards/.

Inputs: data/cards_monthly.csv (A1), data/cards_composition.csv (A2), data/loss_shape.csv and data/ccmr_level.csv (A3).
Outputs:
  mix_by_trust.csv        tier shares per trust and prospectus as-of date (from the FICO table via the straddle rule)
  a1_predicted.csv        per trust-month and shape: actual, predicted, residual, mix_extrapolated
  a1_ranking.csv          mean residual per trust under each shape, and the rank; the ranking-stability check
  a2_panel.csv            panel regression coefficients (month FE; month + trust FE), Driscoll-Kraay SEs
Run: `uv run absrisk analyze cards [--series ccip]`.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from ..shape import TIERS, default_shapes, load_level, predict_chargeoff, tiers_from_buckets
from . import cards as cards_est


SCORE_MIN, SCORE_MAX = 300, 850


def mix_by_trust(composition: pd.DataFrame) -> pd.DataFrame:
    """Tier shares per (trust, as_of) from the FICO table. Uses receivables shares, else accounts.

    Bucket edges outside the FICO range are clamped into it and the clamp is recorded: Citi's table opens a
    bucket at 1 rather than at the bottom of the scale, and open-ended top buckets vary. Clamping only moves
    an edge onto the scale; it never moves a boundary between two tiers.
    """
    rows = []
    fico = composition[composition["table"] == "fico"]
    for (trust, as_of), g in fico.groupby(["trust", "as_of"]):
        share_col = "share_receivables" if g["share_receivables"].notna().any() else "share_accounts"
        g = g.dropna(subset=[share_col])
        buckets, clamped = [], []
        for _, r in g.iterrows():
            lo = None if pd.isna(r["bucket_lo"]) else int(r["bucket_lo"])
            hi = None if pd.isna(r["bucket_hi"]) else int(r["bucket_hi"])
            if lo is not None and lo < SCORE_MIN:
                clamped.append(f"{lo}->{SCORE_MIN}")
                lo = SCORE_MIN
            if hi is not None and hi > SCORE_MAX:
                clamped.append(f"{hi}->{SCORE_MAX}")
                hi = SCORE_MAX
            buckets.append((lo, hi, float(r[share_col])))
        try:
            mix = tiers_from_buckets(buckets)
        except Exception as e:  # noqa: BLE001
            rows.append({"trust": trust, "as_of": as_of, "error": str(e)[:120]})
            continue
        rows.append({"trust": trust, "as_of": as_of, "basis": share_col, "clamped_edges": ";".join(clamped),
                     "score_type": ",".join(sorted(g["score_type"].dropna().astype(str).unique())),
                     "sample_note": ";".join(sorted(g["sample_note"].dropna().astype(str).unique())) if "sample_note" in g else "",
                     **{t: mix.get(t, 0.0) for t in TIERS}})
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
    ap.add_argument("--out", default="data/results/cards")
    ap.add_argument("--series", default="ccip", choices=["ccip", "ccp"])
    ap.add_argument("--rate", default="gross_co_rate")
    a = ap.parse_args(argv)
    warnings.filterwarnings("ignore")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    monthly = pd.read_csv(a.monthly)
    composition = pd.read_csv(a.composition)
    shapes, level = default_shapes(), load_level()
    mix = mix_by_trust(composition)
    mix.to_csv(out / "mix_by_trust.csv", index=False)
    pred = predicted(monthly, mix, shapes, level, a.series, a.rate)
    pred.to_csv(out / "a1_predicted.csv", index=False)
    if not pred.empty:
        ranking(pred).to_csv(out / "a1_ranking.csv", index=False)
    mm = monthly_mix(mix, monthly)
    try:
        fits, tidy = cards_est.panel_regression(monthly.assign(period_end=pd.to_datetime(monthly["period_end"])), mm, rate_col=a.rate)
        tidy.to_csv(out / "a2_panel.csv", index=False)
        (out / "a2_panel_summary.txt").write_text("\n\n".join(f"== {k} ==\n{v.summary()}" for k, v in fits.items()))
    except Exception as e:  # noqa: BLE001
        (out / "a2_panel.csv").write_text(f"not estimated: {e}\n")
    print(f"wrote {out}: {len(pred)} trust-month-shape rows, {mix['trust'].nunique() if not mix.empty else 0} trusts with a mix", file=sys.stderr)
    return 0
