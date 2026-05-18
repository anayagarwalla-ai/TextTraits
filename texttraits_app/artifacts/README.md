# Training Artifacts

This folder is reserved for local training outputs and extraction scratch files.

Files in this directory are intentionally ignored by Git because they may be large, duplicated, environment-specific, or derived from private datasets. The deployable app uses the smaller runtime bundle in `texttraits_app/models/`.

Typical local-only files:

- `texttraits_model.joblib`
- `metrics.json`
- temporary training logs
- checkpoint files

To rebuild the runtime bundle from a local training artifact:

```bash
cd texttraits_app
python extract_trained_model.py
```

Do not commit raw datasets, Colab scratch outputs, credentials, or private training artifacts.
