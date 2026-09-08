"""Loss shape by credit tier (Track A, task A3): published relative-loss shapes and CFPB-calibrated level.

    from absrisk.shape import predict_chargeoff, tiers_from_buckets
    mix = tiers_from_buckets([(None, 599, 0.05), (600, 659, 0.10), (660, 719, 0.30), (720, None, 0.55)])
    predict_chargeoff(mix, 2023, "fico_odds")        # annualised gross charge-off rate, CCIP basis

Data: data/loss_shape.csv (shapes, built by `shapes.build_loss_shape`) and data/ccmr_level.csv (level,
built by `python -m absrisk.shape.build_level` from the CFPB workbooks). Sources: design/shape-sources.md.
"""

from .level import (
    SERIES,
    calibration_check,
    cfpb_mix,
    cfpb_rate,
    data_dir,
    default_shapes,
    level_for,
    load_level,
    predict_chargeoff,
)
from .shapes import build_loss_shape, load_shapes, shape_vector, write_loss_shape
from .tiers import TIER_BOUNDS, TIERS, band_rates_to_tiers, overlap_fraction, tier_of, tiers_from_buckets

__all__ = [
    "SERIES",
    "TIERS",
    "TIER_BOUNDS",
    "band_rates_to_tiers",
    "build_loss_shape",
    "calibration_check",
    "cfpb_mix",
    "cfpb_rate",
    "data_dir",
    "default_shapes",
    "level_for",
    "load_level",
    "load_shapes",
    "overlap_fraction",
    "predict_chargeoff",
    "shape_vector",
    "tier_of",
    "tiers_from_buckets",
    "write_loss_shape",
]
