# Track B build: ABS-EE fetcher and `loans` table (tasks B1, B2)

Written 2026-09-08. Code: `src/absrisk/autos/` (`fetch.py`, `parse.py`, `build.py`, `deals.py`, `__init__.py`).
Contract: design/analysis-plan.md section 1 (tables) and section 5 (deal list). Evidence for every rule:
design/scout-autos.md, cited by section below. Tests: `tests/test_autos_{parse,build,fetch}.py` on fixtures cut
from the real scouting files; nothing here touches EDGAR from a test or from this machine (PLAN.md section 5).

Commands (the top-level CLI delegates `absrisk autos ...` to `absrisk.autos.main`):

    absrisk autos fetch --deal sdart-2026-1 --raw data/raw/autos        # or --all
    absrisk autos build --deal sdart-2026-1 --raw data/raw/autos --out data/autos [--loan-months --panel data/panel]
    absrisk autos run-local --deal sdart-2026-1                          # loans from the scout files on disk

`.github/workflows/autos-build.yml` runs fetch then build per deal (`--raw raw/autos --out out/autos`) and a
collect job copies `out/autos/*` into `data/autos/` and commits.

## 1. Deal list: data/deals.csv

Columns `deal, lender, cik, doc_prefix, name, depositor_cik, notes`. `cik` is the CIK whose submissions JSON lists
the deal's ABS-EE filings: the depositor for depositor-filed shelves (with `doc_prefix` picking the deal out of the
shelf), the trust for self-filers (scout-autos 11, "Design inputs for the fetcher"; the split is in 1a).

| deal | lender | listed under | prefix | note |
|---|---|---|---|---|
| sdart-2026-1 | santander | depositor 0001383094 | sdart261 | offering pool lp/sp share period 2026-01-31 (scout 2) |
| sdart-2025-1 | santander | depositor 0001383094 | sdart251 | early filings on the older page `CIK0001383094-submissions-001.json` |
| carmax-2026-2 | carmax | trust 0002117307 | - | pre-closing pools filed by CarMax Business Services 0001259380, not fetched |
| carmax-2025-1 | carmax | trust 0002049715 | - | |
| copar-2025-1 | capone | depositor 0001133438 | copart251 | PTI in percent (scout 6.1) |
| exeter-2025-5 | exeter | trust 0002092528 | - | filer agent 0000929638 in the accession prefix |
| exeter-2025-1 | exeter | blank: resolved by full-text search | - | scout 1a's entity list shows 0002049379 |
| amcar-2024-1 | americredit | trust 0002020251 | - | |
| toyota-2025-a | toyota | trust 0002047571 | - | the trust files its own ABS-EE (R2 submissions JSON) |
| honda-2025-1 | honda | depositor 0000890975 (cik blank) | harot251 | amendments ABS-EE/A per period (scout 6.11) |

How the Honda prefix was discovered, and how the fetcher does it when a depositor-filed deal has none: full-text
search (efts, `forms=ABS-EE`) for the exact trust name; among hits whose `ciks` include the depositor and whose
`display_names` include the trust, the primary document name (after the colon in `_id`) starts with the prefix,
up to `absee` (`harot251abseea_0828-1757.htm` -> `harot251`, from the R3 search saved at
`data/raw/scout/edgar3/.../_search/honda-auto-receivables.json`, hit 0001193125-26-374999). A blank `cik` is
resolved the same way from the search's entity aggregation, matching the trust name exactly and refusing to guess
(`fetch.resolve_deal`). Both paths are tested against canned search responses.

## 2. Fetcher rules (`fetch.py`)

1. Session: `absrisk.http.make_session()` unless one is injected (tests inject a fake). User-Agent and throttle
   are the session's (5 requests/second, SEC plain format; PLAN.md 5).
