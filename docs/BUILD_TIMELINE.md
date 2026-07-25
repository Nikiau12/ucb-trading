# UCB Trading — Build Timeline

UCB Trading evolved from a compact Telegram signal bot into a multilingual
decision-support product with a Telegram Mini App, personalized risk planning,
subscriptions, and persistent state.

This timeline is reconstructed from 96 commits between March 17 and June 28,
2026. Two Git author identities — `Nikita Kotrelev` and `Nukita` — belong to the
same builder.

## Timeline

### 1. March 17 — First working bot

**Goal:** prove that a Telegram interface could turn MEXC market data into a
useful analysis response.

The first commit shipped a deployable bot, exchange client, SMC analyzer,
spike scanner, notifier, Docker configuration, and Railway setup in 454 lines
of new code.

The same day added:

- Telegram commands and multi-user support;
- natural-language and full-analysis commands;
- support for any MEXC coin and trade scenarios;
- background scans with anti-spam caches;
- context scoring to suppress noisy setups;
- a five-timeframe fusion engine;
- the first automated engine tests.

**Evidence:** `8466c14`, `63947a4`, `3e6d295`, `2b19834`, `e3ef0a4`.

**What changed:** the product moved from a notification script to a structured
analysis system.

### 2. March 18–24 — Autotrading expansion

**Goal:** explore whether the signal engine could also drive automated
execution.

The scope expanded to include:

- a separate BingX autotrader;
- hedge-mode and leverage handling;
- concurrent Railway services;
- smart-grid and partial take-profit experiments;
- position limits and daily-loss controls;
- volume, timeframe, and BTC-correlation filters;
- a microservice-style split between `core`, `mexc`, and `bingx`.

This period also contains many corrective commits: leverage arguments, position
side, active-order counting, timeframe restrictions, import fixes, and safer
risk limits.

**Evidence:** `138f2e9`, `9295d2a`, `641619a`, `48acb92`, `768a9f7`,
`1569876`, `8e2adb4`, `7b59ae5`.

**What changed:** execution risk and operational complexity became first-class
product constraints rather than implementation details.

### 3. March 25–April 20 — Strategy narrowing

**Goal:** reduce noisy behavior and make the trading logic more selective.

The product introduced a liquidity-sweep / false-breakout scanner using 4h and
1d levels with 15m triggers. It then narrowed automated execution to
BTC, ETH, and SOL and eventually simplified the autotrader to one primary
strategy.

Follow-up work added:

- stricter position guards and cooldowns;
- adjusted stop-loss and deviation rules;
- a flag-pattern scanner;
- clearer MEXC alert prices.

**Evidence:** `1b1711a`, `d797ebd`, `f00e6c8`, `c1fac11`, `692521c`,
`568a631`.

**What changed:** the project moved away from maximizing the number of setups
and toward explicit filtering and safer failure modes.

### 4. May 14–June 8 — Return to the signal product

**Goal:** make the user-facing MEXC experience more useful and deployable.

This phase added a BTC-led trade policy, restored the production bot, improved
signal formatting, introduced coin explanations and listing monitoring, and
created the first trial-access flow.

**Evidence:** `61a5c32`, `f90651c`, `49d13fc`, `f76f22a`.

**What changed:** the main product value shifted back from automated execution
to market analysis and decision support.

### 5. June 21 — Product architecture reset

**Goal:** turn the accumulated experiments into one coherent product.

A new `trading/` module introduced:

- deterministic indicators, levels, and market-structure analysis;
- MEXC snapshot retrieval with cache fallback;
- trade-plan generation;
- scanner orchestration and Telegram rendering;
- state management.

The same day added:

- five-language onboarding and help;
- per-user deposit and settings;
- personalized position sizing;
- priority scans for major pairs;
- a unified aiogram bot;
- clearer onboarding requirements and command flow.

Obsolete BingX execution code, experimental scripts, and the duplicate bot were
then removed in a single cleanup of 1,840 lines.

**Evidence:** `9955f0e`, `bcc743c`, `82790bc`, `75842bb`, `c0b854e`,
`6b6d7a9`, `19db3f7`.

**What changed:** UCB Trading became a focused decision-support product instead
of a collection of trading experiments.

### 6. June 22 — Mini App and monetization

**Goal:** add a visual workspace and complete the product journey.

This phase shipped:

- monthly USDT TRC20 subscription verification;
- a multilingual Telegram Mini App;
- PostgreSQL-backed profiles, signals, and access state;
- settings-driven signal recalculation;
- professional charts and signal detail pages;
- USDT-only input rules and a trial paywall;
- a redesigned trading interface;
- persistent signal deduplication across deployments.

Several same-day fixes addressed onboarding buttons, event-loop startup, HTTPS
normalization, and payment/signal UX.

**Evidence:** `32e6ae7`, `bb9d4c8`, `faa87b0`, `06e1729`, `fcf22f2`,
`0c1443c`.

**What changed:** the bot gained a complete path from onboarding to analysis,
history, access control, and payment.

### 7. June 28 — UX hardening

**Goal:** reduce confusion in the trial and subscription experience.

The final production commits simplified the USDT subscription flow, improved
message and signal readability, clarified the paywall, and fixed trial scanning.

**Evidence:** `ad68b8f`, `151dc7e`, `3d438d6`.

**What changed:** the focus moved from adding capability to making existing
capability understandable.

### 8. July 25 — Portfolio and quality pass

**Goal:** turn the working product into verifiable professional evidence.

The portfolio pass added:

- a product-focused README and documented environment template;
- an annotated screenshot walkthrough;
- 40 automated tests;
- GitHub Actions for compilation and tests;
- a reproducible 20-market live evaluation;
- a public case-study page;
- this build timeline and product postmortem.

The evaluation processed 20/20 live MEXC markets. Ten generated plans passed
all invariants, while ten markets were safely skipped by filters. All 36 risk
profiles and 65 symbol-normalization cases passed.

## Build pattern

The history is not a straight line:

```text
signal bot
  → richer analysis
  → autotrading experiments
  → stricter risk controls
  → strategy narrowing
  → decision-support pivot
  → Mini App and monetization
  → testing and evaluation
```

That progression is the main product story: rapid AI-assisted implementation
created breadth, while testing, deletion, and scope correction created a more
coherent product.
