# Scout: loss-by-credit-tier in the CFPB Consumer Credit Card Market Reports (CCMR)

Scouted 2026-09-08. Sources: CCMR 2025, 2023, 2021 PDFs plus the CFPB's official
"figure data" workbooks for each report. Raw files under
`data/raw/scout/cfpb/` (inventory in section 9).

Source marks used throughout:

- **[W]** exact value from the CFPB figure-data workbook that accompanies the report
  (official download, see section 6). This is the same aggregated data the chart is
  drawn from, so it supersedes chart reading.
- **[T]** printed in the report body, a table, or a chart data label.
- **[C]** read off a rendered chart; approximate.

Page references give the PDF page index. For the 2025 and 2023 reports the printed
page number equals the PDF page. For the 2021 report the printed page is PDF page
minus 1 (verified on PDF pp. 30, 46, 80, which carry printed 29, 45, 79); both are
given as "PDF p46 / printed p45".

---

## 0. Bottom line

**The CCMR does not publish charge-off or delinquency by credit-score tier, in any of
the three editions.** The 2021 and 2023 reports say so explicitly and give the reason;
the 2025 report simply presents both series by card type only. Verbatim:

- 2023, PDF p45, footnote 88: "We rely on 60 plus day delinquency here, as in previous
  reports. **Because credit scores are heavily influenced by delinquency and
  charge-offs, these measures are not shown by credit score tiers.**" [T]
- 2021, PDF p42 / printed p41, footnote 75: "Because credit scores are heavily
  influenced by delinquency and charge-offs, these measures are not shown by credit
  score." [T]
- 2025: section 4.2 "Non-payment" (PDF pp78-80) contains Figure 52 (60+ day
  delinquency) and Figure 53 (charge-off), each split only into general purpose vs
  private label. No tier split anywhere in the report, its 137 figures, or its
  workbook (every figure header checked; grep of the workbook for
  delinquent/charged-off rows finds only the two card-type series). [W][T]

The CFPB's reasoning is that tiering by *current* score (which is what the CCMR
does, see section 2) is endogenous to the outcome: an account that goes 60+ days
delinquent gets re-scored into a lower tier, so a "deep subprime charge-off rate"
computed on current score would mostly measure the scoring model.

What the CCMR *does* give by tier, with exact numbers: utilization, average credit
line (per account and per cardholder), average balance, payment rate, share
revolving, share paying only the minimum, persistent-debt share, late-fee incidence,
approval rate, and (2025 only) balance and revolving behaviour by *origination*
score for new-account vintages. Those are all tabulated in section 4 and can serve as
tier-level inputs to a loss model, but none is a loss rate.

Aggregate (all-tier) charge-off and delinquency series are available as exact monthly
or quarterly data back to 2006 and are tabulated in section 3.

---

## 1. Files downloaded

All fetched with `curl -A "abs-risk/0.1 research (+https://github.com/User5017)"`;
no 403s were encountered, so no fallback was needed.

| File | Source URL | HTTP | Bytes | SHA-256 |
|---|---|---|---|---|
| `cfpb_consumer-credit-card-market-report_2025.pdf` (191 pp) | https://files.consumerfinance.gov/f/documents/cfpb_consumer-credit-card-market-report_2025.pdf | 200 | 2,038,409 | `b5b1d4b2…364949` |
| `cfpb_consumer-credit-card-market-report_2023.pdf` (175 pp) | https://files.consumerfinance.gov/f/documents/cfpb_consumer-credit-card-market-report_2023.pdf | 200 | 1,781,113 | `a0d2d36f…a34c13d2a064` |
| `cfpb_consumer-credit-card-market-report_2021.pdf` (178 pp) | https://files.consumerfinance.gov/f/documents/cfpb_consumer-credit-card-market-report_2021.pdf | 200 | 2,039,541 | `0e5a8b65…489f3ce` |
| `cfpb_consumer-credit-card-market-report-figure-data_2025.xlsm` | https://files.consumerfinance.gov/f/documents/cfpb_consumer-credit-card-market-report-figure-data_2025.xlsm | 200 | 248,573 | `b7ce8050…98d914c` |
| `cfpb_consumer-credit-card-market-report-figure-data_2023.xlsx` | https://files.consumerfinance.gov/f/documents/cfpb_consumer-credit-card-market-report-figure-data_2023.xlsx | 200 | 225,775 | `faf96ecc…35f3c8254` |
| `cfpb_consumer-credit-card-market-report-figure-data_2021.xlsx` | https://files.consumerfinance.gov/f/documents/cfpb_consumer-credit-card-market-report-figure-data_2021.xlsx | 200 | 117,767 | `1b84881b…a6a8264` |

Full hashes are in the shell log; re-run `sha256sum` in the directory to reproduce.

Landing pages (saved as HTML): 2025 at
`/data-research/research-reports/the-consumer-credit-card-market-2025/`; 2023 at
`/data-research/research-reports/the-consumer-credit-card-market/` (the guessed
`…-2023/` slug 404s); 2021 at
`/data-research/research-reports/consumer-credit-card-market-2022/` (the guessed
`…-2021/` slug 404s). A `…_2025-12.pdf` link on the credit-card data hub returns a
404 page and was discarded.

---

## 2. Tier definitions, score type, and tiering basis (verbatim)

### 2025 report (PDF p15, "Definitions") [T]

> "Credit score: for the purposes of the report, 'credit score' refers to credit
> scores from major national consumer reporting agencies alongside other data sources
> or proprietary scores, which lenders typically use to determine consumers' credit
> eligibility, credit line, and interest rate pricing. **For all Y-14+ and MMI
> analyses, we use credit score provided by credit card issuers. For all CCIP
> analyses, we use FICO® Scores provided by one of the three nationwide consumer
> reporting agencies.**"

