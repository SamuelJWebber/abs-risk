# abs-risk handoff

Rewritten **2026-11-09** (Claude Code, second pass of the day). Read `CLAUDE.md` first, then this.
**Rewrite this file at the end of every session — never append.** Under 150 lines.
Evidence words are exact: **fixture-proven** = a test on committed fixtures; **seen live** = observed on real
EDGAR-derived data or a real Actions run; **unverified** = neither.

## State

Two tracks. **Cards is concluded on public data; autos B3-B5 are done** (B3, B4 descriptive; B5, the only
causal design, a robust null). 252 tests green locally (`python -m uv run pytest`). Pages:
https://samueljwebber.github.io/abs-risk/ (Pages built successfully for every push today; see the end of this
file for what was checked on the live pages). **Public repo.** TASKS.md: every task done.

## Done today, with evidence

1. **Duplicate trust-months, deduped on ingest** (`dedupe_rows`, `src/absrisk/cards/parse.py`). One row per
   (trust, period_end); 10-D/A beats 10-D, then later `filing_date` from `manifest.json`, then higher accession;
   the loser is listed under `superseded` in the winner's `row_labels_json`; two plain 10-Ds with different
   numbers are logged as `DuplicateMonth`. *Fixture-proven*: `tests/test_cards_dedupe.py` (a copy of the July
   2026 BA fixture under a second accession) failed on the old code, passes now. *Seen live*: refresh run
   42691131162 wrote 561 rows, zero duplicates; all five former pairs kept the 10-D/A, each original
   `identical: true`; no conflicts. A guard test on the committed CSV fails on the pre-fix table.
2. **Refresh workflow** (`.github/workflows/cards-refresh.yml`). Had failed since 2026-10-20 (a test pinned the
   composition table to the fixture prospectus; Amex then COMET filed newer ones). Test fixed (*seen live*:
   passed on the runner). Now weekly (Mondays 09:17 UTC) so its ~10 MiB cache survives GitHub's 7-day eviction;
   re-runs the dedupe, golden and composition tests on the new tables before committing; rebuilds card results
   and both card pages when a table changed. Actions bumped to checkout v7, cache v6, upload-artifact v7,
   setup-uv v10.3.3 (no `v10` tag exists; run 42698996217 failed at setup on that). *Seen live*, run
   42699120327: cache restored from `cards-raw-42691131162`, 0 filings fetched and 573 skipped, the post-parse
   checks passed, "tables unchanged; pages left as they are", nothing committed, no Node 20 warning.
3. **Golden checks** (`checks/golden.yaml`, `tests/test_golden.py`): one gross charge-off rate per trust, label
   and printed number found in the committed July 2026 filing, and the committed CSV row checked to come from
   that accession with that value. *Fixture-proven*; corrupting one value and one printed string fails 3 checks.
4. **Card results rebuilt on the deduplicated table** (`absrisk analyze cards`, `report cards`, `report
   conclusions`; not the free-riding tests, which are separate scripts under `design/freeride/` and untouched).
   First reproduced the September results exactly from the September inputs (*seen live*). With today's table:
   trust rankings unchanged under all four shapes; stage decomposition moves in the second decimal (Amex
   conversion ratio 1.38 either way). **Panel regression (cards page section 6) identified nothing and had been
   printed as estimates**: one prospectus snapshot per trust makes month-FE saturated (6 mixes, 5 tiers +
   intercept: it reproduces trust means) and month+trust-FE unidentified (it printed coefficients ~1e9).
   `panel_regression` now returns a status and note per spec and blanks the unidentified one; the page explains.
   *Fixture-proven* on synthetic panels (`tests/test_cards_panel.py`). A4 marked done (scope sentence added).
