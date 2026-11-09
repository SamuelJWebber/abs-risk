# abs-risk handoff

Rewritten **2026-11-09** (Claude Code). Read `CLAUDE.md` first for the rules, then this for what is true now.
**Rewrite this file at the end of every session — never append.** Under 150 lines.

## State

Two tracks. **Cards is concluded on public data. Autos B3-B5 are now done**: B3 and B4 descriptive, B5 (the
only causal design) a documented null. 237 tests green locally (`python -m uv run pytest`), on the refreshed data. Published at
https://samueljwebber.github.io/abs-risk/ . **Public repo.**

## What changed this session

1. **Duplicate trust-months fixed on ingest.** `parse_raw` now calls `dedupe_rows` (`src/absrisk/cards/parse.py`):
   one row per (trust, period_end); the superseding filing wins (10-D/A over 10-D, then later `filing_date` from
   `manifest.json`, then higher accession); the loser is listed under `superseded` in the winner's
   `row_labels_json`; two plain 10-Ds with *different* numbers go to the failure log as `DuplicateMonth`.
   Test `tests/test_cards_dedupe.py` copies the real July 2026 BA fixture under a second accession: it failed
   on the old code (two rows) and passes now. Fixture-proven. The live result: see "Cards refresh" below.
2. **The monthly cards-refresh had been failing since 2026-10-20** (run 39438090561). The test comparing the
   committed composition table to the fixtures failed once Amex filed a newer prospectus (July 2026), so the
   workflow died at its Tests step every month. The test now does a row-for-row check only where the committed
   prospectus is the fixture's, and structural checks for a newer one. Also: `test_cli_parse` was overwriting
   `data/cards_parse_failures.csv` with an empty file on every test run; it writes to tmp now.
