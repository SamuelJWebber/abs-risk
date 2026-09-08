"""Regression discontinuity at lender score cutoffs (analysis-plan §2, B3).

Three steps, each a function:
  find_cutoffs   where does the lender's own pricing or sizing jump in score? Local-linear fits on each side
                 of every candidate score; a cutoff is a jump larger than k times the local residual spread.
  density_test   McCrary-style test for bunching of the running variable at the cutoff (manipulation or
                 selection). Uses rddensity when installed, else a binned log-density difference.
  rd_estimate    local-linear RD of an outcome on score at the cutoff with a triangular kernel. Uses rdrobust
                 (MSE-optimal bandwidth, bias-corrected robust CI) when installed; otherwise a manual local-
                 linear fit over a grid of bandwidths so the reader sees sensitivity.

Nothing here is published unless the first stage (APR or amount jump) exists and the density test passes.
Known pool floors (CarMax 650, Toyota 620) and securitization cliffs (Exeter and AmeriCredit 640) are excluded
by the caller; they are selection, not pricing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _local_linear(x: np.ndarray, y: np.ndarray, c: float, h: float, side: str) -> tuple[float, float, int]:
    """Triangular-kernel local-linear fit on one side of c; returns (fitted value at c, residual sd, n)."""
    if side == "left":
        m = (x < c) & (x >= c - h)
    else:
        m = (x >= c) & (x < c + h)
    xs, ys = x[m], y[m]
    if len(xs) < 5:
        return np.nan, np.nan, int(len(xs))
    w = 1 - np.abs(xs - c) / h
    A = np.column_stack([np.ones_like(xs), xs - c])
    W = np.sqrt(w)
    beta, *_ = np.linalg.lstsq(A * W[:, None], ys * W, rcond=None)
    resid = ys - A @ beta
    return float(beta[0]), float(np.sqrt(np.average(resid**2, weights=w))), int(len(xs))


def find_cutoffs(df: pd.DataFrame, running: str = "score", var: str = "orig_apr", lo: int = 500, hi: int = 800,
                 step: int = 5, h: float = 25.0, k: float = 3.0, min_n: int = 200,
                 min_jump: float | None = None) -> pd.DataFrame:
    """Candidate cutoffs where `var` jumps at a score threshold. Returns every candidate with its statistics.

    A candidate is flagged when |jump| > k * se and, if `min_jump` is given, |jump| > min_jump as well (so a
    statistically sharp but economically trivial step is not a cutoff). The grid is aligned to multiples of `step`.
    """
    x = df[running].to_numpy(dtype=float)
    y = df[var].to_numpy(dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    rows = []
    lo = int(np.ceil(lo / step) * step)
    for c in range(lo, hi + 1, step):
        fl, sl, nl = _local_linear(x, y, c, h, "left")
        fr, sr, nr = _local_linear(x, y, c, h, "right")
        if nl < min_n or nr < min_n or not np.isfinite(fl) or not np.isfinite(fr):
            continue
        jump = fr - fl
        se = np.sqrt(sl**2 / nl + sr**2 / nr)
        flag = bool(abs(jump) > k * se) and (min_jump is None or abs(jump) > min_jump)
        rows.append({"cutoff": c, "left": fl, "right": fr, "jump": jump, "se": se, "t": jump / se if se > 0 else np.nan,
                     "n_left": nl, "n_right": nr, "flag": flag})
    return pd.DataFrame(rows)


def density_test(score: pd.Series | np.ndarray, c: float, h: float = 25.0, bin_width: float = 5.0) -> dict:
    """Bunching test at c. rddensity if available; else compare binned densities just left and right of c."""
    x = np.asarray(score, dtype=float)
    x = x[np.isfinite(x)]
    try:
        import rddensity  # type: ignore

        r = rddensity.rddensity(x, c=c)
        test = r.test  # Series: t_asy, t_jk, p_asy, p_jk; the asymptotic pair is NaN when scores have mass points
        t = test.get("t_asy")
        p = test.get("p_asy")
        which = "asymptotic"
        if t is None or not np.isfinite(t):
            t, p, which = test.get("t_jk"), test.get("p_jk"), "jackknife"
        if t is not None and np.isfinite(t):
            return {"method": f"rddensity-{which}", "t": float(t), "p": float(p), "n": int(len(x)),
                    "mass_points": bool(getattr(r, "massPoints_flag", False))}
    except Exception:  # noqa: BLE001
        pass
    # one histogram over the whole window so every bin is half-open [a, b) and the cutoff value sits on the
    # right side only (np.histogram closes only the very last bin, which is at c + h)
    nb = int(round(h / bin_width))
    edges = c + bin_width * np.arange(-nb, nb + 2)          # one spare bin at the end absorbs the closed edge
    counts, _ = np.histogram(x, bins=edges)
    counts = counts[:-1]
    edges = edges[:-1]
    cl, cr = counts[:nb], counts[nb:]
    edges_l, edges_r = edges[: nb + 1], edges[nb:]
    # log-linear trend on each side, extrapolated to c, fitted by weighted least squares with Poisson weights:
    # var(log count) ~ 1/count, so the coefficient covariance is (A' W A)^-1 and the intercept SE follows.
    def edge_fit(counts, centers):
        if len(counts) < 3 or counts.sum() == 0:
            return np.nan, np.nan
        cnt = np.maximum(counts.astype(float), 0.5)
        lc = np.log(cnt)
        A = np.column_stack([np.ones_like(centers), centers - c])
        W = np.diag(cnt)
        cov = np.linalg.inv(A.T @ W @ A)
        beta = cov @ A.T @ W @ lc
        return float(beta[0]), float(np.sqrt(cov[0, 0]))
    lc_l, se_l = edge_fit(cl, (edges_l[:-1] + edges_l[1:]) / 2)
    lc_r, se_r = edge_fit(cr, (edges_r[:-1] + edges_r[1:]) / 2)
    diff = lc_r - lc_l
    se = np.sqrt(np.nan_to_num(se_l) ** 2 + np.nan_to_num(se_r) ** 2)
    t = diff / se if se > 0 else np.nan
    from math import erf, sqrt

    p = 2 * (1 - 0.5 * (1 + erf(abs(t) / sqrt(2)))) if np.isfinite(t) else np.nan
    return {"method": "binned-log-density", "log_density_jump": float(diff), "t": float(t), "p": float(p), "n": int(len(x))}


def rd_estimate(df: pd.DataFrame, outcome: str, c: float, running: str = "score",
                bandwidths: tuple[float, ...] = (10, 15, 20, 25, 30, 40)) -> pd.DataFrame:
    """RD effect of crossing c on `outcome`. rdrobust row first when available, then manual bandwidth grid."""
    x = df[running].to_numpy(dtype=float)
    y = df[outcome].to_numpy(dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    rows = []
    try:
        from rdrobust import rdrobust  # type: ignore

        r = rdrobust(y, x, c=c)
        est = r.coef.iloc[0, 0]
        rows.append({"method": "rdrobust", "bandwidth": float(r.bws.iloc[0, 0]), "estimate": float(est),
                     "se": float(r.se.iloc[0, 0]), "ci_lo": float(r.ci.iloc[2, 0]), "ci_hi": float(r.ci.iloc[2, 1]),
                     "p_robust": float(r.pv.iloc[2, 0]), "n_left": int(r.N_h[0]), "n_right": int(r.N_h[1])})
    except Exception:  # noqa: BLE001
        pass
    for h in bandwidths:
        fl, sl, nl = _local_linear(x, y, c, h, "left")
        fr, sr, nr = _local_linear(x, y, c, h, "right")
        if nl < 5 or nr < 5:
            continue
        est = fr - fl
        se = np.sqrt(sl**2 / nl + sr**2 / nr)
        rows.append({"method": "local-linear", "bandwidth": float(h), "estimate": float(est), "se": float(se),
                     "ci_lo": float(est - 1.96 * se), "ci_hi": float(est + 1.96 * se), "p_robust": np.nan,
                     "n_left": nl, "n_right": nr})
    return pd.DataFrame(rows)


def outcome_by_horizon(loans: pd.DataFrame, months: int) -> pd.Series:
    """1 if the loan charged off within `months` of first observation, 0 if observed that long without, NaN if not yet."""
    obs = loans["months_observed"].to_numpy()
    co = (loans["exit_type"] == "chargeoff").to_numpy()
    y = np.where(co & (obs <= months), 1.0, np.where(obs >= months, 0.0, np.nan))
    return pd.Series(y, index=loans.index)
