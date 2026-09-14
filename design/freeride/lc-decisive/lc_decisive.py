"""
LC DECISIVE RUN - settles the seven referee objections against the "free-riding" claim.

Pre-specified headline: within-cell quintiles of log(total_bc_limit+1), cells =
sub_grade x issue_year x FICO-20pt-band, mature 36-month vintages 2012-2015,
terminal status only, outcome = realized cash per $100 of original principal,
standard errors clustered on the cell.

Everything else in this file is robustness, the horse race, or a diagnostic.
"""
import json
import os
import sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(
    "C:/Users/samwe/AppData/Local/Temp/claude/"
    "c--Users-samwe-OneDrive-Documents-codex-projects-Job-autoapply/"
    "8b3ac5c3-74cb-44aa-9894-816ca22156c2/scratchpad/freeride-data",
    "LendingClub_2007_to_2018Q4.csv")
OUT_TXT = os.path.join(HERE, "results.txt")
OUT_JSON = os.path.join(HERE, "results.json")

MIN_CELL = 25           # pre-set minimum loans per cell
MIN_TAIL = 500          # a field needs this many loans in both Q1 and Q5 to enter the race

L = []
def log(s=""):
    s = str(s)
    print(s)
    L.append(s)

R = {}

# ------------------------------------------------------------------ field lists
BUREAU = [
    "annual_inc", "dti", "delinq_2yrs", "inq_last_6mths", "mths_since_last_delinq",
    "open_acc", "pub_rec", "revol_bal", "revol_util", "total_acc",
    "collections_12_mths_ex_med", "acc_now_delinq", "tot_coll_amt", "tot_cur_bal",
    "open_acc_6m", "open_act_il", "open_il_12m", "open_il_24m", "mths_since_rcnt_il",
    "total_bal_il", "il_util", "open_rv_12m", "open_rv_24m", "max_bal_bc", "all_util",
    "total_rev_hi_lim", "inq_fi", "total_cu_tl", "inq_last_12m", "acc_open_past_24mths",
    "avg_cur_bal", "bc_open_to_buy", "bc_util", "chargeoff_within_12_mths",
    "delinq_amnt", "mo_sin_old_il_acct", "mo_sin_old_rev_tl_op",
    "mo_sin_rcnt_rev_tl_op", "mo_sin_rcnt_tl", "mort_acc", "mths_since_recent_bc",
    "mths_since_recent_inq", "num_accts_ever_120_pd", "num_actv_bc_tl",
    "num_actv_rev_tl", "num_bc_sats", "num_bc_tl", "num_il_tl", "num_op_rev_tl",
    "num_rev_accts", "num_rev_tl_bal_gt_0", "num_sats", "num_tl_120dpd_2m",
    "num_tl_30dpd", "num_tl_90g_dpd_24m", "num_tl_op_past_12m", "pct_tl_nvr_dlq",
    "percent_bc_gt_75", "pub_rec_bankruptcies", "tax_liens", "tot_hi_cred_lim",
    "total_bal_ex_mort", "total_bc_limit", "total_il_high_credit_limit",
]

OTHER_LENDER = {
    "total_bc_limit", "total_rev_hi_lim", "tot_hi_cred_lim", "total_il_high_credit_limit",
    "acc_open_past_24mths", "num_tl_op_past_12m", "open_rv_12m", "open_rv_24m",
    "open_il_12m", "open_il_24m", "mort_acc", "num_bc_tl", "num_bc_sats",
    "num_rev_accts", "num_il_tl", "num_op_rev_tl", "num_sats", "open_acc", "total_acc",
    "total_cu_tl", "open_act_il", "mo_sin_old_rev_tl_op", "mo_sin_old_il_acct",
    "mo_sin_rcnt_rev_tl_op", "mo_sin_rcnt_tl", "mths_since_recent_bc",
}
MIXED = {"bc_open_to_buy"}
def klass(f):
    if f in OTHER_LENDER:
        return "OTHER-LENDER"
    if f in MIXED:
        return "MIXED"
    return "BORROWER"

KEEP = ([
    "term", "issue_d", "loan_status", "funded_amnt", "int_rate", "grade", "sub_grade",
    "fico_range_low", "fico_range_high", "total_rec_prncp", "total_rec_int",
    "recoveries", "collection_recovery_fee", "total_pymnt", "out_prncp", "loan_amnt",
] + BUREAU)

# ------------------------------------------------------------------ load
log("=" * 78)
log("LC DECISIVE RUN - realized cash, clustered SEs, FICO-balanced cells, horse race")
log("=" * 78)
log(f"Data: {DATA}")

raw_n = 0
term_counts = {}
chunks = []
for ch in pd.read_csv(DATA, usecols=KEEP, low_memory=False, chunksize=250000):
    raw_n += len(ch)
    ch["term"] = ch["term"].astype(str).str.strip()
    for k, v in ch["term"].value_counts().items():
        term_counts[k] = term_counts.get(k, 0) + int(v)
    ch = ch[ch["term"].isin(["36 months", "60 months"])]
    ch = ch[ch["loan_status"].isin(["Fully Paid", "Charged Off"])]
    chunks.append(ch)
df = pd.concat(chunks, ignore_index=True)
del chunks
log(f"Raw rows in file: {raw_n:,}")
for k in sorted(term_counts):
    log(f"   term {k!r}: {term_counts[k]:,} ({100.0*term_counts[k]/raw_n:.2f}% of raw file)")
