# Render-Hosted Files

This file flags the parts of the repository that are used by the Render web service.
It is intentionally documentation-only so it does not change imports, build behavior,
or the deployed app.

## Render Service Entrypoint

Render reads `render.yaml` from the repository root.

Current Render commands:

```text
Build: pip install -r requirements.txt
Start: gunicorn app:app --bind 0.0.0.0:$PORT --workers ${WEB_CONCURRENCY:-2} --timeout 60
```

That means the root `app.py` is the WSGI entrypoint. It loads the real Flask app
from `texttraits_app/app.py`.

## Render-Hosted Runtime Files

These files are part of the deployed Render web service runtime:

```text
render.yaml
requirements.txt
app.py

texttraits_app/app.py
texttraits_app/demo_predictor.py
texttraits_app/email_delivery.py
texttraits_app/env_loader.py
texttraits_app/hubspot_client.py
texttraits_app/integration_adapters.py
texttraits_app/observability.py
texttraits_app/predictor.py
texttraits_app/storage.py
texttraits_app/wsgi.py

texttraits_app/templates/index.html

texttraits_app/static/api_client.js
texttraits_app/static/app.js
texttraits_app/static/csv_utils.js
texttraits_app/static/enterprise_copy.js
texttraits_app/static/product_config.js
texttraits_app/static/styles.css
texttraits_app/static/text_utils.js
texttraits_app/static/ui_helpers.js

texttraits_app/models/texttraits_inference_bundle.joblib
texttraits_app/models/texttraits_inference_manifest.json
```

## Render-Related But Not Runtime-Critical

These files document or support deployment, but the Render service does not use them
as its active runtime entrypoint when `render.yaml` is present:

```text
Procfile
Dockerfile
DEPLOYMENT.md
DEPLOYMENT_NOTES.md
README.md
.env.example
texttraits_app/requirements.txt
texttraits_app/models/README.md
texttraits_app/artifacts/README.md
```

## Included In The Repo, Not Hosted By Render As The Main Web App

Render may clone these files because it clones the repository, but they are not the
main Render-hosted Flask app:

```text
hubspot-project/
accessible-text-inference-app/
training/
tests/
scripts/
docs/
outputs/
output/
production_readiness/
```

## Local Generated Files To Avoid Treating As Hosted Source

These are local runtime byproducts and should not be considered Render-hosted source
files:

```text
texttraits_app/__pycache__/
texttraits_app/artifacts/*.log
texttraits_app/artifacts/*.sqlite3
```

