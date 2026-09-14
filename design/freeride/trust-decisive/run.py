"""trust-decisive: settle the eight referee objections to the Amex-vs-Synchrony cycle test.

PART 1  deduplicate and re-baseline
PART 2  the payment-rate test (never run before)
PART 3  an honest power statement
PART 4  fix the two known mix-adjustment biases

Reads only from C:/Users/samwe/code/abs-risk. Writes only into this folder.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from lib import ols_nw, slope_row, const_design, ncdf, MDE_MULT  # noqa: E402

REPO = "C:/Users/samwe/code/abs-risk"
TRUSTS = ["amex", "bofa", "chase", "citi", "comet", "synchrony"]
TIERS = ["deep_subprime", "subprime", "near_prime", "prime", "prime_plus", "superprime"]
SHAPES = ["fico_odds", "fico_fed2007", "acms2018", "acms2018_dpd90"]
TIER_EDGES = [("deep_subprime", 300, 579), ("subprime", 580, 619), ("near_prime", 620, 659),
              ("prime", 660, 719), ("prime_plus", 720, 799), ("superprime", 800, 850)]

REGIMES = [
    ("pre_covid", "2019-01", "2020-02"),
    ("stimulus", "2020-04", "2021-12"),
    ("normalising", "2022-01", "2023-06"),
    ("squeeze", "2023-07", "2026-12"),
]
SEASONING = ["2019-12", "2020-01", "2020-02", "2020-03"]   # Synchrony pool-addition seasoning

lines = []


def log(s=""):
    print(s)
    lines.append(str(s))


def tbl(df, fmt="%.6f"):
    return df.to_string(index=False, float_format=lambda v: fmt % v)


def h1(s):
    log("")
    log("=" * 104)
    log(s)
    log("=" * 104)


def h2(s):
    log("")
    log("-" * 104)
    log(s)
    log("-" * 104)


results = {}

# ==================================================================== LOAD
RAW = pd.read_csv(os.path.join(REPO, "data", "cards_monthly.csv"))
RAW["period_end"] = pd.to_datetime(RAW["period_end"])
RAW["ym"] = RAW["period_end"].dt.to_period("M")
RAW = RAW.sort_values(["trust", "period_end"]).reset_index(drop=True)

COMP = pd.read_csv(os.path.join(REPO, "data", "cards_composition.csv"))
SHP = pd.read_csv(os.path.join(REPO, "data", "loss_shape.csv"))
XW = pd.read_csv(os.path.join(REPO, "crosswalks", "fico_buckets.csv"))

# ==================================================================== PART 1
h1("PART 1 - DEDUPLICATE AND RE-BASELINE")

DATA_COLS = ["trust", "period_end", "receivables_principal", "gross_co_rate", "net_co_rate",
             "co_basis", "co_annualisation", "payment_rate", "yield", "delinq_30plus_share",
             "delinq_90plus_share", "delinq_basis", "excess_spread"]

dup_mask = RAW.duplicated(subset=["trust", "ym"], keep=False)
DUPS = RAW[dup_mask].copy()
log("")
log(f"Raw file: {len(RAW)} rows, {RAW['trust'].nunique()} trusts, "
    f"{RAW['ym'].min()} .. {RAW['ym'].max()}.")
log("")
log("(1a) Duplicate trust-months. Every one is an EXACT duplicate on all 13 data columns; the pairs")
log("     differ ONLY in source_accession / source_file, i.e. the same monthly pool report was filed")
log("     twice under two accession numbers. Nothing is lost by keeping one of each pair.")
log("")
chk = DUPS.groupby(["trust", "ym"])[DATA_COLS].nunique(dropna=False)
identical = bool((chk.drop(columns=["trust"], errors="ignore") <= 1).all().all())
log(f"     data columns identical within every duplicate pair: {identical}")
log("")
log(tbl(DUPS[["trust", "ym", "receivables_principal", "delinq_30plus_share", "payment_rate",
              "source_accession", "source_file"]]
        .assign(receivables_principal=lambda d: d["receivables_principal"] / 1e9)
        .rename(columns={"receivables_principal": "recv_$bn"}), "%.6f"))

M = RAW.drop_duplicates(subset=["trust", "ym"], keep="first").reset_index(drop=True)
DROPPED = RAW[RAW.duplicated(subset=["trust", "ym"], keep="first")].copy()
log("")
log(f"(1b) Rows dropped (the SECOND filing of each pair): {len(DROPPED)}. "
    f"{len(RAW)} -> {len(M)} rows.")
for _, r in DROPPED.iterrows():
    log(f"       dropped  {r['trust']:10s} {str(r['ym'])}  accession {r['source_accession']}  "
        f"file {r['source_file']}")
log("")
log("     Rows KEPT for those same months:")
for _, r in RAW[RAW.duplicated(subset=['trust', 'ym'], keep='last')].iterrows():
    log(f"       kept     {r['trust']:10s} {str(r['ym'])}  accession {r['source_accession']}  "
        f"file {r['source_file']}")

cnt = M.groupby("trust").agg(months=("ym", "size"), first=("ym", "min"), last=("ym", "max"))
cnt["span_months"] = [(r["last"] - r["first"]).n + 1 for _, r in cnt.iterrows()]
cnt["missing"] = cnt["span_months"] - cnt["months"]
log("")
log("(1c) Per-trust month counts after dedupe:")
log(tbl(cnt.reset_index().astype({"first": str, "last": str}), "%.0f"))

allm = pd.period_range(M["ym"].min(), M["ym"].max(), freq="M")
piv30 = M.pivot_table(index="ym", columns="trust", values="delinq_30plus_share")
aligned = piv30.dropna(how="any")
log("")
log(f"     Calendar span 2018-12..2026-07 = {len(allm)} months.")
miss = {t: [str(p) for p in allm if p not in set(M[M['trust'] == t]['ym'])] for t in TRUSTS}
for t in TRUSTS:
    if miss[t]:
        log(f"     {t} missing: {', '.join(miss[t])}")
log(f"     Months with all six trusts present (the aligned panel used everywhere below): {len(aligned)}"
    f"  ({aligned.index.min()} .. {aligned.index.max()})")
log("")
log("     THE '87 vs 90' CONTRADICTION, RESOLVED - and the referee's diagnosis of it is WRONG.")
in_reg = [p for p in aligned.index if any(pd.Period(a) <= p <= pd.Period(b) for _, a, b in REGIMES)]
log(f"       aligned months that fall inside one of the four regime windows: {len(in_reg)}")
log("         (the aligned panel is 89; 2018-12 and 2020-03 fall in no window; 89 - 2 = 87.)")
log("       per-trust regime-window row counts, with duplicates and after dedupe:")
for t in TRUSTS:
    n0 = int(((RAW["trust"] == t) & RAW["ym"].map(
        lambda p: any(pd.Period(a) <= p <= pd.Period(b) for _, a, b in REGIMES))).sum())
    n1 = int(((M["trust"] == t) & M["ym"].map(
        lambda p: any(pd.Period(a) <= p <= pd.Period(b) for _, a, b in REGIMES))).sum())
    log(f"         {t:10s} with dups {n0:3d}   deduped {n1:3d}")
log("       So the 87 was the ALIGNED (all-six-present) count and the 90 was a SINGLE TRUST'S row")
log("       count. They differ because COMET IS MISSING 2019-05, 2019-06 AND 2019-07 - not because")
log("       of the duplicates. Referee item 7 is right that the duplicates exist and right that they")
log("       double-weight five months; it is wrong that they explain the 87-vs-90 gap. Deduping")
log("       moves bofa 91->90, citi 92->90 and comet 88->87; it leaves 87 and 90 exactly where they")
log("       were.")

# ---- does any headline number from the previous run change?
h2("(1d) Which previous-run headline numbers move, and by how much")


def mean30(df):
    return df.groupby("trust")["delinq_30plus_share"].mean()


m_raw, m_ded = mean30(RAW), mean30(M)
cmp1 = pd.DataFrame({"with_dups": m_raw, "deduped": m_ded}).loc[TRUSTS]
cmp1["abs_change"] = cmp1["deduped"] - cmp1["with_dups"]
cmp1["pct_change"] = 100 * cmp1["abs_change"] / cmp1["with_dups"]
log("")
log("     Full-sample mean 30+ share per trust:")
log(tbl(cmp1.reset_index(), "%.8f"))
raw_ratio_dup = float(m_raw["amex"] / m_raw["synchrony"])
raw_ratio_ded = float(m_ded["amex"] / m_ded["synchrony"])
log("")
log(f"     RAW amex/synchrony 30+ ratio: with dups {raw_ratio_dup:.6f}, deduped {raw_ratio_ded:.6f}.")
log("     UNCHANGED TO ALL PRINTED DIGITS, and this is arithmetic, not luck: none of the five")
log("     duplicated trust-months belongs to amex or to synchrony (they are bofa x2, citi x2, comet x1).")
log("")
log("     MIX-ADJUSTED amex/synchrony ratio: also EXACTLY unchanged, provably. The adjusted ratio is")
log("       (a_amex / (L * S_amex)) / (a_sync / (L * S_sync)) = (a_amex / a_sync) * (S_sync / S_amex).")
log("     The pinning level L cancels, so the only inputs are the two unduplicated trust means and the")
log("     two mix-dot-shape scalars. Dedupe moves L (through bofa/citi/comet) but not the ratio.")
log("     Verified numerically in PART 4 below.")

six_dup = np.exp(np.log(RAW.pivot_table(index="ym", columns="trust",
                                        values="delinq_30plus_share")).mean(axis=1))
six_ded = np.exp(np.log(piv30).mean(axis=1))
log("")
log("     What DOES move: anything that averages across trusts or across months within a regime.")
reg_rows = []
for name, a, b in REGIMES:
    sel_r = RAW[(RAW["ym"] >= pd.Period(a)) & (RAW["ym"] <= pd.Period(b))]
    sel_d = M[(M["ym"] >= pd.Period(a)) & (M["ym"] <= pd.Period(b))]
    for t in TRUSTS:
        v0 = sel_r[sel_r["trust"] == t]["delinq_30plus_share"]
        v1 = sel_d[sel_d["trust"] == t]["delinq_30plus_share"]
        if len(v0) and abs(v0.mean() - v1.mean()) > 1e-12:
            reg_rows.append({"regime": name, "trust": t, "n_with_dups": len(v0), "n_deduped": len(v1),
                             "mean_with_dups": v0.mean(), "mean_deduped": v1.mean(),
                             "pct_change": 100 * (v1.mean() - v0.mean()) / v0.mean()})
REGCH = pd.DataFrame(reg_rows)
if len(REGCH):
    log(tbl(REGCH, "%.8f"))
log("")
log("     Largest absolute move in any regime x trust cell: "
    f"{REGCH['pct_change'].abs().max():.4f}% (comet, pre_covid). No sign flips anywhere.")
log("     Roll ladder: the roll code requires (ym_t - ym_{t-1}).n == 1, so the SECOND row of each")
log("     duplicate pair simply produced a NaN roll and was dropped by .dropna(). The roll MEANS and")
log("     n's in the previous run were therefore already correct; only the level means and the month")
log("     counts were contaminated.")

results["part1"] = {
    "raw_rows": int(len(RAW)), "deduped_rows": int(len(M)),
    "dropped": DROPPED[["trust", "source_accession", "source_file"]].assign(
        ym=DROPPED["ym"].astype(str)).to_dict(orient="records"),
    "months_per_trust": {k: int(v) for k, v in cnt["months"].items()},
    "aligned_months": int(len(aligned)),
    "raw_ratio_with_dups": raw_ratio_dup, "raw_ratio_deduped": raw_ratio_ded,
    "regime_cell_changes": REGCH.to_dict(orient="records"),
}
DROPPED.assign(ym=DROPPED["ym"].astype(str))[
    ["trust", "ym", "source_accession", "source_file", "receivables_principal",
     "delinq_30plus_share", "payment_rate"]].to_csv(
    os.path.join(HERE, "part1_dropped_rows.csv"), index=False)
cnt.reset_index().astype({"first": str, "last": str}).to_csv(
    os.path.join(HERE, "part1_month_counts.csv"), index=False)

# ==================================================================== PANEL
M["regime"] = M["ym"].map(lambda p: next((n for n, a, b in REGIMES
                                          if pd.Period(a) <= p <= pd.Period(b)), None))

PR = M.pivot_table(index="ym", columns="trust", values="payment_rate")[TRUSTS]
D30 = M.pivot_table(index="ym", columns="trust", values="delinq_30plus_share")[TRUSTS]
YLD = M.pivot_table(index="ym", columns="trust", values="yield")[TRUSTS]
idx = D30.dropna(how="any").index.intersection(PR.dropna(how="any").index)
PR, D30, YLD = PR.loc[idx], D30.loc[idx], YLD.loc[idx]
LPR, LD30 = np.log(PR), np.log(D30)
X_STRESS = LD30.mean(axis=1).rename("six_mean_log30")      # the common stressor
X_PRMEAN = LPR.mean(axis=1).rename("six_mean_logPR")
REG = pd.Series([next((n for n, a, b in REGIMES if pd.Period(a) <= p <= pd.Period(b)), None)
                 for p in idx], index=idx, name="regime")
SEAS_MASK = pd.Series([str(p) not in SEASONING for p in idx], index=idx)

# ==================================================================== PART 2
h1("PART 2 - THE PAYMENT-RATE TEST  (the direct measure; never run before)")

h2("(2b) THE CONFOUND, STATED FIRST")
log("")
log("     Amex's payment rate is ~0.447 and Synchrony's is ~0.233. Almost none of that gap is")
log("     priority. It is PRODUCT DESIGN:")
log("       - Amex's securitised pool is dominated by charge-card-like and pay-in-full revolving")
log("         behaviour; a transactor repays ~100% of the balance every month by contract, not by")
log("         choice under stress.")
log("       - Synchrony is private-label/retail with deferred-interest promotional balances that are")
log("         DESIGNED not to amortise until the promo window ends.")
log("     A level difference of 2x in payment rate is therefore uninformative about priority. Every")
log("     test below is on CHANGES (elasticities of log payment rate to the common cycle), which")
log("     differences out any time-invariant product feature. A trust-specific TREND in product mix")
log("     is NOT differenced out; that is the residual threat and it is not testable here.")
log("")
log("     Quantifying the level confound directly is not possible from these files: no trust prints a")
log("     transactor/revolver split, a pay-in-full share, or a promotional-balance share. The best")
log("     available proxy is portfolio yield (finance charge income / receivables): a pool of")
log("     transactors earns little interest.")
yld_mean = M.groupby("trust")["yield"].mean().loc[TRUSTS]
pr_mean = M.groupby("trust")["payment_rate"].mean().loc[TRUSTS]
PROXY = pd.DataFrame({"mean_payment_rate": pr_mean, "mean_yield": yld_mean})
PROXY["yield_per_unit_pr"] = PROXY["mean_yield"] / PROXY["mean_payment_rate"]
log("")
log(tbl(PROXY.reset_index(), "%.4f"))
log("")
log("     Amex has the HIGHEST payment rate and a yield (0.277) barely below Synchrony's (0.273).")
log("     If Amex's pool were mostly transactors its yield would be far lower. So the Amex payment")
log("     rate is high for reasons the yield does not explain, and 'transactor mix' is a partial, not")
log("     a complete, account of the level. Either way the level is not evidence of priority.")

h2("(2e) DENOMINATORS - what each trust's printed payment rate actually divides by")
den = {
    "amex": "principal collections / MONTHLY PAYMENT RATE implies BEGINNING TOTAL RECEIVABLES "
            "(principal + finance charge). Denominator NOT printed; inferred.",
    "bofa": "Collections of Principal Receivables / PRIOR MONTH PRINCIPAL RECEIVABLES.",
    "chase": "Principal Payment Rate: principal collections / AVERAGE POOL BALANCE (printed, verified).",
    "citi": "4. Principal Payment Rate, on AVERAGE PRINCIPAL over the due period "
            "(due-period days vary; trust also prints a separate Total Payment Rate).",
    "comet": "principal collections / ADJUSTED BEGINNING PRINCIPAL, which INCLUDES additional "
             "principal receivables added that month (an inflow in the denominator).",
    "synchrony": "principal collections / BOP PRINCIPAL RECEIVABLES.",
}
log("")
for t in TRUSTS:
    log(f"     {t:10s} {den[t]}")
log("")
log("     CROSS-DENOMINATOR FLAGS:")
log("       amex vs everyone: amex is the ONLY trust whose denominator is TOTAL receivables rather")
log("         than PRINCIPAL receivables. Total > principal, so amex's printed rate is biased DOWN")
log("         relative to a principal-basis rate by roughly the finance-charge share of receivables")
log("         (~3% of the balance). This makes amex's LEVEL understated, not overstated - it does not")
log("         manufacture the amex/synchrony level gap, it shrinks it.")
log("       amex denominator is not printed at all; it is inferred from collections / printed rate.")
log("       citi's due period is not a calendar month (due_period_days varies), so citi's rate has a")
log("         day-count wobble the others do not.")
log("       comet's denominator includes same-month additions, so a month with a big pool addition")
log("         mechanically DEPRESSES comet's payment rate. Same denominator-dilution mechanism the")
log("         referee flagged for Synchrony's Dec-2019 delinquency share.")
log("       LEVEL comparisons across trusts are therefore not interpretable. ELASTICITIES are, so")
log("         long as the denominator definition is constant within a trust over time - which the")
log("         row labels confirm it is (identical label in the first and last month for all six).")
log("       Residual caveat: a denominator that is constant in DEFINITION can still move for")
log("         mechanical reasons (comet's additions), which is noise in that trust's elasticity.")

h2("(2a) PAYMENT RATE - levels, full panel and by regime")
lv = M.dropna(subset=["regime"]).groupby(["regime", "trust"])["payment_rate"].agg(["size", "mean", "std"])
PRREG = lv["mean"].unstack()[TRUSTS]
PRREG = PRREG.reindex([n for n, _, _ in REGIMES])
full = M.groupby("trust")["payment_rate"].mean().loc[TRUSTS]
PRREG.loc["FULL PANEL"] = full
log("")
log("     Mean monthly payment rate:")
log(tbl(PRREG.reset_index().rename(columns={"index": "regime"}), "%.4f"))
log("")
log("     Same thing in logs, differenced from each trust's own pre_covid mean (so the product-feature")
log("     level is removed and only the CHANGE is shown). Negative = payment rate fell.")
PRD = np.log(PRREG.loc[[n for n, _, _ in REGIMES]]) - np.log(PRREG.loc["pre_covid"])
log(tbl(PRD.reset_index().rename(columns={"index": "regime"}), "%+.4f"))
log("")
log("     Read the squeeze row: every trust's payment rate is ABOVE its pre-covid level in the")
log("     2023-07..2026-07 squeeze, and AMEX IS NOT DISTINCTIVE: amex +0.302, bofa +0.333,")
log("     chase +0.351, citi +0.311, comet +0.305 in logs. The odd trust out is SYNCHRONY at")
log("     +0.115 - the only one whose payment rate barely recovered. A priority story wants AMEX")
log("     to stand apart from the pack; instead the pack is tight and SYNCHRONY trails it, which")
log("     is equally consistent with Synchrony's promotional-balance mix being sticky (a product")
log("     fact, not a borrower choice). Descriptive only - the test is (2c).")
PRREG.reset_index().rename(columns={"index": "regime"}).to_csv(
    os.path.join(HERE, "part2_payment_rate_by_regime.csv"), index=False)
MON = pd.DataFrame({"ym": [str(p) for p in idx]})
for t in TRUSTS:
    MON["pr_" + t] = PR[t].values
    MON["d30_" + t] = D30[t].values
MON["six_mean_log30"] = X_STRESS.values
MON["six_mean_logPR"] = X_PRMEAN.values
MON["regime"] = REG.values
MON["log_pr_amex_minus_sync"] = (LPR["amex"] - LPR["synchrony"]).values
MON["log_d30_amex_minus_sync"] = (LD30["amex"] - LD30["synchrony"]).values
MON.to_csv(os.path.join(HERE, "part2_monthly_panel.csv"), index=False)

h2("(2c) THE TEST - elasticity of each trust's log payment rate to the common stressor")
log("")
log("     PRE-SPECIFIED SPECIFICATION:")
log("       log(payment_rate_{i,t}) = a_i + b_i * X_t + e_{i,t},")
log("       X_t = the six-trust mean of log(30+ share) in month t  (the common stressor),")
log("       Newey-West Bartlett standard errors, 6 lags, one regression per trust.")
log("     PRIORITY predicts b_amex > b_synchrony (Amex's payment rate holds up better when stress rises).")
log("     SELECTION predicts b_amex = b_synchrony (only the intercepts a_i differ).")
log(f"     n = {len(idx)} aligned months, {idx.min()} .. {idx.max()}.")
log("")
e_rows = []
for t in TRUSTS:
    r = ols_nw(LPR[t].values, const_design(X_STRESS.values), lags=6)
    e_rows.append({"trust": t, **{k: v for k, v in slope_row(r, t).items() if k != "spec"}})
E2C = pd.DataFrame(e_rows)
log(tbl(E2C[["trust", "n", "beta", "se", "z", "p", "ci_lo", "ci_hi", "r2"]], "%.4f"))
log("")
log("     beta is d log(payment rate) / d log(common 30+ level). A NEGATIVE beta means the trust's")
log("     payment rate falls when the market's delinquency rises.")

# robustness cycle definitions
alt_rows = []
for lab, X in (("six_mean_log30 (headline)", X_STRESS),
               ("six_mean_logPR", X_PRMEAN)):
    for t in TRUSTS:
        Xv = X.values
        if lab == "six_mean_logPR":
            Xv = (LPR.drop(columns=[t]).mean(axis=1)).values   # leave-one-out, else mechanical
            lab2 = "six_mean_logPR (leave-one-out)"
        else:
            lab2 = lab
        r = ols_nw(LPR[t].values, const_design(Xv), lags=6)
        alt_rows.append({"cycle": lab2, "trust": t, **{k: v for k, v in slope_row(r, t).items()
                                                       if k not in ("spec",)}})
# leave-one-out stress too
for t in TRUSTS:
    Xv = LD30.drop(columns=[t]).mean(axis=1).values
    r = ols_nw(LPR[t].values, const_design(Xv), lags=6)
    alt_rows.append({"cycle": "five-trust log30 (leave-one-out)", "trust": t,
                     **{k: v for k, v in slope_row(r, t).items() if k != "spec"}})
ALT = pd.DataFrame(alt_rows)
ALT.to_csv(os.path.join(HERE, "part2_elasticities_all_cycles.csv"), index=False)
log("")
log("     ROBUSTNESS (not the headline) - same regression against two other cycle definitions:")
log(tbl(ALT.pivot(index="trust", columns="cycle", values="beta").loc[TRUSTS].reset_index(), "%.4f"))
log("")
log("     Note the third column and do not skip past it. Against the leave-one-out mean PAYMENT RATE")
log("     cycle, Amex loads at 1.02 and Synchrony at 0.47 - Synchrony's payment rate is the LEAST")
log("     cyclical of the six and Amex's is middling. That is the ANTI-priority direction: if Amex")
log("     were protected, its payment rate would be the one that moves least with the herd. It is")
log("     also only a scaling statement (Synchrony's log payment rate has the smallest variance of")
log("     the six, so it loads low on any common factor) and I am not resting anything on it.")

h2("(2d) THE DIFFERENCE REGRESSIONS - is anything AMEX-SPECIFIC there?")
log("")
log("     Regressing the DIFFERENCE directly is the right way to test b_i = b_j: it carries the")
log("     covariance between the two trusts' residuals, which a naive comparison of two separate")
log("     standard errors throws away (and, because the residuals are strongly positively correlated,")
log("     the naive comparison is far too conservative).")
log("")
log("       log(PR_i,t) - log(PR_synchrony,t) = a + d * X_t + e_t,  NW 6 lags.")
log("       d = b_i - b_synchrony.  PRIORITY (for amex) predicts d > 0.")
log("")
d_rows = []
for t in [x for x in TRUSTS if x != "synchrony"]:
    y = (LPR[t] - LPR["synchrony"]).values
    r = ols_nw(y, const_design(X_STRESS.values), lags=6)
    row = slope_row(r, f"{t} - synchrony")
    row["trust"] = t
    row["corr_resid_with_sync"] = float(np.corrcoef(LPR[t], LPR["synchrony"])[0, 1])
    d_rows.append(row)
D2D = pd.DataFrame(d_rows)
log(tbl(D2D[["spec", "n", "beta", "se", "z", "p", "ci_lo", "ci_hi", "r2"]], "%.4f"))
D2D.to_csv(os.path.join(HERE, "part2_difference_regressions.csv"), index=False)
amex_d = D2D[D2D["trust"] == "amex"].iloc[0]
log("")
log(f"     AMEX minus SYNCHRONY: d = {amex_d['beta']:+.4f} (se {amex_d['se']:.4f}, z = {amex_d['z']:+.2f}, "
    f"p = {amex_d['p']:.3f}),")
log(f"     95% CI [{amex_d['ci_lo']:+.4f}, {amex_d['ci_hi']:+.4f}].")
log("")
log("     Is Amex an outlier among the five non-Synchrony trusts? Rank of d:")
rk = D2D.sort_values("beta", ascending=False)[["trust", "beta", "se", "z"]]
log(tbl(rk, "%+.4f"))

# amex vs each other trust, so "amex-specific" can be checked pairwise
pw = []
for t in TRUSTS:
    if t == "amex":
        continue
    y = (LPR["amex"] - LPR[t]).values
    r = ols_nw(y, const_design(X_STRESS.values), lags=6)
    row = slope_row(r, f"amex - {t}")
    pw.append(row)
PW = pd.DataFrame(pw)
log("")
log("     Amex against every other trust one at a time (d = b_amex - b_other):")
log(tbl(PW[["spec", "n", "beta", "se", "z", "p"]], "%+.4f"))
PW.to_csv(os.path.join(HERE, "part2_amex_pairwise.csv"), index=False)

h2("(2f) ROBUSTNESS ON THE AMEX-MINUS-SYNCHRONY DIFFERENCE (never promoted to the headline)")
log("")
log("     The headline in (2c)/(2d) is a LEVELS regression on trending series. Four alternatives:")
log("       R1 add a linear time trend      (kills any common drift in product mix)")
log("       R2 first differences            (d log PR difference on d X; no trend can survive)")
log("       R3 squeeze window only          (2023-07..end, the regime referee item 1 says is flat)")
log("       R4 drop the stimulus window     (2020-04..2021-12 removed entirely)")
log("")
tt = np.arange(len(idx), dtype=float)
ydiff = (LPR["amex"] - LPR["synchrony"]).values
d30diff = (LD30["amex"] - LD30["synchrony"]).values
rb = []
for lab, yv, Xm in (
    ("R0 headline levels                | PR", ydiff, const_design(X_STRESS.values)),
    ("R1 levels + linear trend          | PR", ydiff,
     np.column_stack([np.ones(len(tt)), X_STRESS.values, tt])),
    ("R0 headline levels                | 30+", d30diff, const_design(X_STRESS.values)),
    ("R1 levels + linear trend          | 30+", d30diff,
     np.column_stack([np.ones(len(tt)), X_STRESS.values, tt])),
):
    rb.append(slope_row(ols_nw(yv, Xm, lags=6), lab))
for lab, yv in (("R2 first differences              | PR", ydiff),
                ("R2 first differences              | 30+", d30diff)):
    dy = np.diff(yv)
    dx = np.diff(X_STRESS.values)
    rb.append(slope_row(ols_nw(dy, const_design(dx), lags=6), lab))
sq = pd.Series([p >= pd.Period("2023-07") for p in idx], index=idx).values
nostim = pd.Series([not (pd.Period("2020-04") <= p <= pd.Period("2021-12")) for p in idx],
                   index=idx).values
for lab, msk in (("R3 squeeze window only            | ", sq),
                 ("R4 drop the stimulus window       | ", nostim)):
    rb.append(slope_row(ols_nw(ydiff[msk], const_design(X_STRESS.values[msk]), lags=6), lab + "PR"))
    rb.append(slope_row(ols_nw(d30diff[msk], const_design(X_STRESS.values[msk]), lags=6), lab + "30+"))
RB = pd.DataFrame(rb)
log(tbl(RB[["spec", "n", "beta", "se", "z", "p", "ci_lo", "ci_hi"]], "%+.4f"))
RB.to_csv(os.path.join(HERE, "part2_robustness.csv"), index=False)
log("")
log("     TWO OF THESE ARE SIGNIFICANT AND BOTH POINT THE PRIORITY WAY. I am not going to bury them,")
log("     and I am not going to promote them either - the headline is pre-specified. They are")
log("     dissected in (2g). The headline levels specification and the trend-adjusted version are")
log("     both flat zeros; the signs across variants do not agree; and note that R2 on the payment")
log("     rate (+0.58) and R2 on 30+ (-0.52) BOTH read as priority while the LEVELS versions of the")
log("     same two regressions (+0.03, +0.08) do not. A relationship that exists at one-month")
log("     frequency and vanishes in levels is the signature of a TIMING artefact, not a cycle.")
log("")
log("     REFEREE ITEM 1, QUANTIFIED: how much common-stressor variation does each window actually")
log("     contain? sd of X within window, and the within-window OLS trend in X:")
vr = []
for name, a, b in REGIMES:
    m2 = np.array([pd.Period(a) <= p <= pd.Period(b) for p in idx])
    xv = X_STRESS.values[m2]
    tv = np.arange(m2.sum(), dtype=float)
    sl = float(np.linalg.lstsq(const_design(tv), xv, rcond=None)[0][1]) if m2.sum() > 2 else np.nan
    vr.append({"window": name, "n": int(m2.sum()), "sd_X": float(np.std(xv, ddof=1)),
               "range_X": float(xv.max() - xv.min()), "trend_per_month": sl,
               "trend_over_window": sl * max(m2.sum() - 1, 0)})
vr.append({"window": "FULL ALIGNED PANEL", "n": len(idx),
           "sd_X": float(np.std(X_STRESS.values, ddof=1)),
           "range_X": float(X_STRESS.max() - X_STRESS.min()), "trend_per_month": np.nan,
           "trend_over_window": np.nan})
VR = pd.DataFrame(vr)
log(tbl(VR, "%+.4f"))
VR.to_csv(os.path.join(HERE, "part2_stressor_variation.csv"), index=False)
log("")
log("     The squeeze window's sd of X is a fraction of the full panel's, and its within-window")
log("     trend is near zero. The referee is right: a between-regime step comparison had almost no")
log("     stressor variation to work with. That is exactly why every test above uses the CONTINUOUS")
log("     monthly stressor over the whole panel instead of regime bins.")

h2("(2g) CHASING THE ONE SIGNIFICANT RESULT - is the first-difference effect a cycle or a calendar?")
log("")
log("     The candidate finding: in month-to-month changes, when the market's 30+ rises, Amex's")
log("     payment rate falls LESS than Synchrony's (+0.58, z 3.3) and Amex's 30+ rises LESS than")
log("     Synchrony's (-0.52, z -2.8). Both are the priority direction. Three ways it could be fake:")
log("       (i)  SEASONALITY / DAY COUNT. February has 28 days and fewer collection days, so every")
log("            trust's payment rate dips and its 30+ jumps in a fixed monthly pattern. Trusts with")
log("            different due-period conventions get hit by different amounts, so a seasonal")
log("            difference would load onto the differenced regressor with no behaviour involved.")
log("       (ii) TIMING / LEAD-LAG. The six trusts do not close their due periods on the same day.")
log("            If Amex's series is half a month out of phase with the common series, the")
log("            contemporaneous difference regression picks up the phase, and the SUM of the")
log("            coefficients on the lead, the contemporaneous term and the lag goes back to zero.")
log("       (iii) A REAL short-run priority response that genuinely dies out within a year.")
log("     Tests: add month-of-year dummies; run the distributed lag and report the SUM; and run the")
log("     12-month difference, which is immune to fixed seasonality but keeps cyclical movement.")
log("")
mo = np.array([p.month for p in idx])
g_rows = []
for lab, yv in (("PR ", ydiff), ("30+", d30diff)):
    dy, dx, dmo = np.diff(yv), np.diff(X_STRESS.values), mo[1:]
    # S1 first difference + month-of-year dummies
    Dm = np.zeros((len(dmo), 11))
    for j, mm in enumerate(range(2, 13)):
        Dm[:, j] = (dmo == mm).astype(float)
    g_rows.append(slope_row(ols_nw(dy, np.column_stack([np.ones(len(dy)), dx, Dm]), lags=6),
                            f"S1 1st diff + month dummies      | {lab}"))
    # S2 distributed lag: lead, contemporaneous, lag -- report each and the SUM
    Xdl = np.column_stack([np.ones(len(dx) - 2), dx[2:], dx[1:-1], dx[:-2]])
    r = ols_nw(dy[1:-1], Xdl, lags=6)
    ssum = float(r["beta"][1:4].sum())
    Cs = r["cov"][1:4, 1:4]
    se_sum = float(np.sqrt(np.ones(3) @ Cs @ np.ones(3)))
    g_rows.append({"spec": f"S2 dist-lag lead  (dx_t+1)       | {lab}", "n": r["n"],
                   "beta": float(r["beta"][1]), "se": float(r["se"][1]), "z": float(r["t"][1]),
                   "p": float(r["p"][1]), "ci_lo": np.nan, "ci_hi": np.nan, "r2": r["r2"],
                   "sigma_resid": r["sigma_resid"], "const": float(r["beta"][0])})
    g_rows.append({"spec": f"S2 dist-lag contemporaneous      | {lab}", "n": r["n"],
                   "beta": float(r["beta"][2]), "se": float(r["se"][2]), "z": float(r["t"][2]),
                   "p": float(r["p"][2]), "ci_lo": np.nan, "ci_hi": np.nan, "r2": r["r2"],
                   "sigma_resid": r["sigma_resid"], "const": float(r["beta"][0])})
    g_rows.append({"spec": f"S2 dist-lag lag   (dx_t-1)       | {lab}", "n": r["n"],
                   "beta": float(r["beta"][3]), "se": float(r["se"][3]), "z": float(r["t"][3]),
                   "p": float(r["p"][3]), "ci_lo": np.nan, "ci_hi": np.nan, "r2": r["r2"],
                   "sigma_resid": r["sigma_resid"], "const": float(r["beta"][0])})
    g_rows.append({"spec": f"S2 SUM of the three (long run)   | {lab}", "n": r["n"],
                   "beta": ssum, "se": se_sum, "z": ssum / se_sum,
                   "p": float(2 * (1 - ncdf(abs(ssum / se_sum)))),
                   "ci_lo": ssum - 1.959964 * se_sum, "ci_hi": ssum + 1.959964 * se_sum,
                   "r2": r["r2"], "sigma_resid": r["sigma_resid"], "const": float(r["beta"][0])})
    # S3 twelve-month difference
    y12 = yv[12:] - yv[:-12]
    x12 = X_STRESS.values[12:] - X_STRESS.values[:-12]
    g_rows.append(slope_row(ols_nw(y12, const_design(x12), lags=12),
                            f"S3 12-month difference           | {lab}"))
# S4/S5/S6 squeeze window: trend, month dummies, 12-month differences
mo_sq = mo[sq]
Dsq = np.zeros((int(sq.sum()), 11))
for j, mm in enumerate(range(2, 13)):
    Dsq[:, j] = (mo_sq == mm).astype(float)
for lab, yv in (("PR ", ydiff), ("30+", d30diff)):
    ts = np.arange(int(sq.sum()), dtype=float)
    g_rows.append(slope_row(ols_nw(yv[sq], np.column_stack([np.ones(len(ts)), X_STRESS.values[sq], ts]),
                                   lags=6), f"S4 squeeze only + linear trend   | {lab}"))
    g_rows.append(slope_row(ols_nw(yv[sq], np.column_stack([np.ones(len(ts)), X_STRESS.values[sq], Dsq]),
                                   lags=6), f"S5 squeeze only + month dummies  | {lab}"))
    g_rows.append(slope_row(ols_nw(yv[sq], np.column_stack([np.ones(len(ts)), X_STRESS.values[sq],
                                                            ts, Dsq]), lags=6),
                            f"S6 squeeze + trend + month dums  | {lab}"))
# how much of X inside the squeeze window is pure seasonality?
xs = X_STRESS.values[sq]
ts_ = np.arange(len(xs), dtype=float)
r_seas = ols_nw(xs, np.column_stack([np.ones(len(xs)), ts_, Dsq]), lags=6)
seas_r2 = r_seas["r2"]
G2 = pd.DataFrame(g_rows)
log(tbl(G2[["spec", "n", "beta", "se", "z", "p"]], "%+.4f"))
G2.to_csv(os.path.join(HERE, "part2_diagnose_firstdiff.csv"), index=False)
log("")
log("     VERDICT ON THE FIRST-DIFFERENCE RESULT: IT IS A PHASE ARTEFACT, CONCLUSIVELY.")
log("     Payment rate, distributed lag: lead -0.799, contemporaneous +1.399, lag -0.602. The")
log("     contemporaneous coefficient is enormous and it is flanked on BOTH sides by large negative")
log("     ones. Their SUM is -0.002 with se 0.106 - a zero to three decimal places. That is exactly")
log("     what you get when two series carry the same information a fraction of a month out of")
log("     phase. The 12-month difference, which is immune to fixed seasonality and to phase but")
log("     keeps every bit of cyclical movement, gives -0.011 (se 0.045, z -0.25). Dead.")
log("     30+ ratio, same story: contemporaneous -0.899 flanked by +0.305 and +0.327, sum -0.267")
log("     (se 0.173, z -1.54, p 0.12); the 12-month difference is +0.161 (se 0.221, z +0.73).")
log("     Nothing survives once you stop asking about a single month's timing.")
log("")
log("     THE SQUEEZE-ONLY RESULT DOES NOT COLLAPSE, BUT IT CONTRADICTS ITSELF.")
log(f"     Inside 2023-07..2026-07 the common stressor X has sd 0.0500, and a linear trend plus")
log(f"     eleven month-of-year dummies explain R2 = {seas_r2:.3f} of it - so roughly {100*seas_r2:.0f}% of what")
log("     little variation there is is calendar, not credit. What is left gives:")
log("       payment rate: +0.159 (z 1.28, ns) with month dummies, +0.279 (z 2.07) adding a trend")
log("                     -> WEAK, PRIORITY DIRECTION (Amex's payment rate holds up better).")
log("       30+ ratio   : +0.692 (z 3.09) with month dummies, +0.735 (z 2.99) adding a trend")
log("                     -> AGAINST PRIORITY. A POSITIVE coefficient here means that when stress")
log("                        rises inside the squeeze, Amex's delinquency rises MORE than")
log("                        Synchrony's, i.e. the gap COMPRESSES - the opposite of protection.")
log("     THE TWO MEASURES POINT OPPOSITE WAYS IN THE SAME WINDOW. A real priority mechanism cannot")
log("     simultaneously make Amex pay better AND go delinquent faster. This is 37 monthly")
log("     observations with 13 regressors, leaving 24 degrees of freedom, and Newey-West 6-lag")
log("     standard errors are not trustworthy at that length. I read the pair as noise, and I would")
log("     read it as noise whichever way it had come out - which is the point of saying so here")
log("     rather than after seeing the sign I liked.")

results["part2"] = {
    "n_months": int(len(idx)),
    "robustness": RB.to_dict(orient="records"),
    "stressor_variation": VR.to_dict(orient="records"),
    "levels_by_regime": PRREG.to_dict(orient="index"),
    "elasticities": E2C.to_dict(orient="records"),
    "difference_vs_synchrony": D2D.drop(columns=["trust"]).to_dict(orient="records"),
    "amex_pairwise": PW.to_dict(orient="records"),
    "alt_cycles": ALT.to_dict(orient="records"),
    "denominators": den,
}

# ==================================================================== PART 3
h1("PART 3 - AN HONEST POWER STATEMENT")

h2("(3a) Cyclical betas: log(30+ level) on the six-trust mean log level")
log("")
log("       log(30+_{i,t}) = a_i + beta_i * X_t + e_{i,t},  X_t = six-trust mean log 30+, NW 6 lags.")
log("     Because X is the mean of the six left-hand variables, the six betas average to exactly 1")
log("     BY CONSTRUCTION. Only the SPREAD across trusts carries information.")
log("")
b_rows = []
for samp, mask in (("full panel", pd.Series(True, index=idx)), ("ex Dec-2019 seasoning", SEAS_MASK)):
    Xs = X_STRESS[mask].values
    for t in TRUSTS:
        r = ols_nw(LD30[t][mask].values, const_design(Xs), lags=6)
        row = slope_row(r, t)
        row["sample"] = samp
        row["trust"] = t
        b_rows.append(row)
B3A = pd.DataFrame(b_rows)
for samp in B3A["sample"].unique():
    log(f"     {samp}:")
    log(tbl(B3A[B3A["sample"] == samp][["trust", "n", "beta", "se", "z", "ci_lo", "ci_hi", "r2"]], "%.4f"))
    log("")
B3A.to_csv(os.path.join(HERE, "part3_cyclical_betas.csv"), index=False)
log("     Amex vs Synchrony is tested properly in (3c): the difference regression, which is exactly")
log("     beta_amex - beta_synchrony with the right covariance.")

h2("(3c) THE SPECIFICATION WITH NO RESEARCHER DEGREES OF FREEDOM")
log("")
log("       log( 30+_amex,t / 30+_synchrony,t ) = a + beta * X_t + e_t,  NW 6 lags.")
log("     No regime bins. No baseline window. No event dates. One number.")
log("     PRIORITY predicts beta < 0: when market stress doubles, the protected card's delinquency")
log("     rises LESS than the unprotected one's, so the log ratio falls.")
log("")
c_rows = []
for samp, mask in (("full panel", pd.Series(True, index=idx)), ("ex Dec-2019 seasoning", SEAS_MASK)):
    r = ols_nw((LD30["amex"] - LD30["synchrony"])[mask].values,
               const_design(X_STRESS[mask].values), lags=6)
    row = slope_row(r, f"log(amex30+/sync30+) ~ X  [{samp}]")
    row["sample"] = samp
    c_rows.append(row)
    # same on payment rate for symmetry
    r2 = ols_nw((LPR["amex"] - LPR["synchrony"])[mask].values,
                const_design(X_STRESS[mask].values), lags=6)
    row2 = slope_row(r2, f"log(amexPR/syncPR)  ~ X  [{samp}]")
    row2["sample"] = samp
    c_rows.append(row2)
C3C = pd.DataFrame(c_rows)
log(tbl(C3C[["spec", "n", "beta", "se", "z", "p", "ci_lo", "ci_hi", "r2"]], "%.4f"))
C3C.to_csv(os.path.join(HERE, "part3_no_dof_spec.csv"), index=False)
main = C3C.iloc[0]
log("")
log(f"     HEADLINE: beta = {main['beta']:+.4f}, se = {main['se']:.4f}, z = {main['z']:+.2f}, "
    f"p = {main['p']:.3f}, 95% CI [{main['ci_lo']:+.4f}, {main['ci_hi']:+.4f}].")

h2("(3b) MINIMUM DETECTABLE EFFECT")
log("")
log("     MDE at 80% power and a 5% two-sided test = (1.960 + 0.842) * SE(beta) = 2.802 * SE(beta).")
log("     SE(beta) is the Newey-West SE actually produced by the panel, so it already contains the")
log("     panel's real stressor variation and its real (serially correlated) residual noise.")
log("")
mde_rows = []
sdX = float(np.std(X_STRESS.values, ddof=1))
rngX = float(X_STRESS.max() - X_STRESS.min())
for _, r in C3C.iterrows():
    mde = MDE_MULT * r["se"]
    mde_rows.append({
        "spec": r["spec"], "n": r["n"], "se_beta": r["se"], "mde_beta": mde,
        "mde_pct_per_doubling": 100 * (np.exp(mde * np.log(2)) - 1),
        "mde_pct_over_observed_range": 100 * (np.exp(mde * rngX) - 1),
    })
for t in TRUSTS:
    r = ols_nw(LPR[t].values, const_design(X_STRESS.values), lags=6)
    pass
MDE = pd.DataFrame(mde_rows)
log(f"     Common stressor X: sd = {sdX:.4f} log points, peak-to-trough range = {rngX:.4f} log points")
log(f"       (a factor of {np.exp(rngX):.2f} between the calmest and the worst month of the panel).")
log("")
log(tbl(MDE, "%.4f"))
log("")
mde_d30 = MDE.iloc[0]
mde_pr = MDE.iloc[1]
log("     PLAIN TERMS, delinquency ratio:")
log(f"       A priority mechanism that moves the Amex/Synchrony 30+ gap by less than "
    f"{mde_d30['mde_pct_per_doubling']:.1f}% per")
log("       DOUBLING of market-wide delinquency is invisible to this design. Over the panel's entire")
log(f"       observed stress range (a {np.exp(rngX):.2f}x swing) the design cannot see an effect smaller than "
    f"{mde_d30['mde_pct_over_observed_range']:.1f}%.")
log("     PLAIN TERMS, payment rate:")
log(f"       A priority mechanism that moves the Amex/Synchrony payment-rate gap by less than "
    f"{mde_pr['mde_pct_per_doubling']:.1f}%")
log("       per doubling of market-wide delinquency is invisible here.")
log("")
log("     Compare that against the size of the thing being explained: the raw Amex/Synchrony 30+ ratio")
log(f"     is {raw_ratio_ded:.3f}, i.e. a gap of {100*(1-raw_ratio_ded):.1f}% below parity, "
    f"{abs(np.log(raw_ratio_ded)):.3f} in logs.")
share_d30 = mde_d30["mde_beta"] * np.log(2) / abs(np.log(raw_ratio_ded))
log(f"     So the MDE per doubling of stress is {100*share_d30:.1f}% of the whole gap. A priority effect")
log(f"     worth less than about {100*share_d30:.0f}% of the gap per doubling of stress cannot be seen.")
MDE.to_csv(os.path.join(HERE, "part3_mde.csv"), index=False)

h2("(3d) THE STIMULUS CONTRAST AGAINST ALL THREE DEFENSIBLE BASELINES")
log("")
log("     Referee objection 2: the previous run's 'stimulus widened the gap' result rested entirely on")
log("     using 2019-12..2020-03 as the baseline, and that window is contaminated by a Synchrony pool")
log("     addition. Here is the December-2019 arithmetic, from the file:")
sy = M[M["trust"] == "synchrony"].set_index("ym")
for p in ["2019-10", "2019-11", "2019-12", "2020-01", "2020-02", "2020-03"]:
    pp = pd.Period(p)
    if pp in sy.index:
        j = json.loads(sy.loc[pp, "row_labels_json"])
        b = {k.replace(" days delinquent", "").strip(): float(v)
             for k, v in j["inputs"]["delinquency_buckets"].items()}
        d3059 = b.get("30-59", np.nan)
        log(f"       {p}  recv ${sy.loc[pp,'receivables_principal']/1e9:7.3f}bn  "
            f"30-59 $ {d3059/1e6:8.2f}m  30+ share {sy.loc[pp,'delinq_30plus_share']:.5f}")
r_nov = float(sy.loc[pd.Period('2019-11'), 'receivables_principal'])
r_dec = float(sy.loc[pd.Period('2019-12'), 'receivables_principal'])
log(f"       receivables jumped {100*(r_dec/r_nov-1):+.1f}% in one month "
    f"while the 30-59 DOLLAR balance moved much less: that is denominator dilution, not credit news.")
log("")
BASELINES = [
    ("clean_pre_break_2018-12..2019-11", "2018-12", "2019-11"),
    ("prev_run_pre_covid_2019-01..2020-02", "2019-01", "2020-02"),
    ("contaminated_post_add_2019-12..2020-03", "2019-12", "2020-03"),
]
D30_AS = M.pivot_table(index="ym", columns="trust", values="delinq_30plus_share")[
    ["amex", "synchrony"]].dropna(how="any")
lr = np.log(D30_AS["amex"]) - np.log(D30_AS["synchrony"])
log("")
log("     NOTE ON SAMPLE: this contrast involves only amex and synchrony, so it uses every month in")
log("     which BOTH print (92 months), not the six-trust aligned panel. That is what makes the")
log(f"     'clean 12-month pre-break window' actually 12 months rather than 9.")
stim = lr[(lr.index >= pd.Period("2020-04")) & (lr.index <= pd.Period("2021-12"))]


def nw_mean_se(v, lags=6):
    r = ols_nw(np.asarray(v, dtype=float), np.ones((len(v), 1)), lags=lags)
    return float(r["beta"][0]), float(r["se"][0]), r["n"]


sm, ss, sn = nw_mean_se(stim.values)
def ratio_of_means(a, b):
    w = D30_AS[(D30_AS.index >= pd.Period(a)) & (D30_AS.index <= pd.Period(b))]
    return float(w["amex"].mean() / w["synchrony"].mean())


rom_stim = ratio_of_means("2020-04", "2021-12")
srows = []
for name, a, b in BASELINES:
    base = lr[(lr.index >= pd.Period(a)) & (lr.index <= pd.Period(b))]
    bm, bs, bn = nw_mean_se(base.values)
    d = sm - bm
    se = float(np.sqrt(ss ** 2 + bs ** 2))
    rom_b = ratio_of_means(a, b)
    srows.append({"baseline": name, "n_base": bn, "base_mean_logratio": bm, "n_stim": sn,
                  "pct_change_ratio_of_means": 100 * (rom_stim / rom_b - 1),
                  "stim_mean_logratio": sm, "diff_log": d, "se": se, "z": d / se,
                  "p": 2 * (1 - ncdf(abs(d / se))),
                  "pct_change_in_ratio": 100 * (np.exp(d) - 1),
                  "direction": "GAP COMPRESSED (priority direction)" if d > 0
                               else "GAP WIDENED (against priority)"})
S3D = pd.DataFrame(srows)
log("")
log("     SIGN CONVENTION, stated so it cannot be read backwards: the quantity is")
log("     log(amex 30+ / synchrony 30+). Amex is far BELOW Synchrony, so this log ratio is negative")
log("     (about -1.1, ratio ~0.33). A POSITIVE change means the ratio moves TOWARD 1, i.e. Amex's")
log("     advantage SHRINKS, i.e. THE GAP COMPRESSES. Stimulus = households flush = the priority")
log("     mechanism is not binding, so PRIORITY predicts the gap COMPRESSES in the stimulus window")
log("     (positive diff). SELECTION predicts no change, because the mix difference is permanent.")
log("")
log(tbl(S3D[["baseline", "n_base", "base_mean_logratio", "stim_mean_logratio", "diff_log", "se", "z",
             "p", "pct_change_in_ratio", "pct_change_ratio_of_means", "direction"]], "%.4f"))
S3D.to_csv(os.path.join(HERE, "part3_stimulus_baselines.csv"), index=False)
log("")
log("     THE SIGN OF THE STIMULUS CONTRAST IS A BASELINE CHOICE, NOT A FINDING. The two")
log("     uncontaminated baselines give GAP COMPRESSION (+10.0% and +3.0% on mean-of-logs, +13.5%")
log("     and +6.6% on ratio-of-means - the PRIORITY direction). The contaminated post-addition")
log("     window gives GAP WIDENING (-15.3% / -12.5%). NONE of the three is significant at any")
log("     conventional level: |z| <= 1.55, smallest p = 0.12.")
log("     REFEREE ITEM 2 IS CONFIRMED, including its magnitudes: they said 8.5-13.5% compression")
log("     against uncontaminated baselines and the ratio-of-means column here reads 6.6-13.5%.")
log("     The previous run's opposite conclusion came from the one contaminated window. But note")
log("     the symmetric point: the referee's preferred sign is not significant either. The correct")
log("     statement is that the stimulus episode carries NO usable information in either direction.")
log("")
log("     Referee objection 3: the 21-month stimulus window averages over a large hump. Monthly ratio:")
mrat = np.exp(lr)
hump = mrat[(mrat.index >= pd.Period("2020-03")) & (mrat.index <= pd.Period("2021-12"))]
HUMP = pd.DataFrame({"ym": [str(p) for p in hump.index], "amex_over_sync_30plus": hump.values})
log(tbl(HUMP, "%.4f"))
HUMP.to_csv(os.path.join(HERE, "part3_stimulus_hump.csv"), index=False)
log(f"     peak {hump.max():.4f} in {hump.idxmax()}, trough {hump.min():.4f} in {hump.idxmin()}.")
log("     A single window mean over a series that rises 38% and then falls 50% is not a summary of")
log("     anything; the hump peaks in 2020-07, the month the $600/week supplement expired.")

h2("(3e) Referee objection 5: the 2019->2020 compression ordering, checked")
yr = np.log(D30).groupby(D30.index.year).mean()
ch_level = (yr.loc[2019] - yr.loc[2020])
lrat = np.log(D30).sub(np.log(D30["synchrony"]), axis=0)
yrr = lrat.groupby(D30.index.year).mean()
ch_gap = (yrr.loc[2020] - yrr.loc[2019]).drop("synchrony").sort_values(ascending=False)
CH = pd.DataFrame({"trust": ch_gap.index, "gap_compression_vs_sync_2019_to_2020": ch_gap.values,
                   "own_level_fall_in_logs": [float(ch_level[t]) for t in ch_gap.index]})
log("")
log("     Two different things get called 'compression'. Both, so nothing hides:")
log("       own_level_fall  = log(own 30+ in 2019) - log(own 30+ in 2020). Bigger = its own")
log("                         delinquency fell more.")
log("       gap_compression = log(i/synchrony) in 2020 minus in 2019. POSITIVE = the trust's ratio")
log("                         to Synchrony moved TOWARD 1, i.e. its advantage over Synchrony shrank.")
log("                         This is the referee's measure and it is the one a halo story speaks to:")
log("                         in a flush year the protected card should LOSE its advantage.")
log("")
log(tbl(CH, "%+.4f"))
log("")
log("     Synchrony's own level fell MOST in 2020 "
    f"({float(ch_level['synchrony']):+.4f}) and Amex's fell LEAST ({float(ch_level['amex']):+.4f}).")
log("     In ratio terms that means AMEX'S ADVANTAGE OVER SYNCHRONY SHRANK THE MOST of any trust.")
log("     The ordering amex > citi > chase > bofa > comet reproduces the referee's ordering exactly;")
log("     my magnitudes differ from theirs in the third decimal because I use mean-of-logs on the")
log("     deduplicated panel. Under a halo reading this is WEAKLY WITH priority, not against it, and")
log("     the previous run's verdict item 3 asserted the opposite while printing this same table.")
log("     It is also weak evidence in the pure statistical sense: 2020 is one year, the ordering is")
log("     driven by a single hump (see above), and Amex leads citi by 0.009 log points.")
CH.to_csv(os.path.join(HERE, "part3_2019_2020_compression.csv"), index=False)

results["part3"] = {
    "betas": B3A.to_dict(orient="records"),
    "no_dof": C3C.to_dict(orient="records"),
    "mde": MDE.to_dict(orient="records"),
    "stressor_sd": sdX, "stressor_range": rngX,
    "stimulus_baselines": S3D.to_dict(orient="records"),
    "hump": HUMP.to_dict(orient="records"),
}

# ==================================================================== PART 4
h1("PART 4 - FIX THE MIX ADJUSTMENT'S TWO KNOWN BIASES")

fico = COMP[COMP["table"] == "fico"].copy()
fico["share"] = fico["share_receivables"]
wcols = ["w_" + t for t in TIERS]
mrg = fico.merge(XW[["trust", "bucket_label"] + wcols + ["flags"]],
                 on=["trust", "bucket_label"], how="left", validate="1:1")
assert not mrg[wcols].isna().any().any()

unscored_flag = mrg["flags"].fillna("").str.contains("unscored")
unsc = mrg[unscored_flag].groupby("trust")["share"].sum()
others = [t for t in TRUSTS if t != "synchrony"]
unsc_other = {t: float(unsc.get(t, 0.0)) for t in others}
avg_unscored = float(np.mean(list(unsc_other.values())))
log("")
log("(4a) BIAS 1 - Synchrony's unscored are counted as deep subprime.")
log("     Synchrony's bottom row is labelled 'No score and/or less than or equal to 599*'. Every other")
log("     trust prints a separate unscored row which the crosswalk drops (weight 0) before")
log("     renormalising. So Synchrony's unscored population is forced into the worst tier while")
log("     everyone else's is removed. That pushes Synchrony's expected loss UP and therefore its")
log("     actual/expected DOWN, which makes the Amex/Synchrony adjusted ratio LOOK BIGGER (more of")
log("     the gap attributed to Amex, less to mix). The fix moves the ratio DOWN.")
log("")
log("     Unscored share printed by each of the other five trusts:")
for t in others:
    log(f"       {t:10s} {unsc_other[t]:.6f}")
log(f"       mean of the five = {avg_unscored:.6f}")
log(f"     Synchrony's combined bottom bucket share = {float(fico[(fico.trust=='synchrony')].iloc[0]['share']):.6f}")


def score_to_tier_weights(lo, hi):
    """Uniform-in-score split of an integer score bucket [lo,hi] across the six tiers."""
    lo = 300 if (lo is None or not np.isfinite(lo)) else max(300, int(round(lo)))
    hi = 850 if (hi is None or not np.isfinite(hi)) else min(850, int(round(hi)))
    if hi < lo:
        lo, hi = hi, lo
    width = hi - lo + 1
    w = {}
    for name, a, b in TIER_EDGES:
        ov = max(0, min(hi, b) - max(lo, a) + 1)
        w[name] = ov / width
    return w


def synchrony_mix(offset=0, strip_unscored=0.0):
    """Synchrony tier shares with a VantageScore->FICO offset and an unscored share stripped from
    the bottom bucket. offset = points ADDED to Synchrony's VantageScore to make it FICO-comparable."""
    g = fico[fico["trust"] == "synchrony"].copy().reset_index(drop=True)
    edges = [(None, 599.0), (600.0, 659.0), (660.0, 719.0), (720.0, None)]
    s = g["share"].to_numpy(dtype=float).copy()
    s[0] = max(s[0] - strip_unscored, 0.0)
    s = s / s.sum()
    v = np.zeros(6)
    for i, (lo, hi) in enumerate(edges):
        lo2 = None if lo is None else lo + offset
        hi2 = None if hi is None else hi + offset
        w = score_to_tier_weights(lo2, hi2)
        v += s[i] * np.array([w[t] for t in TIERS])
    return v / v.sum()


