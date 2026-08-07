# Native 4H + 1D strategy report — 2026-08-07

## Correction

This report replaces the earlier hourly signal research. The intended strategy
uses daily context and four-hour setups for BTC, ETH and SOL. Hourly MEXC rows
are used only to construct complete 4H OHLCV candles. The strategy builder
receives an empty hourly series and cannot calculate an hourly signal.

The backtest makes a decision only after a 4H candle closes. An order becomes
eligible on the next 4H candle, all exits are evaluated on 4H OHLC, and an
ambiguous candle applies the stop first. The daily series contains only fully
closed daily candles.

## Protocol

Six profiles per asset were registered before the run. Selection used four
chronological windows from 2022-12-08 through 2025-06-01. A profile required
three positive windows, at least 20 trades and a positive mean return. A winner
then had to remain profitable with 8 bps commission plus 4 bps slippage per
fill and with entry delayed by one additional 4H candle.

Confirmation covered 2025-06-01 through 2025-12-24. Validation and the final
test stayed closed unless all earlier gates passed.

## BTC

The selected training profile was long-only: aligned 1D/4H uptrend, 4H ADX at
least 20 and a closed 4H reclaim of EMA20. It produced 39 selection trades,
three positive windows and +3.35% mean window return. Selection stress passed:

- higher friction: 39 trades, +10.76%, PF 1.74, 4.88% drawdown;
- one extra 4H entry-delay bar: 29 trades, +5.96%, PF 1.47, 3.05% drawdown.

The frozen profile failed confirmation: four trades, -1.80%, PF 0.45. The
sample was also below the five-trade gate. BTC validation and test stayed
closed.

## ETH

The strongest 30-candle structural range profile was positive in all four
windows and averaged +2.47%, but produced only 19 trades. The pre-registered
minimum was 20, so no ETH profile was selected. The threshold was not reduced
after observing the result. ETH confirmation, validation and test stayed
closed.

## SOL

The selected training profile allowed long and short EMA20 pullbacks when the
1D and 4H trends aligned and 4H ADX was at least 25. It produced 38 trades,
three positive windows and +2.85% mean window return. Selection stress passed:

- higher friction: 38 trades, +10.50%, PF 1.66, 3.03% drawdown;
- one extra 4H entry-delay bar: 31 trades, +10.34%, PF 1.88, 2.02% drawdown.

The frozen profile failed confirmation: seven trades, -1.02%, PF 0.75. Higher
friction returned -1.32%, and the delayed-entry case returned -2.54%. SOL
validation and test stayed closed.

## Decision

No profile is approved for production. The corrected timeframe materially
improved training behavior, especially for BTC and SOL, but neither survived
independent confirmation. ETH missed the sample gate by one trade and cannot
be promoted by lowering the rule after the fact.

Production, real orders and Railway remain unchanged. The SOL 4H paper harness
is implemented but its recurring automation remains paused.

Historical performance does not guarantee future results.
