"""Mix-adjust the abs-risk trust delinquency gap, build the roll ladder, and test it against the credit cycle.

Parts:
  A  mix-adjust the 30+ entry rate with the four published loss shapes (+ straddle-rule sensitivity)
  B  monthly stock-to-stock roll ladder per trust per rung from the dollar buckets in row_labels_json
  C  the cycle test: does the Amex/Synchrony entry gap compress when households are flush?

Reads only from C:/Users/samwe/code/abs-risk. Writes everything into this folder.
"""
import json
import os
import numpy as np
import pandas as pd

REPO = "C:/Users/samwe/code/abs-risk"
HERE = os.path.dirname(os.path.abspath(__file__))

TIERS = ["deep_subprime", "subprime", "near_prime", "prime", "prime_plus", "superprime"]
TRUSTS = ["amex", "bofa", "chase", "citi", "comet", "synchrony"]
SHAPES = ["fico_odds", "fico_fed2007", "acms2018", "acms2018_dpd90"]

lines = []


def log(s=""):
    print(s)
    lines.append(str(s))


def tbl(df, floatfmt="%.6f"):
    return df.to_string(index=False, float_format=lambda v: floatfmt % v)


# ------------------------------------------------------------------ load
M = pd.read_csv(os.path.join(REPO, "data", "cards_monthly.csv"))
M["period_end"] = pd.to_datetime(M["period_end"])
M["ym"] = M["period_end"].dt.to_period("M")
M = M.sort_values(["trust", "period_end"]).reset_index(drop=True)

COMP = pd.read_csv(os.path.join(REPO, "data", "cards_composition.csv"))
SHP = pd.read_csv(os.path.join(REPO, "data", "loss_shape.csv"))
XW = pd.read_csv(os.path.join(REPO, "crosswalks", "fico_buckets.csv"))

results = {}

# ================================================================== PART A
log("=" * 100)
log("PART A - MIX-ADJUST THE 30+ ENTRY RATE")
log("=" * 100)

fico = COMP[COMP["table"] == "fico"].copy()
fico["share"] = fico["share_receivables"]
xw = XW.copy()
wcols = ["w_" + t for t in TIERS]

m = fico.merge(xw[["trust", "bucket_label"] + wcols + ["rule", "flags"]],
               on=["trust", "bucket_label"], how="left", validate="1:1")
assert not m[wcols].isna().any().any(), m[m[wcols].isna().any(axis=1)]


def mix_from(m, straddle="proportional"):
    """Tier shares per trust. straddle: 'proportional' (crosswalk weights, uniform-in-score),
    'lower' (whole bucket to its lowest touched tier), 'upper' (whole bucket to its highest touched tier)."""
    out = {}
    drops = {}
    for t, g in m.groupby("trust"):
        W = g[wcols].to_numpy(dtype=float)
        s = g["share"].to_numpy(dtype=float)
        scored = W.sum(axis=1) > 0            # unscored rows carry all-zero weights
        drops[t] = float(s[~scored].sum())
        W, s = W[scored], s[scored]
        s = s / s.sum()                        # renormalise over scored buckets
        if straddle == "lower":
            W2 = np.zeros_like(W)
            W2[np.arange(len(W)), W.argmax(axis=1) * 0 + np.array([np.nonzero(r)[0][0] for r in W])] = 1.0
            W = W2
        elif straddle == "upper":
            W2 = np.zeros_like(W)
            W2[np.arange(len(W)), np.array([np.nonzero(r)[0][-1] for r in W])] = 1.0
            W = W2
        v = (s[:, None] * W).sum(axis=0)
        out[t] = dict(zip(TIERS, v / v.sum()))
    return pd.DataFrame(out).T.loc[TRUSTS], drops