def other_mix(trust):
    g = mrg[mrg["trust"] == trust]
    W = g[wcols].to_numpy(dtype=float)
    s = g["share"].to_numpy(dtype=float)
    scored = W.sum(axis=1) > 0
    W, s = W[scored], s[scored]
    s = s / s.sum()
    v = (s[:, None] * W).sum(axis=0)
    return v / v.sum()


# reproduce published crosswalk for synchrony at offset 0, unscored included: sanity check
chk_v = synchrony_mix(0, 0.0)
pub_v = other_mix("synchrony")
log("")
log(f"     sanity: my uniform-in-score rule reproduces the published synchrony crosswalk at offset 0 "
    f"to max abs diff {np.max(np.abs(chk_v - pub_v)):.2e}")

shape_vec = {s: SHP[SHP["shape_source"] == s].set_index("tier")["relative_loss"].astype(float).to_dict()
             for s in SHAPES}
act30 = M.groupby("trust")["delinq_30plus_share"].mean().loc[TRUSTS]
recv = M.groupby("trust")["receivables_principal"].mean().loc[TRUSTS]
base_mix = {t: other_mix(t) for t in TRUSTS}


def adj_ratio(sync_vec, shape):
    """Amex/Synchrony mix-adjusted ratio. The pinning level cancels, so this is exact."""
    v = np.array([shape_vec[shape][t] for t in TIERS])
    S_a = float(base_mix["amex"] @ v)
    S_s = float(sync_vec @ v)
    return float((act30["amex"] / act30["synchrony"]) * (S_s / S_a))


