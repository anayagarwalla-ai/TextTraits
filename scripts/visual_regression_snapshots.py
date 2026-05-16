from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "visual-regression"
PORT = int(os.environ.get("TEXTTRAITS_VISUAL_PORT", "5042"))
BASE = f"http://127.0.0.1:{PORT}"


EXPLORER_SAMPLE = (
    "I wanted to send a quick update because the project is moving, but the next steps still feel a little scattered. "
    "We finished the research, found two confusing handoff points, and should decide by Friday who owns the customer notes, "
    "the design review, and the final message to the group."
)


def wait_for_server() -> None:
    import urllib.request

    deadline = time.time() + 20
    while time.time() < deadline:
      try:
          with urllib.request.urlopen(f"{BASE}/health", timeout=1) as response:
              if response.status == 200:
                  return
      except Exception:
          time.sleep(0.25)
    raise RuntimeError("Timed out waiting for local TextTraits server")


def main() -> int:
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        print(f"Playwright is not installed in this Python environment: {exc}", file=sys.stderr)
        print("Install it locally or run the existing smoke tests instead.", file=sys.stderr)
        return 2

    OUT.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "PORT": str(PORT),
        "TEXTTRAITS_SECRET_KEY": "visual-regression-local",
        "TEXTTRAITS_DB_PATH": "/tmp/texttraits-visual-regression.sqlite3",
    }
    server = subprocess.Popen(
        [sys.executable, "texttraits_app/app.py"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    try:
        wait_for_server()
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
            page = context.new_page()

            page.goto(f"{BASE}/explorer?visual=1", wait_until="load")
            page.screenshot(path=str(OUT / "explorer-empty.png"), full_page=False)
            page.locator("#explorer-text").fill(EXPLORER_SAMPLE)
            page.locator("#analyze-explorer").click()
            expect(page.get_by_text("How this comes across", exact=True)).to_be_visible(timeout=15000)
            page.screenshot(path=str(OUT / "explorer-result.png"), full_page=False)

            page.goto(f"{BASE}/enterprise?visual=1", wait_until="load")
            page.screenshot(path=str(OUT / "enterprise-empty.png"), full_page=False)
            page.get_by_role("button", name="Generate sample drafts").click()
            expect(page.get_by_text("Sample workspace ready. Next: open the review queue.", exact=True)).to_be_visible(timeout=15000)
            page.screenshot(path=str(OUT / "enterprise-dashboard.png"), full_page=False)
            page.get_by_role("button", name="Open review queue").click()
            expect(page.get_by_text("Review generated drafts", exact=True)).to_be_visible(timeout=10000)
            page.screenshot(path=str(OUT / "enterprise-drafts.png"), full_page=False)

            page.set_viewport_size({"width": 390, "height": 844})
            page.goto(f"{BASE}/enterprise?visual=mobile", wait_until="load")
            page.get_by_role("button", name="Generate sample drafts").click()
            expect(page.get_by_text("Sample workspace ready. Next: open the review queue.", exact=True)).to_be_visible(timeout=15000)
            page.screenshot(path=str(OUT / "enterprise-mobile.png"), full_page=False)
            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()

    print(f"Visual regression snapshots written to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
