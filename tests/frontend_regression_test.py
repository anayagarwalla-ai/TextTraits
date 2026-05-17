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
    csv_js = client.get("/static/csv_utils.js").get_data(as_text=True)
    enterprise_copy_js = client.get("/static/enterprise_copy.js").get_data(as_text=True)
    styles_css = client.get("/static/styles.css").get_data(as_text=True)

    assert_true("workflow" in config_js and "Import" in config_js and "Track" in config_js, "enterprise workflow config missing")
    assert_true("TextTraitsUtils" in utils_js and "escapeHtml" in utils_js, "text utility module missing")
    assert_true("TextTraitsUi" in ui_js and "errorCard" in ui_js, "UI helper module missing")
    assert_true("TextTraitsCsv" in csv_js and "csvCell" in csv_js, "CSV helper module missing")
    assert_true("TextTraitsEnterpriseCopy" in enterprise_copy_js and "inboxReply" in enterprise_copy_js, "Enterprise copy helper module missing")
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
        "selected-prompt",
        "explorerPlaceholder",
        "daily-home-card",
        "streakMilestone",
        "inferExplorerSource",
        "emailRewriteOpener",
        "goalRewriteClose",
        "mobile-result-actions",
    )
    for phrase in explorer_requirements:
        assert_true(phrase in app_js or phrase in html or phrase in config_js, f"Explorer coach flow missing {phrase}")
    assert_true("dailyPromptSample" not in app_js, "Daily prompt should not carry sample responses into the writing field")
    assert_true("input.value = `${prompt.prompt}" not in app_js, "Prompt library should not write prompts into the writing sample")
    assert_true('replace(/^i wanted to send/i, "Quick update:")' not in app_js, "Email rewrite opener should not create duplicated quick-update phrasing")
    assert_true("copyInput) copyInput.disabled = !text.trim()" in app_js, "Copy input should be disabled until the user has text")
    assert_true("confirm(" not in app_js and "accountDeletePending" in app_js, "Account deletion should avoid native confirm dialogs")
    assert_true("showAccountError" in app_js and "passwordPolicyMessage" in app_js, "Account sheet should validate obvious input errors before calling the API")
    assert_true("accountCodePanelOpen" in app_js and "scrollAccountCodePanelIntoView" in app_js, "Email code account panel should stay reachable on mobile")
    assert_true("copyTextFromButton" in app_js and "Clipboard unavailable" in app_js, "Copy actions should handle unavailable clipboard APIs")
    assert_true("sheetIn" in styles_css and "softReveal" in styles_css and "prefers-reduced-motion" in styles_css, "Subtle UI motion should be present and respect reduced motion")
    assert_true("explorerStyleDetailsOpen" in app_js and "explorerQuickChecksOpen" in app_js, "Explorer result drawers should preserve open state during tab changes")
    assert_true("opacity: 0.94" in styles_css and "opacity: 0.96" in styles_css, "Animations should stay subtle enough to avoid blank-feeling transitions")

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
        "data-tree-shortcut",
        "Operations",
        "\"insights\", \"Insights\"",
        "data-enterprise-primary-tab=\"drafts\"",
        "Paste CSV rows or load the sample CSV first.",
        "data-review-row",
        "data-export-row",
        "data-inbox-reply",
        "enterpriseTabNote",
        "enterpriseToolNote",
        "parseCsvLine",
        "enterpriseFocusMode",
        "Focus editor",
        "What changed",
        "Local demo / preview integrations",
    )
    for phrase in enterprise_requirements:
        assert_true(phrase in app_js or phrase in html or phrase in config_js, f"Enterprise workflow missing {phrase}")
    assert_true("integrationSetupOpen" in app_js, "CRM setup actions should open the exact setup section")
    assert_true("Local demo:" in html and "Privacy" in html and "Terms" in html, "Local demo footer should expose trust links")
    assert_true('data-generate-batch ${canGenerate' not in app_js and 'data-generate-batch>Generate batch briefs' in app_js, "Batch generate should stay clickable so empty input can show helpful guidance")

    print("Frontend regression checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
