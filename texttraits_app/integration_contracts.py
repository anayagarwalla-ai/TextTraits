from __future__ import annotations

from copy import deepcopy
from typing import Any


CONTRACT_VERSION = "2026.05.25"

PROVIDER_ALIASES = {
    "hubspot": "hubspot",
    "hubspot_workflow": "hubspot",
    "hubspot_workflow_action": "hubspot",
    "salesforce": "salesforce",
    "salesforce_journey": "salesforce",
    "salesforce_journey_builder": "salesforce",
    "sendgrid": "sendgrid_ses",
    "ses": "sendgrid_ses",
    "sendgrid_ses": "sendgrid_ses",
    "sendgrid-ses": "sendgrid_ses",
    "middleware": "sendgrid_ses",
    "braze": "braze",
    "braze_canvas": "braze",
    "currents": "braze",
    "marketo": "marketo",
    "marketo_smart_campaign": "marketo",
    "iterable": "iterable",
    "iterable_workflow": "iterable",
    "warehouse": "warehouse",
    "warehouse_feedback": "warehouse",
    "cdp": "warehouse",
    "post_send_webhook": "post_send_webhook",
    "webhook": "post_send_webhook",
}

BASE_OUTPUTS = {
    "request_id": {"type": "string", "description": "Stable TextTraits request identifier."},
    "content_hash": {"type": "string", "description": "SHA-256 hash of the analyzed subject/body pair."},
    "score": {"type": "integer", "description": "Overall policy score from 0 to 100."},
    "gate_status": {"type": "string", "description": "ready, needs_review, or blocked."},
    "send_ready": {"type": "boolean", "description": "Whether downstream send systems can continue automatically."},
    "route": {"type": "string", "description": "Approved route or review queue for the message."},
    "highest_severity": {"type": "string", "description": "Highest finding severity for routing."},
}

