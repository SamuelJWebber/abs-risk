"""The generated pages: one shell, rebuilt exactly from the committed results, and saying what the numbers say.

R1-12: the three generated pages had no doctype (quirks mode), no viewport (phones lay them out at about 980 px) and
no links. R1-7: the cards page said the mix "is held fixed between prospectus dates" while 92% of trust-months used a
snapshot dated after them. R1-11: page text contradicted the tables beside it.
"""

from __future__ import annotations

import re
from html import unescape
from pathlib import Path

import pandas as pd
import pytest

from absrisk.report import autos_page, cards_page, conclusions_page
from absrisk.report.svg import page

REPO = Path(__file__).resolve().parents[1]
DOCS = REPO / "docs"
CARDS = REPO / "data" / "results" / "cards"
AUTOS = REPO / "data" / "results" / "autos"
GENERATED = ("autos.html", "cards.html", "conclusions.html")


def _text(html: str) -> str:
    return unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)))


@pytest.mark.parametrize("name", sorted(p.name for p in DOCS.glob("*.html")))
def test_every_page_has_doctype_charset_and_viewport(name):
    h = (DOCS / name).read_text(encoding="utf-8")
    assert h.lstrip().lower().startswith("<!doctype html>"), name
    assert re.search(r"<meta charset=['\"]utf-8['\"]", h, re.I), name
    assert re.search(r"<meta name=['\"]viewport['\"] content=['\"]width=device-width", h, re.I), name


@pytest.mark.parametrize("name", GENERATED)
def test_generated_pages_link_to_each_other_and_carry_no_build_date(name):
    h = (DOCS / name).read_text(encoding="utf-8")
    for other in ("index.html", "conclusions.html", "cards.html", "autos.html"):
        assert f"href='{other}'" in h, (name, other)
    assert f"href='{name}' aria-current='page'" in h
    assert not re.search(r"Built \d{4}-\d{2}-\d{2}", h)       # a date stamp made every rebuild a diff
    assert re.search(r"[Dd]ata through [A-Z][a-z]+ \d{4}", _text(h))


def test_page_shell():
    h = page("t", "<p>x</p>", current="cards.html")
    assert h.startswith("<!doctype html>\n<html lang='en'><head><meta charset='utf-8'>")
    assert "<title>t</title>" in h and h.rstrip().endswith("</main></body></html>")


@pytest.fixture(scope="module")
def rebuilt(tmp_path_factory):
    out = tmp_path_factory.mktemp("docs")
    cards_page.build(CARDS, out / "cards.html")
    conclusions_page.build(AUTOS, CARDS, out / "conclusions.html")
    autos_page.build(AUTOS, out / "autos.html")
    return out


@pytest.mark.parametrize("name", GENERATED)
def test_committed_page_is_what_the_code_builds_from_the_committed_results(rebuilt, name):
    assert (rebuilt / name).read_text(encoding="utf-8") == (DOCS / name).read_text(encoding="utf-8"), (
        f"docs/{name} is stale: run `absrisk report {name.removesuffix('.html')}`")


def test_cards_page_states_how_the_snapshot_is_applied():
    t = _text((DOCS / "cards.html").read_text(encoding="utf-8"))
    pred = pd.read_csv(CARDS / "a1_predicted.csv")
    one = pred[pred["shape_source"] == pred["shape_source"].iloc[0]]
    assert "held fixed between prospectus dates" not in t
    assert f"{one['mix_extrapolated'].mean():.0%} of trust-months are predicted from a snapshot dated after them" in t
    if one["level_year_clamped"].any():
        assert f"({one['level_year_clamped'].mean():.0%} of trust-months)" in t


def test_cards_page_text_agrees_with_its_tables():
    t = _text((DOCS / "cards.html").read_text(encoding="utf-8"))
    n = pd.read_csv(REPO / "data" / "loss_shape.csv").dropna(subset=["relative_loss"])["shape_source"].nunique()
    words = {2: "two", 3: "three", 4: "four", 5: "five"}
    assert f"2. The {words[n]} loss-by-tier shapes" in t
    assert "no single ordering is reported as a finding" not in t     # the headline reports the extremes as a finding
    assert "Since when" in t                                            # the scope sentence promises it
