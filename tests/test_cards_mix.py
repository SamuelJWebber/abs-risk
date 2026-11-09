"""The card analysis maps prospectus FICO buckets to tiers through the committed crosswalk, and nowhere else.

REVIEW.md R1-1: the analysis once read an unscored bucket's open edges as 300-850 and spread those balances over
the whole scale (half of them into deep subprime), while the crosswalk it never read said "weight 0, renormalise".
Published residuals moved by up to 0.06 points (BofA, fico_fed2007: +1.07% printed, +1.13% under the rule).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from absrisk.cards.composition import build_crosswalk, read_csv, tier_shares
from absrisk.estimate.run_cards import mix_by_trust
from absrisk.shape import TIERS, tiers_from_buckets

REPO = Path(__file__).resolve().parents[1]
COMPOSITION = REPO / "data" / "cards_composition.csv"
CROSSWALK = REPO / "crosswalks" / "fico_buckets.csv"
COMMITTED_MIX = REPO / "data" / "results" / "cards" / "mix_by_trust.csv"


def _crosswalk_mix() -> dict[str, dict[str, float]]:
    shares = tier_shares(read_csv(COMPOSITION), read_csv(CROSSWALK))
    return {trust: s for (trust, basis), s in shares.items() if basis == "receivables"}


def test_analysis_mix_is_the_crosswalk_mix():
    """Limit case first: the analysis must give exactly the crosswalk's shares, trust by trust."""
    mix = mix_by_trust(pd.read_csv(COMPOSITION), pd.read_csv(CROSSWALK)).set_index("trust")
    want = _crosswalk_mix()
    assert set(mix.index) == set(want)
    for trust, s in want.items():
        for t in TIERS:
            assert mix.loc[trust, t] == pytest.approx(s[t], abs=1e-9), (trust, t)
        assert mix.loc[trust, "unscored"] == pytest.approx(s["unscored"], abs=1e-12), trust


def test_committed_mix_is_the_crosswalk_mix():
    """The published mix (data/results/cards/mix_by_trust.csv) is the crosswalk mix. Before the fix BofA's deep
    subprime share was 0.0034 too high, which is what moved its residual."""
    mix = pd.read_csv(COMMITTED_MIX).set_index("trust")
    for trust, s in _crosswalk_mix().items():
        for t in TIERS:
            assert mix.loc[trust, t] == pytest.approx(s[t], abs=1e-9), (trust, t)


def test_unscored_balances_are_dropped_not_spread():
    comp = pd.DataFrame([
        {"trust": "x", "as_of": "2026-01-31", "table": "fico", "bucket_lo": None, "bucket_hi": None,
         "share_receivables": 0.5, "share_accounts": None, "score_type": "FICO", "sample_note": "n; bucket: unscored",
         "bucket_label": "No score"},
        {"trust": "x", "as_of": "2026-01-31", "table": "fico", "bucket_lo": 660, "bucket_hi": 719,
         "share_receivables": 0.5, "share_accounts": None, "score_type": "FICO", "sample_note": "n",
         "bucket_label": "660-719"},
    ])
    xw = pd.DataFrame(build_crosswalk([{**r, "bucket_lo": "" if pd.isna(r["bucket_lo"]) else r["bucket_lo"],
                                        "bucket_hi": "" if pd.isna(r["bucket_hi"]) else r["bucket_hi"]}
                                       for r in comp.to_dict("records")]))
    m = mix_by_trust(comp, xw).iloc[0]
    assert m["prime"] == pytest.approx(1.0)              # half the book unscored: the other half is all of the mix
    assert m["deep_subprime"] == 0.0                      # not 0.5 * 280/551 as when unscored was read as 300-850
    assert m["unscored"] == pytest.approx(0.5)
    assert m["sample_note"] == "n"


def test_all_unscored_is_an_error_row_and_a_missing_crosswalk_row_raises():
    comp = pd.DataFrame([{"trust": "x", "as_of": "2026-01-31", "table": "fico", "bucket_lo": None, "bucket_hi": None,
                          "share_receivables": 1.0, "share_accounts": None, "score_type": "FICO", "sample_note": "",
                          "bucket_label": "No score"}])
    xw = pd.DataFrame([{"trust": "x", "bucket_label": "No score", **{f"w_{t}": 0.0 for t in TIERS}}])
    m = mix_by_trust(comp, xw).iloc[0]
    assert "no scored bucket" in m["error"] and m["unscored"] == 1.0
    with pytest.raises(ValueError, match="crosswalk has no row"):
        mix_by_trust(comp, xw.assign(bucket_label="Unscored"))


def test_tiers_from_buckets_refuses_an_unscored_bucket():
    with pytest.raises(ValueError, match="unscored"):
        tiers_from_buckets([(None, None, 0.01), (660, None, 0.99)])


def test_committed_crosswalk_is_the_rule_applied_to_the_committed_composition():
    """The two committed files cannot drift apart: the crosswalk is build_crosswalk() of the composition table."""
    built = build_crosswalk(read_csv(COMPOSITION))
    committed = read_csv(CROSSWALK)
    assert [(r["trust"], r["bucket_label"]) for r in committed] == [(r["trust"], r["bucket_label"]) for r in built]
    for a, b in zip(committed, built):
        assert (a["rule"], a["flags"]) == (b["rule"], b["flags"]), a["bucket_label"]
        for t in TIERS:
            assert float(a[f"w_{t}"]) == pytest.approx(b[f"w_{t}"], abs=1e-6), (a["trust"], a["bucket_label"], t)
