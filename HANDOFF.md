# abs-risk handoff

Rewritten **2026-11-10** (Claude Code, review round 1 implemented). Read `CLAUDE.md` first, then this.
**Rewrite this file at the end of every session — never append.** Under 150 lines.
Evidence words are exact: **fixture-proven** = a test on committed fixtures or synthetic data; **seen live** =
observed on real EDGAR-derived data, a real Actions run or the live Pages; **unverified** = neither.

## State

Two tracks, both published at https://samueljwebber.github.io/abs-risk/ . Cards is concluded on public data; autos
B3-B5 are done. REVIEW.md (round 1: 2 HIGH, 5 MEDIUM, 10 LOW) now carries a status line under every finding:
15 fixed, R1-7 fixed as the short-term disclosure, R1-16 and part of R1-2 deferred to the user (below). Full suite:
333 passed locally (`python -m uv run pytest -o addopts=""`, about 3 minutes). **Public repo.**

## What changed in round 1, with evidence

1. **R1-1 card mix** (fbbeac8). The analysis reads `crosswalks/fico_buckets.csv`; unscored balances are dropped and
   renormalised, not spread over 300-850; one implementation of the straddle rule (`shape.tiers.overlap_fraction`);
   dead crosswalk code removed. BofA fico_fed2007 residual +1.07% -> +1.13%. *Fixture-proven* (tests/test_cards_mix.py,
   5 of 6 failed on the old code) and *seen live* (rebuilt results match the review's independent numbers exactly).
2. **R1-2 leaks** (8d98a73). 21 of 22 files scrubbed of local paths, plus the home IP/ISP and the second GitHub account
   name. tests/test_no_leaks.py fails on any profile path, AppData, user-path slug, OneDrive path, home path or
   non-noreply email in tracked text (fixtures exempt from the email rule), and on any post-6a18549 commit with a
   personal author address. *Fixture-proven* (fails on the old tree; planted-leak test). CLAUDE.md line 5 is the one
   allowed exception; see "Needs the user".
3. **R1-3 / R1-14 refresh alerts** (9847d92). `absrisk cards check` fails on a parse failure the committed log lacks or
   a trust >1 month behind; warns when a mix snapshot is >18 months old (Citi's is 18 now; it will warn from the
   October data on, by design not a failure). The workflow keeps the committed log, runs the check with
   continue-on-error, commits, then fails the run. Schedule now Mondays and Thursdays 09:17 UTC. A `rebuild` dispatch
   input forces the results-and-pages branch. *Fixture-proven* (broken BA copy). *Seen live*: runs 42724889951,
   42726294384, 42727357720 (forced rebuilds, 0 filings fetched, "check passed"). The failing path is not seen live.
4. **R1-4 / R1-5 card stages** (4f261d1). Trust averages are geometric means, so entry x progression x conversion =
   co_monthly exactly and shares sum to one (Amex conversion ratio 1.39, entry share 125%). The direction test splits
   months by a delinquency index (`cards_roll.regimes`, a3_regimes.csv) and finds the one named step that raised every
   trust's 30+ share. Result: **mixed** (tight minus loose: Amex -0.10, Citi +0.09; across normalising->squeeze: BofA
   -0.12, COMET -0.06). Both pages say so; the conclusions heading is now computed ("selection, on every level
   comparison"); the landing page no longer claims the cycle test agrees. *Fixture-proven* (7 of 8 new tests failed).
5. **R1-6 autos inference** (89a27e4). Lender intervals add the deal-to-deal spread from the three two-deal lenders
   (3 df, t critical values; `hazard.deal_spread_intervals`, b2_lender_intervals.csv); clustered intervals use t(9).
   In the review's simulation clustered intervals covered 41-47% for single-deal lenders, the new ones 89-97%
   (*fixture-proven*). Building it exposed a confounder now controlled in every hazard spec: **months in pool** (loans
   enter a trust current, so months 0-2 in the pool have charge-off odds 0.13x). Terms spec against Santander: Honda
   0.15 [0.04, 0.61], Toyota 0.19, CarMax 0.23 distinguishable; Capital One 0.36, AmeriCredit 0.75, Exeter 1.10 not.
   Structure: amount 0.72, PTI 2.47, LTV 4.24. *Seen live* on the committed loan data (b2 rerun, 16 min, 2 threads).
6. **R1-7** (fc25eca, short-term). The cards page states the look-ahead (92% of trust-months predicted from a later
   snapshot; a new prospectus rewrites history; 22% of months on the 2024 CFPB level). The real fix is next step 1.
7. **R1-8..R1-13** (89a27e4, fc25eca). One-scale check (five lenders past 850: median 38x, same as without Exeter);
   sparse edge levels merged and no-event levels blanked (no odds ratio outside 1e-3..1e3); RD sentence gives 0 of 14
   at the optimal bandwidth and 4 of 56 off-optimal refits; text contradictions fixed (four shapes, since-when table,
   price share 27% against the terms gradient); entry/roll tables carry `co_without_30_share` (Capital One 75%).
8. **R1-12 page shell** (fc25eca). `report.svg.page`: doctype, charset, viewport, nav, "Data through <month>" instead
   of a build date. *Seen live* at 375 px on all three generated pages: standards mode, scrollWidth = 375, nothing
   overflowing outside table scrollers, 10 autos charts inside the viewport.
9. **R1-15 / R1-17** (a9d7df3, 20f1435). PLAN marks the refresh commands as not built and the CFPB re-check as
   local-only; TASKS counts fixed; diag.yml and ua_diag.py (refused User-Agent) deleted.
10. **Bigger improvements** done: 1, 3, 4, 5, 6, 7, 8 (autos golden checks, 2767a8b: one loan per deal traced from its
    EX-102 record to the parquet plus two charge-offs; corrupting two values fails four checks). Also a straddle-rule
    sensitivity (a1_straddle.csv: residuals move up to 1.47 points under the bounds; only Synchrony keeps its rank
    everywhere) and the hazard terms spec without Exeter (b2x, b2_terms_without_exeter.csv; Capital One moves most).
11. **Runner determinism** (4112b2d, 8dd2962). The first forced rebuild on a runner committed last-digit changes
    (log/exp differ between Windows and Linux libm; the unidentified panel fit printed platform-dependent garbage).
    Geometric-mean tables are now rounded to 10 decimals, a2_panel.csv to 6 significant digits, and the unidentified
    fit prints no numbers. *Seen live*: the third forced rebuild (run 42727357720) rebuilt every card result and both
    card pages on Linux and committed nothing ("no changes").

## Decisions taken without asking (reversible)

- **CLAUDE.md not edited.** It still names a local path (line 5). It is the assistants' instruction file; an edit
  on a workflow's instruction is not authorised. tests/test_no_leaks.py allows exactly that line.
- **Months in pool added to the hazard model** although the review did not ask: without it the deal-spread estimate
  measured young-deal artefacts (0.48 in log odds in the terms spec; 0.33 with it).
- **Geometric means** for the card stage averages (the review allowed either); numbers moved in the third digit.
- **Snapshot age is a warning, not a failure**, in the alert check (Citi files no prospectus when it issues no notes).
- **Straddle bounds** are lowest-tier / highest-tier, the widest rule that keeps balances inside bucket edges.
- `autos-build.yml` and `scout.yml` keep their v4 actions (cannot be verified without a heavy EDGAR run).

## Next steps (no user needed)

1. **Composition history (REVIEW bigger improvement 2, the R1-7 fix).** About 87 424B filings since mid-2018 across
   the six trusts (Amex ~25, COMET ~17, BofA ~15, Synchrony ~14, Chase ~8, Citi ~8, counted from the cached scout
   submissions). Plan: `fetch.list_prospectuses` (every 424B since 2018) on the runner; key cards_composition.csv by
   prospectus accession; drop the one-accession-per-trust assertion in test_committed_csvs_match_fixtures; teach the
   composition parser the older layouts with one fixture per variant; `predicted()` already steps the mix forward
   with merge_asof, so back-fill then covers only months before the first snapshot. Then rerun the panel: month+trust
   FE may become identified. Expect parser work like the 10-D historical layouts (311 -> 554 rows took a session).
2. **Aalen-Johansen curves and the eligibility effect.** The hazard model now holds months in pool fixed; the b1
   cumulative-incidence curves (delayed entry by age) do not, so seasoned entrants' first months understate hazard.
   The fresh-entrant cut on the page is the partial answer; a pool-time-adjusted version is not built.
3. Watch the first scheduled runs (Thursday 2026-11-12, Monday 2026-11-16): October 10-Ds arrive around the 15th, so
   the Monday run should commit new rows and exercise the rebuild branch with changed tables.

## Unverified or open

- The check's failing path on a runner (fixture-proven only); the twice-weekly cache keep-alive (verify with
  `gh api repos/SamuelJWebber/abs-risk/actions/caches`: last_accessed_at never older than four days).
