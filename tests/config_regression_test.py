from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_preflight(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged.update(env)
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "preflight.py")],
        cwd=ROOT,
        env=merged,
        text=True,
        capture_output=True,
        check=False,
    )


def main() -> int:
    local = run_preflight({"TEXTTRAITS_ENV": "development", "TEXTTRAITS_EMAIL_PROVIDER": ""})
    assert_true(local.returncode == 0, local.stderr)

    broken_prod = run_preflight(
        {
            "TEXTTRAITS_ENV": "production",
            "TEXTTRAITS_SECRET_KEY": "replace-with-a-long-random-secret",
            "TEXTTRAITS_PUBLIC_BASE_URL": "http://example.com",
            "TEXTTRAITS_DATABASE_URL": "",
            "DATABASE_URL": "",
            "TEXTTRAITS_EMAIL_PROVIDER": "",
        }
    )
    assert_true(broken_prod.returncode == 1, "broken production config should fail")
    assert_true("hosted Postgres" in broken_prod.stderr, "preflight should require hosted Postgres")
    assert_true("HTTPS" in broken_prod.stderr, "preflight should require HTTPS")

    good_prod = run_preflight(
        {
            "TEXTTRAITS_ENV": "production",
            "TEXTTRAITS_SECRET_KEY": "a-realistic-test-secret-with-more-than-enough-entropy",
            "TEXTTRAITS_PUBLIC_BASE_URL": "https://texttraits.example",
            "TEXTTRAITS_DATABASE_URL": "postgresql://texttraits:secret@db.example.com:5432/texttraits",
            "TEXTTRAITS_DB_SSLMODE": "require",
            "DATABASE_URL": "",
            "TEXTTRAITS_SECURE_COOKIES": "true",
            "TEXTTRAITS_EMAIL_PROVIDER": "smtp",
            "TEXTTRAITS_FROM_EMAIL": "no-reply@texttraits.example",
            "TEXTTRAITS_SMTP_HOST": "smtp.example.com",
            "TEXTTRAITS_SMTP_USERNAME": "apikey",
            "TEXTTRAITS_SMTP_PASSWORD": "secret",
        }
    )
    assert_true(good_prod.returncode == 0, good_prod.stderr)

    print("Configuration regression checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
