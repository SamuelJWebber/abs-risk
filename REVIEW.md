# Review round 1 (2026-11-09)

Adversarial review of `main` at `d321697`, after the 2026-11-09 pass (dedupe on ingest, card pages rebuilt,
section 6 corrected, golden checks, weekly refresh). There is no earlier REVIEW.md, so no previous finding was
marked Fixed and none could regress. The fixes the 11-09 pass made were re-checked anyway; they hold, with one
partial exception (R1-9).

**Counts: 2 HIGH, 5 MEDIUM, 10 LOW.**

The short version: every headline number re-derives from the raw inputs with independent code, so the arithmetic
is sound. The wrong things are elsewhere:

- one silent method slip that moves published card numbers (R1-1);
- personal environment details in this public repo (R1-2);
- a weekly job that can go stale while staying green (R1-3);
- three claims the data does not carry as stated (R1-4, R1-5, R1-6);
- one undisclosed look-ahead in the card mix (R1-7).

How it was run: `python -m uv run pytest -o addopts=""` (252 passed, 169 s); both failed cards-refresh logs and both
11-09 dispatched runs read in full; `git log -p -20` read line by line; the card rebuild branch run on an exported
copy of HEAD; the live Pages fetched and compared; six headline numbers re-derived from raw inputs with code that does
not import `absrisk`. The audit skill's four personas (silent wrong answer, stranger who cloned the repo, leak hunter,
bad actor) were run in-process, because this reviewer had no subagent tool. Nothing touched EDGAR and nothing heavy
ran; the 15-minute autos pipeline was not re-run.

Severity: HIGH = wrong result, data loss, broken run, privacy or security; MEDIUM = a claim or safeguard that does
not hold as stated; LOW = cosmetic, stale, or a weakness without a wrong number today.

---

## Findings

### R1-1 · HIGH · The card analysis spreads unscored balances across the whole 300-850 range, against its own crosswalk

**What is wrong.** Take the limit case: a trust whose prospectus put 100% of balances in "Unscored". The documented
rule (`src/absrisk/shape/tiers.py:68-69`: "Buckets for accounts with no score cannot be mapped; drop them and
renormalise") and the committed crosswalk (`crosswalks/fico_buckets.csv`, `src/absrisk/cards/composition.py:422`:
"unscored: weight 0; tier shares renormalised over scored buckets") would refuse to place it. The analysis instead
reads the empty edges as `(None, None)` (`src/absrisk/estimate/run_cards.py:49-58`), and `tiers_from_buckets` treats
`(None, None)` as 300-850 (`tiers.py:43-48`). That puts 280/551 = 51% of the unscored balance in deep subprime.

The analysis never reads the crosswalk file at all. `estimate/cards.py:16` `tier_mix_by_trust` and `:38`
`predict_by_trust`, the crosswalk-based path, are dead code. So the file that PLAN section 2 calls "explicit", and
that the refresh regenerates and tests every week, has no effect on any published number.

Unscored shares are small (0.03% Amex to 0.69% BofA), so the headline ordering survives. But printed numbers move:

| page cell | published | under the documented rule |
|---|---|---|
| cards section 1, BofA deep subprime | 2.3% | 1.9% |
| cards section 4, BofA residual, fico_fed2007 | +1.07% | +1.13% |
| cards section 4, BofA residual, fico_odds | +0.95% | +1.00% |
| cards section 4, Citi residual, fico_fed2007 | +0.53% | +0.57% |
| cards section 4, rank under acms2018_dpd90, BofA / COMET | 3 / 2 | 2 / 3 (a near tie: -0.371% vs -0.373%) |

**Evidence.**

```
python -m uv run python -c "import pandas as pd; from absrisk.cards.composition import read_csv, tier_shares; from absrisk.estimate.run_cards import mix_by_trust; xw = tier_shares(read_csv('data/cards_composition.csv'), read_csv('crosswalks/fico_buckets.csv')); m = mix_by_trust(pd.read_csv('data/cards_composition.csv')).set_index('trust'); print({t: round(m.loc[t,'deep_subprime'] - xw[(t,'receivables')]['deep_subprime'], 4) for t in m.index})"
-> {'amex': 0.0002, 'bofa': 0.0034, 'chase': 0.0007, 'citi': 0.0019, 'comet': 0.001, 'synchrony': 0.0}
```

