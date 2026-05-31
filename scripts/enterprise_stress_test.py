from __future__ import annotations

import argparse
import contextlib
import http.cookiejar
import json
import os
import secrets
import subprocess  # nosec B404
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "enterprise-stress"
DEFAULT_PORT = 5053


@dataclass(frozen=True)
class StressCase:
    name: str
    subject: str
    body: str
    workspace_id: str
    audience: str
    intent: str
    source_system: str
    analysis_mode: str = "pre_send_gate"
    expected_status: int = 200

    def payload(self, cycle: int) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "tenant_id": f"tenant_{self.workspace_id}",
            "request_id": f"stress-{self.name}-{cycle:05d}",
            "subject": self.subject,
            "body": self.body,
            "audience": self.audience,
            "intent": self.intent,
            "source_system": self.source_system,
            "analysis_mode": self.analysis_mode,
            "campaign_id": f"cmp_{self.name}_{cycle % 7}",
            "journey_id": f"journey_{self.source_system}_{cycle % 5}",
            "template_id": f"tmpl_{self.name}_{cycle % 11}",
            "locale": "en-US",
            "headers": {
                "List-Unsubscribe": "<https://preferences.example.test/unsubscribe>",
                "X-TextTraits-Stress": self.name,
            },
            "consent_context": {
                "region": "US",
                "lawful_basis": "business_contact",
                "has_unsubscribe": "unsubscribe" in self.body.lower() or "preferences" in self.body.lower(),
            },
            "delivery_context": {
                "provider": self.source_system,
                "send_type": "workflow_gate",
                "idempotency_key": f"idem_{self.name}_{cycle:05d}",
            },
            "assets": {
                "links": ["https://example.test/resource", "https://example.test/preferences"],
                "image_count": 1 if self.name != "risky_bulk" else 5,
                "image_bytes": 1800 if self.name != "risky_bulk" else 12000,
                "html_bytes": 900 + len(self.body),
            },
        }


class StressClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookie_jar))
        self.csrf_token = ""  # nosec B105

    def open_session(self) -> None:
        session = self.request("GET", "/api/session")
        self.csrf_token = session["csrf_token"]

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None, expected: int = 200) -> Any:
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.csrf_token:
            headers["X-CSRF-Token"] = self.csrf_token
        request = urllib.request.Request(f"{self.base_url}{path}", data=data, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=15) as response:
                body = response.read().decode("utf-8")
                if response.status != expected:
                    raise AssertionError(f"{method} {path} returned {response.status}, expected {expected}: {body[:600]}")
                if "application/json" in response.headers.get("Content-Type", ""):
                    return json.loads(body)
                return body
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code == 429:
                retry_header = exc.headers.get("Retry-After") or "1"
                with contextlib.suppress(ValueError):
                    retry_after = max(1, int(float(retry_header)))
                    raise RateLimitError(path, retry_after, body) from exc
                raise RateLimitError(path, 1, body) from exc
            if exc.code == expected:
                with contextlib.suppress(json.JSONDecodeError):
                    return json.loads(body)
                return body
            raise AssertionError(f"{method} {path} returned {exc.code}, expected {expected}: {body[:600]}") from exc


class RateLimitError(Exception):
    def __init__(self, path: str, retry_after: int, body: str) -> None:
        super().__init__(f"{path} rate limited; retry after {retry_after}s")
        self.path = path
        self.retry_after = retry_after
        self.body = body


def wait_for_server(base_url: str) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=1) as response:  # nosec B310
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.25)
    raise RuntimeError(f"Timed out waiting for {base_url}")


