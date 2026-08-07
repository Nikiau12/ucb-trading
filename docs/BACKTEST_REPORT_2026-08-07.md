# UCB historical backtest — 2026-08-07

## Scope

- MEXC perpetual-contract 1-hour candles;
- BTC_USDT, ETH_USDT and SOL_USDT;
- 9,500 candles per symbol, from 2025-07-07 16:00 UTC through
  2026-08-07 11:00 UTC;
- 1,000 USDT independent starting balance per symbol;
- 1% risk per trade and 10x requested leverage;
- 4 bps commission and 2 bps adverse slippage on every fill;
- production `trade_plan.make_plan` strategy and current MEXC contract rules.

The engine used only closed candles, activated orders on the next candle,
disallowed overlapping positions and assumed that a stop executes before a
take-profit when OHLC data cannot determine the intrabar order.

## Results

| Symbol | Trades | Win rate | Net return | Max drawdown | Profit factor | Fees |
|---|---:|---:|---:|---:|---:|---:|
| BTC_USDT | 42 | 35.71% | -4.90% | 9.14% | 0.81 | 18.61 USDT |
| ETH_USDT | 28 | 42.86% | +3.24% | 3.98% | 1.28 | 7.63 USDT |
| SOL_USDT | 30 | 36.67% | -1.02% | 6.12% | 0.93 | 6.86 USDT |
| **Aggregate** | **100** | **38.00%** | **-0.90%** on 3,000 USDT | — | — | **33.11 USDT** |

Aggregate net PnL was **-26.86 USDT**. The strategy therefore does not yet have
enough evidence for a general profitability claim. ETH was profitable in this
sample, while BTC and SOL were not.

## Interpretation

This is a baseline, not a parameter-optimization result. Changing thresholds to
maximize this same period would overfit the strategy. The next research step
should split older data into training and validation windows, define candidate
changes before examining the holdout, and confirm them on a later untouched
period. Paper trading should follow before any real-money automation.

Historical performance does not guarantee future results.
