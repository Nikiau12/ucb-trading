# Per-symbol profile research — 2026-08-07

## Objective

Find a separate evidence-based trading profile for BTC_USDT, ETH_USDT and
SOL_USDT without selecting on validation or the final test. Every symbol was
offered the same finite profile library; only the selected profile could differ.
The objective was `return_pct - 0.5 * max_drawdown_pct`, not raw historical
profit alone.

All simulations used 1-hour MEXC perpetual candles, 1% risk, 10x requested
leverage, 4 bps commission and 2 bps adverse slippage per fill.

## Locked windows and gates

| Window | Start (UTC) | End (UTC) | Purpose |
|---|---|---|---|
| Selection | 2023-11-29 19:00 | 2025-06-01 11:00 | Choose exactly one profile per symbol |
| Confirmation | 2025-06-01 11:00 | 2025-12-24 11:00 | Confirm only the winner; no fallback |
| Validation | 2025-12-24 11:00 | 2026-04-16 11:00 | Open only after confirmation passes |
| Test | 2026-04-16 11:00 | 2026-08-07 11:00 | Untouched |

Selection required at least 15 trades, positive return and profit factor above
1. Confirmation and validation each required at least 5 trades, positive return,
profit factor above 1, no more drawdown than baseline and a return above baseline.

## Results

### BTC_USDT

The selected profile was trend-only with closed 1h candle and directional RSI
confirmation.

| Window | Trades | Return | Max drawdown | Profit factor | Decision |
|---|---:|---:|---:|---:|---|
| Selection | 18 | +6.62% | 2.05% | 1.86 | Selected |
| Confirmation | 11 | -3.32% | 3.32% | 0.55 | Failed |

The baseline lost 11.05% in the confirmation window, so the candidate reduced
the loss substantially but was still not profitable. Validation was not opened.

### ETH_USDT

No profile passed the selection gate. The best raw result was range-only at
+6.89% with a 3.29 profit factor, but it produced only 10 trades instead of the
required 15. All profiles with adequate sample size were unprofitable. No ETH
profile was selected and validation was not opened.

### SOL_USDT

The selected profile was trend-only with a closed 1h candle confirmation.

| Window | Trades | Return | Max drawdown | Profit factor | Decision |
|---|---:|---:|---:|---:|---|
| Selection | 26 | +6.96% | 2.02% | 1.62 | Selected |
| Confirmation | 12 | +1.08% | 1.99% | 1.18 | Passed |
| Validation | 3 | +0.66% | 1.03% | 1.63 | Failed |

The SOL candidate stayed profitable on validation, but produced fewer than five
trades and underperformed the +1.03% baseline return. It therefore failed the
pre-registered validation gate.

## Decision

No per-symbol profile is approved for production. BTC was not stable across the
two training subperiods, ETH had no adequately sampled profitable profile, and
SOL was promising but did not beat baseline on sufficient validation evidence.
The final test remained untouched and Railway must not be updated with these
profiles.

The next ETH research step must change its range entry and invalidation model,
not lower the minimum trade count. BTC needs a more stable confirmation rule.
SOL should be observed on additional forward/paper-trading data without changing
its frozen profile.

Historical performance does not guarantee future results.

## Follow-up: ETH range model

The ETH training history was expanded backwards to 2022-10-09 while keeping all
later boundaries locked. Eight range profiles were declared before evaluation.
The selected profile trades both long and short range setups without an added
candle or RSI filter.

| Window | Trades | Return | Max drawdown | Profit factor | Decision |
|---|---:|---:|---:|---:|---|
| Selection | 20 | +7.78% | 3.55% | 2.03 | Selected |
| Confirmation | 3 | +0.06% | 1.00% | 1.03 | Failed: sample below 5 |

The rule remained marginally profitable but did not produce enough independent
confirmation trades. Validation and test remained closed. Tight reversal and
RSI filters reduced both sample size and performance; they are rejected.

## Follow-up: BTC rolling stability

BTC profiles were compared across four consecutive selection windows rather
than one aggregate period. The selected profile was long-only, trend-only, with
closed 1h and directional RSI confirmation. It was positive in all four windows,
with 23 trades, +2.43% mean return and +0.30% in its worst window.

On the separate confirmation period it produced only three trades, -0.75%
return and a 0.64 profit factor. It therefore failed before validation. This
shows that the profile was historically stable until mid-2025 but did not remain
stable afterward.

## Follow-up: SOL forward paper test

The frozen SOL trend + closed 1h confirmation profile now runs in a stateful
paper-trading harness. It processes closed 1h candles, never sends an exchange
order, and records virtual pending entries, partial TP1 exits, TP2, stops,
commission, slippage and account equity. Initial virtual equity is 1,000 USDT.

The first live paper evaluation rejected the current setup, so there is no
pending order or open virtual position. This is expected: the profile should
remain selective and must not be loosened during forward observation.