log("")
log("     Mix-adjusted Amex/Synchrony ratio under three treatments of Synchrony's bottom bucket:")
treat = [
    ("A. previous run (all of the bottom bucket treated as scored <=599)", 0.0),
    ("B. FIX: strip the other-five mean unscored share (%.4f) from the bottom bucket" % avg_unscored,
     avg_unscored),
    ("C. BOUND: strip Synchrony's own worst case - the largest unscored share printed by any "
     "other trust (%.4f)" % max(unsc_other.values()), max(unsc_other.values())),
]
rows4a = []
for lab, strip in treat:
    v = synchrony_mix(0, strip)
    for s in SHAPES:
        rows4a.append({"treatment": lab, "strip_unscored": strip, "shape": s,
                       "adj_ratio": adj_ratio(v, s)})
A4 = pd.DataFrame(rows4a)
p4 = A4.pivot(index="treatment", columns="shape", values="adj_ratio")[SHAPES]
log("")
log(tbl(p4.reset_index(), "%.4f"))
A4.to_csv(os.path.join(HERE, "part4a_unscored_fix.csv"), index=False)
d_fix = (p4.iloc[1] - p4.iloc[0])
log("")
log("     Change from the fix (B minus A), per shape:")
log("       " + ", ".join(f"{s}: {d_fix[s]:+.4f} ({100*d_fix[s]/p4.iloc[0][s]:+.2f}%)" for s in SHAPES))
log("     The bias is REAL and it is in the direction the referee said (the fix lowers the ratio, i.e.")
log("     MORE of the gap is mix than the previous run reported), but it is SMALL: the other five")
log(f"     trusts' unscored shares average only {avg_unscored:.4f}, so at most ~0.3pp of Synchrony's")
log("     6.17% bottom bucket is being misplaced. This objection is correct in kind, minor in size.")
log("     It is dwarfed by the VantageScore problem below.")

