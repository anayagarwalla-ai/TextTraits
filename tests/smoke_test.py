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


def main() -> int:
    client = app_module.app.test_client()

    home = client.get("/")
    assert_true(home.status_code == 200, f"home returned {home.status_code}")
    html = home.get_data(as_text=True)
    assert_true("Write a little clearer every day" in html, "public heading missing")
    assert_true("Enterprise" in html, "enterprise mode toggle missing")
    assert_true("static/app.js" in html, "app script missing")
    assert_true("static/styles.css" in html, "stylesheet missing")
    assert_true("Strong confidence" not in html, "truth-confidence wording should not render")
    removed_decision_word = "conse" + "quential"
    assert_true(removed_decision_word not in html.lower(), "removed warning copy should not render")
    removed_phrase = "may be " + "wron" + "g"
    assert_true(removed_phrase not in html.lower(), "removed warning copy should not render")
    assert_true("Developer tools" not in html, "developer tools should be hidden by default")
    assert_true("response-debug" not in html, "raw response debug should be hidden by default")
    assert_true("model_path" not in html, "model internals should not render in public HTML")

    app_js = client.get("/static/app.js")
    assert_true(app_js.status_code == 200, f"app.js returned {app_js.status_code}")
    js = app_js.get_data(as_text=True)
    assert_true("Core campaign context" in js, "enterprise campaign context missing")
    assert_true("Generated email draft" in js, "enterprise draft path missing")
    assert_true("{{first_name}}" in js, "merge field placeholder missing")
    assert_true("Copy subject lines" in js, "subject copy action missing")
    assert_true("Validate and export CSV" in js, "CSV export action missing")
    assert_true("Save campaign" in js, "saved campaign action missing")
    assert_true("Resolved preview" in js, "resolved preview missing")
    assert_true("Brand voice" in js, "brand voice profiles missing")
    assert_true("Generate next variant" in js, "feedback variant action missing")
    assert_true("Saved workspaces" in js, "workspace management missing")
    assert_true("Batch CSV upload" in js, "batch CSV workflow missing")
    assert_true("Gmail / Outlook inbox mode" in js, "inbox reply mode missing")
    assert_true("Chrome sidebar preview" in js, "Chrome sidebar preview missing")
    assert_true("Learn from winners" in js, "winner learning workflow missing")
    assert_true("Contact and persona database" in js, "persona database missing")
    assert_true("Full sequence builder" in js, "sequence builder missing")
    assert_true("Today's work" in js, "queue dashboard missing")
    assert_true("Import prospects" in js, "primary workflow path missing")
    assert_true("Workspace" in js, "project sidebar missing")
    assert_true("Review queue" in js, "draft review queue missing")
    assert_true("Download export CSV" in js, "batch export action missing")
    assert_true("Gmail / Outlook reply queue" in js, "reply queue missing")
    assert_true("First read" in js, "Explorer simple summary missing")
    assert_true("Today's prompt" in js, "Explorer daily prompt missing")
    assert_true("Writing log" in js, "Explorer writing log missing")
    assert_true("Save this reading" in js, "Explorer save-reading workflow missing")
    assert_true("Make clearer" in js, "Explorer rewrite action missing")
    assert_true(removed_decision_word not in js.lower(), "removed warning copy should not render in JS")
    assert_true(removed_phrase not in js.lower(), "removed warning copy should not render in JS")

    styles = client.get("/static/styles.css")
    assert_true(styles.status_code == 200, f"styles.css returned {styles.status_code}")

    health = client.get("/health")
    assert_true(health.status_code == 200, f"health returned {health.status_code}")
    assert_true("model" in health.get_json(), "health payload missing model")

    payload = {
        "text": (
            "I keep thinking about how much a short piece of writing can reveal. "
            "The point is not to judge a person, but to understand how models detect patterns, "
            "where confidence is limited, and why careful interpretation matters."
        ),
        "model": "local",
    }
    response = client.post("/evaluate", json=payload)
    assert_true(response.status_code == 200, f"evaluate returned {response.status_code}: {response.get_data(as_text=True)}")
    data = response.get_json()
    assert_true("predictions" in data, "response missing predictions")
    assert_true("gender" in data["predictions"], "response missing gender prediction")
    assert_true("text_stats" in data["predictions"], "response missing text stats")

    print("Smoke tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
