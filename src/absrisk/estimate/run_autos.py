"""Run the Track B estimators over every loans table under data/autos/ and write results under data/results/autos/.

Outputs (all CSV unless noted):
  loans_summary.csv          per deal: N, first/last period, exit_type shares, score coverage, PTI unit rule
  b1_cif.csv                 cumulative incidence by lender x score bucket x age (AJ and KM), with N
  b1_at_12.csv, b1_at_24.csv the 12- and 24-month cuts
  b2_hazard_ratios.csv       odds ratios by factor level for charge-off and prepay, with and without controls; clustered
                             intervals with t(G-1) critical values; levels with no events blanked
  b2_lender_intervals.csv    terms-specification lender odds ratios with intervals that include the deal-to-deal spread
  b2_terms_without_exeter.csv  the terms specification refitted without Exeter, whose score is VantageScore (stage b2x)
  b2_fit.json                fit metadata (cells, exposure, columns, deal-shock estimates)
  b3_cutoffs.csv             candidate pricing cutoffs per lender (APR and amount jumps)
  b3_rd.csv                  density test, first stage and outcome RD at each flagged cutoff
  b1_cohort_at_12.csv, b1_cohort_at_24.csv   the B1 cuts inside one origination year at a time
  b3_rd_bandwidths.csv       outcome RD at 0.5-2x the MSE-optimal bandwidth, usable cutoffs only
Result-file prefixes predate the task board: b1_* is TASKS B3, b2_* is B4, b3_* is B5, b6_* is the entry/roll split.
Run: `uv run absrisk analyze autos [--in data/autos] [--out data/results/autos]`.
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from . import decompose, hazard, rd, survival

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
        a = survival.ages(g)
        rows.append({
            "deal": deal, "lender": g["lender"].iloc[0], "n_loans": len(g),
            "first_period": str(g["first_period"].min()), "last_period": str(g["last_period"].max()),
            "months_observed_median": float(g["months_observed"].median()),
            "entry_age_median": float(a["entry_age"].median()), "entry_age_p90": float(a["entry_age"].quantile(0.9)),
            "exit_age_max": int(a["exit_age"].max()),
            "share_chargeoff": float(et.get("chargeoff", 0)), "share_prepay": float(et.get("prepay", 0)),
            "share_repurchase": float(et.get("repurchase", 0)), "share_absent": float(et.get("absent", 0)),
            "share_censored": float(et.get("censored", 0)),
            "score_missing_share": float(g["score"].isna().mean()), "score_median": float(g["score"].median()),
            "score_max": float(g["score"].max()), "score_above_850_share": float((g["score"] > 850).mean()),
            "score_type": ",".join(sorted(g["score_type"].dropna().astype(str).unique())[:3]),
            "pti_median": float(g["pti"].median()) if "pti" in g else np.nan,
            "apr_median": float(g["orig_apr"].median()), "amount_median": float(g["orig_amount"].median()),
        })
    return pd.DataFrame(rows)


def run_b1(loans: pd.DataFrame, out: Path, n_boot: int = 200):
    df = loans.copy()
    df["score_b"] = survival.score_bucket(df["score"])
    cif = survival.cumulative_incidence(df, by=["lender", "score_b"], horizon=36, n_boot=n_boot)
    cif.to_csv(out / "b1_cif.csv", index=False)
    survival.incidence_at(cif, ["lender", "score_b"], 12).to_csv(out / "b1_at_12.csv", index=False)
    survival.incidence_at(cif, ["lender", "score_b"], 24).to_csv(out / "b1_at_24.csv", index=False)
    by_lender = survival.cumulative_incidence(df, by=["lender"], horizon=36, n_boot=n_boot)
    by_lender.to_csv(out / "b1_cif_by_lender.csv", index=False)
    # fresh-entrant cut: loans first observed within six months of origination
    fresh = survival.cumulative_incidence(df, by=["lender", "score_b"], horizon=36, n_boot=n_boot, max_entry_age=6)
    fresh.to_csv(out / "b1_cif_fresh.csv", index=False)
    survival.incidence_at(fresh, ["lender", "score_b"], 24).to_csv(out / "b1_at_24_fresh.csv", index=False)
    return cif


def run_b1_cohort(loans: pd.DataFrame, out: Path, n_boot: int = 200, horizons: tuple[int, ...] = (12, 24)):
    """Same score, same origination year, different lender (TASKS B3: "by origination cohort").

    Each lender's public pools hold one or two vintages, and vintages differ industry-wide, so a pooled lender gap
    could be a vintage gap. This cut compares lenders inside one origination year at a time. Writes
    b1_cohort_at_<h>.csv, the B1 table with an `orig_year` column in front."""
    if "orig_month" not in loans:
        return None
    df = loans.copy()
    df["score_b"] = survival.score_bucket(df["score"])
    df["orig_year"] = pd.to_datetime(df["orig_month"]).dt.year.astype("Int64")
    by = ["orig_year", "lender", "score_b"]
    cif = survival.cumulative_incidence(df, by=by, horizon=max(horizons), n_boot=n_boot)
    for h in horizons:
        survival.incidence_at(cif, by, h).to_csv(out / f"b1_cohort_at_{h}.csv", index=False)
    return cif


def run_b3_bandwidths(loans: pd.DataFrame, out: Path, mults: tuple[float, ...] = rd.BANDWIDTH_MULTS):
    """Bandwidth sensitivity of the charge-off effect at every cutoff that passes the screen (TASKS B5).

    Reads b3_rd.csv from `out`, keeps the usable cutoffs (`rd.usable`), and refits the 12- and 24-month outcome at
    0.5 to 2 times the MSE-optimal bandwidth on exactly the sample run_b3 used. Writes b3_rd_bandwidths.csv."""
    p = out / "b3_rd.csv"
    if not p.exists():
        return None
    rdres = pd.read_csv(p)
    if rdres.empty:
        return None
    rows = []
    for _, r in rdres[rd.usable(rdres)].iterrows():
        g = loans[loans["lender"] == r["lender"]].dropna(subset=["score"])
        for m in (12, 24):
            gg = g.assign(y=rd.outcome_by_horizon(g, m)).dropna(subset=["y"])
            if len(gg) < 2000:
                continue
            s = rd.rd_bandwidth_sensitivity(gg, "y", float(r["cutoff"]), mults=mults)
            if s.empty:
                continue
            s.insert(0, "horizon", m)
            s.insert(0, "cutoff", float(r["cutoff"]))
            s.insert(0, "lender", r["lender"])
            rows.append(s)
    res = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        columns=["lender", "cutoff", "horizon", "bw_mult", "bandwidth", "estimate", "se", "ci_lo", "ci_hi", "p_robust",
                 "n_left", "n_right", "error"])
    res.to_csv(out / "b3_rd_bandwidths.csv", index=False)
    return res


def run_b2(loans: pd.DataFrame, out: Path):
    df = hazard.add_design_columns(loans)
    keep = ["deal", "lender", "score_b", "cohort_q", "amount_q", "pti_q", "ltv_q", "apr_q"]
    keep = [k for k in keep if k in df]
    lm = hazard.expand_loan_months(df, keep=keep)
    # A ladder, in the order a reader should think about it. `price` conditions on the lender's own APR, which the
    # lender set from its view of the borrower's risk: that is a mediator, not a confounder, so it is reported last
    # and labelled. Adding it flattens the score gradient, which is itself a result (see the page).
    structure = [k for k in ("amount_q", "pti_q", "ltv_q") if k in df]
    # months in pool separates from loan age only when loans entered their trusts at different ages; when every loan
    # entered at one age (a synthetic panel) the two are the same clock and the design would be singular
    pool = ["pool_b"] if survival.ages(df)["entry_age"].nunique() > 1 else []
    specs = {
        "raw": ["age_b", *pool, "lender"],
        "score": ["age_b", *pool, "score_b", "lender"],
        "terms": ["age_b", *pool, "score_b", "lender", "cohort_q"] + structure,
        "price": ["age_b", *pool, "score_b", "lender", "cohort_q"] + structure + (["apr_q"] if "apr_q" in df else []),
    }
    rows, meta = [], {"months_in_pool": "included" if pool else "left out: every loan entered at the same age"}
    # baselines with mass: the 660 score bucket (the prime boundary), the 7-9 month age bin, the largest lender and the
    # most populous origination quarter. Without the last, the baseline quarter was the earliest one (2017Q2, five
    # loans, no charge-offs) and every quarter's odds ratio came out near 1e10 with no interval; the other factors'
    # estimates were unaffected (checked 2026-11-09: identical to 1e-6 in log odds either way).
    base_lender = str(df["lender"].value_counts().idxmax())
    base_cohort = str(df["cohort_q"].value_counts().idxmax()) if "cohort_q" in df else None
    baseline = {"score_b": "660", "age_b": "7-9", "pool_b": "9+", "lender": base_lender, "amount_q": "0", "pti_q": "0",
                "ltv_q": "0", "apr_q": "0"}
    if base_cohort is not None:
        baseline["cohort_q"] = base_cohort
    lender_rows = []
    for name, factors in specs.items():
        cells = hazard.aggregate_cells(lm, cells=[f for f in factors if f not in ("age_b", "pool_b")] + ["deal"])
        res = hazard.fit_hazards(cells, factors=factors, cluster="deal", baseline=baseline)
        meta[name] = res["design_info"]
        for event in ("chargeoff", "prepay"):
            for f in factors:
                ev = cells.groupby(f, observed=True)[f"d_{event}"].sum().to_dict()
                hr = hazard.hazard_ratios(res[event], f, t_df=res["design_info"].get("t_df"),
                                          events={str(k): v for k, v in ev.items()})
                hr.insert(0, "factor", f)
                hr.insert(0, "event", event)
                hr.insert(0, "spec", name)
                rows.append(hr)
        if name in ("score", "terms"):
            li, info = hazard.deal_spread_intervals(cells, factors, baseline)
            li.insert(0, "spec", name)
            lender_rows.append(li)
            meta[name]["deal_spread"] = info
    if lender_rows:
        pd.concat(lender_rows, ignore_index=True).to_csv(out / "b2_lender_intervals.csv", index=False)
    meta["baseline"] = baseline
    meta["spec_notes"] = {
        "raw": "loan age and months in pool only: the gap as it appears in the data, composition included",
        "score": "adds the bureau score bucket: same score, different lender",
        "terms": "adds origination quarter, loan amount, payment-to-income and loan-to-value quintiles: same score and same loan structure",
        "price": "adds the lender's own APR quintile. APR is set by the lender from its private view of the borrower, so it is a"
                 " mediator of lender differences, not a confounder; conditioning on it answers a narrower question and absorbs"
                 " part of the score gradient (about a quarter of what remains after loan structure). Reported for that reason,"
                 " not as the preferred specification.",
    }
    pd.concat(rows, ignore_index=True).to_csv(out / "b2_hazard_ratios.csv", index=False)
    (out / "b2_fit.json").write_text(json.dumps(meta, indent=1, default=str))


def run_b2_without(loans: pd.DataFrame, out: Path, lender: str = "exeter") -> pd.DataFrame | None:
    """The terms specification refitted without one lender: by default Exeter, whose "Consumer Credit Bureau" score is
    VantageScore for 98.9% of its pool, so its score buckets are not the FICO buckets the others share. Design
    columns (quintile edges, merged levels) come from the full sample so the two fits compare like with like.
    Writes b2_terms_without_<lender>.csv: charge-off odds ratios for the lenders and the three structure measures."""
    if lender not in set(loans["lender"]):
        return None
    df = hazard.add_design_columns(loans)
    df = df[df["lender"] != lender]
    keep = [k for k in ["deal", "lender", "score_b", "cohort_q", "amount_q", "pti_q", "ltv_q"] if k in df]
    lm = hazard.expand_loan_months(df, keep=keep)
    structure = [k for k in ("amount_q", "pti_q", "ltv_q") if k in df]
    pool = ["pool_b"] if survival.ages(df)["entry_age"].nunique() > 1 else []
    factors = ["age_b", *pool, "score_b", "lender", "cohort_q"] + structure
    baseline = {"score_b": "660", "age_b": "7-9", "pool_b": "9+", "lender": str(df["lender"].value_counts().idxmax()),
                "amount_q": "0", "pti_q": "0", "ltv_q": "0", "cohort_q": str(df["cohort_q"].value_counts().idxmax())}
    cells = hazard.aggregate_cells(lm, cells=[f for f in factors if f not in ("age_b", "pool_b")] + ["deal"])
    res = hazard.fit_hazards(cells, factors=factors, cluster="deal", baseline=baseline)
    rows = []
    for f in ["lender", *structure]:
        ev = cells.groupby(f, observed=True)["d_chargeoff"].sum().to_dict()
        hr = hazard.hazard_ratios(res["chargeoff"], f, t_df=res["design_info"].get("t_df"),
                                  events={str(k): v for k, v in ev.items()})
        hr.insert(0, "factor", f)
        rows.append(hr)
    t = pd.concat(rows, ignore_index=True)
    t.insert(0, "without", lender)
    t["baseline_lender"] = baseline["lender"]
    t.to_csv(out / f"b2_terms_without_{lender}.csv", index=False)
    return t


def run_b6(loans: pd.DataFrame, out: Path):
    """Selection or prioritisation: split each lender's gap into getting into trouble and trouble becoming loss."""
    base = str(loans["lender"].value_counts().idxmax())
    overall = decompose.decompose(loans, by=["lender"])
    overall.to_csv(out / "b6_decomposition.csv", index=False)
    decompose.attribute(overall, "lender", base).to_csv(out / "b6_attribution.csv", index=False)
    within = decompose.by_score_and_group(loans, min_loans=1200, min_ever30=60)
    within = within.dropna(subset=["implied"]).copy()
    within["score_b"] = pd.to_numeric(within["score_b"], errors="coerce")
    within = within.dropna(subset=["score_b"])
    within.to_csv(out / "b6_by_score.csv", index=False)
    # attribution inside each score bucket, against the baseline lender present in that bucket
    rows = []
    for sb, g in within.groupby("score_b"):
        if base not in set(g["lender"]) or g["lender"].nunique() < 2:
            continue
        a = decompose.attribute(g, "lender", base)
        a.insert(0, "score_b", int(sb))
        rows.append(a)
    if rows:
        pd.concat(rows, ignore_index=True).to_csv(out / "b6_attribution_by_score.csv", index=False)


