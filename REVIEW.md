# Review round 2 (2026-11-09)

Adversarial review of `main` at `1086ee6`, after round 1 was implemented (fixes fbbeac8 through 1086ee6). Round 1
(2 HIGH, 5 MEDIUM, 10 LOW) is in git history: `git show 1086ee6:REVIEW.md`.

**Counts: 1 HIGH, 5 MEDIUM, 7 LOW. Regressions: 0** (every round-1 finding marked Fixed still passes its check).

The short version. The arithmetic is sound again: every headline number re-derives from the raw filings and the raw
CFPB workbook with code that does not import `absrisk`. What is wrong is how three headline claims are framed, and
one chart:

- the autos headline "50 times" counts months in which a loan cannot charge off, because it had to be current to be
  sold into the trust; the project measured this effect itself and corrected only the hazard model (R2-1);
- Synchrony's trust is a retail pool, a quarter of it private label, but it is calibrated to the general-purpose
  level; the one card result the page calls assumption-free depends on that (R2-2);
- the "ends of the ranking" and "selection on every level comparison" claims outrun the project's own straddle
  sensitivity, Citi's conversion and AmeriCredit's split (R2-3, R2-4);
- in dark mode the "actual" line of every cards chart is invisible (R2-5);
- one commit with a personal email address would stop every scheduled refresh for good (R2-6).

How it was run: `python -m uv run pytest -o addopts=""` (333 passed, 247 s with BLAS capped at two threads);
`gh run list` and the full log of run 42727357720; `git log -p -20` read; the live Pages fetched, compared with
`docs/` and inspected at 375 px; the audit skill's four personas (silent wrong answer, stranger with a clone, leak
hunter, bad actor) run in-process, because this reviewer has no subagent tool. Nothing touched EDGAR. Heavy work
stayed on two threads: autos b1, b2 and b6 were rebuilt into a scratch folder and compared byte for byte.

Severity: HIGH = wrong result, data loss, broken run, privacy or security; MEDIUM = a claim or safeguard that does
not hold as stated; LOW = cosmetic, stale, or a weakness without a wrong number today.

---

## Round 1, re-checked

| finding | status in round 1 | check re-run now | holds |
|---|---|---|---|
| R1-1 card mix from the crosswalk | Fixed | `mix_by_trust.csv` against `tier_shares(composition, crosswalk)`: max difference 1.4e-16; BofA fico_fed2007 on the page +1.13% | yes |
| R1-2 local paths | Fixed for 21 of 22 files; CLAUDE.md line and history deferred | the round-1 `git grep` returns only `CLAUDE.md:5`, the deferred line | yes, as scoped |
| R1-3 alert contract | Fixed | `tests/test_cards_check.py` passes; run 42727357720 logs "check passed"; an October month simulated below also passes, with the Citi warning | yes |
| R1-4 direction test | Fixed | re-derived independently (below): Amex -0.10, Citi +0.09, BofA -0.12 and COMET -0.06 across the one tightening | yes |
| R1-5 stages multiply back | Fixed | independent geometric means: Amex shares +1.254, +0.075, -0.329, sum 1.000 | yes |
| R1-6 lender intervals | Fixed | simulation test passes; page intervals equal `b2_lender_intervals.csv`; b2 rebuilt byte-identical | yes |
| R1-7 look-ahead disclosed | short-term fix | page states 92% and 22%; `tests/test_pages.py` holds it | yes |
| R1-8 one-scale check | Fixed | re-derived: 37.7x on the past-850 lenders, the same as without Exeter | yes |
| R1-9 degenerate odds ratios | Fixed | the round-1 command returns 0 rows | yes |
| R1-10 RD sentence | Fixed | 0 of 14 at the optimal bandwidth (Honda 605 at 12 months: p 0.0504, interval -0.0001 to 0.138) | yes |
| R1-11 five contradictions | Fixed | "four" shapes, no "no single ordering", since-when table, 27% price share, no "collapses" in methods.md | yes |
| R1-12 page shell | Fixed | doctype, charset, viewport on all four pages; 375 px standards mode, no overflow (cards, autos) | yes (see R2-5) |
| R1-13 charge-offs that skip 30+ | Fixed | `co_without_30_share` in b6 tables; b6 rebuilt byte-identical | yes |
| R1-14 cache schedule | Fixed | cron `17 9 * * 1,4`; caches last accessed within a day | yes; first scheduled run not yet seen |
| R1-15 stale numbers | Fixed | `grep -n "573\|153 rows"` finds only the qualified TASKS A2 line | yes |
| R1-16 personal email in history | Deferred to the user | still on 43 commits, none since 6a18549 | open, as scoped |
| R1-17 refused User-Agent workflow | Fixed | `grep -rn "(+https" scripts .github` returns nothing | yes |

