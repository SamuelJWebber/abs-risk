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
| A1 | 10-D fetcher and parser for the six live trusts | one command pulls every 10-D since 2019 for Amex, COMET, Chase, Citi, Synchrony, BA into data/raw/cards/; parser emits monthly gross and net charge-off, payment rate, yield, 30+ and 90+ delinquency per trust into data/cards_monthly.csv; fixture test per trust; one golden number per trust traced to a filing | done 2026-09-08 (parsers verified against dollar rows within 1e-4; 552 filings since 2019; first runner pass = cards-refresh workflow; golden entries still to add to checks/) |
| A2 | Prospectus composition tables | FICO and credit-limit distributions for each live trust, with as-of date, bucket edges and basis (balances or accounts), in data/cards_composition.csv; crosswalks/fico_buckets.csv maps every bucket to the six CFPB tiers with the straddle rule written down | done 2026-09-08 (153 rows, 41 crosswalk rows, every straddle flagged; design/cards-build.md) |
| A3 | Shape sources | data/loss_shape.csv holds three relative-loss-by-tier shapes (FICO odds table, Agarwal et al. 2018, placeholder for Track B) with citations; level calibration to the CCMR aggregate reproduces the industry loss for each year | done 2026-09-08 (four filled shapes: fico_odds, fico_fed2007, acms2018, acms2018_dpd90; consumer-odds shapes are 5-6x at deep subprime, card-level ACMS shapes 1.2x; CCIP and CCP levels 2013-2024; design/shape-sources.md) |
| A4 | Residual page | docs/cards.html shows actual vs predicted charge-off and the residual per trust under each shape, with the scope sentence from PLAN §2 on the page; the ranking of trusts under each shape is stated | doing (driver `absrisk analyze cards` and page written; waits on data/cards_monthly.csv from the cards-refresh run) |

## B. Autos, loan level

| # | Task | Pass condition | Status |
|---|------|----------------|--------|
| B1 | ABS-EE fetcher | one command lists every ABS-EE filing for a chosen set of trusts and downloads the EX-102 XML into data/raw/autos/<trust>/<accession>/; manifest records URL, size, hash | done 2026-09-08 (autos-build workflow, one job per deal; ten deals, 759,808 loans, 10.4M loan-months, Jan 2025 to Jul 2026; Exeter 2025-1 and Honda 2025-1 resolved by name on the runner) |
| B2 | Loan-month panel | streaming parser writes parquet under data/panel/ with a stated schema; assetNumber persistence verified; competing-risk coding for payoff, charge-off, repurchase | done 2026-09-08 (`loans` parquet per deal committed under data/autos/; loan-month parquet optional, gitignored) |
| B3 | Same score, different lender | docs/autos.html chart 1: cumulative charge-off by origination cohort by 20-point score bucket by lender, with N per cell | doing (Aalen-Johansen with delayed entry and bootstrap bands; first result: at 480-620 Exeter ~20%, Santander ~14%, AmeriCredit ~10% by 24 months; at 700-760 Santander 5-10% vs captives under 1.5%) |
| B4 | Loan size and payment burden at constant score | chart 2 with cohort and lender fixed effects, described as descriptive with controls | doing (discrete-time competing-risks hazard: amount quintiles OR 1.0-1.1 n.s.; PTI 1.3-1.8; LTV 1.7-2.6; APR 1.9-11; lender excess for Exeter/Santander vanishes with terms) |
| B5 | Regression discontinuity at lender cutoffs | density test, first-stage jump in rate or amount, outcome jump, bandwidth sensitivity; published only if the first stage exists | doing (cutoff search with bandwidth-stability rule; rdrobust + rddensity; first run in progress) |

## Handoff 2026-09-08 (session 1)
Scouting is complete on both tracks and the CFPB side. EDGAR access works only from GitHub Actions with the plain
`abs-risk contact@email` User-Agent (secret ABSRISK_CONTACT is set); the home ISP is blocked for good. Raw artifacts
live under data/raw/scout/edgar, edgar2, edgar3 (gitignored, re-fetchable with `gh run download`). Next session,
one of: A3 (shape sources, needs no EDGAR, unblocks the whole card residual), A1 (10-D fetcher and parser; labels
and bases are in design/scout-cards.md), or B1+B2 (ABS-EE fetcher and parquet panel; field list, unit fixes,
retention and exit rules are in design/scout-autos.md §11). The auto scout's third-pass list (§10 there) should be
folded into B1's first run rather than run as scouting.

## Open items and known gaps
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
