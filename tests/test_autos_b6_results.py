"""Recompute the published auto entry/roll decomposition using the committed loan tables."""
from pathlib import Path

import pandas as pd
import pytest

from absrisk.estimate.run_autos import load_loans, run_b6

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ("b6_decomposition.csv", "b6_attribution.csv", "b6_by_score.csv", "b6_attribution_by_score.csv")


@pytest.mark.slow
def test_auto_decomposition_tables_match_the_loan_data(tmp_path):
    run_b6(load_loans(ROOT / "data/autos"), tmp_path)
    for name in OUTPUTS:
        expected = pd.read_csv(ROOT / "data/results/autos" / name)
        actual = pd.read_csv(tmp_path / name)
        keys = ["lender", "score_b"] if "score_b" in expected else ["lender"]
        pd.testing.assert_frame_equal(
            expected.set_index(keys, verify_integrity=True).sort_index(),
            actual.set_index(keys, verify_integrity=True).sort_index(),
            check_exact=False, rtol=1e-9, atol=1e-10, obj=name,
        )
