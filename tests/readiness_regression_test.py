from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    template = (ROOT / "texttraits_app/templates/index.html").read_text()
    app_js = (ROOT / "texttraits_app/static/app.js").read_text()
    css = (ROOT / "texttraits_app/static/styles.css").read_text()
    ui_js = (ROOT / "texttraits_app/static/ui_helpers.js").read_text()
    storage_py = (ROOT / "texttraits_app/storage.py").read_text()
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    tracked_clutter = {"Testpush.txt", "made_by_codex.txt", "my_code.txt", "local_website_todo.txt"}

    assert_true('data-mode="model-only"' in template, "App shell should be locked to the model-only branch mode")
    assert_true("Objective text traits from the local model." in template, "Hero should lead with objective model output")
    assert_true("product_config.js" not in template, "Legacy product switcher config should not load")
    assert_true("csv_utils.js" not in template, "CSV helper should not load in the model-only branch")
    assert_true("enterprise_copy.js" not in template, "Enterprise copy generator should not load in the model-only branch")
    assert_true("TextTraitsUi" in ui_js and "loadingCard" in ui_js and "errorCard" in ui_js, "Shared UI helper module should hold repeated states")
    assert_true("Running local model analysis" in ui_js, "Shared loading copy should reference model analysis")

    objective_features = (
        "objective-form",
        "objective-text",
        "objective-count",
        "Run model analysis",
        "primaryTargets",
        "dimensionTargets",
        "inputQualityCard",
        "evidenceTable",
        "rawJsonBlock",
        "copyReport",
        "downloadReport",
        "resultReport",
        "model-only",
        "model_only_evaluate",
    )
    for phrase in objective_features:
        assert_true(phrase in app_js, f"objective model-only feature missing: {phrase}")

    removed_surfaces = (
        "data-generate-sample-drafts",
        "enterpriseLandingTab",
        "data-enterprise-primary-tab",
        "starter-sample-panel",
        "habit-strip",
        "daily-home-card",
        "streakMilestone",
        "inferExplorerSource",
        "goalRewriteClose",
        "data-open-journal",
        "data-apply-journal-filter",
        "selected-prompt",
        "enterprise-focus-band",
        "secondary-workspace-section",
        "enterpriseFocusMode",
        "lastDraftChange",
        "data-review-draft",
        "data-review-prospect",
        "data-tree-shortcut",
        "parseCsvLine",
        "renderAccountCard",
        "copyTextFromButton",
        "Password for export/delete",
    )
    for phrase in removed_surfaces:
        assert_true(phrase not in app_js, f"legacy non-model surface should not be active: {phrase}")

    assert_true('body[data-mode="model-only"]' in css, "Model-only styles should be explicit")
    assert_true(".model-input-form" in css and ".objective-result" in css, "Model-only UI needs dedicated styling")
    assert_true(".objective-table .table-row" in css, "Objective evidence table should be styled")
    assert_true(".objective-detail-grid" in css and ".objective-bars" in css, "Model distributions should be scannable")
    assert_true("opacity: 0.94" in css and "opacity: 0.96" in css, "Motion should polish the UI without creating blank transient states")
    assert_true((ROOT / "scripts/visual_regression_snapshots.py").exists(), "Local visual snapshot script should exist")
    assert_true("schema_migrations" in storage_py, "Database schema should record applied migration baseline")
    assert_true("tests/security_attack_harness.py" in workflow, "CI should run the security attack harness")
    assert_true("tests/accessibility_smoke_test.py" in workflow, "CI should run accessibility smoke checks")
    for name in tracked_clutter:
        assert_true(not (ROOT / name).exists(), f"Remove repo clutter before deploy: {name}")

    print("Readiness regression checks passed.")


if __name__ == "__main__":
    main()