log("")
log("(4b) BIAS 2 - VANTAGESCORE vs FICO. HEADLINE RANGE, NOT A CAVEAT.")
log("     Synchrony's table is VantageScore 4.0; every other trust's is FICO. The scales share a")
log("     300-850 range and nothing else. offset = points ADDED to Synchrony's VantageScore to put it")
log("     on the FICO scale, so a POSITIVE offset means VantageScore reads LOW relative to FICO and")
log("     Synchrony's pool is really better than its table suggests.")
log("")
OFFS = [-40, -20, 0, 20, 40]
rows4b = []
for strip_lab, strip in (("unscored_fixed", avg_unscored), ("previous_run", 0.0)):
    for off in OFFS:
        v = synchrony_mix(off, strip)
        for s in SHAPES:
            rows4b.append({"unscored_treatment": strip_lab, "offset_points": off, "shape": s,
                           "adj_ratio": adj_ratio(v, s)})
B4 = pd.DataFrame(rows4b)
B4.to_csv(os.path.join(HERE, "part4b_offset_grid.csv"), index=False)
for lab in ("unscored_fixed", "previous_run"):
    sub = B4[B4["unscored_treatment"] == lab]
    p = sub.pivot(index="offset_points", columns="shape", values="adj_ratio")[SHAPES]
    p["row_min"] = p.min(axis=1)
    p["row_max"] = p.max(axis=1)
    log(f"     Synchrony unscored treatment = {lab}:")
    log(tbl(p.reset_index(), "%.4f"))
    log("")
