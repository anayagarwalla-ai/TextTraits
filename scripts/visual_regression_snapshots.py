from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib import request as urllib_request


ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "outputs" / "visual_sweeps"
GENERAL_OUT = OUT_ROOT / "general_ui_usage"
HUBSPOT_OUT = OUT_ROOT / "hubspot_integration"
CHROMIUM_UNSAFE_PORTS = {
    1,
    7,
    9,
    11,
    13,
    15,
    17,
    19,
    20,
    21,
    22,
    23,
    25,
    37,
    42,
    43,
    53,
    69,
    77,
    79,
    87,
    95,
    101,
    102,
    103,
    104,
    109,
    110,
    111,
    113,
    115,
    117,
    119,
    123,
    135,
    137,
    139,
    143,
    161,
    179,
    389,
    427,
    465,
    512,
    513,
    514,
    515,
    526,
    530,
    531,
    532,
    540,
    548,
    554,
    556,
    563,
    587,
    601,
    636,
    989,
    990,
    993,
    995,
    1719,
    1720,
    1723,
    2049,
    3659,
    4045,
    5060,
    5061,
    6000,
    6566,
    6665,
    6666,
    6667,
    6668,
    6669,
    6697,
    10080,
}


def visual_port() -> int:
    requested = int(os.environ.get("TEXTTRAITS_VISUAL_PORT", "5042"))
    if requested not in CHROMIUM_UNSAFE_PORTS:
        return requested
    candidate = 5042
    while candidate in CHROMIUM_UNSAFE_PORTS:
        candidate += 1
    print(f"Requested visual port {requested} is blocked by Chromium; using {candidate} instead.", file=sys.stderr)
    return candidate


PORT = visual_port()
BASE = f"http://127.0.0.1:{PORT}"
RUN_ID = os.environ.get("TEXTTRAITS_VISUAL_RUN_ID") or str(int(time.time()))
VISUAL_EMAIL = os.environ.get("TEXTTRAITS_VISUAL_EMAIL") or f"visual-admin+{RUN_ID}@example.com"
VISUAL_PASSWORD = "texttraits-visual-admin"
VISUAL_DB_PATH = os.environ.get("TEXTTRAITS_VISUAL_DB_PATH") or f"/tmp/texttraits-visual-regression-{RUN_ID}.sqlite3"


EXPLORER_SAMPLE = (
    "I wanted to send a quick update because the project is moving, but the next steps still feel scattered. "
    "We finished the research, found two confusing handoff points, and should decide by Friday who owns the customer notes, "
    "the design review, and the final message to the group."
)

ENTERPRISE_SAMPLE = (
    "Hi Maya, your team has three renewal workflows with unclear approval routing. TextTraits can review the existing HubSpot "
    "drafts, flag risky claims, and route only the blocked drafts to the right reviewer before the campaign is scheduled."
)


def wait_for_server() -> None:
    deadline = time.time() + 25
    while time.time() < deadline:
        try:
            with urllib_request.urlopen(f"{BASE}/health", timeout=1) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.25)
    raise RuntimeError("Timed out waiting for local TextTraits server")


def screenshot(page, path: Path, *, full_page: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(path), full_page=full_page)


def page_metrics(page) -> dict:
    return page.evaluate(
        """() => {
          const body = document.body;
          const doc = document.documentElement;
          const headings = Array.from(document.querySelectorAll('h1,h2,h3,summary,strong')).slice(0, 80).map((item) => item.textContent.trim()).filter(Boolean);
          const buttons = Array.from(document.querySelectorAll('button,a.button-secondary')).slice(0, 80).map((item) => item.textContent.trim()).filter(Boolean);
          return {
            title: document.title,
            url: location.href,
            bodyWidth: body.scrollWidth,
            viewportWidth: window.innerWidth,
            bodyHeight: body.scrollHeight,
            viewportHeight: window.innerHeight,
            overflowX: body.scrollWidth > window.innerWidth + 2 || doc.scrollWidth > window.innerWidth + 2,
            headings,
            buttons,
          };
        }"""
    )


