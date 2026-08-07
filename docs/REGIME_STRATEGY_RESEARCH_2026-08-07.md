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

## Decision after iterations 1-2

No BTC or ETH profile was selected. Confirmation, validation and the final test
remained closed. There was no production or Railway change.

The next BTC hypothesis should change the payoff and cancellation logic rather
than add more indicator thresholds. The next ETH hypothesis needs a structural
range definition with a larger sample, for example repeated support/resistance
tests and a time-bounded reclaim, while retaining a pre-registered parameter
library.

## Iteration 3

BTC iteration 3 changed execution and payoff rules. Pending entries expired
after four or six hours, stale setups could be cancelled using the previous
closed candle, positions used 48/72-hour time stops, TP2 was extended to 2.5R
or 3R, and selected variants moved the remaining stop to breakeven after TP1.
The best profile was the 40-hour breakout retest with 3R TP2 and breakeven. It
produced 92 trades and +0.75% mean window return, but only two of four windows
were positive. BTC therefore failed selection, although this was a measurable
improvement over the best iteration-2 mean return of -1.75%.

ETH iteration 3 replaced Bollinger Bands with structural ranges. Support and
resistance required repeated tests separated by at least six hours, and the
entry required a reclaim within a pre-declared two- or four-hour window. The
120-hour, three-touch, four-hour-reclaim profile passed rolling selection:
216 trades, three positive windows and +8.14% mean window return. It also
remained positive under higher friction (+5.28%) and delayed entry (+37.00%)
over the combined selection history.

The frozen ETH winner then failed the independent confirmation period:

| Scenario | Trades | Return | Profit factor | Max drawdown |
|---|---:|---:|---:|---:|
| Production baseline | 16 | -0.68% | 0.91 | 3.84% |
| Structural candidate | 43 | -8.85% | 0.72 | 14.67% |
| Higher friction | 43 | -12.38% | 0.63 | 17.31% |
| One-extra-hour delay | 28 | -11.39% | 0.48 | 14.43% |

The pattern changed sharply outside selection. ETH validation and the final
test remained closed. Iteration 3 therefore produces no production change.

## Current decision

No BTC or ETH profile is approved. BTC needs a new trigger or timeframe rather
than another exit-parameter variation. ETH structural ranges are materially
more promising than Bollinger-only ranges, but the regime shift on independent
confirmation prevents deployment. Production and Railway remain unchanged.

Historical performance does not guarantee future results.