mix, dropped = mix_from(m, "proportional")
log("")
log("(A1) Tier mix per trust from the prospectus score table, via crosswalks/fico_buckets.csv.")
log("     Straddle rule (absrisk.shape.tiers docstring, reused verbatim): a score bucket is assumed")
log("     uniform over the integer scores it spans, so a bucket crossing a tier edge is split in")
log("     proportion to the integer scores on each side. Open ends clamp to 300 / 850.")
log("     Unscored buckets carry weight 0 and the remaining shares are renormalised.")
log("     Share dropped as unscored: " + ", ".join(f"{k}={v:.4f}" for k, v in dropped.items()))
log("")
log(tbl(mix.reset_index().rename(columns={"index": "trust"}), "%.5f"))
log("")
log("     SCORE-SCALE WARNING: synchrony's table is VantageScore 4.0, every other trust is FICO.")
log("     The two scales are not interchangeable; every synchrony comparison below inherits this.")
log("     chase's FICO table is a ~5% random sample of the pool, not the pool.")
log("     Each table is ONE snapshot (amex 2025-05-31, bofa 2026-04-01, chase 2026-03-31,")
log("     citi 2025-03-30, comet 2026-06-10, synchrony 2026-05-31), not a time series.")

# actual entry + weights, full sample
act = M.groupby("trust").agg(
    months=("period_end", "size"),
    first=("period_end", "min"),
    last=("period_end", "max"),
    actual_30plus=("delinq_30plus_share", "mean"),
    actual_90plus=("delinq_90plus_share", "mean"),
    recv=("receivables_principal", "mean"),
).loc[TRUSTS]

shape_vec = {s: SHP[SHP["shape_source"] == s].set_index("tier")["relative_loss"].astype(float).to_dict()
             for s in SHAPES}

log("")
log("     relative_loss by tier (prime = 1) in each of the four published shapes:")
log(tbl(pd.DataFrame(shape_vec).loc[TIERS].reset_index().rename(columns={"index": "tier"}), "%.4f"))


def part_a(mix, label):
    rows = []
    for s in SHAPES:
        v = np.array([shape_vec[s][t] for t in TIERS])
        S = mix[TIERS].to_numpy() @ v                       # mix . shape, per trust
        w = act["recv"].to_numpy()
        a = act["actual_30plus"].to_numpy()
        level = float((w * a).sum() / (w * S).sum())        # pinned to THESE SIX TRUSTS
        exp = level * S
        for i, t in enumerate(TRUSTS):
            rows.append({"variant": label, "shape": s, "trust": t, "level": level,
                         "mix_dot_shape": S[i], "actual": a[i], "expected": exp[i],
                         "act_over_exp": a[i] / exp[i]})
    return pd.DataFrame(rows)


A = part_a(mix, "proportional")
mix_lo, _ = mix_from(m, "lower")
mix_hi, _ = mix_from(m, "upper")
A_lo = part_a(mix_lo, "straddle_to_lower_tier")
A_hi = part_a(mix_hi, "straddle_to_upper_tier")
A_all = pd.concat([A, A_lo, A_hi], ignore_index=True)
A_all.to_csv(os.path.join(HERE, "partA_mix_adjustment.csv"), index=False)

raw_ratio = float(act.loc["amex", "actual_30plus"] / act.loc["synchrony", "actual_30plus"])

log("")
log("(A2) expected(t) = level * sum_tiers( share(t,tier) * relative_loss(shape,tier) ).")
log("     level is pinned so the receivables-weighted mean of expected over THESE SIX TRUSTS equals the")
log("     receivables-weighted mean of actual over THESE SIX TRUSTS. It is NOT calibrated to the industry,")
log("     to the CFPB aggregate, or to any outside benchmark; it is a within-six normalisation only.")
log("     weights = each trust's full-sample mean receivables_principal; actual = full-sample mean of")
log("     delinq_30plus_share (each trust on its own printed denominator, see delinq_basis).")
log("")
log(tbl(act.reset_index()[["trust", "months", "actual_30plus", "actual_90plus", "recv"]]
        .assign(recv=lambda d: d["recv"] / 1e9), "%.6f"))
log("     (recv in $bn, mean over the trust's own months)")

