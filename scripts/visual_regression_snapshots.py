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


EMAIL_SUBJECT = "Next step after Tuesday"
EMAIL_BODY = (
    "Hi Maya, thanks for walking through the renewal workflow on Tuesday. "
    "The strongest gap I heard was that managers see risk after the forecast is already under pressure. "
    "If helpful, I can send a two-minute benchmark showing how teams flag coaching moments earlier. "
    "Would Thursday afternoon work for a quick fit check?"
)

RISKY_SUBJECT = "FREE guaranteed result for {{ first_name }}"
RISKY_BODY = (
    "Hi {{ first_name }}, this is a guaranteed game-changing offer with lots of things and stuff. "
    "Visit https://a.example https://b.example https://c.example https://d.example"
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
    for snapshot in OUT.glob("*.png"):
        snapshot.unlink()
    env = {
        **os.environ,
        "PORT": str(PORT),
        "TEXTTRAITS_SECRET_KEY": "visual-regression-local",
        "TEXTTRAITS_DATABASE_URL": "",
        "DATABASE_URL": "",
        "TEXTTRAITS_DB_PATH": "/tmp/texttraits-visual-regression.sqlite3",
    }
    Path(env["TEXTTRAITS_DB_PATH"]).unlink(missing_ok=True)
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

            page.goto(f"{BASE}/?visual=1", wait_until="load")
            expect(page.get_by_text("Enterprise email optimization, without generated copy.", exact=True)).to_be_visible(timeout=10000)
            page.screenshot(path=str(OUT / "optimizer-empty.png"), full_page=False)

            expect(page.get_by_text("Source-system trend", exact=True)).to_be_visible(timeout=10000)
            page.get_by_text("Source-system trend", exact=True).scroll_into_view_if_needed()
            page.screenshot(path=str(OUT / "optimizer-dashboard-filters.png"), full_page=False)

            expect(page.get_by_text("Governance policy", exact=True)).to_be_visible(timeout=10000)
            page.get_by_text("Governance policy", exact=True).scroll_into_view_if_needed()
            page.locator("[data-policy-field='min_ready_score']").fill("80")
            page.get_by_role("button", name="Save policy controls").click()
            expect(page.locator(".setup-message", has_text="Governance policy controls saved.")).to_be_visible(timeout=10000)
            page.screenshot(path=str(OUT / "optimizer-policy-saved.png"), full_page=False)

            expect(page.get_by_text("Adapter simulator", exact=True)).to_be_visible(timeout=10000)
            page.get_by_text("Adapter simulator", exact=True).scroll_into_view_if_needed()
            page.get_by_role("button", name="Run simulator").click()
            expect(page.locator(".setup-message", has_text="HubSpot simulator returned")).to_be_visible(timeout=10000)
            page.screenshot(path=str(OUT / "optimizer-adapter-simulator.png"), full_page=False)

            expect(page.get_by_text("Integration setup", exact=True)).to_be_visible(timeout=10000)
            page.get_by_text("Integration setup", exact=True).scroll_into_view_if_needed()
            page.get_by_role("button", name="Save recommended mapping").first.click()
            expect(page.get_by_text("mapping is ready for workflow routing")).to_be_visible(timeout=10000)
            page.screenshot(path=str(OUT / "optimizer-setup-saved.png"), full_page=False)

            expect(page.get_by_text("Admin settings", exact=True)).to_be_visible(timeout=10000)
            page.get_by_text("Admin settings", exact=True).scroll_into_view_if_needed()
            page.screenshot(path=str(OUT / "optimizer-admin-settings.png"), full_page=False)

            page.get_by_text("API key management", exact=True).scroll_into_view_if_needed()
            page.locator("[data-api-key-form='name']").fill("Visual regression sandbox key")
            page.locator("[data-api-key-form='scopes']").fill("default:/v1/email/analyze, default:/v1/governance")
            page.get_by_role("button", name="Create local key profile").click()
            expect(page.get_by_text("Local API key profile saved. No credential material was generated or stored.")).to_be_visible(timeout=10000)
            page.screenshot(path=str(OUT / "optimizer-api-key-profile.png"), full_page=False)

            page.get_by_text("Webhook signing setup", exact=True).scroll_into_view_if_needed()
            page.locator("[data-webhook-secret]").fill("visual-regression-test-secret")
            page.get_by_role("button", name="Run local signature test").click()
            expect(page.get_by_text("Local signature test passed", exact=False)).to_be_visible(timeout=10000)
            page.screenshot(path=str(OUT / "optimizer-webhook-signing.png"), full_page=False)

            page.locator("#email-subject").fill(EMAIL_SUBJECT)
            page.locator("#email-body").fill(EMAIL_BODY)
            page.locator("#analyze-email").click()
            expect(page.get_by_text("Send-readiness gate for the existing draft", exact=True)).to_be_visible(timeout=15000)
            page.screenshot(path=str(OUT / "optimizer-result.png"), full_page=False)

            page.get_by_text("Developer-only raw /v1/email/analyze response", exact=True).click()
            expect(page.locator(".optimizer-json pre").first).to_be_visible(timeout=10000)
            page.screenshot(path=str(OUT / "optimizer-raw-json.png"), full_page=False)

            page.locator("#email-subject").fill(RISKY_SUBJECT)
            page.locator("#email-body").fill(RISKY_BODY)
            page.locator("#analyze-email").click()
            expect(page.get_by_text("Send-readiness gate for the existing draft", exact=True)).to_be_visible(timeout=15000)
            page.reload(wait_until="load")
            expect(page.locator(".approval-queue-panel")).to_be_visible(timeout=10000)
            page.wait_for_timeout(500)
            page.locator(".approval-queue-panel").scroll_into_view_if_needed()
            page.screenshot(path=str(OUT / "optimizer-approval-queue.png"), full_page=False)

            page.goto(f"{BASE}/security", wait_until="load")
            expect(page.get_by_text("Data handling", exact=True)).to_be_visible(timeout=10000)
            page.screenshot(path=str(OUT / "optimizer-security.png"), full_page=False)

            page.goto(f"{BASE}/privacy", wait_until="load")
            expect(page.get_by_text("Privacy", exact=True)).to_be_visible(timeout=10000)
            page.screenshot(path=str(OUT / "optimizer-privacy.png"), full_page=False)

            page.goto(f"{BASE}/terms", wait_until="load")
            expect(page.get_by_text("Terms", exact=True)).to_be_visible(timeout=10000)
            page.screenshot(path=str(OUT / "optimizer-terms.png"), full_page=False)

            page.goto(f"{BASE}/deployment", wait_until="load")
            expect(page.get_by_text("Deployment Readiness", exact=True)).to_be_visible(timeout=10000)
            page.screenshot(path=str(OUT / "optimizer-deployment.png"), full_page=False)

            page.set_viewport_size({"width": 390, "height": 844})
            page.goto(f"{BASE}/?visual=mobile", wait_until="load")
            page.locator("#email-subject").fill(EMAIL_SUBJECT)
            page.locator("#email-body").fill(EMAIL_BODY)
            page.locator("#analyze-email").click()
            expect(page.get_by_text("Send-readiness gate for the existing draft", exact=True)).to_be_visible(timeout=15000)
            page.screenshot(path=str(OUT / "optimizer-mobile.png"), full_page=False)
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