> "Credit tier: when reporting results by credit score in this report, scores are
> generally grouped into six 'credit tiers': **'superprime' (800 or greater), 'prime
> plus' (720 to 799), 'prime' (660 to 719), 'near-prime' (620 to 659), 'subprime'
> (580 to 619), and 'deep subprime' (579 or less).** This six-tier division differs
> from the five-tier division used in some prior CFPB consumer credit card market
> reports. In our credit card reports up to 2021, superprime was defined to include
> scores of 720 or greater. As of the 2023 report, this tier is now defined to be
> comprised of two categories: superprime (a score of 800 or greater) and prime plus
> (a score of 720 to 799)."

> "**Unless noted otherwise, we present account and consumer credit tiers based on
> credit score at each point in time; therefore, the specific accounts or consumers
> present in each tier change over time**, partly in response to how cardholders use
> and manage their cards."

The exceptions "noted otherwise" are Figures 31-35 (PDF pp55-60), which are explicitly
"by origination credit score" (Y-14) and use four groups: Below-prime, Prime, Prime
plus, Superprime.

### 2023 report (PDF p12, section 1.3) [T]

> "When reporting results by credit scores in this report, scores are generally
> grouped into six tiers: superprime (800 or greater), prime plus (720 to 799), prime
> (660 to 719), near-prime (620 to 659), subprime (580 to 619), and deep subprime
> (579 or less). Previous reports only used five tiers as they did not break out the
> prime plus category. … Where historical data are used or in places with limited
> coverage of cardholders with scores below 620, fewer than six credit score tiers may
> be represented."

> "Data relied upon in this report include widely used, commercially available credit
> scores, but as issuers use different credit scores, a given account's 'credit score
> tier' may differ from bank to bank." Footnote 17: "It is also typical for lenders to
> supplement commercially-available scores with proprietary models."

The 2023 report does not name FICO or VantageScore for its CCP analyses; it says
"commercially available." Its footnote 73 (PDF p38) cites ficoscore.com in the payment
discussion, but that is not a data-source statement.

### 2021 report (PDF pp20-21 / printed pp19-20, Table 1) [T]

Five tiers: superprime (720 or greater), prime (660-719), near-prime (620-659),
subprime (580-619), deep subprime (579 or less). Same "commercially-available credit
scores" language; same caution that model changes complicate long comparisons.
"Credit scores in the CCP and Y-14 are refreshed regularly. Unless noted otherwise,
accounts and consumers are classified into score tiers based on their credit score
at that time." Table 1 (Q4 2019, CCP) shares of the *scored cardholding* population:
superprime 64%, prime 16%, near-prime 8%, subprime 6%, deep subprime 7%.

### Summary

| Item | 2021 | 2023 | 2025 |
|---|---|---|---|
| Tiers | 5 (superprime = 720+) | 6 (prime plus 720-799 split from superprime 800+) | 6, same cutoffs as 2023 |
| Score used, credit-bureau panel | "commercially-available" (CCP) | "commercially available" (CCP) | **FICO® Score** (CCIP) |
| Score used, issuer data (Y-14/MMI) | issuer-supplied | issuer-supplied | issuer-supplied |
| Tiering basis | current score at each point in time | current score at each point in time | current score, except Figs 31-35 by origination score |

---

## 3. Charge-off and delinquency: what exists (all-tier, by card type only)

### 3.1 Where the series live

| Report | Figure | PDF page | Measure | Frequency / span | Data source |
|---|---|---|---|---|---|
| 2025 | Fig 52 | p78 | Share of balances 60+ days delinquent (excludes charged-off balances, fn 127) | monthly, Jan 2014 - Dec 2024 | CCIP |
| 2025 | Fig 53 | p80 | Annualized rate of balances charged off; "gross amount charged off, not including recoveries" (fn 129) | monthly, Jan 2014 - Dec 2024 | CCIP |
| 2023 | §3 Fig 17 | p46 | Share of balances 60+ days delinquent | quarterly, 2013Q1 - 2022Q4 | CCP |
| 2023 | §3 Fig 18 | p47 | Annualized rate of gross outstanding balances charged off | quarterly, 2013Q1 - 2022Q4 | CCP |
| 2021 | §2 Fig 17 | p43 / printed 42 | Share of **accounts** 60+ days delinquent | quarterly, 2006Q1 - 2020Q4 | CCP |
| 2021 | §2 Fig 18 | p44 / printed 43 | Share of **balances** 60+ days delinquent | quarterly, 2006Q1 - 2020Q4 | CCP |
| 2021 | §2 Fig 19 | p46 / printed 45 | Annualized rate of gross outstanding balances charged off | quarterly, 2006Q1 - 2020Q4 | CCP |

All are gross (pre-recovery) charge-off rates on balances. No net charge-off series
is published; the reports mention net charge-offs only when quoting issuer earnings
calls (2021 PDF p45 fn 80). No 90+ day series; the CCMR uses 60+ throughout ("severe"
delinquency, 2021 fn 78).

### 3.2 Annualized gross charge-off rate, all tiers, by card type [W]

Year-end value (December for CCIP monthly; Q4 for CCP quarterly) and simple annual
average of the monthly/quarterly annualized rates.