An independent re-implementation of predicted = level(year) x (mix . shape) reproduces every committed
`a1_ranking.csv` residual to 0.001 pp with the committed mix. With unscored dropped it gives the right-hand column
above.

**Fix.**
1. Build the analysis mix from the crosswalk: call `tier_shares` on the committed crosswalk, or drop `lo is None and
   hi is None` rows in `mix_by_trust` and renormalise.
2. Delete the dead crosswalk functions in `estimate/cards.py`.
3. Rerun `absrisk analyze cards`, `report cards` and `report conclusions`.

**Verify.** Add a test that `mix_by_trust(composition)` equals `tier_shares(composition, crosswalk)` for every trust to
1e-9. It fails today with a 0.0034 gap at BofA. After the rebuild, the BofA fico_fed2007 residual on the cards page
reads +1.13%.

### R1-2 · HIGH · This public repo carries absolute local paths that name the user's account, sync folder and a private project

**What is wrong.** Commit 8cf68b2 says the free-riding tree was "scanned before committing ... no local paths". It
was not clean:

- 22 tracked files hold 52 lines of absolute Windows paths.
- Most sit under `design/freeride/`; the rest are `design/free-riding-bias.html:239`, `design/scout-autos.md:3`,
  `design/scout-cards.md` and `CLAUDE.md`.
- They expose the Windows account name, the cloud-sync folder layout, and in 8 files the name of a sibling project.
  That project's repository is private (confirmed with `gh repo list`).
- This repo is public under the real-name account, so anyone can read them, including on GitHub's code search.
- No credentials or third-party personal data were found. A scan of all 64 commits for tokens and keys was clean.

The same paths make the free-riding scripts unrunnable from a clone (`design/freeride/trust-cycle/run.py:15`
hard-codes the repo root; the LendingClub inputs are read from a temp folder of another project).

**Evidence.** This pattern deliberately avoids the private names, so this file does not repeat them:

```
git grep -c -I -E "C:[/\\]Users|AppData[/\\]Local|OneDrive" -- . ':!uv.lock'
-> 22 files, 52 lines (design/freeride/workflow-results.json:25, lc-decisive/*.py: 2 each, ...)
```

**Fix.**
1. In one commit, replace every absolute path with a repo-relative path or a placeholder such as `<scratch>/`.
   Do this in the `.py`, `.txt`, `.json` and `.html` files under `design/`, in `design/scout-*.md` and in `CLAUDE.md`.
2. Add a test that fails when tracked text matches `C:[/\\]Users|AppData|OneDrive`.
3. Removing the strings from history needs `git filter-repo --replace-text` and a force push to the public `main`.
   That rewrite is destructive, so it is the user's call.

**Verify.** The `git grep` above returns nothing. The new test fails on a planted path and passes on the scrubbed tree.

### R1-3 · MEDIUM · The weekly refresh stays green when a new month fails to parse, so a trust can go stale unnoticed

**What is wrong.** Take the limit case: a trust changes filer agent and its October 10-D layout breaks the parser. That
has already happened three times in this corpus (Synchrony 2019, BofA 2025, Amex 2025).

- `absrisk cards parse` logs the failure and still exits 0 (`src/absrisk/cards/__init__.py:79-104`: `return 1 if not
  rows else 0`).
- The workflow runs it without `--strict` (`.github/workflows/cards-refresh.yml:47-48`).
- The post-parse checks (`cards-refresh.yml:51-53`: dedupe, golden for July 2026, composition) never look at the
  failure log.

So the run commits the grown failure log, reports success, and leaves both pages ending in September. Nobody is
emailed, because nothing failed. The user follows this repo from a phone.

**Evidence.** A copy of the BofA fixture with its charge-off label altered:

```
absrisk cards parse --raw <tmp>/raw --trust bofa --out <tmp>/m.csv --failures <tmp>/f.csv; echo $?
-> ERROR bofa 0001140361-26-099999: ParseError: bofa: no charge-off table headed 2026-07-31
-> 1 filings failed to parse, 0 months filed twice ... ; exit code 0
```

