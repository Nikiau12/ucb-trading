# Native 4H/1D trade diagnosis — 2026-08-07

## Scope and protocol

This report diagnoses the rejected BTC and SOL profiles using closed 4H candles
and completed 1D context only. Production, Railway and paper trading were not
changed. The final test window was not opened.

The already observed 2025-06-01 to 2025-12-24 confirmation window is used only
to explain why the old profiles were rejected. It is contaminated for future
model selection and cannot be presented as proof for any replacement profile.

The reproducible command is:

```bash
./venv/bin/python -m evaluation.diagnose_higher_timeframe_trades \
  --output /tmp/ucb-4h-diagnostics.json
```

## BTC diagnosis

The rejected profile is `btc_4h_pullback_long`.

- Selection: 39 trades, +13.89%, PF 2.07, 17 TP2 exits, 11 direct stops and
  11 stops after TP1.
- Confirmation: four trades, -1.80%, PF 0.45. Three trades hit a direct stop;
  only one reached TP2.
- Selection winners and losers had virtually the same mean ADX (29.37 versus
  29.34) and ATR percentage (1.47% versus 1.48%). Raising confidence, ADX or a
  generic volatility threshold is therefore not supported by this sample.
- Selection winners occurred in a somewhat younger daily trend (42.7 completed
  daily bars versus 54.9) and closed farther through the 4H EMA20 reclaim
  (0.48 ATR versus 0.33 ATR). These are weak signals, not proven edges.

Three deliberately small BTC variants were pre-registered from those training
observations: maximum daily-trend age, minimum 4H reclaim strength, and their
combination. Their selection-only aggregates were:

| Candidate | Trades | Positive windows | Return | PF | Max DD |
|---|---:|---:|---:|---:|---:|
| age <= 60 daily bars | 24 | 3/4 | +12.35% | 2.54 | 4.35% |
| reclaim >= 0.20 ATR | 28 | 3/4 | +11.01% | 2.18 | 4.47% |
| both filters | 17 | 3/4 | +9.90% | 2.74 | 3.27% |

None is approved. The combined filter has fewer than 20 trades and all three
still have one negative training window.

## SOL diagnosis

The rejected profile is `sol_4h_pullback_both`.

- Selection: 38 trades, +11.85%, PF 1.78, 17 TP2 exits, 14 direct stops and
  seven stops after TP1.
- Confirmation: seven trades, -1.02%, PF 0.75. The long side produced two TP2,
  one direct stop and one stop after TP1. All three short entries hit a direct
  stop. This is diagnostic evidence only and was not used as a new validation.
- In selection, winners had lower mean 4H volatility (2.87% versus 3.23%), a
  younger daily trend (22.1 versus 32.7 bars), less daily extension (1.44 versus
  1.69 ATR), and a stronger 4H close through EMA20 (0.38 versus 0.28 ATR).

The pre-registered SOL candidates separate long and short behaviour and include
one conservative combined rule:

| Candidate | Trades | Positive windows | Return | PF | Max DD |
|---|---:|---:|---:|---:|---:|
| long quality | 15 | 4/4 | +8.22% | 2.84 | 1.10% |
| short early/low-volatility | 9 | 3/4 | +8.17% | 7.90 | 1.17% |
| conservative both sides | 25 | 3/4 | +11.31% | 2.46 | 1.08% |

The high PF of the short-only variant is not reliable with nine trades. The
long-only variant is consistent across four windows but also misses the
20-trade sample gate. The combined variant has enough trades and materially
lower drawdown than the old selection, but remains exploratory.

## Decision

No profile is profitable in a statistically confirmed, deployable sense yet.
The old BTC/SOL profiles remain rejected and paper trading stays paused. The
next legitimate evidence must come from new forward 4H data after 2026-08-07.
Until enough trades accumulate, the candidates can be shadow-scored without
orders; results must include fees, slippage and the existing stop-first policy.

ETH remains unchanged: its structural range candidate stays frozen, and the
minimum sample gate is not reduced after seeing the 19-trade result.
