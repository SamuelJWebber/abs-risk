"""The 60-month book is the one place total_bc_limit looked strong. Race it there too,
same cells, same realized-cash outcome, clustered on the cell."""
import json, os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = ("C:/Users/samwe/AppData/Local/Temp/claude/"
        "c--Users-samwe-OneDrive-Documents-codex-projects-Job-autoapply/"
        "8b3ac5c3-74cb-44aa-9894-816ca22156c2/scratchpad/freeride-data/"
        "LendingClub_2007_to_2018Q4.csv")
MIN_CELL = 25
MIN_TAIL = 300
L = []
def log(s=""):
    s = str(s); print(s); L.append(s)

BUREAU = ["annual_inc","dti","delinq_2yrs","inq_last_6mths","open_acc","pub_rec","revol_bal",
 "revol_util","total_acc","collections_12_mths_ex_med","acc_now_delinq","tot_coll_amt",
 "tot_cur_bal","total_rev_hi_lim","acc_open_past_24mths","avg_cur_bal","bc_open_to_buy",
 "bc_util","chargeoff_within_12_mths","mo_sin_old_il_acct","mo_sin_old_rev_tl_op",
 "mo_sin_rcnt_rev_tl_op","mo_sin_rcnt_tl","mort_acc","mths_since_recent_bc",
 "mths_since_recent_inq","num_accts_ever_120_pd","num_actv_bc_tl","num_actv_rev_tl",
 "num_bc_sats","num_bc_tl","num_il_tl","num_op_rev_tl","num_rev_accts","num_rev_tl_bal_gt_0",
 "num_sats","num_tl_90g_dpd_24m","num_tl_op_past_12m","percent_bc_gt_75",
 "pub_rec_bankruptcies","tax_liens","tot_hi_cred_lim","total_bal_ex_mort","total_bc_limit",
 "total_il_high_credit_limit"]
OTHER_LENDER = {"total_bc_limit","total_rev_hi_lim","tot_hi_cred_lim","total_il_high_credit_limit",
 "acc_open_past_24mths","num_tl_op_past_12m","mort_acc","num_bc_tl","num_bc_sats","num_rev_accts",
 "num_il_tl","num_op_rev_tl","num_sats","open_acc","total_acc","mo_sin_old_rev_tl_op",
 "mo_sin_old_il_acct","mo_sin_rcnt_rev_tl_op","mo_sin_rcnt_tl","mths_since_recent_bc"}

KEEP = ["term","issue_d","loan_status","funded_amnt","int_rate","grade","sub_grade",
        "fico_range_low","fico_range_high","total_rec_prncp","total_rec_int","recoveries",
        "collection_recovery_fee"] + BUREAU
chunks = []
for ch in pd.read_csv(DATA, usecols=KEEP, low_memory=False, chunksize=300000):
    ch["term"] = ch["term"].astype(str).str.strip()
    ch = ch[(ch["term"] == "60 months") & ch["loan_status"].isin(["Fully Paid","Charged Off"])]
    chunks.append(ch)
S = pd.concat(chunks, ignore_index=True)
S["issue_year"] = pd.to_datetime(S["issue_d"], format="%b-%Y", errors="coerce").dt.year
S = S[S["issue_year"].isin([2012, 2013])]
for c in ["funded_amnt","total_rec_prncp","total_rec_int","recoveries","collection_recovery_fee",
          "fico_range_low","fico_range_high","int_rate"] + BUREAU:
    S[c] = pd.to_numeric(S[c], errors="coerce")
S = S[S["funded_amnt"] > 0].copy()
S["fico"] = (S["fico_range_low"] + S["fico_range_high"]) / 2.0
S["fico_band"] = np.floor(S["fico"] / 20.0) * 20.0
S["net_return"] = 100.0*(S["total_rec_int"]+S["total_rec_prncp"]+S["recoveries"]
                         -S["collection_recovery_fee"]-S["funded_amnt"])/S["funded_amnt"]
S = S[S["fico"].notna() & S["net_return"].notna() & S["sub_grade"].notna()].reset_index(drop=True)
LIFE = float(S["total_rec_int"].sum()/(S["funded_amnt"]*S["int_rate"]/100.0).sum())

def cellcodes(s, keys):
    key = s[keys[0]].astype(str)
    for k in keys[1:]:
        key = key + "|" + s[k].astype(str)
    codes, uniq = pd.factorize(key, sort=True)
    return codes.astype(np.int64), len(uniq)

def wcq(codes, ncell, x, min_cell=MIN_CELL):
    x = np.asarray(x, float); q = np.full(len(x), -1, np.int64)
    valid = np.isfinite(x)
    if valid.sum() == 0: return q
    c = codes[valid]; v = x[valid]
    o = np.lexsort((v, c)); cs, vs = c[o], v[o]
    cnt = np.bincount(cs, minlength=ncell)
    st = np.concatenate([[0], np.cumsum(cnt)[:-1]])
    nv = np.ones(len(cs), bool); nv[1:] = (cs[1:]!=cs[:-1])|(vs[1:]!=vs[:-1])
    nd = np.bincount(cs[nv], minlength=ncell)
    ok = (cnt>=min_cell)&(nd>=2)
    bp = np.zeros((ncell,4)); safe = np.maximum(cnt-1,0)
    for j,p in enumerate([.2,.4,.6,.8]):
        idx = np.clip(st+np.minimum((p*cnt).astype(np.int64),safe),0,len(vs)-1); bp[:,j]=vs[idx]
    b = bp[c]
    qv = ((v>b[:,0]).astype(np.int64)+(v>b[:,1])+(v>b[:,2])+(v>b[:,3]))
    q[valid] = np.where(ok[c], qv, -1)
    return q

