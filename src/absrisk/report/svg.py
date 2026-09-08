"""Tiny inline-SVG line chart, enough for cumulative-incidence curves and residual series."""

from __future__ import annotations

from html import escape

PALETTE = ["#1f5fbf", "#d1495b", "#2a9d8f", "#e9a03b", "#7b4fa0", "#4c9f70", "#8a6d3b", "#5c5c5c", "#c2185b", "#00838f"]


def line_chart(series: list[dict], width=720, height=300, y_label="", x_label="", y_fmt="{:.1%}", title="") -> str:
    """series: [{"name": str, "x": [...], "y": [...]}]. Axes are auto-scaled; y starts at 0."""
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

    out = [f"<svg viewBox='0 0 {width} {height}' width='100%' role='img' aria-label='{escape(title)}' style='max-width:{width}px'>"]
    if title:
        out.append(f"<text x='{pad_l}' y='18' class='ct'>{escape(title)}</text>")
    # gridlines and y ticks
    for i in range(5):
        yv = y0 + (y1 - y0) * i / 4
        out.append(f"<line x1='{pad_l}' x2='{width - pad_r}' y1='{sy(yv):.1f}' y2='{sy(yv):.1f}' class='grid'/>")
        out.append(f"<text x='{pad_l - 6}' y='{sy(yv) + 4:.1f}' text-anchor='end' class='tick'>{escape(y_fmt.format(yv))}</text>")
    nx = min(8, int(x1 - x0) or 1)
    for i in range(nx + 1):
        xv = x0 + (x1 - x0) * i / nx
        out.append(f"<text x='{sx(xv):.1f}' y='{height - pad_b + 16}' text-anchor='middle' class='tick'>{xv:g}</text>")
    if y_label:
        out.append(f"<text transform='rotate(-90)' x='{-(pad_t + ih / 2):.1f}' y='14' text-anchor='middle' class='axis'>{escape(y_label)}</text>")
    if x_label:
        out.append(f"<text x='{pad_l + iw / 2:.1f}' y='{height - 6}' text-anchor='middle' class='axis'>{escape(x_label)}</text>")
    for i, s in enumerate(series):
        pts = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in zip(s["x"], s["y"]) if y == y)
        color = s.get("color", PALETTE[i % len(PALETTE)])
        out.append(f"<polyline fill='none' stroke='{color}' stroke-width='2' points='{pts}'><title>{escape(s['name'])}</title></polyline>")
    # legend
    lx, ly = pad_l + 8, pad_t + 8
    for i, s in enumerate(series[:10]):
        color = s.get("color", PALETTE[i % len(PALETTE)])
        out.append(f"<rect x='{lx}' y='{ly + i * 16 - 8}' width='12' height='3' fill='{color}'/>")
        out.append(f"<text x='{lx + 18}' y='{ly + i * 16 - 3}' class='tick'>{escape(s['name'])}</text>")
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


CSS = """
:root{--bg:#fbfaf7;--fg:#1d1d1b;--muted:#6b6b66;--line:#e2dfd6;--card:#ffffff;--accent:#1f5fbf}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#15161a;--fg:#ececea;--muted:#a0a09a;--line:#2d2f36;--card:#1d1f25}}
:root[data-theme="dark"]{--bg:#15161a;--fg:#ececea;--muted:#a0a09a;--line:#2d2f36;--card:#1d1f25}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,Segoe UI,Roboto,sans-serif}
main{max-width:1040px;margin:0 auto;padding:24px 20px 60px}
h1{font-size:26px;margin:0 0 4px}h2{font-size:20px;margin:36px 0 8px;border-top:1px solid var(--line);padding-top:18px}h3{font-size:16px;margin:20px 0 6px}
p{max-width:72ch}.muted{color:var(--muted)}.note{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--accent);padding:10px 14px;margin:12px 0;max-width:80ch}
.tw{overflow-x:auto;margin:8px 0 16px}table{border-collapse:collapse;font-size:13px;min-width:420px}th,td{border-bottom:1px solid var(--line);padding:5px 9px;text-align:right;white-space:nowrap}th:first-child,td:first-child{text-align:left}th{color:var(--muted);font-weight:600}
svg{display:block;margin:6px 0 14px;background:var(--card);border:1px solid var(--line);border-radius:6px}
svg .grid{stroke:var(--line);stroke-width:1}svg .tick{fill:var(--muted);font-size:11px}svg .axis{fill:var(--muted);font-size:12px}svg .ct{fill:var(--fg);font-size:13px;font-weight:600}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:12px}
footer{margin-top:40px;color:var(--muted);font-size:13px}
"""
