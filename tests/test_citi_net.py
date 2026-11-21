"""Citi's monthly rate is a NET loss rate, and all six trusts are compared on net (REVIEW.md abs-B-1).

The limit case: one trust reports losses after recoveries and five before. Recoveries run a fifth to a third of gross
charge-offs, so the net trust looks a fifth to a third better than it is and drops down any ranking. That is what
the cards page published until 2026-11-21: Citi's "Credit Loss Component" was stored as gross_co_rate and ranked
fifth of six. The component equals the monthly net-loss table in Citi's own prospectus, checked here against the
committed copy of that prospectus, and the analysis now reads the net rate for every trust.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

import pandas as pd
import pytest

from absrisk.estimate import cards_roll, run_cards
from absrisk.report import cards_page

REPO = Path(__file__).resolve().parents[1]
PROSPECTUS = REPO / "tests" / "fixtures" / "cards" / "citi" / "prospectus" / "0001193125-25-144490" / "d945716d424b2.htm"
RESULTS = REPO / "data" / "results" / "cards"
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def _rows(path: Path) -> str:
    """The document as text, one table row per line, cells separated by '|'."""
    raw = path.read_text(encoding="utf-8", errors="replace").replace("\r", " ").replace("\n", " ")
    raw = re.sub(r"(?i)</tr>", "\n", raw)
    raw = re.sub(r"(?i)</(td|th)>", "|", raw)
    raw = re.sub(r"(?s)<[^>]+>", "", raw)
    return re.sub(r"[ \t]+", " ", html.unescape(raw).replace("\xa0", " "))


def _flat(path: Path) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", path.read_text(encoding="utf-8", errors="replace"))).replace("\xa0", " "))


def prospectus_net_losses() -> pd.Series:
    """Total row of 'Net Losses by Year of Account Origination (by Monthly Due Period)', percent, indexed by YYYY-MM."""
    txt = _rows(PROSPECTUS)
    i = txt.find("Net Losses by Year of Account Origination")
    assert i > 0
    seg = txt[i:i + 60000]
    months, totals, cur = [], [], None
    for row in (r for r in seg.split("\n") if r.strip()):
        cells = [c.strip() for c in row.split("|")]
        flat = " ".join(cells)
        hdr = re.findall(r"(" + "|".join(MONTHS) + r")\s*(20\d\d)", flat)
        if "Origination" in flat and hdr:
            cur = [f"{y}-{MONTHS.index(m) + 1:02d}" for m, y in hdr]
            if "Principal" in flat and len(cur) > 1 and cur[0] == cur[1]:      # the balance column repeats a month
                cur = cur[1:]
            continue
        if cells and cells[0] == "Total" and cur:
            vals = [float(v) for v in re.findall(r"(?<![\d,])(\d{1,2}\.\d{2})(?![\d,])", flat)]
            if len(vals) == len(cur):
                months += cur
                totals += vals
            cur = None
    return pd.Series(totals, index=months).groupby(level=0).first()


@pytest.fixture(scope="module")
def monthly() -> pd.DataFrame:
    return pd.read_csv(REPO / "data" / "cards_monthly.csv")


def test_citi_monthly_rate_equals_the_prospectus_net_loss_table(monthly):
    p = prospectus_net_losses()
    c = monthly[monthly["trust"] == "citi"].copy()
    c["ym"] = pd.to_datetime(c["period_end"]).dt.strftime("%Y-%m")
    j = c.set_index("ym")[["net_co_rate"]].join(p.rename("prospectus"), how="inner")
    assert len(j) >= 60, len(j)                                   # January 2020 to March 2025
    diff = (j["net_co_rate"] * 100 - j["prospectus"]).abs()
    assert (diff < 0.0151).all(), j[diff >= 0.0151]               # every month within one printed hundredth
    assert (diff < 0.005).mean() > 0.9                            # and nine in ten identical


def test_citi_rows_carry_a_net_rate_and_no_gross_rate(monthly):
    c = monthly[monthly["trust"] == "citi"]
    assert c["gross_co_rate"].isna().all() and c["net_co_rate"].notna().all()
    j = json.loads(c["row_labels_json"].iloc[-1])
    assert j["labels"]["net_co_rate"].startswith("Credit Loss Component")
    assert "gross_co_rate" not in j["labels"]
    assert "net of recoveries" in j["null_reasons"]["gross_co_rate"]
    # the other five print both rates, and gross is never below net
    rest = monthly[monthly["trust"] != "citi"]
    assert rest[["gross_co_rate", "net_co_rate"]].notna().all().all()
    assert (rest["gross_co_rate"] >= rest["net_co_rate"] - 1e-9).all()


def test_the_prospectus_defines_the_series_as_net_and_reports_the_gross_over_net_ratios():
    t = _flat(PROSPECTUS)
    assert "Net losses include principal recoveries" in t
    assert re.search(r"charged off as uncollectible in that month \(net of recoveries\)", t)
    m = re.search(r"Gross Charge-Offs \$ ([\d,]+) \$ ([\d,]+) \$ ([\d,]+) \$ ([\d,]+) Recoveries .*? "
                  r"Net Losses \$ ([\d,]+) \$ ([\d,]+) \$ ([\d,]+) \$ ([\d,]+)", t)
    assert m, "loss experience table not found"
    v = [float(x.replace(",", "")) for x in m.groups()]
    ratios = [g / n for g, n in zip(v[:4], v[4:])]                # Q1 2025, 2024, 2023, 2022
    assert round(min(ratios), 2) == cards_page.CITI_GROSS_OVER_NET[0] == 1.21
    assert round(max(ratios), 2) == cards_page.CITI_GROSS_OVER_NET[1] == 1.47


def test_every_card_result_is_on_the_net_rate(monthly):
    assert cards_roll.RATE == "net_co_rate"
    pred = pd.read_csv(RESULTS / "a1_predicted.csv")
    assert set(pred["trust"]) == {"amex", "bofa", "chase", "citi", "comet", "synchrony"}
    m = monthly.assign(period_end=monthly["period_end"].astype(str))
    one = pred[pred["shape_source"] == pred["shape_source"].iloc[0]].assign(period_end=lambda d: d["period_end"].astype(str))
    j = one.merge(m[["trust", "period_end", "net_co_rate", "gross_co_rate"]], on=["trust", "period_end"])
    assert len(j) == len(one)
    assert (j["actual"] - j["net_co_rate"]).abs().max() < 1e-12
    citi = j[j["trust"] == "citi"]
    assert citi["actual_gross"].isna().all() and citi["residual_gross"].isna().all()
    rest = j[j["trust"] != "citi"]
    assert (rest["actual_gross"] - rest["gross_co_rate"]).abs().max() < 1e-12
    assert ((rest["residual_gross"] - rest["residual"]) - (rest["gross_co_rate"] - rest["net_co_rate"])).abs().max() < 1e-12
    basis = pd.read_csv(RESULTS / "a1_basis.csv").set_index("trust")
    assert basis.loc["citi", "months_gross"] == 0 and pd.isna(basis.loc["citi", "net_over_gross"])
    assert basis.drop(index="citi")["net_over_gross"].between(0.5, 0.95).all()


def test_citi_is_no_longer_ranked_as_if_its_net_rate_were_gross():
    rank = pd.read_csv(RESULTS / "a1_ranking.csv")
    citi = rank[rank["trust"] == "citi"]["rank"]
    assert citi.max() <= 4 and citi.min() >= 2, citi.tolist()     # the review's "between 2 and 4"; it was 5
    assert rank[rank["trust"] == "citi"]["mean_residual_gross"].isna().all()


def test_rate_basis_table_reports_the_gap():
    m = pd.DataFrame({"trust": ["a"] * 3 + ["b"] * 3, "gross_co_rate": [0.04, 0.05, 0.06, None, None, None],
                      "net_co_rate": [0.03, 0.04, 0.05, 0.02, 0.02, 0.02]})
    b = run_cards.rate_basis(m).set_index("trust")
    assert b.loc["a", "net_over_gross"] == pytest.approx(0.8) and b.loc["a", "gross_minus_net"] == pytest.approx(0.01)
    assert b.loc["b", "months_gross"] == 0 and pd.isna(b.loc["b", "net_over_gross"]) and b.loc["b", "months_net"] == 3


def test_a_sign_is_read_on_the_gross_rate_and_a_net_only_trust_gets_bounds():
    """Net actual against a gross prediction is biased low. A trust that prints gross is read on gross; one that does
    not is '+' only if its net residual, a floor, is already positive under every shape."""
    rank = pd.DataFrame({
        "shape_source": ["s1", "s2"] * 3, "trust": ["g", "g", "netpos", "netpos", "netneg", "netneg"],
        "mean_residual": [-0.002, -0.001, 0.001, 0.002, -0.004, 0.006], "mean_actual": [0.02] * 6,
        "mean_residual_gross": [0.001, 0.002, None, None, None, None], "rank": [3, 3, 1, 1, 2, 2]})
    lo, hi = cards_page._gross_residuals(rank)
    assert (lo.loc["g"] > 0).all() and (lo.loc["g"] == hi.loc["g"]).all()        # negative on net, positive on gross
    assert (lo.loc["netpos"] > 0).all() and (hi.loc["netpos"] > lo.loc["netpos"]).all()
    assert lo.loc["netneg", "s1"] < 0 < hi.loc["netneg", "s2"]


def test_cards_page_says_net_and_names_the_correction():
    t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", (REPO / "docs" / "cards.html").read_text(encoding="utf-8"))))
    assert "Every trust is compared on its net charge-off rate" in t
    assert "labelled Citi's net rate gross" in t
    assert "annualised net charge-off" in t and "annualised gross charge-off" not in t
    assert "Net against a gross benchmark." in t
    assert "convert least" not in t and "inferred gross" not in t
