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

## Strict strategy research

Use the separate research runner to prevent parameter selection on the final
test period:

```bash
python -m evaluation.run_walk_forward \
  --symbols BTC_USDT ETH_USDT SOL_USDT \
  --candidate-set setup_v4 \
  --candles 25000 \
  --workers 4 \
  --data-end 2026-08-07T11:00:00Z \
  --output walk-forward-report.json
```

The runner evaluates the declared candidates on training first. It opens
validation only when a candidate passes the training gate, and opens the final
test only after the validation gate passes. Historical candles are cached under
`/tmp/ucb-walk-forward-data` by default and are not committed to the repository.

## Separate profile per symbol

To select and independently confirm one profile for each major contract:

```bash
python -m evaluation.run_symbol_optimization \
  --symbols BTC_USDT ETH_USDT SOL_USDT \
  --candles 25000 \
  --workers 3 \
  --data-end 2026-08-07T11:00:00Z \
  --output symbol-profile-report.json
```

The optimizer uses the same bounded profile library for every symbol. It chooses
one winner per symbol on the selection window and does not fall back to a second
profile if that winner fails confirmation. Validation and test remain protected
by separate chronological gates.
