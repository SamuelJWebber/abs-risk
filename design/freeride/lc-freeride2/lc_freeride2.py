"""
Stage 1/2/3: did Lending Club free-ride on OTHER card lenders' limit decisions,
and did it free-ride ENOUGH?

Stage 1: does LC's price (int_rate) / grade (sub_grade) load on total_bc_limit?
Stage 2: within sub_grade, does total_bc_limit still predict charge-off?
Stage 3: what is the residual mispricing worth in bps?

Sample reproduces the prior run: 36-month, issued 2012-2017, terminal status,
non-missing bankcard fields, total_bc_limit > 0.

Numpy only (no sklearn/statsmodels). Helpers reused from
C:/Users/samwe/code/abs-risk/design/freeride/lending-club/freeride_test.py
"""
import json
import os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(
    os.path.dirname(HERE), "freeride-data", "LendingClub_2007_to_2018Q4.csv"
)
OUT_JSON = os.path.join(HERE, "results.json")
OUT_TXT = os.path.join(HERE, "results.txt")

USECOLS = [
    "term", "issue_d", "loan_status", "fico_range_low", "fico_range_high",
    "total_bc_limit", "bc_open_to_buy", "num_bc_tl", "tot_hi_cred_lim",
    "loan_amnt", "annual_inc", "dti", "revol_util", "grade", "sub_grade",
    "int_rate", "installment", "verification_status", "home_ownership",
]

log_lines = []
R = {}


def log(s=""):
    print(s)
    log_lines.append(str(s))


