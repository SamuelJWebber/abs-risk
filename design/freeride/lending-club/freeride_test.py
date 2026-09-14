"""
Test: do OTHER lenders' bankcard line decisions predict Lending Club default beyond FICO?

Data: Lending Club 2007-2018Q4 accepted loans (DePaul mirror, no login).
Sample: 36-month term, issued 2012-2017, loan_status in {Fully Paid, Charged Off}.
Models (logistic, Newton-Raphson in numpy, 70/30 split, seed 42):
  M1: default ~ fico
  M2: default ~ fico + log(total_bc_limit+1) + bc_open_to_buy/total_bc_limit + num_bc_tl
Repeated within FICO tiers 660-699, 700-739, 740+.
Outputs: results.json and results.txt in the same folder.
"""
import json
import os
import sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(HERE, "LendingClub_2007_to_2018Q4.csv")
OUT_JSON = os.path.join(HERE, "results.json")
OUT_TXT = os.path.join(HERE, "results.txt")

USECOLS = [
    "term", "issue_d", "loan_status", "fico_range_low", "fico_range_high",
    "total_bc_limit", "bc_open_to_buy", "num_bc_tl", "tot_hi_cred_lim",
    "total_rev_hi_lim", "bc_util", "total_cu_tl", "loan_amnt", "annual_inc",
    "dti", "grade", "int_rate",
]

log_lines = []


def log(s=""):
    print(s)
    log_lines.append(str(s))


# ---------------------------------------------------------------- helpers

