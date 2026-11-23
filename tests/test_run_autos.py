"""End-to-end run of the Track B driver on two synthetic deals written as parquet."""

from __future__ import annotations

import numpy as np
import pandas as pd

from absrisk.estimate import run_autos
from tests.test_estimate import make_loans


def _full_schema(df: pd.DataFrame, deal: str) -> pd.DataFrame:
    df = df.copy()
    df["deal"] = deal
    df["cik"] = "0000000000"
    df["first_period"] = pd.Timestamp("2025-02-28")
    df["last_period"] = pd.Timestamp("2026-07-31")
    df["score_type"] = "FICO"
    df["score_missing"] = df["score"].isna()
    df["vehicle_value"] = df["orig_amount"] / df["ltv"]
    df["new_used"] = "2"
    df["state"] = "TX"
    df["commercial"] = False
    df["exit_code"] = np.where(df["exit_type"] == "chargeoff", "4", np.where(df["exit_type"] == "prepay", "1", ""))
    df["max_dpd"] = 0
    df["chargeoff_amount"] = 0.0
    return df


def test_driver_writes_every_output(tmp_path):
    a = _full_schema(make_loans(n=15000, seed=11, h_co=0.01, lender="alpha"), "alpha-2025-1")
    b = _full_schema(make_loans(n=15000, seed=12, h_co=0.02, lender="beta"), "beta-2025-1")
    b["orig_apr"] = np.where(b["score"] >= 640, b["orig_apr"] - 0.04, b["orig_apr"])   # a pricing cutoff at 640
    in_dir, out = tmp_path / "autos", tmp_path / "results"
    in_dir.mkdir()
    a.to_parquet(in_dir / "alpha-2025-1.parquet", index=False)
    b.to_parquet(in_dir / "beta-2025-1.parquet", index=False)
    assert run_autos.main(["--in", str(in_dir), "--out", str(out)]) == 0
    for name in ("loans_summary.csv", "b1_cif.csv", "b1_at_12.csv", "b1_at_24.csv", "b2_hazard_ratios.csv", "b2_fit.json", "b3_cutoffs.csv", "b3_rd.csv",
                 "b1_cohort_at_12.csv", "b1_cohort_at_24.csv", "b3_rd_bandwidths.csv", "b1_gap.csv",
                 "b1_late_repurchase.csv", "b1_fixed_pairs.csv", "b1_gap_trust_loss.csv", "b1_at_12_trust_loss.csv",
                 "b1_at_24_trust_loss.csv"):
        assert (out / name).exists(), name
    hr = pd.read_csv(out / "b2_hazard_ratios.csv")
    lender = hr[(hr["spec"] == "score") & (hr["event"] == "chargeoff") & (hr["factor"] == "lender")]
    assert len(lender) == 1 and 1.6 < lender["odds_ratio"].iloc[0] < 2.5          # beta vs alpha at fixed score
    cuts = pd.read_csv(out / "b3_cutoffs.csv")
    assert ((cuts["lender"] == "beta") & (cuts["var"] == "orig_apr") & (cuts["cutoff"] == 640) & cuts["flag"]).any()
    rdres = pd.read_csv(out / "b3_rd.csv")
    assert ((rdres["lender"] == "beta") & (rdres["cutoff"] == 640)).any()


def test_load_loans_normalises_legacy_capone_negative_recoveries(tmp_path):
    """REVIEW.md abs-B-6: legacy Capital One parquet carries negative recovered_amount; load_loans flips it idempotently."""
    from pathlib import Path
    import pytest

    repo = Path(__file__).resolve().parents[1]
    d = tmp_path / "autos"
    d.mkdir()
    syn = _full_schema(make_loans(n=20, seed=1, lender="capone"), "copar-syn")
    syn["recovered_amount"] = np.where(syn["exit_type"] == "chargeoff", -500.0, 0.0)
    syn.to_parquet(d / "copar-syn.parquet", index=False)
    loaded = run_autos.load_loans(d, basis="trust_loss")
    assert (loaded["recovered_amount"] >= 0).all()
    assert loaded["recovered_amount"].sum() == pytest.approx(500.0 * (syn["exit_type"] == "chargeoff").sum())
    # already-positive Capital One data is left unchanged (idempotent after parser rebuild)
    loaded.to_parquet(d / "copar-syn.parquet", index=False)
    again = run_autos.load_loans(d, basis="trust_loss")
    assert (again["recovered_amount"] >= 0).all() and again["recovered_amount"].sum() == pytest.approx(loaded["recovered_amount"].sum())

    # committed copar-2025-1 parquet normalises to +$695,460.96
    copar_only = tmp_path / "copar"
    copar_only.mkdir()
    pd.read_parquet(repo / "data" / "autos" / "copar-2025-1.parquet").to_parquet(copar_only / "copar-2025-1.parquet", index=False)
    real = run_autos.load_loans(copar_only, basis="trust_loss")
    assert (real["recovered_amount"] >= 0).all()
    assert real["recovered_amount"].sum() == pytest.approx(695_460.96, abs=0.05)
