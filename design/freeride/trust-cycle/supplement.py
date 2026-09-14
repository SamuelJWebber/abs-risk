"""Supplement: the shape of the cycle in months, the within-squeeze trend, and whether the mix
adjustment can change the cycle conclusion at all."""
import json
import os
import numpy as np
import pandas as pd

REPO = "C:/Users/samwe/code/abs-risk"
HERE = os.path.dirname(os.path.abspath(__file__))
TRUSTS = ["amex", "bofa", "chase", "citi", "comet", "synchrony"]
SHAPES = ["fico_odds", "fico_fed2007", "acms2018", "acms2018_dpd90"]
lines = []


def log(s=""):
    print(s)
    lines.append(str(s))


def tbl(df, f="%.4f"):
    return df.to_string(index=False, float_format=lambda v: f % v)


M = pd.read_csv(os.path.join(REPO, "data", "cards_monthly.csv"))
M["period_end"] = pd.to_datetime(M["period_end"])
M["ym"] = M["period_end"].dt.to_period("M")
W = M.pivot_table(index="ym", columns="trust", values="delinq_30plus_share")[TRUSTS].dropna()

log("=" * 100)
log("SUPPLEMENT - the cycle in months, not bins")
log("=" * 100)
log("")
log("Monthly 30+ share, every trust, and the amex/synchrony ratio. Aligned months only "
    f"(n={len(W)}, {W.index.min()}..{W.index.max()}).")
S = W.copy()
S["amex/sync"] = W["amex"] / W["synchrony"]
S["six_mean"] = W.mean(axis=1)
S["amex/six"] = W["amex"] / S["six_mean"]
S["sync/six"] = W["synchrony"] / S["six_mean"]
S["diff_pp"] = (W["amex"] - W["synchrony"]) * 100
S.round(5).to_csv(os.path.join(HERE, "supp_monthly_series.csv"))
q = S.reset_index()
q["ym"] = q["ym"].astype(str)
log(tbl(q[["ym", "amex", "synchrony", "six_mean", "amex/sync", "diff_pp", "amex/six", "sync/six"]], "%.5f"))

# --- within-squeeze trend in the log ratio
log("")
log("WITHIN-SQUEEZE TREND. Priority says the gap should keep widening as the squeeze deepens.")
log("Regress log(amex 30+ / synchrony 30+) on a linear month trend inside 2023-07..end.")


def nw_ols(y, X, lags=6):
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    e = y - X @ beta
    n, k = X.shape
    A = np.linalg.inv(X.T @ X)
    u = X * e[:, None]
    Sg = u.T @ u
    for L in range(1, lags + 1):
        w = 1.0 - L / (lags + 1.0)
        G = u[L:].T @ u[:-L]
        Sg += w * (G + G.T)
    cov = A @ Sg @ A * n / (n - k)
    return beta, np.sqrt(np.diag(cov))