def cases() -> list[StressCase]:
    return [
        StressCase(
            name="ready_sales",
            workspace_id="stress-sales",
            source_system="hubspot",
            audience="Enterprise prospect",
            intent="Follow-up",
            subject="Next step after the renewal workflow review",
            body=(
                "Hi Maya, thanks for walking through the renewal workflow with us on Tuesday. "
                "The main risk I heard is that managers see coaching gaps after the forecast is already under pressure. "
                "Could we use Thursday's review to compare the three account signals and decide whether the current workflow gate is enough? "
                "Manage preferences: https://example.test/preferences"
            ),
        ),
        StressCase(
            name="risky_bulk",
            workspace_id="stress-marketing",
            source_system="marketo",
            audience="Bulk campaign",
            intent="Marketing campaign",
            subject="FREE guaranteed pipeline result for {{ first_name }}",
            body=(
                "Hi {{ first_name }}, this guaranteed game-changing result has lots of things and stuff. "
                "Visit https://a.example.test https://b.example.test https://c.example.test https://d.example.test. "
                "We should send this to every contact today."
            ),
        ),
        StressCase(
            name="render_tokens",
            workspace_id="stress-lifecycle",
            source_system="braze",
            audience="Customer lifecycle",
            intent="Template review",
            subject="Renewal checklist for {{ first_name }} and {{ account_name }}",
            body=(
                "Hi {{ first_name }}, please review {{ missing_owner }} before Friday. "
                "The renewal checklist for {{ account_name }} is ready, and the List-Unsubscribe header should remain attached. "
                "Manage preferences: https://example.test/preferences"
            ),
        ),
        StressCase(
            name="html_escape",
            workspace_id="stress-security",
            source_system="sendgrid",
            audience="Security review",
            intent="Middleware test",
            subject="Quarterly review <script>alert('subject')</script>",
            body=(
                "Hi team, this body includes literal HTML-like text <script>alert('body')</script> "
                "and a long token req_1234567890abcdef1234567890abcdef1234567890abcdef that should wrap without executing. "
                "Could we confirm the scoring output escapes evidence and stores only hashes?"
            ),
        ),
        StressCase(
            name="long_context",
            workspace_id="stress-ops",
            source_system="iterable",
            audience="Revenue operations",
            intent="Governance stress",
            subject="Operations review for a very long template identifier",
            body=(
                "Hi Jordan, the operations team needs a concise reason to hold or release the current email journey. "
                + "The draft repeats the same operational note to test layout wrapping, dashboard storage, and model metadata. "
                * 24
                + "Please confirm whether the existing journey gate should route this to a reviewer before send."
            ),
        ),
        StressCase(
            name="empty_body",
            workspace_id="stress-validation",
            source_system="salesforce",
            audience="Validation",
            intent="Invalid input",
            subject="",
            body="",
            expected_status=400,
        ),
    ]


def assert_analysis(case: StressCase, payload: dict[str, Any], response: Any) -> list[str]:
    warnings: list[str] = []
    if case.expected_status != 200:
        if not isinstance(response, dict):
            warnings.append(f"{case.name}: invalid response body is not JSON")
        return warnings
    if not isinstance(response, dict):
        raise AssertionError(f"{case.name}: analysis response is not JSON")
    gate_status = response.get("policy", {}).get("gate", {}).get("status")
    if gate_status not in {"ready", "needs_review", "blocked"}:
        raise AssertionError(f"{case.name}: unexpected gate status {gate_status!r}")
    if not str(response.get("content_hash", "")).startswith("sha256:"):
        raise AssertionError(f"{case.name}: missing content hash")
    response_text = json.dumps(response, sort_keys=True)
    if payload["body"] and payload["body"] in response_text:
        raise AssertionError(f"{case.name}: raw body leaked into analysis response")
    if payload["subject"] and "<script>" in payload["subject"].lower() and "<script>" in response_text.lower():
        warnings.append(f"{case.name}: escaped script marker appears in structured output; verify UI escaping")
    if case.name == "risky_bulk" and gate_status == "ready":
        raise AssertionError("risky bulk campaign unexpectedly passed the send gate")
    if case.name == "ready_sales" and gate_status == "blocked":
        warnings.append("ready sales sample was blocked; inspect policy thresholds")
    return warnings


