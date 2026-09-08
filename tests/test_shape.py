"""Task A3: loss shapes by tier, CFPB level calibration, and the bucket-to-tier straddle rule.

Reads the committed data/loss_shape.csv and data/ccmr_level.csv. The workbook rebuild test runs only when
the CFPB figure-data workbooks are present under data/raw/scout/cfpb/ (they are not committed).
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from absrisk.shape import (
    TIER_BOUNDS,
    TIERS,
    band_rates_to_tiers,
    build_loss_shape,
    calibration_check,
    cfpb_mix,
    cfpb_rate,
    data_dir,
    level_for,
    load_level,
    load_shapes,
    overlap_fraction,
    predict_chargeoff,
    shape_vector,
    tiers_from_buckets,
)
from absrisk.shape.build_level import RAW_DIR, WB_2023, WB_2025, build as build_level
from absrisk.shape.shapes import COLUMNS as SHAPE_COLUMNS

SCORE_ORDER = {t: i for i, t in enumerate(TIERS)}  # lowest score tier first


@pytest.fixture(scope="module")
def shapes() -> pd.DataFrame:
    return load_shapes(data_dir() / "loss_shape.csv")


@pytest.fixture(scope="module")
def level() -> pd.DataFrame:
    return load_level()


def filled_sources(shapes: pd.DataFrame) -> list[str]:
    return [s for s in shapes["shape_source"].unique() if not shapes.loc[shapes["shape_source"] == s, "relative_loss"].isna().any()]


# --- loss_shape.csv -----------------------------------------------------------------------------------------


def test_loss_shape_schema(shapes):
    assert list(shapes.columns) == SHAPE_COLUMNS
    for src, sub in shapes.groupby("shape_source"):
        assert sorted(sub["tier"]) == sorted(TIERS), src
        for _, r in sub.iterrows():
            assert (int(r["tier_lo"]), int(r["tier_hi"])) == TIER_BOUNDS[r["tier"]]
    for src in ("fico_odds", "acms2018", "autos_b1"):  # the three the plan names
        assert src in set(shapes["shape_source"]), src
    filled = filled_sources(shapes)
    assert "autos_b1" not in filled  # placeholder until Track B
    assert shapes.loc[shapes["shape_source"] == "autos_b1", "note"].str.contains("Track B").all()
    for src in filled:
        sub = shapes[shapes["shape_source"] == src]
        assert (sub["citation"].str.len() > 40).all(), src
        assert (sub["source_rate"] > 0).all(), src


def test_prime_is_one_in_every_filled_shape(shapes):
    for src in filled_sources(shapes):
        vec = shape_vector(shapes, src)
        assert vec["prime"] == 1.0, src


def test_relative_loss_non_increasing_with_score(shapes):
    for src in filled_sources(shapes):
        vec = shape_vector(shapes, src)
        vals = [vec[t] for t in TIERS]
        assert all(a >= b for a, b in zip(vals, vals[1:])), (src, vals)
        assert vec["deep_subprime"] > vec["prime"] > vec["superprime"], (src, vals)


def test_committed_shape_csv_matches_rebuild(shapes):
    rebuilt = build_loss_shape()
    pd.testing.assert_frame_equal(
        shapes.reset_index(drop=True), rebuilt.fillna({"flag": "", "note": "", "citation": "", "source_unit": ""}), check_dtype=False
    )


def test_placeholder_shape_is_refused(shapes, level):
    with pytest.raises(ValueError, match="placeholder"):
        shape_vector(shapes, "autos_b1")
    with pytest.raises(ValueError):
        predict_chargeoff({"prime": 1.0}, 2023, "autos_b1", shapes=shapes, level=level)
    with pytest.raises(ValueError, match="unknown shape_source"):
        shape_vector(shapes, "no_such_shape")


# --- ccmr_level.csv -----------------------------------------------------------------------------------------


def test_level_schema(level):
    assert set(level["series"]) == {"ccip", "ccp"}
    ccip = level[level["series"] == "ccip"]
    ccp = level[level["series"] == "ccp"]
    assert sorted(ccip["year"]) == list(range(2014, 2025))
    assert sorted(ccp["year"]) == list(range(2013, 2023))
    assert (ccip["n_periods"] == 12).all() and (ccp["n_periods"] == 4).all()
    shares = level[[f"share_{t}" for t in TIERS]]
    assert ((shares > 0) & (shares < 1)).all().all()
    assert (shares.sum(axis=1) - 1.0).abs().max() < 1e-5
    assert level["gp_chargeoff_rate"].between(0.01, 0.10).all()
    assert level["gp_chargeoff_rate_ye"].between(0.01, 0.10).all()
    assert level["citation_rate"].str.contains("Figure").all()
    assert level["citation_mix"].str.contains("Figure").all()


def test_level_matches_scout_note_spot_values(level):
    # design/scout-ccmr-tiers.md section 3.2: CCIP GP annual average 2019 3.67, 2024 5.25 (percent);
    # CCP GP annual average 2019 6.53, YE2022 4.3.
    assert cfpb_rate(level, 2019, "ccip") == pytest.approx(0.0367, abs=5e-5)
    assert cfpb_rate(level, 2024, "ccip") == pytest.approx(0.0525, abs=5e-5)
    assert cfpb_rate(level, 2019, "ccp") == pytest.approx(0.0653, abs=5e-5)
    row = level[(level["year"] == 2022) & (level["series"] == "ccp")].iloc[0]
    assert row["gp_chargeoff_rate_ye"] == pytest.approx(0.043, abs=1e-9)


def test_calibration_check_every_year_and_series(shapes, level):
    chk = calibration_check(1e-9, shapes=shapes, level=level)
    assert len(chk) == len(level) * len(filled_sources(shapes))
    assert chk["abs_err"].max() <= 1e-9
    assert (chk["level"] > 0).all()


def test_predict_chargeoff_is_level_times_mix_dot_shape(shapes, level):
    for src in filled_sources(shapes):
        for series, year in (("ccip", 2023), ("ccp", 2019)):
            lvl = level_for(year, src, series, shapes=shapes, level=level)
            assert predict_chargeoff({"prime": 1.0}, year, src, series, shapes=shapes, level=level) == pytest.approx(lvl)
            vec = shape_vector(shapes, src)
            mix = {"deep_subprime": 0.2, "prime": 0.5, "superprime": 0.3}
            expected = lvl * sum(mix[t] * vec[t] for t in mix)
            assert predict_chargeoff(mix, year, src, series, shapes=shapes, level=level) == pytest.approx(expected)
            worst = predict_chargeoff({"deep_subprime": 1.0}, year, src, series, shapes=shapes, level=level)
            best = predict_chargeoff({"superprime": 1.0}, year, src, series, shapes=shapes, level=level)
            assert worst > cfpb_rate(level, year, series) > best


def test_predict_chargeoff_rejects_bad_input(shapes, level):
    with pytest.raises(ValueError, match="sum to"):
        predict_chargeoff({"prime": 0.5}, 2023, "fico_odds", shapes=shapes, level=level)
    with pytest.raises(ValueError, match="unknown tiers"):
        predict_chargeoff({"prime": 0.5, "platinum": 0.5}, 2023, "fico_odds", shapes=shapes, level=level)
    with pytest.raises(ValueError, match="years available"):
        predict_chargeoff({"prime": 1.0}, 2013, "fico_odds", "ccip", shapes=shapes, level=level)
    assert predict_chargeoff({"prime": 1.0}, 2013, "fico_odds", "ccp", shapes=shapes, level=level) > 0


def test_cfpb_mix_sums_to_one(level):
    for _, r in level.iterrows():
        mix = cfpb_mix(level, int(r["year"]), str(r["series"]))
        assert sum(mix.values()) == pytest.approx(1.0, abs=1e-5)


@pytest.mark.skipif(not (RAW_DIR / WB_2025).exists() or not (RAW_DIR / WB_2023).exists(), reason="CFPB workbooks not downloaded")
def test_level_rebuild_from_workbooks_matches_committed(level, tmp_path):
    rebuilt = build_level(RAW_DIR)
    out = tmp_path / "ccmr_level.csv"
    rebuilt.to_csv(out, index=False, lineterminator="\n")
    pd.testing.assert_frame_equal(pd.read_csv(out), level, check_dtype=False)


# --- tiers_from_buckets --------------------------------------------------------------------------------------


def test_overlap_fraction_edges():
    assert overlap_fraction(660, 719, "prime") == 1.0
    assert overlap_fraction(660, 719, "subprime") == 0.0
    assert overlap_fraction(None, 599, "deep_subprime") == pytest.approx(280 / 300)
    assert overlap_fraction(None, 599, "subprime") == pytest.approx(20 / 300)
    assert overlap_fraction(720, None, "prime_plus") == pytest.approx(80 / 131)
    assert overlap_fraction(720, None, "superprime") == pytest.approx(51 / 131)


def test_tiers_from_buckets_hand_example_with_straddles():
    # A typical prospectus table: <600 / 600-659 / 660-719 / 720+. The first bucket straddles deep subprime and
    # subprime (580), the second straddles subprime and near-prime (620), the last straddles prime plus and
    # superprime (800). Each straddle is split by the count of integer scores on each side.
    buckets = [(None, 599, 0.10), (600, 659, 0.20), (660, 719, 0.30), (720, None, 0.40)]
    got = tiers_from_buckets(buckets)
    expected = {
        "deep_subprime": 0.10 * 280 / 300,
        "subprime": 0.10 * 20 / 300 + 0.20 * 20 / 60,
        "near_prime": 0.20 * 40 / 60,
        "prime": 0.30,
        "prime_plus": 0.40 * 80 / 131,
        "superprime": 0.40 * 51 / 131,
    }
    assert set(got) == set(TIERS)
    for t in TIERS:
        assert got[t] == pytest.approx(expected[t]), t
    assert sum(got.values()) == pytest.approx(1.0)


def test_tiers_from_buckets_exact_tier_edges_pass_through():
    buckets = [(lo, hi, 1 / 6) for lo, hi in TIER_BOUNDS.values()]
    got = tiers_from_buckets(buckets)
    for t in TIERS:
        assert got[t] == pytest.approx(1 / 6)


def test_tiers_from_buckets_validation():
    with pytest.raises(ValueError, match="sum to"):
        tiers_from_buckets([(None, 659, 0.5), (660, None, 0.4)])
    with pytest.raises(ValueError, match="bad bucket edges"):
        tiers_from_buckets([(700, 650, 1.0)])
    with pytest.raises(ValueError, match="bad bucket edges"):
        tiers_from_buckets([(250, 850, 1.0)])
    with pytest.raises(ValueError, match="no buckets"):
        tiers_from_buckets([])


# --- band_rates_to_tiers (the same rule applied to published rates) ------------------------------------------


def test_band_rates_to_tiers_hand_example():
    bands = [(300, 669, 10.0), (670, 850, 2.0)]
    got = band_rates_to_tiers(bands)
    assert got["deep_subprime"] == got["subprime"] == got["near_prime"] == 10.0
    assert got["prime"] == pytest.approx((10 * 10.0 + 50 * 2.0) / 60)
    assert got["prime_plus"] == got["superprime"] == 2.0


def test_band_rates_to_tiers_requires_full_cover():
    with pytest.raises(ValueError, match="cover"):
        band_rates_to_tiers([(300, 669, 10.0), (700, 850, 2.0)])
    with pytest.raises(ValueError, match="overlap"):
        band_rates_to_tiers([(300, 669, 10.0), (660, 850, 2.0)])
