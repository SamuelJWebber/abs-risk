"""Self-contained HTML chart pack for the payment-rate test. No libraries, inline SVG."""
import os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
P = pd.read_csv(os.path.join(HERE, "part2_monthly_panel.csv"))
TRUSTS = ["amex", "bofa", "chase", "citi", "comet", "synchrony"]
COL = {"amex": "#2f6f9f", "bofa": "#c8783c", "chase": "#4f8f5a", "citi": "#9a5ba6",
       "comet": "#b8523f", "synchrony": "#3c3c3c"}
W, H, ML, MR, MT, MB = 900, 300, 56, 150, 22, 34
PW, PH = W - ML - MR, H - MT - MB
n = len(P)
xs = np.arange(n)
LBL = P["ym"].tolist()
BANDS = [("stimulus", "2020-04", "2021-12"), ("squeeze", "2023-07", LBL[-1])]


def xpix(i):
    return ML + PW * i / max(n - 1, 1)


def panel(title, sub, series, ylab, fmt="{:.2f}"):
    ally = np.concatenate([v for _, v in series])
    lo, hi = float(np.nanmin(ally)), float(np.nanmax(ally))
    pad = (hi - lo) * 0.08 or 0.01
    lo, hi = lo - pad, hi + pad

    def yp(v):
        return MT + PH * (1 - (v - lo) / (hi - lo))

    s = [f'<figure><figcaption><b>{title}</b><span>{sub}</span></figcaption>',
         f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{title}">']
    for nm, a, b in BANDS:
        i0 = LBL.index(a) if a in LBL else 0
        i1 = LBL.index(b) if b in LBL else n - 1
        s.append(f'<rect x="{xpix(i0):.1f}" y="{MT}" width="{xpix(i1)-xpix(i0):.1f}" '
                 f'height="{PH}" class="band"/>')
        s.append(f'<text x="{xpix(i0)+4:.1f}" y="{MT+12}" class="bandlbl">{nm}</text>')
    for k in range(5):
        v = lo + (hi - lo) * k / 4
        y = yp(v)
        s.append(f'<line x1="{ML}" y1="{y:.1f}" x2="{ML+PW}" y2="{y:.1f}" class="grid"/>')
        s.append(f'<text x="{ML-8}" y="{y+4:.1f}" class="ytick">{fmt.format(v)}</text>')
    for i, lab in enumerate(LBL):
        if lab.endswith("-01"):
            s.append(f'<line x1="{xpix(i):.1f}" y1="{MT}" x2="{xpix(i):.1f}" y2="{MT+PH}" class="gridv"/>')
            s.append(f'<text x="{xpix(i):.1f}" y="{MT+PH+16}" class="xtick">{lab[:4]}</text>')
    for nm, v in series:
        d = " ".join(("M" if j == 0 else "L") + f"{xpix(j):.1f},{yp(v[j]):.1f}"
                     for j in range(len(v)) if np.isfinite(v[j]))
        s.append(f'<path d="{d}" fill="none" stroke="{COL.get(nm,"#777")}" stroke-width="1.9"/>')
    for j, (nm, v) in enumerate(series):
        y = MT + 14 + j * 17
        s.append(f'<line x1="{ML+PW+14}" y1="{y-4}" x2="{ML+PW+32}" y2="{y-4}" '
                 f'stroke="{COL.get(nm,"#777")}" stroke-width="2.4"/>')
        s.append(f'<text x="{ML+PW+38}" y="{y}" class="leg">{nm} '
                 f'<tspan class="legv">{fmt.format(v[-1])}</tspan></text>')
    s.append(f'<text class="ylab" transform="translate(16,{MT+PH/2}) rotate(-90)">{ylab}</text>')
    s.append("</svg></figure>")
    return "\n".join(s)


blocks = [
    panel("Monthly payment rate, six card trusts",
          "principal collections over each trust's own printed denominator - levels are NOT comparable across trusts",
          [(t, P["pr_" + t].to_numpy()) for t in TRUSTS], "payment rate"),
    panel("Same series in logs, each trust re-based to its own 2019 mean",
          "this is what the elasticity test actually uses - product-design levels are differenced out",
          [(t, np.log(P["pr_" + t].to_numpy()) -
            np.log(P.loc[P["ym"].str.startswith("2019"), "pr_" + t].mean())) for t in TRUSTS],
          "log change vs 2019", "{:+.2f}"),
    panel("The common stressor and the two difference series",
          "X = six-trust mean log 30+ share; the two ratios are what the headline regressions explain",
          [("synchrony", P["six_mean_log30"].to_numpy()),
           ("amex", P["log_pr_amex_minus_sync"].to_numpy()),
           ("citi", P["log_d30_amex_minus_sync"].to_numpy())],
          "log points", "{:+.2f}"),
]
legend_fix = ("<p class=\"note\">Third panel legend: <b>synchrony</b>-coloured line is the common stressor X, "
              "<b>amex</b>-coloured is log(Amex PR / Synchrony PR), <b>citi</b>-coloured is "
              "log(Amex 30+ / Synchrony 30+).</p>")

html = f"""<!doctype html><meta charset="utf-8"><title>Payment-rate test - trust-decisive</title>
<style>
:root{{--ink:#1b1b1b;--mut:#6b6b6b;--line:#dcdcdc;--bg:#fbfaf8;--band:#f0ece4}}
body{{margin:0;padding:28px 32px 60px;background:var(--bg);color:var(--ink);
 font:14px/1.55 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:1000px}}
h1{{font-size:20px;margin:0 0 4px}}
.sub{{color:var(--mut);margin:0 0 24px;font-size:13px}}
figure{{margin:0 0 26px;background:#fff;border:1px solid var(--line);border-radius:6px;padding:10px 8px 4px}}
figcaption{{padding:2px 10px 6px;font-size:13px}}
figcaption span{{display:block;color:var(--mut);font-size:12px;font-weight:400}}
svg{{width:100%;height:auto;display:block}}
.grid{{stroke:#ececec;stroke-width:1}} .gridv{{stroke:#f2f2f2;stroke-width:1}}
.band{{fill:var(--band);opacity:.75}}
.bandlbl{{font-size:10px;fill:#9a9086}}
.ytick{{font-size:10px;fill:var(--mut);text-anchor:end}}
.xtick{{font-size:10px;fill:var(--mut);text-anchor:middle}}
.ylab{{font-size:10px;fill:var(--mut);text-anchor:middle}}
.leg{{font-size:11px;fill:var(--ink)}} .legv{{fill:var(--mut)}}
.note{{color:var(--mut);font-size:12px;margin:-14px 0 24px}}
.key{{border-left:3px solid #2f6f9f;padding:8px 14px;background:#fff;border-radius:0 4px 4px 0;
 border-top:1px solid var(--line);border-right:1px solid var(--line);border-bottom:1px solid var(--line)}}
code{{background:#f3f1ed;padding:1px 4px;border-radius:3px;font-size:12px}}
</style>
<h1>The payment-rate test</h1>
<p class="sub">Amex vs Synchrony, six securitised card trusts, {LBL[0]} to {LBL[-1]}.
Shaded bands are the stimulus and squeeze windows.</p>
{blocks[0]}
{blocks[1]}
{blocks[2]}
{legend_fix}
<div class="key"><p style="margin:0 0 6px"><b>What the pictures show</b></p>
<p style="margin:0">Panel 1: the level gap is enormous and constant - that is product design, not priority.
Panel 2: once each trust is re-based, five of the six move together and <b>Synchrony</b> is the laggard,
not Amex the leader. Panel 3: the two difference series are flat against a stressor that swings by a
factor of 2.17. Headline elasticity gap, Amex minus Synchrony: <code>+0.028 (se 0.087)</code> on payment
rate and <code>+0.081 (se 0.150)</code> on the 30+ ratio. Both zero.</p></div>
"""
out = os.path.join(HERE, "payment_rate_charts.html")
with open(out, "w", encoding="utf-8") as f:
    f.write(html)
print("wrote", out)
