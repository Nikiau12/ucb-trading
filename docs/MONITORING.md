# Production monitoring

## Availability

`GET /health` checks the Mini App process and performs a real `SELECT 1` against
Postgres in production. It returns HTTP 503 when the database is unavailable.
The payload also includes the latest `plan_scanner` heartbeat, scan duration,
processed/failed/stale symbol counts, alerts sent and consecutive failures.

Recommended external alert:

- request `/health` every minute;
- alert immediately on non-200 responses;
- alert when `scanner.fresh` is false, `scanner.status` is `error`, or
  `scanner.details.failed` is greater than zero.

## Metrics

`GET /metrics` exposes low-cardinality Prometheus text metrics:

- `ucb_app_uptime_seconds`;
- `ucb_http_requests_total` by normalized route and status;
- `ucb_http_request_duration_seconds_sum` by normalized route and status.

Paths containing symbols are normalized to `/api/market/:symbol`, preventing a
separate time series for every coin. The endpoint contains no Telegram IDs,
symbols, tokens, wallet addresses or other user data.

## Worker heartbeat

The worker stores scanner status in the shared `runtime_health` Postgres table.
Successful scans reset `consecutive_failures`; failed scans increment it while
preserving the last successful timestamp. This lets the Mini App report a dead
or degraded scanner even while its own HTTP process remains available.