def exercise_related_endpoints(client: StressClient, case: StressCase, payload: dict[str, Any], cycle: int) -> list[str]:
    warnings: list[str] = []
    if case.expected_status != 200:
        return warnings
    render = client.request(
        "POST",
        "/v1/templates/render-test",
        {
            "subject": payload["subject"],
            "body": payload["body"],
            "personalization_context": {"first_name": "Maya", "account_name": "Northstar Systems"},
            "headers": payload["headers"],
        },
    )
    unresolved = render.get("render_test", {}).get("unresolved_tokens", [])
    if case.name == "render_tokens" and not unresolved:
        raise AssertionError("render token stress case should report unresolved tokens")
    simulator = client.request(
        "POST",
        "/v1/integrations/simulate",
        {"provider": case.source_system if case.source_system in {"hubspot", "braze", "marketo", "iterable", "warehouse"} else "hubspot", "payload": {"inputFields": {"email_subject": payload["subject"], "email_body": payload["body"]}}},
    )
    if "manifest" not in simulator:
        raise AssertionError(f"{case.name}: simulator response missing manifest")
    if cycle % 4 == 0:
        event = {
            "workspace_id": case.workspace_id,
            "event_id": f"stress-event-{case.name}-{cycle}",
            "provider": case.source_system,
            "event_type": "clicked" if case.name != "risky_bulk" else "complained",
            "request_id": payload["request_id"],
        }
        webhook = client.request("POST", "/v1/webhooks/post-send", event)
        if "duplicate" not in webhook:
            raise AssertionError(f"{case.name}: webhook response missing duplicate flag")
    return warnings


def capture_ui_snapshots(base_url: str, selected_cases: list[StressCase]) -> list[str]:
    try:
        from playwright.sync_api import expect, sync_playwright
    except Exception as exc:
        return [f"Playwright unavailable for UI snapshots: {exc}"]

    warnings: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        page = context.new_page()
        page.goto(f"{base_url}/?stress=enterprise", wait_until="load")
        expect(page.get_by_text("Enterprise email optimization, without generated copy.", exact=True)).to_be_visible(timeout=10000)
        page.screenshot(path=str(OUT / "stress-empty-desktop.png"), full_page=False)

        for case in selected_cases:
            if case.expected_status != 200:
                continue
            page.locator("#email-subject").fill(case.subject)
            page.locator("#email-body").fill(case.body)
            page.locator("#analyze-email").click()
            expect(page.get_by_text("Send-readiness gate for the existing draft", exact=True)).to_be_visible(timeout=15000)
            page.wait_for_timeout(250)
            page.screenshot(path=str(OUT / f"stress-result-{case.name}.png"), full_page=False)
            visible_text = page.locator("body").inner_text(timeout=10000)
            if "<script>" in visible_text.lower():
                warnings.append(f"{case.name}: literal script marker is visible in UI output; confirm it is inert text")

        page.get_by_text("Developer-only raw /v1/email/analyze response", exact=True).click()
        expect(page.locator(".optimizer-json pre").first).to_be_visible(timeout=10000)
        page.screenshot(path=str(OUT / "stress-raw-json-expanded.png"), full_page=False)

        page.get_by_text("Source-system trend", exact=True).scroll_into_view_if_needed()
        page.screenshot(path=str(OUT / "stress-dashboard-after-api-runs.png"), full_page=False)

        api_key_section = page.locator("[aria-label='API key management']")
        api_key_section.scroll_into_view_if_needed()
        page.locator("[data-api-key-form='name']").fill("Stress test local profile")
        page.locator("[data-api-key-form='scopes']").fill(
            "stress-sales:/v1/email/analyze, stress-marketing:/v1/governance, stress-ops:/v1/integrations/simulate"
        )
        page.get_by_role("button", name="Create local key profile").click()
        expect(page.get_by_text("No credential material was generated or stored.", exact=False)).to_be_visible(timeout=10000)
        api_key_section.scroll_into_view_if_needed()
        page.screenshot(path=str(OUT / "stress-admin-long-scopes.png"), full_page=False)

        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(f"{base_url}/?stress=mobile", wait_until="load")
        mobile_case = selected_cases[0]
        page.locator("#email-subject").fill(mobile_case.subject)
        page.locator("#email-body").fill(mobile_case.body)
        page.locator("#analyze-email").click()
        expect(page.get_by_text("Send-readiness gate for the existing draft", exact=True)).to_be_visible(timeout=15000)
        page.screenshot(path=str(OUT / "stress-mobile-result.png"), full_page=False)
        browser.close()
    return warnings