n36 = term_counts.get("36 months", 0)
frac_discarded = 1.0 - n36 / raw_n
log(f"   -> the 36-month restriction discards {100*frac_discarded:.2f}% of the raw file "
    f"({raw_n - n36:,} of {raw_n:,} rows), which is the 60-month book plus unparsed terms.")
R["raw_rows"] = int(raw_n)
R["term_counts_raw"] = {k: int(v) for k, v in term_counts.items()}
R["frac_raw_discarded_by_36m"] = float(frac_discarded)

df["issue_dt"] = pd.to_datetime(df["issue_d"], format="%b-%Y", errors="coerce")
df["issue_year"] = df["issue_dt"].dt.year
for c in ["funded_amnt", "total_rec_prncp", "total_rec_int", "recoveries",
          "collection_recovery_fee", "total_pymnt", "out_prncp", "int_rate",
          "fico_range_low", "fico_range_high"] + BUREAU:
    df[c] = pd.to_numeric(df[c], errors="coerce")
df = df[df["funded_amnt"] > 0].copy()
df["default"] = (df["loan_status"] == "Charged Off").astype(float)
df["fico"] = (df["fico_range_low"] + df["fico_range_high"]) / 2.0
df["fico_band"] = (np.floor(df["fico"] / 20.0) * 20.0)
df["net_return"] = 100.0 * (df["total_rec_int"] + df["total_rec_prncp"] + df["recoveries"]
                            - df["collection_recovery_fee"] - df["funded_amnt"]) / df["funded_amnt"]

SG = sorted(df["sub_grade"].dropna().unique())
sg_map = {s: i for i, s in enumerate(SG)}


def make_sample(term, years):
    s = df[(df["term"] == term) & (df["issue_year"].isin(years))].copy()
    s = s[s["fico"].notna() & s["net_return"].notna() & s["sub_grade"].notna()]
    return s.reset_index(drop=True)


# ------------------------------------------------------------------ cell machinery
def cellcodes(s, keys):
    key = s[keys[0]].astype(str)
    for k in keys[1:]:
        key = key + "|" + s[k].astype(str)
    codes, uniq = pd.factorize(key, sort=True)
    return codes.astype(np.int64), len(uniq)


def within_cell_quintile(codes, ncell, x, min_cell=MIN_CELL):
    """Value-based within-cell quintiles (tied values stay together).
    Returns q in 0..4, -1 where undefined (missing x, or cell too small/degenerate)."""
    x = np.asarray(x, dtype=float)
    q = np.full(len(x), -1, dtype=np.int64)
    valid = np.isfinite(x)
    if valid.sum() == 0:
        return q, np.zeros(0, dtype=bool)
    c = codes[valid]
    v = x[valid]
    order = np.lexsort((v, c))
    cs, vs = c[order], v[order]
    counts = np.bincount(cs, minlength=ncell)
    starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
    # distinct-value count per cell
    newv = np.ones(len(cs), dtype=bool)
    newv[1:] = (cs[1:] != cs[:-1]) | (vs[1:] != vs[:-1])
    ndist = np.bincount(cs[newv], minlength=ncell)
    ok_cell = (counts >= min_cell) & (ndist >= 2)
    bp = np.zeros((ncell, 4), dtype=float)
    safe = np.maximum(counts - 1, 0)
    for j, p in enumerate([0.2, 0.4, 0.6, 0.8]):
        idx = starts + np.minimum((p * counts).astype(np.int64), safe)
        idx = np.clip(idx, 0, len(vs) - 1)
        bp[:, j] = vs[idx]
    bpv = bp[c]
    qv = ((v > bpv[:, 0]).astype(np.int64) + (v > bpv[:, 1]) + (v > bpv[:, 2])
          + (v > bpv[:, 3]))
    qv = np.where(ok_cell[c], qv, -1)
    q[valid] = qv
    return q, ok_cell


def within_cell_rankfrac(codes, ncell, x):
    """Tie-averaged within-cell rank fraction in (0,1); nan where x missing."""
    x = np.asarray(x, dtype=float)
    out = np.full(len(x), np.nan)
    valid = np.isfinite(x)
    if valid.sum() == 0:
        return out
    c = codes[valid]
    v = x[valid]
    order = np.lexsort((v, c))
    cs, vs = c[order], v[order]
    counts = np.bincount(cs, minlength=ncell)
    starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
    pos = np.arange(len(cs)) - starts[cs]
    newg = np.ones(len(cs), dtype=bool)
    newg[1:] = (cs[1:] != cs[:-1]) | (vs[1:] != vs[:-1])
    grp = np.cumsum(newg) - 1
    gcnt = np.bincount(grp)
    gsum = np.bincount(grp, weights=pos.astype(float))
    avgpos = (gsum / gcnt)[grp]
    rf = (avgpos + 0.5) / counts[cs]
    tmp = np.empty(len(cs))
    tmp[order] = rf
    out[valid] = tmp
    return out


