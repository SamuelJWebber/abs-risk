"""
Monte Carlo: does free-riding on a premium badge contaminate estimators of the
"brand / priority" effect in card delinquency?

Person i, month t, card c (issuer 0 = premium, 1..4 = non-premium).
Channels (each switchable):
  SELECTION   premium issuer approves on a private signal of creditworthiness beyond FICO
  BRAND       true protection term alpha on the premium card (default 0)
  FREE-RIDING other issuers raise their lines by GAMMA when the premium badge is on the file
Always on:
  line endogeneity  each issuer's line responds to the others' lines (2 best-response rounds)
  liquidity         person-level: more available credit lowers delinquency (beta), more total
                    balance raises it (kappa); net sign by FICO tier follows Agarwal et al. 2018
  card terms        own-card room (Andersson et al. 2013) and balance share (Gathergood et al. 2019)

Run:  cd C:/Users/samwe/code/abs-risk && python -m uv run python <this file>
"""
import os, itertools, time
import numpy as np
import pandas as pd

OUT = os.path.dirname(os.path.abspath(__file__))
SEED = 20260910
N = 200_000          # people
T = 12               # months
CUTOFF = 680         # premium approval FICO cutoff (RD running variable)
GAMMA = 0.10         # free-riding: +10% on other issuers' lines when badge present (ASSUMED;
                     # bracketed by Foley et al. Chile +6.7% other-bank limits and Dobbie et al. +50% for flag removal)
LAM_L = 0.05         # line endogeneity: $ of own line per $ of other issuers' lines (ASSUMED, unmeasured)
ALPHA_ON = 0.4       # brand term, latent units, when "brand on"
BASE_LINE = np.array([12000., 8000., 5000., 2500., 3500.])   # issuer 0..4 (premium, bank, bank, retail, subprime)

# FICO tiers as in Agarwal-Chomsisengphet-Mahoney-Stroebel (QJE 2018): <=660, 661-700, 701-740, >740
TIER_EDGES = np.array([660, 700, 740])
UTIL_MEAN = np.array([0.60, 0.45, 0.32, 0.15])   # balance/line; ACMS all-cards MPB 0.59/0.46/0.32/-0.05 (prime floored)
BETA = np.array([0.020, 0.020, 0.015, 0.012])    # liquidity relief per $1000 available credit (latent units)
KAPPA = np.array([0.060, 0.040, 0.030, 0.010])   # debt burden per $1000 total balance (latent units)
B1 = 0.02            # own-card room per $1000 lowers own-card delinquency (Andersson et al.)
B2 = 0.50            # own-card balance share raises own-card delinquency (Gathergood et al. balance matching)
TARGET_MONTHLY = np.array([0.030, 0.015, 0.007, 0.0025])   # monthly 30+ entry by tier, calibration target
RD_BW = 15


def tier_of(fico):
    return np.searchsorted(TIER_EDGES, fico, side="left")   # 0..3


def demean_by(x, key, nkey):
    """subtract group means; x may be 1-d or 2-d (rows=obs)."""
    cnt = np.bincount(key, minlength=nkey).astype(float)
    if x.ndim == 1:
        s = np.bincount(key, weights=x, minlength=nkey)
        return x - (s / np.maximum(cnt, 1))[key]
    out = np.empty_like(x)
    for k in range(x.shape[1]):
        s = np.bincount(key, weights=x[:, k], minlength=nkey)
        out[:, k] = x[:, k] - (s / np.maximum(cnt, 1))[key]
    return out


def ols_slope(y, X):
    """coefficient vector from lstsq; X may be 1-d."""
    if X.ndim == 1:
        return np.array([np.dot(X, y) / np.dot(X, X)])
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    return b


