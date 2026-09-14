"""Coverage gaps, and the December 2019 Synchrony pool addition - the single biggest threat to the
cycle reading."""
import os
import numpy as np
import pandas as pd

REPO = "C:/Users/samwe/code/abs-risk"
HERE = os.path.dirname(os.path.abspath(__file__))
TRUSTS = ["amex", "bofa", "chase", "citi", "comet", "synchrony"]
lines = []


def log(s=""):
    print(s)
    lines.append(str(s))


def tbl(df, f="%.5f"):
    return df.to_string(index=False, float_format=lambda v: f % v)


M = pd.read_csv(os.path.join(REPO, "data", "cards_monthly.csv"))
M["period_end"] = pd.to_datetime(M["period_end"])
M["ym"] = M["period_end"].dt.to_period("M")

log("COVERAGE - months present per trust, and gaps")
full = pd.period_range(M["ym"].min(), M["ym"].max(), freq="M")
for t in TRUSTS:
    have = set(M[M["trust"] == t]["ym"])
    miss = [str(p) for p in full if p not in have]
    log(f"  {t:10s} n={len(have):3d}  {min(have)}..{max(have)}  missing: {miss if miss else 'none'}")
log(f"  full span {full.min()}..{full.max()} = {len(full)} months")

W = M.pivot_table(index="ym", columns="trust", values="delinq_30plus_share")[TRUSTS]
log("")
log("30+ SHARE AROUND THE DECEMBER 2019 SYNCHRONY POOL ADDITION (all trusts, monthly):")
win = W.loc[pd.Period("2019-08"):pd.Period("2020-06")]
q = win.reset_index()
q["ym"] = q["ym"].astype(str)
q["amex/sync"] = win["amex"].to_numpy() / win["synchrony"].to_numpy()
log(tbl(q))

R = M.pivot_table(index="ym", columns="trust", values="receivables_principal")[TRUSTS] / 1e9
log("")
log("RECEIVABLES ($bn) over the same window:")
q2 = R.loc[pd.Period("2019-08"):pd.Period("2020-06")].reset_index()
q2["ym"] = q2["ym"].astype(str)
log(tbl(q2, "%.3f"))

log("")
log("One-month change at 2019-12 (Nov -> Dec 2019):")
d = pd.DataFrame({
    "trust": TRUSTS,
    "d30plus_nov19": W.loc[pd.Period("2019-11"), TRUSTS].to_numpy(),
    "d30plus_dec19": W.loc[pd.Period("2019-12"), TRUSTS].to_numpy(),
    "pct_change_30plus": (W.loc[pd.Period("2019-12"), TRUSTS].to_numpy() /
                          W.loc[pd.Period("2019-11"), TRUSTS].to_numpy() - 1),
    "recv_bn_nov19": R.loc[pd.Period("2019-11"), TRUSTS].to_numpy(),
    "recv_bn_dec19": R.loc[pd.Period("2019-12"), TRUSTS].to_numpy(),
    "pct_change_recv": (R.loc[pd.Period("2019-12"), TRUSTS].to_numpy() /
                        R.loc[pd.Period("2019-11"), TRUSTS].to_numpy() - 1),
})
log(tbl(d, "%.5f"))

log("")
log("Amex/Synchrony 30+ ratio, means of three clean sub-windows that avoid the Dec-2019 break:")
def mm(a, b):
    w = W.loc[pd.Period(a):pd.Period(b)].dropna()
    r = w["amex"] / w["synchrony"]
    return {"window": f"{a}..{b}", "n": len(r), "amex": w["amex"].mean(), "sync": w["synchrony"].mean(),
            "mean_ratio": r.mean(), "ratio_of_means": w["amex"].mean() / w["synchrony"].mean(),
            "diff_pp": (w["amex"].mean() - w["synchrony"].mean()) * 100}
sub = pd.DataFrame([
    mm("2018-12", "2019-11"),   # before the Synchrony addition
    mm("2019-12", "2020-03"),   # after the addition, before stimulus
    mm("2020-04", "2021-12"),   # stimulus
    mm("2022-01", "2023-06"),   # normalising
    mm("2023-07", "2026-07"),   # squeeze
])
log(tbl(sub, "%.5f"))

with open(os.path.join(HERE, "breaks.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
sub.to_csv(os.path.join(HERE, "supp_clean_windows.csv"), index=False)
print("\nwrote breaks.txt")
