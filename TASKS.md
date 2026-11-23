# Task board

One bounded task per session. Each has a pass condition written before work starts.
Status: `todo` | `doing` | `done YYYY-MM-DD` | `blocked (why)`.

## 0. Access and scouting

| # | Task | Pass condition | Status |
|---|------|----------------|--------|
| 0.1 | EDGAR access from a runner | `scout.yml` probe returns 200 from data.sec.gov with ABSRISK_CONTACT set | done 2026-09-08 (plain `abs-risk contact` User-Agent; any URL in the UA is refused; home ISP blocked regardless, PLAN §5; runs 34190694825 diag, 34190842910 full) |
| 0.2 | Card trust scouting | design/scout-cards.md has, per live trust, the charge-off row labels and the FICO and credit-limit tables copied from a downloaded prospectus | done 2026-09-08 (all seven trusts from raw 10-D exhibits and prospectus annexes; Discover defeased; Synchrony is VantageScore; Chase FICO is a 5% sample; Amex buckets do not map) |
| 0.3 | Auto ABS-EE scouting | design/scout-autos.md has, for three issuers across the spectrum, the field list, score distribution, delinquency and charge-off shares from a downloaded EX-102, and an asset-number persistence check across two months | done 2026-09-08 (nine loan files, seven issuers, 20 public filers found; asset ids persist 100% in same-deal pairs; credit score never changes month to month, so it is an origination attribute; retention and charge-off timing rules differ by issuer; design inputs for B1/B2 in design/scout-autos.md §11) |
| 0.4 | CFPB tier data | design/scout-ccmr-tiers.md has the tier definitions and every by-tier series the CCMR publishes, with workbook citations | done 2026-09-08 (finding: no loss by tier exists; utilization, lines, balances, late-fee incidence by tier do; workbooks for 2021, 2023, 2025 saved) |

## A. Cards, pool level

| # | Task | Pass condition | Status |
|---|------|----------------|--------|
| A1 | 10-D fetcher and parser for the six live trusts | one command pulls every 10-D since 2019 for Amex, COMET, Chase, Citi, Synchrony, BA into data/raw/cards/; parser emits monthly gross and net charge-off, payment rate, yield, 30+ and 90+ delinquency per trust into data/cards_monthly.csv; fixture test per trust; one golden number per trust traced to a filing | done 2026-09-08 (parsers verified against dollar rows within 1e-4; 552 filings since 2019; first runner pass = cards-refresh workflow; golden entries added 2026-11-09 in checks/golden.yaml, one per trust, checked against the filing text and the committed table by tests/test_golden.py. 2026-11-21: Citi prints only a net rate; its column was labelled gross until then (REVIEW.md abs-B-1), and every card result now reads the net rate for all six trusts) |
| A2 | Prospectus composition tables | FICO and credit-limit distributions for each live trust, with as-of date, bucket edges and basis (balances or accounts), in data/cards_composition.csv; crosswalks/fico_buckets.csv maps every bucket to the six CFPB tiers with the straddle rule written down | done 2026-09-08 (fixture build of seven prospectuses: 153 rows, 41 crosswalk rows; the committed six-trust tables: 138 and 36; every straddle flagged; design/cards-build.md. Since 2026-11-09 the analysis reads the crosswalk and a straddle-rule sensitivity is published) |
| A3 | Shape sources | data/loss_shape.csv holds three relative-loss-by-tier shapes (FICO odds table, Agarwal et al. 2018, placeholder for Track B) with citations; level calibration to the CCMR aggregate reproduces the industry loss for each year | done 2026-09-08 (four filled shapes: fico_odds, fico_fed2007, acms2018, acms2018_dpd90; consumer-odds shapes are 5-6x at deep subprime, card-level ACMS shapes 1.2x; CCIP and CCP levels 2013-2024; design/shape-sources.md) |
| A4 | Residual page | docs/cards.html shows actual vs predicted charge-off and the residual per trust under each shape, with the scope sentence from PLAN §2 on the page; the ranking of trusts under each shape is stated | done 2026-11-09 (docs/cards.html: actual against predicted per trust (section 3), residual and rank under each of four shapes (section 4), PLAN section 2 scope sentence in the note; rebuilt on the deduplicated table through Sep 2026. Ranking of the extremes holds under every shape; the middle three change rank. 2026-11-21, on the net rate and counted over 12 combinations of loss curve and straddle rule: Synchrony first in 10, Amex last in 10, no trust holds one rank in all 12; the stage split no longer reads conversion as the fate of late accounts, REVIEW.md abs-A-2) |

## B. Autos, loan level

