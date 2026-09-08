"""Shape times level: predicted charge-off for any tier mix, calibrated to the CFPB aggregate.

    predicted(mix, year) = level(year) * sum_over_tiers( mix[tier] * relative_loss[tier] )

`level(year)` is chosen so that the CFPB's own tier mix for that year reproduces the CFPB aggregate
general-purpose charge-off rate for the chosen bureau series. Because every shape is normalised to
prime = 1, `level(year)` is the charge-off rate the shape implies for the prime tier in that year.

Two CFPB series exist and are never spliced: `ccip` (2025 report, FICO-scored panel, 2014-2024) and `ccp`
(2023 report, 2013-2022). They differ by roughly 0.6x on the same years (design/scout-ccmr-tiers.md §3.2),
so a residual computed under one must be compared only with residuals under the same one.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .shapes import load_shapes, shape_vector
from .tiers import TIERS

SERIES = ("ccip", "ccp")
LEVEL_COLUMNS = [
    "year",
    "series",
    "gp_chargeoff_rate",
    "gp_chargeoff_rate_ye",
    "n_periods",
    *[f"share_{t}" for t in TIERS],
    "mix_periods",
    "citation_rate",
    "citation_mix",
]


def data_dir() -> Path:
    """The repo's data/ directory: next to this package when installed editable, else the working directory."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "data" / "ccmr_level.csv").exists() and (parent / "pyproject.toml").exists():
            return parent / "data"
    return Path("data")


def load_level(path: Path | None = None) -> pd.DataFrame:
    path = Path(path) if path is not None else data_dir() / "ccmr_level.csv"
    df = pd.read_csv(path)
    missing = [c for c in LEVEL_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{path}: missing columns {missing}")
    bad = set(df["series"]) - set(SERIES)
    if bad:
        raise ValueError(f"{path}: unknown series {sorted(bad)}")
    if df.duplicated(["year", "series"]).any():
        raise ValueError(f"{path}: duplicate (year, series) rows")
    return df


def default_shapes() -> pd.DataFrame:
    return load_shapes(data_dir() / "loss_shape.csv")


def cfpb_mix(level: pd.DataFrame, year: int, series: str) -> dict[str, float]:
    row = level[(level["year"] == int(year)) & (level["series"] == series)]
    if len(row) != 1:
        have = sorted(level.loc[level["series"] == series, "year"].tolist())
        raise ValueError(f"no {series} level for {year}; years available: {have}")
    r = row.iloc[0]
    return {t: float(r[f"share_{t}"]) for t in TIERS}


def cfpb_rate(level: pd.DataFrame, year: int, series: str) -> float:
    row = level[(level["year"] == int(year)) & (level["series"] == series)]
    if len(row) != 1:
        have = sorted(level.loc[level["series"] == series, "year"].tolist())
        raise ValueError(f"no {series} level for {year}; years available: {have}")
    return float(row.iloc[0]["gp_chargeoff_rate"])


def _mix_dot_shape(mix: dict[str, float], vec: dict[str, float]) -> float:
    unknown = set(mix) - set(TIERS)
    if unknown:
        raise ValueError(f"unknown tiers in mix: {sorted(unknown)}")
    total = sum(float(v) for v in mix.values())
    if abs(total - 1.0) > 1e-5:  # prospectus shares are printed to 0.01 percent; allow a few 1e-5 of slack
        raise ValueError(f"mix shares sum to {total!r}, not 1")
    return sum(float(mix.get(t, 0.0)) * vec[t] for t in TIERS)


def level_for(
    year: int,
    shape_source: str,
    series: str = "ccip",
    *,
    shapes: pd.DataFrame | None = None,
    level: pd.DataFrame | None = None,
) -> float:
    """Calibrated level: CFPB aggregate rate / (CFPB mix . shape). Equals the implied prime-tier rate."""
    shapes = default_shapes() if shapes is None else shapes
    level = load_level() if level is None else level
    vec = shape_vector(shapes, shape_source)
    return cfpb_rate(level, year, series) / _mix_dot_shape(cfpb_mix(level, year, series), vec)


def predict_chargeoff(
    mix: dict[str, float],
    year: int,
    shape_source: str,
    series: str = "ccip",
    *,
    shapes: pd.DataFrame | None = None,
    level: pd.DataFrame | None = None,
) -> float:
    """Predicted annualised gross charge-off rate (fraction) for a pool with tier shares `mix`.

    `mix` maps tier -> share of balances (missing tiers count as zero; shares must sum to 1). `series`
    picks the CFPB panel the level is calibrated to; the answer is only comparable with actual rates on the
    same basis as that panel's aggregate (gross, balance-weighted).
    """
    shapes = default_shapes() if shapes is None else shapes
    level = load_level() if level is None else level
    vec = shape_vector(shapes, shape_source)
    lvl = cfpb_rate(level, year, series) / _mix_dot_shape(cfpb_mix(level, year, series), vec)
    return lvl * _mix_dot_shape(mix, vec)


def calibration_check(
    tol: float = 1e-9,
    *,
    shapes: pd.DataFrame | None = None,
    level: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """For every (year, series, filled shape): feed the CFPB mix back in and require the CFPB rate back.

    Returns one row per check with the absolute error; raises AssertionError if any error exceeds `tol`.
    """
    shapes = default_shapes() if shapes is None else shapes
    level = load_level() if level is None else level
    filled = [
        s
        for s in shapes["shape_source"].unique()
        if not shapes.loc[shapes["shape_source"] == s, "relative_loss"].isna().any()
    ]
    out = []
    for _, r in level.iterrows():
        year, series = int(r["year"]), str(r["series"])
        mix = cfpb_mix(level, year, series)
        target = cfpb_rate(level, year, series)
        for s in filled:
            got = predict_chargeoff(mix, year, s, series, shapes=shapes, level=level)
            out.append(
                {
                    "year": year,
                    "series": series,
                    "shape_source": s,
                    "cfpb_rate": target,
                    "reproduced": got,
                    "abs_err": abs(got - target),
                    "level": level_for(year, s, series, shapes=shapes, level=level),
                }
            )
    df = pd.DataFrame(out)
    worst = df["abs_err"].max() if len(df) else 0.0
    assert worst <= tol, f"calibration off by {worst!r} > {tol!r}:\n{df[df['abs_err'] > tol]}"
    return df
