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


# ----------------------------------------------------------------------------- charts in both themes (REVIEW.md R2-5)

MARK = re.compile(r"<(polyline|rect|circle|line)\b([^>]*)>")


def _theme_vars(html: str) -> dict[str, dict[str, str]]:
    """The CSS custom properties of each theme: light from `:root{...}`, dark from both dark scopes, which must agree."""
    css = html[html.index("<style>"):html.index("</style>")]
    parse = lambda block: dict(re.findall(r"--([\w-]+):([^;}]+)", block))   # noqa: E731
    light = parse(re.search(r":root\{([^}]*)\}", css).group(1))
    media = parse(re.search(r":root:not\(\[data-theme=\"light\"\]\)\{([^}]*)\}", css).group(1))
    toggle = parse(re.search(r":root\[data-theme=\"dark\"\]\{([^}]*)\}", css).group(1))
    assert media == toggle, "the prefers-color-scheme block and the data-theme block define different dark colours"
    return {"light": light, "dark": {**light, **toggle}}


def _hex_luminance(c: str) -> float:
    c = c.strip().lstrip("#")
    if len(c) == 3:
        c = "".join(x * 2 for x in c)
    rgb = [int(c[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_hex_luminance(a), _hex_luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _resolve(colour: str, theme: dict[str, str]) -> str:
    colour = colour.strip()
    if colour == "currentColor":
        return theme["fg"]
    m = re.fullmatch(r"var\(--([\w-]+)\)", colour)
    return theme[m.group(1)].strip() if m else colour


def chart_colours(html: str) -> list[str]:
    """Every stroke and fill colour on a data mark (gridlines, class 'grid', are meant to recede and are skipped)."""
    out = []
    for _, attrs in MARK.findall(html):
        if "class='grid'" in attrs:
            continue
        for prop in ("stroke", "fill"):
            for v in re.findall(rf"\b{prop}='([^']+)'", attrs) + re.findall(rf"{prop}:([^;']+)", attrs):
                if v.strip() not in ("none", "transparent"):
                    out.append(v)
    return out


def test_contrast_helper_matches_the_review_measurement():
    assert contrast("#1d1d1b", "#1d1f25") == pytest.approx(1.03, abs=0.01)    # the invisible "actual" line
    assert contrast("#000000", "#ffffff") == pytest.approx(21.0)


@pytest.mark.parametrize("name", GENERATED)
def test_every_chart_mark_clears_3_to_1_against_the_card_in_both_themes(name):
    h = (DOCS / name).read_text(encoding="utf-8")
    themes = _theme_vars(h)
    colours = chart_colours(h)
    if name != "conclusions.html":
        assert colours, name
    bad = sorted({(c, t, round(contrast(_resolve(c, v), v["card"]), 2)) for c in colours for t, v in themes.items()
                  if contrast(_resolve(c, v), v["card"]) < 3.0})
    assert not bad, f"{name}: chart colours under 3:1 against the chart card: {bad}"


def test_the_cards_actual_line_is_drawn_in_the_text_colour():
    h = (DOCS / "cards.html").read_text(encoding="utf-8")
    actual = re.findall(r"<polyline[^>]*style='stroke:([^']+)'[^>]*><title>actual</title>", h)
    assert actual and set(actual) == {"var(--fg)"}


@pytest.mark.parametrize("name", GENERATED)
def test_axis_ticks_are_round_numbers(name):
    ticks = re.findall(r"text-anchor='middle' class='tick'>([^<]*)<", (DOCS / name).read_text(encoding="utf-8"))
    assert not [t for t in ticks if re.search(r"\.\d{3,}", t)], name                  # 11.6375 months, before R2-5


def test_nice_ticks():
    from absrisk.report.svg import nice_ticks

    assert nice_ticks(0, 36) == [0, 5, 10, 15, 20, 25, 30, 35]
    assert nice_ticks(2019.0, 2026.75) == [2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]
    assert nice_ticks(480, 840) == [500, 550, 600, 650, 700, 750, 800]
    assert nice_ticks(3, 3) == [3]
