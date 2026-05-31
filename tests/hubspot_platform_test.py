from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "texttraits_app"
sys.path.insert(0, str(APP_DIR))
tmpdir = Path(tempfile.mkdtemp(prefix="texttraits_hubspot_platform_"))
os.environ["TEXTTRAITS_DB_PATH"] = str(tmpdir / "hubspot_platform.sqlite3")
os.environ["DATABASE_URL"] = ""
os.environ["TEXTTRAITS_DATABASE_URL"] = ""
os.environ["TEXTTRAITS_SECRET_KEY"] = "test-secret-key"
os.environ["TEXTTRAITS_PUBLIC_BASE_URL"] = "https://texttraits.example.test"
os.environ["HUBSPOT_CLIENT_SECRET"] = "hubspot-test-secret"
os.environ["HUBSPOT_REQUIRE_SIGNATURE"] = "false"

import app as app_module  # noqa: E402
from hubspot_platform import calculate_hubspot_signature_v3, validate_hubspot_signature_v3  # noqa: E402


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def csrf_headers(client) -> dict[str, str]:
    token = client.get("/api/session").get_json()["csrf_token"]
    return {"X-CSRF-Token": token}


def main() -> int:
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
    platform = client.get("/v1/integrations/hubspot/platform-config")
    assert_true(platform.status_code == 200, platform.get_data(as_text=True))
    platform_payload = platform.get_json()["hubspot"]
    assert_true(platform_payload["extension_points"]["crm_app_card"]["endpoint"].endswith("/v1/integrations/hubspot/crm-card"), "platform config missing CRM card endpoint")
    assert_true("HUBSPOT_CLIENT_SECRET" in platform_payload["required_env"], "platform config missing HubSpot secret env")

    card = client.get("/v1/integrations/hubspot/crm-card?portalId=123&objectType=contacts&objectId=456")
    assert_true(card.status_code == 200, card.get_data(as_text=True))
    card_payload = card.get_json()["card"]
    assert_true(card_payload["hubspot_context"]["portalId"] == "123", "CRM card should echo safe HubSpot context")
    assert_true(card_payload["primary_action"]["endpoint"].endswith("/v1/integrations/hubspot/crm-card/analyze-email"), "CRM card missing analyze action")

    sample = {
        "workspace_id": "hubspot-platform-test",
        "requestId": "hubspot-card-test",
        "inputFields": {
            "subject": "Renewal workflow follow-up",
            "body": "Hi Maya, thanks for walking through the renewal workflow. Would Thursday afternoon work for a quick fit check?",
            "audience": "HubSpot CRM record",
            "intent": "CRM outreach review",
        },
    }
    analysis = client.post("/v1/integrations/hubspot/crm-card/analyze-email", json=sample, headers=csrf_headers(client))
    assert_true(analysis.status_code == 200, analysis.get_data(as_text=True))
    analysis_payload = analysis.get_json()
    assert_true(analysis_payload["outputFields"]["texttraits_request_id"] == "hubspot-card-test", "CRM card analysis should preserve request id")
    assert_true("texttraits_score" in analysis_payload["outputFields"], "CRM card analysis missing score output")
    assert_true(sample["inputFields"]["body"] not in str(analysis_payload), "CRM card analysis should not echo raw body")

    openapi = client.get("/v1/openapi.json").get_json()
    for path in (
        "/v1/integrations/hubspot/platform-config",
        "/v1/integrations/hubspot/crm-card",
        "/v1/integrations/hubspot/crm-card/analyze-email",
    ):
        assert_true(path in openapi["paths"], f"OpenAPI missing {path}")

    print("HubSpot platform tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
