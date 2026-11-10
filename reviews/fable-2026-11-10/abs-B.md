# abs-B: abs-risk, outside comparison

Snapshot `f45e9fe27bcba60b5a48bd3cfa18cf69827e4f10` (GitHub `main`), read 2026-11-10. Nothing in the snapshot or the
real project folder was changed. What I ran, all in `work/abs-B/` with the snapshot's `.venv` Python, single process:
`deal_levels.py` and `deal_series.py` (deal totals and monthly cumulative charge-offs from `data/autos/*.parquet`),
`matched.py` (the published cells reproduced with `absrisk.estimate.lender_gap`, then matched strata; output in
`matched_out.txt`), `headline_variants.py` (the headline median with and without one Exeter pool), `tables.py` / `policy.py` / `grep_sent.py` (tables and sentences out of the prospectuses and 10-D
exhibits cached under the project's untracked `data/raw/scout/`). Outside reading: CFPB Data Point 2021-10, FEDS
2020-042 and one Philadelphia Fed conference paper (curl, User-Agent `abs-risk/0.1.0`), trade press and NBER by
WebFetch, GitHub by read-only `gh`. EDGAR: one request with the project's User-Agent and no contact address was
refused (403, "Undeclared Automated Tool"); not retried, because the contact is an Actions secret. The session's web
search budget ran out before the card indices could be searched.

## Verdict

- The auto loan parsing is right. Where an issuer publishes the same deal's losses, ours agree to within 0.03 points
  (Exeter 2025-1: 6.42% and 7.25% gross against the issuer's 6.44% and 7.28%), and loan counts match to the loan.
- The card data has one real error: Citi's "gross charge-off" is Citi's **net** loss rate. Every Citi result on the
  cards and conclusions pages compares Citi net of recoveries with five trusts gross (HIGH, confirmed three ways).
- The conclusions page's central test (a high "conversion" rules out priority) does not measure what it says: at Amex
  and Chase more principal is charged off each month than sits in the delinquency bucket about to reach 180 days, so
  a large share of charge-offs never passed through "90 days late". The page also says the filings do not state
  charge-off policy; the trusts' prospectuses do (HIGH).
- "16 times at the same score" is correct arithmetic, but it is the same score on different loans from shelves the
  issuers curate, and it is 9 without one score-selected Exeter pool. Matched on vehicle type, term and loan-to-value
  it is 3 to 7 times; the project's own hazard model says 5. No published study contradicts a large same-score gap;
  the nearest (CFPB, subprime scores) finds about 2 times, which matches the project's 1.7 in that range.
- Confidence: high on the two HIGH findings (both sides read); medium on the size of the matched ratio (thin cells).

## Findings

### abs-B-1 [HIGH] [CONFIRMED] [new] Citi's "gross charge-off rate" is Citi's net loss rate, so Citi is compared net of recoveries with five trusts that are gross

- **Where it shows.** `docs/cards.html` section 4: Citi residual -1.18% / -0.93% / +0.57% / +0.43%, rank 5 under every
  shape, "amex, citi, synchrony keep the same rank under every shape". Section 5: Citi `co_monthly` 0.172%, conversion
  27.2%, ratio 0.85, "The trust whose 90-day-late balances convert least is citi", direction test "rose for citi
  (+0.09)". `docs/conclusions.html`: the same table and "the ends of the ranking hold (amex, citi, synchrony keep their
  place)". `design/methods.md:201`: "only a gross rate component". `src/absrisk/cards/parse.py:518-521`: "Credit Loss
  Component is inferred gross".
- **Evidence.** Citi's own prospectus, cached by the project at
  `data/raw/scout/edgar/cards/citi/prospectus/0001193125-25-144490/d945716d424b2.htm`:
  - table "Net Losses by Year of Account Origination (by Monthly Due Period)": Dec 2024 2.84, Jan 2025 2.26, Feb 2025
    2.28, Mar 2025 3.00. `data/cards_monthly.csv`, trust `citi`, `gross_co_rate`: 2024-12-26 0.0284, 2025-01-28 0.0226,
    2025-02-25 0.0228, 2025-03-26 0.0300. Identical.
  - table "Loss Experience for the Accounts": net losses 1.25% (2022), 1.92% (2023), 2.57% (2024); gross charge-offs
    over average principal are 440,245/23,990,438 = 1.84%, 577,471/23,760,232 = 2.43%, 696,088/22,439,121 = 3.10%. The
    CSV's Citi yearly means are 1.25%, 1.91%, 2.55%: the net column.
  - definition in the same document: Portfolio Yield is collections "after subtracting the amount of principal
    receivables that were charged off ... (net of recoveries)"; the Credit Loss Component is that subtraction.
  - Re-run: `python work/abs-B/tables.py <that file> out.txt`, then grep "Net Losses"; and
    `pd.read_csv('data/cards_monthly.csv').query("trust=='citi'")` grouped by year of `period_end`.
- **How I tried to refute it.** Checked whether the other five are also net: no, each prints a labelled gross and a
  labelled net row and the CSV carries both (July 2026, read in the raw exhibits: Amex 1.8640/1.1114, BofA 2.74/2.13,
  Chase 2.02/1.58, COMET 2.96/1.80, Synchrony 5.3437/4.1142). Checked for coincidence: four monthly values match to the
  basis point and three annual means to 0.02 points, while gross is 0.5 to 0.6 points higher every year.
- **Size.** Gross over net at Citi is 1.47 (2022), 1.27 (2023), 1.21 (2024), 1.25 (Q1 2025); 1.29 pooled. Citi's mean
  "actual" of 2.15% is therefore about 2.8% gross (2.6 to 3.2). Its residual rises by roughly 0.6 points under every
  shape, which moves it from rank 5 to rank 2 or 3 (BofA is -0.63 / -0.37 / +1.13 / +1.00). Conversion goes from 27.2%
  to about 35%, a ratio of about 1.09 against Synchrony instead of 0.85, so Citi is no longer the trust that "converts
  least" and review finding R2-4's "Citi exception" is an artefact of the same mix-up. On a net basis for all six the
  means are Amex 1.20, Chase 1.69, COMET 2.01, BofA 2.13, Citi 2.15, Synchrony 4.02: Citi is second highest, not
  third lowest.
- **Why it matters.** Published ranks, residuals, the stage table and three sentences about Citi are wrong, and
  methods.md's "kept as reported, never mixed" is not true for this trust.
- **Fix.** Store the Citi series as `net_co_rate`. Either compare all six trusts net (every other trust has the
  column), or gross Citi up with the annual gross/net ratio from the loss-experience table in each Citi prospectus and
  say so. Add a golden check that pins one Citi month to the prospectus's monthly net-loss table.

### abs-B-2 [HIGH] [CONFIRMED] [new] "Conversion" is not the rate at which 90-day-late balances become losses, and the charge-off policies the page says are unstated are in the prospectuses

- **Where it shows.** `docs/conclusions.html`: "The answer: selection, on every level comparison"; "once an account is
  90 days late, it converts to a write-off at 1.39 times synchrony's rate ... Priority predicts the opposite sign on
  conversion"; "Separating those needs each issuer's charge-off policy, which the filings do not state"
  (`report/conclusions_page.py:169`); "their late accounts are not rescued more often than anyone else's".
  `docs/index.html`: "On every level comparison it is selection". `docs/cards.html` section 5.
- **Evidence.**
  1. The policies are stated, in the prospectuses the project already parses for score mix (same cached folder).
     Amex: charge off at "approximately 180 days delinquent ... or sooner if the death or bankruptcy of the account
     holder has been confirmed". Citi: 180 days, or bankruptcy "not later than 30 days after the servicer receives
     notice". COMET: 180 days, 120 for workout loans; charge-off types "contractual ..., bankruptcies and estates".
     Chase: earlier for bankrupt, deceased and non-complying restructured accounts. (`work/abs-B/policy.py`.)
  2. With a 180-day rule, only the oldest thirty-day slice of the 90+ balance can charge off contractually next month,
     so conversion from that pipeline cannot stay above about one third. The page's own geometric means are Amex
     44.5%, Chase 38.7%, BofA 34.8%; conversion is above one third in 99%, 95% and 61% of months for those three, and
     in 33%, 22% and 4% for Synchrony, COMET and Citi (from `cards_monthly.csv`).
  3. Read directly in the July 2026 reports: Chase charged off $20.16M of principal in the month while its whole
     150-179 day bucket held $16.44M. Amex charged off about $39.5M (1.8640% x 31/365 x $24.93bn) while its 120+ bucket
     held $45.9M; that bucket runs from day 121 to charge-off near day 180, two monthly cohorts (the single 91-120
     cohort is $32.1M), so about $23M was due to charge off contractually. Citi, by contrast: about $32.7M net against
     $42.2M in its 151-180 bucket.
- **What that means.** The numerator of "conversion" includes charge-offs that never sat in the 90+ bucket: bankruptcy,
  death and other early write-offs. That share is at least 18% at Chase (read directly) and roughly 40% at Amex (my
  split of its 120+ bucket) in July 2026, and it is mechanically larger where contractual delinquency is low. So a conversion ratio of 1.39 at Amex does not show
  that Amex's late accounts are rescued less; it shows that more of Amex's losses arrive without a delinquency
  pipeline. The project spotted exactly this in autos ("75% of capone's" charge-offs never 30 days late, "so the split
  says little about capone") and did not apply it to cards.
- **How I tried to refute it.** A falling delinquency stock can lift conversion above a third for a few months but not
  as a 94-month geometric mean. The base mismatch (principal charge-offs over total-receivable delinquencies) lowers
  conversion, it does not raise it. What I could not establish is each trust's exact bypass share over time, so I
  cannot say what the corrected ratio is, only that the published one cannot carry the sign argument. With abs-B-1,
  the one trust the pages call an exception on conversion (Citi) is also an artefact.
- **Why it matters.** Entry cannot separate the stories (the page says so), so conversion is the only evidence for
  "selection, not priority". That evidence does not measure rescue.
- **Fix.** Delete "which the filings do not state" and quote each trust's policy. Report conversion as charge-offs
  over the oldest bucket where the report prints one (Chase, Citi, BofA, COMET), and bound the bypass share. Change the
  heading and the landing-page line to what survives: low-loss trusts have far fewer delinquent balances; public data
  cannot say whether their delinquent accounts are rescued more or less often.

### abs-B-3 [MEDIUM] [CONFIRMED] [new] "16 times at the same score" is same score, different loan, from curated shelves; with recorded loan structure matched it is 3 to 7 times

- **Where it shows.** `docs/autos.html`: "the highest one-year charge-off rate is a median 16 times the lowest (95%
  interval 10 to 19); the bucket ratios run from 9 to 17 ... exeter at 5.64% against carmax at 0.63%".
- **Evidence** (`work/abs-B/matched.py`, which first reproduces every published cell and ratio):
  - The five ratios are 9.0, 10.0, 15.6, 17.1, 16.3. The two buckets with the most charge-offs in the lower cell
    (660 and 680: 29 and 25) give 9 to 10; the three near 16 divide by CarMax cells of 21, 10 and 18 charge-offs, with
    published intervals of 8.6 to 44 and 8.8 to 33 at 720 and 740. The median of five sits on a knife edge: it is 16
    because Exeter's 700-719 cell (1,617 loans) clears the 1,500-loan rule; if that one cell did not count, the 700
    bucket would be Santander over CarMax at 8.2 and the median 10.
  - Inside the 660-679 bucket the loans differ: median APR 19.5-21.0% at Exeter, 15.7-17.0% at Santander, 12.7-13.6% at
    CarMax, 5.0% at Honda; median loan-to-value 1.24 / 1.16 / 1.03 / 1.03; median term 76-77 / 72 / 67 / 73 months;
    used vehicles 92% / 70-77% / 100% / 19%.
  - Used vehicles, 66-78 month terms, same loan-to-value band, same 20-point bucket (lower cell at least 5
    charge-offs): Exeter over CarMax 7.0, 4.5, 7.4; Santander over CarMax 2.8 to 5.4, median 4.9 over seven strata.
    Inside one APR band as well (16-20%, 660-679): Exeter 5.09%, Santander 5.49%, CarMax 1.02%, about 5 times. Cells
    are thin; treat as indicative.
  - The project's own hazard model already says this: terms specification, Exeter 1.10 against CarMax 0.23 is 4.8
    times; with APR, 0.98 against 0.34 is 2.9 times. The headline uses the uncontrolled figure.
  - Shelf curation, from the prospectuses in the project's cache. CarMax: the public CAOT pools are "selected from ...
    core portfolio ... with a FICO score at origination greater than or equal to 650"; since June 2024 a second public
    shelf, CarMax Select Receivables Trust, takes core and non-core contracts, "a substantial portion of which are
    obligations of lower credit obligors" (Fitch on CMXS 2024-A: weighted FICO 603, loss proxy 9%; American Banker,
    2024-07-02). CMXS files ABS-EE and is not in the data, so "carmax" is CarMax's better shelf. Exeter: EART 2025-5
    excludes loans with bureau score at least 640 **and** proprietary score at least 240, so its 660+ loans are the ones
    Exeter's own model marked down: 12-month charge-off at 660-679 is 9.38% in 2025-5 against 5.23% in 2025-1 (part
    of that is vintage: below 640, where nothing is excluded, Exeter's 2025 loans run about 1.1 to 1.4 times its 2024
    loans in the page's own by-year table). Without that pool, the project's own `bucket_ratios` gives a median of
    **9.4** (ratios 8.6, 9.4, 8.2, 17.1, 16.3), because Exeter's 700-719 cell falls to 1,253 loans and stops counting;
    with the cell rule relaxed to 1,000 loans it is 14.1 (`work/abs-B/headline_variants.py`). The page's "without
    Exeter" check prints the same 9, but not that a score-selected pool is what separates 9 from 16.
- **Outside benchmark.** Issuer static pools put whole-shelf net loss at month 24 at 13.6-16.9% for Exeter (2022-1 to
  2024-1) and 0.69-1.18% for CarMax's 650+ pools of the same vintages, about 12 to 21 times deal for deal. Holding
  score fixed therefore barely narrows the raw shelf gap, because inside Exeter and Santander charge-off is nearly flat in score (page table: Santander 5.62% at
  500-519, 5.39% at 660-679).
- **Why it matters.** The sentence most likely to be quoted reads as a lender effect at a fixed borrower. It is a
  description of who ends up in which public pool; with recorded loan structure held fixed the ratio is about a third
  of the headline, and the headline itself is 9 or 16 depending on one cell of one score-selected pool.
- **Fix.** Lead with the range and both numbers: "9 to 17 times at the same score; about 5 times once loan-to-value,
  payment burden, vehicle type and term are held fixed". Say next to it that CarMax's lower-credit public shelf is not
  in the data and that one Exeter pool is score-selected. Add CMXS (and ESART) deals.

### abs-B-4 [MEDIUM] [CONFIRMED] [new] "The size of a loan is not the risk in it" is presented as settled; it is an old descriptive result, and the causal evidence runs the other way

- **Where it shows.** `docs/conclusions.html`, "What else the data settled": "The size of a loan is not the risk in it;
  the payment is ... Anyone reasoning about a bigger line as risk in itself has the wrong variable."
- **Evidence.** Klee and Shin (FEDS 2020-042, 5.9 million ABS-EE loans, 15 issuers) already report it: one standard
  deviation more loan amount lowers charge-off odds 18.1%, while rate, term and payment-to-income raise them 64.2%,
  20.6% and 8.9%. Adams, Einav and Levin (AER 2009; NBER Digest, read 2026-11-10) find that for the same buyer and
  car each extra $1,000 lent "increases the default rate on the loan by around 15 percent". The project's coefficient
  is loan amount with payment-to-income and loan-to-value held fixed, which makes it a proxy for income and vehicle
  value, as the page itself explains; and the project's only causal design for loan amount returned a null.
- **Why it matters.** The sentence about "a bigger line" carries an auto-loan correlation to card credit limits, which
  nothing here observes.
- **Fix.** "At the same payment burden and loan-to-value, larger loans default less, as Klee and Shin (2020) also
  find; a larger loan to the same borrower raises both, and Adams, Einav and Levin (2009) find it raises default."
  Drop "settled" and the line about lines.

### abs-B-5 [LOW] [CONFIRMED] [new] The notes date Exeter's score-based pool selection from 2025-4; the prospectus says 2025-2

`data/deals.csv:7` and `design/scout-autos.md:226` say "since 2025-4". The EART 2026-2 prospectus (cached) says
"Consistent with the ... 2025-2, ... 2025-3, ... 2025-4 and ... 2025-5 transactions" and stars those four in its static
pool tables. No published number changes (the project holds 2025-1 and 2025-5). Fix the two notes.

### abs-B-6 [LOW] [CONFIRMED] [new] The dollar fields in the loans tables are unused and one has the wrong sign

`recovered_amount` is negative on all 162 Capital One charge-offs (sum -$695,461; the sponsor's sign convention), and
`chargeoff_amount` is taken only from the first month carrying a zero-balance code. No page uses either
(`grep -rn recovered_amount src/absrisk/estimate src/absrisk/report` is empty), so nothing published is wrong. The
page's "charge-off rate" is the share of loans charged off, not dollars; say so once. Recoveries differ by lender in
the data (Honda 60% of charged-off principal, Toyota 54%, Santander 43%, Exeter 41%, CarMax 40%), so a net-dollar
comparison would widen the captive gap, not narrow it.

## Outside comparisons

**Same deal, issuer's own numbers (the parse check).**

| deal | outside source and figure | ours | match |
|---|---|---|---|
| Exeter 2025-1, deep subprime | EART 2026-2 prospectus (0000929638-26-001122), static pool through 2026-01-31: 65,321 loans, $1,449,126,814; cumulative gross loss 1.64% (month 6), 3.90% (9), 6.44% (12), 7.28% (13); net 4.14%, 4.72% | 65,321 loans; gross 1.63%, 3.89%, 6.42%, 7.25% | yes, read both |
| Exeter 2025-5, deep subprime | same annex: 55,508 loans, $1,272,421,908; gross 0.08% (month 2), 0.32% (3) | 55,432 loans; 0.07%, 0.30% | close; 76 loans and about $0.2M short |
| CarMax 2025-1, prime used | CAOT 2026-2 prospectus (0001193125-26-173162), Annex I: 82,495 loans, $1,515,152,457; cumulative net loss 0.27% (month 12), 0.34% (14) | 82,495 loans; gross 0.44%, 0.57%; net of our life-to-date recovery share (39.6%) 0.26%, 0.35% | consistent; recoveries are not dated in the loans table |
| Santander Drive 2025-1, subprime | 10-D exhibit 0001193125-26-352838, **search excerpt only**: cumulative net loss ratio 5.86%, about $131.7M | gross $225.6M less recoveries $96.8M = $128.8M | 2% apart; not read directly |
| Honda 2025-1, prime captive | 10-D exhibits, **search excerpts only**: $2,999,103 on 246 contracts (October 2025), about $3.79M on 321 (December 2025) | 260 and 344 charged-off loans; gross $6.60M and $8.34M | counts 6-7% above; unresolved |
| AmeriCredit 2024-1 | 10-D, **search excerpt only**: 73,190 loans, $1,675,919,179 at closing | 72,665 loans | 0.7% fewer; loss not obtained |

Definitions: issuers report dollars over the cutoff pool balance; the project publishes a count-based incidence by
age. On the two deals where I read both sides in dollars the parse is exact to rounding. The issuer is the authority;
we agree with it.

**Rating agencies, sector level.** Fitch auto indices as reported by Auto Remarketing (2026-05-21): subprime
annualised net loss 9.81% in the January 2026 index and 8.80% in March 2026, subprime 60+ days 6.90% (record) and
6.11%, recovery 37.5%. S&P tracker for March 2025 (search excerpt): prime 0.69%, subprime 7.98%, about 12 times. These
are unconditional pool-level rates on current balance; ours is a same-score loan-level incidence, so they bound the
raw gap, they do not test the headline. They are consistent with abs-B-3: the same-score ratio (9 to 17) is about as
large as the unconditional prime-to-subprime ratio. Presale expected losses by shelf were not retrieved except CMXS
2024-A (Fitch 9%) and CarMax's own assumed 1.25% lifetime net loss for CAOT 2026-2 (prospectus).

**CFPB, "Subprime Auto Loan Outcomes by Lender Type", Data Point 2021-10** (files.consumerfinance.gov, read
2026-11-10). Credit-bureau panel, loans originated 2014-16, scores 620 or less, 60+ days delinquent within about three
years. Banks about 15%, small finance companies nearly 40%; with score and other controls small finance falls to about
30%: "Our controls explain some but not most of the variation". So about 2 to 2.7 times across lender types at subprime
scores. Ours in the comparable range: 1.7 times across Exeter, Santander and AmeriCredit at 540-599. Agreement. The
CFPB also finds captive borrowers have "default risk comparable to those of Large and Small Finance borrowers" at
subprime scores, while our captive pools (620 and up, securitised, entering at 10-13 months old) show odds 0.15-0.19
of Santander's. Different score range and whole books against selected pools; for a statement about lenders the CFPB's
data is the better instrument, for loan structure ours is (the bureau panel has no loan-to-value or payment burden).

**Klee and Shin, "Post-crisis Signals in Securitization: Evidence from Auto ABS", FEDS 2020-042.** Every public auto
ABS from 2017 Q1 to 2019 Q1: 5,930,935 loans, 89 deals, 15 issuers. Lenders hold unobservably better loans longer
before securitising; one standard deviation of that signal lowers charge-off odds 41.3% in the first three months in
the pool. This is outside support for the project's pool-window correction and a warning beyond it: loans that enter
old are better loans, not only loans inside a mechanical window, so Honda, Toyota and Capital One (entry at 10-13
months) stay flattered after the fix. Their hard-variable signs match ours (abs-B-4).

**Lautier, Pozdnyakov and Yan, "On the Convergence of Credit Risk in Current Consumer Automobile Loans"**
(Philadelphia Fed auto lending conference, 2023-07-12). ABS-EE loans from CarMax 2017-2, Ally 2017-3, SDART 2017-2 and
DRIVE 2017-1; 275,000 loans cut to 58,118 that are alike (used vehicles, 72-73 months, no co-borrower, no subvention,
one income-verification level). Left truncation, right censoring and competing risks in discrete time: the same
estimator family as ours. Lifetime default by APR band: 52% at 20%+, 37%, 21%, 10%, 4% at 0-5%; hazards converge
after three to four years. What they do that we do not: homogenise term, vehicle type and subvention before comparing,
and band by price rather than score. Their 13 times between the extreme price bands is the scale of our 16 times at
one score, which says the score is doing little of the sorting across these shelves.

**MSCI (Yang and Zhang, 2021-06-15; Journal of Structured Finance 2022).** 165 deals, 18 issuers. Two deals alike on
pool statistics diverged because of "higher percentage of weaker loans and higher loan-to-value"; "credit scores have
not presented the full story". Issuer is a model input; no same-score issuer ratio is published. That issuer matters
beyond score is established; a number for it is not, and ours is the only one I found.

**Adams, Einav and Levin (AER 2009)**: see abs-B-4. **Yannelis and Zhang (JFE 2023, NBER w29169)**: abstract only (search
excerpt); it is about competition and screening, and reports no lender default ratio at fixed score.

**Seeds I could not verify.** Momeni and Sovich, "The Marginal Propensity to Default", and a Jansen, Kruger and
Maturana paper on the ABS-EE data: two searches each found nothing. They may exist; I am not asserting either way.

**Open-source work on ABS-EE.** `pipeworx-io/mcp-abs-loan-level` (trust-level delinquency rollups),
`benuehlinger/bens-field-notes` (delinquency dashboard), `UNC-Cofires/Form-ABS-EE-Scraping` (CMBS only),
`johnlichtenstein/examine_ABSEE`, `dado0583/SEC-ABS-EE`, `glebkorolkov/absscraper` (fetchers). None publishes loss by
lender and score.

**Card trusts' own reports.** July 2026 values read in the six raw 10-D exhibits equal `cards_monthly.csv`: Amex
default 1.8640%, net 1.1114%, payment rate 50.7944%, yield 31.7408%; BofA 2.74% / 2.13%; Chase 2.02% / 1.58%; COMET
2.96% / 1.80%, principal payment rate 47.98%, yield 27.09%; Synchrony gross yield 28.3297%; Citi 1.90% (net, see
abs-B-1), principal payment rate 43.84%, yield component 23.41%. Yield and payment rate are in the data file and on no
page. Agency card indices: not checked (below).

## Where ours is better than the outside work

- Loan-level cumulative incidence by score and lender with delayed entry, competing risks, a pool-window correction
  and intervals. The agency indices are unconditional pool rates; the CFPB has no loan terms; the open-source
  ABS-EE projects stop at delinquency rollups.
- Lender intervals that carry deal-to-deal spread, and a minimum-events rule on denominators. Klee and Shin and MSCI
  treat loans as independent.
- The page says outright that the lender coefficient is not causal and reports its regression discontinuity as a
  null. That is more careful than most trade commentary on "issuer quality".

## Checked and found right

- Loan counts equal the issuers' at closing for Exeter 2025-1 (65,321), CarMax 2025-1 (82,495), CarMax 2026-2 (52,812).
- Exeter 2025-1 cumulative gross charge-off dollars at four ages, against the issuer's static pool table.
- Every published 12-month cell in 660-759 and the five bucket ratios (9.0, 10.0, 15.6, 17.1, 16.3) reproduce.
- The 1.7 times lender spread at 540-599 is in line with the CFPB's 2 to 2.7 times at subprime scores.
- Signs of loan amount, payment-to-income, rate and term agree with Klee and Shin.
- Card July 2026 loss, payment-rate and yield values for all six trusts against the raw exhibits (Citi's label aside).
- The estimator (left truncation, competing risks, discrete time) is the one the statistical literature uses.

## Not checked

- Trustee cumulative net loss for Toyota 2025-A, Capital One 2025-1, CarMax 2026-2, Santander 2026-1 and AmeriCredit
  2024-1 at July 2026, and Santander 2025-1 and Honda 2025-1 from the documents themselves: EDGAR refused the
  project's User-Agent without its contact secret, issuer investor pages returned 404, and filing mirrors refused.
  The Honda count gap (6-7%) needs the servicer report's definition of a loss contract.
- S&P, Fitch and KBRA card indices for 2026 and S&P's 2026 auto tracker: spglobal.com returned 403 and the shared web
  search budget was exhausted before these searches ran.
- Rating-agency presale expected losses for the ten deals.
- Whether CMXS holds CarMax loans at 660 and above in volume (it files ABS-EE; needs a fetch on the runner).
- Santander's score model: its 424B5 is "not yet read" in `data/deals.csv`, and the "9 times without Exeter" figure
  rests on that score being on CarMax's scale.
- The exact bypass share behind abs-B-2 by trust and month.
