# abs-risk handoff

Rewritten **2026-11-22** (autos review fixes: abs-A-4, abs-A-5, abs-A-7, abs-B-3, abs-B-5). Read `CLAUDE.md` first,
then this. **Rewrite this file at the end of every session, never append.** Under 150 lines.
Evidence words are exact: **fixture-proven** = a test on committed fixtures or synthetic data; **seen on the data** =
recomputed here from the committed tables; **seen live** = observed on a real Actions run or the live Pages;
**unverified** = none of these.

## State

Two tracks, both published at https://samueljwebber.github.io/abs-risk/ . **Public repo.**

Every HIGH and MEDIUM finding of the 2026-11-10 independent review (`REVIEW.md`, `reviews/fable-2026-11-10/`) is now
fixed (abs-A-3 fixed in part), along with four of the five LOW findings.

## What changed on 2026-11-22, with evidence

1. **Risk-set floor on cumulative-incidence hazards (abs-A-7).** `survival._curves` and `lender_gap.group_life_tables`
   now enforce `survival.MIN_RISK_SET` = 50: any month of loan age with fewer than 50 loans at risk contributes zero
   hazard rather than `d / n`. *Seen on the data*: every `b1_*` table under `data/results/autos/` was rebuilt from the
   committed `data/autos/*.parquet` tables; in `b1_cif.csv`, thin early risk sets (such as 1 default among 29 loans at
   age 5 in AmeriCredit's 480 bucket, which previously contributed 3.45 points to its 12-month rate, and 1 among 25 at
   age 24 in Exeter's 480 bucket) no longer jump the Aalen-Johansen or Kaplan-Meier curves. *Fixture-proven*:
   `tests/test_autos_review_fixes.py::test_min_risk_set_suppresses_hazard_from_thin_early_risk_set` and
   `test_committed_cif_respects_min_risk_set_and_autos_page_blanks_late_lenders`.
2. **Late-first-age cells blanked on the autos page (abs-A-4).** `lender_gap.first_age_table`,
   `lender_gap.blank_late_entry_cells` and `lender_gap.usable_cells(at, cif=cif)` identify each cell's first observed
   age with at least `MIN_RISK_SET` = 50 loans at risk and blank any cell whose first observed age exceeds
   `survival.MAX_FIRST_AGE` = 6 months. *Seen on the data*: after the 3-month pool offset, median first observed age is
   11 months at Capital One, 9 at Toyota and 7 at Honda (whose age-6 risk sets hold at most 32 loans), against 3 at
   Exeter, 4 at CarMax and Santander, and 5 at AmeriCredit. Their cumulative rates are blanked in the section 2 cell
   table on `docs/autos.html` (which now prints `first_age_12` beside `n_loans_12`) and excluded from the 24-month
   by-score chart rather than printed as full 12- or 24-month rates. *Fixture-proven*:
   `tests/test_autos_review_fixes.py::test_blank_late_entry_cells_blanks_lenders_first_observed_past_cutoff`.
3. **Shelf selection, score scale and co-borrower averaging disclosed (abs-A-5, abs-B-3, abs-B-5).** `report/autos_page.py`,
   `report/conclusions_page.py` and `design/methods.md` now state the prospectus shelf-selection rules at both ends of
   the headline pair (CarMax's public CAOT pools selected from its core portfolio with FICO 650 or above while non-core
   / lower-credit obligors go to CarMax Select; Exeter's EART pools since 2025-2 excluding obligors with credit bureau
   score 640 or above and proprietary score 240 or above, which go to Exeter Select), Exeter's 20-point
   VantageScore-over-FICO gap in its prospectus (weighted average 582 vs 562; 14% vs 32% below 540), and CarMax's
   co-borrower FICO averaging on joint loans (truncated to an integer by `autos/parse.py`). `data/deals.csv` and
   `design/scout-autos.md` also date Exeter's score selection from 2025-2 (abs-B-5). *Fixture-proven*:
   `tests/test_autos_review_fixes.py::test_carmax_fixture_proves_co_borrower_half_point_scores_are_averaged_and_truncated`
   verifies on the committed `tests/fixtures/autos/carmax-2026-2/2026-06.xml` fixture that `.5` scores occur exclusively
   on `coObligorIndicator=true` records and are truncated by `score_value`.

## What changed on 2026-11-21, with evidence

1. **Citi is net (abs-B-1), all six card trusts compared on net.** `cards/parse.py` stores Citi's Credit Loss Component
   in `net_co_rate` and leaves `gross_co_rate` empty; `cards_roll.RATE = "net_co_rate"`. Sign statements against the
   gross CFPB level use `a1_basis.csv` (`tests/test_citi_net.py`).
2. **Conversion is not rescue (abs-A-2, abs-B-2).** `cards_roll.ceiling` -> `a3_ceiling.csv` (Chase 1.21, Synchrony 1.05,
   BofA 1.03, COMET 0.99, Citi 0.88 on net, Amex 0.69 of a two-cohort bucket). Both card pages withdraw the old
   reading; `tests/test_conclusions_claims.py` holds the withdrawn sentences off all four pages.
3. **Santander buy-backs are defaults (abs-A-1) and fixed pairs lead the autos page (abs-A-3).** `survival.as_defaults`
   reclassifies 1,321 repurchases of loans with `max_dpd >= 90` (1,295 Santander). `lender_gap.fixed_pair_ratios` ->
   `b1_fixed_pairs.csv` leads `docs/autos.html` (`tests/test_autos_defaults.py`, `tests/test_autos_gap.py`).

## Next steps (no user needed)

1. **Watch the next `cards-refresh` run** (Mondays and Thursdays 09:17 UTC). It re-parses on the runner with the net
   Citi parser and must commit nothing if the tables match.
2. **R2-2 properly**: calibrate Synchrony by product (24.3% private label against general purpose), starting from
   `shape/build_level.py`.
3. **Composition history** (round 1's R1-7 fix; about 87 424B filings since 2018): plan in `git show f45e9fe:HANDOFF.md`.
4. **Partner auto shelves**: add CarMax Select (CMXS) and Exeter Select (ESART) deals to measure the shelf filter
   directly, and print the 11-event / 10-point-bucket sensitivity variants from abs-A-3 and the net-recovery note from
   abs-B-6.

## Unverified or open

- **Not seen live:** the 2026-11-22 rebuilt pages (`docs/autos.html`, `docs/conclusions.html`) until this branch merges
  and deploys to GitHub Pages.
- The hazard model (`b2_*`), RD (`b3_*`) and decomposition (`b6_*`) tables were not refitted on 2026-11-22 because none
  of them uses `survival._curves` with `MIN_RISK_SET` (`b2` fits loan-month binomial logits; `b6` requires at least
  1,200 loans or 60 ever-30 loans per cell).
- Three COMET 2019 filings still fail printed-vs-recomputed checks (documented, left failing).
- Honest lender intervals assume deal shocks alike across lenders and rest on 3 degrees of freedom.

## Needs the user

1. **CLAUDE.md line 5** names a local path. Replace it with "the credit-dashboard repository next to this one", or
   tell a session to; then delete the KNOWN entry in `tests/test_no_leaks.py`.
2. History rewrite (R1-2 item 3, R1-16): **decided 2026-11-22, no history rewrite** (43 old commits before 2026-09-14;
   noreply enforced on every commit since by hook and `tests/test_no_leaks.py`).

## Rules that matter here

- **The SEC refuses any User-Agent containing a URL in parentheses.** Accepted form: `<name> <contact-email>`.
  Never hit EDGAR from tests. Save every filing before parsing. Parse by label, never by position.
- After changing card or autos code, rerun the analysis and the reports: `tests/test_cards_results.py` and
  `tests/test_pages.py` fail when committed results or pages are stale. `docs/index.html` is hand-written.
- `.venv\Scripts\python.exe -m pytest -o addopts=""` runs the suite without re-syncing.
- **This repo is public.** `tests/test_no_leaks.py` is the floor, not the ceiling: read agent output before committing.