log("")
log("(A3) actual / expected per trust per shape (proportional straddle):")
piv = A.pivot(index="trust", columns="shape", values="act_over_exp").loc[TRUSTS][SHAPES]
pivE = A.pivot(index="trust", columns="shape", values="expected").loc[TRUSTS][SHAPES]
log("")
log("  expected 30+ share:")
log(tbl(pivE.reset_index(), "%.6f"))
log("  actual/expected:")
log(tbl(piv.reset_index(), "%.4f"))

log("")
log("(A3) HEADLINE - Amex-vs-Synchrony ratio, raw and mix-adjusted:")
hl = []
for s in SHAPES:
    r = float(piv.loc["amex", s] / piv.loc["synchrony", s])
    hl.append({"shape": s, "raw_ratio": raw_ratio, "mix_adjusted_ratio": r,
               "survives_pct": 100.0 * (1 - r) / (1 - raw_ratio),
               "expected_ratio_amex_over_sync": float(pivE.loc["amex", s] / pivE.loc["synchrony", s])})
HL = pd.DataFrame(hl)
log(tbl(HL, "%.4f"))
log("     raw_ratio = mean amex 30+ / mean synchrony 30+ over each trust's full sample.")
log("     survives_pct = how much of the raw gap-below-parity is left after mix adjustment,")
log("       measured as (1 - adjusted) / (1 - raw) * 100.")

log("")
log("(A4) Straddle sensitivity - whole straddling bucket to the LOWER tier, then to the UPPER tier:")
sens = []
for lab, df in (("proportional", A), ("straddle_to_lower_tier", A_lo), ("straddle_to_upper_tier", A_hi)):
    p = df.pivot(index="trust", columns="shape", values="act_over_exp")
    for s in SHAPES:
        sens.append({"variant": lab, "shape": s, "amex_over_sync_adj": float(p.loc["amex", s] / p.loc["synchrony", s])})
SENS = pd.DataFrame(sens).pivot(index="shape", columns="variant", values="amex_over_sync_adj").loc[SHAPES]
SENS["min"] = SENS.min(axis=1)
SENS["max"] = SENS.max(axis=1)
log(tbl(SENS.reset_index(), "%.4f"))

results["partA"] = {
    "raw_amex_over_synchrony_30plus": raw_ratio,
    "actual_30plus_mean": act["actual_30plus"].to_dict(),
    "tier_mix_proportional": mix[TIERS].to_dict(orient="index"),
    "act_over_exp": piv.to_dict(),
    "headline": HL.to_dict(orient="records"),
    "straddle_sensitivity": SENS.reset_index().to_dict(orient="records"),
    "unscored_dropped": dropped,
}

# ================================================================== PART B
log("")
log("=" * 100)
log("PART B - THE ROLL LADDER")
log("=" * 100)

CO_FIELD = {  # pool-level gross charge-off dollars in the month, per trust, from inputs
    "amex": ("defaulted_amount", 1.0, "Defaulted Amount (gross), dollars"),
    "bofa": ("total_charge_offs_thousands", 1000.0, "Total Charge-Offs, printed in thousands"),
    "chase": ("gross_losses", 1.0, "Gross Losses, dollars"),
    "comet": ("defaulted_amount", 1.0, "Defaulted Amount (gross), dollars"),
    "synchrony": ("default_amount", 1.0, "Default Amount for Defaulted Accounts, dollars"),
}
DENOM_USED = {}   # denominator each trust prints for delinquency shares (recorded, not used for rolls)

# canonical rung names keyed by the LOWER edge (days) of the source bucket
def norm(k):
    return k.replace(" days delinquent", "").strip()


