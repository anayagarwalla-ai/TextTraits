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


class HubSpotContractTests(unittest.TestCase):
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

    def test_hubspot_analysis_does_not_run_demographic_model(self) -> None:
        client = app_module.app.test_client()
        with mock.patch.object(app_module.predictor, "predict", side_effect=AssertionError("model should not run")):
            response = client.post(
                "/v1/integrations/hubspot/crm-card/analyze-email",
                json={
                    "portal_id": "12345",
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

    @staticmethod
    def analysis_record(request_id: str = "analysis-1") -> dict:
        return {
            "request_id": request_id,
            "workspace_id": "hubspot_12345",
            "tenant_id": "12345",
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
        campaign = storage.hubspot_analysis_health_rollup("campaign_id")
        self.assertEqual(campaign[0]["campaign_id"], "campaign-1")
        self.assertEqual(campaign[0]["needs_review"], 1)
        failures = storage.hubspot_failed_check_rollup()
        self.assertEqual(failures[0], {"check": "Specificity", "count": 1})


if __name__ == "__main__":
    unittest.main(verbosity=2)
