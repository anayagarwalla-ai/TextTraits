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
        "Message Coach Mode",
        "messageModeOptions",
        "Reply triage",
        "replyTriage",
        "Decision Draft Mode",
        "decisionDraft",
        "Personal Style Profile",
    )
    for phrase in explorer_requirements:
        assert_true(phrase in app_js or phrase in html or phrase in config_js, f"Explorer coach flow missing {phrase}")
    assert_true("dailyPromptSample" not in app_js, "Daily prompt should not carry sample responses into the writing field")
    assert_true("input.value = `${prompt.prompt}" not in app_js, "Prompt library should not write prompts into the writing sample")
    assert_true('replace(/^i wanted to send/i, "Quick update:")' not in app_js, "Email rewrite opener should not create duplicated quick-update phrasing")
    assert_true('inferExplorerSource(state.latestText, "")' in app_js, "Explorer reading summary should infer source from pasted text, not the selected rewrite goal")
    assert_true("copyInput) copyInput.disabled = !text.trim()" in app_js, "Copy input should be disabled until the user has text")
    assert_true("confirm(" not in app_js and "accountDeletePending" in app_js, "Account deletion should avoid native confirm dialogs")
    assert_true("showAccountError" in app_js and "passwordPolicyMessage" in app_js, "Account sheet should validate obvious input errors before calling the API")
    assert_true("accountCodePanelOpen" in app_js and "scrollAccountCodePanelIntoView" in app_js, "Email code account panel should stay reachable on mobile")
    assert_true("copyTextFromButton" in app_js and "Clipboard unavailable" in app_js, "Copy actions should handle unavailable clipboard APIs")
    assert_true("sheetIn" in styles_css and "softReveal" in styles_css and "prefers-reduced-motion" in styles_css, "Subtle UI motion should be present and respect reduced motion")
    assert_true("explorerStyleDetailsOpen" in app_js and "explorerQuickChecksOpen" in app_js, "Explorer result drawers should preserve open state during tab changes")
    assert_true("opacity: 0.94" in styles_css and "opacity: 0.96" in styles_css, "Animations should stay subtle enough to avoid blank-feeling transitions")
    assert_true("state.explorerPromptTitle = \"\";" in app_js and "state.explorerPromptSource = \"\";" in app_js, "Explorer sample changes should clear stale daily prompt state")
    assert_true("requestAnimationFrame(() => document.querySelector(\"#explorer-text\")?.focus());" in app_js, "Explorer sample changes should return focus to the writing field")
    assert_true('clean.includes("meeting")' not in app_js, "Explorer source inference should not treat every meeting note as an email")
    assert_true(r"\b(dear|hi|hello)\s+\w+" in app_js and "thanks[, ]+(for|again|so much)" in app_js, "Explorer email inference should use explicit email-like cues")

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
        "Batch QA Mode",
        "batchQaForRow",
        "Outcome Learning",
        "Manager Coaching Layer",
        "managerCoachingInsights",
    )
    for phrase in enterprise_requirements:
        assert_true(phrase in app_js or phrase in html or phrase in config_js, f"Enterprise workflow missing {phrase}")
    assert_true("integrationSetupOpen" in app_js, "CRM setup actions should open the exact setup section")
    assert_true("return state.batchErrors.length ? [] : rows;" in app_js, "Batch CSV should block generated rows when validation errors exist")
    assert_true("state.batchErrors = [];\n    state.batchRows = [];\n    state.batchProgress = 0;\n    state.sampleWorkspaceLoaded = true;" in app_js, "Loading sample CSV should clear stale batch errors before showing valid input")
    assert_true("Local demo:" in html and "Privacy" in html and "Terms" in html, "Local demo footer should expose trust links")
    assert_true('data-generate-batch ${canGenerate' not in app_js and 'data-generate-batch>Generate batch briefs' in app_js, "Batch generate should stay clickable so empty input can show helpful guidance")
    assert_true("starter-sample-panel" not in app_js, "Enterprise setup should not show duplicate sample panels")
    assert_true('enterprise-sample-drawer" ${state.sampleWorkspaceLoaded ? "open" : ""}' in app_js, "Loaded sample workspace should keep the next action visible")
    assert_true("state.batchInput = sampleCsv;" in app_js and "state.batchRows = parseCsv(sampleCsv, state.batchMapping);" in app_js, "Loading sample workspace should populate sample queues, not just show a toast")
    assert_true("Refresh sample data" in app_js and "data-generate-sample-drafts>Generate sample drafts" in app_js, "Loaded sample workspace should still offer sample draft generation")
    assert_true("sendReadyChecklist" in app_js and "Add unsubscribe token before sending" in app_js, "Enterprise draft checklist should reflect real send readiness")
    assert_true('Unsubscribe token present"].map' not in app_js, "Enterprise checklist should not hard-code a successful unsubscribe token")
    assert_true("validateExportReadiness" in app_js, "Enterprise exports should validate send readiness before download")
    assert_true("const validation = validateExportReadiness(variants, context);" in app_js, "CSV export should block invalid drafts")
    assert_true("const validation = validateExportReadiness([draft], context);" in app_js, "Single-draft export should block invalid drafts")
    assert_true("inboxFirstName" in app_js and "{...context, firstName: inboxFirstName(thread) || context.firstName}" in app_js, "Inbox reply drafts should use the selected thread's name")
    assert_true(".send-checklist span.needs-work" in styles_css and ".send-checklist span.is-ok" in styles_css, "Send-readiness checklist should visually distinguish issues from completed items")

    print("Frontend regression checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
