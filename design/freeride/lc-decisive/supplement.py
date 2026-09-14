"""
Supplement to lc_decisive.py. Three things:
 1. Split the pre-registered OTHER-LENDER class into the three sub-kinds that the
    pre-registration itself named - LIMITS GRANTED, ACCOUNTS APPROVED, APPROVAL
    TIMING - because only LIMITS GRANTED is the free-riding construct.
 2. Does total_bc_limit survive once the cell also conditions on the strongest
    other-lender field (acc_open_past_24mths)?
 3. The headline statistic by letter grade (the earlier claim was loudest in grade A).
"""
import json
import os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
import importlib.util
spec = importlib.util.spec_from_file_location("lcd", os.path.join(HERE, "lc_decisive.py"))

DATA = ("C:/Users/samwe/AppData/Local/Temp/claude/"
        "c--Users-samwe-OneDrive-Documents-codex-projects-Job-autoapply/"
        "8b3ac5c3-74cb-44aa-9894-816ca22156c2/scratchpad/freeride-data/"
        "LendingClub_2007_to_2018Q4.csv")
RES = json.load(open(os.path.join(HERE, "results.json")))
MIN_CELL = 25
L = []
def log(s=""):
    s = str(s)
    print(s)
    L.append(s)

OUT = {}

# ---------------------------------------------------------------- 1. sub-class split
LIMITS_GRANTED = {"total_bc_limit", "total_rev_hi_lim", "tot_hi_cred_lim",
                  "total_il_high_credit_limit"}
APPROVAL_TIMING = {"mo_sin_old_rev_tl_op", "mo_sin_old_il_acct", "mo_sin_rcnt_rev_tl_op",
                   "mo_sin_rcnt_tl", "mths_since_recent_bc"}
race = RES["horse_race"]

def sub(f):
    if f in LIMITS_GRANTED:
        return "LIMITS-GRANTED"
    if f in APPROVAL_TIMING:
        return "APPROVAL-TIMING"
    if RES["class_test"]["by_class"]["OTHER-LENDER"]["fields"].count(f):
        return "ACCOUNTS-APPROVED"
    return None

log("=" * 78)
log("SUPPLEMENT 1 - the pre-registered OTHER-LENDER class split into its three named")
log("sub-kinds. Only LIMITS-GRANTED is the free-riding construct ('other lenders")
log("extended this person a big line, so they vouched for him').")
log("=" * 78)
log(f"{'sub-kind':<20} {'n':>3} {'median rank':>12} {'mean |Q5-Q1|':>13} {'signs':>22}")
groups = {}
for r in race:
    s = sub(r["field"])
    if s:
        groups.setdefault(s, []).append(r)
bor = [r for r in race if r["klass"] == "BORROWER"]
groups["BORROWER-OWN-STATE"] = bor
for k, v in sorted(groups.items(), key=lambda kv: np.median([r["rank"] for r in kv[1]])):
    pos = sum(1 for r in v if r["q5_minus_q1"] > 0)
    log(f"{k:<20} {len(v):>3} {np.median([r['rank'] for r in v]):>12.1f} "
        f"{np.mean([abs(r['q5_minus_q1']) for r in v]):>13.3f} "
        f"{str(pos)+' up / '+str(len(v)-pos)+' down':>22}")
log("")
log("LIMITS-GRANTED fields, individually (this is the free-riding construct):")
log(f"{'field':<30} {'rank':>5} {'Q5-Q1':>9} {'clSE':>7} {'t':>8} {'bps/yr':>8}")
for r in sorted([x for x in race if sub(x['field']) == 'LIMITS-GRANTED'], key=lambda x: x["rank"]):
    log(f"{r['field']:<30} {r['rank']:>5} {r['q5_minus_q1']:>+9.3f} {r['se_cluster']:>7.3f} "
        f"{r['t_cluster']:>+8.2f} {r['ann_bps']:>+8.0f}")
OUT["subclass"] = {k: {"n": len(v), "median_rank": float(np.median([r["rank"] for r in v])),
                       "mean_abs_spread": float(np.mean([abs(r["q5_minus_q1"]) for r in v])),
                       "n_positive": int(sum(1 for r in v if r["q5_minus_q1"] > 0)),
                       "fields": [r["field"] for r in v]}
                   for k, v in groups.items()}

