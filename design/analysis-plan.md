# Analysis plan: what gets estimated, how, and on what tables

Written 2026-09-08 after scouting (design/scout-*.md). This is the contract between the data builders and the
analysis. Schemas here are what the fetchers and parsers must emit; the estimators below are what runs on them.

## 0. The question and its honest translation

The question asked: "charge-off of Amex vs Capital One for the same FICO and line amount", and "how much line
amount influences payment hierarchy". Payment hierarchy proper (which debt one person pays first) needs one
person observed across products; no public data has that. The two public neighbours, in order of how much
they can say:

1. **Autos, loan level (Track B).** Same score, different lender, different loan size: the auto version of the
   question, estimable with loan-level data and proper survival methods. Lender cutoffs allow a regression
   discontinuity, which is the only design here that supports a causal sentence.
2. **Cards, pool level (Track A).** Issuer effect at constant score mix. Descriptive. Cannot separate
   underwriting, product, selection, and behaviour. Reported with that sentence attached.

## 1. Track B tables

### 1a. `loans` (one row per loan per deal; committed as parquet, one file per deal under data/autos/)

| column | type | source / rule |
|---|---|---|
| deal | str | deal slug, e.g. `sdart-2026-1` |
| lender | str | sponsor family: santander, exeter, americredit, carmax, capone, toyota, ford, honda, ... |
| cik | str | filer CIK (10 digits) |
| asset_id | str | assetNumber, verbatim (opaque at Capital One) |
| first_period | date | first reportingPeriodEndingDate the loan appears |
| last_period | date | last period the loan appears |
| orig_month | date | originationDate (MM/YYYY -> first of month) |
| orig_amount | float | originalLoanAmount |
| orig_apr | float | originalInterestRatePercentage, as a fraction (0.18 = 18%) |
| orig_term | int | originalLoanTerm (months) |
| pti | float | paymentToIncomePercentage normalised to a fraction (Capital One reports percent: divide by 100) |
| score | int or null | obligorCreditScore; null when 0, empty, or non-numeric |
| score_type | str | obligorCreditScoreType verbatim (Bureau / FICO / VantageScore / ...) |
| score_missing | bool | true when score is null |
| vehicle_value | float | vehicleValueAmount |
| ltv | float | orig_amount / vehicle_value, null if value <= 0 |
| new_used | str | vehicleNewUsedCode |
| state | str | obligorGeographicLocation at first observation |
| income_verified | str | obligorIncomeVerificationLevelCode |
| employment_verified | str | obligorEmploymentVerificationCode |
| subvented | str | first value seen (Santander repeats the element) |
| commercial | bool | Ford commercial-obligor slice (score scale 1-670, no PTI); excluded from consumer analyses |
| exit_period | date or null | earlier of: period with the first non-empty zeroBalanceCode; period after which the loan is absent |
| exit_type | str | chargeoff (code 4) / prepay (code 1) / repurchase (code 3) / other (2, 5, 99) / absent (dropped with no code) / censored |
| exit_code | str | zeroBalanceCode verbatim at exit |
| months_observed | int | count of periods present |
| max_dpd | int | max currentDelinquencyStatus (days) over the life |
| first_30_period, first_60_period, first_90_period | date or null | first period with dpd >= 30 / 60 / 90 |
| chargeoff_amount | float | chargedoffPrincipalAmount at exit |
| recovered_amount | float | sum of recoveredAmount |
| bal_first, bal_last | float | reportingPeriodActualEndBalanceAmount at first and last observation |

Retention rules from scouting: CarMax, Capital One and Exeter keep every loan for the deal's life; Santander,
AmeriCredit and Toyota keep charge-offs but drop payoffs the month after; Ford drops everything after one month.
The exit rule above handles all three. A loan absent with no code is `absent` and treated as prepay-like exit in
sensitivity, censored in the main run; the share is reported per deal.

### 1b. `loan_months` (one row per loan per period; parquet, NOT committed, rebuilt by the workflow)

deal, asset_id, period, balance_begin, balance_end, dpd, zb_code, scheduled_payment, actual_payment, interest_paid,
principal_paid, chargeoff_amount, recovered_amount, repossessed, servicing_flag. Kept for time-varying models later.

### 1c. `deals` (metadata; committed CSV)

deal, lender, cik, cutoff_date, first_filing, last_filing, n_filings, score_model_stated, score_floor_stated,
wa_score_stated, prospectus_accession, notes.

## 2. Track B estimators

All on `loans`, consumer loans only (`commercial = false`), origination cohorts with at least 12 months of
observation for the cumulative measures.

**B1. Descriptive, same score, different lender.** Kaplan-Meier style cumulative charge-off by months since
origination, by 20-point score bucket, by lender. Competing exits (prepay, repurchase) are censoring in the
Kaplan-Meier version and competing risks in the Aalen-Johansen version; both are shown, the gap between them is
the prepayment effect. Every cell prints N.

