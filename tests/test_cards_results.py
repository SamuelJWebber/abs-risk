"""The committed card results are what the code computes from the committed inputs.

A method change that is not followed by `absrisk analyze cards` leaves the published numbers describing old code
(REVIEW.md R1-1 was a method slip of that kind in reverse). This reruns the card analysis (about six seconds) into a
temporary directory and compares every result table with the committed one.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from absrisk.estimate import run_cards

REPO = Path(__file__).resolve().parents[1]
RESULTS = REPO / "data" / "results" / "cards"


@pytest.fixture(scope="module")
def rebuilt(tmp_path_factory):
    out = tmp_path_factory.mktemp("cards_results")
    rc = run_cards.main(["--monthly", str(REPO / "data" / "cards_monthly.csv"),
                         "--composition", str(REPO / "data" / "cards_composition.csv"),
                         "--crosswalk", str(REPO / "crosswalks" / "fico_buckets.csv"),
                         "--out", str(out)])
    assert rc == 0
    return out


@pytest.mark.parametrize("name", sorted(p.name for p in RESULTS.glob("*.csv")))
def test_committed_card_table_matches_a_rebuild(rebuilt, name):
    a = pd.read_csv(RESULTS / name)
    b = pd.read_csv(rebuilt / name)
    assert list(a.columns) == list(b.columns), name
    assert len(a) == len(b), name
    # the saturated panel fit is exact arithmetic up to the solver; everything else is plain arithmetic
    rtol = 1e-6 if name == "a2_panel.csv" else 1e-9
    for c in a.columns:
        if pd.api.types.is_numeric_dtype(a[c]) and pd.api.types.is_numeric_dtype(b[c]):
            assert np.allclose(a[c].to_numpy(float), b[c].to_numpy(float), rtol=rtol, atol=1e-12, equal_nan=True), (name, c)
        else:
            assert a[c].fillna("").astype(str).tolist() == b[c].fillna("").astype(str).tolist(), (name, c)


def test_every_rebuilt_table_is_committed(rebuilt):
    assert sorted(p.name for p in rebuilt.glob("*.csv")) == sorted(p.name for p in RESULTS.glob("*.csv"))