---

## Findings

### R2-1 · HIGH · The autos headline gap counts months in which a loan cannot charge off, and rests on one to three charge-offs per bucket

**What is wrong.** Take the limit case: a lender whose loans all enter its trust at age 12. A loan must be current to
be sold into a trust, and a current loan usually needs three or four missed payments before it charges off. So by
age 12 that lender's cumulative charge-off is close to zero by construction, whoever its borrowers are.

The project measured this. Its hazard model puts charge-off odds in the first three months in the pool at 0.13 of
a seasoned loan's, and 0.66 to 0.72 in months 3-5 (`b2_hazard_ratios.csv`, `pool_b`; `hazard.py:43-44`). It added
months in pool to the hazard model in round 1, but not to the Aalen-Johansen curves behind the headline
(`survival.py` `ages`: delayed entry at first observation; `autos_page.py:281`). HANDOFF next step 2 records the gap,
and the page says the result "survives the obvious objections" (`autos_page.py:276`).

The lenders at the bottom of the ratio are the seasoned ones. In the 660-799 cells, median age at entry is 10 to 13
months at Honda, 13 to 14 at Toyota and 13 to 15 at Capital One, against 3 at Exeter and 4 to 6 at Santander in
660-700 (`b1_at_12.csv`, `entry_age_median`). At age 12 the seasoned lenders' risk sets are mostly loans in their
first months in the pool.

On top of that, every one of the seven ratios divides by a cell with one to three charge-offs by age 12. The
bottom cells are Honda 660 (2), Toyota 680 (1), Honda 700 (3), Capital One 720 (1), Honda 740 (3), Toyota 760 (1) and
Honda 780 (1). Taking the lowest of several noisy small cells biases the ratio further up, and no interval is shown.

The fresh-entrant cut cannot answer this. It exists only at 24 months (`run_autos.py:84`), and it has no Exeter,
Santander, Toyota or Capital One cell.

**Evidence.** The same estimator with each loan counted from its third month in the pool, from the committed
parquet, without `absrisk`. At shift 0 it reproduces every published `b1_at_12.csv` cell (Honda 660 0.102%, Exeter
660 5.064%) and the published 49.6x:

```python
import glob, numpy as np, pandas as pd
d = pd.concat(pd.read_parquet(f) for f in glob.glob("data/autos/*.parquet")).reset_index(drop=True)
mi = lambda s: pd.to_datetime(s).dt.year * 12 + pd.to_datetime(s).dt.month
fp, om, lp = mi(d.first_period), mi(d.orig_month), mi(d.last_period)
ev = np.where(d.exit_type == "chargeoff", "co", np.where(d.exit_type.isin(["prepay", "repurchase", "other", "absent"]), "x", "c"))
ex = mi(d.zb_date).where(d.zb_date.notna(), mi(d.exit_period)).fillna(fp + d.months_observed - 1).where(ev != "c", lp)
lag = pd.Series(0, index=d.index)
for _, g in d.groupby("deal"):            # methods.md section 1: pool cutoff lag
    first = g.first_period == g.first_period.min()
    if ((ex[g.index] < fp[g.index]) & first & (ev[g.index] != "c")).any():
        lag[g.index[first]] = 1
e0 = (fp - lag - om).clip(lower=0).to_numpy()
x0 = (e0 + (ex - (fp - lag)).clip(lower=0)).to_numpy()
def aj12(m, k):                           # AJ charge-off by age 12; a loan counts from k months after it entered the pool
    e, x, v = e0[m] + k, x0[m], ev[m]
    e, x, v = e[x >= e], x[x >= e], v[x >= e]
    n = np.array([((e <= t) & (x >= t)).sum() for t in range(13)])
    co = np.array([((x == t) & (v == "co")).sum() for t in range(13)])
    out = np.array([((x == t) & (v != "c")).sum() for t in range(13)])
    s = np.concatenate([[1.0], np.cumprod(1 - out / np.maximum(n, 1))[:-1]])
    return (s * co / np.maximum(n, 1)).sum(), n[-1]
b = (d.score // 20 * 20).to_numpy()
for k in (0, 3):
    r = []
    for lo in range(660, 800, 20):
        c = {l: aj12((b == lo) & (d.lender == l).to_numpy(), k) for l in d.lender.unique()
             if ((b == lo) & (d.lender == l).to_numpy()).sum() >= 1500}
        c = {l: v[0] for l, v in c.items() if aj12((b == lo) & (d.lender == l).to_numpy(), 0)[1] >= 250 and v[0] > 0}
        if len(c) >= 3:
            r.append(float(max(c.values()) / min(c.values())))
    print(k, "median", round(float(np.median(r)), 1), [round(v, 1) for v in r])
-> 0 median 49.6 [49.6, 41.3, 73.2, 25.0, 69.3, 62.7, 3.6]
-> 3 median 33.3 [33.3, 20.2, 45.1, 17.1, 77.7, 38.9, 3.1]
```

