from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from typing import Any
from urllib.parse import unquote


HUBSPOT_SIGNATURE_HEADER = "X-HubSpot-Signature-v3"
HUBSPOT_TIMESTAMP_HEADER = "X-HubSpot-Request-Timestamp"
DEFAULT_SIGNATURE_TOLERANCE_SECONDS = 300


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def signature_tolerance_seconds() -> int:
    raw = os.getenv("HUBSPOT_SIGNATURE_TOLERANCE_SECONDS", "").strip()
    try:
        return max(30, int(raw)) if raw else DEFAULT_SIGNATURE_TOLERANCE_SECONDS
    except ValueError:
        return DEFAULT_SIGNATURE_TOLERANCE_SECONDS


def hubspot_client_secret() -> str:
    return os.getenv("HUBSPOT_CLIENT_SECRET", "").strip()


def canonical_request_url(url: str) -> str:
    return unquote(str(url or ""))


def calculate_hubspot_signature_v3(method: str, url: str, body: str | bytes, timestamp_ms: str | int, client_secret: str) -> str:
    body_text = body.decode("utf-8") if isinstance(body, bytes) else str(body or "")
    source = f"{method.upper()}{canonical_request_url(url)}{body_text}{timestamp_ms}"
    digest = hmac.new(client_secret.encode("utf-8"), source.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def validate_hubspot_signature_v3(
    *,
    method: str,
    url: str,
    body: str | bytes,
    headers: Any,
    client_secret: str | None = None,
    now_ms: int | None = None,
) -> dict[str, Any]:
    secret = (client_secret or hubspot_client_secret()).strip()
    required = env_flag("HUBSPOT_REQUIRE_SIGNATURE", False)
    if not secret:
        return {
            "configured": False,
            "required": required,
            "valid": False,
            "status": "not_configured",
            "message": "Set HUBSPOT_CLIENT_SECRET to validate signed HubSpot platform requests.",
        }

    supplied = str(headers.get(HUBSPOT_SIGNATURE_HEADER) or headers.get("X-HubSpot-Signature-V3") or "").strip()
    timestamp = str(headers.get(HUBSPOT_TIMESTAMP_HEADER) or "").strip()
    if not supplied or not timestamp:
        return {
            "configured": True,
            "required": required,
            "valid": False,
            "status": "missing_signature",
            "message": "HubSpot signature or timestamp header is missing.",
        }
    try:
        request_time = int(timestamp)
    except ValueError:
        return {
            "configured": True,
            "required": required,
            "valid": False,
            "status": "invalid_timestamp",
            "message": "HubSpot timestamp header is not an integer millisecond value.",
        }

    current_time = now_ms if now_ms is not None else int(time.time() * 1000)
    tolerance_ms = signature_tolerance_seconds() * 1000
    if abs(current_time - request_time) > tolerance_ms:
        return {
            "configured": True,
            "required": required,
            "valid": False,
            "status": "timestamp_out_of_range",
            "message": "HubSpot request timestamp is outside the configured replay tolerance.",
        }

    expected = calculate_hubspot_signature_v3(method, url, body, timestamp, secret)
    valid = hmac.compare_digest(supplied, expected)
    return {
        "configured": True,
        "required": required,
        "valid": valid,
        "status": "valid" if valid else "signature_mismatch",
        "message": "HubSpot request signature validated." if valid else "HubSpot request signature did not match.",
    }


def flask_hubspot_signature_status(flask_request: Any) -> dict[str, Any]:
    return validate_hubspot_signature_v3(
        method=flask_request.method,
        url=flask_request.url,
        body=flask_request.get_data(cache=True) or b"",
        headers=flask_request.headers,
    )


def build_hubspot_platform_config(public_base_url: str) -> dict[str, Any]:
    base = (public_base_url or "http://127.0.0.1:5000").rstrip("/")
    return {
        "provider": "hubspot",
        "name": "TextTraits HubSpot Platform App",
        "mode": "developer_platform_scaffold",
        "requires_https": True,
        "hubspot_docs": {
            "quickstart": "https://developers.hubspot.com/docs/getting-started/introduction",
            "app_configuration": "https://developers.hubspot.com/docs/apps/developer-platform/build-apps/app-configuration",
            "app_cards": "https://developers.hubspot.com/docs/apps/developer-platform/add-features/ui-extensions/extension-points/app-cards/overview",
            "custom_workflow_actions": "https://developers.hubspot.com/docs/apps/developer-platform/add-features/custom-workflow-actions",
            "request_validation": "https://developers.hubspot.com/docs/apps/developer-platform/build-apps/authentication/request-validation",
        },
        "required_env": [
            "TEXTTRAITS_PUBLIC_BASE_URL",
            "HUBSPOT_CLIENT_ID",
            "HUBSPOT_CLIENT_SECRET",
        ],
        "optional_env": [
            "HUBSPOT_REQUIRE_SIGNATURE",
            "HUBSPOT_SIGNATURE_TOLERANCE_SECONDS",
            "TEXTTRAITS_API_KEY_SHA256",
            "TEXTTRAITS_API_KEY_SCOPES",
        ],
        "oauth": {
            "redirect_url": f"{base}/api/integrations/hubspot/oauth/callback",
            "start_url": f"{base}/api/integrations/hubspot/oauth/start",
            "scopes": ["crm.objects.contacts.read", "crm.objects.companies.read", "crm.objects.deals.read"],
            "token_storage_default": "metadata_only",
        },
        "extension_points": {
            "crm_app_card": {
                "endpoint": f"{base}/v1/integrations/hubspot/crm-card",
                "analyze_endpoint": f"{base}/v1/integrations/hubspot/crm-card/analyze-email",
                "supported_objects": ["contacts", "companies", "deals"],
                "purpose": "Let a HubSpot user invoke TextTraits on an existing draft or workflow email context from a CRM record.",
            },
            "custom_workflow_action": {
                "endpoint": f"{base}/v1/integrations/hubspot/workflow-actions/analyze-email",
                "purpose": "Score an existing workflow email and return writeback fields for branching or review routing.",
            },
        },
        "writeback_fields": {
            "texttraits_score": "Integer score from 0 to 100.",
            "texttraits_gate": "ready, needs_review, or blocked.",
            "texttraits_route": "Suggested queue or branch.",
            "texttraits_request_id": "Stable TextTraits request ID for audit joins.",
            "texttraits_content_hash": "SHA-256 hash of analyzed subject/body pair.",
        },
        "local_project": {
            "path": "hubspot-platform/",
            "render_command": "python scripts/render_hubspot_project.py --base-url https://your-public-texttraits-domain.example",
            "credential_command": "python scripts/setup_hubspot_env.py",
        },
        "security": {
            "signature_header": HUBSPOT_SIGNATURE_HEADER,
            "timestamp_header": HUBSPOT_TIMESTAMP_HEADER,
            "signature_configured": bool(hubspot_client_secret()),
            "signature_required": env_flag("HUBSPOT_REQUIRE_SIGNATURE", False),
            "signature_tolerance_seconds": signature_tolerance_seconds(),
        },
    }


def hubspot_crm_object_context(query_args: Any) -> dict[str, str]:
    keys = (
        "portalId",
        "portal_id",
        "objectId",
        "object_id",
        "objectType",
        "object_type",
        "associatedObjectId",
        "associatedObjectType",
        "userId",
        "user_id",
    )
    context: dict[str, str] = {}
    for key in keys:
        value = query_args.get(key)
        if value not in (None, ""):
            context[key] = str(value)[:200]
    return context


def build_hubspot_crm_card(query_args: Any, public_base_url: str, workspace_id: str, signature_status: dict[str, Any]) -> dict[str, Any]:
    config = build_hubspot_platform_config(public_base_url)
    return {
        "provider": "hubspot",
        "card": {
            "title": "TextTraits email fit",
            "subtitle": "Score an existing outreach or marketing email before it enters a workflow.",
            "status": "ready_for_signed_platform_callback" if signature_status.get("valid") else "sandbox_ready",
        },
        "workspace_id": workspace_id,
        "hubspot_context": hubspot_crm_object_context(query_args),
        "signature": signature_status,
        "primary_action": {
            "label": "Analyze draft email",
            "method": "POST",
            "endpoint": config["extension_points"]["crm_app_card"]["analyze_endpoint"],
            "inputs": ["subject", "body", "audience", "intent"],
        },
        "fields": [
            {"label": "Score", "value": "Run analysis", "type": "score"},
            {"label": "Gate", "value": "Run analysis", "type": "status"},
            {"label": "Route", "value": "Run analysis", "type": "route"},
        ],
        "limitations": [
            "TextTraits evaluates existing text; it does not generate or send email from HubSpot.",
            "Results are decision support and should be calibrated on approved workspace samples before live routing.",
            "Live HubSpot callbacks should use signed request validation in production.",
        ],
    }