# ---------------------------------------------------------------- reload data for 2 & 3
KEEP = ["term", "issue_d", "loan_status", "funded_amnt", "int_rate", "grade", "sub_grade",
        "fico_range_low", "fico_range_high", "total_rec_prncp", "total_rec_int",
        "recoveries", "collection_recovery_fee", "total_bc_limit", "acc_open_past_24mths"]
chunks = []
for ch in pd.read_csv(DATA, usecols=KEEP, low_memory=False, chunksize=300000):
    ch["term"] = ch["term"].astype(str).str.strip()
    ch = ch[(ch["term"] == "36 months") & ch["loan_status"].isin(["Fully Paid", "Charged Off"])]
    chunks.append(ch)
S = pd.concat(chunks, ignore_index=True)
S["issue_year"] = pd.to_datetime(S["issue_d"], format="%b-%Y", errors="coerce").dt.year
S = S[S["issue_year"].isin([2012, 2013, 2014, 2015])]
for c in ["funded_amnt", "total_rec_prncp", "total_rec_int", "recoveries",
          "collection_recovery_fee", "fico_range_low", "fico_range_high",
          "total_bc_limit", "acc_open_past_24mths", "int_rate"]:
    S[c] = pd.to_numeric(S[c], errors="coerce")
S = S[S["funded_amnt"] > 0].copy()
S["fico"] = (S["fico_range_low"] + S["fico_range_high"]) / 2.0
S["fico_band"] = np.floor(S["fico"] / 20.0) * 20.0
S["net_return"] = 100.0 * (S["total_rec_int"] + S["total_rec_prncp"] + S["recoveries"]
                           - S["collection_recovery_fee"] - S["funded_amnt"]) / S["funded_amnt"]
S["default"] = (S["loan_status"] == "Charged Off").astype(float)
S = S[S["fico"].notna() & S["net_return"].notna() & S["sub_grade"].notna()].reset_index(drop=True)
LIFE = RES["lgd_and_life"]["interest_earning_life_years"]

# ---- copy the two estimators (kept identical to lc_decisive.py) ----
def cellcodes(s, keys):
    key = s[keys[0]].astype(str)
    for k in keys[1:]:
        key = key + "|" + s[k].astype(str)
    codes, uniq = pd.factorize(key, sort=True)
    return codes.astype(np.int64), len(uniq)

def within_cell_quintile(codes, ncell, x, min_cell=MIN_CELL):
    x = np.asarray(x, dtype=float)
    q = np.full(len(x), -1, dtype=np.int64)
    valid = np.isfinite(x)
    if valid.sum() == 0:
        return q
    c = codes[valid]; v = x[valid]
    order = np.lexsort((v, c)); cs, vs = c[order], v[order]
    counts = np.bincount(cs, minlength=ncell)
    starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
    newv = np.ones(len(cs), dtype=bool)
    newv[1:] = (cs[1:] != cs[:-1]) | (vs[1:] != vs[:-1])
    ndist = np.bincount(cs[newv], minlength=ncell)
    ok_cell = (counts >= min_cell) & (ndist >= 2)
    bp = np.zeros((ncell, 4)); safe = np.maximum(counts - 1, 0)
    for j, p in enumerate([0.2, 0.4, 0.6, 0.8]):
        idx = np.clip(starts + np.minimum((p * counts).astype(np.int64), safe), 0, len(vs) - 1)
        bp[:, j] = vs[idx]
    bpv = bp[c]
    qv = ((v > bpv[:, 0]).astype(np.int64) + (v > bpv[:, 1]) + (v > bpv[:, 2]) + (v > bpv[:, 3]))
    q[valid] = np.where(ok_cell[c], qv, -1)
    return q