def fe_quintile_reg(y, codes, q, ncell):
    """Cell-FE regression of y on quintile dummies Q2..Q5 (Q1 base).
    Returns dict with Q5-Q1 coefficient, clustered SE, HC0 SE, quintile coefs."""
    m = q >= 0
    y = np.asarray(y, float)[m]
    c = codes[m]
    qq = q[m]
    # drop cells that do not contain both a Q1 and a Q5 observation
    has1 = np.bincount(c, weights=(qq == 0).astype(float), minlength=ncell)
    has5 = np.bincount(c, weights=(qq == 4).astype(float), minlength=ncell)
    keep_cell = (has1 > 0) & (has5 > 0)
    m2 = keep_cell[c]
    y, c, qq = y[m2], c[m2], qq[m2]
    if len(y) < 100:
        return None
    uc, c = np.unique(c, return_inverse=True)
    G = len(uc)
    n = len(y)
    X = np.column_stack([(qq == k).astype(float) for k in range(1, 5)])
    cnt = np.bincount(c, minlength=G).astype(float)
    ybar = np.bincount(c, weights=y, minlength=G) / cnt
    yt = y - ybar[c]
    Xt = np.empty_like(X)
    for j in range(X.shape[1]):
        xb = np.bincount(c, weights=X[:, j], minlength=G) / cnt
        Xt[:, j] = X[:, j] - xb[c]
    XtX = Xt.T @ Xt
    XtXi = np.linalg.pinv(XtX)
    beta = XtXi @ (Xt.T @ yt)
    u = yt - Xt @ beta
    k = X.shape[1]
    # HC0
    meat0 = (Xt * (u ** 2)[:, None]).T @ Xt
    V0 = XtXi @ meat0 @ XtXi
    # clustered on cell
    S = np.zeros((k, k))
    ord2 = np.argsort(c, kind="stable")
    cc = c[ord2]
    Xc = Xt[ord2]
    uc_ = u[ord2]
    bounds = np.concatenate([[0], np.flatnonzero(np.diff(cc)) + 1, [len(cc)]])
    for a, b in zip(bounds[:-1], bounds[1:]):
        s = Xc[a:b].T @ uc_[a:b]
        S += np.outer(s, s)
    dfc = (G / max(G - 1.0, 1.0)) * ((n - 1.0) / max(n - k - G, 1.0))
    Vc = XtXi @ S @ XtXi * dfc
    qmean = [float(y[qq == j].mean()) if (qq == j).any() else float("nan") for j in range(5)]
    qn = [int((qq == j).sum()) for j in range(5)]
    coefs = [0.0] + [float(b) for b in beta]
    return {
        "n": int(n), "n_clusters": int(G),
        "q_raw_mean": qmean, "q_n": qn,
        "fe_coef_vs_Q1": coefs,
        "q5_minus_q1": float(beta[3]),
        "se_cluster": float(np.sqrt(max(Vc[3, 3], 0))),
        "se_hc0": float(np.sqrt(max(V0[3, 3], 0))),
        "t_cluster": float(beta[3] / np.sqrt(max(Vc[3, 3], 1e-300))),
        "t_hc0": float(beta[3] / np.sqrt(max(V0[3, 3], 1e-300))),
        "monotone_increasing": bool(all(coefs[i] <= coefs[i + 1] + 1e-12 for i in range(4))),
        "monotone_decreasing": bool(all(coefs[i] >= coefs[i + 1] - 1e-12 for i in range(4))),
    }


def logit_within_cell(yb, codes, ncell, rf):
    """Logistic on charge-off with a cell-default-rate offset and the field's
    within-cell tie-averaged rank fraction (centred) as the only regressor.
    Clustered z on the cell."""
    m = np.isfinite(rf)
    y = np.asarray(yb, float)[m]
    c = codes[m]
    x = rf[m] - 0.5
    uc, c = np.unique(c, return_inverse=True)
    G = len(uc)
    cnt = np.bincount(c, minlength=G).astype(float)
    p_cell = np.bincount(c, weights=y, minlength=G) / cnt
    p_cell = np.clip(p_cell, 0.002, 0.998)
    off = np.log(p_cell / (1 - p_cell))[c]
    X = np.column_stack([np.ones(len(y)), x])
    beta = np.zeros(2)
    for _ in range(60):
        eta = off + X @ beta
        p = 1.0 / (1.0 + np.exp(-eta))
        w = np.clip(p * (1 - p), 1e-9, None)
        g = X.T @ (y - p) - 1e-6 * beta
        H = (X.T * w) @ X + 1e-6 * np.eye(2)
        step = np.linalg.solve(H, g)
        beta += step
        if np.max(np.abs(step)) < 1e-9:
            break
    eta = off + X @ beta
    p = 1.0 / (1.0 + np.exp(-eta))
    w = np.clip(p * (1 - p), 1e-9, None)
    H = (X.T * w) @ X + 1e-6 * np.eye(2)
    Hi = np.linalg.inv(H)
    u = (y - p)
    S = np.zeros((2, 2))
    ord2 = np.argsort(c, kind="stable")
    cc, Xc, ucr = c[ord2], X[ord2], u[ord2]
    bounds = np.concatenate([[0], np.flatnonzero(np.diff(cc)) + 1, [len(cc)]])
    for a, b in zip(bounds[:-1], bounds[1:]):
        s = Xc[a:b].T @ ucr[a:b]
        S += np.outer(s, s)
    V = Hi @ S @ Hi * (G / max(G - 1.0, 1.0))
    se = float(np.sqrt(max(V[1, 1], 0)))
    return {"coef_top_vs_bottom_logodds": float(beta[1]), "se_cluster": se,
            "z_cluster": float(beta[1] / se) if se > 0 else float("nan"),
            "n": int(len(y)), "n_clusters": int(G)}