| bucket | published | from the third month in pool |
|---|---|---|
| 660 | Exeter 5.06% / Honda 0.10% = 50x | Exeter 5.64% / Honda 0.17% = 33x |
| 680 | Exeter 4.70% / Toyota 0.11% = 41x | Exeter 4.95% / Honda 0.25% = 20x |
| median of seven | 50x (range 4 to 73) | 33x (range 3 to 78); 36x if, as `bucket_ratios` does, a bucket whose lowest cell has no charge-off (Toyota 680 here) is dropped |

In most buckets Honda's and Toyota's 12-month rates rise 1.5 to 3 times (Toyota 740: 0.16% to 0.52%). Exeter's rise
5 to 11% and Santander's 9 to 17% in 660-720. Three months is a lower bound on the correction, because months 3-5
still run at about two thirds of the seasoned hazard.

The entry/roll split is not inflated the same way. Its 30+ entry rates barely move or fall when the first three pool
months are dropped (Honda 660 0.064 to 0.060, CarMax 660 0.094 to 0.096), because a loan current at sale can be 30
days late a month later. The qualitative finding survives; the number does not.

**Fix.**
1. Compute the headline cells with delayed entry at three months in the pool (`ages()` gets a `pool_offset`). Better:
   use the hazard model's predicted 12-month cumulative incidence with `pool_b` fixed at `9+`.
2. Require at least ten charge-offs in a cell before it can be the denominator of a ratio.
3. Put a bootstrap interval on each bucket ratio and on the median, resampling loans within lender.
4. Publish the fresh-entrant cut at 12 months too, and say on the page what the pool window does to seasoned lenders.
   Also update "survives the obvious objections", the 700-779 "61 times" and methods.md section 1.

**Verify.** The snippet above, run at the shift the fix chooses, reproduces the page's median. No headline ratio has
a denominator cell with fewer than ten events. Each ratio on the page carries an interval.

### R2-2 · MEDIUM · Synchrony's "assumption-free" residual is calibrated to general-purpose cards, but its trust is a retail pool, a quarter of it private label

**What is wrong.** The level that turns a score mix into a predicted loss comes only from the CFPB's
general-purpose series (`shape/build_level.py:130,160`). The Synchrony trust is not a general-purpose pool. The
project's own notes say so (`cards/composition.py:53-54`, `design/scout-cards.md:414`: "private-label/retail pool").

Its prospectus (0001104659-26-092741, "Program Partner" table) splits receivables as follows:
- private label credit cards (Amazon, Lowe's): 24.3%;
- dual cards, which the CFPB's market report counts as general purpose: 70.4%;
- Synchrony Mastercard: 5.3%.

The CFPB's private-label charge-off rate in the same Figure 53 runs about twice the general-purpose one: 7.1% against
3.7% in 2019, and 8.5% against 5.3% in 2024.

The cards page says Synchrony "keeps the same sign under all 4, so it is the one trust whose gap does not depend on
the assumption" (`report/cards_page.py:130`), and that it is above its prediction "in every year since 2018" (the
since-when note). It also reports the gap as +1.07% to +1.73%. Both rest on a product assumption the page never
states.

**Evidence.** The same construction as `build_level.py`, using the "Private label" column of Figures 53 and 3,
applied to the private-label share of the pool (the workbook is the local copy under `data/raw/scout/cfpb/`):

| shape | published (all general purpose) | 24.3% private label | all private label |
|---|---|---|---|
| acms2018 | +1.07% | +0.41% | -1.63% |
| acms2018_dpd90 | +1.10% | +0.45% | -1.56% |
| fico_fed2007 | +1.73% | +1.15% | -0.66% |
| fico_odds | +1.64% | +1.05% | -0.77% |

