from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "texttraits_app"
sys.path.insert(0, str(APP_DIR))

from b2b_profile_engine import PROFILE_ENGINE_VERSION, build_b2b_profile  # noqa: E402


EXPECTED_COLUMNS = (
    "tenant_id",
    "account_id",
    "contact_id_hash",
    "consent_basis",
    "opt_out_state",
    "communication_history",
    "account_context",
    "campaign_goal",
    "outcome_label",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_row(row: dict[str, str]) -> dict[str, str]:
    return {key: str(row.get(key, "") or "").strip() for key in EXPECTED_COLUMNS}


def sample_rows() -> list[dict[str, str]]:
    return [
        {
            "tenant_id": "demo",
            "account_id": "acct_pipeline_001",
            "contact_id_hash": "sha256:demo-contact-1",
            "consent_basis": "business_relationship",
            "opt_out_state": "subscribed",
            "communication_history": "The VP Sales said forecast surprises and late renewal risk are the biggest issue. Security review matters before any rollout. They asked whether this works with Salesforce and existing outreach workflows.",
            "account_context": "B2B SaaS account using Salesforce, Outreach, and RevOps weekly forecast review.",
            "campaign_goal": "Book a workflow-fit pilot discussion",
            "outcome_label": "positive_reply",
        },
        {
            "tenant_id": "demo",
            "account_id": "acct_ops_002",
            "contact_id_hash": "sha256:demo-contact-2",
            "consent_basis": "marketing_consent",
            "opt_out_state": "subscribed",
            "communication_history": "Marketing operations is worried about another tool, adoption, and governance. They asked for a HubSpot workflow action and audit trail before procurement.",
            "account_context": "Lifecycle marketing team with HubSpot workflows and legal review for campaign approvals.",
            "campaign_goal": "Route to governance-first nurture",
            "outcome_label": "needs_review",
        },
    ]


def read_rows(path: Path | None) -> list[dict[str, str]]:
    if not path:
        return sample_rows()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [column for column in EXPECTED_COLUMNS if column not in (reader.fieldnames or [])]
        if missing:
            raise SystemExit(f"Missing required columns: {', '.join(missing)}")
        return [safe_row(row) for row in reader]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_training_record(row: dict[str, str]) -> dict:
    profile = build_b2b_profile(row)
    return {
        "tenant_id": row["tenant_id"],
        "account_id": row["account_id"],
        "contact_id_hash": row["contact_id_hash"],
        "consent_basis": row["consent_basis"],
        "opt_out_state": row["opt_out_state"],
        "outcome_label": row["outcome_label"],
        "safe_features": profile["safe_features"],
        "business_profile": profile["business_profile"],
        "resonance_strategy": profile["resonance_strategy"],
        "privacy": profile["privacy"],
        "labels_allowed": [
            "buying_stage",
            "business_priority",
            "objection_signal",
            "role_context",
            "next_best_action_class",
            "outcome_label",
        ],
        "labels_blocked": [
            "raw_email",
            "raw_phone",
            "age",
            "gender",
            "health",
            "religion",
            "politics",
            "sexual_orientation",
            "financial_eligibility",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare privacy-safe B2B profile model data without local training.")
    parser.add_argument("--communications-csv", type=Path, help="Consented communication export with the documented columns.")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output" / "b2b_profile_model")
    parser.add_argument("--cloud-target", default="colab-or-managed-training", help="Name of the remote training target. No local training is run.")
    args = parser.parse_args()

    rows = read_rows(args.communications_csv)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    records = [build_training_record(row) for row in rows]

    write_jsonl(args.output_dir / "b2b_profile_training_rows.jsonl", records)
    manifest = {
        "created_at": utc_now(),
        "profile_engine_version": PROFILE_ENGINE_VERSION,
        "row_count": len(records),
        "source": str(args.communications_csv) if args.communications_csv else "synthetic_demo_rows",
        "cloud_target": args.cloud_target,
        "local_training_performed": False,
        "expected_columns": EXPECTED_COLUMNS,
        "recommended_model_heads": [
            "buying_stage",
            "business_priority",
            "objection_signal",
            "role_context",
            "next_best_action_class",
            "outcome_label",
        ],
        "privacy_controls": [
            "Use hashed contact IDs.",
            "Keep consent and opt-out state in every row.",
            "Train only on business-relevant labels.",
            "Do not train demographic or sensitive personal attribute heads.",
            "Store raw communication history outside the model artifact when possible.",
        ],
    }
    (args.output_dir / "cloud_training_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Prepared {len(records)} rows in {args.output_dir}")
    print("No local training was run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
