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
    assert_true("integrationManifests" in api_js and "fieldMappings" in api_js and "saveFieldMapping" in api_js, "v1 integration mapping API helpers should remain available")
    assert_true("openApiContract" in api_js and "installKit" in api_js, "v1 contract export API helpers should remain available")
    assert_true("governancePolicy" in api_js and "saveGovernancePolicy" in api_js, "governance policy API helpers should remain available")
    assert_true("enterpriseIntegrationPlan" in api_js and "simulateAdapter" in api_js and "renderTemplateTest" in api_js, "enterprise simulator API helpers should remain available")
    assert_true("governanceExport" in api_js, "governance export API helper should remain available")
    assert_true("b2bProfile" in api_js, "B2B profile API helper should remain available")

    for route_html in (html, enterprise_html, explorer_html):
        assert_true("Enterprise email optimization, without generated copy." in route_html, "route-level pages should be optimizer-only")
        assert_true("Score existing emails through a stable v1 API" in route_html, "optimizer route copy missing")
        assert_true("never writes the email for you" in route_html, "non-generative positioning missing")
        assert_true("Local build:" in route_html and "Privacy" in route_html and "Terms" in route_html, "footer trust links missing")
        assert_true("Skip to analysis workspace" in route_html and 'aria-current="page"' in route_html, "accessibility navigation affordances missing")
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
        "Production-ready",
        "tt_sbx",
        "tt_prod",
    )
    public_surface = html + app_js
    for phrase in forbidden_public_copy:
        assert_true(phrase not in public_surface, f"legacy or generative public copy leaked: {phrase}")

    optimizer_requirements = (
        "Analyze an existing email",
        "Paste a draft from Gmail, Outlook, Outreach, Salesloft, or your editor.",
        "TextTraits scores it without writing a replacement.",
        "Policy-backed email analysis will appear here.",
        "Enterprise integration lab",
        "Policy score",
        "Structured findings",
        "Severity, category, evidence, remediation",
        "Stable contract",
        "Sandbox adapters",
        "Integration lab status",
        "Governance ledger",
        "Sample imports",
        "Setup manifests",
        "Policy controls",
        "Research targets",
        "Adapter simulator",
        "Paste a provider payload and inspect mapped scoring outputs",
        "Run simulator",
        "Governance policy",
        "Ready score",
        "Storage mode",
        "Environment",
        "Send timeout ms",
        "Idempotency window sec",
        "Rule family behavior",
        "Fail closed",
        "Fail open",
        "Save policy controls",
        "Integration setup",
        "Save recommended mapping",
        "Download OpenAPI JSON",
        "Copy install steps",
        "Contract export",
        "Required inputs:",
        "No replacement email was generated.",
        "Report excludes the full email body.",
        "Subject line",
        "Request ID",
        "Policy bundle",
        "Gate output",
        "Objective model signals",
        "Shown as evidence, not generated writing",
        "Developer-only raw /v1/email/analyze response",
        "Enterprise context fields",
        "Rendered-template test",
        "Run render test",
        "Governance dashboard",
        "Enterprise readiness checklist",
        "Workspace data boundary",
        "Top failing rule packs",
        "Dashboard filters",
        "Source-system trend",
        "Campaign drilldown",
        "Outcome joins",
        "Policy history and audit log",
        "Exports",
        "Export schedule",
        "Guided integration wizard",
        "Choose platform",
        "Validate payload",
        "Run sandbox test",
        "Promote environment",
        "Payload validates",
        "Documented",
        "Needs mapping",
        "Production blocked",
        "Admin settings",
        "Roles and permissions",
        "API key management",
        "Webhook signing setup",
        "Approval queue",
        "Why this score",
        "Model limitations",
        "Non-generative",
        "Security and deployment readiness",
        "Deployment checklist",
        "Analyze",
        "Dashboard",
        "Simulator",
        "Integrations",
        "Admin",
        "B2B profile intelligence",
        "Build a business profile",
        "consented communication history",
        "Build relationship profile",
        "B2B profile report",
        "Relationship intelligence appears",
        "Next best action",
        "Generation guardrails",
        "Safe feature payload",
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
        "scoreExplanation(analysis)",
        "reportJson(data, optimization)",
        "copyReport(button)",
        "downloadReport()",
        "apiClient.analyzeEmail",
        "apiClient.governanceDashboard",
        "apiClient.integrationFlows",
        "apiClient.integrationManifests",
        "apiClient.enterpriseIntegrationPlan",
        "apiClient.simulateAdapter",
        "apiClient.openApiContract",
        "apiClient.installKit",
        "integrationLab(analysis)",
        "labOverview()",
        "enterpriseReadinessChecklist(",
        "setupContracts(manifests, mappings)",
        "recommendedMapping(manifest)",
        "saveRecommendedMapping(provider)",
        "downloadOpenApiContract()",
        "copyInstallSteps()",
        "governancePolicyControls(policy",
        "governanceDashboardPanels(dashboard",
        "dashboardTrendCharts(dashboard",
        "dashboardEmptyState(title)",
        "exportsPanel()",
        "saveExportSchedule()",
        "downloadGovernanceExport(kind",
        "currentEnterpriseContext()",
        "renderTestSummary(result)",
        "runRenderTest()",
        "findingActionMeta(finding",
        "simulatorValidation(state.simulatorProvider",
        "simulatorResultSummary(state.simulatorResult",
        "bindNavigation()",
        "ruleFamilyLabel(family)",
        "ruleModeLabel(mode)",
        "adapterSimulator(plan, manifests)",
        "runAdapterSimulator()",
        "adminSettingsPanel({policy",
        "apiKeyManagementPanel()",
        "webhookSigningPanel()",
        "approvalQueuePanel(dashboard",
        "profileBuilder()",
        "b2bProfileReport()",
        "buildB2BProfile()",
        "apiClient.b2bProfile",
        "trustAndDeploymentPanel(policy",
        "createLocalApiKeyProfile()",
        "runWebhookSignatureTest()",
        "errorRecoverySteps(message",
        "currentPolicyFromForm()",
        "savePolicyControls()",
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
        ".integration-lab-overview",
        ".lab-status-card",
        ".setup-contracts",
        ".setup-contract-card",
        ".setup-action-row",
        ".governance-policy-controls",
        ".enterprise-nav",
        ".skip-link",
        ".enterprise-context-panel",
        ".render-test-card",
        ".governance-dashboard",
        ".dashboard-panel-grid",
        ".export-center",
        ".policy-history-panel",
        ".setup-wizard",
        ".status-badge",
        ".rule-family-control-group",
        ".rule-family-grid",
        ".adapter-simulator",
        ".adapter-simulator-grid",
        ".adapter-simulator-result",
        ".dashboard-filter-grid",
        ".trend-chart-grid",
        ".dashboard-empty-state",
        ".approval-queue-grid",
        ".approval-action-row",
        ".admin-settings-panel",
        ".role-grid",
        ".api-key-list",
        ".trust-deployment-panel",
        ".b2b-profile-builder",
        ".b2b-profile-report",
        ".profile-report-grid",
        ".profile-playbook",
        ".score-explanation-grid",
        ".hash-line",
        ".policy-control-grid",
        ".policy-toggle-row",
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
    assert_true(".enterprise-nav" in styles_css and "position: static;" in styles_css, "transparent nav should not overlay page content while scrolling")

    print("Frontend regression checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
