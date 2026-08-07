# UCB train/validation/test research — 2026-08-07

## Protocol fixed before evaluation

- MEXC perpetual 1-hour candles for BTC_USDT, ETH_USDT and SOL_USDT;
- 15,000 candles per symbol, with a 1,440-hour indicator warm-up;
- chronological 60% training / 20% validation / 20% untouched test split;
- 1,000 USDT independent balance per symbol, 1% risk and 10x requested leverage;
- 4 bps commission and 2 bps adverse slippage per fill;
- closed candles only, next-candle entry eligibility, no overlapping positions,
  and stop-first handling for ambiguous OHLC candles.

Candidate changes were deliberately limited to universal filters rather than
symbol-specific tuning:

1. current 0.60 minimum confidence (baseline);
2. 0.65 minimum confidence;
3. 0.70 minimum confidence;
4. 0.60 confidence plus agreement between signal direction and both 4h and 1d trends.

A candidate had to produce at least 40 training trades, positive aggregate net
PnL and positive PnL on at least two of the three symbols. Only then could it be
selected by `return_pct - 0.5 * max_drawdown_pct` and evaluated on validation.

## Windows

| Window | Start (UTC) | End (UTC) | Status |
|---|---|---|---|
| Training | 2025-01-19 11:00 | 2025-12-24 11:00 | Evaluated |
| Validation | 2025-12-24 11:00 | 2026-04-16 11:00 | Not opened |
| Test | 2026-04-16 11:00 | 2026-08-07 11:00 | Untouched |

## Training results

| Candidate | Trades | Win rate | Net return | Max drawdown | Profit factor | Positive symbols |
|---|---:|---:|---:|---:|---:|---:|
| Baseline 0.60 | 96 | 29.17% | -7.40% | 8.08% | 0.62 | 0/3 |
| Confidence 0.65 | 93 | 29.03% | -7.45% | 8.12% | 0.61 | 0/3 |
| Confidence 0.70 | 91 | 28.57% | -7.66% | 8.34% | 0.60 | 0/3 |
| 4h + 1d aligned 0.60 | 93 | 29.03% | -7.46% | 8.14% | 0.61 | 0/3 |

The baseline lost 221.98 USDT on the 3,000 USDT aggregate starting balance.
By symbol it returned -13.50% on BTC, -3.28% on ETH and -5.42% on SOL.

## Decision

No candidate passed the pre-registered training gate. Validation was therefore
not inspected and the test interval remains untouched. None of these filters
should be deployed. The result also shows that the confidence score currently
does not rank historical outcomes well enough: increasing its threshold removed
few trades and slightly worsened performance.

The next research iteration should use training data only to redesign the setup
logic itself (market regime, entry confirmation and invalidation), freeze that
new rule, and then evaluate it once on validation. The untouched test period
must remain closed until a candidate passes validation.

Historical performance does not guarantee future results.