**Fix.** Add a post-parse check: fail when `data/cards_parse_failures.csv` gains an accession that is not in the
committed copy (`git show HEAD:data/cards_parse_failures.csv`). Also fail when any live trust's latest `period_end`
trails the newest trust's by more than one calendar month. The three known COMET 2019 failures stay allowed because
they are already committed.

**Verify.** Plant a corrupted copy of a fixture filing under a new accession in a temp raw dir. The new check exits
non-zero. On the unmodified tree it passes.

### R1-4 · MEDIUM · The card "direction test" compares two periods with the same delinquency; a real tightening shows the opposite

**What is wrong.** The test reads conversion moving the wrong way "in a squeeze" as evidence against prioritisation.
The cards page section 5 and the conclusions page "second test" put it this way: "Between pre-covid 2019 and squeeze
2023H2 on it did the opposite ... fell for none".

By the trusts' own delinquency, though, "squeeze 2023H2 on" is not tighter than "pre-covid 2019". Every trust's 30+
share is lower in the squeeze (x0.75 to x0.93). The low-delinquency periods are the middle two. The one transition in
which every trust's delinquency rose is normalising 2022-23H1 to squeeze 2023H2 on (x1.15 to x1.55). Across it,
BofA's conversion ratio fell 0.13 and COMET's 0.07, which is the direction prioritisation predicts. Amex, Chase and
Citi were flat.

"Delinquency itself swung with the cycle, so the pressure was real" (`cards_page.py:120-128`) uses the max/min swing
across all four periods, not the two endpoints the test compares.

**Evidence.**

```
python -m uv run python -c "import pandas as pd; m = pd.read_csv('data/cards_monthly.csv', parse_dates=['period_end']); P = {'pre': ('2019-01-01','2020-02-29'), 'norm': ('2022-01-01','2023-06-30'), 'squeeze': ('2023-07-01','2030-12-31')}; print(pd.DataFrame({k: m[m.period_end.between(a, b)].groupby('trust').delinq_30plus_share.mean() for k, (a, b) in P.items()}).round(4))"
-> 30+ share       pre      norm   squeeze   conversion ratio  pre   norm  squeeze
   amex          0.0098   0.0055   0.0076                    1.13   1.46   1.48
   bofa          0.0161   0.0100   0.0139                    0.99   1.21   1.08
   chase         0.0117   0.0075   0.0087                    1.13   1.24   1.22
   citi          0.0157   0.0095   0.0141                    0.86   0.84   0.88
   comet         0.0199   0.0119   0.0184                    0.91   1.01   0.95
```

The ratios come from `data/results/cards/a3_stress.csv`, re-derived independently from `cards_monthly.csv`
(amex 1.126 / 1.342 / 1.463 / 1.477).

**Fix.**
1. Define loose and tight periods from the data, for example months above or below the pooled median 30+ share, or
   report every period pair.
2. Rewrite both paragraphs to say the result is mixed. Amex rises against the low-delinquency periods; BofA and
   COMET fall on the only clean tightening.
3. Code: `estimate/run_cards.py:25-30`, `report/cards_page.py:108-145`, `report/conclusions_page.py:117-131`.

**Verify.** The page prints each period's mean 30+ share next to the ratios. The "fell for" list is computed from a
transition in which delinquency rose.

### R1-5 · MEDIUM · The conclusions page's two-factor formula does not reproduce the numbers in its own table

**What is wrong.** The page states "loss = entry x conversion", with conversion "the chance that falling behind
becomes a write-off" (`report/conclusions_page.py:81-83`). It then tables only those two factors (`:97-100`). But the
computed `conversion` is monthly charge-off divided by the 90+ share (`estimate/cards_roll.py:49`), and the identity
needs a third factor, progression (90+/30+, about 0.47 to 0.51).

A reader checking Amex gets 0.74% x 44.9% = 0.33%, not the 0.153% in the same row. The note under the table
(`:101-102`) says "the three shares ... their product is the charge-off rate" while showing two. The shares of the gap
shown (Amex entry 124%, conversion -33%) sum to 91%. The missing 9% is progression, which is never shown on this page.

**Evidence.** `docs/conclusions.html` table row: `amex | 94 | 0.153% | 0.74% | 44.9% | ...`. The cards page section 5
carries the correct three-factor identity and the progression column, so the two pages disagree.

