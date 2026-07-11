from __future__ import annotations

from runtime_config import env_int


HUBSPOT_LATENCY_BUDGETS_MS = {
    "analysis": env_int("TEXTTRAITS_HUBSPOT_BUDGET_ANALYSIS_MS", 750, minimum=50, maximum=30000),
    "workflow": env_int("TEXTTRAITS_HUBSPOT_BUDGET_WORKFLOW_MS", 2000, minimum=100, maximum=60000),
    "sync": env_int("TEXTTRAITS_HUBSPOT_BUDGET_SYNC_MS", 5000, minimum=250, maximum=120000),
    "campaign": env_int("TEXTTRAITS_HUBSPOT_BUDGET_CAMPAIGN_MS", 10000, minimum=500, maximum=180000),
    "batch": env_int("TEXTTRAITS_HUBSPOT_BUDGET_BATCH_MS", 15000, minimum=500, maximum=300000),
    "bootstrap": env_int("TEXTTRAITS_HUBSPOT_BUDGET_BOOTSTRAP_MS", 2500, minimum=100, maximum=60000),
    "admin": env_int("TEXTTRAITS_HUBSPOT_BUDGET_ADMIN_MS", 3000, minimum=100, maximum=60000),
    "default": env_int("TEXTTRAITS_HUBSPOT_BUDGET_DEFAULT_MS", 5000, minimum=100, maximum=120000),
}


def hubspot_latency_class(path: str) -> str:
    clean = str(path or "")
    if "/app-home/bootstrap" in clean or "/settings/bootstrap" in clean or "/home-bootstrap" in clean or "/settings-bootstrap" in clean:
        return "bootstrap"
    if "/bulk/" in clean:
        return "batch"
    if "/campaigns/" in clean or "/review-campaign-assets" in clean:
        return "campaign"
    if clean.endswith("/analyze-and-sync"):
        return "sync"
    if "/workflow-actions/" in clean:
        return "workflow"
    if clean.endswith("/analyze-email") or clean.endswith("/assets/analyze") or clean.endswith("/marketing-emails/analyze"):
        return "analysis"
    if clean.startswith("/api/enterprise/hubspot/"):
        return "admin"
    return "default"


def hubspot_latency_budget_ms(path: str) -> int:
    return HUBSPOT_LATENCY_BUDGETS_MS[hubspot_latency_class(path)]
