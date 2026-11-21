"""Sentences the independent review of 2026-11-10 showed do not follow stay off every published page.

REVIEW.md abs-A-2, abs-B-1, abs-B-2, abs-A-6 and abs-B-4. The pages concluded "selection, on every level comparison"
from a conversion ratio that is not the fate of late accounts, said the filings do not state charge-off policies
(they do), said the comparison "rules out" the priority story, and named Citi as the trust that "converts least" from
a net rate labelled gross. The limit case for the word search: a page that drops a sentence but keeps its claim under
another wording. So the test also requires the replacement statements, which say what the filings cannot show.
"""

from __future__ import annotations

import re
from html import unescape
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PAGES = ("index.html", "conclusions.html", "cards.html", "autos.html")

WITHDRAWN = (
    "rules out", "rule out", "ruled out",
    "which the filings do not state",
    "on every level comparison",
    "selection, and it is not close",
    "The answer: selection",
    "Priority predicts the opposite sign",
    "not rescued more often than anyone else",
    "That is the opposite of what protection would look like",
    "the more trustworthy half", "the more trustworthy one",
    "converts least", "convert least",
    "inferred gross",
    "What else the data settled",
    "bigger line",
    "close to the baseline lender's rate",
    "There is no sign here of an account that borrowers protect",
    "The level comparison carries the argument",
    "returns to better selection dwarf",
)


def _text(name: str) -> str:
    return unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", (REPO / "docs" / name).read_text(encoding="utf-8"))))


@pytest.mark.parametrize("name", PAGES)
def test_no_withdrawn_sentence_is_published(name):
    t = _text(name).lower()
    found = [w for w in WITHDRAWN if w.lower() in t]
    assert not found, (name, found)


def test_conclusions_say_what_the_filings_cannot_show():
    t = _text("conclusions.html")
    assert "What the filings show: far fewer late balances, and nothing on rescue" in t
    assert "these filings do not answer the question in the title" in t
    assert "The prospectuses do state each issuer's charge-off policy" in t
    assert "Why conversion says nothing about rescue." in t
    assert "it is withdrawn" in t                                  # the old conclusion is named as withdrawn, not dropped silently
    assert re.search(r"at least \d+% of its charge-offs never aged through late delinquency", t)


def test_cards_page_withdraws_the_conversion_reading_and_prints_the_check():
    t = _text("cards.html")
    assert "Conversion is not the fate of late accounts." in t
    assert "That reading is withdrawn." in t
    assert "it does not separate the two stories" in t
    assert re.search(r"wrote off 1\.\d\d times the dollars that were in that bucket a month earlier", t)


def test_landing_page_does_not_announce_an_answer():
    t = _text("index.html")
    assert "The answer" not in t
    assert "cannot say whether their late accounts are rescued more or less often" in t


def test_autos_page_reports_the_roll_gap_it_used_to_call_close():
    t = _text("autos.html")
    assert "the advantage is mostly entry" in t
    assert re.search(r"honda below one in \d+ of \d+ buckets", t)
    assert "part of the gap does sit after trouble starts" in t
