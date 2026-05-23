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
    ui_js = client.get("/static/ui_helpers.js").get_data(as_text=True)
    css = client.get("/static/styles.css").get_data(as_text=True)

    assert_true('aria-live="polite"' in html, "live region missing")
    assert_true('aria-label="Model status"' in html, "model status needs an accessible label")
    assert_true('aria-label="TextTraits workspace"' in html, "workspace landmark label missing")
    assert_true('aria-label="Example inputs"' in js, "sample inputs need an accessible group label")
    assert_true('aria-label="Primary model targets"' in js, "primary result grid needs an accessible label")
    assert_true('aria-label="MBTI dimension distributions"' in js, "dimension grid needs an accessible label")
    assert_true('aria-label="Model evidence table"' in js, "evidence table needs an accessible label")
    assert_true("focus()" in js, "completion focus behavior missing")
    assert_true("announce(" in js, "screen reader announcements missing")
    assert_true("disabled" in js and "state.text.trim()" in js, "empty input disablement missing")
    assert_true("prefers-reduced-motion" in css, "reduced-motion CSS missing")
    assert_true("focus-visible" in css, "visible focus styles missing")
    assert_true("clientError" in js, "client-side error reporting missing")
    assert_true("toast-stack" in html and "toast-stack" in css, "consistent toast region missing")
    assert_true("role=\"status\"" in ui_js and "role=\"alert\"" in ui_js, "shared loading/error states need live semantics")
    assert_true("role=\"status\"" in js and "role=\"alert\"" in js, "model-only loading/error states need live semantics")

    print("Accessibility smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