**Fix.**
1. Print the three-factor identity and the `progression` and `progression_share_of_gap` columns on the conclusions
   page.
2. Define conversion as "the monthly charge-off as a share of balances 90+ days late".

**Verify.** For every row, entry x progression x conversion equals co_monthly to rounding, and the three shares sum to
1 +/- 0.03. They do not sum exactly, because `by_trust` takes ratios of means; say so in one line or use geometric
means.

### R1-6 · MEDIUM · Lender intervals and p-values on the autos page are clustered over 10 deals; four lenders own a single deal

**What is wrong.** The hazard logits use cluster-robust errors by deal with normal critical values
(`src/absrisk/estimate/hazard.py:91-92`). There are 10 deals and about 90 parameters. AmeriCredit, Capital One, Honda
and Toyota own exactly one deal each.

For those four, the lender dummy coincides with one cluster. At the MLE that cluster's score for the dummy is zero, so
the sandwich carries no between-deal variance for them. Their intervals measure within-deal noise only. In a simulation
with deal-level shocks (the reason to cluster at all), the reported SE is about a third of the true sampling spread
for single-deal lenders and two thirds for two-deal lenders.

Affected on the page:
- chart 2's lender bars;
- the prepayment table's p-values (AmeriCredit "p 0.000");
- Exeter vs Santander, 1.13 [1.004, 1.276], p = 0.043, which is not distinguishable from 1 under honest errors.

The captive gaps (Honda 0.16 [0.11, 0.23]) would survive intervals three times wider. The amount, PTI and LTV
estimates vary within deals and are not degenerate, but 10 clusters still understate their width somewhat.

**Evidence.** Simulation: 10 deals, lenders A-D own one deal, E-F own two, G is the baseline, deal shock sd 0.3,
300 replications, the same `GLM(...).fit(cov_type="cluster")` call:

```python
import numpy as np, statsmodels.api as sm
rng = np.random.default_rng(0); deals = list("ABCDEEFFGG"); L = list("ABCDEF")
est, se = [], []
for _ in range(300):
    u = rng.normal(0, 0.3, 10); X, Y, G = [], [], []
    for d, l in enumerate(deals):
        for _ in range(60):
            x = rng.normal(); k = rng.binomial(400, 1 / (1 + np.exp(4 - 0.5 * x - u[d])))
            X.append([1, x] + [float(l == m) for m in L]); Y.append([k, 400 - k]); G.append(d)
    r = sm.GLM(np.array(Y), np.array(X, dtype=float), family=sm.families.Binomial()).fit(
        cov_type="cluster", cov_kwds={"groups": np.array(G)})
    est.append(r.params[2:]); se.append(r.bse[2:])
print(dict(zip(L, (np.array(se).mean(0) / np.array(est).std(0)).round(2))))   # 1.0 = honest SE
-> {'A': 0.35, 'B': 0.34, 'C': 0.33, 'D': 0.33, 'E': 0.65, 'F': 0.67}
```

**Fix.**
1. Report lender effects with a wild cluster bootstrap over deals (Webb weights, 10 clusters).
2. Alternatively, drop intervals and p-values for lenders with one deal and say why.
3. Use t(G-1) critical values for the within-deal factors.
4. Reword "Exeter 1.13" as indistinguishable from Santander unless the new interval excludes 1.

**Verify.** On the simulation above, the new method's mean SE / sampling SD is close to 1 for every lender. On the
real data, the rerun interval for Exeter is printed next to the old one.

### R1-7 · MEDIUM · 92% of predicted card months use a mix snapshot from the future, and each new prospectus rewrites all of history

**What is wrong.** `prospectus_files` keeps only the newest prospectus per trust (`cards/composition.py:337-350`).
`predicted` back-fills that single snapshot to every earlier month (`estimate/run_cards.py:84-88`). So the Amex
prediction for December 2018 uses the Amex pool of July 2026.

Across the six trusts, 92.3% of trust-months are predicted from a snapshot dated after them. When a trust files a new
prospectus, the weekly refresh silently changes every historical residual for that trust. This happened on 11-09 for
Amex and COMET.

