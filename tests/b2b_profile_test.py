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
    response = client.post(
        "/v1/b2b/profile",
        json={
            "communication_history": (
                "Email maya@example.com. The VP Sales said forecast surprises, renewal risk, "
                "Salesforce workflow fit, and security review are the biggest blockers. "
                "They are worried about another tool and asked for a narrow pilot next week."
            ),
            "account_context": "B2B SaaS account using Salesforce, Outreach, and RevOps forecast reviews.",
            "campaign_goal": "Book a workflow-fit pilot discussion",
        },
        headers=headers,
    )
    assert_true(response.status_code == 200, "B2B profile endpoint should return 200")
    data = response.get_json()
    assert_true(data["privacy"]["raw_identifiers_returned"] is False, "raw identifiers must not be returned")
    assert_true(data["privacy"]["sensitive_attribute_inference"] == "disabled", "sensitive inference should stay disabled")
    assert_true(data["privacy"]["pii_detected_counts"]["emails"] == 1, "email count should be recorded without exposing value")
    assert_true("maya@example.com" not in str(data), "raw email leaked in profile response")
    assert_true("redacted_preview" not in data["safe_features"], "profile should not return transcript previews")
    assert_true("forecast" in data["safe_features"]["evidence_terms_observed"], "business evidence terms should remain available")
    assert_true(data["business_profile"]["business_priorities"], "business priorities should be extracted")
    assert_true(data["business_profile"]["detected_objections"], "objections should be extracted")
    assert_true(data["resonance_strategy"]["recommended_angles"], "recommended angles should be available")
    assert_true("raw identifiers" in data["activation"]["llm_generation_context"]["blocked"], "LLM context should block raw identifiers")
    print("B2B profile checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
