# Shape sources: relative loss by credit tier, and the CFPB level that scales it

Written 2026-09-08 for task A3. Code: `src/absrisk/shape/`. Data: `data/loss_shape.csv` (shapes),
`data/ccmr_level.csv` (level). Evidence copies: `tests/fixtures/shape/`. Scouting that established the
gap this fills: `design/scout-ccmr-tiers.md` (the CFPB publishes no charge-off by score tier, by choice).

## 0. What is being built and why

Track A predicts a card trust's charge-off from its FICO mix:

    predicted(trust, year) = level(year) x sum_over_tiers( share(trust, tier) x relative_loss(tier) )

- `relative_loss(tier)` is a **shape**: how much worse or better each tier loses than the prime tier
  (660-719), with prime = 1.0. No public source gives this for cards directly, so three candidates from
  public sources are laid side by side and the residual is reported under each.
- `level(year)` is the multiplier that makes the CFPB's own tier mix reproduce the CFPB's aggregate
  general-purpose charge-off rate in that year. Because every shape has prime = 1, the level is the
  charge-off rate the shape implies for the prime tier.

The six tiers are the CFPB's (2023 report PDF p12; 2025 report PDF p15): deep subprime 579 or less,
subprime 580-619, near-prime 620-659, prime 660-719, prime plus 720-799, superprime 800 or greater.

## 1. The one straddle rule

Nothing public gives the score density inside a band, so every band or bucket is taken as uniform over
the integer scores it spans. A band that straddles a tier boundary is split in proportion to the number
of integer scores on each side; a tier fed by several bands gets the score-count-weighted average of
their rates. This is linear interpolation of the cumulative share in score. The same function pair
(`tiers.tiers_from_buckets` for prospectus shares, `tiers.band_rates_to_tiers` for published rates)
does both, so the prospectus crosswalk in A2 and the shapes here cannot drift apart.

Example, a typical prospectus table: `<600 / 600-659 / 660-719 / 720+` with shares 10/20/30/40%.
`<600` is 300 integer scores of which 280 are deep subprime and 20 subprime, so it contributes
9.33% to deep subprime and 0.67% to subprime; `600-659` gives 20 of 60 scores to subprime (6.67%)
and 40 to near-prime (13.33%); `720+` is 131 scores, 80 prime plus (24.43%) and 51 superprime
(15.57%). `tests/test_shape.py::test_tiers_from_buckets_hand_example_with_straddles` pins this.

Consequences worth knowing: the FICO band 580-669 covers subprime and near-prime whole, so those two
tiers get the same value from any source that uses it; the 720+ band in the 2007 table lumps prime
plus with superprime; the ACMS "<=660" group covers all three below-prime tiers. Every such case is
written into the `flag` column of `loss_shape.csv` by the code, not by hand.

## 2. The shapes

### 2.1 `fico_odds`: Experian's "likely to become seriously delinquent" by FICO range

**What it measures.** For consumers in a FICO Score range, the share Experian says are "likely to become
seriously delinquent (i.e., go more than 90 days past due on a debt payment) in the future". This is
the consumer-level, any-account odds concept FICO Scores are built on (90+ days late within 24 months).

**Source.** Experian's per-score pages "NNN Credit Score: Is it Good or Bad?", one page per range,
fetched 2026-09-08 with curl; the visible text of each page is saved as
`tests/fixtures/shape/experian_<score>_credit_score.txt`:

