# UCB Trading — Product Postmortem

## Summary

UCB Trading is a Telegram bot and Mini App that turns live MEXC Futures data
into structured market-analysis plans with personalized position sizing,
risk controls, history, access management, and subscription verification.

I designed and built the product end to end using AI-assisted development:
product flow, Telegram UX, deterministic market logic, backend APIs, data
persistence, Mini App interface, payment verification, deployment iterations,
testing, and evaluation.

The most important outcome was not the number of features. It was learning to
reduce a broad trading-automation experiment into a clearer decision-support
product with explicit calculations and inspectable limitations.

## Initial hypothesis

The initial hypothesis was that a Telegram-native tool could reduce the work
between identifying a market setup and producing an actionable risk plan.

A user should not need to:

1. collect market context in one tool;
2. calculate entry, stop, and targets elsewhere;
3. manually convert a risk percentage into position size;
4. monitor a separate interface for new setups.

Telegram was selected because identity, notifications, commands, and
distribution already exist in the same environment.

## What shipped

The final public product includes:

- Telegram onboarding in five languages;
- live MEXC market data;
- deterministic multi-timeframe analysis;
- entry, stop, TP1/TP2, position-size, and margin calculations;
- deposit, risk, leverage, and margin settings;
- scanner and automatic alerts;
- a responsive Telegram Mini App with charts and signal history;
- PostgreSQL state and persistent deduplication;
- free-trial and subscription access;
- confirmed USDT TRC20 payment verification.

The project history contains 96 commits over three months.

## What worked

### Telegram was a strong distribution and UX choice

The bot made it possible to ship onboarding, commands, alerts, localization,
and access control without building a separate authentication system. The Mini
App then provided the visual space that chat messages could not.

### Personal risk settings created clearer product value

Separating market analysis from user-specific exposure made the output more
useful. The same market setup can produce a different quantity and required
margin for different deposits, risk percentages, and leverage values.

### Deterministic logic made evaluation possible

The current engine exposes its calculations instead of returning an opaque
generated answer. That made it possible to verify price ordering, risk
exposure, target allocation, position size, and required margin.

### Iteration included deletion, not only addition

The project briefly expanded into BingX autotrading, multiple execution
strategies, and many operational controls. Removing the obsolete execution
surface and consolidating the product around MEXC analysis was one of the most
important architectural decisions.

### The quality pass produced real evidence

The final evaluation processed 20/20 predefined live markets using fresh MEXC
data:

- 10 plans generated and 10 safe skips;
- 10/10 generated plans passed all mathematical invariants;
- 36/36 personalized risk scenarios passed;
- 65/65 symbol-normalization cases passed;
- 3.18 s median and 3.30 s p90 full-analysis latency;
- 2.55 ms median local plan-computation time.

These results measure software correctness and responsiveness, not trading
profitability.

## What did not work

### Scope expanded too quickly

The history moved from a signal bot to autotrading, grids, sniper strategies,
false breakouts, multiple timeframes, and several exchange-specific behaviors
within days.

This increased the number of interactions that could fail: leverage modes,
position sides, pending orders, loss limits, timeframe conflicts, imports, and
deployment processes. The corrective commits in this period are evidence that
the product surface grew faster than its verification system.

### Testing arrived too late

Some tests existed during the early multi-timeframe work, but a stable,
maintained suite was not preserved through the later architecture reset.
Production behavior was therefore validated mainly through fixes after
integration.

The portfolio pass restored a focused 40-test suite and CI, but this should have
been part of the main development loop earlier.

### Product and deployment observability are incomplete

The live `/start` onboarding and Mini App worked, but `/plan` and `/scan` did
not produce a visible response while the user was still in deposit onboarding.
The root cause was an FSM handler that consumed every text message—including
commands—before command routing. The local fix excludes slash commands from
the deposit-input handler and adds regression coverage. Production verification
still requires deployment of the patched version.

The repository does not yet provide structured request IDs, command latency
logging, alerting, or an operational dashboard.

### Product metrics were not designed in from the start

The project can now report technical correctness and latency, but it cannot
honestly report user retention, trial conversion, paid subscriptions, or
decision usefulness because those events were not instrumented as a product
analytics system.

### Trading performance remains unverified

The evaluation deliberately avoids claiming profitability. A responsible
performance claim would require a versioned strategy, historical data controls,
fees, slippage, look-ahead protection, and a time-bounded backtesting
methodology.

## Pivotal decisions

### From execution to decision support

Removing the BingX autotrading surface reduced operational and financial risk.
The product became easier to explain: it analyzes markets and calculates risk;
it does not place orders on behalf of the user.

### From chat-only to bot plus Mini App

Telegram messages are effective for alerts but weak for history, charts, and
settings. The Mini App split created a clearer division:

- bot for onboarding, commands, and notifications;
- Mini App for visual analysis, history, settings, and access.

### From fixed assumptions to per-user risk

Hardcoded deposits and margins were replaced with user settings. This turned a
generic signal into a personalized calculation while keeping the underlying
market analysis shared.

### From in-memory behavior to persistent state

Signal history, profiles, subscriptions, and alert deduplication moved into
PostgreSQL so the product could survive restarts and deployments.

## How AI-assisted development was used

AI assistance accelerated scaffolding, debugging, refactoring, UI iteration,
test generation, and documentation. It was especially useful when moving
between Telegram UX, Python services, exchange data, payment verification, and
front-end work.

The project also exposed the main risk of AI-assisted speed: it is easy to add
scope faster than the product can be validated. The corrective practices were
to narrow the system, remove obsolete code, make the engine deterministic, and
add explicit tests and evaluation.

I remained responsible for the product hypothesis, scope decisions, system
integration, verification criteria, and the decision to ship or remove each
capability.

## What I would do differently

1. Define one product metric and one primary user journey before adding a
   second strategy or exchange.
2. Start with the decision-support product and postpone all order execution.
3. Add CI and invariant tests with the first risk-calculation function.
4. Introduce structured command and external-API logging before production.
5. Separate experimental strategies from the deployable product through
   feature flags or isolated branches.
6. Instrument onboarding, plan requests, safe skips, Mini App opens, trial use,
   and subscription conversion from the first release.
7. Create a versioned backtesting specification before discussing signal
   performance.

## Next steps

The immediate engineering priority is to diagnose the production `/plan` and
`/scan` path with deployment logs and structured tracing.

After that:

- add command-level latency and error metrics;
- expand tests around alert deduplication and database behavior;
- instrument product usage and trial conversion;
- run the live evaluation on a schedule;
- define a separate, reproducible backtesting project if performance analysis
  becomes necessary.

## Interview takeaway

The strongest story is not “I generated a trading bot with AI.” It is:

> I used AI-assisted development to move quickly across product design,
> backend, market data, Telegram UX, and a Mini App. The first version became
> too broad, so I removed the automated-execution surface, consolidated the
> product around deterministic decision support, and added tests and a
> reproducible 20-market evaluation. That taught me that speed is valuable only
> when scope, observability, and verification grow with it.