# ------------------------------------------------------------------ helpers
def auc(y, p):
    """Mann-Whitney AUC via ranks (ties averaged)."""
    y = np.asarray(y)
    p = np.asarray(p)
    order = np.argsort(p, kind="mergesort")
    ranks = np.empty(len(p), dtype=float)
    ranks[order] = np.arange(1, len(p) + 1)
    sp = p[order]
    i = 0
    n = len(sp)
    while i < n:
        j = i
        while j + 1 < n and sp[j + 1] == sp[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = (i + 1 + j + 1) / 2.0
        i = j + 1
    n1 = y.sum()
    n0 = len(y) - n1
    if n1 == 0 or n0 == 0:
        return float("nan")
    return float((ranks[y == 1].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0))


def logit_fit(X, y, ridge=1e-6, max_iter=60, tol=1e-9):
    n, k = X.shape
    beta = np.zeros(k)
    for _ in range(max_iter):
        eta = X @ beta
        np.clip(eta, -35, 35, out=eta)
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
    ll = float(np.sum(y * np.log(p + 1e-12) + (1 - y) * np.log(1 - p + 1e-12)))
    return beta, se, ll


def predict(X, beta):
    return 1.0 / (1.0 + np.exp(-np.clip(X @ beta, -35, 35)))


def ols(X, y):
    """OLS with HC0 (heteroskedasticity-robust) standard errors. X includes intercept."""
    XtX = X.T @ X
    XtX_inv = np.linalg.pinv(XtX)
    beta = XtX_inv @ (X.T @ y)
    e = y - X @ beta
    meat = (X.T * (e ** 2)) @ X
    cov = XtX_inv @ meat @ XtX_inv
    se = np.sqrt(np.maximum(np.diag(cov), 0.0))
    ssr = float(e @ e)
    sst = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - ssr / sst
    k = X.shape[1]
    n = X.shape[0]
    adj = 1.0 - (1.0 - r2) * (n - 1) / (n - k)
    return {"beta": beta, "se": se, "r2": r2, "adj_r2": adj, "n": n, "k": k,
            "rmse": float(np.sqrt(ssr / (n - k)))}


def dummies(codes, n_levels, drop_first=True):
    """One-hot from integer codes 0..n_levels-1."""
    D = np.zeros((len(codes), n_levels), dtype=float)
    D[np.arange(len(codes)), codes] = 1.0
    return D[:, 1:] if drop_first else D


# ------------------------------------------------------------------ load
log("=" * 78)
log("LENDING CLUB FREE-RIDING TEST 2 : did LC price other lenders' limits,")
log("and did it price them ENOUGH?")
log("=" * 78)
log(f"Data: {DATA}")

df = pd.read_csv(DATA, usecols=USECOLS, low_memory=False)
log(f"Raw rows: {len(df):,}")

df["term"] = df["term"].astype(str).str.strip()
df = df[df["term"] == "36 months"]
log(f"After term == 36 months: {len(df):,}")

df["issue_dt"] = pd.to_datetime(df["issue_d"], format="%b-%Y", errors="coerce")
df["issue_year"] = df["issue_dt"].dt.year
df = df[(df["issue_year"] >= 2012) & (df["issue_year"] <= 2017)]
log(f"After issue year 2012-2017: {len(df):,}")

df = df[df["loan_status"].isin(["Fully Paid", "Charged Off"])].copy()
df["default"] = (df["loan_status"] == "Charged Off").astype(int)
log(f"After terminal status only: {len(df):,}; charge-off {df['default'].mean()*100:.2f}%")

df["fico"] = (df["fico_range_low"] + df["fico_range_high"]) / 2.0
for c in ["total_bc_limit", "bc_open_to_buy", "num_bc_tl", "tot_hi_cred_lim",
          "annual_inc", "dti", "revol_util", "loan_amnt", "installment"]:
    df[c] = pd.to_numeric(df[c], errors="coerce")

# int_rate may arrive as "13.99%" on some mirrors
if df["int_rate"].dtype == object:
    df["int_rate"] = pd.to_numeric(
        df["int_rate"].astype(str).str.replace("%", "", regex=False).str.strip(),
        errors="coerce")
else:
    df["int_rate"] = pd.to_numeric(df["int_rate"], errors="coerce")

n0 = len(df)
df = df.dropna(subset=["fico", "total_bc_limit", "bc_open_to_buy", "num_bc_tl"])
log(f"After dropping missing bankcard fields: {len(df):,} (dropped {n0-len(df):,})")
df = df[df["total_bc_limit"] > 0].copy()
log(f"After total_bc_limit > 0: {len(df):,}")

n0 = len(df)
df = df.dropna(subset=["int_rate", "sub_grade", "grade"])
log(f"After dropping missing int_rate/sub_grade: {len(df):,} (dropped {n0-len(df):,})")

df["otb_share"] = (df["bc_open_to_buy"] / df["total_bc_limit"]).clip(0, 1)
df["log_bc"] = np.log(df["total_bc_limit"].astype(float) + 1.0)
df["log_inc"] = np.log(df["annual_inc"].astype(float).clip(lower=1.0))

LETTERS = ["A", "B", "C", "D", "E", "F", "G"]
sg_levels = [L + str(i) for L in LETTERS for i in range(1, 6)]
sg_map = {s: i + 1 for i, s in enumerate(sg_levels)}
df["sub_grade"] = df["sub_grade"].astype(str).str.strip()
df["sg_int"] = df["sub_grade"].map(sg_map)
n0 = len(df)
df = df.dropna(subset=["sg_int"])
if len(df) != n0:
    log(f"  dropped {n0-len(df):,} rows with unmappable sub_grade")
df["sg_int"] = df["sg_int"].astype(int)
df["sg_code"] = df["sg_int"] - 1
df["yr_code"] = (df["issue_year"] - df["issue_year"].min()).astype(int)
n_sg = 35
n_yr = int(df["yr_code"].max()) + 1

N = len(df)
CO = float(df["default"].mean())
log("")
log(f"FINAL ANALYSIS SAMPLE: N = {N:,}, charge-off rate {CO*100:.2f}%, "
    f"mean APR {df['int_rate'].mean():.2f}%")
R["sample"] = {
    "n": int(N), "charge_off_rate": CO,
    "mean_int_rate": float(df["int_rate"].mean()),
    "sd_int_rate": float(df["int_rate"].std()),
    "mean_fico": float(df["fico"].mean()),
    "median_total_bc_limit": float(df["total_bc_limit"].median()),
    "years": "2012-2017", "term": "36 months",
}

log("")
log("Loans and charge-off by issue year:")
by_yr = []
for yr, g in df.groupby("issue_year"):
    log(f"   {yr}: n={len(g):,}  charge-off {g['default'].mean()*100:.2f}%  "
        f"mean APR {g['int_rate'].mean():.2f}%  median bc limit ${g['total_bc_limit'].median():,.0f}")
    by_yr.append({"year": int(yr), "n": int(len(g)),
                  "charge_off": float(g["default"].mean()),
                  "mean_int_rate": float(g["int_rate"].mean()),
                  "median_bc_limit": float(g["total_bc_limit"].median())})
R["by_year_descriptives"] = by_yr

# ------------------------------------------------------------------ correlations
log("")
log("-" * 78)
log("CORRELATIONS with log(total_bc_limit)  [Pearson, full sample]")
log("-" * 78)
corr_vars = {
    "fico": df["fico"],
    "log(annual_inc)": df["log_inc"],
    "annual_inc": df["annual_inc"],
    "revol_util": df["revol_util"],
    "dti": df["dti"],
    "num_bc_tl": df["num_bc_tl"],
    "otb_share": df["otb_share"],
    "int_rate": df["int_rate"],
    "sub_grade(1-35)": df["sg_int"].astype(float),
}
corrs = {}
lb = df["log_bc"]
for name, v in corr_vars.items():
    m = v.notna() & lb.notna()
    c = float(np.corrcoef(lb[m].values.astype(float), v[m].values.astype(float))[0, 1])
    corrs[name] = c
    log(f"   corr(log_bc_limit, {name:<16}) = {c:+.4f}   (n={int(m.sum()):,})")
R["correlations_log_bc_limit"] = corrs

# ==================================================================
# STAGE 1 : DID LC PRICE IT?
# ==================================================================
log("")
log("=" * 78)
log("STAGE 1 - DID LENDING CLUB PRICE OTHER LENDERS' LIMITS?")
log("=" * 78)

fico = df["fico"].values.astype(float)
lbc = df["log_bc"].values.astype(float)
otb = df["otb_share"].values.astype(float)
nbc = df["num_bc_tl"].values.astype(float)
ir = df["int_rate"].values.astype(float)
sgi = df["sg_int"].values.astype(float)
yr_code = df["yr_code"].values.astype(int)
one = np.ones(N)
Dyr = dummies(yr_code, n_yr)  # base = 2012

# extra LC observables for the 1e check
dti_v = pd.to_numeric(df["dti"], errors="coerce").fillna(df["dti"].median()).values.astype(float)
ru_v = pd.to_numeric(df["revol_util"], errors="coerce").fillna(df["revol_util"].median()).values.astype(float)
inc_v = df["log_inc"].values.astype(float)
amt_v = df["loan_amnt"].values.astype(float)

BC_NAMES = ["log_bc_limit", "otb_share", "num_bc_tl"]


def stage1_report(dep, dep_name, unit, tag):
    """Run FICO-only, FICO+bankcard, each with and without year FE."""
    out = {}
    specs = {
        "fico_only": (np.column_stack([one, fico]), ["const", "fico"]),
        "fico_plus_bc": (np.column_stack([one, fico, lbc, otb, nbc]),
                         ["const", "fico"] + BC_NAMES),
        "fico_only_yearFE": (np.column_stack([one, fico, Dyr]),
                             ["const", "fico"] + [f"yr{y}" for y in range(1, n_yr)]),
        "fico_plus_bc_yearFE": (np.column_stack([one, fico, lbc, otb, nbc, Dyr]),
                                ["const", "fico"] + BC_NAMES + [f"yr{y}" for y in range(1, n_yr)]),
    }
    for key, (X, names) in specs.items():
        res = ols(X, dep)
        out[key] = {
            "r2": res["r2"], "adj_r2": res["adj_r2"], "rmse": res["rmse"],
            "coef": {nm: float(b) for nm, b in zip(names, res["beta"])},
            "se": {nm: float(s) for nm, s in zip(names, res["se"])},
            "t": {nm: float(b / s) if s > 0 else float("nan")
                  for nm, b, s in zip(names, res["beta"], res["se"])},
        }
        log("")
        log(f"[{tag}] {dep_name} ~ {key}   R2 = {res['r2']:.5f}  (adj {res['adj_r2']:.5f})  RMSE {res['rmse']:.4f}")
        for nm in names:
            if nm.startswith("yr") or nm == "const":
                continue
            b = out[key]["coef"][nm]
            s = out[key]["se"][nm]
            log(f"      {nm:<14} {b:+.6f}  (HC0 SE {s:.6f}, t = {b/s:+7.1f})")
        if "log_bc_limit" in out[key]["coef"]:
            b = out[key]["coef"]["log_bc_limit"]
            s = out[key]["se"]["log_bc_limit"]
            per10 = b * np.log(1.10)
            out[key]["effect_per_10pct_more_limit"] = float(per10)
            out[key]["effect_per_10pct_more_limit_se"] = float(s * np.log(1.10))
            out[key]["effect_per_doubling"] = float(b * np.log(2.0))
            log(f"      -> per +10% other-lender limit: {per10:+.5f} {unit}"
                f"   (per doubling: {b*np.log(2.0):+.4f} {unit})")
    out["delta_r2_bc_given_fico"] = out["fico_plus_bc"]["r2"] - out["fico_only"]["r2"]
    out["delta_r2_bc_given_fico_yearFE"] = (out["fico_plus_bc_yearFE"]["r2"]
                                            - out["fico_only_yearFE"]["r2"])
    log("")
    log(f"[{tag}] incremental R2 from the three bankcard fields, given FICO      = "
        f"{out['delta_r2_bc_given_fico']:+.5f}")
    log(f"[{tag}] incremental R2 from the three bankcard fields, given FICO+yrFE = "
        f"{out['delta_r2_bc_given_fico_yearFE']:+.5f}")
    return out


log("")
log("--- 1a: int_rate (percentage points of APR) ---")
R["stage1a_int_rate"] = stage1_report(ir, "int_rate", "pp of APR", "1a")

log("")
log("--- 1b: sub_grade as integer A1=1 ... G5=35 (ordinal check) ---")
R["stage1b_sub_grade"] = stage1_report(sgi, "sub_grade_int", "notches", "1b")

# ---- 1c summary
log("")
log("--- 1c: variance accounting ---")
a = R["stage1a_int_rate"]
log(f"   int_rate:      FICO alone R2 = {a['fico_only']['r2']:.4f}; "
    f"+bankcard R2 = {a['fico_plus_bc']['r2']:.4f} "
    f"(+{a['delta_r2_bc_given_fico']:.4f})")
log(f"   int_rate + yr: FICO alone R2 = {a['fico_only_yearFE']['r2']:.4f}; "
    f"+bankcard R2 = {a['fico_plus_bc_yearFE']['r2']:.4f} "
    f"(+{a['delta_r2_bc_given_fico_yearFE']:.4f})")
b = R["stage1b_sub_grade"]
log(f"   sub_grade:     FICO alone R2 = {b['fico_only']['r2']:.4f}; "
    f"+bankcard R2 = {b['fico_plus_bc']['r2']:.4f} "
    f"(+{b['delta_r2_bc_given_fico']:.4f})")

# ---- 1e: is the bankcard loading incremental to LC's other observables?
log("")
log("--- 1e: does the bankcard loading survive LC's other observables? ---")
Xbase = np.column_stack([one, fico, dti_v, ru_v, inc_v, amt_v, Dyr])
Xfull = np.column_stack([one, fico, dti_v, ru_v, inc_v, amt_v, lbc, otb, nbc, Dyr])
rb = ols(Xbase, ir)
rf = ols(Xfull, ir)
nm_f = ["const", "fico", "dti", "revol_util", "log_inc", "loan_amnt",
        "log_bc_limit", "otb_share", "num_bc_tl"]
log(f"   base  (fico,dti,revol_util,log_inc,loan_amnt,yrFE)  R2 = {rb['r2']:.5f}")
log(f"   +bankcard                                           R2 = {rf['r2']:.5f}  "
    f"(delta {rf['r2']-rb['r2']:+.5f})")
for i, nm in enumerate(nm_f):
    if nm == "const":
        continue
    log(f"      {nm:<14} {rf['beta'][i]:+.6f} (SE {rf['se'][i]:.6f}, t={rf['beta'][i]/rf['se'][i]:+7.1f})")
log(f"   -> per +10% other-lender limit, controlling for LC's other observables: "
    f"{rf['beta'][6]*np.log(1.10)*100:+.2f} bps of APR")
R["stage1e_controls"] = {
    "r2_base": rb["r2"], "r2_with_bankcard": rf["r2"],
    "delta_r2": rf["r2"] - rb["r2"],
    "coef": {nm: float(v) for nm, v in zip(nm_f, rf["beta"][:len(nm_f)])},
    "se": {nm: float(v) for nm, v in zip(nm_f, rf["se"][:len(nm_f)])},
    "bps_per_10pct_more_limit": float(rf["beta"][6] * np.log(1.10) * 100),
}

# ---- 1d: by year
log("")
log("--- 1d: by issue year (did LC start using it?) ---")
log(f"{'year':<6}{'n':>9}{'R2 fico':>10}{'R2 +bc':>10}{'dR2':>9}"
    f"{'bps APR / +10% limit':>22}{'t':>8}{'notch / +10%':>15}")
by_year_rows = []
for yr in sorted(df["issue_year"].unique()):
    m = (df["issue_year"] == yr).values
    Xa = np.column_stack([one[m], fico[m]])
    Xb = np.column_stack([one[m], fico[m], lbc[m], otb[m], nbc[m]])
    ra = ols(Xa, ir[m])
    rbb = ols(Xb, ir[m])
    rs = ols(Xb, sgi[m])
    bps = rbb["beta"][2] * np.log(1.10) * 100
    tstat = rbb["beta"][2] / rbb["se"][2]
    notch = rs["beta"][2] * np.log(1.10)
    log(f"{int(yr):<6}{int(m.sum()):>9,}{ra['r2']:>10.4f}{rbb['r2']:>10.4f}"
        f"{rbb['r2']-ra['r2']:>9.4f}{bps:>22.2f}{tstat:>8.1f}{notch:>15.4f}")
    by_year_rows.append({
        "year": int(yr), "n": int(m.sum()), "r2_fico": ra["r2"],
        "r2_fico_plus_bc": rbb["r2"], "delta_r2": rbb["r2"] - ra["r2"],
        "bps_apr_per_10pct_limit": float(bps),
        "t_log_bc": float(tstat),
        "coef_log_bc_apr_pp": float(rbb["beta"][2]),
        "se_log_bc_apr_pp": float(rbb["se"][2]),
        "subgrade_notches_per_10pct_limit": float(notch),
    })
R["stage1d_by_year"] = by_year_rows

# ==================================================================
# STAGE 2 : DID IT PRICE IT ENOUGH?
# ==================================================================
log("")
log("=" * 78)
log("STAGE 2 - DID LC PRICE IT ENOUGH? (residual signal inside sub_grade)")
log("=" * 78)

y = df["default"].values.astype(float)
Dsg = dummies(df["sg_code"].values.astype(int), n_sg)  # base = A1, 34 dummies

rng = np.random.RandomState(42)
perm = rng.permutation(N)
ntr = int(round(0.7 * N))
tr, te = perm[:ntr], perm[ntr:]


def zsc(v, tr_idx):
    m, s = v[tr_idx].mean(), v[tr_idx].std()
    return (v - m) / s, float(m), float(s)


zl, ml, sl = zsc(lbc, tr)
zo, mo, so = zsc(otb, tr)
zn, mn, sn = zsc(nbc, tr)

X_base = np.column_stack([one, Dsg, Dyr])
X_full = np.column_stack([one, Dsg, Dyr, zl, zo, zn])

log(f"  design: intercept + 34 sub_grade dummies + {n_yr-1} year dummies "
    f"(+3 bankcard fields); train {len(tr):,} / test {len(te):,}")
bb, sb, llb = logit_fit(X_base[tr], y[tr])
bf, sf_, llf = logit_fit(X_full[tr], y[tr])
auc_b = auc(y[te], predict(X_base[te], bb))
auc_f = auc(y[te], predict(X_full[te], bf))

k = X_full.shape[1]
i_l, i_o, i_n = k - 3, k - 2, k - 1
coef_l = bf[i_l] / sl           # per log unit
se_l = sf_[i_l] / sl
log("")
log(f"  2a  AUC  sub_grade+yearFE only        = {auc_b:.4f}")
log(f"      AUC  + bankcard fields            = {auc_f:.4f}   gain {auc_f-auc_b:+.4f}")
log(f"      LR stat (3 df) = {2*(llf-llb):.1f}")
log(f"      log(total_bc_limit+1) coefficient = {coef_l:+.4f} per log unit "
    f"(SE {se_l:.4f}, z = {bf[i_l]/sf_[i_l]:+.1f})")
log(f"      odds ratio per +10% other-lender limit = {np.exp(coef_l*np.log(1.10)):.4f}")
log(f"      odds ratio per doubling of limit      = {np.exp(coef_l*np.log(2.0)):.4f}")
log(f"      otb_share coef {bf[i_o]/so:+.4f} per unit (z {bf[i_o]/sf_[i_o]:+.1f}); "
    f"num_bc_tl coef {bf[i_n]/sn:+.4f} per account (z {bf[i_n]/sf_[i_n]:+.1f})")
R["stage2a"] = {
    "n_train": int(len(tr)), "n_test": int(len(te)),
    "auc_subgrade_yearFE": float(auc_b),
    "auc_plus_bankcard": float(auc_f),
    "auc_gain": float(auc_f - auc_b),
    "lr_stat_3df": float(2 * (llf - llb)),
    "coef_log_bc_per_logunit": float(coef_l),
    "se_log_bc_per_logunit": float(se_l),
    "z_log_bc": float(bf[i_l] / sf_[i_l]),
    "odds_ratio_per_10pct": float(np.exp(coef_l * np.log(1.10))),
    "odds_ratio_per_doubling": float(np.exp(coef_l * np.log(2.0))),
    "coef_otb_share": float(bf[i_o] / so), "z_otb_share": float(bf[i_o] / sf_[i_o]),
    "coef_num_bc_tl": float(bf[i_n] / sn), "z_num_bc_tl": float(bf[i_n] / sf_[i_n]),
}

# full-sample (not split) coefficient, for the cleanest point estimate + SE
bf2, sf2, _ = logit_fit(X_full, y)
log(f"      [full-sample fit] log_bc coef {bf2[i_l]/sl:+.4f} "
    f"(SE {sf2[i_l]/sl:.4f}, z {bf2[i_l]/sf2[i_l]:+.1f})")
R["stage2a"]["fullsample_coef_log_bc"] = float(bf2[i_l] / sl)
R["stage2a"]["fullsample_se_log_bc"] = float(sf2[i_l] / sl)
R["stage2a"]["fullsample_z_log_bc"] = float(bf2[i_l] / sf2[i_l])

# robustness: sub_grade x year interactions (full saturation of LC's price grid)
sgyr = (df["sg_code"].values.astype(int) * n_yr + yr_code)
uniq = np.unique(sgyr)
remap = {v: i for i, v in enumerate(uniq)}
sgyr_c = np.array([remap[v] for v in sgyr], dtype=int)
Dsgy = dummies(sgyr_c, len(uniq))
Xb2 = np.column_stack([one, Dsgy])
Xf2 = np.column_stack([one, Dsgy, zl, zo, zn])
bb2, sbb2, _ = logit_fit(Xb2[tr], y[tr], ridge=1e-4)
bff2, sff2, _ = logit_fit(Xf2[tr], y[tr], ridge=1e-4)
a_b2 = auc(y[te], predict(Xb2[te], bb2))
a_f2 = auc(y[te], predict(Xf2[te], bff2))
kk = Xf2.shape[1]
log("")
log(f"  2a-robust  sub_grade x issue_year cells ({len(uniq)} cells, fully saturated):")
log(f"      AUC {a_b2:.4f} -> {a_f2:.4f} (gain {a_f2-a_b2:+.4f}); "
    f"log_bc coef {bff2[kk-3]/sl:+.4f} (z {bff2[kk-3]/sff2[kk-3]:+.1f})")
R["stage2a_saturated"] = {
    "n_cells": int(len(uniq)), "auc_base": float(a_b2), "auc_full": float(a_f2),
    "auc_gain": float(a_f2 - a_b2),
    "coef_log_bc": float(bff2[kk - 3] / sl),
    "z_log_bc": float(bff2[kk - 3] / sff2[kk - 3]),
}

# ---- 2b: by letter grade
log("")
log("  2b: coefficient on log(total_bc_limit+1) WITHIN each letter grade")
log("      (controls: the 5 sub_grade dummies inside that grade + year dummies)")
log(f"{'grade':<7}{'n':>9}{'CO%':>8}{'coef':>10}{'SE':>9}{'z':>8}"
    f"{'OR/+10%':>10}{'AUC base':>10}{'AUC +bc':>10}{'gain':>9}")
grade_rows = []
for L in LETTERS:
    m = (df["grade"].values == L)
    nL = int(m.sum())
    if nL < 2000:
        log(f"{L:<7}{nL:>9,}   too few rows, skipped")
        continue
    yL = y[m]
    sgL = df["sg_code"].values[m] - sg_map[L + "1"] + 1
    DsgL = dummies(sgL.astype(int), 5)
    DyrL = dummies(yr_code[m], n_yr)
    lbL, oL, nL_ = lbc[m], otb[m], nbc[m]
    rngL = np.random.RandomState(42)
    pL = rngL.permutation(nL)
    ntrL = int(round(0.7 * nL))
    trL, teL = pL[:ntrL], pL[ntrL:]
    zlL = (lbL - lbL[trL].mean()) / lbL[trL].std()
    slL = lbL[trL].std()
    zoL = (oL - oL[trL].mean()) / oL[trL].std()
    znL = (nL_ - nL_[trL].mean()) / nL_[trL].std()
    oneL = np.ones(nL)
    XbL = np.column_stack([oneL, DsgL, DyrL])
    XfL = np.column_stack([oneL, DsgL, DyrL, zlL, zoL, znL])
    b1, s1, _ = logit_fit(XbL[trL], yL[trL], ridge=1e-4)
    b2, s2, _ = logit_fit(XfL[trL], yL[trL], ridge=1e-4)
    aL1 = auc(yL[teL], predict(XbL[teL], b1))
    aL2 = auc(yL[teL], predict(XfL[teL], b2))
    # full-sample coefficient for the reported point estimate
    bF, sF, _ = logit_fit(XfL, yL, ridge=1e-4)
    kf = XfL.shape[1]
    cf = bF[kf - 3] / slL
    sef = sF[kf - 3] / slL
    zf = bF[kf - 3] / sF[kf - 3]
    log(f"{L:<7}{nL:>9,}{yL.mean()*100:>8.2f}{cf:>10.4f}{sef:>9.4f}{zf:>8.1f}"
        f"{np.exp(cf*np.log(1.10)):>10.4f}{aL1:>10.4f}{aL2:>10.4f}{aL2-aL1:>9.4f}")
    grade_rows.append({
        "grade": L, "n": nL, "charge_off": float(yL.mean()),
        "coef_log_bc": float(cf), "se_log_bc": float(sef), "z": float(zf),
        "odds_ratio_per_10pct": float(np.exp(cf * np.log(1.10))),
        "odds_ratio_per_doubling": float(np.exp(cf * np.log(2.0))),
        "auc_base": float(aL1), "auc_plus_bc": float(aL2), "auc_gain": float(aL2 - aL1),
    })
R["stage2b_by_grade"] = grade_rows

# ---- 2c: headline cross-tab
log("")
log("  2c: HEADLINE TABLE - charge-off by quintile of other-lender bankcard limit,")
log("      quintiles cut WITHIN each letter grade")
log(f"{'grade':<7}{'Q':<4}{'n':>9}{'med limit':>12}{'CO%':>8}{'mean APR%':>11}"
    f"{'mean FICO':>11}{'med income':>12}")
cross = []
df["_q"] = np.nan
for L in LETTERS:
    g = df[df["grade"] == L]
    if len(g) < 500:
        continue
    q = pd.qcut(g["total_bc_limit"], 5, labels=False, duplicates="drop")
    df.loc[g.index, "_q"] = q.values
for L in LETTERS:
    g = df[df["grade"] == L]
    if len(g) < 500:
        continue
    for qq in sorted(g["_q"].dropna().unique()):
        cell = g[g["_q"] == qq]
        row = {
            "grade": L, "quintile": int(qq) + 1, "n": int(len(cell)),
            "median_bc_limit": float(cell["total_bc_limit"].median()),
            "charge_off": float(cell["default"].mean()),
            "mean_int_rate": float(cell["int_rate"].mean()),
            "mean_fico": float(cell["fico"].mean()),
            "median_annual_inc": float(cell["annual_inc"].median()),
            "mean_sub_grade_int": float(cell["sg_int"].mean()),
        }
        cross.append(row)
        log(f"{L:<7}Q{row['quintile']:<3}{row['n']:>9,}"
            f"{row['median_bc_limit']:>12,.0f}{row['charge_off']*100:>8.2f}"
            f"{row['mean_int_rate']:>11.2f}{row['mean_fico']:>11.1f}"
            f"{row['median_annual_inc']:>12,.0f}")
R["stage2c_crosstab"] = cross

# ---- 2d: sanity on direction, plus an "is the grade just coarse?" probe
log("")
log("  2d: direction / coarseness probes")
log("      mean sub_grade integer by limit quintile within grade (is LC already")
log("      nudging low-limit borrowers to worse sub-grades inside the letter?):")
for L in LETTERS:
    rows = [r for r in cross if r["grade"] == L]
    if not rows:
        continue
    s = "  ".join(f"Q{r['quintile']}:{r['mean_sub_grade_int']:.2f}" for r in rows)
    log(f"      {L}: {s}")

# does the residual survive if we ALSO control for the continuous LC inputs?
X_b3 = np.column_stack([one, Dsg, Dyr, fico, dti_v, ru_v, inc_v, amt_v])
X_f3 = np.column_stack([one, Dsg, Dyr, fico, dti_v, ru_v, inc_v, amt_v, zl, zo, zn])
# scale continuous vars for conditioning
for j in range(X_b3.shape[1] - 5, X_b3.shape[1]):
    mu, sdv = X_b3[:, j].mean(), X_b3[:, j].std()
    X_b3[:, j] = (X_b3[:, j] - mu) / sdv
    X_f3[:, j] = (X_f3[:, j] - mu) / sdv
b3, s3, _ = logit_fit(X_b3[tr], y[tr], ridge=1e-4)
f3, sf3, _ = logit_fit(X_f3[tr], y[tr], ridge=1e-4)
a3b = auc(y[te], predict(X_b3[te], b3))
a3f = auc(y[te], predict(X_f3[te], f3))
k3 = X_f3.shape[1]
log("")
log(f"      + FICO/dti/revol_util/log_inc/loan_amnt as continuous controls on top of")
log(f"        sub_grade+year: AUC {a3b:.4f} -> {a3f:.4f} (gain {a3f-a3b:+.4f}); "
    f"log_bc coef {f3[k3-3]/sl:+.4f} (z {f3[k3-3]/sf3[k3-3]:+.1f})")
R["stage2d_with_continuous_controls"] = {
    "auc_base": float(a3b), "auc_full": float(a3f), "auc_gain": float(a3f - a3b),
    "coef_log_bc": float(f3[k3 - 3] / sl), "z_log_bc": float(f3[k3 - 3] / sf3[k3 - 3]),
}

# mature-vintage robustness for stage 2a
mm = (df["issue_year"] <= 2015).values
ym = y[mm]
Xbm = np.column_stack([one[mm], Dsg[mm], Dyr[mm]])
Xfm = np.column_stack([one[mm], Dsg[mm], Dyr[mm], zl[mm], zo[mm], zn[mm]])
nmm = int(mm.sum())
rngm = np.random.RandomState(42)
pm = rngm.permutation(nmm)
ntrm = int(round(0.7 * nmm))
trm, tem = pm[:ntrm], pm[ntrm:]
bm1, sm1, _ = logit_fit(Xbm[trm], ym[trm], ridge=1e-4)
bm2, sm2, _ = logit_fit(Xfm[trm], ym[trm], ridge=1e-4)
am1 = auc(ym[tem], predict(Xbm[tem], bm1))
am2 = auc(ym[tem], predict(Xfm[tem], bm2))
km = Xfm.shape[1]
log("")
log(f"  2a-mature (2012-2015 only, n={nmm:,}, CO {ym.mean()*100:.2f}%): "
    f"AUC {am1:.4f} -> {am2:.4f} (gain {am2-am1:+.4f}); "
    f"log_bc coef {bm2[km-3]/sl:+.4f} (z {bm2[km-3]/sm2[km-3]:+.1f})")
R["stage2a_mature"] = {
    "n": nmm, "charge_off": float(ym.mean()),
    "auc_base": float(am1), "auc_full": float(am2), "auc_gain": float(am2 - am1),
    "coef_log_bc": float(bm2[km - 3] / sl), "z_log_bc": float(bm2[km - 3] / sm2[km - 3]),
}

# ==================================================================
# STAGE 3 : WHAT WAS IT WORTH?
# ==================================================================
log("")
log("=" * 78)
log("STAGE 3 - WHAT WAS THE UNDER-WEIGHTING WORTH?")
log("=" * 78)
log("Formula: annualised loss rate ~= cumulative charge-off over loan life / 1.5,")
log("  where 1.5 years is the approximate average life of a 36-month amortising")
log("  loan (weighted-average life of level payments with prepayment ignored is")
log("  ~1.55y; we use 1.5). Charge-off here is the share of LOANS charged off, not")
log("  the share of principal lost, so this is an upper bound on nothing and a")
log("  rough proxy: it ignores recoveries, prepayment, partial repayment before")
log("  default (loss given default < 100% of original balance), and timing.")
log("")
log(f"{'grade':<7}{'Q1 limit':>10}{'Q5 limit':>10}{'Q1 CO%':>9}{'Q5 CO%':>9}"
    f"{'dCO pp':>9}{'ann loss pp':>13}{'Q1 APR':>9}{'Q5 APR':>9}"
    f"{'dAPR pp':>10}{'GAP bps':>10}")
stage3 = []
for L in LETTERS:
    rows = [r for r in cross if r["grade"] == L]
    if len(rows) < 5:
        continue
    q1 = [r for r in rows if r["quintile"] == 1][0]
    q5 = [r for r in rows if r["quintile"] == 5][0]
    dco = (q1["charge_off"] - q5["charge_off"]) * 100          # pp, cumulative
    ann = dco / 1.5                                            # pp per year
    dapr = q1["mean_int_rate"] - q5["mean_int_rate"]           # pp
    gap_bps = (ann - dapr) * 100
    log(f"{L:<7}{q1['median_bc_limit']:>10,.0f}{q5['median_bc_limit']:>10,.0f}"
        f"{q1['charge_off']*100:>9.2f}{q5['charge_off']*100:>9.2f}{dco:>9.2f}"
        f"{ann:>13.2f}{q1['mean_int_rate']:>9.2f}{q5['mean_int_rate']:>9.2f}"
        f"{dapr:>10.2f}{gap_bps:>10.0f}")
    stage3.append({
        "grade": L, "n_q1": q1["n"], "n_q5": q5["n"],
        "q1_median_limit": q1["median_bc_limit"], "q5_median_limit": q5["median_bc_limit"],
        "q1_charge_off": q1["charge_off"], "q5_charge_off": q5["charge_off"],
        "delta_charge_off_pp": float(dco),
        "annualised_loss_gap_pp": float(ann),
        "q1_mean_apr": q1["mean_int_rate"], "q5_mean_apr": q5["mean_int_rate"],
        "delta_apr_pp": float(dapr),
        "mispricing_bps": float(gap_bps),
    })
R["stage3"] = stage3

# volume-weighted overall mispricing: how many dollars sit in the underpriced cells
tot_amt = df["loan_amnt"].sum()
w_rows = []
for s in stage3:
    L = s["grade"]
    cellq1 = df[(df["grade"] == L) & (df["_q"] == 0)]
    w_rows.append({"grade": L, "q1_principal": float(cellq1["loan_amnt"].sum()),
                   "q1_share_of_book": float(cellq1["loan_amnt"].sum() / tot_amt)})
R["stage3_volume"] = {"total_principal": float(tot_amt), "q1_cells": w_rows}
log("")
log(f"  Book size in sample: ${tot_amt/1e9:.2f}bn original principal.")
for w in w_rows:
    s = [x for x in stage3 if x["grade"] == w["grade"]][0]
    log(f"   grade {w['grade']}: bottom-limit quintile = ${w['q1_principal']/1e9:.2f}bn "
        f"({w['q1_share_of_book']*100:.1f}% of book), under-charged by "
        f"{s['mispricing_bps']:.0f} bps/yr on that tranche")
wavg = sum([x["mispricing_bps"] * w["q1_principal"] for x, w in
            zip(stage3, w_rows)]) / sum(w["q1_principal"] for w in w_rows)
q1_share = sum(w["q1_principal"] for w in w_rows) / tot_amt
log(f"   principal-weighted average gap on the bottom-quintile tranche: {wavg:.0f} bps/yr; "
    f"that tranche is {q1_share*100:.1f}% of the book")
log(f"   spread over the whole book: {wavg*q1_share:.0f} bps/yr equivalent")
R["stage3_volume"]["weighted_avg_gap_bps_on_q1"] = float(wavg)
R["stage3_volume"]["q1_share_of_book"] = float(q1_share)
R["stage3_volume"]["bookwide_equivalent_bps"] = float(wavg * q1_share)

# the same thing done with a model instead of a cell: predicted CO change
log("")
log("  Model-based cross-check (logit coef from 2a, at the sample mean):")
p0 = CO
b_l = R["stage2a"]["fullsample_coef_log_bc"]
for mult, lab in [(np.log(2.0), "doubling of other-lender limit"),
                  (np.log(1.10), "+10% other-lender limit")]:
    od = p0 / (1 - p0) * np.exp(b_l * mult)
    p1 = od / (1 + od)
    log(f"     {lab}: charge-off {p0*100:.2f}% -> {p1*100:.2f}% "
        f"({(p1-p0)*100:+.2f} pp cumulative, {(p1-p0)*100/1.5:+.2f} pp/yr, "
        f"{(p1-p0)*100/1.5*100:+.0f} bps/yr)")
    R.setdefault("stage3_model", {})[lab] = {
        "p_base": p0, "p_new": float(p1),
        "delta_pp_cumulative": float((p1 - p0) * 100),
        "delta_bps_per_year": float((p1 - p0) * 100 / 1.5 * 100),
    }

with open(OUT_JSON, "w") as fh:
    json.dump(R, fh, indent=2, default=float)
with open(OUT_TXT, "w", encoding="utf-8") as fh:
    fh.write("\n".join(log_lines))
log("")
log(f"Wrote {OUT_JSON}")
log(f"Wrote {OUT_TXT}")