# ------------------------------------------------------------------ headline sample
log("")
log("-" * 78)
log("SAMPLE CONSTRUCTION (pre-specified)")
log("-" * 78)
S = make_sample("36 months", [2012, 2013, 2014, 2015])
log(f"36-month, issue 2012-2015, terminal status, funded_amnt>0 : N = {len(S):,}")
log(f"   charge-off rate (loan counts) = {S['default'].mean()*100:.2f}%")
log(f"   NOTE: no filter on bankcard-field completeness at sample level "
    f"(total_bc_limit missing in {S['total_bc_limit'].isna().mean()*100:.2f}% of this sample)")
log("   by issue year:")
for yr, g in S.groupby("issue_year"):
    log(f"      {int(yr)}: n={len(g):,}  charge-off {g['default'].mean()*100:.2f}%  "
        f"mean APR {g['int_rate'].mean():.2f}%  total_bc_limit missing {g['total_bc_limit'].isna().mean()*100:.1f}%")
R["headline_sample"] = {
    "n": int(len(S)), "charge_off_rate_counts": float(S["default"].mean()),
    "total_bc_limit_missing_share": float(S["total_bc_limit"].isna().mean()),
    "by_year": {int(yr): {"n": int(len(g)), "co": float(g["default"].mean()),
                          "apr": float(g["int_rate"].mean()),
                          "bc_missing": float(g["total_bc_limit"].isna().mean())}
                for yr, g in S.groupby("issue_year")},
}

# ------------------------------------------------------------------ referee 1 & 2: LGD and life
log("")
log("-" * 78)
log("REFEREE 1 (LGD) and REFEREE 2 (annualisation divisor) - MEASURED, not assumed")
log("-" * 78)
co = S[S["default"] == 1]
lgd_loan = ((co["funded_amnt"] - co["total_rec_prncp"] - co["recoveries"]
             + co["collection_recovery_fee"]) / co["funded_amnt"])
lgd_dollar = float((co["funded_amnt"] - co["total_rec_prncp"] - co["recoveries"]
                    + co["collection_recovery_fee"]).sum() / co["funded_amnt"].sum())
log(f"Charged-off loans: n={len(co):,}")
log(f"   realized LGD, dollar-weighted, on ORIGINAL principal net of recoveries = {lgd_dollar*100:.2f}%")
log(f"   realized LGD, simple mean across loans                                 = {lgd_loan.mean()*100:.2f}%")
log(f"   -> the 100% LGD assumption overstates loss by a factor of {1.0/lgd_dollar:.2f}x")
int_life = float(S["total_rec_int"].sum() / (S["funded_amnt"] * S["int_rate"] / 100.0).sum())
log(f"MEASURED realized weighted-average INTEREST-EARNING LIFE on this sample:")
log(f"   sum(total_rec_int) / sum(funded_amnt * APR) = "
    f"${S['total_rec_int'].sum():,.0f} / ${(S['funded_amnt']*S['int_rate']/100).sum():,.0f} "
    f"= {int_life:.4f} years")
log(f"   -> the divisor 1.5 used before was {1.5/int_life:.2f}x too large; annualised "
    f"figures below use {int_life:.4f}.")
R["lgd_and_life"] = {"n_charged_off": int(len(co)), "lgd_dollar_weighted": lgd_dollar,
                     "lgd_mean_loan": float(lgd_loan.mean()),
                     "interest_earning_life_years": int_life}

# referee 3: loan size by limit quintile
codes, ncell = cellcodes(S, ["sub_grade", "issue_year", "fico_band"])
S["cell"] = codes
lbc = np.log(S["total_bc_limit"].values + 1.0)
qh, okcell = within_cell_quintile(codes, ncell, lbc)
S["q_bc"] = qh
log("")
log("-" * 78)
log("REFEREE 3 (counts vs dollars) and REFEREE 4 (FICO balance) - diagnostics")
log("-" * 78)
log(f"Cells = sub_grade x issue_year x FICO-20pt band: {ncell:,} distinct cells, "
    f"{int(okcell.sum()):,} usable (n>={MIN_CELL} and >=2 distinct limit values)")
rows = []
for j in range(5):
    g = S[S["q_bc"] == j]
    rows.append({"q": j + 1, "n": int(len(g)),
                 "median_total_bc_limit": float(g["total_bc_limit"].median()),
                 "median_funded_amnt": float(g["funded_amnt"].median()),
                 "mean_fico": float(g["fico"].mean()),
                 "mean_int_rate": float(g["int_rate"].mean()),
                 "charge_off_rate": float(g["default"].mean()),
                 "mean_net_return": float(g["net_return"].mean())})
log(f"{'Q':>3} {'n':>9} {'med bc limit':>13} {'med loan $':>11} {'mean FICO':>10} "
    f"{'mean APR':>9} {'CO% cnt':>8} {'net ret/$100':>13}")
for r in rows:
    log(f"{r['q']:>3} {r['n']:>9,} {r['median_total_bc_limit']:>13,.0f} "
        f"{r['median_funded_amnt']:>11,.0f} {r['mean_fico']:>10.1f} "
        f"{r['mean_int_rate']:>9.2f} {r['charge_off_rate']*100:>8.2f} "
        f"{r['mean_net_return']:>13.3f}")
