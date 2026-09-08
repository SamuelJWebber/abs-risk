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

## 2. The hazard ladder (Track B)

Discrete-time competing risks: one row per loan-month, two binomial logits (charge-off, prepay) on aggregated
cells, standard errors clustered by deal. Four specifications, each adding one layer:

| spec | adds | answers |
|---|---|---|
| raw | loan age | the gap as it appears, composition included |
| score | bureau score bucket | same score, different lender |
| terms | origination quarter, amount, payment-to-income, loan-to-value | same score, same loan structure |
| price | the lender's own APR quintile | same score, same structure, same price |

**`terms` is the main result; `price` is a decomposition, not a better control.** The lender sets APR from its
private read of the borrower, so APR is a mediator of lender differences, not a confounder. Conditioning on a
mediator answers a narrower question and can create collider bias. It is reported because what it does is itself
a finding: adding APR collapses the bureau score's own gradient almost to nothing, which says the lender's price
contains nearly all of the score's predictive content and more.

**What the lender coefficient is not.** It is not a causal effect of switching lender. Lenders differ in the
borrowers they attract, in what they know beyond the bureau score, in servicing and collections, and in which
loans they put into a public deal. The coefficient carries all of that.

**Clustering by deal is the honest floor.** With ten deals, cluster-robust intervals are wide, and they should
be: the unit of independent variation here is closer to a deal than a loan.

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