In the same way, 22.5% of months (all of 2025-2026) use the 2024 CFPB level (`run_cards.py:90`, `level_year_clamped`).
The page states neither. Its scope note says the mix "is held fixed between prospectus dates"
(`report/cards_page.py:14-15`), which never applies, because only one date is ever kept.

**Evidence.**

```
python -m uv run python -c "import pandas as pd; p = pd.read_csv('data/results/cards/a1_predicted.csv'); p = p[p.shape_source == 'acms2018']; print(round(p.mix_extrapolated.mean(), 3), round(p.level_year_clamped.mean(), 3))"
-> 0.923 0.225
```

**Fix.**
1. Short term: print both shares on the cards page and replace "held fixed between prospectus dates" with "one
   snapshot per trust, dated 2025-03 to 2026-07, applied to every month since December 2018". Also say that 2025-26
   months use the 2024 industry level.
2. Proper fix: see Bigger improvements item 2.

**Verify.** The page shows the extrapolated share. A new prospectus no longer changes any month before its own as-of
date once snapshots are kept.

### R1-8 · LOW · Five of seven auto lenders report on a 250-900 auto-industry scale; the page treats only Exeter as a scale problem

The autos headline says the lender gap "survives the obvious objections, score scale and vintage: leaving out Exeter,
whose score is VantageScore ... 38 times". `design/methods.md` section 1 adds that every other lender reports "a bureau
score that is FICO where it says which". But only the industry-option FICO Auto scores reach 900:

- Toyota ("FICO Score 8 Auto") has 12.7% of loans above 850, Honda 11.6%, CarMax 7.3%, Capital One 2.5% and
  Santander 0.6%.
- AmeriCredit tops out at 854 and Exeter at 845.

So with Exeter left out, comparisons still cross scales: AmeriCredit (max 854) against Honda or Toyota, and Santander,
whose filings leave its scale unstated (`design/autos-build.md:154`). `design/methods.md` section 6 already says the
scales differ; the headline does not.

```
python -m uv run python -c "import pandas as pd, glob; d = pd.concat(pd.read_parquet(f, columns=['lender','score']) for f in glob.glob('data/autos/*.parquet')); print(d.groupby('lender').score.agg(['max', lambda s: round((s > 850).mean(), 3)]))"
```

**Fix.** Add a same-family robustness line (lenders whose scores reach 900 only), or soften "survives ... score scale"
to "survives Exeter's VantageScore". **Verify.** The headline sentence matches section 6 of methods.md.

### R1-9 · LOW · Zero-event cells are still in the hazard table, as odds ratios near 1e-10 with p-values near 1e-200

The 11-09 pass fixed the 2017Q2 cohort baseline, which had made every quarter about 1e10. The same artefact remains
for cells with no events:

- score buckets 360 and 900;
- cohorts 2017Q2 and 2017Q4.

That is 13 rows of `data/results/autos/b2_hazard_ratios.csv`, with p down to 1.3e-208. The autos page prints the
score rows as "0.00", which reads as zero risk rather than "no events".

```
python -m uv run python -c "import pandas as pd; h = pd.read_csv('data/results/autos/b2_hazard_ratios.csv'); print(h[(h.odds_ratio < 1e-3) | (h.odds_ratio > 1e3)][['spec','event','factor','level','odds_ratio','p']])"
-> 13 rows: cohort_q 2017Q2, 2017Q4; score_b 360, 900
```

**Fix.** Merge sparse edge levels (scores <380 into 380, >=880 into 880; cohorts with fewer than 500 loans into one
"early" level) before fitting, or print "no events" for them. **Verify.** The command above returns no rows.

### R1-10 · LOW · "0 of 14 at every bandwidth" hides that 4 of 14 clear zero at one bandwidth

The page (`report/autos_page.py:273`) says no cutoff-horizon keeps a robust interval clear of zero "at every
bandwidth". That is true, but it is the weakest possible criterion for a null. Four of 14 do clear zero at one
multiplier: Honda 605 at 12 and 24 months and Honda 700 at 24 months at 2x, and Santander 725 at 12 months at 0.5x.
That is 4 of 56 off-optimal fits, near what chance gives. The null still stands, but the page should say this rather
than lean on "every".