# within-cell FICO gap
rf_f = within_cell_rankfrac(codes, ncell, S["fico"].values)
m = S["q_bc"] >= 0
fic = S["fico"].values
cnt = np.bincount(codes[m.values], minlength=ncell).astype(float)
fbar = np.bincount(codes[m.values], weights=fic[m.values], minlength=ncell) / np.maximum(cnt, 1)
fdev = fic[m.values] - fbar[codes[m.values]]
qm = S["q_bc"].values[m.values]
fico_gap_within = float(fdev[qm == 4].mean() - fdev[qm == 0].mean())
fico_gap_raw = float(fic[m.values][qm == 4].mean() - fic[m.values][qm == 0].mean())
log(f"FICO Q5-Q1 gap: raw within this sample {fico_gap_raw:+.2f} points; "
    f"AFTER removing the cell mean (i.e. inside sub_grade x year x 20-pt FICO band) "
    f"{fico_gap_within:+.2f} points.")
log(f"Loan size Q1 median ${rows[0]['median_funded_amnt']:,.0f} vs Q5 median "
    f"${rows[4]['median_funded_amnt']:,.0f} - which is exactly why the outcome below is "
    f"dollars per $100 of original principal, not a loan count.")
R["quintile_diagnostics"] = rows
R["fico_gap_raw_q5_q1"] = fico_gap_raw
R["fico_gap_within_cell_q5_q1"] = fico_gap_within
R["n_cells_headline"] = int(ncell)
R["n_cells_usable_headline"] = int(okcell.sum())

# ------------------------------------------------------------------ HEADLINE
log("")
log("=" * 78)
log("HEADLINE (PRE-SPECIFIED) - within-cell quintiles of log(total_bc_limit+1)")
log("outcome = realized cash per $100 of original principal; SEs clustered on cell")
log("=" * 78)
head = fe_quintile_reg(S["net_return"].values, codes, qh, ncell)
R["headline"] = head
log(f"N used = {head['n']:,}   clusters (cells) = {head['n_clusters']:,}")
log(f"{'Q':>3} {'n':>9} {'raw mean net ret/$100':>23} {'cell-FE coef vs Q1':>20}")
for j in range(5):
    log(f"{j+1:>3} {head['q_n'][j]:>9,} {head['q_raw_mean'][j]:>23.4f} "
        f"{head['fe_coef_vs_Q1'][j]:>20.4f}")
log("")
log(f"Q5 - Q1 = {head['q5_minus_q1']:+.4f} dollars per $100 of original principal (LIFETIME)")
log(f"   clustered SE (on cell) = {head['se_cluster']:.4f}   t = {head['t_cluster']:+.2f}")
log(f"   unclustered HC0 SE     = {head['se_hc0']:.4f}   t = {head['t_hc0']:+.2f}")
log(f"   clustering inflates the SE by {head['se_cluster']/head['se_hc0']:.2f}x")
log(f"   monotone increasing in the quintile? {head['monotone_increasing']}")
ann = head["q5_minus_q1"] / int_life
ann_se = head["se_cluster"] / int_life
log(f"   APPROXIMATION ONLY, clearly labelled: divided by the MEASURED interest-earning "
    f"life of {int_life:.4f}y -> {ann:+.4f} pp/yr = {ann*100:+.0f} bps/yr "
    f"(clustered SE {ann_se*100:.0f} bps).")
log(f"   This annualisation is an approximation: it spreads a lifetime cash difference "
    f"over an average life and ignores the timing of the cashflows.")
R["headline_annualised"] = {"interest_earning_life": int_life, "spread_pp_per_yr": ann,
                            "se_pp_per_yr": ann_se}

# ------------------------------------------------------------------ robustness
log("")
log("-" * 78)
log("ROBUSTNESS (never the headline)")
log("-" * 78)
rob = {}

S17 = make_sample("36 months", [2012, 2013, 2014, 2015, 2016, 2017])
c17, n17 = cellcodes(S17, ["sub_grade", "issue_year", "fico_band"])
q17, _ = within_cell_quintile(c17, n17, np.log(S17["total_bc_limit"].values + 1.0))
r = fe_quintile_reg(S17["net_return"].values, c17, q17, n17)
rob["pooled_2012_2017"] = r
log(f"2012-2017 pooled (incl. immature 2016-17): N={r['n']:,} cells={r['n_clusters']:,}  "
    f"Q5-Q1 = {r['q5_minus_q1']:+.4f} /$100 (cl SE {r['se_cluster']:.4f}, t {r['t_cluster']:+.2f})")

c_nf, n_nf = cellcodes(S, ["sub_grade", "issue_year"])
q_nf, _ = within_cell_quintile(c_nf, n_nf, lbc)
r = fe_quintile_reg(S["net_return"].values, c_nf, q_nf, n_nf)
rob["cells_subgrade_x_year_no_fico"] = r
log(f"cells = sub_grade x issue_year (NO FICO band): N={r['n']:,} cells={r['n_clusters']:,}  "
    f"Q5-Q1 = {r['q5_minus_q1']:+.4f} /$100 (cl SE {r['se_cluster']:.4f}, t {r['t_cluster']:+.2f})")

c_sg, n_sg = cellcodes(S, ["sub_grade"])
q_sg, _ = within_cell_quintile(c_sg, n_sg, lbc)
r = fe_quintile_reg(S["net_return"].values, c_sg, q_sg, n_sg)
rob["cells_subgrade_only"] = r
log(f"cells = sub_grade only: N={r['n']:,} cells={r['n_clusters']:,}  "
    f"Q5-Q1 = {r['q5_minus_q1']:+.4f} /$100 (cl SE {r['se_cluster']:.4f}, t {r['t_cluster']:+.2f})")

