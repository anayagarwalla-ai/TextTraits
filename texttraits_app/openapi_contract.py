from __future__ import annotations

from typing import Any

from email_analysis import API_VERSION, POLICY_BUNDLE_VERSION
from integration_contracts import CONTRACT_VERSION, all_manifests


def schema_ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}


def json_request(schema_name: str) -> dict[str, Any]:
    return {
        "required": True,
        "content": {
            "application/json": {
                "schema": schema_ref(schema_name),
            }
        },
    }


def json_response(schema_name: str, description: str = "OK") -> dict[str, Any]:
    return {
        "description": description,
        "content": {
            "application/json": {
                "schema": schema_ref(schema_name),
            }
        },
    }


def error_response(description: str = "Error") -> dict[str, Any]:
    return json_response("ErrorResponse", description)


def build_openapi_spec(base_url: str) -> dict[str, Any]:
    public_url = (base_url or "http://127.0.0.1:5000").rstrip("/")
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "TextTraits Enterprise Email Analysis API",
            "version": API_VERSION,
            "summary": "Non-generative scoring, policy gating, routing, and integration workflow contracts for existing emails.",
            "description": "TextTraits v1 analyzes existing email content and returns objective model signals, structured policy findings, send-readiness gates, integration routes, hashes, versions, and governance metadata. It does not generate or rewrite email copy.",
        },
        "servers": [{"url": public_url}],
        "security": [{"ApiKeyAuth": []}, {"CsrfSession": []}],
        "tags": [
            {"name": "Email analysis"},
            {"name": "Integration setup"},
            {"name": "Sandbox adapters"},
            {"name": "Governance"},
        ],
        "paths": {
            "/v1/email/analyze": {
                "post": {
                    "tags": ["Email analysis"],
                    "operationId": "analyzeEmail",
                    "summary": "Analyze an existing email and return a policy-backed send-readiness decision.",
                    "requestBody": json_request("EmailAnalyzeRequest"),
                    "responses": {"200": json_response("EmailAnalyzeResponse"), "400": error_response("Invalid request"), "503": error_response("Model unavailable")},
                }
            },
            "/v1/integrations/manifests": {
                "get": {
                    "tags": ["Integration setup"],
                    "operationId": "listIntegrationManifests",
                    "summary": "List provider manifests and saved field mappings.",
                    "responses": {"200": json_response("IntegrationManifestsResponse"), "401": error_response("Authentication required")},
                }
            },
            "/v1/integrations/{provider}/manifest": {
                "get": {
                    "tags": ["Integration setup"],
                    "operationId": "getIntegrationManifest",
                    "summary": "Get one provider manifest, template, and saved mapping.",
                    "parameters": [provider_parameter()],
                    "responses": {"200": json_response("IntegrationManifestResponse"), "401": error_response("Authentication required"), "404": error_response("Unsupported provider")},
                }
            },
            "/v1/integrations/{provider}/field-mapping/validate": {
                "post": {
                    "tags": ["Integration setup"],
                    "operationId": "validateFieldMapping",
                    "summary": "Validate a provider field mapping before saving it.",
                    "parameters": [provider_parameter()],
                    "requestBody": json_request("FieldMappingSaveRequest"),
                    "responses": {"200": json_response("FieldMappingValidationResponse"), "404": error_response("Unsupported provider")},
                }
            },
            "/v1/integrations/{provider}/field-mapping": {
                "post": {
                    "tags": ["Integration setup"],
                    "operationId": "saveFieldMapping",
                    "summary": "Save a validated provider field mapping for a workspace.",
                    "parameters": [provider_parameter()],
                    "requestBody": json_request("FieldMappingSaveRequest"),
                    "responses": {"200": json_response("FieldMappingSaveResponse"), "400": error_response("Incomplete mapping"), "404": error_response("Unsupported provider")},
                }
            },
            "/v1/integrations/sandbox-flows": {
                "get": {
                    "tags": ["Sandbox adapters"],
                    "operationId": "listSandboxFlows",
                    "summary": "List available sandbox adapter flows.",
                    "security": [],
                    "responses": {"200": json_response("SandboxFlowsResponse")},
                }
            },
            "/v1/integrations/hubspot/platform-config": {
                "get": {
                    "tags": ["Integration setup"],
                    "operationId": "getHubSpotPlatformConfig",
                    "summary": "Return HubSpot developer-platform endpoints, env requirements, and local scaffold guidance.",
                    "security": [],
                    "responses": {"200": json_response("HubSpotPlatformConfigResponse")},
                }
            },
            "/v1/integrations/hubspot/crm-card": {
                "get": {
                    "tags": ["Integration setup"],
                    "operationId": "getHubSpotCrmCard",
                    "summary": "Return a safe HubSpot CRM app-card context for invoking TextTraits from a CRM record.",
                    "security": [],
                    "responses": {"200": json_response("HubSpotCrmCardResponse"), "401": error_response("HubSpot signature verification failed")},
                }
            },
            "/v1/integrations/hubspot/crm-card/analyze-email": {
                "post": {
                    "tags": ["Sandbox adapters"],
                    "operationId": "hubspotCrmCardAnalyzeEmail",
                    "summary": "Analyze an existing email draft invoked from a HubSpot CRM app card.",
                    "requestBody": json_request("HubSpotCrmCardAnalyzeRequest"),
                    "responses": {"200": json_response("HubSpotCrmCardAnalyzeResponse"), "401": error_response("HubSpot signature verification failed")},
                }
            },
            "/v1/integrations/hubspot/workflow-actions/analyze-email": {
                "post": {
                    "tags": ["Sandbox adapters"],
                    "operationId": "hubspotWorkflowAction",
                    "summary": "Sandbox HubSpot workflow action analysis flow.",
                    "requestBody": json_request("HubSpotWorkflowRequest"),
                    "responses": {"200": json_response("HubSpotWorkflowResponse")},
                }
            },
            "/v1/integrations/salesforce/journey-builder/activity": {
                "post": {
                    "tags": ["Sandbox adapters"],
                    "operationId": "salesforceJourneyBuilderActivity",
                    "summary": "Sandbox Salesforce Journey Builder activity analysis flow.",
                    "requestBody": json_request("SalesforceJourneyRequest"),
                    "responses": {"200": json_response("SalesforceJourneyResponse")},
                }
            },
            "/v1/integrations/sendgrid-ses/middleware": {
                "post": {
                    "tags": ["Sandbox adapters"],
                    "operationId": "sendgridSesMiddleware",
                    "summary": "Sandbox SendGrid/SES pre-send middleware flow.",
                    "requestBody": json_request("SendMiddlewareRequest"),
                    "responses": {"200": json_response("SendMiddlewareResponse")},
                }
            },
            "/v1/integrations/braze/canvas-gate": {
                "post": {
                    "tags": ["Sandbox adapters"],
                    "operationId": "brazeCanvasGate",
                    "summary": "Sandbox Braze Canvas pre-send gate with Currents join metadata.",
                    "requestBody": json_request("EnterpriseAdapterRequest"),
                    "responses": {"200": json_response("EnterpriseAdapterResponse")},
                }
            },
            "/v1/integrations/marketo/smart-campaign-gate": {
                "post": {
                    "tags": ["Sandbox adapters"],
                    "operationId": "marketoSmartCampaignGate",
                    "summary": "Sandbox Marketo smart campaign email-asset gate.",
                    "requestBody": json_request("EnterpriseAdapterRequest"),
                    "responses": {"200": json_response("EnterpriseAdapterResponse")},
                }
            },
            "/v1/integrations/iterable/workflow-gate": {
                "post": {
                    "tags": ["Sandbox adapters"],
                    "operationId": "iterableWorkflowGate",
                    "summary": "Sandbox Iterable workflow gate with Handlebars render checks.",
                    "requestBody": json_request("EnterpriseAdapterRequest"),
                    "responses": {"200": json_response("EnterpriseAdapterResponse")},
                }
            },
            "/v1/integrations/warehouse/feedback-import": {
                "post": {
                    "tags": ["Sandbox adapters"],
                    "operationId": "warehouseFeedbackImport",
                    "summary": "Import warehouse feedback rows and join outcomes to analyses.",
                    "requestBody": json_request("WarehouseFeedbackRequest"),
                    "responses": {"200": json_response("SampleImportResponse")},
                }
            },
            "/v1/integrations/simulate": {
                "post": {
                    "tags": ["Integration setup"],
                    "operationId": "simulateAdapter",
                    "summary": "Run an internal adapter simulator for a provider payload.",
                    "requestBody": json_request("AdapterSimulatorRequest"),
                    "responses": {"200": json_response("EnterpriseAdapterResponse")},
                }
            },
            "/v1/templates/render-test": {
                "post": {
                    "tags": ["Email analysis"],
                    "operationId": "renderTemplateTest",
                    "summary": "Render-test Liquid, Handlebars, percent, and bracket personalization tokens against sample context.",
                    "requestBody": json_request("TemplateRenderTestRequest"),
                    "responses": {"200": json_response("TemplateRenderTestResponse")},
                }
            },
            "/v1/webhooks/post-send": {
                "post": {
                    "tags": ["Governance"],
                    "operationId": "postSendWebhook",
                    "summary": "Ingest signed post-send provider events with retry deduplication.",
                    "parameters": [
                        {"name": "X-TextTraits-Signature", "in": "header", "required": False, "schema": {"type": "string"}, "description": "HMAC-SHA256 signature using TEXTTRAITS_WEBHOOK_SECRET."},
                        {"name": "X-TextTraits-Timestamp", "in": "header", "required": False, "schema": {"type": "string"}, "description": "Unix timestamp used in timestamped webhook signatures."},
                    ],
                    "requestBody": json_request("PostSendWebhookRequest"),
                    "responses": {"200": json_response("PostSendWebhookResponse"), "202": json_response("PostSendWebhookResponse", "Accepted for retry"), "401": error_response("Webhook signature verification failed")},
                }
            },
            "/v1/samples/import": {
                "post": {
                    "tags": ["Governance"],
                    "operationId": "importSamples",
                    "summary": "Import warehouse-style sample rows and analyze them in batch.",
                    "requestBody": json_request("SampleImportRequest"),
                    "responses": {"200": json_response("SampleImportResponse"), "413": error_response("Too many samples")},
                }
            },
            "/v1/governance/dashboard": {
                "get": {
                    "tags": ["Governance"],
                    "operationId": "governanceDashboard",
                    "summary": "Return persisted governance summary, analyses, webhooks, imports, and field mappings.",
                    "responses": {"200": json_response("GovernanceDashboardResponse"), "401": error_response("Authentication required")},
                }
            },
            "/v1/governance/export": {
                "get": {
                    "tags": ["Governance"],
                    "operationId": "governanceExport",
                    "summary": "Export analyses, findings, outcomes, or joined outcome rows as JSON or CSV.",
                    "responses": {"200": {"description": "JSON or CSV governance export"}, "401": error_response("Authentication required")},
                }
            },
            "/v1/governance/policy": {
                "get": {
                    "tags": ["Governance"],
                    "operationId": "getGovernancePolicy",
                    "summary": "Return workspace governance policy controls used by the send-readiness gate.",
                    "responses": {"200": json_response("GovernancePolicyResponse"), "401": error_response("Authentication required")},
                },
                "put": {
                    "tags": ["Governance"],
                    "operationId": "saveGovernancePolicy",
                    "summary": "Save workspace governance policy controls for thresholds, retention, and storage mode.",
                    "requestBody": json_request("GovernancePolicySaveRequest"),
                    "responses": {"200": json_response("GovernancePolicyResponse")},
                },
            },
            "/v1/openapi.json": {
                "get": {
                    "tags": ["Integration setup"],
                    "operationId": "openApiContract",
                    "summary": "Return this machine-readable API contract.",
                    "security": [],
                    "responses": {"200": {"description": "OpenAPI document"}},
                }
            },
            "/v1/install-kit": {
                "get": {
                    "tags": ["Integration setup"],
                    "operationId": "installKit",
                    "summary": "Return endpoint links, manifests, and sample payload references for enterprise installation.",
                    "security": [],
                    "responses": {"200": json_response("InstallKitResponse")},
                }
            },
        },
        "components": {
            "securitySchemes": {
                "ApiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-TextTraits-Api-Key"},
                "CsrfSession": {"type": "apiKey", "in": "header", "name": "X-CSRF-Token"},
            },
            "schemas": schemas(),
        },
        "x-texttraits": {
            "non_generative": True,
            "policy_bundle_version": POLICY_BUNDLE_VERSION,
            "integration_contract_version": CONTRACT_VERSION,
            "provider_manifest_count": len(all_manifests()),
        },
    }


