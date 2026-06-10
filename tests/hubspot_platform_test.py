from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "texttraits_app"
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(SCRIPTS_DIR))
tmpdir = Path(tempfile.mkdtemp(prefix="texttraits_hubspot_platform_"))
os.environ["TEXTTRAITS_DB_PATH"] = str(tmpdir / "hubspot_platform.sqlite3")
os.environ["DATABASE_URL"] = ""
os.environ["TEXTTRAITS_DATABASE_URL"] = ""
os.environ["TEXTTRAITS_SECRET_KEY"] = "test-secret-key"
os.environ["TEXTTRAITS_PUBLIC_BASE_URL"] = "https://texttraits.example.test"
os.environ["HUBSPOT_CLIENT_SECRET"] = "hubspot-test-secret"
os.environ["HUBSPOT_REQUIRE_SIGNATURE"] = "false"
os.environ.pop("TEXTTRAITS_HUBSPOT_INGRESS_SECRET", None)
os.environ.pop("TEXTTRAITS_REQUIRE_HUBSPOT_INGRESS_AUTH", None)

import app as app_module  # noqa: E402
from hubspot_platform import calculate_hubspot_signature_v3, validate_hubspot_signature_v3  # noqa: E402
from render_hubspot_project import render_project  # noqa: E402


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def csrf_headers(client) -> dict[str, str]:
    token = client.get("/api/session").get_json()["csrf_token"]
    return {"X-CSRF-Token": token}


def main() -> int:
    rendered_dir = tmpdir / "rendered"
    render_project(
        rendered_dir,
        {
            "__TEXTTRAITS_PUBLIC_BASE_URL__": "https://texttraits.example.test",
            "__TEXTTRAITS_SUPPORT_EMAIL__": "support@example.com",
            "__TEXTTRAITS_SUPPORT_URL__": "https://texttraits.example.test/security",
            "__TEXTTRAITS_DOCUMENTATION_URL__": "https://texttraits.example.test/docs",
        },
    )
    app_meta = (rendered_dir / "src" / "app" / "app-hsmeta.json").read_text(encoding="utf-8")
    workflow_meta = (rendered_dir / "src" / "app" / "workflow-actions" / "texttraits-score-email-hsmeta.json").read_text(encoding="utf-8")
    card_jsx = (rendered_dir / "src" / "app" / "cards" / "TextTraitsEmailFitCard.jsx").read_text(encoding="utf-8")
    assert_true("__TEXTTRAITS_PUBLIC_BASE_URL__" not in app_meta + workflow_meta + card_jsx, "rendered HubSpot project should not contain base URL placeholders")
    assert_true("https://texttraits.example.test/api/integrations/hubspot/oauth/callback" in app_meta, "HubSpot app metadata should include OAuth callback")
    assert_true("/v1/integrations/hubspot/workflow-actions/analyze-email" in workflow_meta, "workflow action metadata should point at current callback")
    assert_true("/v1/integrations/hubspot/crm-card/analyze-email" in card_jsx, "CRM card should call the current analyze endpoint")

    method = "POST"
    url = "https://texttraits.example.test/v1/integrations/hubspot/crm-card/analyze-email"
    body = '{"ok":true}'
    timestamp = str(int(time.time() * 1000))
    signature = calculate_hubspot_signature_v3(method, url, body, timestamp, "hubspot-test-secret")
    valid = validate_hubspot_signature_v3(
        method=method,
        url=url,
        body=body,
        headers={"X-HubSpot-Signature-v3": signature, "X-HubSpot-Request-Timestamp": timestamp},
        client_secret="hubspot-test-secret",
    )
    assert_true(valid["valid"] is True and valid["status"] == "valid", "valid HubSpot signature should pass")
    invalid = validate_hubspot_signature_v3(
        method=method,
        url=url,
        body=body,
        headers={"X-HubSpot-Signature-v3": "wrong", "X-HubSpot-Request-Timestamp": timestamp},
        client_secret="hubspot-test-secret",
    )
    assert_true(invalid["valid"] is False and invalid["status"] == "signature_mismatch", "bad HubSpot signature should fail")

    client = app_module.app.test_client()
    sample = {
        "workspace_id": "hubspot_246356639",
        "idempotency_key": "hubspot-card-test",
        "portal_id": "246356639",
        "object_type": "contacts",
        "object_id": "456",
        "inputFields": {
            "subject": "Renewal workflow follow-up",
            "body": "Hi Maya, thanks for walking through the renewal workflow. Would Thursday afternoon work for a quick fit check?",
            "audience": "HubSpot CRM record",
            "intent": "CRM outreach review",
        },
    }
    analysis = client.post("/v1/integrations/hubspot/crm-card/analyze-email", json=sample)
    assert_true(analysis.status_code == 200, analysis.get_data(as_text=True))
    analysis_payload = analysis.get_json()
    assert_true(analysis_payload["workflow"] == "hubspot_crm_card", "CRM card analysis should identify the card workflow")
    assert_true(analysis_payload["outputFields"]["texttraits_idempotency_key"] == "hubspot-card-test", "CRM card analysis should preserve idempotency key")
    assert_true("texttraits_score" in analysis_payload["outputFields"], "CRM card analysis missing score output")
    assert_true("email_quality" in analysis_payload["analysis"], "CRM card analysis missing current email-quality checks")
    assert_true(analysis_payload["analysis"]["context"]["portal_id"] == "246356639", "CRM card analysis should normalize HubSpot portal context")
    assert_true(sample["inputFields"]["body"] not in str(analysis_payload), "CRM card analysis should not echo raw body")

    workflow_action = client.post(
        "/v1/integrations/hubspot/workflow-actions/analyze-email",
        json={
            "inputFields": {
                "email_subject": "Renewal workflow follow-up",
                "email_body": "Please review the renewal checklist by Friday and reply with any missing owner details.",
                "workflow_name": "QA renewal workflow",
            },
        },
    )
    assert_true(workflow_action.status_code == 200, workflow_action.get_data(as_text=True))
    workflow_payload = workflow_action.get_json()
    assert_true(workflow_payload["workflow"] == "hubspot_workflow_action", "workflow action endpoint should stay available")
    assert_true("texttraits_gate" in workflow_payload["outputFields"], "workflow action should return branchable gate output")

    template_test = client.post(
        "/v1/integrations/hubspot/template-test",
        json={
            "inputFields": {
                "subject": "Hi {{first_name}}",
                "body": "Hi {{first_name}}, please review {{company}} before Friday. {{unsubscribe_link}}",
            },
            "sample_context": {"first_name": "Maya", "company": "Acme", "unsubscribe_link": "https://example.com/unsubscribe"},
            "headers": {"from": "marketing@example.com", "reply_to": "sales@example.com"},
        },
    )
    assert_true(template_test.status_code == 200, template_test.get_data(as_text=True))
    assert_true(template_test.get_json()["template_test"]["rendered_subject"] == "Hi Maya", "template test should render personalization tokens")

    print("HubSpot platform tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
