# Methods: what each estimate can carry

Written 2026-09-08 alongside the first real results. Companion to design/analysis-plan.md, which states the
specifications; this file states what they mean and where they break.

## 0. The question, and why it is answered sideways

The question was payment hierarchy: which debt does a person pay first, and does a bigger line change that.
Answering it needs one person observed across two products with both balances, both limits, and both outcomes.
No public dataset has that. Regulation AB II exempted credit card ABS from loan-level disclosure, the credit
panels (CFPB CCIP, NY Fed CCP) are confidential, and Y-14M is supervisory. So the page never claims a hierarchy
estimate. It answers the two questions public data can carry:

- **Autos, loan level.** At the same credit score, does the lender matter, and does loan size or payment burden
  matter? This is the same shape of question as "Amex versus Capital One at the same FICO and line", in the one
  consumer product where loan-level data is public.
- **Cards, pool level.** Does a trust charge off more than its own score mix predicts?

## 1. The survival clock (Track B)

**Age is months since origination, not months since the file first shows the loan.** Auto ABS pools are seasoned
at formation: the median loan in these ten deals is 3 to 13 months old when its deal's first ABS-EE lands, and
the 90th percentile runs to 65 months. Counting from first appearance would line up a 2-month-old Santander loan
with a 5-year-old AmeriCredit loan at "age 1" and compare them.

**Delayed entry (left truncation).** A loan is in the risk set only at ages it was actually observed:
`entry_age <= t <= exit_age`. Ignoring this inflates early hazards, because loans that had already defaulted
before the pool formed are not in the file at all.

**Pool cutoff lag.** A deal's first file often carries exits dated the month before its own period end: the loan
left between the pool cutoff and the first report. When that happens, every loan in the first file is taken to
have entered one month earlier. Without it those exits look like events before entry.

**Exit dating.** The event month is the sponsor's own zero-balance effective date when given, else the first
period carrying a zero-balance code. For sponsors that keep closed loans in the file forever (CarMax, Capital
One, Exeter), the first period carrying a code is the first file, not the event; the zero-balance date fixes that
for 220 to 10,920 loans per deal.

**Competing risks.** A loan that pays off cannot later charge off. Aalen-Johansen cumulative incidence treats
prepayment, repurchase and disappearance as competing exits; the Kaplan-Meier curve treats them as censoring and
is always higher. Both are published. The gap between them is the prepayment effect, and it is large for the
captives, whose borrowers refinance and trade in faster.

**Uncertainty.** 95 percent percentile bootstrap over loans, 200 resamples. It is not clustered, so it understates
uncertainty where a cell is one deal (which is most cells at the extremes of score).

**Survivor selection.** A seasoned loan is in a pool because it survived to the cutoff, and lenders differ in how
they select loans into deals. The fresh-entrant cut (first seen within six months of origination) is published
next to the full table for that reason. Where they agree, seasoning is not driving the comparison.

**Vintage (added 2026-11-09).** Each lender's public pools hold one or two origination years, and vintages differ
across the industry, so a pooled lender gap could be a vintage gap. The test compares the same two lenders in the
same 20-point bucket inside one origination year against their pooled ratio (`pair_ratios`, page section 2). If
vintage drove the gap, the within-year ratio would sit nearer one. Result: a median 1.00 of the pooled ratio over
67 pairs (64 in the 2024 vintage, 3 in 2025; no other year has two lenders in one usable bucket); the seven pairs more
than ten times apart pooled are 34 times apart inside 2024 against 38 pooled. The one pair that moves is Exeter
against AmeriCredit at 620 (1.9 within 2024 against 3.8 pooled), because AmeriCredit's pool is the 2023 vintage.

**Score scale.** Exeter's "Consumer Credit Bureau" score is VantageScore for 98.9% of its pool (its 424B5,
design/scout-autos.md section 8); every other lender reports a bureau score that is FICO where it says which. A 700
there and a 700 at Honda are close but not the same number. The headline same-bucket ratio is therefore also
reported without Exeter: a median 38 times across seven buckets, against 50 with it. Exeter is not the only scale
issue (REVIEW.md R1-8): Toyota, Honda, CarMax, Capital One and Santander report scores above 850 (12.7%, 11.6%,
7.3%, 2.5% and 0.6% of loans), which only the 250-900 auto-industry FICO scale allows, while AmeriCredit tops out at
854 and Exeter at 845. Restricted to those five, the median is again 38 times over the same seven buckets: the one
lender off that scale besides Exeter is never the highest or the lowest in them.

## 2. The hazard ladder (Track B)

Discrete-time competing risks: one row per loan-month, two binomial logits (charge-off, prepay) on aggregated
cells. Every specification holds loan age and **months in pool** fixed: a loan must be current to be sold into a
trust, so its first months in the pool have charge-off odds about an eighth of a seasoned loan's (odds ratio 0.13
for months 0-2), and a young deal is mostly such months. Before 2026-11-09 this was missing, which made young deals
look safer and two deals of one lender look further apart than they are. Score buckets and origination quarters
with too few loans at either end are merged into their neighbours (under 500 loans; they once printed odds ratios
near 1e-10 with p near 1e-200), and a level that still has no events is left blank. Four specifications, each adding
one layer:

| spec | adds | answers |
|---|---|---|
| raw | loan age | the gap as it appears, composition included |
| score | bureau score bucket | same score, different lender |
| terms | origination quarter, amount, payment-to-income, loan-to-value | same score, same loan structure |
| price | the lender's own APR quintile | same score, same structure, same price |

**`terms` is the main result; `price` is a decomposition, not a better control.** The lender sets APR from its
private read of the borrower, so APR is a mediator of lender differences, not a confounder. Conditioning on a
mediator answers a narrower question and can create collider bias. It is reported because what it does is itself
a finding: adding APR flattens the bureau score's own gradient (scores 500-599 against 760-839) from about 6.8
times to about 4.0 times in monthly charge-off odds, removing roughly a quarter of it in log odds. The lender's price
carries part of the score's predictive content and more; the score keeps most of its own.

**What the lender coefficient is not.** It is not a causal effect of switching lender. Lenders differ in the
borrowers they attract, in what they know beyond the bureau score, in servicing and collections, and in which
loans they put into a public deal. The coefficient carries all of that.

**Inference with ten deals.** The unit of independent variation is closer to a deal than a loan, so intervals
are clustered by deal, with t critical values on nine degrees of freedom. That is not enough for the lender
coefficients (REVIEW.md R1-6): AmeriCredit, Capital One, Honda and Toyota each own one deal, so the lender dummy
coincides with one cluster and the sandwich carries no between-deal variance for it. In a simulation with deal
shocks (`tests/test_autos_inference.py`) such an interval covered the truth about half the time. Lender intervals
on the page therefore add the deal-to-deal spread, measured where it can be seen, between the two deals of each
lender that has two (CarMax, Exeter, Santander: three degrees of freedom), with t critical values
(`hazard.deal_spread_intervals`, `b2_lender_intervals.csv`). In the simulation those cover about 93% of the time. On
the data the spread is about 0.33 in log odds in the terms specification; with it, Honda (0.15 [0.04, 0.61]), Toyota
(0.19 [0.05, 0.77]) and CarMax (0.23 [0.06, 0.89]) stay distinguishable from Santander, and Capital One (0.36),
AmeriCredit (0.75) and Exeter (1.10) do not. The assumption doing the work is that deal shocks are alike across
lenders; with one deal, nothing else can say how lucky a lender's deal was.

## 3. Regression discontinuity (Track B)

The only design here that can carry a causal sentence, and only where it passes three screens:

1. **First stage.** APR or loan amount jumps at the score, holding the trend on each side. A cutoff with no jump
   in terms is not a pricing cutoff.
2. **Density.** The running variable must not bunch at the line (rddensity, jackknife when scores have mass
   points, which they always do). A pile-up on the good side means the pool was selected there: an approval or
   securitization threshold, not a pricing step. Those are reported and excluded.
3. **Stability.** The jump keeps its sign and significance at 0.6 and 1.4 times the bandwidth. A wiggle in a noisy
   variable flips; a pricing step does not.

Known non-cutoffs, excluded by name: CarMax's 650 floor, Toyota's 620 floor, and the 640 cliffs at Exeter and
AmeriCredit, which are securitization eligibility, documented in the prospectuses.

Outcomes are restricted to loans first observed within six months of origination, so that survival-to-entry does
not select the two sides of the line differently.

**Expected outcome, stated in advance: mostly nulls.** These pools have tens of thousands of loans, not millions,
and 24-month charge-off differences of a percentage point need more. A null RD with a clean first stage is
reported as a null, not dropped.

**Result, 2026-11-09.** Sixteen candidate cutoffs; eight fail the density test; seven pass it and have a first stage
in APR or loan amount. Each of the seven was refitted at 0.5, 0.75, 1, 1.5 and 2 times its MSE-optimal bandwidth
(`rd.rd_bandwidth_sensitivity`, `data/results/autos/b3_rd_bandwidths.csv`). None of the fourteen cutoff-and-horizon
estimates clears zero with a bias-corrected robust interval at the optimal bandwidth, and none keeps one clear of
zero at every bandwidth; across the 56 off-optimal refits, four clear zero (Honda 605 at 12 and 24 months and Honda
700 at 24 months at twice the bandwidth, Santander 725 at 12 months at half), about the three chance would give. The
closest, Honda at 700 over 24
months, is +2.0 to +2.6 points at every bandwidth but clears zero only at twice the bandwidth (robust p 0.07 at the
optimal one). The design answers with a null, as expected in advance.

## 4. Shape times level (Track A)

