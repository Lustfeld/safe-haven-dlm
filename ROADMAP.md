# Roadmap - planned and parked work

The published core (README) asks one question: gradual drift vs. discrete breaks
in safe-haven betas, via a fixed-variance dynamic linear model. Everything below
either extends that core or was deliberately left open. Nothing here is required to
read or reproduce the core result.

Each item notes the idea and where it would fit, so the project can be picked up
later without re-reading everything.

## 1. Stochastic volatility in the observation equation
**Status: planned; the most direct extension.** The core DLM assumes a constant
observation variance, yet the innovation diagnostics (notebook 05) show volatility
clustering and fat tails that a constant variance cannot capture. Letting the
observation variance vary over time (stochastic volatility), estimated in a Bayesian
frame such as a joint TVP-SV model via MCMC, is the most direct way to relax that
assumption, and would be the first thing a continuation builds.

## 2. Estimating lambda instead of fixing it
**Status: checked in the core, not adopted.** Notebook 05 profiles the likelihood
over lambda. It does not peak at zero time variation; it peaks at a lambda between
0.1 and 0.3 for all four currencies, far above the fixed 1e-3. I do not take that
estimate at face value, because with a constant observation variance the
coefficients can absorb volatility clustering and the drift may be overstated (Sims
2001; Cogley and Sargent 2005). The credible way to estimate lambda is jointly with a
time-varying variance, which is item 1. Two further checks belong here: one lambda
per coefficient instead of a common one (some coefficients, such as the constant,
may well be driven to zero, the pile-up case of Stock and Watson 1998), and a
prior on lambda in place of a point value.

## 3. Genuine jumps rather than pure drift
**Status: conceptual, not implemented.** The random-walk state equation can only
produce gradual drift, yet events like the 2015 SNB de-peg are discontinuous. This
is the core tension the project raises but does not resolve. Candidate models:
a state equation with an added jump component, Markov-switching / regime-switching
coefficients, or a mixture-innovation state space. A middle way is to let the
betas depend on an observed state such as FX volatility, as Christiansen, Ranaldo
and Söderlind (2011) do for carry-trade strategies with a smooth transition
regression. This is the most promising direction for a thesis-length continuation.

## 4. Bayesian in-depth treatment
**Status: planned.** A fully Bayesian DLM (priors on the state variances, a posterior
over the whole coefficient path) would be the natural anchor for an in-depth study of
time-series methods, building on the stochastic-volatility direction above.

## 5. Out-of-sample / predictive evaluation
**Status: out of scope by design.** The whole project is in-sample structural
analysis. A predictive extension (recursive filtering, one-step forecasts, formal
break vs. drift model comparison) would be a separate study.

## 6. Synchronous prices
**Status: open.** The free FX data are noon rates, the regressors are closing
values, and notebook 02 shows that one lag of the regressors carries about as much
of the equity response as the same day. The core keeps the thesis specification.
A clean version would either use exchange rates sampled at the US close or carry
the lagged regressors through the break search and the DLM.

## References

Christiansen, C., Ranaldo, A. & Söderlind, P. (2011). The Time-Varying Systematic Risk
of Carry Trade Strategies. *Journal of Financial and Quantitative Analysis*, 46(4),
1107-1125.

Cogley, T. & Sargent, T. J. (2005). Drifts and Volatilities: Monetary Policies and
Outcomes in the Post WWII US. *Review of Economic Dynamics*, 8(2), 262-302.

Sims, C. A. (2001). Comment on Sargent and Cogley's "Evolving Post-World War II U.S.
Inflation Dynamics". *NBER Macroeconomics Annual 2001*, 16, 373-379.

Stock, J. H. & Watson, M. W. (1998). Median Unbiased Estimation of Coefficient Variance
in a Time-Varying Parameter Model. *Journal of the American Statistical Association*,
93(441), 349-358.
