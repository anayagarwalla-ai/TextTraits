# Accessible Text Inference App

This folder is the portable handoff area for the public TextTraits app. It explains how to move the app into a fresh environment without carrying raw research data, local caches, or private training artifacts.

This folder includes a standalone copy of the public Flask app:

```text
app.py
predictor.py
demo_predictor.py
templates/index.html
```

The canonical development source still lives in `../texttraits_app/`. If you make product changes there, refresh this export before handing it off.

## What This Export Contains

- `app.py` - Flask app with public routes, health check, demo fallback, and dev-tool gating.
- `predictor.py` - runtime model loader and prediction response shaping.
- `demo_predictor.py` - deterministic mock predictor for missing-model demo mode.
- `templates/index.html` - public single-screen user interface.
- `requirements.txt` - Python dependencies needed by the Flask app.
- `.env.example` - safe environment variable template.
- `models/README.md` - model placement instructions.
- `scripts/setup_models.py` - local helper for creating model folders and copying from the canonical app when available.
- `scripts/verify_models.py` - local helper for checking whether the export has a runtime bundle.

## What Is Intentionally Omitted

- Raw PANDORA datasets.
- Full training artifacts and Colab checkpoints.
- Credentials, API keys, or private Google Drive links.
- Large future model binaries unless explicitly copied into `models/`.

The current canonical runtime model is about 15 MB and is tracked in the root app at:

```text
../texttraits_app/models/texttraits_inference_bundle.joblib
```

If this export is moved outside the repo, place the runtime bundle at:

```text
models/texttraits_inference_bundle.joblib
```

## Fresh Environment Setup

From the repository root:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python scripts/verify_models.py
python texttraits_app/app.py
```

From this export folder, if you have copied or mounted the app source separately:

```bash
pip install -r requirements.txt
python scripts/verify_models.py
python app.py
```

If the model is missing, local developers can set `TEXTTRAITS_ALLOW_DEMO=true` for clearly labeled demo mode. Public deployments should fail closed.

## Public Deployment Defaults

Use these defaults for public-facing deployments:

```text
ENABLE_DEV_TOOLS=false
TEXTTRAITS_ALLOW_DEMO=false
```

Set `TEXTTRAITS_ALLOW_DEMO=true` only for local demos where mock output is acceptable.

## Responsible Use Copy

The public app must clearly state that predictions are probabilistic estimates from text patterns, not facts about the user. It must not be used for hiring, admissions, policing, eligibility, finance, housing, medical decisions, or other consequential decisions.