class World:
    """All random primitives drawn once; channels applied on top so counterfactuals share draws."""

    def __init__(self, seed):
        rng = np.random.default_rng(seed)
        self.theta = rng.standard_normal(N)                                  # unobserved creditworthiness
        v = rng.standard_normal(N)
        self.fico = np.clip(700 + 60 * (0.7 * self.theta + 0.714 * v), 520, 850)
        self.zf = (self.fico - 700) / 60
        self.tier = tier_of(self.fico)
        self.s_prem = self.theta + 0.8 * rng.standard_normal(N)              # premium issuer's private signal
        self.applicant = rng.random(N) < 0.6
        self.u_coin = rng.random(N)                                          # coin for selection-off approval
        self.cash = 1500 * np.exp(0.6 * self.zf + 0.3 * self.theta + 0.4 * rng.standard_normal(N))
        self.K = rng.choice([2, 3, 4], size=N, p=[0.40, 0.35, 0.25])
        self.perm = np.argsort(rng.random((N, 4)), axis=1) + 1              # order of non-premium issuers
        self.e = rng.standard_normal((N, T))                                 # person-month shock
        # card-level draws: allocate max possible cards (4 per person) so draws are stable across scenarios
        self.eta_card = rng.standard_normal((N, 5))                          # issuer private signal on lines, by issuer slot
        self.util_noise = rng.standard_normal((N, 5))
        self.xi = rng.standard_normal((N, 5, T))                             # card-month shock by issuer slot
    # ---------- premium holding ----------
    def premium(self, selection, cutoff=CUTOFF):
        above = self.applicant & (self.fico >= cutoff)
        p_sel = np.mean(self.s_prem[above] > 0)     # selection-on approval rate, reused so premium share matches
        if selection:
            return above & (self.s_prem > 0)
        return above & (self.u_coin < p_sel)

    # ---------- card table ----------
    def cards(self, G):
        n_np = self.K - G.astype(int)
        pid, iss = [], []
        for r in range(4):
            m = n_np > r
            pid.append(np.nonzero(m)[0]); iss.append(self.perm[m, r])
        pid.append(np.nonzero(G)[0]); iss.append(np.zeros(G.sum(), dtype=int))
        pid = np.concatenate(pid); iss = np.concatenate(iss)
        o = np.lexsort((iss, pid))
        return pid[o], iss[o]

    # ---------- lines with free-riding and endogeneity ----------
    def lines(self, pid, iss, G, gamma):
        L0 = BASE_LINE[iss] * np.exp(0.8 * self.zf[pid] + 0.15 * self.eta_card[pid, iss])
        L0 = L0 * (1 + gamma * G[pid] * (iss != 0))          # free-riding on the badge
        L = L0.copy()
        for _ in range(2):                                   # best-response rounds on others' lines
            tot = np.bincount(pid, weights=L, minlength=N)
            L = L0 + LAM_L * (tot[pid] - L)
        return L

    # ---------- delinquency ----------
    def latent(self, pid, iss, L, alpha):
        tier = self.tier[pid]
        u = np.clip(UTIL_MEAN[tier] + 0.15 * self.util_noise[pid, iss], 0.02, 0.98)
        B = u * L
        room = L - B
        totB = np.bincount(pid, weights=B, minlength=N)
        Q = np.bincount(pid, weights=room, minlength=N) + self.cash
        share = B / totB[pid]
        person_term = -0.8 * self.theta - BETA[self.tier] * Q / 1000 + KAPPA[self.tier] * totB / 1000
        card_term = -B1 * room / 1000 + B2 * share - alpha * (iss == 0)
        y = (person_term[pid] + card_term)[:, None] + self.e[pid] + self.xi[pid, iss]      # (ncards, T)
        return y, dict(L=L, B=B, room=room, share=share, u=u)


def calibrate_thresholds(w):
    """thresholds by tier so that the all-channels-off world hits TARGET_MONTHLY."""
    G = w.premium(False)
    pid, iss = w.cards(G)
    L = w.lines(pid, iss, G, 0.0)
    y, _ = w.latent(pid, iss, L, 0.0)
    thr = np.zeros(4)
    tier = w.tier[pid]
    for k in range(4):
        thr[k] = np.quantile(y[tier == k].ravel(), 1 - TARGET_MONTHLY[k])
    return thr


