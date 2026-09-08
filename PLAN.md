# abs-risk — Plan (v0, methodology only; data specifics land after scouting)

**Status:** scouting, 2026-09-08. Scouting notes: design/scout-cards.md, design/scout-autos.md,
design/scout-ccmr-tiers.md. Task board: TASKS.md.

## 0. Context

The question that started this: can second-order credit risk, the risk created by the lender's own action
(line, price, product) and the borrower's response to it, be estimated from public data? The strict version,
two cards on one person with their lines and outcomes, cannot: Regulation AB II exempted credit card ABS from
loan-level disclosure, and Y-14M and the credit panels are private. Two honest neighbours can:

1. **Cards, pool level.** Do issuers with the same FICO mix charge off differently, and by how much?
2. **Autos, loan level.** At the same credit score, how do loan size, rate, payment-to-income and lender change
   default? Public auto ABS file loan-level data monthly, with the lender's own score cutoffs visible.

Separate from the credit-card-data dashboard. That one shows the market; this one tests claims.
Same person, same tooling (Python, uv, DuckDB, static HTML on GitHub Pages), same rules: no paid data, no
server, no LLM in the numeric path, ignored for six months it is still correct or visibly wrong.

## 1. Goal and non-goals

**Goal.** Two published analyses, each a static page with the data and code behind it, that a card or auto
risk person could check line by line, plus a monthly refresh so the numbers stay current.

**Non-goals.** No payment-hierarchy claim (nothing public identifies it; say so on the page). No causal claim
from the pool-level card residual (it mixes underwriting, product, customer mix within a score band, pool
selection and behaviour). No account-level card modelling. No forecasting in v1.

## 2. Track A: card master trust pools

**Estimand.** For trust *t* in month *m*, the issuer effect at constant score mix:

    residual(t, m) = actual_chargeoff(t, m) - sum_over_tiers( share(t, tier) * loss_curve(tier, year(m)) )

- `actual_chargeoff` from the trust's monthly 10-D (annualised net or gross, whichever every trust reports;
  the choice is recorded per trust and never mixed).
- `share(t, tier)` from the trust's most recent prospectus FICO distribution, mapped to CFPB tiers.
  Prospectus buckets differ by trust; the crosswalk is explicit (crosswalks/fico_buckets.csv) and any bucket
  that straddles a tier boundary is split by a stated rule, with the sensitivity shown.
- `loss_curve(tier, year)` from the CFPB Consumer Credit Card Market Report figure data (annualised
  charge-off by tier, by year), the one public loss-by-tier curve for US cards.

**Outputs.** Per trust: actual vs predicted charge-off over time, the residual, and the same for payment
rate and 30+ delinquency where the prospectus mix allows. A cross-trust chart of residual against pool
credit-limit mix, labelled as descriptive.

**What the residual can and cannot say.** It can say "Trust X loses more than its FICO mix predicts, by Y
points, consistently since Z." It cannot say why. The page carries that sentence.

**Known hazards.** Trust pools are selected, seasoned accounts, not the issuer's book. Prospectus FICO is a
snapshot (refreshed score, as of a date) and pools are refreshed by account additions. Amex pools are lending
receivables only. Trusts report charge-offs on different bases (gross vs net, principal vs total receivables).
Each hazard gets a scope note on the page and a row in checks/.

## 3. Track B: auto loan-level ABS

**Data.** Form ABS-EE exhibit 102, filed monthly per trust, one record per loan: credit score (and score
type), original amount, rate, term, payment-to-income, vehicle value and new/used, origination date, state,
current delinquency status, zero-balance code (payoff, charge-off, repurchase), charge-off amount, recoveries.
Same asset number across months, so a loan-month panel is buildable. Lenders span prime to deep subprime.

**Three questions, in order of how clean the identification is.**

1. **Descriptive, same score, different lender.** Cumulative default by origination cohort, by 20-point score
   bucket, by lender. The public version of "Amex vs Capital One at the same FICO", in autos.
2. **Loan size and payment burden at constant score.** Default against original amount and payment-to-income
   within score bucket and lender, with cohort fixed effects. Descriptive with controls, not causal.
3. **Regression discontinuity at the lender's own cutoffs.** Lenders price by score tier; where APR jumps at
   a score threshold, compare loans just above and below. That is the published card design (credit-limit
   cutoffs, Agarwal et al. 2018) run on public data. Requires: a visible jump in rate or amount at the cutoff,
   enough loans within the bandwidth, no manipulation of the running variable (density test).

**Outputs.** A page per question with the chart, the table, the N, and the code path that made it. A loan-month
parquet panel under data/ (not committed if large; rebuilt from raw filings by one command).

**Known hazards.** Scores may be masked or bucketed by some issuers (scouting checks this). Files are large;
subprime deals run to 100k+ loans per month. Charge-off timing conventions differ by lender. Prepayment and
repurchase compete with default and must be treated as censoring, not as survival.

## 4. Storage and refresh

- Raw filings under data/raw/<track>/<trust-or-deal>/<accession>/, never committed, re-downloadable.
- Derived tables small enough to commit under data/; large panels as parquet under data/panel/ (gitignored)
  with a manifest that records the filings they came from.
- One command per track: `absrisk cards refresh`, `absrisk autos refresh`. Monthly GitHub Actions run once
  both tracks have a fixture test and a golden check; not before.
- Golden checks (checks/golden.yaml): numbers traced to a filing page or a CFPB table, re-verified each run.

## 5. Open until scouting completes

- Which trusts report which charge-off basis; which prospectuses give FICO by balances vs by accounts.
- Whether auto issuers report real credit scores; which fields are populated; asset-number persistence.
- The CFPB figure-data workbooks: exact tier definitions and the years covered.
- Contact address for the EDGAR User-Agent: the SEC asks for one. Set ABSRISK_CONTACT before any refresh runs
  unattended; the session code appends it.
