from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "texttraits_app"
sys.path.insert(0, str(APP_DIR))
tmpdir = tempfile.TemporaryDirectory()
os.environ["TEXTTRAITS_DB_PATH"] = str(Path(tmpdir.name) / "smoke.sqlite3")
os.environ["DATABASE_URL"] = ""
os.environ["TEXTTRAITS_DATABASE_URL"] = ""
os.environ.setdefault("ENABLE_DEV_TOOLS", "false")
os.environ.setdefault("TEXTTRAITS_SECRET_KEY", "test-secret-key")

import app as app_module  # noqa: E402


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def csrf_headers(client) -> dict[str, str]:
    token = client.get("/api/session").get_json()["csrf_token"]
    return {"X-CSRF-Token": token}


def main() -> int:
    client = app_module.app.test_client()

    home = client.get("/")
    assert_true(home.status_code == 200, f"home returned {home.status_code}")
    html = home.get_data(as_text=True)
    assert_true('data-mode="enterprise-optimizer"' in html, "enterprise optimizer page mode missing")
    assert_true("Enterprise email optimization, without generated copy." in html, "optimizer heading missing")
    assert_true("Enterprise optimizer" in html, "optimizer status card missing")
    assert_true("never writes the email for you" in html and "Local build:" in html, "non-generative footer copy missing")
    assert_true("Skip to analysis workspace" in html and 'aria-current="page"' in html, "accessible navigation state missing")
    assert_true("static/app.js" in html, "app script missing")
    assert_true("static/api_client.js" in html, "api client script missing")
    assert_true("static/text_utils.js" in html, "text utility script missing")
    assert_true("static/ui_helpers.js" in html, "ui helper script missing")
    assert_true("static/styles.css" in html, "stylesheet missing")
    assert_true("static/product_config.js" not in html, "legacy product config should not load")
    assert_true("static/csv_utils.js" not in html, "CSV helper should not load")
    assert_true("static/enterprise_copy.js" not in html, "email generation helper should not load")
    assert_true("Explorer" not in html, "Explorer surface should not render")
    assert_true("Developer tools" not in html, "developer tools should be hidden by default")
    assert_true("response-debug" not in html, "raw response debug should be hidden by default")
    assert_true("model_path" not in html, "model internals should not render in public HTML")
    for path, title in (("/privacy", "Privacy"), ("/terms", "Terms"), ("/security", "Security"), ("/deployment", "Deployment Readiness")):
        route = client.get(path)
        route_html = route.get_data(as_text=True)
        assert_true(route.status_code == 200 and title in route_html, f"{path} trust route missing")
        assert_true('data-mode="enterprise-optimizer"' in route_html and "Back to TextTraits" in route_html, f"{path} should match enterprise app shell")

    app_js = client.get("/static/app.js")
    assert_true(app_js.status_code == 200, f"app.js returned {app_js.status_code}")
    js = app_js.get_data(as_text=True)
    required_js = (
        "optimizer-form",
        "email-subject",
        "email-body",
        "Analyze email optimization",
        "emailOptimization(subject, email)",
        "apiClient.analyzeEmail",
        "Policy score",
        "Enterprise context fields",
        "Rendered-template test",
        "Run render test",
        "Structured findings",
        "Stable contract",
        "Policy gate",
        "Integration lab status",
        "Governance ledger",
        "Setup manifests",
        "Sandbox adapters",
        "Governance policy",
        "Governance dashboard",
        "Dashboard filters",
        "Source-system trend",
        "Campaign drilldown",
        "No matching data yet",
        "Enterprise readiness checklist",
        "Workspace data boundary",
        "Exports",
        "Export schedule",
        "Policy history and audit log",
        "Top failing rule packs",
        "Production-ready",
        "Needs mapping",
        "Production blocked",
        "Guided integration wizard",
        "Choose platform",
        "Validate payload",
        "Run sandbox test",
        "Promote environment",
        "Research targets",
        "Adapter simulator",
        "Run simulator",
        "Save policy controls",
        "Send timeout ms",
        "Idempotency window sec",
        "Rule family behavior",
        "Fail closed",
        "Integration setup",
        "Save recommended mapping",
        "Contract export",
        "Download OpenAPI JSON",
        "Objective model signals",
        "Why this score",
        "Developer-only raw /v1/email/analyze response",
        "Approval queue",
        "Admin settings",
        "Roles and permissions",
        "API key management",
        "Webhook signing setup",
        "Security and deployment readiness",
        "Model limitations",
        "Non-generative",
        "Deployment checklist",
        "No replacement email was generated",
        "enterprise_email_optimization",
        "Copy report",
        "Download JSON",
        "Report excludes the full email body",
    )
    for phrase in required_js:
        assert_true(phrase in js, f"enterprise optimizer UI missing {phrase}")

    forbidden_js = (
        "renderExplorerInput",
        "Try this rewrite",
        "Prompt library",
        "daily-home-card",
        "Generate sample drafts",
        "Generated email draft",
        "Campaign basics",
        "buildEmailVariant",
        "data-generate-batch",
        "Full sequence builder",
    )
    for phrase in forbidden_js:
        assert_true(phrase not in js, f"legacy writing/generation surface leaked into app.js: {phrase}")

    styles = client.get("/static/styles.css")
    assert_true(styles.status_code == 200, f"styles.css returned {styles.status_code}")
    css = styles.get_data(as_text=True)
    assert_true('body[data-mode="enterprise-optimizer"]' in css, "enterprise optimizer layout styles missing")
    assert_true(".optimizer-score-card" in css and ".optimizer-check-card" in css, "optimizer result styles missing")
    assert_true(".governance-policy-controls" in css and ".policy-control-grid" in css, "governance policy styles missing")
    assert_true(".adapter-simulator" in css, "adapter simulator styles missing")
    assert_true(".enterprise-nav" in css and ".render-test-card" in css and ".dashboard-panel-grid" in css, "enterprise workflow styles missing")

    health = client.get("/health")
    assert_true(health.status_code == 200, f"health returned {health.status_code}")
    assert_true(health.get_json()["ok"] is True, "public health should report aggregate readiness")
    assert_true(set(health.get_json().keys()) == {"ok"}, "public health should not expose deployment internals")

    session = client.get("/api/session")
    assert_true(session.status_code == 200, "session endpoint missing")
    assert_true(session.get_json()["app"]["auth"] is True, "auth app info missing")

    payload = {
        "text": (
            "Subject: Next step after Tuesday\n\n"
            "Hi Maya, thanks for walking through the renewal workflow on Tuesday. "
            "The strongest gap I heard was that managers see risk after the forecast is already under pressure. "
            "Would Thursday afternoon work for a quick fit check?"
        ),
        "model": "local",
        "mode": "enterprise-email-optimizer",
    }
    response = client.post("/evaluate", json=payload, headers=csrf_headers(client))
    assert_true(response.status_code == 200, f"evaluate returned {response.status_code}: {response.get_data(as_text=True)}")
    data = response.get_json()
    predictions = data["predictions"]
    assert_true(data["model"] == "local", "response should identify the local model")
    assert_true("gender" in predictions, "response missing language-association prediction")
    assert_true("mbti_dimensions" in predictions, "response missing MBTI dimension predictions")
    assert_true("text_stats" in predictions, "response missing text stats")
    assert_true("input_quality" in predictions, "response missing input-quality metadata")

    v1_payload = {
        "request_id": "smoke-v1",
        "subject": "Next step after Tuesday",
        "body": payload["text"],
        "audience": "Prospect",
        "intent": "Follow-up",
        "channel": "ui_enterprise_optimizer",
    }
    v1_response = client.post("/v1/email/analyze", json=v1_payload, headers=csrf_headers(client))
    assert_true(v1_response.status_code == 200, f"v1 analyze returned {v1_response.status_code}: {v1_response.get_data(as_text=True)}")
    v1_data = v1_response.get_json()
    assert_true(v1_data["policy"]["bundle_version"] == "2026.05.25", "v1 response missing policy version")
    assert_true(v1_data["content_hash"].startswith("sha256:"), "v1 response missing content hash")
    assert_true("findings" in v1_data and "routes" in v1_data, "v1 response missing structured findings/routes")
    policy_response = client.get("/v1/governance/policy?workspace_id=smoke")
    assert_true(policy_response.status_code == 200, "governance policy endpoint missing")
    assert_true(policy_response.get_json()["policy"]["content_storage_mode"] == "hash_only", "governance policy default missing")

    print("Smoke tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
