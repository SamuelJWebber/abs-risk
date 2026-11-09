"""The weekly refresh fails when a trust stops parsing (REVIEW.md R1-3).

The limit case: a trust's new statement breaks the parser. `absrisk cards parse` logs it and exits 0, so before this
check the run went green, committed the longer failure log and left the trust a month behind. Built from a real
fixture: the July 2026 BA filing copied under a new accession with its exhibits emptied.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

from absrisk.cards import main
from absrisk.cards.check import new_failures, read_failure_log, run_check, stale_mixes, trailing_trusts

FIX = Path(__file__).parent / "fixtures" / "cards"
BOFA = FIX / "bofa" / "0001140361-26-033313"          # 10-D, period 2026-07-31
BROKEN = "0001140361-26-099999"                       # invented accession for the broken copy


def _monthly(rows):
    return pd.DataFrame(rows, columns=["trust", "period_end"])


def test_new_failure_is_any_accession_the_committed_log_lacks():
    before = [{"trust": "comet", "accession": "a1", "error": "x"}]
    now = before + [{"trust": "bofa", "accession": "b2", "error": "ParseError: no table"}]
    assert new_failures(now, before) == [now[1]]
    assert new_failures(before, before) == []
    assert read_failure_log("trust,accession,error\ncomet,a1,x\n") == before
    assert read_failure_log("") == []


def test_a_trust_two_months_behind_fails_and_one_month_does_not():
    m = _monthly([("a", "2026-09-30"), ("b", "2026-08-31"), ("c", "2026-07-31"), ("d", "2026-09-25")])
    assert trailing_trusts(m) == [("c", "2026-07", 2)]
    res = run_check(m, [], [])
    assert not res.ok and "c ends at 2026-07, 2 months behind" in res.failures[0]
    assert run_check(m[m["trust"] != "c"], [], []).ok


def test_an_old_score_mix_is_a_warning_not_a_failure():
    m = _monthly([("a", "2026-10-31"), ("b", "2026-10-31")])
    comp = pd.DataFrame({"trust": ["a", "b"], "table": ["fico", "fico"], "as_of": ["2025-03-30", "2026-06-30"]})
    assert stale_mixes(comp, m) == [("a", "2025-03-30", 19)]
    res = run_check(m, [], [], comp)
    assert res.ok and len(res.warnings) == 1 and "a score mix is from 2025-03-30" in res.warnings[0]


@pytest.fixture()
def raw_with_broken_filing(tmp_path):
    raw = tmp_path / "raw"
    shutil.copytree(BOFA, raw / "bofa" / BOFA.name)
    dest = raw / "bofa" / BROKEN
    shutil.copytree(BOFA, dest)
    m = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
    m.update(accession=BROKEN, filing_date="2026-09-15")
    (dest / "manifest.json").write_text(json.dumps(m, indent=1), encoding="utf-8")
    for p in dest.glob("*ex99*.htm"):
        p.write_text("<html><body><p>layout changed</p></body></html>", encoding="utf-8")
    return raw


def _parse(raw: Path, tmp: Path, tag: str) -> tuple[Path, Path]:
    out, fails = tmp / f"m_{tag}.csv", tmp / f"f_{tag}.csv"
    assert main(["parse", "--raw", str(raw), "--trust", "bofa", "--out", str(out), "--failures", str(fails)]) == 0
    return out, fails


def test_cli_check_fails_on_a_new_broken_filing_and_passes_without_it(tmp_path, raw_with_broken_filing, capsys):
    clean_raw = tmp_path / "clean"
    shutil.copytree(BOFA, clean_raw / "bofa" / BOFA.name)
    m_clean, f_clean = _parse(clean_raw, tmp_path, "clean")
    m_broken, f_broken = _parse(raw_with_broken_filing, tmp_path, "broken")   # parse itself still exits 0
    assert BROKEN in f_broken.read_text(encoding="utf-8")
    common = ["--composition", str(tmp_path / "none.csv")]
    assert main(["check", "--monthly", str(m_clean), "--failures", str(f_clean), "--failures-before", str(f_clean),
                 *common]) == 0
    assert main(["check", "--monthly", str(m_broken), "--failures", str(f_broken), "--failures-before", str(f_clean),
                 *common]) == 1
    err = capsys.readouterr().err
    assert f"new parse failure: bofa {BROKEN}" in err
    # once the failure is in the committed log it is known, and the run is green again
    assert main(["check", "--monthly", str(m_broken), "--failures", str(f_broken), "--failures-before", str(f_broken),
                 *common]) == 0


def test_the_committed_tables_pass_the_check():
    repo = Path(__file__).resolve().parents[1]
    assert main(["check", "--monthly", str(repo / "data" / "cards_monthly.csv"),
                 "--failures", str(repo / "data" / "cards_parse_failures.csv"),
                 "--failures-before", str(repo / "data" / "cards_parse_failures.csv"),
                 "--composition", str(repo / "data" / "cards_composition.csv")]) == 0
