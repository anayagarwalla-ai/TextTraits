from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "texttraits_app"
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

tmpdir = tempfile.TemporaryDirectory()
os.environ["TEXTTRAITS_DB_PATH"] = str(Path(tmpdir.name) / "workspace.sqlite3")
os.environ["DATABASE_URL"] = ""
os.environ["TEXTTRAITS_DATABASE_URL"] = ""
os.environ["TEXTTRAITS_ALLOW_DEMO"] = "true"
os.environ["ENABLE_DEV_TOOLS"] = "false"
os.environ.setdefault("TEXTTRAITS_SECRET_KEY", "test-secret-key")

import seed_demo_crm  # noqa: E402


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    dataset = seed_demo_crm.load_dataset(seed_demo_crm.DEFAULT_DATASET_PATH)
    expected_analyses = len(dataset["analyses"])
    expected_workspace = dataset["workspace_id"]

    first_summary = seed_demo_crm.seed_from_file(seed_demo_crm.DEFAULT_DATASET_PATH, refresh=True)
    assert_true(first_summary["analyses"] == expected_analyses, "all demo analyses should seed")
    assert_true({"ready", "needs_review", "blocked"}.issubset(first_summary["gate_counts"]), "demo seed should cover ready, review, and blocked gates")
    assert_true(first_summary["outcome_events"] >= expected_analyses, "demo seed should create activity/outcome events")
    assert_true(first_summary["review_events"] >= expected_analyses, "demo seed should create review events")

    sys.path.insert(0, str(APP_DIR))
    import storage  # noqa: E402

    analyses = storage.list_hubspot_email_analyses(limit=100, filters={"workspace_id": expected_workspace})
    assert_true(len(analyses) == expected_analyses, "seeded analyses should be queryable by workspace")
    for analysis in analyses:
        assert_true(analysis["company_id"], "seeded analyses should include company IDs")
        assert_true(analysis["contact_id"], "seeded analyses should include contact IDs")
        assert_true(analysis["deal_id"], "seeded analyses should include deal IDs")
        assert_true(analysis["owner_id"], "seeded analyses should include owner IDs")
        context = analysis.get("context") or {}
        assert_true(context.get("delivery_context", {}).get("demo_dataset"), "seeded analyses should preserve demo context")

    outcomes = storage.list_hubspot_outcome_events(limit=100, filters={"workspace_id": expected_workspace})
    assert_true(len(outcomes) == first_summary["outcome_events"], "seeded outcome count should match the summary")
    assert_true(any(event["event_type"] == "replied" for event in outcomes), "demo outcomes should include reply activity")
    assert_true(any((event.get("payload") or {}).get("deal_id") for event in outcomes), "outcome payloads should keep CRM deal context")

    request_ids = {analysis["request_id"] for analysis in analyses}
    review_states = storage.list_hubspot_review_states(limit=100)
    assert_true(any(state["request_id"] in request_ids for state in review_states), "seeded review states should join to analyses")

    policy = storage.get_hubspot_policy_config(expected_workspace, dataset["environment"])
    assert_true(policy and policy["policy"]["version"] == dataset["policy"]["version"], "demo policy should be saved")
    routing = storage.get_hubspot_route_owner_map(dataset["portal_id"], expected_workspace)
    assert_true(routing and routing["route_owner_map"].get("Compliance review"), "demo owner routing should be saved")

    dashboard = storage.hubspot_email_dashboard(limit=100)
    assert_true(dashboard["gate_counts"].get("blocked", 0) >= 1, "dashboard should include blocked demo analyses")
    assert_true(dashboard["campaign_health"], "dashboard should include campaign rollups")
    assert_true(dashboard["blocked_by_region"], "dashboard should include region rollups")
    assert_true(dashboard["outcome_by_audience_segment"], "dashboard should include audience outcome rollups")

    second_summary = seed_demo_crm.seed_from_file(seed_demo_crm.DEFAULT_DATASET_PATH, refresh=True)
    analyses_after_refresh = storage.list_hubspot_email_analyses(limit=100, filters={"workspace_id": expected_workspace})
    outcomes_after_refresh = storage.list_hubspot_outcome_events(limit=100, filters={"workspace_id": expected_workspace})
    assert_true(second_summary["analyses"] == expected_analyses, "refresh seed should still process all analyses")
    assert_true(len(analyses_after_refresh) == expected_analyses, "refresh seed should not duplicate analyses")
    assert_true(len(outcomes_after_refresh) == first_summary["outcome_events"], "refresh seed should not duplicate outcomes")

    print("Demo CRM seed checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
