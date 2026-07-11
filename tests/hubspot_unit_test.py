from __future__ import annotations

import os
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "texttraits_app"
sys.path.insert(0, str(APP_DIR))

TEST_DIR = tempfile.TemporaryDirectory()
os.environ["TEXTTRAITS_DB_PATH"] = str(Path(TEST_DIR.name) / "hubspot-unit.sqlite3")
os.environ["DATABASE_URL"] = ""
os.environ["TEXTTRAITS_DATABASE_URL"] = ""
os.environ.setdefault("TEXTTRAITS_SECRET_KEY", "hubspot-unit-secret")

import app as app_module  # noqa: E402
import hubspot_client as client_module  # noqa: E402
import storage  # noqa: E402
from hubspot_analysis import HUBSPOT_EMAIL_RULES_ENGINE_ID, HubSpotAnalysisDecision, HubSpotEmailDraft  # noqa: E402
from hubspot_sync import HubSpotSyncOperation, run_hubspot_sync_operations  # noqa: E402
from integration_adapters import IntegrationProvider, build_authorization_url  # noqa: E402
from runtime_config import env_int  # noqa: E402
from rate_limit import SlidingWindowRateLimiter  # noqa: E402


class HubSpotContractTests(unittest.TestCase):
    def test_rate_limiter_is_bounded_and_returns_retry_window(self) -> None:
        limiter = SlidingWindowRateLimiter(window_seconds=60, max_keys=100)
        self.assertEqual(limiter.allow("portal-a", 2, now=10), (True, 0))
        self.assertEqual(limiter.allow("portal-a", 2, now=11), (True, 0))
        allowed, retry_after = limiter.allow("portal-a", 2, now=12)
        self.assertFalse(allowed)
        self.assertGreater(retry_after, 0)
        self.assertEqual(limiter.allow("portal-a", 2, now=71), (True, 0))
        for index in range(150):
            limiter.allow(f"key-{index}", 1, now=72 + index / 1000)
        self.assertLessEqual(limiter.key_count, 100)

    def test_invalid_integer_environment_falls_back_and_clamps(self) -> None:
        with mock.patch.dict(os.environ, {"UNIT_INTEGER": "not-a-number"}):
            self.assertEqual(env_int("UNIT_INTEGER", 20, minimum=5, maximum=30), 20)
        with mock.patch.dict(os.environ, {"UNIT_INTEGER": "999"}):
            self.assertEqual(env_int("UNIT_INTEGER", 20, minimum=5, maximum=30), 30)

    def test_draft_aliases_normalize_once(self) -> None:
        draft = HubSpotEmailDraft.from_payload(
            {"inputFields": {"hs_email_subject": "Renewal review", "hs_email_body": "Please approve by Friday."}}
        )
        self.assertEqual(draft.subject, "Renewal review")
        self.assertEqual(draft.body, "Please approve by Friday.")
        self.assertEqual(draft.word_count, 6)

    def test_output_contract_includes_engine_and_asset_fields(self) -> None:
        decision = HubSpotAnalysisDecision(
            request_id="request-1",
            content_hash="hash-1",
            idempotency_key="idempotency-1",
            score=82,
            gate="ready",
            route="Sending system",
            next_step="Proceed.",
            owner_queue="Sending system",
            blocker_level="None",
            blocker_reason="All checks passed.",
            policy_version="policy-1",
        )
        fields = decision.output_fields({"texttraits_asset_id": "email-1"})
        self.assertEqual(fields["texttraits_analysis_engine"], HUBSPOT_EMAIL_RULES_ENGINE_ID)
        self.assertEqual(fields["texttraits_asset_id"], "email-1")
        self.assertTrue(fields["texttraits_send_ready"])
        contract = json.loads((ROOT / "hubspot-project/contracts/analysis-contract.json").read_text())
        self.assertEqual(contract["analysisEngine"], HUBSPOT_EMAIL_RULES_ENGINE_ID)
        self.assertTrue(set(contract["commonOutputFields"]).issubset(fields))

    def test_declared_hubspot_backend_contract_matches_flask_routes(self) -> None:
        contract = json.loads((ROOT / "hubspot-project/contracts/analysis-contract.json").read_text())
        declared = set(contract["backendEndpoints"])
        for component in contract["components"].values():
            declared.update(component.get("backendEndpoints", []))
        for workflow in contract["workflowActions"].values():
            declared.add(workflow["endpoint"])
        implemented = {rule.rule for rule in app_module.app.url_map.iter_rules()}
        self.assertTrue(declared.issubset(implemented), sorted(declared - implemented))

    def test_hubspot_analysis_does_not_run_demographic_model(self) -> None:
        client = app_module.app.test_client()
        with mock.patch.object(app_module.predictor, "predict", side_effect=AssertionError("model should not run")):
            response = client.post(
                "/v1/integrations/hubspot/crm-card/analyze-email",
                json={
                    "portal_id": "12345",
                    "delivery_context": {"asset_type": "MARKETING_EMAIL", "html": "<p>Private delivery copy</p>"},
                    "inputFields": {
                        "subject": "Renewal checklist",
                        "body": "Hi Maya, please review the renewal checklist by Friday and reply with approval.",
                    },
                },
            )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertFalse(payload["analysis"]["model_inference_used"])
        self.assertEqual(payload["analysis"]["analysis_engine"], HUBSPOT_EMAIL_RULES_ENGINE_ID)
        stored = storage.get_hubspot_email_analysis(payload["outputFields"]["texttraits_request_id"])
        self.assertNotIn("Hi Maya, please review the renewal checklist", json.dumps(stored))
        self.assertNotIn("Private delivery copy", json.dumps(stored))

    def test_analysis_ingress_rejects_non_object_json(self) -> None:
        client = app_module.app.test_client()
        response = client.post("/v1/integrations/hubspot/crm-card/analyze-email", json=[{"subject": "No"}])
        self.assertEqual(response.status_code, 400)
        self.assertIn("JSON object", response.get_json()["error"])

    def test_content_hash_is_tenant_scoped(self) -> None:
        text = "Same draft content"
        first = app_module.hubspot_content_hash(text, "hubspot_portal-a")
        second = app_module.hubspot_content_hash(text, "hubspot_portal-b")
        self.assertNotEqual(first, second)
        self.assertTrue(first.startswith("hmac-sha256:"))

    def test_score_regression_matrix_is_deterministic_and_complete(self) -> None:
        policy = app_module.normalized_hubspot_email_policy({})
        first = app_module.hubspot_score_validation_report(policy)
        second = app_module.hubspot_score_validation_report(policy)
        self.assertGreaterEqual(first["cases_total"], 8)
        self.assertTrue(first["passed"], first["cases"])
        self.assertEqual(
            [(case["id"], case["actual_score"], case["actual_gate"], case["actual_route"]) for case in first["cases"]],
            [(case["id"], case["actual_score"], case["actual_gate"], case["actual_route"]) for case in second["cases"]],
        )
        cases = {case["id"]: case for case in first["cases"]}
        self.assertEqual(cases["risky_compliance_route"]["actual_route"], "Compliance review")
        self.assertEqual(cases["malformed_empty_draft"]["actual_gate"], "blocked")
        self.assertEqual(cases["templated_personalized_draft"]["actual_gate"], "ready")

    def test_oauth_scope_selection_rejects_unapproved_scopes(self) -> None:
        provider = IntegrationProvider(
            name="HubSpot",
            category="CRM",
            status="needs_credentials",
            auth="OAuth 2.0",
            scopes=("oauth",),
            optional_scopes=("crm.objects.contacts.read",),
            setup_steps=(),
            client_id_env="UNIT_HUBSPOT_CLIENT_ID",
            client_secret_env="UNIT_HUBSPOT_CLIENT_SECRET",
            auth_url="https://app.hubspot.com/oauth/authorize",
        )
        with mock.patch.dict(
            os.environ,
            {"UNIT_HUBSPOT_CLIENT_ID": "client-id", "UNIT_HUBSPOT_CLIENT_SECRET": "client-secret"},
        ):
            url = build_authorization_url(
                provider,
                "https://texttraits.example/oauth/callback",
                "state-1",
                ["crm.objects.contacts.read", "unapproved.scope"],
            )
        self.assertIn("crm.objects.contacts.read", url)
        self.assertNotIn("unapproved.scope", url)

    def test_hubspot_manifest_and_runtime_oauth_scopes_match(self) -> None:
        manifest = json.loads((ROOT / "hubspot-project/src/app/app-hsmeta.json").read_text())
        configured = manifest["config"]["auth"]
        provider = app_module.get_provider("HubSpot")
        self.assertIsNotNone(provider)
        self.assertEqual(set(configured["requiredScopes"]), set(provider.scopes))
        self.assertEqual(set(configured["optionalScopes"]), set(provider.optional_scopes))


class HubSpotClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = {
            "portal_id": "12345",
            "status": "connected",
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "expires_at": "2999-01-01T00:00:00+00:00",
            "scopes": ["crm.objects.contacts.read"],
        }

    def test_connection_is_reused_within_client(self) -> None:
        with (
            mock.patch.object(client_module, "get_hubspot_portal_connection", return_value=self.connection) as connection_lookup,
            mock.patch.object(client_module, "_json_request", return_value=(200, {"ok": True})),
            mock.patch.object(client_module, "_audit_hubspot_api_event"),
        ):
            client = client_module.HubSpotApiClient("12345")
            client.request("GET", "/crm/objects/contacts", required_scopes=("crm.objects.contacts.read",))
            client.request("GET", "/crm/objects/contacts", required_scopes=("crm.objects.contacts.read",))
        self.assertEqual(connection_lookup.call_count, 1)

    def test_transient_network_failure_retries(self) -> None:
        with (
            mock.patch.object(client_module, "get_hubspot_portal_connection", return_value=self.connection),
            mock.patch.object(client_module, "_json_request", side_effect=[(599, {"error": "network"}), (200, {"ok": True})]) as transport,
            mock.patch.object(client_module, "_audit_hubspot_api_event"),
            mock.patch.object(client_module.time, "sleep"),
        ):
            response = client_module.HubSpotApiClient("12345").request("GET", "/crm/objects/contacts")
        self.assertEqual(response["status_code"], 200)
        self.assertEqual(transport.call_count, 2)

    def test_non_idempotent_post_is_not_retried(self) -> None:
        with (
            mock.patch.object(client_module, "get_hubspot_portal_connection", return_value=self.connection),
            mock.patch.object(client_module, "_json_request", return_value=(503, {"error": "upstream"})) as transport,
            mock.patch.object(client_module, "_audit_hubspot_api_event"),
            self.assertRaises(client_module.HubSpotClientError),
        ):
            client_module.HubSpotApiClient("12345").request("POST", "/crm/objects/contacts", body={"properties": {}})
        self.assertEqual(transport.call_count, 1)

    def test_idempotency_key_allows_safe_post_retry(self) -> None:
        with (
            mock.patch.object(client_module, "get_hubspot_portal_connection", return_value=self.connection),
            mock.patch.object(client_module, "_json_request", side_effect=[(503, {"error": "upstream"}), (200, {"ok": True})]) as transport,
            mock.patch.object(client_module, "_audit_hubspot_api_event"),
            mock.patch.object(client_module.time, "sleep"),
        ):
            response = client_module.HubSpotApiClient("12345").request(
                "POST",
                "/crm/objects/contacts",
                body={"properties": {}},
                idempotency_key="contact-create-1",
            )
        self.assertEqual(response["status_code"], 200)
        self.assertEqual(transport.call_count, 2)