At the 24.3% blend the sign survives, but Synchrony's lead over BofA under the two FICO shapes falls to 0.02 and
0.05 points (BofA +1.13% and +1.00%). Calibrated wholly as private label, Synchrony becomes the trust that loses
least against its mix.

```python
import openpyxl, pandas as pd
wb = openpyxl.load_workbook("data/raw/scout/cfpb/cfpb_consumer-credit-card-market-report-figure-data_2025.xlsm", read_only=True, data_only=True)
def fig(title):
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        for i, r in enumerate(rows):
            if title in [c for c in r if isinstance(c, str)]:
                hdr, out = list(rows[i + 1]), []
                for r2 in rows[i + 2:]:
                    if r2[0] is None: break
                    out.append(r2)
                return pd.DataFrame(out, columns=hdr)
T = ["Deep subprime", "Subprime", "Near-prime", "Prime", "Prime plus", "Superprime"]
co = fig("MONTHLY ANNUALIZED RATE OF BALANCES CHARGED OFF (CCIP)"); co["y"] = pd.to_datetime(co["Date"]).dt.year
cons = fig("CREDIT CARD CONSUMERS, YEAR-END 2023 (CCIP)").set_index("Credit score tier")
bal = fig("MONTHLY AVERAGE PER-CARDHOLDER CYCLE-ENDING BALANCES (CCIP)"); bal["y"] = pd.to_datetime(bal["Date"]).dt.year
bal = bal.groupby("y")[T].mean()
syn = dict(zip(T, [0.0576, 0.0631, 0.1180, 0.2720, 0.2988, 0.1905]))       # data/results/cards/mix_by_trust.csv
sh = pd.read_csv("data/loss_shape.csv").dropna(subset=["relative_loss"])
names = dict(zip(T, ["deep_subprime", "subprime", "near_prime", "prime", "prime_plus", "superprime"]))
m = pd.read_csv("data/cards_monthly.csv", parse_dates=["period_end"]).query("trust == 'synchrony'")
for s, g in sh.groupby("shape_source"):
    v = {t: float(g.set_index("tier").loc[names[t], "relative_loss"]) for t in T}
    def level(p, y):
        mix = {t: cons.loc[t, p] * bal.loc[y, t] for t in T}
        return co[co.y == y][p].mean() / (sum(mix[t] * v[t] for t in T) / sum(mix.values()))
    res = {}
    for w in (0.0, 0.243, 1.0):                                              # share of the pool calibrated as private label
        y = m.period_end.dt.year.clip(2014, 2024)
        lv = y.map(lambda yy: (1 - w) * level("General purpose", yy) + w * level("Private label", yy))
        res[w] = (m.gross_co_rate - lv * sum(syn[t] * v[t] for t in T)).mean()
    print(f"{s:<15}" + "  ".join(f"PL {w:.0%}: {r:+.2%}" for w, r in res.items()))
```

**Fix.**
1. Record each trust's private-label share from its prospectus program table in the composition step (Synchrony
   24.3%; zero for the general-purpose trusts).
2. Calibrate a blended level per trust from both CFPB columns, and add the private-label series to `ccmr_level.csv`.
3. Until then, the cards page states the assumption next to the Synchrony sentence and drops "does not depend on the
   assumption". The conclusions page says the same where it uses Synchrony as the baseline.

**Verify.** `mix_by_trust.csv` (or a new column) carries the private-label share. The Synchrony row on the page
matches the blended column above. A test pins that a trust with a nonzero private-label share is not calibrated to
the general-purpose level alone.

### R2-3 · MEDIUM · "The ends of the ranking hold" ignores the project's own straddle sensitivity, and the conclusions page calls Citi an end

**What is wrong.** Round 1 asked for a straddle-rule sensitivity, and `a1_straddle.csv` now has one. Its answer
contradicts two headline sentences:

- The cards page says Amex "charges off least relative to its mix under every shape" (`report/cards_page.py:108-118`).
  Under the upper straddle bound with acms2018_dpd90, Citi is last and Amex fifth.
- Under the lower bound, Citi ranks fourth under every shape.
- The conclusions page says "Under all four, the ends of the ranking hold (amex, citi, synchrony keep their place)
  ... The ordering of the extremes is a finding" (`report/conclusions_page.py:157-163`). Citi is fifth of six, not
  an end, and both its rank and Amex's move with the straddle rule.

Only Synchrony keeps one rank in all twelve shape-rule cells, and R2-2 qualifies even that. The cards page's own
straddle paragraph says the rank statements hold under the uniform rule only. The conclusions page has no such
qualifier.

**Evidence.**