```
python -m uv run python -c "import pandas as pd; b = pd.read_csv('data/results/autos/b3_rd_bandwidths.csv'); b['c'] = (b.ci_lo > 0) | (b.ci_hi < 0); print(b.groupby('bw_mult').c.sum().to_dict())"
-> {0.5: 1, 0.75: 0, 1.0: 0, 1.5: 0, 2.0: 3}
```

**Fix.** Print "at the optimal bandwidth 0 of 14; across 56 other fits, 4 clear zero, about what chance gives".
**Verify.** The sentence on the page carries both numbers.

### R1-11 · LOW · Page text contradicts the numbers next to it in five places

1. Cards section 2 is headed "The three loss-by-tier shapes" over a table of four (`report/cards_page.py:171`).
2. Cards section 4 always prints "no single ordering is reported as a finding" (`:203-205`). The headline above it
   says "the ordering of the extremes is a finding".
3. The new scope sentence promises the residual can say "by how many points, and since when" (`:18`). The same page
   then says "The size of the gap is not identified" (5 of 6 trusts change sign with the shape), and nothing on the
   page addresses "since when".
4. Autos: "Adding price removes about 37% of the remaining score gradient". The share is computed against the score
   specification (`report/autos_page.py:235`; `_score_gradient` gives 9.40x to 4.12x, so 36.9%). Against the 7.04x
   that remains after structure, price removes 27.5%.
5. `design/methods.md:79-80` says adding APR "collapses the bureau score's own gradient almost to nothing". The page's
   own number is 4.2x.

**Fix.** Edit each string (or compute the share against `terms`). **Verify.** Each sentence agrees with the table
beside it.

### R1-12 · LOW · The three generated pages have no doctype, no viewport and no links, so phones get a zoomed-out desktop page

`docs/autos.html`, `docs/cards.html` and `docs/conclusions.html` start with `<title>`. They have no `<!doctype html>`
(quirks mode), no `<meta name="viewport">` and no `<meta charset>`. GitHub Pages sends UTF-8 and the files are pure
ASCII, so encoding is safe. On a phone, though, each page lays out at about 980 px and scales down. HANDOFF says phone
width was never checked, and the user reads from a phone.

None of the three pages links anywhere: not back to the index, not to the repo or `design/methods.md`, both of which
they name as plain text. Code: the `h = [f"<title>..."]` lines in `report/cards_page.py:155`,
`report/conclusions_page.py:66` and `report/autos_page.py:393`.

**Fix.** Add one shared page shell in `report/svg.py` (doctype, charset, viewport, a nav line) used by all three
builders. **Verify.** A test asserts every `docs/*.html` starts with `<!doctype html>` and contains a viewport meta.

### R1-13 · LOW · The entry/roll split drops charge-offs that never show a 30-day delinquency (75% of Capital One's)

`estimate/decompose.py:36-41` codes a charge-off without a recorded 30+ month as a competing exit in the entry stage,
so it appears in neither factor. That is 75.3% of Capital One's charge-offs (133 of 223 are at 0 days: bankruptcy-type
events, already noted in `design/scout-autos.md`) and 6.5% of AmeriCredit's.

Capital One's pooled row in `data/results/autos/b6_attribution.csv` (entry share 0.977) is therefore meaningless. It is
not on the page, because the by-score table needs 100 ever-30 loans per cell. The page's "Their product is the
charge-off rate" holds only approximately.

```
-> charge-offs with no 30+ month: americredit 0.065, capone 0.753, carmax 0.015, exeter 0.018, honda 0.029, santander 0.002, toyota 0.038
```

**Fix.** Add a third path, "charge-off without delinquency", or report its share per lender. Drop Capital One from the
pooled table. Change "is" to "approximates". **Verify.** `b6_attribution.csv` either carries a no-30 share column or
has no Capital One row, and the section 5 sentence says "approximates".

### R1-14 · LOW · The weekly schedule sits on GitHub's 7-day cache eviction limit

The workflow comment says weekly runs keep the cache alive (`cards-refresh.yml:7-10, 15`). Each run restores the cache
saved at the end of the previous run, which is about 7 days minus the run's 6.5 minutes old. A scheduled start delayed
by more than that can find it evicted. The fallback still works: a full re-fetch of 569 filings, about 27 minutes and
about 2,800 EDGAR requests (run 42691131162).