def provider_parameter() -> dict[str, Any]:
    return {
        "name": "provider",
        "in": "path",
        "required": True,
        "schema": {"type": "string", "enum": ["hubspot", "salesforce", "sendgrid_ses", "braze", "marketo", "iterable", "warehouse", "post_send_webhook"]},
    }


def schemas() -> dict[str, Any]:
    finding = {
        "type": "object",
        "required": ["id", "severity", "category", "title", "evidence", "remediation"],
        "properties": {
            "id": {"type": "string"},
            "severity": {"type": "string", "enum": ["critical", "high", "medium", "low", "info"]},
            "category": {"type": "string"},
            "title": {"type": "string"},
            "evidence": {"type": "array", "items": {"type": "object"}},
            "remediation": {"type": "string"},
            "details": {"type": "string"},
        },
    }
    gate = {
        "type": "object",
        "required": ["status", "send_ready", "route", "highest_severity"],
        "properties": {
            "status": {"type": "string", "enum": ["ready", "needs_review", "blocked"]},
            "send_ready": {"type": "boolean"},
            "route": {"type": "string"},
            "highest_severity": {"type": "string"},
            "thresholds": {"type": "object"},
        },
    }
    mapping = {
        "type": "object",
        "properties": {
            "inputs": {"type": "object", "additionalProperties": {"type": "string"}},
            "outputs": {"type": "object", "additionalProperties": {"type": "string"}},
        },
    }
    governance_policy = {
        "type": "object",
        "properties": {
            "workspace_id": {"type": "string"},
            "version": {"type": "string"},
            "policy_environment": {"type": "string", "enum": ["sandbox", "staging", "production"]},
            "retention_days": {"type": "integer", "minimum": 30, "maximum": 3650},
            "webhook_retention_days": {"type": "integer", "minimum": 30, "maximum": 3650},
            "webhook_dedupe_window_days": {"type": "integer", "minimum": 1, "maximum": 365},
            "min_ready_score": {"type": "integer", "minimum": 0, "maximum": 100},
            "high_severity_requires_review": {"type": "boolean"},
            "rule_family_modes": {"type": "object", "additionalProperties": {"type": "string", "enum": ["fail_open", "review", "fail_closed"]}},
            "content_storage_mode": {"type": "string", "enum": ["hash_only", "metadata_only"]},
            "sample_import_limit": {"type": "integer", "minimum": 1, "maximum": 100},
            "send_path_timeout_ms": {"type": "integer", "minimum": 50, "maximum": 10000},
            "idempotency_window_seconds": {"type": "integer", "minimum": 60, "maximum": 86400},
            "updated_at": {"type": "string"},
        },
    }
    return {
        "EmailAnalyzeRequest": {
            "type": "object",
            "required": ["body"],
            "properties": {
                "request_id": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "audience": {"type": "string"},
                "intent": {"type": "string"},
                "channel": {"type": "string"},
                "policy_bundle": {"type": "string"},
                "tenant_id": {"type": "string"},
                "workspace_id": {"type": "string"},
                "source_system": {"type": "string"},
                "analysis_mode": {"type": "string", "enum": ["authoring_lint", "pre_send_gate", "send_path_middleware", "post_send_analytics", "batch_feedback", "direct_api"]},
                "campaign_id": {"type": "string"},
                "journey_id": {"type": "string"},
                "step_id": {"type": "string"},
                "template_id": {"type": "string"},
                "template_version": {"type": "string"},
                "locale": {"type": "string"},
                "headers": {"type": "object"},
                "consent_context": {"type": "object"},
                "delivery_context": {"type": "object"},
                "recipient_context": {"type": "object"},
                "personalization_context": {"type": "object"},
                "assets": {"type": "object"},
                "message": {"type": "object"},
            },
        },
        "EmailAnalyzeResponse": {
            "type": "object",
            "required": ["api_version", "request_id", "content_hash", "policy", "model", "scores", "findings", "routes"],
            "properties": {
                "api_version": {"type": "string"},
                "request_id": {"type": "string"},
                "content_hash": {"type": "string"},
                "created_at": {"type": "string"},
                "policy": {
                    "type": "object",
                    "required": ["bundle_id", "bundle_version", "gate", "rule_packs"],
                    "properties": {
                        "bundle_id": {"type": "string"},
                        "bundle_version": {"type": "string"},
                        "gate": gate,
                        "rule_packs": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "model": {"type": "object"},
                "input": {"type": "object"},
                "stats": {"type": "object"},
                "scores": {"type": "object", "additionalProperties": {"type": "integer"}},
                "findings": {"type": "array", "items": finding},
                "routes": {"type": "array", "items": {"type": "object"}},
                "predictions": {"type": "object"},
                "privacy": {"type": "object"},
            },
        },
        "Finding": finding,
        "Gate": gate,
        "FieldMapping": mapping,
        "FieldMappingSaveRequest": {
            "type": "object",
            "properties": {
                "workspace_id": {"type": "string"},
                "save_draft": {"type": "boolean"},
                "mapping": mapping,
            },
        },
        "FieldMappingValidationResponse": {
            "type": "object",
            "required": ["validation"],
            "properties": {
                "api_version": {"type": "string"},
                "contract_version": {"type": "string"},
                "provider": {"type": "string"},
                "manifest": {"type": "object"},
                "validation": {"type": "object"},
                "mapping_template": mapping,
            },
        },
        "FieldMappingSaveResponse": {
            "type": "object",
            "properties": {
                "api_version": {"type": "string"},
                "contract_version": {"type": "string"},
                "provider": {"type": "string"},
                "workspace_id": {"type": "string"},
                "field_mapping": {"type": "object"},
            },
        },
        "IntegrationManifestsResponse": {
            "type": "object",
            "properties": {
                "api_version": {"type": "string"},
                "contract_version": {"type": "string"},
                "manifests": {"type": "array", "items": {"type": "object"}},
                "field_mappings": {"type": "array", "items": {"type": "object"}},
            },
        },
        "IntegrationManifestResponse": {
            "type": "object",
            "properties": {
                "manifest": {"type": "object"},
                "mapping_template": mapping,
                "saved_mapping": {"type": ["object", "null"]},
            },
        },
        "SandboxFlowsResponse": {"type": "object"},
        "HubSpotPlatformConfigResponse": {"type": "object"},
        "HubSpotCrmCardResponse": {"type": "object"},
        "HubSpotCrmCardAnalyzeRequest": {"type": "object"},
        "HubSpotCrmCardAnalyzeResponse": {"type": "object"},
        "HubSpotWorkflowRequest": {"type": "object"},
        "HubSpotWorkflowResponse": {"type": "object"},
        "SalesforceJourneyRequest": {"type": "object"},
        "SalesforceJourneyResponse": {"type": "object"},
        "SendMiddlewareRequest": {"type": "object"},
        "SendMiddlewareResponse": {"type": "object"},
        "EnterpriseAdapterRequest": {"type": "object"},
        "EnterpriseAdapterResponse": {"type": "object"},
        "WarehouseFeedbackRequest": {"type": "object"},
        "AdapterSimulatorRequest": {"type": "object"},
        "TemplateRenderTestRequest": {"type": "object"},
        "TemplateRenderTestResponse": {"type": "object"},
        "PostSendWebhookRequest": {"type": "object"},
        "PostSendWebhookResponse": {"type": "object"},
        "SampleImportRequest": {"type": "object"},
        "SampleImportResponse": {"type": "object"},
        "GovernanceDashboardResponse": {"type": "object"},
        "GovernancePolicy": governance_policy,
        "GovernancePolicySaveRequest": {
            "type": "object",
            "properties": {
                "workspace_id": {"type": "string"},
                "policy": governance_policy,
            },
        },
        "GovernancePolicyResponse": {
            "type": "object",
            "properties": {
                "api_version": {"type": "string"},
                "workspace_id": {"type": "string"},
                "policy": governance_policy,
            },
        },
        "InstallKitResponse": {"type": "object"},
        "ErrorResponse": {"type": "object", "properties": {"error": {"type": "string"}}},
    }


def build_install_kit(base_url: str) -> dict[str, Any]:
    public_url = (base_url or "http://127.0.0.1:5000").rstrip("/")
    endpoint_paths = [
        "/v1/email/analyze",
        "/v1/integrations/manifests",
        "/v1/integrations/{provider}/manifest",
        "/v1/integrations/{provider}/field-mapping/validate",
        "/v1/integrations/{provider}/field-mapping",
        "/v1/integrations/sandbox-flows",
        "/v1/integrations/hubspot/platform-config",
        "/v1/integrations/hubspot/crm-card",
        "/v1/integrations/hubspot/crm-card/analyze-email",
        "/v1/integrations/hubspot/workflow-actions/analyze-email",
        "/v1/integrations/salesforce/journey-builder/activity",
        "/v1/integrations/sendgrid-ses/middleware",
        "/v1/integrations/braze/canvas-gate",
        "/v1/integrations/marketo/smart-campaign-gate",
        "/v1/integrations/iterable/workflow-gate",
        "/v1/integrations/warehouse/feedback-import",
        "/v1/integrations/simulate",
        "/v1/templates/render-test",
        "/v1/webhooks/post-send",
        "/v1/samples/import",
        "/v1/governance/dashboard",
        "/v1/governance/export",
        "/v1/governance/policy",
        "/v1/openapi.json",
    ]
    return {
        "api_version": API_VERSION,
        "contract_version": CONTRACT_VERSION,
        "policy_bundle_version": POLICY_BUNDLE_VERSION,
        "non_generative": True,
        "openapi_url": f"{public_url}/v1/openapi.json",
        "documentation": {
            "repository_path": "docs/v1-email-api.md",
            "openapi_url": f"{public_url}/v1/openapi.json",
        },
        "authentication": {
            "browser": "X-CSRF-Token from /api/session",
            "server_to_server": "Set TEXTTRAITS_API_KEY_SHA256 or TEXTTRAITS_API_KEY_HASHES and send X-TextTraits-Api-Key.",
            "workspace_reads": "Governance dashboards, exports, policies, saved mappings, and manifest mapping views require an authenticated browser session in production or a scoped API key.",
            "webhooks": "Set TEXTTRAITS_WEBHOOK_SECRET and send X-TextTraits-Signature plus X-TextTraits-Timestamp when timestamp enforcement is enabled.",
        },
        "endpoints": [{"path": path, "url": f"{public_url}{path.replace('{provider}', 'hubspot')}"} for path in endpoint_paths],
        "provider_manifests": all_manifests(),
        "sample_payloads": [
            "samples/v1-email-analyze-request.json",
            "samples/hubspot-crm-card-analyze-request.json",
            "samples/hubspot-workflow-action-request.json",
            "samples/hubspot-field-mapping-request.json",
            "samples/post-send-webhook-event.json",
            "samples/governance-policy-request.json",
            "samples/enterprise-context-analyze-request.json",
            "samples/adapter-simulator-request.json",
            "samples/warehouse-feedback-import-request.json",
        ],
        "integration_sequence": [
            "Read /v1/openapi.json and provider manifests.",
            "Validate and save field mappings for the workspace.",
            "Render-test personalization tokens with sample recipient context before routing a template.",
            "Route existing email content through /v1/email/analyze or a provider adapter.",
            "Persist request_id and content_hash with downstream send records.",
            "Set workspace governance policy controls for thresholds, retention, dedupe, and storage mode.",
            "Send provider outcomes to /v1/webhooks/post-send for governance joins.",
            "Export normalized analyses, findings, outcomes, or joins for internal governance reporting.",
            "Review /v1/governance/dashboard for quality, routing, and delivery patterns.",
        ],
    }
