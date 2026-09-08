"""The six CFPB credit tiers and the one rule for splitting score buckets across them.

Tier edges are the CFPB Consumer Credit Card Market Report definitions (2023 report PDF p12, 2025 report
PDF p15): deep subprime 579 or less, subprime 580-619, near-prime 620-659, prime 660-719, prime plus
720-799, superprime 800 or greater. Scores are integers on the FICO 300-850 scale.

Straddle rule (used for prospectus buckets, for published score bands, and for anything else that
arrives with edges that do not match the tiers): a bucket is assumed to hold its accounts uniformly over
the integer scores it spans, so a bucket that straddles a tier boundary is split in proportion to the
number of integer scores on each side. This is linear interpolation of the bucket's cumulative share in
score. Nothing finer is published, so nothing finer is assumed.
"""

from __future__ import annotations

from collections.abc import Iterable

TIERS: tuple[str, ...] = ("deep_subprime", "subprime", "near_prime", "prime", "prime_plus", "superprime")

SCORE_MIN = 300
SCORE_MAX = 850

TIER_BOUNDS: dict[str, tuple[int, int]] = {
    "deep_subprime": (SCORE_MIN, 579),
    "subprime": (580, 619),
    "near_prime": (620, 659),
    "prime": (660, 719),
    "prime_plus": (720, 799),
    "superprime": (800, SCORE_MAX),
}

Bucket = tuple[int | None, int | None, float]


def tier_of(score: int) -> str:
    """Tier containing an integer score."""
    for tier, (lo, hi) in TIER_BOUNDS.items():
        if lo <= score <= hi:
            return tier
    raise ValueError(f"score {score} outside {SCORE_MIN}-{SCORE_MAX}")


def _edges(lo: int | None, hi: int | None) -> tuple[int, int]:
    lo = SCORE_MIN if lo is None else int(lo)
    hi = SCORE_MAX if hi is None else int(hi)
    if lo < SCORE_MIN or hi > SCORE_MAX or lo > hi:
        raise ValueError(f"bad bucket edges ({lo}, {hi}); need {SCORE_MIN} <= lo <= hi <= {SCORE_MAX}")
    return lo, hi


def overlap_fraction(lo: int | None, hi: int | None, tier: str) -> float:
    """Share of the integer scores in [lo, hi] that fall inside `tier`. lo=None means 300, hi=None means 850.
    Bounds are inclusive on both sides, so (660, 719) is exactly the prime tier and (720, None) is 720+."""
    lo, hi = _edges(lo, hi)
    tlo, thi = TIER_BOUNDS[tier]
    inter = min(hi, thi) - max(lo, tlo) + 1
    return max(inter, 0) / (hi - lo + 1)


def tiers_from_buckets(buckets: Iterable[Bucket], *, tol: float = 1e-6) -> dict[str, float]:
    """Map score buckets with shares to the six tiers.

    `buckets` is an iterable of (lo, hi, share) with inclusive integer edges; lo=None is an open lower
    bucket ("less than 600" is (None, 599, share)), hi=None an open upper one ("720 and above" is
    (720, None, share)). Shares must sum to 1 within `tol`. A bucket that straddles a tier boundary is
    split in proportion to the number of integer scores on each side (module docstring).

    Buckets for accounts with no score cannot be mapped; drop them and renormalise before calling, and
    record that you did.
    """
    buckets = list(buckets)
    if not buckets:
        raise ValueError("no buckets")
    total = sum(float(s) for _, _, s in buckets)
    if abs(total - 1.0) > tol:
        raise ValueError(f"bucket shares sum to {total!r}, not 1 (tol {tol})")
    out = {t: 0.0 for t in TIERS}
    for lo, hi, share in buckets:
        if share < 0:
            raise ValueError(f"negative share {share!r} for bucket ({lo}, {hi})")
        for tier in TIERS:
            f = overlap_fraction(lo, hi, tier)
            if f:
                out[tier] += float(share) * f
    return out


def band_rates_to_tiers(bands: Iterable[tuple[int | None, int | None, float]]) -> dict[str, float]:
    """Turn a published rate-by-score-band table into a rate per tier.

    Each band's rate is taken as constant over the integer scores it spans; a tier's rate is the
    score-count-weighted average of the band rates over the tier's range (the same straddle rule as
    `tiers_from_buckets`, applied to rates instead of shares). Bands must be non-overlapping and cover
    every tier completely, otherwise ValueError.
    """
    bands = [(*_edges(lo, hi), float(r)) for lo, hi, r in bands]
    bands.sort()
    for (lo1, hi1, _), (lo2, _, _) in zip(bands, bands[1:]):
        if lo2 <= hi1:
            raise ValueError(f"bands overlap at {lo2}")
    out: dict[str, float] = {}
    for tier, (tlo, thi) in TIER_BOUNDS.items():
        width = thi - tlo + 1
        covered = 0
        acc = 0.0
        for lo, hi, rate in bands:
            inter = min(hi, thi) - max(lo, tlo) + 1
            if inter > 0:
                covered += inter
                acc += rate * inter
        if covered != width:
            raise ValueError(f"bands cover {covered} of {width} scores in {tier}")
        out[tier] = acc / width
    return out