MANIFESTS: dict[str, dict[str, Any]] = {
    "hubspot": {
        "provider": "hubspot",
        "name": "HubSpot Workflow Action",
        "version": CONTRACT_VERSION,
        "entrypoint": "/v1/integrations/hubspot/workflow-actions/analyze-email",
        "install_surface": "HubSpot workflow custom action",
        "auth": "OAuth app or private app proxy",
        "required_inputs": {
            "subject": {"type": "string", "hubspot_property": "email_subject", "description": "Subject or workflow email title."},
            "body": {"type": "string", "hubspot_property": "email_body", "description": "Existing email body to score."},
        },
        "optional_inputs": {
            "audience": {"type": "string", "hubspot_property": "lifecyclestage", "description": "Recipient segment or object context."},
            "intent": {"type": "string", "hubspot_property": "workflow_name", "description": "Campaign, follow-up, renewal, or internal handoff intent."},
            "recipient_id": {"type": "string", "hubspot_property": "hs_object_id", "description": "Contact/company/deal identifier."},
            "message_id": {"type": "string", "hubspot_property": "email_campaign_id", "description": "Provider message identifier for event joins."},
        },
        "outputs": {
            **BASE_OUTPUTS,
            "findings_count": {"type": "integer", "description": "Number of policy findings."},
        },
        "recommended_writeback": {
            "texttraits_score": "score",
            "texttraits_gate": "gate_status",
            "texttraits_route": "route",
            "texttraits_request_id": "request_id",
            "texttraits_content_hash": "content_hash",
        },
    },
    "salesforce": {
        "provider": "salesforce",
        "name": "Salesforce Journey Builder Activity",
        "version": CONTRACT_VERSION,
        "entrypoint": "/v1/integrations/salesforce/journey-builder/activity",
        "install_surface": "Journey Builder custom activity",
        "auth": "Installed package / connected app",
        "required_inputs": {
            "subject": {"type": "string", "journey_attribute": "EmailSubject", "description": "Existing journey email subject."},
            "body": {"type": "string", "journey_attribute": "EmailBody", "description": "Existing journey email body."},
        },
        "optional_inputs": {
            "audience": {"type": "string", "journey_attribute": "ContactType", "description": "Subscriber or segment context."},
            "intent": {"type": "string", "journey_attribute": "JourneyName", "description": "Journey or activity purpose."},
            "recipient_id": {"type": "string", "journey_attribute": "ContactKey", "description": "Contact key for governance joins."},
            "message_id": {"type": "string", "journey_attribute": "ActivityInstanceId", "description": "Message/activity identifier."},
        },
        "outputs": {
            **BASE_OUTPUTS,
            "branch_result": {"type": "string", "description": "send or review branch output."},
        },
        "recommended_writeback": {
            "TextTraits_Request_ID__c": "request_id",
            "TextTraits_Score__c": "score",
            "TextTraits_Gate__c": "gate_status",
            "TextTraits_Route__c": "route",
        },
    },
    "sendgrid_ses": {
        "provider": "sendgrid_ses",
        "name": "SendGrid / Amazon SES Middleware",
        "version": CONTRACT_VERSION,
        "entrypoint": "/v1/integrations/sendgrid-ses/middleware",
        "install_surface": "Pre-send API proxy or middleware",
        "auth": "Server-to-server API key",
        "required_inputs": {
            "subject": {"type": "string", "path": "message.subject", "description": "Outgoing subject."},
            "body": {"type": "string", "path": "message.text|message.html", "description": "Outgoing body before provider handoff."},
        },
        "optional_inputs": {
            "audience": {"type": "string", "path": "message.audience", "description": "Campaign or transactional recipient context."},
            "intent": {"type": "string", "path": "message.intent", "description": "Transactional, nurture, renewal, or campaign intent."},
            "assets.links": {"type": "array", "path": "message.assets.links", "description": "Links detected by the sending system."},
            "assets.image_count": {"type": "integer", "path": "message.assets.image_count", "description": "Image count for deliverability checks."},
        },
        "outputs": {
            **BASE_OUTPUTS,
            "provider_action": {"type": "string", "description": "forward_to_provider or hold_for_review."},
        },
        "recommended_writeback": {
            "X-TextTraits-Request-ID": "request_id",
            "X-TextTraits-Policy-Version": "policy_bundle_version",
            "X-TextTraits-Gate": "gate_status",
        },
    },
    "braze": {
        "provider": "braze",
        "name": "Braze Canvas / Currents Loop",
        "version": CONTRACT_VERSION,
        "entrypoint": "/v1/integrations/braze/canvas-gate",
        "install_surface": "Canvas webhook step plus Currents event ingestion",
        "auth": "Server-to-server API key or Braze webhook signature",
        "required_inputs": {
            "subject": {"type": "string", "path": "message.subject|canvas_step.subject", "description": "Canvas email step subject."},
            "body": {"type": "string", "path": "message.body|message.html|canvas_step.body", "description": "Email template body before send."},
        },
        "optional_inputs": {
            "campaign_id": {"type": "string", "path": "campaign_id|canvas_id", "description": "Campaign or Canvas identifier."},
            "journey_id": {"type": "string", "path": "canvas_id|journey_id", "description": "Canvas or journey identifier."},
            "template_id": {"type": "string", "path": "message.template_id|template_id", "description": "Template id for governance joins."},
            "personalization_context": {"type": "object", "path": "personalization_context", "description": "Sample Liquid render context."},
        },
        "outputs": {**BASE_OUTPUTS, "currents_join_key": {"type": "string", "description": "Request id for Currents event joins."}},
        "recommended_writeback": {
            "texttraits_request_id": "request_id",
            "texttraits_gate": "gate_status",
            "texttraits_score": "score",
            "texttraits_route": "route",
        },
    },
    "marketo": {
        "provider": "marketo",
        "name": "Marketo Smart Campaign Gate",
        "version": CONTRACT_VERSION,
        "entrypoint": "/v1/integrations/marketo/smart-campaign-gate",
        "install_surface": "Program asset review gate",
        "auth": "Server-to-server API key",
        "required_inputs": {
            "subject": {"type": "string", "path": "asset.subject|subject", "description": "Email asset subject."},
            "body": {"type": "string", "path": "asset.html|asset.text|body", "description": "Email asset content."},
        },
        "optional_inputs": {
            "campaign_id": {"type": "string", "path": "program_id|campaign_id", "description": "Program or smart campaign id."},
            "template_id": {"type": "string", "path": "asset.id|template_id", "description": "Marketo email asset id."},
            "locale": {"type": "string", "path": "locale", "description": "Locale for template review."},
        },
        "outputs": {**BASE_OUTPUTS, "review_status": {"type": "string", "description": "approve, warn, or review."}},
        "recommended_writeback": {
            "texttraits_request_id": "request_id",
            "texttraits_score": "score",
            "texttraits_gate": "gate_status",
            "texttraits_route": "route",
        },
    },
    "iterable": {
        "provider": "iterable",
        "name": "Iterable Workflow Gate",
        "version": CONTRACT_VERSION,
        "entrypoint": "/v1/integrations/iterable/workflow-gate",
        "install_surface": "Workflow webhook or template approval step",
        "auth": "Server-to-server API key",
        "required_inputs": {
            "subject": {"type": "string", "path": "message.subject|subject", "description": "Workflow message subject."},
            "body": {"type": "string", "path": "message.body|message.html|body", "description": "Handlebars template body."},
        },
        "optional_inputs": {
            "campaign_id": {"type": "string", "path": "campaign_id", "description": "Iterable campaign id."},
            "journey_id": {"type": "string", "path": "workflow_id|journey_id", "description": "Workflow id."},
            "personalization_context": {"type": "object", "path": "personalization_context", "description": "Sample Handlebars render context."},
        },
        "outputs": {**BASE_OUTPUTS, "event_stream_join_key": {"type": "string", "description": "Request id for event stream joins."}},
        "recommended_writeback": {
            "texttraitsRequestId": "request_id",
            "texttraitsGate": "gate_status",
            "texttraitsScore": "score",
            "texttraitsRoute": "route",
        },
    },
    "warehouse": {
        "provider": "warehouse",
        "name": "Warehouse Feedback Import",
        "version": CONTRACT_VERSION,
        "entrypoint": "/v1/integrations/warehouse/feedback-import",
        "install_surface": "Batch worker or reverse ETL job",
        "auth": "Server-to-server API key",
        "required_inputs": {
            "subject": {"type": "string", "path": "subject", "description": "Campaign/template subject column."},
            "body": {"type": "string", "path": "body|content|html", "description": "Campaign/template content column."},
        },
        "optional_inputs": {
            "campaign_id": {"type": "string", "path": "campaign_id", "description": "Campaign id."},
            "template_id": {"type": "string", "path": "template_id", "description": "Template id."},
            "event_type": {"type": "string", "path": "event_type", "description": "Outcome event type when importing feedback rows."},
        },
        "outputs": {**BASE_OUTPUTS, "normalized_findings_table": {"type": "string", "description": "Normalized findings export surface."}},
        "recommended_writeback": {
            "texttraits_request_id": "request_id",
            "texttraits_content_hash": "content_hash",
            "texttraits_gate": "gate_status",
            "texttraits_score": "score",
        },
    },
    "post_send_webhook": {
        "provider": "post_send_webhook",
        "name": "Post-send Webhook Ingestion",
        "version": CONTRACT_VERSION,
        "entrypoint": "/v1/webhooks/post-send",
        "install_surface": "Provider webhook destination",
        "auth": "Provider webhook signature or server-to-server API key",
        "required_inputs": {
            "provider": {"type": "string", "path": "provider", "description": "sendgrid, ses, hubspot, salesforce, or another provider id."},
            "event_type": {"type": "string", "path": "event_type|event", "description": "delivered, opened, clicked, bounced, complained, etc."},
            "dedupe_key": {"type": "string", "path": "event_id|id|message_id", "description": "Stable provider event id for retry dedupe."},
        },
        "optional_inputs": {
            "request_id": {"type": "string", "path": "request_id|texttraits_request_id", "description": "TextTraits analysis request id."},
            "content_hash": {"type": "string", "path": "content_hash", "description": "TextTraits content hash for joins."},
            "delivery_status": {"type": "string", "path": "delivery_status|status", "description": "Provider outcome status."},
        },
        "outputs": {
            "accepted": {"type": "boolean", "description": "Whether the event was accepted."},
            "duplicate": {"type": "boolean", "description": "Whether the event was a retry/duplicate."},
            "dedupe_key": {"type": "string", "description": "Stored dedupe key."},
            "seen_count": {"type": "integer", "description": "Number of deliveries seen for this dedupe key."},
        },
        "recommended_writeback": {},
    },
}