rows = []
for lab, lo, hi in [("squeeze 2023-07..end", "2023-07", "2026-12"),
                    ("post-2022 2022-01..end", "2022-01", "2026-12"),
                    ("pre-covid 2019-01..2020-02", "2019-01", "2020-02")]:
    w = W[(W.index >= pd.Period(lo, "M")) & (W.index <= pd.Period(hi, "M"))]
    y = np.log(w["amex"].to_numpy() / w["synchrony"].to_numpy())
    t = np.arange(len(y), dtype=float)
    X = np.column_stack([np.ones_like(t), t])
    b, se = nw_ols(y, X, lags=min(6, max(1, len(y) // 4)))
    rows.append({"window": lab, "n": len(y), "intercept": b[0], "slope_per_month": b[1],
                 "slope_se": se[1], "z": b[1] / se[1], "slope_per_year_pct": 100 * (np.exp(12 * b[1]) - 1)})
T = pd.DataFrame(rows)
log(tbl(T, "%.5f"))
log("  slope_per_year_pct: percent change in the ratio per year implied by the trend.")

# --- is the 2020 compression amex-specific, or common to all five vs synchrony?
log("")
log("IS THE 2020 COMPRESSION AMEX-SPECIFIC? Change in log(trust/synchrony) from calendar 2019 to 2020.")
M["year"] = M["period_end"].dt.year
yr = M.groupby(["year", "trust"])["delinq_30plus_share"].mean().unstack("trust")[TRUSTS]
lr = np.log(yr.div(yr["synchrony"], axis=0))
cmp_ = pd.DataFrame({
    "trust": TRUSTS,
    "log_ratio_2019": lr.loc[2019, TRUSTS].to_numpy(),
    "log_ratio_2020": lr.loc[2020, TRUSTS].to_numpy(),
    "change_2019_to_2020": (lr.loc[2020, TRUSTS] - lr.loc[2019, TRUSTS]).to_numpy(),
    "log_ratio_2024_26": np.log(yr.loc[2024:2026, TRUSTS].mean() / yr.loc[2024:2026, "synchrony"].mean()).to_numpy(),
})
cmp_["change_2019_to_2024_26"] = cmp_["log_ratio_2024_26"] - cmp_["log_ratio_2019"]
log(tbl(cmp_, "%.4f"))
log("  If borrowers rank cards, the MOST protected card should compress most when nobody is short.")
log("  If instead synchrony's own level simply fell furthest, every trust's ratio rises by a similar")
log("  amount and nothing card-specific is happening.")

# --- can the mix adjustment change the cycle conclusion?
A = pd.read_csv(os.path.join(HERE, "partA_mix_adjustment.csv"))
A = A[A["variant"] == "proportional"]
er = {s: float(A[(A.shape_source if False else A["shape"]) == s].set_index("trust").loc["amex", "expected"] /
               A[A["shape"] == s].set_index("trust").loc["synchrony", "expected"]) for s in SHAPES}
reg = pd.read_csv(os.path.join(HERE, "partC_30plus_by_regime.csv")).set_index("regime")
raw = reg["amex"] / reg["synchrony"]
out = pd.DataFrame({"regime": raw.index, "raw_ratio": raw.to_numpy()})
for s in SHAPES:
    out[s] = raw.to_numpy() / er[s]
log("")
log("MIX ADJUSTMENT CANNOT CHANGE THE SHAPE OF THE CYCLE. The composition tables are single snapshots,")
log("so expected(amex)/expected(synchrony) is one CONSTANT per shape; the mix-adjusted ratio is the raw")
log("ratio divided by that constant, in every regime. Adjusted ratio by regime:")
log("  expected(amex)/expected(synchrony) per shape: " + ", ".join(f"{k}={v:.4f}" for k, v in er.items()))
log(tbl(out, "%.4f"))
out.to_csv(os.path.join(HERE, "supp_mixadj_by_regime.csv"), index=False)

# --- synchrony pool composition drift proxy: receivables and the Dec-2019 addition
log("")
log("SYNCHRONY POOL DRIFT. Its trust receivables nearly doubled over the sample, so its mix in 2019 is")
log("not its mix in 2026. Month-over-month changes above 8 percent:")
g = M[M["trust"] == "synchrony"].sort_values("period_end")
ch = g["receivables_principal"].pct_change()
b = pd.DataFrame({"period_end": g["period_end"].dt.date, "pct_change": ch.to_numpy(),
                  "recv_bn": g["receivables_principal"].to_numpy() / 1e9})
log(tbl(b[b["pct_change"].abs() > 0.08], "%.4f"))
log("")
log("Annual mean receivables ($bn) per trust:")
ar = M.groupby(["year", "trust"])["receivables_principal"].mean().unstack("trust")[TRUSTS] / 1e9
log(tbl(ar.reset_index(), "%.2f"))
ar.to_csv(os.path.join(HERE, "supp_receivables_by_year.csv"))

with open(os.path.join(HERE, "supplement.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print("\nwrote supplement.txt")