def auc(y, p):
    """Mann-Whitney AUC via ranks (ties averaged)."""
    y = np.asarray(y)
    p = np.asarray(p)
    order = np.argsort(p)
    ranks = np.empty(len(p), dtype=float)
    ranks[order] = np.arange(1, len(p) + 1)
    # average ranks for ties
    sp = p[order]
    i = 0
    while i < len(sp):
        j = i
        while j + 1 < len(sp) and sp[j + 1] == sp[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = (i + 1 + j + 1) / 2.0
        i = j + 1
    n1 = y.sum()
    n0 = len(y) - n1
    if n1 == 0 or n0 == 0:
        return float("nan")
    return float((ranks[y == 1].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0))


def logit_fit(X, y, ridge=1e-6, max_iter=50, tol=1e-8):
    """Newton-Raphson logistic regression. X already includes intercept column.
    Returns beta, standard errors (from inverse Hessian)."""
    n, k = X.shape
    beta = np.zeros(k)
    for it in range(max_iter):
        eta = X @ beta
        p = 1.0 / (1.0 + np.exp(-eta))
        w = p * (1 - p)
        grad = X.T @ (y - p) - ridge * beta
        H = (X.T * w) @ X + ridge * np.eye(k)
        step = np.linalg.solve(H, grad)
        beta = beta + step
        if np.max(np.abs(step)) < tol:
            break
    eta = X @ beta
    p = 1.0 / (1.0 + np.exp(-eta))
    w = p * (1 - p)
    H = (X.T * w) @ X + ridge * np.eye(k)
    cov = np.linalg.inv(H)
    se = np.sqrt(np.diag(cov))
    ll = float(np.sum(y * np.log(p + 1e-12) + (1 - y) * np.log(1 - p + 1e-12)))
    return beta, se, ll


def predict(X, beta):
    return 1.0 / (1.0 + np.exp(-(X @ beta)))


def run_pair(df, label, seed=42):
    """Fit M1 and M2 on a 70/30 split; return dict of results."""
    rng = np.random.RandomState(seed)
    n = len(df)
    idx = rng.permutation(n)
    n_tr = int(round(0.7 * n))
    tr, te = idx[:n_tr], idx[n_tr:]
    y = df["default"].values.astype(float)

    f = df["fico"].values.astype(float)
    lbc = np.log(df["total_bc_limit"].values.astype(float) + 1.0)
    otb = df["otb_share"].values.astype(float)
    nbc = df["num_bc_tl"].values.astype(float)

    # standardize on training set so Newton is well conditioned and coefficients are comparable
    def z(v):
        m, s = v[tr].mean(), v[tr].std()
        return (v - m) / s, m, s

    zf, mf, sf = z(f)
    zl, ml, sl = z(lbc)
    zo, mo, so = z(otb)
    zn, mn, sn = z(nbc)
    one = np.ones(n)

    X1 = np.column_stack([one, zf])
    X2 = np.column_stack([one, zf, zl, zo, zn])

    b1, se1, ll1 = logit_fit(X1[tr], y[tr])
    b2, se2, ll2 = logit_fit(X2[tr], y[tr])
    auc1 = auc(y[te], predict(X1[te], b1))
    auc2 = auc(y[te], predict(X2[te], b2))
    # also a model with the bankcard fields only (no FICO) to show their standalone content
    X3 = np.column_stack([one, zl, zo, zn])
    b3, se3, ll3 = logit_fit(X3[tr], y[tr])
    auc3 = auc(y[te], predict(X3[te], b3))

    # coefficient in natural units for log(total_bc_limit+1): per 1 log-unit (=2.72x limit)
    coef_lbc_nat = b2[2] / sl
    se_lbc_nat = se2[2] / sl
    # per 10% more bankcard limit: odds ratio
    or_10pct = float(np.exp(coef_lbc_nat * np.log(1.10)))
    # FICO per 10 points
    coef_fico_nat_m1 = b1[1] / sf * 10
    coef_fico_nat_m2 = b2[1] / sf * 10

    res = {
        "label": label,
        "n_total": int(n), "n_train": int(len(tr)), "n_test": int(len(te)),
        "default_rate": float(y.mean()),
        "M1_auc_test": auc1,
        "M2_auc_test": auc2,
        "M3_bankcard_only_auc_test": auc3,
        "auc_gain_M2_minus_M1": auc2 - auc1,
        "M1_loglik_train": ll1, "M2_loglik_train": ll2,
        "LR_stat_M2_vs_M1": 2 * (ll2 - ll1),
        "M1_coef_fico_per10pts": float(coef_fico_nat_m1),
        "M2_coef_fico_per10pts": float(coef_fico_nat_m2),
        "M2_coef_log_total_bc_limit_per_logunit": float(coef_lbc_nat),
        "M2_se_log_total_bc_limit_per_logunit": float(se_lbc_nat),
        "M2_z_log_total_bc_limit": float(b2[2] / se2[2]),
        "M2_odds_ratio_per_10pct_more_bc_limit": or_10pct,
        "M2_coef_otb_share_per_unit": float(b2[3] / so),
        "M2_z_otb_share": float(b2[3] / se2[3]),
        "M2_coef_num_bc_tl_per_account": float(b2[4] / sn),
        "M2_z_num_bc_tl": float(b2[4] / se2[4]),
        "M2_standardized_coefs": {
            "fico": float(b2[1]), "log_total_bc_limit": float(b2[2]),
            "otb_share": float(b2[3]), "num_bc_tl": float(b2[4]),
        },
        "M2_standardized_se": {
            "fico": float(se2[1]), "log_total_bc_limit": float(se2[2]),
            "otb_share": float(se2[3]), "num_bc_tl": float(se2[4]),
        },
        "train_means": {"fico": float(mf), "log_total_bc_limit": float(ml),
                        "otb_share": float(mo), "num_bc_tl": float(mn)},
        "train_sds": {"fico": float(sf), "log_total_bc_limit": float(sl),
                      "otb_share": float(so), "num_bc_tl": float(sn)},
    }
    return res


def fmt(res):
    log(f"--- {res['label']} ---")
    log(f"  n={res['n_total']:,} (train {res['n_train']:,} / test {res['n_test']:,}); default rate {res['default_rate']*100:.2f}%")
    log(f"  M1 (FICO only)              test AUC = {res['M1_auc_test']:.4f}")
    log(f"  M2 (FICO + other-lender bc) test AUC = {res['M2_auc_test']:.4f}   gain = {res['auc_gain_M2_minus_M1']:+.4f}")
    log(f"  M3 (other-lender bc only)   test AUC = {res['M3_bankcard_only_auc_test']:.4f}")
    log(f"  LR stat M2 vs M1 (3 df) = {res['LR_stat_M2_vs_M1']:.1f}")
    log(f"  FICO per +10 pts: M1 {res['M1_coef_fico_per10pts']:+.4f}, M2 {res['M2_coef_fico_per10pts']:+.4f} (log-odds)")
    log(f"  log(total_bc_limit+1): {res['M2_coef_log_total_bc_limit_per_logunit']:+.4f} per log unit (SE {res['M2_se_log_total_bc_limit_per_logunit']:.4f}, z={res['M2_z_log_total_bc_limit']:+.1f}); odds ratio per +10% limit = {res['M2_odds_ratio_per_10pct_more_bc_limit']:.4f}")
    log(f"  bc_open_to_buy share (0-1): {res['M2_coef_otb_share_per_unit']:+.4f} per unit (z={res['M2_z_otb_share']:+.1f})")
    log(f"  num_bc_tl: {res['M2_coef_num_bc_tl_per_account']:+.4f} per account (z={res['M2_z_num_bc_tl']:+.1f})")
    s = res["M2_standardized_coefs"]
    log(f"  standardized (per 1 SD) M2: fico {s['fico']:+.3f}, log_bc_limit {s['log_total_bc_limit']:+.3f}, otb_share {s['otb_share']:+.3f}, num_bc_tl {s['num_bc_tl']:+.3f}")


# ---------------------------------------------------------------- load

log(f"Reading {CSV}")
df = pd.read_csv(CSV, usecols=USECOLS, low_memory=False)
log(f"Raw rows: {len(df):,}")

df["term"] = df["term"].astype(str).str.strip()
df = df[df["term"] == "36 months"]
log(f"After term==36 months: {len(df):,}")

df["issue_dt"] = pd.to_datetime(df["issue_d"], format="%b-%Y", errors="coerce")
df["issue_year"] = df["issue_dt"].dt.year
df = df[(df["issue_year"] >= 2012) & (df["issue_year"] <= 2017)]
log(f"After issue 2012-2017: {len(df):,}")

log("loan_status counts in this window:")
for k, v in df["loan_status"].value_counts().items():
    log(f"   {k}: {v:,}")

df = df[df["loan_status"].isin(["Fully Paid", "Charged Off"])].copy()
df["default"] = (df["loan_status"] == "Charged Off").astype(int)
log(f"After keeping Fully Paid / Charged Off: {len(df):,}; charge-off rate {df['default'].mean()*100:.2f}%")

df["fico"] = (df["fico_range_low"] + df["fico_range_high"]) / 2.0

for c in ["total_bc_limit", "bc_open_to_buy", "num_bc_tl", "tot_hi_cred_lim", "total_rev_hi_lim", "bc_util", "total_cu_tl"]:
    df[c] = pd.to_numeric(df[c], errors="coerce")

log("Missingness of bankcard fields in this window:")
for c in ["fico", "total_bc_limit", "bc_open_to_buy", "num_bc_tl", "tot_hi_cred_lim", "total_cu_tl"]:
    log(f"   {c}: {df[c].isna().mean()*100:.2f}% missing")
log("Missingness of total_bc_limit by issue year:")
for yr, g in df.groupby("issue_year"):
    log(f"   {yr}: {g['total_bc_limit'].isna().mean()*100:.2f}% missing of {len(g):,}; charge-off {g['default'].mean()*100:.2f}%")

n_before = len(df)
df = df.dropna(subset=["fico", "total_bc_limit", "bc_open_to_buy", "num_bc_tl"])
log(f"After dropping rows missing bankcard fields: {len(df):,} (dropped {n_before-len(df):,})")
# open-to-buy share: guard zero limit
df = df[df["total_bc_limit"] > 0].copy()
df["otb_share"] = (df["bc_open_to_buy"] / df["total_bc_limit"]).clip(0, 1)
log(f"After requiring total_bc_limit>0: {len(df):,}")

log("")
log("Descriptives (analysis sample):")
log(df[["fico", "total_bc_limit", "bc_open_to_buy", "otb_share", "num_bc_tl", "loan_amnt"]].describe(percentiles=[.1, .25, .5, .75, .9]).to_string())

# ---------------------------------------------------------------- plain-words table: default by bc-limit quintile within FICO tier
log("")
log("Charge-off rate by other-lender bankcard limit QUINTILE, within FICO tier (quintiles cut within tier):")
tiers = [("660-699", 660, 699.9), ("700-739", 700, 739.9), ("740+", 740, 900)]
quint_table = {}
for name, lo, hi in tiers:
    g = df[(df["fico"] >= lo) & (df["fico"] <= hi)].copy()
    g["q"] = pd.qcut(g["total_bc_limit"], 5, labels=False, duplicates="drop")
    rows = []
    for q, gg in g.groupby("q"):
        rows.append({"quintile": int(q) + 1, "n": int(len(gg)),
                     "median_total_bc_limit": float(gg["total_bc_limit"].median()),
                     "charge_off_rate": float(gg["default"].mean())})
    quint_table[name] = rows
    log(f"  FICO {name} (n={len(g):,}):")
    for r in rows:
        log(f"     Q{r['quintile']}: n={r['n']:,}, median limit ${r['median_total_bc_limit']:,.0f}, charge-off {r['charge_off_rate']*100:.2f}%")

# ---------------------------------------------------------------- regressions
results = {}
log("")
log("=================== LOGISTIC RESULTS (70/30 holdout, seed 42) ===================")
r_all = run_pair(df, "ALL FICO (660+)")
fmt(r_all)
results["all"] = r_all
for name, lo, hi in tiers:
    g = df[(df["fico"] >= lo) & (df["fico"] <= hi)]
    r = run_pair(g, f"FICO {name}")
    fmt(r)
    results[name] = r

# robustness: alternate seed
log("")
log("Robustness: seed 7 (ALL FICO):")
r_alt = run_pair(df, "ALL FICO seed 7", seed=7)
fmt(r_alt)
results["all_seed7"] = r_alt

# robustness: add total_cu_tl (finance trades, the reason-code-06 analog) where available
g = df.dropna(subset=["total_cu_tl"]).copy()
log("")
log(f"Finance-trade (total_cu_tl) check on rows where it is populated: n={len(g):,}")
if len(g) > 10000:
    rng = np.random.RandomState(42)
    idx = rng.permutation(len(g)); n_tr = int(0.7 * len(g)); tr, te = idx[:n_tr], idx[n_tr:]
    y = g["default"].values.astype(float)
    def zz(v):
        v = v.astype(float); m, s = v[tr].mean(), v[tr].std(); return (v - m) / s, s
    zf, sf = zz(g["fico"].values)
    zl, sl = zz(np.log(g["total_bc_limit"].values + 1))
    zo, so = zz(g["otb_share"].values)
    zn, sn = zz(g["num_bc_tl"].values)
    zc, sc = zz(g["total_cu_tl"].values)
    one = np.ones(len(g))
    XA = np.column_stack([one, zf, zl, zo, zn])
    XB = np.column_stack([one, zf, zl, zo, zn, zc])
    bA, seA, llA = logit_fit(XA[tr], y[tr]); bB, seB, llB = logit_fit(XB[tr], y[tr])
    aA = auc(y[te], predict(XA[te], bA)); aB = auc(y[te], predict(XB[te], bB))
    log(f"  M2 AUC {aA:.4f} -> M2+total_cu_tl AUC {aB:.4f}; total_cu_tl coef per finance trade {bB[5]/sc:+.4f} (z={bB[5]/seB[5]:+.1f})")
    log(f"  share of borrowers with >=1 finance trade: {(g['total_cu_tl']>0).mean()*100:.1f}%; charge-off with 0 trades {g.loc[g['total_cu_tl']==0,'default'].mean()*100:.2f}% vs >=1 {g.loc[g['total_cu_tl']>0,'default'].mean()*100:.2f}%")
    results["finance_trades"] = {"n": int(len(g)), "M2_auc": aA, "M2_plus_cu_auc": aB,
                                 "coef_total_cu_tl_per_trade": float(bB[5]/sc), "z": float(bB[5]/seB[5]),
                                 "share_with_finance_trade": float((g['total_cu_tl']>0).mean()),
                                 "co_rate_0_trades": float(g.loc[g['total_cu_tl']==0,'default'].mean()),
                                 "co_rate_1plus_trades": float(g.loc[g['total_cu_tl']>0,'default'].mean())}
else:
    log("  too few rows with total_cu_tl; skipped")

results["quintile_table"] = quint_table
results["sample"] = {"n_final": int(len(df)), "charge_off_rate": float(df["default"].mean()),
                     "years": "2012-2017", "term": "36 months"}

with open(OUT_JSON, "w") as fh:
    json.dump(results, fh, indent=2)
with open(OUT_TXT, "w", encoding="utf-8") as fh:
    fh.write("\n".join(log_lines))
log(f"\nWrote {OUT_JSON} and {OUT_TXT}")
