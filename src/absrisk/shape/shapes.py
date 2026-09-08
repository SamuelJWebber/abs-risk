"""Relative loss by credit tier: the published sources, transcribed, and their mapping to the six tiers.

Every number here was read from the cited page on 2026-09-08; copies of the pages are under
tests/fixtures/shape/. The mapping from a source's score bands to the six CFPB tiers is
`absrisk.shape.tiers.band_rates_to_tiers` (one straddle rule for the whole project). `relative_loss` is the
tier's rate divided by the prime tier's rate, so prime = 1.0 in every shape. design/shape-sources.md
discusses what each shape measures and where it falls short.

Shapes:
- fico_odds        Experian's per-band "likely to become seriously delinquent" figures for FICO Score ranges.
- fico_fed2007     Fair Isaac's two-year default rate by FICO band on new accounts opened Oct 2000-Apr 2001,
                   as reproduced in the Federal Reserve's 2007 Report to Congress on credit scoring.
- acms2018         Agarwal, Chomsisengphet, Mahoney and Stroebel (QJE 2018), Table IV: cumulative net
                   charge-offs per account over the first 24 months divided by average daily balances, by
                   origination-FICO group, for cards originated 2008-2013 at the eight largest US banks.
- acms2018_dpd90   Same table, cumulative probability of 90+ days past due within 24 months (per account).
- autos_b1         Placeholder; filled by Track B from the auto loan-level panel.
"""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

from .tiers import TIER_BOUNDS, TIERS, band_rates_to_tiers

COLUMNS = [
    "shape_source",
    "tier",
    "tier_lo",
    "tier_hi",
    "source_rate",
    "source_unit",
    "relative_loss",
    "flag",
    "note",
    "citation",
]

FIXTURES = "tests/fixtures/shape/"

# --- fico_odds: Experian, "NNN Credit Score: Is it Good or Bad?" pages ---------------------------------------
# One page per FICO band, fetched 2026-09-08; visible text saved as experian_<score>_credit_score.txt.
# Band edges are Experian's stated FICO Score ranges (Very Poor 300-579, Fair 580-669, Good 670-739,
# Very Good 740-799, Exceptional 800-850). Rates are the percentages in the quoted sentences.
EXPERIAN_URL = "https://www.experian.com/blogs/ask-experian/credit-education/score-basics/{score}-credit-score/"
FICO_ODDS_BANDS = [
    # (lo, hi, rate_pct, page score, verbatim sentence, flag)
    (300, 579, 62.0, 550,
     "Roughly 62% of consumers with credit scores under 579 are likely to become seriously delinquent "
     "(i.e., go more than 90 days past due on a debt payment) in the future.", ""),
    (580, 669, 28.0, 620,
     "Statistically speaking, 28% of consumers with credit scores in the Fair range are likely to become "
     "seriously delinquent in the future.", ""),
    (670, 739, 9.0, 700,
     "Approximately 9% of consumers with Good FICO Scores are likely to become seriously delinquent in the "
     "future.", ""),
    (740, 799, 1.0, 760,
     "Approximately 1% of consumers with Very Good FICO Scores are likely to become seriously delinquent in "
     "the future.", ""),
    (800, 850, 1.0, 810,
     "Less than 1% of consumers with Exceptional FICO Scores are likely to become seriously delinquent in the "
     "future.", "upper_bound"),
]
FICO_ODDS_UNIT = "percent of consumers in the band likely to become 90+ days past due on any debt (Experian)"
FICO_ODDS_CITATION = (
    "Experian, 'NNN Credit Score: Is it Good or Bad?' series, one page per FICO Score range, fetched "
    "2026-09-08: " + ", ".join(EXPERIAN_URL.format(score=s) for s in (550, 620, 700, 760, 810))
    + f" (visible text saved as {FIXTURES}experian_<score>_credit_score.txt). Band edges are Experian's "
    "stated ranges; the Exceptional band says 'less than 1%' and is carried at the bound 1.0."
)

