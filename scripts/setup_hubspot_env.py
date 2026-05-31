from __future__ import annotations

import argparse
import getpass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_prompt(label: str, default: str = "", secret: bool = False) -> str:
    suffix = f" [{default}]" if default else ""
    if secret:
        value = getpass.getpass(f"{label}{suffix}: ").strip()
    else:
        value = input(f"{label}{suffix}: ").strip()
    return value or default


def update_env_file(env_path: Path, values: dict[str, str]) -> None:
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    seen: set[str] = set()
    updated: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            updated.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in values:
            updated.append(f"{key}={values[key]}")
            seen.add(key)
        else:
            updated.append(line)
    if updated and updated[-1].strip():
        updated.append("")
    for key, value in values.items():
        if key not in seen:
            updated.append(f"{key}={value}")
    env_path.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely add HubSpot developer app settings to a local TextTraits .env file.")
    parser.add_argument("--env-file", default=str(ROOT / ".env"), help="Path to the .env file to update.")
    args = parser.parse_args()

    env_path = Path(args.env_file).expanduser().resolve()
    print(f"Updating {env_path}")
    print("Paste values from the HubSpot developer app. Secret inputs are not echoed.")

    values = {
        "TEXTTRAITS_PUBLIC_BASE_URL": read_prompt("Public HTTPS TextTraits base URL", "https://your-domain.example"),
        "HUBSPOT_CLIENT_ID": read_prompt("HubSpot client ID"),
        "HUBSPOT_CLIENT_SECRET": read_prompt("HubSpot client secret", secret=True),
        "HUBSPOT_REQUIRE_SIGNATURE": read_prompt("Require signed HubSpot platform callbacks", "true"),
        "HUBSPOT_SIGNATURE_TOLERANCE_SECONDS": read_prompt("HubSpot signature replay tolerance seconds", "300"),
        "TEXTTRAITS_STORE_OAUTH_TOKENS": read_prompt("Store OAuth tokens locally", "false"),
    }
    update_env_file(env_path, values)
    print("HubSpot environment keys written. Secret values were not printed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
