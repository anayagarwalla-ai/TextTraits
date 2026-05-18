# TextTraits Deployment Notes

This repo is ready to deploy as a dynamic Flask web service. It has not been deployed to a live public URL from this checkout.

## Current Deployment State

- Branch intended for the public app: `main`.
- Latest verified commit: see the handoff message or `git rev-parse HEAD`.
- Live public URL: pending.
- GitHub Pages: not configured, and not appropriate for the Flask app.
- GitHub deployment API check: no public deployment evidence was available from the unauthenticated API check.
- Existing remote branch: `origin/codex/production-readiness` contains a larger production/auth/persistence experiment and a separate free-deploy checklist. It is not merged into `main`.

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
gunicorn texttraits_app.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 60
```

The repo also includes:

- `Procfile`
- `render.yaml`
- `texttraits_app/wsgi.py`

## Required Environment Variables

For public hosting:

```text
ENABLE_DEV_TOOLS=false
TEXTTRAITS_ALLOW_DEMO=false
```

Optional:

```text
PORT=<provided by host>
WEB_CONCURRENCY=2
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

The simplest current free path is Render Free Web Service:

1. Connect GitHub repo `csboi/TextTraits`.
2. Select branch `main`.
3. Create a dynamic Web Service, not a static site.
4. Use the repo `render.yaml`, or set:
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn texttraits_app.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 60`
5. Set env vars:
   - `ENABLE_DEV_TOOLS=false`
   - `TEXTTRAITS_ALLOW_DEMO=false`
6. Deploy.
7. Open `https://<hosted-url>/health` and confirm:
   - `ok` is `true`
   - `demo` is `false`
   - `dev_tools_enabled` is `false`

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

The repo is deploy-ready. A live public URL still requires the repository owner to create or authorize a free hosting service account, connect the GitHub repo, set the environment variables above, and start the service.