| Year | GP, CCP (2021/2023 rpt) YE / avg | PL, CCP YE / avg | GP, CCIP (2025 rpt) YE / avg | PL, CCIP YE / avg |
|---|---|---|---|---|
| 2006 | 6.4 / 5.58 | 8.8 / 10.03 | | |
| 2007 | 6.5 / 6.00 | 10.8 / 9.98 | | |
| 2008 | 8.8 / 8.00 | 12.9 / 12.35 | | |
| 2009 | 14.1 / 12.97 | 15.9 / 16.12 | | |
| 2010 | 9.8 / 13.00 | 13.9 / 15.80 | | |
| 2011 | 6.3 / 7.85 | 11.8 / 12.17 | | |
| 2012 | 5.4 / 5.82 | 10.7 / 11.20 | | |
| 2013 | 4.0 / 4.35 | 9.3 / 10.45 | | |
| 2014 | 4.0 / 4.00 | 9.5 / 9.35 | 2.56 / 2.74 | 6.33 / 6.04 |
| 2015 | 3.8 / 3.95 | 10.1 / 9.70 | 2.32 / 2.50 | 6.07 / 5.97 |
| 2016 | 4.6 / 4.22 | 10.5 / 10.67 | 3.03 / 2.74 | 7.00 / 6.79 |
| 2017 | 5.2 / 5.12 | 9.2 / 10.53 | 3.59 / 3.33 | 7.01 / 7.43 |
| 2018 | 5.9 / 5.80 | 10.9 / 11.43 | 3.72 / 3.59 | 7.83 / 7.33 |
| 2019 | 6.3 / 6.53 | 8.4 / 10.88 | 3.10 / 3.67 | 5.28 / 7.12 |
| 2020 | 3.6 / 5.70 | 5.0 / 7.47 | 2.51 / 3.60 | 3.54 / 5.87 |
| 2021 | 2.9 / 3.75 | 4.5 / 5.75 | 2.02 / 2.61 | 3.07 / 4.07 |
| 2022 | 4.3 / 4.00 | 7.7 / 7.13 | 3.07 / 2.57 | 5.60 / 4.72 |
| 2023 | | | 4.75 / 3.93 | 8.92 / 7.32 |
| 2024 | | | 4.94 / 5.25 | 7.74 / 8.52 |

Percent. 2006-2012 from the 2021 workbook (§2 Fig 19); 2013-2022 CCP from the 2023
workbook (§3 Fig 18); the 2021 workbook's 2013-2020 values agree with the 2023
workbook to within 0.1-0.3 pp (e.g. 2019 GP Q4 6.0 vs 6.3). CCIP from the 2025
workbook (Fig 53). Cross-check: the December data labels printed on the 2025 Fig 53
chart (GP 2.6, 2.3, 3.0, 3.6, 3.7, 3.1, 2.5, 2.0, 3.1, 4.8, 4.9; PL 6.3, 6.1, 7.0,
7.0, 7.8, 5.3, 3.5, 3.1, 5.6, 8.9, 7.7) match the workbook year-end column exactly
[T]. Printed text checks: 2023 PDF p47 "General purpose charge-offs remained roughly
consistent at around six percent … until mid-2020, declined to less than three
percent by mid-2021, and then moderated to 4.3 percent by the fourth quarter of 2022.
Private label charge-offs fell throughout 2020 and 2021 to 4.5 percent. Since
mid-2021, private label charge-offs have risen to 7.7 percent" [T]; matches.

**Important: the CCP and CCIP series are not on the same basis.** For overlapping
years the CCIP charge-off rate runs roughly 40-45% below the CCP rate (2019 GP
annual average 3.67% vs 6.53%). The 2025 report, PDF p10 fn 13: "The CCIP data used
in this report differ from the consumer credit data used for previous reports. …
Since the 2023 Report, the CFPB has replaced the Consumer Credit Panel with a new
panel, the Consumer Credit Information Panel. As a result, some of the estimates
derived from the CCIP in this report may not be directly comparable to prior reports
because of changes in the data source and some of the data construction." The report
does not explain the construction difference for charge-off specifically. Do not
splice the two series without a level adjustment.

### 3.3 Share of balances 60+ days delinquent, all tiers, by card type [W]

| Year | GP, CCP YE / avg | PL, CCP YE / avg | GP, CCIP YE / avg | PL, CCIP YE / avg |
|---|---|---|---|---|
| 2006 | 3.2 / 2.92 | 3.5 / 3.60 | | |
| 2007 | 3.7 / 3.30 | 4.1 / 3.88 | | |
| 2008 | 4.7 / 4.10 | 5.2 / 4.67 | | |
| 2009 | 6.0 / 5.80 | 5.2 / 5.35 | | |
| 2010 | 4.2 / 4.85 | 4.1 / 4.45 | | |
| 2011 | 2.8 / 3.12 | 3.4 / 3.53 | | |
| 2012 | 2.3 / 2.38 | 3.2 / 3.15 | | |
| 2013 | 1.9 / 1.98 | 3.3 / 3.15 | | |
| 2014 | 1.8 / 1.78 | 3.1 / 3.05 | 1.81 / 1.80 | 2.88 / 2.86 |
| 2015 | 1.8 / 1.65 | 3.1 / 3.05 | 1.87 / 1.73 | 2.93 / 2.81 |
| 2016 | 2.0 / 1.80 | 3.6 / 3.38 | 2.04 / 1.84 | 3.25 / 3.00 |
| 2017 | 2.1 / 2.00 | 3.9 / 3.72 | 2.21 / 2.06 | 3.57 / 3.43 |
| 2018 | 2.3 / 2.12 | 4.1 / 4.03 | 2.28 / 2.13 | 3.80 / 3.71 |
| 2019 | 2.4 / 2.25 | 4.4 / 4.15 | 2.43 / 2.25 | 3.93 / 3.72 |
| 2020 | 1.8 / 1.93 | 3.1 / 3.55 | 1.85 / 2.02 | 2.69 / 3.14 |
| 2021 | 1.4 / 1.45 | 2.6 / 2.50 | 1.43 / 1.52 | 2.28 / 2.22 |
| 2022 | 2.1 / 1.75 | 3.6 / 3.08 | 2.07 / 1.68 | 3.49 / 2.82 |
| 2023 | | | 2.90 / 2.44 | 3.96 / 3.61 |
| 2024 | | | 2.96 / 2.96 | 3.79 / 3.87 |

Percent. Unlike charge-off, the CCP and CCIP delinquency series agree closely for
general purpose (within 0.1 pp) and differ modestly for private label (CCIP ~0.3-0.5
pp lower). Printed check: 2023 PDF p46 "As of the fourth quarter of 2022, 2.1 percent
of general purpose card balances and 3.6 percent of private label card balances were
60 or more days delinquent" [T]; matches.

