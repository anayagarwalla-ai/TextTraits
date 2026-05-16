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
    enterprise_html = client.get("/enterprise").get_data(as_text=True)
    explorer_html = client.get("/explorer").get_data(as_text=True)
    app_js = client.get("/static/app.js").get_data(as_text=True)
    api_js = client.get("/static/api_client.js").get_data(as_text=True)
    config_js = client.get("/static/product_config.js").get_data(as_text=True)
    utils_js = client.get("/static/text_utils.js").get_data(as_text=True)
    ui_js = client.get("/static/ui_helpers.js").get_data(as_text=True)

    assert_true("workflow" in config_js and "Import" in config_js and "Track" in config_js, "enterprise workflow config missing")
    assert_true("TextTraitsUtils" in utils_js and "escapeHtml" in utils_js, "text utility module missing")
    assert_true("TextTraitsUi" in ui_js and "errorCard" in ui_js, "UI helper module missing")
    assert_true("TextTraits" in enterprise_html and "TextTraits" in explorer_html, "route-level product pages missing")
    assert_true("resetPassword" in api_js and "verifyEmail" in api_js, "account API helpers missing")
    assert_true("oauth/start" in api_js or "integrationProviders" in api_js, "integration setup helpers missing")

    forbidden_public_copy = (
        "model separation",
        "classifier",
        "strong confidence",
        "Trans/other source label",
    )
    public_surface = html + config_js
    for phrase in forbidden_public_copy:
        assert_true(phrase not in public_surface, f"forbidden public copy leaked: {phrase}")

    explorer_requirements = (
        "How does this come across?",
        "What should I change?",
        "Try this rewrite",
        "Make clearer",
        "Make warmer",
        "Make shorter",
        "weekly-recap-page",
        "journal-search",
        "sourceExcerpt",
        "data-open-journal",
        "data-apply-journal-filter",
    )
    for phrase in explorer_requirements:
        assert_true(phrase in app_js or phrase in html or phrase in config_js, f"Explorer coach flow missing {phrase}")

    enterprise_requirements = (
        "Today's work",
        "Review queue",
        "Copy draft",
        "CSV",
        "CRM setup",
        "Email setup",
        "status-token",
        "data-review-draft",
        "data-review-prospect",
        "Paste CSV rows or load the sample CSV first.",
        "enterpriseTabNote",
        "enterpriseToolNote",
    )
    for phrase in enterprise_requirements:
        assert_true(phrase in app_js or phrase in html or phrase in config_js, f"Enterprise workflow missing {phrase}")

    print("Frontend regression checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