```
python -m uv run python -c "import pandas as pd; s = pd.read_csv('data/results/cards/a1_straddle.csv'); print(s.pivot_table(index=['shape_source','trust'], columns='straddle_rule', values='rank').loc[(slice(None), ['amex','citi','synchrony']), :])"
-> acms2018_dpd90 amex: lower 6, uniform 6, upper 5;  citi: lower 4, uniform 5, upper 6
   every shape, citi under 'lower': 4;  synchrony: 1 in all twelve cells
```

**Fix.** Compute "keeps its place" over shape x straddle rule, not over shape alone, in both page builders (one
function, shared). Name only trusts at rank 1 or rank N as ends. With today's data the sentence becomes: Synchrony
ranks first in all twelve cells; Amex is last in eleven of twelve.

**Verify.** A test builds both pages from a rank table in which the bottom trust moves under one straddle rule, and
asserts that neither page calls it a held end.

### R2-4 · MEDIUM · "Selection on every level comparison" is contradicted by Citi in cards and by AmeriCredit, which the conclusions page silently drops

**What is wrong.** The landing page says "On every level comparison it is selection, in cards and in auto loans"
(`docs/index.html:21-22`). The conclusions page's computed heading says "selection, on every level comparison"
(`conclusions_page.py:98-101`). The fixed text then says:

- "priority would show up as accounts rescued from deep delinquency and the opposite is observed" (`:166-169`);
- "their late accounts are not rescued more often than anyone else's" (`:184-188`).

Two comparisons on the project's own tables say otherwise:

