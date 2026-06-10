# TextTraits

TextTraits is a Flask web app for enterprise email optimization. This branch is non-generative: it scores existing email drafts, returns objective model signals, policy-backed findings, send-readiness gates, content hashes, integration routes, and governance metadata without writing replacement copy.

The app is designed as a workflow scoring layer for teams that already use tools such as CRM, marketing automation, warehouse imports, or send-path middleware. It should not be used as the sole authority for legal, consent, deliverability, compliance, hiring, admissions, finance, housing, medical, or other consequential decisions.

## Responsible Use

These outputs are model- and rule-derived signals from text patterns and workflow metadata. They may be wrong. Enterprise teams should validate thresholds, review false passes and false reviews, and keep humans responsible for claims, consent, opt-out handling, regulated content, and customer-specific policy.

## Repository Layout

- `texttraits_app/` - canonical Flask app, predictor, template, and runtime model folder.
- `texttraits_app/models/` - current runtime model bundle and safe manifest.
- `texttraits_app/artifacts/` - ignored local training artifacts and extraction scratch space.
- `training/` - Colab/high-RAM training and export scripts.
- `scripts/` - setup and verification helpers for model files.
- `tests/` - lightweight smoke tests.
- `hubspot-platform/` - HubSpot developer-platform templates for the Enterprise-Only integration path.
- `docs/enterprise-pitch-readiness.md` - free pitch script, demo boundaries, and pilot-readiness notes.
- `docs/hubspot-platform-integration.md` - HubSpot setup, callbacks, request-signature handling, and CLI flow.
- `docs/enterprise-one-pager.md` - concise enterprise positioning and pilot ask.
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
- `TEXTTRAITS_API_KEY_SHA256` or `TEXTTRAITS_API_KEY_HASHES` - preferred production server-to-server API key configuration.
- `TEXTTRAITS_WEBHOOK_SECRET` - signs post-send outcome webhooks; pair it with `TEXTTRAITS_WEBHOOK_REQUIRE_TIMESTAMP=true`.
- `TEXTTRAITS_REQUIRE_ENTERPRISE_BROWSER_AUTH` - keep `true` in production so governance reads require login or a scoped API key.
- `HUBSPOT_CLIENT_ID` and `HUBSPOT_CLIENT_SECRET` - HubSpot developer app OAuth credentials; use `python scripts/setup_hubspot_env.py`.
- `HUBSPOT_REQUIRE_SIGNATURE` - set `true` before accepting live HubSpot platform callbacks.

Public deployments should keep `ENABLE_DEV_TOOLS=false` and run `python3 scripts/preflight.py`.

## HubSpot Integration

The Enterprise-Only branch now includes a HubSpot platform scaffold. Render it after you have a public TextTraits HTTPS URL:

```bash
python scripts/render_hubspot_project.py --base-url https://your-public-texttraits-domain.example --support-email support@example.com
```

See `docs/hubspot-platform-integration.md` for the developer-account flow and the backend endpoints.

## Enterprise Demo

Fresh workspaces show clearly labeled synthetic example rows in dashboard panels so the workflow can be evaluated without pretending live customer data exists. To seed local demo rows into the SQLite database, run:

```bash
python3 scripts/seed_enterprise_demo.py --workspace-id demo_enterprise
```

These rows are synthetic examples only. See `docs/enterprise-pitch-readiness.md` for the free pitch path and the list of claims to avoid until a customer supplies credentials, requirements, and approved sample data.

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
