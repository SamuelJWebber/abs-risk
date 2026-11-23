# abs-risk handoff

Rewritten **2026-11-22** (Round 2: Synchrony product-consistent calibration R2-2 and autos dollar-field fix abs-B-6).
Read `CLAUDE.md` first, then this. **Rewrite this file at the end of every session, never append.** Under 150 lines.
Evidence words are exact: **fixture-proven** = a test on committed fixtures or synthetic data; **seen on the data** =
recomputed here from the committed tables; **seen live** = observed on a real Actions run or the live Pages;
**unverified** = none of these.

## State

Two tracks, both published at https://samueljwebber.github.io/abs-risk/ . **Public repo.**

The independent review of 2026-11-10 (`REVIEW.md`, `reviews/fable-2026-11-10/`) had all four HIGH findings and three
others fixed on 2026-11-21 (Citi relabelled net and all six card trusts compared on net; card conversion withdrawn as
a rescue measure via `a3_ceiling.csv`; Santander 90+ late buy-backs counted as defaults; fixed lender pairs leading
`docs/autos.html`). On 2026-11-22, Round 2's **R2-2** (Synchrony product-consistent calibration) and **abs-B-6**
(autos dollar fields) were implemented and verified. `REVIEW.md` carries a status row for every finding.

Non-slow suite (`pytest -o addopts="" -m "not slow"`, including `repo_hygiene` and workbook rebuild): **404 passed, 0 failed, 1 deselected (`slow`)**.

## What changed on 2026-11-22, with evidence

1. **Product-consistent card calibration (R2-2).**
   - `shape/build_level.py` adds the CFPB private-label charge-off and tier-mix series (`pl_chargeoff_rate`,
     `pl_chargeoff_rate_ye`, `pl_share_*`) for both CCIP (2014-2024) and CCP (2013-2022) to `data/ccmr_level.csv`.
     *Fixture-proven*: `tests/test_shape.py` verifies schema, scout-note spot values, `calibration_check(..., product="pl")`
     within 1e-9, linear blending, and exact workbook rebuild against the local CFPB workbooks.
   - `cards/composition.py` extracts each trust's prospectus Program Partner table (`extract_program_tables`,
     `extract_private_label_share`, failing loudly on unrecognised labels) and writes `private_label_share` into
     `data/cards_composition.csv` (`0.242755` for Synchrony's 2026-08-31 prospectus, `0.243089` on the 2026-05-31
     fixture, `0.0` for the five general-purpose trusts). *Fixture-proven*: `tests/test_cards_composition.py`.
   - `shape/level.py` (`level_for`, `predict_chargeoff`) and `estimate/run_cards.py` (`mix_by_trust`, `predicted`,
     `product_sensitivity`) blend general-purpose and private-label CFPB levels by each trust's `private_label_share`
     and emit `a1_product.csv` (0% GP, prospectus blend, 100% PL). *Seen on the data*: Synchrony's gross residual
     moves from `+1.07%..+1.74%` (rank 1 everywhere) to `+0.41%..+1.16%` (still positive under all 4 curves; net
     residual `-0.54%..+0.21%`, rank 1 under ACMS and rank 4 under FICO behind BofA, Citi, Chase; 100% PL reverses
     gross sign to `-1.63%..-0.64%`, rank 6). Across 12 shape x straddle cells, `bofa` and `synchrony` tie for rank 1
     in 5 each and `amex` is last in 10 (`cards_page.ends` and `ends_clause` now report ties explicitly).
   - `cards.html`, `conclusions.html`, `design/methods.md`, `design/cards-build.md`, and `design/shape-sources.md`
     updated and rebuilt. *Fixture-proven* and *seen on the data*: `tests/test_synchrony_product.py`,
     `tests/test_cards_results.py`, `tests/test_pages.py`, `tests/test_conclusions_claims.py`.
2. **Autos dollar fields and count-based rate basis (abs-B-6).**
   - `autos/parse.py` negates Capital One's negative `recoveredAmount` (`recovery_sign = -1.0` for `CAPONE_LENDERS`,
     logged in file diagnostics); `autos/build.py` records the first non-null `chargedoffPrincipalAmount` at or after
     zero-balance exit without summing across retained months. *Fixture-proven*: `tests/test_autos_parse.py`,
     `tests/test_autos_build.py`.
   - `estimate/run_autos.load_loans` idempotently flips legacy all-negative Capital One recoveries on load so existing
     `copar-2025-1.parquet` (`-$695,460.96`) normalises to `+$695,460.96` without hand-editing the Actions-built
     parquet. *Seen on the data*: `tests/test_run_autos.py`.
   - `report/autos_page.py` (`docs/autos.html`) states once in its scope note that every rate on the page is a
     count-based share of loans rather than principal dollars or net of recoveries; `design/autos-build.md` and
     `design/methods.md` updated. *Fixture-proven*: `tests/test_pages.py`.