# 60-month, run separately, mature vintages only (2012-2013 are past 60m maturity by 2018Q4)
for yrs, tag in [([2012, 2013], "60m_2012_2013_mature"), ([2012, 2013, 2014, 2015], "60m_2012_2015")]:
    S60 = make_sample("60 months", yrs)
    if len(S60) > 5000:
        c60, n60 = cellcodes(S60, ["sub_grade", "issue_year", "fico_band"])
        q60, _ = within_cell_quintile(c60, n60, np.log(S60["total_bc_limit"].values + 1.0))
        r = fe_quintile_reg(S60["net_return"].values, c60, q60, n60)
        life60 = float(S60["total_rec_int"].sum() / (S60["funded_amnt"] * S60["int_rate"] / 100.0).sum())
        r["interest_earning_life"] = life60
        r["charge_off_rate"] = float(S60["default"].mean())
        r["mean_net_return"] = float(S60["net_return"].mean())
        rob[tag] = r
        log(f"60-MONTH loans, {yrs[0]}-{yrs[-1]} (run separately, never pooled): "
            f"N={r['n']:,} cells={r['n_clusters']:,} CO {r['charge_off_rate']*100:.1f}% "
            f"mean net return {r['mean_net_return']:+.2f}/$100; interest-earning life {life60:.3f}y")
        log(f"     Q5-Q1 = {r['q5_minus_q1']:+.4f} /$100 (cl SE {r['se_cluster']:.4f}, "
            f"t {r['t_cluster']:+.2f}); annualised {r['q5_minus_q1']/life60*100:+.0f} bps/yr; "
            f"monotone {r['monotone_increasing']}")
R["robustness"] = rob

# ------------------------------------------------------------------ HORSE RACE
log("")
log("=" * 78)
log("THE HORSE RACE - identical cells, identical realized-cash outcome, one field at a time")
log("=" * 78)
pop = {}
for f in BUREAU:
    pop[f] = float(S[f].notna().mean())
elig = [f for f in BUREAU if pop[f] >= 0.60]
drop = [f for f in BUREAU if pop[f] < 0.60]
log(f"Fields populated for >=60% of the headline sample: {len(elig)} of {len(BUREAU)}")
log(f"Excluded for <60% population: " + ", ".join(f"{f} ({pop[f]*100:.0f}%)" for f in drop))
R["field_population"] = pop
R["excluded_low_population"] = drop

race = []
degenerate = []
yb = S["default"].values
nr = S["net_return"].values
for f in elig:
    x = S[f].values.astype(float)
    q, _ = within_cell_quintile(codes, ncell, x)
    res = fe_quintile_reg(nr, codes, q, ncell)
    if res is None or res["q_n"][0] < MIN_TAIL or res["q_n"][4] < MIN_TAIL:
        degenerate.append((f, None if res is None else (res["q_n"][0], res["q_n"][4])))
        continue
    rf = within_cell_rankfrac(codes, ncell, x)
    lg = logit_within_cell(yb, codes, ncell, rf)
    race.append({
        "field": f, "klass": klass(f), "population": pop[f],
        "n": res["n"], "n_clusters": res["n_clusters"],
        "q_n": res["q_n"], "q_raw_mean": res["q_raw_mean"],
        "fe_coef_vs_Q1": res["fe_coef_vs_Q1"],
        "q5_minus_q1": res["q5_minus_q1"], "se_cluster": res["se_cluster"],
        "se_hc0": res["se_hc0"], "t_cluster": res["t_cluster"], "t_hc0": res["t_hc0"],
        "monotone_up": res["monotone_increasing"], "monotone_down": res["monotone_decreasing"],
        "logit_coef": lg["coef_top_vs_bottom_logodds"], "logit_z": lg["z_cluster"],
        "logit_n": lg["n"],
        "ann_bps": res["q5_minus_q1"] / int_life * 100.0,
    })
race.sort(key=lambda r: -abs(r["q5_minus_q1"]))
for i, r in enumerate(race, 1):
    r["rank"] = i
R["horse_race"] = race
R["degenerate_fields"] = [{"field": f, "tails": t} for f, t in degenerate]

log(f"Fields that could not form both a Q1 and a Q5 with >= {MIN_TAIL} loans "
    f"(too few distinct values): {', '.join(f for f, _ in degenerate) if degenerate else 'none'}")
log("")
log("FULL RANKED TABLE, by |Q5 - Q1| in realized net return per $100 of original principal")
log("direction '+' means the HIGH quintile of the field earned MORE realized cash")
log("")
log(f"{'#':>3} {'field':<28} {'class':<13} {'N':>8} {'Q5-Q1':>9} {'clSE':>7} {'t':>8} "
    f"{'bps/yr':>8} {'logit z':>9} {'mono':>5} {'pop%':>5}")
for r in race:
    mono = "up" if r["monotone_up"] else ("down" if r["monotone_down"] else "-")
    log(f"{r['rank']:>3} {r['field']:<28} {r['klass']:<13} {r['n']:>8,} "
        f"{r['q5_minus_q1']:>+9.3f} {r['se_cluster']:>7.3f} {r['t_cluster']:>+8.2f} "
        f"{r['ann_bps']:>+8.0f} {r['logit_z']:>+9.2f} {mono:>5} {r['population']*100:>5.0f}")

