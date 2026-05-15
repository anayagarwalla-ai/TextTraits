from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "texttraits_app"
sys.path.insert(0, str(APP_DIR))

tmpdir = tempfile.TemporaryDirectory()
os.environ["TEXTTRAITS_DB_PATH"] = str(Path(tmpdir.name) / "workspace.sqlite3")
os.environ.setdefault("ENABLE_DEV_TOOLS", "false")
os.environ.setdefault("TEXTTRAITS_SECRET_KEY", "test-secret-key")

import app as app_module  # noqa: E402


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    client = app_module.app.test_client()

    unauth_workspace = client.get("/api/workspace")
    assert_true(unauth_workspace.status_code == 401, "workspace should require auth")
    unauth_export = client.get("/api/account/export")
    assert_true(unauth_export.status_code == 401, "account export should require auth")

    signup = client.post("/api/signup", json={"email": "security@example.com", "password": "texttraits-test"})
    assert_true(signup.status_code == 200, signup.get_data(as_text=True))
    duplicate = client.post("/api/signup", json={"email": "SECURITY@example.com", "password": "texttraits-test"})
    assert_true(duplicate.status_code == 409, "duplicate signup should be rejected case-insensitively")

    bad_login = client.post("/api/login", json={"email": "security@example.com", "password": "wrong-password"})
    assert_true(bad_login.status_code == 401, "bad login should fail")

    bad_reset = client.post("/api/reset-password", json={"token": "not-real", "password": "new-password"})
    assert_true(bad_reset.status_code == 400, "invalid reset token should fail")

    headers = client.get("/").headers
    assert_true(headers.get("X-Content-Type-Options") == "nosniff", "nosniff header missing")
    assert_true(headers.get("X-Frame-Options") == "SAMEORIGIN", "frame header missing")
    assert_true(headers.get("Referrer-Policy") == "same-origin", "referrer policy missing")

    providers = client.get("/api/integration-providers").get_json()["providers"]
    assert_true(all("client_secret_env" not in provider for provider in providers), "provider API leaked secret env names")
    assert_true(all("missing_env" in provider for provider in providers), "provider setup status missing")

    logout = client.post("/api/logout")
    assert_true(logout.status_code == 200, "logout failed")
    deleted = client.delete("/api/account")
    assert_true(deleted.status_code == 401, "delete after logout should require auth")

    print("Security regression checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
