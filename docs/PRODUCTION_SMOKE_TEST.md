# UCB Trading — Production Smoke Test

Run this checklist after deploying the command-routing patch.

## Why this deployment matters

During deposit onboarding, the FSM amount handler previously matched every text
message. Because it was registered before the command handlers, `/start`,
`/help`, `/plan`, `/scan`, and `/settings` could be consumed as invalid deposit
input instead of reaching their commands.

The patch limits the deposit handler to ordinary non-command text and adds
structured command logs.

## Before deployment

- Confirm the deployment uses the repository's `main` branch.
- Confirm the worker command is `python bot_mexc.py`.
- Confirm `TELEGRAM_BOT_TOKEN`, `DATABASE_URL`, and `MINI_APP_URL` are present.
- Set `LOG_LEVEL=INFO`.
- Run `pytest -q`; all 40 tests must pass.

## Smoke-test sequence

Use a Telegram account that can restart onboarding:

1. Send `/start`.
2. Select a language.
3. Before entering a deposit, send `/help`.
   - Expected: the help response appears.
4. Send `/plan`.
   - Expected: the bot asks for a deposit and displays the deposit button.
5. Send `/scan`.
   - Expected: the same deposit-required response appears.
6. Send a numeric deposit such as `5000`.
   - Expected: the bot confirms and saves the deposit.
7. Send `/settings`.
   - Expected: the saved deposit and risk settings appear.
8. Send `/plan BTC_USDT`.
   - Expected: an immediate loading message, followed by either a valid plan or
     a safe-skip result.
9. Send `/scan`.
   - Expected: an immediate scanning message, followed by ranked results or a
     no-setups response.

## Expected logs

The worker should record:

```text
command.plan.received
command.plan.deposit_required
command.scan.received
command.scan.deposit_required
```

After a deposit is saved, the `deposit_required` records should no longer
appear for that user.

## Failure triage

- No `command.*.received` log: the deployed code or Telegram polling worker is
  not using this version.
- `received` appears but no Telegram status message: inspect database access
  and Bot API errors before market-data calls.
- Loading appears and later fails: inspect the logged stack trace and MEXC
  availability.
- Commands work but `/scan` is slow: compare production timing with the
  3.18-second median local evaluation and inspect worker/network concurrency.

