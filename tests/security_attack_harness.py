from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "texttraits_app"
sys.path.insert(0, str(APP_DIR))

tmpdir = tempfile.TemporaryDirectory()
os.environ["TEXTTRAITS_DB_PATH"] = str(Path(tmpdir.name) / "attack_workspace.sqlite3")
os.environ["DATABASE_URL"] = ""
os.environ["TEXTTRAITS_DATABASE_URL"] = ""
os.environ["TEXTTRAITS_EMAIL_PROVIDER"] = ""
os.environ.setdefault("ENABLE_DEV_TOOLS", "false")
os.environ.setdefault("TEXTTRAITS_SECRET_KEY", "attack-harness-secret")
os.environ.setdefault("TEXTTRAITS_DEV_ACCOUNT_LINKS", "false")

import app as app_module  # noqa: E402
import storage as storage_module  # noqa: E402


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def csrf_headers(client, extra: dict[str, str] | None = None) -> dict[str, str]:
    token = client.get("/api/session").get_json()["csrf_token"]
    headers = {"X-CSRF-Token": token}
    if extra:
        headers.update(extra)
    return headers


def main() -> int:
    client = app_module.app.test_client()

    health = client.get("/health")
    assert_true(health.status_code == 200 and set(health.get_json().keys()) == {"ok"}, "public health leaked internals")

    csp = client.get("/").headers.get("Content-Security-Policy", "")
    assert_true("style-src 'self';" in csp, "CSP should disallow inline styles in the primary app")
    assert_true("frame-ancestors 'self'" in csp and "object-src 'none'" in csp, "CSP missing clickjacking/plugin defenses")

    providers = client.get("/api/integration-providers").get_json()["providers"]
    assert_true(all("client_secret_env" not in provider for provider in providers), "integration provider leaked secret env key")
    assert_true(all(not any("SECRET" in item for item in provider.get("missing_env", [])) for provider in providers), "missing_env leaked secret key")

    for path, method in (
        ("/api/signup", "post"),
        ("/api/login", "post"),
        ("/api/request-password-reset", "post"),
        ("/evaluate", "post"),
        ("/api/workspace", "put"),
        ("/api/integrations/hubspot/oauth/start", "post"),
    ):
        response = getattr(client, method)(path, json={"text": "hello", "email": "x@example.com", "password": "long-enough-password"})
        assert_true(response.status_code in {401, 419}, f"{method.upper()} {path} should reject missing CSRF/session")

    weak = client.post(
        "/api/signup",
        json={"email": "weak@example.com", "password": "password123"},
        headers=csrf_headers(client),
    )
    assert_true(weak.status_code == 400, "weak/common password was accepted")

    signup = client.post(
        "/api/signup",
        json={"email": "attack@example.com", "password": "correct-horse-battery", "name": "<img src=x onerror=alert(1)>"},
        headers=csrf_headers(client),
    )
    assert_true(signup.status_code == 200 and signup.get_json()["authenticated"] is False, signup.get_data(as_text=True))
    duplicate = client.post(
        "/api/signup",
        json={"email": "ATTACK@example.com", "password": "correct-horse-battery"},
        headers=csrf_headers(client),
    )
    assert_true(duplicate.status_code == 200 and duplicate.get_json()["authenticated"] is False, "duplicate signup leaked through status or auth")

    for url in ("/api/reset-password?token=stolen", "/api/reset-password/stolen", "/api/verify-email?token=stolen", "/api/verify-email/stolen"):
        redirect = client.get(url, follow_redirects=False)
        assert_true("stolen" not in redirect.headers.get("Location", ""), f"dev token helper leaked token through {url}")

    verified_user = storage_module.create_user("verified-attack@example.com", "correct-horse-battery", "Attack User")
    storage_module.verify_email_token(verified_user["_verification_token"], "verified-attack@example.com")
    login = client.post(
        "/api/login",
        json={"email": "verified-attack@example.com", "password": "correct-horse-battery"},
        headers=csrf_headers(client),
    )
    assert_true(login.status_code == 200, "verified account should sign in for authenticated attack checks")

    bad_workspace = client.put(
        "/api/workspace",
        json={"data": {"mode": "explorer", "latestText": "private text", "evil": "<script>alert(1)</script>"}},
        headers=csrf_headers(client),
    )
    assert_true(bad_workspace.status_code == 400, "workspace accepted unsupported key")
    good_workspace = client.put(
        "/api/workspace",
        json={"data": {"mode": "explorer", "latestText": "private text", "explorerHistory": [{"name": "<script>alert(1)</script>"}]}},
        headers=csrf_headers(client),
    )
    assert_true(good_workspace.status_code == 200, good_workspace.get_data(as_text=True))
    assert_true(good_workspace.get_json()["workspace"]["data"]["latestText"] == "", "workspace persisted raw pasted text")

    raw_secret = client.post(
        "/api/integrations",
        json={"provider": "HubSpot", "config": {"nested": {"refresh_token": "steal-me"}}},
        headers=csrf_headers(client),
    )
    assert_true(raw_secret.status_code == 400, "integration config accepted nested token")

    client_error = client.post(
        "/api/client-errors",
        json={"message": "password=hunter2 token=abc123 Bearer secret-token", "source": "/?reset_token=abc123"},
        headers=csrf_headers(client),
    )
    assert_true(client_error.status_code == 200, "client error endpoint failed")
    user = storage_module.get_user_by_email("verified-attack@example.com")
    latest_event = storage_module.recent_events(user["id"], limit=1)[0]
    assert_true("hunter2" not in str(latest_event) and "abc123" not in str(latest_event), "client error log leaked credentials")

    old_production = app_module.PRODUCTION
    old_public_base_url = app_module.PUBLIC_BASE_URL
    try:
        app_module.PRODUCTION = True
        app_module.PUBLIC_BASE_URL = "https://texttraits.example"
        forged = client.post(
            "/api/request-password-reset",
            json={"email": "attack@example.com"},
            headers=csrf_headers(client, {"Origin": "https://evil.example"}),
        )
        assert_true(forged.status_code == 403, "production origin check accepted forged origin")
    finally:
        app_module.PRODUCTION = old_production
        app_module.PUBLIC_BASE_URL = old_public_base_url

    huge = client.post("/evaluate", json={"text": "word " * 1905}, headers=csrf_headers(client))
    assert_true(huge.status_code == 413, "oversized evaluation payload was accepted")

    export_without_password = client.post("/api/account/export", json={"password": ""}, headers=csrf_headers(client))
    assert_true(export_without_password.status_code == 403, "account export did not require password confirmation")

    print("Security attack harness passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
