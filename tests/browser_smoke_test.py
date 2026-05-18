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
    js = client.get("/static/app.js").get_data(as_text=True)
    css = client.get("/static/styles.css").get_data(as_text=True)

    assert_true('id="mode-explorer"' in html, "Explorer mode control missing")
    assert_true('id="mode-enterprise"' in html, "Enterprise mode control missing")
    assert_true("renderExplorerInput" in js, "Explorer render path missing")
    assert_true("renderEnterpriseInput" in js, "Enterprise render path missing")
    assert_true("renderEnterpriseResult" in js, "Enterprise result path missing")
    assert_true("buildEmailVariant" in js, "Enterprise draft generator missing")
    assert_true("subjectLines" in js, "Subject variant generator missing")
    assert_true("channelPreview" in js, "Channel preview generator missing")
    assert_true("downloadCsv" in js, "CSV export path missing")
    assert_true("validateMergeFields" in js, "Merge field validation missing")
    assert_true("transformDraft" in js, "Draft transforms missing")
    assert_true("saveCurrentCampaign" in js, "Saved campaign workflow missing")
    assert_true("resolveMergeFields" in js, "Resolved preview path missing")
    assert_true("workspace-tabs" in js, "Enterprise workspace tabs missing")
    assert_true("grouped-tabs" in js, "Grouped enterprise navigation missing")
    assert_true("activeEnterpriseTool" in js, "Grouped tool navigation missing")
    assert_true("campaignHome" in js, "Campaign home workspace missing")
    assert_true("draftsWorkspace" in js, "Focused draft workspace missing")
    assert_true("analyticsWorkspace" in js, "Analytics workspace missing")
    assert_true("parseCsv" in js, "Batch CSV parser missing")
    assert_true("batchRowsHtml" in js, "Batch result renderer missing")
    assert_true("sampleInboxThreads" in js, "Inbox reply samples missing")
    assert_true("winnerPatterns" in js, "Winner learning missing")
    assert_true("outcomeGrid" in js, "Outcome tracking missing")
    assert_true("crmConnections" in js, "CRM connection states missing")
    assert_true('role="tab"' in js, "tab role semantics missing")
    assert_true("action.disabled = !text.trim()" in js, "empty input disablement missing")
    assert_true("data-sample-target" in js, "sample-driven input path missing")
    assert_true("Hi {{first_name}}" in js, "merge-field placeholder rendering missing")
    assert_true("Worth a quick 15-minute fit call?" in js, "CTA grammar fix missing")
    assert_true("data-mode=\"enterprise\"" in css, "Enterprise visual theme missing")
    assert_true("enterprise-collapsed" in css, "Collapsed enterprise layout missing")
    assert_true("editor-workspace" in css, "Email editor layout missing")
    assert_true("variant-row" in css, "Variant comparison layout missing")
    assert_true("batch-table" in css, "Batch table layout missing")
    assert_true("project-sidebar" in css, "Project sidebar layout missing")
    assert_true("flow-path" in css, "Workflow path layout missing")
    assert_true("prospect-table" in css, "Prospect table layout missing")
    assert_true("tool-switcher" in css, "Tool switcher layout missing")
    assert_true("inbox-list" in css, "Inbox layout missing")
    assert_true("outcome-grid" in css, "Outcome tracking layout missing")
    assert_true("@media (max-width: 700px)" in css, "Responsive breakpoint missing")

    print("Browser smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
