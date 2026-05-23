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

    assert_true('data-mode="enterprise-optimizer"' in template, "App shell should be locked to the optimizer branch mode")
    assert_true("Enterprise email optimization, without generated copy." in template, "Hero should lead with email optimization")
    assert_true("Explorer" not in template, "Explorer UI should be removed from the shell")
    assert_true("product_config.js" not in template, "Legacy product switcher config should not load")
    assert_true("csv_utils.js" not in template, "CSV helper should not load in the optimizer branch")
    assert_true("enterprise_copy.js" not in template, "Email copy generator should not load in the optimizer branch")
    assert_true("TextTraitsUi" in ui_js and "loadingCard" in ui_js and "errorCard" in ui_js, "Shared UI helper module should hold repeated states")
    assert_true("Scoring the existing email" in ui_js, "Shared loading copy should reference email optimization")

    optimizer_features = (
        "optimizer-form",
        "email-subject",
        "email-body",
        "email-audience",
        "email-intent",
        "emailOptimization",
        "scoreRing",
        "checkCards",
        "modelSignals",
        "rawJsonBlock",
        "copyReport",
        "downloadReport",
        "enterprise-email-optimizer",
        "enterprise_email_optimization",
    )
    for phrase in optimizer_features:
        assert_true(phrase in app_js, f"enterprise optimizer feature missing: {phrase}")

    removed_surfaces = (
        "renderExplorerInput",
        "Try this rewrite",
        "Prompt library",
        "daily-home-card",
        "streakMilestone",
        "inferExplorerSource",
        "goalRewriteClose",
        "data-open-journal",
        "data-apply-journal-filter",
        "selected-prompt",
        "data-generate-sample-drafts",
        "enterpriseFocusMode",
        "lastDraftChange",
        "data-review-draft",
        "data-review-prospect",
        "data-tree-shortcut",
        "parseCsvLine",
        "buildEmailVariant",
        "validateExportReadiness",
        "sendReadyChecklist",
    )
    for phrase in removed_surfaces:
        assert_true(phrase not in app_js, f"legacy non-optimizer surface should not be active: {phrase}")

    assert_true('body[data-mode="enterprise-optimizer"]' in css, "Optimizer styles should be explicit")
    assert_true(".optimizer-form" in css and ".optimizer-result" in css, "Optimizer UI needs dedicated styling")
    assert_true(".optimizer-check-card.needs-work" in css, "Risk checks should be visually distinct")
    assert_true(".optimizer-detail-grid" in css and ".optimizer-bars" in css, "Model distributions should be scannable")
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