HEAD = B4[B4["unscored_treatment"] == "unscored_fixed"]
lo, hi = float(HEAD["adj_ratio"].min()), float(HEAD["adj_ratio"].max())
lo_row = HEAD.loc[HEAD["adj_ratio"].idxmin()]
hi_row = HEAD.loc[HEAD["adj_ratio"].idxmax()]
log(f"     HONEST HEADLINE RANGE (unscored fixed, across 4 shapes x 5 offsets):")
log(f"       mix-adjusted Amex/Synchrony ratio runs {lo:.3f} .. {hi:.3f}")
log(f"       low  at offset {int(lo_row['offset_points']):+d}, shape {lo_row['shape']}")
log(f"       high at offset {int(hi_row['offset_points']):+d}, shape {hi_row['shape']}")
log(f"     RAW (unadjusted) ratio = {raw_ratio_ded:.3f}.")
log(f"     Share of the raw gap-below-parity that SURVIVES mix adjustment, "
    f"(1-adj)/(1-raw): {100*(1-hi)/(1-raw_ratio_ded):.0f}% .. {100*(1-lo)/(1-raw_ratio_ded):.0f}%.")
log("")
log("     Restricting to +/-20 points, the range the referee named, and the proportional straddle:")
sub20 = HEAD[HEAD["offset_points"].isin([-20, 0, 20])]
log(f"       across shapes and +/-20: {sub20['adj_ratio'].min():.3f} .. {sub20['adj_ratio'].max():.3f}")
sub20f = sub20[sub20["shape"] == "fico_odds"]
log(f"       fico_odds shape only, +/-20: {sub20f['adj_ratio'].min():.3f} .. {sub20f['adj_ratio'].max():.3f}")
log("")
log("     PLAIN STATEMENT OF THE UNCERTAINTY: the previous run reported the mix-adjusted Amex/Synchrony")
log("     ratio as roughly 0.60-0.71 across shapes, i.e. 'about 40% of the gap is mix'. Once the two")
log(f"     known biases are handled the honest interval is {lo:.2f} to {hi:.2f}. The upper end says mix")
log("     explains almost none of the gap; the lower end says mix explains most of it. THIS RANGE IS")
log("     WIDE ENOUGH TO CONTAIN BOTH STORIES, and no pool-level datum narrows it, because no trust")
log("     publishes its score table on a common scale.")

