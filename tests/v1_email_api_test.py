from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "texttraits_app"
sys.path.insert(0, str(APP_DIR))
os.environ.setdefault("ENABLE_DEV_TOOLS", "false")

import app as app_module  # noqa: E402
import storage  # noqa: E402


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def csrf_headers(client) -> dict[str, str]:
    token = client.get("/api/session").get_json()["csrf_token"]
    return {"X-CSRF-Token": token}


def main() -> int:
    client = app_module.app.test_client()
    headers = csrf_headers(client)
    payload = {
        "request_id": "api-test-001",
        "subject": "Next step after Tuesday",
        "body": (
            "Hi Maya, thanks for walking through the renewal workflow on Tuesday. "
            "The strongest gap I heard was that managers see risk after the forecast is already under pressure. "
            "Would Thursday afternoon work for a quick fit check?"
        ),
        "audience": "Prospect",
        "intent": "Follow-up",
        "channel": "hubspot_workflow",
        "assets": {"links": [], "image_count": 0, "image_bytes": 0, "html_bytes": 240},
    }

    response = client.post("/v1/email/analyze", json=payload, headers=headers)
    assert_true(response.status_code == 200, response.get_data(as_text=True))
    analysis = response.get_json()
    assert_true(analysis["api_version"] == "v1", "analysis contract should be versioned")
    assert_true(analysis["request_id"] == "api-test-001", "request id should be preserved")
    assert_true(analysis["content_hash"].startswith("sha256:"), "content hash missing")
    assert_true(analysis["policy"]["bundle_version"] == "2026.05.25", "policy bundle version missing")
    assert_true("model" in analysis and analysis["model"]["version"], "model version missing")
    assert_true(payload["body"] not in str(analysis), "analysis response should not return raw email body text")
    assert_true({"severity", "category", "evidence", "remediation"}.issubset(set(analysis["findings"][0].keys())) if analysis["findings"] else True, "findings should be structured")
    assert_true(analysis["policy"]["gate"]["status"] in {"ready", "needs_review", "blocked"}, "gate status missing")
    persisted_analyses = storage.recent_email_analyses(limit=20)
    assert_true(any(item["request_id"] == "api-test-001" for item in persisted_analyses), "analysis should persist to governance storage")

    openapi = client.get("/v1/openapi.json")
    assert_true(openapi.status_code == 200, openapi.get_data(as_text=True))
    openapi_data = openapi.get_json()
    assert_true(openapi_data["openapi"].startswith("3."), "OpenAPI contract should declare 3.x")
    for path in (
        "/v1/email/analyze",
        "/v1/integrations/hubspot/workflow-actions/analyze-email",
        "/v1/integrations/salesforce/journey-builder/activity",
        "/v1/integrations/sendgrid-ses/middleware",
        "/v1/integrations/braze/canvas-gate",
        "/v1/integrations/marketo/smart-campaign-gate",
        "/v1/integrations/iterable/workflow-gate",
        "/v1/integrations/warehouse/feedback-import",
        "/v1/integrations/simulate",
        "/v1/templates/render-test",
        "/v1/webhooks/post-send",
        "/v1/governance/dashboard",
        "/v1/governance/export",
        "/v1/governance/policy",
    ):
        assert_true(path in openapi_data["paths"], f"OpenAPI contract missing {path}")
    assert_true(openapi_data["x-texttraits"]["non_generative"] is True, "OpenAPI contract should mark non-generative positioning")

    install_kit = client.get("/v1/install-kit")
    assert_true(install_kit.status_code == 200, install_kit.get_data(as_text=True))
    install_data = install_kit.get_json()
    assert_true(install_data["openapi_url"].endswith("/v1/openapi.json"), "install kit should link OpenAPI contract")
    assert_true(len(install_data["provider_manifests"]) >= 4, "install kit should include provider manifests")
    assert_true(any("/v1/email/analyze" in item["path"] for item in install_data["endpoints"]), "install kit missing analyze endpoint")
    assert_true(any("/v1/governance/policy" in item["path"] for item in install_data["endpoints"]), "install kit missing governance policy endpoint")
    assert_true(any("/v1/integrations/simulate" in item["path"] for item in install_data["endpoints"]), "install kit missing adapter simulator endpoint")
    assert_true("samples/governance-policy-request.json" in install_data["sample_payloads"], "install kit missing governance policy sample")
    assert_true("samples/enterprise-context-analyze-request.json" in install_data["sample_payloads"], "install kit missing enterprise context sample")
    assert_true("samples/adapter-simulator-request.json" in install_data["sample_payloads"], "install kit missing adapter simulator sample")
    assert_true("samples/warehouse-feedback-import-request.json" in install_data["sample_payloads"], "install kit missing warehouse feedback sample")

    integration_plan = client.get("/api/enterprise/integration-plan")
    assert_true(integration_plan.status_code == 200, integration_plan.get_data(as_text=True))
    assert_true(integration_plan.get_json()["recommendation"]["primary_target"] == "journey_workflow_gate", "enterprise plan should expose deep research target matrix")

    risky = {
        "request_id": "api-test-risky",
        "subject": "FREE guaranteed result for {{first_name}}",
        "body": (
            "Hi {{first_name}}, this is a guaranteed game-changing offer with lots of things and stuff. "
            "Visit https://a.example https://b.example https://c.example https://d.example"
        ),
        "audience": "Bulk campaign",
        "intent": "Marketing campaign",
        "channel": "bulk_email",
        "assets": {"image_count": 4, "image_bytes": 8000, "html_bytes": 10000},
    }
    risky_response = client.post("/v1/email/analyze", json=risky, headers=headers)
    assert_true(risky_response.status_code == 200, risky_response.get_data(as_text=True))
    risky_analysis = risky_response.get_json()
    categories = {item["category"] for item in risky_analysis["findings"]}
    for category in {"compliance", "unsubscribe", "personalization", "format", "cta"}:
        assert_true(category in categories, f"missing {category} rule-pack finding")
    assert_true(risky_analysis["policy"]["gate"]["send_ready"] is False, "risky campaign should not be send ready")

    flows = client.get("/v1/integrations/mock-flows").get_json()["flows"]
    assert_true(any(flow["id"] == "hubspot_workflow_action" for flow in flows), "HubSpot mock flow missing")
    assert_true(any(flow["id"] == "salesforce_journey_builder_activity" for flow in flows), "Salesforce mock flow missing")
    assert_true(any(flow["id"] == "sendgrid_ses_middleware" for flow in flows), "SendGrid/SES mock flow missing")

    manifests = client.get("/v1/integrations/manifests")
    assert_true(manifests.status_code == 200, manifests.get_data(as_text=True))
    manifest_ids = {item["provider"] for item in manifests.get_json()["manifests"]}
    for provider in {"hubspot", "salesforce", "sendgrid_ses", "post_send_webhook"}:
        assert_true(provider in manifest_ids, f"missing {provider} integration manifest")
    for provider in {"braze", "marketo", "iterable", "warehouse"}:
        assert_true(provider in manifest_ids, f"missing deep research provider manifest: {provider}")

    hubspot_manifest = client.get("/v1/integrations/hubspot/manifest").get_json()
    assert_true("mapping_template" in hubspot_manifest and "subject" in hubspot_manifest["mapping_template"]["inputs"], "HubSpot mapping template missing")
    incomplete_mapping = client.post(
        "/v1/integrations/hubspot/field-mapping/validate",
        json={"mapping": {"inputs": {"subject": "email_subject"}, "outputs": {}}},
        headers=headers,
    )
    assert_true(incomplete_mapping.status_code == 200, incomplete_mapping.get_data(as_text=True))
    assert_true(incomplete_mapping.get_json()["validation"]["valid"] is False, "incomplete mapping should not validate")
    complete_mapping = {
        "inputs": {"subject": "email_subject", "body": "email_body", "audience": "lifecyclestage", "intent": "workflow_name"},
        "outputs": {
            "texttraits_score": "score",
            "texttraits_gate": "gate_status",
            "texttraits_route": "route",
            "texttraits_request_id": "request_id",
            "texttraits_content_hash": "content_hash",
        },
    }
    saved_mapping = client.post(
        "/v1/integrations/hubspot/field-mapping",
        json={"workspace_id": "qa-workspace", "mapping": complete_mapping},
        headers=headers,
    )
    assert_true(saved_mapping.status_code == 200, saved_mapping.get_data(as_text=True))
    assert_true(saved_mapping.get_json()["field_mapping"]["status"] == "ready", "complete mapping should persist as ready")
    persisted_mapping = storage.get_integration_field_mapping("qa-workspace", "hubspot")
    assert_true(persisted_mapping is not None and persisted_mapping["status"] == "ready", "field mapping should persist")

    default_policy = client.get("/v1/governance/policy?workspace_id=policy-default-test")
    assert_true(default_policy.status_code == 200, default_policy.get_data(as_text=True))
    assert_true(default_policy.get_json()["policy"]["min_ready_score"] == 72, "default governance policy should expose ready threshold")
    saved_policy = client.put(
        "/v1/governance/policy",
        json={
            "workspace_id": "qa-workspace",
            "policy": {
                "min_ready_score": 80,
                "retention_days": 365,
                "webhook_retention_days": 730,
                "webhook_dedupe_window_days": 45,
                "content_storage_mode": "metadata_only",
                "sample_import_limit": 3,
                "send_path_timeout_ms": 10000,
                "high_severity_requires_review": True,
            },
        },
        headers=headers,
    )
    assert_true(saved_policy.status_code == 200, saved_policy.get_data(as_text=True))
    policy = saved_policy.get_json()["policy"]
    assert_true(policy["workspace_id"] == "qa-workspace" and policy["min_ready_score"] == 80, "workspace policy should persist normalized controls")
    policy_analysis = client.post(
        "/v1/email/analyze",
        json={**payload, "workspace_id": "qa-workspace", "request_id": "api-test-policy-controls"},
        headers=headers,
    )
    assert_true(policy_analysis.status_code == 200, policy_analysis.get_data(as_text=True))
    policy_payload = policy_analysis.get_json()
    assert_true(policy_payload["policy"]["gate"]["thresholds"]["ready_minimum_score"] == 80, "analysis gate should use saved ready threshold")
    assert_true(policy_payload["privacy"]["stored_text_policy"] == "metadata_only", "analysis privacy policy should reflect saved storage mode")
    assert_true(policy_payload["input"]["enterprise_context"]["workspace_id"] == "qa-workspace", "analysis should preserve enterprise workspace context")

    fail_open_policy = client.put(
        "/v1/governance/policy",
        json={
            "workspace_id": "qa-fail-open",
            "policy": {
                "min_ready_score": 50,
                "high_severity_requires_review": False,
                "rule_family_modes": {"cta": "fail_open", "compliance": "fail_closed", "unsubscribe": "fail_closed"},
                "policy_environment": "sandbox",
            },
        },
        headers=headers,
    )
    assert_true(fail_open_policy.status_code == 200, fail_open_policy.get_data(as_text=True))
    no_cta = client.post(
        "/v1/email/analyze",
        json={
            "workspace_id": "qa-fail-open",
            "request_id": "api-test-fail-open-cta",
            "subject": "Thursday renewal checkpoint",
            "body": "Hi Maya, the renewal checkpoint is scheduled for Thursday and includes three manager handoff details.",
            "source_system": "marketo",
            "analysis_mode": "pre_send_gate",
            "campaign_id": "cmp-policy",
            "template_id": "tmpl-policy",
        },
        headers=headers,
    )
    assert_true(no_cta.status_code == 200, no_cta.get_data(as_text=True))
    assert_true(no_cta.get_json()["policy"]["gate"]["send_ready"] is True, "fail-open CTA policy should allow a high CTA finding when score passes")

    render_test = client.post(
        "/v1/templates/render-test",
        json={
            "subject": "Hello {{ first_name }}",
            "body": "Hi {{ first_name }} / %FIRST_NAME%, review {{ missing_token }} by Friday. Unsubscribe: https://example.test/unsub",
            "personalization_context": {"first_name": "Maya"},
            "headers": {"List-Unsubscribe": "<https://example.test/unsub>"},
        },
        headers=headers,
    )
    assert_true(render_test.status_code == 200, render_test.get_data(as_text=True))
    render_payload = render_test.get_json()["render_test"]
    assert_true(render_payload["unsubscribe"]["header_present"] is True, "render test should inspect List-Unsubscribe headers")
    assert_true(any(item["key"] == "missing_token" for item in render_payload["unresolved_tokens"]), "render test should report unresolved template tokens")

    hubspot = client.post(
        "/v1/integrations/hubspot/workflow-actions/analyze-email",
        json={"requestId": "hubspot-test", "inputFields": {"email_subject": payload["subject"], "email_body": payload["body"]}},
        headers=headers,
    )
    assert_true(hubspot.status_code == 200, hubspot.get_data(as_text=True))
    assert_true("texttraits_gate" in hubspot.get_json()["outputFields"], "HubSpot output fields missing gate")
    mapped_hubspot = client.post(
        "/v1/integrations/hubspot/workflow-actions/analyze-email",
        json={
            "workspace_id": "qa-workspace",
            "requestId": "hubspot-mapped-test",
            "inputFields": {"email_subject": payload["subject"], "email_body": payload["body"], "lifecyclestage": "Prospect", "workflow_name": "Follow-up"},
        },
        headers=headers,
    )
    assert_true(mapped_hubspot.status_code == 200, mapped_hubspot.get_data(as_text=True))
    assert_true(mapped_hubspot.get_json()["mapping_status"] == "ready", "HubSpot adapter should use saved field mapping")
    assert_true("texttraits_score" in mapped_hubspot.get_json()["outputFields"], "mapped HubSpot output field missing score")

    middleware = client.post(
        "/v1/integrations/sendgrid-ses/middleware",
        json={"workspace_id": "qa-workspace", "provider": "sendgrid", "idempotency_key": "sendgrid-risky-001", "message": {"subject": risky["subject"], "text": risky["body"], "assets": risky["assets"]}},
        headers=headers,
    )
    assert_true(middleware.status_code == 200, middleware.get_data(as_text=True))
    assert_true(middleware.get_json()["allow_send"] is False, "middleware should hold risky send")
    assert_true(middleware.get_json()["latency_budget"]["within_budget"] is True, "send middleware should report latency budget status")

    braze = client.post(
        "/v1/integrations/braze/canvas-gate",
        json={
            "workspace_id": "qa-workspace",
            "canvas_step": {"subject": "Renewal note for {{ first_name }}", "body": "Hi {{ first_name }}, review the renewal checklist by Thursday. Manage preferences: https://example.test/prefs"},
            "personalization_context": {"first_name": "Maya"},
            "headers": {"List-Unsubscribe": "<https://example.test/unsub>"},
        },
        headers=headers,
    )
    assert_true(braze.status_code == 200, braze.get_data(as_text=True))
    assert_true(braze.get_json()["adapter"] == "braze", "Braze adapter should return adapter identity")

    for endpoint, provider in (
        ("/v1/integrations/marketo/smart-campaign-gate", "marketo"),
        ("/v1/integrations/iterable/workflow-gate", "iterable"),
    ):
        adapter = client.post(
            endpoint,
            json={"workspace_id": "qa-workspace", "subject": payload["subject"], "body": payload["body"], "campaign_id": f"cmp-{provider}", "template_id": f"tmpl-{provider}"},
            headers=headers,
        )
        assert_true(adapter.status_code == 200, adapter.get_data(as_text=True))
        assert_true(adapter.get_json()["adapter"] == provider, f"{provider} adapter should return adapter identity")

    simulator = client.post(
        "/v1/integrations/simulate",
        json={"provider": "hubspot", "payload": {"inputFields": {"email_subject": payload["subject"], "email_body": payload["body"]}}},
        headers=headers,
    )
    assert_true(simulator.status_code == 200, simulator.get_data(as_text=True))
    assert_true(simulator.get_json()["manifest"]["provider"] == "hubspot", "adapter simulator should include provider manifest")

    warehouse = client.post(
        "/v1/integrations/warehouse/feedback-import",
        json={
            "workspace_id": "qa-workspace",
            "chunk_index": 0,
            "chunk_total": 2,
            "resume_token": "qa-resume-001",
            "rows": [
                {
                    "subject": "Warehouse feedback row",
                    "body": "Hi Maya, could we review the checklist on Thursday?",
                    "campaign_id": "cmp-warehouse",
                    "template_id": "tmpl-warehouse",
                    "event_type": "clicked",
                    "delivery_status": "clicked",
                }
            ],
        },
        headers=headers,
    )
    assert_true(warehouse.status_code == 200, warehouse.get_data(as_text=True))
    assert_true(warehouse.get_json()["summary"]["resume_available"] is True, "warehouse import should preserve resumability metadata without exposing the raw token")
    assert_true(str(warehouse.get_json()["summary"]["resume_digest"]).startswith("sha256:"), "warehouse import should store a replay-safe resume digest")

    event = {"event_id": "delivery-001", "provider": "sendgrid", "event_type": "delivered", "request_id": "api-test-001"}
    first_event = client.post("/v1/webhooks/post-send", json=event, headers=headers)
    second_event = client.post("/v1/webhooks/post-send", json=event, headers=headers)
    assert_true(first_event.status_code == 200, first_event.get_data(as_text=True))
    assert_true(first_event.get_json()["dedupe_window_days"] == 30, "webhook response should expose active dedupe window")
    assert_true(first_event.get_json()["signature_status"] == "not_configured", "webhook should expose signature hook status")
    assert_true(second_event.get_json()["duplicate"] is True, "webhook dedupe should identify retries")
    persisted_events = storage.recent_webhook_events(limit=20)
    assert_true(any(item["dedupe_key"] == "delivery-001" and item["seen_count"] >= 2 for item in persisted_events), "webhook retry count should persist")
    window_key = "window-replay-001"
    storage.upsert_webhook_event(
        window_key,
        {"provider": "sendgrid", "event_type": "delivered", "delivery_status": "delivered"},
        {"event_id": window_key},
        workspace_id="qa-window",
        dedupe_window_days=1,
    )
    old_seen = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(timespec="seconds")
    with storage.connect() as conn:
        storage.execute(
            conn,
            "UPDATE webhook_events SET last_seen_at = ? WHERE workspace_id = ? AND dedupe_key = ?",
            (old_seen, "qa-window", "qa-window:window-replay-001"),
        )
    replayed, replay_duplicate = storage.upsert_webhook_event(
        window_key,
        {"provider": "sendgrid", "event_type": "delivered", "delivery_status": "delivered"},
        {"event_id": window_key},
        workspace_id="qa-window",
        dedupe_window_days=1,
    )
    assert_true(replay_duplicate is False and replayed["seen_count"] == 1, "dedupe window should reset stale webhook replay keys")

    batch = client.post("/v1/samples/import", json={"samples": [payload, risky]}, headers=headers)
    assert_true(batch.status_code == 200, batch.get_data(as_text=True))
    assert_true(batch.get_json()["summary"]["accepted"] == 2, "batch import should analyze sample rows")
    import_id = batch.get_json()["summary"]["import_id"]
    persisted_imports = storage.recent_sample_imports(limit=10)
    assert_true(any(item["import_id"] == import_id for item in persisted_imports), "sample import summary should persist")

    dashboard = client.get("/v1/governance/dashboard")
    assert_true(dashboard.status_code == 200, dashboard.get_data(as_text=True))
    governance = dashboard.get_json()
    assert_true(governance["analysis_volume"] >= 4, "governance dashboard should reflect analyses")
    assert_true("gate_counts" in governance and "webhook_events" in governance, "governance dashboard missing operational sections")
    qa_dashboard = client.get("/v1/governance/dashboard?workspace_id=qa-workspace")
    assert_true(qa_dashboard.status_code == 200, qa_dashboard.get_data(as_text=True))
    qa_governance = qa_dashboard.get_json()
    assert_true(qa_governance["policy"]["min_ready_score"] == 80, "workspace dashboard should include saved policy")
    assert_true("source_counts" in qa_governance and "model_version_counts" in qa_governance, "dashboard should expose governance analytics")
    assert_true("top_failing_rule_packs" in qa_governance and "joined_outcomes" in qa_governance, "dashboard should expose normalized finding and outcome joins")

    export_json = client.get("/v1/governance/export?workspace_id=qa-workspace&type=findings")
    assert_true(export_json.status_code == 200, export_json.get_data(as_text=True))
    assert_true("rows" in export_json.get_json(), "governance JSON export should include rows")
    export_csv = client.get("/v1/governance/export?workspace_id=qa-workspace&type=joins&format=csv")
    assert_true(export_csv.status_code == 200 and "text/csv" in export_csv.content_type, "governance CSV export should return CSV")

    os.environ["TEXTTRAITS_API_KEY"] = "test-key"
    os.environ["TEXTTRAITS_API_KEY_SCOPES"] = "qa-workspace:/v1/email/analyze"
    api_key_response = client.post(
        "/v1/email/analyze",
        json={**payload, "workspace_id": "qa-workspace", "request_id": "api-key-scoped"},
        headers={"X-TextTraits-Api-Key": "test-key"},
    )
    assert_true(api_key_response.status_code == 200, "scoped API key should allow matching workspace and endpoint without CSRF")
    scoped_denied = client.post(
        "/v1/integrations/sendgrid-ses/middleware",
        json={"workspace_id": "other-workspace", "message": {"subject": "Hello", "text": "Could we review this on Thursday?"}},
        headers={"X-TextTraits-Api-Key": "test-key"},
    )
    assert_true(scoped_denied.status_code == 419, "scoped API key should not allow mismatched workspace/endpoint without CSRF")
    os.environ.pop("TEXTTRAITS_API_KEY_SCOPES", None)

    print("v1 email API tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