- **Citi.** It is the second-lowest card trust by residual. Its 90-day-late balances convert to loss least of all six
  trusts (27.2% a month, 0.85 times Synchrony's), and conversion carries +0.20 of its gap. Citi's late accounts are
  rescued more often than anyone else's. The cards page says so (`cards_page.py:182`); the conclusions page says the
  opposite.
- **AmeriCredit.** It loses 26% less than Santander at the same score (median total ratio 0.74 over ten buckets).
  Only 42% of that is entry; 58% is the roll from 30 days late to charge-off (roll ratio 0.84). The conclusions page
  shows lenders with an entry share of at least 0.7 as selection and at most 0.3 as the exception
  (`conclusions_page.py:44-45`). AmeriCredit, at 0.42, appears nowhere.

**Evidence.**

```
python -m uv run python -c "import pandas as pd; a = pd.read_csv('data/results/autos/b6_attribution_by_score.csv'); a = a[a.n_ever30 >= 100]; print(a.groupby('lender')[['entry_share_of_gap','roll_ratio','total_ratio']].median().round(3))"
-> americredit 0.421 0.844 0.741; carmax 1.032 1.072 0.164; exeter 0.004 1.408 1.368; honda 0.842 0.754 0.087; toyota 0.856 0.759 0.161
   data/results/cards/a3_by_trust.csv citi: conversion 0.2721, conversion_ratio 0.8475, conversion_share_of_gap +0.1954
```

**Fix.** Compute the sentences from the tables.
1. List every lender and trust with its entry share. Name the ones where entry is under half: AmeriCredit, and Citi's
   conversion share.
2. Replace "not rescued more often than anyone else's" with a statement about the lowest-loss trust (Amex) that the
   table carries.
3. Rewrite the landing page line to match ("mostly selection; AmeriCredit and Citi partly after trouble").

**Verify.** The conclusions page names every lender in `b6_attribution_by_score.csv` with enough cells. A test fails
when a fixed sentence asserts something about "issuers with low losses" that one of them contradicts.

### R2-5 · MEDIUM · In dark mode the "actual" line of every cards chart is invisible

**What is wrong.** Section 3 of the cards page ("Actual against predicted, by trust") draws the actual charge-off
series with a hard-coded stroke `#1d1d1b` (`report/cards_page.py:301`). The page shell defines a dark theme
(`report/svg.py:134-136`) whose chart card is `#1d1f25`. The contrast is 1.03:1. A reader whose phone is in dark mode
sees four "predicted" lines and no actual line in all six charts. The legend still lists "actual", with an invisible
swatch.

Round 1 checked these pages at 375 px but not in dark mode. Cosmetic, same charts: x-axis ticks read 11.6375, 23.275,
34.9125 ("months from 2018-12-31"), because `line_chart` prints `{xv:g}` of fractional months (`report/svg.py:38`).

**Evidence.** Live page in the browser pane, 375 x 812, `prefers-color-scheme: dark`: the polyline titled "actual" has
stroke `#1d1d1b` on a `rgb(21, 22, 26)` page. Contrast of every chart colour against the dark card: `#1d1d1b` 1.03,
every other series 2.5 to 7.5.

**Fix.** Let `line_chart` take a theme colour: `{"color": "fg"}` emits `style='stroke:var(--fg)'` (and the same for
the legend swatch). Use it for "actual". Round x ticks to whole months or years.

**Verify.** A test over `docs/*.html` fails on any chart stroke or fill whose contrast against either theme's card
colour is under 3:1. The live cards page in dark mode shows a light "actual" line.

### R2-6 · MEDIUM · One commit with a personal email address would stop every scheduled refresh, and only a history rewrite could restart it

**What is wrong.** The refresh's first real step runs the whole test suite, before it fetches anything
(`.github/workflows/cards-refresh.yml:51-52`). The suite includes
`test_commits_since_the_review_carry_noreply_addresses`, which fails on any commit since 6a18549 whose author or
committer address is not a noreply one (`tests/test_no_leaks.py:99-112`).

So suppose the user edits a file on github.com without email privacy on, or commits from another machine. From then
on every Monday and Thursday run fails at "Tests". No data is fetched and no page is rebuilt. Only two things undo
it: rewriting public history, the decision HANDOFF leaves to the user, or editing the test. The leak check is right
to exist. What is wrong is gating the data pipeline on commit metadata the pipeline cannot repair.

**Evidence.** In a local clone of HEAD, one commit authored with an ordinary webmail address, then
`pytest tests/test_no_leaks.py` -> `FAILED tests/test_no_leaks.py::test_commits_since_the_review_carry_noreply_addresses`
(1 failed, 2 passed).

**Fix.** Mark the commit-metadata test (e.g. `@pytest.mark.repo_hygiene`) and run `pytest -m "not repo_hygiene"`
in the refresh. Keep it in the local suite, and as a check on pushes from people rather than on the bot's schedule.

**Verify.** With the planted commit, the refresh's Tests command passes and the local full suite still fails.

### R2-7 · LOW · HANDOFF expects October rows from the Monday 2026-11-16 run, which runs before EDGAR opens

All six trusts file their 10-D on the 15th or the next business day. The July 2026 statements were all accepted on
2026-08-17, between 06:02 and 14:00 Eastern (the `ACCEPTANCE-DATETIME` in each scouted index-headers file). 15
November 2026 is a Sunday, so the October 10-Ds land during Monday the 16th. The cron fires at 09:17 UTC, which is
04:17 Eastern, before EDGAR accepts filings at 06:00. The first run that can commit October rows and exercise the
rebuild branch with changed tables is Thursday 2026-11-19.

HANDOFF.md:90 tells the next session to expect it on the 16th. A session that sees "no changes" that day may hunt
for a bug that is not there. HANDOFF.md:3 also dates itself 2026-11-10, against 2026-11-09 local time in the commit.

**Fix.** Say "the Thursday 2026-11-19 run"; date the handoff in local time. **Verify.** `grep -n "Monday run should" HANDOFF.md` returns nothing.

### R2-8 · LOW · Templated headline sentences assert what they never check

`report/cards_page.py:94-118` picks the stable trust with the best rank and prints that it "charges off more than its
own score mix predicts under every one of the N shapes". It never checks that the residual is positive under every
shape. It prints "The ends of the ranking hold; the middle does not" even when no trust moves. Fed a rank table in
which Synchrony is first but negative under one shape, it prints:

```
synchrony charges off more than its own score mix predicts under every one of the 4 shapes (residual -0.10% to +1.50%);
... 0 of 3 trusts change rank ... So the ordering of the extremes is a finding and the ordering of the middle is not.
```

`direction_sentences` similarly calls a move "the direction prioritisation predicts" whenever it is negative, even
inside the 0.05 band it calls flat elsewhere. Today every sentence is true. But the refresh rebuilds these pages
unattended twice a week, and `tests/test_pages.py` only checks that a page equals its own rebuild.

**Fix.** Guard each templated claim with the condition it states, and fall back to a neutral sentence. Add a test
that feeds adversarial tables and checks the wording. **Verify.** The table above yields no "more than ... under every
one" sentence.

### R2-9 · LOW · A failure in the stage or panel step leaves last run's tables in place, and both pages publish them

`estimate/run_cards.py:219-231` catches any exception in the stage step. It overwrites `a3_stages.csv` with
"not computed: ..." and leaves `a3_by_trust.csv`, `a3_stress.csv` and `a3_regimes.csv` as the previous run wrote
them. Both pages read those three, so a refresh with a new month publishes stage numbers from the old data.
`tests/test_cards_results.py` compares a rebuild with itself on the runner, so the run stays green. The panel step
(`:233-246`) does the same with `a2_panel_summary.txt`.

**Fix.** Delete or overwrite every output of a step before running it, or let the exception fail the run. **Verify.**
Monkeypatch `cards_roll.regimes` to raise; `absrisk analyze cards` exits non-zero or leaves no stale a3 file.

### R2-10 · LOW · Two promises the code does not keep

- `cards/check.py:12-14` says the stale-mix warning "is printed in the run log and on the cards page". No page code
  reads `stale_mixes`. From the October data on, Citi's 19-month-old mix will warn in the log only.
- The landing page is hand-written (`docs/index.html`), and the refresh rebuilds only the cards and conclusions pages.
  Its "a test on how losses move with the cycle is mixed" and the R2-4 sentence will not follow a change in the
  computed verdict.

**Fix.** Print the warning in the cards page header, and either generate the index's two result sentences from the
same tables or drop them. **Verify.** A stale-mix fixture shows the warning on the built page.

### R2-11 · LOW · The runner and the local machine build results with different Python versions

Run 42727357720's log reads "Using CPython 3.14.4 interpreter at: /usr/bin/python3" (ubuntu-latest is now an
Ubuntu 26.04 image). Local runs use 3.12.10. There is no `.python-version`, and `setup-uv` gets no `python-version`.
`uv.lock` pins packages but not the interpreter, so committed results come from whichever machine ran last. One
forced rebuild was byte-identical, but nothing holds that. A runner image moving to a Python without wheels for a
locked package would break `uv sync` on a scheduled run.

