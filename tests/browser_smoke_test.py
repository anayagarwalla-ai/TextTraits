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
    html = client.get("/").get_data(as_text=True)
    explorer_html = client.get("/explorer").get_data(as_text=True)
    enterprise_html = client.get("/enterprise").get_data(as_text=True)
    js = client.get("/static/app.js").get_data(as_text=True)
    api_js = client.get("/static/api_client.js").get_data(as_text=True)
    utils_js = client.get("/static/text_utils.js").get_data(as_text=True)
    ui_js = client.get("/static/ui_helpers.js").get_data(as_text=True)
    css = client.get("/static/styles.css").get_data(as_text=True)

    for route_html in (html, explorer_html, enterprise_html):
        assert_true("Enterprise email optimization, without generated copy." in route_html, "route should render optimizer shell")
        assert_true("Enterprise optimizer" in route_html, "route should render optimizer status")
        assert_true("Explorer" not in route_html, "Explorer route should not expose Explorer UI")
        assert_true("product_config.js" not in route_html, "legacy product module should not load")
        assert_true("csv_utils.js" not in route_html, "CSV module should not load")
        assert_true("enterprise_copy.js" not in route_html, "email generation module should not load")

    assert_true("TextTraitsApi" in api_js and "evaluate" in api_js, "API client global missing")
    assert_true("clientError" in api_js and "event:" in api_js, "client error/event helpers should remain available")
    assert_true("TextTraitsUtils" in utils_js and "localStats" in utils_js and "escapeHtml" in utils_js, "shared text utility module missing")
    assert_true("TextTraitsUi" in ui_js and "loadingCard" in ui_js and "errorCard" in ui_js, "shared UI helper module missing")

    required_app_features = (
        "samples",
        "Follow-up",
        "Cold outreach",
        "Reply",
        "emailOptimization",
        "scoreLength",
        "scoreSubject",
        "scoreClarity",
        "scoreBuyerFocus",
        "scoreRing",
        "checkCards",
        "modelSignals",
        "rawJsonBlock",
        "apiClient.evaluate",
        "mode: \"enterprise-email-optimizer\"",
        "apiClient.clientError",
    )
    for phrase in required_app_features:
        assert_true(phrase in js, f"enterprise optimizer path missing {phrase}")

    forbidden_app_features = (
        "role=\"tab\"",
        "workspace-tabs",
        "renderAccountCard",
        "daily-home-card",
        "reviewQueueTable",
        "recordExport",
        "buildEmailVariant",
        "parseCsvLine",
        "batchRowsHtml",
        "mobile-result-actions",
        "data-open-journal",
        "data-enterprise-primary-tab",
        "data-generate-sample-drafts",
    )
    for phrase in forbidden_app_features:
        assert_true(phrase not in js, f"legacy app surface should not be active: {phrase}")

    assert_true('body[data-mode="enterprise-optimizer"] .workspace' in css, "optimizer workspace layout missing")
    assert_true(".optimizer-form" in css, "optimizer input form styling missing")
    assert_true(".optimizer-summary-grid" in css, "optimization summary styling missing")
    assert_true(".optimizer-check-grid" in css, "send readiness styling missing")
    assert_true(".optimizer-json pre" in css, "raw JSON styling missing")
    assert_true("@media (max-width: 700px)" in css, "responsive breakpoint missing")
    assert_true((ROOT / "scripts/visual_regression_snapshots.py").exists(), "visual regression snapshot script missing")

    print("Browser smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