**Typo in the 2025 report.** PDF p78 says "In 2024, delinquency rates were relatively
flat, decreasing from 4% to 3.8% for general purpose cards and increasing from 2.9% to
3.0% for private label cards." The workbook, the chart's own data labels, and the
2023 report all have those the other way round (GP 2.9 → 3.0%, PL 4.0 → 3.8%). Use the
workbook.

Share of **accounts** 60+ delinquent (2021 §2 Fig 17, CCP, Q4) [W]: GP 2013 1.1, 2014
1.1, 2015 1.2, 2016 1.3, 2017 1.4, 2018 1.5, 2019 1.6, 2020 1.0; PL 1.0, 1.1, 1.1, 1.3,
1.3, 1.3, 1.4, 1.0; peak 2009Q4 GP 2.5, PL 1.1. Account-based rates are roughly 40% of
balance-based rates for GP.

---

## 4. Tier-level series that do exist

All values [W] unless marked. Tier columns run from lowest to highest score. "GP" =
general purpose, "PL" = private label. Score basis is current score (section 2)
except 4.8.

### 4.1 Average utilization rate, general purpose, by tier (percent)

2025 Fig 91, PDF p131, CCIP, FICO score. Printed text: "consumers with deep subprime
scores consistently have utilization rates over 90 percent"; overall "23 percent … in
2023, up from 20 percent in 2020 and back to the level in 2019" [T]. Chart render
confirms the Overall labels (22, 22, 22, 22, 22, 23, 20, 20, 22, 23) and tier line
positions [C].

| Year | Deep subprime | Subprime | Near-prime | Prime | Prime plus | Superprime | Overall |
|---|---|---|---|---|---|---|---|
| 2014 | 94.9 | 74.1 | 60.9 | 45.9 | 21.3 | 5.9 | 21.9 |
| 2015 | 93.8 | 75.1 | 62.0 | 45.8 | 21.4 | 6.0 | 21.9 |
| 2016 | 94.1 | 75.8 | 62.9 | 46.0 | 21.0 | 6.1 | 22.1 |
| 2017 | 93.2 | 74.9 | 63.3 | 46.8 | 21.1 | 6.3 | 22.3 |
| 2018 | 95.0 | 76.1 | 63.7 | 46.5 | 20.9 | 6.4 | 22.5 |
| 2019 | 96.2 | 77.0 | 63.7 | 46.2 | 20.5 | 6.4 | 22.6 |
| 2020 | 97.7 | 77.8 | 62.6 | 44.5 | 18.9 | 5.8 | 20.5 |
| 2021 | 97.9 | 77.2 | 61.7 | 43.4 | 18.8 | 6.2 | 20.3 |
| 2022 | 96.4 | 77.4 | 64.1 | 45.9 | 19.9 | 6.5 | 21.7 |
| 2023 | 97.0 | 78.8 | 66.8 | 48.9 | 20.5 | 6.6 | 22.6 |

2023 §5 Fig 23, PDF p92, CCP:

| Year | Deep subprime | Subprime | Near-prime | Prime | Prime plus | Superprime | Overall |
|---|---|---|---|---|---|---|---|
| 2013 | 84.9 | 72.1 | 61.8 | 47.1 | 22.0 | 6.6 | 21.0 |
| 2014 | 85.3 | 72.2 | 61.7 | 46.9 | 22.5 | 6.7 | 21.3 |
| 2015 | 86.1 | 73.4 | 62.2 | 46.7 | 22.4 | 6.7 | 21.3 |
| 2016 | 87.8 | 74.4 | 63.3 | 46.8 | 22.0 | 6.8 | 21.5 |
| 2017 | 88.5 | 75.5 | 64.5 | 47.7 | 22.0 | 7.0 | 21.8 |
| 2018 | 88.7 | 75.4 | 64.4 | 47.3 | 21.7 | 7.0 | 21.7 |
| 2019 | 88.4 | 74.8 | 63.9 | 46.8 | 21.2 | 6.9 | 21.6 |
| 2020 | 86.5 | 73.5 | 62.2 | 45.0 | 19.6 | 6.2 | 19.3 |
| 2021 | 87.1 | 72.3 | 60.9 | 43.8 | 19.4 | 6.5 | 19.2 |
| 2022 | 90.0 | 75.0 | 63.9 | 46.3 | 20.4 | 6.8 | 20.7 |

Note the CCP → CCIP jump in deep subprime (≈88% → ≈95% for the same years); another
panel discontinuity.

2021 §4 Fig 17, PDF p80 / printed p79, CCP, five tiers (superprime = 720+):

| Year | Deep subprime | Subprime | Near-prime | Prime | Superprime (720+) |
|---|---|---|---|---|---|
| 2006 | 77.4 | 65.1 | 55.4 | 38.7 | 11.9 |
| 2007 | 80.2 | 65.3 | 55.4 | 38.6 | 11.5 |
| 2008 | 83.1 | 69.1 | 59.8 | 43.4 | 12.2 |
| 2009 | 85.4 | 71.6 | 62.1 | 47.2 | 13.5 |
| 2010 | 81.4 | 69.8 | 60.5 | 47.3 | 13.6 |
| 2011 | 83.8 | 70.6 | 60.7 | 47.0 | 13.7 |
| 2012 | 84.5 | 71.8 | 60.9 | 47.3 | 13.8 |
| 2013 | 84.4 | 71.7 | 61.5 | 46.8 | 13.6 |
| 2014 | 85.0 | 71.9 | 61.2 | 46.9 | 13.9 |
| 2015 | 86.9 | 73.3 | 62.0 | 46.5 | 13.8 |
| 2016 | 87.5 | 74.3 | 63.3 | 46.7 | 13.8 |
| 2017 | 88.7 | 75.2 | 64.4 | 47.5 | 14.0 |
| 2018 | 88.4 | 75.4 | 64.3 | 47.3 | 14.0 |
| 2019 | 88.2 | 75.1 | 63.9 | 46.6 | 13.9 |
| 2020 | 86.6 | 73.3 | 62.3 | 44.9 | 12.6 |