**Fix.** Add `.python-version` with `3.12`, and `python-version: "3.12"` to `setup-uv`. **Verify.** The run log
shows CPython 3.12.

### R2-12 · LOW · autos-build can exceed the SEC's 10 requests a second in aggregate

`.github/workflows/autos-build.yml:49` runs up to four deal jobs at once. Each has its own `make_session()` throttle
at 5 requests a second, all under the same User-Agent and contact address, so the aggregate can reach 20 a second
during the index and listing phase. The SEC's limit is per user. The workflow is dispatch-only and EX-102 downloads
are slow, so real bursts are short. CLAUDE.md's 5-a-second cap reads as a project limit, not a per-job one.

**Fix.** `max-parallel: 2`, or pass a per-job rate of 5 divided by `max-parallel`. **Verify.** A dispatched run's
log shows no more than 10 requests in any second across jobs.

### R2-13 · LOW · The direction test's "tight" months are mostly two calendar eras

Months above the median delinquency index run from December 2018 to June 2020 (19) and from September 2023 to May
2025 (21), plus seven months of 2025-26. The loose months are mid-2020 to mid-2023, the stimulus and forbearance
years. So "tight against loose" largely compares 2019 and 2024-26 with 2020-23, eras that also differ in charge-off
and re-aging practice. The page does not list the months.

**Fix.** Print the tight months (or a strip chart of the index) under the table, and add the split inside 2024-26
alone. **Verify.** The page shows which months are tight.

---

## Still open from round 1 (the user's decision, not counted above)

- `CLAUDE.md:5` names a local path with the Windows account name (R1-2, deferred). The fix is a one-line edit to a
  relative mention, then deleting the `KNOWN` entry in `tests/test_no_leaks.py`.
- 43 commits carry a personal email address (R1-16), and the old paths sit in public history (R1-2 item 3). Removing
  them needs `git filter-repo` and a force push to `main`.

---

## Bigger improvements (ranked)

1. **Pool-time-adjusted incidence for autos** (R2-1). Report cumulative charge-off from the hazard model with months
   in pool held at `9+`, or with delayed entry at pool month three. Add a minimum of ten events per cell and a
   bootstrap interval on every ratio. This replaces the headline that is most likely to be quoted and is now
   overstated.
2. **Product-consistent card calibration** (R2-2). Carry each trust's private-label share from its prospectus, add the
   CFPB private-label series to `ccmr_level.csv`, and calibrate each trust to its own blend. Show Synchrony under all
   three calibrations until the blend is the default.
3. **One robustness grid behind every card sentence** (R2-3, R2-4, R2-8). Compute "holds" over shape x straddle rule
   x product calibration in one place. Have every templated sentence assert its own precondition, and test the
   wording against adversarial tables.
4. **Composition history** (round 1 improvement 2, still the main card gap). Back-fill only before each trust's first
   snapshot; the panel's trust effects may then be identified.
