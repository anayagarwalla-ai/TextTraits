from __future__ import annotations

from pathlib import Path


EXPORT_ROOT = Path(__file__).resolve().parents[1]
MODEL = EXPORT_ROOT / "models" / "texttraits_inference_bundle.joblib"
MANIFEST = EXPORT_ROOT / "models" / "texttraits_inference_manifest.json"


def describe(path: Path) -> str:
    if not path.exists():
        return "missing"
    return f"found ({path.stat().st_size / (1024 * 1024):.1f} MB)"


def main() -> int:
    print("Accessible export model verification")
    print(f"- runtime model: {MODEL} -> {describe(MODEL)}")
    print(f"- manifest: {MANIFEST} -> {describe(MANIFEST)}")
    if not MODEL.exists():
        print("\nPlace the runtime bundle at models/texttraits_inference_bundle.joblib.")
        print("If this folder is still inside the full repo, run: python ../scripts/setup_models.py --export-only")
        print("The public Flask app can still use demo mode if a real model is unavailable.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