5. **Autos B3-B5** from the committed `data/autos/*.parquet` (no EDGAR). Before any change, the September results
   were re-run with current code: every table identical except the origination-quarter dummies (*seen live*).
   - B3 vintage: same two lenders, same bucket, inside one origination year vs pooled: ratio a median **1.00** of
     pooled over 67 pairs (64 in 2024, 3 in 2025); the 7 pairs >10x apart pooled are 34x within 2024 vs 38x.
     Without Exeter (VantageScore for 98.9% of its pool) the same-bucket gap is 38x vs 50x. Both on the page.
   - B4 chart 2: forest plot of the terms spec. Top vs bottom quintile: amount 0.72 [0.65, 0.80], PTI 2.47
     [2.08, 2.94], LTV 4.33 [3.48, 5.38]; lenders vs Santander: Exeter 1.13, AmeriCredit 0.99, captives
     0.16-0.24. (The September handoff quoted the *price* column as the result; corrected in TASKS.md.)
     Cohort baseline was 2017Q2 (5 loans, no charge-offs: every quarter OR ~1e10); now 2024Q4. Other
     coefficients unchanged to 3e-6 in log odds.
   - B5 null: 16 candidates, 8 fail density, 7 usable (APR or amount first stage, `rd.usable`). Robust
     intervals: 0 of 14 cutoff-horizon estimates clear zero at the optimal bandwidth, 0 of 14 at every one of
     0.5-2x. Closest: Honda 700 at 24 months, +2.0 to +2.6 points, robust p 0.07. Multiplier-1 rows reproduce
     `b3_rd.csv` exactly.
   - All of these are *seen live* on the committed loan data; the new functions are also *fixture-proven* on
     synthetic data (`tests/test_autos_b3_b5.py`).
6. Smaller: `test_cli_parse` no longer overwrites `data/cards_parse_failures.csv`; autos page states which
   sections are descriptive vs causal; stale "months since first seen" text fixed (code counts from origination);
   README, PLAN, TASKS and the landing page no longer say "scouting" or carry counts the refresh makes stale.

## Decisions taken without asking (reversible)

- **Autos data not extended past 2026-07.** `autos-build` has no incremental mode: extending means
  re-downloading every EX-102 of all ten deals (tens of GB from EDGAR, multi-hour runner jobs) for three more
  months of follow-up. The brief said not to re-download, and the B3-B5 results do not need it.
- **Card pages rebuilt** although cards is "closed": the rebuild only propagates the dedupe and corrects section
  6; no free-riding test was run.
- **Weekly refresh** rather than a monthly run plus a cache keep-alive job: one workflow, smaller fetches.
- `autos-build.yml`, `scout.yml`, `diag.yml` keep their v4 actions (still run, with a Node 20 deprecation
  warning). Not bumped because none can be verified without a heavy EDGAR run.

## Unverified or open

- The weekly schedule has not fired yet (first: Monday 2026-11-16). The dispatched run above is the evidence.
- The page-rebuild branch of the refresh (tables changed) has not run on a runner yet; locally the same three
  commands produced the committed pages.
- Three COMET filings (2019-05, -06, -07) still fail printed-vs-recomputed checks: filer rounding errors,
  documented in design/cards-build.md, deliberately left failing (COMET has 91 of 94 months).
- Exeter's VantageScore is treated as on the FICO scale in the hazard model's shared score buckets; the
  same-bucket headline is reported with and without Exeter, the hazard model is not.

## Nothing needs the user

No step here waits on the user. Answering the closed cards question would need borrower-level tradeline data
(NY Fed CCP, a bureau extract, the CFPB panel); that is an access decision, not a task.

## Rules that matter here

- **The SEC refuses any User-Agent containing a URL in parentheses.** Accepted form: `<name> <contact-email>`.
  `ABSRISK_CONTACT` is an Actions secret; the home IP is blocked by the SEC, so EDGAR fetches run only on Actions.
- Never hit EDGAR from tests. Save every filing before parsing. Parse by label, never by position.
- Result-file prefixes predate the task board: `b1_*` = TASKS B3, `b2_*` = B4, `b3_*` = B5, `b6_*` = entry/roll.
- `absrisk analyze autos` is ~15 min (RD ~7, hazard ~5, incidence ~2); skip stages with
  `--skip b1,b1c,b2,b3,b3bw,b6`. `absrisk analyze cards` is ~6 s. Cap BLAS threads when the machine is shared.
- pytest's `addopts = "-q"` hides the summary line under `-q`; use `-o addopts=""` to see the count.
- **This repo is public.** Read anything an agent generated in bulk before committing it.

## Live pages check (2026-11-09, after Pages build 42700684862 for b95f5a7)

*Seen live*: autos, cards, conclusions and index pages fetched from samueljwebber.github.io/abs-risk return 200
and are identical to `docs/` apart from line endings (CRLF in the Windows checkout). Not checked in a browser at
phone width; charts were checked for size in an emulated 1100 px viewport only (all ten autos charts render).
