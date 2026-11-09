"""The card panel regression says when it cannot identify a score-mix gradient.

With one prospectus snapshot per trust, tier shares are constant within a trust: the month-FE fit is saturated
(as many parameters as distinct mixes) and the trust-FE fit is not identified at all. Both used to be printed on
docs/cards.html as estimates, the second with coefficients in the billions.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from absrisk.estimate.cards import TIERS, identification, panel_regression


def _panel(n_trusts: int, months: int = 36, moving: bool = False, seed: int = 0):
    rng = np.random.default_rng(seed)
    per = pd.date_range("2023-01-31", periods=months, freq="ME")
    monthly, mix = [], []
    for t in range(n_trusts):
        base = rng.dirichlet(np.ones(len(TIERS)))
        for i, p in enumerate(per):
            shares = base
            if moving:                                   # a new snapshot every six months
                shares = rng.dirichlet(np.ones(len(TIERS))) if i % 6 == 0 else shares
                base = shares
            mix.append({"trust": f"t{t}", "period_end": p, **dict(zip(TIERS, shares))})
            monthly.append({"trust": f"t{t}", "period_end": p,
                            "gross_co_rate": 0.02 + 0.05 * shares[0] + rng.normal(0, 0.002)})
    return pd.DataFrame(monthly), pd.DataFrame(mix)


def test_one_snapshot_per_trust_is_saturated_and_unidentified():
    monthly, mix = _panel(6)
    _, tidy = panel_regression(monthly, mix)
    st = tidy.drop_duplicates("spec").set_index("spec")["status"].to_dict()
    assert st == {"month_fe": "saturated", "month_and_trust_fe": "not identified"}
    hidden = tidy[tidy["spec"] == "month_and_trust_fe"]
    assert hidden["coef"].isna().all() and hidden["se"].isna().all()
    assert tidy[tidy["spec"] == "month_fe"]["coef"].notna().any()     # kept, but labelled saturated


def test_moving_mixes_across_many_trusts_are_identified():
    monthly, mix = _panel(12, moving=True)
    d = identification(mix.merge(monthly, on=["trust", "period_end"]), [t for t in TIERS if t != "superprime"])
    assert d["month_fe"][0] == "identified" and d["month_and_trust_fe"][0] == "identified"