# --- fico_fed2007: Fair Isaac default rates in the Federal Reserve's 2007 credit-scoring report --------------
FED2007_URL = "https://www.federalreserve.gov/boarddocs/rptcongress/creditscore/general_tables.htm"
FICO_FED2007_BANDS = [
    # (lo, hi, rate_pct, label as printed)
    (300, 519, 41.0, "Less than 520"),
    (520, 559, 28.4, "520-559"),
    (560, 599, 22.5, "560-599"),
    (600, 639, 15.8, "600-639"),
    (640, 679, 8.9, "640-679"),
    (680, 719, 4.4, "680-719"),
    (720, 850, 1.0, "720 or more"),
]
FICO_FED2007_UNIT = (
    "percent of new accounts (opened Oct 2000-Apr 2001) 90+ days delinquent or with other derogatory "
    "information within the two years from Oct 2000 (Fair Isaac Corp.)"
)
FICO_FED2007_CITATION = (
    "Board of Governors of the Federal Reserve System, 'Report to the Congress on Credit Scoring and Its "
    "Effects on the Availability and Affordability of Credit' (August 2007), Tables for General Background, "
    "Table 2 'Default Rate on New Loans for the Two Years after Origination, by FICO Credit Score, October "
    f"2000 to October 2002', Source: Fair Isaac Corp.; {FED2007_URL} (fetched 2026-09-08, copy at "
    f"{FIXTURES}fed2007_creditscore_general_tables.htm)"
)

# --- acms2018: Agarwal, Chomsisengphet, Mahoney, Stroebel, QJE 133(1) 2018, Table IV ------------------------
# Table IV "Quasi-experiment-level summary statistics, post origination", QJE pp. 154-155 (PDF pp. 26-27 of
# the Stern copy). Values are means across the 743 credit-limit quasi-experiments of the account-level mean
# within 5 FICO points of the cutoff, at 12/24/36/48/60 months after origination; FICO groups are by score
# at origination. "Chargeoffs" are gross charge-offs minus recoveries (paper fn 29). Data: OCC Credit Card
# Metrics, eight largest US banks, accounts originated January 2008 to November 2013, observed to Dec 2014.
ACMS_URL = "https://pages.stern.nyu.edu/~jstroebe/PDF/ACMS_Passthrough.pdf"
ACMS_HORIZONS = (12, 24, 36, 48, 60)
ACMS_GROUPS = {  # group label -> inclusive score edges on the 300-850 scale
    "<=660": (300, 660),
    "661-700": (661, 700),
    "701-740": (701, 740),
    ">740": (741, 850),
}
ACMS_TABLE4 = {
    "cumulative_chargeoffs_usd": {
        "<=660": (47, 178, 306, 403, 483),
        "661-700": (67, 259, 443, 552, 634),
        "701-740": (61, 245, 403, 524, 602),
        ">740": (35, 124, 190, 261, 322),
    },
    "adb_usd": {
        "<=660": (1260, 1065, 1164, 1079, 1050),
        "661-700": (2160, 1794, 1734, 1501, 1465),
        "701-740": (2197, 1719, 1481, 1260, 1097),
        ">740": (2101, 1524, 1343, 1064, 1084),
    },
    "cumulative_prob_90dpd_pct": {
        "<=660": (4.8, 10.2, 13.2, 14.5, 15.2),
        "661-700": (3.3, 8.1, 10.9, 12.2, 12.9),
        "701-740": (2.9, 7.2, 9.7, 10.9, 11.5),
        ">740": (1.3, 3.2, 4.5, 5.1, 5.4),
    },
    "cumulative_prob_60dpd_pct": {
        "<=660": (6.4, 12.0, 15.1, 16.5, 17.2),
        "661-700": (4.1, 9.3, 12.2, 13.6, 14.4),
        "701-740": (3.6, 8.2, 10.9, 12.2, 12.9),
        ">740": (1.6, 3.8, 5.2, 5.9, 6.2),
    },
}
ACMS_CITATION = (
    "Agarwal, Chomsisengphet, Mahoney and Stroebel, 'Do Banks Pass Through Credit Expansions to Consumers "
    "Who Want to Borrow?', Quarterly Journal of Economics 133(1), 2018, pp. 129-190, Table IV "
    "'Quasi-experiment-level summary statistics, post origination', pp. 154-155, rows {rows} by FICO score "
    f"group; {ACMS_URL} (PDF pp. 26-27; copy at {FIXTURES}acms2018_passthrough_stern.pdf, page text at "
    f"{FIXTURES}acms2018_table4_pages154-155.txt)"
)