3. **Autos B3-B5** (all from the committed `data/autos/*.parquet`, no EDGAR):
   - Before changing anything, the September results were re-run from the committed loans tables with current
     code: summary, incidence (all six b1 tables), RD and decomposition tables **identical**; hazard identical
     except the origination-quarter dummies (see B4).
   - **B3 vintage.** Same two lenders, same 20-point bucket, inside one origination year vs pooled: the
     within-year ratio is a median **1.00** of the pooled one over 67 pairs (64 in 2024, 3 in 2025). The 7 pairs
     >10x apart pooled are 34x apart within 2024 vs 38x pooled. So the lender gap is not a vintage gap.
     Only Exeter vs AmeriCredit at 620 halves (1.9 vs 3.8; AmeriCredit's pool is the 2023 vintage).
   - **Score scale.** Exeter reports VantageScore for 98.9% of its pool. Without Exeter, the same-bucket gap is
     a median 38x (7 buckets) against 50x with it. Both checks are computed into the page headline.
   - **B4 chart 2** = forest plot of the *terms* spec. Top vs bottom quintile: amount 0.72 [0.65, 0.80],
     PTI 2.47 [2.08, 2.94], LTV 4.33 [3.48, 5.38]. Lenders vs Santander: Exeter 1.13, AmeriCredit 0.99, captives
     0.16-0.24. The previous handoff said "amount n.s., PTI 1.3-1.8, LTV 1.7-2.6, lender excess vanishes with
     terms": those were the **price** column (APR is a mediator, not the main spec). Corrected in TASKS.md.
     The cohort baseline was 2017Q2 (5 loans, zero charge-offs), giving ~1e10 odds ratios for every quarter; it
     is now the most populous quarter, 2024Q4. All other coefficients unchanged to 3e-6 in log odds.
   - **B5 null.** 16 candidate cutoffs, 8 fail density, 7 usable (first stage in APR *or* amount, `rd.usable`).
     Refitted at 0.5/0.75/1/1.5/2x the MSE-optimal bandwidth: **0 of 14** cutoff-horizon estimates keep a robust
     interval clear of zero at every bandwidth. Closest: Honda 700 at 24 months, +2.0 to +2.6 points at every
     bandwidth, robust p 0.07 at the optimal one. Multiplier-1 rows reproduce `b3_rd.csv` exactly.
   - Page (`docs/autos.html`) states which sections are descriptive and which could be causal; the stale
     "months counted from first seen" sentence is gone (code counts from origination since 2026-09-08).

## Descriptive vs causal, as the page now says

- Sections 2, 3, 5 (who defaults where, the hazard ladder, entry/roll split): **descriptive**. Controls narrow
  the comparison; they do not make it causal.
- Section 4 (RD at lender cutoffs): the only design that could carry a causal sentence. **It finds nothing**
  robust. That is the result, stated in advance as the likely one (design/methods.md section 3).

## Cards refresh

Dispatched once today after the fixes (run 42691131162, success, bot commit 127ffdb). **Seen live:** 561 rows,
zero duplicate trust-months; every trust 94 distinct months Dec-2018 to Sep-2026 except COMET at 91 (the three
known failures). All five former duplicates collapsed to the 10-D/A, each original recorded as `identical: true`;
no `DuplicateMonth` conflicts. `tests/test_cards_dedupe.py` now also checks the committed CSV (fails on the
pre-refresh table, passes on this one). The run re-downloaded every 10-D (no cache survives a month, see Next 3);
the scheduled run on the 20th would have done the same.

The refreshed composition table carries a newer COMET prospectus (0001193125-26-413919) that reprints the same
2026-06-10 pool date; the composition test briefly failed on that and now accepts an as-of date not earlier
than the fixture's. Without that fix the Nov 20 scheduled refresh would have failed at its Tests step again.

## Cards: closed, do not re-run

The cross-lender free-riding hypothesis is **closed on public data** (design/two-tests.html). Answering it needs
borrower-level tradeline data where one household holds both cards (NY Fed CCP, a bureau extract, the CFPB
panel). That is an access problem, not a code problem. **Do not re-run those tests.**

## Next

1. **Cards results downstream of the dedupe** (`absrisk analyze cards`, `report cards`, `report conclusions`)
   were built in September from the table with five duplicate months. Per the instruction not to re-run the
   cards track, they were left as they are. The duplicates did not move the headline ratios, but the panel
   regression double-weights those five months. One cheap local run fixes it if the user wants the pages
   rebuilt on the deduped table; it is not the free-riding test.
2. **Autos data stops at 2026-07-31.** Newer ABS-EE months exist on EDGAR. Extending needs the
   `autos-build` workflow (runner downloads tens of GB of EX-102 XML; the home IP is blocked by the SEC). Not
   done: the instruction was not to re-download, and the results above do not need it.
3. **The Actions raw-filings cache never survives a month** (GitHub evicts after 7 days; the refresh runs
   monthly), so every cards-refresh re-downloads all ~570 10-Ds (~15 min at 5 req/s). Options: a weekly no-op
   run that touches the cache, or keying the cache so the 20th run restores it. Not changed.
4. A4 (cards residual page) is still marked "doing" in TASKS.md though docs/cards.html exists; whoever closes
   the cards track should check its pass condition and mark it.
5. Three COMET filings (2019-05, -06, -07) still fail their printed-vs-recomputed checks; documented in
   design/cards-build.md as filer rounding errors, deliberately left failing.

## Rules that matter here

- **The SEC refuses any User-Agent containing a URL in parentheses.** Accepted form: `<name> <contact-email>`.
  Set `ABSRISK_CONTACT` in the environment; there is no `.env` loader. EDGAR fetches run only on Actions.
- Never hit EDGAR from tests. Save every filing before parsing. Parse by label, never by position.
- Result-file prefixes predate the task board: `b1_*` = TASKS B3, `b2_*` = B4, `b3_*` = B5, `b6_*` = entry/roll.
- `absrisk analyze autos` full run is ~15 min single-machine (RD ~7, hazard ~5, incidence ~2); stages can be
  skipped with `--skip b1,b1c,b2,b3,b3bw,b6`. Cap BLAS threads when something else is running.
- **This repo is public.** Read anything an agent generated in bulk before committing it.
