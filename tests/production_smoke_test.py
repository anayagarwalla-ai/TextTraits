from __future__ import annotations

import base64
import hashlib
import hmac
import json
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
import hubspot_client as hubspot_client_module  # noqa: E402
import storage as storage_module  # noqa: E402


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def csrf_headers(client) -> dict[str, str]:
    token = client.get("/api/session").get_json()["csrf_token"]
    return {"X-CSRF-Token": token}


def signed_hubspot_headers(secret: str, payload: dict, timestamp: int | None = None) -> tuple[bytes, dict[str, str]]:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    signed_body = body
    if timestamp is not None:
        headers["X-TextTraits-Timestamp"] = str(timestamp)
        signed_body = str(timestamp).encode("utf-8") + b"." + body
    signature = hmac.new(secret.encode("utf-8"), signed_body, hashlib.sha256).hexdigest()
    headers["X-TextTraits-Signature"] = f"sha256={signature}"
    return body, headers


HUBSPOT_V3_QUERY_DECODE_MAP = {
    "%3A": ":",
    "%2F": "/",
    "%3F": "?",
    "%40": "@",
    "%21": "!",
    "%24": "$",
    "%27": "'",
    "%28": "(",
    "%29": ")",
    "%2A": "*",
    "%2C": ",",
    "%3B": ";",
}


