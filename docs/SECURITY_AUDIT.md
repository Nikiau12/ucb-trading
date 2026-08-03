# Security audit — 2026-08-03

## Scope

The review covered the Telegram bot, Mini App API and browser code, PostgreSQL
persistence, TRC20 payment verification, Python dependencies, GitHub Actions,
repository settings, and accidental secret exposure in the current Git history.

## Fixed in this branch

| Severity | Finding | Resolution |
| --- | --- | --- |
| Critical | Mini App silently entered demo mode when the bot token was absent | Demo access now requires explicit `MINI_APP_DEMO_MODE=true`, and production fails closed |
| Critical | An old public wallet transaction could be submitted as a new subscription payment | TRC20 claims now expire after 72 hours and transaction hashes are uniquely reserved in PostgreSQL |
| High | Signal fields were interpolated into HTML without escaping | Dynamic signal markup is escaped and side/confidence/id values are normalized |
| High | Runtime was Python 3.9 with vulnerable/outdated dependency pins | Runtime moved to Python 3.12 and direct dependencies were updated |
| Medium | Telegram Web App authorization was replayable for 24 hours | Authorization lifetime defaults to one hour and rejects future or oversized payloads |
| Medium | Market and payment endpoints had no application-level throttling | Per-user sliding-window limits and a short market-data cache were added |
| Medium | No browser security headers | CSP, no-sniff, no-referrer, permissions policy, API no-store, and HSTS on HTTPS were added |
| Medium | Configurable URL fetches allowed unexpected schemes/hosts | CoinGecko and MEXC fetches now enforce HTTPS host allowlists |
| Medium | No continuous SAST/SCA process | Bandit, pip-audit, CodeQL, and Dependabot configuration were added |

No committed private key or live bot token pattern was found in the current
repository history. The local `.env` remains ignored by Git.

## Accepted temporary exceptions

The CI dependency audit temporarily ignores advisories that have no compatible
release in the current package index:

- Starlette form/host/path advisories: this application does not parse multipart
  forms, does not use attacker-controlled URL reconstruction, and now emits a
  restrictive CSP. Upgrade FastAPI/Starlette when a compatible fixed release is
  available.
- Requests zip extraction and python-dotenv mutation helpers: neither affected
  helper is called by this project. Upgrade when fixed releases are available.
- Aiogram 3.22 currently requires aiohttp `<3.13`. The listed aiohttp advisories
  predominantly affect server request parsing, static serving, cookie-jar
  deserialization, or APIs this bot does not use; UCB uses aiohttp only as a
  Telegram/exchange client. Remove these exceptions as soon as Aiogram supports
  a fixed aiohttp release.

## Follow-up hardening

1. Replace the legacy JSONB `access_state` document with normalized PostgreSQL
   rows and transactions for fully atomic trial consumption across multiple bot
   workers.
2. Give each payment intent a unique exact USDT amount or a payment-provider
   invoice so a recent transfer cannot be claimed by the wrong user.
3. Vendor the remaining Telegram bridge script if Telegram provides a versioned
   distribution; the pinned chart and icon scripts now use verified SRI hashes.
4. Enable required status checks in repository settings,
   then protect `main` after the new workflows pass on a pull request.
