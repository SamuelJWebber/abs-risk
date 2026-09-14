"""Shared econometrics helpers: OLS with Newey-West HAC standard errors, by hand.

No statsmodels, no sklearn. numpy lstsq only.
"""
import numpy as np


def ols_nw(y, X, lags=6, names=None):
    """OLS of y on X (X must already include a constant column if wanted).

    Newey-West / Bartlett HAC covariance with `lags` lags, small-sample factor n/(n-k).
    Returns dict with beta, se, t, p (normal), n, k, r2, resid, cov.
    """
    y = np.asarray(y, dtype=float).ravel()
    X = np.asarray(X, dtype=float)
    if X.ndim == 1:
        X = X[:, None]
    ok = np.isfinite(y) & np.isfinite(X).all(axis=1)
    y, X = y[ok], X[ok]
    n, k = X.shape
    XtX = X.T @ X
    XtX_inv = np.linalg.pinv(XtX)
    beta = XtX_inv @ (X.T @ y)
    resid = y - X @ beta
    u = X * resid[:, None]
    S = u.T @ u
    for L in range(1, lags + 1):
        if L >= n:
            break
        w = 1.0 - L / (lags + 1.0)
        G = u[L:].T @ u[:-L]
        S += w * (G + G.T)
    dof_adj = n / max(n - k, 1)
    cov = dof_adj * (XtX_inv @ S @ XtX_inv)
    se = np.sqrt(np.clip(np.diag(cov), 0, None))
    t = beta / np.where(se > 0, se, np.nan)
    p = 2.0 * (1.0 - _ncdf(np.abs(t)))
    ybar = y.mean()
    sst = float(((y - ybar) ** 2).sum())
    r2 = 1.0 - float((resid ** 2).sum()) / sst if sst > 0 else np.nan
    return {
        "names": names if names is not None else [f"x{i}" for i in range(k)],
        "beta": beta, "se": se, "t": t, "p": p, "n": n, "k": k,
        "r2": r2, "resid": resid, "cov": cov,
        "sigma_resid": float(np.sqrt((resid ** 2).sum() / max(n - k, 1))),
    }


def _ncdf(x):
    """Standard normal CDF via erf (math.erf vectorised)."""
    from math import erf
    xa = np.atleast_1d(np.asarray(x, dtype=float))
    out = np.array([0.5 * (1.0 + erf(v / np.sqrt(2.0))) for v in xa])
    return out if np.ndim(x) else float(out[0])


def ncdf(x):
    return _ncdf(x)


def slope_row(res, label, xi=1):
    """Pull the slope (column xi) out of an ols_nw result as a flat dict."""
    return {
        "spec": label,
        "n": res["n"],
        "beta": float(res["beta"][xi]),
        "se": float(res["se"][xi]),
        "z": float(res["t"][xi]),
        "p": float(res["p"][xi]),
        "ci_lo": float(res["beta"][xi] - 1.959964 * res["se"][xi]),
        "ci_hi": float(res["beta"][xi] + 1.959964 * res["se"][xi]),
        "r2": float(res["r2"]),
        "sigma_resid": res["sigma_resid"],
        "const": float(res["beta"][0]),
    }


def const_design(x):
    x = np.asarray(x, dtype=float)
    return np.column_stack([np.ones(len(x)), x])


# 80% power, 5% two-sided: (z_{0.975} + z_{0.80})
MDE_MULT = 1.959964 + 0.8416212