def acms_chargeoff_rate(group: str, months: int = 24) -> float:
    """Annualised net charge-off rate per dollar of balance over the first `months` months.

    Cumulative charge-offs per account at the horizon divided by the sum of the average daily balances
    reported at each 12-month horizon up to it (each ADB value stands for one year of balance). Fraction.
    """
    if months not in ACMS_HORIZONS:
        raise ValueError(f"months must be one of {ACMS_HORIZONS}")
    k = ACMS_HORIZONS.index(months)
    co = ACMS_TABLE4["cumulative_chargeoffs_usd"][group][k]
    adb = sum(ACMS_TABLE4["adb_usd"][group][: k + 1])
    return co / adb


def acms_group_rates(basis: str = "chargeoff", months: int = 24) -> dict[str, float]:
    if basis == "chargeoff":
        return {g: acms_chargeoff_rate(g, months) for g in ACMS_GROUPS}
    if basis == "dpd90":
        k = ACMS_HORIZONS.index(months)
        return {g: ACMS_TABLE4["cumulative_prob_90dpd_pct"][g][k] for g in ACMS_GROUPS}
    raise ValueError("basis must be 'chargeoff' or 'dpd90'")


def _tier_flags(bands: list[tuple[int, int, float, str]]) -> dict[str, str]:
    """Mechanical flags: which source bands feed each tier, and whether one band covers several tiers."""
    flags: dict[str, list[str]] = {t: [] for t in TIERS}
    for tier, (tlo, thi) in TIER_BOUNDS.items():
        hits = [(lo, hi, f) for lo, hi, _, f in bands if min(hi, thi) >= max(lo, tlo)]
        if len(hits) > 1:
            flags[tier].append("straddle_split:" + "|".join(f"{lo}-{hi}" for lo, hi, _ in hits))
        else:
            lo, hi, _ = hits[0]
            others = [t for t, (a, b) in TIER_BOUNDS.items() if t != tier and lo <= a and b <= hi]
            if others:
                flags[tier].append(f"band_{lo}-{hi}_also_covers:" + "+".join(others))
        for lo, hi, f in hits:
            if f:
                flags[tier].append(f"{f}:{lo}-{hi}")
    return {t: ";".join(v) for t, v in flags.items()}


def _rows(shape_source, bands, unit, note, citation) -> list[dict]:
    """bands: (lo, hi, rate, flag). Rates in the source's unit; relative_loss normalised to prime."""
    rates = band_rates_to_tiers([(lo, hi, r) for lo, hi, r, _ in bands])
    flags = _tier_flags(bands)
    prime = rates["prime"]
    return [
        {
            "shape_source": shape_source,
            "tier": t,
            "tier_lo": TIER_BOUNDS[t][0],
            "tier_hi": TIER_BOUNDS[t][1],
            "source_rate": round(rates[t], 6),
            "source_unit": unit,
            "relative_loss": round(rates[t] / prime, 6),
            "flag": flags[t],
            "note": note,
            "citation": citation,
        }
        for t in TIERS
    ]


