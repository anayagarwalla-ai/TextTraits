from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    app_js = (ROOT / "texttraits_app/static/app.js").read_text()
    css = (ROOT / "texttraits_app/static/styles.css").read_text()
    ui_js = (ROOT / "texttraits_app/static/ui_helpers.js").read_text()
    csv_js = (ROOT / "texttraits_app/static/csv_utils.js").read_text()
    enterprise_copy_js = (ROOT / "texttraits_app/static/enterprise_copy.js").read_text()
    storage_py = (ROOT / "texttraits_app/storage.py").read_text()
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    tracked_clutter = {"Testpush.txt", "made_by_codex.txt", "my_code.txt", "local_website_todo.txt"}

    assert_true("data-generate-sample-drafts" in app_js, "Enterprise empty state needs a one-click sample draft path")
    assert_true("enterpriseLandingTab" in app_js, "Sample Enterprise generation should be able to land on the dashboard")
    assert_true("data-enterprise-primary-tab" in app_js, "Enterprise header needs a contextual dashboard/review queue action")
    assert_true("starter-sample-panel" in app_js and "starter-sample-panel" in css, "Enterprise setup needs visible starter samples")
    assert_true("habit-strip" in app_js and "habit-strip" in css, "Explorer result should expose calm journal progress")
    assert_true("data-open-journal" in app_js and "data-apply-journal-filter" in app_js, "Explorer journal should be easy to open and filter")
    assert_true("Come back tomorrow" in app_js and 'aria-controls="explorer-journal"' in app_js, "Explorer habit loop should guide the next visit accessibly")
    assert_true("selected-prompt" in app_js and "dailyPromptSample" not in app_js, "Prompt buttons should select guidance without filling user writing")
    assert_true("copyInput) copyInput.disabled = !text.trim()" in app_js, "Empty copy actions should not create no-op clicks")
    assert_true("enterprise-focus-band" in app_js and "secondary-workspace-section" in app_js, "Enterprise dashboard should hide secondary density behind one expandable area")
    assert_true("data-review-draft" in app_js and "data-review-prospect" in app_js, "Enterprise review queue should open the exact draft or prospect")
    assert_true("data-tree-shortcut" in app_js, "Enterprise project sidebar rows should navigate instead of acting as dead buttons")
    assert_true('data-enterprise-primary-tab="drafts"' in app_js and 'data-tab="drafts"' not in app_js, "Only real tabs should use data-tab navigation")
    assert_true("Paste CSV rows or load the sample CSV first." in app_js, "Batch generation should not silently use sample data")
    assert_true("data-review-row" in app_js and "data-export-row" in app_js, "Batch row actions should be real workflow controls")
    assert_true("enterpriseTabNote" in app_js and "enterpriseToolNote" in app_js, "Enterprise workspace notes should match the current tab/tool")
    assert_true("Operations" in app_js and '"insights", "Insights"' in app_js, "Enterprise should avoid too many top-level workspace surfaces")
    assert_true("parseCsvLine" in app_js, "Batch CSV should handle quoted or uneven rows before deploy")
    assert_true("focus-stats" in css and "secondary-workspace-section" in css, "Enterprise density controls need responsive styling")
    assert_true("TextTraitsUi" in ui_js and "loadingCard" in ui_js and "errorCard" in ui_js, "Shared UI helper module should hold repeated states")
    assert_true("TextTraitsCsv" in csv_js and "csvCell" in csv_js, "CSV parsing/export helpers should live outside the main app script")
    assert_true("TextTraitsEnterpriseCopy" in enterprise_copy_js and "buildSequence" in enterprise_copy_js, "Enterprise copy helpers should live outside the main app script")
    assert_true((ROOT / "scripts/visual_regression_snapshots.py").exists(), "Local visual snapshot script should exist")
    assert_true("enterprise-setup-open" in css, "Enterprise setup should stay progressively disclosed")
    assert_true("accountResetToken" in app_js and "prompt(" not in app_js and "confirm(" not in app_js, "Account reset/export/delete should not use native browser dialogs")
    assert_true("accountDeletePending" in app_js and "account-warning" in css, "Account deletion should use an in-app confirmation state")
    assert_true("renderAccountCard();" in app_js and "initAccount" in app_js, "Account card should refresh after session, verification, login, and delete changes")
    assert_true("copyTextFromButton" in app_js, "Copy/export controls should fail gracefully when the clipboard API is unavailable")
    assert_true("Password for export/delete" in app_js, "Sensitive account actions need an in-sheet password field")
    assert_true("schema_migrations" in storage_py, "Database schema should record applied migration baseline")
    assert_true("tests/security_attack_harness.py" in workflow, "CI should run the security attack harness")
    assert_true("tests/accessibility_smoke_test.py" in workflow, "CI should run accessibility smoke checks")
    for name in tracked_clutter:
        assert_true(not (ROOT / name).exists(), f"Remove repo clutter before deploy: {name}")

    print("Readiness regression checks passed.")


if __name__ == "__main__":
    main()
