"""The survival clock: age since origination with delayed entry, pool-cutoff lag, and exit dating."""

import pandas as pd

from absrisk.estimate.survival import ages, cumulative_incidence


def _loans():
    return pd.DataFrame({
        "deal": ["d"] * 5,
        "asset_id": list("abcde"),
        "orig_month": ["2025-12-01", "2025-06-01", "2026-01-01", "2024-01-01", "2026-02-01"],
        "first_period": ["2026-04-30"] * 4 + ["2026-06-30"],          # e was added to the pool later
        "last_period": ["2026-07-31"] * 5,
        "months_observed": [4, 4, 4, 4, 2],
        "exit_type": ["prepay", "chargeoff", "censored", "prepay", "censored"],
        "exit_period": ["2026-04-30", "2026-06-30", None, "2026-05-31", None],
        "zb_date": ["2026-03-01", "2026-06-01", None, None, None],       # a left before the first report
        "score": [700, 600, 650, 720, 680],
    })


def test_ages_delayed_entry_and_cutoff_lag():
    a = ages(_loans())
    # the first file carries an exit dated March, so every loan present in the April file entered in March
    assert a.loc[0, "entry_age"] == 3          # Dec 2025 -> Mar 2026
    assert a.loc[0, "exit_age"] == 3           # exited in the entry month
    assert a.loc[1, "entry_age"] == 9 and a.loc[1, "exit_age"] == 12 and a.loc[1, "event"] == "chargeoff"
    assert a.loc[2, "entry_age"] == 2 and a.loc[2, "exit_age"] == 6 and a.loc[2, "event"] == "censored"   # Jan 2026 -> Jul 2026
    assert a.loc[3, "entry_age"] == 26 and a.loc[3, "exit_age"] == 28 and a.loc[3, "event"] == "prepay"   # exit_period May, no zb_date
    # e joined in June with no lag applied (not in the first file): entry = Jun - Feb = 4, censored at Jul = 5
    assert a.loc[4, "entry_age"] == 4 and a.loc[4, "exit_age"] == 5


def test_life_table_respects_left_truncation():
    cif = cumulative_incidence(_loans(), by=["deal"], horizon=30)
    # nobody is at risk at age 0 or 1 (youngest entry is 2), so incidence stays zero there
    assert cif.loc[cif["age"] <= 1, "at_risk"].eq(0).all()
    assert cif.loc[cif["age"] == 3, "at_risk"].iloc[0] == 2          # a (3..3) and c (2..8) at age 3
    assert cif.loc[cif["age"] == 12, "d_chargeoff"].iloc[0] == 1
    assert cif["aj_chargeoff"].iloc[-1] > 0


def test_fallback_without_dates_uses_months_observed():
    df = pd.DataFrame({"months_observed": [3, 5], "exit_type": ["chargeoff", "censored"]})
    a = ages(df)
    assert list(a["entry_age"]) == [0, 0] and list(a["exit_age"]) == [3, 5]
