from __future__ import annotations

import argparse
import shutil
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = ROOT / "hubspot-platform" / "templates"
DEFAULT_OUTPUT_DIR = ROOT / "hubspot-platform" / "rendered"


def render_text(value: str, replacements: dict[str, str]) -> str:
    rendered = value
    for key, replacement in replacements.items():
        rendered = rendered.replace(key, replacement)
    return rendered


def render_project(output_dir: Path, replacements: dict[str, str]) -> None:
    if output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)
        for child in output_dir.iterdir():
            for attempt in range(5):
                try:
                    if child.is_dir():
                        shutil.rmtree(child)
                    else:
                        child.unlink()
                    break
                except PermissionError:
                    if attempt == 4:
                        raise
                    time.sleep(0.5)
    else:
        output_dir.mkdir(parents=True, exist_ok=True)
    for source in TEMPLATE_DIR.rglob("*"):
        relative = source.relative_to(TEMPLATE_DIR)
        target = output_dir / relative
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        text = source.read_text(encoding="utf-8")
        target.write_text(render_text(text, replacements), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Render the HubSpot developer-project scaffold for a TextTraits deployment.")
    parser.add_argument("--base-url", required=True, help="Public HTTPS TextTraits base URL, for example https://texttraits.example.com")
    parser.add_argument("--support-email", default="support@example.com", help="Support email visible in HubSpot app metadata.")
    parser.add_argument("--support-url", default="", help="Support URL visible in HubSpot app metadata. Defaults to <base-url>/security.")
    parser.add_argument("--documentation-url", default="", help="Documentation URL visible in HubSpot app metadata. Defaults to <base-url>/v1/install-kit.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory to write rendered project files.")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    if not base_url.startswith("https://"):
        raise SystemExit("--base-url must be an HTTPS URL for HubSpot production callbacks.")

    replacements = {
        "__TEXTTRAITS_PUBLIC_BASE_URL__": base_url,
        "__TEXTTRAITS_SUPPORT_EMAIL__": args.support_email,
        "__TEXTTRAITS_SUPPORT_URL__": args.support_url or f"{base_url}/security",
        "__TEXTTRAITS_DOCUMENTATION_URL__": args.documentation_url or f"{base_url}/v1/install-kit",
    }
    output_dir = Path(args.output_dir).expanduser().resolve()
    render_project(output_dir, replacements)
    print(f"Rendered HubSpot project to {output_dir}")
    print("Next: cd into that folder and run `hs project upload` or `hs project dev` after HubSpot CLI auth.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
