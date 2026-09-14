"""Same headline table, but quintiles cut within each sub_grade x issue_year cell,
so the comparison is balanced on both LC's price and the vintage."""
import json
import os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "freeride-data",
                    "LendingClub_2007_to_2018Q4.csv")
USECOLS = ["term", "issue_d", "loan_status", "fico_range_low", "fico_range_high",
           "total_bc_limit", "bc_open_to_buy", "num_bc_tl", "loan_amnt",
           "grade", "sub_grade", "int_rate"]
lines = []


def log(s=""):
    print(s)
    lines.append(str(s))


df = pd.read_csv(DATA, usecols=USECOLS, low_memory=False)
df["term"] = df["term"].astype(str).str.strip()
df = df[df["term"] == "36 months"]
df["issue_dt"] = pd.to_datetime(df["issue_d"], format="%b-%Y", errors="coerce")
df["issue_year"] = df["issue_dt"].dt.year
df = df[(df["issue_year"] >= 2012) & (df["issue_year"] <= 2017)]
df = df[df["loan_status"].isin(["Fully Paid", "Charged Off"])].copy()
df["default"] = (df["loan_status"] == "Charged Off").astype(int)
df["fico"] = (df["fico_range_low"] + df["fico_range_high"]) / 2.0
for c in ["total_bc_limit", "bc_open_to_buy", "num_bc_tl", "loan_amnt"]:
    df[c] = pd.to_numeric(df[c], errors="coerce")
df["int_rate"] = pd.to_numeric(df["int_rate"], errors="coerce")
df = df.dropna(subset=["fico", "total_bc_limit", "bc_open_to_buy", "num_bc_tl", "int_rate"])
df = df[df["total_bc_limit"] > 0].copy()

df["_q"] = np.nan
kept = 0
for (sg, yr), g in df.groupby(["sub_grade", "issue_year"]):
    if len(g) < 250:
        continue
    df.loc[g.index, "_q"] = pd.qcut(g["total_bc_limit"], 5, labels=False,
                                    duplicates="drop").values
    kept += len(g)
d = df.dropna(subset=["_q"]).copy()
log(f"Rows in sub_grade x year quintiles: {len(d):,} of {len(df):,}")
log("")
log("CHARGE-OFF BY OTHER-LENDER LIMIT QUINTILE, CUT WITHIN SUB_GRADE x ISSUE YEAR")
log(f"{'quintile':<10}{'n':>10}{'median limit':>14}{'charge-off %':>14}"
    f"{'mean APR %':>12}{'mean FICO':>11}{'SE pp':>8}")
rows = []
for q in sorted(d["_q"].unique()):
    c = d[d["_q"] == q]
    p = c["default"].mean()
    r = {"quintile": int(q) + 1, "n": int(len(c)),
         "median_limit": float(c["total_bc_limit"].median()),
         "charge_off": float(p), "mean_apr": float(c["int_rate"].mean()),
         "mean_fico": float(c["fico"].mean()),
         "se_pp": float(np.sqrt(p * (1 - p) / len(c)) * 100)}
    rows.append(r)
    log(f"Q{r['quintile']:<9}{r['n']:>10,}{r['median_limit']:>14,.0f}"
        f"{p*100:>14.2f}{r['mean_apr']:>12.2f}{r['mean_fico']:>11.1f}{r['se_pp']:>8.2f}")
q1, q5 = rows[0], rows[-1]
diff = (q1["charge_off"] - q5["charge_off"]) * 100
se = np.sqrt(q1["se_pp"] ** 2 + q5["se_pp"] ** 2)
dapr = q1["mean_apr"] - q5["mean_apr"]
log("")
log(f"Q1 - Q5 = {diff:.2f} pp (SE {se:.2f}, t {diff/se:.1f}); APR diff {dapr:+.3f} pp")
log(f"annualised loss gap {diff/1.5:.2f} pp/yr; mispricing "
    f"{(diff/1.5 - dapr)*100:.0f} bps/yr at 100% LGD, "
    f"{(diff/1.5*0.65 - dapr)*100:.0f} bps/yr at 65% LGD")
out = {"rows": rows, "q1_minus_q5_pp": float(diff), "se_pp": float(se),
       "t": float(diff / se), "delta_apr_pp": float(dapr),
       "mispricing_bps_lgd100": float((diff / 1.5 - dapr) * 100),
       "mispricing_bps_lgd65": float((diff / 1.5 * 0.65 - dapr) * 100),
       "n": int(len(d))}
with open(os.path.join(HERE, "subgrade_year_quintiles.json"), "w") as fh:
    json.dump(out, fh, indent=2, default=float)
with open(os.path.join(HERE, "subgrade_year_quintiles.txt"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines))
log("Wrote subgrade_year_quintiles.txt / .json")
