"""Merge the four output files into one results.txt and one results.json, and add the verdict block."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def rd(n):
    with open(os.path.join(HERE, n), encoding="utf-8") as f:
        return f.read()


VERDICT = """
====================================================================================================
VERDICT
====================================================================================================

PART A. Raw Amex/Synchrony 30+ entry ratio = 0.2902 (amex 0.7384%, synchrony 2.5447%, full-sample
mean monthly 30+ share on each trust's own printed denominator). This reproduces the published
0.74 / 2.54 / 0.29 exactly.

After mix adjustment (level pinned within these six trusts only):
    fico_odds        0.6203     46.5 percent of the raw gap-below-parity was score mix
    fico_fed2007     0.6407     49.4 percent was mix
    acms2018         0.3497      8.4 percent was mix
    acms2018_dpd90   0.3808     12.8 percent was mix
Straddle sensitivity moves each of these by up to 0.22 (full range across shapes and rules:
0.3109 to 0.6974). The four shapes DISAGREE by roughly a factor of two on the adjusted ratio, and
that disagreement is larger than the sensitivity to the straddle rule. Nothing here pins the number
better than "somewhere between 0.31 and 0.70".

PART B. On the only two rungs that are structurally comparable, amex is modestly better than
synchrony, not equal:
    30->60   amex 0.7279  synchrony 0.7923  ratio 0.919
    60->90   amex 0.8271  synchrony 0.8818  ratio 0.938
The published claim that amex's "conversion" is 1.38x WORSE is reproduced (1.3813) but is a
denominator artefact: amex's 90+ stock includes an open-ended 120+ bucket. The dollar roll from the
deepest bucket to charge-off runs the other way (amex 0.7069 vs synchrony 1.0715 = 0.66), and that
is an artefact too, in the opposite direction, for the same reason. Neither number measures curing.

PART C. THE CYCLE TEST FAVOURS SELECTION.
    window                              amex/sync 30+   levels (amex, sync)
    2018-12..2019-11 pre-break              0.3055      0.00955  0.03124
    2019-12..2020-03 post pool addition     0.3962      0.01049  0.02648
    2020-04..2021-12 stimulus               0.3467      0.00664  0.01914
    2022-01..2023-06 normalising            0.2672      0.00549  0.02053
    2023-07..2026-07 squeeze                0.2615      0.00769  0.02943

The raw four-bin version appears to show the priority signature (0.3252 pre-covid -> 0.3467
stimulus -> 0.2615 squeeze). It does not survive one break. In December 2019, three months before
the pandemic and four before any stimulus, synchrony's trust receivables rose 38.6 percent in a
single month (5.459bn -> 7.565bn) and its 30+ share fell 27.3 percent (3.297% -> 2.396%), while no
other trust's 30+ share moved more than 4 percent. The amex/synchrony ratio jumped from 0.3196 to
0.4222 in that month. Measured against the correct immediately-preceding baseline, the ratio FELL
during the stimulus (0.3962 -> 0.3467): the amex gap WIDENED when households were flush, which is
the opposite of the priority prediction.

Inside the squeeze the ratio is flat: regressing log(amex/synchrony) on a month trend over
2023-07..2026-07 gives -0.032 percent per month (Newey-West se 0.111 percent, z = -0.29), about
-0.4 percent a year, while the six-trust mean 30+ level rose 42 percent (0.01082 -> 0.01539) and
synchrony's own level rose 43 percent (2.053% -> 2.943%). Priority says the gap should widen as the
squeeze deepens. It does not move.

The 2020 compression is also not amex-specific. Change in log(trust/synchrony) from calendar 2019 to
2020: amex +0.246, citi +0.217, chase +0.199, bofa +0.147, comet +0.034. Every trust's ratio to
synchrony rose by a similar amount, which is what "synchrony's own level fell furthest" looks like,
not what "the amex card is protected" looks like.

FLOOR CHECK. The ratio and the percentage-point difference DISAGREE, and the difference is the one
to distrust. Difference from synchrony (pp): -2.17 pre-break, -1.25 stimulus, -2.17 squeeze - a
textbook priority shape. But the difference equals synchrony's level times (1 - ratio), so when
synchrony's level falls from 3.12% to 1.91% the difference must shrink by 39 percent even with a
perfectly constant ratio. The ratio is safe here because no level is near zero: the lowest monthly
30+ share in the whole panel is amex 0.420% (2021-06) and synchrony never goes below 1.334%
(2021-10), so there is no small-denominator instability. The log ratio agrees with the ratio by
construction. The ratio-to-six-trust-mean agrees too: amex 0.547 pre-break, 0.565 stimulus, 0.500
squeeze - flat then a step down, no cyclical oscillation. Three of the four representations agree;
the fourth (pp difference) is mechanically forced by the level and carries no extra information.

WHAT IS REAL AND NOT CYCLICAL. There is a persistent step down in the ratio after 2021, from about
0.30-0.40 to about 0.26, and it stays there for 55 straight months. That is a level shift, not an
oscillation, and it is what pool composition drift looks like: synchrony's trust receivables roughly
doubled over the sample (5.46bn in 2019-11 to 10.89bn in 2026-07). The single composition snapshot
in cards_composition.csv describes the doubled pool, so Part A's mix adjustment cannot be applied to
the 2019 pool at all.

MIX ADJUSTMENT CANNOT RESCUE THE CYCLE TEST EITHER WAY. Because the composition tables are single
snapshots, expected(amex)/expected(synchrony) is one constant per shape, so the mix-adjusted ratio
is the raw ratio divided by that constant in every regime. Mix adjustment shifts the whole path up
and changes none of its shape.
"""

txt = "\n\n".join([rd("results.txt"), rd("supplement.txt"), rd("breaks.txt"), rd("clean_windows.txt"), VERDICT])
with open(os.path.join(HERE, "results.txt"), "w", encoding="utf-8") as f:
    f.write(txt)

res = json.load(open(os.path.join(HERE, "results.json"), encoding="utf-8"))
res["clean_windows"] = json.load(open(os.path.join(HERE, "clean_windows.json"), encoding="utf-8"))
res["verdict"] = VERDICT.strip()
json.dump(res, open(os.path.join(HERE, "results.json"), "w", encoding="utf-8"), indent=2, default=str)
print("merged; results.txt now", len(txt), "chars")
print(sorted(os.listdir(HERE)))
