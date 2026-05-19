# Supabase Postgres Setup

The production-readiness app supports Supabase through a normal Postgres
connection string. No Supabase API key is needed for server-side persistence.

## Required Environment Variable

Set this on the hosting provider:

```text
DATABASE_URL=postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
```

The app also accepts `TEXTTRAITS_DATABASE_URL`, but `DATABASE_URL` is the
standard hosting-provider variable and is enough on its own.

For production, also set:

```text
TEXTTRAITS_ENV=production
TEXTTRAITS_DB_SSLMODE=require
TEXTTRAITS_DB_CONNECT_TIMEOUT=10
TEXTTRAITS_SECURE_COOKIES=true
TEXTTRAITS_TRUST_PROXY=true
ENABLE_DEV_TOOLS=false
TEXTTRAITS_ALLOW_DEMO=false
TEXTTRAITS_DEV_ACCOUNT_LINKS=false
```

## Which Supabase URL To Use

Use the Supabase dashboard:

```text
Project > Connect > Connection string
```

Recommended for a hosted Flask web service:

- Use the **Session pooler** connection string if the host may not support IPv6.
- Use the **Direct connection** only if the host supports IPv6 or the project has
  the Supabase IPv4 add-on.
- Avoid transaction-pooler mode for this app unless it is specifically tested,
  because transaction poolers can be incompatible with prepared statements and
  session-level behavior in some Postgres clients.

The storage layer automatically appends:

- `connect_timeout=10` unless already present;
- `sslmode=require` for remote production Postgres unless already present or set
  through `TEXTTRAITS_DB_SSLMODE`.

## Initialize / Verify

After setting env vars:

```bash
python scripts/preflight.py
python scripts/migrate.py
python tests/env_storage_regression_test.py
```

Expected health behavior after deploy:

```text
GET /health
{"ok": true}
```

The public `/health` endpoint intentionally does not expose the database URL,
host, username, or detailed database status.

## Local Safety

Never commit a real Supabase URL, password, `.env`, SSL certificate, dashboard
screenshot containing secrets, or database dump.

For local development without Supabase, omit `DATABASE_URL`; the app falls back
to SQLite at `TEXTTRAITS_DB_PATH`.