| # | Task | Pass condition | Status |
|---|------|----------------|--------|
| B1 | ABS-EE fetcher | one command lists every ABS-EE filing for a chosen set of trusts and downloads the EX-102 XML into data/raw/autos/<trust>/<accession>/; manifest records URL, size, hash | done 2026-09-08 (autos-build workflow, one job per deal; ten deals, 759,808 loans, 10.4M loan-months, Jan 2025 to Jul 2026; Exeter 2025-1 and Honda 2025-1 resolved by name on the runner) |
| B2 | Loan-month panel | streaming parser writes parquet under data/panel/ with a stated schema; assetNumber persistence verified; competing-risk coding for payoff, charge-off, repurchase | done 2026-09-08 (`loans` parquet per deal committed under data/autos/; loan-month parquet optional, gitignored) |
| B3 | Same score, different lender | docs/autos.html chart 1: cumulative charge-off by origination cohort by 20-point score bucket by lender, with N per cell | done 2026-11-09 (Aalen-Johansen with delayed entry and bootstrap bands, b1_*.csv; by origination year in b1_cohort_at_12/24.csv and page section 2. Since review round 2 (2026-11-10) every b1 table counts a loan from its fourth month in the trust, a ratio's lower cell needs ten charge-offs, and each ratio carries a loan-resampling interval (b1_gap.csv): the same-bucket gap is a median 16x (95% interval 10 to 19), 9x without Exeter, not the 50x published before; inside one vintage the ratio is 0.93 of the pooled one over 29 pairs. Descriptive. 2026-11-21: a buy-back of a loan that had been 90 days late is a default (REVIEW.md abs-A-1), so the median is still 16x but its range is 12 to 22 and it is 13x without Exeter; the page now leads with fixed pairs by year of loan age (Exeter and Santander over CarMax 11.7 and 13.4 in year one, 6.8 and 5.3 in year two; b1_fixed_pairs.csv), and the charge-off-only figures are in b1_gap_trust_loss.csv) |
| B4 | Loan size and payment burden at constant score | chart 2 with cohort and lender fixed effects, described as descriptive with controls | done 2026-11-09 (chart 2 = forest plot of the terms specification on the page. Since review round 1 every specification also holds months in pool fixed, sparse edge levels are merged, clustered intervals use t(9), and lender intervals carry the deal-to-deal spread (REVIEW.md R1-6, R1-9). Terms, top quintile against bottom: amount 0.72 [0.64, 0.81], PTI 2.47 [2.03, 3.01], LTV 4.24 [3.35, 5.38]; lenders against Santander: Honda 0.15 [0.04, 0.61], Toyota 0.19 [0.05, 0.77], CarMax 0.23 [0.06, 0.89] distinguishable; Capital One 0.36, AmeriCredit 0.75, Exeter 1.10 not. The numbers once listed here (amount n.s., PTI 1.3-1.8, LTV 1.7-2.6) are the price column, where APR is a mediator.) |
| B5 | Regression discontinuity at lender cutoffs | density test, first-stage jump in rate or amount, outcome jump, bandwidth sensitivity; published only if the first stage exists | done 2026-11-09 (null. 16 candidates, 8 fail density, 7 usable; 0 of 14 cutoff-horizon estimates clear zero with a robust interval at the optimal bandwidth and 0 of 14 at every bandwidth; 4 of the 56 off-optimal refits do, about what chance gives; b3_rd_bandwidths.csv. design/methods.md section 3) |

## Handoff
HANDOFF.md, rewritten every session, is the handoff. The 2026-09-08 note that stood here described
the scouting stage and is in git history.

## Open items and known gaps
- From the independent review of 2026-11-10 (REVIEW.md status table): **Closed 2026-11-22:** abs-A-4 (late-first-age
  cells blanked), abs-A-5 and abs-B-3 (score comparability, co-borrower averaging and shelf selection disclosed on the
  pages and in `design/methods.md`), abs-A-7 (50-loan risk-set floor in `survival._curves` and
  `lender_gap.group_life_tables`), abs-B-5 (Exeter selection dated from 2025-2), abs-B-6 (Capital One negative
  `recoveredAmount` negated on parse/load, delayed `chargeoff_amount` handled without summing across retained months,
  count-based basis stated on `docs/autos.html`), and Round 2's R2-2 (Synchrony calibrated to its 24.3% private-label
  prospectus blend using both CFPB series, with `a1_product.csv` and section 4 table).
- The hazard model's numbers in row B4 are from before the default definition changed; the page prints the
  refitted ones.
- Track B schema hazards to encode, not discover again: PTI is a fraction everywhere except Capital One (percent);
  three different "no score" encodings; Ford carries a commercial-obligor slice on a different score scale with no
  PTI; Santander repeats `subvented` in about 1% of records (take the first value); Synchrony-style score-type labels
  vary ("Bureau", "FICO", VantageScore at Exeter).
- Track B retention: CarMax, Capital One and Exeter keep every loan for the deal's life; Santander, AmeriCredit and
  Toyota keep charge-offs but drop payoffs the month after; Ford drops everything after one month. Exit is the
  earlier of first zero-balance code and first absence.
- Track A mapping: five of seven FICO tables collapse to <600 / 600-659 / 660-719 / 720+; Amex's buckets
  (560/660/700/760) do not, Synchrony is VantageScore, Chase is a 5% sample. The crosswalk carries these as flags.
- Discover Card Execution Note Trust was defeased 2025-12-18 (Capital One acquisition). Its history to Nov 2025 is usable only via OCR of image statements; out of scope for v1.
- Chase and BA compute loss rates on average balance; Amex, COMET and Synchrony on beginning balance. Keep per-trust basis in the data, never mix.
- Delinquency bucket edges differ by trust (design/scout-cards.md). 30+ and 90+ are the only cross-trust comparable cuts.
- CFPB CCP to CCIP panel break in 2025: aggregate charge-off levels are not spliceable across the 2023 and 2025 reports (design/scout-ccmr-tiers.md).
