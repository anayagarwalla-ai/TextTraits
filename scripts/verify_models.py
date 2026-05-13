from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_MODEL = ROOT / "texttraits_app" / "models" / "texttraits_inference_bundle.joblib"
CANONICAL_MANIFEST = ROOT / "texttraits_app" / "models" / "texttraits_inference_manifest.json"
EXPORT_MODEL = ROOT / "accessible-text-inference-app" / "models" / "texttraits_inference_bundle.joblib"


def describe(path: Path) -> str:
    if not path.exists():
        return "missing"
    size_mb = path.stat().st_size / (1024 * 1024)
    return f"found ({size_mb:.1f} MB)"


def main() -> int:
    parser = argparse.ArgumentParser(description="Check TextTraits runtime model files.")
    parser.add_argument(
        "--export",
        action="store_true",
        help="Also require a standalone copy inside accessible-text-inference-app/models.",
    )
    args = parser.parse_args()

    print("TextTraits model verification")
    print(f"- canonical model: {CANONICAL_MODEL} -> {describe(CANONICAL_MODEL)}")
    print(f"- canonical manifest: {CANONICAL_MANIFEST} -> {describe(CANONICAL_MANIFEST)}")
    print(f"- export model: {EXPORT_MODEL} -> {describe(EXPORT_MODEL)}")

    missing = []
    if not CANONICAL_MODEL.exists():
        missing.append(CANONICAL_MODEL)
    if not CANONICAL_MANIFEST.exists():
        missing.append(CANONICAL_MANIFEST)
    if args.export and not EXPORT_MODEL.exists():
        missing.append(EXPORT_MODEL)

    if missing:
        print("\nMissing required files:")
        for path in missing:
            print(f"- {path}")
        print("\nNext steps:")
        print("- If you cloned the full repo, run: python scripts/setup_models.py")
        print("- If the model is not available, the Flask app can still run in demo mode.")
        print("- Do not commit raw datasets, credentials, or private training artifacts.")
        return 1

    print("\nModel files look ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
