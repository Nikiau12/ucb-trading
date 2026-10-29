# BingX 4H/1D forward validation — 2026-10-29

## Decision

No BTC, ETH or SOL profile is approved for production.  Every profile is below
the pre-registered minimum of 20 forward trades.  Railway, the production bot,
paper orders and real orders remain unchanged.

The forward run covers 2026-08-07 08:00 UTC through 2026-10-29 12:00 UTC.  It
uses native BingX USDT-M 4H candles, completed 1D context, entry no earlier than
the next 4H candle, a stop-first rule for ambiguous OHLC candles, the live
BingX taker fee of 5 bps per fill and 2 bps simulated slippage per fill.

## BTC

| Frozen profile | Trades | Return | PF | Average R | Max DD | Status |
|---|---:|---:|---:|---:|---:|---|
| Age <= 60 daily bars | 3 | -0.68% | 0.69 | -0.22 | 2.16% | Insufficient sample |
| Reclaim >= 0.20 ATR | 2 | +1.38% | 11.68 | +0.70 | 0.13% | Insufficient sample |
| Both filters | 1 | +1.51% | n/a | +1.52 | 0.00% | Insufficient sample |

The positive BTC variants share the same winning trade from 2026-08-26.  They
are not independent evidence and cannot justify promotion.

## ETH

| Frozen profile | Trades | Return | PF | Average R | Max DD | Status |
|---|---:|---:|---:|---:|---:|---|
| Range 30, long | 2 | +3.24% | 3.75 | +1.67 | 1.18% | Insufficient sample |
| Range 30, short | 1 | -1.22% | 0.00 | -1.22 | 1.22% | Insufficient sample |
| Range 30, both sides | 4 | -1.27% | 0.62 | -0.30 | 3.39% | Insufficient sample |
| Range 30, 3 touches | 0 | 0.00% | n/a | 0.00 | 0.00% | Insufficient sample |
| Range 60, both sides | 4 | +5.34% | 4.61 | +1.35 | 1.08% | Insufficient sample |
| Range 60, 3 touches | 2 | +1.28% | 2.20 | +0.67 | 1.07% | Insufficient sample |

The best-looking ETH result contains only four trades and depends heavily on
two winners.  It is promising enough to keep shadow-scoring, but not enough to
claim a profitable strategy.

## SOL

All three frozen SOL profiles produced zero filled forward trades.  The filters
are currently too selective for this market window, so there is no new SOL
performance evidence yet.

## Reproducibility

Run:

```bash
python -m evaluation.run_bingx_forward_validation \
  --end 2026-10-29T12:00:00Z \
  --output /tmp/ucb-bingx-forward-2026-10-29.json
```

The downloader rejects gaps and incomplete candles and caches raw normalized
data outside the repository.  Source hashes for the 1,455 candles per asset:

- BTC: `dcf82825becc5c9c0eed851a24d70889156a0ca715b2ce89032534dcc66c3ca5`
- ETH: `48b0e2f2af54d695a9a390f4370f1b94a069f8c59b4b7b3ba5ff1163a273e647`
- SOL: `f7961ce2775f0f8fdb4fd3a3607cc767e39359bb9f7652d77ab1062dd953a3db`

Historical results do not guarantee future performance.