BUCKET_ORDER = {
    "amex": ["31-60", "61-90", "91-120", "120+"],
    "bofa": ["30-59", "60-89", "90-119", "120-149", "150-179", "180+"],
    "chase": ["30-59", "60-89", "90-119", "120-149", "150-179", "180+"],
    "citi": ["1-30", "31-60", "61-90", "91-120", "121-150", "151-180"],
    "comet": ["30-59", "60-89", "90-119", "120-149", "150+"],
    "synchrony": ["1-29", "30-59", "60-89", "90-119", "120-149", "150-179", "180+"],
}
RUNG_NAME = {  # index of source bucket in BUCKET_ORDER -> canonical rung, per trust
    "amex": {0: "30->60", 1: "60->90", 2: "90->120"},
    "bofa": {0: "30->60", 1: "60->90", 2: "90->120", 3: "120->150", 4: "150->180"},
    "chase": {0: "30->60", 1: "60->90", 2: "90->120", 3: "120->150", 4: "150->180"},
    "citi": {0: "1->30", 1: "30->60", 2: "60->90", 3: "90->120", 4: "120->150"},
    "comet": {0: "30->60", 1: "60->90", 2: "90->120", 3: "120->150"},
    "synchrony": {0: "1->30", 1: "30->60", 2: "60->90", 3: "90->120", 4: "120->150", 5: "150->180"},
}
DEEPEST = {"amex": "120+", "bofa": "150-179", "chase": "150-179", "citi": "151-180",
           "comet": "150+", "synchrony": "150-179"}

rows = []
for t, g in M.groupby("trust"):
    g = g.sort_values("period_end").reset_index(drop=True)
    order = BUCKET_ORDER[t]
    prev = None
    prev_ym = None
    for _, r in g.iterrows():
        j = json.loads(r["row_labels_json"])
        inp = j["inputs"]
        b = {norm(k): float(v) for k, v in inp["delinquency_buckets"].items()}
        assert set(b) == set(order), (t, sorted(b), order)
        # pool-level gross charge-off dollars
        if t == "citi":
            co = float(r["gross_co_rate"]) * (float(inp["due_period_days"]) / 365.0) * float(inp["average_principal"])
            co_note = "DERIVED: gross_co_rate (invested-amount basis) x days/365 x average_principal"
        else:
            f, mult, _ = CO_FIELD[t]
            co = float(inp[f]) * mult
            co_note = CO_FIELD[t][2]
        d = {"trust": t, "period_end": r["period_end"], "ym": r["ym"], "co_dollars": co, "co_note": co_note}
        for k in order:
            d["b_" + k] = b[k]
        if prev is not None and (r["ym"] - prev_ym).n == 1:
            for i, k in enumerate(order[:-1]):
                nxt = order[i + 1]
                if prev[k] > 0:
                    d["roll_" + RUNG_NAME[t].get(i, f"idx{i}")] = b[nxt] / prev[k]
            dk = DEEPEST[t]
            if prev[dk] > 0:
                d["roll_CO"] = co / prev[dk]
        rows.append(d)
        prev, prev_ym = b, r["ym"]
    DENOM_USED[t] = str(g.iloc[0]["delinq_basis"])

R = pd.DataFrame(rows)
R.to_csv(os.path.join(HERE, "partB_rolls_monthly.csv"), index=False)

RUNGS = ["1->30", "30->60", "60->90", "90->120", "120->150", "150->180", "CO"]
rollcols = ["roll_" + x for x in RUNGS]
for c in rollcols:
    if c not in R:
        R[c] = np.nan

log("")
log("Denominator each trust prints for its delinquency SHARES (recorded; roll rates below are")
log("bucket-dollar / bucket-dollar and therefore denominator-free):")
for t in TRUSTS:
    log(f"  {t:10s} {DENOM_USED[t]}")
log("")
log("Charge-off dollars used for the final rung:")
for t in TRUSTS:
    n = R[R["trust"] == t]["co_note"].iloc[0]
    log(f"  {t:10s} {n}")

log("")
log("(B1) Full-sample mean monthly roll rate, roll_k(t) = bucket_{k+1}(t) / bucket_k(t-1).")
log("     Only consecutive-month pairs are used. Each trust's own bucket names are printed.")
log("")
b1rows = []
for t in TRUSTS:
    g = R[R["trust"] == t]
    order = BUCKET_ORDER[t]
    for i, k in enumerate(order[:-1]):
        rn = RUNG_NAME[t].get(i)
        if rn is None:
            continue
        c = "roll_" + rn
        v = g[c].dropna()
        b1rows.append({"trust": t, "rung": rn, "from_bucket": k, "to_bucket": order[i + 1],
                       "n": len(v), "mean": v.mean(), "median": v.median(), "sd": v.std()})
    v = g["roll_CO"].dropna()
    b1rows.append({"trust": t, "rung": "CO", "from_bucket": DEEPEST[t], "to_bucket": "charge-off $",
                   "n": len(v), "mean": v.mean(), "median": v.median(), "sd": v.std()})
