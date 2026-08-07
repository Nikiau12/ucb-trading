# BTC and ETH regime-strategy research — 2026-08-07

## Scope and safeguards

The experiment used 35,000 fixed MEXC one-hour candles ending at
2026-08-07 11:00 UTC. New builders are research-only and do not change the
production bot. Every signal uses closed candles. The candidate libraries were
declared in source before each run and contain eight setups per asset.

Selection was divided into four chronological windows. A candidate needed at
least three positive windows, at least 20 trades and a positive mean return.
Any winner would then need to remain profitable with 8 bps commission plus 4
bps slippage per fill and with entry delayed by one additional candle. The
independent confirmation, validation and final test stayed closed when these
gates failed.

## Iteration 1

BTC tested direct breakout-close and EMA continuation entries. All eight
profiles failed selection. The least-negative profile was long EMA
continuation: 212 trades, one positive window out of four and -2.82% mean
window return. Direct 20-hour long breakout averaged -8.71%.

ETH tested Bollinger-band touch/reclaim entries in low-ADX regimes. All eight
profiles failed selection. The least-negative profile used 20-hour, two-standard-
deviation bands: 319 trades, one positive window and -3.21% mean return. Its
last window returned +21.87%, but the three earlier windows were negative. The
effect is therefore regime-dependent rather than stable.

## Iteration 2

Iteration 2 was designed only from selection diagnostics. BTC stopped chasing
the trigger close and waited for a retest of the broken level or one-hour EMA.
This reduced trading and drawdown, but no profile reached three positive
windows. The least-negative profile was long EMA retest: 101 trades, one
positive window, -1.75% mean return and 7.43% maximum window drawdown.

ETH required a prior close outside the band, a flatter EMA, lower ATR
percentile and no volume shock. This combination was too selective: profiles
produced between zero and five total trades. The sample is unusable and no
threshold was relaxed after viewing the result.

## Decision

No BTC or ETH profile is selected. Stress tests, confirmation, validation and
the final test remain closed. There is no production or Railway change.

The next BTC hypothesis should change the payoff and cancellation logic rather
than add more indicator thresholds. The next ETH hypothesis needs a structural
range definition with a larger sample, for example repeated support/resistance
tests and a time-bounded reclaim, while retaining a pre-registered parameter
library.

Historical performance does not guarantee future results.
