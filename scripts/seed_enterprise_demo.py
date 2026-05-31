from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "texttraits_app"
sys.path.insert(0, str(APP_DIR))

import app as app_module  # noqa: E402


DEMO_MESSAGES = [
    {
        "request_id": "demo_seed_braze_renewal_01",
        "source_system": "braze",
        "analysis_mode": "pre_send_gate",
        "campaign_id": "cmp_renewal_risk",
        "journey_id": "canvas_q2_expansion",
        "template_id": "tmpl_renewal_manager_handoff",
        "subject": "Renewal risk check for {{ first_name }}",
        "body": (
            "Hi {{ first_name }}, your team mentioned renewal risk reviews are happening later than planned. "
            "Could we review the current manager handoff on Thursday and decide whether the dashboard should flag "
            "at-risk accounts one week earlier?"
        ),
        "personalization_context": {"first_name": "Maya"},
        "headers": {"List-Unsubscribe": "<https://example.test/unsubscribe>"},
    },
    {
        "request_id": "demo_seed_marketo_claims_02",
        "source_system": "marketo",
        "analysis_mode": "authoring_lint",
        "campaign_id": "cmp_q2_webinar",
        "journey_id": "program_revops_webinar",
        "template_id": "tmpl_webinar_invite_v3",
        "subject": "Guaranteed revenue lift",
        "body": (
            "Hi Jordan, this webinar will guarantee a game-changing forecast process for every team. "
            "It covers a lot of things and should help somehow. Click here, book a meeting, and forward it to your manager."
        ),
        "headers": {"List-Unsubscribe": "<https://example.test/unsubscribe>"},
    },
    {
        "request_id": "demo_seed_iterable_unsub_03",
        "source_system": "iterable",
        "analysis_mode": "pre_send_gate",
        "campaign_id": "cmp_product_update",
        "journey_id": "journey_onboarding_nurture",
        "template_id": "tmpl_product_update_v7",
        "subject": "Product update",
        "body": (
            "Hi Sam, this product update is probably useful. It has some things that are very important "
            "and will help your team in a revolutionary way. Reply when you can."
        ),
    },
    {
        "request_id": "demo_seed_hubspot_followup_04",
        "source_system": "hubspot",
        "analysis_mode": "pre_send_gate",
        "campaign_id": "cmp_midmarket_followup",
        "journey_id": "workflow_demo_followup",
        "template_id": "tmpl_followup_fit_check",
        "subject": "Next step after Tuesday",
        "body": (
            "Hi Maya, thanks for walking through the renewal workflow on Tuesday. "
            "The strongest gap I heard was that managers see risk after the forecast is already under pressure. "
            "Could we do a 15-minute fit check Thursday afternoon?"
        ),
        "headers": {"List-Unsubscribe": "<https://example.test/unsubscribe>"},
    },
]

DEMO_OUTCOMES = [
    {"event_id": "demo_evt_delivered_01", "provider": "braze", "event_type": "delivered", "request_id": "demo_seed_braze_renewal_01", "delivery_status": "delivered", "campaign_id": "cmp_renewal_risk", "template_id": "tmpl_renewal_manager_handoff"},
    {"event_id": "demo_evt_opened_02", "provider": "hubspot", "event_type": "opened", "request_id": "demo_seed_hubspot_followup_04", "delivery_status": "opened", "campaign_id": "cmp_midmarket_followup", "template_id": "tmpl_followup_fit_check"},
    {"event_id": "demo_evt_complained_03", "provider": "iterable", "event_type": "complained", "request_id": "demo_seed_iterable_unsub_03", "delivery_status": "complained", "campaign_id": "cmp_product_update", "template_id": "tmpl_product_update_v7"},
]


def csrf_headers(client) -> dict[str, str]:
    client.get("/")
    with client.session_transaction() as session:
        token = session.get("csrf_token", "")
    return {"X-CSRF-Token": token}


def seed_demo_workspace(workspace_id: str) -> tuple[int, int]:
    client = app_module.app.test_client()
    headers = csrf_headers(client)
    accepted = 0
    for message in DEMO_MESSAGES:
        response = client.post(
            "/v1/email/analyze",
            json={**message, "workspace_id": workspace_id, "tenant_id": workspace_id, "locale": "en-US"},
            headers=headers,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Analysis seed failed for {message['request_id']}: {response.get_data(as_text=True)}")
        accepted += 1
    outcomes = 0
    for event in DEMO_OUTCOMES:
        response = client.post(
            "/v1/webhooks/post-send",
            json={**event, "workspace_id": workspace_id},
            headers=headers,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Outcome seed failed for {event['event_id']}: {response.get_data(as_text=True)}")
        outcomes += 1
    return accepted, outcomes


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed clearly labeled synthetic enterprise demo rows into the local TextTraits database.")
    parser.add_argument("--workspace-id", default="demo_enterprise", help="Workspace ID to seed. Defaults to demo_enterprise.")
    args = parser.parse_args()
    analyses, outcomes = seed_demo_workspace(args.workspace_id)
    print(f"Seeded {analyses} demo analyses and {outcomes} demo outcomes into workspace {args.workspace_id}.")
    print("These rows are synthetic examples for local demos; do not present them as customer data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
