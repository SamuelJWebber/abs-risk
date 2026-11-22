# abs-risk handoff

Rewritten **2026-11-21** (Claude Code: the independent review of 2026-11-10 implemented). Read `CLAUDE.md` first,
then this. **Rewrite this file at the end of every session, never append.** Under 150 lines.
Evidence words are exact: **fixture-proven** = a test on committed fixtures or synthetic data; **seen on the data** =
recomputed here from the committed tables; **seen live** = observed on a real Actions run or the live Pages;
**unverified** = none of these.

## State

Two tracks, both published at https://samueljwebber.github.io/abs-risk/ . **Public repo.**

The published claims changed on 2026-11-21. Before then the pages said: Citi's loss rate was gross (it is net); the
card comparison "rules out" the priority story and the answer was "selection, on every level comparison" (it does
not, and the filings cannot say); Santander's bought-back loans were harmless exits (they are defaults). All three
came from the independent review filed on 2026-11-10 (`REVIEW.md`, top table, and `reviews/fable-2026-11-10/`).
`REVIEW.md` now has a status row for every finding of that review.

Full suite: 393 passed locally (`.venv\Scripts\python.exe -m pytest -o addopts=""`, about 14 minutes on a busy
machine with BLAS capped at two threads).

## What changed on 2026-11-21, with evidence

1. **Citi is net (abs-B-1).** `cards/parse.py` writes Citi's Credit Loss Component to `net_co_rate`; `gross_co_rate`
   is empty with the reason. *Seen on the data*: the full 10-D set was re-parsed locally from the runner's artifact
   (`gh run download 44586415892`, into ignored `data/raw/cards/`); the parse reproduced the committed table byte
   for byte before the change and changed only Citi's 95 rows after it. *Fixture-proven*: `tests/test_citi_net.py`
   re-derives the 63-of-63 match against the committed prospectus.
2. **All six trusts on the net rate.** `cards_roll.RATE = "net_co_rate"` is the default of every card estimator.
   Ranks are on net (like for like across trusts). The CFPB level is gross, so sign statements are read on the gross
   rate for the five trusts that print it (`residual_gross`, `mean_residual_gross`) and on bounds for Citi (its net
   rate as a floor, 1.47 times net as the top). New tables `a1_basis.csv`. On net: Synchrony first in 10 of 12
   combinations of curve and straddle rule, Amex last in 10, Citi rank 2 or 3 under the uniform rule (it was 5).
3. **Conversion is not rescue (abs-A-2, abs-B-2).** `cards_roll.ceiling` -> `a3_ceiling.csv`: charge-off dollars over
   the last delinquency bucket a month earlier. Chase 1.21 (above one in 99% of 94 months), Synchrony 1.05, BofA
   1.03, COMET 0.99, Citi 0.88 on net, Amex 0.69 of a bucket holding two cohorts. Both card pages print it and
   withdraw the old reading; the conclusions page no longer announces an answer. `tests/test_conclusions_claims.py`
   lists the withdrawn sentences and fails if one reappears on any of the four pages.
4. **Santander buy-backs are defaults (abs-A-1).** `survival.as_defaults` (applied in `run_autos.load_loans`) labels a
   repurchase of a loan with `max_dpd >= 90` as a charge-off for every estimator; `exit_type_trust` keeps the trust's
   label. 1,321 loans reclassified, 1,295 of them Santander's. Every autos result was rebuilt (all stages). The
   charge-off-only versions sit beside them: `b1_gap_trust_loss.csv`, `b1_at_12_trust_loss.csv`,
   `b1_at_24_trust_loss.csv`. *Seen on the data*: the review's cells reproduce exactly (660 bucket 5.39% -> 7.25%).
5. **Fixed pairs lead the autos page (abs-A-3).** `lender_gap.fixed_pair_ratios` -> `b1_fixed_pairs.csv`:
   Mantel-Haenszel rate ratio over score bucket and month of age, scores 660-759, by year of loan age, on both
   definitions, with and without loan structure matched. Exeter and Santander over CarMax: 11.7 and 13.4 in year
   one, 6.8 and 5.3 in year two.
   On the buy-back definition Santander's cells rise 28% to 49% in the review's seven buckets, up to 105% in the thin 760 bucket.
6. **Wording fixed in passing:** abs-A-6 (roll "close to the baseline"), abs-B-4 ("settled", "bigger line"), abs-A-9
   (issuer-level opening sentences), and round 2's R2-3 and R2-4. R2-2 is disclosed on the page, not fixed.
7. `design/methods.md` and `design/cards-build.md` say the same things as the pages.

## Decisions taken without asking (reversible)

- **Net is the basis for every card comparison**, as the review recommended, rather than gross for five trusts with
  Citi set aside. Reverse with `absrisk analyze cards --rate gross_co_rate` (Citi then drops out of every table).
