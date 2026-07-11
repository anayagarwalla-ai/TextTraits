from __future__ import annotations

import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "texttraits_app"
sys.path.insert(0, str(APP_DIR))

tmpdir = tempfile.TemporaryDirectory()
os.environ["TEXTTRAITS_DB_PATH"] = str(Path(tmpdir.name) / "hubspot-performance.sqlite3")
os.environ["DATABASE_URL"] = ""
os.environ["TEXTTRAITS_DATABASE_URL"] = ""
os.environ.setdefault("TEXTTRAITS_SECRET_KEY", "hubspot-performance-secret")

import app as app_module  # noqa: E402
import storage  # noqa: E402
from hubspot_performance import hubspot_latency_budget_ms  # noqa: E402


def measured_post(client, path: str, payload: dict) -> tuple[float, object]:
    started = time.perf_counter()
    response = client.post(path, json=payload)
    return (time.perf_counter() - started) * 1000, response


def percentile(values: list[float], fraction: float = 0.95) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(len(ordered) * fraction) - 1))
    return ordered[index]


def assert_budget(path: str, durations: list[float]) -> None:
    p95 = percentile(durations)
    budget = hubspot_latency_budget_ms(path)
    if p95 > budget:
        raise AssertionError(f"{path} local p95 {p95:.2f}ms exceeded {budget}ms budget")


def install_portal(portal_id: str) -> None:
    with storage.connect() as conn:
        storage.execute(
            conn,
            """
            INSERT INTO hubspot_portal_tokens (
              portal_id, hub_domain, account_name, access_token_encrypted, refresh_token_encrypted,
              scopes, token_type, expires_at, status, installed_by, connected_at, updated_at, disconnected_at
            ) VALUES (?, 'performance.example', 'Performance Portal', '', '', ?, 'bearer', '', 'connected', 'performance-test', ?, ?, '')
            """,
            (portal_id, json.dumps([]), storage.utc_now(), storage.utc_now()),
        )


def main() -> int:
    client = app_module.app.test_client()
    card_path = "/v1/integrations/hubspot/crm-card/analyze-email"
    workflow_path = "/v1/integrations/hubspot/workflow-actions/analyze-email"
    batch_path = "/v1/integrations/hubspot/campaigns/analyze"
    bootstrap_path = "/v1/integrations/hubspot/app-home/bootstrap"
    draft = {
        "portal_id": "performance-portal",
        "inputFields": {
            "email_subject": "Renewal review by Friday",
            "email_body": "Hi Maya, please review the attached renewal terms and reply with approval by Friday.",
        },
    }

    card_durations = []
    for _ in range(15):
        duration, response = measured_post(client, card_path, draft)
        if response.status_code != 200:
            raise AssertionError(response.get_data(as_text=True))
        if "Server-Timing" not in response.headers:
            raise AssertionError("HubSpot responses should expose Server-Timing")
        card_durations.append(duration)

    workflow_durations = []
    for _ in range(10):
        duration, response = measured_post(client, workflow_path, draft)
        if response.status_code != 200:
            raise AssertionError(response.get_data(as_text=True))
        workflow_durations.append(duration)

    batch_payload = {
        "portal_id": "performance-portal",
        "emails": [
            {
                "id": f"email-{index}",
                "subject": f"Candidate update {index}",
                "body": "Hi Jordan, your interview is Tuesday at 10 AM. Reply to confirm attendance.",
            }
            for index in range(25)
        ],
    }
    batch_duration, batch_response = measured_post(client, batch_path, batch_payload)
    if batch_response.status_code != 200:
        raise AssertionError(batch_response.get_data(as_text=True))

    install_portal("performance-portal")
    bootstrap_duration, bootstrap_response = measured_post(client, bootstrap_path, {"portal_id": "performance-portal"})
    if bootstrap_response.status_code != 200:
        raise AssertionError(bootstrap_response.get_data(as_text=True))

    assert_budget(card_path, card_durations)
    assert_budget(workflow_path, workflow_durations)
    assert_budget(batch_path, [batch_duration])
    assert_budget(bootstrap_path, [bootstrap_duration])
    print(
        "HubSpot performance budgets passed: "
        f"card_p95={percentile(card_durations):.2f}ms "
        f"workflow_p95={percentile(workflow_durations):.2f}ms "
        f"batch_25={batch_duration:.2f}ms "
        f"bootstrap={bootstrap_duration:.2f}ms "
        f"card_mean={statistics.mean(card_durations):.2f}ms"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