| FICO range (Experian's label) | Page | Verbatim | Rate used |
|---|---|---|---|
| 300-579 (Very Poor) | [550-credit-score](https://www.experian.com/blogs/ask-experian/credit-education/score-basics/550-credit-score/) | "Roughly 62% of consumers with credit scores under 579 are likely to become seriously delinquent (i.e., go more than 90 days past due on a debt payment) in the future." | 62 |
| 580-669 (Fair) | [620-credit-score](https://www.experian.com/blogs/ask-experian/credit-education/score-basics/620-credit-score/) | "Statistically speaking, 28% of consumers with credit scores in the Fair range are likely to become seriously delinquent in the future." | 28 |
| 670-739 (Good) | [700-credit-score](https://www.experian.com/blogs/ask-experian/credit-education/score-basics/700-credit-score/) | "Approximately 9% of consumers with Good FICO Scores are likely to become seriously delinquent in the future." | 9 |
| 740-799 (Very Good) | [760-credit-score](https://www.experian.com/blogs/ask-experian/credit-education/score-basics/760-credit-score/) | "Approximately 1% of consumers with Very Good FICO Scores are likely to become seriously delinquent in the future." | 1 |
| 800-850 (Exceptional) | [810-credit-score](https://www.experian.com/blogs/ask-experian/credit-education/score-basics/810-credit-score/) | "Less than 1% of consumers with Exceptional FICO Scores are likely to become seriously delinquent in the future." | 1 (upper bound, flagged) |

**Mapping.** Deep subprime = 300-579 band. Subprime and near-prime both = 580-669 band (28).
Prime = 10 scores of 580-669 and 50 of 670-739: (10x28 + 50x9)/60 = 12.17. Prime plus = 20 of
670-739 and 60 of 740-799: (20x9 + 60x1)/80 = 3.0. Superprime = 1 (bound).

**Limits.** Consumer-level and any-account (a mortgage or auto delinquency counts), not a card
charge-off; incidence, not dollars, so it says nothing about balance-weighting; undated ("statistically
speaking"); rounded to whole percents; the top band is a bound, so superprime is overstated and the
superprime/prime-plus gap understated. Its relative values are the steepest of the set.

### 2.2 `fico_fed2007`: Fair Isaac default rate by FICO band, 2000-2002, via the Federal Reserve

**What it measures.** "Default Rate on New Loans for the Two Years after Origination, by FICO Credit
Score, October 2000 to October 2002". Note in the source: "New accounts were those opened in the six
months from October 2000 to April 2001. An account was in default if it had been delinquent for at
least ninety days or had any other derogatory credit information within the two years starting in
October 2000. Source. Fair Isaac Corp."

**Source.** Board of Governors of the Federal Reserve System, *Report to the Congress on Credit Scoring
and Its Effects on the Availability and Affordability of Credit* (August 2007), "Tables for General
Background", Table 2. https://www.federalreserve.gov/boarddocs/rptcongress/creditscore/general_tables.htm
(fetched 2026-09-08; copy at `tests/fixtures/shape/fed2007_creditscore_general_tables.htm`).

| FICO band (as printed) | Default rate (%) |
|---|---|
| Less than 520 | 41.0 |
| 520-559 | 28.4 |
| 560-599 | 22.5 |
| 600-639 | 15.8 |
| 640-679 | 8.9 |
| 680-719 | 4.4 |
| 720 or more | 1.0 |

**Mapping.** "Less than 520" is taken as 300-519, "720 or more" as 720-850. Deep subprime =
(220x41.0 + 40x28.4 + 20x22.5)/280 = 37.88; subprime = (20x22.5 + 20x15.8)/40 = 19.15; near-prime =
(20x15.8 + 20x8.9)/40 = 12.35; prime = (20x8.9 + 40x4.4)/60 = 5.90; prime plus = superprime = 1.0.

**Limits.** Account-level default on new accounts of every loan type, not card charge-off, not
balance-weighted; a 2000-2002 vintage on the FICO models of the time; the 720+ band is not split, so
this shape cannot tell prime plus from superprime. Its virtue is that it is a FICO-sourced table with
a stated definition, a stated window, and 40-point bands that separate subprime from near-prime,
which the Experian bands cannot.

### 2.3 `acms2018`: card charge-offs by origination FICO, Agarwal, Chomsisengphet, Mahoney and Stroebel (QJE 2018)

**What it measures.** Net charge-offs per dollar of balance on the card itself, by FICO group at
origination, over the first 24 months of the account.

**Source.** Agarwal, Chomsisengphet, Mahoney and Stroebel, "Do Banks Pass Through Credit Expansions to
Consumers Who Want to Borrow?", *Quarterly Journal of Economics* 133(1), 2018, pp. 129-190. Table IV,
"Quasi-experiment-level summary statistics, post origination", pp. 154-155 (PDF pp. 26-27 of
https://pages.stern.nyu.edu/~jstroebe/PDF/ACMS_Passthrough.pdf; copy at
`tests/fixtures/shape/acms2018_passthrough_stern.pdf`; the two pages are printed landscape and the
extracted text, reversed back to reading order, is at `tests/fixtures/shape/acms2018_table4_pages154-155.txt`).
Data: OCC Credit Card Metrics, account-level data from the eight largest US banks, January 2008 to
December 2014 (paper p. 138); the quasi-experiment sample is cards originated January 2008 to November
2013 within 50 FICO points of a credit-limit cutoff (p. 139), and Table IV averages accounts within 5
FICO points of the cutoff across the 743 quasi-experiments (table notes). "Chargeoffs" are gross
charge-offs minus recoveries (fn 29). FICO groups are defined at origination.

Transcribed rows (means across quasi-experiments; groups <=660, 661-700, 701-740, >740):

| Months after origination | Cumulative chargeoffs ($) | ADB ($) | Cumulative prob 90+ DPD (%) |
|---|---|---|---|
| 12 | 47 / 67 / 61 / 35 | 1,260 / 2,160 / 2,197 / 2,101 | 4.8 / 3.3 / 2.9 / 1.3 |
| 24 | 178 / 259 / 245 / 124 | 1,065 / 1,794 / 1,719 / 1,524 | 10.2 / 8.1 / 7.2 / 3.2 |
| 36 | 306 / 443 / 403 / 190 | 1,164 / 1,734 / 1,481 / 1,343 | 13.2 / 10.9 / 9.7 / 4.5 |
| 48 | 403 / 552 / 524 / 261 | 1,079 / 1,501 / 1,260 / 1,064 | 14.5 / 12.2 / 10.9 / 5.1 |
| 60 | 483 / 634 / 602 / 322 | 1,050 / 1,465 / 1,097 / 1,084 | 15.2 / 12.9 / 11.5 / 5.4 |

Cross-checks against the paper's text: "At 12 months after origination, ADB increase from $1,260 for
the lowest FICO score group (<=660), to more than $2,150 for the middle FICO score groups, before
falling to $2,101 for the highest" (p. 153); "At 48 months after origination, cumulative total costs
are $588 for the lowest FICO score group, slightly more than $800 for the middle groups, and $488 for
the highest" and chargeoffs are "more than half of these costs" (p. 172): 403/588 = 69%, 261/488 = 53%.
Table I (p. 141) gives the same groups' history at origination, "number of times 90+ DPD in the last
24 months": 0.51 / 0.21 / 0.14 / 0.05, the FICO-odds concept measured on these consumers.

**Rate definition.** Annualised charge-off rate over months 1-24 = cumulative chargeoffs at 24 months
divided by (ADB at 12 months + ADB at 24 months), each ADB value standing for one year of balance.
<=660: 178/(1260+1065) = 7.66%; 661-700: 259/(2160+1794) = 6.55%; 701-740: 245/(2197+1719) = 6.26%;
>740: 124/(2101+1524) = 3.42%. Two years rather than one because year 1 of a new card is immature
(charge-off follows 180 days of delinquency); not longer because from 36 months the 701-740 group's
rate exceeds 661-700's (its balances shrink faster than its charge-offs stop), and the ranking of the
raw groups is no longer monotone. All horizons, both bases:

| Months | CO/ADB <=660 | 661-700 | 701-740 | >740 | P(90+ DPD) <=660 | 661-700 | 701-740 | >740 |
|---|---|---|---|---|---|---|---|---|
| 12 | 3.73 | 3.10 | 2.78 | 1.67 | 4.8 | 3.3 | 2.9 | 1.3 |
| 24 | 7.66 | 6.55 | 6.26 | 3.42 | 10.2 | 8.1 | 7.2 | 3.2 |
| 36 | 8.77 | 7.79 | 7.47 | 3.82 | 13.2 | 10.9 | 9.7 | 4.5 |
| 48 | 8.82 | 7.68 | 7.87 | 4.33 | 14.5 | 12.2 | 10.9 | 5.1 |
| 60 | 8.60 | 7.33 | 7.76 | 4.53 | 15.2 | 12.9 | 11.5 | 5.4 |

(CO/ADB in percent per year, cumulative to the horizon; P(90+ DPD) cumulative percent of accounts.)

**Mapping.** Groups are taken as 300-660, 661-700, 701-740, 741-850. Deep subprime, subprime and
near-prime all = the <=660 group (7.66%), flagged. Prime = (1x7.66 + 40x6.55 + 19x6.26)/60 = 6.48%.
Prime plus = (21x6.26 + 59x3.42)/80 = 4.17%. Superprime = 3.42%.

**Limits.** A selected sample: new accounts at credit-limit cutoffs at the largest banks, originated
2008-2013, observed for their first two years, so both the crisis vintage and the "new account" life
stage differ from a seasoned trust pool. The <=660 group is one number for three tiers, and the
credit-limit cutoffs in that group sit close to 660 (paper, Figure II Panel E), so it understates deep
subprime by an unknown amount. Charge-offs are net of recoveries where the CFPB level is gross. And the
shape it gives is *flat*: 1.18 for everything below prime, 0.53 for superprime, against 5 and 0.08 from
the FICO odds. Part of that is real (dollar losses per dollar of balance vary far less across tiers
than the incidence of delinquency, because low-score accounts carry small balances), part is the
sample. That gap is the point of carrying more than one shape.

Note for PLAN.md: the paper's data are OCC Credit Card Metrics, 2008-2014 (originations 2008-2013),
not Y-14M 2008-2012 as PLAN section 2 says.

### 2.4 `acms2018_dpd90`: the same table, incidence instead of dollars

Cumulative probability of 90+ days past due within 24 months on the treated card, per account:
10.2 / 8.1 / 7.2 / 3.2 percent. Same mapping and caveats as 2.3. Included because it is the same
sample and groups on the FICO-odds definition (90+ DPD within 24 months), which shows how much of the
FICO-vs-ACMS gap is definition and how much is sample: on this definition the ACMS sample is still
flat (1.30 below prime, 0.41 superprime), so the sample, not the dollar-weighting, is most of it.

### 2.5 `autos_b1`: placeholder

Six rows with `relative_loss` empty and `flag = placeholder`. Filled by Track B from the auto
loan-level panel (cumulative charge-off by 20-point score bucket, estimator B1), mapped with the same
`band_rates_to_tiers`. `shape_vector` and `predict_chargeoff` refuse it until it is filled.

### 2.6 Looked for, not used

- FICO's own odds chart. FICO and myFICO pages describe the 90+ DPD-within-24-months design but do not
  publish the band table today. An older eight-band myFICO table (800+ 1%, 750-799 2%, 700-749 5%,
  650-699 15%, 600-649 31%, 550-599 51%, 500-549 71%, under 500 87%) circulates on secondary sites only;
  the 2017 myFICO "Understanding Your FICO Score" booklet (myFICO_UYFS_Booklet.pdf, fetched) does not
  contain it, and the Federal Reserve's 2007 report reproduces only the population distribution from
  that myFICO page, not the odds. Not used because no primary copy was found.
- The CFPB reports: no loss by tier in any edition (scout note section 0). Late-fee incidence by tier
  (scout section 4.6) is the nearest CFPB proxy and could be a fourth shape later; it is a 30-day
  measure and Y-14-scored, so it was left out of v1.
- NY Fed Consumer Credit Panel transition rates by score bucket: not attempted this session.

## 3. Side by side

`relative_loss` (prime = 1):

| Tier | fico_odds | fico_fed2007 | acms2018 | acms2018_dpd90 | autos_b1 |
|---|---|---|---|---|---|
| Deep subprime (<=579) | 5.096 | 6.420 | 1.182 | 1.299 | - |
| Subprime (580-619) | 2.301 | 3.246 | 1.182 | 1.299 | - |
| Near-prime (620-659) | 2.301 | 2.093 | 1.182 | 1.299 | - |
| Prime (660-719) | 1.000 | 1.000 | 1.000 | 1.000 | - |
| Prime plus (720-799) | 0.247 | 0.169 | 0.643 | 0.541 | - |
| Superprime (800+) | 0.082 | 0.169 | 0.528 | 0.408 | - |

`source_rate` in each source's own unit (percent of consumers; percent of accounts; fraction of balance
per year; percent of accounts):

| Tier | fico_odds | fico_fed2007 | acms2018 | acms2018_dpd90 |
|---|---|---|---|---|
| Deep subprime | 62.00 | 37.88 | 0.0766 | 10.20 |
| Subprime | 28.00 | 19.15 | 0.0766 | 10.20 |
| Near-prime | 28.00 | 12.35 | 0.0766 | 10.20 |
| Prime | 12.17 | 5.90 | 0.0648 | 7.85 |
| Prime plus | 3.00 | 1.00 | 0.0417 | 4.25 |
| Superprime | 1.00 | 1.00 | 0.0342 | 3.20 |

Reading it: the two consumer-odds shapes say a deep-subprime dollar loses five to six times a prime
dollar and a superprime dollar a tenth; the card-level ACMS shapes say 1.2 and 0.5. Under either the
level is recalibrated so the industry mix still reproduces the industry loss, so what changes between
shapes is how far apart two trusts with different mixes are *predicted* to be, and therefore which
trust carries the residual. A4 reports the ranking under each; if it moves, that is the finding.

## 4. The level: `data/ccmr_level.csv`

One row per year and bureau panel. Built by `python -m absrisk.shape.build_level` from the two CCMR
figure-data workbooks (not committed; URLs and hashes in scout note section 1), reading every cell by
figure label and column header. Columns: `year, series, gp_chargeoff_rate, gp_chargeoff_rate_ye,
n_periods, share_<tier> x6, mix_periods, citation_rate, citation_mix`.

### 4.1 Aggregate rate

- `ccip` (2014-2024): 2025 workbook, sheet "Section 4 - Pmts, Debt, Coll.", Figure 53 "Monthly
  annualized rate of balances charged off (CCIP)", column "General purpose". Gross, pre-recovery,
  balance-weighted (2025 report fn 129). `gp_chargeoff_rate` = mean of the 12 monthly values;
  `_ye` = December.
- `ccp` (2013-2022): 2023 workbook, sheet "Section 3 - Use of credit", Figure 18 "Quarterly annualized
  rate of gross outstanding balances charged off (CCP)", column "General purpose". Mean of the four
  quarters; `_ye` = Q4.

The two panels are not on one basis: for the same years the CCIP rate is roughly 0.6x the CCP rate
(2019: 3.67% vs 6.53%) while their delinquency series agree (scout note sections 3.2-3.3, 2025 report
fn 13). They are two series, never spliced, and a trust's residual is comparable only with residuals
computed under the same series. Both reproduce the scout note's tables to the digit
(`test_level_matches_scout_note_spot_values`).

### 4.2 Balance share by tier: not published, so constructed

No CCMR workbook gives balances by tier. What exists: per-cardholder balance by tier every period
(2025 Fig 16, 2023 S3 Fig 5, all cards), per-account general-purpose balance by tier at one year-end
(2025 Fig 18 for 2024, 2023 S3 Fig 7 for 2022), consumers with a general-purpose card by tier at one
year-end (2025 Fig 3, YE2023), and general-purpose accounts by tier at one year-end (2023 S5 Fig 17,
YE2022; 2021 S2 Fig 1, YE2020, five tiers). Utilization and credit line per cardholder by tier exist
every year (2025 Figs 91 and 89; 2023 S5 Figs 23 and 21). Constructions used:

- **CCIP**: share(t, y) proportional to consumers with a GP card in tier t at YE2023 (Fig 3, held
  fixed) x mean monthly per-cardholder balance of tier t in year y (Fig 16). 2024 has Jan-Jul only
  (`mix_periods` says so). Fig 16 is all cards, so about a tenth of each tier's weight is private-label
  balance applied to a general-purpose rate.
- **CCP**: share(t, y) proportional to GP accounts in tier t at YE2022 (S5 Fig 17) x per-account GP
  balance at YE2022 (S3 Fig 7), which is the exact GP balance by tier at that date ($933B in total),
  moved to other years by the tier's mean quarterly per-cardholder balance in year y divided by its
  2022Q4 value (S3 Fig 5). The 2023 report's own Table 1 cardholder counts were not used because the
  2025 report (PDF p19 fn 37) says they overstate low-score cardholders.

Cross-check of the CCIP construction against the utilization x line route the coordinator suggested
(2023, all from the 2025 workbook):

| Tier | GP consumers YE2023 (M, Fig 3) | Per-cardholder balance 2023 ($, Fig 16 mean) | Utilization 2023 (Fig 91) | Line per cardholder 2023 ($, Fig 89) | Share via balance (%) | Share via util x line (%) |
|---|---|---|---|---|---|---|
| Deep subprime | 21.3 | 4,768 | 0.970 | 5,696 | 10.7 | 10.0 |
| Subprime | 10.6 | 5,458 | 0.788 | 8,121 | 6.1 | 5.8 |
| Near-prime | 14.0 | 7,034 | 0.668 | 12,524 | 10.3 | 10.0 |
| Prime | 29.1 | 8,112 | 0.489 | 22,068 | 24.8 | 26.8 |
| Prime plus | 69.3 | 4,823 | 0.205 | 29,335 | 35.1 | 35.5 |
| Superprime | 50.5 | 2,436 | 0.066 | 41,654 | 12.9 | 11.9 |

Within two points per tier; the balance route is the more direct measurement and is the one used.

The CCP anchor (YE2022, 2023 workbook):

| Tier | GP accounts (M, S5 Fig 17) | Per-account GP balance ($, S3 Fig 7) | GP balances ($B) | Share (%) | Per-cardholder balance 2022Q4 ($, S3 Fig 5) |
|---|---|---|---|---|---|
| Deep subprime | 26.8 | 1,369 | 36.7 | 3.9 | 3,331 |
| Subprime | 26.4 | 1,544 | 40.8 | 4.4 | 4,476 |
| Near-prime | 46.9 | 1,961 | 92.0 | 9.9 | 6,698 |
| Prime | 100.6 | 2,588 | 260.4 | 27.9 | 9,135 |
| Prime plus | 196.6 | 1,921 | 377.7 | 40.5 | 5,536 |
| Superprime | 147.1 | 855 | 125.8 | 13.5 | 2,678 |

**The two panels disagree on deep subprime**: about 4% of balances in CCP (2022) against about 11%
in CCIP (2023). The CCIP panel has more deep-subprime cardholders (21.3M with a GP card at YE2023
against 9.2M in the 2023 report's Table 1 for YE2021) and they carry larger balances ($4,768 against
$3,331), consistent with the CCP-to-CCIP jumps the scout note found in deep-subprime utilization. The
score is also different (FICO in CCIP; "commercially available" in CCP). This is a reason the two
series stay separate, not something to average.

### 4.3 Limits of the level

- Tiers are by *current* score (2025 report p15), so a tier's balance is a moving population; the
  same endogeneity that stops the CFPB publishing loss by tier makes the tier mix here a mix of
  current, not origination, scores. Prospectus FICO is also a refreshed score, so the bases match.
- Counts by tier are held at one year-end per panel; only the per-cardholder balances move across
  years. A trend in the cardholder mix (the 2025 report notes below-prime cardholding at its highest
  since 2014) is not in the shares.
- The rate is gross and balance-weighted on the bureau panel; trust rates that are net, or on
  principal receivables, or on average rather than beginning balance, need their own basis note (A1).
- CCIP 2024 shares use January-July balances.

### 4.4 The tables

Aggregate rate (percent; annual mean and year-end) and constructed balance shares (percent):

| Series | Year | Rate | YE | Deep subprime | Subprime | Near-prime | Prime | Prime plus | Superprime | Mix periods |
|---|---|---|---|---|---|---|---|---|---|---|
| ccip | 2014 | 2.74 | 2.56 | 9.9 | 5.1 | 8.5 | 23.8 | 39.5 | 13.2 | 12 months Jan-Dec 2014 |
| ccip | 2015 | 2.50 | 2.32 | 9.5 | 5.1 | 8.8 | 23.8 | 39.4 | 13.4 | 12 months Jan-Dec 2015 |
| ccip | 2016 | 2.74 | 3.03 | 9.4 | 5.2 | 9.2 | 24.0 | 38.9 | 13.3 | 12 months Jan-Dec 2016 |
| ccip | 2017 | 3.33 | 3.59 | 9.4 | 5.3 | 9.4 | 24.3 | 38.2 | 13.4 | 12 months Jan-Dec 2017 |
| ccip | 2018 | 3.59 | 3.72 | 9.7 | 5.3 | 9.5 | 24.5 | 37.7 | 13.3 | 12 months Jan-Dec 2018 |
| ccip | 2019 | 3.67 | 3.10 | 10.1 | 5.5 | 9.6 | 24.7 | 36.9 | 13.2 | 12 months Jan-Dec 2019 |
| ccip | 2020 | 3.60 | 2.51 | 11.4 | 6.0 | 9.8 | 24.8 | 35.9 | 12.0 | 12 months Jan-Dec 2020 |
| ccip | 2021 | 2.61 | 2.02 | 11.8 | 6.0 | 9.4 | 23.9 | 35.8 | 13.1 | 12 months Jan-Dec 2021 |
| ccip | 2022 | 2.57 | 3.07 | 10.6 | 6.0 | 9.9 | 24.2 | 35.7 | 13.4 | 12 months Jan-Dec 2022 |
| ccip | 2023 | 3.93 | 4.75 | 10.7 | 6.1 | 10.3 | 24.8 | 35.1 | 12.9 | 12 months Jan-Dec 2023 |
| ccip | 2024 | 5.25 | 4.94 | 11.3 | 6.2 | 10.3 | 25.0 | 34.6 | 12.6 | 7 months Jan-Jul 2024 |
| ccp | 2013 | 4.35 | 4.00 | 3.2 | 3.6 | 8.1 | 27.4 | 44.5 | 13.1 | 4 quarters 2013Q1-2013Q4 |
| ccp | 2014 | 4.00 | 4.00 | 3.2 | 3.5 | 8.1 | 26.9 | 44.9 | 13.3 | 4 quarters 2014Q1-2014Q4 |
| ccp | 2015 | 3.95 | 3.80 | 3.2 | 3.6 | 8.4 | 26.7 | 44.7 | 13.4 | 4 quarters 2015Q1-2015Q4 |
| ccp | 2016 | 4.23 | 4.60 | 3.5 | 3.8 | 8.8 | 26.8 | 43.8 | 13.4 | 4 quarters 2016Q1-2016Q4 |
| ccp | 2017 | 5.12 | 5.20 | 3.6 | 4.0 | 9.1 | 27.1 | 42.9 | 13.4 | 4 quarters 2017Q1-2017Q4 |
| ccp | 2018 | 5.80 | 5.90 | 3.6 | 4.0 | 9.2 | 27.5 | 42.4 | 13.3 | 4 quarters 2018Q1-2018Q4 |
| ccp | 2019 | 6.53 | 6.30 | 3.7 | 4.1 | 9.4 | 27.9 | 41.8 | 13.0 | 4 quarters 2019Q1-2019Q4 |
| ccp | 2020 | 5.70 | 3.60 | 3.8 | 4.1 | 9.4 | 28.5 | 41.5 | 12.7 | 4 quarters 2020Q1-2020Q4 |
| ccp | 2021 | 3.75 | 2.90 | 3.5 | 3.8 | 9.0 | 27.8 | 42.1 | 13.8 | 4 quarters 2021Q1-2021Q4 |
| ccp | 2022 | 4.00 | 4.30 | 3.7 | 4.2 | 9.6 | 27.8 | 41.1 | 13.6 | 4 quarters 2022Q1-2022Q4 |

Calibrated level per shape, i.e. the prime-tier charge-off rate each shape implies (percent). The
CFPB column is the aggregate the calibration reproduces; `calibration_check()` verifies every cell to
1e-9 and `tests/test_shape.py` runs it.

| Series | Year | CFPB | fico_odds | fico_fed2007 | acms2018 | acms2018_dpd90 |
|---|---|---|---|---|---|---|
| ccip | 2014 | 2.74 | 2.36 | 2.11 | 3.27 | 3.39 |
| ccip | 2015 | 2.50 | 2.17 | 1.94 | 2.98 | 3.08 |
| ccip | 2016 | 2.74 | 2.37 | 2.12 | 3.26 | 3.37 |
| ccip | 2017 | 3.33 | 2.85 | 2.55 | 3.94 | 4.07 |
| ccip | 2018 | 3.59 | 3.03 | 2.71 | 4.23 | 4.37 |
| ccip | 2019 | 3.67 | 3.03 | 2.70 | 4.31 | 4.43 |
| ccip | 2020 | 3.60 | 2.78 | 2.46 | 4.16 | 4.25 |
| ccip | 2021 | 2.61 | 2.02 | 1.78 | 3.04 | 3.11 |
| ccip | 2022 | 2.57 | 2.06 | 1.82 | 3.00 | 3.08 |
| ccip | 2023 | 3.93 | 3.10 | 2.75 | 4.55 | 4.66 |
| ccip | 2024 | 5.25 | 4.03 | 3.56 | 6.05 | 6.18 |
| ccp | 2013 | 4.35 | 5.26 | 5.03 | 5.40 | 5.71 |
| ccp | 2014 | 4.00 | 4.88 | 4.68 | 4.98 | 5.27 |
| ccp | 2015 | 3.95 | 4.77 | 4.57 | 4.91 | 5.19 |
| ccp | 2016 | 4.23 | 4.96 | 4.73 | 5.22 | 5.50 |
| ccp | 2017 | 5.12 | 5.88 | 5.59 | 6.29 | 6.62 |
| ccp | 2018 | 5.80 | 6.59 | 6.26 | 7.10 | 7.46 |
| ccp | 2019 | 6.53 | 7.29 | 6.92 | 7.95 | 8.33 |
| ccp | 2020 | 5.70 | 6.31 | 5.99 | 6.92 | 7.25 |
| ccp | 2021 | 3.75 | 4.33 | 4.13 | 4.60 | 4.84 |
| ccp | 2022 | 4.00 | 4.46 | 4.24 | 4.87 | 5.11 |

Why the prime level sits below the aggregate under CCIP and above it under CCP: the CCIP mix carries
11% deep subprime, which the steep shapes price at five to six times prime, so prime must sit low for
the mix to average to the aggregate; the CCP mix carries 4%.

## 5. Using it

    from absrisk.shape import predict_chargeoff, tiers_from_buckets, calibration_check
    mix = tiers_from_buckets([(None, 599, 0.05), (600, 659, 0.10), (660, 719, 0.30), (720, None, 0.55)])
    predict_chargeoff(mix, 2023, "fico_odds")                 # CCIP basis by default
    predict_chargeoff(mix, 2019, "acms2018", series="ccp")
    calibration_check()                                       # DataFrame, raises if any year is off

`loss_shape.csv` is written by `absrisk.shape.write_loss_shape` from the constants in `shapes.py`
(the test suite checks the committed file equals a rebuild, so the mapping is executed code, not a
typed number). `ccmr_level.csv` is written by `absrisk.shape.build_level`; the rebuild test runs when
the workbooks are present.