def rd_estimate(w, G, y_person, mask, cutoff=CUTOFF):
    """fuzzy RD at CUTOFF on applicants: jump in y_person / jump in G, local linear, bandwidth RD_BW."""
    x = w.fico - cutoff
    keep = mask & (np.abs(x) <= RD_BW)
    def side_intercept(v, side):
        m = keep & (x >= 0 if side else x < 0)
        X = np.column_stack([np.ones(m.sum()), x[m]])
        return np.linalg.lstsq(X, v[m], rcond=None)[0][0]
    itt = side_intercept(y_person, True) - side_intercept(y_person, False)
    fs = side_intercept(G.astype(float), True) - side_intercept(G.astype(float), False)
    return itt, fs, keep.sum()


def run_scenario(w, thr, free_riding, brand, selection, gamma=GAMMA, cutoff=CUTOFF):
    G = w.premium(selection, cutoff)
    pid, iss = w.cards(G)
    alpha = ALPHA_ON if brand else 0.0
    g = gamma if free_riding else 0.0
    L = w.lines(pid, iss, G, g)
    y, terms = w.latent(pid, iss, L, alpha)
    tier_c = w.tier[pid]
    D = (y > thr[tier_c][:, None]).astype(float)                # (ncards, T)
    y0, _ = w.latent(pid, iss, L, 0.0)                          # counterfactual: brand off, same draws
    D0 = (y0 > thr[tier_c][:, None]).astype(float)
    Lnf = w.lines(pid, iss, G, 0.0)                             # counterfactual: free-riding off, same draws
    ynf, _ = w.latent(pid, iss, Lnf, alpha)
    Dnf = (ynf > thr[tier_c][:, None]).astype(float)

    P = (iss == 0).astype(float)
    Gc = G[pid].astype(float)
    Dbar = D.mean(axis=1)
    ncards = len(pid)
    res = {}

    # true effects (pp)
    true_prem = 100 * (D[P == 1] - D0[P == 1]).mean()           # brand causal effect on premium-card monthly 30+
    fr_other = 100 * (D[(P == 0) & (Gc == 1)] - Dnf[(P == 0) & (Gc == 1)]).mean()   # free-riding causal effect on holders' other cards
    fr_prem = 100 * (D[P == 1] - Dnf[P == 1]).mean()            # free-riding causal effect on the premium card itself

    # (a) pool-level comparison at constant FICO mix (10-point bins, weights = premium cards' mix)
    fbin = ((w.fico[pid] - 500) // 10).astype(int)
    nb = fbin.max() + 1
    def rate(mask):
        return np.bincount(fbin[mask], weights=Dbar[mask], minlength=nb), np.bincount(fbin[mask], minlength=nb)
    sp, cp = rate(P == 1); sn, cn = rate(P == 0)
    ok = (cp > 0) & (cn > 0)
    wts = cp[ok] / cp[ok].sum()
    est_a = 100 * np.sum(wts * (sp[ok] / cp[ok] - sn[ok] / cn[ok]))
    res["a_pool_constant_fico"] = dict(true=true_prem, est=est_a,
        note="premium cards minus non-premium cards, monthly 30+ entry, reweighted to premium cards' 10-pt FICO mix")

    # (b) cross-section: other-card delinquency, holders vs non-holders, FICO-bin controls
    m = P == 0
    yb = demean_by(Dbar[m], fbin[m], nb); xb = demean_by(Gc[m], fbin[m], nb)
    est_b = 100 * ols_slope(yb, xb)[0]
    res["b_crosssection_other_cards"] = dict(true=0.0, est=est_b,
        note=f"coef on holds-premium in other-card monthly 30+, FICO-bin FE; true causal free-riding effect on holders' other cards = {fr_other:+.3f} pp (not brand)")

    # (c) within person, across cards, no time effects (holders only; card-level 12-month mean)
    h = Gc == 1
    hid = np.unique(pid[h], return_inverse=True)[1]
    yc = demean_by(Dbar[h], hid, hid.max() + 1); xc = demean_by(P[h], hid, hid.max() + 1)
    est_c = 100 * ols_slope(yc, xc)[0]
    res["c_person_fe"] = dict(true=true_prem, est=est_c,
        note="holders only; premium card vs the same person's other cards, 12-month means, person FE")

    # (d) within person-month FE on the hierarchy sample (>=1 late and >=1 current card in that month)
    rows_c, rows_t = np.nonzero(np.ones_like(D[h], dtype=bool))
    idx_c = np.nonzero(h)[0][rows_c]
    Dl = D[idx_c, rows_t]
    pm = hid[rows_c] * T + rows_t
    npm = pm.max() + 1
    nlate = np.bincount(pm, weights=Dl, minlength=npm); ncard = np.bincount(pm, minlength=npm)
    mixed = (nlate[pm] > 0) & (nlate[pm] < ncard[pm])
    pm2 = np.unique(pm[mixed], return_inverse=True)[1]
    yd = demean_by(Dl[mixed], pm2, pm2.max() + 1); xd = demean_by(P[idx_c][mixed], pm2, pm2.max() + 1)
    est_d = 100 * ols_slope(yd, xd)[0]
    prem_mixed = mixed & (P[idx_c] == 1)
    true_d = 100 * (Dl[prem_mixed] - D0[idx_c, rows_t][prem_mixed]).mean()
    res["d_person_month_fe"] = dict(true=true_d, est=est_d,
        note=f"holders; person-month FE on months with >=1 late and >=1 current card ({mixed.sum():,} card-months); true = brand effect on premium cards inside that sample")

    # (e) same as (d) plus card line, balance, room and balance-share controls
    X = np.column_stack([P[idx_c], terms["L"][idx_c] / 1000, terms["B"][idx_c] / 1000,
                         terms["room"][idx_c] / 1000, terms["share"][idx_c]])[mixed]
    Xe = demean_by(X, pm2, pm2.max() + 1)
    est_e = 100 * ols_slope(yd, Xe)[0]
    res["e_person_month_fe_plus_line_controls"] = dict(true=true_d, est=est_e,
        note="(d) plus line, balance, room, balance share (all measured before the spell; no post-spell line cuts simulated)")

    # (f) fuzzy RD at premium approval cutoff, outcome = person's other-card delinquency
    other_rate = np.bincount(pid[P == 0], weights=Dbar[P == 0], minlength=N) / np.maximum(np.bincount(pid[P == 0], minlength=N), 1)
    itt, fs, nband = rd_estimate(w, G, other_rate, w.applicant, cutoff)
    est_f = 100 * itt / fs
    res["f_rd_at_cutoff_other_cards"] = dict(true=0.0, est=est_f,
        note=f"fuzzy RD, applicants within {RD_BW} FICO pts of {cutoff} (n={nband:,}), first stage {fs:.2f}; estimand = badge's causal effect on other cards = free-riding liquidity effect {fr_other:+.3f} pp, not brand")

    diag = dict(premium_share=G.mean(), n_cards=ncards, monthly_rate_all=D.mean(),
                rate_prem=D[P == 1].mean(), rate_other_holders=D[(P == 0) & (Gc == 1)].mean(),
                rate_nonholders=D[Gc == 0].mean(), fr_effect_other=fr_other, fr_effect_prem=fr_prem,
                mean_line_other_holders=terms["L"][(P == 0) & (Gc == 1)].mean(),
                mean_line_other_nonholders=terms["L"][(P == 0) & (Gc == 0)].mean())
    return res, diag


def line_diagnostic(w, thr):
    """implied effect of +$1000 on one card's line on 12-month any-30+ for that card, by tier (compare to ACMS)."""
    G = w.premium(False)
    pid, iss = w.cards(G)
    L = w.lines(pid, iss, G, 0.0)
    first = np.r_[True, pid[1:] != pid[:-1]]          # one card per person
    y, _ = w.latent(pid, iss, L, 0.0)
    L2 = L.copy(); L2[first] += 1000
    y2, _ = w.latent(pid, iss, L2, 0.0)
    tier = w.tier[pid]
    out = {}
    for k in range(4):
        m = first & (tier == k)
        a0 = (y[m] > thr[k]).any(axis=1).mean(); a1 = (y2[m] > thr[k]).any(axis=1).mean()
        out[k] = (100 * a0, 100 * (a1 - a0))
    return out


def main():
    t0 = time.time()
    names = {"a_pool_constant_fico": "(a) pool-level, constant FICO mix",
             "b_crosssection_other_cards": "(b) cross-section, other cards, FICO-controlled",
             "c_person_fe": "(c) within-person, no time effects",
             "d_person_month_fe": "(d) person x month FE, issuer dummy",
             "e_person_month_fe_plus_line_controls": "(e) person x month FE + line/balance controls",
             "f_rd_at_cutoff_other_cards": "(f) RD at approval cutoff, other cards"}
    # (free_riding, brand, selection, gamma, cutoff)
    scen_list = [(fr, br, se, GAMMA, CUTOFF) for fr, br, se in itertools.product([0, 1], [0, 1], [0, 1])]
    scen_list += [(1, 0, 0, 0.25, CUTOFF),            # sensitivity: larger free-riding
                  (0, 0, 0, GAMMA, 620), (1, 0, 0, GAMMA, 620), (1, 0, 0, 0.25, 620)]   # subprime holders
    def label_of(fr, br, se, g, cut):
        return (f"free-riding {'ON' if fr else 'off'}{' (gamma=%.2f)' % g if (fr and g != GAMMA) else ''}, "
                f"brand {'POSITIVE' if br else 'zero'}, selection {'ON' if se else 'off'}"
                f"{'' if cut == CUTOFF else ', cutoff %d' % cut}")
    SEEDS = [SEED + k for k in range(5)]
    rows, diags, notes = [], [], {}
    diag_lines = []
    for seed in SEEDS:
        w = World(seed)
        thr = calibrate_thresholds(w)
        dl = line_diagnostic(w, thr)
        diag_lines.append(dl)
        clean = {}   # (brand, cutoff) -> estimates with free-riding off and selection off
        for fr, br, se, g, cut in scen_list:
            res, diag = run_scenario(w, thr, fr, br, se, gamma=g, cutoff=cut)
            label = label_of(fr, br, se, g, cut)
            if fr == 0 and se == 0:
                clean[(br, cut)] = {k: r["est"] for k, r in res.items()}
            diag.update(scenario=label, seed=seed); diags.append(diag)
            for k, r in res.items():
                rows.append(dict(scenario=label, seed=seed, free_riding=fr, brand=br, selection=se,
                                 gamma=g if fr else 0.0, cutoff=cut, estimator=names[k],
                                 true=r["true"], est=r["est"], est_clean=clean[(br, cut)][k]))
                notes[(label, names[k])] = r["note"]
        print(f"seed {seed} done {time.time()-t0:.0f}s")
    raw = pd.DataFrame(rows)
    raw.to_csv(os.path.join(OUT, "results_by_seed.csv"), index=False)
    pd.DataFrame(diags).to_csv(os.path.join(OUT, "diagnostics_by_seed.csv"), index=False)

    # aggregate over seeds. For (d)/(e) the reported 'true' is the estimator's own value in the clean world
    # (free-riding off, selection off, same brand, same seed): the hierarchy-sample scale is not a population pp.
    agg = raw.groupby(["scenario", "free_riding", "brand", "selection", "gamma", "cutoff", "estimator"], sort=False).agg(
        true=("true", "mean"), est=("est", "mean"), est_sd=("est", "std"), est_clean=("est_clean", "mean")).reset_index()
    de = agg.estimator.str.startswith("(d)") | agg.estimator.str.startswith("(e)")
    agg["true_brand_effect_pp"] = np.where(de, agg.est_clean, agg.true)
    agg["estimated_pp"] = agg.est
    agg["bias_pp"] = agg.estimated_pp - agg.true_brand_effect_pp
    agg["channel_bias_vs_clean_pp"] = agg.est - agg.est_clean          # what free-riding / selection add, on the estimator's own scale
    agg["mc_se_pp"] = agg.est_sd / np.sqrt(len(SEEDS))
    agg["note"] = [notes[(s, e)] for s, e in zip(agg.scenario, agg.estimator)]
    for c in ["true_brand_effect_pp", "estimated_pp", "bias_pp", "channel_bias_vs_clean_pp", "mc_se_pp", "est_clean"]:
        agg[c] = agg[c].round(3)
    out = agg[["scenario", "free_riding", "brand", "selection", "gamma", "cutoff", "estimator",
               "true_brand_effect_pp", "estimated_pp", "bias_pp", "channel_bias_vs_clean_pp", "mc_se_pp", "est_clean", "note"]]
    out.to_csv(os.path.join(OUT, "results.csv"), index=False)
    dd = pd.DataFrame(diags).drop(columns=["seed"]).groupby("scenario", sort=False).mean().reset_index()
    dd.to_csv(os.path.join(OUT, "diagnostics.csv"), index=False)
    dlm = {k: (np.mean([d[k][0] for d in diag_lines]), np.mean([d[k][1] for d in diag_lines])) for k in range(4)}

    md = ["# Free-riding Monte Carlo: what each estimator reports as the 'brand effect'", "",
          f"N={N:,} people x {T} months x 2-4 cards, {len(SEEDS)} seeds (mean reported, mc_se = sd/sqrt(seeds)). "
          "Units: monthly 30+ entry in percentage points; negative = premium card (or premium holders' other cards) less delinquent. "
          "For (d) and (e) the outcome scale is 'share of the late cards in a mixed month', so their 'true' column is the same estimator's value in the clean world (free-riding off, selection off, same brand term).", "",
          "Parameters: GAMMA (free-riding) = %.2f on other issuers' lines (ASSUMED; Chile other-bank +6.7%%, US bankruptcy-flag removal +50%%); LAM_L = %.2f (assumed); ALPHA (brand, latent) = %.1f; utilization by tier %s; liquidity beta %s; burden kappa %s; own-card room B1=%.2f, balance share B2=%.2f; premium cutoff FICO %d."
          % (GAMMA, LAM_L, ALPHA_ON, UTIL_MEAN.tolist(), BETA.tolist(), KAPPA.tolist(), B1, B2, CUTOFF), "",
          "Calibration check, effect of +$1000 on one card's line on that card's 12-month any-30+ (ACMS 2018, 90+DPD over 4 years: +1.16, +0.80, +0.74, -0.17 pp):", ""]
    for k, (base, d) in dlm.items():
        md.append(f"- tier {k} ({['<=660','661-700','701-740','>740'][k]}): base {base:.2f}%, change {d:+.2f} pp")
    md += ["", "## Results", ""]
    for label in out.scenario.unique():
        sub = out[out.scenario == label]
        md += [f"### {label}", "", "| estimator | true | estimate | bias | vs clean world | mc se |", "|---|---|---|---|---|---|"]
        for _, r in sub.iterrows():
            md.append(f"| {r.estimator} | {r.true_brand_effect_pp:+.3f} | {r.estimated_pp:+.3f} | {r.bias_pp:+.3f} | {r.channel_bias_vs_clean_pp:+.3f} | {r.mc_se_pp:.3f} |")
        md.append("")
    md += ["## Diagnostics (means over seeds)", "", dd.to_string(), ""]
    with open(os.path.join(OUT, "results.md"), "w", encoding="utf-8") as f:
        f.write(chr(10).join(md))
    pd.set_option("display.width", 250)
    print(out.drop(columns=["note"]).to_string())
    print(dd.to_string())
    print("line diagnostic", dlm)


if __name__ == "__main__":
    main()
