from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "texttraits_app"
sys.path.insert(0, str(APP_DIR))
os.environ.setdefault("ENABLE_DEV_TOOLS", "false")

import app as app_module  # noqa: E402


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def csrf_headers(client) -> dict[str, str]:
    token = client.get("/api/session").get_json()["csrf_token"]
    return {"X-CSRF-Token": token}


def main() -> int:
    client = app_module.app.test_client()
    headers = csrf_headers(client)

    html = client.get("/enterprise").get_data(as_text=True)
    app_js = client.get("/static/app.js").get_data(as_text=True)
    css = client.get("/static/styles.css").get_data(as_text=True)

    for phrase in (
        "Revenue Lab",
        "Revenue Signal Lab",
        "Simulate the B2B workflow before a real integration exists.",
        "Run workflow simulation",
        "What the platform user sees",
        "No raw PII returned",
    ):
        assert_true(phrase in html or phrase in app_js, f"workflow lab UI missing: {phrase}")

    for phrase in (
        "workflowProviders",
        "workflowScenarios",
        "workflowPayload(scenario, provider)",
        "revenueSignalLab()",
        "runRevenueSignalSimulation()",
        "loadWorkflowProfileBuilder()",
        "apiClient.b2bProfile",
        "apiClient.simulateAdapter",
    ):
        assert_true(phrase in app_js, f"workflow lab implementation missing: {phrase}")

    for phrase in (
        ".revenue-signal-lab",
        ".revenue-lab-grid",
        ".workflow-score-row",
        ".workflow-timeline",
    ):
        assert_true(phrase in css, f"workflow lab styling missing: {phrase}")

    profile_response = client.post(
        "/v1/b2b/profile",
        json={
            "workspace_id": "smoke",
            "campaign_goal": "Route to governance-first nurture",
            "account_context": "Lifecycle marketing team using HubSpot workflows, campaign approvals, and legal review.",
            "communication_history": (
                "Contact maya@example.com asked for a HubSpot workflow action, consent handling, "
                "audit trails, and proof that raw inbox history would not be stored before procurement."
            ),
        },
        headers=headers,
    )
    assert_true(profile_response.status_code == 200, profile_response.get_data(as_text=True))
    profile = profile_response.get_json()
    assert_true(profile["privacy"]["raw_identifiers_returned"] is False, "profile must not return raw identifiers")
    assert_true("maya@example.com" not in str(profile), "profile leaked raw email")
    assert_true(profile["business_profile"]["business_priorities"], "business profile should extract priorities")
    assert_true(profile["activation"]["crm_fields"], "profile should expose CRM writeback fields")

    adapter_response = client.post(
        "/v1/integrations/simulate",
        json={
            "provider": "hubspot",
            "payload": {
                "workspace_id": "smoke",
                "inputFields": {
                    "email_subject": "Governance-first workflow pilot",
                    "email_body": (
                        "Hi Maya, your team asked whether TextTraits can fit inside HubSpot without storing "
                        "raw inbox history. Could we test a workflow action that writes back score, route, and "
                        "objection signals?"
                    ),
                    "lifecyclestage": "Marketing operations",
                    "workflow_name": "Governance nurture",
                },
            },
        },
        headers=headers,
    )
    assert_true(adapter_response.status_code == 200, adapter_response.get_data(as_text=True))
    adapter = adapter_response.get_json()
    assert_true(adapter["adapter"] == "hubspot", "adapter simulator should preserve provider identity")
    assert_true(adapter["manifest"]["provider"] == "hubspot", "adapter simulator should return provider manifest")
    assert_true("texttraits_score" in adapter["writeback"], "adapter should return writeback score")
    assert_true("texttraits_route" in adapter["writeback"], "adapter should return writeback route")
    assert_true(adapter["analysis"]["gate"]["status"] in {"ready", "needs_review", "blocked"}, "gate status should be displayable")

    print("B2B workflow lab smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