5. **CI that the bot can always pass** (R2-6). Split repo-hygiene tests from data tests. Add a calendar check that
   fails when the newest month is more than 50 days older than the run date, which covers every trust stalling at
   once.
6. **Theme-aware charts** (R2-5): colours as CSS variables, and a contrast test over `docs/*.html` in both themes.
7. **An autos freshness test like `test_cards_results.py`.** b1 and b6 rebuild in about 90 seconds and are
   byte-stable. A code change that is not followed by `absrisk analyze autos` would then fail locally, as it already
   does for cards.
8. **Pin the interpreter** (R2-11) so the local and runner builds use one Python.

---

## Checked and solid

**Tests.** 333 passed locally, 1 warning (the saturated-panel SingularMatrixWarning), 247 s with BLAS at two
threads. On the runner, one workbook test skips, as documented.

**Runs.** `gh run list`: no failed run since 42698996217. That one, and 39438090561 (2026-10-20), are the two
failures round 1 explained; both are fixed and every later run succeeded. Run 42727357720's log, read in full:
- cache restored from cards-raw-42726294384;
- 569 filings skipped, 0 fetched;
- the three known COMET 2019 failures, 561 rows;
- composition 138 rows, 36 crosswalk rows;
- "check passed";
- forced rebuild, both result tests passed, "no changes".

The caches list `last_accessed_at` within a day.

**An October refresh, simulated.** Appending an October row per trust and running `analyze cards`, both page builders
and `cards check` works: "Data through October 2026", 95 months split 47/48, the Citi 19-month warning, "check
passed".

**Independent re-derivations from raw inputs** (no `absrisk` import):
- *Card residuals.* FICO tables parsed with BeautifulSoup from the raw BofA, Chase, Citi, COMET and Synchrony
  prospectuses (bucket shares equal the committed ones to six decimals). Mapped uniformly in score to the six tiers,
  unscored dropped. Level from Figures 3, 16 and 53 of the raw 2025 CFPB workbook via openpyxl: rates equal
  `ccmr_level.csv` to 3.3e-7, tier shares to 7.6e-7. All 24 trust-shape mean residuals equal `a1_ranking.csv` to
  under 0.00005 points. Amex's 2026 prospectus is not on this machine, so its committed composition rows were used.
- *Delinquency inputs.* Every July 2026 30+ and 90+ bucket amount for all six trusts was found in the raw 10-D text
  (Citi's denominator is the sum of current and buckets). The shares equal `cards_monthly.csv` to 5e-9.
- *Stages and the direction test,* from `cards_monthly.csv`. Amex 0.370 / 0.288 / 1.387, entry share 1.254; largest
  difference from `a3_by_trust.csv` 5e-11. Tight minus loose: Amex -0.099, Citi +0.090, BofA, Chase and COMET flat.
- *Autos.* The loan count in one month's raw EX-102 equals the loans the parquet shows present that month, for six
  deals: 72,469; 46,343; 78,455; 36,112; 52,812; 55,323. Capital One's 223 charge-offs and CarMax 2026-2's 37 equal
  the raw `zeroBalanceCode` 4 counts. Every 12-month AJ cell in 660-799 was reproduced exactly; the same-bucket gap
  is 49.6x, and 37.7x without Exeter or on the past-850 lenders.

**Rebuilds.** Autos b1 (eight tables), b6 (five tables) and b2 (`b2_hazard_ratios.csv`, `b2_lender_intervals.csv`,
`b2_fit.json`; 7 minutes on two threads) rebuilt from the committed parquet into a scratch folder are byte-identical
to the committed files. b2x and the RD stages were not rebuilt.

**Live pages.** All four return 200 and equal `docs/` after newline normalisation. Cards and autos at 375 px: standards
mode, `scrollWidth` 375, nothing overflowing outside table scrollers.

**Leaks and secrets.** The round-1 path grep finds only the deferred CLAUDE.md line. The diffs since 6a18549 have no
token, key or private-key pattern. Every commit since 6a18549 uses a noreply address.

**Input handling.** EX-102 is parsed with lxml 6.1.3 `iterparse`, which since lxml 5 does not resolve external
entities. HTML is parsed with BeautifulSoup. There is no pickle, `eval` or `shell=True`, and `git show` runs with a
list argv.

**EDGAR etiquette.** `make_session()` is unchanged: `abs-risk/<version> <contact>`, 0.2 s between requests, retries
honouring Retry-After. Tests never touch the network.