**Fix.** `cron: "17 9 * * 1,4"` (Monday and Thursday), or a tiny Thursday job that only restores the cache.
**Verify.** In `gh api repos/SamuelJWebber/abs-risk/actions/caches`, `last_accessed_at` is never older than 4 days.

### R1-15 · LOW · Wrong or stale numbers and promises in HANDOFF, TASKS and PLAN

- `HANDOFF.md:30` says run 42699120327 "0 filings fetched and 573 skipped". The log's skipped counts are
  94+95+94+96+94+96 = 569.
- `TASKS.md:20` (A2) says "153 rows, 41 crosswalk rows". That is the seven-prospectus fixture build. The committed
  tables have 138 and 36.
- `PLAN.md:99` promises `absrisk cards refresh` and `absrisk autos refresh`; neither exists.
- `PLAN.md:101` says CFPB golden numbers are "re-verified each run". The workbook test is skipped on the runner,
  because the workbooks are not there.
- `PLAN.md:41` says the straddle rule is shown "with the sensitivity". No straddle sensitivity is on the page.

**Fix.** Correct the numbers and mark the PLAN items as not built (or build the straddle sensitivity). **Verify.**
`grep -n "573\|153 rows" HANDOFF.md TASKS.md` returns nothing stale.

### R1-16 · LOW · A personal email address is the author on 43 of 64 commits in this public repo

`git log --all --format=%ae | sort | uniq -c`: 43 commits carry a personal Gmail address, 16 the GitHub noreply
address, and 5 the bot. Current git config already uses the noreply address, so nothing new will add to it. GitHub
shows commit emails in every `.patch` view.

**Fix.** Optional, as part of R1-2's history decision: `git filter-repo --mailmap` to the noreply address, which also
needs a force push. **Verify.** The command above shows no personal address.

### R1-17 · LOW · The diagnostic workflow still sends the User-Agent the SEC refuses, outside `make_session()`

`.github/workflows/diag.yml` runs `scripts/scout/ua_diag.py`. That script sends
`absrisk/0.1.0 research (+https://github.com/...)`, the URL-in-parentheses form AGENTS.md says is refused
(`ua_diag.py:20-28`). It calls `requests.get` and `curl` directly, not `make_session()`. One more dispatch would repeat
the probe that risks an "Undeclared Automated Tool" block. It is dispatch-only and has done its job.

**Fix.** Delete `diag.yml`, or drop the refused variants and route through `make_session()`. **Verify.**
`grep -rn "(+https" scripts .github` returns nothing.

---

## Bigger improvements (ranked)

1. **One source of truth for bucket-to-tier.** The analysis reads `crosswalks/fico_buckets.csv` (or `tier_shares`),
   the dead crosswalk path in `estimate/cards.py` goes, and a test pins analysis mix = crosswalk mix. This removes the
   whole R1-1 class: two implementations of one rule drifting apart.
2. **Keep a composition history instead of one snapshot.**
   - Fetch every 424B per trust since 2019 once (a few dozen documents at 5 requests a second).
   - Key `cards_composition.csv` by prospectus accession, and step each trust's mix forward from each as-of date.
   - Back-fill only before the earliest one, and say how many months that is.
   - This removes most of the 92% look-ahead (R1-7), makes old residuals stable when a trust files a new prospectus,
     and is the only way the month + trust fixed-effects panel can ever be identified.
3. **An alert contract for the unattended refresh.** Fail the run on a new parse failure, on a trust whose latest
   month trails the newest by more than one, or on a composition snapshot older than 18 months. The existing "Run
   failed" email then carries the signal (R1-3).
4. **Honest inference with few clusters.** Use a wild cluster bootstrap over deals for every interval on the autos
   page, and keep the chart but stop drawing intervals that measure only within-deal noise (R1-6).
5. **A data-defined stress test for cards.** Split months by the pooled 30+ share rather than by named calendar
   periods, and report the conversion ratio in tight against loose months per trust. This is the version of the
   "direction" argument the data can carry (R1-4).
6. **One page shell for every generated page.** Doctype, charset, viewport, nav links, and the last data month in the
   header, with a test across `docs/*.html` (R1-12). Then check one page at 375 px.