def fe_quintile_reg(y, codes, q, ncell):
    m = q >= 0
    y = np.asarray(y, float)[m]; c = codes[m]; qq = q[m]
    has1 = np.bincount(c, weights=(qq == 0).astype(float), minlength=ncell)
    has5 = np.bincount(c, weights=(qq == 4).astype(float), minlength=ncell)
    keep = (has1 > 0) & (has5 > 0); m2 = keep[c]
    y, c, qq = y[m2], c[m2], qq[m2]
    if len(y) < 100:
        return None
    uc, c = np.unique(c, return_inverse=True); G = len(uc); n = len(y)
    X = np.column_stack([(qq == k).astype(float) for k in range(1, 5)])
    cnt = np.bincount(c, minlength=G).astype(float)
    yt = y - (np.bincount(c, weights=y, minlength=G) / cnt)[c]
    Xt = np.empty_like(X)
    for j in range(4):
        Xt[:, j] = X[:, j] - (np.bincount(c, weights=X[:, j], minlength=G) / cnt)[c]
    XtXi = np.linalg.pinv(Xt.T @ Xt)
    beta = XtXi @ (Xt.T @ yt); u = yt - Xt @ beta
    Sm = np.zeros((4, 4))
    o = np.argsort(c, kind="stable"); cc, Xc, ucr = c[o], Xt[o], u[o]
    bnd = np.concatenate([[0], np.flatnonzero(np.diff(cc)) + 1, [len(cc)]])
    for a, b in zip(bnd[:-1], bnd[1:]):
        s = Xc[a:b].T @ ucr[a:b]; Sm += np.outer(s, s)
    dfc = (G / max(G - 1.0, 1.0)) * ((n - 1.0) / max(n - 4 - G, 1.0))
    V = XtXi @ Sm @ XtXi * dfc
    coefs = [0.0] + [float(b) for b in beta]
    return {"n": int(n), "G": int(G), "q5_minus_q1": float(beta[3]),
            "se": float(np.sqrt(max(V[3, 3], 0))),
            "t": float(beta[3] / np.sqrt(max(V[3, 3], 1e-300))),
            "coefs": coefs, "q_n": [int((qq == j).sum()) for j in range(5)],
            "mono": bool(all(coefs[i] <= coefs[i + 1] + 1e-12 for i in range(4)))}

# ---------------------------------------------------------------- 2. conditioning test
log("")
log("=" * 78)
log("SUPPLEMENT 2 - does total_bc_limit survive conditioning on acc_open_past_24mths?")
log("=" * 78)
c0, n0 = cellcodes(S, ["sub_grade", "issue_year", "fico_band"])
q_ao = within_cell_quintile(c0, n0, S["acc_open_past_24mths"].values.astype(float))
S["q_ao"] = q_ao
base = fe_quintile_reg(S["net_return"].values, c0,
                       within_cell_quintile(c0, n0, np.log(S["total_bc_limit"].values + 1.0)), n0)
S2 = S[S["q_ao"] >= 0].copy()
c1, n1 = cellcodes(S2, ["sub_grade", "issue_year", "fico_band", "q_ao"])
q_bc2 = within_cell_quintile(c1, n1, np.log(S2["total_bc_limit"].values + 1.0))
cond = fe_quintile_reg(S2["net_return"].values, c1, q_bc2, n1)
log(f"cells = sub_grade x year x FICO band                  : Q5-Q1(bc limit) "
    f"{base['q5_minus_q1']:+.3f} /$100 (cl SE {base['se']:.3f}, t {base['t']:+.2f}), "
    f"N={base['n']:,}, cells={base['G']:,}")
log(f"cells = ... x acc_open_past_24mths quintile           : Q5-Q1(bc limit) "
    f"{cond['q5_minus_q1']:+.3f} /$100 (cl SE {cond['se']:.3f}, t {cond['t']:+.2f}), "
    f"N={cond['n']:,}, cells={cond['G']:,}")
log(f"-> {cond['q5_minus_q1']/base['q5_minus_q1']*100:.0f}% of the bankcard-limit spread "
    f"remains once the cell also holds recent third-party approvals fixed.")