def run_b3(loans: pd.DataFrame, out: Path):
    cut_rows, rd_rows = [], []
    for lender, g in loans.groupby("lender"):
        g = g.dropna(subset=["score"])
        if len(g) < 5000:
            continue
        for var in ("orig_apr", "orig_amount"):
            # economic floor on a jump: half a point of APR, or five percent of the median loan amount
            min_jump = 0.005 if var == "orig_apr" else 0.05 * float(g["orig_amount"].median())
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
    ap.add_argument("--skip", default="", help="comma list of stages to skip: b1,b1c,b2,b2x,b3,b3bw,b6")
    a = ap.parse_args(argv)
    warnings.filterwarnings("ignore")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    loans = load_loans(Path(a.in_dir))
    summarize(loans).to_csv(out / "loans_summary.csv", index=False)
    skip = {s.strip() for s in a.skip.split(",") if s.strip()}
    if "b1" not in skip:
        run_b1(loans, out)
    if "b1c" not in skip:
        run_b1_cohort(loans, out)
    if "b2" not in skip:
        run_b2(loans, out)
    if "b2x" not in skip:
        run_b2_without(loans, out)
    if "b3" not in skip:
        run_b3(loans, out)
    if "b3bw" not in skip:
        run_b3_bandwidths(loans, out)
    if "b6" not in skip:
        run_b6(loans, out)
    print(f"wrote results to {out} for {len(loans):,} loans in {loans['deal'].nunique()} deals", file=sys.stderr)
    return 0
