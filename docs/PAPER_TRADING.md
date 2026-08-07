# SOL paper trading

`evaluation.sol_paper_trade` runs the frozen SOL profile without exchange
credentials and without sending real orders.

Manual run:

```bash
./venv/bin/python -m evaluation.sol_paper_trade \
  --state /Users/nikitakotrelev/.codex/state/ucb-sol-paper/state.json
```

Each invocation processes newly closed 4-hour candles since the previous run.
The one-day context and four-hour setup are both built only from completed
candles. Hourly rows are used solely to construct complete 4-hour candles and
are never exposed to the signal builder.
State is written atomically and contains:

- virtual equity, starting at 1,000 USDT;
- a pending limit entry with an 8-hour expiry;
- at most one open paper position;
- 50% TP1 and remaining TP2 execution;
- pessimistic stop-first handling for ambiguous OHLC candles;
- 4 bps commission and 2 bps adverse slippage per fill;
- a permanent virtual trade journal.

The frozen research profile is `sol_4h_pullback_both`: aligned 1D/4H trend with
a closed 4H EMA20 reclaim or rejection. It failed independent historical
confirmation, so the recurring automation is paused and must not be resumed
without explicit approval. Changing the profile during forward observation
invalidates the paper-test sample.

An old empty hourly state can migrate to state version 2. Migration discards
the hourly rejection counter and starts from the current closed 4H boundary.
Migration refuses any state containing an order, position or trade.

This harness is observation-only. It must never import credentials, call order
creation methods, update Railway or message real users.
