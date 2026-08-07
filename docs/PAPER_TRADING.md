# SOL paper trading

`evaluation.sol_paper_trade` runs the frozen SOL profile without exchange
credentials and without sending real orders.

Manual run:

```bash
./venv/bin/python -m evaluation.sol_paper_trade \
  --state /Users/nikitakotrelev/.codex/state/ucb-sol-paper/state.json
```

Each invocation processes newly closed 1-hour candles since the previous run.
State is written atomically and contains:

- virtual equity, starting at 1,000 USDT;
- a pending limit entry with a 12-hour expiry;
- at most one open paper position;
- 50% TP1 and remaining TP2 execution;
- pessimistic stop-first handling for ambiguous OHLC candles;
- 4 bps commission and 2 bps adverse slippage per fill;
- a permanent virtual trade journal.

The frozen profile accepts SOL trend setups with a closed 1-hour candle
confirmation and minimum confidence 0.60. Changing that profile during forward
observation invalidates the paper-test sample.

This harness is observation-only. It must never import credentials, call order
creation methods, update Railway or message real users.
