# TextTraits

TextTraits is a local Flask web app that helps people explore what a writing sample may reveal to a text classifier. It estimates signals such as gender-related language patterns, age-related patterns, MBTI-style dimensions, writing style, and confidence.

The app is designed as an educational public-facing tool. It should not be used to make decisions about real people.

## Responsible Use

These outputs are model-generated guesses from text patterns. They may be wrong. Text can contain misleading signals from topic, community, genre, copied phrasing, or the model's training data. Do not use TextTraits for hiring, admissions, policing, eligibility, finance, housing, medical decisions, or other consequential decisions.

## Repository Layout

- `texttraits_app/` - canonical Flask app, predictor, template, and runtime model folder.
- `texttraits_app/models/` - current runtime model bundle and safe manifest.
- `texttraits_app/artifacts/` - ignored local training artifacts and extraction scratch space.
- `training/` - Colab/high-RAM training and export scripts.
- `scripts/` - setup and verification helpers for model files.
- `tests/` - lightweight smoke tests.
- `accessible-text-inference-app/` - clean portable export guide and standalone model-placement structure.

## Quick Start

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python scripts/verify_models.py
python texttraits_app/app.py
```

Then open:

```text
http://127.0.0.1:5000/
```

On macOS/Linux, activate the virtual environment with:

```bash
source .venv/bin/activate
```

## Environment Variables

Copy `.env.example` if your deployment system loads environment files.

- `HOST` - Flask host, default `127.0.0.1`.
- `PORT` - Flask port, default `5000`.
- `ENABLE_DEV_TOOLS` - set `true` only for local developer diagnostics.
- `TEXTTRAITS_ALLOW_DEMO` - keep `false` in production; local developers can set `true` only for clearly labeled mock output.
- `TEXTTRAITS_DEV_ACCOUNT_LINKS` - keep `false` in production; local developers can set `true` to surface verification/reset helper links when email is not configured.
- `TEXTTRAITS_SECURE_COOKIES` - set `true` behind HTTPS.

Public deployments should keep `ENABLE_DEV_TOOLS=false` and run `python3 scripts/preflight.py`.

## Model Files

The current runtime model is tracked at:

```text
texttraits_app/models/texttraits_inference_bundle.joblib
```

It is about 15 MB, so it is small enough for normal GitHub storage. Raw PANDORA data, local training artifacts, Colab scratch files, and full checkpoints are intentionally excluded.

Check model readiness:

```bash
python scripts/verify_models.py
```

Prepare the portable export folder:

```bash
python scripts/setup_models.py
```

If a future model is too large for GitHub, place it externally and update the setup script with a verified download source. Do not invent download links.

## Developer Tools

Developer-only diagnostics are hidden by default. To enable raw metadata, metrics, and JSON payload tools locally:

```bash
set ENABLE_DEV_TOOLS=true
python texttraits_app/app.py
```

PowerShell:

```powershell
$env:ENABLE_DEV_TOOLS="true"
python texttraits_app/app.py
```

With developer tools disabled, the public UI does not display raw JSON, local model paths, dataset references, debug metrics, or dataset diagnostics.

## Tests

Run the smoke tests:

```bash
python tests/smoke_test.py
```

The smoke test verifies:

- The home page renders.
- Public debug panels are hidden by default.
- The evaluation endpoint returns a structured response.
- The health endpoint responds.

Run the demo CRM seed regression:

```bash
python tests/demo_crm_seed_test.py
```

## Demo CRM Dataset

The HubSpot governance and reporting surfaces can be populated with a synthetic CRM-style dataset:

```bash
python scripts/migrate.py
python scripts/seed_demo_crm.py
```

The fixture lives at `texttraits_app/demo_data/hubspot_crm_demo.json`. It includes fictional companies, contacts, deals, owners, campaigns, review actions, and activity/outcome events using reserved example domains. It is synthetic repository data, so it avoids third-party licensing constraints and real personal data.

The seed uses the configured database environment, just like `scripts/migrate.py`. To force a local SQLite demo database, set `TEXTTRAITS_DATABASE_URL=` and `DATABASE_URL=` and point `TEXTTRAITS_DB_PATH` at the desired `.sqlite3` file.

The seed targets workspace `demo_hubspot_crm` and refreshes that workspace by default before loading data, so rerunning the command does not duplicate analyses or outcomes. Use `python scripts/seed_demo_crm.py --no-refresh` only when you intentionally want to append. After seeding, open the Enterprise view, expand CRM setup, and load HubSpot governance data; use workspace `demo_hubspot_crm` when inspecting the saved demo policy.

## Training

High-RAM training scripts live in `training/`. See `training/README.md` for Colab commands, expected Google Drive paths, and output files.

The deployable app does not require raw training data. It only needs the runtime model bundle in `texttraits_app/models/`.

## Deployment Notes

This app is currently a Flask service. A production deployment should:

- Install dependencies from `requirements.txt`.
- Provide `texttraits_app/models/texttraits_inference_bundle.joblib`.
- Set `ENABLE_DEV_TOOLS=false`.
- Set `TEXTTRAITS_ALLOW_DEMO=false`.
- Run `python3 scripts/verify_models.py` so the runtime model checksum is checked.
- Review `SECURITY_HARDENING.md`.
- Run behind a production WSGI server or the platform's Python web runtime.

The repo includes a deployable WSGI entrypoint and free-hosting handoff files:

- `texttraits_app/wsgi.py`
- `app.py`
- `Procfile`
- `render.yaml`
- `DEPLOYMENT_NOTES.md`
- `production_readiness/FREE_DEPLOY_REQUIREMENTS.txt`

Public demo start command:

```bash
gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 60
```

The repository is deploy-ready, but no live public URL is currently verified in this checkout.

## Enterprise HubSpot Docs

- `docs/hubspot_score_methodology.md`
- `docs/hubspot_workflow_action.md`
- `docs/hubspot_reliability_security.md`
- `docs/enterprise_demo_script.md`

## Troubleshooting

- If `/evaluate` says the model is unavailable, run `python scripts/verify_models.py` and confirm the model bundle exists.
- If you see mock results, the app is in demo fallback mode because the trained model was not loaded.
- If the UI shows developer JSON or model paths, disable `ENABLE_DEV_TOOLS`.
- If Colab training appears frozen, use `training/colab_one_shot_export_logged.py` for heartbeat logging.
