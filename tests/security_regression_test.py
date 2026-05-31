from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "texttraits_app"
sys.path.insert(0, str(APP_DIR))

tmpdir = Path(tempfile.mkdtemp(prefix="texttraits_security_regression_"))
os.environ["TEXTTRAITS_DB_PATH"] = str(tmpdir / "workspace.sqlite3")
os.environ["DATABASE_URL"] = ""
os.environ["TEXTTRAITS_DATABASE_URL"] = ""
os.environ["TEXTTRAITS_EMAIL_PROVIDER"] = ""
os.environ.setdefault("ENABLE_DEV_TOOLS", "false")
os.environ.setdefault("TEXTTRAITS_SECRET_KEY", "test-secret-key")

import app as app_module  # noqa: E402
import storage as storage_module  # noqa: E402


@app_module.app.get("/__test/rate-limit")
@app_module.rate_limited(1)
def _test_rate_limited_route():
    return {"ok": True}


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

    previous_hash = os.environ.get("TEXTTRAITS_API_KEY_SHA256")
    previous_scopes = os.environ.get("TEXTTRAITS_API_KEY_SCOPES")
    try:
        os.environ["TEXTTRAITS_API_KEY_SHA256"] = hashlib.sha256(b"hashed-read-key").hexdigest()
        os.environ["TEXTTRAITS_API_KEY_SCOPES"] = "*:/v1/governance"
        api_client = app_module.app.test_client()
        hashed_key_dashboard = api_client.get("/v1/governance/dashboard", headers={"X-TextTraits-Api-Key": "hashed-read-key"})
        wrong_key_dashboard = api_client.get("/v1/governance/dashboard", headers={"X-TextTraits-Api-Key": "wrong-key"})
        assert_true(hashed_key_dashboard.status_code == 200, "hashed API key should allow scoped governance read")
        assert_true(wrong_key_dashboard.status_code == 401, "invalid API key should fail closed")
    finally:
        if previous_hash is None:
            os.environ.pop("TEXTTRAITS_API_KEY_SHA256", None)
        else:
            os.environ["TEXTTRAITS_API_KEY_SHA256"] = previous_hash
        if previous_scopes is None:
            os.environ.pop("TEXTTRAITS_API_KEY_SCOPES", None)
        else:
            os.environ["TEXTTRAITS_API_KEY_SCOPES"] = previous_scopes

    old_production = app_module.PRODUCTION
    old_public_url = app_module.PUBLIC_BASE_URL
    try:
        app_module.PRODUCTION = True
        app_module.PUBLIC_BASE_URL = "https://texttraits.example"
        session_only_client = app_module.app.test_client()
        session_only_client.get("/api/session")
        locked_dashboard = session_only_client.get("/v1/governance/dashboard", headers={"Origin": "https://texttraits.example"})
        assert_true(locked_dashboard.status_code == 401, "production governance reads should require login or scoped API key")
    finally:
        app_module.PRODUCTION = old_production
        app_module.PUBLIC_BASE_URL = old_public_url

    first_rate = client.get("/__test/rate-limit")
    second_rate = client.get("/__test/rate-limit")
    assert_true(first_rate.status_code == 200, "rate-limit fixture should allow first request")
    assert_true(second_rate.status_code == 429, "rate-limit fixture should throttle second request")
    assert_true(second_rate.headers.get("Retry-After"), "rate-limit responses should include Retry-After")
    assert_true(second_rate.headers.get("X-RateLimit-Limit") == "1", "rate-limit response should include limit")
    assert_true(second_rate.get_json()["rate_limit"]["retry_after_seconds"] >= 1, "rate-limit JSON should include retry guidance")

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

    csv_analysis = client.post(
        "/v1/email/analyze",
        json={
            "workspace_id": "csv-security",
            "request_id": "csv-security-001",
            "subject": "Quarterly renewal checklist",
            "body": "Hi Maya, the renewal checklist is ready for Thursday and includes the three manager handoff details.",
            "source_system": "=HYPERLINK(\"https://evil.example\")",
            "campaign_id": "=HYPERLINK(\"https://evil.example\")",
        },
        headers=csrf_headers(client),
    )
    assert_true(csv_analysis.status_code == 200, csv_analysis.get_data(as_text=True))
    csv_export = client.get("/v1/governance/export?workspace_id=csv-security&type=analyses&format=csv")
    assert_true(csv_export.status_code == 200, "governance CSV export should succeed")
    assert_true("'=HYPERLINK" in csv_export.get_data(as_text=True), "CSV export should neutralize formula-like cells")
    assert_true("filename=\"texttraits-analyses-csv-security.csv\"" in csv_export.headers.get("Content-Disposition", ""), "CSV filename should be quoted and sanitized")

    previous_webhook_secret = os.environ.get("TEXTTRAITS_WEBHOOK_SECRET")
    previous_webhook_timestamp = os.environ.get("TEXTTRAITS_WEBHOOK_REQUIRE_TIMESTAMP")
    try:
        secret = "webhook-test-secret"
        os.environ["TEXTTRAITS_WEBHOOK_SECRET"] = secret
        os.environ["TEXTTRAITS_WEBHOOK_REQUIRE_TIMESTAMP"] = "true"
        event = {"event_id": "signed-event-001", "provider": "sendgrid", "event_type": "delivered", "request_id": "csv-security-001"}
        raw_body = json.dumps(event, separators=(",", ":")).encode("utf-8")
        timestamp = str(int(time.time()))
        signature = "sha256=" + hmac.new(secret.encode("utf-8"), f"{timestamp}.".encode("utf-8") + raw_body, hashlib.sha256).hexdigest()
        signed_webhook = client.post(
            "/v1/webhooks/post-send",
            data=raw_body,
            content_type="application/json",
            headers={**csrf_headers(client), "X-TextTraits-Signature": signature, "X-TextTraits-Timestamp": timestamp},
        )
        assert_true(signed_webhook.status_code == 200, signed_webhook.get_data(as_text=True))
        assert_true(signed_webhook.get_json()["signature_status"] == "verified", "fresh webhook signature should verify")
        unsigned_timestamp_event = {"event_id": "signed-event-002", "provider": "sendgrid", "event_type": "delivered"}
        unsigned_timestamp_body = json.dumps(unsigned_timestamp_event, separators=(",", ":")).encode("utf-8")
        body_signature = "sha256=" + hmac.new(secret.encode("utf-8"), unsigned_timestamp_body, hashlib.sha256).hexdigest()
        missing_timestamp = client.post(
            "/v1/webhooks/post-send",
            data=unsigned_timestamp_body,
            content_type="application/json",
            headers={**csrf_headers(client), "X-TextTraits-Signature": body_signature},
        )
        assert_true(missing_timestamp.status_code == 401, "timestamp-required webhooks should reject replayable signatures")
    finally:
        if previous_webhook_secret is None:
            os.environ.pop("TEXTTRAITS_WEBHOOK_SECRET", None)
        else:
            os.environ["TEXTTRAITS_WEBHOOK_SECRET"] = previous_webhook_secret
        if previous_webhook_timestamp is None:
            os.environ.pop("TEXTTRAITS_WEBHOOK_REQUIRE_TIMESTAMP", None)
        else:
            os.environ["TEXTTRAITS_WEBHOOK_REQUIRE_TIMESTAMP"] = previous_webhook_timestamp

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
