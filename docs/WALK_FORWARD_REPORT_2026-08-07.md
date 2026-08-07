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

## Iteration 2 — regime and trend strength

The second iteration was defined after inspecting training outcomes only. It
disabled range setups and tested ADX 22/25/30 plus an RSI momentum requirement.
Validation and test were still unopened.

| Candidate | Trades | Net return | Max drawdown | Profit factor | Positive symbols |
|---|---:|---:|---:|---:|---:|
| Trend, ADX >= 22 | 79 | -3.28% | 3.74% | 0.78 | 0/3 |
| Trend, ADX >= 25 | 64 | -4.83% | 5.81% | 0.62 | 0/3 |
| Trend, ADX >= 30 | 46 | -2.67% | 3.40% | 0.69 | 1/3 |
| Trend, ADX >= 25, RSI momentum | 43 | -1.76% | 2.43% | 0.78 | 1/3 |

Removing ranges materially reduced losses, but none of these candidates passed
the training gate. A larger ADX did not monotonically improve outcomes.

## Iteration 3 — entry distance

Older candles were added to training without moving the already locked
validation and test boundaries. The data end was pinned to 2026-08-07 11:00 UTC
for reproducibility. Training now began on 2023-11-29 19:00 UTC.

The closest candidate required a trend setup, an entry 0.10-0.50 ATR from the
current price, and directional RSI. It produced 47 trades, -0.47% return, 3.08%
maximum drawdown and 0.94 profit factor. BTC returned +6.05% and SOL +1.65%, but
ETH returned -9.13%. It therefore failed the universal training gate.

## Iteration 4 — closed 1h confirmation

The strategy was then changed conceptually from a blind 4h EMA limit to a
closed-candle confirmation. A long requires a bullish closed 1h candle above
EMA20 1h; a short requires a bearish closed candle below EMA20 1h. The selected
candidate also requires RSI to agree with trade direction and accepts trend
regimes only.

### Training

| Candidate | Trades | Win rate | Net return | Max drawdown | Profit factor | Positive symbols |
|---|---:|---:|---:|---:|---:|---:|
| Baseline | 207 | 35.75% | -2.55% | 6.88% | 0.93 | 1/3 |
| 1h confirmation | 99 | 40.40% | +0.23% | 4.23% | 1.01 | 2/3 |
| **1h confirmation + RSI** | **97** | **43.30%** | **+2.47%** | **3.60%** | **1.15** | **2/3** |

The 1h confirmation plus RSI candidate passed the training gate and was frozen
before validation.

### Validation

| Version | Trades | Win rate | Net return | Max drawdown | Profit factor | Positive symbols |
|---|---:|---:|---:|---:|---:|---:|
| Baseline | 34 | 44.12% | +0.10% | 3.21% | 1.02 | 2/3 |
| Frozen candidate | 13 | 53.85% | +1.20% | 0.69% | 1.69 | 3/3 |

The candidate passed every quality condition but produced only 13 validation
trades, below the pre-registered minimum of 20. Validation is therefore marked
as failed. The final test window remains untouched and the candidate must not be
deployed yet. The next defensible step is cross-sectional validation of the
unchanged candidate on additional liquid contracts, without tuning its rules or
lowering the sample-size gate.

Historical performance does not guarantee future results.
