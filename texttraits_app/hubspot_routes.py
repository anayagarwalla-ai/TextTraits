from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import Blueprint, request


AnalysisResponse = Callable[[dict[str, Any], str], Any]
PayloadNormalizer = Callable[[dict[str, Any], str], dict[str, Any]]
RateLimiter = Callable[[int], Callable]
ExtensionResponse = Callable[[dict[str, Any]], Any]


@dataclass(frozen=True)
class HubSpotAnalysisRouteDependencies:
    analysis_response: AnalysisResponse
    normalize_asset_payload: PayloadNormalizer
    normalize_marketing_email_payload: PayloadNormalizer
    rate_limited: RateLimiter


@dataclass(frozen=True)
class HubSpotExtensionRouteDependencies:
    home_response: ExtensionResponse
    settings_response: ExtensionResponse
    rate_limited: RateLimiter


def create_hubspot_analysis_blueprint(deps: HubSpotAnalysisRouteDependencies) -> Blueprint:
    blueprint = Blueprint("hubspot_analysis", __name__)

    @blueprint.post("/v1/integrations/hubspot/crm-card/analyze-email")
    @deps.rate_limited(60)
    def crm_card_analyze_email():
        return deps.analysis_response(request.get_json(silent=True) or {}, "hubspot_crm_card")

    @blueprint.post("/v1/integrations/hubspot/workflow-actions/analyze-email")
    @deps.rate_limited(60)
    def workflow_action_analyze_email():
        return deps.analysis_response(request.get_json(silent=True) or {}, "hubspot_workflow_action")

    @blueprint.post("/v1/integrations/hubspot/workflow-actions/analyze-asset-copy")
    @deps.rate_limited(60)
    def workflow_action_analyze_asset_copy():
        payload = request.get_json(silent=True) or {}
        normalized = deps.normalize_asset_payload(payload, "asset_copy_workflow_gate")
        return deps.analysis_response(normalized, "hubspot_asset_copy_workflow_action")

    @blueprint.post("/v1/integrations/hubspot/marketing-emails/analyze")
    @deps.rate_limited(60)
    def marketing_email_analyze():
        payload = request.get_json(silent=True) or {}
        normalized = deps.normalize_marketing_email_payload(payload, "marketing_email_preflight")
        return deps.analysis_response(normalized, "hubspot_marketing_email_preflight")

    @blueprint.post("/v1/integrations/hubspot/assets/analyze")
    @deps.rate_limited(60)
    def asset_analyze():
        payload = request.get_json(silent=True) or {}
        normalized = deps.normalize_asset_payload(payload, "asset_copy_preflight")
        return deps.analysis_response(normalized, "hubspot_asset_copy_preflight")

    return blueprint


def create_hubspot_extension_blueprint(deps: HubSpotExtensionRouteDependencies) -> Blueprint:
    blueprint = Blueprint("hubspot_extension", __name__)

    @blueprint.post("/v1/integrations/hubspot/app-home/bootstrap")
    @deps.rate_limited(60)
    def app_home_bootstrap():
        return deps.home_response(request.get_json(silent=True) or {})

    @blueprint.post("/v1/integrations/hubspot/settings/bootstrap")
    @deps.rate_limited(60)
    def settings_bootstrap():
        return deps.settings_response(request.get_json(silent=True) or {})

    return blueprint
