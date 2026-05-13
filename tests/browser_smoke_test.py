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
    assert_true('role="tab"' in js, "tab role semantics missing")
    assert_true("action.disabled = !text.trim()" in js, "empty input disablement missing")
    assert_true("data-sample-target" in js, "sample-driven input path missing")
    assert_true("Hi {{first_name}}" in js, "merge-field placeholder rendering missing")
    assert_true("Worth a quick 15-minute fit call?" in js, "CTA grammar fix missing")
    assert_true("data-mode=\"enterprise\"" in css, "Enterprise visual theme missing")
    assert_true("@media (max-width: 700px)" in css, "Responsive breakpoint missing")

    print("Browser smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
