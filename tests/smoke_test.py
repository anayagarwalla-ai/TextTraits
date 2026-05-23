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

    home = client.get("/")
    assert_true(home.status_code == 200, f"home returned {home.status_code}")
    html = home.get_data(as_text=True)
    assert_true('body data-mode="model-only"' in html, "model-only page mode missing")
    assert_true("Objective text traits from the local model." in html, "model-only heading missing")
    assert_true("Model-only build" in html, "model-only status card missing")
    assert_true("prediction distributions, confidence margins, cue terms, and text statistics" in html, "model-only value copy missing")
    assert_true("static/app.js" in html, "app script missing")
    assert_true("static/api_client.js" in html, "api client script missing")
    assert_true("static/text_utils.js" in html, "text utility script missing")
    assert_true("static/ui_helpers.js" in html, "ui helper script missing")
    assert_true("static/styles.css" in html, "stylesheet missing")
    assert_true("static/product_config.js" not in html, "legacy product config should not load")
    assert_true("static/csv_utils.js" not in html, "CSV helper should not load in model-only UI")
    assert_true("static/enterprise_copy.js" not in html, "Enterprise copy helper should not load")
    assert_true("Developer tools" not in html, "developer tools should be hidden by default")
    assert_true("response-debug" not in html, "raw response debug should be hidden by default")
    assert_true("model_path" not in html, "model internals should not render in public HTML")

    app_js = client.get("/static/app.js")
    assert_true(app_js.status_code == 200, f"app.js returned {app_js.status_code}")
    js = app_js.get_data(as_text=True)
    required_js = (
        "objective-form",
        "objective-text",
        "Run model analysis",
        "Objective prediction output",
        "Model-only result",
        "primaryTargets",
        "dimensionTargets",
        "confidenceBand",
        "distributionBars",
        "evidenceTable",
        "Input quality",
        "Raw model response",
        "Copy JSON",
        "Download JSON",
        "model_only_evaluate",
    )
    for phrase in required_js:
        assert_true(phrase in js, f"model-only UI missing {phrase}")

    forbidden_js = (
        "renderExplorerInput",
        "renderEnterpriseInput",
        "renderEnterpriseResult",
        "Try this rewrite",
        "Generate sample drafts",
        "Generated email draft",
        "Prompt library",
        "Campaign basics",
        "buildEmailVariant",
        "consumerPromptLibrary",
        "data-generate-batch",
        "clarityScore",
    )
    for phrase in forbidden_js:
        assert_true(phrase not in js, f"legacy GPT-like surface leaked into model-only app.js: {phrase}")

    styles = client.get("/static/styles.css")
    assert_true(styles.status_code == 200, f"styles.css returned {styles.status_code}")
    css = styles.get_data(as_text=True)
    assert_true('body[data-mode="model-only"]' in css, "model-only layout styles missing")
    assert_true(".objective-card" in css and ".objective-table" in css, "objective result styles missing")

    health = client.get("/health")
    assert_true(health.status_code == 200, f"health returned {health.status_code}")
    assert_true(health.get_json()["ok"] is True, "public health should report aggregate readiness")
    assert_true(set(health.get_json().keys()) == {"ok"}, "public health should not expose deployment internals")

    session = client.get("/api/session")
    assert_true(session.status_code == 200, "session endpoint missing")
    assert_true(session.get_json()["app"]["auth"] is True, "auth app info missing")

    payload = {
        "text": (
            "I keep thinking about how much a short piece of writing can reveal. "
            "The point is not to judge a person, but to understand how models detect patterns, "
            "where confidence is limited, and why careful interpretation matters."
        ),
        "model": "local",
        "mode": "model-only",
    }
    response = client.post("/evaluate", json=payload, headers=csrf_headers(client))
    assert_true(response.status_code == 200, f"evaluate returned {response.status_code}: {response.get_data(as_text=True)}")
    data = response.get_json()
    predictions = data["predictions"]
    assert_true(data["model"] == "local", "response should identify the local model")
    assert_true("gender" in predictions, "response missing gender prediction")
    assert_true("mbti_dimensions" in predictions, "response missing MBTI dimension predictions")
    assert_true("text_stats" in predictions, "response missing text stats")
    assert_true("input_quality" in predictions, "response missing input-quality metadata")

    print("Smoke tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