Related: share of below-prime cardholders with ≥90% utilization across all GP cards.
2025 Fig 92 (PDF p132, CCIP, monthly 2014-Jul 2024): below-prime overall 49% as of
July 2024, "its highest level since 2014" [T]; Jan 2014 deep subprime 59.2, subprime
35.5, near-prime 24.9, below-prime overall 39.9 [W]. 2023 §5 Fig 24 (PDF p93, CCP,
quarterly 2013-2022) and 2021 §4 Fig 18 (PDF p81 / printed p80) carry the same
series; full rows are in the workbook dumps.

### 4.2 Average credit line per account, year-end (dollars)

| Tier | 2025 Fig 90, p130, CCIP, YE2024 GP | PL | 2023 §5 Fig 22, p91, CCP, EOY2022 GP | PL |
|---|---|---|---|---|
| Deep subprime | 2,165 | 1,064 | 1,521 | 998 |
| Subprime | 2,571 | 1,297 | 2,059 | 1,225 |
| Near-prime | 3,309 | 1,676 | 3,067 | 1,617 |
| Prime | 5,795 | 2,692 | 5,587 | 2,486 |
| Prime plus | 9,876 | 3,775 | 9,428 | 3,366 |
| Superprime | 13,198 | 4,180 | 12,529 | 3,714 |
| Overall | 8,358 | 3,067 | 8,260 | 2,867 |

2025 printed check: superprime GP line "about $11,000 higher than for consumers with
deep subprime" (13,198 − 2,165 = 11,033) [T].

### 4.3 Average credit line per cardholder (dollars, all cards)

2025 Fig 89, PDF p130, CCIP:

| Year | Deep subprime | Subprime | Near-prime | Prime | Prime plus | Superprime | Overall |
|---|---|---|---|---|---|---|---|
| 2014 | 4,092 | 5,961 | 9,376 | 17,884 | 25,571 | 36,798 | 21,585 |
| 2015 | 4,086 | 6,111 | 9,687 | 18,276 | 25,843 | 37,235 | 21,982 |
| 2016 | 4,272 | 6,467 | 10,384 | 18,877 | 26,284 | 37,661 | 22,518 |
| 2017 | 4,416 | 6,571 | 10,523 | 19,329 | 26,743 | 38,011 | 22,981 |
| 2018 | 4,630 | 6,794 | 10,930 | 20,031 | 27,204 | 38,156 | 23,385 |
| 2019 | 4,868 | 7,241 | 11,453 | 20,863 | 27,876 | 38,408 | 23,931 |
| 2020 | 4,792 | 6,552 | 10,073 | 18,892 | 26,242 | 37,656 | 23,248 |
| 2021 | 4,600 | 6,631 | 10,282 | 19,167 | 26,796 | 38,557 | 23,835 |
| 2022 | 4,900 | 7,619 | 11,858 | 21,091 | 28,216 | 40,051 | 25,086 |
| 2023 | 5,696 | 8,121 | 12,524 | 22,068 | 29,335 | 41,654 | 26,218 |

2023 §5 Fig 21, PDF p91, CCP:

| Year | Deep subprime | Subprime | Near-prime | Prime | Prime plus | Superprime | Overall |
|---|---|---|---|---|---|---|---|
| 2013 | 2,952 | 4,795 | 8,474 | 17,671 | 25,492 | 36,610 | 22,135 |
| 2014 | 3,055 | 4,920 | 8,812 | 17,908 | 25,669 | 37,025 | 22,435 |
| 2015 | 3,166 | 5,164 | 9,237 | 18,329 | 26,032 | 37,512 | 22,754 |
| 2016 | 3,414 | 5,624 | 9,907 | 18,954 | 26,632 | 38,419 | 23,461 |
| 2017 | 3,624 | 5,737 | 10,124 | 19,513 | 27,266 | 39,037 | 24,116 |
| 2018 | 3,739 | 5,971 | 10,692 | 20,509 | 27,931 | 39,544 | 24,772 |
| 2019 | 3,919 | 6,342 | 11,202 | 21,295 | 28,634 | 39,807 | 25,342 |
| 2020 | 3,387 | 5,263 | 9,563 | 19,160 | 26,824 | 38,751 | 24,462 |
| 2021 | 3,084 | 5,232 | 9,735 | 19,330 | 27,271 | 39,420 | 24,782 |
| 2022 | 3,949 | 6,482 | 11,369 | 21,178 | 28,549 | 40,694 | 26,069 |

2021 §4 Fig 16, PDF p79 / printed p78, CCP, general purpose only, five tiers, 2006-2020
(selected years): 2006 DS 3,528 / SP 5,744 / NP 10,226 / P 21,159 / SPR 29,287 /
overall 22,805; 2019 3,610 / 5,629 / 9,605 / 18,966 / 30,264 / 23,548; 2020 3,100 /
4,549 / 8,131 / 16,528 / 28,764 / 22,358. Full series in the workbook dump.

### 4.4 Average per-account cycle-ending balance, year-end (dollars)

| Tier | 2025 Fig 18, p37, CCIP, YE2024 GP | PL | 2023 §3 Fig 7, p35, CCP, EOY2022 GP | PL |
|---|---|---|---|---|
| Deep subprime | 2,112 | 699 | 1,369 | 599 |
| Subprime | 2,057 | 629 | 1,544 | 548 |
| Near-prime | 2,230 | 652 | 1,961 | 607 |
| Prime | 2,885 | 732 | 2,588 | 648 |
| Prime plus | 2,044 | 457 | 1,921 | 391 |
| Superprime | 874 | 177 | 855 | 156 |
| Overall | 1,899 | 488 | 1,727 | 440 |

Printed checks: 2025 p37 "lowest for those with superprime scores at $874 per general
purpose card account" [T]; 2023 p35 "$855" [T].