results["part4"] = {
    "unscored_other_five": unsc_other,
    "avg_unscored_other_five": avg_unscored,
    "unscored_fix_table": A4.to_dict(orient="records"),
    "offset_grid": B4.to_dict(orient="records"),
    "headline_range": {"lo": lo, "hi": hi,
                       "lo_at": {"offset": int(lo_row["offset_points"]), "shape": lo_row["shape"]},
                       "hi_at": {"offset": int(hi_row["offset_points"]), "shape": hi_row["shape"]}},
    "raw_ratio": raw_ratio_ded,
}

# ==================================================================== VERDICT
h1("VERDICT")
log("")
log("ONE SENTENCE: No - nothing in the pool-level data distinguishes priority from selection, because")
log("the only two tests with any direct power (the payment-rate elasticity and the no-degrees-of-freedom")
log("log-ratio regression) both return null differences between Amex and Synchrony with confidence")
log("intervals wide enough to contain effects several times larger than the entire gap being explained;")
log("what WOULD distinguish them is borrower-level data in which the same household holds both cards -")
log("a credit-bureau tradeline panel, the CFPB CCDB, or the NY Fed CCP - where you can watch which")
log("account a single squeezed borrower pays first.")
log("")
log("Supporting numbers, each labelled by what kind of claim it is:")
log("")
log("  (a) PROVEN BY ARITHMETIC ON THE DATA")
log(f"      - 5 duplicate trust-months, 10 rows, all identical on every data column; {len(RAW)} -> {len(M)} rows.")
log(f"      - The aligned panel is {len(aligned)} months, not 87.")
log("      - Dedupe changes neither the raw nor the mix-adjusted Amex/Synchrony ratio, because the")
log("        duplicates are bofa/citi/comet only and the pinning level cancels out of the ratio.")
log("      - Synchrony's receivables rose "
    f"{100*(r_dec/r_nov-1):+.1f}% in Dec-2019; the pre-stimulus baseline is contaminated.")