# and the reverse
q_bc0 = within_cell_quintile(c0, n0, np.log(S["total_bc_limit"].values + 1.0))
S["q_bc"] = q_bc0
S3 = S[S["q_bc"] >= 0].copy()
c2, n2 = cellcodes(S3, ["sub_grade", "issue_year", "fico_band", "q_bc"])
q_ao2 = within_cell_quintile(c2, n2, S3["acc_open_past_24mths"].values.astype(float))
rev = fe_quintile_reg(S3["net_return"].values, c2, q_ao2, n2)
base_ao = fe_quintile_reg(S["net_return"].values, c0, q_ao, n0)
log(f"REVERSE: acc_open_past_24mths spread {base_ao['q5_minus_q1']:+.3f} -> "
    f"{rev['q5_minus_q1']:+.3f} /$100 (cl SE {rev['se']:.3f}, t {rev['t']:+.2f}) once the cell "
    f"also holds the bankcard-limit quintile fixed "
    f"({rev['q5_minus_q1']/base_ao['q5_minus_q1']*100:.0f}% survives).")
OUT["conditioning"] = {"bc_base": base, "bc_given_acc24": cond,
                       "acc24_base": base_ao, "acc24_given_bc": rev}

# ---------------------------------------------------------------- 3. by letter grade
log("")
log("=" * 78)
log("SUPPLEMENT 3 - headline statistic by LETTER GRADE (the old claim was loudest in A)")
log("=" * 78)
log(f"{'grade':>5} {'N':>9} {'cells':>6} {'Q5-Q1 bc limit':>15} {'clSE':>7} {'t':>8} "
    f"{'bps/yr':>8} {'| acc_open_24m Q5-Q1':>21} {'t':>8}")
by_grade = {}
for g, sg in S.groupby("grade"):
    if len(sg) < 5000:
        continue
    cg, ng = cellcodes(sg, ["sub_grade", "issue_year", "fico_band"])
    rb = fe_quintile_reg(sg["net_return"].values, cg, within_cell_quintile(
        cg, ng, np.log(sg["total_bc_limit"].values + 1.0)), ng)
    ra = fe_quintile_reg(sg["net_return"].values, cg, within_cell_quintile(
        cg, ng, sg["acc_open_past_24mths"].values.astype(float)), ng)
    if rb is None:
        continue
    log(f"{g:>5} {rb['n']:>9,} {rb['G']:>6,} {rb['q5_minus_q1']:>+15.3f} {rb['se']:>7.3f} "
        f"{rb['t']:>+8.2f} {rb['q5_minus_q1']/LIFE*100:>+8.0f} "
        f"{ra['q5_minus_q1']:>+21.3f} {ra['t']:>+8.2f}")
    by_grade[g] = {"bc": rb, "acc24": ra}
OUT["by_grade"] = by_grade

# ---------------------------------------------------------------- 4. dollar-weighted check
log("")
log("=" * 78)
log("SUPPLEMENT 4 - the same headline weighted by ORIGINAL PRINCIPAL, not by loan")
log("=" * 78)
m = (S["q_bc"] >= 0).values
w = S["funded_amnt"].values[m]
q = S["q_bc"].values[m]
nr = S["net_return"].values[m]
for j in range(5):
    k = q == j
    log(f"   Q{j+1}: loan-weighted mean {nr[k].mean():+.3f} /$100, "
        f"principal-weighted {np.average(nr[k], weights=w[k]):+.3f} /$100, "
        f"principal ${w[k].sum()/1e9:.2f}bn")
log(f"   principal-weighted Q5-Q1 (NO cell FE, raw) = "
    f"{np.average(nr[q==4], weights=w[q==4]) - np.average(nr[q==0], weights=w[q==0]):+.3f} /$100")
OUT["principal_weighted"] = {
    f"Q{j+1}": {"loan_wtd": float(nr[q == j].mean()),
                "prin_wtd": float(np.average(nr[q == j], weights=w[q == j])),
                "principal_bn": float(w[q == j].sum() / 1e9)} for j in range(5)}

with open(os.path.join(HERE, "supplement.txt"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(L))

def js(o):
    if isinstance(o, dict):
        return {str(k): js(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [js(v) for v in o]
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o

with open(os.path.join(HERE, "supplement.json"), "w", encoding="utf-8") as fh:
    json.dump(js(OUT), fh, indent=2)
print("\nWrote supplement.txt and supplement.json")