B1 = pd.DataFrame(b1rows)
B1.to_csv(os.path.join(HERE, "partB_ladder_full_sample.csv"), index=False)
log(tbl(B1, "%.4f"))

log("")
log("(B2) Comparability of rungs across trusts:")
log("  COMPARABLE across all six (same structure, a closed bucket into the next closed bucket):")
log("    30->60  : amex 31-60->61-90 | bofa/chase/comet/synchrony 30-59->60-89 | citi 31-60->61-90")
log("              (amex and citi are offset one day; every trust's source and target are closed 30-day")
log("               windows, so this rung is comparable.)")
log("    60->90  : same structure everywhere.")
log("  COMPARABLE for five trusts, NOT amex:")
log("    90->120 : bofa/chase/comet/synchrony 90-119->120-149, citi 91-120->121-150 are closed->closed.")
log("              AMEX'S TARGET 120+ IS OPEN-ENDED - it is a stock of everything from 120 days to")
log("              charge-off, roughly two extra months of accumulation, so amex's 90->120 roll is")
log("              mechanically inflated and must not be compared with the others.")
log("  COMPARABLE for four trusts:")
log("    120->150: bofa/chase/comet/synchrony/citi have it; amex does not (no 150 bucket at all).")
log("              comet's target 150+ is open-ended, so comet's 120->150 is also inflated.")
log("    150->180: bofa/chase/synchrony only; their 180+ target is essentially EMPTY (printed 0.0 in")
log("              almost every month - they charge off at 180), so this rung is near zero by")
log("              construction and carries no information.")
log("  NOT COMPARABLE:")
log("    1->30   : only citi (1-30) and synchrony (1-29) print an under-30 bucket. amex, bofa, chase")
log("              and comet do not, so this rung exists for two trusts only.")
log("    CO      : the denominator is each trust's DEEPEST bucket, and those are different objects -")
log("              amex 120+ (open, ~2 months wide), comet 150+ (open), citi 151-180 (closed, charge-off")
log("              at 180), bofa/chase/synchrony 150-179 (closed). A wider denominator gives a lower")
log("              ratio for free. Read the CO rung only within a trust over time, never across trusts.")

log("")
log("(B3) Amex vs Synchrony rung by rung (full sample means):")
b3 = []
for rn in RUNGS:
    a = B1[(B1["trust"] == "amex") & (B1["rung"] == rn)]
    s = B1[(B1["trust"] == "synchrony") & (B1["rung"] == rn)]
    if len(a) and len(s):
        b3.append({"rung": rn, "amex": float(a["mean"].iloc[0]), "synchrony": float(s["mean"].iloc[0]),
                   "amex_over_sync": float(a["mean"].iloc[0]) / float(s["mean"].iloc[0]),
                   "comparable": rn in ("30->60", "60->90")})
B3 = pd.DataFrame(b3)
log(tbl(B3, "%.4f"))

