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
        assert_true("Enterprise email optimization, without generated copy." in route_html, "route-level pages should be optimizer-only")
        assert_true("Score existing emails with local model signals" in route_html, "optimizer route copy missing")
        assert_true("never writes the email for you" in route_html, "non-generative positioning missing")
        assert_true("Local demo:" in route_html and "Privacy" in route_html and "Terms" in route_html, "footer trust links missing")
        assert_true("Explorer" not in route_html, "Explorer copy should not render")

    forbidden_public_copy = (
        "Write a little clearer every day",
        "A simple writing coach",
        "Generate sample drafts",
        "Prompt library",
        "Try this rewrite",
        "Generated email draft",
        "Campaign basics",
        "Full sequence builder",
        "Chrome sidebar preview",
        "Gmail / Outlook inbox mode",
    )
    public_surface = html + app_js
    for phrase in forbidden_public_copy:
        assert_true(phrase not in public_surface, f"legacy or generative public copy leaked: {phrase}")

    optimizer_requirements = (
        "Analyze an existing email",
        "Paste a draft from Gmail, Outlook, Outreach, Salesloft, or your editor.",
        "TextTraits scores it without writing a replacement.",
        "Email quality report will appear here.",
        "Optimization layer",
        "Optimization score",
        "Send-readiness checks",
        "What to optimize before sending",
        "Works beside existing tools",
        "No replacement email was generated.",
        "Report excludes the full email body.",
        "Subject line",
        "Body length",
        "Next step",
        "Specificity",
        "Clarity",
        "Buyer focus",
        "Objective model signals",
        "Shown as evidence, not generated writing",
        "Raw model response",
    )
    for phrase in optimizer_requirements:
        assert_true(phrase in app_js or phrase in html, f"optimizer workflow missing {phrase}")

    implementation_requirements = (
        "emailOptimization(subject, email)",
        "scoreLength(wordCount)",
        "scoreSubject(subject)",
        "scoreClarity(stats, text)",
        "scoreBuyerFocus(text)",
        "ctaPattern",
        "datePattern",
        "vagueTerms",
        "hypeTerms",
        "scoreRing(optimization)",
        "checkCards(optimization)",
        "modelSignalCard(target, prediction)",
        "modelSignals(predictions)",
        "rawJsonBlock(data)",
        "reportJson(data, optimization)",
        "copyReport(button)",
        "downloadReport()",
        "trackEvent(\"enterprise_email_optimization\"",
        "apiClient.clientError?.({message: state.latestError, source: \"enterprise-email-optimizer\"})",
    )
    for phrase in implementation_requirements:
        assert_true(phrase in app_js, f"optimizer implementation missing {phrase}")

    legacy_implementation = (
        "function rewriteTitle",
        "inferExplorerSource",
        "consumerPromptLibrary",
        "sampleInboxThreads",
        "winnerPatterns",
        "managerCoachingInsights",
        "validateExportReadiness",
        "sendReadyChecklist",
        "enterpriseFocusMode",
        "buildEmailVariant",
        "subjectLines",
        "channelPreview",
    )
    for phrase in legacy_implementation:
        assert_true(phrase not in app_js, f"legacy implementation should not run in optimizer branch: {phrase}")

    style_requirements = (
        'body[data-mode="enterprise-optimizer"]',
        'body[data-mode="enterprise-optimizer"] .topbar',
        'body[data-mode="enterprise-optimizer"] .workspace',
        ".optimizer-status-card",
        ".optimizer-form",
        ".optimizer-empty",
        ".optimizer-result",
        ".optimizer-summary-grid",
        ".optimizer-score-card",
        ".optimizer-context-card",
        ".optimizer-check-card",
        ".optimizer-model-card",
        ".optimizer-check-grid",
        ".optimizer-detail-grid",
        ".optimizer-json pre",
        ".score-track",
        ".cue-row",
        "prefers-reduced-motion",
        "focus-visible",
    )
    for phrase in style_requirements:
        assert_true(phrase in styles_css, f"optimizer styling missing {phrase}")

    assert_true("sheetIn" in styles_css and "softReveal" in styles_css, "subtle UI motion should stay available")
    assert_true(".sample-card:hover:not(:disabled)" in styles_css, "sample hover state should remain readable")
    assert_true("grid-template-columns: repeat(3, minmax(0, 1fr))" in styles_css, "check cards should use stable grid tracks")

    print("Frontend regression checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
