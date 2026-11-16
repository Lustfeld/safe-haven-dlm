"""Shared inputs for the safe-haven notebooks.

Every notebook regresses the same excess returns on the same five regressors, and
notebooks 04-06 fit the same dynamic linear model. Defining that construction once
keeps the notebooks from drifting apart. Paths are anchored to the repository root,
so the notebooks do not depend on the working directory.
"""

import ast
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
FIG_DIR = ROOT / "figures"
PAPER_DIR = ROOT / "paper"

CURRENCIES = ["CHF", "EUR", "GBP", "JPY"]
RATE = {"CHF": "CHF_3M", "EUR": "EUR_3M", "GBP": "GBP_3M", "JPY": "JPY_3M"}
REGRESSORS = ["SP500", "UST10Y", "fxvol", "TED", "VIX"]
TERMS = ["const"] + REGRESSORS
# Scale of the state innovations: W = LAMBDA * diag(Var(theta_OLS)). Each coefficient
# moves by sqrt(LAMBDA) OLS standard errors per day, so over n days the random walk
# has a prior standard deviation of sqrt(n * LAMBDA) standard errors - about 2.4 for
# n = 5790. Larger => more time variation. Fixed, not estimated (see notebook 05).
LAMBDA = 1e-3


def load_levels():
    """Daily levels as committed in data/levels.csv."""
    return pd.read_csv(DATA_DIR / "levels.csv", index_col="date", parse_dates=True)


class ModelData:
    """Excess returns and the five regressors, for all four currencies.

    Returns and volatility are built on a gap-free FX panel (days with any missing
    exchange rate are dropped first), matching the thesis's handling of incomplete
    days. The fx-volatility regressor is the 30-day rolling standard deviation of
    log returns, averaged over the *other* three currencies (leave-one-out).
    """

    def __init__(self, levels):
        self.levels = levels
        fx = levels[CURRENCIES].dropna()
        self.appreciation = np.log(fx).diff()

        self.sp500_d = np.log(levels["SP500"]).diff().rename("SP500")
        self.vix_d = np.log(levels["VIX"]).diff().rename("VIX")
        self.ust10y_d = levels["UST10Y"].diff().rename("UST10Y")
        # unlike the four _d series, TED is a level (percentage points) put on a
        # daily basis, not a daily change
        self.ted = ((levels["US_3M"] - levels["TBILL_3M"]) / 360).rename("TED")

        # interbank rates are % p.a.; /100/360 gives the daily decimal carry
        interest_diff = pd.DataFrame(
            {cur: (levels[RATE[cur]] - levels["US_3M"]) / 100 / 360
             for cur in CURRENCIES})
        self.excess = self.appreciation + interest_diff

        realized = np.log(self.appreciation.rolling(30).std())
        fx_vol = pd.DataFrame(
            {cur: realized[[o for o in CURRENCIES if o != cur]].mean(axis=1)
             for cur in CURRENCIES})
        self.fx_vol = fx_vol - fx_vol.mean()   # centre log-vol so it does not offset the intercept

    def model_frame(self, cur, ted=None):
        """Regression frame for one currency; `ted` replaces the TED series."""
        return pd.concat([
            self.excess[cur].rename("excess"),
            self.sp500_d, self.ust10y_d, self.fx_vol[cur].rename("fxvol"),
            (self.ted if ted is None else ted).rename("TED"), self.vix_d,
        ], axis=1).dropna()


def load_data():
    """Build the model inputs from the committed daily levels."""
    return ModelData(load_levels())


class DLM(sm.tsa.statespace.MLEModel):
    """Dynamic regression DLM: Y_t = F_t theta_t + v_t, theta_t = G theta_{t-1} + w_t."""

    def __init__(self, Y, F, W, m0, C0, burn=0):
        p = F.shape[1]
        super().__init__(endog=Y, k_states=p, k_posdef=p, loglikelihood_burn=burn)
        self["design"] = F.T.reshape(1, p, len(Y))   # F_t = (1, x_t')
        self["transition"] = np.eye(p)               # G_t = I_p  (random walk)
        self["selection"] = np.eye(p)
        self["state_cov"] = W                        # W
        self.initialize_known(m0, C0)                # theta_0 ~ N(m0, C0)

    @property
    def param_names(self):
        return ["V"]                                 # observation variance

    @property
    def start_params(self):
        return [np.var(self.endog)]

    # V is of order 1e-5 for daily returns in decimals. Optimising over log V keeps
    # the problem well scaled, so BFGS converges without warnings.
    def transform_params(self, u):
        return np.exp(u)

    def untransform_params(self, p):
        return np.log(p)

    def update(self, params, **kwargs):
        params = super().update(params, **kwargs)
        self["obs_cov", 0, 0] = params[0]            # V