class HubSpotSyncTests(unittest.TestCase):
    def test_independent_operations_run_concurrently_and_return_in_plan_order(self) -> None:
        barrier = threading.Barrier(2)

        def operation(name: str) -> dict:
            barrier.wait(timeout=1)
            return {"action": name}

        with mock.patch.dict(os.environ, {"TEXTTRAITS_HUBSPOT_SYNC_WORKERS": "2"}):
            actions, errors = run_hubspot_sync_operations(
                [
                    HubSpotSyncOperation("first", lambda: operation("first")),
                    HubSpotSyncOperation("second", lambda: operation("second")),
                ],
                lambda name, error: {"action": name, "error": str(error)},
            )
        self.assertEqual(actions, [{"action": "first"}, {"action": "second"}])
        self.assertEqual(errors, [])


class HubSpotStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        path = Path(os.environ["TEXTTRAITS_DB_PATH"])
        path.unlink(missing_ok=True)
        storage.init_db()

    def test_sqlite_context_manager_closes_connection(self) -> None:
        with storage.connect() as connection:
            storage.execute(connection, "SELECT 1").fetchone()
        with self.assertRaises(storage.sqlite3.ProgrammingError):
            storage.execute(connection, "SELECT 1")

    def test_current_schema_contains_replay_and_governance_dimensions(self) -> None:
        with storage.connect() as connection:
            analysis_columns = {row["name"] for row in connection.execute("PRAGMA table_info(hubspot_email_analyses)").fetchall()}
            outcome_columns = {row["name"] for row in connection.execute("PRAGMA table_info(hubspot_email_outcome_events)").fetchall()}
            outcome_indexes = {row["name"] for row in connection.execute("PRAGMA index_list(hubspot_email_outcome_events)").fetchall()}
        self.assertTrue({"rule_pack", "policy_version", "analysis_engine"}.issubset(analysis_columns))
        self.assertIn("event_key", outcome_columns)
        self.assertIn("idx_hubspot_email_outcomes_event_key", outcome_indexes)

    @staticmethod
    def analysis_record(request_id: str = "analysis-1", portal_id: str = "12345") -> dict:
        return {
            "request_id": request_id,
            "workspace_id": f"hubspot_{portal_id}",
            "tenant_id": portal_id,
            "portal_id": portal_id,
            "source_system": "hubspot",
            "campaign_id": "campaign-1",
            "template_id": "template-1",
            "content_hash": f"hash-{request_id}",
            "score": 72,
            "gate": "needs_review",
            "route": "Marketing review",
            "checks": [{"id": "specificity", "label": "Specificity", "status": "needs_review", "weight": 20, "score": 10}],
            "findings": [{"id": "specificity_low", "title": "Needs detail", "severity": "medium"}],
            "context": {
                "audience_type": "candidate",
                "region": "US",
                "business_unit": "Staffing",
                "job_family": "Logistics",
                "skill_family": "Warehouse",
            },
            "analysis_engine": HUBSPOT_EMAIL_RULES_ENGINE_ID,
            "policy": {"version": "policy-1", "rule_pack": "general"},
        }

    def test_analysis_and_artifacts_commit_atomically(self) -> None:
        with mock.patch.object(storage, "save_hubspot_analysis_artifacts", side_effect=RuntimeError("artifact failure")):
            with self.assertRaises(RuntimeError):
                storage.save_hubspot_email_analysis(self.analysis_record())
        self.assertIsNone(storage.get_hubspot_email_analysis("analysis-1"))

    def test_batch_analyses_commit_atomically(self) -> None:
        records = [self.analysis_record("batch-1"), self.analysis_record("batch-2")]
        original = storage.save_hubspot_analysis_artifacts
        calls = 0

        def fail_second_artifact(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("second artifact failure")
            return original(*args, **kwargs)

        with mock.patch.object(storage, "save_hubspot_analysis_artifacts", side_effect=fail_second_artifact):
            with self.assertRaises(RuntimeError):
                storage.save_hubspot_email_analyses(records)
        self.assertIsNone(storage.get_hubspot_email_analysis("batch-1"))
        self.assertIsNone(storage.get_hubspot_email_analysis("batch-2"))

    def test_normalized_dimensions_drive_rollups(self) -> None:
        storage.save_hubspot_email_analysis(self.analysis_record())
        row = storage.get_hubspot_email_analysis("analysis-1")
        self.assertEqual(row["region"], "US")
        self.assertEqual(row["analysis_engine"], HUBSPOT_EMAIL_RULES_ENGINE_ID)
        self.assertEqual(row["rule_pack"], "general")
        self.assertEqual(row["policy_version"], "policy-1")
        campaign = storage.hubspot_analysis_health_rollup("campaign_id")
        self.assertEqual(campaign[0]["campaign_id"], "campaign-1")
        self.assertEqual(campaign[0]["needs_review"], 1)
        failures = storage.hubspot_failed_check_rollup()
        self.assertEqual(failures[0], {"check": "Specificity", "count": 1})
        self.assertEqual(storage.hubspot_analysis_health_rollup("rule_pack")[0]["rule_pack"], "general")

    def test_dashboard_uses_one_database_connection(self) -> None:
        storage.save_hubspot_email_analysis(self.analysis_record())
        with mock.patch.object(storage, "connect", wraps=storage.connect) as connect_spy:
            dashboard = storage.hubspot_email_dashboard()
        self.assertEqual(connect_spy.call_count, 1)
        self.assertEqual(dashboard["rule_pack_health"][0]["rule_pack"], "general")

    def test_outcome_event_replays_are_idempotent(self) -> None:
        record = {
            "request_id": "analysis-1",
            "content_hash": "hash-analysis-1",
            "workspace_id": "hubspot_12345",
            "tenant_id": "12345",
            "source_system": "hubspot_webhook",
            "event_type": "marketingEmail.propertyChange",
            "event_id": "event-1",
            "occurred_at": "2026-07-11T12:00:00Z",
            "payload": {"marketingEmail": {"subject": "Private subject", "html": "<p>Private body</p>"}, "campaignId": "campaign-1"},
        }
        first = storage.save_hubspot_outcome_event(record)
        replay = storage.save_hubspot_outcome_event(record)
        self.assertFalse(first["duplicate"])
        self.assertTrue(replay["duplicate"])
        self.assertEqual(first["event_key"], replay["event_key"])
        self.assertNotIn("Private subject", json.dumps(first["payload"]))
        self.assertNotIn("Private body", json.dumps(first["payload"]))
        self.assertEqual(first["payload"]["campaignId"], "campaign-1")
        self.assertEqual(len(storage.list_hubspot_outcome_events()), 1)

    def test_outcome_batch_validation_is_atomic(self) -> None:
        records = [
            {
                "request_id": "analysis-1",
                "content_hash": "hash-analysis-1",
                "source_system": "hubspot",
                "event_type": "delivered",
                "event_id": "delivery-1",
            },
            {
                "request_id": "analysis-2",
                "content_hash": "hash-analysis-2",
                "source_system": "hubspot",
                "event_type": "",
                "event_id": "invalid-1",
            },
        ]
        with self.assertRaises(ValueError):
            storage.save_hubspot_outcome_events(records)
        self.assertEqual(storage.list_hubspot_outcome_events(), [])

    def test_dashboard_is_portal_scoped_and_reports_exact_totals(self) -> None:
        storage.save_hubspot_email_analysis(self.analysis_record("portal-a-1", "portal-a"))
        storage.save_hubspot_email_analysis(self.analysis_record("portal-a-2", "portal-a"))
        storage.save_hubspot_email_analysis(self.analysis_record("portal-b-1", "portal-b"))
        storage.save_hubspot_review_event("portal-a-1", "send_to_marketing_review")
        storage.save_hubspot_review_event("portal-a-2", "send_to_marketing_review")
        storage.save_hubspot_review_event("portal-b-1", "approve_review")
        storage.save_hubspot_outcome_event(
            {
                "request_id": "portal-a-1",
                "workspace_id": "hubspot_portal-a",
                "tenant_id": "portal-a",
                "source_system": "hubspot",
                "event_type": "clicked",
            }
        )
        storage.save_hubspot_outcome_event(
            {
                "request_id": "portal-b-1",
                "workspace_id": "hubspot_portal-b",
                "tenant_id": "portal-b",
                "source_system": "hubspot",
                "event_type": "complained",
            }
        )

        dashboard = storage.hubspot_email_dashboard(
            limit=1,
            analysis_filters={"portal_id": "portal-a"},
            outcome_filters={"tenant_id": "portal-a"},
        )
        self.assertEqual(dashboard["total_analyses"], 2)
        self.assertEqual(dashboard["analysis_window_count"], 1)
        self.assertEqual(dashboard["outcome_counts"], {"clicked": 1})
        self.assertEqual(dashboard["review_sla"]["open"], 1)
        self.assertEqual(dashboard["review_sla"]["resolved"], 0)

    def test_review_action_rejects_cross_portal_request_id(self) -> None:
        storage.save_hubspot_email_analysis(self.analysis_record("portal-a-review", "portal-a"))
        response = app_module.app.test_client().post(
            "/v1/integrations/hubspot/review-action",
            json={
                "portal_id": "portal-b",
                "request_id": "portal-a-review",
                "action": "approve_review",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(storage.list_hubspot_review_states(filters={"request_id": "portal-a-review"}), [])

    def test_outcome_ingest_rejects_cross_tenant_request_id(self) -> None:
        storage.save_hubspot_email_analysis(self.analysis_record("portal-a-outcome", "portal-a"))
        response = app_module.app.test_client().post(
            "/v1/integrations/hubspot/outcomes",
            json={
                "portal_id": "portal-b",
                "request_id": "portal-a-outcome",
                "event_type": "clicked",
                "event_id": "cross-tenant-1",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(storage.list_hubspot_outcome_events(), [])

    def test_retention_purge_removes_old_governance_rows(self) -> None:
        storage.save_hubspot_email_analysis(self.analysis_record("old-analysis"))
        storage.save_hubspot_review_event("old-analysis", "mark_reviewed")
        storage.save_hubspot_outcome_event(
            {
                "request_id": "old-analysis",
                "content_hash": "hash-old-analysis",
                "source_system": "hubspot",
                "event_type": "delivered",
                "event_id": "old-delivery",
            }
        )
        old = "2020-01-01T00:00:00+00:00"
        with storage.connect() as connection:
            for table, column in storage.HUBSPOT_RETENTION_TABLES:
                storage.execute(connection, f"UPDATE {table} SET {column} = ?", (old,))
        preview = storage.hubspot_retention_summary(days=90, dry_run=True)
        self.assertGreaterEqual(preview["total_records"], 5)
        purged = storage.hubspot_retention_summary(days=90, dry_run=False)
        self.assertEqual(purged["total_records"], preview["total_records"])
        self.assertIsNone(storage.get_hubspot_email_analysis("old-analysis"))
        self.assertEqual(storage.list_hubspot_outcome_events(), [])

    def test_csv_export_cells_neutralize_formulas(self) -> None:
        for value in ("=SUM(A1:A2)", "+cmd", "-10+20", "@IMPORTDATA(A1)"):
            self.assertTrue(app_module.safe_csv_cell(value).startswith("'"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