- Three COMET 2019 filings still fail printed-vs-recomputed checks (filer rounding; documented, left failing).
- Honest lender intervals assume deal shocks alike across lenders and rest on 3 degrees of freedom.

## Needs the user

1. **CLAUDE.md line 5**: replace `(C:\...\credit-dashboard)` with a relative mention such as "(the credit-dashboard
   repository next to this one)", or tell a session to. Then delete the KNOWN entry in tests/test_no_leaks.py.
2. **History rewrite decision (R1-2 item 3, R1-16)**: the old paths and a personal email remain in 43+ commits of the
   public history. Removing them needs `git filter-repo --replace-text ... --mailmap ...` and a force push to main,
   which breaks every clone (including the other assistant's) and leaves GitHub's cached views until GitHub Support
   purges them. Say yes or no; a session can do the rewrite once told to.

## Rules that matter here

- **The SEC refuses any User-Agent containing a URL in parentheses.** Accepted form: `<name> <contact-email>`.
  `ABSRISK_CONTACT` is an Actions secret; the home IP is blocked by the SEC, so EDGAR fetches run only on Actions.
- Never hit EDGAR from tests. Save every filing before parsing. Parse by label, never by position.
- Result-file prefixes predate the task board: `b1_*` = TASKS B3, `b2_*` = B4, `b3_*` = B5, `b6_*` = entry/roll.
- `absrisk analyze autos` is ~30 min now (b2 ~16 with months in pool, RD ~7, hazard without Exeter ~4); skip stages
  with `--skip b1,b1c,b2,b2x,b3,b3bw,b6`. `absrisk analyze cards` ~20 s. Cap BLAS threads when the machine is shared.
- After changing card or autos code, rerun the analysis and the reports: tests/test_cards_results.py and
  tests/test_pages.py fail when committed results or pages are stale.
- pytest's `addopts = "-q"` hides the summary line under `-q`; use `-o addopts=""` to see the count.
- **This repo is public.** tests/test_no_leaks.py is the floor, not the ceiling: still read agent output before committing.