**B2. Discrete-time hazard, competing risks.** Loan-month expansion from `loans` (age 1..months_observed).
Multinomial logit of the monthly event (none / chargeoff / prepay) on: loan-age dummies (baseline hazard),
score-bucket dummies, lender dummies, origination-cohort dummies (quarter), log(orig_amount), orig_apr, orig_term,
pti, ltv, new_used, state region. Standard errors clustered by deal. The lender coefficients at fixed score are
the "same FICO, different lender" answer; the log(amount) and pti coefficients at fixed score and lender are the
"how much does size matter" answer. Reported as hazard ratios with 95% intervals, plus a version without
controls, so the reader sees how much of the raw gap is composition.

**B3. Regression discontinuity at lender cutoffs.** Step 1, find the cutoffs: within lender and cohort, plot mean
orig_apr and mean orig_amount against score in 5-point bins; a cutoff is a score where APR jumps by more than the
local noise (formal: fit local linear on each side, test the jump). Step 2, validity: McCrary density test of
score at the cutoff (a pile-up on the good side means manipulation or selection); covariate balance on
orig_term, pti, ltv, new_used at the cutoff. Step 3, estimate: local linear RD of (a) the first stage, APR and
amount on score, and (b) the outcome, 12- and 24-month charge-off on score, with a data-driven bandwidth
(rdrobust, MSE-optimal) and robustness across bandwidths. The ratio (b)/(a) is the effect of the pricing or
sizing change on default for loans at the cutoff. Published only where the first stage exists and the density
test passes. Known non-cutoffs: the 650 floor at CarMax, 620 at Toyota, and the 640 cliffs at Exeter and
AmeriCredit are securitization selection, not pricing; these are reported as such and not used.

**B4. What this says about cards.** Nothing directly. The page says so. The score-shape from B1 feeds Track A as
one of three candidate shapes.

## 3. Track A tables

### 3a. `cards_monthly` (committed CSV)

trust, period_end, receivables_principal, gross_co_rate, net_co_rate, co_basis (beginning / average / ending),
co_annualisation (x12 / x365_over_days / actual_365), payment_rate, yield, delinq_30plus_share, delinq_90plus_share,
delinq_basis, excess_spread, source_accession, source_file, row_labels_json.

Row labels and bases per trust are in design/scout-cards.md; the parser matches labels, never positions.

### 3b. `cards_composition` (committed CSV)

trust, as_of, table (fico / credit_limit / account_age), bucket_lo, bucket_hi, share_receivables, share_accounts,
score_type (FICO / VantageScore), sample_note (Chase 5% sample), prospectus_accession, prospectus_file.

### 3c. `loss_shape` (committed CSV)

shape_source (fico_odds / acms2018 / autos_b1), tier (deep_subprime / subprime / near_prime / prime / prime_plus /
superprime), relative_loss, note, citation. Plus `ccmr_level.csv`: year, gp_chargeoff_rate, balance_share by tier,
citation to the CFPB figure-data workbook.

## 4. Track A estimators

**A1. Shape times level prediction.** For each trust and month, predicted = level(year) x sum over tiers of
share(trust, tier) x relative_loss(tier), with level calibrated so the CFPB balance mix reproduces the CFPB
aggregate charge-off in that year. Residual = actual - predicted, under each of the three shapes.

**A2. Panel regression, the honest version.** Trust-month panel, 2019 to date. gross_co_rate on: tier shares
(from composition tables, interpolated between prospectus dates), month fixed effects, trust fixed effects.
With six trusts and slow-moving mix, trust fixed effects and mix are close to collinear; the regression is
reported with and without trust effects and the reader is told which one identifies what. Standard errors:
Driscoll-Kraay (cross-sectional dependence across trusts in the same month).

**A3. What is reported.** Per trust: actual, predicted (three shapes), residual over time. Ranking of trusts by
residual under each shape. If the ranking is not stable across shapes, that is the headline.

## 5. Order of work

1. A3 shape sources (no EDGAR).
2. B1 fetcher + B2 parser to `loans` on a first deal set: sdart-2026-1, sdart-2025-1, carmax-2026-2, carmax-2025-1,
   copar-2025-1, exeter-2025-5, exeter-2025-1, amcar-2024-1, toyota-2025-a, honda-2025-1. Built and tested locally
   on the scout files; run on Actions as a matrix, one job per deal, artifacts collected and committed by a final job.
3. A1 10-D fetcher + parser to `cards_monthly` for the six live trusts, 2019 to date; A2 composition tables.
4. Estimators B1, B2, B3 on `loans`; A1, A2 on the card tables. Pages under docs/.
