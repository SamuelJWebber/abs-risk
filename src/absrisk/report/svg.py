"""Tiny inline-SVG line chart, enough for cumulative-incidence curves and residual series."""

from __future__ import annotations

import math
from html import escape

# Series colours are CSS variables with one value per theme (REVIEW.md R2-5: a hard-coded near-black "actual" line had
# contrast 1.03:1 on the dark chart card). Both sets were checked with the dataviz palette validator against their own
# card colour: every slot clears 3:1, adjacent slots stay apart under protan and deutan simulation (worst 8.6 light,
# 8.4 dark, OKLab x100), and normal vision (worst 17.1 and 19.3). tests/test_pages.py re-checks the contrast on the
# built pages. A series with "color": "fg" is drawn in the text colour, which is right in both themes.
SERIES_LIGHT = ["#2a78d6", "#d95926", "#12896a", "#a87400", "#c74a7e", "#008300", "#6250d6", "#d13a3a"]
SERIES_DARK = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"]
PALETTE = [f"var(--s{i})" for i in range(len(SERIES_LIGHT))]


def _colour(s: dict, i: int) -> str:
    c = s.get("color")
    if c == "fg":
        return "var(--fg)"
    return c or PALETTE[i % len(PALETTE)]


def nice_ticks(lo: float, hi: float, max_ticks: int = 8) -> list[float]:
    """Round tick values (1, 2, 2.5 or 5 times a power of ten) inside [lo, hi], at most `max_ticks` + 1 of them.
    The x axis used to print equal fractions of the range, such as 11.6375 months (REVIEW.md R2-5)."""
    if not (hi > lo):
        return [lo]
    raw = (hi - lo) / max_ticks
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    first = math.ceil(lo / step - 1e-9) * step
    out, v = [], first
    while v <= hi + 1e-9 * step:
        out.append(round(v, 10))
        v += step
    return out


def line_chart(series: list[dict], width=720, height=300, y_label="", x_label="", y_fmt="{:.1%}", title="",
               x_fmt="{:g}") -> str:
    """series: [{"name": str, "x": [...], "y": [...], "color": optional "fg" or a CSS colour}]. Axes are auto-scaled;
    y starts at 0; x ticks are round numbers printed with `x_fmt`."""
    pad_l, pad_r, pad_t, pad_b = 56, 16, 28, 40
    xs = [v for s in series for v in s["x"]]
    ys = [v for s in series for v in s["y"] if v == v]
    if not xs or not ys:
        return "<p class='muted'>no data</p>"
    x0, x1 = min(xs), max(xs)
    y0, y1 = 0.0, max(ys) * 1.08 or 1.0
    iw, ih = width - pad_l - pad_r, height - pad_t - pad_b

    def sx(x):
        return pad_l + (x - x0) / (x1 - x0 or 1) * iw

    def sy(y):
        return pad_t + ih - (y - y0) / (y1 - y0 or 1) * ih

    out = [f"<svg viewBox='0 0 {width} {height}' width='{width}' height='{height}' role='img' aria-label='{escape(title)}' style='width:100%;max-width:{width}px;height:auto'>"]
    if title:
        out.append(f"<text x='{pad_l}' y='18' class='ct'>{escape(title)}</text>")
    # gridlines and y ticks
    for i in range(5):
        yv = y0 + (y1 - y0) * i / 4
        out.append(f"<line x1='{pad_l}' x2='{width - pad_r}' y1='{sy(yv):.1f}' y2='{sy(yv):.1f}' class='grid'/>")
        out.append(f"<text x='{pad_l - 6}' y='{sy(yv) + 4:.1f}' text-anchor='end' class='tick'>{escape(y_fmt.format(yv))}</text>")
    for xv in nice_ticks(x0, x1):
        out.append(f"<text x='{sx(xv):.1f}' y='{height - pad_b + 16}' text-anchor='middle' class='tick'>{escape(x_fmt.format(xv))}</text>")
    if y_label:
        out.append(f"<text transform='rotate(-90)' x='{-(pad_t + ih / 2):.1f}' y='14' text-anchor='middle' class='axis'>{escape(y_label)}</text>")
    if x_label:
        out.append(f"<text x='{pad_l + iw / 2:.1f}' y='{height - 6}' text-anchor='middle' class='axis'>{escape(x_label)}</text>")
    for i, s in enumerate(series):
        pts = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in zip(s["x"], s["y"]) if y == y)
        out.append(f"<polyline fill='none' style='stroke:{_colour(s, i)}' stroke-width='2' points='{pts}'><title>{escape(s['name'])}</title></polyline>")
    # legend
    lx, ly = pad_l + 8, pad_t + 8
    for i, s in enumerate(series[:10]):
        out.append(f"<rect x='{lx}' y='{ly + i * 16 - 8}' width='12' height='3' style='fill:{_colour(s, i)}'/>")
        out.append(f"<text x='{lx + 18}' y='{ly + i * 16 - 3}' class='tick'>{escape(s['name'])}</text>")
    out.append("</svg>")
    return "".join(out)


