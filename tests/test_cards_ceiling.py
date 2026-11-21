"""Conversion is not the fate of late accounts (REVIEW.md abs-A-2 and abs-B-2).

The limit case: a trust where every charge-off ages through delinquency. An account is written off at 180 days late,
so the month before it sat in the last delinquency bucket, and a month's charge-offs can never exceed what that bucket
held. Chase's are 1.2 times it, month after month, because the prospectuses allow an earlier write-off on bankruptcy
or death. The pages read charge-off over 90-day-late balances as "how often late accounts end in loss" and concluded
that American Express's high ratio was the opposite of protection. `cards_roll.ceiling` is the check that the ratio
cannot carry that reading, and the pages now print it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from absrisk.estimate import cards_roll

REPO = Path(__file__).resolve().parents[1]
RESULTS = REPO / "data" / "results" / "cards"


def _trust(trust: str, bucket: str, key: str, factor: float, months: int = 12, unit: float = 1.0) -> pd.DataFrame:
    """A trust whose last bucket holds 100 every month-end and whose charge-offs are `factor` times that."""
    per = pd.date_range("2024-01-31", periods=months, freq="ME")
    rows = []
    for p in per:
        inputs = {key: 100.0 * factor / unit, "delinquency_buckets": {"90-119": 300.0, bucket: 100.0}}
        rows.append({"trust": trust, "period_end": p.date().isoformat(), "net_co_rate": 0.02,
                     "row_labels_json": json.dumps({"inputs": inputs})})
    return pd.DataFrame(rows)


def test_charge_offs_that_all_age_through_cannot_exceed_the_last_bucket():
    c = cards_roll.ceiling(_trust("chase", "150-179", "gross_losses", 0.9)).iloc[0]
    assert c["months"] == 11                                        # the first month has no month before it
    assert c["chargeoff_over_bucket"] == pytest.approx(0.9) and c["min_share_not_aged"] == 0.0
    assert c["share_months_above_one"] == 0.0 and c["basis"] == "gross"


def test_an_excess_over_the_bucket_is_a_lower_bound_on_unaged_charge_offs():
    c = cards_roll.ceiling(_trust("chase", "150-179", "gross_losses", 1.25)).iloc[0]
    assert c["chargeoff_over_one_month"] == pytest.approx(1.25)
    assert c["min_share_not_aged"] == pytest.approx(0.2)            # 1 - 1/1.25
    assert c["share_months_above_one"] == 1.0


def test_a_bucket_of_two_cohorts_is_compared_one_cohort_at_a_time_and_units_are_applied():
    a = cards_roll.ceiling(_trust("amex", "120+", "defaulted_amount", 0.7)).iloc[0]
    assert a["bucket_months"] == 2 and a["chargeoff_over_bucket"] == pytest.approx(0.7)
    assert a["chargeoff_over_one_month"] == pytest.approx(1.4)
    b = cards_roll.ceiling(_trust("bofa", "150-179", "total_charge_offs_thousands", 1.1, unit=1000.0)).iloc[0]
    assert b["chargeoff_over_bucket"] == pytest.approx(1.1)


def test_a_gap_in_the_months_is_not_compared_across():
    d = _trust("chase", "150-179", "gross_losses", 1.0, months=6).drop(index=3)      # April missing
    assert cards_roll.ceiling(d).iloc[0]["months"] == 3                              # Feb, Mar, Jun; not May


def test_committed_ceiling_table_shows_charge_offs_above_the_last_bucket():
    c = pd.read_csv(RESULTS / "a3_ceiling.csv").set_index("trust")
    assert set(c.index) == {"amex", "bofa", "chase", "citi", "comet", "synchrony"}
    assert c.loc["chase", "chargeoff_over_one_month"] > 1.15 and c.loc["chase", "share_months_above_one"] > 0.9
    assert c.loc["chase", "min_share_not_aged"] > 0.13
    assert c.loc["amex", "bucket_months"] == 2 and 0.6 < c.loc["amex", "chargeoff_over_bucket"] < 0.8
    assert c.loc["citi", "basis"] == "net" and (c.drop(index="citi")["basis"] == "gross").all()
    assert (c["months"] >= 85).all()
    rebuilt = cards_roll.ceiling(pd.read_csv(REPO / "data" / "cards_monthly.csv")).set_index("trust")
    assert rebuilt["chargeoff_over_bucket"].round(8).equals(c["chargeoff_over_bucket"].round(8))


def test_stages_run_on_the_named_rate_column():
    m = pd.DataFrame({"trust": ["a", "a"], "period_end": ["2024-01-31", "2024-02-29"], "co_annualisation": ["x12", "x12"],
                      "gross_co_rate": [0.06, 0.06], "net_co_rate": [0.048, 0.048],
                      "delinq_30plus_share": [0.02, 0.02], "delinq_90plus_share": [0.01, 0.01]})
    net, gross = cards_roll.stages(m), cards_roll.stages(m, "gross_co_rate")
    assert net["co_monthly"].iloc[0] == pytest.approx(0.004) and gross["co_monthly"].iloc[0] == pytest.approx(0.005)
    assert (net["identity_error"] < 1e-15).all() and (gross["identity_error"] < 1e-15).all()
