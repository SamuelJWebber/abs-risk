"""
Robustness for freeride_test.py (self-contained).
  R1: mature vintages only (2012-2015, 36-month: every loan reached maturity before 2018Q4) + issue-year dummies.
  R2: R1 + applicant self-reported controls (log annual_inc, dti, log loan_amnt) - does total_bc_limit survive?
Each: AUC of base model (FICO + year [+ controls]) vs base + other-lender bankcard fields, all and by tier.
Writes results_robust.json / results_robust.txt.
"""
import json, os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(HERE, "LendingClub_2007_to_2018Q4.csv")
USECOLS = ["term", "issue_d", "loan_status", "fico_range_low", "fico_range_high",
           "total_bc_limit", "bc_open_to_buy", "num_bc_tl", "annual_inc", "dti", "loan_amnt"]
lines = []
def log(s=""):
    print(s); lines.append(str(s))

def auc(y, p):
    order = np.argsort(p, kind="mergesort")
    sp = p[order]
    ranks = np.empty(len(p)); ranks[order] = np.arange(1, len(p) + 1)
    # tie-average
    i = 0
    while i < len(sp):
        j = i
        while j + 1 < len(sp) and sp[j + 1] == sp[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = (i + j + 2) / 2.0
        i = j + 1
    n1 = y.sum(); n0 = len(y) - n1
    return float((ranks[y == 1].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0))

def logit_fit(X, y, ridge=1e-6, max_iter=60, tol=1e-8):
    n, k = X.shape; beta = np.zeros(k)
    for _ in range(max_iter):
        p = 1 / (1 + np.exp(-(X @ beta))); w = p * (1 - p)
        H = (X.T * w) @ X + ridge * np.eye(k)
        step = np.linalg.solve(H, X.T @ (y - p) - ridge * beta)
        beta += step
        if np.max(np.abs(step)) < tol: break
    p = 1 / (1 + np.exp(-(X @ beta))); w = p * (1 - p)
    cov = np.linalg.inv((X.T * w) @ X + ridge * np.eye(k))
    return beta, np.sqrt(np.diag(cov))

def predict(X, b): return 1 / (1 + np.exp(-(X @ b)))

log(f"Reading {CSV}")
df = pd.read_csv(CSV, usecols=USECOLS, low_memory=False)
df["term"] = df["term"].astype(str).str.strip()
df = df[df["term"] == "36 months"]
df["issue_year"] = pd.to_datetime(df["issue_d"], format="%b-%Y", errors="coerce").dt.year
df = df[(df["issue_year"] >= 2012) & (df["issue_year"] <= 2015)]
log(f"36-month loans issued 2012-2015: {len(df):,}")
for k, v in df["loan_status"].value_counts().items(): log(f"   {k}: {v:,}")
df = df[df["loan_status"].isin(["Fully Paid", "Charged Off"])].copy()
df["default"] = (df["loan_status"] == "Charged Off").astype(int)
df["fico"] = (df["fico_range_low"] + df["fico_range_high"]) / 2
for c in ["total_bc_limit", "bc_open_to_buy", "num_bc_tl", "annual_inc", "dti", "loan_amnt"]:
    df[c] = pd.to_numeric(df[c], errors="coerce")
df = df.dropna(subset=["fico", "total_bc_limit", "bc_open_to_buy", "num_bc_tl", "annual_inc", "dti", "loan_amnt"])
df = df[(df["total_bc_limit"] > 0) & (df["annual_inc"] > 0)].copy()
df["otb_share"] = (df["bc_open_to_buy"] / df["total_bc_limit"]).clip(0, 1)
df["dti"] = df["dti"].clip(0, 100)
log(f"Analysis sample (mature, complete fields): {len(df):,}; charge-off {df['default'].mean()*100:.2f}%")
log(f"Correlation log(total_bc_limit) with log(annual_inc): {np.corrcoef(np.log(df['total_bc_limit']), np.log(df['annual_inc']))[0,1]:.3f}")
log(f"Correlation log(total_bc_limit) with fico: {np.corrcoef(np.log(df['total_bc_limit']), df['fico'])[0,1]:.3f}")

def design(g, tr, with_controls):
    cols = {}
    cols["fico"] = g["fico"].values.astype(float)
    if with_controls:
        cols["log_inc"] = np.log(g["annual_inc"].values.astype(float))
        cols["dti"] = g["dti"].values.astype(float)
        cols["log_loan"] = np.log(g["loan_amnt"].values.astype(float))
    bc = {"log_bc_limit": np.log(g["total_bc_limit"].values.astype(float) + 1),
          "otb_share": g["otb_share"].values.astype(float),
          "num_bc_tl": g["num_bc_tl"].values.astype(float)}
    def z(v): m, s = v[tr].mean(), v[tr].std(); return (v - m) / s, s
    base_names, base_cols, base_sd = [], [], {}
    for k, v in cols.items():
        zv, s = z(v); base_names.append(k); base_cols.append(zv); base_sd[k] = s
    yrs = g["issue_year"].values
    for yr in sorted(np.unique(yrs))[1:]:
        base_names.append(f"yr{yr}"); base_cols.append((yrs == yr).astype(float)); base_sd[f"yr{yr}"] = 1.0
    bc_names, bc_cols, bc_sd = [], [], {}
    for k, v in bc.items():
        zv, s = z(v); bc_names.append(k); bc_cols.append(zv); bc_sd[k] = s
    one = np.ones(len(g))
    Xb = np.column_stack([one] + base_cols)
    Xf = np.column_stack([one] + base_cols + bc_cols)
    return Xb, Xf, base_names, bc_names, base_sd, bc_sd

def run(g, label, with_controls, seed=42):
    rng = np.random.RandomState(seed); idx = rng.permutation(len(g)); ntr = int(0.7 * len(g))
    tr, te = idx[:ntr], idx[ntr:]
    y = g["default"].values.astype(float)
    Xb, Xf, bn, cn, bsd, csd = design(g, tr, with_controls)
    bb, seb = logit_fit(Xb[tr], y[tr]); bf, sef = logit_fit(Xf[tr], y[tr])
    a_b = auc(y[te], predict(Xb[te], bb)); a_f = auc(y[te], predict(Xf[te], bf))
    k0 = 1 + len(bn)
    i_l = k0 + cn.index("log_bc_limit")
    coef_l = bf[i_l] / csd["log_bc_limit"]; se_l = sef[i_l] / csd["log_bc_limit"]
    i_inc = 1 + bn.index("log_inc") if with_controls else None
    out = {"label": label, "controls": with_controls, "n": int(len(g)), "default_rate": float(y.mean()),
           "auc_base": a_b, "auc_plus_bankcard": a_f, "auc_gain": a_f - a_b,
           "coef_log_bc_limit_per_logunit": float(coef_l), "se": float(se_l), "z": float(bf[i_l] / sef[i_l]),
           "odds_ratio_per_10pct_limit": float(np.exp(coef_l * np.log(1.1))),
           "std_coef_log_bc_limit": float(bf[i_l]),
           "std_coef_fico": float(bf[1]),
           "std_coef_log_inc": float(bf[i_inc]) if with_controls else None}
    log(f"--- {label} | controls={'income+dti+loan' if with_controls else 'none'} | n={len(g):,}, CO {y.mean()*100:.2f}% ---")
    log(f"   AUC base {a_b:.4f} -> +bankcard {a_f:.4f} (gain {a_f-a_b:+.4f})")
    log(f"   log(total_bc_limit): {coef_l:+.4f}/log unit (z={bf[i_l]/sef[i_l]:+.1f}); OR per +10% limit {np.exp(coef_l*np.log(1.1)):.4f}")
    log(f"   standardized: fico {bf[1]:+.3f}, log_bc_limit {bf[i_l]:+.3f}" + (f", log_inc {bf[i_inc]:+.3f}" if with_controls else ""))
    return out

tiers = [("ALL 660+", 0, 900), ("660-699", 660, 699.9), ("700-739", 700, 739.9), ("740+", 740, 900)]
results = {}
for ctrl in (False, True):
    log(""); log("=========== " + ("R2: mature 2012-2015 + year dummies + income/dti/loan controls" if ctrl else "R1: mature 2012-2015 + year dummies") + " ===========")
    for name, lo, hi in tiers:
        g = df[(df["fico"] >= lo) & (df["fico"] <= hi)]
        results[f"{'R2' if ctrl else 'R1'}_{name}"] = run(g, name, ctrl)

# plain-words: within FICO 700-739 AND within income tercile, does bc limit still sort default?
log(""); log("Charge-off by other-lender bankcard limit tercile, within FICO tier x income tercile (mature sample):")
grid = {}
for name, lo, hi in tiers[1:]:
    g = df[(df["fico"] >= lo) & (df["fico"] <= hi)].copy()
    g["inc_t"] = pd.qcut(g["annual_inc"], 3, labels=["low inc", "mid inc", "high inc"])
    g["bc_t"] = g.groupby("inc_t", observed=True)["total_bc_limit"].transform(lambda s: pd.qcut(s, 3, labels=["low lim", "mid lim", "high lim"]))
    tab = g.groupby(["inc_t", "bc_t"], observed=True)["default"].agg(["mean", "size"])
    grid[name] = {f"{a}|{b}": {"co": float(m), "n": int(s)} for (a, b), (m, s) in tab.iterrows()}
    log(f"  FICO {name}:")
    for (a, b), (m, s) in tab.iterrows():
        log(f"     {a:8s} {b:8s}: CO {m*100:.2f}% (n={s:,})")
results["grid"] = grid
results["sample_n"] = int(len(df))
with open(os.path.join(HERE, "results_robust.json"), "w") as fh: json.dump(results, fh, indent=2)
with open(os.path.join(HERE, "results_robust.txt"), "w", encoding="utf-8") as fh: fh.write("\n".join(lines))
log("done")
