from __future__ import annotations

import json
from pathlib import Path

import joblib


APP_DIR = Path(__file__).resolve().parent
SOURCE_PATH = APP_DIR / "artifacts" / "texttraits_model.joblib"
MODEL_DIR = APP_DIR / "models"
RUNTIME_MODEL_PATH = MODEL_DIR / "texttraits_inference_bundle.joblib"
MANIFEST_PATH = MODEL_DIR / "texttraits_inference_manifest.json"


def main() -> None:
    if not SOURCE_PATH.exists():
        raise FileNotFoundError(f"Training artifact not found at {SOURCE_PATH}")

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    artifact = joblib.load(SOURCE_PATH)
    joblib.dump(artifact, RUNTIME_MODEL_PATH)

    manifest = {
        "runtime_model_path": str(RUNTIME_MODEL_PATH),
        "source_training_artifact": str(SOURCE_PATH),
        "vectorizer": type(artifact["vectorizer"]).__name__,
        "models": {name: type(model).__name__ for name, model in artifact["models"].items()},
        "metrics": artifact.get("metrics", {}),
        "label_notes": artifact.get("label_notes", {}),
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"Extracted runtime model to {RUNTIME_MODEL_PATH}")
    print(f"Wrote manifest to {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