# conversion metric for comparison
ANN = {"x12": 12.0, "x365_over_days": 365.0 / 30.4, "actual_365": 365.0 / 30.4}
M["co_monthly"] = M["gross_co_rate"] / M["co_annualisation"].map(ANN)
M["entry"] = M["delinq_30plus_share"]
M["progression"] = M["delinq_90plus_share"] / M["delinq_30plus_share"]
M["conversion"] = M["co_monthly"] / M["delinq_90plus_share"]
conv = M.groupby("trust")[["co_monthly", "entry", "progression", "conversion"]].mean().loc[TRUSTS]
log("")
log("  The published three-factor decomposition (entry x progression x conversion), full sample:")
log(tbl(conv.reset_index(), "%.6f"))
cr = float(conv.loc["amex", "conversion"] / conv.loc["synchrony", "conversion"])
log(f"  amex/synchrony conversion ratio = {cr:.4f}  (the published '1.38x worse' claim)")
log(f"  amex/synchrony entry ratio      = {float(conv.loc['amex','entry']/conv.loc['synchrony','entry']):.4f}")
log("")
log("  Does the rung-by-rung ladder agree with the 'conversion' metric? Compare:")
log(f"    conversion metric (monthly CO rate / 90+ stock): amex/synchrony = {cr:.4f}")
aco = float(B1[(B1.trust == 'amex') & (B1.rung == 'CO')]['mean'].iloc[0])
sco = float(B1[(B1.trust == 'synchrony') & (B1.rung == 'CO')]['mean'].iloc[0])
log(f"    final roll rung  (CO $ / deepest bucket $ lagged): amex {aco:.4f} vs synchrony {sco:.4f} "
    f"= {aco/sco:.4f}")
results["partB"] = {
    "ladder": B1.to_dict(orient="records"),
    "amex_vs_sync_rungs": B3.to_dict(orient="records"),
    "decomposition_full_sample": conv.to_dict(orient="index"),
    "conversion_ratio_amex_over_sync": cr,
    "denominators": DENOM_USED,
}

# ================================================================== PART C
log("")
log("=" * 100)
log("PART C - THE CYCLE TEST")
log("=" * 100)

REGIMES = [
    ("pre_covid", "2019-01", "2020-02"),
    ("stimulus", "2020-04", "2021-12"),
    ("normalising", "2022-01", "2023-06"),
    ("squeeze", "2023-07", "2026-12"),
]


def regime_of(p):
    for n, a, b in REGIMES:
        if pd.Period(a, "M") <= p <= pd.Period(b, "M"):
            return n
    return None


M["regime"] = M["ym"].map(regime_of)
R["regime"] = R["ym"].map(regime_of)
M["year"] = M["period_end"].dt.year

log("")
log("Regimes: pre_covid 2019-01..2020-02 | stimulus 2020-04..2021-12 | normalising 2022-01..2023-06 |")
log("         squeeze 2023-07..end. 2018-12 and 2020-03 fall outside every window and are dropped.")

log("")
log("(C1) Levels per regime per trust (mean of monthly values):")
c1 = M.dropna(subset=["regime"]).groupby(["regime", "trust"]).agg(
    n=("period_end", "size"),
    d30plus=("delinq_30plus_share", "mean"),
    d90plus=("delinq_90plus_share", "mean"),
    co_monthly=("co_monthly", "mean"),
).reset_index()
c1r = R.dropna(subset=["regime"]).groupby(["regime", "trust"])[rollcols].mean().reset_index()
C1 = c1.merge(c1r, on=["regime", "trust"], how="left")
C1["regime"] = pd.Categorical(C1["regime"], [n for n, _, _ in REGIMES], ordered=True)
C1 = C1.sort_values(["regime", "trust"])
C1.to_csv(os.path.join(HERE, "partC_levels_by_regime.csv"), index=False)
log(tbl(C1[["regime", "trust", "n", "d30plus", "d90plus", "co_monthly",
            "roll_30->60", "roll_60->90", "roll_90->120", "roll_120->150", "roll_CO"]], "%.5f"))

log("")
log("(C2) 30+ share, each trust vs synchrony, by regime. LEVELS FIRST, then ratio, log ratio,")
log("     difference in percentage points, and each trust against the six-trust mean.")
piv30 = C1.pivot(index="regime", columns="trust", values="d30plus")[TRUSTS]
six = piv30.mean(axis=1)
log("")
log("  levels (monthly 30+ share of receivables, as a fraction):")
log(tbl(piv30.reset_index(), "%.5f"))
log("")
log("  ratio to synchrony:")
rat = piv30.div(piv30["synchrony"], axis=0)
log(tbl(rat.reset_index(), "%.4f"))
log("")
log("  log ratio to synchrony:")
log(tbl(np.log(rat).reset_index(), "%.4f"))
log("")
log("  difference from synchrony, percentage points (trust - synchrony) * 100:")
dif = (piv30.sub(piv30["synchrony"], axis=0)) * 100
log(tbl(dif.reset_index(), "%.4f"))
log("")
log("  ratio to the unweighted six-trust mean of the 30+ share:")
rat6 = piv30.div(six, axis=0)
log(tbl(rat6.reset_index(), "%.4f"))
log("")
log("  six-trust mean level by regime: " + ", ".join(f"{i}={v:.5f}" for i, v in six.items()))

