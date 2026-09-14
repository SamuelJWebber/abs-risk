import json
import pandas as pd

M = pd.read_csv("C:/Users/samwe/code/abs-risk/data/cards_monthly.csv")
print(M.columns.tolist())
for t, g in M.groupby("trust"):
    r = g.sort_values("period_end").iloc[len(g) // 2]
    j = json.loads(r["row_labels_json"])
    inp = j.get("inputs", {})
    print("=" * 70)
    print(t, r["period_end"], "co_basis=", r["co_basis"], "co_ann=", r["co_annualisation"])
    print("  delinq_basis:", r["delinq_basis"])
    print("  input keys:", sorted(k for k in inp if k != "delinquency_buckets"))
    print("  buckets:", inp.get("delinquency_buckets"))
    for k, v in inp.items():
        if k != "delinquency_buckets":
            print("     ", k, "=", v)
    print("  labels:", j.get("labels"))