2021 §2 Fig 4, PDF p30 / printed p29, CCP, average per-**cardholder** GP balance,
five tiers, Q4 values: 2018 DS 3,239 / SP 4,312 / NP 6,376 / P 9,418 / SPR 4,982 /
overall 5,701; 2019 3,389 / 4,589 / 6,700 / 9,730 / 5,030 / 5,814; 2020 2,883 /
3,659 / 5,595 / 8,273 / 4,397 / 5,033. Quarterly 2006Q1-2020Q4 in the workbook.

### 4.5 Payment behaviour by tier (Y-14+, issuer-supplied score)

| Metric (GP unless noted) | Deep subprime | Subprime | Near-prime | Prime | Prime plus | Superprime | Overall | Source |
|---|---|---|---|---|---|---|---|---|
| Payment rate 2024 (payments / balances), GP | 8.1% | 10.9% | 12.0% | 15.3% | 39.5% | 102.8% | | 2025 Fig 43, p69 |
| Share of active accounts revolving 2024, GP | 88.1% | 83.4% | 81.7% | 72.2% | 41.9% | 19.6% | 48.8% (Fig 47) | 2025 Fig 50, p76 |
| Share of active accounts revolving 2022, GP | 85.6% | 80.3% | 78.0% | 68.8% | 40.9% | 19.5% | 47.0% | 2023 §3 Fig 16, p44 |
| Share of accounts paying only the minimum 2024, GP | 25.8% | 30.9% | 29.4% | 22.7% | 10.4% | 5.5% | 14.8% | 2025 Fig 45, p72 |
| Share of accounts paying only the minimum 2022, GP | 21.0% | 25.6% | 24.2% | 18.8% | 9.1% | 5.4% | 12.0% | 2023 §3 Fig 12, p40 |
| Share of accounts in persistent debt 2024, GP | 41.1% (subprime + deep subprime combined) | | 30.4% | 23.1% | 7.4% | 2.4% | 13.0% | 2025 Fig 51, p77 (Y-14) |
| Share of accounts in persistent debt 2022, GP | 31.7% (combined) | | 22.1% | 17.2% | 6.0% | 2.3% | 9.9% | 2023 §4 Fig 22, p72 (Y-14) |

Persistent-debt series are annual 2015-2024 in the 2025 workbook (e.g. 2019: 37.3 /
27.2 / 20.0 / 6.6 / 2.0 / overall 11.9).

2023 PDF p39 is the only sentence in any of the three reports that pairs a tier with
delinquency: "Cardholders with deep subprime credit scores have higher rates of
delinquency and at times may pay nothing at all." No number attached [T].

### 4.6 Late-fee incidence by tier (average number of late fees per account per year)

Closest published proxy for tier-level 30-day delinquency (a late fee is assessed on a
missed minimum payment).

| Tier | 2025 Fig 40, p65, 2024 GP | PL | 2023 §4 Fig 16, p66, 2022 GP | PL | 2021 §3 Fig 10, p58 / printed 57, 2019 GP | 2020 GP |
|---|---|---|---|---|---|---|
| Deep subprime | 3.69 | 4.74 | 3.7 | 5.1 | 3.5 | 3.0 |
| Subprime | 2.57 | 2.70 | 2.3 | 2.8 | 2.2 | 1.8 |
| Near-prime | 1.68 | 1.86 | 1.5 | 1.9 | 1.4 | 1.2 |
| Prime | 0.94 | 1.31 | 0.8 | 1.4 | 0.9 | 0.8 |
| Prime plus | 0.42 | 0.73 | 0.4 | 0.8 | (in superprime) | |
| Superprime | 0.19 | 0.32 | 0.2 | 0.3 | 0.3 | 0.3 |
| Overall | 0.88 | 1.32 | 0.8 | 1.3 | 0.8 | 0.7 |

### 4.7 Approval rate by tier (MMI)

2025 Fig 77, PDF p114 (2024) and 2023 §5 Fig 8, PDF p81 (2022) give approval rates by
tier for GP and PL; 2025 printed labels top out at 93% for superprime [T]. Rows are in
the workbook dumps (Section 6 / Section 5 sheets). Not extracted here.

### 4.8 By origination score (2025 only, Y-14, accounts opened 2015-2021)

The only CCMR figures tiered on score *at origination*. Four groups: Below-prime
(<660), Prime, Prime plus, Superprime.

- Fig 33 (PDF p58): average balance by month since origination, Panel A with intro
  APR promotion, Panel B without. Month-3 balances, Panel A: below-prime 912, prime
  1,845, prime plus 2,487, superprime 2,146; Panel B: 402, 677, 554, 462 [W]. Series
  run months 0-36.
- Fig 34 (PDF p59): share of accounts revolving in the month after promotion end vs
  non-promotional accounts: below-prime 66.9% vs 59.2%; prime 57.0 vs 46.4; prime
  plus 36.6 vs 25.2; superprime 20.0 vs 13.7 [W].
- Fig 35 (PDF p60): average interest charged in first three years: below-prime $346
  (no promo) / $512 (promo); prime $451 / $662; prime plus $220 / $402; superprime
  $60 / $127 [W][T].

Also Fig 59 (PDF p91, MMI, 2024): average FICO score of accounts entering settlement,
by cycles past due. Direct settlements: 0 cycles 625, 1 cycle 616, 2 cycles 582, 3
cycles 551, 4 cycles 535, 5 cycles 530, 6 cycles 531; via debt-settlement companies
459, 461, 432, 427, 421, 418, 420 [W][T]. This is the report's only score-by-
delinquency-stage cross-tab, and it runs the opposite direction (score given stage,
not loss given score).

---

## 5. Nearest CFPB substitutes for a loss-by-score curve

