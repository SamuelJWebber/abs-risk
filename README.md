# abs-risk

Two questions about consumer credit risk, answered only from public SEC filings and regulator reports.

1. **Cards, pool level.** Do issuers with the same FICO mix charge off differently? Card master trust
   prospectuses give each pool's FICO and credit-limit distribution; monthly 10-D reports give charge-offs,
   payment rates and delinquency. Published loss-by-tier shapes, calibrated to the CFPB's aggregate level,
   turn the mix into a predicted loss; the residual is the issuer effect at constant score mix.
2. **Autos, loan level.** Public auto ABS file monthly loan-level data (Form ABS-EE, exhibit 102): credit
   score, amount, rate, term, payment-to-income, delinquency status, charge-off, per loan, per month, per
   lender. Same-score comparisons across lenders, loan size against default at constant score, and
   regression discontinuity at lenders' own score cutoffs.

Status (2026-11-09): both tracks have published results at https://samueljwebber.github.io/abs-risk/ .
HANDOFF.md says what is true now and what is verified; TASKS.md is the board; PLAN.md the design;
design/methods.md what each estimate can carry. Card data refreshes twice a week (Mondays and Thursdays) through `.github/workflows/cards-refresh.yml`.

    python -m uv sync                      # install
    python -m uv run pytest                # all tests, fixtures only, never EDGAR
    python -m uv run absrisk analyze autos # Track B results from the committed loans tables (~30 min)
    python -m uv run absrisk analyze cards # Track A results (~20 s); then `absrisk report cards|conclusions`
    python -m uv run absrisk report autos  # docs/autos.html