bc = [r for r in race if r["field"] == "total_bc_limit"][0]
log("")
log(f"WHERE total_bc_limit FALLS: rank {bc['rank']} of {len(race)} by absolute realized "
    f"net-return spread (Q5-Q1 = {bc['q5_minus_q1']:+.3f} /$100 = {bc['ann_bps']:+.0f} bps/yr).")
log("TOP FIVE fields: " + "; ".join(
    f"{r['field']} ({r['klass']}, {r['q5_minus_q1']:+.3f}/$100, {r['ann_bps']:+.0f} bps/yr)"
    for r in race[:5]))

# class test
log("")
log("-" * 78)
log("CLASS TEST (classification was written down in PRE_REGISTRATION.txt BEFORE the ranking)")
log("-" * 78)
for cl in ["OTHER-LENDER", "BORROWER", "MIXED"]:
    sub = [r for r in race if r["klass"] == cl]
    if not sub:
        continue
    ranks = [r["rank"] for r in sub]
    spreads = [abs(r["q5_minus_q1"]) for r in sub]
    log(f"{cl:<13}: {len(sub):>2} fields, median rank {np.median(ranks):.1f}, "
        f"mean |Q5-Q1| {np.mean(spreads):.3f}, median |Q5-Q1| {np.median(spreads):.3f}, "
        f"best rank {min(ranks)} ({[r['field'] for r in sub if r['rank']==min(ranks)][0]})")
top10 = race[:10]
log(f"Composition of the TOP 10: "
    f"{sum(1 for r in top10 if r['klass']=='OTHER-LENDER')} other-lender, "
    f"{sum(1 for r in top10 if r['klass']=='BORROWER')} borrower-state, "
    f"{sum(1 for r in top10 if r['klass']=='MIXED')} mixed "
    f"(out of {sum(1 for r in race if r['klass']=='OTHER-LENDER')} / "
    f"{sum(1 for r in race if r['klass']=='BORROWER')} / "
    f"{sum(1 for r in race if r['klass']=='MIXED')} available)")
# Mann-Whitney style comparison of ranks between the two classes
ol = np.array([r["rank"] for r in race if r["klass"] == "OTHER-LENDER"], float)
bo = np.array([r["rank"] for r in race if r["klass"] == "BORROWER"], float)
wins = 0.0
for a in ol:
    wins += np.sum(a < bo) + 0.5 * np.sum(a == bo)
prob = wins / (len(ol) * len(bo))
log(f"P(a random OTHER-LENDER field outranks a random BORROWER-STATE field) = {prob:.3f} "
    f"(0.50 = no difference; >0.50 favours the free-riding reading)")
R["class_test"] = {
    "prob_other_lender_outranks_borrower": float(prob),
    "by_class": {cl: {"n": len([r for r in race if r["klass"] == cl]),
                      "median_rank": float(np.median([r["rank"] for r in race if r["klass"] == cl])),
                      "mean_abs_spread": float(np.mean([abs(r["q5_minus_q1"]) for r in race if r["klass"] == cl])),
                      "fields": [r["field"] for r in race if r["klass"] == cl]}
                 for cl in ["OTHER-LENDER", "BORROWER", "MIXED"]
                 if any(r["klass"] == cl for r in race)},
    "top10_classes": [r["klass"] for r in top10],
    "total_bc_limit_rank": bc["rank"], "n_fields": len(race),
}

# ------------------------------------------------------------------ acc_open_past_24mths
log("")
log("-" * 78)
log("acc_open_past_24mths - the purest 'other lenders just approved this person' proxy")
log("-" * 78)
ao = [r for r in race if r["field"] == "acc_open_past_24mths"]
if ao:
    a = ao[0]
    q_ao, _ = within_cell_quintile(codes, ncell, S["acc_open_past_24mths"].values.astype(float))
    log(f"rank {a['rank']} of {len(race)}; N={a['n']:,}; cells={a['n_clusters']:,}")
    log(f"{'Q':>3} {'n':>9} {'median accts opened 24m':>25} {'raw mean net ret':>18} "
        f"{'FE coef vs Q1':>15} {'CO% cnt':>8}")
    for j in range(5):
        g = S[q_ao == j]
        log(f"{j+1:>3} {a['q_n'][j]:>9,} {g['acc_open_past_24mths'].median():>25.0f} "
            f"{a['q_raw_mean'][j]:>18.3f} {a['fe_coef_vs_Q1'][j]:>15.3f} "
            f"{g['default'].mean()*100:>8.2f}")
    log(f"Q5 - Q1 = {a['q5_minus_q1']:+.4f} /$100 (clustered SE {a['se_cluster']:.4f}, "
        f"t {a['t_cluster']:+.2f}) = {a['ann_bps']:+.0f} bps/yr")
    log(f"within-cell logistic on charge-off, top vs bottom of the field: "
        f"{a['logit_coef']:+.4f} log-odds (clustered z {a['logit_z']:+.2f})")
    R["acc_open_24m"] = a

# ------------------------------------------------------------------ EX ANTE
log("")
log("=" * 78)
log("EX-ANTE IMPLEMENTABILITY - breakpoints cut on PRIOR vintages only, applied forward")
log("=" * 78)