- **CFPB Office of Research blog, 6 Aug 2024**, "Credit card delinquencies are higher
  than in 2019 because lenders took on more risk" (Fulford & Gibbs; cited in the 2025
  report fn 126, PDF p78). Saved as `blog_delinq_2024.html` (now marked "archived
  content"). Uses the CCIP. Figure 2 gives 90+ day delinquency by origination
  *vintage* (2016-2023) by months since origination; Figure 4 re-weights vintages by
  5-percentile origination-score-rank bins. It does not publish delinquency by score
  tier; the score-bin weights are not released. Charts are PNGs only, no data file.
- **Consumer Credit Trends: Credit cards, "Borrower risk profiles"**
  (`/data-research/consumer-credit-trends/credit-cards/borrower-risk-profiles/`):
  origination volumes by score tier, CCP/CCIP-based, downloadable CSV on the
  sub-pages. Originations only; no performance.

Neither gives a charge-off or delinquency rate by tier. If the project needs one, the
candidate sources are outside the CFPB: Fed FR Y-14M is confidential; the NY Fed
Consumer Credit Panel publishes delinquency transition rates by score bucket in its
Quarterly Report on Household Debt and Credit (referenced by the 2023 report, PDF p46
fn 90); issuer 10-Ks and ABS trust reports give losses by FICO band for their own
books.

---

## 6. Machine-readable data availability

**Figure data behind the CCMR: yes, official, complete for the published figures.**
The 2025 report (PDF p13): "In publishing this report, the Bureau shares the
aggregated data underlying tables and figures, which are available for download. Code
and notes from the analysis would reveal confidential data and are thus withheld."
Workbooks:

- 2025: `cfpb_consumer-credit-card-market-report-figure-data_2025.xlsm` (linked from
  the 2025 landing page and the credit-card data hub). 9 sheets: Information (blank),
  Index (figure number → title → source), one sheet per report section, Appendix A.
  Figures 1-137 all present.
- 2023: `…figure-data_2023.xlsx` (linked from the 2023 landing page). 7 sheets, one
  per section; figure numbering restarts within each section as in the PDF.
- 2021: `…figure-data_2021.xlsx` (linked from the 2021 landing page, via
  `/documents/10205/…`). 8 sheets. Index note: "For figures shown in red, underlying
  data are not published here. Please contact the providers of the data sources
  associated with those figures directly" (applies to third-party-sourced figures
  such as Competiscan mail volume).

Dumped to `figdata_{year}_dump.txt` (tab-separated, `r<row>` prefix = workbook row)
for grepping.

**Underlying panels: no.** Y-14M is Federal Reserve confidential supervisory data; the
2025 report (PDF p13): "The internal data are confidential and cannot be shared with
the public." CCIP/CCP are de-identified bureau samples held by the CFPB and not
released. MMI and Specialized Issuer data are firm-level aggregates under 1022(c)(4)
orders, not released.

**Other CFPB credit-card datasets (hub `/data-research/credit-card-data/`,
`cc_data_hub.html`, and the Public Data Inventory, `public_data_inventory.html`):**

- Credit Card Agreement Database: quarterly submissions of agreement PDFs from issuers
  with 10,000+ accounts, 2011Q3-2014Q4 and 2016Q1-present. Documents, not a data table.
- Terms of Credit Card Plans (TCCP) survey: semi-annual, 150+ issuers, machine-
  readable CSV (the credit-dashboard repo already ingests this). Pricing terms only,
  no performance.
- College credit card agreements: annual, documents.
- Consumer Credit Trends dashboards: CSV downloads, originations/inquiries by score
  tier, age, income. No delinquency.

No CFPB dataset offers Y-14-derived account performance in machine-readable form.

---

## 7. Final tables

### Table A. Annualized gross charge-off rate by year × tier (percent)

Tier columns: **n/a for every year and every report** because the CFPB does not
publish charge-off by score tier (2021 fn 75, 2023 fn 88; 2025 has no tier split).
"All" columns are the best available all-tier values from section 3.2, annual average
of the quarterly/monthly annualized gross rate, [W].

| Year | Deep subprime | Subprime | Near-prime | Prime | Prime plus | Superprime | All GP, CCP | All GP, CCIP | All PL, CCP | All PL, CCIP |
|---|---|---|---|---|---|---|---|---|---|---|
| 2013 | n/a | n/a | n/a | n/a | n/a | n/a | 4.35 | | 10.45 | |
| 2014 | n/a | n/a | n/a | n/a | n/a | n/a | 4.00 | 2.74 | 9.35 | 6.04 |
| 2015 | n/a | n/a | n/a | n/a | n/a | n/a | 3.95 | 2.50 | 9.70 | 5.97 |
| 2016 | n/a | n/a | n/a | n/a | n/a | n/a | 4.22 | 2.74 | 10.67 | 6.79 |
| 2017 | n/a | n/a | n/a | n/a | n/a | n/a | 5.12 | 3.33 | 10.53 | 7.43 |
| 2018 | n/a | n/a | n/a | n/a | n/a | n/a | 5.80 | 3.59 | 11.43 | 7.33 |
| 2019 | n/a | n/a | n/a | n/a | n/a | n/a | 6.53 | 3.67 | 10.88 | 7.12 |
| 2020 | n/a | n/a | n/a | n/a | n/a | n/a | 5.70 | 3.60 | 7.47 | 5.87 |
| 2021 | n/a | n/a | n/a | n/a | n/a | n/a | 3.75 | 2.61 | 5.75 | 4.07 |
| 2022 | n/a | n/a | n/a | n/a | n/a | n/a | 4.00 | 2.57 | 7.13 | 4.72 |
| 2023 | n/a | n/a | n/a | n/a | n/a | n/a | | 3.93 | | 7.32 |
| 2024 | n/a | n/a | n/a | n/a | n/a | n/a | | 5.25 | | 8.52 |

CCP columns: 2023 report §3 Fig 18 (PDF p47), 2006-2012 available from the 2021
report §2 Fig 19 (section 3.2). CCIP columns: 2025 report Fig 53 (PDF p80). Gross,
pre-recovery, balance-weighted; no net charge-off series exists in the CCMR.

### Table B. Share of balances 60+ days delinquent by year × tier (percent)

Same n/a reason. "All" columns are annual averages from section 3.3, [W].

