# abs-risk handoff

Rewritten **2026-11-28** (autos review fixes abs-A-4/A-5/A-7/B-3/B-5 + Synchrony product calibration R2-2 + abs-B-6).
Read `CLAUDE.md` first, then this. **Rewrite this file at the end of every session, never append.** Under 150 lines.
Evidence words are exact: **fixture-proven** = a test on committed fixtures or synthetic data; **seen on the data** =
recomputed here from the committed tables; **seen live** = observed on a real Actions run or the live Pages;
**unverified** = none of these.

## State

Two tracks, both published at https://samueljwebber.github.io/abs-risk/ . **Public repo.**

Every HIGH, MEDIUM, and LOW finding of the 2026-11-10 independent review (`REVIEW.md`, `reviews/fable-2026-11-10/`)
plus Round 2's **R2-2** is now fixed (`abs-A-3` fixed in part; `abs-A-8` closed by events).

## What changed on 2026-11-22, with evidence

1. **Product-consistent card calibration (R2-2).**
   - `shape/build_level.py` adds CFPB private-label charge-off and tier-mix series (`pl_chargeoff_rate`,
     `pl_chargeoff_rate_ye`, `pl_share_*`) for CCIP (2014-2024) and CCP (2013-2022) to `data/ccmr_level.csv`.
   - `cards/composition.py` parses Synchrony's prospectus Program Partner table into `private_label_share` (`0.242755`
     for Synchrony, `0.0` elsewhere) in `data/cards_composition.csv` and `mix_by_trust.csv`.
   - `shape/level.py` and `estimate/run_cards.py` blend GP and PL levels by `private_label_share`, emitting
     `a1_product.csv` (0% GP, 24.3% blend, 100% PL). *Seen on the data*: Synchrony's gross residual moves from
     `+1.07%..+1.74%` to `+0.41%..+1.16%` (reverses at 100% PL: `-1.63%..-0.64%`); across 12 shape x straddle cells,
     `bofa` and `synchrony` tie for rank 1 in 5 each while `amex` is last in 10 (`cards_page.ends` reports ties).
   - *Fixture-proven* and *seen on the data*: `tests/test_shape.py`, `tests/test_cards_composition.py`,
     `tests/test_synchrony_product.py`, `tests/test_cards_results.py`, `tests/test_pages.py`.
2. **Risk-set floor and late-first-age blanking on autos (abs-A-7, abs-A-4).**
   - `survival._curves` and `lender_gap.group_life_tables` enforce `survival.MIN_RISK_SET = 50`; `lender_gap.blank_late_entry_cells`
     and `usable_cells(at, cif=cif)` blank cells first reaching 50 at risk past `survival.MAX_FIRST_AGE = 6`
     (Capital One 11, Toyota 9, Honda 7) on `docs/autos.html`. *Seen on the data* and *fixture-proven*:
     all `b1_*` tables rebuilt; `tests/test_autos_review_fixes.py`.
3. **Shelf selection, score scale, co-borrower averaging, Exeter date, and dollar fields (abs-A-5, abs-B-3, abs-B-5, abs-B-6).**
   - `autos_page.py`, `conclusions_page.py`, `design/methods.md`, `data/deals.csv`, and `design/scout-autos.md` disclose
     CarMax core FICO >= 650 vs Select, CarMax co-borrower `.5` score averaging/truncation, Exeter EART exclusion since
     `2025-2` and 582 VantageScore vs 562 FICO gap, and count-based rate basis (`SCOPE`).
   - `autos/parse.py`, `autos/build.py`, and `run_autos.load_loans` negate Capital One's negative `recoveredAmount`
     (`copar-2025-1.parquet`: -$695,460.96 -> +$695,460.96 on load) and take first non-null `chargedoffPrincipalAmount`
     at/after zero-balance exit. *Fixture-proven* and *seen on the data*: `tests/test_autos_parse.py`,
     `tests/test_autos_build.py`, `tests/test_run_autos.py`, `tests/test_autos_review_fixes.py`.

## Offline replay of the published loss decomposition

The November 28 replay pins the 567 parsed trust-months and ten auto-loan tables (759,808 loans). All card result tables reproduced. The current 50-loan risk-set floor changes 24 of 67 score-by-lender implied loss rates versus the older committed auto estimates. Regenerated both by-score B6 tables and the two affected pages. CarMax's median roll ratio is 0.94, Honda's is 0.61 and Toyota's is 0.70. The hash manifest, source-coverage limits and commands are in [the replay](checks/replays/2026-11-28/README.md).

## Decisions taken without asking (reversible)

- **Prospectus product blend is the default card calibration** (`a1_product.csv` keeps 0%, blend, and 100% PL).
- **Net remains the basis for card comparisons** (`cards_roll.RATE = "net_co_rate"`); sign statements use gross.
- **Autos default event remains charge-off or 90+ late buy-back everywhere** (`survival.as_defaults`).
- **`data/autos/copar-2025-1.parquet` was not hand-patched locally**; `run_autos.load_loans` normalises it in memory.
- **`wip/paused-2026-11-10` (1e3af87, local only) was never merged and nothing was salvaged.**

## Next steps (no user needed)

1. **Watch the next `cards-refresh` run** (Mondays and Thursdays 09:17 UTC): verify the runner parses `private_label_share`
   and net Citi rates cleanly and commits no unexpected diff.
2. **Composition history** (round 1's R1-7 fix; ~87 424B filings since 2018): plan in `git show f45e9fe:HANDOFF.md`.
3. **Partner auto shelves**: add CarMax Select (CMXS) and Exeter Select (ESART) deals to measure the shelf filter directly.

## Unverified or open

- **Not seen live:** the rebuilt `cards.html`, `autos.html`, and `conclusions.html` on GitHub Pages until deployed.
- `copar-2025-1.parquet` carries legacy negative `recovered_amount` bytes on disk until `autos-build` reruns.
- Three COMET 2019 10-D filings still fail printed-vs-recomputed checks (documented, left failing).
- Honest lender intervals rest on 3 degrees of freedom; Santander prospectus buy-back wording is not cached locally.

## Needs the user

1. **CLAUDE.md line 5** names a local path. Replace it with "the credit-dashboard repository next to this one", then
   delete the KNOWN entry in `tests/test_no_leaks.py`.
2. **History rewrite (R1-2 item 3, R1-16):** decided 2026-11-22, no history rewrite (noreply enforced on every commit
   since 2026-09-14 by hook and `tests/test_no_leaks.py`).

## Rules that matter here

- **SEC User-Agent must have no URL in parentheses** (`<name> <contact-email>`). Never hit EDGAR from tests.
- Cap BLAS threads (`OMP_NUM_THREADS=2`, `OPENBLAS_NUM_THREADS=2`, `MKL_NUM_THREADS=2`) on busy machines.
- After changing card or autos code, rerun analysis and reports: `tests/test_cards_results.py` and `tests/test_pages.py`
  fail when committed results or pages are stale. `docs/index.html` is hand-written.
- **This repo is public.** `tests/test_no_leaks.py` is the floor, not the ceiling: check diffs and commit emails before pushing.
