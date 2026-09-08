# Task board

One bounded task per session. Each has a pass condition written before work starts.
Status: `todo` | `doing` | `done YYYY-MM-DD` | `blocked (why)`.

## 0. Access and scouting

| # | Task | Pass condition | Status |
|---|------|----------------|--------|
| 0.1 | EDGAR access from a runner | `scout.yml` probe returns 200 from data.sec.gov with ABSRISK_CONTACT set | done 2026-09-08 (plain `abs-risk contact` User-Agent; any URL in the UA is refused; home ISP blocked regardless, PLAN §5; runs 34190694825 diag, 34190842910 full) |
| 0.2 | Card trust scouting | design/scout-cards.md has, per live trust, the charge-off row labels and the FICO and credit-limit tables copied from a downloaded prospectus | done 2026-09-08 (all seven trusts from raw 10-D exhibits and prospectus annexes; Discover defeased; Synchrony is VantageScore; Chase FICO is a 5% sample; Amex buckets do not map) |
| 0.3 | Auto ABS-EE scouting | design/scout-autos.md has, for three issuers across the spectrum, the field list, score distribution, delinquency and charge-off shares from a downloaded EX-102, and an asset-number persistence check across two months | doing (nine loan files from seven issuers profiled; same-deal pairs show full persistence at CarMax and Capital One and survivor persistence at Santander; write-up in progress) |
| 0.4 | CFPB tier data | design/scout-ccmr-tiers.md has the tier definitions and every by-tier series the CCMR publishes, with workbook citations | done 2026-09-08 (finding: no loss by tier exists; utilization, lines, balances, late-fee incidence by tier do; workbooks for 2021, 2023, 2025 saved) |

## A. Cards, pool level

| # | Task | Pass condition | Status |
|---|------|----------------|--------|
| A1 | 10-D fetcher and parser for the six live trusts | one command pulls every 10-D since 2019 for Amex, COMET, Chase, Citi, Synchrony, BA into data/raw/cards/; parser emits monthly gross and net charge-off, payment rate, yield, 30+ and 90+ delinquency per trust into data/cards_monthly.csv; fixture test per trust; one golden number per trust traced to a filing | todo |
| A2 | Prospectus composition tables | FICO and credit-limit distributions for each live trust, with as-of date, bucket edges and basis (balances or accounts), in data/cards_composition.csv; crosswalks/fico_buckets.csv maps every bucket to the six CFPB tiers with the straddle rule written down | todo |
| A3 | Shape sources | data/loss_shape.csv holds three relative-loss-by-tier shapes (FICO odds table, Agarwal et al. 2018, placeholder for Track B) with citations; level calibration to the CCMR aggregate reproduces the industry loss for each year | todo |
| A4 | Residual page | docs/cards.html shows actual vs predicted charge-off and the residual per trust under each shape, with the scope sentence from PLAN §2 on the page; the ranking of trusts under each shape is stated | todo |

## B. Autos, loan level

| # | Task | Pass condition | Status |
|---|------|----------------|--------|
| B1 | ABS-EE fetcher | one command lists every ABS-EE filing for a chosen set of trusts and downloads the EX-102 XML into data/raw/autos/<trust>/<accession>/; manifest records URL, size, hash | todo |
| B2 | Loan-month panel | streaming parser writes parquet under data/panel/ with a stated schema; assetNumber persistence verified; competing-risk coding for payoff, charge-off, repurchase | todo |
| B3 | Same score, different lender | docs/autos.html chart 1: cumulative charge-off by origination cohort by 20-point score bucket by lender, with N per cell | todo |
| B4 | Loan size and payment burden at constant score | chart 2 with cohort and lender fixed effects, described as descriptive with controls | todo |
| B5 | Regression discontinuity at lender cutoffs | density test, first-stage jump in rate or amount, outcome jump, bandwidth sensitivity; published only if the first stage exists | todo |

## Open items and known gaps
- Discover Card Execution Note Trust was defeased 2025-12-18 (Capital One acquisition). Its history to Nov 2025 is usable only via OCR of image statements; out of scope for v1.
- Chase and BA compute loss rates on average balance; Amex, COMET and Synchrony on beginning balance. Keep per-trust basis in the data, never mix.
- Delinquency bucket edges differ by trust (design/scout-cards.md). 30+ and 90+ are the only cross-trust comparable cuts.
- CFPB CCP to CCIP panel break in 2025: aggregate charge-off levels are not spliceable across the 2023 and 2025 reports (design/scout-ccmr-tiers.md).
