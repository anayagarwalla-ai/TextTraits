# TextTraits Deployment Notes

TextTraits now has a Flask backend with session auth, workspace persistence, event logging, per-account rate limits, password reset token flows, data export/delete routes, privacy/terms routes, and a WSGI entrypoint.

## Environment

Copy `.env.example` into your deployment environment and set:

- `TEXTTRAITS_SECRET_KEY`: long random secret used for Flask sessions.
- `TEXTTRAITS_DB_PATH`: durable SQLite path for local development and backup testing.
- `DATABASE_URL` or `TEXTTRAITS_DATABASE_URL`: hosted Postgres URL for production. The storage layer switches to Postgres automatically when this is set.
- `TEXTTRAITS_DB_SSLMODE=require`: required for remote production Postgres connections. Localhost Postgres does not force SSL by default.
- `TEXTTRAITS_DB_CONNECT_TIMEOUT=10`: default connection timeout appended to Postgres URLs.
- `TEXTTRAITS_PUBLIC_BASE_URL`: public HTTPS origin used in account/reset links.
- `TEXTTRAITS_EMAIL_PROVIDER`: `smtp`, `sendgrid`, or empty for local dev-only links.
- `TEXTTRAITS_FROM_EMAIL`: verified sender address for account emails.
- `TEXTTRAITS_SMTP_*` or `TEXTTRAITS_SENDGRID_API_KEY`: transactional email credentials.
- `TEXTTRAITS_SECURE_COOKIES=true`: use in HTTPS deployments.
- `TEXTTRAITS_TRUST_PROXY=true`: use behind Render/Fly/Heroku/reverse proxy HTTPS termination.
- `SENTRY_DSN`: optional Sentry DSN for server error reporting.
- OAuth credentials such as `HUBSPOT_CLIENT_ID`, `SALESFORCE_CLIENT_ID`, `GOOGLE_CLIENT_ID`, and `MICROSOFT_CLIENT_ID`.
- `TEXTTRAITS_RATE_LIMIT_PER_MINUTE`: default per-endpoint request limit.
- `TEXTTRAITS_MAX_TEXT_WORDS`: max submitted sample size.
- `ENABLE_DEV_TOOLS=false`: keep disabled in public deployments.

## Run Locally

```bash
python3 texttraits_app/app.py
```

For local Postgres:

```bash
export DATABASE_URL="postgresql://texttraits:texttraits123@localhost:5432/texttraits"
PORT=5001 python3 texttraits_app/app.py
```

You can also create a local `.env` file. The app loads `.env` automatically for local development without overriding real deployment environment variables.

## Production WSGI

Install production dependencies and run through a WSGI server:

```bash
pip install -r requirements.txt gunicorn
cd texttraits_app
gunicorn wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2
```

Place the app behind HTTPS and set `TEXTTRAITS_SECURE_COOKIES=true`.

## Container / Render

The repo includes:

- `Dockerfile` for container deployments.
- `Procfile` for Heroku-style platforms.
- `render.yaml` for Render web service + managed Postgres setup.

Before promoting a release, run:

```bash
TEXTTRAITS_ENV=production python3 scripts/preflight.py
```

## Persistence And Backups

Local development can store signed-in workspace state in SQLite. Production should set `DATABASE_URL` or `TEXTTRAITS_DATABASE_URL` to managed Postgres. Use the database provider’s automated backups and point-in-time recovery. `scripts/backup_sqlite.py` is included only for local/dev SQLite snapshots.

## Operational Checks

- `GET /health` verifies model availability, sync mode, and persistence status.
- `GET /health` also reports database backend/SSL status, email delivery, error-reporting, and configured integration counts.
- `texttraits_app/artifacts/app.log` receives rotated server logs in text or JSON format.
- `audit_events` records login, signup, evaluation, sync, integration, export/delete, and client events.
- `/api/client-errors` receives client-side error reports.
- Sentry is enabled automatically when `SENTRY_DSN` is set and `sentry-sdk[flask]` is installed.

## External Integrations

CRM/email/sidebar providers now report whether credentials are configured. OAuth start/callback routes are available for providers with configured credentials:

- HubSpot OAuth app/client secret
- Salesforce connected app
- Outreach/Salesloft API credentials
- Gmail/Outlook OAuth consent setup
- Chrome extension signing and store packaging

OAuth access/refresh tokens are not stored by default. Set `TEXTTRAITS_STORE_OAUTH_TOKENS=true` only after encryption/key-management has been reviewed.

## Account Readiness

Implemented locally:

- signup/login/logout
- password reset token flow
- email verification token endpoint
- data export
- account deletion
- per-account rate limit keys

Production still needs domain/HTTPS, provider-approved OAuth apps, and a reviewed transactional email sender domain.

## Legal And Privacy Review

`LEGAL_REVIEW.md` lists product behavior, privacy/terms topics, compliance-sensitive areas, and launch gates. It is not legal advice; use it as the handoff checklist for counsel/privacy review.

## Pre-Deploy QA

Run:

```bash
python3 -m py_compile texttraits_app/app.py texttraits_app/storage.py
node --check texttraits_app/static/app.js
python3 tests/smoke_test.py
python3 tests/browser_smoke_test.py
python3 tests/production_smoke_test.py
python3 tests/accessibility_smoke_test.py
python3 tests/security_regression_test.py
python3 tests/config_regression_test.py
python3 tests/frontend_regression_test.py
python3 tests/env_storage_regression_test.py
```
