"""Estimators for both tracks (design/analysis-plan.md §2 and §4).

survival:  cumulative incidence of charge-off with prepayment as a competing risk (Aalen-Johansen) and the
           Kaplan-Meier version that treats it as censoring; by score bucket and lender.
hazard:    discrete-time competing-risks hazard on the loan-month expansion, fitted as two binomial GLMs on
           aggregated cells with standard errors clustered by deal.
rd:        regression discontinuity at lender score cutoffs: cutoff search, density test, local-linear estimate.
cards:     shape-times-level prediction and the trust-month panel regression with Driscoll-Kraay errors.
"""
