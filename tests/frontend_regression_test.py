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
    utils_js = client.get("/static/text_utils.js").get_data(as_text=True)
    ui_js = client.get("/static/ui_helpers.js").get_data(as_text=True)
    styles_css = client.get("/static/styles.css").get_data(as_text=True)

    assert_true("TextTraitsUtils" in utils_js and "escapeHtml" in utils_js, "text utility module missing")
    assert_true("TextTraitsUi" in ui_js and "errorCard" in ui_js, "UI helper module missing")
    assert_true("resetPassword" in api_js and "verifyEmail" in api_js, "account API helpers should remain available")
    assert_true("oauth/start" in api_js or "integrationProviders" in api_js, "integration setup helpers should remain available")

    for route_html in (html, enterprise_html, explorer_html):
        assert_true("Objective text traits from the local model." in route_html, "route-level product pages should be model-only")
        assert_true("Analyze writing through prediction distributions" in route_html, "model-only route copy missing")
        assert_true("Local demo:" in route_html and "Privacy" in route_html and "Terms" in route_html, "footer trust links missing")

    forbidden_public_copy = (
        "Write a little clearer every day",
        "Explorer",
        "Enterprise",
        "Generate sample drafts",
        "Prompt library",
        "Try this rewrite",
        "Generated email draft",
        "Campaign basics",
        "Chrome sidebar preview",
        "Gmail / Outlook inbox mode",
        "model separation",
        "strong confidence",
        "Trans/other source label",
    )
    public_surface = html + app_js
    for phrase in forbidden_public_copy:
        assert_true(phrase not in public_surface, f"legacy or confusing public copy leaked: {phrase}")

    model_only_requirements = (
        "Analyze one text sample",
        "Results are limited to trained model targets and computed text statistics.",
        "Prediction distributions will appear here.",
        "Local inference",
        "MBTI dimensions",
        "Age and language-association targets",
        "Confidence margins",
        "Cue terms",
        "16-class style target",
        "Language-association target",
        "Age-bucket target",
        "Age-estimate target",
        "Energy dimension",
        "Information dimension",
        "Decision dimension",
        "Structure dimension",
        "Evidence table",
        "Returned model fields",
        "Input quality",
        "No input-quality warnings returned by the model pipeline.",
        "Raw model response",
    )
    for phrase in model_only_requirements:
        assert_true(phrase in app_js or phrase in html, f"model-only workflow missing {phrase}")

    implementation_requirements = (
        "confidenceBand",
        "confidence(prediction)",
        "margin(prediction)",
        "cueTerms(prediction)",
        "distributionBars(prediction)",
        "inputQualityCard(predictions)",
        "evidenceTable(predictions)",
        "rawJsonBlock(data)",
        "resultReport(data)",
        "copyReport(button)",
        "downloadReport()",
        "bindResultActions()",
        "renderError(state.latestError)",
        "apiClient.clientError?.({message: state.latestError, source: \"model-only\"})",
        "trackEvent(\"model_only_evaluate\"",
    )
    for phrase in implementation_requirements:
        assert_true(phrase in app_js, f"model-only implementation missing {phrase}")

    legacy_implementation = (
        "function rewriteTitle",
        "withTerminalPunctuation",
        "inferExplorerSource",
        "goalRewriteClose",
        "consumerPromptLibrary",
        "sampleInboxThreads",
        "winnerPatterns",
        "managerCoachingInsights",
        "validateExportReadiness",
        "sendReadyChecklist",
        "enterpriseFocusMode",
        "accountDeletePending",
        "trapAccountFocus",
    )
    for phrase in legacy_implementation:
        assert_true(phrase not in app_js, f"legacy implementation should not run in model-only branch: {phrase}")

    style_requirements = (
        'body[data-mode="model-only"] .app-shell',
        'body[data-mode="model-only"] .topbar',
        'body[data-mode="model-only"] .workspace',
        ".model-only-card",
        ".model-input-form",
        ".objective-result",
        ".objective-section",
        ".objective-samples",
        ".objective-actions",
        ".objective-hero-card",
        ".objective-grid",
        ".primary-objective-grid",
        ".objective-card",
        ".objective-detail-card",
        ".objective-quality-card",
        ".objective-table",
        ".objective-json pre",
        ".cue-row",
        "prefers-reduced-motion",
        "focus-visible",
    )
    for phrase in style_requirements:
        assert_true(phrase in styles_css, f"model-only styling missing {phrase}")

    assert_true("sheetIn" in styles_css and "softReveal" in styles_css, "subtle UI motion should stay available")
    assert_true(".mode-chip:hover:not(:disabled)" in styles_css, "button hover states should remain subtle and readable")
    assert_true(".sample-card:hover:not(:disabled)" in styles_css, "sample hover state should remain readable")
    assert_true("grid-template-columns: repeat(4, minmax(0, 1fr))" in styles_css, "primary cards should use stable grid tracks")
    assert_true("overflow-x: auto" in styles_css, "model evidence table should handle narrow screens")

    print("Frontend regression checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