def hubspot_v3_signature_headers(secret: str, payload: dict, url: str, timestamp_ms: int | None = None) -> tuple[bytes, dict[str, str]]:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    timestamp_value = str(timestamp_ms if timestamp_ms is not None else int(app_module.time.time() * 1000))
    canonical_url = url.split("#", 1)[0]
    if "?" in canonical_url:
        path, query = canonical_url.split("?", 1)
        for encoded, decoded in HUBSPOT_V3_QUERY_DECODE_MAP.items():
            query = query.replace(encoded, decoded).replace(encoded.lower(), decoded)
        canonical_url = f"{path}?{query}"
    raw_string = f"POST{canonical_url}{body.decode('utf-8')}{timestamp_value}"
    signature = base64.b64encode(hmac.new(secret.encode("utf-8"), raw_string.encode("utf-8"), hashlib.sha256).digest()).decode("utf-8")
    return body, {
        "Content-Type": "application/json",
        "X-HubSpot-Signature-v3": signature,
        "X-HubSpot-Request-Timestamp": timestamp_value,
    }


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
    assert_true("risk_phrases" not in crm_payload["analysis"]["policy"], "public HubSpot card response should not expose full policy phrase lists")
    assert_true("vague_phrases" not in crm_payload["analysis"]["email_quality"]["policy"], "public email-quality payload should not expose full vague phrase lists")
    assert_true("predictions" not in crm_payload["analysis"], "HubSpot card response should not expose model prediction internals outside dev tools")
    assert_true(app_module.normalized_hubspot_asset_type("STATIC_LIST") == "OBJECT_LIST", "legacy list asset label should normalize to HubSpot Campaigns API asset type")
    assert_true(app_module.normalized_hubspot_asset_type("WORKFLOW") == "AUTOMATION_PLATFORM_FLOW", "legacy workflow label should normalize to HubSpot Campaigns API asset type")
    assert_true(app_module.normalized_hubspot_asset_type("SMS") == "MARKETING_SMS", "legacy SMS label should normalize to HubSpot Campaigns API asset type")
    assert_true(app_module.normalized_hubspot_asset_type("SOCIAL_POST") == "SOCIAL_BROADCAST", "legacy social label should normalize to HubSpot Campaigns API asset type")
    assert_true(app_module.normalized_hubspot_asset_type("CTA") == "CTA", "legacy CTA asset type should remain available for older HubSpot CTA assets")
    assert_true(app_module.normalized_hubspot_asset_type("ctas") == "WEB_INTERACTIVE", "modern CTA labels should normalize to the HubSpot web interactive asset type")
    assert_true(
        app_module.hubspot_asset_types_from_payload({"asset_types": ["MARKETING_EMAIL", "STATIC_LIST", "WORKFLOW", "SMS", "SOCIAL_POST"]})
        == ["MARKETING_EMAIL", "OBJECT_LIST", "AUTOMATION_PLATFORM_FLOW", "MARKETING_SMS", "SOCIAL_BROADCAST"],
        "HubSpot campaign review should send current Campaigns API asset type identifiers",
    )
    copy_coverage = app_module.hubspot_campaign_copy_coverage(
        {
            "MARKETING_EMAIL": {"assets": [{"status": "analyzed"}, {"status": "fetch_error"}]},
            "FORM": {"assets": [{"status": "metadata_only"}]},
            "LANDING_PAGE": {"assets": [{"status": "analyzed"}]},
        }
    )
    assert_true("MARKETING_EMAIL" in copy_coverage["direct_copy_fetch_asset_types"], "Campaign coverage should identify directly fetched marketing email assets")
    assert_true("FORM" in copy_coverage["direct_copy_fetch_asset_types"], "Campaign coverage should identify directly fetched form assets")
    assert_true("LANDING_PAGE" in copy_coverage["direct_copy_fetch_asset_types"], "Campaign coverage should identify directly fetched landing page assets")
    assert_true("FORM" in copy_coverage["metadata_only_asset_types"], "Campaign coverage should identify assets mapped without reviewable copy")
    assert_true({"MARKETING_EMAIL", "LANDING_PAGE"}.issubset(set(copy_coverage["reviewed_asset_types"])), "Campaign coverage should list asset types that were actually scored")
    assert_true(copy_coverage["coverage_score"] == 50.0, "Campaign coverage should report the percentage of assets actually scored")
    assert_true(copy_coverage["coverage_gap_assets"], "Campaign coverage should describe metadata-only gaps")
    assert_true("SEQUENCE" in app_module.HUBSPOT_DIRECT_COPY_ASSET_TYPES, "Sequences should be treated as directly fetchable when HubSpot grants automation access")
    associations, missing_associations = app_module.hubspot_analysis_record_associations(
        {"object_type": "contacts", "object_id": "101", "analysis_association_type_ids": {"contacts": 123}},
        {"object_type": "contacts", "object_id": "101"},
    )
    assert_true(associations and associations[0]["to"]["id"] == "101", "Analysis record associations should be created when real association type IDs are supplied")
    assert_true(associations[0]["types"][0]["associationTypeId"] == 123, "Analysis record associations should preserve the supplied HubSpot association type ID")
    workflow_associations, _ = app_module.hubspot_analysis_record_associations(
        {"inputFields": {"object_type": "contacts", "object_id": "202", "analysis_association_type_ids": "{\"contacts\":456}"}},
        {},
    )
    assert_true(workflow_associations and workflow_associations[0]["types"][0]["associationTypeId"] == 456, "Workflow JSON association maps should be parsed for custom-object associations")
    no_associations, missing_without_ids = app_module.hubspot_analysis_record_associations({"object_type": "contacts", "object_id": "303"}, {})
    assert_true(not no_associations and missing_without_ids, "TextTraits should not invent HubSpot association type IDs for custom-object records")

    audit_events = []
    original_access_token = hubspot_client_module.HubSpotApiClient._access_token
    original_json_request = hubspot_client_module._json_request
    original_log_event = hubspot_client_module.log_event

    def fake_access_token(self, required_scopes=()):
        return "unit-test-token"

    def fake_json_request(url, method, body=None, headers=None, timeout=20):
        assert_true(headers.get("Authorization") == "Bearer unit-test-token", "HubSpot client should send bearer token to the API")
        assert_true("secret body" in json.dumps(body or {}), "Test request body should reach the fake transport")
        return 200, {"id": "101", "ok": True}

    def fake_log_event(user_id, event_type, payload=None):
        audit_events.append({"user_id": user_id, "event_type": event_type, "payload": payload or {}})

    try:
        hubspot_client_module.HubSpotApiClient._access_token = fake_access_token
        hubspot_client_module._json_request = fake_json_request
        hubspot_client_module.log_event = fake_log_event
        api_client = hubspot_client_module.HubSpotApiClient("246356639")
        api_response = api_client.request(
            "PATCH",
            "/crm/objects/2026-03/contacts/101",
            body={"properties": {"internal_note": "secret body"}},
            required_scopes=("crm.objects.contacts.write",),
            idempotency_key="qa-idempotency-key",
        )
    finally:
        hubspot_client_module.HubSpotApiClient._access_token = original_access_token
        hubspot_client_module._json_request = original_json_request
        hubspot_client_module.log_event = original_log_event

    assert_true(api_response["status_code"] == 200, "Stubbed HubSpot API call should succeed")
    api_audit = next((event for event in audit_events if event["event_type"] == "hubspot_api_request"), None)
    assert_true(api_audit is not None, "HubSpot API client should write a safe audit event for live calls")
    assert_true(api_audit["payload"]["path"] == "/crm/objects/2026-03/contacts/{id}", "HubSpot API audit path should scrub object IDs")
    assert_true(api_audit["payload"]["required_scopes"] == ["crm.objects.contacts.write"], "HubSpot API audit should record required scopes")
    assert_true(api_audit["payload"]["idempotency_key_present"] is True, "HubSpot API audit should record idempotency presence without logging the key")
    assert_true("unit-test-token" not in json.dumps(api_audit) and "secret body" not in json.dumps(api_audit), "HubSpot API audit should not leak tokens or request bodies")

    normalized_asset = app_module.normalize_hubspot_asset_payload(
        {
            "workspace_id": "hubspot_246356639",
            "portal_id": "246356639",
            "campaign_id": "asset-campaign",
            "asset_type": "landing page",
            "asset": {
                "id": "landing-1",
                "name": "Renewal landing page",
                "html": "<h1>Renewal planning</h1><p>Please review your renewal options by Friday and choose a support tier. {{unsubscribe_link}}</p>",
            },
        }
    )
    assert_true(normalized_asset["template_id"] == "landing-1", "Generic HubSpot asset normalization should preserve the asset ID as template context")
    assert_true(normalized_asset["delivery_context"]["asset_type"] == "LANDING_PAGE", "Generic HubSpot asset normalization should preserve the normalized asset type")
    assert_true("review your renewal options" in normalized_asset["inputFields"]["email_body"], "Generic HubSpot asset normalization should extract reviewable copy")

    asset_preflight = client.post(
        "/v1/integrations/hubspot/assets/analyze",
        json={
            "workspace_id": "hubspot_246356639",
            "portal_id": "246356639",
            "campaign_id": "asset-campaign",
            "asset_type": "FORM",
            "asset": {
                "id": "form-1",
                "name": "Demo request form",
                "submitText": "Please choose a demo time by Friday and confirm the best contact email. {{unsubscribe_link}}",
            },
        },
    )
    assert_true(asset_preflight.status_code == 200, asset_preflight.get_data(as_text=True))
    asset_payload = asset_preflight.get_json()
    assert_true(asset_payload["workflow"] == "hubspot_asset_copy_preflight", "Generic HubSpot asset endpoint should return its workflow")
    assert_true(asset_payload["analysis"]["context"]["template_id"] == "form-1", "Generic HubSpot asset endpoint should preserve asset IDs for reporting")
    assert_true(asset_payload["analysis"]["context"]["delivery_context"]["asset_type"] == "FORM", "Generic HubSpot asset endpoint should preserve asset type context")
    assert_true(asset_payload["outputFields"]["texttraits_asset_type"] == "FORM", "Generic HubSpot asset endpoint should expose branchable asset type output")
    assert_true(asset_payload["outputFields"]["texttraits_asset_id"] == "form-1", "Generic HubSpot asset endpoint should expose branchable asset ID output")

    direct_fetch_urls = []

    def fake_json_request_for_get(url, method, body=None, headers=None, timeout=20):
        direct_fetch_urls.append(url)
        return 200, {"id": "asset-1", "name": "Asset", "body": "Please review this offer by Friday."}

    try:
        hubspot_client_module.HubSpotApiClient._access_token = fake_access_token
        hubspot_client_module._json_request = fake_json_request_for_get
        hubspot_client_module.log_event = fake_log_event
        api_client = hubspot_client_module.HubSpotApiClient("246356639")
        api_client.get_campaign_asset_copy("MARKETING_EMAIL", "email-1")
        api_client.get_campaign_asset_copy("FORM", "form-1")
        api_client.get_campaign_asset_copy("LANDING_PAGE", "page-1")
        api_client.get_campaign_asset_copy("SITE_PAGE", "site-1")
        api_client.get_campaign_asset_copy("BLOG_POST", "blog-1")
        api_client.list_owners({"limit": 10})
        api_client.search_lists({"query": "TextTraits", "objectTypeId": "0-1", "count": 10})
        api_client.get_lists({"listIds": ["101"]})
        api_client.get_list("101", {"includeFilters": "false"})
        api_client.get_list_memberships("101", {"limit": 25})
    finally:
        hubspot_client_module.HubSpotApiClient._access_token = original_access_token
        hubspot_client_module._json_request = original_json_request
        hubspot_client_module.log_event = original_log_event

    assert_true(any("/marketing/v3/emails/email-1" in url for url in direct_fetch_urls), "Marketing email direct copy fetch should use the documented Marketing Emails v3 path")
    assert_true(any("/marketing/v3/forms/form-1" in url for url in direct_fetch_urls), "Form direct copy fetch should use the documented Forms v3 path")
    assert_true(any("/cms/pages/2026-03/landing-pages/page-1" in url for url in direct_fetch_urls), "Landing page direct copy fetch should use the 2026-03 CMS Pages path")
    assert_true(any("/cms/pages/2026-03/site-pages/site-1" in url for url in direct_fetch_urls), "Site page direct copy fetch should use the 2026-03 CMS Pages path")
    assert_true(any("/cms/blogs/2026-03/posts/blog-1" in url for url in direct_fetch_urls), "Blog post direct copy fetch should use the 2026-03 CMS Blogs path")
    assert_true(any("/crm/owners/2026-03" in url for url in direct_fetch_urls), "Owner lookup should use HubSpot's 2026-03 Owners API path")
    assert_true(any("/crm/lists/2026-03/search" in url for url in direct_fetch_urls), "Segment search should use HubSpot's 2026-03 Lists search API path")
    assert_true(any("/crm/lists/2026-03/101/memberships" in url for url in direct_fetch_urls), "Segment membership preview should use HubSpot's 2026-03 memberships path")

    record_card = client.post(
        "/v1/integrations/hubspot/crm-card/analyze-email",
        json={
            "portal_id": "246356639",
            "inputFields": {
                "object_type": "contacts",
                "object_id": "101",
                "subject": "Factory tour review",
                "body": "Hi Brian, please review the June 3 factory tour checklist by Friday and reply with any changes.",
            },
        },
    )
    assert_true(record_card.status_code == 200, record_card.get_data(as_text=True))
    app_card_latest = client.post(
        "/v1/integrations/hubspot/app-card/latest",
        json={
            "portal_id": "246356639",
            "inputFields": {"object_type": "contacts", "object_id": "101"},
        },
    )
    assert_true(app_card_latest.status_code == 200, app_card_latest.get_data(as_text=True))
    assert_true(app_card_latest.get_json()["latest"]["request_id"] == record_card.get_json()["outputFields"]["texttraits_request_id"], "HubSpot app card should load the latest analysis for its CRM record")

    idempotent_payload = {
        "workspace_id": "hubspot_246356639",
        "idempotency_key": "qa-idempotent-email",
        "inputFields": {
            "subject": "Renewal routing check",
            "body": "Hi Brian, please review the renewal checklist by Friday and reply with the items your team wants included.",
        },
    }
    idempotent_a = client.post("/v1/integrations/hubspot/crm-card/analyze-email", json=idempotent_payload).get_json()
    idempotent_b = client.post("/v1/integrations/hubspot/crm-card/analyze-email", json=idempotent_payload).get_json()
    assert_true(idempotent_a["outputFields"]["texttraits_request_id"] == idempotent_b["outputFields"]["texttraits_request_id"], "idempotency key should produce stable HubSpot request IDs")
    idempotent_conflict = client.post(
        "/v1/integrations/hubspot/crm-card/analyze-email",
        json={
            **idempotent_payload,
            "inputFields": {
                "subject": "Renewal routing check",
                "body": "Hi Brian, this changed draft should not reuse the same idempotency key.",
            },
        },
    )
    assert_true(idempotent_conflict.status_code == 409, "same idempotency key with different content should be rejected")

    template_test = client.post(
        "/v1/integrations/hubspot/template-test",
        json={
            "inputFields": {
                "subject": "Hi {{first_name}}",
                "body": "Hi {{first_name}}, please review {{company}} at https://example.com before Friday. {{unsubscribe_link}}",
            },
            "sample_context": {"first_name": "Brian", "company": "HubSpot", "unsubscribe_link": "https://example.com/unsubscribe"},
            "headers": {"from": "marketing@example.com", "reply_to": "sales@example.com"},
        },
    )
    assert_true(template_test.status_code == 200, template_test.get_data(as_text=True))
    template_payload = template_test.get_json()["template_test"]
    assert_true(template_payload["ready"] is True, "rendered template test should pass when tokens and unsubscribe are present")
    assert_true(template_payload["rendered_subject"] == "Hi Brian", "template test should render Liquid-style tokens")

    review_event = client.post(
        "/v1/integrations/hubspot/review-action",
        json={
            "request_id": crm_payload["outputFields"]["texttraits_request_id"],
            "action": "mark_reviewed",
            "actor_id": "qa-reviewer",
            "payload": {"gate": crm_payload["outputFields"]["texttraits_gate"], "notes": "QA reviewed."},
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
    owner_id, owner_source = app_module.hubspot_owner_for_analysis(
        {"route_owner_map": {"Compliance review": "owner-compliance", "Marketing review": "owner-marketing"}},
        {"route": risky_email["outputFields"]["texttraits_route"], "gate": risky_email["outputFields"]["texttraits_gate"], "findings": risky_email["analysis"]["email_quality"]["findings"]},
        risky_email["outputFields"],
    )
    assert_true(owner_id == "owner-compliance" and owner_source.startswith("route:"), "HubSpot review tasks should resolve owner IDs from configured TextTraits route maps")
    default_owner_id, default_owner_source = app_module.hubspot_owner_for_analysis(
        {"default_hubspot_owner_id": "owner-default"},
        {"route": "Unknown queue", "gate": "needs_review", "findings": []},
        {},
    )
    assert_true(default_owner_id == "owner-default" and default_owner_source == "default", "HubSpot review tasks should support a configured fallback owner without hardcoded IDs")
    routing_config = client.post(
        "/v1/integrations/hubspot/review-routing/config",
        json={
            "portal_id": "246356639",
            "workspace_id": "hubspot_246356639",
            "route_owner_map": {"Compliance review": "owner-compliance-db", "Marketing review": "owner-marketing-db"},
            "default_owner_id": "owner-default-db",
            "action": "save",
        },
    )
    assert_true(routing_config.status_code == 200, routing_config.get_data(as_text=True))
    routed_owner_id, routed_owner_source = app_module.hubspot_owner_for_analysis(
        {"portal_id": "246356639", "workspace_id": "hubspot_246356639"},
        {"route": "Compliance review", "gate": "blocked", "findings": []},
        {},
    )
    assert_true(routed_owner_id == "owner-compliance-db" and routed_owner_source.startswith("route:"), "Saved HubSpot review routing should assign compliance tasks without per-request owner maps")
    stored_default_owner_id, stored_default_owner_source = app_module.hubspot_owner_for_analysis(
        {"portal_id": "246356639", "workspace_id": "hubspot_246356639"},
        {"route": "Unmapped route", "gate": "needs_review", "findings": []},
        {},
    )
    assert_true(stored_default_owner_id == "owner-default-db" and stored_default_owner_source == "default", "Saved HubSpot review routing should provide a fallback owner")
    approve_review = client.post(
        "/v1/integrations/hubspot/review-action",
        json={
            "request_id": risky_email["outputFields"]["texttraits_request_id"],
            "action": "approve_review",
            "actor_id": "qa-approver",
            "payload": {"notes": "Approved after QA check.", "owner_queue": risky_email["outputFields"]["texttraits_route"]},
        },
    )
    assert_true(approve_review.status_code == 200, approve_review.get_data(as_text=True))
    assert_true(approve_review.get_json()["event"]["action"] == "approve_review", "HubSpot approval review action should be recorded")

    approval_sync_urls = []
    approval_sync_bodies = []

    def fake_json_request_for_approval_sync(url, method, body=None, headers=None, timeout=20):
        approval_sync_urls.append(f"{method} {url}")
        approval_sync_bodies.append(body or {})
        if "/crm/objects/2026-03/2-123456/search" in url:
            return 200, {"results": [{"id": "analysis-record-1", "properties": {"texttraits_request_id": record_card.get_json()["outputFields"]["texttraits_request_id"]}}]}
        return 200, {"id": "synced", "properties": (body or {}).get("properties", {})}

    try:
        with storage_module.connect() as conn:
            storage_module.execute(
                conn,
                """
                INSERT INTO hubspot_portal_tokens (
                  portal_id, hub_domain, account_name, access_token_encrypted, refresh_token_encrypted,
                  scopes, token_type, expires_at, status, installed_by, connected_at, updated_at, disconnected_at
                )
                VALUES (?, ?, ?, '', '', ?, 'bearer', '', 'connected', ?, ?, ?, '')
                ON CONFLICT(portal_id) DO UPDATE SET scopes = excluded.scopes, status = excluded.status, updated_at = excluded.updated_at
                """,
                (
                    "246356639",
                    "qa.example.com",
                    "QA Portal",
                    json.dumps(["crm.objects.contacts.write", "crm.objects.custom.read", "crm.objects.custom.write"]),
                    "qa-approver@example.com",
                    storage_module.utc_now(),
                    storage_module.utc_now(),
                ),
            )
        hubspot_client_module.HubSpotApiClient._access_token = fake_access_token
        hubspot_client_module._json_request = fake_json_request_for_approval_sync
        hubspot_client_module.log_event = fake_log_event
        synced_approval = client.post(
            "/v1/integrations/hubspot/review-action",
            json={
                "portal_id": "246356639",
                "request_id": record_card.get_json()["outputFields"]["texttraits_request_id"],
                "action": "approve_review",
                "actor_id": "qa-approver@example.com",
                "object_type": "contacts",
                "object_id": "101",
                "task_id": "task-101",
                "analysis_object_type": "2-123456",
                "sync_hubspot": True,
                "payload": {"notes": "Approved and synced.", "owner_queue": "Marketing review"},
            },
        )
    finally:
        hubspot_client_module.HubSpotApiClient._access_token = original_access_token
        hubspot_client_module._json_request = original_json_request
        hubspot_client_module.log_event = original_log_event
        storage_module.disconnect_hubspot_portal("246356639", actor="qa-approval-sync-cleanup")

    assert_true(synced_approval.status_code == 200, synced_approval.get_data(as_text=True))
    approval_sync = synced_approval.get_json()["sync"]
    approval_actions = {item["action"] for item in approval_sync["actions"]}
    assert_true({"review_crm_property_writeback", "review_task_updated", "analysis_object_review_state_updated"}.issubset(approval_actions), "Approval review actions should sync CRM properties, task state, and analysis object state")
    assert_true(any("/crm/objects/2026-03/tasks/task-101" in url for url in approval_sync_urls), "Approval sync should update the HubSpot review task when task_id is supplied")
    assert_true(any("/crm/objects/2026-03/2-123456/search" in url for url in approval_sync_urls), "Approval sync should search for the existing TextTraits Analysis custom-object record")
    assert_true(any((body.get("properties") or {}).get("texttraits_review_status") == "approved" for body in approval_sync_bodies), "Approval sync should write approved review status to HubSpot properties")

    reject_review = client.post(
        "/v1/integrations/hubspot/review-action",
        json={
            "request_id": unclear_email["outputFields"]["texttraits_request_id"],
            "action": "reject_review",
            "actor_id": "qa-rejector",
            "payload": {"notes": "Rejected because the draft lacks reviewable content.", "owner_queue": unclear_email["outputFields"]["texttraits_route"]},
        },
    )
    assert_true(reject_review.status_code == 200, reject_review.get_data(as_text=True))
    approved_states = client.get("/api/enterprise/hubspot/review-states?status=approved")
    rejected_states = client.get("/api/enterprise/hubspot/review-states?status=rejected")
    assert_true(approved_states.status_code == 200 and approved_states.get_json()["review_states"], "approved review states should be queryable")
    assert_true(rejected_states.status_code == 200 and rejected_states.get_json()["review_states"], "rejected review states should be queryable")

    policy_update = client.put(
        "/api/enterprise/hubspot/policy",
        json={
            "workspace_id": "hubspot_246356639",
            "environment": "production",
            "policy": {
                "version": "qa-policy",
                "rule_pack": "finance",
                "ready_score_threshold": 75,
                "review_score_threshold": 60,
                "block_score_threshold": 20,
                "block_if_no_cta": False,
                "block_high_severity_findings": False,
                "compliance_review_on_risk_terms": True,
                "require_personalization": False,
                "min_body_words": 20,
                "max_body_words": 240,
                "custom_risk_phrases": ["nonrefundable"],
                "custom_vague_phrases": ["next-level"],
                "required_template_tokens": ["first_name", "unsubscribe_link"],
                "required_headers": ["from", "reply_to"],
            },
        },
        headers=csrf_headers(client),
    )
    assert_true(policy_update.status_code == 200, policy_update.get_data(as_text=True))
    policy_get = client.get("/api/enterprise/hubspot/policy?workspace_id=hubspot_246356639")
    assert_true(policy_get.get_json()["policy"]["version"] == "qa-policy", "HubSpot policy should persist")
    assert_true(policy_get.get_json()["policy"]["rule_pack"] == "finance", "HubSpot policy should persist rule pack")
    assert_true("finance" in {item["id"] for item in policy_get.get_json()["rule_packs"]}, "policy response should expose supported rule packs")

    template_policy_check = client.post(
        "/v1/integrations/hubspot/template-test",
        json={
            "workspace_id": "hubspot_246356639",
            "inputFields": {
                "subject": "Renewal plan",
                "body": "Please review the renewal plan. {{unsubscribe_link}}",
            },
            "sample_context": {"unsubscribe_link": "https://example.com/unsubscribe"},
            "headers": {"from": "qa@example.com", "reply_to": "sales@example.com"},
        },
    )
    assert_true(template_policy_check.status_code == 200, template_policy_check.get_data(as_text=True))
    template_policy_json = template_policy_check.get_json()["template_test"]
    assert_true(template_policy_json["ready"] is False, "template test should enforce policy-required tokens")
    assert_true("first_name" in template_policy_json["missing_required_tokens"], "finance policy token requirement should be visible")

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

    finance_risky = client.post(
        "/v1/integrations/hubspot/crm-card/analyze-email",
        json={
            "workspace_id": "hubspot_246356639",
            "inputFields": {
                "subject": "Investment review",
                "body": "Hi Brian, this is a risk-free investment with no downside for your team. Please review the plan by Friday.",
            },
        },
    ).get_json()
    assert_true(finance_risky["outputFields"]["texttraits_gate"] == "blocked", "finance rule pack should block financial risk language")
    assert_true(finance_risky["analysis"]["policy"]["rule_pack_label"] == "Financial services", "analysis should expose active rule-pack label")

    workflow_action = client.post(
        "/v1/integrations/hubspot/workflow-actions/analyze-email",
        json={
            "inputFields": {
                "email_subject": "Renewal workflow follow-up",
                "email_body": "Check this message before the automated renewal sequence continues.",
                "workflow_name": "QA renewal workflow",
            },
        },
    )
    assert_true(workflow_action.status_code == 200, workflow_action.get_data(as_text=True))
    assert_true(workflow_action.get_json()["workflow"] == "hubspot_workflow_action", "HubSpot workflow action endpoint should remain available")
    assert_true(workflow_action.get_json()["analysis"]["context"]["campaign_id"] == "QA renewal workflow", "workflow aliases should map campaign context")

    asset_copy_workflow_action = client.post(
        "/v1/integrations/hubspot/workflow-actions/analyze-asset-copy",
        json={
            "inputFields": {
                "asset_type": "FORM",
                "asset_id": "demo-form",
                "asset_name": "Demo request form",
                "asset_copy": "Please choose a demo time by Friday and confirm the best contact email. {{unsubscribe_link}}",
                "campaign_id": "asset-campaign",
                "analysis_mode": "asset_copy_workflow_gate",
            },
        },
    )
    assert_true(asset_copy_workflow_action.status_code == 200, asset_copy_workflow_action.get_data(as_text=True))
    asset_copy_workflow_payload = asset_copy_workflow_action.get_json()
    assert_true(asset_copy_workflow_payload["workflow"] == "hubspot_asset_copy_workflow_action", "HubSpot asset copy workflow action endpoint should return a workflow-specific telemetry label")
    assert_true(asset_copy_workflow_payload["analysis"]["context"]["analysis_mode"] == "asset_copy_workflow_gate", "HubSpot asset copy workflow action should preserve workflow analysis mode")
    assert_true(asset_copy_workflow_payload["outputFields"]["texttraits_asset_name"] == "Demo request form", "HubSpot asset copy workflow action should expose branchable asset name output")

    marketing_email = client.post(
        "/v1/integrations/hubspot/marketing-emails/analyze",
        json={
            "workspace_id": "hubspot_246356639",
            "portal_id": "246356639",
            "marketingEmail": {
                "id": "marketing-email-42",
                "subject": "Factory tour confirmation",
                "html": "<p>Hi {{first_name}}, please confirm the June 3 factory tour by Friday. {{unsubscribe_link}}</p>",
                "campaignId": "factory-tour-campaign",
                "fromEmail": "marketing@example.com",
                "replyTo": "reply@example.com",
                "state": "DRAFT",
            },
        },
    )
    assert_true(marketing_email.status_code == 200, marketing_email.get_data(as_text=True))
    marketing_payload = marketing_email.get_json()
    assert_true(marketing_payload["workflow"] == "hubspot_marketing_email_preflight", "Marketing email endpoint should use the marketing preflight workflow")
    assert_true(marketing_payload["analysis"]["context"]["source_system"] == "hubspot_marketing_email", "Marketing emails should preserve source-system context")
    assert_true(marketing_payload["analysis"]["context"]["campaign_id"] == "factory-tour-campaign", "Marketing email campaign ID should map into context")
    assert_true(marketing_payload["analysis"]["context"]["template_id"] == "marketing-email-42", "Marketing email ID should be preserved as template context")

    stats_urls = []

    def fake_json_request_for_stats(url, method, body=None, headers=None, timeout=20):
        stats_urls.append(url)
        if "/marketing/v3/campaigns/factory-tour-campaign/assets/MARKETING_EMAIL" in url:
            return 200, {"results": [{"id": "marketing-email-42", "name": "Factory tour confirmation"}]}
        if "/marketing/v3/emails/marketing-email-42" in url:
            return 200, {"id": "marketing-email-42", "name": "Factory tour confirmation", "stats": {"delivered": 120, "opened": 73, "clicked": 18}}
        if "/marketing/v3/campaigns/factory-tour-campaign" in url:
            return 200, {"id": "factory-tour-campaign", "name": "Factory Tour", "stats": {"sent": 120, "opened": 73}}
        return 200, {"ok": True}

    try:
        hubspot_client_module.HubSpotApiClient._access_token = fake_access_token
        hubspot_client_module._json_request = fake_json_request_for_stats
        hubspot_client_module.log_event = fake_log_event
        stats_sync = client.post(
            "/v1/integrations/hubspot/stats/sync",
            json={
                "workspace_id": "hubspot_246356639",
                "portal_id": "246356639",
                "campaign_id": "factory-tour-campaign",
                "asset_types": ["MARKETING_EMAIL"],
                "limit": 1,
            },
        )
    finally:
        hubspot_client_module.HubSpotApiClient._access_token = original_access_token
        hubspot_client_module._json_request = original_json_request
        hubspot_client_module.log_event = original_log_event

    assert_true(stats_sync.status_code == 200, stats_sync.get_data(as_text=True))
    stats_payload = stats_sync.get_json()
    snapshot_kinds = {item["kind"] for item in stats_payload["snapshots"]}
    assert_true({"campaign", "campaign_assets", "campaign_marketing_email"}.issubset(snapshot_kinds), "Stats sync should fetch campaign metadata, campaign assets, and marketing email stats")
    assert_true(any("/marketing/v3/emails/marketing-email-42" in url for url in stats_urls), "Stats sync should fetch campaign email asset details")
    assert_true(any(event["request_id"] == marketing_payload["outputFields"]["texttraits_request_id"] for event in stats_payload["outcome_events"]), "Stats sync should join campaign email performance back to the matching TextTraits analysis")

    segment_urls = []

    def fake_json_request_for_segments(url, method, body=None, headers=None, timeout=20):
        segment_urls.append(f"{method} {url}")
        if "/crm/lists/2026-03/search" in url:
            return 200, {
                "lists": [
                    {
                        "listId": "101",
                        "name": "TextTraits Needs Review",
                        "objectTypeId": "0-1",
                        "processingType": "DYNAMIC",
                        "listSize": 7,
                    }
                ],
                "paging": {},
            }
        if "/crm/lists/2026-03/101/memberships" in url:
            return 200, {"results": [{"recordId": "123", "membershipTimestamp": "2026-07-05T00:00:00Z"}]}
        if "/crm/lists/2026-03/101/memberships/add-and-remove" in url:
            assert_true(body == {"recordIdsToAdd": ["456", "789"], "recordIdsToRemove": ["123"]}, "Segment membership update should pass add/remove record IDs through")
            return 200, {"updated": True}
        return 200, {}

    try:
        hubspot_client_module.HubSpotApiClient._access_token = fake_access_token
        hubspot_client_module._json_request = fake_json_request_for_segments
        hubspot_client_module.log_event = fake_log_event
        segment_search = client.post(
            "/v1/integrations/hubspot/lists/search",
            json={"portal_id": "246356639", "query": "TextTraits", "objectTypeId": "0-1", "processingTypes": ["DYNAMIC"], "limit": 10},
        )
        segment_members = client.post(
            "/v1/integrations/hubspot/lists/memberships",
            json={"portal_id": "246356639", "list_id": "101", "limit": 25},
        )
        segment_update = client.post(
            "/v1/integrations/hubspot/lists/memberships/update",
            json={"portal_id": "246356639", "list_id": "101", "recordIdsToAdd": ["456", "789"], "recordIdsToRemove": ["123"]},
        )
    finally:
        hubspot_client_module.HubSpotApiClient._access_token = original_access_token
        hubspot_client_module._json_request = original_json_request
        hubspot_client_module.log_event = original_log_event

    assert_true(segment_search.status_code == 200, segment_search.get_data(as_text=True))
    segment_payload = segment_search.get_json()
    assert_true(segment_payload["lists"][0]["list_id"] == "101", "HubSpot segment search should normalize list IDs for UI selection")
    assert_true(segment_payload["lists"][0]["processing_type"] == "DYNAMIC", "HubSpot segment search should preserve processing type")
    assert_true(segment_members.status_code == 200, segment_members.get_data(as_text=True))
    assert_true(segment_members.get_json()["memberships"][0]["recordId"] == "123", "HubSpot segment membership preview should expose member record IDs")
    assert_true(segment_update.status_code == 200, segment_update.get_data(as_text=True))
    assert_true(segment_update.get_json()["details"]["operation"] == "add_and_remove", "HubSpot segment membership update should support add-and-remove operations")
    assert_true(any("POST" in url and "/crm/lists/2026-03/search" in url for url in segment_urls), "Segment search endpoint should call HubSpot's Lists search API")
    assert_true(any("PUT" in url and "/crm/lists/2026-03/101/memberships/add-and-remove" in url for url in segment_urls), "Segment update endpoint should call HubSpot's list add-and-remove API")

    campaign_preflight = client.post(
        "/v1/integrations/hubspot/campaigns/analyze",
        json={
            "workspace_id": "hubspot_246356639",
            "portal_id": "246356639",
            "campaign": {"id": "campaign-q3", "name": "Q3 lifecycle campaign"},
            "emails": [
                {
                    "id": "email-ready",
                    "revision_id": "r1",
                    "subject": "Factory tour checklist",
                    "html": "<p>Hi Brian, please review the June 3 factory tour checklist by Friday and reply with any changes. {{unsubscribe_link}}</p>",
                },
                {
                    "id": "email-risk",
                    "revision_id": "r1",
                    "subject": "Guaranteed results",
                    "html": "<p>Hi Brian, this plan is guaranteed to save 100% of your team's time. Please approve today.</p>",
                },
            ],
        },
    )
    assert_true(campaign_preflight.status_code == 200, campaign_preflight.get_data(as_text=True))
    campaign_payload = campaign_preflight.get_json()
    assert_true(campaign_payload["summary"]["analyzed"] == 2, "Campaign preflight should analyze each supplied email asset")
    assert_true(campaign_payload["summary"]["campaign_id"] == "campaign-q3", "Campaign preflight should preserve campaign context")
    assert_true(campaign_payload["summary"]["gate_counts"].get("blocked", 0) >= 1, "Campaign preflight should surface risky campaign assets")

    outcome = client.post(
        "/v1/integrations/hubspot/outcomes",
        json={
            "request_id": crm_payload["outputFields"]["texttraits_request_id"],
            "content_hash": crm_payload["outputFields"]["texttraits_content_hash"],
            "workspace_id": "hubspot_246356639",
            "event_type": "opened",
            "event_id": "qa-opened-1",
            "payload": {"campaign": "qa"},
        },
    )
    assert_true(outcome.status_code == 200, outcome.get_data(as_text=True))
    invalid_outcome = client.post("/v1/integrations/hubspot/outcomes", json={"request_id": crm_payload["outputFields"]["texttraits_request_id"]})
    assert_true(invalid_outcome.status_code == 400, "invalid outcome payload should fail cleanly instead of raising an internal error")

    analyses = client.get("/api/enterprise/hubspot/analyses?workspace_id=hubspot_246356639")
    assert_true(analyses.status_code == 200, analyses.get_data(as_text=True))
    assert_true(len(analyses.get_json()["analyses"]) >= 3, "HubSpot analyses should persist for reporting")
    assert_true(analyses.get_json()["review_states"], "HubSpot review states should be queryable")
    findings = client.get("/api/enterprise/hubspot/findings?severity=high")
    assert_true(findings.status_code == 200 and findings.get_json()["findings"], "normalized findings endpoint should return queryable rows")
    checks = client.get("/api/enterprise/hubspot/checks?status=blocked")
    assert_true(checks.status_code == 200 and checks.get_json()["checks"], "normalized checks endpoint should return queryable rows")
    review_states = client.get("/api/enterprise/hubspot/review-states?status=resolved")
    assert_true(review_states.status_code == 200 and review_states.get_json()["review_states"], "review state endpoint should show resolved reviews")
    outcomes = client.get(f"/api/enterprise/hubspot/outcomes?request_id={crm_payload['outputFields']['texttraits_request_id']}")
    assert_true(outcomes.status_code == 200 and outcomes.get_json()["events"], "outcome events should join back by request_id")
    bulk_asset_import = client.post(
        "/v1/integrations/hubspot/bulk/import-assets",
        json={
            "portal_id": "246356639",
            "campaign_id": "campaign-q3",
            "import_id": "qa-import-1",
            "csv_text": 'asset_type,asset_id,asset_name,asset_copy,region,business_unit,audience_type\nMARKETING_SMS,sms-1,QA SMS,"Hi Brian, reply by Friday for details on job JR-204. {{unsubscribe_link}}",US,Staffing,candidate',
        },
    )
    assert_true(bulk_asset_import.status_code == 200, bulk_asset_import.get_data(as_text=True))
    assert_true(bulk_asset_import.get_json()["summary"]["coverage"]["coverage_score"] == 100.0, "Bulk asset import should report full coverage for scored mapped copy")
    salesforce_import = client.post(
        "/v1/integrations/hubspot/salesforce/outcomes/import",
        json={
            "portal_id": "246356639",
            "workspace_id": "hubspot_246356639",
            "events": [
                {
                    "event_type": "placement_created",
                    "salesforce_campaign_id": "701-demo",
                    "salesforce_opportunity_id": "006-demo",
                    "audience_type": "client",
                    "region": "US",
                    "skill_family": "Logistics",
                }
            ],
        },
    )
    assert_true(salesforce_import.status_code == 200 and salesforce_import.get_json()["events"], "Mapped Salesforce outcomes should import without fake Salesforce credentials")
    dashboard = client.get("/api/enterprise/hubspot/dashboard")
    assert_true(dashboard.status_code == 200, dashboard.get_data(as_text=True))
    assert_true("top_failed_checks" in dashboard.get_json()["dashboard"], "HubSpot dashboard should include failed-check rollups")
    assert_true(dashboard.get_json()["dashboard"]["outcome_counts"].get("opened", 0) >= 1, "HubSpot dashboard should include outcome joins")
    dashboard_payload = dashboard.get_json()["dashboard"]
    assert_true("campaign_health" in dashboard_payload, "HubSpot dashboard should include campaign-health rollups")
    assert_true("template_health" in dashboard_payload, "HubSpot dashboard should include template-health rollups")
    assert_true("source_health" in dashboard_payload, "HubSpot dashboard should include source trend rollups")
    assert_true("outcome_rates" in dashboard_payload, "HubSpot dashboard should include outcome-rate rollups")
    assert_true("blocked_by_region" in dashboard_payload, "HubSpot dashboard should include blocked-by-region rollups")
    assert_true("risky_claim_types" in dashboard_payload, "HubSpot dashboard should include risky-claim rollups")
    assert_true("review_sla" in dashboard_payload, "HubSpot dashboard should include review SLA rollups")
    assert_true("send_ready_by_business_unit" in dashboard_payload, "HubSpot dashboard should include business-unit readiness rollups")
    assert_true("outcome_by_audience_segment" in dashboard_payload, "HubSpot dashboard should include audience-segment outcome rollups")
    home_bootstrap = client.get("/api/enterprise/hubspot/home-bootstrap")
    home_bootstrap_payload = home_bootstrap.get_json()
    assert_true(home_bootstrap.status_code == 200, "HubSpot home bootstrap should load in one request")
    assert_true("dashboard" in home_bootstrap_payload and "readiness" in home_bootstrap_payload, "HubSpot home bootstrap should combine dashboard and readiness data")
    assert_true(home_bootstrap_payload["templates"], "HubSpot home bootstrap should include staffing workflow templates")
    staffing_templates = client.get("/api/enterprise/hubspot/staffing-workflow-templates")
    assert_true(staffing_templates.status_code == 200, staffing_templates.get_data(as_text=True))
    template_ids = {item["id"] for item in staffing_templates.get_json()["templates"]}
    assert_true({"candidate_nurture", "job_alert", "passive_candidate_reactivation", "client_hiring_campaign", "regional_lead_routing"}.issubset(template_ids), "Staffing workflow templates should cover core Randstad-style flows")
    policy_response = client.get("/api/enterprise/hubspot/policy")
    assert_true(policy_response.status_code == 200, policy_response.get_data(as_text=True))
    rule_pack_ids = {item["id"] for item in policy_response.get_json()["rule_packs"]}
    assert_true({"staffing_general", "staffing_us", "staffing_eu", "staffing_apac", "healthcare_staffing", "finance_staffing", "public_sector_staffing"}.issubset(rule_pack_ids), "Policy packs should include staffing, regional, and regulated-sector variants")
    approval_templates = client.get("/api/enterprise/hubspot/approval-chain-templates")
    assert_true(approval_templates.status_code == 200 and approval_templates.get_json()["approval_chains"], "Approval chain templates should be available to admins")
    setup_wizard = client.get("/api/enterprise/hubspot/setup-wizard")
    assert_true(setup_wizard.status_code == 200 and setup_wizard.get_json()["steps"], "HubSpot setup wizard should expose admin setup steps")
    settings_bootstrap = client.get("/api/enterprise/hubspot/settings-bootstrap?portal_id=246356639")
    settings_bootstrap_payload = settings_bootstrap.get_json()
    assert_true(settings_bootstrap.status_code == 200, "HubSpot settings bootstrap should load in one request")
    assert_true(settings_bootstrap_payload["surfaces"] and settings_bootstrap_payload["setup_steps"], "HubSpot settings bootstrap should include surfaces and setup steps")
    assert_true("connections" in settings_bootstrap_payload and "token_storage" in settings_bootstrap_payload, "HubSpot settings bootstrap should include connection readiness")
    randstad_readiness = client.get("/api/enterprise/hubspot/randstad-readiness")
    assert_true(randstad_readiness.status_code == 200 and randstad_readiness.get_json()["readiness"]["overall_usefulness_score"] >= 8, "Randstad-style readiness report should rate the installed integration")
    surfaces = client.get("/api/enterprise/hubspot/surfaces")
    assert_true(surfaces.status_code == 200, surfaces.get_data(as_text=True))
    surfaces_payload = surfaces.get_json()
    surface_items = surfaces_payload["surfaces"]
    surface_ids = {item["id"] for item in surface_items}
    assert_true(
        {
            "marketing_email_preflight",
            "campaign_preflight",
            "analyze_and_sync",
            "workflow_action",
            "asset_copy_workflow_action",
            "crm_record_card",
            "campaign_create_update",
            "campaign_picker",
            "campaign_asset_association",
            "marketing_email_pre_publish_guardrail",
            "marketing_email_draft_sync",
            "marketing_email_picker",
            "asset_copy_preflight",
            "live_asset_copy_review",
            "bulk_asset_import",
            "salesforce_outcome_mapping",
            "owner_directory",
            "review_route_owner_mapping",
            "staffing_workflow_templates",
            "approval_chain_templates",
            "hubspot_setup_wizard",
            "review_task_creation",
            "approval_workflow_sync",
            "crm_property_writeback",
            "analysis_custom_object",
            "timeline_events",
            "lists_segments",
            "lists_segments_search",
            "review_segment_templates",
            "webhook_sync",
            "stats_sync",
            "live_campaign_review",
            "app_uninstall_cleanup",
            "crm_property_provisioning",
            "analysis_schema_provisioning",
            "webhook_management",
        }.issubset(surface_ids),
        "HubSpot surface registry should cover marketing, campaign, workflow, CRM card, setup, writeback, tasks, lists, webhooks, and stats use cases",
    )
    live_campaign_surface = next(item for item in surface_items if item["id"] == "live_campaign_review")
    assert_true("marketing.campaigns.read" in live_campaign_surface["required_scopes"], "Live campaign review should expose required HubSpot Campaigns scope")
    assert_true("marketing-email" in live_campaign_surface["recommended_scopes"], "Live campaign review should recommend Marketing Email scope for real copy scoring")
    live_asset_surface = next(item for item in surface_items if item["id"] == "live_asset_copy_review")
    assert_true("forms" in live_asset_surface["recommended_scopes"], "Live asset copy review should recommend Forms scope for direct form scoring")
    assert_true("content" in live_asset_surface["recommended_scopes"], "Live asset copy review should recommend Content scope for direct CMS scoring")
    assert_true("token_storage" in surfaces_payload and "ready" in surfaces_payload["token_storage"], "HubSpot surface registry should expose token-storage readiness")

    hubspot_project = ROOT / "hubspot-project"
    project_files = [
        "hsproject.json",
        "src/app/app-hsmeta.json",
        "src/app/cards/texttraits-email-fit-card-hsmeta.json",
        "src/app/cards/TextTraitsEmailFitCard.jsx",
        "src/app/workflow-actions/texttraits-analyze-email-hsmeta.json",
        "src/app/workflow-actions/texttraits-analyze-asset-copy-hsmeta.json",
        "src/app/workflow-actions/texttraits-analyze-and-sync-hsmeta.json",
        "src/app/workflow-actions/texttraits-review-campaign-assets-hsmeta.json",
        "src/app/settings/texttraits-settings-hsmeta.json",
        "src/app/home/texttraits-home-hsmeta.json",
    ]
    for relative_path in project_files:
        project_file = hubspot_project / relative_path
        assert_true(project_file.exists(), f"HubSpot project file missing: {relative_path}")
        if project_file.suffix == ".json":
            json.loads(project_file.read_text())
    workflow_definition = json.loads((hubspot_project / "src/app/workflow-actions/texttraits-analyze-email-hsmeta.json").read_text())
    output_names = {field["name"] for field in workflow_definition["config"]["outputFields"]}
    assert_true({"texttraits_score", "texttraits_gate", "texttraits_route", "texttraits_blocker_reason", "texttraits_request_id", "texttraits_content_hash"}.issubset(output_names), "HubSpot workflow action should expose branchable TextTraits output fields")
    synced_workflow_definition = json.loads((hubspot_project / "src/app/workflow-actions/texttraits-analyze-and-sync-hsmeta.json").read_text())
    synced_input_names = {field["typeDefinition"]["name"] for field in synced_workflow_definition["config"]["inputFields"]}
    assert_true("analysis_association_type_ids" in synced_input_names, "HubSpot synced workflow action should allow association type ID configuration for analysis custom objects")
    synced_output_names = {field["name"] for field in synced_workflow_definition["config"]["outputFields"]}
    assert_true({"texttraits_score", "texttraits_gate", "texttraits_sync_status", "texttraits_sync_actions"}.issubset(synced_output_names), "HubSpot synced workflow action should expose sync status output fields")
    asset_copy_workflow_definition = json.loads((hubspot_project / "src/app/workflow-actions/texttraits-analyze-asset-copy-hsmeta.json").read_text())
    assert_true("/v1/integrations/hubspot/workflow-actions/analyze-asset-copy" in asset_copy_workflow_definition["config"]["actionUrl"], "HubSpot asset copy workflow action should target the workflow asset copy endpoint")
    asset_copy_input_names = {field["typeDefinition"]["name"] for field in asset_copy_workflow_definition["config"]["inputFields"]}
    assert_true({"asset_type", "asset_id", "asset_name", "asset_copy", "campaign_id", "analysis_mode"}.issubset(asset_copy_input_names), "HubSpot asset copy workflow action should expose mapped asset-copy inputs")
    asset_copy_output_names = {field["name"] for field in asset_copy_workflow_definition["config"]["outputFields"]}
    assert_true({"texttraits_score", "texttraits_gate", "texttraits_route", "texttraits_asset_type", "texttraits_asset_id", "texttraits_asset_name", "texttraits_request_id"}.issubset(asset_copy_output_names), "HubSpot asset copy workflow action should expose branchable asset and routing outputs")
    campaign_workflow_definition = json.loads((hubspot_project / "src/app/workflow-actions/texttraits-review-campaign-assets-hsmeta.json").read_text())
    assert_true("/v1/integrations/hubspot/workflow-actions/review-campaign-assets" in campaign_workflow_definition["config"]["actionUrl"], "HubSpot campaign workflow action should target the campaign asset review endpoint")
    campaign_output_names = {field["name"] for field in campaign_workflow_definition["config"]["outputFields"]}
    assert_true({"texttraits_campaign_health", "texttraits_gate", "texttraits_route", "texttraits_analyzed_count", "texttraits_blocked_count", "texttraits_copy_coverage"}.issubset(campaign_output_names), "HubSpot campaign workflow action should expose branchable campaign health and copy coverage fields")
    assert_true({"texttraits_coverage_score", "texttraits_coverage_label"}.issubset(campaign_output_names), "HubSpot campaign workflow action should expose coverage score output fields")

    live_action_payloads = {
        "/v1/integrations/hubspot/analyze-and-sync": {"portal_id": "246356639", "inputFields": {"email_subject": "QA subject", "email_body": "Please review the renewal terms by Friday. {{unsubscribe_link}}"}, "object_type": "contacts", "object_id": "101"},
        "/v1/integrations/hubspot/workflow-actions/review-campaign-assets": {"portal_id": "246356639", "campaign_id": "campaign-guid", "asset_types": "MARKETING_EMAIL,FORM,OBJECT_LIST", "limit": 5},
        "/v1/integrations/hubspot/campaigns/create": {"portal_id": "246356639", "name": "QA campaign"},
        "/v1/integrations/hubspot/campaigns/update": {"portal_id": "246356639", "campaign_id": "campaign-guid", "properties": {"hs_name": "QA campaign updated"}},
        "/v1/integrations/hubspot/campaigns/list": {"portal_id": "246356639", "query": "QA", "limit": 5},
        "/v1/integrations/hubspot/campaigns/associate-asset": {"portal_id": "246356639", "campaign_id": "campaign-guid", "asset_type": "MARKETING_EMAIL", "asset_id": "123"},
        "/v1/integrations/hubspot/campaigns/assets": {"portal_id": "246356639", "campaign_id": "campaign-guid", "asset_type": "MARKETING_EMAIL"},
        "/v1/integrations/hubspot/campaigns/review": {"portal_id": "246356639", "campaign_id": "campaign-guid", "asset_types": ["MARKETING_EMAIL", "FORM", "LANDING_PAGE", "WEB_INTERACTIVE", "AUTOMATION_PLATFORM_FLOW", "OBJECT_LIST"]},
        "/v1/integrations/hubspot/marketing-emails/create-draft": {"portal_id": "246356639", "name": "QA email", "subject": "QA subject", "templatePath": "@hubspot/email/dnd/welcome.html"},
        "/v1/integrations/hubspot/marketing-emails/update-draft": {"portal_id": "246356639", "email_id": "123", "subject": "Updated subject"},
        "/v1/integrations/hubspot/marketing-emails/fetch": {"portal_id": "246356639", "email_id": "123"},
        "/v1/integrations/hubspot/marketing-emails/pre-publish-guardrail": {"portal_id": "246356639", "email_id": "123"},
        "/v1/integrations/hubspot/marketing-emails/list": {"portal_id": "246356639", "query": "QA", "limit": 5},
        "/v1/integrations/hubspot/owners/list": {"portal_id": "246356639", "limit": 10},
        "/v1/integrations/hubspot/assets/fetch-and-analyze": {"portal_id": "246356639", "asset_type": "FORM", "asset_id": "form-123"},
        "/v1/integrations/hubspot/tasks/create-review": {"portal_id": "246356639", "request_id": crm_payload["outputFields"]["texttraits_request_id"]},
        "/v1/integrations/hubspot/properties/writeback": {"portal_id": "246356639", "request_id": record_card.get_json()["outputFields"]["texttraits_request_id"], "object_type": "contacts", "object_id": "101"},
        "/v1/integrations/hubspot/properties/provision": {"portal_id": "246356639", "object_types": ["contacts"]},
        "/v1/integrations/hubspot/analysis-records/create": {"portal_id": "246356639", "request_id": crm_payload["outputFields"]["texttraits_request_id"], "object_type": "2-123456"},
        "/v1/integrations/hubspot/analysis-schema/provision": {"portal_id": "246356639"},
        "/v1/integrations/hubspot/timeline-events/create": {"portal_id": "246356639", "request_id": crm_payload["outputFields"]["texttraits_request_id"], "app_id": "1160452", "eventTemplateId": "texttraits_review", "objectId": "101"},
        "/v1/integrations/hubspot/lists/create": {"portal_id": "246356639", "name": "TextTraits QA review list", "objectTypeId": "0-1", "processingType": "MANUAL"},
        "/v1/integrations/hubspot/lists/search": {"portal_id": "246356639", "query": "TextTraits", "objectTypeId": "0-1", "limit": 5},
        "/v1/integrations/hubspot/lists/memberships": {"portal_id": "246356639", "list_id": "101", "limit": 5},
        "/v1/integrations/hubspot/lists/create-review-segments": {"portal_id": "246356639", "objectTypeId": "0-1"},
        "/v1/integrations/hubspot/stats/sync": {"portal_id": "246356639", "email_id": "123"},
        "/v1/integrations/hubspot/webhooks/configure": {"portal_id": "246356639", "app_id": "1160452"},
    }
    for endpoint, live_payload in live_action_payloads.items():
        live_response = client.post(endpoint, json=live_payload)
        assert_true(live_response.status_code in {403, 409, 503}, f"{endpoint} should be implemented and gated by connection/scopes, not return {live_response.status_code}: {live_response.get_data(as_text=True)}")

    webhook_event = client.post(
        "/v1/integrations/hubspot/webhooks/receive",
        json=[{"portalId": 246356639, "eventType": "contact.propertyChange", "eventId": 987, "objectId": 101, "occurredAt": 1770000000000}],
    )
    assert_true(webhook_event.status_code == 200, webhook_event.get_data(as_text=True))
    assert_true(webhook_event.get_json()["events"][0]["source_system"] == "hubspot_webhook", "HubSpot webhook ingest should normalize events")
    assert_true(webhook_event.get_json()["rescores"] == [], "Non-copy CRM webhook events should not trigger draft re-scoring")

    webhook_rescore = client.post(
        "/v1/integrations/hubspot/webhooks/receive",
        json=[
            {
                "portalId": 246356639,
                "eventType": "marketingEmail.propertyChange",
                "eventId": "email-copy-1",
                "objectId": "email-123",
                "occurredAt": 1770000001000,
                "marketingEmail": {
                    "id": "email-123",
                    "subject": "Guaranteed savings",
                    "html": "<p>Hi Brian, this will guarantee 100% savings by Friday. {{unsubscribe_link}}</p>",
                    "campaignId": "campaign-q3",
                },
            }
        ],
    )
    assert_true(webhook_rescore.status_code == 200, webhook_rescore.get_data(as_text=True))
    rescore_payload = webhook_rescore.get_json()
    assert_true(rescore_payload["rescores"][0]["status"] == "analyzed", "Copy-bearing HubSpot webhooks should trigger automatic re-scoring")
    assert_true(rescore_payload["rescores"][0]["gate"] in {"blocked", "needs_review", "ready"}, "Webhook re-score should return a branchable gate")

    webhook_metadata_only = client.post(
        "/v1/integrations/hubspot/webhooks/receive",
        json=[{"portalId": 246356639, "eventType": "marketingEmail.propertyChange", "eventId": "email-meta-1", "objectId": "email-456", "occurredAt": 1770000002000}],
    )
    assert_true(webhook_metadata_only.status_code == 200, webhook_metadata_only.get_data(as_text=True))
    assert_true(webhook_metadata_only.get_json()["rescores"][0]["status"] == "copy_unavailable", "Metadata-only draft webhooks should explain that copy mapping is required")

    connections = client.get("/api/enterprise/hubspot/connections")
    assert_true(connections.status_code == 200 and "token_storage" in connections.get_json(), "HubSpot admin connections endpoint should expose token storage state")
    setup_status = client.get("/api/enterprise/hubspot/setup-status?portal_id=246356639")
    assert_true(setup_status.status_code == 200, setup_status.get_data(as_text=True))
    setup_payload = setup_status.get_json()["setup_status"]
    setup_groups = {item["label"]: item for item in setup_payload["groups"]}
    assert_true({"Campaign sync", "Workflow actions", "Webhook re-scoring", "Approval workflow", "Reporting writeback"}.issubset(setup_groups), "HubSpot setup status should summarize campaign, workflow, webhook, approval, and reporting readiness")
    assert_true("admin_attention" in setup_payload and setup_payload["admin_attention"], "HubSpot setup status should flag admin attention items when a portal needs setup")
    assert_true("last_sync_at" in setup_payload, "HubSpot setup status should expose last sync activity")
    uninstall = client.post(
        "/v1/integrations/hubspot/app-uninstalled",
        json={"portalId": 246356639, "eventType": "app.uninstalled", "eventId": "uninstall-qa-1", "occurredAt": 1770000003000},
    )
    assert_true(uninstall.status_code == 200, uninstall.get_data(as_text=True))
    uninstall_payload = uninstall.get_json()
    assert_true(uninstall_payload["ok"] is True and uninstall_payload["portal_id"] == "246356639", "HubSpot uninstall callback should resolve the portal")
    assert_true(uninstall_payload["tokens_cleared"] is True, "HubSpot uninstall callback should clear stored portal tokens")
    assert_true(uninstall_payload["retention"]["analyses_retained"] is True, "HubSpot uninstall callback should explain retained audit data")
    disconnected_connections = client.get("/api/enterprise/hubspot/connections")
    assert_true(
        any(item["portal_id"] == "246356639" and item["status"] == "disconnected" for item in disconnected_connections.get_json()["connections"]),
        "HubSpot uninstall callback should mark the portal disconnected",
    )

    readiness = client.get("/api/enterprise/readiness")
    assert_true(readiness.status_code == 200, readiness.get_data(as_text=True))
    readiness_payload = readiness.get_json()["readiness"]
    readiness_ids = {item["id"] for item in readiness_payload["checks"]}
    assert_true({"runtime_model", "hubspot_oauth", "hubspot_ingress_auth", "retention_controls", "hubspot_surface_coverage"}.issubset(readiness_ids), "enterprise readiness report missing expected checks")
    assert_true("production_ready" in readiness_payload and "pilot_ready" in readiness_payload, "enterprise readiness summary missing")

    score_validation = client.get("/api/enterprise/hubspot/score-validation?workspace_id=hubspot_246356639")
    assert_true(score_validation.status_code == 200, score_validation.get_data(as_text=True))
    validation_payload = score_validation.get_json()["validation"]
    assert_true(validation_payload["cases_total"] == 3, "score validation should cover clear, vague, and risky cases")
    assert_true(validation_payload["cases_passed"] >= 2, "score validation should pass core routing cases")
    vague_case = next(item for item in validation_payload["cases"] if item["id"] == "vague_review_or_block")
    assert_true(vague_case["actual_gate"] != "ready", "vague validation email should not be send-ready")

    retention = client.get("/api/enterprise/hubspot/retention?days=1")
    assert_true(retention.status_code == 200, retention.get_data(as_text=True))
    retention_payload = retention.get_json()["retention"]
    assert_true(retention_payload["dry_run"] is True, "retention GET should be a dry run")
    assert_true("hubspot_email_analyses" in retention_payload["tables"], "retention preview should include analyses table")
    unsafe_retention = client.post("/api/enterprise/hubspot/retention", json={"days": 1, "dry_run": False}, headers=csrf_headers(client))
    assert_true(unsafe_retention.status_code == 400, "retention purge should require explicit confirmation")

    json_export = client.get("/api/enterprise/hubspot/exports/analyses.json?workspace_id=hubspot_246356639")
    assert_true(json_export.status_code == 200 and json_export.get_json()["analyses"], "HubSpot JSON export should return analyses")
    csv_export = client.get("/api/enterprise/hubspot/exports/analyses.csv?workspace_id=hubspot_246356639")
    assert_true(csv_export.status_code == 200 and "text/csv" in csv_export.headers.get("Content-Type", ""), "HubSpot CSV export should be available")
    policy_history = client.get("/api/enterprise/hubspot/policy/history?workspace_id=hubspot_246356639")
    assert_true(policy_history.status_code == 200 and policy_history.get_json()["history"], "HubSpot policy history should be retained")
    setup_guide = client.get("/hubspot/setup-guide")
    assert_true(setup_guide.status_code == 200 and "TextTraits Email Fit HubSpot Setup Guide" in setup_guide.get_data(as_text=True), "HubSpot setup guide should be publicly renderable")
    marketplace_readiness = client.get("/api/enterprise/hubspot/marketplace-readiness")
    assert_true(marketplace_readiness.status_code == 200, marketplace_readiness.get_data(as_text=True))
    marketplace_payload = marketplace_readiness.get_json()["marketplace_readiness"]
    marketplace_ids = {item["id"] for item in marketplace_payload["checks"]}
    assert_true(
        {"setup_guide", "oauth_authorization_code", "scope_justification", "disconnect_uninstall_docs", "active_installs", "verified_domain"}.issubset(marketplace_ids),
        "HubSpot marketplace readiness should cover setup guide, OAuth, scopes, uninstall, installs, and domain checks",
    )
    assert_true("marketing-email" in marketplace_payload["optional_scopes"], "Marketplace readiness should report optional HubSpot marketing scopes")
    assert_true(marketplace_payload["setup_guide_url"].endswith("/hubspot/setup-guide"), "Marketplace readiness should expose the setup guide URL")

    signed_secret = "qa-hubspot-ingress-secret"
    previous_secret = os.environ.get("TEXTTRAITS_HUBSPOT_INGRESS_SECRET")
    os.environ["TEXTTRAITS_HUBSPOT_INGRESS_SECRET"] = signed_secret
    previous_production_for_signature = app_module.PRODUCTION
    try:
        unsigned = client.post("/v1/integrations/hubspot/crm-card/analyze-email", json={"inputFields": {"subject": "Unsigned", "body": "Please reply by Friday."}})
        assert_true(unsigned.status_code == 401, "HubSpot ingress should require signature when a secret is configured")
        signed_payload = {"inputFields": {"subject": "Signed", "body": "Hi Brian, please reply by Friday with the renewal checklist."}}
        body, headers = signed_hubspot_headers(signed_secret, signed_payload)
        signed = client.post("/v1/integrations/hubspot/crm-card/analyze-email", data=body, headers=headers)
        assert_true(signed.status_code == 200, signed.get_data(as_text=True))
        app_module.PRODUCTION = True
        legacy_body, legacy_headers = signed_hubspot_headers(signed_secret, signed_payload)
        legacy_signed = client.post("/v1/integrations/hubspot/crm-card/analyze-email", data=legacy_body, headers=legacy_headers)
        assert_true(legacy_signed.status_code == 401, "production HubSpot HMAC should require a timestamped signature")
        stale_body, stale_headers = signed_hubspot_headers(signed_secret, signed_payload, timestamp=1)
        stale_signed = client.post("/v1/integrations/hubspot/crm-card/analyze-email", data=stale_body, headers=stale_headers)
        assert_true(stale_signed.status_code == 401, "stale timestamped HubSpot HMAC should be rejected")
        fresh_body, fresh_headers = signed_hubspot_headers(signed_secret, signed_payload, timestamp=int(app_module.time.time()))
        fresh_signed = client.post("/v1/integrations/hubspot/crm-card/analyze-email", data=fresh_body, headers=fresh_headers)
        assert_true(fresh_signed.status_code == 200, fresh_signed.get_data(as_text=True))
    finally:
        app_module.PRODUCTION = previous_production_for_signature
        if previous_secret is None:
            os.environ.pop("TEXTTRAITS_HUBSPOT_INGRESS_SECRET", None)
        else:
            os.environ["TEXTTRAITS_HUBSPOT_INGRESS_SECRET"] = previous_secret

    previous_hubspot_client_secret = os.environ.get("HUBSPOT_CLIENT_SECRET")
    previous_texttraits_ingress_secret = os.environ.get("TEXTTRAITS_HUBSPOT_INGRESS_SECRET")
    hubspot_client_secret = "qa-hubspot-client-secret"
    os.environ["HUBSPOT_CLIENT_SECRET"] = hubspot_client_secret
    os.environ.pop("TEXTTRAITS_HUBSPOT_INGRESS_SECRET", None)
    try:
        webhook_payload = [
            {
                "eventId": 531833541,
                "subscriptionId": 3923621,
                "portalId": 246356639,
                "appId": 16111050,
                "occurredAt": int(app_module.time.time() * 1000),
                "subscriptionType": "contact.creation",
                "objectId": 138017612137,
                "changeFlag": "CREATED",
            }
        ]
        webhook_path = "/v1/integrations/hubspot/webhooks/receive"
        encoded_query = "redirect=https%3A%2F%2Fexample.com%2Fthanks&note=Hello%2C%20Brian"
        signed_url = f"https://hooks.texttraits.test{webhook_path}?{encoded_query}"
        v3_body, v3_headers = hubspot_v3_signature_headers(hubspot_client_secret, webhook_payload, signed_url)
        v3_signed = client.post(f"{webhook_path}?{encoded_query}", base_url="https://hooks.texttraits.test", data=v3_body, headers=v3_headers)
        assert_true(v3_signed.status_code == 200, v3_signed.get_data(as_text=True))
        assert_true(v3_signed.get_json()["ingress_auth"]["mode"] == "hubspot_v3", "HubSpot v3 webhook signature should be accepted")
        invalid_headers = dict(v3_headers)
        invalid_headers["X-HubSpot-Signature-v3"] = "invalid-signature"
        invalid_v3 = client.post(f"{webhook_path}?{encoded_query}", base_url="https://hooks.texttraits.test", data=v3_body, headers=invalid_headers)
        assert_true(invalid_v3.status_code == 401, "invalid HubSpot v3 signatures should be rejected")
        stale_body, stale_headers = hubspot_v3_signature_headers(hubspot_client_secret, webhook_payload, signed_url, timestamp_ms=1)
        stale_v3 = client.post(f"{webhook_path}?{encoded_query}", base_url="https://hooks.texttraits.test", data=stale_body, headers=stale_headers)
        assert_true(stale_v3.status_code == 401, "stale HubSpot v3 signatures should be rejected")
    finally:
        if previous_hubspot_client_secret is None:
            os.environ.pop("HUBSPOT_CLIENT_SECRET", None)
        else:
            os.environ["HUBSPOT_CLIENT_SECRET"] = previous_hubspot_client_secret
        if previous_texttraits_ingress_secret is None:
            os.environ.pop("TEXTTRAITS_HUBSPOT_INGRESS_SECRET", None)
        else:
            os.environ["TEXTTRAITS_HUBSPOT_INGRESS_SECRET"] = previous_texttraits_ingress_secret

    previous_production = app_module.PRODUCTION
    previous_admins = set(app_module.ENTERPRISE_ADMIN_EMAILS)
    app_module.PRODUCTION = True
    app_module.ENTERPRISE_ADMIN_EMAILS.clear()
    try:
        locked_admin = client.get("/api/enterprise/hubspot/dashboard")
        assert_true(locked_admin.status_code == 503, "production enterprise admin endpoints should require an allowlist")
    finally:
        app_module.PRODUCTION = previous_production
        app_module.ENTERPRISE_ADMIN_EMAILS.clear()
        app_module.ENTERPRISE_ADMIN_EMAILS.update(previous_admins)

    previous_admin_allowlist_flag = os.environ.get("TEXTTRAITS_REQUIRE_ENTERPRISE_ADMIN_ALLOWLIST")
    os.environ["TEXTTRAITS_REQUIRE_ENTERPRISE_ADMIN_ALLOWLIST"] = "true"
    app_module.ENTERPRISE_ADMIN_EMAILS.clear()
    try:
        locked_staging_admin = client.get("/api/enterprise/hubspot/dashboard")
        assert_true(locked_staging_admin.status_code == 503, "staging enterprise admin endpoints should support fail-closed allowlist enforcement")
    finally:
        if previous_admin_allowlist_flag is None:
            os.environ.pop("TEXTTRAITS_REQUIRE_ENTERPRISE_ADMIN_ALLOWLIST", None)
        else:
            os.environ["TEXTTRAITS_REQUIRE_ENTERPRISE_ADMIN_ALLOWLIST"] = previous_admin_allowlist_flag
        app_module.ENTERPRISE_ADMIN_EMAILS.clear()
        app_module.ENTERPRISE_ADMIN_EMAILS.update(previous_admins)

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
