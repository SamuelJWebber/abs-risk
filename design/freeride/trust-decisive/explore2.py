import pandas as pd
pd.set_option("display.width", 200)
s = pd.read_csv("C:/Users/samwe/code/abs-risk/data/loss_shape.csv")
print(s[["shape_source", "tier", "tier_lo", "tier_hi", "relative_loss", "flag"]].to_string())
print("\n=== composition fico ===")
c = pd.read_csv("C:/Users/samwe/code/abs-risk/data/cards_composition.csv")
f = c[c["table"] == "fico"]
print(f.groupby("trust")["as_of"].first())
print(f[["trust", "bucket_label", "bucket_lo", "bucket_hi", "share_receivables"]].to_string())
print("\ntotal share per trust:", f.groupby("trust")["share_receivables"].sum().to_dict())
print("\ntables present:", c["table"].unique())
