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
os.environ["DATABASE_URL"] = ""
os.environ["TEXTTRAITS_DATABASE_URL"] = ""
os.environ["TEXTTRAITS_EMAIL_PROVIDER"] = ""
os.environ.setdefault("ENABLE_DEV_TOOLS", "false")
os.environ.setdefault("TEXTTRAITS_SECRET_KEY", "test-secret-key")

import app as app_module  # noqa: E402
import storage as storage_module  # noqa: E402


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def csrf_headers(client) -> dict[str, str]:
    token = client.get("/api/session").get_json()["csrf_token"]
    return {"X-CSRF-Token": token}


def main() -> int:
    client = app_module.app.test_client()

    unauth_workspace = client.get("/api/workspace")
    assert_true(unauth_workspace.status_code == 401, "workspace should require auth")
    unauth_export = client.post("/api/account/export", json={"password": "x"}, headers=csrf_headers(client))
    assert_true(unauth_export.status_code == 401, "account export should require auth")

    missing_csrf = client.post("/api/signup", json={"email": "csrf@example.com", "password": "texttraits-test"})
    assert_true(missing_csrf.status_code == 419, "unsafe requests should require csrf")

    signup = client.post("/api/signup", json={"email": "security@example.com", "password": "texttraits-test"}, headers=csrf_headers(client))
    assert_true(signup.status_code == 200, signup.get_data(as_text=True))
    assert_true(signup.get_json()["authenticated"] is False, "signup should not authenticate before email verification")
    pending_signup = storage_module.get_pending_signup_by_email("security@example.com")
    assert_true(str(pending_signup["verification_token"]).startswith("sha256:"), "verification code should be stored hashed")
    duplicate = client.post("/api/signup", json={"email": "SECURITY@example.com", "password": "texttraits-test"}, headers=csrf_headers(client))
    assert_true(duplicate.status_code == 200, "duplicate signup should not expose account existence by status")
    assert_true(duplicate.get_json()["authenticated"] is False, "duplicate signup should not authenticate")
    assert_true("dev_verify_code" not in duplicate.get_json(), "duplicate signup should not issue another verification code")

    bad_login = client.post("/api/login", json={"email": "security@example.com", "password": "wrong-password"}, headers=csrf_headers(client))
    assert_true(bad_login.status_code == 401, "bad login should fail")
    unverified_login = client.post("/api/login", json={"email": "security@example.com", "password": "texttraits-test"}, headers=csrf_headers(client))
    assert_true(unverified_login.status_code == 403, "unverified login should require email verification")

    bad_reset = client.post("/api/reset-password", json={"token": "not-real", "password": "new-password"}, headers=csrf_headers(client))
    assert_true(bad_reset.status_code == 400, "invalid reset token should fail")
    reset_user = storage_module.create_user("reset-security@example.com", "texttraits-test", "Reset Security")
    storage_module.verify_email_token(reset_user["_verification_token"], "reset-security@example.com")
    login_verified = client.post(
        "/api/login",
        json={"email": "reset-security@example.com", "password": "texttraits-test"},
        headers=csrf_headers(client),
    )
    assert_true(login_verified.status_code == 200, "verified security account should sign in")
    reset_request = client.post("/api/request-password-reset", json={"email": "reset-security@example.com"}, headers=csrf_headers(client))
    assert_true(reset_request.status_code == 200, "reset request should succeed")
    stored_user = storage_module.get_user_by_email("reset-security@example.com")
    assert_true(str(stored_user["reset_token"]).startswith("sha256:"), "reset token should be stored hashed")

    headers = client.get("/").headers
    assert_true(headers.get("X-Content-Type-Options") == "nosniff", "nosniff header missing")
    assert_true(headers.get("X-Frame-Options") == "SAMEORIGIN", "frame header missing")
    assert_true(headers.get("Referrer-Policy") == "same-origin", "referrer policy missing")
    assert_true("Content-Security-Policy" in headers, "content security policy missing")
    reset_redirect = client.get("/api/reset-password/example-token", follow_redirects=False)
    assert_true(reset_redirect.headers["Location"].endswith("/"), "reset helper links should stay disabled unless explicitly enabled")
    verify_redirect = client.get("/api/verify-email/example-token", follow_redirects=False)
    assert_true(verify_redirect.headers["Location"].endswith("/"), "verify helper links should stay disabled unless explicitly enabled")

    providers = client.get("/api/integration-providers").get_json()["providers"]
    assert_true(all("client_secret_env" not in provider for provider in providers), "provider API leaked secret env names")
    assert_true(all(not any("SECRET" in item for item in provider.get("missing_env", [])) for provider in providers), "provider API leaked secret env setup names")
    assert_true(all("missing_env" in provider for provider in providers), "provider setup status missing")
    raw_token = client.post("/api/integrations", json={"provider": "HubSpot", "config": {"access_token": "secret"}}, headers=csrf_headers(client))
    assert_true(raw_token.status_code == 400, "integration config should reject raw tokens")
    nested_token = client.post("/api/integrations", json={"provider": "HubSpot", "config": {"nested": {"api_key": "secret"}}}, headers=csrf_headers(client))
    assert_true(nested_token.status_code == 400, "integration config should reject nested raw credentials")
    oauth_missing_csrf = client.post("/api/integrations/hubspot/oauth/start")
    assert_true(oauth_missing_csrf.status_code == 419, "OAuth start should be csrf protected")

    bad_workspace = client.put("/api/workspace", json={"data": {"mode": "explorer", "unexpectedScript": "<script>bad()</script>"}}, headers=csrf_headers(client))
    assert_true(bad_workspace.status_code == 400, "workspace sync should reject unsupported keys")
    text_workspace = client.put("/api/workspace", json={"data": {"mode": "explorer", "latestText": "private pasted text"}}, headers=csrf_headers(client))
    assert_true(text_workspace.status_code == 200, "workspace sync should accept allowed keys")
    assert_true(text_workspace.get_json()["workspace"]["data"]["latestText"] == "", "workspace sync should strip raw pasted text")

    client_error = client.post(
        "/api/client-errors",
        json={"message": "reset_token=abc123 password=hunter2", "source": "/?verify_token=abc123"},
        headers=csrf_headers(client),
    )
    assert_true(client_error.status_code == 200, "client error logging should succeed")
    latest_event = storage_module.recent_events(stored_user["id"], limit=1)[0]
    assert_true("abc123" not in str(latest_event["payload"]) and "hunter2" not in str(latest_event["payload"]), "client errors should redact token-like values")

    logout = client.post("/api/logout", headers=csrf_headers(client))
    assert_true(logout.status_code == 200, "logout failed")
    deleted = client.delete("/api/account", json={"password": "texttraits-test"}, headers=csrf_headers(client))
    assert_true(deleted.status_code == 401, "delete after logout should require auth")

    print("Security regression checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
