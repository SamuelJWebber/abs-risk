"""
Supplement: (i) how much of the total signal LC's grade absorbed, (ii) the
break-even arithmetic in bps (what LC charged per doubling of other-lender
limit vs what the loss difference required), (iii) binomial standard errors on
the headline cross-tab, (iv) loss-given-default sensitivity.
Reads the same sample; writes supplement.txt / supplement.json.
"""
import json
import os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "freeride-data",
                    "LendingClub_2007_to_2018Q4.csv")
OUT_TXT = os.path.join(HERE, "supplement.txt")
OUT_JSON = os.path.join(HERE, "supplement.json")

USECOLS = ["term", "issue_d", "loan_status", "fico_range_low", "fico_range_high",
           "total_bc_limit", "bc_open_to_buy", "num_bc_tl", "loan_amnt",
           "annual_inc", "grade", "sub_grade", "int_rate"]

lines = []


def log(s=""):
    print(s)
    lines.append(str(s))


def logit_fit(X, y, ridge=1e-6, max_iter=60, tol=1e-9):
    n, k = X.shape
    beta = np.zeros(k)
    for _ in range(max_iter):
        eta = np.clip(X @ beta, -35, 35)
        p = 1.0 / (1.0 + np.exp(-eta))
        w = p * (1 - p) + 1e-10
        grad = X.T @ (y - p) - ridge * beta
        H = (X.T * w) @ X + ridge * np.eye(k)
        step = np.linalg.solve(H, grad)
        beta = beta + step
        if np.max(np.abs(step)) < tol:
            break
    eta = np.clip(X @ beta, -35, 35)
    p = 1.0 / (1.0 + np.exp(-eta))
    w = p * (1 - p) + 1e-10
    H = (X.T * w) @ X + ridge * np.eye(k)
    se = np.sqrt(np.diag(np.linalg.inv(H)))
    return beta, se


def dummies(codes, n_levels):
    D = np.zeros((len(codes), n_levels))
    D[np.arange(len(codes)), codes] = 1.0
    return D[:, 1:]


df = pd.read_csv(DATA, usecols=USECOLS, low_memory=False)
df["term"] = df["term"].astype(str).str.strip()
df = df[df["term"] == "36 months"]
df["issue_dt"] = pd.to_datetime(df["issue_d"], format="%b-%Y", errors="coerce")
df["issue_year"] = df["issue_dt"].dt.year
df = df[(df["issue_year"] >= 2012) & (df["issue_year"] <= 2017)]
df = df[df["loan_status"].isin(["Fully Paid", "Charged Off"])].copy()
df["default"] = (df["loan_status"] == "Charged Off").astype(int)
df["fico"] = (df["fico_range_low"] + df["fico_range_high"]) / 2.0
for c in ["total_bc_limit", "bc_open_to_buy", "num_bc_tl", "annual_inc", "loan_amnt"]:
    df[c] = pd.to_numeric(df[c], errors="coerce")
df["int_rate"] = pd.to_numeric(
    df["int_rate"].astype(str).str.replace("%", "", regex=False).str.strip(),
    errors="coerce") if df["int_rate"].dtype == object else pd.to_numeric(df["int_rate"], errors="coerce")
df = df.dropna(subset=["fico", "total_bc_limit", "bc_open_to_buy", "num_bc_tl", "int_rate"])
df = df[df["total_bc_limit"] > 0].copy()
df["otb_share"] = (df["bc_open_to_buy"] / df["total_bc_limit"]).clip(0, 1)
df["log_bc"] = np.log(df["total_bc_limit"] + 1.0)
LETTERS = list("ABCDEFG")
sg_map = {L + str(i): j + 1 for j, (L, i) in
          enumerate([(L, i) for L in LETTERS for i in range(1, 6)])}
df["sg_code"] = df["sub_grade"].astype(str).str.strip().map(sg_map) - 1
df["yr_code"] = (df["issue_year"] - 2012).astype(int)
N = len(df)
CO = float(df["default"].mean())
log(f"Sample N = {N:,}, charge-off {CO*100:.2f}%")

y = df["default"].values.astype(float)
one = np.ones(N)
fico = df["fico"].values.astype(float)
lbc = df["log_bc"].values.astype(float)
otb = df["otb_share"].values.astype(float)
nbc = df["num_bc_tl"].values.astype(float)
Dyr = dummies(df["yr_code"].values.astype(int), 6)
Dsg = dummies(df["sg_code"].values.astype(int), 35)

sl = lbc.std()
zl = (lbc - lbc.mean()) / sl
zo = (otb - otb.mean()) / otb.std()
zn = (nbc - nbc.mean()) / nbc.std()
zf = (fico - fico.mean()) / fico.std()

# ---- A. absorption: total signal (given FICO) vs residual (given sub_grade)
XA = np.column_stack([one, zf, Dyr, zl, zo, zn])
bA, sA = logit_fit(XA, y, ridge=1e-4)
kA = XA.shape[1]
c_total = bA[kA - 3] / sl
se_total = sA[kA - 3] / sl

