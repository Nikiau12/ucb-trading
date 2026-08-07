# UCB strategy backtest

The backtest runs the production `trade_plan.make_plan` function in a
walk-forward loop over 1-hour OHLCV data.

It is intentionally conservative:

- a signal sees only candles closed at its decision time;
- 4-hour and daily candles are included only after the complete period closes;
- an order can fill no earlier than the next 1-hour candle;
- if a candle touches both stop and take-profit, stop is applied first;
- a take-profit is never awarded on the entry candle without tick data;
- commission and adverse slippage are charged on every fill;
- only one position can be open for a symbol at a time.

Expected CSV columns are `timestamp,open,high,low,close,volume`. Timestamps can
be Unix seconds, Unix milliseconds or ISO-8601 values.

```bash
python -m trading.backtest btc_usdt_1h.csv \
  --symbol BTC_USDT \
  --deposit 1000 \
  --risk 1 \
  --fee-bps 4 \
  --slippage-bps 2 \
  --output backtest-result.json
```

The report states its execution assumptions and includes net return, maximum
drawdown, profit factor, average R, total fees and every simulated trade. A
positive result is historical evidence, not a promise of future profitability.
