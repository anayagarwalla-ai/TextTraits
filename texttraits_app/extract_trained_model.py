from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import joblib


APP_DIR = Path(__file__).resolve().parent
SOURCE_PATH = APP_DIR / "artifacts" / "texttraits_model.joblib"
MODEL_DIR = APP_DIR / "models"
RUNTIME_MODEL_PATH = MODEL_DIR / "texttraits_inference_bundle.joblib"
MANIFEST_PATH = MODEL_DIR / "texttraits_inference_manifest.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_source_artifact() -> None:
    expected = os.getenv("TEXTTRAITS_TRAINING_ARTIFACT_SHA256", "").strip()
    required = os.getenv("TEXTTRAITS_REQUIRE_TRAINING_ARTIFACT_HASH", "").strip().lower() in {"1", "true", "yes", "on"}
    if not expected:
        if required or os.getenv("TEXTTRAITS_ENV", "").strip().lower() == "production":
            raise RuntimeError("Training artifact extraction requires TEXTTRAITS_TRAINING_ARTIFACT_SHA256.")
        return
    actual = sha256(SOURCE_PATH)
    if actual.lower() != expected.lower():
        raise RuntimeError("Training artifact checksum does not match TEXTTRAITS_TRAINING_ARTIFACT_SHA256.")


def main() -> None:
    if not SOURCE_PATH.exists():
        raise FileNotFoundError(f"Training artifact not found at {SOURCE_PATH}")

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    verify_source_artifact()
    artifact = joblib.load(SOURCE_PATH)
    joblib.dump(artifact, RUNTIME_MODEL_PATH)
    runtime_hash = sha256(RUNTIME_MODEL_PATH)

    manifest = {
        "runtime_model_path": str(RUNTIME_MODEL_PATH),
        "runtime_model_sha256": runtime_hash,
        "source_training_artifact": str(SOURCE_PATH),
        "source_training_artifact_sha256": sha256(SOURCE_PATH),
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