## Decisions taken without asking (reversible)

- **Prospectus product blend is the default card calibration** (`private_label_share` from the Program Partner table,
  dual cards counted as general purpose per CFPB). All three calibrations (0%, blend, 100% PL) stay in `a1_product.csv`
  and section 4 of `docs/cards.html`.
- **Net remains the basis for every card comparison** (`cards_roll.RATE = "net_co_rate"`), with sign statements read
  on gross (and Citi bounds 1.0x to 1.47x net).
- **The default event in autos remains charge-off or 90+ late buy-back everywhere** (`survival.as_defaults`).
- **`data/autos/copar-2025-1.parquet` was not hand-patched locally** (keeps 2026-09-08 runner provenance); `parse.py`
  fixes future `autos-build` runs and `run_autos.load_loans` normalises the committed file idempotently in memory.
- **`wip/paused-2026-11-10` (1e3af87, local only) was never merged and nothing was salvaged.**

## Next steps (no user needed)

1. **Watch the next `cards-refresh` run** (Mondays and Thursdays 09:17 UTC): verify the runner parses `private_label_share`
   cleanly from the cached prospectuses and commits no unexpected Citi or Synchrony diff.
2. **abs-A-4**: blank a cell whose first observed age is past a stated age (Capital One 11, Toyota 9, Honda 6).
3. **abs-A-5 and abs-B-3**: put the shelf-selection language (CarMax core portfolio, FICO 650+; Exeter excluding 640+)
   and co-borrower averaging on `docs/autos.html`.
4. **Composition history** (round 1's R1-7 fix; ~87 424B filings since 2018): still the largest open item
   (`git show f45e9fe:HANDOFF.md`, "Next steps" 1).
5. **abs-A-7** (risk-set floor) and **abs-B-5** (Exeter selection dated from 2025-2, not 2025-4).

## Unverified or open

- **Not seen live:** the rebuilt `cards.html`, `conclusions.html`, and `autos.html` on GitHub Pages until merged and
  deployed; `cards-refresh` has not yet run with the `private_label_share` composition parser.
- `copar-2025-1.parquet` itself still carries the 2026-09-08 negative `recovered_amount` bytes on disk until
  `autos-build` reruns (`run_autos.load_loans` already normalises it on load).
- The 2026-11-21 refitted autos hazard model has no outside comparison figure; honest lender intervals rest on 3 df.
- Three COMET 2019 10-D filings still fail printed-vs-recomputed checks (documented, left failing).
- Santander's prospectus wording on buy-backs is not cached locally.

## Needs the user

1. **CLAUDE.md line 5** names a local path. Replace it with "the credit-dashboard repository next to this one", or
   tell a session to; then delete the KNOWN entry in `tests/test_no_leaks.py`.
2. **History rewrite (R1-2 item 3, R1-16).** Decided 2026-11-22: no history rewrite (43 commits pre-2026-09-14 carry
   a personal address; all commits since use noreply, enforced by `tests/test_no_leaks.py`). Optional GitHub Settings ->
   Emails: enable "Keep my email addresses private" and "Block command line pushes that expose my email".

## Rules that matter here

- **SEC User-Agent must have no URL in parentheses** (`<name> <contact-email>`); `ABSRISK_CONTACT` is an Actions
  secret. Never hit EDGAR from tests. Save every filing before parsing. Parse by label, never by position.
- Cap BLAS threads (`OMP_NUM_THREADS=2`, `OPENBLAS_NUM_THREADS=2`, `MKL_NUM_THREADS=2`) on busy machines.
- After changing card or autos code, rerun analysis and reports: `tests/test_cards_results.py` and `tests/test_pages.py`
  fail when committed results or pages are stale. `docs/index.html` is hand-written.
- **This repo is public.** `tests/test_no_leaks.py` is the floor, not the ceiling: check diffs and commit emails before pushing.