XB = np.column_stack([one, Dsg, Dyr, zl, zo, zn])
bB, sB = logit_fit(XB, y, ridge=1e-4)
kB = XB.shape[1]
c_resid = bB[kB - 3] / sl
se_resid = sB[kB - 3] / sl

absorbed = 1.0 - c_resid / c_total
log("")
log("A. HOW MUCH OF THE SIGNAL DID LC'S GRADE ABSORB?")
log(f"   coefficient on log(total_bc_limit+1), controlling FICO + year FE  : "
    f"{c_total:+.4f} (SE {se_total:.4f})")
log(f"   same, controlling 35 sub_grade dummies + year FE (residual)       : "
    f"{c_resid:+.4f} (SE {se_resid:.4f})")
log(f"   => share of the FICO-conditional signal absorbed by the grade     : "
    f"{absorbed*100:.1f}%   (left unpriced: {(1-absorbed)*100:.1f}%)")

# ---- B. break-even bps per doubling of other-lender limit
def dp(coef, mult, p0=CO):
    od = p0 / (1 - p0) * np.exp(coef * mult)
    return od / (1 + od) - p0


LIFE = 1.5
res = {}
log("")
log("B. BREAK-EVEN ARITHMETIC, PER DOUBLING OF OTHER-LENDER BANKCARD LIMIT")
log(f"   (evaluated at the sample charge-off rate {CO*100:.2f}%; "
    f"annualised = cumulative / {LIFE} years)")
d_tot = dp(c_total, np.log(2.0)) * 100
d_res = dp(c_resid, np.log(2.0)) * 100
req_tot = -d_tot / LIFE * 100          # bps/yr of APR needed to cover total loss gap
req_res = -d_res / LIFE * 100
charged = 0.5240 * 100                 # pp -> bps, from stage 1a int_rate ~ fico+bc+yrFE
log(f"   total loss gap  (FICO-conditional): {d_tot:+.3f} pp cumulative -> "
    f"required APR spread {req_tot:.0f} bps/yr")
log(f"   residual loss gap (within sub_grade): {d_res:+.3f} pp cumulative -> "
    f"still-required APR spread {req_res:.0f} bps/yr")
log(f"   APR spread LC actually charged (coef -0.5240 pp/doubling)        : "
    f"{charged:.0f} bps/yr")
log(f"   => LC priced {charged/req_tot*100:.0f}% of what the loss gap required; "
    f"shortfall {req_tot-charged:.0f} bps/yr per doubling")
res["absorption"] = {
    "coef_total_given_fico": float(c_total), "se_total": float(se_total),
    "coef_residual_given_subgrade": float(c_resid), "se_residual": float(se_resid),
    "share_absorbed_by_grade": float(absorbed),
}
res["breakeven_per_doubling"] = {
    "cum_co_gap_total_pp": float(d_tot), "required_bps_total": float(req_tot),
    "cum_co_gap_residual_pp": float(d_res), "required_bps_residual": float(req_res),
    "apr_bps_actually_charged": float(charged),
    "share_of_required_priced": float(charged / req_tot),
    "shortfall_bps": float(req_tot - charged),
}

# LGD sensitivity
log("")
log("   LGD sensitivity (share of original principal actually lost per charge-off):")
for lgd in [1.0, 0.75, 0.65, 0.5]:
    log(f"     LGD {lgd:.2f}: required total {req_tot*lgd:.0f} bps, "
        f"still-required residual {req_res*lgd:.0f} bps, charged {charged:.0f} bps "
        f"-> shortfall {req_tot*lgd-charged:+.0f} bps/yr")
res["lgd_sensitivity"] = {str(l): {"required_total_bps": float(req_tot * l),
                                   "required_residual_bps": float(req_res * l),
                                   "shortfall_bps": float(req_tot * l - charged)}
                          for l in [1.0, 0.75, 0.65, 0.5]}

# ---- C. crosstab with binomial SEs, Q1 vs Q5 within letter grade
log("")
log("C. HEADLINE CROSS-TAB WITH STANDARD ERRORS (Q1 vs Q5 within letter grade)")
log(f"{'grade':<7}{'n Q1':>8}{'n Q5':>8}{'Q1 CO%':>9}{'Q5 CO%':>9}{'diff pp':>9}"
    f"{'SE pp':>8}{'t':>7}{'dAPR pp':>10}{'gap bps':>10}{'gap SE':>9}")
rows = []
df["_q"] = np.nan
for L in LETTERS:
    g = df[df["grade"] == L]
    if len(g) < 500:
        continue
    df.loc[g.index, "_q"] = pd.qcut(g["total_bc_limit"], 5, labels=False,
                                    duplicates="drop").values