- **The default event is charge-off or late buy-back everywhere**, hazard model and decomposition included, not only
  in the headline. The result files keep the column name `chargeoff`.
- **`wip/paused-2026-11-10` (1e3af87, local only) was not merged and nothing was salvaged.** Its `claims.py` needs
  `a1_grid.csv`, which only that commit's unfinished calibration work produces, and its selection wording is keyed to
  the conversion ratio the review refuted. The branch is still on this disk, untouched. Delete it or keep it.
- **Citi's upper bound on gross is 1.47 times net** in every year, the highest year its one cached prospectus
  reports (2022). Outside 2022 to early 2025 that is an assumption; the floor (net itself) is not.
- CLAUDE.md still not edited (see "Needs the user").

## Next steps (no user needed)

1. **Watch the next `cards-refresh` run** (Mondays and Thursdays 09:17 UTC, usually hours late). It re-parses on the
   runner with the new parser and must commit nothing if the tables match. If it commits a Citi diff, compare it
   with the local parse before believing either.
2. **abs-A-4**: blank a cell whose first observed age is past a stated age (Capital One 11, Toyota 9, Honda 6).
3. **abs-A-5 and abs-B-3**: put the shelf-selection language (CarMax core portfolio, FICO 650 and above; Exeter
   excluding scores of 640 and above) and the co-borrower averaging on the autos page.
4. **R2-2 properly**: calibrate Synchrony by product (private label against general purpose), which is what the
   paused commit was building. Start from `shape/build_level.py`, not from that commit's data.
5. **Composition history** (round 1's R1-7 fix; about 87 424B filings since 2018): still the largest open item. The
   plan is in git history: `git show f45e9fe:HANDOFF.md`, "Next steps" 1.
6. abs-A-7 (no hazard from a risk set under a stated size); abs-B-5 and abs-B-6 (two LOW notes).

## Unverified or open

- **Not seen live:** the rebuilt pages on GitHub Pages at the time of writing this file; check the four URLs after
  the push deploys. The runner has not yet parsed with the new parser.
- The hazard model was refitted on the default definition; the review did not refit it, so there is no outside
  figure to compare the new lender odds ratios with.
- The check's failing path on a runner (fixture-proven only); three COMET 2019 filings still fail
  printed-vs-recomputed checks (documented, left failing).
- Honest lender intervals assume deal shocks alike across lenders and rest on 3 degrees of freedom.
- Santander's prospectus wording on buy-backs is not cached (sec.gov is unreachable from this machine); the page
  describes what the loan records show and does not say why Santander does it.

## Needs the user

1. **CLAUDE.md line 5** names a local path. Replace it with "the credit-dashboard repository next to this one", or
   tell a session to; then delete the KNOWN entry in `tests/test_no_leaks.py`.
2. History rewrite (R1-2 item 3, R1-16). **Decided 2026-11-22: no history rewrite** (the owner said "make the
   decision and do it"). 43 commits here carry a personal address, none since 2026-09-14; the repo has no forks. A
   rewrite would not remove the address from GitHub (old commits stay reachable by hash until GitHub Support purges
   them, and public push-event archives keep author addresses), and it would change every commit hash these review
   and handoff files cite and break every clone and the scheduled jobs' pushes. The leak is already stopped: every
   commit since uses the noreply address, held by the hook and tests. Reverse by running `git filter-repo --mailmap`
   and force-pushing; nothing done today prevents it. One account setting would also stop it at the source and is
   the owner's own: GitHub Settings, Emails, "Keep my email addresses private" and "Block command line pushes that
   expose my email".

## Rules that matter here

- **The SEC refuses any User-Agent containing a URL in parentheses.** Accepted form: `<name> <contact-email>`.
  `ABSRISK_CONTACT` is an Actions secret; the home IP is blocked by the SEC, so EDGAR fetches run only on Actions.
  To parse locally, download a run's `cards-raw-<run id>` artifact (kept 7 days) instead of fetching.
- Never hit EDGAR from tests. Save every filing before parsing. Parse by label, never by position.
- `absrisk cards parse` over the full set takes about 20 minutes locally. `absrisk analyze autos` took about
  35 minutes on 2026-11-21 with two BLAS threads on a shared machine; `analyze cards` about 20 seconds.
- After changing card or autos code, rerun the analysis and the reports: `tests/test_cards_results.py` and
  `tests/test_pages.py` fail when committed results or pages are stale. `docs/index.html` is hand-written.
- The venv has pytest; `uv run` works but re-syncs, so `.venv\Scripts\python.exe -m pytest -o addopts=""` is quicker.
- Result-file prefixes predate the task board: `b1_*` = TASKS B3, `b2_*` = B4, `b3_*` = B5, `b6_*` = entry/roll.
- **This repo is public.** `tests/test_no_leaks.py` is the floor, not the ceiling: read agent output before committing.
