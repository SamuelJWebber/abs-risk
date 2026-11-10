# abs-A: abs-risk, internal attack

Snapshot `f45e9fe27bcba60b5a48bd3cfa18cf69827e4f10` (GitHub `main`, committed 2026-11-09 20:39 -0500), reviewed 2026-11-10.

What I ran. All scripts and their saved outputs are in `<review-scratch>/work\abs-A\`
(`sNN_*.py` -> `out_sNN.txt`). They read the committed `data/autos/*.parquet` and `data/cards_monthly.csv` with my own
clock and Aalen-Johansen code (`mylib.py`, no `absrisk` import). To re-run one:
`cd work\abs-A; $env:PYTHONUTF8=1; ..\..\src\abs-risk\.venv\Scripts\python.exe s02_gap.py`.
Raw filings: only the copies already cached under `<code>/abs-risk\data\raw\scout` (six EX-102 files, three
prospectuses, one Amex 10-D), read with `python -I`. Nothing was requested from sec.gov. Tests ran single-process in a
clone of the snapshot (`work\abs-A\clone`). Live pages fetched with curl from github.io.

## Verdict

- The auto headline reproduces exactly (15.55, printed as 16) and the qualitative result is right: at one score, subprime
  pools charge off several times more than prime pools. Sure of that.
- The number 16 is the top of its own range, and it is a first-year figure. The same rule gives 13 with an 11-event floor,
  8 with 10-point buckets; the bootstrap centre is 12 to 13; at 24 months the one measurable pair is 4.5 times; with
  loan-to-value, payment-to-income and term held fixed it is 6 to 9 in year one and about 4 in year two.
- One lender's published rates are wrong for the page's purpose: Santander buys back loans at 120+ days late, and the
  project counts those as harmless exits. Its headline cells are 31 to 49% too low. This widens the gap, it does not shrink it.
- The card and conclusions pages' central inference ("conversion is higher at Amex, so it is selection, not priority")
  does not hold: the conversion measure is above what delinquency ageing can produce, so it measures something else.
- Tests pass (358), live pages equal the snapshot, and the scheduled workflow is safe on rate and failure handling.

## Findings

### abs-A-1 [HIGH] [CONFIRMED] [new] Santander's buy-backs of loans 120+ days late are counted as harmless exits, so every published Santander rate is too low and every "against Santander" comparison is tilted

- Where it shows: https://samueljwebber.github.io/abs-risk/autos.html. Section 2 table (`santander | 660 | ... | 5.39%`,
  680 4.67%, 700 3.30%, 720 3.08%, 740 5.29% at 12 months); summary "Deep in subprime ... exeter 21.8%, santander 15.1%,
  americredit 12.9%"; section 3, where Santander is the baseline of every lender odds ratio; section 5 and
  conclusions.html "exeter: entry ratio 1.00, roll ratio 1.41". The page's only words on it: a loan "leaves when it pays
  off, is repurchased, or charges off".
- Evidence:
  - `src/absrisk/estimate/survival.py:26` `COMPETING = {"prepay", "repurchase", "other", "absent"}`: a repurchase is
    treated like a payoff.
  - `s10_misc.py`: share of repurchased loans that had reached 90 days late: sdart-2025-1 85.7% of 691, sdart-2026-1
    92.1% of 763; Exeter 7% of 360. `s11_repurchase.py`: 1,087 such Santander loans, 1,073 of them leaving in pool
    months 3, 4 or 5, against 1,726 Santander charge-offs in those same three months.
  - Raw file check (`s12_rawrepo.py`, `out_s12.txt`), SDART 2026-1 EX-102 for July 2026 (accession 0001193125-26-352879):
    207 records with `zeroBalanceCode` 3, of which 199 carry `currentDelinquencyStatus` 120 or more (first example: 148
    days, charged-off amount 0, balance to zero). June file (0001193125-26-303622): 272 of 297. Santander's own charge-offs
    in the same file are mostly at 120+ days (818 of 989, `out_rawscan.txt`), so these loans leave at the charge-off stage.
  - Effect, counting a repurchase of a loan that had been 90+ days late as a loss (`out_s11.txt`):
    12-month cells 660: 5.39% -> 7.25%; 680: 4.67% -> 6.67%; 700: 3.30% -> 4.91%; 720: 3.08% -> 4.04%; 740: 5.29% -> 6.95%.
    Deep-subprime 24-month average: Santander 15.13% -> 16.77% (Exeter 21.76% -> 21.79%, AmeriCredit unchanged).
    Share of ever-30-day-late loans lost: Santander 21.9% -> 24.2%; crude Exeter/Santander roll ratio 1.35 -> 1.22, and
    the page's per-bucket median 1.42 -> 1.27 (`s13_entry_roll.py`).
  - The project knew at scouting and did not carry it forward: `design/scout-autos.md:525-526` ("Santander repurchased
    297 loans in one month, mostly 98-118 days delinquent, so treat repurchase of delinquent loans as a censoring that
    correlates with the event"). REVIEW.md rounds 1 and 2 do not mention it.
- How I tried to refute it: (1) checked the raw XML rather than trusting `max_dpd` in the parquet; (2) checked the other
  six lenders (0 to 25 such loans each); (3) checked whether the headline median moves. It does not: the bucket ratios
  become 11.6, 13.4, 15.6, 21.4, 22.4 (Santander overtakes Exeter at 660 and 680), median still 15.6. So the headline
  number survives; Santander's levels, the 9-to-17 range, the deep-subprime line and the Exeter "roll" story do not. The
  hazard model was not refitted; Santander's event count rises about 9% overall and far more in pool months 3-5, which is
  also where the page's "months 3 to 5 still 0.66 times" comes from.
- Why it matters: the page says it describes "who defaults where". A borrower 148 days late whose loan the sponsor buys
  back has defaulted. One lender's default rate is understated by a third in the first year, and that lender is the
  yardstick for all the others.
- Fix: add an exit type for repurchase at 90+ days late and count it as the event (show the trust-loss definition
  beside it); refit b1, b2, b6; say on the page what Santander's repurchases are.

### abs-A-2 [HIGH] [CONFIRMED arithmetic, PLAUSIBLE cause] [new] Card "conversion" exceeds what delinquency ageing can produce, so "Amex converts at 1.39 times Synchrony, the opposite of protection" is not evidence about protection

- Where it shows: cards.html section 5 ("once an account is 90 days late it converts to a loss at 1.39 times synchrony's
  rate ... That is the opposite of what protection would look like"); conclusions.html ("The answer: selection, on every
  level comparison", "The conversion comparison rules out the simple priority story", "their late accounts are not
  rescued more often than anyone else's"); index.html ("On every level comparison it is selection").
- Evidence:
  - The limit case. Under the 180-day charge-off rule a balance sits in the 90+ bucket for three reports (91-120,
    121-150, 151-180) and then charges off. If every such balance rolled to loss, the month's charge-off would be one
    third of the 90+ stock. Anything above a third did not come through the bucket.
  - `s14_conversion.py` on `data/cards_monthly.csv`: geometric-mean conversion Amex 44.5%, Chase 38.7%, BofA 34.8%,
    Synchrony 32.1%, COMET 31.1%, Citi 27.2% (the page's own column). Above one third in 99% of Amex's 94 months, 95% of
    Chase's, 61% of BofA's, 33% of Synchrony's. So at least 25% of Amex's and 14% of Chase's charge-offs never aged
    through late delinquency.
  - Raw Amex 10-D for July 2026 (accession 0001104659-26-097714, exhibit 99): "Defaulted Amount 39,467,785.90";
    "91-120 Days Delinquent 32,094,421"; "120+ Days Delinquent 45,924,272". Defaults are 51% of the 91+ stock and 86% of
    the whole 120+ bucket, which holds two months of ageing. Roughly 40% of that month's defaults cannot be aged accounts.
  - The three trusts with a conversion ratio above one (Amex 1.39, Chase 1.20, BofA 1.08) are exactly the three above the
    one-third bound. The likely source is bankruptcy, death and settlement charge-offs, which are written off on notice
    and are a larger share of losses in prime pools (not confirmed: the 10-Ds I could read do not split them out).
  - Second, independent of the first: paying a card first keeps it from going 30 days late at all, so priority lowers
    entry. conclusions.html concedes this ("Priority could lower entry too") and then rests the verdict on conversion.
- How I tried to refute it: a falling delinquency stock could push the ratio above a third for a few months, not for
  94; the base mismatch (defaults on principal, delinquency on total receivables) pushes Amex's ratio up by about 5%, far
  short of 44.5 against 33.3; Amex's row for July 2026 in the CSV equals the filing.
- Why it matters: the contractual conversion at Amex is at most about 33%, against Synchrony's 32% (less if Synchrony
  also has bankruptcy losses). Its ratio is somewhere at or below about 1.0 to 1.2, sign unknown. The cards leg of "it is
  selection" therefore says only that Amex has fewer delinquent balances, which both stories predict. This is separate
  from REVIEW R2-4 (Citi, AmeriCredit), which is still open and live.
- Fix: say conversion mixes aged and non-aged charge-offs and cannot be read as rescue; drop "rules out"; keep the
  entry fact. If any trust reports bankruptcy charge-offs separately, subtract them and show the bound for the rest.

### abs-A-3 [MEDIUM] [CONFIRMED] [new] "A median 16 times" sits on a knife edge and is a first-year number; the same data give 8 to 13 under equally reasonable rules and 4.5 at two years

- Where it shows: autos.html summary: "the highest one-year charge-off rate is a median 16 times the lowest (95%
  interval 10 to 19); the bucket ratios run from 9 to 17".
- Evidence (`s02_gap.py`, `s09_boot.py`, `s04_agefixed.py`, `s15_poolmonth.py`):
  - Reproduced: bucket ratios 9.0, 10.0, 15.6, 17.1, 16.3; median 15.55; without Exeter 9.41; counted from pool month
    0 and 6: 12.85 and 11.45. All equal `data/results/autos/b1_gap.csv`.
  - The 720 bucket's lower end (CarMax) has exactly 10 charge-offs, the threshold. With the project's own function:
    `lender_gap.bucket_ratios(lender_gap.usable_cells(pd.read_csv('data/results/autos/b1_at_12.csv')), min_events=m)`
    -> m=10: median 15.55 over 5 buckets; m=11: 12.75 over 4; m=19: 9.95 over 3.
  - Bucket width: 10 points 8.2, 20 points 15.6, 25 points 17.4, 30 points 14.0. Mean of the five 13.6, geometric mean 13.1.
  - Bootstrap of the whole rule (400 resamples within lender): median 12.4 with everything re-decided, 13.0 with the
    project's fixed cells; 60% of replicates fall below 13. The published point estimate sits near the 75th percentile
    of its own bootstrap distribution. The published interval (10 to 19) reproduces (9.6 to 18.7).
  - Horizon. The page's own tables: Santander 660 against CarMax 660 is 5.39% / 0.63% = 8.6 at 12 months and 13.45% /
    2.97% = 4.5 at 24 months. At 18 months the same pairs give 5.3 (660), 6.4 (680), 6.4 (700), 11.1 (720), 15.4 (740).
    By months in the trust (scores 660-759): Exeter's monthly hazard is about 15 times CarMax's in months 3-5 and 7 to 8
    times in months 9-14, because prime losses arrive later (CarMax's hazard in months 3-5 is 0.34 of its months 9-14
    level; Exeter's is 0.68).
  - Mix. Mantel-Haenszel rate ratios at fixed score bucket and age, scores 660-759, ages 6-12: Santander/CarMax 10.1,
    then 6.9 with loan-to-value bands, 6.4 with payment-to-income and term, 5.6 with origination year; Exeter/CarMax 11.6
    -> 8.2 -> 8.6 -> 8.3. Ages 12-24: Santander/CarMax 5.5 -> 3.6; Exeter/CarMax 6.7 -> 4.2. New against used adds nothing
    for CarMax pairs (CarMax is all used).
- What survives: "Who lends matters about as much as what the score says" holds on like-for-like terms inside the
  project's hazard model (highest over lowest lender 1.34 / 0.13 = 10 in the score specification, against 9 for score).
  The loan-age comparison is fair for the pairs that make the headline: Exeter is observed from age 3, Santander and
  CarMax from age 4.
- Why it matters: 16 will be quoted as the lender gap. It is the high cluster of a two-cluster set, at the horizon where
  the gap is widest.
- Fix: report the pooled age-stratified ratio (about 10 to 12 in year one) with the range, give the 18 and 24 month
  figures beside it, and say the ratio falls with loan age.

### abs-A-4 [MEDIUM] [CONFIRMED] [new] The "12-month" rates for Capital One, Toyota and Honda cover two, four and six months of loan age; the page blames their low rates on few charge-offs

- Where it shows: autos.html section 2 table (`aj_chargeoff_12`: capone 700-840 0.00% to 0.22%; toyota; honda) and the
  summary: "capone, honda and toyota sit lower still, on fewer than 10 charge-offs each by twelve months, which is too
  few to divide by".
- Evidence: `survival.py:119` sets the hazard to zero at any age with nobody at risk. At-risk counts by age 0..12 from the
  committed `b1_cif.csv`, bucket 740: capone `[0,0,0,0,0,0,0,0,0,0,0,703,1498]`, toyota first non-zero at age 9, honda at
  age 6 (32 loans) and 7; exeter from age 3, santander and carmax from age 4. `s05_thin_risksets.py`: median first observed
  age capone 11, toyota 9, honda 6, americredit 5, carmax 4, santander 4, exeter 3.
- Why it matters: those columns are printed as the same quantity for every lender. A Capital One "12-month" rate is two
  months of exposure. The 24-month column has the same hole. The headline escapes only because the 10-event rule
  happens to exclude these cells.
- Fix: blank a cell whose first observed age is later than a stated age (say 6), or print every lender over the common
  age window; correct the sentence.

### abs-A-5 [MEDIUM] [CONFIRMED] [new] "The same credit score" is three different things at the two ends of the headline ratio, and both pools are filtered by their sponsors on their own risk models

- Where it shows: autos.html intro: "a 700 at Exeter and a 700 at Honda are close but not the same number"; summary:
  "exeter is the highest lender in the 660, 680 and 700 buckets"; index.html "Both hold at the same credit score".
- Evidence:
  - Exeter. Its prospectus, quoted in `design/scout-autos.md:398-400`, gives the same pool on both scales: weighted
    average 582 on the bureau (Vantage) score and 562 on FICO; 14% below 540 on the first, 32% on the second. Not close.
  - Exeter again (`scout-autos.md:393-397`, `225-229`): since 2025-4 the public pools exclude loans with bureau score
    640 or more and proprietary score 240 or more. What is left above 640 in exeter-2025-5 is what Exeter's own model
    rates poorly. `s06_exeter_deals.py`: monthly hazard at ages 6-12, scores 660-719: 1.10% in 2025-5 against 0.74% in
    2025-1 (1.5 times); scores 600-639, where no filter applies: 0.96% against 0.82% (1.17 times). 2025-5 supplies 20%
    of the loans and 24% of the charge-offs in the three Exeter headline cells.
  - CarMax. Cached prospectus (0001193125-26-173162): the pool "was selected from CarMax Business Services' core
    portfolio ... with a FICO score at origination greater than or equal to 650"; "core" is defined by an expected
    cumulative-net-loss range, and since June 2024 contracts "outside the core portfolio, a substantial portion of which
    are obligations of lower credit obligors" go to the separate CarMax Select trusts. So the public CarMax 660-679 loans
    are the ones CarMax itself classed as lower risk.
  - CarMax again: the score for a joint loan "is calculated as the average of each obligor's FICO score" (same
    prospectus). In the July 2026 file 6,755 of 15,670 co-obligor records have a half-point score (`out_rawscan.txt`), so
    about 30% of CarMax loans carry an average of two people. `autos/parse.py:133` truncates them.
- Why it matters: the comparison is between the leftover top of a deep-subprime book on one scale and the hand-picked
  bottom of a prime book on another. The page's general caveat ("not the lenders' whole books") does not tell the reader
  that the filter runs in opposite directions at the two ends. Effect of the Exeter scale alone is about 20% of the ratio
  (shift Exeter down 20 points and its 660 cell meets CarMax's 0.79% instead of 0.63%), and the page's "without Exeter"
  check covers that part. The CarMax filter cannot be sized without the CarMax Select files.
- Fix: say so in the summary; add the CarMax Select and Exeter Select trusts, or call the result a comparison of
  shelves, not lenders.

### abs-A-6 [MEDIUM] [CONFIRMED] [new] Honda and Toyota borrowers who fall behind are 25 to 40% less likely to be charged off, and the pages call that "close to the baseline" and "no sign" of protection

- Where it shows: autos.html section 5: "once behind they charge off at close to the baseline lender's rate. There is no
  sign here of an account that borrowers protect"; conclusions.html: "(roll ratios carmax 1.07, honda 0.75, toyota 0.76)".
- Evidence: the page's own numbers are 0.75 and 0.76. Recomputed (`s13_entry_roll.py`, medians over buckets 640-760):
  published definitions give Honda 0.68, Toyota 0.76, CarMax 1.07, Exeter 1.42, entry shares 84%, 86%, 103%. With
  Santander's delinquent buy-backs counted (abs-A-1): Honda 0.61, Toyota 0.70, CarMax 0.96, Exeter 1.27, AmeriCredit 0.78.
  With the entry stage also held to ages 12-24 for every lender, entry shares are Honda 78%, Toyota 83%, CarMax 98%.
- Why it matters: "mostly entry" survives for all three. "No sign of anything after trouble" is true for CarMax only.
  REVIEW R2-4 raised this for AmeriCredit and Citi; the captives were missed.
- Fix: print the roll ratios with intervals and let the sentence follow them.

### abs-A-7 [LOW] [CONFIRMED] [new] A few published cells rest on one charge-off in a tiny early risk set

- `s05_thin_risksets.py`: honda 640, 12 months, 1.61%: 66% of it is one charge-off among 94 loans at age 7. americredit
  480, 7.03%: 49% is one among 29 at age 5. americredit 540: 3.5 points of its 16.69% at 24 months are four charge-offs
  among 114 loans at age 5, which is why that bucket sits above 520 and 560 and lifts AmeriCredit's deep-subprime
  average from about 11.8% to 12.9%.
- Fix: no hazard from a risk set under a stated size.

### abs-A-8 [LOW] [PLAUSIBLE] [new] The first scheduled refresh (2026-11-12 09:17 UTC) is also the first run of the workflow and code as they now stand

- `gh run list -R SamuelJWebber/abs-risk` (2026-11-10): the last `cards-refresh` run is 42727357720 at 49ffdd6, on
  Python 3.14.4. Since then da4a343, cc0f90b and 2657d8a changed the workflow (Python 3.12, `-m "not repo_hygiene and
  not slow"`), the card driver and both card pages, all rebuilt on Windows. Only `hygiene` has run at f45e9fe. The test
  step rebuilds results and pages and compares them with the committed files, so a platform difference fails the run
  before anything is fetched. Loud, not garbage. A manual dispatch before Thursday would settle it.
- Same file, for the record: actions are pinned to tags, not commit SHAs, in a job with `contents: write`
  (`cards-refresh.yml:39-47,89`); `autos-build.yml` still uses checkout v4 and setup-uv v6. Nothing alerts when every
  trust stalls together (REVIEW "bigger improvement 5", still open).

### abs-A-9 [LOW] [CONFIRMED] [new] The landing and conclusions pages open with issuer-level sentences that the trust data cannot carry

- index.html: "American Express loses less than Synchrony. Toyota loses less than Santander."; conclusions.html:
  "American Express loses less on its card portfolio than Synchrony does"; "Issuers with low losses at the same credit
  score got there by lending to people who do not fall behind". The data are one master trust per card issuer and one or
  two public deals per auto lender (four lenders have one deal). cards.html and autos.html say so in their first
  paragraph; index.html does not, and conclusions.html says it only in its last section.
- Fix: "the American Express trust", "Toyota's public pool", on first use.

### Known-but-live (already in REVIEW.md, still on the public pages; one line each)

- R2-2 [known-but-live]: cards.html still says Synchrony is "the one trust whose gap does not depend on the assumption"
  and "+1.07% to +1.73%"; the correction (1e3af87) is unpublished.
- R2-3 [known-but-live]: conclusions.html still says "the ends of the ranking hold (amex, citi, synchrony keep their place)".
- R2-4 [known-but-live]: index.html "On every level comparison it is selection"; conclusions.html heading and "short version".
- Housekeeping: REVIEW.md round 2 has no status lines; HANDOFF.md still says 333 tests and "median 38x".

## Checked and found right

- Headline arithmetic: every number in `b1_gap.csv` I recomputed matches (15.552, 9.410, 12.852, 11.449, band 1.682).
- Loan age in the headline pairs is held fixed: Exeter, Santander and CarMax are observed from ages 3-4; age-stratified
  rate ratios (ages 6-12) agree with the bucket ratios (Exeter/CarMax 10.5 at 660-719, 24.9 at 720-759; Santander/CarMax
  9.4 and 14.8).
- Loan amount, top against bottom quintile, 0.72 on the page: 0.71 by my stratified estimate, 0.73 with new/used added,
  0.78 with term added. Holds.
- Lender odds ratios in the hazard table are in line with stratified rate ratios at fixed score, age and loan structure
  (Santander over CarMax 3.6 to 6.4, over Toyota 4.3 to 7.4, over Honda 5 to 10; Exeter over Santander 1.1 to 1.3).
- Entry/roll medians reproduce (entry shares 84%, 86%, 103%; Exeter roll 1.42).
- Charge-off flag: in six raw files (CarMax, Exeter, Santander, AmeriCredit, Toyota, Capital One) zero-balance code 4
  catches the charge-offs: only 3 records (AmeriCredit) carry a charged-off amount with no code, and 53 carry one on a
  paid-off loan. Charge-off timing is about 120 days at all of them; only Exeter leaves any loans open past 120 days
  (308 of 48,292). The rate is the share of loans charged off (a count, not dollars), gross of recoveries, cumulative
  by loan age. The page never says it is a count or that recoveries are ignored; one sentence would fix that (LOW).
- Calendar time: all ten deals are observed between May 2024 and July 2026, eight of them from January 2025 on. No deal
  was called or stopped filing inside the window.
- Card definitions: charge-off bases differ by trust (ending, average, beginning principal; invested amount at Citi) and
  so do annualisation conventions; the page says they are kept as reported. Yield and payment rate are parsed but no
  published claim uses them.
- Duplicates: no asset id twice inside a deal; four Exeter loans appear in both Exeter deals (repurchased from one, sold
  into the next). Cards: one row per trust-month, no gaps except COMET's three documented 2019 months; five superseded
  filings, all identical to the kept one; the Amex July 2026 row equals the raw 10-D.
- Tests: `pytest -o addopts="" -p no:cacheprovider`, single process: 358 passed, 1 skipped, 421 s. Tree clean afterwards.
- Live pages: index, cards, autos, conclusions equal the snapshot's `docs/` (curl, 2026-11-10; Last-Modified 01:40 GMT).
  `tests/test_pages.py` confirms the committed pages are what the code builds from the committed results.
- Workflow: one throttled session at 5 requests a second with the project User-Agent (`http.py:25,66`); a concurrency
  group; any fetch error exits non-zero before parsing; tables are re-tested before the commit; the alert check fails
  the run after committing; no trigger hands a write token to a fork; the contact secret reaches only the fetch step.

## Not checked

- The hazard model (b2, 16 minutes) and the regression discontinuity were not refitted; b2 was compared only against my
  stratified ratios, and its response to abs-A-1 is an estimate.
- Card residuals against the score mix were not re-derived from the prospectuses (rounds 1 and 2 did that); I checked
  one monthly row against its filing.
- Honda: no raw file is cached, so its charge-off coding and score reporting are unverified. No deal has more than two
  monthly raw files cached, so the parquet build was not replayed end to end. sec.gov was not contacted.
- The split of card charge-offs into aged, bankrupt and deceased (abs-A-2's cause) is not in the filings I could read.
- The CarMax Select and Exeter Select pools (abs-A-5) are not in the data.
- Whether the workflow passes on the Linux runner (abs-A-8).