log("")
log("(C2) Year by year, so the shape is visible rather than four bins:")
yr = M.groupby(["year", "trust"])["delinq_30plus_share"].mean().unstack("trust")[TRUSTS]
yn = M.groupby(["year", "trust"])["delinq_30plus_share"].size().unstack("trust")[TRUSTS]
log("")
log("  levels by year (30+ share):")
log(tbl(yr.reset_index(), "%.5f"))
log("  months per year per trust: " + str(yn.min(axis=1).to_dict()) + " (min across trusts)")
log("")
log("  ratio to synchrony by year:")
yrat = yr.div(yr["synchrony"], axis=0)
log(tbl(yrat.reset_index(), "%.4f"))
log("")
log("  difference from synchrony by year, percentage points:")
log(tbl(((yr.sub(yr["synchrony"], axis=0)) * 100).reset_index(), "%.4f"))
log("")
log("  ratio to the six-trust mean by year:")
log(tbl(yr.div(yr.mean(axis=1), axis=0).reset_index(), "%.4f"))
yr.to_csv(os.path.join(HERE, "partC_30plus_by_year.csv"))
piv30.to_csv(os.path.join(HERE, "partC_30plus_by_regime.csv"))

# roll-rate ratios by regime, comparable rungs only
log("")
log("(C2b) Comparable roll rungs, amex vs synchrony, by regime:")
rr = []
for rn in ["30->60", "60->90"]:
    p = C1.pivot(index="regime", columns="trust", values="roll_" + rn)
    for reg in p.index:
        rr.append({"rung": rn, "regime": reg, "amex": p.loc[reg, "amex"], "synchrony": p.loc[reg, "synchrony"],
                   "ratio": p.loc[reg, "amex"] / p.loc[reg, "synchrony"],
                   "diff_pp": (p.loc[reg, "amex"] - p.loc[reg, "synchrony"]) * 100})
RR = pd.DataFrame(rr)
log(tbl(RR, "%.4f"))
RR.to_csv(os.path.join(HERE, "partC_roll_ratios_by_regime.csv"), index=False)


# --- formal test on monthly data: log(amex 30+) - log(sync 30+) on regime dummies, Newey-West
def nw_ols(y, X, lags=6):
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    e = y - X @ beta
    n, k = X.shape
    XtX_inv = np.linalg.inv(X.T @ X)
    S = (X * e[:, None]).T @ (X * e[:, None])
    for L in range(1, lags + 1):
        w = 1.0 - L / (lags + 1.0)
        u = X * e[:, None]
        G = u[L:].T @ u[:-L]
        S += w * (G + G.T)
    cov = XtX_inv @ S @ XtX_inv * n / (n - k)
    return beta, np.sqrt(np.diag(cov))


w = M.dropna(subset=["regime"]).pivot_table(index="ym", columns="trust", values="delinq_30plus_share")
w = w.dropna(subset=["amex", "synchrony"])
w = w[w.index.map(regime_of).notna()]
ylr = np.log(w["amex"].to_numpy() / w["synchrony"].to_numpy())
regs = [regime_of(p) for p in w.index]
names = [n for n, _, _ in REGIMES]
X = np.column_stack([np.array([1.0 if r == n else 0.0 for r in regs]) for n in names])
beta, se = nw_ols(ylr, X, lags=6)
log("")
log("(C3) Formal test on the 87 aligned monthly observations: regress log(amex 30+ / synchrony 30+)")
log("     on four regime dummies with no constant; Newey-West standard errors, 6 lags.")
log("     Coefficient = mean log ratio in that regime; exp(coef) = the ratio.")
tst = pd.DataFrame({"regime": names, "n": [regs.count(n) for n in names],
                    "mean_log_ratio": beta, "se": se, "ratio": np.exp(beta),
                    "ratio_lo95": np.exp(beta - 1.96 * se), "ratio_hi95": np.exp(beta + 1.96 * se)})
