#!/usr/bin/env python3
"""Seed a synthetic CRM-style HubSpot demo dataset for TextTraits."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "texttraits_app"
DEFAULT_DATASET_PATH = APP_DIR / "demo_data" / "hubspot_crm_demo.json"


def load_dataset(path: Path = DEFAULT_DATASET_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def entity_index(dataset: dict[str, Any], key: str, id_key: str) -> dict[str, dict[str, Any]]:
    return {str(item.get(id_key)): item for item in dataset.get(key, []) if item.get(id_key)}


def prepare_imports():
    sys.path.insert(0, str(APP_DIR))
    from env_loader import load_env_file  # noqa: WPS433

    load_env_file(ROOT / ".env")
    if os.getenv("TEXTTRAITS_ENV", "").strip().lower() != "production":
        os.environ.setdefault("TEXTTRAITS_ALLOW_DEMO", "true")
    os.environ.setdefault("ENABLE_DEV_TOOLS", "false")

    import app as app_module  # noqa: WPS433
    import storage as storage_module  # noqa: WPS433

    return app_module, storage_module


def reset_demo_workspace(storage_module, dataset: dict[str, Any]) -> None:
    workspace_id = str(dataset["workspace_id"])
    environment = str(dataset.get("environment") or "production")
    policy_version = str((dataset.get("policy") or {}).get("version") or "")

    with storage_module.connect() as conn:
        rows = storage_module.execute(
            conn,
            "SELECT request_id FROM hubspot_email_analyses WHERE workspace_id = ?",
            (workspace_id,),
        ).fetchall()
        request_ids = [str(row["request_id"]) for row in rows if row["request_id"]]
        for request_id in request_ids:
            for table in (
                "hubspot_email_review_events",
                "hubspot_email_review_states",
                "hubspot_email_checks",
                "hubspot_email_findings",
                "hubspot_email_analyses",
            ):
                storage_module.execute(conn, f"DELETE FROM {table} WHERE request_id = ?", (request_id,))
        storage_module.execute(conn, "DELETE FROM hubspot_email_outcome_events WHERE workspace_id = ?", (workspace_id,))
        if policy_version:
            storage_module.execute(
                conn,
                "DELETE FROM hubspot_policy_versions WHERE workspace_id = ? AND environment = ? AND version = ?",
                (workspace_id, environment, policy_version),
            )


def install_demo_policy(storage_module, dataset: dict[str, Any]) -> None:
    workspace_id = str(dataset["workspace_id"])
    environment = str(dataset.get("environment") or "production")
    policy = dataset.get("policy") or {}
    if policy:
        storage_module.save_hubspot_policy_config(workspace_id, environment, policy, updated_by="demo_crm_seed")

    portal_id = str(dataset.get("portal_id") or "").strip()
    owners = entity_index(dataset, "owners", "owner_id")
    if portal_id and owners:
        storage_module.save_hubspot_route_owner_map(
            portal_id,
            workspace_id,
            {
                "Marketing review": next(
                    (owner["owner_id"] for owner in owners.values() if owner.get("queue") == "Marketing review"),
                    "",
                ),
                "Compliance review": next(
                    (owner["owner_id"] for owner in owners.values() if owner.get("queue") == "Compliance review"),
                    "",
                ),
            },
            default_owner_id=next(iter(owners.keys()), ""),
            updated_by="demo_crm_seed",
        )


def base_analysis_payload(dataset: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    accounts = entity_index(dataset, "accounts", "company_id")
    contacts = entity_index(dataset, "contacts", "contact_id")
    deals = entity_index(dataset, "deals", "deal_id")
    owners = entity_index(dataset, "owners", "owner_id")
    campaigns = entity_index(dataset, "campaigns", "campaign_id")

    contact = contacts.get(str(analysis.get("contact_id"))) or {}
    account = accounts.get(str(analysis.get("company_id"))) or {}
    deal = deals.get(str(analysis.get("deal_id"))) or {}
    owner = owners.get(str(analysis.get("owner_id"))) or {}
    campaign = campaigns.get(str(analysis.get("campaign_id"))) or {}
    contact_name = " ".join(part for part in (contact.get("first_name"), contact.get("last_name")) if part)

    delivery_context = {
        "demo_dataset": dataset.get("name"),
        "demo_analysis_id": analysis.get("id"),
        "campaign_name": campaign.get("name"),
        "contact_role": contact.get("role"),
        "company": account.get("name"),
        "industry": account.get("industry"),
        "deal_name": deal.get("name"),
        "deal_stage": deal.get("stage"),
        "deal_amount": deal.get("amount"),
        "deal_close_date": deal.get("close_date"),
        "owner_name": owner.get("name"),
        "owner_queue": owner.get("queue"),
        **(analysis.get("delivery_context") or {}),
    }

    payload = {
        "workspace_id": dataset["workspace_id"],
        "source_system": analysis.get("source_system") or "hubspot_demo_crm",
        "analysis_mode": analysis.get("analysis_mode") or "send_path_gate",
        "campaign_id": analysis.get("campaign_id") or "",
        "template_id": analysis.get("template_id") or "",
        "contact_id": analysis.get("contact_id") or "",
        "company_id": analysis.get("company_id") or "",
        "deal_id": analysis.get("deal_id") or "",
        "owner_id": analysis.get("owner_id") or "",
        "object_type": analysis.get("object_type") or "contacts",
        "object_id": analysis.get("object_id") or analysis.get("contact_id") or "",
        "locale": analysis.get("locale") or "en-US",
        "contact_name": contact_name,
        "company_name": account.get("name") or "",
        "lifecycle_stage": account.get("lifecycle_stage") or "",
        "recent_activity": contact.get("recent_activity") or "",
        "audience_type": campaign.get("audience_type") or "client",
        "region": account.get("region") or "",
        "business_unit": account.get("business_unit") or "",
        "job_family": analysis.get("job_family") or account.get("industry") or "",
        "skill_family": analysis.get("skill_family") or account.get("business_unit") or "",
        "client_account": account.get("name") or "",
        "client_account_id": analysis.get("company_id") or "",
        "source_channel": campaign.get("source_channel") or "",
        "headers": {
            "from": "demo-outreach@example.com",
            "reply_to": "demo-replies@example.com",
        },
        "delivery_context": {key: value for key, value in delivery_context.items() if value not in (None, "")},
        "idempotency_key": analysis["idempotency_key"],
    }
    tenant_id = str(dataset.get("tenant_id") or "").strip()
    clean_tenant = "".join(ch for ch in tenant_id if ch.isalnum() or ch in {"-", "_"})[:120]
    if clean_tenant and dataset["workspace_id"] == f"hubspot_{clean_tenant}":
        payload["tenant_id"] = tenant_id
    return payload


def analysis_payload(dataset: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    payload = base_analysis_payload(dataset, analysis)
    subject = str(analysis.get("subject") or "")
    body = str(analysis.get("body") or "")
    endpoint = str(analysis.get("endpoint") or "")

    if endpoint.endswith("/marketing-emails/analyze"):
        payload["marketingEmail"] = {
            "id": analysis.get("template_id"),
            "subject": subject,
            "html": f"<p>{body}</p>",
            "campaignId": analysis.get("campaign_id"),
            "fromEmail": "demo-outreach@example.com",
            "replyTo": "demo-replies@example.com",
            "state": "DRAFT",
        }
    elif endpoint.endswith("/assets/analyze") or endpoint.endswith("/workflow-actions/analyze-asset-copy"):
        payload.update(
            {
                "asset_type": analysis.get("asset_type") or payload["delivery_context"].get("asset_type") or "HUBSPOT_ASSET",
                "asset_id": analysis.get("template_id"),
                "asset_name": analysis.get("asset_name") or subject,
                "asset_copy": body,
            }
        )
        payload["inputFields"] = {
            "asset_type": payload["asset_type"],
            "asset_id": payload["asset_id"],
            "asset_name": payload["asset_name"],
            "asset_copy": body,
        }
    else:
        payload["inputFields"] = {"subject": subject, "body": body}
    return payload


def run_analysis(app_module, endpoint: str, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    with app_module.app.test_request_context(endpoint, method="POST", json=payload):
        if endpoint.endswith("/marketing-emails/analyze"):
            normalized = app_module.normalize_hubspot_marketing_email_payload(payload, "marketing_email_preflight")
            return app_module.hubspot_analysis_result(normalized, "hubspot_marketing_email_preflight")
        if endpoint.endswith("/assets/analyze"):
            normalized = app_module.normalize_hubspot_asset_payload(payload, "asset_copy_preflight")
            return app_module.hubspot_analysis_result(normalized, "hubspot_asset_copy_preflight")
        if endpoint.endswith("/workflow-actions/analyze-asset-copy"):
            normalized = app_module.normalize_hubspot_asset_payload(payload, "asset_copy_workflow_gate")
            return app_module.hubspot_analysis_result(normalized, "hubspot_asset_copy_workflow_action")
        if endpoint.endswith("/workflow-actions/analyze-email"):
            return app_module.hubspot_analysis_result(payload, "hubspot_workflow_action")
        return app_module.hubspot_analysis_result(payload, "hubspot_crm_card")


def apply_analysis_timestamp(storage_module, request_id: str, created_at: str) -> None:
    if not created_at:
        return
    with storage_module.connect() as conn:
        for table in ("hubspot_email_analyses", "hubspot_email_checks", "hubspot_email_findings"):
            storage_module.execute(conn, f"UPDATE {table} SET created_at = ? WHERE request_id = ?", (created_at, request_id))


def event_context(dataset: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    accounts = entity_index(dataset, "accounts", "company_id")
    contacts = entity_index(dataset, "contacts", "contact_id")
    deals = entity_index(dataset, "deals", "deal_id")
    owners = entity_index(dataset, "owners", "owner_id")
    campaigns = entity_index(dataset, "campaigns", "campaign_id")
    account = accounts.get(str(analysis.get("company_id"))) or {}
    contact = contacts.get(str(analysis.get("contact_id"))) or {}
    deal = deals.get(str(analysis.get("deal_id"))) or {}
    owner = owners.get(str(analysis.get("owner_id"))) or {}
    campaign = campaigns.get(str(analysis.get("campaign_id"))) or {}
    return {
        "demo_analysis_id": analysis.get("id"),
        "campaign_id": analysis.get("campaign_id"),
        "campaign_name": campaign.get("name"),
        "company_id": analysis.get("company_id"),
        "company": account.get("name"),
        "contact_id": analysis.get("contact_id"),
        "contact": " ".join(part for part in (contact.get("first_name"), contact.get("last_name")) if part),
        "deal_id": analysis.get("deal_id"),
        "deal_name": deal.get("name"),
        "owner_id": analysis.get("owner_id"),
        "owner": owner.get("name"),
        "region": account.get("region"),
        "business_unit": account.get("business_unit"),
        "audience_type": campaign.get("audience_type"),
        "skill_family": analysis.get("skill_family") or account.get("business_unit"),
        "job_family": analysis.get("job_family") or account.get("industry"),
    }


def save_activity_events(storage_module, dataset: dict[str, Any], analysis: dict[str, Any], result: dict[str, Any]) -> tuple[int, int]:
    output_fields = result.get("outputFields") or {}
    request_id = str(output_fields.get("texttraits_request_id") or "")
    content_hash = str(output_fields.get("texttraits_content_hash") or "")
    context = event_context(dataset, analysis)

    review_count = 0
    for review in analysis.get("review_actions", []):
        payload = {**context, **(review.get("payload") or {})}
        storage_module.save_hubspot_review_event(
            request_id,
            str(review["action"]),
            payload,
            actor_id=str(review.get("actor_id") or ""),
            status=str(review.get("status") or "recorded"),
        )
        review_count += 1

    outcome_count = 0
    for outcome in analysis.get("outcomes", []):
        payload = {**context, **(outcome.get("payload") or {})}
        storage_module.save_hubspot_outcome_event(
            {
                "request_id": request_id,
                "content_hash": content_hash,
                "workspace_id": dataset["workspace_id"],
                "tenant_id": dataset.get("tenant_id") or dataset["workspace_id"],
                "source_system": "hubspot_demo_crm",
                "event_type": outcome["event_type"],
                "event_id": outcome.get("event_id") or f"{analysis['id']}:{outcome['event_type']}",
                "payload": payload,
                "occurred_at": outcome.get("occurred_at"),
            }
        )
        outcome_count += 1
    return review_count, outcome_count


def seed_dataset(dataset: dict[str, Any], refresh: bool = True, dry_run: bool = False) -> dict[str, Any]:
    summary = {
        "workspace_id": dataset["workspace_id"],
        "dataset": dataset.get("name", ""),
        "analyses": 0,
        "review_events": 0,
        "outcome_events": 0,
        "gate_counts": {},
        "route_counts": {},
    }
    if dry_run:
        for analysis in dataset.get("analyses", []):
            for key in ("id", "endpoint", "idempotency_key", "contact_id", "company_id", "deal_id", "owner_id", "subject", "body"):
                if not analysis.get(key):
                    raise ValueError(f"Demo analysis {analysis.get('id') or '<unknown>'} is missing {key}.")
            summary["analyses"] += 1
        return summary

    app_module, storage_module = prepare_imports()
    if refresh:
        reset_demo_workspace(storage_module, dataset)
    install_demo_policy(storage_module, dataset)

    for analysis in dataset.get("analyses", []):
        endpoint = str(analysis.get("endpoint") or "/v1/integrations/hubspot/crm-card/analyze-email")
        payload = analysis_payload(dataset, analysis)
        result, status_code = run_analysis(app_module, endpoint, payload)
        if status_code != 200:
            raise RuntimeError(f"Seed analysis {analysis.get('id')} failed with {status_code}: {result}")
        request_id = str((result.get("outputFields") or {}).get("texttraits_request_id") or "")
        apply_analysis_timestamp(storage_module, request_id, str(analysis.get("created_at") or ""))
        review_count, outcome_count = save_activity_events(storage_module, dataset, analysis, result)
        gate = str((result.get("outputFields") or {}).get("texttraits_gate") or "unknown")
        route = str((result.get("outputFields") or {}).get("texttraits_route") or "unknown")
        summary["analyses"] += 1
        summary["review_events"] += review_count
        summary["outcome_events"] += outcome_count
        summary["gate_counts"][gate] = summary["gate_counts"].get(gate, 0) + 1
        summary["route_counts"][route] = summary["route_counts"].get(route, 0) + 1

    return summary


def seed_from_file(path: Path = DEFAULT_DATASET_PATH, refresh: bool = True, dry_run: bool = False) -> dict[str, Any]:
    return seed_dataset(load_dataset(path), refresh=refresh, dry_run=dry_run)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH, help="Path to the demo CRM JSON fixture.")
    parser.add_argument("--no-refresh", action="store_true", help="Append to existing demo records instead of clearing the demo workspace first.")
    parser.add_argument("--dry-run", action="store_true", help="Validate the fixture shape without writing records.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    summary = seed_from_file(args.dataset, refresh=not args.no_refresh, dry_run=args.dry_run)
    verb = "Validated" if args.dry_run else "Seeded"
    print(
        f"{verb} demo CRM dataset: "
        f"workspace={summary['workspace_id']} "
        f"analyses={summary['analyses']} "
        f"gates={summary['gate_counts']} "
        f"routes={summary['route_counts']} "
        f"review_events={summary['review_events']} "
        f"outcome_events={summary['outcome_events']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