def run(minutes: float, port: int, pace_seconds: float) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for artifact in OUT.glob("*"):
        if artifact.is_file():
            artifact.unlink()
    base_url = f"http://127.0.0.1:{port}"
    db_path = str(Path(tempfile.gettempdir()) / f"texttraits-enterprise-stress-{port}.sqlite3")
    Path(db_path).unlink(missing_ok=True)
    env = {
        **os.environ,
        "PORT": str(port),
        "TEXTTRAITS_SECRET_KEY": secrets.token_urlsafe(32),
        "TEXTTRAITS_DATABASE_URL": "",
        "DATABASE_URL": "",
        "TEXTTRAITS_DB_PATH": db_path,
    }
    server = subprocess.Popen(  # nosec B603
        [sys.executable, "texttraits_app/app.py"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    started = time.time()
    stress_cases = cases()
    failures: list[str] = []
    warnings: list[str] = []
    throttles: dict[str, int] = {}
    cycle = 0
    endpoint_calls = 0
    try:
        wait_for_server(base_url)
        client = StressClient(base_url)
        client.open_session()
        deadline = time.monotonic() + minutes * 60
        while time.monotonic() < deadline:
            case = stress_cases[cycle % len(stress_cases)]
            payload = case.payload(cycle)
            try:
                response = client.request("POST", "/v1/email/analyze", payload, expected=case.expected_status)
                endpoint_calls += 1
                warnings.extend(assert_analysis(case, payload, response))
                if case.expected_status == 200:
                    warnings.extend(exercise_related_endpoints(client, case, payload, cycle))
                    endpoint_calls += 3 if cycle % 4 == 0 else 2
                if cycle % 6 == 0:
                    dashboard = client.request("GET", f"/v1/governance/dashboard?workspace_id={urllib.parse.quote(case.workspace_id)}")
                    endpoint_calls += 1
                    if "analysis_volume" not in dashboard:
                        raise AssertionError(f"{case.name}: dashboard missing analysis volume")
                    export = client.request("GET", f"/v1/governance/export?workspace_id={urllib.parse.quote(case.workspace_id)}&type=analyses&format=json")
                    endpoint_calls += 1
                    if "rows" not in export:
                        raise AssertionError(f"{case.name}: export missing rows")
            except Exception as exc:
                if isinstance(exc, RateLimitError):
                    throttles[exc.path] = throttles.get(exc.path, 0) + 1
                    time.sleep(min(exc.retry_after, 5))
                else:
                    failures.append(f"cycle {cycle} {case.name}: {exc}")
            cycle += 1
            time.sleep(pace_seconds)
        warnings.extend(capture_ui_snapshots(base_url, stress_cases[:5]))
    finally:
        server.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            server.wait(timeout=5)
        if server.poll() is None:
            server.kill()
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started))
    summary = {
        "started_at": started_at,
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "requested_minutes": minutes,
        "elapsed_seconds": round(time.time() - started, 2),
        "cycles": cycle,
        "endpoint_calls": endpoint_calls,
        "pace_seconds": pace_seconds,
        "cases": [case.name for case in stress_cases],
        "failures": failures,
        "throttles": throttles,
        "warnings": sorted(set(warnings)),
        "screenshots": sorted(path.name for path in OUT.glob("*.png")),
    }
    summary_json = json.dumps(summary, indent=2)
    (OUT / "stress-summary.json").write_text(summary_json, encoding="utf-8")
    stamped_name = f"stress-summary-{started_at.replace(':', '').replace('-', '')}.json"
    (OUT / stamped_name).write_text(summary_json, encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a timed enterprise stress test against TextTraits.")
    parser.add_argument("--minutes", type=float, default=20.0)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--pace-seconds", type=float, default=0.75, help="Delay between stress cycles; keep near real workflow pressure unless testing throttling.")
    args = parser.parse_args()
    if args.minutes <= 0:
        raise SystemExit("--minutes must be positive")
    if args.pace_seconds < 0:
        raise SystemExit("--pace-seconds cannot be negative")
    return run(args.minutes, args.port, args.pace_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
