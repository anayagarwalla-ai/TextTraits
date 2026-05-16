from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    app_js = (ROOT / "texttraits_app/static/app.js").read_text()
    css = (ROOT / "texttraits_app/static/styles.css").read_text()
    storage_py = (ROOT / "texttraits_app/storage.py").read_text()
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    tracked_clutter = {"Testpush.txt", "made_by_codex.txt", "my_code.txt", "local_website_todo.txt"}

    assert_true("data-generate-sample-drafts" in app_js, "Enterprise empty state needs a one-click sample draft path")
    assert_true("enterpriseLandingTab" in app_js, "Sample Enterprise generation should be able to land on the dashboard")
    assert_true("data-enterprise-primary-tab" in app_js, "Enterprise header needs a contextual dashboard/review queue action")
    assert_true("starter-sample-panel" in app_js and "starter-sample-panel" in css, "Enterprise setup needs visible starter samples")
    assert_true("habit-strip" in app_js and "habit-strip" in css, "Explorer result should expose calm journal progress")
    assert_true("enterprise-focus-band" in app_js and "secondary-workspace-section" in app_js, "Enterprise dashboard should hide secondary density behind one expandable area")
    assert_true("focus-stats" in css and "secondary-workspace-section" in css, "Enterprise density controls need responsive styling")
    assert_true("enterprise-setup-open" in css, "Enterprise setup should stay progressively disclosed")
    assert_true("accountResetToken" in app_js and "prompt(" not in app_js, "Account reset/export/delete should not use native prompt dialogs")
    assert_true("Password for export/delete" in app_js, "Sensitive account actions need an in-sheet password field")
    assert_true("schema_migrations" in storage_py, "Database schema should record applied migration baseline")
    assert_true("tests/security_attack_harness.py" in workflow, "CI should run the security attack harness")
    assert_true("tests/accessibility_smoke_test.py" in workflow, "CI should run accessibility smoke checks")
    for name in tracked_clutter:
        assert_true(not (ROOT / name).exists(), f"Remove repo clutter before deploy: {name}")

    print("Readiness regression checks passed.")


if __name__ == "__main__":
    main()
