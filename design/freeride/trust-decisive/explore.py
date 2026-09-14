import json, os
import numpy as np, pandas as pd

REPO = "C:/Users/samwe/code/abs-risk"
M = pd.read_csv(os.path.join(REPO, "data", "cards_monthly.csv"))
print("rows", len(M))
M["period_end"] = pd.to_datetime(M["period_end"])
M["ym"] = M["period_end"].dt.to_period("M").astype(str)

# exact duplicate rows
dup_all = M[M.duplicated(keep=False)]
print("\nEXACT FULL-ROW DUPS:", len(dup_all))
print(dup_all[["trust", "ym", "receivables_principal", "payment_rate"]].to_string())

# duplicate trust-month (not necessarily identical)
dtm = M[M.duplicated(subset=["trust", "ym"], keep=False)]
print("\nDUP TRUST-MONTH ROWS:", len(dtm))
print(dtm[["trust","ym","receivables_principal","delinq_30plus_share","payment_rate","source_accession","source_file"]].to_string())

print("\nper-trust month counts raw:")
print(M.groupby("trust")["ym"].agg(["size","nunique"]))

print("\npayment_rate nulls per trust:")
print(M.groupby("trust")["payment_rate"].agg(["size", "count", "mean", "min", "max"]))
print("\nyield nulls:")
print(M.groupby("trust")["yield"].agg(["count","mean"]))
print("\nexcess_spread nulls:")
print(M.groupby("trust")["excess_spread"].agg(["count","mean"]))

# denominators from row_labels_json notes
print("\n=== payment_rate labels / notes per trust (first row each) ===")
for t, g in M.groupby("trust"):
    r = g.sort_values("period_end").iloc[0]
    j = json.loads(r["row_labels_json"])
    lab = j.get("labels", {}).get("payment_rate")
    note = j.get("notes", {}).get("payment_rate")
    inp = list(j.get("inputs", {}).keys())
    print(f"--- {t}: label={lab!r}")
    print(f"    note={note!r}")
    print(f"    inputs={inp}")
    pr = j.get("printed", {}).get("payment_rate")
    rc = j.get("recomputed", {}).get("payment_rate")
    print(f"    printed={pr} recomputed={rc}")

# last rows too (labels may change)
print("\n=== last-row payment_rate labels ===")
for t, g in M.groupby("trust"):
    r = g.sort_values("period_end").iloc[-1]
    j = json.loads(r["row_labels_json"])
    print(t, r["ym"], repr(j.get("labels", {}).get("payment_rate")), "|", repr(j.get("notes", {}).get("payment_rate")))