log(tbl(tst, "%.4f"))
d_sq_st = beta[3] - beta[1]
se_d = float(np.sqrt(se[3] ** 2 + se[1] ** 2))
log(f"     squeeze minus stimulus in logs = {d_sq_st:+.4f} (se ~ {se_d:.4f}, z = {d_sq_st/se_d:+.2f});")
log(f"     ratio of ratios = {np.exp(d_sq_st):.4f}. Positive means the gap NARROWED in the squeeze.")
d_st_pre = beta[1] - beta[0]
se_d2 = float(np.sqrt(se[1] ** 2 + se[0] ** 2))
log(f"     stimulus minus pre_covid in logs = {d_st_pre:+.4f} (se ~ {se_d2:.4f}, z = {d_st_pre/se_d2:+.2f}).")
log("     (se treats the four regime means as independent; the NW correction is within-regime only,")
log("      so the difference se is approximate.)")

log("")
log("(C4) FLOOR CHECK - the same claim in four representations, amex vs synchrony:")
fc = pd.DataFrame({
    "amex_level": piv30["amex"], "sync_level": piv30["synchrony"],
    "ratio": rat["amex"], "log_ratio": np.log(rat["amex"]),
    "diff_pp": dif["amex"], "amex_vs_six_mean": rat6["amex"], "sync_vs_six_mean": rat6["synchrony"],
    "six_mean": six,
})
log(tbl(fc.reset_index(), "%.5f"))
fc.to_csv(os.path.join(HERE, "partC_floor_check.csv"))

log("")
log("(C5) Receivables level breaks - month-over-month change in receivables_principal above 5%:")
brk = []
for t, g in M.groupby("trust"):
    g = g.sort_values("period_end")
    ch = g["receivables_principal"].pct_change()
    for (_, r), c in zip(g.iterrows(), ch):
        if pd.notna(c) and abs(c) > 0.05:
            brk.append({"trust": t, "period_end": r["period_end"].date(), "pct_change": c,
                        "recv_bn": r["receivables_principal"] / 1e9})
BRK = pd.DataFrame(brk)
log(tbl(BRK, "%.4f") if len(BRK) else "  none above 5%")
BRK.to_csv(os.path.join(HERE, "partC_receivable_breaks.csv"), index=False)
log("")
log("  Full-sample receivables path, first / min / max / last ($bn):")
pth = M.groupby("trust")["receivables_principal"].agg(["first", "min", "max", "last"]) / 1e9
log(tbl(pth.reset_index(), "%.3f"))

results["partC"] = {
    "levels_30plus_by_regime": piv30.to_dict(orient="index"),
    "ratio_to_synchrony_by_regime": rat.to_dict(orient="index"),
    "log_ratio_to_synchrony_by_regime": np.log(rat).to_dict(orient="index"),
    "diff_pp_to_synchrony_by_regime": dif.to_dict(orient="index"),
    "ratio_to_six_mean_by_regime": rat6.to_dict(orient="index"),
    "six_trust_mean_by_regime": six.to_dict(),
    "levels_30plus_by_year": yr.to_dict(orient="index"),
    "ratio_to_synchrony_by_year": yrat.to_dict(orient="index"),
    "regime_regression": tst.to_dict(orient="records"),
    "squeeze_minus_stimulus_log": d_sq_st,
    "roll_ratios_by_regime": RR.to_dict(orient="records"),
    "receivable_breaks": BRK.to_dict(orient="records") if len(BRK) else [],
}

with open(os.path.join(HERE, "results.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")


def jd(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (pd.Period, pd.Timestamp)):
        return str(o)
    return str(o)


with open(os.path.join(HERE, "results.json"), "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, default=jd)
print("\nwrote results.txt, results.json and CSVs to", HERE)
