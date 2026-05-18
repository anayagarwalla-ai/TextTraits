from __future__ import annotations

import shutil
from pathlib import Path


EXPORT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = EXPORT_ROOT.parent
EXPORT_MODEL_DIR = EXPORT_ROOT / "models"
CANONICAL_MODEL_DIR = REPO_ROOT / "texttraits_app" / "models"


def copy_if_present(name: str) -> bool:
    source = CANONICAL_MODEL_DIR / name
    target = EXPORT_MODEL_DIR / name
    if not source.exists():
        return False
    EXPORT_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return True


def main() -> int:
    EXPORT_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    copied_model = copy_if_present("texttraits_inference_bundle.joblib")
    copied_manifest = copy_if_present("texttraits_inference_manifest.json")

    print(f"Export model directory: {EXPORT_MODEL_DIR}")
    print(f"Copied runtime model: {copied_model}")
    print(f"Copied manifest: {copied_manifest}")

    if not copied_model:
        print("\nNo canonical model was found. Place the runtime bundle at:")
        print(EXPORT_MODEL_DIR / "texttraits_inference_bundle.joblib")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
