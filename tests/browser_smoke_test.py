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

    assert_true("TextTraitsApi" in api_js and "evaluate" in api_js and "analyzeEmail" in api_js, "API client global missing")
    assert_true("clientError" in api_js and "event:" in api_js, "client error/event helpers should remain available")
    assert_true("governanceExport" in api_js and "renderTemplateTest" in api_js, "enterprise export/render helpers should remain available")
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
        "apiClient.analyzeEmail",
        "policy_bundle: state.policyBundle",
        "integrationLab",
        "labOverview",
        "bindNavigation",
        "currentEnterpriseContext",
        "runRenderTest",
        "governanceDashboardPanels",
        "dashboardTrendCharts",
        "approvalQueuePanel",
        "scoreExplanation",
        "adminSettingsPanel",
        "apiKeyManagementPanel",
        "webhookSigningPanel",
        "trustAndDeploymentPanel",
        "saveExportSchedule",
        "createLocalApiKeyProfile",
        "runWebhookSignatureTest",
        "errorRecoverySteps",
        "enterpriseReadinessChecklist",
        "downloadGovernanceExport",
        "governanceDashboard",
        "enterpriseIntegrationPlan",
        "governancePolicy",
        "saveGovernancePolicy",
        "simulateAdapter",
        "integrationManifests",
        "fieldMappings",
        "saveFieldMapping",
        "openApiContract",
        "installKit",
        "downloadOpenApiContract",
        "copyInstallSteps",
        "governancePolicyControls",
        "ruleFamilyLabel",
        "ruleModeLabel",
        "adapterSimulator",
        "runAdapterSimulator",
        "savePolicyControls",
        "recommendedMapping",
        "saveRecommendedMapping",
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
    assert_true(".governance-policy-controls" in css, "governance policy styling missing")
    assert_true(".enterprise-readiness-panel" in css and ".readiness-grid" in css, "enterprise readiness styling missing")
    assert_true(".rule-family-control-group" in css and ".rule-family-grid" in css, "rule family policy styling missing")
    assert_true(".adapter-simulator" in css and ".adapter-simulator-result" in css, "adapter simulator styling missing")
    assert_true(".enterprise-nav" in css and ".legal-shell" in css, "persistent nav and legal page styling missing")
    assert_true(".dashboard-filter-grid" in css and ".trend-chart-grid" in css, "dashboard filters and trend styling missing")
    assert_true(".approval-queue-grid" in css and ".approval-action-row" in css and ".admin-settings-panel" in css, "approval/admin styling missing")
    assert_true(".api-key-list" in css and ".trust-deployment-panel" in css, "API/trust styling missing")
    assert_true(".hash-line" in css and "overflow-wrap: anywhere" in css, "hash overflow protection missing")
    assert_true(".optimizer-json pre" in css, "raw JSON styling missing")
    assert_true("@media (max-width: 700px)" in css, "responsive breakpoint missing")
    assert_true((ROOT / "scripts/visual_regression_snapshots.py").exists(), "visual regression snapshot script missing")

    print("Browser smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
