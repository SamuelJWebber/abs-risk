"""The card stage decomposition multiplies back, and the direction test compares months that were really tight.

REVIEW.md R1-5: the conclusions page printed loss = entry x conversion and tabled two factors whose product was not
the charge-off rate (Amex 0.74% x 44.9% = 0.33%, not 0.153%): progression was missing, and arithmetic means of each
factor do not multiply back. R1-4: the "direction test" compared pre-covid 2019 with a "squeeze" in which every
trust's delinquency was lower, and printed "fell for none".
"""

from __future__ import annotations

import re
from html import unescape
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from absrisk.estimate import cards_roll

REPO = Path(__file__).resolve().parents[1]
RESULTS = REPO / "data" / "results" / "cards"


def _text(path: Path) -> str:
    return unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", path.read_text(encoding="utf-8"))))


def _panel(seed: int = 0, months: int = 60) -> pd.DataFrame:
    """Two trusts; delinquency cycles; trust 'a' converts less when the cycle is high (what priority predicts)."""
    rng = np.random.default_rng(seed)
    per = pd.date_range("2020-01-31", periods=months, freq="ME")
    cyc = 1 + 0.4 * np.sin(np.arange(months) / 6)
    rows = []
    for trust, e0, conv0, slope in (("a", 0.008, 0.45, -0.25), ("b", 0.025, 0.33, 0.0)):
        for i, p in enumerate(per):
            entry = e0 * cyc[i] * np.exp(rng.normal(0, 0.02))
            prog = 0.5 * np.exp(rng.normal(0, 0.02))
            conv = conv0 * (1 + slope * (cyc[i] - 1)) * np.exp(rng.normal(0, 0.02))
            rows.append({"trust": trust, "period_end": p.date().isoformat(), "gross_co_rate": entry * prog * conv * 12,
                         "delinq_30plus_share": entry, "delinq_90plus_share": entry * prog, "co_annualisation": "x12"})
    return pd.DataFrame(rows)


def test_trust_averages_multiply_back_and_shares_sum_to_one():
    bt = cards_roll.by_trust(cards_roll.stages(pd.read_csv(REPO / "data" / "cards_monthly.csv")))
    assert np.allclose(bt["entry"] * bt["progression"] * bt["conversion"], bt["co_monthly"], rtol=1e-12)
    s = (bt["entry_share_of_gap"] + bt["progression_share_of_gap"] + bt["conversion_share_of_gap"]).dropna()
    assert np.allclose(s, 1.0, atol=1e-12) and len(s) == len(bt) - 1


def test_committed_card_stage_table_is_exact():
    bt = pd.read_csv(RESULTS / "a3_by_trust.csv")
    assert np.allclose(bt["entry"] * bt["progression"] * bt["conversion"], bt["co_monthly"], rtol=1e-9)
    assert {"progression_ratio", "progression_share_of_gap"} <= set(bt.columns)


def test_regimes_split_by_delinquency_and_find_the_priority_sign():
    st = cards_roll.stages(_panel())
    reg = cards_roll.regimes(st)
    assert set(reg["regime"]) == {"loose", "tight"}
    ix = reg.drop_duplicates("regime").set_index("regime")
    assert ix.loc["tight", "index_mean"] > 1 > ix.loc["loose", "index_mean"]
    assert ix.loc["tight", "calendar_months"] + ix.loc["loose", "calendar_months"] == 60
    d = cards_roll.direction_summary(pd.DataFrame(), reg, [])
    assert d["regime"]["fell"] == ["a"] and d["verdict"] == "priority"


def test_a_calendar_label_is_not_a_squeeze():
    st = cards_roll.stages(_panel())
    # 'later' has lower delinquency than 'early' for both trusts: comparing them is not a tightening
    periods = {"early": ("2020-01-01", "2020-12-31"), "later": ("2023-06-01", "2024-12-31")}
    s = cards_roll.stress_test(st, periods)
    ent = s.pivot_table(index="trust", columns="period", values="entry")
    d = cards_roll.direction_summary(s, pd.DataFrame(), list(periods))
    if (ent["later"] < ent["early"]).all():
        assert d["endpoints"]["looser"] and not d["endpoints"]["tighter"] and d["tightenings"] == []
    for t in d["tightenings"]:
        assert t["rise_min"] > 1                    # a listed tightening raised every trust's 30+ share


def test_committed_direction_test_uses_real_tightenings():
    s = pd.read_csv(RESULTS / "a3_stress.csv")
    reg = pd.read_csv(RESULTS / "a3_regimes.csv")
    order = [p for p in ("pre-covid 2019", "stimulus 2020-21", "normalising 2022-23H1", "squeeze 2023H2 on") if p in set(s["period"])]
    d = cards_roll.direction_summary(s, reg, order)
    ent = s.pivot_table(index="trust", columns="period", values="entry")
    for t in d["tightenings"]:
        assert (ent[t["to"]] > ent[t["from"]]).all()
    tight = reg[reg["regime"] == "tight"]["index_mean"].iloc[0]
    loose = reg[reg["regime"] == "loose"]["index_mean"].iloc[0]
    assert tight > loose


@pytest.mark.parametrize("page", ["cards.html", "conclusions.html"])
def test_pages_print_three_factors_and_no_fell_for_none_from_a_loosening(page):
    t = _text(REPO / "docs" / page)
    assert "progression" in t
    assert "fell for none" not in t                     # the old claim, computed from a loosening
    assert "30-plus share" in t and "tight" in t        # the delinquency behind each comparison is printed


def test_conclusions_identity_is_three_factors():
    t = _text(REPO / "docs" / "conclusions.html")
    assert re.search(r"monthly charge-off\s*=\s*entry.*x\s*progression.*x\s*conversion", t)
    assert "share of balances 90 or more days late" in t