def ex_ante(field, sample, years):
    """For each target year, cut breakpoints on sub_grade x fico_band using STRICTLY
    EARLIER vintages, apply them to the target year, and estimate Q5-Q1 with cell FE
    (cells = sub_grade x fico_band within that year), clustered."""
    out = []
    x_all = sample[field].values.astype(float)
    grp_key = sample["sub_grade"].astype(str) + "|" + sample["fico_band"].astype(str)
    gcodes, guniq = pd.factorize(grp_key, sort=True)
    ng = len(guniq)
    yrs = sample["issue_year"].values
    for ty in years[1:]:
        prior = (yrs < ty) & np.isfinite(x_all)
        tgt = (yrs == ty) & np.isfinite(x_all)
        if tgt.sum() < 2000:
            continue
        # breakpoints per group from prior vintages
        bp = np.full((ng, 4), np.nan)
        cnts = np.zeros(ng, dtype=int)
        pc = gcodes[prior]
        pv = x_all[prior]
        order = np.lexsort((pv, pc))
        cs, vs = pc[order], pv[order]
        counts = np.bincount(cs, minlength=ng)
        starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
        safe = np.maximum(counts - 1, 0)
        for j, p in enumerate([0.2, 0.4, 0.6, 0.8]):
            idx = np.clip(starts + np.minimum((p * counts).astype(np.int64), safe), 0, max(len(vs) - 1, 0))
            if len(vs):
                bp[:, j] = vs[idx]
        cnts = counts
        good = cnts >= MIN_CELL
        tc = gcodes[tgt]
        tv = x_all[tgt]
        ok = good[tc]
        b = bp[tc]
        q = ((tv > b[:, 0]).astype(np.int64) + (tv > b[:, 1]) + (tv > b[:, 2]) + (tv > b[:, 3]))
        q = np.where(ok & np.isfinite(b[:, 0]), q, -1)
        qfull = np.full(len(sample), -1, dtype=np.int64)
        qfull[np.flatnonzero(tgt)] = q
        res = fe_quintile_reg(sample["net_return"].values, gcodes.astype(np.int64), qfull, ng)
        if res is None:
            continue
        res["target_year"] = int(ty)
        res["breakpoint_years"] = f"{years[0]}-{ty-1}"
        res["ann_bps"] = res["q5_minus_q1"] / int_life * 100.0
        out.append(res)
    return out


ea = ex_ante("total_bc_limit", S, [2012, 2013, 2014, 2015])
log("total_bc_limit, breakpoints from prior vintages only, cells = sub_grade x FICO band "
    "inside the target year:")
log(f"{'target yr':>10} {'breakpts from':>15} {'N':>9} {'cells':>7} {'Q5-Q1':>9} "
    f"{'clSE':>7} {'t':>8} {'bps/yr':>8} {'mono':>6}")
tot_n = 0
tot_w = 0.0
for r in ea:
    mono = "up" if r["monotone_increasing"] else ("down" if r["monotone_decreasing"] else "-")
    log(f"{r['target_year']:>10} {r['breakpoint_years']:>15} {r['n']:>9,} {r['n_clusters']:>7,} "
        f"{r['q5_minus_q1']:>+9.3f} {r['se_cluster']:>7.3f} {r['t_cluster']:>+8.2f} "
        f"{r['ann_bps']:>+8.0f} {mono:>6}")
    tot_n += r["n"]
    tot_w += r["q5_minus_q1"] * r["n"]
if tot_n:
    log(f"N-weighted average ex-ante spread across 2013-2015 = {tot_w/tot_n:+.3f} /$100 "
        f"= {tot_w/tot_n/int_life*100:+.0f} bps/yr, versus the in-sample (hindsight) "
        f"headline of {head['q5_minus_q1']:+.3f} /$100 = {head['q5_minus_q1']/int_life*100:+.0f} bps/yr.")
R["ex_ante"] = {"by_year": ea,
                "weighted_avg_spread": float(tot_w / tot_n) if tot_n else None,
                "weighted_avg_bps": float(tot_w / tot_n / int_life * 100) if tot_n else None,
                "in_sample_headline_spread": head["q5_minus_q1"]}

# ex ante for the top-ranked field too, as a comparison
top_field = race[0]["field"]
if top_field != "total_bc_limit":
    ea2 = ex_ante(top_field, S, [2012, 2013, 2014, 2015])
    tn = sum(r["n"] for r in ea2)
    tw = sum(r["q5_minus_q1"] * r["n"] for r in ea2)
    log(f"For comparison, the same ex-ante rule on the top-ranked field "
        f"({top_field}): N-weighted spread {tw/tn:+.3f} /$100 = {tw/tn/int_life*100:+.0f} bps/yr")
    R["ex_ante_top_field"] = {"field": top_field, "by_year": ea2,
                              "weighted_avg_spread": float(tw / tn) if tn else None,
                              "weighted_avg_bps": float(tw / tn / int_life * 100) if tn else None}

# ------------------------------------------------------------------ write
with open(OUT_TXT, "w", encoding="utf-8") as fh:
    fh.write("\n".join(L))


def jsonable(o):
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, float) and (np.isnan(o) or np.isinf(o)):
        return None
    return o


with open(OUT_JSON, "w", encoding="utf-8") as fh:
    json.dump(jsonable(R), fh, indent=2)
print(f"\nWrote {OUT_TXT} and {OUT_JSON}")