def dlm_inputs(df, lam=LAMBDA):
    """Design matrix, full-sample OLS fit, and the calibrated (C0, W)."""
    Y = df["excess"].values
    F = np.column_stack([np.ones(len(df))] + [df[r].values for r in REGRESSORS])
    ols = sm.OLS(Y, F).fit()
    C0 = ols.mse_resid * np.linalg.inv(F.T @ F)      # OLS coefficient covariance
    W = lam * np.diag(np.diag(C0))                   # calibrated evolution covariance
    return Y, F, ols, C0, W


def dlm_fit(df, lam=LAMBDA):
    """Fit the DLM on one regression frame; returns (results, full-sample OLS fit)."""
    Y, F, ols, C0, W = dlm_inputs(df, lam)
    return DLM(Y, F, W, ols.params, C0).fit(disp=False), ols


def joint_deviation(res, ols_params):
    """Mahalanobis distance of the smoothed theta_t from the constant OLS estimate,
    D_t = (theta_t - OLS)' C_t^{-1} (theta_t - OLS), C_t the smoothed state covariance."""
    theta, cov = res.smoothed_state, res.smoothed_state_cov      # (p, n), (p, p, n)
    d = theta - np.asarray(ols_params)[:, None]
    return np.array([d[:, t] @ np.linalg.solve(cov[:, :, t], d[:, t])
                     for t in range(theta.shape[1])])


def dlm_profile(df, lams, burn=250):
    """Log-likelihood of the DLM as a function of lambda, V re-estimated each time.

    The headline fit starts the filter at the full-sample OLS estimate, which uses
    the data twice. For a likelihood comparison that is not acceptable, so here the
    initial state is vague (10^4 times the OLS variances) and the first `burn`
    observations are left out of the likelihood while the filter settles.
    """
    Y, F, ols, C0, _ = dlm_inputs(df)
    scale = np.diag(np.diag(C0))
    out = {}
    for lam in lams:
        res = DLM(Y, F, lam * scale, ols.params, 1e4 * scale, burn=burn).fit(disp=False)
        out[lam] = res.llf
    return pd.Series(out, name="loglik")


def prefix_gram(y, X):
    """Prefix sums of X'X, X'y and y'y, so a segment's OLS RSS costs O(1)."""
    n, k = X.shape
    Sxx = np.zeros((n + 1, k, k)); Sxy = np.zeros((n + 1, k)); Syy = np.zeros(n + 1)
    Sxx[1:] = np.cumsum(np.einsum("ti,tj->tij", X, X), axis=0)
    Sxy[1:] = np.cumsum(X * y[:, None], axis=0)
    Syy[1:] = np.cumsum(y * y)
    return Sxx, Sxy, Syy


def seg_rss(gram, s, e):
    """OLS RSS on the segment [s, e); s or e may be arrays."""
    Sxx, Sxy, Syy = gram
    k = Sxy.shape[1]
    b = Sxy[e] - Sxy[s]
    beta = np.linalg.solve(Sxx[e] - Sxx[s] + 1e-12 * np.eye(k), b[..., None])[..., 0]
    return Syy[e] - Syy[s] - (beta * b).sum(axis=-1)


def bai_perron(df, max_breaks=5, trim=0.15):
    """Exact least-squares break search (Bai-Perron) with BIC selection.
    Returns segment end indices (last == n) and the BIC path over m."""
    y = df["excess"].values
    X = np.column_stack([np.ones(len(df)), df[REGRESSORS].values])
    n, k = len(df), X.shape[1]
    min_size = int(trim * n)
    gram = prefix_gram(y, X)
    rss = np.full((n + 1, n + 1), np.inf)
    for s in range(n - min_size + 1):
        e = np.arange(s + min_size, n + 1)
        rss[s, e] = seg_rss(gram, s, e)
    cost, cut = [rss[0].copy()], []
    for _ in range(max_breaks):
        tot = cost[-1][:, None] + rss            # last segment starts at t
        cut.append(tot.argmin(axis=0))
        cost.append(tot.min(axis=0))
    # global BIC penalty (m+1)*k*log(n); slightly stronger than the
    # per-segment sum in eq. (12) of the thesis
    bics = [n * np.log(cost[m][n] / n) + (m + 1) * k * np.log(n)
            for m in range(max_breaks + 1)]
    m = int(np.argmin(bics))
    bkps, e = [n], n
    for i in range(m, 0, -1):
        e = int(cut[i - 1][e]); bkps.append(e)
    return sorted(bkps), bics


def break_dates(cur=None):
    """Bai-Perron break dates from data/break_dates.csv (empty before notebook 03)."""
    path = DATA_DIR / "break_dates.csv"
    if not path.exists():
        return [] if cur else {}
    raw = pd.read_csv(path, index_col=0)["break_dates"]
    parsed = {c: [pd.Timestamp(d) for d in ast.literal_eval(raw[c])] for c in raw.index}
    return parsed.get(cur, []) if cur else parsed
