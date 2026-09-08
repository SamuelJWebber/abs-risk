"""Run the Track B estimators over every loans table under data/autos/ and write results under data/results/autos/.

Outputs (all CSV unless noted):
  loans_summary.csv          per deal: N, first/last period, exit_type shares, score coverage, PTI unit rule
  b1_cif.csv                 cumulative incidence by lender x score bucket x age (AJ and KM), with N
  b1_at_12.csv, b1_at_24.csv the 12- and 24-month cuts
  b2_hazard_ratios.csv       odds ratios by factor level for charge-off and prepay, with and without controls
  b2_fit.json                fit metadata (cells, exposure, columns)
  b3_cutoffs.csv             candidate pricing cutoffs per lender (APR and amount jumps)
  b3_rd.csv                  density test, first stage and outcome RD at each flagged cutoff
Run: `uv run absrisk analyze autos [--in data/autos] [--out data/results/autos]`.
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from . import hazard, rd, survival

# securitization floors and cliffs that are selection, not pricing (design/scout-autos.md §6, §11)
KNOWN_SELECTION_CUTOFFS = {"carmax": {650}, "toyota": {620}, "exeter": {640}, "americredit": {640}}
MIN_COHORT_MONTHS = 12


def load_loans(in_dir: Path) -> pd.DataFrame:
    frames = []
    for p in sorted(in_dir.glob("*.parquet")):
        df = pd.read_parquet(p)
        df["deal"] = df.get("deal", p.stem)
        frames.append(df)
    if not frames:
        raise SystemExit(f"no loans parquet under {in_dir}")
    loans = pd.concat(frames, ignore_index=True)
    if "commercial" in loans:
        loans = loans[~loans["commercial"].fillna(False).astype(bool)]
    return loans.reset_index(drop=True)


def summarize(loans: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for deal, g in loans.groupby("deal"):
        et = g["exit_type"].value_counts(normalize=True)
        rows.append({
            "deal": deal, "lender": g["lender"].iloc[0], "n_loans": len(g),
            "first_period": str(g["first_period"].min()), "last_period": str(g["last_period"].max()),
            "months_observed_median": float(g["months_observed"].median()),
            "share_chargeoff": float(et.get("chargeoff", 0)), "share_prepay": float(et.get("prepay", 0)),
            "share_repurchase": float(et.get("repurchase", 0)), "share_absent": float(et.get("absent", 0)),
            "share_censored": float(et.get("censored", 0)),
            "score_missing_share": float(g["score"].isna().mean()), "score_median": float(g["score"].median()),
            "score_type": ",".join(sorted(g["score_type"].dropna().astype(str).unique())[:3]),
            "pti_median": float(g["pti"].median()) if "pti" in g else np.nan,
            "apr_median": float(g["orig_apr"].median()), "amount_median": float(g["orig_amount"].median()),
        })
    return pd.DataFrame(rows)


def run_b1(loans: pd.DataFrame, out: Path):
    df = loans.copy()
    df["score_b"] = survival.score_bucket(df["score"])
    cif = survival.cumulative_incidence(df, by=["lender", "score_b"], horizon=36)
    cif.to_csv(out / "b1_cif.csv", index=False)
    survival.incidence_at(cif, ["lender", "score_b"], 12).to_csv(out / "b1_at_12.csv", index=False)
    survival.incidence_at(cif, ["lender", "score_b"], 24).to_csv(out / "b1_at_24.csv", index=False)
    by_lender = survival.cumulative_incidence(df, by=["lender"], horizon=36)
    by_lender.to_csv(out / "b1_cif_by_lender.csv", index=False)
    return cif


def run_b2(loans: pd.DataFrame, out: Path):
    df = hazard.add_design_columns(loans)
    keep = ["deal", "lender", "score_b", "cohort_q", "amount_q", "pti_q", "ltv_q", "apr_q"]
    keep = [k for k in keep if k in df]
    lm = hazard.expand_loan_months(df, keep=keep)
    specs = {
        "raw": ["age_b", "lender"],
        "score_only": ["age_b", "score_b", "lender"],
        "full": ["age_b", "score_b", "lender", "cohort_q"] + [k for k in ("amount_q", "pti_q", "ltv_q", "apr_q") if k in df],
    }
    rows, meta = [], {}
    for name, factors in specs.items():
        cells = hazard.aggregate_cells(lm, cells=[f for f in factors if f != "age_b"] + (["deal"] if "deal" not in factors else []))
        res = hazard.fit_hazards(cells, factors=factors, cluster="deal")
        meta[name] = res["design_info"]
        for event in ("chargeoff", "prepay"):
            for f in factors:
                hr = hazard.hazard_ratios(res[event], f)
                hr.insert(0, "factor", f)
                hr.insert(0, "event", event)
                hr.insert(0, "spec", name)
                rows.append(hr)
    pd.concat(rows, ignore_index=True).to_csv(out / "b2_hazard_ratios.csv", index=False)
    (out / "b2_fit.json").write_text(json.dumps(meta, indent=1, default=str))


def run_b3(loans: pd.DataFrame, out: Path):
    cut_rows, rd_rows = [], []
    for lender, g in loans.groupby("lender"):
        g = g.dropna(subset=["score"])
        if len(g) < 5000:
            continue
        for var in ("orig_apr", "orig_amount"):
            # economic floor on a jump: half a point of APR, or two percent of the median loan amount
            min_jump = 0.005 if var == "orig_apr" else 0.02 * float(g["orig_amount"].median())
            c = rd.find_cutoffs(g, var=var, lo=int(g["score"].quantile(0.02)), hi=int(g["score"].quantile(0.98)),
                                min_jump=min_jump)
            if c.empty:
                continue
            c.insert(0, "var", var)
            c.insert(0, "lender", lender)
            c["known_selection"] = c["cutoff"].isin(KNOWN_SELECTION_CUTOFFS.get(lender, set()))
            cut_rows.append(c)
        cands = pd.concat(cut_rows, ignore_index=True) if cut_rows else pd.DataFrame()
        if cands.empty:
            continue
        flagged = cands[(cands["lender"] == lender) & cands["flag"] & ~cands["known_selection"]]
        # keep the strongest candidate per 20-point neighbourhood so adjacent steps are not double counted
        flagged = flagged.sort_values("t", key=abs, ascending=False)
        chosen: list[float] = []
        for _, r in flagged.iterrows():
            if all(abs(r["cutoff"] - c0) >= 20 for c0 in chosen):
                chosen.append(float(r["cutoff"]))
        for c0 in chosen[:4]:
            dens = rd.density_test(g["score"], c0, h=25)
            row = {"lender": lender, "cutoff": c0, "density_method": dens["method"], "density_t": dens["t"], "density_p": dens["p"]}
            for var in ("orig_apr", "orig_amount"):
                e = rd.rd_estimate(g, var, c0)
                top = e.iloc[0] if not e.empty else None
                row[f"fs_{var}"] = float(top["estimate"]) if top is not None else np.nan
                row[f"fs_{var}_se"] = float(top["se"]) if top is not None else np.nan
            for m in (12, 24):
                gg = g.assign(y=rd.outcome_by_horizon(g, m)).dropna(subset=["y"])
                if len(gg) < 2000:
                    continue
                e = rd.rd_estimate(gg, "y", c0)
                top = e.iloc[0] if not e.empty else None
                row[f"co{m}_effect"] = float(top["estimate"]) if top is not None else np.nan
                row[f"co{m}_se"] = float(top["se"]) if top is not None else np.nan
                row[f"co{m}_n"] = int(len(gg))
            rd_rows.append(row)
    if cut_rows:
        pd.concat(cut_rows, ignore_index=True).to_csv(out / "b3_cutoffs.csv", index=False)
    pd.DataFrame(rd_rows).to_csv(out / "b3_rd.csv", index=False)


def main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="absrisk analyze autos")
    ap.add_argument("--in", dest="in_dir", default="data/autos")
    ap.add_argument("--out", default="data/results/autos")
    ap.add_argument("--skip", default="", help="comma list of b1,b2,b3 to skip")
    a = ap.parse_args(argv)
    warnings.filterwarnings("ignore")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    loans = load_loans(Path(a.in_dir))
    summarize(loans).to_csv(out / "loans_summary.csv", index=False)
    skip = {s.strip() for s in a.skip.split(",") if s.strip()}
    if "b1" not in skip:
        run_b1(loans, out)
    if "b2" not in skip:
        run_b2(loans, out)
    if "b3" not in skip:
        run_b3(loans, out)
    print(f"wrote results to {out} for {len(loans):,} loans in {loans['deal'].nunique()} deals", file=sys.stderr)
    return 0