for L in LETTERS:
    g = df[df["grade"] == L]
    if len(g) < 500:
        continue
    c1 = g[g["_q"] == 0]
    c5 = g[g["_q"] == 4]
    p1, p5 = c1["default"].mean(), c5["default"].mean()
    n1, n5 = len(c1), len(c5)
    se = np.sqrt(p1 * (1 - p1) / n1 + p5 * (1 - p5) / n5) * 100
    diff = (p1 - p5) * 100
    dapr = c1["int_rate"].mean() - c5["int_rate"].mean()
    gap = (diff / LIFE - dapr) * 100
    gse = se / LIFE * 100
    log(f"{L:<7}{n1:>8,}{n5:>8,}{p1*100:>9.2f}{p5*100:>9.2f}{diff:>9.2f}"
        f"{se:>8.2f}{diff/se:>7.1f}{dapr:>10.2f}{gap:>10.0f}{gse:>9.0f}")
    rows.append({"grade": L, "n_q1": int(n1), "n_q5": int(n5),
                 "q1_co": float(p1), "q5_co": float(p5), "diff_pp": float(diff),
                 "se_pp": float(se), "t": float(diff / se), "delta_apr_pp": float(dapr),
                 "gap_bps": float(gap), "gap_se_bps": float(gse)})
res["crosstab_q1_q5"] = rows

# ---- D. pooled A-C only (where the money is) and dollar figure
mask = df["grade"].isin(["A", "B", "C"]).values
sub = df[mask]
q1 = sub[sub["_q"] == 0]
p1, p5 = q1["default"].mean(), sub[sub["_q"] == 4]["default"].mean()
log("")
log("D. WHERE THE MONEY IS (grades A-C = the investment-grade part of the book)")
log(f"   A-C principal ${sub['loan_amnt'].sum()/1e9:.2f}bn of "
    f"${df['loan_amnt'].sum()/1e9:.2f}bn total ({sub['loan_amnt'].sum()/df['loan_amnt'].sum()*100:.1f}%)")
log(f"   bottom-limit quintile inside A-C: n={len(q1):,}, "
    f"${q1['loan_amnt'].sum()/1e9:.2f}bn, charge-off {p1*100:.2f}% vs top quintile {p5*100:.2f}%")
gaps = [r for r in rows if r["grade"] in ("A", "B", "C")]
wt = []
for r in gaps:
    cell = df[(df["grade"] == r["grade"]) & (df["_q"] == 0)]
    wt.append((r["gap_bps"], float(cell["loan_amnt"].sum())))
wavg = sum(a * b for a, b in wt) / sum(b for _, b in wt)
princ = sum(b for _, b in wt)
log(f"   principal-weighted shortfall on the A-C bottom quintile: {wavg:.0f} bps/yr "
    f"on ${princ/1e9:.2f}bn")
log(f"   annual dollar value at 100% LGD: ${wavg/10000*princ/1e6:.0f}m per year; "
    f"at 65% LGD: ${0.65*wavg/10000*princ/1e6:.0f}m per year")
log(f"   (over the ~1.5y average life that is ${wavg/10000*princ*LIFE/1e6:.0f}m / "
    f"${0.65*wavg/10000*princ*LIFE/1e6:.0f}m of lifetime value on this vintage set)")
res["money"] = {
    "ac_principal": float(sub["loan_amnt"].sum()),
    "total_principal": float(df["loan_amnt"].sum()),
    "ac_q1_principal": float(princ),
    "ac_q1_weighted_gap_bps": float(wavg),
    "annual_dollars_lgd100": float(wavg / 10000 * princ),
    "annual_dollars_lgd65": float(0.65 * wavg / 10000 * princ),
}

# ---- E. does the residual shrink when we use a finer grade proxy (int_rate itself)?
ir = df["int_rate"].values.astype(float)
zi = (ir - ir.mean()) / ir.std()
XC = np.column_stack([one, zi, zi ** 2, Dyr, zl, zo, zn])
bC, sC = logit_fit(XC, y, ridge=1e-4)
kC = XC.shape[1]
log("")
log("E. COARSENESS PROBE: replace 35 sub_grade dummies with a smooth quadratic in")
log("   the actual APR (a finer, continuous read of LC's own price)")
log(f"   log_bc coefficient = {bC[kC-3]/sl:+.4f} (z {bC[kC-3]/sC[kC-3]:+.1f}) "
    f"vs {c_resid:+.4f} with sub_grade dummies")
res["coarseness_probe_apr_quadratic"] = {
    "coef_log_bc": float(bC[kC - 3] / sl), "z": float(bC[kC - 3] / sC[kC - 3]),
    "coef_with_subgrade_dummies": float(c_resid),
}

with open(OUT_JSON, "w") as fh:
    json.dump(res, fh, indent=2, default=float)
with open(OUT_TXT, "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines))
log("")
log(f"Wrote {OUT_TXT} and {OUT_JSON}")
