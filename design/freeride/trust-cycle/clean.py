"""Break-aware windows: all four representations, every trust, plus the floor-risk check on levels."""
import json
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


def tbl(df, f="%.4f"):
    return df.to_string(index=False, float_format=lambda v: f % v)


M = pd.read_csv(os.path.join(REPO, "data", "cards_monthly.csv"))
M["period_end"] = pd.to_datetime(M["period_end"])
M["ym"] = M["period_end"].dt.to_period("M")
W = M.pivot_table(index="ym", columns="trust", values="delinq_30plus_share")[TRUSTS]

WINDOWS = [
    ("pre_break_2018-12..2019-11", "2018-12", "2019-11"),
    ("post_add_pre_stim_2019-12..2020-03", "2019-12", "2020-03"),
    ("stimulus_2020-04..2021-12", "2020-04", "2021-12"),
    ("normalising_2022-01..2023-06", "2022-01", "2023-06"),
    ("squeeze_2023-07..2026-07", "2023-07", "2026-07"),
]

lev, rat, lrat, dif, r6 = {}, {}, {}, {}, {}
for name, a, b in WINDOWS:
    w = W.loc[pd.Period(a):pd.Period(b)]
    mu = w.mean()
    lev[name] = mu
    rat[name] = mu / mu["synchrony"]
    lrat[name] = np.log(mu / mu["synchrony"])
    dif[name] = (mu - mu["synchrony"]) * 100
    r6[name] = mu / mu.mean()

log("BREAK-AWARE WINDOWS. The pre-covid regime is split at the December 2019 Synchrony pool addition")
log("(+38.6% receivables in one month; its 30+ share fell 27.3% while no other trust moved more than 4%).")
log("")
for title, d, f in (("(i) LEVELS - mean monthly 30+ share", lev, "%.5f"),
                    ("(ii) RATIO to synchrony", rat, "%.4f"),
                    ("(iii) LOG RATIO to synchrony", lrat, "%.4f"),
                    ("(iv) DIFFERENCE from synchrony, percentage points", dif, "%.4f"),
                    ("(v) RATIO to the unweighted six-trust mean", r6, "%.4f")):
    log(title)
    log(tbl(pd.DataFrame(d).T.reset_index().rename(columns={"index": "window"}), f))
    log("")

log("FLOOR RISK - how close do the levels get to zero? min and max monthly 30+ share per trust:")
mm = pd.DataFrame({"trust": TRUSTS, "min": W[TRUSTS].min().to_numpy(), "max": W[TRUSTS].max().to_numpy(),
                   "min_month": [str(W[t].idxmin()) for t in TRUSTS],
                   "max_month": [str(W[t].idxmax()) for t in TRUSTS]})
log(tbl(mm, "%.5f"))

out = {"windows": [w[0] for w in WINDOWS],
       "levels": pd.DataFrame(lev).T.to_dict(orient="index"),
       "ratio_to_synchrony": pd.DataFrame(rat).T.to_dict(orient="index"),
       "log_ratio_to_synchrony": pd.DataFrame(lrat).T.to_dict(orient="index"),
       "diff_pp_to_synchrony": pd.DataFrame(dif).T.to_dict(orient="index"),
       "ratio_to_six_mean": pd.DataFrame(r6).T.to_dict(orient="index"),
       "level_min_max": mm.to_dict(orient="records")}
with open(os.path.join(HERE, "clean_windows.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2, default=str)
pd.DataFrame(rat).T.to_csv(os.path.join(HERE, "partC_clean_window_ratios.csv"))
with open(os.path.join(HERE, "clean_windows.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print("\nwrote clean_windows.txt")
