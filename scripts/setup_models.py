from __future__ import annotations

import argparse
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_DIR = ROOT / "texttraits_app" / "models"
CANONICAL_MODEL = CANONICAL_DIR / "texttraits_inference_bundle.joblib"
CANONICAL_MANIFEST = CANONICAL_DIR / "texttraits_inference_manifest.json"
EXPORT_DIR = ROOT / "accessible-text-inference-app" / "models"
EXPORT_MODEL = EXPORT_DIR / "texttraits_inference_bundle.joblib"
EXPORT_MANIFEST = EXPORT_DIR / "texttraits_inference_manifest.json"


def copy_if_available(source: Path, target: Path) -> bool:
    if not source.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size == source.stat().st_size:
        return True
    shutil.copy2(source, target)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare TextTraits model directories.")
    parser.add_argument(
        "--export-only",
        action="store_true",
        help="Only prepare the standalone export folder.",
    )
    args = parser.parse_args()

    CANONICAL_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    print("Preparing TextTraits model directories")
    print(f"- canonical directory: {CANONICAL_DIR}")
    print(f"- export directory: {EXPORT_DIR}")

    copied_model = copy_if_available(CANONICAL_MODEL, EXPORT_MODEL)
    copied_manifest = copy_if_available(CANONICAL_MANIFEST, EXPORT_MANIFEST)

    if copied_model:
        print(f"- export model ready: {EXPORT_MODEL}")
    else:
        print("- canonical runtime model is missing; export copy was not created.")

    if copied_manifest:
        print(f"- export manifest ready: {EXPORT_MANIFEST}")
    else:
        print("- canonical manifest is missing; export manifest copy was not created.")

    if not args.export_only and not CANONICAL_MODEL.exists():
        print("\nNo trained model was found in the canonical app folder.")
        print("Place the runtime bundle here:")
        print(f"  {CANONICAL_MODEL}")
        print("\nThe app will fall back to clearly labeled demo mode unless TEXTTRAITS_ALLOW_DEMO=false.")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