2. Listing: main submissions JSON plus every older page in `filings.files[].name` (scout 1b: the SDART depositor
   has three older pages; a 2025 deal's first filings are there). Older pages are flat column arrays, the main
   page nests them under `filings.recent`; both shapes are handled.
3. Candidates: forms `ABS-EE` and `ABS-EE/A`; for depositor-filed deals only rows whose `primaryDocument` starts
   with `doc_prefix` (case-insensitive). Every candidate is written to `raw/<deal>/listing.json`.
4. One filing per reporting period (`reportDate`), scout 6.10 and 6.11:
   - an amendment (`ABS-EE/A`) wins over the original; the latest amendment by filing date if several;
   - otherwise, when several filings share a period, the one with the largest EX-102 wins (size from each
     candidate's `index.json`; the submission size from the listing is the fallback);
   - a period with several non-amendment filings, or any filing whose primary document is named `...lp` /
     `...sp` / `...mp` / `largepool` / `smallpool`, is flagged `offering_pool`. The builder skips those by
     default so the panel starts at the first post-closing filing (scout 6.10); `--include-offering-pool` keeps it.
   - losers are recorded in the winner's `superseded` list, with a `reason` string.
5. Download: the EX-102 is identified by exhibit type `EX-102` from `<acc>-index-headers.html` (SGML
   `<TYPE>...<FILENAME>...`, HTML-escaped in the page); if that page is missing or names no EX-102, the largest
   `.xml` in `index.json` whose name does not contain `103` (scout 7: names share no pattern; CarMax `cart20262.xml`
   and Ford `autoloanmonthlydeal1183pool.xml` contain no "102"; EX-103 is under 25 KB). Streamed to
   `raw/<deal>/<accession>/<name>` via a `.part` file; a size mismatch against `index.json` deletes the file and
   records an error.
6. Idempotent: a file already present with the size `index.json` reports is not fetched again and its sha256 is
   reused from the previous manifest; index pages already on disk are not re-requested (filings are immutable).
   A truncated file is re-downloaded (tested).
7. Manifest `raw/<deal>/manifest.json`: `deal, accession, form, filing_date, period, primary_document,
   offering_pool, reason, superseded, file, size, sha256, url, ex102_by_type, skipped, error`, plus the resolution
   record (which CIK, which prefix, how) and counts. `period` falls back to `<PERIOD>` in the index-headers page
   if the listing had none.

## 3. Parser rules (`parse.py`)

Streaming lxml `iterparse`, one `<assets>` record at a time, cleared after use; the root is checked to be
`assetData` and records to be flat (nested elements fail loudly). Two small pre-passes read at most one record
(`file_period`) and the first 5,000 (`detect_pti_scale`).

| rule | scout-autos | implementation |
|---|---|---|
| score null when 0, empty or non-numeric | 6.3, 11 table | `score_value`: float() fails or <= 0 -> None; `score_missing` in `loans` |
| score_type verbatim | 3, 6.2 | carried as the string in the file ("Bureau", "FICO", "FICO Score 8 Auto", "Credit Bureau Score"/"None", "Consumer Credit Bureau", "Consumer Bureau"/"Commercial Bureau") |
| PTI to a fraction | 6.1, 11 "Detection rules" | divide by 100 when lender is `capone` **or** the median over the first 5,000 numeric PTIs exceeds 1.0; `info["pti_rule"]` records `issuer`, `median`, `issuer+median` or `None`; if more than 1% of values still exceed 1 after dividing, the build fails |
| dates | 6.5 | `MM/YYYY` (origination, zero-balance effective) -> first of month; `MM-DD-YYYY` (reporting period) -> date |
| repeated elements | 6.7 | first value wins; `info["dup_counts"]` counts records with a repeat per element (SDART's oldest loans carry `subvented` 1 then 98; Ford 53%) |
| Ford commercial obligors | 6.9, 4a | `commercial = "commercial" in obligorCreditScoreType.lower()` ("Commercial Bureau"); those records have no PTI and a 1-670 score scale |
| APR | 6.4 | `originalInterestRatePercentage` carried as the fraction it is; `info["n_apr_gt_1"]` would flag a percent-scale file (0 everywhere so far). 0% APR is common on rate-subvented loans (`subvented = 1`) |
| absent elements | 6.6 | null, never 0 (`currentDelinquencyStatus` is omitted for closed loans at AmeriCredit, CarMax code 1, Toyota code 4) |

Yielded record = the analysis-plan 1b columns (`deal, asset_id, period, balance_begin, balance_end, dpd, zb_code,
scheduled_payment, actual_payment, interest_paid, principal_paid, chargeoff_amount, recovered_amount, repossessed,
servicing_flag`) plus the origination attributes the 1a table needs (`orig_month, orig_amount, orig_apr,
orig_term, pti, score, score_type, vehicle_value, new_used, state, income_verified, employment_verified,
subvented, commercial, zb_date`). Element mapping: balance_begin `reportingPeriodBeginningLoanBalanceAmount`,
balance_end `reportingPeriodActualEndBalanceAmount`, dpd `currentDelinquencyStatus`, scheduled_payment
`reportingPeriodScheduledPaymentAmount`, actual_payment `totalActualAmountPaid`, interest_paid
`actualInterestCollectedAmount`, principal_paid `actualPrincipalCollectedAmount`, chargeoff_amount
`chargedoffPrincipalAmount`, recovered_amount `recoveredAmount`, repossessed `repossessedIndicator`, state
`obligorGeographicLocation` (current address, scout 5a and 6.12), new_used `vehicleNewUsedCode`.

`servicing_flag` is not defined in the plan; here it is `modified` (reportingPeriodModificationIndicator true or a
modificationTypeCode present), `extended` (paymentExtendedNumber > 0), `modified+extended`, or null. Rename or
replace when the time-varying models need something else.

## 4. Builder rules (`build.py`)

One pass per monthly file in period order (files are sorted by their first record's period; two files with one
period is an error); one slotted state object per loan for the deal's life.

- **Exit** (analysis-plan 1a; scout 5b "Consequences", 11 "Retention rule"): earlier of (a) the first period
  carrying a non-empty `zeroBalanceCode` and (b) the last period present before the loan's first absence. Ties go
  to the code (Santander reports code 1 in the payoff month and drops the loan next month, so (a) and (b) coincide
  there). `exit_type`: 4 chargeoff, 1 prepay, 3 repurchase, 2/5/99 and any other code `other`, absent (dropped
  with no code, exit_code null), censored (present in the last file with no code). No per-issuer branch is
  needed: CarMax, Capital One and Exeter keep every loan (exits from codes), Santander, AmeriCredit and Toyota keep
  charge-offs and drop payoffs after their month, Ford drops everything after one month; in every case the code
  is seen at least once, in its month (scout 5b).
- **Absent without a code** is counted and reported per deal (`n_absent_without_code`,
  `share_absent_without_code`); analysis-plan 1a treats it as censored in the main run and prepay-like in
  sensitivity. SDART 2026-1, June+July 2026: 3 of 80,613.
- `months_observed` counts files present; `first_period` / `last_period` the first and last; `bal_first` /
  `bal_last` the end balance then; `max_dpd` and `first_30/60/90_period` over the life (null when delinquency
  was never reported); `chargeoff_amount` at the exit period; `recovered_amount` summed over the life;
  `ltv = orig_amount / vehicle_value`, null when the value is missing or <= 0; static fields from the first
  observation (scores never change, scout 5a).
- **Gaps** (present, absent, present again) are counted; the first absence still fixes the exit (rule (b)).
- **Recovery-only stubs**: Ford files records holding only `assetNumber`, the period and `recoveredAmount` for
  loans that already left the file (the "30 near-empty records", scout 3; "drop", scout 11). They are not
  presence (no months, no last_period, no new loan), but the recovery is credited to a known loan; counted as
  `n_recovery_stub_records`.
- **Offering pools** are excluded from the file list unless asked for (section 2 rule 4).
- Output: `data/autos/<deal>.parquet` (zstd, explicit Arrow schema, dates as `date32`) and
  `<deal>.diagnostics.json` (N, periods, exit counts, absent share, gaps, late additions, duplicate ids, score
  missing, commercial, per-file PTI rule and median, duplicate-element counts, sha256 of every input, retention
  rule text, exit rule text, seconds). With `--loan-months`, one parquet per period under
  `data/panel/<deal>/<period>.parquet` with exactly the 1b columns.

### Deviations from analysis-plan 1a, with reasons

1. One extra column, `zb_date` (date, nullable): the `zeroBalanceEffectiveDate` month at exit. For keep-all
   issuers a loan that closed before the panel's first file carries its code in every file, so `exit_period` under
   rule (a) is the first file seen, not the event month; `zb_date` is the event month. On a panel built from the
   deal's first post-closing filing the two agree; on the two-month local builds they differ for 220 SDART, 1,847
   CarMax and 10,920 Capital One loans. Everything else is column-for-column the 1a list, in its order.
2. `cik` in `loans` is the CIK the filings were listed under (the depositor for depositor-filed shelves), as
   `data/deals.csv` gives it; the trust's own CIK is in the notes column when known.

## 5. Per-lender normalisations in effect

| lender | score | missing score | PTI rule fired | retention seen | other |
|---|---|---|---|---|---|
| santander | "Bureau", 369-900, scale unstated (scout 6.2; 424B5 located, section 10 item 1) | 0 -> null (16.9%) | none (median 0.07) | keeps 4, drops 1 and 3 next month | `subvented` repeated in 1.3% (oldest loans: 1 then 98); delinquency keeps counting after charge-off |
| carmax | "Bureau" = FICO at application, auto scale 650-900, co-obligor average (scout 8) | none | none (median 0.05) | keeps all | delinquency absent for paid-off loans; 100% used |
| capone | "FICO", 700-889 | none | **issuer+median** (median 4.7-5.0) | keeps all | charge-offs often at 0 days |
| exeter | "Consumer Credit Bureau" = VantageScore 98.9% (scout 8) | 0 -> null | none (median 0.09) | keeps all | delinquency reset to 0 at zero balance; some code-4 loans report 0.00 charge-off |
| americredit | "Credit Bureau Score" / "None" | non-numeric under "None" -> null | none | keeps 4, drops 1 next month | `subvented` repeated 9-17%; delinquency absent for some loans |
| toyota | "FICO Score 8 Auto", 620-900 | none | none | keeps 4, drops 1 next month | `subvented` repeated 6%; delinquency absent for code 4 |
| ford | "Consumer Bureau" 424-900 / "Commercial Bureau" 1-670 | empty -> null | none (consumer median 0.08) | drops all after one month | `commercial` flag (21.6%); `subvented` repeated 53%; recovery-only stubs |
| honda | not measured | - | median rule will decide | not measured (scout 10 item 8) | ABS-EE/A preferred |

## 6. What the runner needs

- Secrets/env: `ABSRISK_CONTACT` (email, required: EDGAR refuses a User-Agent without it), optional `ABSRISK_NAME`.
  Nothing else; no tokens.
- Network: `data.sec.gov` (submissions), `efts.sec.gov` (only for deals with a blank CIK or prefix),
  `www.sec.gov/Archives` (index pages and the XML). Throttle is the session's 0.2 s minimum interval (5/s) with
  4 retries on 429/5xx; a deal fetch makes 3 small requests per filing plus one large download, so the throttle
  never binds; bandwidth does.
- Disk: raw files are 95-352 MB per deal-month (scout 9). A 20-month deal is 2-7 GB under `raw/autos/<deal>/`;
  the runner has ~14 GB free by default, so keep one deal per job (the workflow does) and do not cache `raw/`
  between runs unless the cache is per deal.
- Memory: parse is streaming; the builder holds one small object per loan (100k loans is well under 1 GB).

## 7. Expected runtime per deal

Measured locally: parsing two SDART files (581 MB, 159,068 records) took 13.0 s; CarMax two files (336 MB)
8.5 s; Capital One two files (559 MB) 13.1 s, i.e. about 40-45 MB/s or 12k records/s including the PTI pre-pass
and sha256. Download dominates: at 3-5 MB/s (scout 9) a 300 MB file is 1-2 minutes. Per deal on the runner:

| deal | filings so far | raw size | fetch | build |
|---|---|---|---|---|
| sdart-2026-1 | 7 (Feb-Aug 2026) + pool | ~2.1 GB | 8-12 min | 1 min |
| sdart-2025-1 | 18 (Mar 2025-Aug 2026) + pool | ~5.5 GB | 20-30 min | 2-3 min |
| copar-2025-1 | ~17 | ~5 GB | 20-30 min | 2-3 min |
| carmax-2026-2, carmax-2025-1 | 4 / ~17 | 0.7 / 2.9 GB | 3 / 10-15 min | under 2 min |
| exeter-2025-5, exeter-2025-1 | ~10 / ~19 | 1.9 / 3.7 GB | 7 / 15-20 min | 1-2 min |
| amcar-2024-1 | ~30 (since 2024) | ~5.5 GB | 20-30 min | 2-3 min |
| toyota-2025-a | 19 | ~4 GB | 15-25 min | 2 min |
| honda-2025-1 | ~17 | unknown (not profiled) | 15-25 min | 2 min |

The workflow's 330-minute job limit and `max-parallel: 4` leave room; the whole matrix is one to two hours.

## 8. Known gaps

- Nothing here has run against EDGAR yet: the fetcher is tested only on canned responses built from the real
  submissions JSONs, one real index-headers page and the SGML template. First runner pass should be one small deal
  (carmax-2026-2) and a check of `listing.json`, `manifest.json` and one sha256 against `index.json`.
- Older submissions pages were never downloaded; their shape (flat column arrays) is from the EDGAR API
  documentation and the fixture is hand-crafted. If a page nests them differently, `filings_from_page` is the
  one place to fix.
- The offering-pool name rule is what three shelves showed (lp/sp/mp, largepool/smallpool). A shelf that names
  its pool filing differently and files it in a period of its own would come through as a normal first period;
  the builder's `n_added_after_first_file` and a large first-month `absent` count would show it.
- `recovered_amount` is summed over the life as the plan says; if an issuer reports it cumulatively rather than
  per month for retained charge-offs, the sum overstates. Check on a keep-all issuer with a long panel (Exeter).
- Exeter 2025-1, Honda 2025-1 and Toyota/AmeriCredit/Ford id persistence are untested (scout 10 items 2-5);
  `n_gaps`, `n_added_after_first_file` and `share_absent_without_code` in the diagnostics are the checks.
- `servicing_flag` is an interpretation (section 3).
- `data/panel/` is not yet in `.gitignore` (only `data/raw/` is); add it before running `--loan-months` on a
  committed checkout. The three `data/autos/*.parquet` written by `run-local` (3-4.5 MB each) are two-month
  partial builds and will be overwritten by the Actions run; commit or drop them as the coordinator prefers.
- AmeriCredit's July 2026 charge-off spike (scout 5b) and its `"None"` score records are not in the 300-record
  fixture (the cut holds none); the `None`/non-numeric rule is unit-tested on values only.
