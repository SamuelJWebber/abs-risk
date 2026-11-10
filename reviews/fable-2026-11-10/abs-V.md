# abs-V: verification of abs-risk

Given: `findings/abs-A.md` (internal attack, 2 HIGH, 4 MEDIUM, 3 LOW) and `findings/abs-B.md` (outside comparison,
2 HIGH, 2 MEDIUM, 2 LOW). Snapshot `f45e9fe27bcba60b5a48bd3cfa18cf69827e4f10`, verified 2026-11-10.

How I worked. Every verdict below rests on my own code in
`C:\Users\samwe\code\.codex-temp\adversarial-2026-11-10\work\abs-V\` (`vNN_*.py` -> `out_vNN.txt`), not on the
reviewers' scripts: my own survival clock and Aalen-Johansen life table (`vlib.py`, no `absrisk` import, no reuse of
abs-A's `mylib.py`), my own streaming reader for the raw EX-102 files, my own table extractor for the cached
prospectuses and 10-D exhibits. Raw filings were read from `C:\Users\samwe\code\abs-risk\data\raw\scout` with
`python -I -X utf8`. sec.gov was not contacted. GitHub `main` is still `f45e9fe` and the four live pages are
byte-identical to the snapshot's `docs/` (curl, 2026-11-10), so nothing below was fixed after the snapshot.
Re-run any script as: `cd work\abs-V; $env:PYTHONUTF8=1; ..\..\src\abs-risk\.venv\Scripts\python.exe v03_headline.py`.

## Verdict table

| Finding | Their severity | Verdict | Your severity | Corrected one-line statement |
|---|---|---|---|---|
| abs-A-1 Santander buy-backs | HIGH | UPHELD | HIGH (narrow) | Santander buys back loans that never or barely paid, at 120-150 days late, in their 4th to 6th month in the pool; the code counts them as harmless exits. Counting them as defaults raises Santander's 12-month cells by 28% to 49%, its 24-month deep-subprime figure from 15.1% to 16.8%, the "without Exeter" check from 9 to 13 times and the bucket range from 9-17 to 12-22. The headline median 16 does not move, and lender odds ratios move by about a tenth, not a third. |
| abs-A-2 card conversion above its ceiling | HIGH | UPHELD | HIGH | Same fact as abs-B-2. Over 93 months Chase charged off 1.21 times the dollars sitting in its 150-179 day bucket a month earlier, and Amex 1.4 to 1.5 times its oldest cohort, so at least 17% (Chase) and about 30% (Amex) of charge-offs never aged through late delinquency. A conversion ratio above 1 is not evidence about rescue. |
| abs-A-3 "16" is a knife edge | MEDIUM | WEAKENED | MEDIUM | The knife edge is real (13 with an 11-event floor, 8 with 10-point buckets, bootstrap centre 12.6 to 13.3, the published 15.6 at the 81st-90th percentile of its own bootstrap) but it cuts both ways (17 with 25-point buckets, 16.6 at 18 months under the page's own rule). "4.5 at two years" is one pair with CarMax underneath; the same bucket against Honda is 10.5. What does fall with loan age is the ratio for a fixed pair: 10-12 in year one, 5-7 in year two. |
| abs-A-4 "12-month" covers 2 to 7 months | MEDIUM | UPHELD | MEDIUM | Capital One is at risk only at ages 11-12, Toyota 9-12, Honda 6-12; unobserved ages count as zero hazard (`survival.py:119`). The cells are printed in the same column as Exeter's ages 3-12. Headline unaffected. |
| abs-A-5 scores not comparable | MEDIUM | UPHELD | MEDIUM | Every quoted passage is on disk and says what abs-A says. Size of the CarMax filter cannot be measured without the CarMax Select files. |
| abs-A-6 Honda/Toyota roll is not "close" | MEDIUM | UPHELD | MEDIUM | Honda's roll ratio is below 1 in all 10 of its buckets (0.54 to 0.92), Toyota's in 5 of 8. "Mostly entry" stands; "no sign after trouble" is true of CarMax only. |
| abs-B-1 Citi column is net | HIGH | UPHELD | HIGH | 63 of 63 comparable months (Jan 2020 to Mar 2025) equal the prospectus's monthly net-loss table to 0.01 point. Gross is 1.21 to 1.47 times net by year, so Citi's residual rank moves from 5 to between 2 and 4 and it no longer "converts least". |
| abs-B-2 conversion is not rescue; policies are stated | HIGH | UPHELD | HIGH | As abs-A-2. The four prospectus policy quotes are verbatim on disk; "which the filings do not state" is false. |
| abs-B-3 same score, different loan | MEDIUM | WEAKENED | MEDIUM | Curated shelves: confirmed in the prospectuses. But "9 without one score-selected pool" is a cell-size artefact (the 700 cell drops under 1,500 loans; allowed, the median is 14.1 and Exeter 2025-1 alone is 5.67% there), and "3 to 7 matched" is low: pooled over strata it is 6 to 10 in year one and about 4 in year two. |
| abs-B-4 loan size "settled" | MEDIUM | WEAKENED | LOW | Klee and Shin's figures are quoted correctly and agree in sign. Adams-Einav-Levin does not "run the other way": a bigger loan to the same buyer raises payment and loan-to-value, which the page also says raise default. What stands: the word "settled" and the sentence about "a bigger line", which no data here observes. |

Counts: 7 UPHELD, 3 WEAKENED, 0 REFUTED, 0 UNVERIFIABLE as whole findings. Parts I could not verify are listed
under each finding and at the end. LOW findings not re-checked except abs-B-5, which is right (the cached Exeter
prospectus names 2025-2, 2025-3, 2025-4 and 2025-5 and stars those four in its static pool tables).

## Per finding

### abs-A-1: UPHELD, HIGH (narrow)

- Claim: Santander repurchases loans at 120+ days late, the code treats a repurchase as a harmless exit, so
  Santander's published rates are 31-49% too low and comparisons against Santander are tilted.
- What would make it false: repurchase records that are current or lightly delinquent; a repurchase reason unrelated
  to credit; a code path that already counts them; or no visible number moving.
- What I did and saw:
  - Raw records (`v02_rawscan.py`, `v10_repo_profile.py`). SDART 2026-1 EX-102, July 2026 (0001193125-26-352879):
    207 records with `zeroBalanceCode` 3; 199 at `currentDelinquencyStatus` >= 120 and 204 at >= 90 (median 136
    days); none repossessed; charged-off amount zero on all; no `repurchaseAmount`, `repurchaserName` or reason
    code present, `assetSubjectDemandIndicator` false on all. 205 of 207 originated December 2025 or January 2026,
    the newest loans in the pool; 198 still owe at least 98% of the original amount; 31 never made the first payment
    and 162 are paid through no later than one month after the first due date. Balance goes to zero through
    `otherPrincipalAdjustmentAmount`. June 2026 (0001193125-26-303622): 297 records, 272 at >= 120 days, 294 at
    >= 90, 281 owing >= 98% of original. In the same files charge-offs sit at a median 129-135 days, so the
    buy-back replaces the charge-off at the charge-off point. Of loans that never made a payment, 0 (June) and 2
    (July) were charged off and 20 and 31 were repurchased: first-payment defaulters go to buy-back, not to loss.
  - It stops after the early months. SDART 2025-4, July 2026 (0001193125-26-352878, about nine months old): 2
    repurchases against 3,097 charge-off records. In the committed tables 1,277 of 1,295 late Santander repurchases
    leave in the loan's 4th, 5th or 6th monthly report, against 2,057 charge-offs in those months (`v11_repo_effects.py`).
  - Other lenders: share of repurchased loans that had reached 90 days late is 86% of 691 (sdart-2025-1), 92% of 763
    (sdart-2026-1), 7% of 360 (Exeter), 0 of 6 (AmeriCredit), 1 of 37 (Toyota). Santander only.
  - Why Santander does it: **UNVERIFIABLE from the deal documents.** No Santander prospectus or servicing agreement
    is cached (`data/deals.csv:2`: "424B5 ... not yet read"), and sec.gov is off limits. The records themselves are
    what an early-payment-default buy-back looks like, and trade press reports the sponsor is "obligated to buy back"
    loans whose borrowers miss the first few payments (Wolf Street, 2019-10-25, citing Bloomberg and Moody's; read
    2026-11-10 at wolfstreet.com/2019/10/25/subprime-auto-loans-blow-up-60-day-delinquencies-shoot-past-financial-crisis-peak/).
    So the reason is credit, not an unrelated covenant: these are the worst loans in the pool by behaviour.
  - Code path, read myself: `autos/build.py:45` maps code 3 to `repurchase`; `estimate/survival.py:26` puts
    `repurchase` in `COMPETING`; `_event` returns `prepay` for it; `hazard.py:4` pools it with prepay;
    `decompose.py` treats it as leaving without loss. All three estimators on the page count it as a benign exit.
  - One cell both ways, my code (`v03_headline.py`): Santander 660-679 at 12 months, 151 charge-offs, 5.39% as
    published; with repurchases of loans that had been 90+ days late counted, 197 events, 7.25%. All cells:
    480: 5.09 -> 6.98; 560: 5.26 -> 6.89; 660: 5.39 -> 7.25; 680: 4.67 -> 6.67; 700: 3.30 -> 4.91; 720: 3.08 -> 4.04;
    740: 5.29 -> 6.95. That is +28% to +49% (the published figures are 22% to 33% below the corrected ones).
    Deep subprime at 24 months: 15.13% -> 16.77%; Exeter 21.76 -> 21.79; AmeriCredit unchanged.
  - Numbers a reader sees that move: every Santander row in section 2; "santander 15.1%"; "the bucket ratios run
    from 9 to 17" (becomes 11.6 to 22.4); "exeter is the highest lender in the 660, 680 and 700 buckets" (Santander
    becomes the highest at 660 and 680); "without Exeter ... the median is 9 times ... outside the interval above ...
    so part of the gap is a comparison across score scales" (becomes 13.4, inside the 10-19 interval, so that
    sentence loses its support, and the 850-scale check with it); Exeter's roll "exception" shrinks (my crude
    per-bucket version 1.55 -> 1.37; abs-A's with the page's definition 1.42 -> 1.27).
  - Numbers that do not move: the headline median (15.55 both ways) and "1.7 times" in deep subprime (Exeter over
    AmeriCredit, neither affected).
- Corrections to the reviewer: "Santander is the baseline for every lender odds ratio" is true but the tilt is
  small. Santander's events rise 11.0% overall (1,295 on 11,751), so honda 0.15 becomes about 0.14 inside an
  interval of 0.04 to 0.61. The hazard model was not refitted by either of us. Their count of 1,087 late
  repurchases is 1,295 on my read of the same tables (592 + 703); the cell figures agree to the second decimal.
- The fix they propose is right for a page that says it describes "who defaults where": add a default event for a
  repurchase at 90+ days late, keep the trust-loss definition beside it, and say in one sentence what Santander's
  buy-backs are. It makes the lender gap wider, not narrower.

### abs-A-2 and abs-B-2: UPHELD, HIGH (one finding, two routes)

- Claim: the card "conversion" measure cannot be the rate at which 90-day-late balances become losses, so "Amex
  converts at 1.39 times Synchrony, the opposite of protection" and "selection, on every level comparison" do not
  follow; and the charge-off policies the page says are unstated are in the prospectuses.
- What would make it false: charge-offs that fit inside the delinquency bucket about to reach the charge-off age; a
  ceiling argument that only holds in a steady state the data are not in; prospectuses silent on policy.
- Are the two the same fact: yes. abs-A's "above one third in 94 months" and abs-B's "Chase charged off $20.16M
  against $16.44M in its 150-179 day bucket" both say that more is charged off each month than contractual ageing
  can deliver. abs-B's is the direct form; abs-A's is its steady-state average.
- What I did and saw:
  - Raw exhibits, July 2026. Chase EX-99.2: "Gross Losses (3) 20,157,969.63"; "150-179 days 1,843 16,436,974.16";
    3,503 accounts charged off in the month. Amex EX-99.01: "Defaulted Amount 39,467,785.90"; "91-120 Days
    Delinquent 32,094,421"; "120+ Days Delinquent 45,924,272"; 6,816 accounts with a loss against 4,844 accounts in
    the whole 120+ bucket. Both reviewers quoted these correctly.
  - My own page column (`v07_conversion.py`): conversion Amex 44.5%, Chase 38.7%, BofA 34.8%, Synchrony 32.1%, COMET
    31.1%, Citi 27.2%; above one third in 98%, 95%, 61%, 33%, 22% and 1% of months. Matches the page and abs-A.
  - Is the ceiling sound: I tested it without the steady-state assumption (`v08_oldest_bucket.py`), every month,
    dollars charged off in month t over dollars in the last pre-charge-off bucket at the end of month t-1, from the
    dollar inputs the parser stored. Sum over 93 months: Chase 1.21 (above 1 in 99% of months), Synchrony 1.05,
    BofA 1.03, COMET 0.99, Citi 0.88 on a net basis (about 1.1 gross). Amex prints 120+ as one bucket holding two
    monthly cohorts: charge-offs are 0.69 of the whole bucket, 1.39 of half of it. The oldest bucket is 29% to 32%
    of the 90+ stock at the five trusts that print it, so "one third" is, if anything, generous. The bucket counts
    finance charges and fees and the charge-off is principal only, so these are lower bounds. The argument is sound.
    Lower bounds on the share of charge-offs that did not come through the last bucket: Chase 17%, Amex about 28%
    (more if its older cohort is the smaller one, which its bucket profile says), Synchrony 5%, BofA 3%.
  - Reconciling the reviewers on the base mismatch: abs-A says it raises Amex's conversion about 5%, abs-B says it
    lowers it. Both are half right. Dividing a principal-based rate by a total-receivables share raises it by
    total/principal (26.17/24.93 = 1.05 at Amex); counting principal charged off against delinquent balances that
    include fees lowers it. Neither is near the size of 44.5 against 33.
  - Policies on disk, verbatim: Amex "approximately 180 days delinquent) or sooner if the death or bankruptcy of the
    account holder has been confirmed"; Citi "180 days delinquent or ... bankruptcy filings, which are charged off
    not later than 30 days after ... notice"; Chase earlier for "bankrupt cardholders, cardholders who are deceased
    ... or restructured loans that do not comply"; Synchrony earlier for "fraud, bankruptcy, deceased, and accounts
    enrolled in workout programs". `report/conclusions_page.py` prints "which the filings do not state".
- What exactly the page concludes from conversion (conclusions.html): the heading "The answer: selection, on every
  level comparison"; "Priority predicts the opposite sign on conversion"; "The conversion comparison rules out the
  simple priority story, because priority would show up as accounts rescued from deep delinquency and the opposite
  is observed"; "their late accounts are not rescued more often than anyone else's". index.html: "On every level
  comparison it is selection, in cards and in auto loans".
- Does it survive: no, for cards. "The opposite is observed" is not observed: the numerator holds charge-offs that
  never sat in the 90+ stock, most where contractual delinquency is lowest. The only direct evidence on what happens
  inside deep delinquency is the roll between buckets, and it points nowhere useful: balances leave Amex's pipeline
  before 180 days more often than anyone's (implied monthly roll about 0.83, against 0.88 to 0.98 at Chase, BofA,
  COMET and 0.85 to 0.95 at Citi and Synchrony), and the filings cannot say whether they left by being paid or by
  being charged off early. What survives: Amex's 30-plus share is 0.29 of Synchrony's, which the page itself says
  both stories predict; and the page's own caveat that policy can produce a high conversion. On cards the honest
  statement is "far fewer delinquent balances; public data cannot say whether late accounts are rescued more or less".
- Not established by anyone: each trust's bypass share month by month (no 10-D on disk splits bankruptcy from
  contractual charge-offs).

### abs-B-1: UPHELD, HIGH

- Claim: Citi's `gross_co_rate` is Citi's net loss rate, so Citi is compared net with five trusts gross.
- What would make it false: the monthly values differ from the prospectus net-loss table, or the 10-D component is
  defined gross, or the other five are also net.
- What I did and saw (`v05_citi.py`, `out_v05.txt`): parsed the "Net Losses by Year of Account Origination (by
  Monthly Due Period)" Total rows from `data/raw/scout/edgar/cards/citi/prospectus/0001193125-25-144490/d945716d424b2.htm`
  and joined them to `data/cards_monthly.csv`. 63 months, January 2020 to March 2025: 58 identical, 5 differ by
  0.01, none by more. The reviewer checked four. Same prospectus: "Portfolio Yield" is finance charge collections
  "after subtracting the amount of principal receivables that were charged off ... (net of recoveries)", and the
  10-D's Credit Loss Component is that subtraction (July 2026 exhibit: Portfolio Yield 21.51 = Yield Component 23.41
  minus Credit Loss Component 1.90). Loss-experience table: gross charge-offs 696,088 against net losses 575,931 in
  2024 (ratio 1.21), 1.27 in 2023, 1.47 in 2022, 1.25 in Q1 2025; the CSV's yearly means 1.25%, 1.91%, 2.55% are the
  net row. `cards/parse.py:518-521` calls it "inferred gross".
- The other five: checked from the stored row labels and two raw exhibits. Each prints a labelled gross and a
  labelled net row and the CSV carries both (Amex "Annualized Default Rate" 1.8640 and "Net of Recoveries" 1.1114;
  Chase "Gross Losses ... 2.02%" and "Net Losses ... 1.58%"; BofA, COMET, Synchrony the same pattern, recomputed
  from dollars in the stored checks). No second confusion. Citi's `net_co_rate` is empty in all 94 rows.
- Size, recomputed: mean residual shifts by mean net (2.15%) times (ratio minus 1): +0.45 points at 1.21, +0.62 at
  the pooled 1.29, +1.01 at 1.47. Citi's rank becomes 4, 4, 3, 3 at the low ratio, 3, 2, 2, 2 at the pooled one, 2
  everywhere at the high one. The reviewer's "2 or 3" is the middle case; the safe statement is "between 2 and 4,
  i.e. in the middle where rank depends on the curve". Conversion 27.2% becomes 33% to 35% at the 2023-25 ratios
  (1.02 to 1.09 of Synchrony's; higher still at the 2022 ratio), so
  "the trust whose 90-day-late balances convert least is citi" and the R2-4 "Citi exception" go. On a net basis for
  all six the means are Amex 1.20, Chase 1.69, COMET 2.01, BofA 2.13, Citi 2.15, Synchrony 4.02.
- Not verified: the gross/net ratio for 2018-2021 and after March 2025 (one Citi prospectus is cached).

### abs-A-3: WEAKENED, MEDIUM

- Claim: 16 is the top of its own range and a first-year number; 13, 8, 4.5 and 6-9 under other rules.
- What would make it false: the variants do not reproduce, or the alternatives are no more reasonable than the rule.
- What I did and saw (`v03_headline.py`, `v09_matched.py`, `v12_boot.py`; my own clock reproduces every published
  cell and the five ratios 9.0, 10.0, 15.6, 17.1, 16.3, median 15.55):
  - Minimum events 11: 12.75 over four buckets (CarMax's 720 cell has exactly 10 charge-offs). 19: 9.95.
  - Bucket width 10: 8.2. Width 25: 17.2. Width 30: 14.0. Width 40: 15.8.
  - Pool offset 0 and 6: 12.85 and 11.45. Without Exeter: 9.41. All as published.
  - Bootstrap, 400 resamples within lender: median 13.3 with cells and pairs fixed, 12.6 with the rule re-applied;
    81% and 90% of replicates fall below the published 15.55. The published interval reproduces (9.4 to 19.7).
  - Horizon, the part that is narrower than stated. The page's own rule at 18 months gives a median of 16.6 over six
    buckets, because Honda and Toyota then have 10 charge-offs and sit below CarMax. At 24 months Exeter is not
    observed at all above 660 and Santander only in the 660 bucket, where the rule gives 10.5 (Santander over
    Honda); 4.5 is Santander over CarMax in that one bucket. So "4.5 at two years" is a fixed-pair figure, not what
    the rule prints.
  - The fixed-pair decline is real. Pooled over score bucket and age (Mantel-Haenszel, scores 660-759): Exeter over
    CarMax 11.6 [9.3, 14.6] at ages 4-12 and 6.8 [5.9, 7.8] at ages 13-24; Santander over CarMax 10.0 [8.0, 12.7]
    and 5.3 [4.6, 6.2]. With loan-to-value, payment-to-income, term and new/used matched: 9.8 and 6.3 in year one,
    4.2 and 3.4 in year two. abs-A's 6 to 9 and "about 4" stand.
  - And the gap is not capped at 16: Santander over Honda at the same score is 19 [11, 33] in year one.
- Corrected statement: the single highest-over-lowest median depends on which low lender happens to have ten
  charge-offs; it moves between 8 and 17 on defensible rules and its own bootstrap centres on 13.

### abs-B-3: WEAKENED, MEDIUM

- Claim: same score, different loan, curated shelves; 9.4 without one score-selected Exeter pool; 3 to 7 matched.
- What would make it false: loans alike inside a bucket; no selection language in the prospectuses; a matched ratio
  near the headline; or the 9.4 arising from something other than that pool's selection.
- What I did and saw (`v03_headline.py`, `v09_matched.py`, `v04_grep_html.py` on the cached prospectuses):
  - Loans differ inside the bucket (my medians, scores 660-759): loan-to-value 1.24 Exeter, 1.15 Santander, 0.99
    CarMax, 1.04 Honda; term 77, 72, 67, 73 months; APR 19.8%, 14.7%, 9.6%, 4.9%. Confirmed.
  - Shelf curation, cached prospectuses: CarMax 2026-2 (0001193125-26-173162), "selected from CarMax Business
    Services' core portfolio ... with a FICO score at origination greater than or equal to 650", and CarMax Select
    takes "contracts outside the core portfolio, a substantial portion of which are obligations of lower credit
    obligors". Exeter 2026-2 (0000929638-26-001122) excludes obligors with a Credit Bureau Score "greater than or
    equal to 640" and a proprietary score "greater than or equal to 240", "Consistent with" 2025-2 to 2025-5.
    Confirmed.
  - "9.4 without exeter-2025-5": reproduces, but for a different reason than given. Removing that pool takes
    Exeter's 700-719 cell from 1,617 to 1,253 loans, under the 1,500 rule, so Santander (3.30%) replaces Exeter
    there. Exeter 2025-1 alone is 5.67% in that cell on 64 charge-offs, and with the cell admitted the median is
    14.1. It shows the knife edge, not that a score-selected pool makes the gap. (The 2025-5 pool does run hotter
    above 640: 9.4% against 5.2% at 660-679.)
  - "3 to 7 matched": my pooled figures are 6.3 [4.5, 8.7] (Santander) and 9.8 [6.7, 14.4] (Exeter) over CarMax in
    year one, 3.4 and 4.2 in year two. The reviewer's low end comes from single thin strata, and "about 5" is the
    hazard model's all-ages figure (1.10 / 0.23). abs-A's numbers are the better ones; the two reviewers agree once
    loan age is stated.
  - Static pool benchmark, read in the cached prospectuses: Exeter net loss at month 24 is 13.62% to 16.89% for
    2022-1 to 2024-1; CarMax 0.69% to 1.18% for the same vintages. Quoted correctly.

### abs-A-4: UPHELD, MEDIUM

- Claim: unobserved ages count as zero hazard, so "12-month" for three lenders is a few months of exposure.
- What I did and saw: `survival.py:119` `h_co = np.where(n > 0, d_co / n, 0.0)` (same in `lender_gap.py:195`).
  My at-risk counts by age 0..12, bucket 740 (`v09_matched.py`): capone `[0 x11, 703, 1498]`; toyota first at age 9
  (247); honda at age 6 (32) and 7 (415); exeter from 3, santander and carmax from 4. Identical to abs-A's read of
  `b1_cif.csv`. The page prints capone 740 as `aj_chargeoff_12` 0.00% in the same column as santander 5.29%, and
  explains the low captive figures as "fewer than 10 charge-offs each ... too few to divide by". The 10-event rule
  keeps these cells out of the headline at 12 months; they would enter at 18.
- Fix as proposed (blank a cell whose first observed age is past a stated age) is right.

### abs-A-5: UPHELD, MEDIUM

- Claim: "the same credit score" is a different thing at the two ends of the headline ratio (Exeter's reported
  score runs 20 points above FICO; CarMax averages co-borrowers), and both sponsors filter their public pools on
  their own risk models.
- What would make it false: the prospectuses do not say so, or the raw CarMax scores are not averages.
- Passages found on disk: Exeter 2026-2 prospectus, FICO table "Weighted Average FICO Score 562", "Less than 540
  31.66%"; Credit Bureau Score table "Weighted Average Score 582", "Less than 540 14.24%", with the footnote that it
  is VantageScore for 98.94% of the pool. CarMax 2026-2 prospectus: a co-obligor score "is calculated as the average
  of each obligor's FICO score". My scan of the July 2026 CarMax file: 15,670 co-obligor records, 6,755 with a
  fractional score, the reviewer's counts exactly; `autos/parse.py` `score_value` returns `int(x)`.
- Caveats: the Exeter prospectus on disk is for 2026-2, not the two Exeter deals in the data, so the 20-point gap is
  a shelf fact, not measured on those pools. The page does say Exeter's score is VantageScore and runs a "without
  Exeter" check, so the scale half is disclosed; the opposite-direction selection at the two ends is not.

### abs-A-6: UPHELD, MEDIUM

- Claim: Honda and Toyota borrowers who fall behind are 25% to 40% less likely to be charged off, and the pages
  call that "close to the baseline" and "no sign" of protection.
- What would make it false: roll ratios that scatter around 1 by bucket, so that 0.75 is noise.
- What I saw in `data/results/autos/b6_attribution_by_score.csv`: Honda's roll ratio by bucket, 620 to 800: 0.81,
  0.58, 0.65, 0.54, 0.68, 0.92, 0.75, 0.79, 0.76, 0.69; below 1 in all 10. Toyota 0.69 to 0.77 in 660-740 and above
  1 at 640, 760 and 780 (5 of 8 below 1). CarMax 0.84 to 1.09 in 640-740. The page prints 0.75 and 0.76 and calls
  them "close to the baseline lender's rate". With abs-A-1 applied the baseline's roll rises about 11% (my crude
  per-bucket version: Honda 0.81 -> 0.71, Toyota 0.99 -> 0.91, CarMax 0.98 -> 0.90), so the gap widens.
- Not done by me: the page's exact roll definition (charge-off within 12 months of first reaching 30 days) was not
  rebuilt; I read the committed per-bucket file and ran a cruder ever-30 version for direction only.

### abs-B-4: WEAKENED, LOW

- Klee and Shin (FEDS 2020-042), PDF read with my own text extraction: 5,930,935 loans, 89 securities, 15 issuers;
  one standard deviation of loan amount ($10,255) "decreases the odds ratio by 18.1 percent"; rate, term and
  payment-to-income raise it 64.2, 20.6 and 8.9 percent. Quoted correctly. Their window is charge-off in the first
  months after securitisation and they hold the interest rate fixed, not loan-to-value, so it is the same sign, not
  the same estimate.
- Adams, Einav and Levin: the NBER working paper page (w13067, read 2026-11-10) says default rates "rise
  significantly with loan size"; the Digest page with the per-$1,000 figure returned 404, so that number is
  UNVERIFIABLE today. It is one deep-subprime dealer-lender and a loan-size change for the same buyer, which raises
  payment and loan-to-value. The page's own coefficients say those raise default (2.47 and 4.24). No contradiction.
- What stands: "What else the data settled" over-claims a descriptive coefficient, and "a bigger line" carries an
  auto result to card limits that nothing here observes.

## Us against the outside work

| Question | Ours | Theirs (who) | Do definitions match | Who is more correct, and why |
|---|---|---|---|---|
| Is Citi's loss rate what we say it is | 2.15% mean, labelled gross | Citi's own prospectus: that series is net; gross 3.10% against net 2.57% in 2024 | Same trust, same months, 63 of 63 | Citi. Our label is wrong. |
| Do card charge-offs come through late delinquency | conversion read as the fate of 90-day-late accounts | The trusts' own 10-D buckets and prospectus policies: Chase charges off 1.21 times its oldest bucket; early charge-off on bankruptcy and death | Same filings | The filings. Our measure mixes aged and non-aged losses. |
| Do our deal totals match the issuer's | Exeter 2025-1 cumulative gross charge-off 1.63%, 3.89%, 6.41%, 7.25% of cutoff balance (my recompute) | Exeter static pool table: 1.64%, 3.90%, 6.44%, 7.28% | Yes, dollars over cutoff balance | Agreement. The loan parse is right. |
| How big is the shelf gap before holding score fixed | 10 to 12 times at the same score in year one | Issuer static pools: Exeter 13.6-16.9% against CarMax 0.69-1.18% net at month 24, 12 to 21 times | No: whole pool, net dollars, other vintages | Both right; together they say the score explains little of the gap between these two shelves. |
| Lender differences at subprime scores | 1.7 times across three finance companies' pools, charge-off by 24 months | CFPB Data Point 2021-10: banks about 15%, small finance nearly 40%, about 30% with controls; "controls explain some but not most" | No: lender types including banks, bureau panel, 60 days late within three years, scores 620 or less | Not comparable enough to call agreement. For a statement about lenders the CFPB panel is the better instrument (whole books); ours has loan terms it lacks. |
| Sign of loan amount | odds ratio 0.72, top against bottom quintile, at fixed burden and loan-to-value | Klee and Shin 2020: minus 18.1% per standard deviation | Same sign, different controls and window | Agreement on direction. Neither is causal. |

## Fix first

1. Relabel Citi's series as net and compare all six card trusts on the net rate (five already carry it), then
   rewrite the three sentences that name Citi.
2. Take "rules out", "selection, on every level comparison" and "which the filings do not state" off the cards,
   conclusions and landing pages, and say instead that low-loss trusts have far fewer delinquent balances and that
   public data cannot say whether their late accounts are rescued more or less often.
3. Count a repurchase of a loan that was 90 or more days late as a default beside the trust-loss figure, and replace
   the "median 16 times" sentence with: "At the same 20-point score, loans in Exeter's and Santander's public pools
   defaulted about 12 to 13 times as often as loans in CarMax's in their first year and 5 to 7 times as often in
   their second (8 to 10 and about 4 with loan-to-value, payment burden, term and new or used also matched)."
   On the page's current charge-off definition the same sentence reads 10 to 12, then 6 to 10.

## What the published work gets right

- The auto headline arithmetic: every published 12-month cell in 660-799, the five bucket ratios, the median 15.55,
  the pool-offset and without-Exeter variants and the 24-month deep-subprime band reproduce from my independent code.
- The loan parse: Exeter 2025-1 cumulative gross charge-off matches the issuer's static pool table to 0.03 points at
  four ages; CarMax 2025-1 is consistent with the issuer's net figure at the recorded recovery share.
- The qualitative result: at one score, loans in the subprime shelves default many times more often than loans in
  the prime shelves, and a gap of 6 to 10 times survives matching on loan structure. Fixing Santander widens it.
- The card monthly table for the five trusts other than Citi: gross and net are the rows the trusts label gross and
  net (July 2026 read in the Amex and Chase exhibits; all six rows carry recomputation checks from dollars).
- The page is candid about much of this already: it prints the without-Exeter 9, the offsets 13 and 11, the
  interval, says the lender coefficient is not causal, and reports its only causal design as a null.

## Could not verify

- Santander's prospectus or servicing agreement wording on repurchases: not cached, sec.gov off limits.
- The per-$1,000 figure from Adams, Einav and Levin (NBER Digest page 404).
- abs-B's rows marked "search excerpt only" (Santander 2025-1 trustee loss, Honda loss counts, AmeriCredit pool size).
- The hazard model's response to the Santander fix (16-minute refit not run) and the bypass share of card
  charge-offs by trust and month.
- LOW findings abs-A-7, abs-A-8, abs-A-9 and abs-B-6 were not re-checked.
