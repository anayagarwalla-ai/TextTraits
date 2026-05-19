# TextTraits Deployment Notes

This sync branch is ready to deploy as a dynamic Flask web service for staging.
It has not been deployed to a live public URL from this checkout.

## Current Deployment State

- Branch intended for this advanced production-readiness review: `codex/sync-production-readiness`.
- Base app branch: `origin/codex/production-readiness`, currently in sync with `origin/main`.
- Merged sync source: `origin/codex/pycharm-colab-setup`, which includes current `main` plus Colab/training diagnostics workflow updates.
- Latest verified commit: see the handoff message or `git rev-parse HEAD`.
- Live public URL: pending.
- GitHub Pages: not configured, and not appropriate for the Flask app.
- GitHub deployment API check: no public deployment evidence was available from the unauthenticated API check.
- `codex/production-readiness` and `main` now contain the production app, account, persistence, security, and workflow work. This sync branch adds the Supabase handoff and Colab/training workflow material on top.

## Local Run

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python scripts/verify_models.py
python texttraits_app/app.py
```

Open:

```text
http://127.0.0.1:5000/
```

macOS/Linux activation:

```bash
source .venv/bin/activate
```

## Production Start Command

Use this for Render, Railway, Fly, Heroku-style platforms, or any dynamic Python host that supports WSGI:

```bash
gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 60
```

The repo also includes:

- `Procfile`
- `render.yaml`
- `app.py` compatibility entrypoint
- `texttraits_app/wsgi.py`

## Required Environment Variables

For public hosting:

```text
TEXTTRAITS_ENV=production
DATABASE_URL=<Supabase pooler URL for project olacwelhrgzxzrxtmvto>
TEXTTRAITS_SECRET_KEY=<high-entropy-secret>
TEXTTRAITS_PUBLIC_BASE_URL=<hosted-https-url>
TEXTTRAITS_SECURE_COOKIES=true
TEXTTRAITS_TRUST_PROXY=true
TEXTTRAITS_DB_SSLMODE=require
ENABLE_DEV_TOOLS=false
TEXTTRAITS_ALLOW_DEMO=false
TEXTTRAITS_DEV_ACCOUNT_LINKS=false
```

Supabase CLI setup for the project:

```bash
supabase login
supabase init
supabase link --project-ref olacwelhrgzxzrxtmvto
```

The helper `scripts/setup_supabase_cli.sh` runs the same setup and accepts
`SUPABASE_ACCESS_TOKEN` for non-interactive login.

Optional:

```text
PORT=<provided by host>
WEB_CONCURRENCY=2
TEXTTRAITS_EMAIL_PROVIDER=smtp
TEXTTRAITS_FROM_EMAIL=<verified-sender>
TEXTTRAITS_SMTP_HOST=<provider-host>
TEXTTRAITS_SMTP_USERNAME=<provider-user>
TEXTTRAITS_SMTP_PASSWORD=<provider-secret>
SENTRY_DSN=<optional-sentry-dsn>
```

Do not set `ENABLE_DEV_TOOLS=true` in a public deployment. That exposes model metadata and debug payloads.

## Model File Expectation

The runtime model is tracked in Git:

```text
texttraits_app/models/texttraits_inference_bundle.joblib
```

Expected size is about 14-15 MB. Raw PANDORA data and training artifacts are intentionally excluded.

If a deploy fails because the model is missing:

```bash
python scripts/verify_models.py
```

For a public deployment, keep `TEXTTRAITS_ALLOW_DEMO=false` so missing models fail clearly instead of serving mock output.

## Free Deployment Path

The simplest current free path is a free Render Web Service plus a free external Postgres provider such as Supabase or Neon:

1. Connect GitHub repo `csboi/TextTraits`.
2. Select branch `main`.
3. Create a dynamic Web Service, not a static site.
4. Use the repo `render.yaml`, or set:
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 60`
5. Set env vars:
   - the required production variables above
6. Deploy.
7. Open `https://<hosted-url>/health` and confirm `ok` is `true`.

The public health endpoint intentionally exposes only aggregate readiness. Verify database/email/integration details through `scripts/preflight.py`, deploy logs, provider dashboards, and Sentry.

Railway can also run this as a dynamic service, but current free/trial behavior depends on account verification and credits. Fly.io is not a true no-cost free tier for new accounts; check billing before using it.

## Verification Commands

Run before handing off or redeploying:

```bash
python -m py_compile texttraits_app/app.py texttraits_app/predictor.py texttraits_app/demo_predictor.py texttraits_app/wsgi.py
python scripts/verify_models.py
python tests/smoke_test.py
python tests/browser_smoke_test.py
```

Optional export smoke:

```bash
python scripts/setup_models.py --export-only
python scripts/verify_models.py --export
```

## What Remains For A Live Public URL

The repo is deploy-ready after the merge commit is on the deployment branch. A live public URL still requires the repository owner to create or authorize a free hosting service account, connect the GitHub repo, set the environment variables above, connect hosted Postgres and email, and start the service.
