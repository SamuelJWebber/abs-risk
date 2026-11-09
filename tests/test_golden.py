"""Golden checks: numbers in checks/golden.yaml traced to the filing text and to the committed table.

Runs on every `pytest`, so the cards-refresh workflow re-verifies them before it fetches (against the table the
last run committed) and again after it parses (against the table it is about to commit).
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import pytest
import yaml

from absrisk.cards.tables import doc_text, read_text

REPO = Path(__file__).resolve().parents[1]
FIX = REPO / "tests" / "fixtures" / "cards"
GOLDEN = yaml.safe_load((REPO / "checks" / "golden.yaml").read_text(encoding="utf-8"))["cards_monthly"]
WINDOW = 300            # characters after the label within which the printed number must appear


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s)


def _id(g: dict) -> str:
    return f"{g['trust']}-{g['period_end']}-{g['field']}"


def test_one_golden_number_per_live_trust():
    assert sorted(g["trust"] for g in GOLDEN) == sorted({"amex", "comet", "chase", "citi", "synchrony", "bofa"})


@pytest.mark.parametrize("g", GOLDEN, ids=_id)
def test_golden_number_is_printed_in_the_filing(g):
    path = FIX / g["trust"] / str(g["accession"]) / g["document"]
    assert path.exists(), f"golden filing not in the fixtures: {path}"
    text = _norm(doc_text(read_text(path)))
    i = text.find(_norm(g["label"]))
    assert i >= 0, f"label not in {g['document']}: {g['label']!r}"
    after = text[i + len(_norm(g["label"])): i + len(_norm(g["label"])) + WINDOW]
    assert _norm(g["printed"]) in after, f"{g['printed']!r} not within {WINDOW} characters after the label"
    printed = float(g["printed"].replace("%", "").replace(",", "").strip())
    assert printed / 100 == pytest.approx(g["value"], abs=1e-12)


@pytest.mark.parametrize("g", GOLDEN, ids=_id)
def test_committed_table_carries_the_golden_number(g):
    with open(REPO / "data" / "cards_monthly.csv", newline="", encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r["trust"] == g["trust"] and r["period_end"] == str(g["period_end"])]
    assert len(rows) == 1, f"{len(rows)} rows for {g['trust']} {g['period_end']}"
    r = rows[0]
    assert r["source_accession"] == str(g["accession"])
    assert float(r[g["field"]]) == pytest.approx(g["value"], abs=1e-9)