No public source gives card charge-off by score tier. The CFPB says why in its own footnotes: tiering by current
score is endogenous to delinquency, so it withholds the cross-tab. The prediction is therefore built as a shape
(relative loss by tier, from a published source) times a level (calibrated so the CFPB's own tier mix reproduces
the CFPB's own aggregate rate that year).

Four shapes are carried, and they disagree by a factor of five:

- Consumer-level bad rates (FICO odds via Experian; Fed 2007 Table 2, Fair Isaac): deep subprime is 5 to 6 times
  prime.
- Card-level charge-off among accounts already issued (ACMS 2018 Table IV, OCC Credit Card Metrics): deep
  subprime is about 1.2 times prime.

That gap is not an error to resolve. It is what card lenders do: they issue small lines at high prices to low
scores, so realised loss per dollar compresses even though the people default far more often. Every trust result
is published under each shape, and if the ranking of trusts changes with the shape, that is the finding.

## 5. What the card residual cannot say

The residual mixes underwriting, product, customer mix within a score band, pool selection, servicing, and
borrower behaviour. It can say "this trust loses more than its score mix predicts, by this much, consistently."
It cannot say why, and it cannot be turned into a payment-hierarchy statement. Trust pools are also selected,
seasoned accounts, not the issuer's book, and the mix is a prospectus snapshot held fixed between prospectus
dates.

## 6. Comparability caveats carried in the data

- Score types differ by lender: FICO at Capital One, FICO Score 8 Auto at Toyota, unnamed bureau scores elsewhere,
  VantageScore at Exeter. They are not the same scale, so "the same score" across lenders is an approximation and
  the score type is printed next to every lender.
- Payment-to-income is a fraction at every sponsor except Capital One, which reports percent; normalised on load,
  with the rule recorded per file.
- Card charge-off bases differ by trust (beginning, average, ending, invested amount) and annualisation differs
  (times twelve, times 365 over days, actual over 365). Kept as reported, never mixed.
- Citi publishes no net charge-off and no dollar charge-off row, only a gross rate component.
- Synchrony's prospectus score is VantageScore, Chase's FICO table is a 5 percent sample, and Amex's buckets do
  not align to the six tiers. All three are flagged in the crosswalk.

## 7. Selection or protection: the entry and roll split

The question the project exists for is whether a lender's lower losses at the same score mean it picked better
borrowers or that borrowers protect that account. Charge-off levels cannot separate those: both stories predict
the same lower number. Where they differ is which stage of default the advantage sits in.

    charge-off  =  P(reach 30 days past due)  x  P(charge off | reached 30 days past due)
                        entry                              roll

- **Selection** means the borrower is less likely to get into trouble at all. It moves `entry` and leaves `roll`
  alone: once behind, the account should resolve like anyone else's.
- **Protection**, whether from the borrower ranking that debt first, from harder collections, or from collateral
  the borrower cannot lose, moves `roll`. The borrower gets into trouble at the normal rate and the account
  survives it.

Taking logs makes the split additive, so each lender's gap against the baseline divides into an entry share and
a roll share that sum to one. The product approximates the charge-off rate rather than equalling it (REVIEW.md
R1-13): a charge-off never recorded 30 days late, a bankruptcy-type event coded straight to charge-off, is a
competing exit in the entry stage and sits in neither factor. That is 75% of Capital One's charge-offs and at most 6.5%
at every other lender, so `b6_*.csv` carry the share (`co_without_30_share`) and mark Capital One's split as not
holding.

**The roll comparison is the trustworthy half.** It conditions on an observed behaviour, being 30 days late,
rather than on a reported score. These lenders use different score models on different scales (FICO Score 8 Auto
at Toyota, an unnamed bureau score at Santander, VantageScore at Exeter), so an entry comparison "at the same
score" is partly a comparison of score scales. Conditioning on delinquency removes that.

**What it can and cannot conclude.** A lender whose gap is all entry has no protection effect to speak of: that
is what a null roll ratio means, and it rules out the simplest protection story. A lender whose gap is in the
roll has something happening after trouble starts, but the design cannot say whether that is the borrower's
ranking of debts, the servicer's collections, or the collateral. Separating those needs one person observed
across two lenders, which no public data provides.

**Applied to cards.** The same split runs on trust-level delinquency buckets: the flow into 30 days late against
the flow from 30 days to charge-off. It is dollar-weighted and coarser than the loan-level version, and bucket
edges differ by trust, so only the 30-plus and 90-plus cuts are comparable. On the trust data the identity has three
factors, entry (30+ share) x progression (90+ / 30+) x conversion (monthly charge-off / 90+), and the trust averages
are geometric means so that the averages multiply back exactly and the three shares of a gap sum to one.

The stress interaction is the second test: if borrowers really rank debts, a trust whose accounts are ranked first
should see its conversion ratio fall when households are squeezed. "Squeezed" has to come from the data, not from a
calendar label: until November 2026 the test compared "pre-covid 2019" with a "squeeze 2023H2 on" in which every
trust's 30+ share was lower (REVIEW.md R1-4). It now splits months by a delinquency index (each trust's 30+ share over
its own average, averaged across trusts; above the median is tight) and also reports the one step between named
periods that raised every trust's 30+ share. The result is mixed: in tight months the ratio fell for Amex, the
lowest-loss trust, and rose for Citi; across the one clean tightening it fell for BofA and COMET. Conversion is a
flow over a stock that builds ahead of the charge-offs, so it falls whenever delinquency is rising, whoever is paid
first; the level comparison carries the argument and this test neither confirms nor overturns it.
