# abs-risk

Two questions about consumer credit risk, answered only from public SEC filings and regulator reports.

1. **Cards, pool level.** Do issuers with the same FICO mix charge off differently? Card master trust
   prospectuses give each pool's FICO and credit-limit distribution; monthly 10-D reports give charge-offs,
   payment rates and delinquency. A common loss-by-tier curve (CFPB) turns the mix into a predicted loss;
   the residual is the issuer effect at constant score mix.
2. **Autos, loan level.** Public auto ABS file monthly loan-level data (Form ABS-EE, exhibit 102): credit
   score, amount, rate, term, payment-to-income, delinquency status, charge-off, per loan, per month, per
   lender. Same-score comparisons across lenders, loan size against default at constant score, and
   regression discontinuity at lenders' own score cutoffs.

Status: scouting (2026-09-08). See design/ for what was found and PLAN.md / TASKS.md once written.
