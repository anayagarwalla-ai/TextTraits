# TextTraits Security Hardening Checklist

This file is the deploy-time security checklist for the repository owner.

## Must Pass Before Public Deploy

- Run `python3 tests/security_regression_test.py`.
- Run `python3 tests/security_attack_harness.py`.
- Run `python3 tests/production_smoke_test.py`.
- Run `python3 tests/config_regression_test.py`.
- Run `python3 scripts/security_audit.py`.
- Run `python3 -m bandit -q -r texttraits_app accessible-text-inference-app scripts -x '*/artifacts/*,*/models/*'`.
- Run `python3 -m pip_audit -r requirements.txt`, `python3 -m pip_audit -r texttraits_app/requirements.txt`, and `python3 -m pip_audit -r accessible-text-inference-app/requirements.txt`.
- Run `python3 scripts/preflight.py` with production environment variables set.
- Run `python3 scripts/verify_models.py` and confirm the model checksum passes.

## Required Production Settings

- `TEXTTRAITS_ENV=production`
- `TEXTTRAITS_SECRET_KEY=<long random secret>`
- `TEXTTRAITS_PUBLIC_BASE_URL=https://<public-domain>`
- `TEXTTRAITS_ALLOWED_PUBLIC_HOSTS=<public-domain>` if you want startup/preflight to reject accidental or malicious base URL changes
- `TEXTTRAITS_SECURE_COOKIES=true`
- `TEXTTRAITS_TRUST_PROXY=true` only behind a trusted HTTPS proxy
- `TEXTTRAITS_ALLOW_DEMO=false`
- `TEXTTRAITS_DEV_ACCOUNT_LINKS=false`
- `ENABLE_DEV_TOOLS=false`
- `TEXTTRAITS_EMAIL_PROVIDER=smtp` or `sendgrid`
- `TEXTTRAITS_SMTP_TLS=true` when SMTP is used
- `DATABASE_URL` or `TEXTTRAITS_DATABASE_URL` must point to hosted Postgres with SSL

## Guardrails Now In Code

- Unsafe API requests require a CSRF token.
- In production, unsafe API requests also require a same-origin `Origin` or `Referer` header.
- Session cookies are HTTP-only and can be marked secure in production.
- Password reset and email verification tokens are stored as SHA-256 digests.
- Reset and verification emails send one-time codes instead of tokenized URLs. Legacy local helper links redirect tokens into hash fragments for development only.
- Account export and account deletion require password confirmation.
- Workspace, event, and integration payload sizes are bounded.
- Client error logs and audit events redact likely secrets/tokens/passwords, including token-like values inside strings.
- OAuth setup starts through a CSRF-protected POST, and OAuth state is HMAC-signed.
- Raw integration credentials are rejected recursively from client-provided config.
- Public integration provider metadata never exposes client secret environment variable names.
- The public health endpoint returns only an overall readiness boolean, not database/email/integration internals.
- Synced workspace payloads are checked against an allowlist and raw pasted text is stripped before persistence.
- Runtime model loading verifies the trusted SHA-256 checksum before `joblib.load`.
- CSV exports neutralize spreadsheet formula injection.
- CSP, frame, referrer, nosniff, permissions, and opener-policy headers are set. The primary app requires a server nonce for inline scripts and disallows inline styles.
- The legacy standalone demo refuses production startup unless explicitly reviewed and enabled.
- Docker builds ignore local databases/logs and run as a non-root user.

## Do Not Do

- Do not enable `TEXTTRAITS_STORE_OAUTH_TOKENS=true` without encryption/key-management review.
- Do not use `TEXTTRAITS_EMAIL_PROVIDER=console` in production.
- Do not log account email bodies or one-time codes in development logs.
- Do not commit `.env`, SQLite databases, logs, screenshots with private content, raw datasets, or private model artifacts.
- Do not replace the runtime model bundle without updating `runtime_model_sha256` in `texttraits_app/models/texttraits_inference_manifest.json`.
