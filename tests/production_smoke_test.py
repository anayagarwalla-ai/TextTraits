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
os.environ.setdefault("TEXTTRAITS_DEV_ACCOUNT_LINKS", "true")

import app as app_module  # noqa: E402


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def csrf_headers(client) -> dict[str, str]:
    token = client.get("/api/session").get_json()["csrf_token"]
    return {"X-CSRF-Token": token}


SENTRY_BROWSER_SCRIPT = "https://js.sentry-cdn.com/e02e26721e10ee55975fc73c5b7dfd57.min.js"


def main() -> int:
    client = app_module.app.test_client()

    home = client.get("/")
    assert_true(SENTRY_BROWSER_SCRIPT in home.get_data(as_text=True), "Sentry browser loader missing from app shell")
    csp = home.headers.get("Content-Security-Policy", "")
    assert_true("https://js.sentry-cdn.com" in csp, "CSP should allow the Sentry browser loader")
    assert_true("https://*.sentry.io" in csp, "CSP should allow Sentry event transport")

    health = client.get("/health")
    assert_true(health.status_code == 200, f"health returned {health.status_code}")
    assert_true(health.get_json()["ok"] is True, "public health should expose only aggregate readiness")
    assert_true(set(health.get_json().keys()) == {"ok"}, "public health should not expose deployment internals")

    session = client.get("/api/session")
    assert_true(session.status_code == 200, "session endpoint failed")
    assert_true(session.get_json()["authenticated"] is False, "fresh client should be unsigned")
    assert_true(session.get_json()["csrf_token"], "csrf token missing")

    signup = client.post(
        "/api/signup",
        json={"email": "qa@example.com", "password": "texttraits-test", "name": "QA User"},
        headers=csrf_headers(client),
    )
    assert_true(signup.status_code == 200, signup.get_data(as_text=True))
    payload = signup.get_json()
    assert_true(payload["authenticated"] is True, "signup did not authenticate")
    assert_true(payload["workspace"]["data"] == {}, "new workspace should start empty")
    assert_true("dev_verify_url" in payload, "local verification helper missing")
    verify_token = payload["dev_verify_url"].rsplit("/", 1)[-1]
    verify = client.get(f"/api/verify-email/{verify_token}", follow_redirects=False)
    assert_true(verify.status_code == 302, "verification link should redirect back to app")
    verify_post = client.post("/api/verify-email", json={"token": verify_token}, headers=csrf_headers(client))
    assert_true(verify_post.status_code == 200, "verification post should verify account")

    workspace_payload = {
        "mode": "explorer",
        "explorerHistory": [{"name": "QA sample", "clarity": 91}],
        "savedCampaigns": [{"name": "QA campaign", "folder": "RevOps", "status": "Drafts ready"}],
        "feedbackMemory": {"better": 1},
    }
    save = client.put("/api/workspace", json={"name": "QA workspace", "data": workspace_payload}, headers=csrf_headers(client))
    assert_true(save.status_code == 200, save.get_data(as_text=True))
    assert_true(save.get_json()["workspace"]["name"] == "QA workspace", "workspace name did not persist")

    load = client.get("/api/workspace")
    assert_true(load.status_code == 200, "workspace load failed")
    assert_true(load.get_json()["workspace"]["data"]["explorerHistory"][0]["name"] == "QA sample", "workspace data did not persist")

    event = client.post("/api/events", json={"event_type": "qa_event", "payload": {"ok": True}}, headers=csrf_headers(client))
    assert_true(event.status_code == 200, "event logging failed")

    client_error = client.post("/api/client-errors", json={"message": "qa client error"}, headers=csrf_headers(client))
    assert_true(client_error.status_code == 200, "client error logging failed")

    integration = client.post(
        "/api/integrations",
        json={"provider": "HubSpot", "status": "needs auth", "config": {"workspace": "QA"}},
        headers=csrf_headers(client),
    )
    assert_true(integration.status_code == 200, integration.get_data(as_text=True))
    integrations = client.get("/api/integrations").get_json()["integrations"]
    assert_true(any(item["provider"] == "HubSpot" for item in integrations), "integration did not persist")
    providers = client.get("/api/integration-providers")
    assert_true(providers.status_code == 200, "integration provider registry missing")
    provider_names = {item["name"] for item in providers.get_json()["providers"]}
    assert_true({"HubSpot", "Salesforce", "Gmail", "Outlook", "Chrome Sidebar"}.issubset(provider_names), "provider registry incomplete")
    hubspot_provider = next(item for item in providers.get_json()["providers"] if item["name"] == "HubSpot")
    assert_true(hubspot_provider["configured"] is False, "HubSpot should report unconfigured without credentials")
    oauth_start = client.post("/api/integrations/hubspot/oauth/start", headers=csrf_headers(client))
    assert_true(oauth_start.status_code == 409, "OAuth start should require configured provider credentials")

    export = client.post("/api/account/export", json={"password": "texttraits-test"}, headers=csrf_headers(client))
    assert_true(export.status_code == 200, "account export failed")
    assert_true(export.get_json()["workspace"]["name"] == "QA workspace", "account export missing workspace")

    reset_request = client.post("/api/request-password-reset", json={"email": "qa@example.com"}, headers=csrf_headers(client))
    assert_true(reset_request.status_code == 200, "password reset request failed")
    reset_payload = reset_request.get_json()
    assert_true("dev_reset_url" in reset_payload, "local reset helper missing")
    token = reset_payload["dev_reset_url"].rsplit("/", 1)[-1]
    reset = client.post("/api/reset-password", json={"token": token, "password": "new-texttraits-test"}, headers=csrf_headers(client))
    assert_true(reset.status_code == 200, reset.get_data(as_text=True))

    privacy = client.get("/privacy")
    terms = client.get("/terms")
    assert_true(privacy.status_code == 200 and "Privacy" in privacy.get_data(as_text=True), "privacy route missing")
    assert_true(terms.status_code == 200 and "Terms" in terms.get_data(as_text=True), "terms route missing")
    assert_true(SENTRY_BROWSER_SCRIPT in privacy.get_data(as_text=True), "Sentry browser loader missing from privacy page")
    assert_true(SENTRY_BROWSER_SCRIPT in terms.get_data(as_text=True), "Sentry browser loader missing from terms page")

    logout = client.post("/api/logout", headers=csrf_headers(client))
    assert_true(logout.status_code == 200, "logout failed")
    assert_true(client.get("/api/session").get_json()["authenticated"] is False, "logout did not clear session")

    login = client.post("/api/login", json={"email": "qa@example.com", "password": "new-texttraits-test"}, headers=csrf_headers(client))
    assert_true(login.status_code == 200, "login after reset failed")
    delete = client.delete("/api/account", json={"password": "new-texttraits-test"}, headers=csrf_headers(client))
    assert_true(delete.status_code == 200 and delete.get_json()["deleted"] is True, "account delete failed")
    assert_true(client.get("/api/session").get_json()["authenticated"] is False, "delete did not clear session")

    empty = client.post("/evaluate", json={"text": ""}, headers=csrf_headers(client))
    assert_true(empty.status_code == 400, "empty input should fail")
    too_long = client.post("/evaluate", json={"text": "word " * 1905}, headers=csrf_headers(client))
    assert_true(too_long.status_code == 413, "long input should be rejected")

    print("Production smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
