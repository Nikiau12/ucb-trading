# Security policy

## Supported version

Security fixes are applied to the current `main` branch.

## Reporting a vulnerability

Please do not publish vulnerabilities, credentials, payment details, Telegram
initialization data, or database records in a public issue. Use GitHub's private
vulnerability reporting for this repository. Include the affected endpoint or
command, reproduction steps, and expected impact. We will acknowledge a report
within seven days and coordinate a fix before public disclosure.

## Operational rules

- Production secrets belong in Railway environment variables, never in Git.
- `MINI_APP_DEMO_MODE` must remain `false` in production.
- Rotate a credential immediately if it is exposed in logs or source control.
- Security and dependency checks must pass before merging into `main`.