def forest_chart(rows: list[dict], width=720, row_h=20, x_label="odds ratio (log scale)", title="") -> str:
    """Point estimates with intervals on a log axis, one row each, a reference line at 1.

    rows: [{"label": str, "est": float, "lo": float, "hi": float, "group": str}]; a change of `group` starts a new
    labelled block. Rows with a non-positive or missing value are skipped."""
    rows = [r for r in rows if all(r.get(k) == r.get(k) and r.get(k) is not None and r[k] > 0 for k in ("est", "lo", "hi"))]
    if not rows:
        return "<p class='muted'>no data</p>"
    pad_l, pad_r, pad_t, pad_b = 170, 70, 30, 40
    lines = []
    prev = None
    for r in rows:
        if r.get("group") != prev:
            lines.append(("group", r.get("group", "")))
            prev = r.get("group")
        lines.append(("row", r))
    height = pad_t + pad_b + row_h * len(lines)
    lo_v = min(min(r["lo"] for r in rows), 1.0)
    hi_v = max(max(r["hi"] for r in rows), 1.0)
    x0, x1 = math.log(lo_v) - 0.1, math.log(hi_v) + 0.1
    iw = width - pad_l - pad_r

    def sx(v):
        return pad_l + (math.log(v) - x0) / (x1 - x0) * iw

    out = [f"<svg viewBox='0 0 {width} {height}' width='{width}' height='{height}' role='img' aria-label='{escape(title)}' style='width:100%;max-width:{width}px;height:auto'>"]
    if title:
        out.append(f"<text x='{pad_l}' y='18' class='ct'>{escape(title)}</text>")
    ticks = [t for t in (0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20) if lo_v * 0.9 <= t <= hi_v * 1.1] or [1]
    ybot = height - pad_b
    for t in ticks:
        out.append(f"<line x1='{sx(t):.1f}' x2='{sx(t):.1f}' y1='{pad_t}' y2='{ybot}' class='grid'/>")
        out.append(f"<text x='{sx(t):.1f}' y='{ybot + 16}' text-anchor='middle' class='tick'>{t:g}</text>")
    out.append(f"<line x1='{sx(1):.1f}' x2='{sx(1):.1f}' y1='{pad_t}' y2='{ybot}' stroke='currentColor' stroke-width='1'/>")
    out.append(f"<text x='{pad_l + iw / 2:.1f}' y='{height - 6}' text-anchor='middle' class='axis'>{escape(x_label)}</text>")
    for i, (kind, r) in enumerate(lines):
        y = pad_t + row_h * i + row_h / 2
        if kind == "group":
            out.append(f"<text x='8' y='{y + 4:.1f}' class='ct'>{escape(str(r))}</text>")
            continue
        color = PALETTE[0]
        out.append(f"<text x='{pad_l - 8}' y='{y + 4:.1f}' text-anchor='end' class='tick'>{escape(str(r['label']))}</text>")
        out.append(f"<line x1='{sx(r['lo']):.1f}' x2='{sx(r['hi']):.1f}' y1='{y:.1f}' y2='{y:.1f}' style='stroke:{color}' stroke-width='2'/>")
        out.append(f"<circle cx='{sx(r['est']):.1f}' cy='{y:.1f}' r='4' style='fill:{color}'><title>{escape(str(r['label']))}: "
                   f"{r['est']:.2f} [{r['lo']:.2f}, {r['hi']:.2f}]</title></circle>")
        out.append(f"<text x='{width - pad_r + 6}' y='{y + 4:.1f}' class='tick'>{r['est']:.2f}</text>")
    out.append("</svg>")
    return "".join(out)