def fe(y, codes, q, ncell):
    m = q>=0; y = np.asarray(y,float)[m]; c = codes[m]; qq = q[m]
    h1 = np.bincount(c, weights=(qq==0).astype(float), minlength=ncell)
    h5 = np.bincount(c, weights=(qq==4).astype(float), minlength=ncell)
    k = ((h1>0)&(h5>0))[c]; y,c,qq = y[k],c[k],qq[k]
    if len(y)<100: return None
    uc,c = np.unique(c, return_inverse=True); G=len(uc); n=len(y)
    X = np.column_stack([(qq==j).astype(float) for j in range(1,5)])
    cnt = np.bincount(c, minlength=G).astype(float)
    yt = y-(np.bincount(c,weights=y,minlength=G)/cnt)[c]
    Xt = np.empty_like(X)
    for j in range(4):
        Xt[:,j] = X[:,j]-(np.bincount(c,weights=X[:,j],minlength=G)/cnt)[c]
    Bi = np.linalg.pinv(Xt.T@Xt); b = Bi@(Xt.T@yt); u = yt-Xt@b
    Sm = np.zeros((4,4)); o = np.argsort(c,kind="stable"); cc,Xc,ur = c[o],Xt[o],u[o]
    bd = np.concatenate([[0], np.flatnonzero(np.diff(cc))+1, [len(cc)]])
    for a,z in zip(bd[:-1],bd[1:]):
        s = Xc[a:z].T@ur[a:z]; Sm += np.outer(s,s)
    dfc = (G/max(G-1.,1.))*((n-1.)/max(n-4-G,1.))
    V = Bi@Sm@Bi*dfc
    co = [0.0]+[float(x) for x in b]
    return {"n":int(n),"G":int(G),"q5_minus_q1":float(b[3]),
            "se":float(np.sqrt(max(V[3,3],0))),
            "t":float(b[3]/np.sqrt(max(V[3,3],1e-300))),
            "q_n":[int((qq==j).sum()) for j in range(5)],
            "mono":bool(all(co[i]<=co[i+1]+1e-12 for i in range(4)))}

log("="*78)
log("60-MONTH BOOK, MATURE VINTAGES 2012-2013 - the full horse race, same design")
log("="*78)
log(f"N = {len(S):,}; charge-off {100*(S['loan_status']=='Charged Off').mean():.2f}%; "
    f"measured interest-earning life {LIFE:.3f}y; mean net return "
    f"{S['net_return'].mean():+.2f} /$100")
codes, ncell = cellcodes(S, ["sub_grade","issue_year","fico_band"])
race = []
for f in BUREAU:
    if S[f].notna().mean() < 0.60: continue
    r = fe(S["net_return"].values, codes, wcq(codes,ncell,S[f].values.astype(float)), ncell)
    if r is None or r["q_n"][0]<MIN_TAIL or r["q_n"][4]<MIN_TAIL: continue
    r["field"]=f; r["klass"]="OTHER-LENDER" if f in OTHER_LENDER else ("MIXED" if f=="bc_open_to_buy" else "BORROWER")
    r["bps"]=r["q5_minus_q1"]/LIFE*100
    race.append(r)
race.sort(key=lambda r: -abs(r["q5_minus_q1"]))
log(f"{'#':>3} {'field':<28} {'class':<13} {'N':>7} {'Q5-Q1':>9} {'clSE':>7} {'t':>8} {'bps/yr':>8} {'mono':>5}")
for i,r in enumerate(race,1):
    r["rank"]=i
    log(f"{i:>3} {r['field']:<28} {r['klass']:<13} {r['n']:>7,} {r['q5_minus_q1']:>+9.3f} "
        f"{r['se']:>7.3f} {r['t']:>+8.2f} {r['bps']:>+8.0f} {str(r['mono']):>5}")
bc = [r for r in race if r["field"]=="total_bc_limit"][0]
log("")
log(f"total_bc_limit on the 60-month book: rank {bc['rank']} of {len(race)}.")
log("TOP FIVE: " + "; ".join(f"{r['field']} ({r['klass']}, {r['q5_minus_q1']:+.2f}/$100)" for r in race[:5]))
with open(os.path.join(HERE,"sixty_race.txt"),"w",encoding="utf-8") as fh: fh.write("\n".join(L))
with open(os.path.join(HERE,"sixty_race.json"),"w",encoding="utf-8") as fh:
    json.dump({"life":LIFE,"n":int(len(S)),"race":race}, fh, indent=2)
print("\nWrote sixty_race.txt / .json")
