# Production monitoring

## Availability

`GET /health` returns `{"ok": true}` when the process is up. When `DATABASE_URL`
is set, it also runs `SELECT 1` and returns HTTP 503 `{"ok": false}` if Postgres
is unavailable. The response does not include scanner status.

The worker still writes the plan-scanner heartbeat to `runtime_health`. That
table is not exposed on `/health`.

Recommended external alert:

- request `/health` every minute;
- alert immediately on non-200 responses.

## Metrics

`GET /metrics` requires `METRICS_TOKEN`. Send it as `Authorization: Bearer <token>`
or `X-Metrics-Token`. The endpoint rejects the request when the variable is unset.

It exposes low-cardinality Prometheus text metrics:

- `ucb_app_uptime_seconds`;
- `ucb_http_requests_total` by normalized route and status;
- `ucb_http_request_duration_seconds_sum` by normalized route and status.

Paths containing symbols are normalized to `/api/market/:symbol`, preventing a
separate time series for every coin. The endpoint contains no Telegram IDs,
symbols, tokens, wallet addresses or other user data.

## Worker heartbeat

The worker stores scanner status in the shared `runtime_health` Postgres table.
Successful scans reset `consecutive_failures`; failed scans increment it while
preserving the last successful timestamp. Query that table directly when you
need scanner detail; `/health` stays a process and database check only.
