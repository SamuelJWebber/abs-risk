# Free-riding Monte Carlo: what each estimator reports as the 'brand effect'

N=200,000 people x 12 months x 2-4 cards, 5 seeds (mean reported, mc_se = sd/sqrt(seeds)). Units: monthly 30+ entry in percentage points; negative = premium card (or premium holders' other cards) less delinquent. For (d) and (e) the outcome scale is 'share of the late cards in a mixed month', so their 'true' column is the same estimator's value in the clean world (free-riding off, selection off, same brand term).

Parameters: GAMMA (free-riding) = 0.10 on other issuers' lines (ASSUMED; Chile other-bank +6.7%, US bankruptcy-flag removal +50%); LAM_L = 0.05 (assumed); ALPHA (brand, latent) = 0.4; utilization by tier [0.6, 0.45, 0.32, 0.15]; liquidity beta [0.02, 0.02, 0.015, 0.012]; burden kappa [0.06, 0.04, 0.03, 0.01]; own-card room B1=0.02, balance share B2=0.50; premium cutoff FICO 680.

Calibration check, effect of +$1000 on one card's line on that card's 12-month any-30+ (ACMS 2018, 90+DPD over 4 years: +1.16, +0.80, +0.74, -0.17 pp):

- tier 0 (<=660): base 28.45%, change +2.10 pp
- tier 1 (661-700): base 16.36%, change +0.36 pp
- tier 2 (701-740): base 8.06%, change -0.02 pp
- tier 3 (>740): base 2.86%, change -0.09 pp

## Results

### free-riding off, brand zero, selection off

| estimator | true | estimate | bias | vs clean world | mc se |
|---|---|---|---|---|---|
| (a) pool-level, constant FICO mix | +0.000 | +0.021 | +0.021 | +0.000 | 0.002 |
| (b) cross-section, other cards, FICO-controlled | +0.000 | -0.068 | -0.068 | +0.000 | 0.006 |
| (c) within-person, no time effects | +0.000 | +0.049 | +0.049 | +0.000 | 0.003 |
| (d) person x month FE, issuer dummy | +3.282 | +3.282 | +0.000 | +0.000 | 0.194 |
| (e) person x month FE + line/balance controls | +0.052 | +0.052 | +0.000 | +0.000 | 0.648 |
| (f) RD at approval cutoff, other cards | +0.000 | +0.005 | +0.005 | +0.000 | 0.058 |

### free-riding off, brand zero, selection ON

| estimator | true | estimate | bias | vs clean world | mc se |
|---|---|---|---|---|---|
| (a) pool-level, constant FICO mix | +0.000 | -0.310 | -0.310 | -0.330 | 0.003 |
| (b) cross-section, other cards, FICO-controlled | +0.000 | -0.488 | -0.488 | -0.420 | 0.001 |
| (c) within-person, no time effects | +0.000 | +0.016 | +0.016 | -0.033 | 0.003 |
| (d) person x month FE, issuer dummy | +3.282 | +2.367 | -0.915 | -0.915 | 0.365 |
| (e) person x month FE + line/balance controls | +0.052 | -0.952 | -1.004 | -1.004 | 0.415 |
| (f) RD at approval cutoff, other cards | +0.000 | +0.063 | +0.063 | +0.057 | 0.078 |

### free-riding off, brand POSITIVE, selection off

| estimator | true | estimate | bias | vs clean world | mc se |
|---|---|---|---|---|---|
| (a) pool-level, constant FICO mix | -0.343 | -0.323 | +0.021 | +0.000 | 0.003 |
| (b) cross-section, other cards, FICO-controlled | +0.000 | -0.068 | -0.068 | +0.000 | 0.006 |
| (c) within-person, no time effects | -0.343 | -0.289 | +0.055 | +0.000 | 0.002 |
| (d) person x month FE, issuer dummy | -23.217 | -23.217 | +0.000 | +0.000 | 0.170 |
| (e) person x month FE + line/balance controls | -24.564 | -24.564 | +0.000 | +0.000 | 0.838 |
| (f) RD at approval cutoff, other cards | +0.000 | +0.005 | +0.005 | +0.000 | 0.058 |

### free-riding off, brand POSITIVE, selection ON

| estimator | true | estimate | bias | vs clean world | mc se |
|---|---|---|---|---|---|
| (a) pool-level, constant FICO mix | -0.157 | -0.467 | -0.310 | -0.144 | 0.003 |
| (b) cross-section, other cards, FICO-controlled | +0.000 | -0.488 | -0.488 | -0.420 | 0.001 |
| (c) within-person, no time effects | -0.157 | -0.137 | +0.020 | +0.151 | 0.003 |
| (d) person x month FE, issuer dummy | -23.217 | -24.299 | -1.082 | -1.082 | 0.594 |
| (e) person x month FE + line/balance controls | -24.564 | -25.625 | -1.061 | -1.061 | 0.969 |
| (f) RD at approval cutoff, other cards | +0.000 | +0.063 | +0.063 | +0.057 | 0.078 |

### free-riding ON, brand zero, selection off

| estimator | true | estimate | bias | vs clean world | mc se |
|---|---|---|---|---|---|
| (a) pool-level, constant FICO mix | +0.000 | +0.012 | +0.012 | -0.009 | 0.003 |
| (b) cross-section, other cards, FICO-controlled | +0.000 | -0.070 | -0.070 | -0.001 | 0.006 |
| (c) within-person, no time effects | +0.000 | +0.041 | +0.041 | -0.008 | 0.003 |
| (d) person x month FE, issuer dummy | +3.282 | +2.784 | -0.498 | -0.498 | 0.226 |
| (e) person x month FE + line/balance controls | +0.052 | +0.025 | -0.027 | -0.027 | 0.572 |
| (f) RD at approval cutoff, other cards | +0.000 | +0.022 | +0.022 | +0.017 | 0.057 |

### free-riding ON, brand zero, selection ON

| estimator | true | estimate | bias | vs clean world | mc se |
|---|---|---|---|---|---|
| (a) pool-level, constant FICO mix | +0.000 | -0.314 | -0.314 | -0.335 | 0.003 |
| (b) cross-section, other cards, FICO-controlled | +0.000 | -0.490 | -0.490 | -0.422 | 0.001 |
| (c) within-person, no time effects | +0.000 | +0.013 | +0.013 | -0.036 | 0.003 |
| (d) person x month FE, issuer dummy | +3.282 | +1.915 | -1.367 | -1.367 | 0.406 |
| (e) person x month FE + line/balance controls | +0.052 | -0.796 | -0.848 | -0.848 | 0.415 |
| (f) RD at approval cutoff, other cards | +0.000 | +0.072 | +0.072 | +0.067 | 0.076 |

### free-riding ON, brand POSITIVE, selection off

| estimator | true | estimate | bias | vs clean world | mc se |
|---|---|---|---|---|---|
| (a) pool-level, constant FICO mix | -0.338 | -0.326 | +0.012 | -0.004 | 0.003 |
| (b) cross-section, other cards, FICO-controlled | +0.000 | -0.070 | -0.070 | -0.001 | 0.006 |
| (c) within-person, no time effects | -0.338 | -0.292 | +0.047 | -0.003 | 0.002 |
| (d) person x month FE, issuer dummy | -23.217 | -23.569 | -0.351 | -0.351 | 0.189 |
| (e) person x month FE + line/balance controls | -24.564 | -24.652 | -0.088 | -0.088 | 0.776 |
| (f) RD at approval cutoff, other cards | +0.000 | +0.022 | +0.022 | +0.017 | 0.057 |

### free-riding ON, brand POSITIVE, selection ON

| estimator | true | estimate | bias | vs clean world | mc se |
|---|---|---|---|---|---|
| (a) pool-level, constant FICO mix | -0.154 | -0.468 | -0.314 | -0.146 | 0.003 |
| (b) cross-section, other cards, FICO-controlled | +0.000 | -0.490 | -0.490 | -0.422 | 0.001 |
| (c) within-person, no time effects | -0.154 | -0.137 | +0.017 | +0.151 | 0.003 |
| (d) person x month FE, issuer dummy | -23.217 | -24.594 | -1.377 | -1.377 | 0.627 |
| (e) person x month FE + line/balance controls | -24.564 | -25.524 | -0.960 | -0.960 | 0.906 |
| (f) RD at approval cutoff, other cards | +0.000 | +0.072 | +0.072 | +0.067 | 0.076 |

### free-riding ON (gamma=0.25), brand zero, selection off

| estimator | true | estimate | bias | vs clean world | mc se |
|---|---|---|---|---|---|
| (a) pool-level, constant FICO mix | +0.000 | +0.002 | +0.002 | -0.018 | 0.004 |
| (b) cross-section, other cards, FICO-controlled | +0.000 | -0.073 | -0.073 | -0.004 | 0.006 |
| (c) within-person, no time effects | +0.000 | +0.034 | +0.034 | -0.015 | 0.004 |
| (d) person x month FE, issuer dummy | +3.282 | +2.332 | -0.949 | -0.949 | 0.279 |
| (e) person x month FE + line/balance controls | +0.052 | -0.030 | -0.082 | -0.082 | 0.467 |
| (f) RD at approval cutoff, other cards | +0.000 | +0.054 | +0.054 | +0.048 | 0.059 |

### free-riding off, brand zero, selection off, cutoff 620

| estimator | true | estimate | bias | vs clean world | mc se |
|---|---|---|---|---|---|
| (a) pool-level, constant FICO mix | +0.000 | +0.167 | +0.167 | +0.000 | 0.005 |
| (b) cross-section, other cards, FICO-controlled | +0.000 | -0.009 | -0.009 | +0.000 | 0.007 |
| (c) within-person, no time effects | +0.000 | +0.166 | +0.166 | +0.000 | 0.005 |
| (d) person x month FE, issuer dummy | +6.258 | +6.258 | +0.000 | +0.000 | 0.194 |
| (e) person x month FE + line/balance controls | -0.524 | -0.524 | +0.000 | +0.000 | 0.511 |
| (f) RD at approval cutoff, other cards | +0.000 | +0.265 | +0.265 | +0.000 | 0.149 |

### free-riding ON, brand zero, selection off, cutoff 620

| estimator | true | estimate | bias | vs clean world | mc se |
|---|---|---|---|---|---|
| (a) pool-level, constant FICO mix | +0.000 | +0.158 | +0.158 | -0.009 | 0.006 |
| (b) cross-section, other cards, FICO-controlled | +0.000 | +0.007 | +0.007 | +0.016 | 0.007 |
| (c) within-person, no time effects | +0.000 | +0.147 | +0.147 | -0.019 | 0.005 |
| (d) person x month FE, issuer dummy | +6.258 | +5.497 | -0.761 | -0.761 | 0.185 |
| (e) person x month FE + line/balance controls | -0.524 | -0.468 | +0.056 | +0.056 | 0.414 |
| (f) RD at approval cutoff, other cards | +0.000 | +0.329 | +0.329 | +0.064 | 0.144 |

### free-riding ON (gamma=0.25), brand zero, selection off, cutoff 620

| estimator | true | estimate | bias | vs clean world | mc se |
|---|---|---|---|---|---|
| (a) pool-level, constant FICO mix | +0.000 | +0.150 | +0.150 | -0.017 | 0.006 |
| (b) cross-section, other cards, FICO-controlled | +0.000 | +0.030 | +0.030 | +0.039 | 0.007 |
| (c) within-person, no time effects | +0.000 | +0.125 | +0.125 | -0.041 | 0.005 |
| (d) person x month FE, issuer dummy | +6.258 | +4.623 | -1.635 | -1.635 | 0.204 |
| (e) person x month FE + line/balance controls | -0.524 | -0.409 | +0.115 | +0.115 | 0.333 |
| (f) RD at approval cutoff, other cards | +0.000 | +0.429 | +0.429 | +0.164 | 0.153 |

## Diagnostics (means over seeds)

                                                              scenario  premium_share   n_cards  monthly_rate_all  rate_prem  rate_other_holders  rate_nonholders  fr_effect_other  fr_effect_prem  mean_line_other_holders  mean_line_other_nonholders
0                           free-riding off, brand zero, selection off       0.240254  569972.2          0.013666   0.006621            0.005928         0.016036         0.000000        0.000000             10873.472261                 6411.873765
1                            free-riding off, brand zero, selection ON       0.239974  569972.2          0.013691   0.002883            0.002587         0.017166         0.000000        0.000000             12287.438638                 5996.705893
2                       free-riding off, brand POSITIVE, selection off       0.240254  569972.2          0.013377   0.003189            0.005928         0.016036         0.000000        0.000000             10873.472261                 6411.873765
3                        free-riding off, brand POSITIVE, selection ON       0.239974  569972.2          0.013559   0.001311            0.002587         0.017166         0.000000        0.000000             12287.438638                 5996.705893
4                            free-riding ON, brand zero, selection off       0.240254  569972.2          0.013657   0.006532            0.005914         0.016036        -0.001371       -0.008950             11840.032092                 6411.873765
5                             free-riding ON, brand zero, selection ON       0.239974  569972.2          0.013683   0.002829            0.002565         0.017166        -0.002233       -0.005418             13379.702868                 5996.705893
6                        free-riding ON, brand POSITIVE, selection off       0.240254  569972.2          0.013371   0.003147            0.005914         0.016036        -0.001371       -0.004161             11840.032092                 6411.873765
7                         free-riding ON, brand POSITIVE, selection ON       0.239974  569972.2          0.013554   0.001288            0.002565         0.017166        -0.002233       -0.002258             13379.702868                 5996.705893
8               free-riding ON (gamma=0.25), brand zero, selection off       0.240254  569972.2          0.013643   0.006428            0.005885         0.016036        -0.004260       -0.019356             13289.871837                 6411.873765
9               free-riding off, brand zero, selection off, cutoff 620       0.291840  569972.2          0.013914   0.012543            0.010815         0.014942         0.000000        0.000000              8524.516048                 7042.062190
10               free-riding ON, brand zero, selection off, cutoff 620       0.291840  569972.2          0.013939   0.012493            0.010974         0.014942         0.015921       -0.004939              9282.291992                 7042.062190
11  free-riding ON (gamma=0.25), brand zero, selection off, cutoff 620       0.291840  569972.2          0.013980   0.012468            0.011202         0.014942         0.038705       -0.007478             10418.955909                 7042.062190

## Findings (units: monthly 30+ entry, pp; negative = premium card or holders' other cards less delinquent)

1. Free-riding creates essentially NO spurious brand effect in pool-level and cross-sectional estimators when holders are prime (cutoff 680). Brand zero, selection off, free-riding on vs off: (a) moves -0.009 pp, (b) -0.001 pp, (f) +0.017 pp (MC se 0.003, 0.006, 0.057). Causal effect of badge-induced lines on holders' other cards: -0.001 pp at GAMMA 0.10, -0.004 pp at 0.25, on a 0.59 pp monthly base. Holders sit in the FICO bands where Agarwal et al. find near-zero net line effects.
2. Selection is the contaminant and is 100x larger: selection on, free-riding off, brand zero makes (a) report -0.31 pp and (b) -0.49 pp of nonexistent brand effect; adding free-riding changes (a) to -0.314.
3. Where the third channel is nonzero it has the WRONG sign for a halo. Cutoff 620 (holders include <=660): free-riding RAISES holders' other-card delinquency +0.016 pp (GAMMA 0.10) and +0.039 pp (0.25); (b) moves from -0.009 to +0.007 / +0.030; (f) from +0.27 to +0.33 / +0.43 (RD se 0.15). Badge holders look worse, not better.
4. Within-person (c) is immune to the person-level liquidity part: shifts of -0.008 / -0.015 pp against a true brand effect of -0.34 pp.
5. Line endogeneity leaves a small card-level residue in (d) that (e) removes: on the hierarchy-sample scale free-riding shifts (d) by -0.50 pp (se 0.23) at GAMMA 0.10 and -0.95 (se 0.28) at 0.25; (e) shifts -0.03 (se 0.57) and -0.08 (se 0.47). Sign: premium looks MORE protected here because other cards' balance shares rise (B2) and dominate the extra-room effect (B1); the real-data sign depends on B1 vs B2, unmeasured.
6. The larger residue in (d) is not free-riding: all channels off, brand zero, (d) = +3.3 pp (premium card carries the largest balance share); (e) = +0.05. That is H^raw vs H^brand, present regardless of free-riding.
7. (d)/(e) are population-dependent estimands: selection alone shifts them about -1 pp (se 0.4-0.6). (e) costs precision (se 0.5-0.9 vs 0.2) because the premium line is nearly collinear with the premium dummy within person.
8. All channels off, (b) = -0.068 pp: the premium card's OWN large line is liquidity for the holder's other cards; a terms effect, not brand or free-riding, and part of the RD estimand.

Verdict: "free riding harms the ability to come up with a payment hierarchy estimator" is refuted in this DGP. Person x month FE absorb the person-level term; the card-level residue is 0.5-1 pp on the hierarchy scale and is removed by pre-spell line/balance controls. Free-riding adds < 0.01 pp of spurious brand effect for prime holders and a wrong-signed effect when holders include subprime. Selection is what leaves pool and cross-sectional brand effects unidentified.

Assumed, not measured: GAMMA 0.10/0.25, LAM_L 0.05, B1 0.02 per $1000 room, B2 0.5 per unit share, ALPHA 0.4 latent, issuer base lines, additive linear index with homogeneous coefficients. Post-spell line cuts (Antoniou et al.) are not simulated, so (e)'s controls are pre-spell by construction.
