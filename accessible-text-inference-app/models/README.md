# Model Placement

Place the deployable runtime model here if you want this export folder to be self-contained:

```text
models/texttraits_inference_bundle.joblib
```

Optional safe metadata:

```text
models/texttraits_inference_manifest.json
```

The current canonical model lives in the root app:

```text
../texttraits_app/models/texttraits_inference_bundle.joblib
```

From the repository root, copy it into this export folder with:

```bash
python scripts/setup_models.py --export-only
```

Do not put raw datasets, private training exports, credentials, Colab scratch files, or large checkpoints in this folder.