def write_metrics(path: Path, metrics: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")


def assert_no_horizontal_overflow(metrics: list[dict]) -> list[str]:
    issues = []
    for item in metrics:
        if item.get("overflowX"):
            issues.append(f"{item['name']} has horizontal overflow: body {item['bodyWidth']}px vs viewport {item['viewportWidth']}px.")
    return issues


def chrome_executable_path() -> str | None:
    candidates = [
        os.environ.get("TEXTTRAITS_PLAYWRIGHT_CHROME_PATH", ""),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ]
    for candidate in candidates:
        clean = str(candidate or "").strip()
        if clean and Path(clean).exists():
            return clean
    return None


def sign_in_visual_admin(page) -> None:
    session = page.request.get(f"{BASE}/api/session").json()
    headers = {"X-CSRF-Token": session["csrf_token"], "Content-Type": "application/json"}
    signup = page.request.post(
        f"{BASE}/api/signup",
        data=json.dumps({"email": VISUAL_EMAIL, "password": VISUAL_PASSWORD, "name": "Visual Admin"}),
        headers=headers,
    )
    if signup.status not in (200, 201):
        raise RuntimeError(f"Visual admin signup failed with {signup.status}: {signup.text()[:500]}")
    signup_payload = signup.json()
    token = signup_payload.get("dev_verify_code")
    if token:
        session = page.request.get(f"{BASE}/api/session").json()
        headers = {"X-CSRF-Token": session["csrf_token"], "Content-Type": "application/json"}
        verify = page.request.post(f"{BASE}/api/verify-email", data=json.dumps({"email": VISUAL_EMAIL, "token": token}), headers=headers)
        if verify.status != 200:
            raise RuntimeError(f"Visual admin verification failed with {verify.status}: {verify.text()[:500]}")
    session = page.request.get(f"{BASE}/api/session").json()
    headers = {"X-CSRF-Token": session["csrf_token"], "Content-Type": "application/json"}
    login = page.request.post(f"{BASE}/api/login", data=json.dumps({"email": VISUAL_EMAIL, "password": VISUAL_PASSWORD}), headers=headers)
    if login.status != 200:
        raise RuntimeError(f"Visual admin login failed with {login.status}: {login.text()[:500]}")


def run_enterprise_analysis(page, expect) -> None:
    page.locator("#enterprise-text").wait_for(state="attached", timeout=10000)
    page.evaluate(
        """(sample) => {
          const input = document.querySelector("#enterprise-text");
          const button = document.querySelector("#generate-enterprise");
          if (!input || !button) throw new Error("Enterprise input or action button is missing.");
          input.value = sample;
          input.dispatchEvent(new Event("input", {bubbles: true}));
          button.click();
        }""",
        ENTERPRISE_SAMPLE,
    )
    expect(page.get_by_text("Enterprise workspace", exact=True)).to_be_visible(timeout=15000)


def click_attached(page, selector: str) -> None:
    page.locator(selector).wait_for(state="attached", timeout=10000)
    page.evaluate(
        """(selector) => {
          const element = document.querySelector(selector);
          if (!element) throw new Error(`Missing element: ${selector}`);
          element.click();
        }""",
        selector,
    )


def open_hubspot_admin_console(page, expect) -> None:
    summary = page.get_by_text("Integrations and admin", exact=True)
    summary.click()
    expect(page.get_by_text("Live HubSpot governance", exact=True)).to_be_visible(timeout=10000)


def run_general_sweep(page, expect) -> list[dict]:
    metrics: list[dict] = []
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.goto(f"{BASE}/explorer?visual=general", wait_until="load")
    screenshot(page, GENERAL_OUT / "01-explorer-empty.png")
    metrics.append({"name": "explorer-empty", **page_metrics(page)})

    page.locator("#explorer-text").fill(EXPLORER_SAMPLE)
    page.locator("#analyze-explorer").click()
    expect(page.get_by_text("How this comes across", exact=True)).to_be_visible(timeout=15000)
    screenshot(page, GENERAL_OUT / "02-explorer-result.png")
    metrics.append({"name": "explorer-result", **page_metrics(page)})

    page.get_by_role("button", name="Open journal").click()
    expect(page.get_by_text("Search journal", exact=True)).to_be_visible(timeout=10000)
    screenshot(page, GENERAL_OUT / "03-explorer-journal.png")
    metrics.append({"name": "explorer-journal", **page_metrics(page)})

    page.goto(f"{BASE}/enterprise?visual=general", wait_until="load")
    screenshot(page, GENERAL_OUT / "04-enterprise-empty.png")
    metrics.append({"name": "enterprise-empty", **page_metrics(page)})

    run_enterprise_analysis(page, expect)
    screenshot(page, GENERAL_OUT / "05-enterprise-result-dashboard.png")
    metrics.append({"name": "enterprise-result-dashboard", **page_metrics(page)})

    click_attached(page, 'button[data-tab="tools"]')
    expect(page.get_by_text("Batch CSV upload", exact=True)).to_be_visible(timeout=10000)
    screenshot(page, GENERAL_OUT / "06-enterprise-tools.png")
    metrics.append({"name": "enterprise-tools", **page_metrics(page)})

    click_attached(page, 'button[data-tool="inbox"]')
    expect(page.get_by_text("Gmail / Outlook reply queue", exact=True)).to_be_visible(timeout=10000)
    screenshot(page, GENERAL_OUT / "07-enterprise-inbox.png")
    metrics.append({"name": "enterprise-inbox", **page_metrics(page)})

    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{BASE}/enterprise?visual=general-mobile", wait_until="load")
    run_enterprise_analysis(page, expect)
    screenshot(page, GENERAL_OUT / "08-enterprise-mobile-result.png", full_page=True)
    metrics.append({"name": "enterprise-mobile-result", **page_metrics(page)})
    return metrics


def run_hubspot_sweep(page, expect) -> list[dict]:
    metrics: list[dict] = []
    sign_in_visual_admin(page)

    page.set_viewport_size({"width": 1440, "height": 1000})
    page.goto(f"{BASE}/enterprise?visual=hubspot", wait_until="load")
    run_enterprise_analysis(page, expect)
    click_attached(page, 'button[data-tab="tools"]')
    click_attached(page, 'button[data-tool="insights"]')
    open_hubspot_admin_console(page, expect)
    screenshot(page, HUBSPOT_OUT / "01-admin-console-empty.png")
    metrics.append({"name": "hubspot-admin-empty", **page_metrics(page)})

    page.get_by_role("button", name="Load governance").click()
    expect(page.locator(".demo-badge").filter(has_text="Loaded")).to_be_visible(timeout=15000)
    screenshot(page, HUBSPOT_OUT / "02-admin-console-loaded.png", full_page=True)
    metrics.append({"name": "hubspot-admin-loaded", **page_metrics(page)})

    page.goto(f"{BASE}/api/enterprise/hubspot/surfaces", wait_until="load")
    screenshot(page, HUBSPOT_OUT / "03-surfaces-json.png", full_page=True)
    metrics.append({"name": "hubspot-surfaces-json", **page_metrics(page)})

    page.goto(f"{BASE}/api/enterprise/readiness", wait_until="load")
    screenshot(page, HUBSPOT_OUT / "04-readiness-json.png", full_page=True)
    metrics.append({"name": "hubspot-readiness-json", **page_metrics(page)})

    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{BASE}/enterprise?visual=hubspot-mobile", wait_until="load")
    run_enterprise_analysis(page, expect)
    click_attached(page, 'button[data-tab="tools"]')
    click_attached(page, 'button[data-tool="insights"]')
    open_hubspot_admin_console(page, expect)
    screenshot(page, HUBSPOT_OUT / "05-admin-console-mobile.png", full_page=True)
    metrics.append({"name": "hubspot-admin-mobile", **page_metrics(page)})
    return metrics


def main() -> int:
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        print(f"Playwright is not installed in this Python environment: {exc}. Install it with `python -m pip install playwright`.", file=sys.stderr)
        return 2

    for path in (GENERAL_OUT, HUBSPOT_OUT):
        path.mkdir(parents=True, exist_ok=True)

    env = {
        **os.environ,
        "PORT": str(PORT),
        "TEXTTRAITS_SECRET_KEY": "visual-regression-local-secret",
        "TEXTTRAITS_DB_PATH": VISUAL_DB_PATH,
        "DATABASE_URL": "",
        "TEXTTRAITS_DATABASE_URL": "",
        "TEXTTRAITS_DEV_ACCOUNT_LINKS": "true",
        "TEXTTRAITS_ENTERPRISE_ADMIN_EMAILS": VISUAL_EMAIL,
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
            launch_options = {"headless": True}
            chrome_path = chrome_executable_path()
            if chrome_path:
                launch_options["executable_path"] = chrome_path
            browser = p.chromium.launch(**launch_options)
            context = browser.new_context(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
            page = context.new_page()
            all_metrics = run_general_sweep(page, expect)
            all_metrics.extend(run_hubspot_sweep(page, expect))
            issues = assert_no_horizontal_overflow(all_metrics)
            checklist = {
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "general_sweep": str(GENERAL_OUT),
                "hubspot_sweep": str(HUBSPOT_OUT),
                "issues": issues,
                "status": "needs_fixes" if issues else "pass",
            }
            write_metrics(OUT_ROOT / "snapshot-metrics.json", all_metrics)
            (OUT_ROOT / "improvement-checklist.json").write_text(json.dumps(checklist, indent=2), encoding="utf-8")
            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()

    print(f"General UI/usage screenshots written to {GENERAL_OUT}")
    print(f"HubSpot integration screenshots written to {HUBSPOT_OUT}")
    print(f"Snapshot checklist written to {OUT_ROOT / 'improvement-checklist.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
