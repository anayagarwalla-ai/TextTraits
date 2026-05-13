# Runtime Models

This folder contains the model files used by the Flask inference app.

Tracked runtime files:

- `texttraits_inference_bundle.joblib` - the local runtime bundle used by `texttraits_app/predictor.py`.
- `texttraits_inference_manifest.json` - safe model metadata and validation summary.

Expected size:

- The current runtime bundle is about 15 MB, which is small enough for normal GitHub storage.

Do not place raw PANDORA datasets, private exports, Colab scratch files, credentials, or full training checkpoints in this folder. If a future model exceeds normal GitHub limits, use Git LFS or an external storage location and update `scripts/setup_models.py` with a verified download source.

Fresh clone setup:

```bash
python scripts/verify_models.py
python scripts/setup_models.py
```

If the runtime bundle is missing, the app can still launch in clearly labeled demo mode unless `TEXTTRAITS_ALLOW_DEMO=false` is set.