def table(df, cols=None, fmt=None, max_rows=200) -> str:
    """DataFrame to HTML table with per-column formats ({'col': '{:.2%}'})."""
    cols = cols or list(df.columns)
    fmt = fmt or {}
    h = ["<div class='tw'><table><thead><tr>"] + [f"<th>{escape(str(c))}</th>" for c in cols] + ["</tr></thead><tbody>"]
    for _, r in df.head(max_rows).iterrows():
        cells = []
        for c in cols:
            v = r[c]
            if c in fmt and v == v and v is not None:
                try:
                    v = fmt[c].format(v)
                except (ValueError, TypeError):
                    pass
            elif isinstance(v, float):
                v = "" if v != v else f"{v:.4g}"
            cells.append(f"<td>{escape(str(v))}</td>")
        h.append("<tr>" + "".join(cells) + "</tr>")
    h.append("</tbody></table></div>")
    if len(df) > max_rows:
        h.append(f"<p class='muted'>{len(df) - max_rows} more rows in the CSV.</p>")
    return "".join(h)


_S_LIGHT = "".join(f";--s{i}:{c}" for i, c in enumerate(SERIES_LIGHT))
_S_DARK = "".join(f";--s{i}:{c}" for i, c in enumerate(SERIES_DARK))
CSS = """
:root{--bg:#fbfaf7;--fg:#1d1d1b;--muted:#6b6b66;--line:#e2dfd6;--card:#ffffff;--accent:#1f5fbf""" + _S_LIGHT + """}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#15161a;--fg:#ececea;--muted:#a0a09a;--line:#2d2f36;--card:#1d1f25""" + _S_DARK + """}}
:root[data-theme="dark"]{--bg:#15161a;--fg:#ececea;--muted:#a0a09a;--line:#2d2f36;--card:#1d1f25""" + _S_DARK + """}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,Segoe UI,Roboto,sans-serif}
main{max-width:1040px;margin:0 auto;padding:24px 20px 60px}
h1{font-size:26px;margin:0 0 4px}h2{font-size:20px;margin:36px 0 8px;border-top:1px solid var(--line);padding-top:18px}h3{font-size:16px;margin:20px 0 6px}
p{max-width:72ch}.muted{color:var(--muted)}.note{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--accent);padding:10px 14px;margin:12px 0;max-width:80ch}
.tw{overflow-x:auto;margin:8px 0 16px}table{border-collapse:collapse;font-size:13px;min-width:420px}th,td{border-bottom:1px solid var(--line);padding:5px 9px;text-align:right;white-space:nowrap}th:first-child,td:first-child{text-align:left}th{color:var(--muted);font-weight:600}
svg{display:block;margin:6px 0 14px;background:var(--card);border:1px solid var(--line);border-radius:6px}
svg .grid{stroke:var(--line);stroke-width:1}svg .tick{fill:var(--muted);font-size:11px}svg .axis{fill:var(--muted);font-size:12px}svg .ct{fill:var(--fg);font-size:13px;font-weight:600}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(340px,100%),1fr));gap:12px}
footer{margin-top:40px;color:var(--muted);font-size:13px}
nav{font-size:13px;color:var(--muted);margin:0 0 18px;display:flex;flex-wrap:wrap;gap:4px 14px}
nav a{color:var(--accent);text-decoration:none}nav a[aria-current]{color:var(--fg);font-weight:600}
a{color:var(--accent)}
@media (max-width:600px){main{padding:16px 16px 48px}h1{font-size:22px}}
"""

REPO_URL = "https://github.com/SamuelJWebber/abs-risk"
NAV = (("index.html", "Overview"), ("conclusions.html", "Conclusions"), ("cards.html", "Card trusts"),
       ("autos.html", "Auto loans"), (REPO_URL + "/blob/main/design/methods.md", "Methods"), (REPO_URL, "Code and data"))


def page(title: str, body: str, current: str = "") -> str:
    """One shell for every generated page: doctype, charset, viewport, the shared style and a nav line.

    Without the doctype a browser renders in quirks mode, and without the viewport meta a phone lays the page out
    at about 980 px and shrinks it (REVIEW.md R1-12). `current` is the file name of this page, marked in the nav."""
    links = " ".join(f"<a href='{escape(href)}'" + (" aria-current='page'" if href == current else "") + f">{escape(label)}</a>"
                     for href, label in NAV)
    return ("<!doctype html>\n<html lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{escape(title)}</title><style>{CSS}</style></head>\n<body><main><nav>{links}</nav>"
            f"{body}</main></body></html>\n")