def build_loss_shape() -> pd.DataFrame:
    rows: list[dict] = []

    rows += _rows(
        "fico_odds",
        [(lo, hi, r, f) for lo, hi, r, _, _, f in FICO_ODDS_BANDS],
        FICO_ODDS_UNIT,
        "Consumer-level, any-account, 90+ DPD incidence; not a card charge-off rate and not balance-weighted. "
        "Band 580-669 spans subprime and near-prime, so those two tiers carry the same value. Undated by the "
        "source.",
        FICO_ODDS_CITATION,
    )

    rows += _rows(
        "fico_fed2007",
        [(lo, hi, r, "") for lo, hi, r, _ in FICO_FED2007_BANDS],
        FICO_FED2007_UNIT,
        "Account-level two-year default (90+ DPD or other derogatory) on new accounts of all types opened "
        "Oct 2000-Apr 2001; not card-specific, not balance-weighted, 2000-2002 vintage. The top band '720 or "
        "more' spans prime plus and superprime, so those two tiers carry the same value.",
        FICO_FED2007_CITATION,
    )

    co = acms_group_rates("chargeoff", 24)
    rows += _rows(
        "acms2018",
        [(lo, hi, co[g], "") for g, (lo, hi) in ACMS_GROUPS.items()],
        "annual net charge-off rate on balances over months 1-24 after origination: cumulative chargeoffs "
        "($, gross minus recoveries) at 24 months / (ADB at 12 months + ADB at 24 months); fraction",
        "Card-level and balance-weighted, but a selected sample: new accounts within 5 FICO points of a "
        "credit-limit cutoff at the eight largest US banks, originated Jan 2008-Nov 2013, first two years of "
        "life. The coarse '<=660' group cannot separate deep subprime, subprime and near-prime; all three carry "
        "its value, and the cutoffs in that group cluster near 660, so it understates deep subprime.",
        ACMS_CITATION.format(rows="'Cumulative chargeoffs ($)' and 'ADB ($)' after 12 and 24 months"),
    )

    p90 = acms_group_rates("dpd90", 24)
    rows += _rows(
        "acms2018_dpd90",
        [(lo, hi, p90[g], "") for g, (lo, hi) in ACMS_GROUPS.items()],
        "percent of accounts 90+ days past due at least once within 24 months of origination",
        "Same sample and groups as acms2018; per-account incidence on the treated card instead of dollars "
        "charged off per dollar of balance. Same coarse-group caveat for the three lowest tiers.",
        ACMS_CITATION.format(rows="'Cumulative prob 90+ DPD (%)' after 24 months"),
    )

    for t in TIERS:
        rows.append(
            {
                "shape_source": "autos_b1",
                "tier": t,
                "tier_lo": TIER_BOUNDS[t][0],
                "tier_hi": TIER_BOUNDS[t][1],
                "source_rate": math.nan,
                "source_unit": "",
                "relative_loss": math.nan,
                "flag": "placeholder",
                "note": "filled by Track B: cumulative charge-off by 20-point score bucket from the auto "
                "loan-level panel (design/analysis-plan.md, estimator B1/B4)",
                "citation": "",
            }
        )

    return pd.DataFrame(rows, columns=COLUMNS)


def write_loss_shape(path: Path) -> pd.DataFrame:
    df = build_loss_shape()
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, lineterminator="\n")
    return df


def load_shapes(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"flag": str, "note": str, "citation": str, "source_unit": str})
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{path}: missing columns {missing}")
    for c in ("flag", "note", "citation", "source_unit"):
        df[c] = df[c].fillna("")
    return df


def shape_vector(shapes: pd.DataFrame, shape_source: str) -> dict[str, float]:
    """relative_loss by tier for one shape; ValueError if the shape is missing, incomplete or a placeholder."""
    sub = shapes[shapes["shape_source"] == shape_source]
    if sub.empty:
        raise ValueError(f"unknown shape_source {shape_source!r}; have {sorted(shapes['shape_source'].unique())}")
    vec = dict(zip(sub["tier"], sub["relative_loss"].astype(float)))
    if set(vec) != set(TIERS):
        raise ValueError(f"{shape_source}: tiers {sorted(vec)} != {sorted(TIERS)}")
    if any(math.isnan(v) for v in vec.values()):
        raise ValueError(f"{shape_source}: relative_loss not filled (placeholder)")
    return {t: vec[t] for t in TIERS}
