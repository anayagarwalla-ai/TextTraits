from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "texttraits_app"
sys.path.insert(0, str(APP_DIR))

from env_loader import load_env_file  # noqa: E402
import storage  # noqa: E402


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    original = {key: os.environ.get(key) for key in ("DATABASE_URL", "TEXTTRAITS_DATABASE_URL", "TEXTTRAITS_ENV", "TEXTTRAITS_DB_SSLMODE")}
    try:
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text('TEXTTRAITS_PUBLIC_BASE_URL="https://example.test"\nTEXTTRAITS_SECRET_KEY=local-secret\n', encoding="utf-8")
            os.environ.pop("TEXTTRAITS_PUBLIC_BASE_URL", None)
            load_env_file(env_file)
            assert_true(os.environ["TEXTTRAITS_PUBLIC_BASE_URL"] == "https://example.test", ".env loader did not load quoted value")

        os.environ["TEXTTRAITS_ENV"] = "production"
        os.environ["TEXTTRAITS_DATABASE_URL"] = "postgresql://user:pass@db.example.com:5432/texttraits"
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("TEXTTRAITS_DB_SSLMODE", None)
        secure_url = storage.database_url()
        assert_true("sslmode=require" in secure_url, "remote production Postgres should require SSL")
        assert_true("connect_timeout=10" in secure_url, "Postgres URL should include connect timeout")

        os.environ["TEXTTRAITS_DATABASE_URL"] = "postgresql://user:pass@localhost:5432/texttraits"
        local_url = storage.database_url()
        assert_true("sslmode=require" not in local_url, "local Postgres should not force SSL by default")
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    print("Environment/storage regression checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