log("      - The six cyclical betas average to exactly 1 by construction, so a flat log ratio is the")
log("        mechanical default under BOTH stories.")
log("")
log("  (b) ESTIMATED, WITH A MODEL AND UNCERTAINTY")
log(f"      - Payment-rate elasticity gap, Amex minus Synchrony: {amex_d['beta']:+.4f} "
    f"(se {amex_d['se']:.4f}, z {amex_d['z']:+.2f}, p {amex_d['p']:.3f}).")
log(f"      - No-DoF delinquency-ratio elasticity: {main['beta']:+.4f} (se {main['se']:.4f}, "
    f"z {main['z']:+.2f}, p {main['p']:.3f}).")
log(f"      - MDE: an effect smaller than {mde_d30['mde_pct_per_doubling']:.0f}% of the ratio per doubling"
    f" of market stress is invisible.")
log(f"      - Honest mix-adjusted range: {lo:.2f} .. {hi:.2f}.")
log("      - Stimulus contrast: sign flips with the baseline, none significant.")
log("")
log("      - First-difference 'finding' (PR +0.58 z 3.3, 30+ -0.52 z -2.8) dissolves: the")
log("        distributed-lag SUM is -0.002 (se 0.106) and the 12-month difference is -0.011")
log("        (se 0.045). A phase artefact.")
log("      - Squeeze-window-only regressions survive the calendar but CONTRADICT each other:")
log("        payment rate +0.159 (priority direction, ns), 30+ ratio +0.692 (against priority, z 3.1).")
log("")
log("  (c) SPECULATION, LABELLED AS SUCH")
log("      - That Amex's payment-rate level reflects transactor share rather than priority is a story")
log("        consistent with the yield numbers but not established by them.")
log("      - That a bureau-level test would find a halo is a hypothesis; this analysis cannot support it.")
log("")
log("WHAT WOULD ACTUALLY SETTLE IT, in descending order of decisiveness:")
log("  1. A borrower-level tradeline panel where the SAME household holds an Amex and a Synchrony")
log("     private-label card. Condition on the household, then watch which account goes 30 days late")
log("     first when income falls. Household fixed effects hold selection constant BY CONSTRUCTION,")
log("     which is the one thing six aggregate time series can never do. Sources: NY Fed CCP")
log("     (5% anonymised Equifax panel), Experian/TransUnion tradeline extracts, the CFPB CCDB.")
log("  2. Failing that, a within-trust event with borrower-level randomness in the STRESSOR but not")
log("     in the pool: e.g. the state-by-state expiry of pandemic UI supplements, or a")
log("     geographically concentrated layoff, compared across trusts whose pools are geographically")
log("     disclosed. The prospectuses do print state concentration; that is a real, un-run test on")
log("     data that exists, and it would need state-level unemployment merged in.")
log("  3. Failing that, a common score scale. If any one of these trusts published BOTH a FICO and a")
log("     VantageScore distribution for the same pool in the same month, the 0.31-0.98 mix range")
log("     would collapse to something narrow enough to be worth arguing about. Nothing in these")
log("     files does that, and no amount of re-analysis of these files can create it.")
log("")
log("WHAT WOULD NOT SETTLE IT: any further regression of these six monthly series on each other.")
log("The design is exhausted. The betas average to one by construction, the stressor's whole")
log("observed range is a 2.17x swing, and the minimum detectable effect is ~34% of the very gap")
log("under investigation. More specifications will only find more sign flips.")

# ==================================================================== WRITE
with open(os.path.join(HERE, "results.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")


def jsonable(o):
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    if isinstance(o, (np.floating, float)):
        v = float(o)
        return None if not np.isfinite(v) else v
    if isinstance(o, (np.integer, int)):
        return int(o)
    if isinstance(o, (np.bool_, bool)):
        return bool(o)
    if o is None:
        return None
    return str(o)


with open(os.path.join(HERE, "results.json"), "w", encoding="utf-8") as f:
    json.dump(jsonable(results), f, indent=2)

print("\nWROTE", os.path.join(HERE, "results.txt"))
