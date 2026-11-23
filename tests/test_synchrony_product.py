"""Product-consistent card calibration for Synchrony (REVIEW.md R2-2).

Synchrony's card trust is a retail pool whose prospectus Program Partner table puts about a quarter of receivables
in private-label cards (Amazon, Lowe's) and the rest in general-purpose dual cards and Synchrony MasterCard.
Before R2-2 was fixed, Synchrony was calibrated to the CFPB general-purpose series alone, inflating its residual
and placing it rank 1 under every loss curve. These tests pin:

1. `mix_by_trust.csv` carries each trust's prospectus `private_label_share` (~24.3% Synchrony, 0.0% elsewhere).
2. A trust with a nonzero `private_label_share` is calibrated to the linear blend of the CFPB general-purpose and
   private-label levels, never to the general-purpose level alone.
3. `a1_product.csv` reproduces all three calibrations (general purpose 0%, prospectus blend, private label 100%)
   from the committed inputs, with `prospectus_blend` matching `a1_ranking.csv` identically.
4. `cards_page.ends` and `cards_page.ends_sentence` report ties at the top/bottom honestly rather than picking one
   trust arbitrarily, and both `docs/cards.html` and `docs/conclusions.html` disclose the product mix and sensitivity.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from absrisk.estimate import cards_roll, run_cards
from absrisk.report import cards_page
from absrisk.shape import TIERS, default_shapes, load_level, predict_chargeoff

REPO = Path(__file__).resolve().parents[1]
RESULTS = REPO / "data" / "results" / "cards"
DOCS = REPO / "docs"


def _text(name: str) -> str:
    raw = (DOCS / name).read_text(encoding="utf-8")
    raw = re.sub(r"<style>.*?</style>", "", raw, flags=re.S)
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw)))


def test_mix_by_trust_carries_private_label_share():
    mix = pd.read_csv(RESULTS / "mix_by_trust.csv").set_index("trust")
    assert "private_label_share" in mix.columns
    assert 0.24 < mix.loc["synchrony", "private_label_share"] < 0.25
    assert (mix.drop(index="synchrony")["private_label_share"] == 0.0).all()


def test_nonzero_private_label_share_is_not_calibrated_to_gp_alone():
    """REVIEW.md R2-2 Verify: a trust with a nonzero private-label share must not be calibrated to GP alone."""
    shapes, level = default_shapes(), load_level()
    monthly = pd.DataFrame({
        "trust": ["retail", "gp"],
        "period_end": ["2024-06-30", "2024-06-30"],
        "net_co_rate": [0.045, 0.045],
        "gross_co_rate": [0.055, 0.055],
    })
    base_tiers = {"deep_subprime": 0.06, "subprime": 0.06, "near_prime": 0.12,
                  "prime": 0.27, "prime_plus": 0.30, "superprime": 0.19}
    mix = pd.DataFrame([
        {"trust": "retail", "as_of": "2024-01-01", "private_label_share": 0.25, **base_tiers},
        {"trust": "gp", "as_of": "2024-01-01", "private_label_share": 0.0, **base_tiers},
    ])
    pred = run_cards.predicted(monthly, mix, shapes, level, "ccip", rate_col=cards_roll.RATE)
    for s, g in pred.groupby("shape_source"):
        by = g.set_index("trust")
        p_gp = predict_chargeoff(base_tiers, 2024, s, "ccip", product="gp", shapes=shapes, level=level)
        p_pl = predict_chargeoff(base_tiers, 2024, s, "ccip", product="pl", shapes=shapes, level=level)
        assert by.loc["gp", "predicted"] == pytest.approx(p_gp)
        assert by.loc["retail", "predicted"] == pytest.approx(0.75 * p_gp + 0.25 * p_pl)
        assert by.loc["retail", "predicted"] > by.loc["gp", "predicted"] + 0.005
        assert by.loc["retail", "residual"] < by.loc["gp", "residual"] - 0.005


def test_a1_product_matches_independent_rederivation_and_ranking():
    monthly = pd.read_csv(REPO / "data" / "cards_monthly.csv", parse_dates=["period_end"])
    mix = pd.read_csv(RESULTS / "mix_by_trust.csv").set_index("trust")
    prod = pd.read_csv(RESULTS / "a1_product.csv")
    rank = pd.read_csv(RESULTS / "a1_ranking.csv")
    shapes, level = default_shapes(), load_level()

    assert set(prod["trust"]) == {"synchrony"}
    assert set(prod["calibration"]) == {"general_purpose", "prospectus_blend", "private_label"}

    # prospectus_blend rows must equal the published a1_ranking.csv rows identically
    bl = prod[prod["calibration"] == "prospectus_blend"].merge(
        rank[rank["trust"] == "synchrony"], on=["trust", "shape_source"], suffixes=("", "_rk")
    )
    assert len(bl) == 4
    assert np.allclose(bl["mean_residual"], bl["mean_residual_rk"], atol=1e-12)
    assert np.allclose(bl["mean_residual_gross"], bl["mean_residual_gross_rk"], atol=1e-12)
    assert (bl["rank"] == bl["rank_rk"]).all()

    # independent re-derivation of Synchrony across all three calibrations
    syn_m = monthly[monthly["trust"] == "synchrony"].dropna(subset=[cards_roll.RATE])
    syn_tiers = {t: float(mix.loc["synchrony", t]) for t in TIERS}
    w_blend = float(mix.loc["synchrony", "private_label_share"])
    for cal, w in (("general_purpose", 0.0), ("prospectus_blend", w_blend), ("private_label", 1.0)):
        sub = prod[prod["calibration"] == cal].set_index("shape_source")
        for s in sub.index:
            preds = [
                predict_chargeoff(syn_tiers, min(max(int(d.year), 2014), 2024), s, "ccip",
                                  private_label_share=w, shapes=shapes, level=level)
                for d in syn_m["period_end"]
            ]
            assert sub.loc[s, "mean_residual"] == pytest.approx(float((syn_m[cards_roll.RATE] - preds).mean()), abs=1e-12)
            assert sub.loc[s, "mean_residual_gross"] == pytest.approx(float((syn_m["gross_co_rate"] - preds).mean()), abs=1e-12)

    # economic signs & ranks: GP-only is rank 1 everywhere; blend stays positive on gross (rank 1 on ACMS, 4 on FICO);
    # 100% PL reverses gross sign everywhere and drops to rank 6
    gp = prod[prod["calibration"] == "general_purpose"].set_index("shape_source")
    bl = prod[prod["calibration"] == "prospectus_blend"].set_index("shape_source")
    pl = prod[prod["calibration"] == "private_label"].set_index("shape_source")
    assert (gp["rank"] == 1).all()
    assert (bl["mean_residual_gross"] > 0).all()
    assert bl.loc["acms2018", "rank"] == 1 and bl.loc["fico_odds", "rank"] == 4
    assert (pl["mean_residual_gross"] < 0).all()
    assert (pl["rank"] == 6).all()


def test_ends_reports_ties_and_asymmetric_holds_honestly():
    # Synthetic 4-cell table where a and b tie for rank 1 (2 each), while d is last in 3 of 4.
    cells = pd.DataFrame([
        {"straddle_rule": "r1", "shape_source": "s1", "trust": "a", "mean_residual": 0.01, "rank": 1},
        {"straddle_rule": "r1", "shape_source": "s1", "trust": "b", "mean_residual": 0.00, "rank": 2},
        {"straddle_rule": "r1", "shape_source": "s1", "trust": "c", "mean_residual": -0.01, "rank": 3},
        {"straddle_rule": "r1", "shape_source": "s1", "trust": "d", "mean_residual": -0.02, "rank": 4},
        {"straddle_rule": "r1", "shape_source": "s2", "trust": "a", "mean_residual": 0.01, "rank": 1},
        {"straddle_rule": "r1", "shape_source": "s2", "trust": "b", "mean_residual": 0.00, "rank": 2},
        {"straddle_rule": "r1", "shape_source": "s2", "trust": "c", "mean_residual": -0.01, "rank": 3},
        {"straddle_rule": "r1", "shape_source": "s2", "trust": "d", "mean_residual": -0.02, "rank": 4},
        {"straddle_rule": "r2", "shape_source": "s1", "trust": "b", "mean_residual": 0.01, "rank": 1},
        {"straddle_rule": "r2", "shape_source": "s1", "trust": "a", "mean_residual": 0.00, "rank": 2},
        {"straddle_rule": "r2", "shape_source": "s1", "trust": "c", "mean_residual": -0.01, "rank": 3},
        {"straddle_rule": "r2", "shape_source": "s1", "trust": "d", "mean_residual": -0.02, "rank": 4},
        {"straddle_rule": "r2", "shape_source": "s2", "trust": "b", "mean_residual": 0.01, "rank": 1},
        {"straddle_rule": "r2", "shape_source": "s2", "trust": "a", "mean_residual": 0.00, "rank": 2},
        {"straddle_rule": "r2", "shape_source": "s2", "trust": "d", "mean_residual": -0.01, "rank": 3},
        {"straddle_rule": "r2", "shape_source": "s2", "trust": "c", "mean_residual": -0.02, "rank": 4},
    ])
    e = cards_page.ends(cells)
    assert e["top_tied"] == ["a", "b"] and e["top_n"] == 2
    assert e["bottom_tied"] == ["d"] and e["bottom_n"] == 3
    sent = cards_page.ends_sentence(e)
    assert "Only the bottom of the ranking holds under most assumptions; the top does not." in sent
    assert "a and b tie for the largest residual in 2 each" in sent
    assert "d the smallest in 3" in sent


def test_published_pages_reflect_blended_synchrony_calibration():
    cards = _text("cards.html")
    assert "Product calibration: general purpose against private label" in cards
    assert "prospectus blend (24.3% PL, default)" in cards
    assert "bofa and synchrony tie for the largest residual in 5 each" in cards
    assert "synchrony's pool is set against the general-purpose industry level like the other five" not in cards

    conc = _text("conclusions.html")
    assert "24.3% private-label receivables" in conc
    assert "bofa and synchrony tie for the largest gap in 5 each" in conc
    assert "24.3% private label at synchrony" in conc