7. **A leak test on tracked text.** Absolute paths, AppData, OneDrive and non-noreply emails fail `pytest`, because
   AGENTS.md asks for a manual read before committing agent output and that read has already missed once (R1-2).
8. **Golden checks for the autos track**, which PLAN section 4 promised: one loan count and one charge-off count per
   deal, traced to an EX-102 fixture and to the committed parquet.

---

## Checked and solid

**Tests.** 252 pass locally (`python -m uv run pytest -o addopts=""`, 169 s, one SingularMatrixWarning from the
saturated panel test). On the runner, `test_level_rebuild_from_workbooks_matches_committed` skips (the CFPB workbooks
are not there); it runs and passes locally.

**Failed runs explained.**
- 39438090561 (2026-10-20, scheduled): failed on `test_committed_csvs_match_fixtures` comparing Amex's new 2026-07-31
  prospectus with the 2025 fixture. Fixed by b231d71 and 08fa4bc; the test now passes.
- 42698996217: failed at setup because `astral-sh/setup-uv@v10` does not exist. Fixed by pinning v10.3.3.
- 42699120327 log confirms "Cache restored from key: cards-raw-42691131162", 0 fetched, "tables unchanged; pages left
  as they are", "no changes", "Cache saved with key: cards-raw-42699120327", and no Node 20 warning.

**Dedupe.** The committed `data/cards_monthly.csv` has 561 rows and no duplicate by (trust, period_end) or by (trust,
calendar month). All five former pairs kept the 10-D/A with `identical: true`. The COMET gap is exactly the three
documented 2019 failures.

**Golden checks.** For all six entries, the first occurrence of the label in the fixture text leads to the intended
printed number (Amex's first hit is the gross line; BofA's first of two hits is the current column), and the committed
row matches the value.

**Six headline numbers re-derived from raw inputs with code that does not import `absrisk`.**
- Card residuals: all 24 trust-shape means and ranks match to 0.001 pp (from `mix_by_trust.csv`, `loss_shape.csv`,
  `ccmr_level.csv`, `cards_monthly.csv`).
- CFPB level: all 11 CCIP annual means and year-end values in `ccmr_level.csv` read straight from Figure 53 of the
  2025 workbook.
- Card stage stress table: amex conversion ratio 1.126 / 1.342 / 1.463 / 1.477, matching `a3_stress.csv`.
- Autos Aalen-Johansen cells: Exeter 660 at 12 months 5.0644%, Honda 660 0.1021%, Santander 580 at 24 months 13.7399%,
  Toyota 700 1.2582%, AmeriCredit 620 5.8907%. All exact.
- Same-bucket gap: 49.6x (range 3.6 to 73.2) over 7 buckets; 37.7x without Exeter.
- Vintage test: 67 pairs (64 in 2024), median 1.00; the 7 big pairs are 33.7x within against 37.7x pooled. Loan
  totals 759,808 / 10 deals / 7 lenders.

**RD.** 0 of 14 robust intervals clear zero at the optimal bandwidth, as stated.

**Rebuild branch** (unverified on a runner per HANDOFF). On an exported copy of HEAD, `analyze cards`, `report cards`
and `report conclusions` rebuild `docs/cards.html` and `docs/conclusions.html` byte-identical. `a2_panel.csv` differs
only by 1e-15 float noise and the summary only by its timestamp. CSV writers emit CRLF on both platforms and the index
matches, so a Linux runner creates no line-ending churn.

**Live pages.** All four pages on samueljwebber.github.io/abs-risk return 200 and match `docs/` after line-ending
normalisation.

**EDGAR etiquette.** `make_session()` waits 0.2 s between requests (5 a second), retries 429/5xx with backoff, and
sends `abs-risk/<version> <contact>`. The full fetch in 42691131162 took 27 minutes for 569 filings, under 2 requests
a second. `scripts/scout/edgar_scout.py` uses `make_session()`. Tests never touch the network.

**Secrets and unsafe input.**
- No tokens, keys or private keys in any of the 64 commits.
- `yaml.safe_load` only; no pickle, eval or `shell=True` in `src/`.
- The upload artifact holds only filings and manifests, with no User-Agent or contact.
