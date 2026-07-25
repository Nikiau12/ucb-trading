# UCB Trading — Evaluation Report

Run: `20260725T131549Z`  
Generated: 2026-07-25T13:15:49.325926+00:00  
Market source: live MEXC Futures API

## Scope

This evaluation measures product correctness, robustness, and latency. It does
not measure or claim signal profitability.

## Results

| Metric | Result |
|---|---:|
| Symbols completed | 20/20 |
| Plans generated | 10 |
| Safe skips | 10 |
| Valid generated plans | 10/10 (100.0%) |
| Fresh live data | 100.0% |
| Full analysis latency, median | 3176.68 ms |
| Full analysis latency, p90 | 3298.35 ms |
| Local plan computation, median | 2.55 ms |
| Symbol normalization | 100.0% |
| Risk matrix | 100.0% |

## Test set

| Symbol | Output | Confidence | Total ms | Cache | Invariants |
|---|---|---:|---:|---|---|
| BTC_USDT | skip | 0.0 | 3113.93 | no | pass |
| ETH_USDT | skip | 0.0 | 3100.46 | no | pass |
| SOL_USDT | skip | 0.0 | 3108.15 | no | pass |
| XRP_USDT | plan | 1.0 | 3105.75 | no | pass |
| DOGE_USDT | plan | 0.75 | 3110.59 | no | pass |
| ADA_USDT | skip | 0.0 | 3272.36 | no | pass |
| BNB_USDT | skip | 0.0 | 3278.58 | no | pass |
| LTC_USDT | plan | 0.3571 | 3193.6 | no | pass |
| LINK_USDT | skip | 0.0 | 3243.89 | no | pass |
| AVAX_USDT | plan | 0.9 | 3262.49 | no | pass |
| DOT_USDT | plan | 0.75 | 3246.9 | no | pass |
| TRX_USDT | plan | 0.5 | 3152.64 | no | pass |
| BCH_USDT | plan | 0.75 | 3306.6 | no | pass |
| SUI_USDT | skip | 0.0 | 3159.76 | no | pass |
| PEPE_USDT | skip | 0.0 | 2948.05 | no | pass |
| HYPE_USDT | plan | 0.55 | 3120.99 | no | pass |
| TAO_USDT | plan | 0.75 | 3314.87 | no | pass |
| ZEC_USDT | skip | 0.0 | 3297.43 | no | pass |
| NEAR_USDT | skip | 0.0 | 3266.85 | no | pass |
| APT_USDT | plan | 0.9 | 3146.23 | no | pass |

## Correctness checks

A generated plan passes only when:

- entry, stop, targets, quantity, risk amount, and required margin are finite
  and positive;
- price ordering is valid for the selected long or short direction;
- quantity × stop distance equals the configured risk amount;
- required margin matches quantity × entry ÷ leverage;
- TP1 and TP2 allocations sum to 100%.

The risk matrix covers 36 combinations: three deposits, three risk percentages,
and four leverage values. Symbol normalization covers 65 valid and invalid
input formats.

## Reproduce

```bash
python -m pip install -r requirements-dev.txt
python evaluation/run_evaluation.py
```

Raw machine-readable output: `docs/evaluation-results.json`.

## Limitations

- Results are a point-in-time measurement and live-market latency will vary.
- A safe `skip` is accepted when filters reject a setup; it is not counted as a
  generated plan.
- The evaluation does not backtest returns or estimate trading profitability.
- Telegram production delivery latency is outside this local evaluation.