def normalize_provider(provider: str) -> str:
    clean = str(provider or "").strip().lower().replace(" ", "_")
    return PROVIDER_ALIASES.get(clean, clean)


def provider_manifest(provider: str) -> dict[str, Any] | None:
    key = normalize_provider(provider)
    manifest = MANIFESTS.get(key)
    return deepcopy(manifest) if manifest else None


def all_manifests() -> list[dict[str, Any]]:
    return [deepcopy(manifest) for manifest in MANIFESTS.values()]


def mapping_template(provider: str) -> dict[str, Any]:
    manifest = provider_manifest(provider)
    if not manifest:
        return {}
    inputs = {
        key: field.get("hubspot_property") or field.get("journey_attribute") or field.get("path") or key
        for key, field in manifest["required_inputs"].items()
    }
    outputs = dict(manifest.get("recommended_writeback") or {})
    return {"inputs": inputs, "outputs": outputs}


def validate_field_mapping(provider: str, mapping: dict[str, Any] | None) -> dict[str, Any]:
    manifest = provider_manifest(provider)
    if not manifest:
        return {
            "provider": normalize_provider(provider),
            "status": "unsupported_provider",
            "valid": False,
            "missing_inputs": [],
            "missing_outputs": [],
            "warnings": ["Unsupported provider."],
            "normalized_mapping": {},
            "manifest_version": CONTRACT_VERSION,
        }
    clean_mapping = mapping if isinstance(mapping, dict) else {}
    inputs = clean_mapping.get("inputs") if isinstance(clean_mapping.get("inputs"), dict) else {}
    outputs = clean_mapping.get("outputs") if isinstance(clean_mapping.get("outputs"), dict) else {}
    required_inputs = set(manifest.get("required_inputs", {}).keys())
    recommended_outputs = set((manifest.get("recommended_writeback") or {}).keys())
    if manifest["provider"] == "post_send_webhook":
        recommended_outputs = set()
    missing_inputs = sorted(key for key in required_inputs if not str(inputs.get(key) or "").strip())
    missing_outputs = sorted(key for key in recommended_outputs if not str(outputs.get(key) or "").strip())
    warnings: list[str] = []
    optional_inputs = set(manifest.get("optional_inputs", {}).keys())
    unknown_inputs = sorted(set(inputs.keys()) - required_inputs - optional_inputs)
    if unknown_inputs:
        warnings.append(f"Unknown input mappings will be preserved but ignored by default: {', '.join(unknown_inputs[:6])}.")
    if manifest["provider"] == "post_send_webhook" and not str(inputs.get("dedupe_key") or "").strip():
        warnings.append("Webhook mappings should include a stable dedupe_key source to avoid duplicate event counts.")
    status = "ready" if not missing_inputs and not missing_outputs else "needs_mapping"
    return {
        "provider": manifest["provider"],
        "status": status,
        "valid": status == "ready",
        "missing_inputs": missing_inputs,
        "missing_outputs": missing_outputs,
        "warnings": warnings,
        "normalized_mapping": {
            "inputs": {str(key): str(value).strip() for key, value in inputs.items() if str(value).strip()},
            "outputs": {str(key): str(value).strip() for key, value in outputs.items() if str(value).strip()},
        },
        "manifest_version": manifest["version"],
        "required_inputs": sorted(required_inputs),
        "recommended_outputs": sorted(recommended_outputs),
    }
