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
os.environ.setdefault("TEXTTRAITS_DEV_ACCOUNT_LINKS", "true")

import app as app_module  # noqa: E402
import storage as storage_module  # noqa: E402


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
    assert_true(payload["authenticated"] is False, "signup should wait for email verification")
    assert_true(payload["pending_verification"] is True, "signup should create a pending verification")
    assert_true("dev_verify_code" in payload, "local verification helper missing")
    verify_token = payload["dev_verify_code"]
    assert_true(verify_token.isdigit() and len(verify_token) == 6, "verification code should be 6 digits")
    pending_before_duplicate = storage_module.get_pending_signup_by_email("qa@example.com")
    duplicate_signup = client.post(
        "/api/signup",
        json={"email": "qa@example.com", "password": "texttraits-test-updated", "name": "QA Updated"},
        headers=csrf_headers(client),
    )
    assert_true(duplicate_signup.status_code == 200, duplicate_signup.get_data(as_text=True))
    duplicate_payload = duplicate_signup.get_json()
    pending_after_duplicate = storage_module.get_pending_signup_by_email("qa@example.com")
    assert_true("dev_verify_code" not in duplicate_payload, "duplicate signup should not create a second code")
    assert_true("already emailed" in duplicate_payload["message"].lower(), "duplicate signup should tell the user to use the existing code")
    assert_true(pending_before_duplicate["verification_token"] == pending_after_duplicate["verification_token"], "duplicate signup should keep the original verification code")
    verify = client.get(f"/api/verify-email/{verify_token}", follow_redirects=False)
    assert_true(verify.status_code == 302, "verification link should redirect back to app")
    login_before_verify = client.post("/api/login", json={"email": "qa@example.com", "password": "texttraits-test-updated"}, headers=csrf_headers(client))
    assert_true(login_before_verify.status_code == 403, "login should require email verification")
    verify_post = client.post("/api/verify-email", json={"email": "qa@example.com", "token": verify_token}, headers=csrf_headers(client))
    assert_true(verify_post.status_code == 200, "verification post should verify account")
    assert_true(verify_post.get_json()["workspace"]["data"] == {}, "new workspace should start empty")

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

    old_exchange = app_module.exchange_oauth_code
    app_module.exchange_oauth_code = lambda entry, redirect_uri, code: {
        "hub_id": 246356639,
        "hub_domain": "simsayer.com",
        "token_type": "bearer",
        "expires_in": 1800,
        "scope": "crm.objects.contacts.read",
    }
    try:
        marketplace_callback = client.get("/api/integrations/hubspot/oauth/callback?code=sample-code&state=hubspot-install-state")
    finally:
        app_module.exchange_oauth_code = old_exchange
    assert_true(marketplace_callback.status_code == 200, marketplace_callback.get_data(as_text=True))
    assert_true("HubSpot app installed" in marketplace_callback.get_data(as_text=True), "HubSpot marketplace callback should not require TextTraits login")

    crm_card = client.post(
        "/v1/integrations/hubspot/crm-card/analyze-email",
        json={
            "workspace_id": "hubspot_246356639",
            "inputFields": {
                "subject": "Renewal follow-up",
                "body": "Hi Brian, following up on the renewal timing and next steps for your team.",
            },
        },
    )
    assert_true(crm_card.status_code == 200, crm_card.get_data(as_text=True))
    crm_payload = crm_card.get_json()
    assert_true(crm_payload["workflow"] == "hubspot_crm_card", "HubSpot CRM card endpoint should return the card workflow")
    assert_true("texttraits_score" in crm_payload["outputFields"], "HubSpot CRM card endpoint should return writeback fields")
    assert_true("email_quality" in crm_payload["analysis"], "HubSpot CRM card endpoint should return email-quality checks")
    assert_true(crm_payload["analysis"]["email_quality"]["score_source"].startswith("Weighted email-quality checks"), "score source should be explicit")
    assert_true(crm_payload["outputFields"]["texttraits_score"] == crm_payload["analysis"]["email_quality"]["score"], "writeback score should use email-quality score")
    assert_true("decision" in crm_payload["analysis"], "HubSpot CRM card endpoint should return decision metadata")
    assert_true("policy" in crm_payload["analysis"], "HubSpot CRM card endpoint should return policy metadata")
    assert_true("context" in crm_payload["analysis"], "HubSpot CRM card endpoint should return context metadata")
    assert_true(crm_payload["analysis"]["email_quality"]["checks"][0]["evidence"], "HubSpot checks should include evidence-level details")

    review_event = client.post(
        "/v1/integrations/hubspot/review-action",
        json={
            "request_id": crm_payload["outputFields"]["texttraits_request_id"],
            "action": "mark_reviewed",
            "payload": {"gate": crm_payload["outputFields"]["texttraits_gate"]},
        },
    )
    assert_true(review_event.status_code == 200, review_event.get_data(as_text=True))
    assert_true(review_event.get_json()["event"]["action"] == "mark_reviewed", "HubSpot review action should be recorded")

    clear_email = client.post(
        "/v1/integrations/hubspot/crm-card/analyze-email",
        json={
            "workspace_id": "hubspot_246356639",
            "inputFields": {
                "subject": "Factory tour checklist",
                "body": (
                    "Hi Brian, I wanted to confirm whether Wednesday still works for the factory tour. "
                    "If it does, reply by Friday and I will send the short checklist your team can review before the visit."
                ),
            },
        },
    ).get_json()
    assert_true(clear_email["outputFields"]["texttraits_gate"] == "ready", "clear email should be ready to route")

    unclear_email = client.post(
        "/v1/integrations/hubspot/crm-card/analyze-email",
        json={"inputFields": {"subject": "Checking", "body": "Thoughts?"}},
    ).get_json()
    assert_true(unclear_email["outputFields"]["texttraits_gate"] == "blocked", "unclear email should be blocked by quality checks")
    assert_true(unclear_email["analysis"]["email_quality"]["findings"], "unclear email should include actionable findings")
    assert_true(unclear_email["analysis"]["email_quality"]["findings"][0]["evidence"], "findings should show failed-check evidence")

    risky_email = client.post(
        "/v1/integrations/hubspot/crm-card/analyze-email",
        json={
            "inputFields": {
                "subject": "Guaranteed renewal savings",
                "body": "Hi Brian, this renewal is guaranteed to save 100% of the time your team spends on the process. Please approve today.",
            },
        },
    ).get_json()
    assert_true(risky_email["outputFields"]["texttraits_gate"] == "blocked", "risky email should be blocked by compliance policy")
    assert_true(risky_email["outputFields"]["texttraits_route"] == "Compliance review", "risky email should route to compliance review")
    assert_true(risky_email["outputFields"]["texttraits_score"] < 50, "blocked risky email should not show a ready-looking score")
    assert_true(risky_email["analysis"]["email_quality"]["raw_checklist_score"] > risky_email["analysis"]["email_quality"]["score"], "risky email should preserve checklist points before penalties")
    assert_true(risky_email["analysis"]["email_quality"]["score_factors"]["total_penalty"] >= 45, "risky email should be lowered by risk scoring penalties")

    policy_update = client.put(
        "/api/enterprise/hubspot/policy",
        json={
            "workspace_id": "hubspot_246356639",
            "environment": "production",
            "policy": {
                "version": "qa-policy",
                "ready_score_threshold": 75,
                "review_score_threshold": 60,
                "block_score_threshold": 20,
                "block_if_no_cta": False,
                "block_high_severity_findings": False,
                "compliance_review_on_risk_terms": True,
                "require_personalization": False,
                "min_body_words": 20,
                "max_body_words": 240,
            },
        },
        headers=csrf_headers(client),
    )
    assert_true(policy_update.status_code == 200, policy_update.get_data(as_text=True))
    policy_get = client.get("/api/enterprise/hubspot/policy?workspace_id=hubspot_246356639")
    assert_true(policy_get.get_json()["policy"]["version"] == "qa-policy", "HubSpot policy should persist")

    policy_routed = client.post(
        "/v1/integrations/hubspot/crm-card/analyze-email",
        json={
            "workspace_id": "hubspot_246356639",
            "inputFields": {
                "subject": "Factory tour plan",
                "body": (
                    "Hi Brian, the June 3 factory tour agenda includes cupcake line walkthrough, safety notes, "
                    "and a staffing overview for your team. The plan gives Acme a simple view of timing, owners, "
                    "and preparation details before the visit."
                ),
            },
        },
    ).get_json()
    assert_true(policy_routed["analysis"]["policy"]["version"] == "qa-policy", "analysis should use saved policy")
    assert_true(policy_routed["outputFields"]["texttraits_gate"] == "ready", "saved policy should affect routing thresholds")

    workflow_action = client.post(
        "/v1/integrations/hubspot/workflow-actions/analyze-email",
        json={
            "inputFields": {
                "subject": "Renewal workflow follow-up",
                "body": "Check this message before the automated renewal sequence continues.",
            },
        },
    )
    assert_true(workflow_action.status_code == 200, workflow_action.get_data(as_text=True))
    assert_true(workflow_action.get_json()["workflow"] == "hubspot_workflow_action", "HubSpot workflow action endpoint should remain available")

    analyses = client.get("/api/enterprise/hubspot/analyses?workspace_id=hubspot_246356639")
    assert_true(analyses.status_code == 200, analyses.get_data(as_text=True))
    assert_true(len(analyses.get_json()["analyses"]) >= 3, "HubSpot analyses should persist for reporting")
    dashboard = client.get("/api/enterprise/hubspot/dashboard")
    assert_true(dashboard.status_code == 200, dashboard.get_data(as_text=True))
    assert_true("top_failed_checks" in dashboard.get_json()["dashboard"], "HubSpot dashboard should include failed-check rollups")
    json_export = client.get("/api/enterprise/hubspot/exports/analyses.json?workspace_id=hubspot_246356639")
    assert_true(json_export.status_code == 200 and json_export.get_json()["analyses"], "HubSpot JSON export should return analyses")
    csv_export = client.get("/api/enterprise/hubspot/exports/analyses.csv?workspace_id=hubspot_246356639")
    assert_true(csv_export.status_code == 200 and "text/csv" in csv_export.headers.get("Content-Type", ""), "HubSpot CSV export should be available")

    export = client.post("/api/account/export", json={"password": "texttraits-test-updated"}, headers=csrf_headers(client))
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