| Year | Deep subprime | Subprime | Near-prime | Prime | Prime plus | Superprime | All GP, CCP | All GP, CCIP | All PL, CCP | All PL, CCIP |
|---|---|---|---|---|---|---|---|---|---|---|
| 2013 | n/a | n/a | n/a | n/a | n/a | n/a | 1.98 | | 3.15 | |
| 2014 | n/a | n/a | n/a | n/a | n/a | n/a | 1.78 | 1.80 | 3.05 | 2.86 |
| 2015 | n/a | n/a | n/a | n/a | n/a | n/a | 1.65 | 1.73 | 3.05 | 2.81 |
| 2016 | n/a | n/a | n/a | n/a | n/a | n/a | 1.80 | 1.84 | 3.38 | 3.00 |
| 2017 | n/a | n/a | n/a | n/a | n/a | n/a | 2.00 | 2.06 | 3.72 | 3.43 |
| 2018 | n/a | n/a | n/a | n/a | n/a | n/a | 2.12 | 2.13 | 4.03 | 3.71 |
| 2019 | n/a | n/a | n/a | n/a | n/a | n/a | 2.25 | 2.25 | 4.15 | 3.72 |
| 2020 | n/a | n/a | n/a | n/a | n/a | n/a | 1.93 | 2.02 | 3.55 | 3.14 |
| 2021 | n/a | n/a | n/a | n/a | n/a | n/a | 1.45 | 1.52 | 2.50 | 2.22 |
| 2022 | n/a | n/a | n/a | n/a | n/a | n/a | 1.75 | 1.68 | 3.08 | 2.82 |
| 2023 | n/a | n/a | n/a | n/a | n/a | n/a | | 2.44 | | 3.61 |
| 2024 | n/a | n/a | n/a | n/a | n/a | n/a | | 2.96 | | 3.87 |

60+ days, balance-weighted; CCIP series excludes charged-off balances (2025 fn 127).
No 90+ series in the CCMR. Account-weighted 60+ (2006-2020) in section 3.3.

### Table C. Tier definitions

| Tier | 2021 report (5 tiers) | 2023 and 2025 reports (6 tiers) |
|---|---|---|
| Superprime | 720 or greater | 800 or greater |
| Prime plus | (not used) | 720 to 799 |
| Prime | 660 to 719 | 660 to 719 |
| Near-prime | 620 to 659 | 620 to 659 |
| Subprime | 580 to 619 | 580 to 619 |
| Deep subprime | 579 or less | 579 or less |
| Score type, bureau panel | "commercially-available" (CCP) | 2023: "commercially available" (CCP); 2025: FICO® Score (CCIP) |
| Score type, issuer data | issuer-supplied (Y-14, MMI) | issuer-supplied (Y-14+, MMI) |
| Tiering basis | current score at each observation | current score at each observation; 2025 Figs 31-35 by origination score (4 groups) |
| Citations | 2021 PDF pp20-21 / printed 19-20 | 2023 PDF p12; 2025 PDF p15 |

---

## 8. Caveats

1. **No tier-level loss rates exist in the CCMR.** The n/a cells are a documented
   CFPB choice, not a gap in extraction. Anything by tier in this family would have to
   be built from a different source (section 5).
2. **CCP → CCIP break.** The 2025 report's series come from a new bureau panel and
   run far below the 2023 report's CCP charge-off series for the same years (about
   0.55-0.65× on general purpose). Delinquency agrees across panels; charge-off and
   deep-subprime utilization do not. Treat 2013-2022 (CCP) and 2014-2024 (CCIP) as two
   series.
3. **Gross, not net.** All CCMR charge-off rates exclude recoveries. For a net view the
   2025 report gives cumulative recovery by vintage (Fig 61, PDF p92: Q4 2022 vintage
   8.5% after one year, 13.5% after two [T]).
4. **Frequency.** 2025 monthly, 2023 and 2021 quarterly. The "annual average" here is
   an unweighted mean of the period annualized rates, not a balance-weighted annual
   charge-off ratio.
5. **Tier composition drifts.** Tiers are by current score, so a tier's utilization or
   balance series tracks a changing population; the 2025 report (p15) and 2021 report
   (p21 / printed 20, fn 38) both flag this.
6. **Score type differs by data source** within one report: FICO (CCIP) for bureau-
   panel figures, issuer-supplied scores for Y-14/MMI figures. Tier-level utilization,
   credit line and balance are CCIP/CCP; tier-level payment behaviour and late fees are
   Y-14+.
7. **Report typo** in 2025 PDF p78 delinquency sentence (GP and PL swapped); the
   workbook and chart labels are correct.
8. **2021 report typo** PDF p44 / printed 43: "Private label balance delinquency rates
   fell from a peak of 2.4 percent at end of year 2019 to just under 3 percent" is
   internally inconsistent; the workbook has PL 4.3% at 2019Q4 falling to 3.0% by
   2020Q4.
9. **Chart reading was not needed** for any number above; the two chart renders
   (2025 pp80, 131) were used only to confirm that the workbook matches the printed
   figures, which it does.

---

## 9. File inventory, `data/raw/scout/cfpb/`

Downloaded: three report PDFs, three figure-data workbooks, landing pages
(`landing_2025.html`, `landing_2023_the-consumer-credit-card-market.html`,
`landing_2021_consumer-credit-card-market-2022.html`), `reports_cc.html` (research-
reports listing filtered to credit cards), `cc_data_hub.html`, `public_data_inventory.html`,
`cct_credit_cards.html`, `blog_delinq_2024.html`.

Derived: `ccmr_{2021,2023,2025}_text.txt` (pdfplumber per-page text with
`===== PAGE n =====` markers), `figdata_{2021,2023,2025}_dump.txt` (workbook
dumps). Helper scripts kept for reproducibility: `extract_text.py`, `dump.py`,
`reduce.py` (year-end / annual-average reduction), `pgrep.py` (page-annotated grep),
`pages.py` (print a page range). Run with
`uv run --with pdfplumber --with openpyxl python <script>`.
