from __future__ import annotations

import hashlib
import base64
import csv
import hmac
import io
import json
import logging
import os
import re
import secrets
import time
import urllib.request
from html import escape as html_escape, unescape as html_unescape
from collections import defaultdict, deque
from functools import wraps
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode, urlparse

from flask import Flask, Response, g, jsonify, redirect, render_template, render_template_string, request, session
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from demo_predictor import DemoPredictor
from email_delivery import send_account_email, status as email_status
from env_loader import load_env_file
from integration_adapters import (
    build_authorization_url,
    configured_count as configured_integration_count,
    decoded_state,
    encoded_state,
    exchange_oauth_code,
    get_provider,
    provider_names,
    public_providers,
    slug as provider_slug,
)
from observability import configure_logging, init_error_reporting
from predictor import DEFAULT_MODEL_PATH, TextTraitsPredictor
from storage import (
    authenticate_user,
    check_database,
    create_pending_signup,
    create_password_reset,
    database_backend,
    database_url,
    delete_user,
    export_user_data,
    find_hubspot_email_analysis_for_context,
    get_hubspot_email_analysis,
    get_user_by_id,
    get_workspace,
    get_hubspot_policy_config,
    hubspot_email_dashboard,
    hubspot_retention_summary,
    init_db,
    integrations,
    list_hubspot_normalized_checks,
    list_hubspot_normalized_findings,
    list_hubspot_email_analyses,
    list_hubspot_outcome_events,
    list_hubspot_policy_versions,
    list_hubspot_review_events,
    list_hubspot_review_states,
    log_event,
    needs_email_verification,
    recent_events,
    reset_password,
    save_workspace,
    save_hubspot_email_analysis,
    save_hubspot_outcome_event,
    save_hubspot_policy_config,
    save_hubspot_review_event,
    contains_sensitive_key,
    scrub_payload,
    utc_now,
    upsert_integration,
    upsert_oauth_user,
    user_session_version,
    verify_email_token,
    disconnect_hubspot_portal,
    get_hubspot_portal_connection,
    hubspot_connection_has_scopes,
    get_hubspot_route_owner_map,
    list_hubspot_portal_connections,
    save_hubspot_portal_tokens,
    save_hubspot_route_owner_map,
    token_storage_status,
)
from hubspot_client import HubSpotApiClient, HubSpotClientError, HubSpotNotConnectedError, crm_write_scope

load_env_file()


class MissingPredictor:
    is_demo = False
    metrics = {}
    metadata = {
        "model_path": str(DEFAULT_MODEL_PATH),
        "bundle_format": "unavailable",
        "model_count": 0,
        "targets": [],
        "metrics": {},
        "trained_at": "Unknown",
        "dataset": "Unknown",
    }

    def __init__(self, error: Exception) -> None:
        self.error = error

    def predict(self, text: str) -> dict:
        raise RuntimeError(
            f"Runtime model is unavailable at {DEFAULT_MODEL_PATH}. Run `python scripts/setup_models.py` or enable demo mode."
        ) from self.error


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


ENABLE_DEV_TOOLS = env_flag("ENABLE_DEV_TOOLS", False)
PRODUCTION = os.getenv("TEXTTRAITS_ENV", "").strip().lower() == "production"
ALLOW_DEMO_MODE = env_flag("TEXTTRAITS_ALLOW_DEMO", False)
MAX_TEXT_WORDS = int(os.getenv("TEXTTRAITS_MAX_TEXT_WORDS", "1800"))
MAX_CONTENT_LENGTH = int(os.getenv("TEXTTRAITS_MAX_CONTENT_LENGTH", "1000000"))
MAX_WORKSPACE_BYTES = int(os.getenv("TEXTTRAITS_MAX_WORKSPACE_BYTES", "500000"))
MAX_EVENT_BYTES = int(os.getenv("TEXTTRAITS_MAX_EVENT_BYTES", "12000"))
HUBSPOT_MAX_INGRESS_BYTES = int(os.getenv("TEXTTRAITS_HUBSPOT_MAX_INGRESS_BYTES", "200000"))
HUBSPOT_SIGNATURE_MAX_AGE_SECONDS = int(os.getenv("TEXTTRAITS_HUBSPOT_SIGNATURE_MAX_AGE_SECONDS", "300"))
HUBSPOT_MAX_OUTCOME_EVENTS = int(os.getenv("TEXTTRAITS_HUBSPOT_MAX_OUTCOME_EVENTS", "100"))
HUBSPOT_MAX_BATCH_EMAILS = int(os.getenv("TEXTTRAITS_HUBSPOT_MAX_BATCH_EMAILS", "50"))
RATE_LIMIT_PER_MINUTE = int(os.getenv("TEXTTRAITS_RATE_LIMIT_PER_MINUTE", "80"))
APP_SECRET = os.getenv("TEXTTRAITS_SECRET_KEY", "dev-texttraits-change-me")
PUBLIC_BASE_URL = os.getenv("TEXTTRAITS_PUBLIC_BASE_URL", "http://127.0.0.1:5000")
ALLOW_DEV_ACCOUNT_LINKS = env_flag("TEXTTRAITS_DEV_ACCOUNT_LINKS", False)
GOOGLE_AUTH_CLIENT_ID = (os.getenv("TEXTTRAITS_GOOGLE_AUTH_CLIENT_ID") or os.getenv("GOOGLE_CLIENT_ID") or "").strip()
TRUSTED_PUBLIC_HOSTS = {
    host.strip().lower()
    for host in os.getenv("TEXTTRAITS_ALLOWED_PUBLIC_HOSTS", "").split(",")
    if host.strip()
}
ENTERPRISE_ADMIN_EMAILS = {
    email.strip().lower()
    for email in os.getenv("TEXTTRAITS_ENTERPRISE_ADMIN_EMAILS", "").split(",")
    if email.strip()
}
UNSPECIFIED_IPV4 = ".".join(("0", "0", "0", "0"))
LOCAL_PUBLIC_HOSTS = {"localhost", "127.0.0.1", "::1", UNSPECIFIED_IPV4}
HUBSPOT_PUBLIC_INGRESS_PATHS = {
    "/v1/integrations/hubspot/workflow-actions/analyze-email",
    "/v1/integrations/hubspot/workflow-actions/analyze-asset-copy",
    "/v1/integrations/hubspot/workflow-actions/review-campaign-assets",
    "/v1/integrations/hubspot/crm-card/analyze-email",
    "/v1/integrations/hubspot/marketing-emails/analyze",
    "/v1/integrations/hubspot/assets/analyze",
    "/v1/integrations/hubspot/assets/fetch-and-analyze",
    "/v1/integrations/hubspot/campaigns/analyze",
    "/v1/integrations/hubspot/bulk/analyze-emails",
    "/v1/integrations/hubspot/analyze-and-sync",
    "/v1/integrations/hubspot/app-card/latest",
    "/v1/integrations/hubspot/campaigns/create",
    "/v1/integrations/hubspot/campaigns/update",
    "/v1/integrations/hubspot/campaigns/list",
    "/v1/integrations/hubspot/campaigns/associate-asset",
    "/v1/integrations/hubspot/campaigns/assets",
    "/v1/integrations/hubspot/campaigns/review",
    "/v1/integrations/hubspot/marketing-emails/create-draft",
    "/v1/integrations/hubspot/marketing-emails/update-draft",
    "/v1/integrations/hubspot/marketing-emails/fetch",
    "/v1/integrations/hubspot/marketing-emails/pre-publish-guardrail",
    "/v1/integrations/hubspot/marketing-emails/list",
    "/v1/integrations/hubspot/bulk/import-assets",
    "/v1/integrations/hubspot/salesforce/outcomes/import",
    "/v1/integrations/hubspot/owners/list",
    "/v1/integrations/hubspot/review-routing/config",
    "/v1/integrations/hubspot/tasks/create-review",
    "/v1/integrations/hubspot/properties/writeback",
    "/v1/integrations/hubspot/properties/provision",
    "/v1/integrations/hubspot/analysis-records/create",
    "/v1/integrations/hubspot/analysis-schema/provision",
    "/v1/integrations/hubspot/timeline-events/create",
    "/v1/integrations/hubspot/lists/create",
    "/v1/integrations/hubspot/lists/search",
    "/v1/integrations/hubspot/lists/memberships",
    "/v1/integrations/hubspot/lists/memberships/update",
    "/v1/integrations/hubspot/lists/create-review-segments",
    "/v1/integrations/hubspot/stats/sync",
    "/v1/integrations/hubspot/webhooks/receive",
    "/v1/integrations/hubspot/webhooks/configure",
    "/v1/integrations/hubspot/app-uninstalled",
    "/v1/integrations/hubspot/review-action",
    "/v1/integrations/hubspot/outcomes",
    "/v1/integrations/hubspot/template-test",
}
ALLOWED_WORKSPACE_KEYS = {
    "mode",
    "latestText",
    "recipient",
    "enterpriseContext",
    "savedCampaigns",
    "batchRows",
    "batchErrors",
    "inboxThreads",
    "winnerSamples",
    "personaLibrary",
    "outcomeStats",
    "crmConnections",
    "sequenceSettings",
    "explorerHistory",
    "explorerFolder",
    "explorerWritingGoal",
    "explorerRewriteGoal",
    "batchMapping",
    "exportHistory",
    "reviewQueue",
    "teamComments",
    "versionHistory",
    "feedbackMemory",
    "onboarding",
    "adminSettings",
}
COMMON_PASSWORDS = {
    "password",
    "password123",
    "texttraits",
    "texttraits123",
    "qwerty123",
    "letmein123",
}
WORD_RE = re.compile(r"\b[\w'-]+\b")
SENTENCE_RE = re.compile(r"[.!?]+")
SAFE_HUBSPOT_ID_RE = re.compile(r"[^a-zA-Z0-9_.:-]+")
EMAIL_PLACEHOLDER_RE = re.compile(r"({{\s*[^}]+\s*}}|%\w+%|\[\[\s*[\w.]+\s*\]\])")
EMAIL_GREETING_RE = re.compile(r"\b(?:hi|hello|dear)\s+([A-Z][a-z]{1,30}|{{\s*[^}]+\s*}}|%\w+%|\[\[\s*[\w.]+\s*\]\])")
EMAIL_DATE_RE = re.compile(
    r"\b(?:today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday|next week|this week|"
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|"
    r"sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?|\d{1,2}/\d{1,2}(?:/\d{2,4})?)\b",
    re.IGNORECASE,
)
EMAIL_TIME_RE = re.compile(r"\b\d{1,2}(?::\d{2})?\s?(?:am|pm|a\.m\.|p\.m\.)\b", re.IGNORECASE)
EMAIL_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?%?\b")
EMAIL_PROPER_NOUN_RE = re.compile(r"\b[A-Z][a-z]{2,}\b")
EMAIL_CTA_PATTERNS = {
    "reply": re.compile(r"\b(reply|respond|let me know|tell me)\b", re.IGNORECASE),
    "confirm": re.compile(r"\b(confirm|approve|review|check|verify)\b", re.IGNORECASE),
    "schedule": re.compile(r"\b(schedule|book|meet|call|demo|visit)\b", re.IGNORECASE),
    "send": re.compile(r"\b(send|share|forward|attach|provide)\b", re.IGNORECASE),
    "choose": re.compile(r"\b(choose|select|pick|decide)\b", re.IGNORECASE),
}
EMAIL_VAGUE_PHRASES = (
    "just checking",
    "touch base",
    "circle back",
    "things",
    "stuff",
    "some time",
    "soon",
    "maybe",
    "kind of",
    "sort of",
    "asap",
    "when you get a chance",
)
EMAIL_RISK_PHRASES = (
    "guaranteed",
    "guarantee",
    "risk-free",
    "no risk",
    "act now",
    "urgent",
    "final notice",
    "limited time",
    "100%",
    "no strings attached",
    "free money",
)
EMAIL_GENERIC_SUBJECTS = {
    "checking in",
    "check in",
    "follow up",
    "following up",
    "quick question",
    "touching base",
    "hello",
    "hi",
}
HUBSPOT_HIGH_RISK_PHRASES = {
    "guaranteed",
    "guarantee",
    "100%",
    "guaranteed return",
    "risk-free investment",
    "approval guaranteed",
    "job guaranteed",
    "placement guaranteed",
    "guaranteed placement",
    "guaranteed interview",
    "guaranteed hire",
    "visa guaranteed",
    "work authorization guaranteed",
    "security clearance guaranteed",
    "cure",
    "diagnose",
    "hipaa compliant",
}
HUBSPOT_EMAIL_RULE_PACKS = {
    "general": {
        "label": "General B2B",
        "risk_phrases": EMAIL_RISK_PHRASES,
        "vague_phrases": EMAIL_VAGUE_PHRASES,
        "required_template_tokens": ("unsubscribe_link",),
        "required_headers": ("from", "reply_to"),
    },
    "sales": {
        "label": "Sales outreach",
        "risk_phrases": EMAIL_RISK_PHRASES + ("instant roi", "guaranteed pipeline", "limited seats", "exclusive offer"),
        "vague_phrases": EMAIL_VAGUE_PHRASES + ("quick sync", "touch base", "checking in"),
        "required_template_tokens": ("first_name", "unsubscribe_link"),
        "required_headers": ("from", "reply_to"),
    },
    "marketing": {
        "label": "Marketing campaign",
        "risk_phrases": EMAIL_RISK_PHRASES + ("blast", "guaranteed results", "no obligation", "exclusive deal"),
        "vague_phrases": EMAIL_VAGUE_PHRASES + ("exciting update", "game changer", "value add"),
        "required_template_tokens": ("first_name", "unsubscribe_link"),
        "required_headers": ("from", "reply_to"),
    },
    "customer_success": {
        "label": "Customer success",
        "risk_phrases": EMAIL_RISK_PHRASES + ("no effort", "set and forget", "perfect adoption", "guaranteed renewal"),
        "vague_phrases": EMAIL_VAGUE_PHRASES + ("circle back", "quick check", "touch base"),
        "required_template_tokens": ("first_name",),
        "required_headers": ("from", "reply_to"),
    },
    "healthcare": {
        "label": "Healthcare outreach",
        "risk_phrases": EMAIL_RISK_PHRASES + ("cure", "diagnose", "treat", "hipaa compliant", "clinical guarantee"),
        "vague_phrases": EMAIL_VAGUE_PHRASES + ("better outcomes", "patient impact", "workflow improvement"),
        "required_template_tokens": ("first_name", "unsubscribe_link"),
        "required_headers": ("from", "reply_to"),
    },
    "finance": {
        "label": "Financial services",
        "risk_phrases": EMAIL_RISK_PHRASES + ("guaranteed return", "risk-free investment", "no downside", "approval guaranteed"),
        "vague_phrases": EMAIL_VAGUE_PHRASES + ("financial upside", "strong return", "market advantage"),
        "required_template_tokens": ("first_name", "unsubscribe_link"),
        "required_headers": ("from", "reply_to"),
    },
    "staffing_general": {
        "label": "Staffing and recruiting",
        "risk_phrases": EMAIL_RISK_PHRASES
        + (
            "job guaranteed",
            "placement guaranteed",
            "guaranteed placement",
            "guaranteed interview",
            "guaranteed hire",
            "guaranteed candidates",
            "background check guaranteed",
            "visa guaranteed",
            "work authorization guaranteed",
            "salary guaranteed",
            "exclusive role",
        ),
        "vague_phrases": EMAIL_VAGUE_PHRASES + ("great fit", "exciting role", "good opportunity", "next steps soon", "strong candidates"),
        "required_template_tokens": ("first_name", "unsubscribe_link"),
        "required_headers": ("from", "reply_to"),
    },
    "staffing_us": {
        "label": "Staffing - US",
        "risk_phrases": EMAIL_RISK_PHRASES
        + (
            "job guaranteed",
            "placement guaranteed",
            "guaranteed interview",
            "guaranteed hire",
            "eeoc compliant",
            "background check guaranteed",
            "salary guaranteed",
            "benefits guaranteed",
            "work authorization guaranteed",
        ),
        "vague_phrases": EMAIL_VAGUE_PHRASES + ("great fit", "exciting role", "competitive pay", "good opportunity"),
        "required_template_tokens": ("first_name", "unsubscribe_link"),
        "required_headers": ("from", "reply_to"),
    },
    "staffing_eu": {
        "label": "Staffing - EU",
        "risk_phrases": EMAIL_RISK_PHRASES
        + (
            "job guaranteed",
            "placement guaranteed",
            "gdpr compliant",
            "work authorization guaranteed",
            "visa guaranteed",
            "salary guaranteed",
            "exclusive role",
        ),
        "vague_phrases": EMAIL_VAGUE_PHRASES + ("great fit", "exciting role", "local market", "data consent"),
        "required_template_tokens": ("first_name", "unsubscribe_link"),
        "required_headers": ("from", "reply_to"),
    },
    "staffing_apac": {
        "label": "Staffing - APAC",
        "risk_phrases": EMAIL_RISK_PHRASES
        + (
            "job guaranteed",
            "placement guaranteed",
            "work authorization guaranteed",
            "visa guaranteed",
            "salary guaranteed",
            "regional compliance guaranteed",
        ),
        "vague_phrases": EMAIL_VAGUE_PHRASES + ("great fit", "exciting role", "regional opportunity", "local market"),
        "required_template_tokens": ("first_name", "unsubscribe_link"),
        "required_headers": ("from", "reply_to"),
    },
    "healthcare_staffing": {
        "label": "Healthcare staffing",
        "risk_phrases": EMAIL_RISK_PHRASES
        + (
            "license guaranteed",
            "credentialing guaranteed",
            "clinical guarantee",
            "hipaa compliant",
            "patient outcome guaranteed",
            "job guaranteed",
            "placement guaranteed",
        ),
        "vague_phrases": EMAIL_VAGUE_PHRASES + ("clinical fit", "credentialed talent", "better outcomes", "urgent need"),
        "required_template_tokens": ("first_name", "unsubscribe_link"),
        "required_headers": ("from", "reply_to"),
    },
    "finance_staffing": {
        "label": "Finance staffing",
        "risk_phrases": EMAIL_RISK_PHRASES
        + (
            "licensed guaranteed",
            "background check guaranteed",
            "compliance guaranteed",
            "guaranteed return",
            "job guaranteed",
            "placement guaranteed",
            "approval guaranteed",
        ),
        "vague_phrases": EMAIL_VAGUE_PHRASES + ("qualified talent", "strong return", "trusted candidate", "regulated role"),
        "required_template_tokens": ("first_name", "unsubscribe_link"),
        "required_headers": ("from", "reply_to"),
    },
    "public_sector_staffing": {
        "label": "Public sector staffing",
        "risk_phrases": EMAIL_RISK_PHRASES
        + (
            "security clearance guaranteed",
            "contract award guaranteed",
            "government approval guaranteed",
            "background check guaranteed",
            "job guaranteed",
            "placement guaranteed",
        ),
        "vague_phrases": EMAIL_VAGUE_PHRASES + ("public sector ready", "cleared talent", "urgent mandate", "qualified pool"),
        "required_template_tokens": ("first_name", "unsubscribe_link"),
        "required_headers": ("from", "reply_to"),
    },
}
DEFAULT_HUBSPOT_EMAIL_POLICY = {
    "version": "2026-06-01.default",
    "rule_pack": "general",
    "ready_score_threshold": 78,
    "review_score_threshold": 70,
    "block_score_threshold": 50,
    "block_if_no_cta": True,
    "block_high_severity_findings": True,
    "compliance_review_on_risk_terms": True,
    "require_personalization": False,
    "min_body_words": 25,
    "max_body_words": 220,
    "custom_risk_phrases": [],
    "custom_vague_phrases": [],
    "required_template_tokens": ["unsubscribe_link"],
    "required_headers": ["from", "reply_to"],
}
HUBSPOT_CAMPAIGN_ASSET_TYPE_LABELS = {
    "AD_CAMPAIGN": "Ad campaigns",
    "BLOG_POST": "Blog posts",
    "CALL": "Calls",
    "CASE_STUDY": "Case studies",
    "CTA": "Legacy CTAs",
    "EXTERNAL_WEB_URL": "External website pages",
    "FEEDBACK_SURVEY": "Feedback surveys",
    "FILE_MANAGER_FILE": "Files",
    "FORM": "Forms",
    "KNOWLEDGE_ARTICLE": "Knowledge base articles",
    "LANDING_PAGE": "Landing pages",
    "MARKETING_EMAIL": "Marketing emails",
    "MARKETING_EVENT": "Marketing events",
    "MARKETING_SMS": "Marketing SMS",
    "MEDIA": "Videos",
    "MEETING_EVENT": "Meetings",
    "OBJECT_LIST": "Static lists",
    "PLAYBOOK": "Playbooks",
    "PODCAST_EPISODE": "Podcast episodes",
    "SALES_DOCUMENT": "Sales documents",
    "EMAIL": "Sales emails",
    "SEQUENCE": "Sequences",
    "SITE_PAGE": "Website pages",
    "SOCIAL_BROADCAST": "Social posts",
    "WEB_INTERACTIVE": "CTAs",
    "AUTOMATION_PLATFORM_FLOW": "Workflows",
}
HUBSPOT_DEFAULT_CAMPAIGN_ASSET_TYPES = (
    "MARKETING_EMAIL",
    "FORM",
    "LANDING_PAGE",
    "AD_CAMPAIGN",
    "WEB_INTERACTIVE",
    "AUTOMATION_PLATFORM_FLOW",
    "OBJECT_LIST",
    "SOCIAL_BROADCAST",
    "MARKETING_SMS",
    "SEQUENCE",
    "SITE_PAGE",
    "BLOG_POST",
)
HUBSPOT_DIRECT_COPY_ASSET_TYPES = {"MARKETING_EMAIL", "FORM", "LANDING_PAGE", "SITE_PAGE", "BLOG_POST", "SEQUENCE"}
HUBSPOT_DIRECT_COPY_SOURCE_LABELS = {
    "MARKETING_EMAIL": "marketing_email_api",
    "FORM": "forms_api",
    "LANDING_PAGE": "cms_landing_page_api",
    "SITE_PAGE": "cms_site_page_api",
    "BLOG_POST": "cms_blog_post_api",
    "SEQUENCE": "sequences_api",
}
HUBSPOT_MAPPED_COPY_ASSET_TYPES = {"AD_CAMPAIGN", "WEB_INTERACTIVE", "AUTOMATION_PLATFORM_FLOW", "SOCIAL_BROADCAST", "MARKETING_SMS", "CTA", "EMAIL"}
HUBSPOT_ASSET_COPY_SUPPORT = {
    "MARKETING_EMAIL": {
        "level": "direct_read_write",
        "read": "Marketing Emails API",
        "write": "Marketing Emails API draft update",
        "note": "Directly fetched and draft-updated when the portal grants marketing-email scope.",
    },
    "FORM": {"level": "direct_read", "read": "Forms API", "write": "mapped_only", "note": "Direct read is supported; TextTraits does not change form definitions."},
    "LANDING_PAGE": {"level": "direct_read", "read": "CMS pages API", "write": "mapped_only", "note": "Direct read is supported for review; CMS publishing remains owner-controlled."},
    "SITE_PAGE": {"level": "direct_read", "read": "CMS pages API", "write": "mapped_only", "note": "Direct read is supported for review; CMS publishing remains owner-controlled."},
    "BLOG_POST": {"level": "direct_read", "read": "CMS blogs API", "write": "mapped_only", "note": "Direct read is supported for review; publishing remains owner-controlled."},
    "SEQUENCE": {"level": "direct_read", "read": "Sequences API", "write": "mapped_only", "note": "Direct read is supported for sequence metadata and step text returned by HubSpot."},
    "WEB_INTERACTIVE": {"level": "mapped_copy", "read": "Campaign asset association plus mapped payload", "write": "mapped_only", "note": "CTA association is supported by Campaigns API; reviewable CTA copy should be supplied through mapped copy."},
    "MARKETING_SMS": {"level": "mapped_copy", "read": "Campaign asset association plus mapped payload", "write": "mapped_only", "note": "Marketing SMS campaign associations are supported; reviewable message text should be supplied through mapped copy."},
    "SOCIAL_BROADCAST": {"level": "mapped_copy", "read": "Campaign asset association plus mapped payload", "write": "mapped_only", "note": "Social post associations are supported; reviewable post copy should be supplied through mapped copy."},
    "AD_CAMPAIGN": {"level": "mapped_copy", "read": "Campaign asset association plus mapped payload", "write": "mapped_only", "note": "Ad associations are supported; ad creative copy should be supplied through mapped copy."},
    "AUTOMATION_PLATFORM_FLOW": {"level": "mapped_copy", "read": "Campaign asset association plus mapped payload", "write": "mapped_only", "note": "Workflow associations are supported; email/SMS step copy should be supplied through mapped copy or marketing-email IDs."},
    "OBJECT_LIST": {"level": "association_only", "read": "Campaign asset association", "write": "not_applicable", "note": "Lists are used for segmentation and routing, not copy review."},
}
HUBSPOT_STAFFING_OBJECT_SPECIALIZATION = {
    "contacts": {
        "staffing_label": "Candidates and talent contacts",
        "primary_use": "Candidate nurture, consent-aware job alerts, reactivation, and placement follow-up.",
        "texttraits_use": "Score candidate-facing copy and write review fields back to contact records, lists, and timeline events.",
        "recommended_context": ("candidate_status", "skill_family", "region", "recruiter", "job_id", "consent_context"),
    },
    "companies": {
        "staffing_label": "Hiring clients and account targets",
        "primary_use": "Client hiring campaigns, employer account marketing, and account-based follow-up.",
        "texttraits_use": "Score client-facing claims and route risky staffing promises to marketing ops or compliance.",
        "recommended_context": ("client_account", "business_unit", "region", "owner_id"),
    },
    "deals": {
        "staffing_label": "Job orders, opportunities, and placements",
        "primary_use": "Track demand, job-order progress, and placement opportunities tied to campaigns.",
        "texttraits_use": "Join email decisions to job-order outcomes and Salesforce opportunity mappings where configured.",
        "recommended_context": ("job_id", "job_family", "client_account", "salesforce_opportunity_id"),
    },
    "tickets": {
        "staffing_label": "Support, escalations, and compliance exceptions",
        "primary_use": "Capture blocked language reviews, candidate issues, and operational escalations.",
        "texttraits_use": "Route blocked messages into review queues with owner, blocker level, SLA, and final resolution.",
        "recommended_context": ("review_queue", "blocker_level", "sla_due_at", "region"),
    },
}
HUBSPOT_STAFFING_WORKFLOW_TEMPLATES = (
    {
        "id": "candidate_nurture",
        "name": "Candidate nurture",
        "hubspot_surfaces": ("Marketing email", "Lists", "Workflows", "Contact timeline", "CRM properties"),
        "audience_type": "candidate",
        "policy_pack": "staffing_general",
        "steps": (
            "Segment candidates by skill family, region, consent state, and candidate status.",
            "Run TextTraits pre-publish guardrail on each email/SMS/social asset before scheduling.",
            "Route needs-review copy to recruiter or marketing ops; route high-risk claims to compliance.",
            "Write score, gate, route, and blocker reason back to the contact and analysis object.",
            "Join opens/clicks/replies/placements to content hash for outcome analytics.",
        ),
        "required_context": ("candidate_status", "skill_family", "region", "recruiter", "consent_context"),
    },
    {
        "id": "job_alert",
        "name": "Job alert",
        "hubspot_surfaces": ("Marketing email", "Marketing SMS", "Lists", "Workflows", "Campaigns"),
        "audience_type": "candidate",
        "policy_pack": "staffing_general",
        "steps": (
            "Map job ID, job family, location/region, pay/benefit claim source, and unsubscribe state.",
            "Score the rendered template for vague job details, missing next step, and risky guarantees.",
            "Block unqualified salary, visa, work authorization, or placement promises.",
            "Route region-specific exceptions to the configured regional owner.",
        ),
        "required_context": ("job_id", "job_family", "region", "candidate_status", "job_board"),
    },
    {
        "id": "passive_candidate_reactivation",
        "name": "Passive candidate reactivation",
        "hubspot_surfaces": ("Marketing email", "Sequences", "Lists", "Workflows", "Contact timeline"),
        "audience_type": "candidate",
        "policy_pack": "staffing_general",
        "steps": (
            "Use a stale-candidate list or sequence enrollment as the trigger.",
            "Score outreach for concrete role context and low-pressure language.",
            "Send vague or pressure-heavy copy to marketing review before activation.",
            "Measure replies, unsubscribes, suppressions, and reactivation outcomes by skill family.",
        ),
        "required_context": ("candidate_status", "skill_family", "last_contacted_at", "region"),
    },
    {
        "id": "client_hiring_campaign",
        "name": "Client hiring campaign",
        "hubspot_surfaces": ("Campaigns", "Marketing email", "Social posts", "Ads", "Companies", "Deals"),
        "audience_type": "client",
        "policy_pack": "staffing_general",
        "steps": (
            "Associate email, landing-page, form, social, and ad assets to the campaign.",
            "Score all directly fetched assets and require mapped copy for ad/social/CTA claims.",
            "Route risky candidate-availability or guaranteed-hire claims to legal/compliance.",
            "Roll up blocked assets by campaign, business unit, region, and client account.",
        ),
        "required_context": ("client_account", "business_unit", "region", "campaign_id"),
    },
    {
        "id": "regional_lead_routing",
        "name": "Regional lead routing",
        "hubspot_surfaces": ("Forms", "Lists", "Workflows", "Owners", "CRM properties", "Review tasks"),
        "audience_type": "candidate_or_client",
        "policy_pack": "staffing_general",
        "steps": (
            "Capture region, business unit, skill family, and owner queue from form/workflow context.",
            "Use TextTraits gate and route fields as workflow branches.",
            "Assign review tasks to recruiter, marketing ops, compliance/legal, or regional owner.",
            "Track SLA and final resolution before the asset enters a send path.",
        ),
        "required_context": ("region", "business_unit", "skill_family", "owner_id"),
    },
)
HUBSPOT_APPROVAL_CHAIN_TEMPLATES = (
    {
        "id": "standard_staffing_marketing",
        "name": "Standard staffing campaign review",
        "steps": ("Recruiter", "Marketing ops", "Compliance/legal", "Regional owner"),
        "recommended_for": ("Candidate nurture", "Job alerts", "Passive candidate reactivation"),
        "blocked_routes": ("Compliance review", "Regional owner review"),
    },
    {
        "id": "client_claims_review",
        "name": "Client hiring claims review",
        "steps": ("Account owner", "Marketing ops", "Compliance/legal"),
        "recommended_for": ("Client hiring campaign", "Ads", "Social posts", "Landing pages"),
        "blocked_routes": ("Compliance review", "Legal review"),
    },
    {
        "id": "regional_fast_path",
        "name": "Regional routing fast path",
        "steps": ("Recruiter", "Regional owner"),
        "recommended_for": ("Regional lead routing", "Low-risk localized nurture"),
        "blocked_routes": ("Regional owner review",),
    },
)
HUBSPOT_SETUP_WIZARD_STEPS = (
    {
        "id": "scopes",
        "label": "Scopes",
        "action": "Confirm OAuth scopes for campaigns, marketing emails, CRM objects, lists, owners, webhooks, and optional asset copy sources.",
        "endpoint": "/api/enterprise/hubspot/surfaces",
    },
    {
        "id": "properties",
        "label": "CRM properties",
        "action": "Create TextTraits score, gate, route, blocker, request ID, content hash, and review status fields.",
        "endpoint": "/v1/integrations/hubspot/properties/provision",
    },
    {
        "id": "analysis_object",
        "label": "Analysis object",
        "action": "Create the TextTraits Analysis custom object for durable governance records.",
        "endpoint": "/v1/integrations/hubspot/analysis-schema/provision",
    },
    {
        "id": "webhooks",
        "label": "Webhook subscriptions",
        "action": "Subscribe to record updates and lifecycle events for re-scoring and uninstall cleanup.",
        "endpoint": "/v1/integrations/hubspot/webhooks/configure",
    },
    {
        "id": "owners",
        "label": "Owners and review queues",
        "action": "Load HubSpot owners and map Marketing review, Compliance review, Regional owner review, and fallback queues.",
        "endpoint": "/v1/integrations/hubspot/review-routing/config",
    },
    {
        "id": "segments",
        "label": "Review segments",
        "action": "Create or map Ready, Needs review, and Blocked segments/lists for operational queues.",
        "endpoint": "/v1/integrations/hubspot/lists/create-review-segments",
    },
)
HUBSPOT_POLICY_BOOLEAN_KEYS = {
    "block_if_no_cta",
    "block_high_severity_findings",
    "compliance_review_on_risk_terms",
    "require_personalization",
}
HUBSPOT_POLICY_INTEGER_BOUNDS = {
    "ready_score_threshold": (0, 100),
    "review_score_threshold": (0, 100),
    "block_score_threshold": (0, 100),
    "min_body_words": (0, 500),
    "max_body_words": (1, 1200),
}
HUBSPOT_POLICY_LIST_KEYS = {
    "custom_risk_phrases",
    "custom_vague_phrases",
    "required_template_tokens",
    "required_headers",
}
HUBSPOT_INTEGRATION_SURFACES = (
    {
        "id": "crm_record_card",
        "label": "CRM record app card",
        "hubspot_area": "Contacts, companies, deals, tickets",
        "status": "implemented",
        "endpoint": "/v1/integrations/hubspot/crm-card/analyze-email",
        "purpose": "Manual rep or reviewer preflight on a record sidebar.",
        "mapping": ("subject", "body", "portal_id", "object_type", "object_id"),
    },
    {
        "id": "workflow_action",
        "label": "Custom workflow action",
        "hubspot_area": "Workflows and automation branches",
        "status": "implemented",
        "endpoint": "/v1/integrations/hubspot/workflow-actions/analyze-email",
        "purpose": "Send-path gate that returns ready, review, or blocked output fields.",
        "mapping": ("email_subject", "email_body", "workflow_name", "campaign_id", "template_id"),
    },
    {
        "id": "campaign_workflow_action",
        "label": "Campaign asset workflow action",
        "hubspot_area": "Workflows, Campaigns, and campaign assets",
        "status": "implemented",
        "endpoint": "/v1/integrations/hubspot/workflow-actions/review-campaign-assets",
        "purpose": "Review a campaign's HubSpot assets from a workflow and return branchable campaign health fields.",
        "mapping": ("portal_id", "campaign_id", "asset_types[]", "limit"),
    },
    {
        "id": "asset_copy_workflow_action",
        "label": "Asset copy workflow action",
        "hubspot_area": "Workflows, forms, pages, SMS, social posts, CTAs",
        "status": "implemented",
        "endpoint": "/v1/integrations/hubspot/workflow-actions/analyze-asset-copy",
        "purpose": "Score mapped copy from any HubSpot asset inside a workflow and return branchable asset-level routing fields.",
        "mapping": ("asset_type", "asset_id", "asset_name", "asset_copy", "campaign_id"),
    },
    {
        "id": "marketing_email_preflight",
        "label": "Marketing email preflight",
        "hubspot_area": "Marketing Emails v3 assets",
        "status": "implemented_backend",
        "endpoint": "/v1/integrations/hubspot/marketing-emails/analyze",
        "purpose": "Score a HubSpot marketing email draft or revision before scheduling.",
        "mapping": ("id", "subject", "html", "campaignId", "from", "replyTo"),
    },
    {
        "id": "marketing_email_pre_publish_guardrail",
        "label": "Marketing email pre-publish guardrail",
        "hubspot_area": "Marketing Emails, Campaigns, and send-path governance",
        "status": "implemented_requires_oauth",
        "endpoint": "/v1/integrations/hubspot/marketing-emails/pre-publish-guardrail",
        "purpose": "Fetch a real HubSpot marketing email and return a publish-allowed decision without publishing or mutating the email.",
        "mapping": ("portal_id", "email_id", "campaign_id", "policy.rule_pack", "region", "business_unit"),
    },
    {
        "id": "asset_copy_preflight",
        "label": "HubSpot asset copy preflight",
        "hubspot_area": "Forms, landing pages, site pages, blog posts, ads, SMS, social, CTAs, sequences, workflows",
        "status": "implemented_backend",
        "endpoint": "/v1/integrations/hubspot/assets/analyze",
        "purpose": "Score reviewable copy from any HubSpot asset snapshot while preserving the asset type and campaign context.",
        "mapping": ("asset_type", "asset.id", "asset.name", "asset.html", "asset.body", "campaign_id"),
    },
    {
        "id": "live_asset_copy_review",
        "label": "Live asset copy fetch and review",
        "hubspot_area": "Forms, landing pages, site pages, blog posts, marketing emails, sequences",
        "status": "implemented_requires_oauth",
        "endpoint": "/v1/integrations/hubspot/assets/fetch-and-analyze",
        "purpose": "Fetch a single copy-bearing HubSpot asset through OAuth, then run the same TextTraits pre-send quality gate.",
        "mapping": ("portal_id", "asset_type", "asset_id", "campaign_id"),
    },
    {
        "id": "campaign_preflight",
        "label": "Campaign asset preflight",
        "hubspot_area": "Campaigns and campaign assets",
        "status": "implemented_backend",
        "endpoint": "/v1/integrations/hubspot/campaigns/analyze",
        "purpose": "Batch-score the email assets attached to a campaign and summarize risk.",
        "mapping": ("campaign.id", "campaign.name", "emails[].subject", "emails[].html"),
    },
    {
        "id": "bulk_email_preflight",
        "label": "Bulk email quality gate",
        "hubspot_area": "Imports, lists, sequences, and send middleware",
        "status": "implemented_backend",
        "endpoint": "/v1/integrations/hubspot/bulk/analyze-emails",
        "purpose": "Analyze up to the configured batch limit from any HubSpot email-like payload.",
        "mapping": ("emails[]", "workspace_id", "source_system", "idempotency_key"),
    },
    {
        "id": "bulk_asset_import",
        "label": "Bulk campaign asset import",
        "hubspot_area": "CSV imports, warehouse exports, campaign asset staging",
        "status": "implemented_backend",
        "endpoint": "/v1/integrations/hubspot/bulk/import-assets",
        "purpose": "Score imported campaign asset rows from CSV or warehouse export payloads and return campaign-style coverage.",
        "mapping": ("import_id", "assets[]", "csv_text", "asset_type", "asset_copy", "campaign_id"),
    },
    {
        "id": "template_test",
        "label": "Rendered-template test",
        "hubspot_area": "Personalization tokens and marketing templates",
        "status": "implemented",
        "endpoint": "/v1/integrations/hubspot/template-test",
        "purpose": "Render Liquid/Handlebars-style tokens against sample recipient context.",
        "mapping": ("email_subject", "email_body", "sample_context", "headers"),
    },
    {
        "id": "analyze_and_sync",
        "label": "Analyze and sync",
        "hubspot_area": "Campaigns, marketing emails, CRM records, tasks, custom objects, timelines",
        "status": "implemented_requires_oauth",
        "endpoint": "/v1/integrations/hubspot/analyze-and-sync",
        "purpose": "Analyze an existing draft and perform the HubSpot-native writeback, task, custom-object, timeline, and asset sync steps in one workflow-safe call.",
        "mapping": ("portal_id", "subject", "body", "campaign_id", "template_id", "object_type", "object_id", "analysis_object_type"),
    },
    {
        "id": "email_event_outcomes",
        "label": "Email event outcome joins",
        "hubspot_area": "Email events, campaign reporting, webhooks",
        "status": "implemented",
        "endpoint": "/v1/integrations/hubspot/outcomes",
        "purpose": "Join delivered, bounced, opened, clicked, suppressed, unsubscribed, and complaint events back to TextTraits decisions.",
        "mapping": ("request_id", "content_hash", "event_type", "event_id", "occurred_at"),
    },
    {
        "id": "salesforce_outcome_mapping",
        "label": "Salesforce outcome mapping",
        "hubspot_area": "Salesforce-connected reporting and placement outcomes",
        "status": "implemented_backend",
        "endpoint": "/v1/integrations/hubspot/salesforce/outcomes/import",
        "purpose": "Accept mapped Salesforce campaign, opportunity, lead, contact, and placement outcomes without requiring fake Salesforce credentials.",
        "mapping": ("salesforce_campaign_id", "salesforce_opportunity_id", "salesforce_lead_id", "salesforce_contact_id", "event_type"),
    },
    {
        "id": "campaign_create_update",
        "label": "Campaign create/update",
        "hubspot_area": "Campaigns",
        "status": "implemented_requires_oauth",
        "endpoint": "/v1/integrations/hubspot/campaigns/create",
        "purpose": "Create or update HubSpot campaigns from TextTraits-managed campaign metadata.",
        "mapping": ("portal_id", "properties.hs_name", "properties.hs_start_date", "properties.hs_notes"),
    },
    {
        "id": "campaign_picker",
        "label": "Campaign picker and search",
        "hubspot_area": "Campaigns",
        "status": "implemented_requires_oauth",
        "endpoint": "/v1/integrations/hubspot/campaigns/list",
        "purpose": "List HubSpot campaigns so admins can select a real campaign instead of pasting campaign IDs.",
        "mapping": ("portal_id", "query", "limit", "after"),
    },
    {
        "id": "campaign_asset_association",
        "label": "Campaign asset association",
        "hubspot_area": "Campaigns and campaign assets",
        "status": "implemented_requires_oauth",
        "endpoint": "/v1/integrations/hubspot/campaigns/associate-asset",
        "purpose": "Attach reviewed HubSpot assets such as marketing emails, forms, landing pages, workflows, and lists to a campaign.",
        "mapping": ("portal_id", "campaign_id", "asset_type", "asset_id"),
    },
    {
        "id": "marketing_email_draft_sync",
        "label": "Marketing email draft sync",
        "hubspot_area": "Marketing Emails v3 assets",
        "status": "implemented_requires_oauth",
        "endpoint": "/v1/integrations/hubspot/marketing-emails/fetch",
        "purpose": "Create, update, fetch, score, and sync HubSpot marketing email drafts.",
        "mapping": ("portal_id", "email_id", "name", "subject", "templatePath"),
    },
    {
        "id": "marketing_email_picker",
        "label": "Marketing email picker and search",
        "hubspot_area": "Marketing Emails v3 assets",
        "status": "implemented_requires_oauth",
        "endpoint": "/v1/integrations/hubspot/marketing-emails/list",
        "purpose": "List HubSpot marketing emails so campaign review can select real draft assets before scoring.",
        "mapping": ("portal_id", "query", "state", "limit", "after"),
    },
    {
        "id": "review_task_creation",
        "label": "Review task creation",
        "hubspot_area": "Tasks and reviewer queues",
        "status": "implemented_requires_oauth",
        "endpoint": "/v1/integrations/hubspot/tasks/create-review",
        "purpose": "Create a HubSpot task when a draft needs marketing, legal, or compliance review.",
        "mapping": ("portal_id", "request_id", "hubspot_owner_id", "hs_task_subject"),
    },
    {
        "id": "owner_directory",
        "label": "Owner directory",
        "hubspot_area": "Owners and team-aware routing",
        "status": "implemented_requires_oauth",
        "endpoint": "/v1/integrations/hubspot/owners/list",
        "purpose": "Fetch HubSpot owners and team labels so admins can assign TextTraits review queues to real HubSpot users.",
        "mapping": ("portal_id", "limit", "after", "archived"),
    },
    {
        "id": "review_route_owner_mapping",
        "label": "Review route owner mapping",
        "hubspot_area": "Settings and reviewer queues",
        "status": "implemented_backend",
        "endpoint": "/v1/integrations/hubspot/review-routing/config",
        "purpose": "Persist portal-specific mappings from TextTraits review routes to HubSpot owner IDs for review task assignment.",
        "mapping": ("portal_id", "workspace_id", "route_owner_map", "default_owner_id"),
    },
    {
        "id": "staffing_workflow_templates",
        "label": "Staffing workflow templates",
        "hubspot_area": "Staffing campaign operations, workflows, lists, and CRM objects",
        "status": "implemented_backend",
        "endpoint": "/api/enterprise/hubspot/staffing-workflow-templates",
        "purpose": "Expose candidate nurture, job alert, passive reactivation, client hiring, and regional routing templates as product data.",
        "mapping": ("audience_type", "policy_pack", "required_context", "hubspot_surfaces"),
    },
    {
        "id": "approval_chain_templates",
        "label": "Approval chain templates",
        "hubspot_area": "Review queues, owners, tasks, and compliance workflow",
        "status": "implemented_backend",
        "endpoint": "/api/enterprise/hubspot/approval-chain-templates",
        "purpose": "Expose recruiter, marketing ops, compliance/legal, and regional owner approval chains.",
        "mapping": ("route", "owner_queue", "blocked_routes"),
    },
    {
        "id": "hubspot_setup_wizard",
        "label": "HubSpot setup wizard",
        "hubspot_area": "Admin setup, scopes, properties, custom objects, webhooks, owners, queues",
        "status": "implemented_backend",
        "endpoint": "/api/enterprise/hubspot/setup-wizard",
        "purpose": "Guide admins through scopes, field provisioning, analysis object, webhooks, owners, review queues, and segments.",
        "mapping": ("portal_id", "setup_status", "wizard_steps"),
    },
    {
        "id": "approval_workflow_sync",
        "label": "Approval workflow sync",
        "hubspot_area": "Tasks, CRM properties, and custom objects",
        "status": "implemented_requires_oauth",
        "endpoint": "/v1/integrations/hubspot/review-action",
        "purpose": "Sync approved, rejected, resolved, assigned, and queued TextTraits review states back into HubSpot tasks, CRM properties, and Analysis custom-object records.",
        "mapping": ("portal_id", "request_id", "action", "object_type", "object_id", "task_id", "analysis_object_type"),
    },
    {
        "id": "crm_property_writeback",
        "label": "CRM property writeback",
        "hubspot_area": "CRM properties and reports",
        "status": "implemented_requires_oauth",
        "endpoint": "/v1/integrations/hubspot/properties/writeback",
        "purpose": "Write TextTraits score, gate, route, policy version, and blocker reason back to HubSpot records.",
        "mapping": ("portal_id", "request_id", "object_type", "object_id", "properties"),
    },
    {
        "id": "analysis_custom_object",
        "label": "Analysis custom object record",
        "hubspot_area": "Custom objects",
        "status": "implemented_requires_oauth",
        "endpoint": "/v1/integrations/hubspot/analysis-records/create",
        "purpose": "Store a durable TextTraits analysis record in a portal-specific HubSpot custom object and associate it to CRM/campaign/email context when real association type IDs are supplied.",
        "mapping": ("portal_id", "request_id", "object_type", "properties", "analysis_association_type_ids", "analysis_record_associations"),
    },
    {
        "id": "timeline_events",
        "label": "Timeline event sync",
        "hubspot_area": "CRM timelines",
        "status": "implemented_requires_oauth",
        "endpoint": "/v1/integrations/hubspot/timeline-events/create",
        "purpose": "Push TextTraits review history into HubSpot timelines for record-level context.",
        "mapping": ("portal_id", "app_id", "eventTemplateId", "objectId", "tokens"),
    },
    {
        "id": "lists_segments",
        "label": "Lists and segments",
        "hubspot_area": "Lists / Segments",
        "status": "implemented_requires_oauth",
        "endpoint": "/v1/integrations/hubspot/lists/create",
        "purpose": "Create HubSpot segments for assets or records that need review, are blocked, or are ready to send.",
        "mapping": ("portal_id", "name", "objectTypeId", "processingType", "filterBranch"),
    },
    {
        "id": "lists_segments_search",
        "label": "Lists and segments search",
        "hubspot_area": "Lists / Segments",
        "status": "implemented_requires_oauth",
        "endpoint": "/v1/integrations/hubspot/lists/search",
        "purpose": "Read existing HubSpot segments by query, processing type, object type, or list ID before creating duplicates.",
        "mapping": ("portal_id", "query", "processingTypes[]", "objectTypeId", "listIds[]"),
    },
    {
        "id": "lists_segments_membership_update",
        "label": "List membership update",
        "hubspot_area": "Lists / Segments",
        "status": "implemented_requires_oauth",
        "endpoint": "/v1/integrations/hubspot/lists/memberships/update",
        "purpose": "Add or remove records from HubSpot manual or snapshot segments that route TextTraits review work.",
        "mapping": ("portal_id", "list_id", "recordIdsToAdd[]", "recordIdsToRemove[]"),
    },
    {
        "id": "review_segment_templates",
        "label": "Review segment templates",
        "hubspot_area": "Lists / Segments",
        "status": "implemented_requires_oauth",
        "endpoint": "/v1/integrations/hubspot/lists/create-review-segments",
        "purpose": "Create default HubSpot segments for ready, needs-review, and blocked records using TextTraits writeback fields.",
        "mapping": ("portal_id", "objectTypeId", "propertyName", "segments[]"),
    },
    {
        "id": "webhook_sync",
        "label": "Webhook event ingest",
        "hubspot_area": "App webhooks",
        "status": "implemented",
        "endpoint": "/v1/integrations/hubspot/webhooks/receive",
        "purpose": "Ingest HubSpot object/property change notifications with HubSpot signature validation and re-score copy-bearing draft events.",
        "mapping": ("portalId", "eventType", "eventId", "occurredAt", "objectId", "marketingEmail", "subject", "body", "html"),
    },
    {
        "id": "app_uninstall_cleanup",
        "label": "App uninstall cleanup",
        "hubspot_area": "Marketplace lifecycle",
        "status": "implemented",
        "endpoint": "/v1/integrations/hubspot/app-uninstalled",
        "purpose": "Handle HubSpot app removal callbacks by clearing stored portal OAuth tokens and returning retained-data guidance.",
        "mapping": ("portalId", "hubId", "eventType", "occurredAt"),
    },
    {
        "id": "stats_sync",
        "label": "Email and campaign stats sync",
        "hubspot_area": "Marketing performance",
        "status": "implemented_requires_oauth",
        "endpoint": "/v1/integrations/hubspot/stats/sync",
        "purpose": "Pull campaign/email performance snapshots and join them to TextTraits decisions.",
        "mapping": ("portal_id", "email_id", "campaign_id", "startDate", "endDate"),
    },
    {
        "id": "live_campaign_review",
        "label": "Live campaign asset map and review",
        "hubspot_area": "Campaigns and campaign assets",
        "status": "implemented_requires_oauth",
        "endpoint": "/v1/integrations/hubspot/campaigns/review",
        "purpose": "Fetch a HubSpot campaign's selected asset types, score copy-bearing drafts, and return campaign-level health plus an asset map.",
        "mapping": ("portal_id", "campaign_id", "asset_types[]", "limit"),
    },
    {
        "id": "crm_property_provisioning",
        "label": "CRM property provisioning",
        "hubspot_area": "CRM properties",
        "status": "implemented_requires_oauth",
        "endpoint": "/v1/integrations/hubspot/properties/provision",
        "purpose": "Create the TextTraits score, gate, route, policy, request, and blocker fields needed for HubSpot reporting.",
        "mapping": ("portal_id", "object_types[]", "properties[]"),
    },
    {
        "id": "analysis_schema_provisioning",
        "label": "Analysis custom-object provisioning",
        "hubspot_area": "Custom objects",
        "status": "implemented_requires_oauth",
        "endpoint": "/v1/integrations/hubspot/analysis-schema/provision",
        "purpose": "Create or verify the TextTraits Analysis custom object schema for durable, reportable analysis records.",
        "mapping": ("portal_id", "object_name", "associatedObjects[]"),
    },
    {
        "id": "webhook_management",
        "label": "Webhook settings and subscriptions",
        "hubspot_area": "App webhooks",
        "status": "implemented_requires_oauth",
        "endpoint": "/v1/integrations/hubspot/webhooks/configure",
        "purpose": "Configure the HubSpot app webhook target and subscribe to record-change events that can trigger re-scoring.",
        "mapping": ("portal_id", "app_id", "targetUrl", "subscriptions[]"),
    },
)
HUBSPOT_SURFACE_REQUIRED_SCOPES = {
    "asset_copy_workflow_action": (),
    "campaign_workflow_action": ("marketing.campaigns.read",),
    "analyze_and_sync": ("crm.objects.contacts.write", "crm.objects.companies.write", "crm.objects.deals.write"),
    "campaign_create_update": ("marketing.campaigns.write",),
    "campaign_picker": ("marketing.campaigns.read",),
    "campaign_asset_association": ("marketing.campaigns.write",),
    "marketing_email_draft_sync": ("marketing-email",),
    "marketing_email_picker": ("marketing-email",),
    "live_asset_copy_review": (),
    "owner_directory": ("crm.objects.owners.read",),
    "review_route_owner_mapping": (),
    "review_task_creation": (),
    "approval_workflow_sync": (),
    "crm_property_writeback": ("crm.objects.contacts.write", "crm.objects.companies.write", "crm.objects.deals.write"),
    "analysis_custom_object": ("crm.objects.custom.write",),
    "timeline_events": ("timeline",),
    "lists_segments": ("crm.lists.write",),
    "lists_segments_search": ("crm.lists.read",),
    "lists_segments_membership_update": ("crm.lists.write",),
    "review_segment_templates": ("crm.lists.write",),
    "stats_sync": (),
    "app_uninstall_cleanup": (),
    "live_campaign_review": ("marketing.campaigns.read",),
    "crm_property_provisioning": ("crm.objects.contacts.write", "crm.objects.companies.write", "crm.objects.deals.write"),
    "analysis_schema_provisioning": ("crm.objects.custom.write",),
    "webhook_management": (),
}
HUBSPOT_SURFACE_RECOMMENDED_SCOPES = {
    "asset_copy_workflow_action": ("forms", "content", "marketing-email"),
    "campaign_workflow_action": ("marketing-email", "forms", "content"),
    "live_campaign_review": ("marketing-email", "forms", "content"),
    "live_asset_copy_review": ("marketing-email", "forms", "content"),
    "analyze_and_sync": ("crm.objects.custom.write", "timeline", "crm.lists.write"),
    "review_task_creation": ("crm.objects.contacts.write", "crm.objects.companies.write", "crm.objects.deals.write", "crm.objects.owners.read"),
    "approval_workflow_sync": ("crm.objects.contacts.write", "crm.objects.companies.write", "crm.objects.deals.write", "crm.objects.custom.read", "crm.objects.custom.write"),
    "crm_property_writeback": ("tickets",),
    "crm_property_provisioning": ("tickets",),
    "stats_sync": ("marketing-email", "marketing.campaigns.read"),
    "webhook_management": ("oauth",),
    "app_uninstall_cleanup": ("oauth",),
}
HUBSPOT_SURFACE_STATUS_LABELS = {
    "implemented": "Ready",
    "implemented_backend": "Mapped payload ready",
    "implemented_requires_oauth": "Needs OAuth connection",
}
HUBSPOT_OBJECT_PROPERTY_GROUPS = {
    "contacts": "contactinformation",
    "companies": "companyinformation",
    "deals": "dealinformation",
    "tickets": "ticketinformation",
}
TEXTTRAITS_HUBSPOT_PROPERTIES = (
    {"name": "texttraits_score", "label": "TextTraits score", "type": "number", "fieldType": "number", "description": "Latest TextTraits email-quality score."},
    {
        "name": "texttraits_gate",
        "label": "TextTraits gate",
        "type": "enumeration",
        "fieldType": "select",
        "description": "Latest TextTraits routing gate.",
        "options": [
            {"label": "Ready", "value": "ready", "displayOrder": 0, "hidden": False},
            {"label": "Needs review", "value": "needs_review", "displayOrder": 1, "hidden": False},
            {"label": "Blocked", "value": "blocked", "displayOrder": 2, "hidden": False},
        ],
    },
    {"name": "texttraits_route", "label": "TextTraits route", "type": "string", "fieldType": "text", "description": "Current review route or owner queue."},
    {"name": "texttraits_policy_version", "label": "TextTraits policy version", "type": "string", "fieldType": "text", "description": "Policy bundle version used for the latest decision."},
    {"name": "texttraits_last_checked_at", "label": "TextTraits last checked at", "type": "string", "fieldType": "text", "description": "Timestamp of the latest TextTraits analysis."},
    {"name": "texttraits_blocker_reason", "label": "TextTraits blocker reason", "type": "string", "fieldType": "textarea", "description": "Primary blocker or next step from TextTraits."},
    {"name": "texttraits_request_id", "label": "TextTraits request ID", "type": "string", "fieldType": "text", "description": "TextTraits analysis request identifier."},
    {"name": "texttraits_content_hash", "label": "TextTraits content hash", "type": "string", "fieldType": "text", "description": "Tenant-scoped digest for joining outcomes without storing full copy."},
    {
        "name": "texttraits_review_status",
        "label": "TextTraits review status",
        "type": "enumeration",
        "fieldType": "select",
        "description": "Latest human review state synced from TextTraits.",
        "options": [
            {"label": "Open", "value": "open", "displayOrder": 0, "hidden": False},
            {"label": "Queued", "value": "queued", "displayOrder": 1, "hidden": False},
            {"label": "Assigned", "value": "assigned", "displayOrder": 2, "hidden": False},
            {"label": "Approved", "value": "approved", "displayOrder": 3, "hidden": False},
            {"label": "Rejected", "value": "rejected", "displayOrder": 4, "hidden": False},
            {"label": "Resolved", "value": "resolved", "displayOrder": 5, "hidden": False},
            {"label": "Rerun requested", "value": "rerun_requested", "displayOrder": 6, "hidden": False},
        ],
    },
    {"name": "texttraits_review_action", "label": "TextTraits review action", "type": "string", "fieldType": "text", "description": "Latest review action recorded by TextTraits."},
    {"name": "texttraits_review_updated_at", "label": "TextTraits review updated at", "type": "string", "fieldType": "text", "description": "Timestamp of the latest TextTraits review action."},
    {"name": "texttraits_review_updated_by", "label": "TextTraits review updated by", "type": "string", "fieldType": "text", "description": "Actor who recorded the latest TextTraits review action."},
)
TEXTTRAITS_ANALYSIS_SCHEMA_PROPERTIES = (
    {"name": "texttraits_request_id", "label": "Request ID", "type": "string", "fieldType": "text"},
    {"name": "texttraits_score", "label": "Score", "type": "number", "fieldType": "number"},
    {"name": "texttraits_gate", "label": "Gate", "type": "enumeration", "fieldType": "select", "options": [{"label": "Ready", "value": "ready"}, {"label": "Needs review", "value": "needs_review"}, {"label": "Blocked", "value": "blocked"}]},
    {"name": "texttraits_route", "label": "Route", "type": "string", "fieldType": "text"},
    {"name": "texttraits_policy_version", "label": "Policy version", "type": "string", "fieldType": "text"},
    {"name": "texttraits_blocker_reason", "label": "Blocker reason", "type": "string", "fieldType": "textarea"},
    {"name": "texttraits_campaign_id", "label": "Campaign ID", "type": "string", "fieldType": "text"},
    {"name": "texttraits_template_id", "label": "Template or email ID", "type": "string", "fieldType": "text"},
    {"name": "texttraits_source_system", "label": "Source system", "type": "string", "fieldType": "text"},
    {"name": "texttraits_content_hash", "label": "Content hash", "type": "string", "fieldType": "text"},
    {"name": "texttraits_review_status", "label": "Review status", "type": "enumeration", "fieldType": "select", "options": [{"label": "Open", "value": "open"}, {"label": "Queued", "value": "queued"}, {"label": "Assigned", "value": "assigned"}, {"label": "Approved", "value": "approved"}, {"label": "Rejected", "value": "rejected"}, {"label": "Resolved", "value": "resolved"}, {"label": "Rerun requested", "value": "rerun_requested"}]},
    {"name": "texttraits_review_action", "label": "Review action", "type": "string", "fieldType": "text"},
    {"name": "texttraits_review_updated_at", "label": "Review updated at", "type": "string", "fieldType": "text"},
    {"name": "texttraits_review_updated_by", "label": "Review updated by", "type": "string", "fieldType": "text"},
)
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
configure_logging(ARTIFACT_DIR / "app.log")


def validate_runtime_config() -> None:
    failures: list[str] = []
    hubspot_secret = os.getenv("TEXTTRAITS_HUBSPOT_INGRESS_SECRET", "").strip()
    content_hash_secret = os.getenv("TEXTTRAITS_CONTENT_HASH_SECRET", "").strip()
    if APP_SECRET.startswith(("dev-", "replace-")):
        message = "TEXTTRAITS_SECRET_KEY must be a real high-entropy secret."
        if PRODUCTION:
            failures.append(message)
        else:
            logging.warning(message)
    if PRODUCTION and hubspot_secret and len(hubspot_secret) < 32:
        failures.append("TEXTTRAITS_HUBSPOT_INGRESS_SECRET must be at least 32 characters in production.")
    if PRODUCTION and env_flag("TEXTTRAITS_REQUIRE_HUBSPOT_INGRESS_AUTH", False) and not hubspot_secret:
        failures.append("TEXTTRAITS_HUBSPOT_INGRESS_SECRET is required when TEXTTRAITS_REQUIRE_HUBSPOT_INGRESS_AUTH=true.")
    if PRODUCTION and content_hash_secret and len(content_hash_secret) < 32:
        failures.append("TEXTTRAITS_CONTENT_HASH_SECRET must be at least 32 characters in production.")
    if PRODUCTION:
        public_origin = urlparse(PUBLIC_BASE_URL)
        public_hostname = (public_origin.hostname or "").lower()
        if public_origin.scheme != "https":
            failures.append("TEXTTRAITS_PUBLIC_BASE_URL must use HTTPS in production.")
        if not public_origin.netloc:
            failures.append("TEXTTRAITS_PUBLIC_BASE_URL must include a public host.")
        if public_hostname in LOCAL_PUBLIC_HOSTS:
            failures.append("TEXTTRAITS_PUBLIC_BASE_URL cannot point to localhost in production.")
        if TRUSTED_PUBLIC_HOSTS and public_hostname not in TRUSTED_PUBLIC_HOSTS:
            failures.append("TEXTTRAITS_PUBLIC_BASE_URL host must be listed in TEXTTRAITS_ALLOWED_PUBLIC_HOSTS.")
        if ENABLE_DEV_TOOLS:
            failures.append("ENABLE_DEV_TOOLS must be false in production.")
        if ALLOW_DEMO_MODE:
            failures.append("TEXTTRAITS_ALLOW_DEMO must be false in production.")
        if ALLOW_DEV_ACCOUNT_LINKS:
            failures.append("TEXTTRAITS_DEV_ACCOUNT_LINKS must be false in production.")
        if not env_flag("TEXTTRAITS_SECURE_COOKIES", False):
            failures.append("TEXTTRAITS_SECURE_COOKIES=true is required in production.")
        if database_backend() != "postgres":
            failures.append("Production requires DATABASE_URL or TEXTTRAITS_DATABASE_URL for hosted Postgres.")
        elif "sslmode=require" not in database_url():
            failures.append("Production Postgres must use SSL. Set TEXTTRAITS_DB_SSLMODE=require or include sslmode=require.")
        if not email_status()["configured"]:
            failures.append("Production requires TEXTTRAITS_EMAIL_PROVIDER with working SMTP or SendGrid settings.")
        elif email_status()["provider"] == "console":
            failures.append("Console email delivery is not allowed in production.")
        elif email_status()["provider"] == "smtp" and not env_flag("TEXTTRAITS_SMTP_TLS", True):
            failures.append("SMTP TLS must stay enabled in production.")
    if failures:
        raise RuntimeError("Invalid TextTraits production configuration: " + " ".join(failures))


validate_runtime_config()

AVAILABLE_MODELS = [
    {
        "id": "local",
        "name": "Local inference model",
        "available": True,
        "description": "Runtime model bundle",
    },
    {
        "id": "pandora_cloud",
        "name": "PANDORA cloud-trained",
        "available": False,
        "description": "Cloud model is not configured in this deployment",
    },
]


try:
    predictor = TextTraitsPredictor()
except FileNotFoundError as error:
    predictor = DemoPredictor(error) if ALLOW_DEMO_MODE else MissingPredictor(error)

app = Flask(__name__)
app.secret_key = APP_SECRET
if env_flag("TEXTTRAITS_TRUST_PROXY", False):
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
app.config["TEMPLATES_AUTO_RELOAD"] = ENABLE_DEV_TOOLS
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = env_flag("TEXTTRAITS_SECURE_COOKIES", False)
ERROR_REPORTING_STATUS = init_error_reporting(app)
init_db()

rate_buckets: dict[str, deque[float]] = defaultdict(deque)


def rate_limited(limit: int | None = None) -> Callable:
    max_calls = limit or RATE_LIMIT_PER_MINUTE

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            identity = f"user:{current_user_id()}" if current_user_id() else f"ip:{request.remote_addr or 'local'}"
            key = f"{identity}:{request.endpoint or fn.__name__}"
            now = time.time()
            bucket = rate_buckets[key]
            while bucket and now - bucket[0] > 60:
                bucket.popleft()
            if len(bucket) >= max_calls:
                return jsonify({"error": "Too many requests. Please wait a moment and try again."}), 429
            bucket.append(now)
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def current_user_id() -> int | None:
    value = session.get("user_id")
    if not value:
        return None
    try:
        user_id = int(value)
    except (TypeError, ValueError):
        session.clear()
        return None
    expected_version = user_session_version(user_id)
    if expected_version is None or session.get("session_version") != expected_version:
        csrf = session.get("csrf_token")
        session.clear()
        if csrf:
            session["csrf_token"] = csrf
        return None
    return user_id


def csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def start_user_session(user: dict) -> None:
    csrf = csrf_token()
    session.clear()
    session["csrf_token"] = csrf
    session["user_id"] = int(user["id"])
    session["session_version"] = user_session_version(int(user["id"])) or 0


def confirmed_password(user_id: int, password: str) -> bool:
    user = get_user_by_id(user_id)
    if not user or not password:
        return False
    return bool(authenticate_user(user["email"], password))


def password_policy_error(password: str, email: str = "") -> str | None:
    clean = password.strip()
    if len(clean) < 12:
        return "Use at least 12 characters for the password."
    local_part = email.split("@", 1)[0].lower() if "@" in email else ""
    if clean.lower() in COMMON_PASSWORDS or (local_part and local_part in clean.lower()):
        return "Use a less guessable password."
    return None


def require_user() -> tuple[int | None, tuple | None]:
    user_id = current_user_id()
    if not user_id:
        return None, (jsonify({"error": "Please sign in to sync this workspace."}), 401)
    user = get_user_by_id(user_id)
    if not user or not user.get("email_verified"):
        csrf = session.get("csrf_token")
        session.clear()
        if csrf:
            session["csrf_token"] = csrf
        return None, (jsonify({"error": "Verify your email before using account sync."}), 403)
    return user_id, None


def require_enterprise_admin() -> tuple[int | None, tuple | None]:
    user_id, error = require_user()
    if error:
        return None, error
    admin_allowlist_required = PRODUCTION or env_flag("TEXTTRAITS_REQUIRE_ENTERPRISE_ADMIN_ALLOWLIST", False)
    if admin_allowlist_required and not ENTERPRISE_ADMIN_EMAILS:
        return None, (jsonify({"error": "Configure TEXTTRAITS_ENTERPRISE_ADMIN_EMAILS before enabling enterprise admin endpoints in this environment."}), 503)
    if not ENTERPRISE_ADMIN_EMAILS:
        return user_id, None
    user = get_user_by_id(user_id)
    email = str((user or {}).get("email", "")).strip().lower()
    if email not in ENTERPRISE_ADMIN_EMAILS:
        return None, (jsonify({"error": "Enterprise admin access is required."}), 403)
    return user_id, None


def public_url(path: str) -> str:
    return f"{PUBLIC_BASE_URL.rstrip('/')}/{path.lstrip('/')}"


def oauth_completion_page(title: str, message: str, status: int = 200):
    return (
        render_template_string(
            """
            <!doctype html>
            <html lang="en">
              <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <title>{{ title }}</title>
                <link rel="stylesheet" href="/static/styles.css">
              </head>
              <body>
                <main class="legal-page">
                  <h1>{{ title }}</h1>
                  <p>{{ message }}</p>
                  <p>You can close this tab and return to HubSpot.</p>
                </main>
              </body>
            </html>
            """,
            title=title,
            message=message,
        ),
        status,
    )


def marketplace_install_user(entry, token_payload: dict, state: str) -> dict:
    portal_id = str(token_payload.get("hub_id") or token_payload.get("hub_domain") or state or "unknown").strip()
    safe_portal_id = "".join(ch for ch in portal_id if ch.isalnum() or ch in {"-", "_"})[:80] or "unknown"
    user = upsert_oauth_user(
        f"hubspot-install-{safe_portal_id}@integrations.texttraits.local",
        f"HubSpot install {safe_portal_id}",
        provider=entry.name,
    )
    config = {
        "connected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "marketplace_install": True,
        "hubspot_portal_id": token_payload.get("hub_id"),
        "hubspot_domain": token_payload.get("hub_domain"),
        "token_type": token_payload.get("token_type"),
        "expires_in": token_payload.get("expires_in"),
        "scope": token_payload.get("scope"),
        "tokens_stored": bool(token_storage_status()["ready"] and (token_payload.get("access_token") or token_payload.get("refresh_token"))),
    }
    try:
        portal_connection = save_hubspot_portal_tokens(token_payload, installed_by=user["email"])
        config["portal_connection_status"] = portal_connection.get("status")
        config["tokens_available"] = portal_connection.get("tokens_available")
    except Exception:
        logging.exception("hubspot_portal_token_store_failed")
        if os.getenv("TEXTTRAITS_STORE_OAUTH_TOKENS", "").strip().lower() in {"1", "true", "yes", "on"}:
            raise
        config["portal_connection_status"] = "metadata_not_stored"
    return upsert_integration(user["id"], entry.name, "connected", config)


def send_verification_email(user: dict, token: str | None) -> dict:
    if not token:
        return {"sent": False, "provider": "already_verified"}
    url = public_url("/")
    safe_token = html_escape(token)
    safe_url = html_escape(url)
    try:
        return send_account_email(
            user["email"],
            "Your TextTraits verification code",
            f"Your TextTraits verification code is:\n\n{token}\n\nEnter this 6-digit code in TextTraits to create your account. Open TextTraits here: {url}\n\nIf you did not request this, you can ignore this email.",
            f"<p>Your TextTraits verification code is:</p><p><code>{safe_token}</code></p><p>Enter this 6-digit code in TextTraits to create your account.</p><p><a href=\"{safe_url}\">Open TextTraits</a></p>",
        )
    except Exception as error:
        logging.exception("verification_email_failed")
        return {"sent": False, "provider": email_status()["provider"], "error": str(error)}


def send_password_reset_email(email: str, token: str) -> dict:
    url = public_url("/")
    safe_token = html_escape(token)
    safe_url = html_escape(url)
    try:
        return send_account_email(
            email,
            "Reset your TextTraits password",
            f"Open TextTraits and enter this password reset code:\n\n{token}\n\nOpen TextTraits here: {url}\n\nThis code expires in one hour.",
            f"<p>Open TextTraits and enter this password reset code:</p><p><code>{safe_token}</code></p><p><a href=\"{safe_url}\">Open TextTraits</a></p><p>This code expires in one hour.</p>",
        )
    except Exception as error:
        logging.exception("password_reset_email_failed")
        return {"sent": False, "provider": email_status()["provider"], "error": str(error)}


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    nonce = getattr(g, "csp_nonce", "")
    script_src = f"'self' 'nonce-{nonce}'" if nonce else "'self'"
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        f"script-src {script_src} https://js.sentry-cdn.com; "
        "style-src 'self'; "
        "img-src 'self' data:; "
        "font-src 'self' data:; "
        "connect-src 'self' https://*.sentry.io; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'self'",
    )
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    if app.config["SESSION_COOKIE_SECURE"]:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


def request_origin_allowed() -> bool:
    if not PRODUCTION:
        return True
    public_origin = urlparse(PUBLIC_BASE_URL)
    header = request.headers.get("Origin") or request.headers.get("Referer")
    if not header:
        return False
    supplied = urlparse(header)
    allowed_netlocs = {public_origin.netloc, request.host}
    return supplied.scheme == public_origin.scheme and supplied.netloc in allowed_netlocs


def hubspot_public_ingress_path() -> bool:
    return request.method in {"POST", "OPTIONS"} and request.path in HUBSPOT_PUBLIC_INGRESS_PATHS


def hubspot_ingress_secret() -> str:
    return os.getenv("TEXTTRAITS_HUBSPOT_INGRESS_SECRET", "").strip()


def hubspot_ingress_auth_required() -> bool:
    return env_flag("TEXTTRAITS_REQUIRE_HUBSPOT_INGRESS_AUTH", False)


def hubspot_signature_timestamp_required() -> bool:
    return PRODUCTION or env_flag("TEXTTRAITS_REQUIRE_HUBSPOT_SIGNATURE_TIMESTAMP", False)


def hubspot_timestamp_error(timestamp_value: str) -> str | None:
    if not timestamp_value:
        return "HubSpot ingress timestamp is required."
    try:
        timestamp = int(timestamp_value)
    except ValueError:
        return "HubSpot ingress timestamp must be a Unix timestamp."
    age = abs(int(time.time()) - timestamp)
    if age > max(1, HUBSPOT_SIGNATURE_MAX_AGE_SECONDS):
        return "HubSpot ingress timestamp is outside the allowed replay window."
    return None


def hubspot_hmac_signature_matches(secret: str, body: bytes, supplied_signature: str) -> tuple[bool, dict[str, Any]]:
    timestamp_value = request.headers.get("X-TextTraits-Timestamp", "").strip()
    timestamp_required = hubspot_signature_timestamp_required()
    if timestamp_value or timestamp_required:
        timestamp_error = hubspot_timestamp_error(timestamp_value)
        if timestamp_error:
            return False, {"error": timestamp_error}
        signed_body = timestamp_value.encode("utf-8") + b"." + body
        expected = hmac.new(secret.encode("utf-8"), signed_body, hashlib.sha256).hexdigest()
        candidates = {expected, f"sha256={expected}"}
        if any(hmac.compare_digest(supplied_signature, candidate) for candidate in candidates):
            return True, {
                "mode": "hmac_sha256",
                "timestamped": True,
                "timestamp_age_seconds": abs(int(time.time()) - int(timestamp_value)),
            }
        return False, {"error": "HubSpot ingress timestamped signature was invalid."}

    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    candidates = {expected, f"sha256={expected}"}
    if any(hmac.compare_digest(supplied_signature, candidate) for candidate in candidates):
        return True, {"mode": "hmac_sha256", "timestamped": False}
    return False, {"error": "HubSpot ingress signature was missing or invalid."}


def hubspot_client_secret() -> str:
    return os.getenv("HUBSPOT_CLIENT_SECRET", "").strip()


def hubspot_request_body_text(body: bytes) -> str:
    return body.decode("utf-8", errors="replace") if body else ""


HUBSPOT_V3_QUERY_DECODE_MAP = {
    "%3A": ":",
    "%2F": "/",
    "%3F": "?",
    "%40": "@",
    "%21": "!",
    "%24": "$",
    "%27": "'",
    "%28": "(",
    "%29": ")",
    "%2A": "*",
    "%2C": ",",
    "%3B": ";",
}
HUBSPOT_V3_QUERY_DECODE_PATTERN = re.compile("|".join(re.escape(value) for value in HUBSPOT_V3_QUERY_DECODE_MAP), re.IGNORECASE)


def hubspot_raw_request_uri() -> str:
    raw_path = request.environ.get("RAW_URI") or request.environ.get("REQUEST_URI")
    if raw_path:
        raw_path = str(raw_path)
        if raw_path.startswith(("http://", "https://")):
            return raw_path.split("#", 1)[0]
        if raw_path.endswith("?"):
            raw_path = raw_path[:-1]
        return f"{request.url_root.rstrip('/')}{raw_path}".split("#", 1)[0]
    return request.url.split("#", 1)[0]


def hubspot_v3_signature_uri() -> str:
    uri = hubspot_raw_request_uri()
    query_pos = uri.find("?")
    if query_pos == -1:
        return uri
    path = uri[: query_pos + 1]
    query = uri[query_pos + 1 :]
    decoded_query = HUBSPOT_V3_QUERY_DECODE_PATTERN.sub(lambda match: HUBSPOT_V3_QUERY_DECODE_MAP[match.group(0).upper()], query)
    return path + decoded_query


def hubspot_signature_v3_matches(secret: str, body: bytes) -> tuple[bool, dict[str, Any]]:
    supplied_signature = request.headers.get("X-HubSpot-Signature-v3", "").strip()
    timestamp_value = request.headers.get("X-HubSpot-Request-Timestamp", "").strip()
    if not supplied_signature:
        return False, {"error": "HubSpot v3 signature is missing."}
    try:
        timestamp_ms = int(timestamp_value)
    except (TypeError, ValueError):
        return False, {"error": "HubSpot v3 timestamp is missing or invalid."}
    age_ms = abs(int(time.time() * 1000) - timestamp_ms)
    if age_ms > max(1, HUBSPOT_SIGNATURE_MAX_AGE_SECONDS) * 1000:
        return False, {"error": "HubSpot v3 signature timestamp is outside the allowed replay window."}
    raw_string = f"{request.method.upper()}{hubspot_v3_signature_uri()}{hubspot_request_body_text(body)}{timestamp_value}"
    expected = base64.b64encode(hmac.new(secret.encode("utf-8"), raw_string.encode("utf-8"), hashlib.sha256).digest()).decode("utf-8")
    if hmac.compare_digest(expected, supplied_signature):
        return True, {"mode": "hubspot_v3", "timestamped": True, "timestamp_age_seconds": round(age_ms / 1000, 3)}
    return False, {"error": "HubSpot v3 signature was invalid."}


def hubspot_signature_v2_matches(secret: str, body: bytes) -> tuple[bool, dict[str, Any]]:
    supplied_signature = request.headers.get("X-HubSpot-Signature", "").strip()
    if not supplied_signature:
        return False, {"error": "HubSpot v2 signature is missing."}
    raw_string = f"{secret}{request.method.upper()}{hubspot_raw_request_uri()}{hubspot_request_body_text(body)}"
    expected = hashlib.sha256(raw_string.encode("utf-8")).hexdigest()
    if hmac.compare_digest(expected, supplied_signature):
        return True, {"mode": "hubspot_v2", "timestamped": False}
    return False, {"error": "HubSpot v2 signature was invalid."}


def hubspot_platform_signature_error(body: bytes) -> tuple | None:
    has_v3 = bool(request.headers.get("X-HubSpot-Signature-v3"))
    has_v2 = bool(request.headers.get("X-HubSpot-Signature")) and request.headers.get("X-HubSpot-Signature-Version") == "v2"
    if not has_v3 and not has_v2:
        return None
    secret = hubspot_client_secret()
    if not secret:
        return jsonify({"error": "HUBSPOT_CLIENT_SECRET is required to validate HubSpot-signed requests."}), 503
    if has_v3:
        signature_ok, metadata = hubspot_signature_v3_matches(secret, body)
    else:
        signature_ok, metadata = hubspot_signature_v2_matches(secret, body)
    if signature_ok:
        g.hubspot_ingress_auth = metadata
        return None
    return jsonify({"error": metadata.get("error", "HubSpot signature was invalid.")}), 401


def hubspot_ingress_auth_error() -> tuple | None:
    secret = hubspot_ingress_secret()
    body = request.get_data(cache=True) or b""
    hubspot_signature_error = hubspot_platform_signature_error(body)
    if hubspot_signature_error:
        return hubspot_signature_error
    if getattr(g, "hubspot_ingress_auth", None):
        return None
    if not secret and not hubspot_ingress_auth_required():
        g.hubspot_ingress_auth = {"mode": "unsigned"}
        return None
    if not secret:
        return jsonify({"error": "HubSpot ingress authentication is required but TEXTTRAITS_HUBSPOT_INGRESS_SECRET is not configured."}), 503

    supplied_key = request.headers.get("X-TextTraits-API-Key", "")
    if supplied_key and hmac.compare_digest(supplied_key, secret):
        g.hubspot_ingress_auth = {"mode": "api_key"}
        return None

    supplied_signature = request.headers.get("X-TextTraits-Signature", "").strip()
    signature_ok, auth_metadata = hubspot_hmac_signature_matches(secret, body, supplied_signature)
    if supplied_signature and signature_ok:
        g.hubspot_ingress_auth = auth_metadata
        return None
    return jsonify({"error": auth_metadata.get("error", "HubSpot ingress signature was missing or invalid.")}), 401


@app.before_request
def protect_unsafe_requests():
    g.csp_nonce = secrets.token_urlsafe(16)
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    if hubspot_public_ingress_path():
        if request.content_length and request.content_length > HUBSPOT_MAX_INGRESS_BYTES:
            return jsonify({"error": f"HubSpot ingress payloads must stay under {HUBSPOT_MAX_INGRESS_BYTES} bytes."}), 413
        return hubspot_ingress_auth_error()
    if not request_origin_allowed():
        return jsonify({"error": "Request origin did not match this TextTraits deployment."}), 403
    expected = session.get("csrf_token")
    supplied = request.headers.get("X-CSRF-Token") or request.form.get("_csrf_token")
    if not expected or not supplied or not secrets.compare_digest(str(expected), str(supplied)):
        return jsonify({"error": "Security token expired. Refresh the page and try again."}), 419
    return None


@app.errorhandler(Exception)
def handle_exception(error: Exception):
    if isinstance(error, HTTPException):
        return jsonify({"error": error.description}), error.code or 500
    logging.exception("Unhandled application error")
    if ENABLE_DEV_TOOLS:
        raise error
    return jsonify({"error": "Something went wrong. Please retry in a moment."}), 500


def public_model_info() -> dict:
    return {
        "available": not isinstance(predictor, MissingPredictor),
        "demo": bool(getattr(predictor, "is_demo", False)),
        "name": "Demo predictor" if getattr(predictor, "is_demo", False) else "Local inference model",
        "target_count": len(getattr(predictor, "metadata", {}).get("targets", [])),
    }


def public_app_info() -> dict:
    return {
        "sync": True,
        "auth": True,
        "integrations_live": configured_integration_count() > 0,
        "google_auth": bool(GOOGLE_AUTH_CLIENT_ID),
        "google_client_id": GOOGLE_AUTH_CLIENT_ID,
        "max_text_words": MAX_TEXT_WORDS,
        "privacy_url": "/privacy",
        "terms_url": "/terms",
    }


def readiness_item(
    item_id: str,
    label: str,
    status: str,
    detail: str,
    next_step: str = "",
    area: str = "Platform",
) -> dict[str, str]:
    return {
        "id": item_id,
        "area": area,
        "label": label,
        "status": status,
        "detail": detail,
        "next_step": next_step,
    }


def configured_secret_length(name: str) -> int:
    return len(os.getenv(name, "").strip())


def enterprise_readiness_report() -> dict[str, Any]:
    public_origin = urlparse(PUBLIC_BASE_URL)
    public_hostname = (public_origin.hostname or "").lower()
    hubspot_provider = get_provider("HubSpot")
    hubspot_oauth_ready = bool(hubspot_provider and hubspot_provider.configured())
    hubspot_secret_length = configured_secret_length("TEXTTRAITS_HUBSPOT_INGRESS_SECRET")
    hubspot_project_root = Path(__file__).resolve().parents[1] / "hubspot-project"
    hubspot_project_ready = (hubspot_project_root / "hsproject.json").exists() and (hubspot_project_root / "src/app/app-hsmeta.json").exists()
    hubspot_token_status = token_storage_status()
    content_hash_secret_length = configured_secret_length("TEXTTRAITS_CONTENT_HASH_SECRET")
    email_delivery = email_status()
    db_backend = database_backend()
    db_ssl = db_backend == "postgres" and "sslmode=require" in database_url()
    checks = [
        readiness_item(
            "runtime_model",
            "Runtime model",
            "pass" if not isinstance(predictor, MissingPredictor) and not getattr(predictor, "is_demo", False) else "action_needed" if isinstance(predictor, MissingPredictor) else "warning",
            "Local model bundle is available." if not isinstance(predictor, MissingPredictor) and not getattr(predictor, "is_demo", False) else "The app is using demo or missing model behavior.",
            "Install or verify the production model bundle before pitching production usage." if isinstance(predictor, MissingPredictor) or getattr(predictor, "is_demo", False) else "",
            "Scoring",
        ),
        readiness_item(
            "score_validation",
            "Score validation harness",
            "pass",
            "Built-in clear, vague, and risky email cases can be run from the admin console.",
            "Use customer-approved historical examples later for outcome validation.",
            "Scoring",
        ),
        readiness_item(
            "environment",
            "Production environment",
            "pass" if PRODUCTION else "warning",
            "TEXTTRAITS_ENV is production." if PRODUCTION else "This deployment is running outside production mode.",
            "Set TEXTTRAITS_ENV=production for the real enterprise demo environment." if not PRODUCTION else "",
            "Deployment",
        ),
        readiness_item(
            "public_url_https",
            "Public HTTPS URL",
            "pass" if public_origin.scheme == "https" and public_hostname not in LOCAL_PUBLIC_HOSTS else "action_needed" if PRODUCTION else "warning",
            "Public base URL uses HTTPS and a non-local host." if public_origin.scheme == "https" and public_hostname not in LOCAL_PUBLIC_HOSTS else "Public base URL is local or not HTTPS.",
            "Configure TEXTTRAITS_PUBLIC_BASE_URL to the deployed HTTPS URL.",
            "Deployment",
        ),
        readiness_item(
            "database",
            "Hosted database",
            "pass" if db_backend == "postgres" and db_ssl else "action_needed" if PRODUCTION else "warning",
            "Hosted Postgres is configured with SSL." if db_backend == "postgres" and db_ssl else f"Current backend is {db_backend}; production needs hosted Postgres with SSL.",
            "Set DATABASE_URL or TEXTTRAITS_DATABASE_URL with sslmode=require before production.",
            "Data",
        ),
        readiness_item(
            "email_delivery",
            "Transactional email",
            "pass" if email_delivery.get("configured") and email_delivery.get("provider") != "console" else "action_needed" if PRODUCTION else "warning",
            f"Email provider: {email_delivery.get('provider', 'unknown')}.",
            "Configure SMTP or SendGrid so verification and reset flows work outside local development.",
            "Identity",
        ),
        readiness_item(
            "admin_allowlist",
            "Enterprise admin allowlist",
            "pass" if ENTERPRISE_ADMIN_EMAILS else "action_needed" if PRODUCTION or env_flag("TEXTTRAITS_REQUIRE_ENTERPRISE_ADMIN_ALLOWLIST", False) else "warning",
            f"{len(ENTERPRISE_ADMIN_EMAILS)} admin email{'s' if len(ENTERPRISE_ADMIN_EMAILS) != 1 else ''} configured.",
            "Set TEXTTRAITS_ENTERPRISE_ADMIN_EMAILS to the real admin users for the demo or pilot.",
            "Access control",
        ),
        readiness_item(
            "secure_cookies",
            "Secure session cookies",
            "pass" if app.config["SESSION_COOKIE_SECURE"] else "action_needed" if PRODUCTION else "warning",
            "Secure cookies are enabled." if app.config["SESSION_COOKIE_SECURE"] else "Secure cookies are disabled for this local/dev run.",
            "Set TEXTTRAITS_SECURE_COOKIES=true behind HTTPS.",
            "Access control",
        ),
        readiness_item(
            "hubspot_oauth",
            "HubSpot OAuth credentials",
            "pass" if hubspot_oauth_ready else "action_needed",
            "HubSpot OAuth client credentials are configured." if hubspot_oauth_ready else "HubSpot OAuth client credentials are not configured in this deployment.",
            "Add the real HubSpot client ID and secret in the deployment environment.",
            "Integrations",
        ),
        readiness_item(
            "hubspot_project",
            "HubSpot developer project",
            "pass" if hubspot_project_ready else "action_needed",
            "HubSpot project scaffold is present with app config, UI extension card, workflow action, settings, and home page." if hubspot_project_ready else "HubSpot project scaffold is missing.",
            "Run `npm run validate` in hubspot-project and upload with the HubSpot CLI before a live pilot." if hubspot_project_ready else "Add hubspot-project/ with hsproject.json and app feature files.",
            "Integrations",
        ),
        readiness_item(
            "hubspot_token_storage",
            "HubSpot OAuth token storage",
            "pass" if hubspot_token_status.get("ready") else "action_needed" if PRODUCTION or hubspot_token_status.get("enabled") else "warning",
            "Encrypted per-portal HubSpot token storage is ready." if hubspot_token_status.get("ready") else "Per-portal HubSpot token storage is not fully enabled with a Fernet encryption key.",
            "Set TEXTTRAITS_STORE_OAUTH_TOKENS=true and TEXTTRAITS_TOKEN_ENCRYPTION_KEY before using live campaign/email/task/list APIs.",
            "Integrations",
        ),
        readiness_item(
            "hubspot_ingress_auth",
            "HubSpot ingress authentication",
            "pass" if hubspot_secret_length >= 32 else "action_needed" if PRODUCTION or hubspot_ingress_auth_required() else "warning",
            "HubSpot ingress shared secret is configured with production length." if hubspot_secret_length >= 32 else "HubSpot ingress shared secret is missing or shorter than production guidance.",
            "Set TEXTTRAITS_HUBSPOT_INGRESS_SECRET and require timestamped HMAC signatures.",
            "Integrations",
        ),
        readiness_item(
            "hubspot_surface_coverage",
            "HubSpot surface coverage",
            "pass",
            "CRM card, workflow action, marketing-email preflight, campaign batch preflight, live campaign review, campaign create/update, asset association, draft sync, tasks, writeback, property provisioning, analysis schema provisioning, lists, timeline events, webhook ingest/management, stats sync, template test, and outcome joins are implemented as mapped backend surfaces.",
            "Map the installed HubSpot app or workflow actions to the surfaces that match the prospect's HubSpot plan.",
            "Integrations",
        ),
        readiness_item(
            "content_hash_secret",
            "Tenant-scoped content hashing",
            "pass" if content_hash_secret_length >= 32 else "warning",
            "A deployment-specific content-hash secret is configured." if content_hash_secret_length >= 32 else "Content hashes currently fall back to the app secret.",
            "Set TEXTTRAITS_CONTENT_HASH_SECRET to a separate high-entropy secret.",
            "Data",
        ),
        readiness_item(
            "oauth_token_storage",
            "OAuth token storage",
            "warning" if env_flag("TEXTTRAITS_STORE_OAUTH_TOKENS", False) else "pass",
            "OAuth tokens are not persisted by default." if not env_flag("TEXTTRAITS_STORE_OAUTH_TOKENS", False) else "OAuth token persistence is enabled.",
            "Keep token storage disabled until encryption and key-management are reviewed.",
            "Data",
        ),
        readiness_item(
            "dev_tools",
            "Developer tools",
            "pass" if not ENABLE_DEV_TOOLS else "action_needed" if PRODUCTION else "warning",
            "Developer tools are disabled." if not ENABLE_DEV_TOOLS else "Developer tools are enabled for this environment.",
            "Set ENABLE_DEV_TOOLS=false before any external demo that should look production-like.",
            "Deployment",
        ),
        readiness_item(
            "demo_mode",
            "Demo mode",
            "pass" if not ALLOW_DEMO_MODE else "action_needed" if PRODUCTION else "warning",
            "Demo mode is disabled." if not ALLOW_DEMO_MODE else "Demo mode is enabled.",
            "Set TEXTTRAITS_ALLOW_DEMO=false for production and customer pilots.",
            "Deployment",
        ),
        readiness_item(
            "error_reporting",
            "Error reporting",
            "pass" if ERROR_REPORTING_STATUS.get("configured") else "warning",
            f"Error reporting provider: {ERROR_REPORTING_STATUS.get('provider', 'not_configured')}.",
            "Configure Sentry or an equivalent error-reporting sink for production support.",
            "Operations",
        ),
        readiness_item(
            "retention_controls",
            "Retention controls",
            "pass",
            "Admin-only dry-run and purge controls are available for HubSpot analysis records.",
            "Set the customer retention window during pilot onboarding.",
            "Data",
        ),
    ]
    counts: dict[str, int] = {}
    for item in checks:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    production_blockers = [item for item in checks if item["status"] == "action_needed"]
    pilot_warnings = [item for item in checks if item["status"] == "warning"]
    return {
        "generated_at": analyzedTimeForServer(),
        "environment": "production" if PRODUCTION else "non-production",
        "production_ready": not production_blockers,
        "pilot_ready": not isinstance(predictor, MissingPredictor),
        "counts": counts,
        "checks": checks,
        "production_blockers": production_blockers,
        "pilot_warnings": pilot_warnings,
    }


def hubspot_marketplace_readiness_report() -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[1]
    setup_guide_path = repo_root / "docs/hubspot_marketplace_setup_guide.md"
    privacy_path = repo_root / "docs/hubspot_reliability_security.md"
    app_config_path = repo_root / "hubspot-project/src/app/app-hsmeta.json"
    app_config: dict[str, Any] = {}
    if app_config_path.exists():
        try:
            app_config = json.loads(app_config_path.read_text())
        except json.JSONDecodeError:
            app_config = {}
    auth_config = app_config.get("config", {}).get("auth", {}) if isinstance(app_config.get("config"), dict) else {}
    required_scopes = auth_config.get("requiredScopes") if isinstance(auth_config.get("requiredScopes"), list) else []
    optional_scopes = auth_config.get("optionalScopes") if isinstance(auth_config.get("optionalScopes"), list) else []
    public_origin = urlparse(PUBLIC_BASE_URL)
    public_setup_url = f"{PUBLIC_BASE_URL.rstrip('/')}/hubspot/setup-guide" if PUBLIC_BASE_URL else ""
    checks = [
        readiness_item(
            "setup_guide",
            "Public setup guide",
            "pass" if setup_guide_path.exists() else "action_needed",
            f"Setup guide source exists at {setup_guide_path.relative_to(repo_root)}." if setup_guide_path.exists() else "HubSpot setup guide source is missing.",
            "Deploy `/hubspot/setup-guide` on the production HTTPS domain and use that URL in the HubSpot listing.",
            "Marketplace",
        ),
        readiness_item(
            "public_https_setup_url",
            "Setup guide URL",
            "pass" if public_origin.scheme == "https" and (public_origin.hostname or "").lower() not in LOCAL_PUBLIC_HOSTS else "action_needed",
            f"Current setup guide URL candidate: {public_setup_url or 'not configured'}.",
            "Set TEXTTRAITS_PUBLIC_BASE_URL to the verified production HTTPS domain before listing.",
            "Marketplace",
        ),
        readiness_item(
            "single_hubspot_project_app",
            "Single HubSpot app project",
            "pass" if app_config_path.exists() and app_config.get("uid") else "action_needed",
            f"HubSpot app UID: {app_config.get('uid', 'missing')}.",
            "Upload and manage the same HubSpot app ID that is tied to the Marketplace listing.",
            "Marketplace",
        ),
        readiness_item(
            "oauth_authorization_code",
            "OAuth authorization-code flow",
            "pass" if auth_config.get("type") == "oauth" else "action_needed",
            "HubSpot project app config declares OAuth." if auth_config.get("type") == "oauth" else "HubSpot project app config does not declare OAuth.",
            "Keep HubSpot OAuth as the only installation authorization flow for the public listing.",
            "Marketplace",
        ),
        readiness_item(
            "scope_justification",
            "Scope justification",
            "pass" if required_scopes and optional_scopes and setup_guide_path.exists() else "action_needed",
            f"{len(required_scopes)} required scopes and {len(optional_scopes)} optional scopes are documented in the setup guide.",
            "Remove scopes that are not used by active surfaces; keep conditional/deeper scopes optional.",
            "Marketplace",
        ),
        readiness_item(
            "privacy_security_notes",
            "Privacy and security notes",
            "pass" if privacy_path.exists() and setup_guide_path.exists() else "action_needed",
            "HubSpot reliability/security and setup-guide docs describe token encryption, audit logging, retention, and data handling.",
            "Publish privacy/security notes on the production domain before a Marketplace review.",
            "Marketplace",
        ),
        readiness_item(
            "disconnect_uninstall_docs",
            "Disconnect and uninstall behavior",
            "pass" if setup_guide_path.exists() else "action_needed",
            "Setup guide describes disconnect, uninstall callback, token clearing, and retained audit rows.",
            "Verify the uninstall callback in a live HubSpot portal after deploy.",
            "Marketplace",
        ),
        readiness_item(
            "active_installs",
            "Active unique installs",
            "external",
            "HubSpot listing/certification requires real active installs and app activity; this cannot be proven locally.",
            "Install the production app in real HubSpot portals and verify successful OAuth/API or signed extension activity.",
            "Marketplace",
        ),
        readiness_item(
            "verified_domain",
            "Verified domain",
            "external",
            "HubSpot Marketplace review expects a verified public domain; this cannot be proven from the local repo.",
            "Use the production TextTraits domain and verify it in HubSpot before listing.",
            "Marketplace",
        ),
    ]
    counts: dict[str, int] = {}
    for item in checks:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    return {
        "generated_at": analyzedTimeForServer(),
        "setup_guide_url": public_setup_url,
        "setup_guide_source": str(setup_guide_path),
        "required_scopes": required_scopes,
        "optional_scopes": optional_scopes,
        "hubspot_app_uid": app_config.get("uid", ""),
        "distribution": app_config.get("config", {}).get("distribution", "") if isinstance(app_config.get("config"), dict) else "",
        "counts": counts,
        "checks": checks,
        "sources": [
            "https://developers.hubspot.com/docs/apps/developer-platform/list-apps/listing-your-app/app-marketplace-listing-requirements",
            "https://developers.hubspot.com/docs/apps/developer-platform/list-apps/apply-for-certification/certification-requirements",
            "https://developers.hubspot.com/docs/apps/developer-platform/list-apps/listing-your-app/create-an-app-listing-setup-guide",
            "https://developers.hubspot.com/docs/apps/developer-platform/list-apps/understand-app-install-flow",
        ],
    }


def verify_google_identity_token(credential: str) -> dict[str, str]:
    if not GOOGLE_AUTH_CLIENT_ID:
        raise ValueError("Google sign-in is not configured for this deployment.")
    if not credential or len(credential) > 5000:
        raise ValueError("Google sign-in did not return a valid credential.")
    url = "https://oauth2.googleapis.com/tokeninfo?" + urlencode({"id_token": credential})
    with urllib.request.urlopen(url, timeout=8) as response:  # nosec B310
        profile = json.loads(response.read().decode("utf-8"))
    if profile.get("aud") != GOOGLE_AUTH_CLIENT_ID:
        raise ValueError("Google sign-in was issued for a different client.")
    if profile.get("iss") not in {"accounts.google.com", "https://accounts.google.com"}:
        raise ValueError("Google sign-in issuer was not recognized.")
    if str(profile.get("email_verified", "")).lower() != "true":
        raise ValueError("Google account email is not verified.")
    email = str(profile.get("email", "")).strip().lower()
    if "@" not in email:
        raise ValueError("Google sign-in did not include an email address.")
    return {
        "email": email,
        "name": str(profile.get("name") or profile.get("given_name") or "").strip(),
    }


def public_prediction_payload(predictions: dict) -> dict:
    """Remove raw model internals from the default public API response."""
    return scrub_public_value(predictions)


def prediction_confidences(value) -> list[float]:
    if isinstance(value, dict):
        values = []
        if isinstance(value.get("confidence"), (int, float)):
            values.append(float(value["confidence"]))
        for child in value.values():
            values.extend(prediction_confidences(child))
        return values
    if isinstance(value, list):
        values = []
        for item in value:
            values.extend(prediction_confidences(item))
        return values
    return []


def clamp_int(value: Any, low: int, high: int, fallback: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(low, min(high, number))


def normalized_policy_list(value: Any, fallback: Any = (), limit: int = 40) -> list[str]:
    if isinstance(value, str):
        raw_items = re.split(r"[\n,]+", value)
    elif isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    else:
        raw_items = list(fallback or [])
    items: list[str] = []
    for raw_item in raw_items:
        clean = re.sub(r"\s+", " ", str(raw_item or "").strip().lower())[:80]
        if clean and clean not in items:
            items.append(clean)
        if len(items) >= limit:
            break
    return items


def combined_policy_phrases(base: Any, custom: Any, limit: int = 80) -> list[str]:
    return normalized_policy_list([*normalized_policy_list(base, limit=limit), *normalized_policy_list(custom, limit=limit)], limit=limit)


def normalized_hubspot_email_policy(raw_policy: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = dict(DEFAULT_HUBSPOT_EMAIL_POLICY)
    env_policy = os.getenv("TEXTTRAITS_HUBSPOT_EMAIL_POLICY_JSON", "").strip()
    if env_policy:
        try:
            loaded = json.loads(env_policy)
            if isinstance(loaded, dict):
                policy.update(loaded)
        except json.JSONDecodeError:
            logging.warning("invalid_hubspot_email_policy_env")
    if isinstance(raw_policy, dict):
        policy.update(raw_policy)
    clean: dict[str, Any] = {"version": str(policy.get("version") or DEFAULT_HUBSPOT_EMAIL_POLICY["version"])[:80]}
    rule_pack = re.sub(r"[^a-z0-9_]+", "_", str(policy.get("rule_pack") or "general").strip().lower())[:80]
    if rule_pack not in HUBSPOT_EMAIL_RULE_PACKS:
        rule_pack = "general"
    pack = HUBSPOT_EMAIL_RULE_PACKS[rule_pack]
    clean["rule_pack"] = rule_pack
    clean["rule_pack_label"] = pack["label"]
    for key in HUBSPOT_POLICY_BOOLEAN_KEYS:
        clean[key] = bool(policy.get(key, DEFAULT_HUBSPOT_EMAIL_POLICY[key]))
    for key, (low, high) in HUBSPOT_POLICY_INTEGER_BOUNDS.items():
        clean[key] = clamp_int(policy.get(key), low, high, DEFAULT_HUBSPOT_EMAIL_POLICY[key])
    clean["custom_risk_phrases"] = normalized_policy_list(policy.get("custom_risk_phrases"), (), limit=30)
    clean["custom_vague_phrases"] = normalized_policy_list(policy.get("custom_vague_phrases"), (), limit=30)
    clean["risk_phrases"] = combined_policy_phrases(pack.get("risk_phrases"), clean["custom_risk_phrases"], limit=90)
    clean["vague_phrases"] = combined_policy_phrases(pack.get("vague_phrases"), clean["custom_vague_phrases"], limit=90)
    clean["required_template_tokens"] = normalized_policy_list(
        policy.get("required_template_tokens"),
        pack.get("required_template_tokens", ()),
        limit=20,
    )
    clean["required_headers"] = normalized_policy_list(
        policy.get("required_headers"),
        pack.get("required_headers", ()),
        limit=20,
    )
    if clean["max_body_words"] <= clean["min_body_words"]:
        clean["max_body_words"] = min(1200, clean["min_body_words"] + 1)
    if clean["ready_score_threshold"] < clean["review_score_threshold"]:
        clean["ready_score_threshold"] = clean["review_score_threshold"]
    if clean["review_score_threshold"] < clean["block_score_threshold"]:
        clean["review_score_threshold"] = clean["block_score_threshold"]
    return clean


def hubspot_policy_for_request(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    workspace_id = safe_hubspot_identifier(payload.get("workspace_id") or context.get("workspace_id") or "default", "default")
    environment = safe_hubspot_identifier(payload.get("environment") or payload.get("analysis_environment") or "production", "production", limit=80).lower()
    saved = get_hubspot_policy_config(workspace_id, environment)
    if saved is None and workspace_id != "default":
        saved = get_hubspot_policy_config("default", environment)
    raw_policy = saved["policy"] if saved else {}
    policy = normalized_hubspot_email_policy(raw_policy)
    policy["workspace_id"] = workspace_id
    policy["environment"] = environment
    policy["source"] = "saved" if saved else "default"
    return policy


def safe_hubspot_identifier(value: Any, default: str = "", limit: int = 160) -> str:
    clean = SAFE_HUBSPOT_ID_RE.sub("_", str(value or "").strip()).strip("_")
    if not clean:
        clean = default
    return clean[:limit]


def hubspot_content_hash(text: str, workspace_id: str) -> str:
    secret = (os.getenv("TEXTTRAITS_CONTENT_HASH_SECRET") or APP_SECRET).strip()
    key = secret.encode("utf-8")
    tenant_scoped_text = f"{workspace_id}\0{text}".encode("utf-8")
    return "hmac-sha256:" + hmac.new(key, tenant_scoped_text, hashlib.sha256).hexdigest()


def hubspot_idempotent_request_id(workflow: str, workspace_id: str, idempotency_key: str) -> str:
    digest = hmac.new(
        APP_SECRET.encode("utf-8"),
        f"{workspace_id}:{workflow}:{idempotency_key}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:28]
    return f"{workflow}-{digest}"


def public_hubspot_policy(policy: dict[str, Any]) -> dict[str, Any]:
    safe_keys = (
        "version",
        "rule_pack",
        "rule_pack_label",
        "ready_score_threshold",
        "review_score_threshold",
        "block_score_threshold",
        "block_if_no_cta",
        "block_high_severity_findings",
        "compliance_review_on_risk_terms",
        "require_personalization",
        "min_body_words",
        "max_body_words",
        "required_template_tokens",
        "required_headers",
        "workspace_id",
        "environment",
        "source",
    )
    return {key: scrub_public_value(policy.get(key)) for key in safe_keys if key in policy}


def public_hubspot_context(context: dict[str, Any]) -> dict[str, Any]:
    safe_keys = (
        "workspace_id",
        "tenant_id",
        "source_system",
        "workflow",
        "analysis_mode",
        "campaign_id",
        "journey_id",
        "template_id",
        "contact_id",
        "company_id",
        "deal_id",
        "owner_id",
        "portal_id",
        "object_type",
        "object_id",
        "locale",
        "audience_type",
        "region",
        "business_unit",
        "job_id",
        "job_family",
        "skill_family",
        "recruiter",
        "recruiter_id",
        "client_account",
        "client_account_id",
        "candidate_status",
        "ats_system",
        "job_board",
        "source_channel",
        "salesforce_campaign_id",
        "salesforce_opportunity_id",
        "salesforce_lead_id",
        "salesforce_contact_id",
    )
    safe_context = {key: scrub_public_value(context.get(key)) for key in safe_keys if context.get(key)}
    for object_key in ("headers", "consent_context", "delivery_context"):
        value = context.get(object_key)
        if isinstance(value, dict) and value:
            safe_context[object_key] = scrub_payload(value)
    ingress_auth = context.get("ingress_auth") if isinstance(context.get("ingress_auth"), dict) else {}
    safe_context["ingress_auth"] = {
        "mode": str(ingress_auth.get("mode") or "unknown"),
        "timestamped": bool(ingress_auth.get("timestamped", False)),
    }
    return safe_context


def public_hubspot_email_quality(email_quality: dict[str, Any]) -> dict[str, Any]:
    safe_quality = scrub_public_value({key: value for key, value in email_quality.items() if key != "policy"})
    safe_quality["policy"] = public_hubspot_policy(email_quality.get("policy") if isinstance(email_quality.get("policy"), dict) else {})
    return safe_quality


def email_word_count(text: str) -> int:
    return len(WORD_RE.findall(text or ""))


def email_sentence_count(text: str) -> int:
    fragments = [fragment.strip() for fragment in SENTENCE_RE.split(text or "") if fragment.strip()]
    return max(1, len(fragments)) if text.strip() else 0


def email_phrase_hits(text: str, phrases: tuple[str, ...]) -> list[str]:
    lowered = f" {text.lower()} "
    return [phrase for phrase in phrases if phrase in lowered]


def email_cta_hits(text: str) -> list[str]:
    return [label for label, pattern in EMAIL_CTA_PATTERNS.items() if pattern.search(text or "")]


def email_specific_anchors(text: str) -> list[str]:
    anchors: list[str] = []
    anchors.extend(match.group(0) for match in EMAIL_DATE_RE.finditer(text or ""))
    anchors.extend(match.group(0) for match in EMAIL_TIME_RE.finditer(text or ""))
    anchors.extend(match.group(0) for match in EMAIL_NUMBER_RE.finditer(text or ""))
    for match in EMAIL_PROPER_NOUN_RE.finditer(text or ""):
        token = match.group(0)
        if token.lower() not in {"hi", "hello", "dear", "thanks", "thank", "best"}:
            anchors.append(token)
    deduped: list[str] = []
    for anchor in anchors:
        clean = anchor.strip()
        if clean and clean.lower() not in {item.lower() for item in deduped}:
            deduped.append(clean)
    return deduped[:12]


def email_personalization_hits(subject: str, body: str, context: dict[str, Any] | None = None) -> list[str]:
    text = f"{subject}\n{body}"
    hits: list[str] = []
    if EMAIL_GREETING_RE.search(body or ""):
        hits.append("named greeting")
    if EMAIL_PLACEHOLDER_RE.search(text):
        hits.append("personalization token")
    if re.search(r"\b(your|you|your team|for your)\b", text, re.IGNORECASE):
        hits.append("recipient-focused wording")
    context = context or {}
    for label, value in (("contact context", context.get("contact_name")), ("company context", context.get("company_name"))):
        clean = str(value or "").strip()
        if len(clean) >= 3 and re.search(rf"\b{re.escape(clean)}\b", text, re.IGNORECASE):
            hits.append(label)
    return hits


def email_finding(
    finding_id: str,
    severity: str,
    title: str,
    detail: str,
    evidence: list[str],
    next_step: str,
    owner_queue: str,
    blocker_level: str,
    action: str,
) -> dict[str, Any]:
    return {
        "id": finding_id,
        "severity": severity,
        "title": title,
        "detail": detail,
        "evidence": evidence,
        "next_step": next_step,
        "owner_queue": owner_queue,
        "blocker_level": blocker_level,
        "action": action,
    }


def email_check(
    check_id: str,
    label: str,
    weight: int,
    score: int,
    evidence: list[str],
    finding: dict[str, Any] | None = None,
    penalty: int = 0,
) -> dict[str, Any]:
    bounded_score = max(0, min(weight, int(round(score))))
    bounded_penalty = max(0, int(round(penalty)))
    if finding and finding["severity"] == "high":
        status = "blocked"
    elif bounded_score >= weight * 0.8 and finding is None:
        status = "pass"
    elif bounded_score >= weight * 0.5:
        status = "needs_review"
    else:
        status = "blocked" if weight >= 15 else "needs_review"
    return {
        "id": check_id,
        "label": label,
        "weight": weight,
        "score": bounded_score,
        "status": status,
        "evidence": evidence,
        "finding_id": finding["id"] if finding else None,
        "penalty": bounded_penalty,
    }


def email_subject_check(subject: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    subject_words = email_word_count(subject)
    subject_chars = len(subject.strip())
    if not subject.strip():
        finding = email_finding(
            "subject_missing",
            "high",
            "Subject is missing",
            "The draft cannot be routed safely without a subject line.",
            ["No subject text was provided."],
            "Add a short subject that matches the body.",
            "Marketing review",
            "High",
            "Write a concrete subject before running the draft again.",
        )
        return email_check("subject_clarity", "Subject clarity", 15, 0, ["Missing subject."], finding), finding
    if subject_words < 2 or subject_chars < 8:
        finding = email_finding(
            "subject_thin",
            "medium",
            "Subject is too thin",
            "The subject gives reviewers little information about why the email is being sent.",
            [f"{subject_words} subject word{'s' if subject_words != 1 else ''}."],
            "Make the subject name the topic or requested decision.",
            "Marketing review",
            "Medium",
            "Expand the subject with the concrete topic of the message.",
        )
        return email_check("subject_clarity", "Subject clarity", 15, 8, [f"{subject_words} words, {subject_chars} characters."], finding), finding
    if subject.strip().lower() in EMAIL_GENERIC_SUBJECTS:
        finding = email_finding(
            "subject_generic",
            "medium",
            "Subject is generic",
            "Generic subject lines make it harder for reviewers and recipients to understand the email purpose.",
            [f"Subject matched generic pattern: {subject.strip()}."],
            "Make the subject name the specific topic, decision, or date.",
            "Marketing review",
            "Medium",
            "Replace the generic subject before routing.",
        )
        return email_check("subject_clarity", "Subject clarity", 15, 8, [f"{subject_words} words, {subject_chars} characters.", "Generic subject detected."], finding), finding
    if subject_words > 14 or subject_chars > 90:
        finding = email_finding(
            "subject_long",
            "medium",
            "Subject may be too long",
            "Long subjects can be harder to scan in CRM and inbox workflows.",
            [f"{subject_words} words, {subject_chars} characters."],
            "Shorten the subject to the main topic and action.",
            "Marketing review",
            "Medium",
            "Trim the subject before routing this draft.",
        )
        return email_check("subject_clarity", "Subject clarity", 15, 10, [f"{subject_words} words, {subject_chars} characters."], finding), finding
    return email_check("subject_clarity", "Subject clarity", 15, 15, [f"{subject_words} words, {subject_chars} characters."]), None


def email_body_check(body: str, policy: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any] | None]:
    policy = policy or DEFAULT_HUBSPOT_EMAIL_POLICY
    words = email_word_count(body)
    min_body_words = int(policy.get("min_body_words", DEFAULT_HUBSPOT_EMAIL_POLICY["min_body_words"]))
    max_body_words = int(policy.get("max_body_words", DEFAULT_HUBSPOT_EMAIL_POLICY["max_body_words"]))
    if not body.strip():
        finding = email_finding(
            "body_missing",
            "high",
            "Body is missing",
            "The draft cannot be evaluated as an email without body text.",
            ["No body text was provided."],
            "Paste the existing email body before routing.",
            "Marketing review",
            "High",
            "Add body copy, then run TextTraits again.",
        )
        return email_check("body_completeness", "Body completeness", 15, 0, ["Missing body."], finding), finding
    if words < min_body_words:
        severity = "high" if words < 8 else "medium"
        finding = email_finding(
            "body_too_short",
            severity,
            "Body is too short for a reliable routing decision",
            "Very short drafts often omit context, reason, or next step.",
            [f"{words} body words.", f"Current policy minimum is {min_body_words} words."],
            "Add context and one clear next step.",
            "Marketing review",
            "High" if severity == "high" else "Medium",
            "Add the reason for the email and the action you want the recipient to take.",
        )
        return email_check("body_completeness", "Body completeness", 15, 5 if severity == "high" else 9, [f"{words} body words.", f"Policy minimum: {min_body_words}."], finding), finding
    if words > max_body_words:
        finding = email_finding(
            "body_too_long",
            "medium",
            "Body may be too long for CRM outreach",
            "Long drafts can bury the decision or requested action.",
            [f"{words} body words.", f"Current policy maximum is {max_body_words} words."],
            "Shorten the draft around the reason, context, and next step.",
            "Marketing review",
            "Medium",
            "Cut nonessential detail before routing.",
        )
        return email_check("body_completeness", "Body completeness", 15, 10, [f"{words} body words.", f"Policy maximum: {max_body_words}."], finding), finding
    return email_check("body_completeness", "Body completeness", 15, 15, [f"{words} body words."]), None


def email_next_step_check(text: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    cta_hits = email_cta_hits(text)
    time_hits = EMAIL_DATE_RE.findall(text or "") + EMAIL_TIME_RE.findall(text or "")
    if not cta_hits:
        finding = email_finding(
            "next_step_missing",
            "high",
            "No clear next step detected",
            "The draft does not include an explicit ask or routing action.",
            ["No reply, confirm, schedule, review, send, or choose cue was detected."],
            "Add one direct sentence that says what the recipient should do next.",
            "Marketing review",
            "High",
            "Add a concrete ask such as confirming a time, replying with approval, or reviewing a linked item.",
        )
        return email_check("next_step_clarity", "Next-step clarity", 20, 0, ["No CTA pattern detected."], finding), finding
    score = 20 if time_hits else 17
    evidence = [f"Detected action cue: {', '.join(cta_hits[:3])}."]
    if time_hits:
        evidence.append(f"Detected timing cue: {', '.join(str(item) for item in time_hits[:3])}.")
    else:
        evidence.append("No timing cue detected; action is present but not time-bound.")
    return email_check("next_step_clarity", "Next-step clarity", 20, score, evidence), None


def email_specificity_check(text: str, policy: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any] | None]:
    policy = policy or DEFAULT_HUBSPOT_EMAIL_POLICY
    anchors = email_specific_anchors(text)
    vague_hits = email_phrase_hits(text, tuple(policy.get("vague_phrases") or EMAIL_VAGUE_PHRASES))
    rule_pack_label = str(policy.get("rule_pack_label") or "General B2B")
    if len(anchors) >= 2 and not vague_hits:
        return email_check("specificity", "Specificity", 20, 20, [f"Concrete anchors: {', '.join(anchors[:5])}.", f"Rule pack: {rule_pack_label}."]), None
    if len(anchors) >= 1 and len(vague_hits) <= 1:
        return email_check("specificity", "Specificity", 20, 16, [f"Concrete anchors: {', '.join(anchors[:5])}.", f"Rule pack: {rule_pack_label}."]), None
    finding = email_finding(
        "specificity_low",
        "medium",
        "Draft needs more concrete detail",
        "The message has too few concrete anchors or too many vague phrases.",
        [
            f"{len(anchors)} concrete anchor{'s' if len(anchors) != 1 else ''} detected.",
            f"Vague phrases: {', '.join(vague_hits[:5]) if vague_hits else 'none detected'}.",
            f"Rule pack: {rule_pack_label}.",
        ],
        "Add a concrete date, topic, deliverable, person, or decision.",
        "Marketing review",
        "Medium",
        "Name the specific thing this email is about before routing.",
    )
    score = 3 if len(vague_hits) >= 3 else 5 if len(vague_hits) >= 2 else 10
    return email_check("specificity", "Specificity", 20, score, [f"{len(anchors)} concrete anchors.", f"{len(vague_hits)} vague phrases.", f"Rule pack: {rule_pack_label}."], finding), finding


def email_personalization_check(subject: str, body: str, context: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any] | None]:
    hits = email_personalization_hits(subject, body, context)
    if hits:
        return email_check("personalization", "Personalization", 10, 10, [f"Detected: {', '.join(hits)}."]), None
    finding = email_finding(
        "personalization_missing",
        "medium",
        "No personalization signal detected",
        "The draft does not include a named greeting, token, or recipient-focused wording.",
        ["No named greeting, personalization token, or recipient-focused wording was detected."],
        "Add the recipient name or one recipient-specific reference.",
        "Marketing review",
        "Medium",
        "Personalize the draft before adding it to an automated workflow.",
    )
    return email_check("personalization", "Personalization", 10, 4, ["No personalization signal detected."], finding), finding


def email_readability_check(body: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    words = email_word_count(body)
    sentences = email_sentence_count(body)
    avg_sentence_words = words / sentences if sentences else 0
    if not body.strip():
        return email_check("readability", "Readability", 10, 0, ["No body text."]), None
    if avg_sentence_words > 32:
        finding = email_finding(
            "sentences_long",
            "medium",
            "Sentences are too long to scan quickly",
            "Long average sentence length can make the email harder to review or act on.",
            [f"{avg_sentence_words:.1f} words per sentence on average."],
            "Break the draft into shorter sentences.",
            "Marketing review",
            "Medium",
            "Split long sentences before routing.",
        )
        return email_check("readability", "Readability", 10, 5, [f"{avg_sentence_words:.1f} words per sentence."], finding), finding
    if avg_sentence_words > 24:
        finding = email_finding(
            "sentences_dense",
            "low",
            "Sentences are a little dense",
            "The draft is readable, but shorter sentences would be easier to scan.",
            [f"{avg_sentence_words:.1f} words per sentence on average."],
            "Shorten one long sentence if this goes to a broad audience.",
            "Marketing review",
            "Low",
            "Make the copy easier to scan.",
        )
        return email_check("readability", "Readability", 10, 8, [f"{avg_sentence_words:.1f} words per sentence."], finding), finding
    return email_check("readability", "Readability", 10, 10, [f"{avg_sentence_words:.1f} words per sentence."]), None


def email_risk_check(text: str, policy: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any] | None]:
    policy = policy or DEFAULT_HUBSPOT_EMAIL_POLICY
    risk_hits = email_phrase_hits(text, tuple(policy.get("risk_phrases") or EMAIL_RISK_PHRASES))
    rule_pack_label = str(policy.get("rule_pack_label") or "General B2B")
    if not risk_hits:
        return email_check("risk_terms", "Risk terms", 10, 10, [f"No configured risk phrases detected for {rule_pack_label}."]), None
    severity = "high" if any(item in HUBSPOT_HIGH_RISK_PHRASES for item in risk_hits) or len(risk_hits) >= 2 else "medium"
    risk_penalty = 45 if severity == "high" else 25
    finding = email_finding(
        "risk_terms_detected",
        severity,
        "Risky claim or pressure phrase detected",
        "The draft contains wording that may need legal, compliance, or brand review.",
        [
            f"Detected phrase{'s' if len(risk_hits) != 1 else ''}: {', '.join(risk_hits[:5])}.",
            f"Rule pack: {rule_pack_label}.",
            f"Risk scoring penalty: {risk_penalty} points.",
        ],
        "Review or soften the claim before sending.",
        "Compliance review",
        "High" if severity == "high" else "Medium",
        "Remove or qualify risky language before routing.",
    )
    return email_check(
        "risk_terms",
        "Risk terms",
        10,
        0 if severity == "high" else 2,
        [f"Risk phrases: {', '.join(risk_hits[:5])}.", f"Rule pack: {rule_pack_label}.", f"Risk penalty: {risk_penalty} points."],
        finding,
        penalty=risk_penalty,
    ), finding


def email_decision_from_quality(score: int, findings: list[dict[str, Any]], checks: list[dict[str, Any]], policy: dict[str, Any]) -> dict[str, Any]:
    high_findings = [item for item in findings if item.get("severity") == "high"]
    medium_findings = [item for item in findings if item.get("severity") == "medium"]
    top_finding = high_findings[0] if high_findings else medium_findings[0] if medium_findings else findings[0] if findings else None
    check_statuses = {item.get("id"): item.get("status") for item in checks}
    has_missing_cta = any(item.get("id") == "next_step_missing" for item in findings)
    has_risk_terms = any(item.get("id") == "risk_terms_detected" for item in findings)
    ready_threshold = int(policy.get("ready_score_threshold", DEFAULT_HUBSPOT_EMAIL_POLICY["ready_score_threshold"]))
    block_threshold = int(policy.get("block_score_threshold", DEFAULT_HUBSPOT_EMAIL_POLICY["block_score_threshold"]))
    block_high = bool(policy.get("block_high_severity_findings", True))
    if bool(policy.get("compliance_review_on_risk_terms", True)) and has_risk_terms:
        risk_finding = next(item for item in findings if item.get("id") == "risk_terms_detected")
        gate = "blocked" if risk_finding.get("severity") == "high" else "needs_review"
        route = "Compliance review"
        label = "Blocked" if gate == "blocked" else "Needs review"
        score_meaning = "Routed by configured compliance-risk policy"
        blocker_level = risk_finding.get("blocker_level", "High" if gate == "blocked" else "Medium")
        top_finding = risk_finding
    elif bool(policy.get("block_if_no_cta", True)) and has_missing_cta:
        cta_finding = next(item for item in findings if item.get("id") == "next_step_missing")
        gate = "blocked"
        route = cta_finding.get("owner_queue", "Marketing review")
        label = "Blocked"
        score_meaning = "Blocked by configured missing-next-step policy"
        blocker_level = cta_finding.get("blocker_level", "High")
        top_finding = cta_finding
    elif (block_high and high_findings) or score < block_threshold:
        gate = "blocked"
        route = top_finding.get("owner_queue", "Compliance review") if top_finding else "Compliance review"
        label = "Blocked"
        score_meaning = "Blocked by a high-priority email-quality issue"
        blocker_level = top_finding.get("blocker_level", "High") if top_finding else "High"
    elif score >= ready_threshold and not medium_findings and (not policy.get("require_personalization") or check_statuses.get("personalization") == "pass"):
        gate = "ready"
        route = "Sending system"
        label = "Ready to route"
        score_meaning = "Meets current email-quality checks"
        blocker_level = "None"
    else:
        gate = "needs_review"
        route = top_finding.get("owner_queue", "Marketing review") if top_finding else "Marketing review"
        label = "Needs review"
        score_meaning = "Needs one or more quality fixes"
        blocker_level = top_finding.get("blocker_level", "Medium") if top_finding else "Medium"
    if top_finding:
        next_step = top_finding["next_step"]
        action = top_finding["action"]
        reason = top_finding["title"]
    else:
        next_step = "Proceed through the normal send path."
        action = "No configured email-quality issue was detected."
        reason = "All configured checks passed."
    return {
        "gate": gate,
        "label": label,
        "route": route,
        "owner_queue": route,
        "blocker_level": blocker_level,
        "next_step": next_step,
        "action": action,
        "score_meaning": score_meaning,
        "reason": reason,
        "policy_version": policy.get("version", DEFAULT_HUBSPOT_EMAIL_POLICY["version"]),
    }


def build_hubspot_email_quality(subject: str, body: str, text: str, policy: dict[str, Any] | None = None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = normalized_hubspot_email_policy(policy)
    check_builders = (
        lambda: email_subject_check(subject),
        lambda: email_body_check(body, policy),
        lambda: email_next_step_check(text),
        lambda: email_specificity_check(text, policy),
        lambda: email_personalization_check(subject, body, context),
        lambda: email_readability_check(body),
        lambda: email_risk_check(text, policy),
    )
    checks: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for builder in check_builders:
        check, finding = builder()
        checks.append(check)
        if finding:
            findings.append(finding)
    raw_score = sum(item["score"] for item in checks)
    scoring_penalties = [
        {
            "check_id": item["id"],
            "label": item["label"],
            "points": int(item.get("penalty", 0)),
            "evidence": item.get("evidence", []),
        }
        for item in checks
        if int(item.get("penalty", 0)) > 0
    ]
    total_penalty = sum(item["points"] for item in scoring_penalties)
    score = max(0, min(100, raw_score - total_penalty))
    decision = email_decision_from_quality(score, findings, checks, policy)
    return {
        "score": score,
        "raw_checklist_score": raw_score,
        "score_factors": {
            "checklist_points": raw_score,
            "total_penalty": total_penalty,
            "penalties": scoring_penalties,
            "final_score": score,
        },
        "score_source": "Weighted email-quality checks plus explicit risk penalties; not generated copy or a generic model-confidence average.",
        "weights": {item["id"]: item["weight"] for item in checks},
        "checks": checks,
        "findings": findings,
        "decision": decision,
        "policy": policy,
    }


def hubspot_score_validation_report(policy: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = normalized_hubspot_email_policy(policy)
    ready_threshold = int(policy.get("ready_score_threshold", DEFAULT_HUBSPOT_EMAIL_POLICY["ready_score_threshold"]))
    review_threshold = int(policy.get("review_score_threshold", DEFAULT_HUBSPOT_EMAIL_POLICY["review_score_threshold"]))
    cases = [
        {
            "id": "clear_send_ready",
            "name": "Clear send-ready draft",
            "subject": "Factory tour checklist",
            "body": (
                "Hi Brian, I wanted to confirm whether Wednesday still works for the factory tour. "
                "If it does, reply by Friday and I will send the short checklist your team can review before the visit."
            ),
            "expected_gates": ["ready"],
            "expected_min_score": ready_threshold,
            "expected_max_score": 100,
            "expected_findings": [],
        },
        {
            "id": "vague_review_or_block",
            "name": "Vague draft needing review",
            "subject": "Checking in",
            "body": (
                "Hi Brian, just checking in soon about things and stuff. "
                "Let me know when you get a chance."
            ),
            "expected_gates": ["needs_review", "blocked"],
            "expected_min_score": 0,
            "expected_max_score": max(review_threshold, 55),
            "expected_findings": ["specificity_low"],
        },
        {
            "id": "risky_compliance_route",
            "name": "Risky compliance language",
            "subject": "Guaranteed renewal savings",
            "body": (
                "Hi Brian, this renewal is guaranteed to save 100% of the time your team spends on the process. "
                "Please approve today so we can move forward."
            ),
            "expected_gates": ["needs_review", "blocked"],
            "expected_min_score": 0,
            "expected_max_score": max(49, int(policy.get("block_score_threshold", DEFAULT_HUBSPOT_EMAIL_POLICY["block_score_threshold"]))),
            "expected_findings": ["risk_terms_detected"],
        },
    ]
    results = []
    for case in cases:
        quality = build_hubspot_email_quality(
            case["subject"],
            case["body"],
            f"{case['subject']}\n\n{case['body']}",
            policy,
            context or {},
        )
        finding_ids = {str(item.get("id", "")) for item in quality["findings"]}
        actual_gate = str(quality["decision"]["gate"])
        actual_score = int(quality["score"])
        gate_ok = actual_gate in case["expected_gates"]
        score_ok = int(case["expected_min_score"]) <= actual_score <= int(case["expected_max_score"])
        findings_ok = all(expected in finding_ids for expected in case["expected_findings"])
        results.append(
            {
                "id": case["id"],
                "name": case["name"],
                "actual_gate": actual_gate,
                "actual_score": actual_score,
                "actual_route": quality["decision"]["route"],
                "expected_gates": case["expected_gates"],
                "expected_score_range": [case["expected_min_score"], case["expected_max_score"]],
                "expected_findings": case["expected_findings"],
                "detected_findings": sorted(finding_ids),
                "passed": bool(gate_ok and score_ok and findings_ok),
                "score_factors": quality["score_factors"],
            }
        )
    passed = sum(1 for item in results if item["passed"])
    return {
        "generated_at": analyzedTimeForServer(),
        "policy_version": policy.get("version"),
        "rule_pack": policy.get("rule_pack"),
        "rule_pack_label": policy.get("rule_pack_label"),
        "cases_total": len(results),
        "cases_passed": passed,
        "passed": passed == len(results),
        "cases": results,
        "note": "This validates configured routing behavior against built-in QA cases; it is not a substitute for customer outcome validation.",
    }


def scrub_public_value(value):
    if isinstance(value, dict):
        cleaned = {}
        for key, child in value.items():
            if key in {"raw_label", "raw_value", "available_targets"}:
                continue
            if key == "cue_terms":
                cleaned[key] = [
                    {"term": str(item.get("term", ""))}
                    for item in child
                    if isinstance(item, dict) and item.get("term")
                ][:6]
                continue
            cleaned[key] = scrub_public_value(child)
        return cleaned
    if isinstance(value, list):
        return [scrub_public_value(item) for item in value]
    return value


def sanitize_workspace_data(data: dict[str, Any]) -> dict[str, Any]:
    clean = {key: value for key, value in data.items() if key in ALLOWED_WORKSPACE_KEYS}
    # The frontend intentionally syncs only metadata/history. Keep raw pasted text out of cloud persistence.
    clean["latestText"] = ""
    return clean


def nested_value(source: Any, path: tuple[str, ...]) -> Any:
    current = source
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def first_text_value(*values: Any, max_length: int = 160) -> str:
    for value in values:
        if value is None:
            continue
        clean = str(value).strip()
        if clean:
            return clean[:max_length]
    return ""


def optional_context_object(*values: Any) -> dict[str, Any]:
    for value in values:
        if isinstance(value, dict):
            return scrub_payload(value)
    return {}


def first_dict_value(*values: Any) -> dict[str, Any]:
    for value in values:
        if isinstance(value, dict):
            return scrub_payload(value)
    return {}


def strip_html_to_text(value: Any) -> str:
    text = str(value or "")
    if "<" in text and ">" in text:
        text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text)
        text = re.sub(r"(?is)<br\s*/?>", "\n", text)
        text = re.sub(r"(?is)</(?:p|div|li|h[1-6])\s*>", "\n", text)
        text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html_unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s+", "\n", text)
    return text.strip()


def marketing_email_object_from_payload(payload: dict[str, Any], input_fields: dict[str, Any]) -> dict[str, Any]:
    return first_dict_value(
        payload.get("marketingEmail"),
        payload.get("marketing_email"),
        payload.get("email"),
        payload.get("asset"),
        input_fields.get("marketingEmail"),
        input_fields.get("marketing_email"),
        input_fields.get("email"),
        input_fields.get("asset"),
    )


def hubspot_marketing_headers(payload: dict[str, Any], input_fields: dict[str, Any], email: dict[str, Any]) -> dict[str, Any]:
    headers = optional_context_object(payload.get("headers"), input_fields.get("headers"), email.get("headers"))
    header_candidates = {
        "from": first_text_value(
            headers.get("from"),
            input_fields.get("from"),
            input_fields.get("from_email"),
            email.get("from"),
            email.get("fromEmail"),
            nested_value(email, ("from", "email")),
            max_length=160,
        ),
        "from_name": first_text_value(
            headers.get("from_name"),
            input_fields.get("from_name"),
            email.get("fromName"),
            nested_value(email, ("from", "name")),
            max_length=160,
        ),
        "reply_to": first_text_value(
            headers.get("reply_to"),
            headers.get("reply-to"),
            input_fields.get("reply_to"),
            input_fields.get("replyTo"),
            email.get("replyTo"),
            email.get("reply_to"),
            max_length=160,
        ),
    }
    for key, value in header_candidates.items():
        if value:
            headers[key] = value
    return scrub_payload(headers)


def normalize_hubspot_marketing_email_payload(payload: dict[str, Any], analysis_mode: str = "marketing_email_preflight") -> dict[str, Any]:
    input_fields = payload.get("inputFields") if isinstance(payload.get("inputFields"), dict) else {}
    email = marketing_email_object_from_payload(payload, input_fields)
    content = email.get("content") if isinstance(email.get("content"), dict) else {}
    subject = first_text_value(
        input_fields.get("subject"),
        input_fields.get("email_subject"),
        input_fields.get("hs_email_subject"),
        payload.get("subject"),
        payload.get("email_subject"),
        email.get("subject"),
        content.get("subject"),
        max_length=300,
    )
    body_source = first_text_value(
        input_fields.get("body"),
        input_fields.get("email_body"),
        input_fields.get("hs_email_body"),
        input_fields.get("html"),
        input_fields.get("html_body"),
        input_fields.get("email_html"),
        input_fields.get("text"),
        payload.get("body"),
        payload.get("email_body"),
        payload.get("html"),
        payload.get("html_body"),
        email.get("body"),
        email.get("emailBody"),
        email.get("html"),
        email.get("htmlBody"),
        email.get("richText"),
        email.get("text"),
        content.get("body"),
        content.get("html"),
        content.get("htmlBody"),
        max_length=HUBSPOT_MAX_INGRESS_BYTES,
    )
    body = strip_html_to_text(body_source)
    headers = hubspot_marketing_headers(payload, input_fields, email)
    delivery_context = optional_context_object(payload.get("delivery_context"), input_fields.get("delivery_context"), email.get("deliveryContext"))
    for key, value in {
        "status": first_text_value(input_fields.get("status"), payload.get("status"), email.get("state"), email.get("status"), max_length=80),
        "email_type": first_text_value(input_fields.get("email_type"), payload.get("email_type"), email.get("emailType"), email.get("type"), max_length=80),
        "subscription_type": first_text_value(input_fields.get("subscription_type"), email.get("subscriptionType"), nested_value(email, ("subscription", "name")), max_length=120),
    }.items():
        if value:
            delivery_context[key] = value
    normalized = {**payload}
    normalized_input = {**input_fields, "email_subject": subject, "email_body": body}
    normalized["inputFields"] = normalized_input
    normalized["source_system"] = first_text_value(payload.get("source_system"), input_fields.get("source_system"), "hubspot_marketing_email", max_length=80)
    normalized["analysis_mode"] = first_text_value(payload.get("analysis_mode"), input_fields.get("analysis_mode"), analysis_mode, max_length=80)
    normalized["campaign_id"] = first_text_value(
        payload.get("campaign_id"),
        payload.get("campaignId"),
        input_fields.get("campaign_id"),
        input_fields.get("campaignId"),
        email.get("campaign_id"),
        email.get("campaignId"),
        email.get("campaignGuid"),
        nested_value(email, ("campaign", "id")),
        nested_value(payload, ("campaign", "id")),
        max_length=160,
    )
    normalized["template_id"] = first_text_value(
        payload.get("template_id"),
        payload.get("templateId"),
        payload.get("email_id"),
        payload.get("emailId"),
        input_fields.get("template_id"),
        input_fields.get("templateId"),
        input_fields.get("email_id"),
        input_fields.get("emailId"),
        email.get("template_id"),
        email.get("templateId"),
        email.get("id"),
        email.get("emailId"),
        email.get("hs_email_id"),
        max_length=160,
    )
    normalized["journey_id"] = first_text_value(payload.get("journey_id"), payload.get("workflowId"), input_fields.get("journey_id"), email.get("workflowId"), email.get("automationId"), max_length=160)
    normalized["portal_id"] = first_text_value(payload.get("portal_id"), payload.get("portalId"), input_fields.get("portal_id"), email.get("portalId"), max_length=160)
    normalized["locale"] = first_text_value(payload.get("locale"), input_fields.get("locale"), email.get("language"), email.get("locale"), max_length=40)
    normalized["headers"] = headers
    normalized["delivery_context"] = delivery_context
    return normalized


def hubspot_campaign_context(payload: dict[str, Any]) -> dict[str, str]:
    campaign = payload.get("campaign") if isinstance(payload.get("campaign"), dict) else {}
    return {
        "campaign_id": first_text_value(payload.get("campaign_id"), payload.get("campaignId"), campaign.get("id"), campaign.get("guid"), campaign.get("campaignGuid"), max_length=160),
        "campaign_name": first_text_value(payload.get("campaign_name"), payload.get("name"), campaign.get("name"), campaign.get("title"), max_length=240),
        "portal_id": first_text_value(payload.get("portal_id"), payload.get("portalId"), campaign.get("portalId"), max_length=160),
    }


def hubspot_email_items_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("emails", "marketing_emails", "marketingEmails", "assets", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    if isinstance(payload.get("email"), dict) or isinstance(payload.get("marketingEmail"), dict) or payload.get("subject") or payload.get("email_subject"):
        return [payload]
    return []


def normalized_hubspot_asset_type(value: Any) -> str:
    clean = re.sub(r"[^A-Za-z0-9]+", "_", str(value or "").strip()).strip("_").upper()
    aliases = {
        "AD": "AD_CAMPAIGN",
        "ADS": "AD_CAMPAIGN",
        "ADS_CAMPAIGN": "AD_CAMPAIGN",
        "BLOG": "BLOG_POST",
        "BLOGS": "BLOG_POST",
        "BLOG_POSTS": "BLOG_POST",
        "CASE_STUDIES": "CASE_STUDY",
        "CASE_STUDY": "CASE_STUDY",
        "CTAS": "WEB_INTERACTIVE",
        "LEGACY_CTA": "CTA",
        "LEGACY_CTAS": "CTA",
        "EXTERNAL_PAGE": "EXTERNAL_WEB_URL",
        "EXTERNAL_WEBSITE_PAGE": "EXTERNAL_WEB_URL",
        "EXTERNAL_WEBSITE_PAGES": "EXTERNAL_WEB_URL",
        "FEEDBACK": "FEEDBACK_SURVEY",
        "FEEDBACK_SURVEYS": "FEEDBACK_SURVEY",
        "FILE": "FILE_MANAGER_FILE",
        "FILES": "FILE_MANAGER_FILE",
        "FORM_SUBMISSION": "FORM",
        "FORMS": "FORM",
        "KNOWLEDGE_ARTICLES": "KNOWLEDGE_ARTICLE",
        "KB_ARTICLE": "KNOWLEDGE_ARTICLE",
        "KB_ARTICLES": "KNOWLEDGE_ARTICLE",
        "LIST": "OBJECT_LIST",
        "LISTS": "OBJECT_LIST",
        "STATIC_LIST": "OBJECT_LIST",
        "STATIC_LISTS": "OBJECT_LIST",
        "OBJECT_LISTS": "OBJECT_LIST",
        "MARKETINGEMAIL": "MARKETING_EMAIL",
        "MARKETING_EMAILS": "MARKETING_EMAIL",
        "MARKETING_EVENT": "MARKETING_EVENT",
        "MARKETING_EVENTS": "MARKETING_EVENT",
        "MARKETING_SMS_MESSAGES": "MARKETING_SMS",
        "MEETING": "MEETING_EVENT",
        "MEETINGS": "MEETING_EVENT",
        "MEETING_EVENTS": "MEETING_EVENT",
        "PAGE": "SITE_PAGE",
        "PAGES": "SITE_PAGE",
        "PLAYBOOKS": "PLAYBOOK",
        "PODCAST": "PODCAST_EPISODE",
        "PODCASTS": "PODCAST_EPISODE",
        "PODCAST_EPISODES": "PODCAST_EPISODE",
        "SALES_DOCUMENTS": "SALES_DOCUMENT",
        "SALES_EMAIL": "EMAIL",
        "SALES_EMAILS": "EMAIL",
        "SEQUENCES": "SEQUENCE",
        "SITE_PAGES": "SITE_PAGE",
        "SMS": "MARKETING_SMS",
        "SMS_MESSAGES": "MARKETING_SMS",
        "SOCIAL": "SOCIAL_BROADCAST",
        "SOCIAL_POST": "SOCIAL_BROADCAST",
        "SOCIAL_POSTS": "SOCIAL_BROADCAST",
        "SOCIAL_BROADCASTS": "SOCIAL_BROADCAST",
        "VIDEO": "MEDIA",
        "VIDEOS": "MEDIA",
        "WEBSITE_PAGE": "SITE_PAGE",
        "WEBSITE_PAGES": "SITE_PAGE",
        "WEB_CTA": "WEB_INTERACTIVE",
        "WEB_CTAS": "WEB_INTERACTIVE",
        "WORKFLOW": "AUTOMATION_PLATFORM_FLOW",
        "WORKFLOWS": "AUTOMATION_PLATFORM_FLOW",
        "FLOW": "AUTOMATION_PLATFORM_FLOW",
        "FLOWS": "AUTOMATION_PLATFORM_FLOW",
        "AUTOMATION_FLOW": "AUTOMATION_PLATFORM_FLOW",
        "AUTOMATION_FLOWS": "AUTOMATION_PLATFORM_FLOW",
        "MARKETING": "MARKETING_EMAIL",
        "MARKETING_EMAIL": "MARKETING_EMAIL",
        "EMAIL_MARKETING": "MARKETING_EMAIL",
        "LANDINGPAGE": "LANDING_PAGE",
        "LANDING_PAGES": "LANDING_PAGE",
    }
    return aliases.get(clean, clean or "MARKETING_EMAIL")


def hubspot_asset_types_from_payload(payload: dict[str, Any]) -> list[str]:
    raw = payload.get("asset_types") if "asset_types" in payload else payload.get("assetTypes")
    if raw is None:
        raw = payload.get("asset_type") if "asset_type" in payload else payload.get("assetType")
    if isinstance(raw, str):
        parts = [item for item in re.split(r"[\s,]+", raw) if item.strip()]
    elif isinstance(raw, list):
        parts = [item for item in raw if str(item or "").strip()]
    else:
        parts = list(HUBSPOT_DEFAULT_CAMPAIGN_ASSET_TYPES)
    seen: set[str] = set()
    asset_types: list[str] = []
    for item in parts:
        clean = normalized_hubspot_asset_type(item)
        if clean not in seen:
            seen.add(clean)
            asset_types.append(clean)
    return asset_types[:12] or ["MARKETING_EMAIL"]


def hubspot_asset_id(asset: dict[str, Any]) -> str:
    return first_text_value(
        asset.get("id"),
        asset.get("assetId"),
        asset.get("objectId"),
        asset.get("emailId"),
        asset.get("guid"),
        asset.get("campaignAssetId"),
        nested_value(asset, ("asset", "id")),
        max_length=160,
    )


def hubspot_asset_label(asset: dict[str, Any], asset_type: str, asset_id: str = "") -> str:
    return first_text_value(
        asset.get("name"),
        asset.get("title"),
        asset.get("subject"),
        asset.get("label"),
        asset.get("path"),
        asset.get("url"),
        nested_value(asset, ("properties", "hs_name")),
        nested_value(asset, ("properties", "name")),
        nested_value(asset, ("asset", "name")),
        asset_id,
        HUBSPOT_CAMPAIGN_ASSET_TYPE_LABELS.get(asset_type, asset_type),
        max_length=240,
    )


def hubspot_asset_candidate_text(asset: dict[str, Any]) -> str:
    text_keys = {
        "subject",
        "name",
        "title",
        "label",
        "description",
        "metaDescription",
        "htmlTitle",
        "body",
        "html",
        "htmlBody",
        "richText",
        "plainTextVersion",
        "previewText",
        "emailBody",
        "email_body",
        "bodyPlainText",
        "stepBody",
        "taskBody",
        "text",
        "content",
        "postBody",
        "postSummary",
        "pageTitle",
        "submitText",
        "buttonText",
        "caption",
        "message",
    }
    chunks: list[str] = []

    def visit(value: Any, key: str = "", depth: int = 0) -> None:
        if depth > 3 or len(chunks) >= 18:
            return
        if isinstance(value, str):
            if key in text_keys or ("html" in key.lower()) or ("body" in key.lower()) or ("text" in key.lower()) or ("title" in key.lower()):
                clean = strip_html_to_text(value)
                if clean:
                    chunks.append(clean[:1200])
            return
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                visit(child_value, str(child_key), depth + 1)
        elif isinstance(value, list):
            for child in value[:12]:
                visit(child, key, depth + 1)

    visit(asset)
    return "\n".join(dict.fromkeys(chunk for chunk in chunks if chunk)).strip()


def hubspot_campaign_copy_coverage(asset_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    reviewed: set[str] = set()
    metadata_only: set[str] = set()
    fetch_errors: set[str] = set()
    analysis_errors: set[str] = set()
    by_type: dict[str, dict[str, Any]] = {}
    totals = {"assets": 0, "reviewed": 0, "metadata_only": 0, "fetch_errors": 0, "analysis_errors": 0}
    for asset_type, group in asset_map.items():
        assets = group.get("assets") if isinstance(group, dict) else []
        rows = assets if isinstance(assets, list) else []
        statuses = [str(row.get("status") or "unknown") for row in rows if isinstance(row, dict)]
        reviewed_count = statuses.count("analyzed")
        metadata_count = statuses.count("metadata_only")
        fetch_error_count = statuses.count("fetch_error")
        analysis_error_count = statuses.count("analysis_error")
        totals["assets"] += len(statuses)
        totals["reviewed"] += reviewed_count
        totals["metadata_only"] += metadata_count
        totals["fetch_errors"] += fetch_error_count
        totals["analysis_errors"] += analysis_error_count
        if "analyzed" in statuses:
            reviewed.add(asset_type)
        if "metadata_only" in statuses:
            metadata_only.add(asset_type)
        if "fetch_error" in statuses:
            fetch_errors.add(asset_type)
        if "analysis_error" in statuses:
            analysis_errors.add(asset_type)
        support = HUBSPOT_ASSET_COPY_SUPPORT.get(asset_type, {"level": "mapped_copy", "note": "Reviewable copy requires a mapped payload for this asset type."})
        by_type[asset_type] = {
            "label": HUBSPOT_CAMPAIGN_ASSET_TYPE_LABELS.get(asset_type, asset_type),
            "direct_copy_fetch": asset_type in HUBSPOT_DIRECT_COPY_ASSET_TYPES,
            "support_level": support.get("level"),
            "reviewed_assets": reviewed_count,
            "metadata_only_assets": metadata_count,
            "fetch_error_assets": fetch_error_count,
            "analysis_error_assets": analysis_error_count,
            "coverage_score": round((reviewed_count / len(statuses)) * 100, 1) if statuses else 0,
            "note": support.get("note"),
        }
    coverage_score = round((totals["reviewed"] / totals["assets"]) * 100, 1) if totals["assets"] else 0
    if coverage_score >= 90:
        coverage_label = "High campaign coverage"
    elif coverage_score >= 60:
        coverage_label = "Partial campaign coverage"
    elif totals["assets"]:
        coverage_label = "Low campaign coverage"
    else:
        coverage_label = "No campaign assets found"
    metadata_gap_assets = [
        {
            "asset_type": asset_type,
            "label": group.get("label", asset_type) if isinstance(group, dict) else asset_type,
            "support_level": (HUBSPOT_ASSET_COPY_SUPPORT.get(asset_type) or {}).get("level", "mapped_copy"),
            "metadata_only_assets": by_type.get(asset_type, {}).get("metadata_only_assets", 0),
            "note": (HUBSPOT_ASSET_COPY_SUPPORT.get(asset_type) or {}).get("note", "Mapped copy is required before TextTraits can score this asset type."),
        }
        for asset_type, group in asset_map.items()
        if by_type.get(asset_type, {}).get("metadata_only_assets", 0)
    ]
    return {
        "reviewed_asset_types": sorted(reviewed),
        "metadata_only_asset_types": sorted(metadata_only - reviewed),
        "direct_copy_fetch_asset_types": sorted(asset_type for asset_type in asset_map if asset_type in HUBSPOT_DIRECT_COPY_ASSET_TYPES),
        "mapped_copy_asset_types": sorted(asset_type for asset_type in asset_map if asset_type in HUBSPOT_MAPPED_COPY_ASSET_TYPES),
        "fetch_error_asset_types": sorted(fetch_errors),
        "analysis_error_asset_types": sorted(analysis_errors),
        "by_asset_type": by_type,
        "totals": totals,
        "coverage_score": coverage_score,
        "coverage_label": coverage_label,
        "coverage_gap_assets": metadata_gap_assets[:20],
        "note": "Marketing emails, forms, landing pages, site pages, blog posts, and sequences are fetched directly when HubSpot grants the needed API access. Ads, CTAs, workflows, marketing SMS, and social posts are scored when HubSpot returns reviewable copy or when a mapped copy payload is supplied; otherwise they remain metadata-only so coverage is not overstated.",
    }


def hubspot_campaign_asset_review_payload(
    base_payload: dict[str, Any],
    context: dict[str, Any],
    campaign_id: str,
    asset_type: str,
    asset: dict[str, Any],
    index: int,
    copy_source: str,
) -> dict[str, Any]:
    asset_id = hubspot_asset_id(asset)
    label = hubspot_asset_label(asset, asset_type, asset_id)
    subject = first_text_value(asset.get("subject"), asset.get("name"), asset.get("title"), label, max_length=300)
    body = hubspot_asset_candidate_text(asset)
    if body == subject:
        body = ""
    return normalize_hubspot_marketing_email_payload(
        {
            **base_payload,
            "portal_id": context.get("portal_id"),
            "campaign_id": campaign_id,
            "template_id": asset_id,
            "source_system": f"hubspot_{asset_type.lower()}",
            "analysis_mode": "live_campaign_asset_review",
            "marketingEmail": {"id": asset_id, "subject": subject, "html": body, "assetType": asset_type},
            "headers": base_payload.get("headers") if isinstance(base_payload.get("headers"), dict) else {},
            "delivery_context": {
                "asset_type": asset_type,
                "asset_name": label,
                "copy_source": copy_source,
            },
            "idempotency_key": hubspot_idempotency_key(base_payload, "campaign-asset-review", campaign_id, asset_type, asset_id, index),
        },
        "live_campaign_asset_review",
    )


def hubspot_asset_object_from_payload(payload: dict[str, Any], input_fields: dict[str, Any]) -> dict[str, Any]:
    for key in ("asset", "hubspotAsset", "contentAsset", "item", "form", "page", "blogPost", "socialPost", "sms"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
        field_value = input_fields.get(key)
        if isinstance(field_value, dict):
            return field_value
    return {}


def normalize_hubspot_asset_payload(payload: dict[str, Any], analysis_mode: str = "asset_copy_preflight") -> dict[str, Any]:
    input_fields = payload.get("inputFields") if isinstance(payload.get("inputFields"), dict) else {}
    asset = hubspot_asset_object_from_payload(payload, input_fields)
    asset_type = normalized_hubspot_asset_type(
        first_text_value(
            payload.get("asset_type"),
            payload.get("assetType"),
            input_fields.get("asset_type"),
            input_fields.get("assetType"),
            asset.get("assetType"),
            asset.get("type"),
            asset.get("contentType"),
            asset.get("contentTypeCategory"),
            "HUBSPOT_ASSET",
            max_length=120,
        )
    )
    asset_id = first_text_value(
        payload.get("asset_id"),
        payload.get("assetId"),
        payload.get("content_id"),
        payload.get("contentId"),
        input_fields.get("asset_id"),
        input_fields.get("assetId"),
        hubspot_asset_id(asset),
        max_length=160,
    )
    asset_name = first_text_value(
        payload.get("asset_name"),
        payload.get("assetName"),
        input_fields.get("asset_name"),
        input_fields.get("assetName"),
        max_length=300,
    ) or hubspot_asset_label(asset, asset_type, asset_id)
    subject = first_text_value(
        input_fields.get("asset_name"),
        input_fields.get("assetName"),
        input_fields.get("subject"),
        input_fields.get("title"),
        input_fields.get("name"),
        payload.get("asset_name"),
        payload.get("assetName"),
        payload.get("subject"),
        payload.get("title"),
        payload.get("name"),
        asset.get("subject"),
        asset.get("title"),
        asset.get("htmlTitle"),
        asset.get("pageTitle"),
        asset.get("name"),
        asset_name,
        max_length=300,
    )
    direct_body = first_text_value(
        input_fields.get("asset_copy"),
        input_fields.get("copy"),
        input_fields.get("body"),
        input_fields.get("html"),
        input_fields.get("text"),
        input_fields.get("message"),
        input_fields.get("description"),
        payload.get("asset_copy"),
        payload.get("copy"),
        payload.get("body"),
        payload.get("html"),
        payload.get("text"),
        payload.get("message"),
        payload.get("description"),
        max_length=HUBSPOT_MAX_INGRESS_BYTES,
    )
    body = strip_html_to_text(direct_body) if direct_body else hubspot_asset_candidate_text(asset)
    normalized = {**payload}
    normalized_input = {**input_fields, "email_subject": subject, "email_body": body}
    normalized["inputFields"] = normalized_input
    normalized["source_system"] = first_text_value(payload.get("source_system"), input_fields.get("source_system"), f"hubspot_{asset_type.lower()}", max_length=80)
    normalized["analysis_mode"] = first_text_value(payload.get("analysis_mode"), input_fields.get("analysis_mode"), analysis_mode, max_length=80)
    normalized["campaign_id"] = first_text_value(
        payload.get("campaign_id"),
        payload.get("campaignId"),
        input_fields.get("campaign_id"),
        input_fields.get("campaignId"),
        nested_value(asset, ("campaign", "id")),
        asset.get("campaignId"),
        asset.get("campaignGuid"),
        max_length=160,
    )
    normalized["template_id"] = first_text_value(payload.get("template_id"), payload.get("templateId"), input_fields.get("template_id"), asset_id, max_length=160)
    normalized["portal_id"] = first_text_value(payload.get("portal_id"), payload.get("portalId"), input_fields.get("portal_id"), asset.get("portalId"), max_length=160)
    delivery_context = optional_context_object(payload.get("delivery_context"), input_fields.get("delivery_context"))
    delivery_context.update(
        {
            "asset_type": asset_type,
            "asset_id": asset_id,
            "asset_name": asset_name,
            "copy_source": first_text_value(payload.get("copy_source"), input_fields.get("copy_source"), "mapped_asset_payload", max_length=120),
        }
    )
    normalized["delivery_context"] = scrub_payload({key: value for key, value in delivery_context.items() if value})
    if not normalized.get("idempotency_key"):
        explicit_key = first_text_value(input_fields.get("idempotency_key"), payload.get("idempotencyKey"), max_length=160)
        revision = first_text_value(asset.get("updatedAt"), asset.get("updated_at"), asset.get("revisionId"), payload.get("revision_id"), max_length=120)
        if explicit_key:
            normalized["idempotency_key"] = explicit_key
        elif asset_id and revision:
            normalized["idempotency_key"] = f"hubspot-asset:{asset_type}:{asset_id}:{revision or 'current'}"
    return normalized


def with_campaign_context(item: dict[str, Any], payload: dict[str, Any], source_system: str, analysis_mode: str, index: int) -> dict[str, Any]:
    context = hubspot_campaign_context(payload)
    merged = {**item}
    for key, value in (
        ("workspace_id", payload.get("workspace_id")),
        ("tenant_id", payload.get("tenant_id")),
        ("portal_id", payload.get("portal_id") or payload.get("portalId") or context.get("portal_id")),
        ("campaign_id", item.get("campaign_id") or item.get("campaignId") or context.get("campaign_id")),
        ("source_system", item.get("source_system") or payload.get("source_system") or source_system),
        ("analysis_mode", item.get("analysis_mode") or payload.get("analysis_mode") or analysis_mode),
        ("audience_type", item.get("audience_type") or item.get("audienceType") or payload.get("audience_type") or payload.get("audienceType")),
        ("region", item.get("region") or payload.get("region")),
        ("business_unit", item.get("business_unit") or item.get("businessUnit") or payload.get("business_unit") or payload.get("businessUnit")),
        ("job_id", item.get("job_id") or item.get("jobId") or payload.get("job_id") or payload.get("jobId")),
        ("job_family", item.get("job_family") or item.get("jobFamily") or payload.get("job_family") or payload.get("jobFamily")),
        ("skill_family", item.get("skill_family") or item.get("skillFamily") or payload.get("skill_family") or payload.get("skillFamily")),
        ("recruiter", item.get("recruiter") or item.get("recruiter_name") or payload.get("recruiter") or payload.get("recruiter_name")),
        ("recruiter_id", item.get("recruiter_id") or item.get("recruiterId") or payload.get("recruiter_id") or payload.get("recruiterId")),
        ("client_account", item.get("client_account") or item.get("clientAccount") or payload.get("client_account") or payload.get("clientAccount")),
        ("client_account_id", item.get("client_account_id") or item.get("clientAccountId") or payload.get("client_account_id") or payload.get("clientAccountId")),
        ("candidate_status", item.get("candidate_status") or item.get("candidateStatus") or payload.get("candidate_status") or payload.get("candidateStatus")),
        ("ats_system", item.get("ats_system") or item.get("atsSystem") or payload.get("ats_system") or payload.get("atsSystem")),
        ("job_board", item.get("job_board") or item.get("jobBoard") or payload.get("job_board") or payload.get("jobBoard")),
        ("source_channel", item.get("source_channel") or item.get("sourceChannel") or payload.get("source_channel") or payload.get("sourceChannel")),
        ("salesforce_campaign_id", item.get("salesforce_campaign_id") or item.get("salesforceCampaignId") or payload.get("salesforce_campaign_id") or payload.get("salesforceCampaignId")),
        ("salesforce_opportunity_id", item.get("salesforce_opportunity_id") or item.get("salesforceOpportunityId") or payload.get("salesforce_opportunity_id") or payload.get("salesforceOpportunityId")),
    ):
        if value and not merged.get(key):
            merged[key] = value
    item_id = first_text_value(item.get("id"), item.get("emailId"), item.get("template_id"), item.get("templateId"), max_length=120)
    revision = first_text_value(item.get("revision_id"), item.get("revisionId"), item.get("updatedAt"), item.get("updated_at"), max_length=120)
    explicit_key = first_text_value(item.get("idempotency_key"), item.get("idempotencyKey"), max_length=160)
    if explicit_key and not merged.get("idempotency_key"):
        merged["idempotency_key"] = explicit_key
    elif item_id and revision and not merged.get("idempotency_key"):
        merged["idempotency_key"] = f"{source_system}:{context.get('campaign_id') or 'campaign'}:{item_id}:{revision}:{index}"
    return merged


def hubspot_workspace_for_portal(portal_id: str) -> str:
    clean = "".join(ch for ch in str(portal_id or "") if ch.isalnum() or ch in {"-", "_"})[:120]
    return f"hubspot_{clean}" if clean else ""


def validate_hubspot_context(context: dict[str, Any]) -> str | None:
    portal_id = str(context.get("portal_id") or "").strip()
    workspace_id = str(context.get("workspace_id") or "").strip()
    tenant_id = str(context.get("tenant_id") or "").strip()
    source_system = str(context.get("source_system") or "").strip().lower()
    expected_workspace = hubspot_workspace_for_portal(portal_id)
    if source_system and source_system != "hubspot" and not source_system.startswith("hubspot_"):
        return "HubSpot source_system must identify HubSpot."
    if portal_id and tenant_id and tenant_id != portal_id:
        return "HubSpot tenant_id must match the portal ID supplied by the installed app."
    if expected_workspace and workspace_id and workspace_id != expected_workspace:
        return "HubSpot workspace_id must match the installed portal."
    if expected_workspace and not workspace_id:
        context["workspace_id"] = expected_workspace
    if portal_id and not tenant_id:
        context["tenant_id"] = portal_id
    return None


def hubspot_context_from_payload(payload: dict[str, Any], input_fields: dict[str, Any]) -> dict[str, Any]:
    raw_context = payload.get("crmContext") if isinstance(payload.get("crmContext"), dict) else {}
    extension_context = payload.get("hubspotContext") if isinstance(payload.get("hubspotContext"), dict) else {}
    generic_context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    object_id = first_text_value(
        input_fields.get("object_id"),
        input_fields.get("hs_object_id"),
        payload.get("object_id"),
        raw_context.get("objectId"),
        raw_context.get("object_id"),
        extension_context.get("objectId"),
        extension_context.get("recordId"),
        generic_context.get("objectId"),
        generic_context.get("recordId"),
    )
    object_type = first_text_value(
        input_fields.get("object_type"),
        payload.get("object_type"),
        raw_context.get("objectType"),
        raw_context.get("objectTypeId"),
        extension_context.get("objectType"),
        extension_context.get("objectTypeId"),
        generic_context.get("objectType"),
        generic_context.get("objectTypeId"),
    )
    portal_id = first_text_value(
        input_fields.get("portal_id"),
        payload.get("portal_id"),
        payload.get("tenant_id"),
        nested_value(extension_context, ("portal", "id")),
        extension_context.get("portalId"),
        generic_context.get("portalId"),
        raw_context.get("portalId"),
    )
    context = {
        "workspace_id": first_text_value(payload.get("workspace_id"), input_fields.get("workspace_id"), f"hubspot_{portal_id}" if portal_id else "hubspot_workspace"),
        "tenant_id": first_text_value(payload.get("tenant_id"), input_fields.get("tenant_id"), portal_id),
        "source_system": first_text_value(payload.get("source_system"), input_fields.get("source_system"), "hubspot", max_length=80),
        "workflow": first_text_value(payload.get("workflow"), input_fields.get("workflow"), input_fields.get("workflow_name"), max_length=120),
        "analysis_mode": first_text_value(payload.get("analysis_mode"), input_fields.get("analysis_mode"), "send_path_gate", max_length=80),
        "campaign_id": first_text_value(payload.get("campaign_id"), input_fields.get("campaign_id"), input_fields.get("workflow_name"), max_length=160),
        "journey_id": first_text_value(payload.get("journey_id"), input_fields.get("journey_id"), max_length=160),
        "template_id": first_text_value(payload.get("template_id"), input_fields.get("template_id"), max_length=160),
        "contact_id": first_text_value(payload.get("contact_id"), input_fields.get("contact_id"), raw_context.get("contactId"), object_id if "contact" in object_type.lower() else "", max_length=160),
        "company_id": first_text_value(payload.get("company_id"), input_fields.get("company_id"), raw_context.get("companyId"), max_length=160),
        "deal_id": first_text_value(payload.get("deal_id"), input_fields.get("deal_id"), raw_context.get("dealId"), max_length=160),
        "owner_id": first_text_value(payload.get("owner_id"), input_fields.get("owner_id"), raw_context.get("ownerId"), max_length=160),
        "portal_id": portal_id,
        "object_type": object_type,
        "object_id": object_id,
        "locale": first_text_value(payload.get("locale"), input_fields.get("locale"), extension_context.get("locale"), generic_context.get("locale"), max_length=40),
        "contact_name": first_text_value(payload.get("contact_name"), input_fields.get("contact_name"), raw_context.get("contactName"), max_length=160),
        "company_name": first_text_value(payload.get("company_name"), input_fields.get("company_name"), raw_context.get("companyName"), max_length=160),
        "lifecycle_stage": first_text_value(payload.get("lifecycle_stage"), input_fields.get("lifecycle_stage"), raw_context.get("lifecycleStage"), max_length=120),
        "recent_activity": first_text_value(payload.get("recent_activity"), input_fields.get("recent_activity"), raw_context.get("recentActivity"), max_length=300),
        "audience_type": first_text_value(payload.get("audience_type"), payload.get("audienceType"), input_fields.get("audience_type"), input_fields.get("audienceType"), raw_context.get("audienceType"), max_length=80),
        "region": first_text_value(payload.get("region"), input_fields.get("region"), raw_context.get("region"), max_length=120),
        "business_unit": first_text_value(payload.get("business_unit"), payload.get("businessUnit"), input_fields.get("business_unit"), input_fields.get("businessUnit"), raw_context.get("businessUnit"), max_length=160),
        "job_id": first_text_value(payload.get("job_id"), payload.get("jobId"), input_fields.get("job_id"), input_fields.get("jobId"), raw_context.get("jobId"), max_length=160),
        "job_family": first_text_value(payload.get("job_family"), payload.get("jobFamily"), input_fields.get("job_family"), input_fields.get("jobFamily"), raw_context.get("jobFamily"), max_length=160),
        "skill_family": first_text_value(payload.get("skill_family"), payload.get("skillFamily"), input_fields.get("skill_family"), input_fields.get("skillFamily"), raw_context.get("skillFamily"), max_length=160),
        "recruiter": first_text_value(payload.get("recruiter"), payload.get("recruiter_name"), input_fields.get("recruiter"), input_fields.get("recruiter_name"), raw_context.get("recruiter"), max_length=160),
        "recruiter_id": first_text_value(payload.get("recruiter_id"), payload.get("recruiterId"), input_fields.get("recruiter_id"), input_fields.get("recruiterId"), raw_context.get("recruiterId"), max_length=160),
        "client_account": first_text_value(payload.get("client_account"), payload.get("clientAccount"), input_fields.get("client_account"), input_fields.get("clientAccount"), raw_context.get("clientAccount"), max_length=200),
        "client_account_id": first_text_value(payload.get("client_account_id"), payload.get("clientAccountId"), input_fields.get("client_account_id"), input_fields.get("clientAccountId"), raw_context.get("clientAccountId"), max_length=160),
        "candidate_status": first_text_value(payload.get("candidate_status"), payload.get("candidateStatus"), input_fields.get("candidate_status"), input_fields.get("candidateStatus"), raw_context.get("candidateStatus"), max_length=120),
        "ats_system": first_text_value(payload.get("ats_system"), payload.get("atsSystem"), input_fields.get("ats_system"), input_fields.get("atsSystem"), raw_context.get("atsSystem"), max_length=120),
        "job_board": first_text_value(payload.get("job_board"), payload.get("jobBoard"), input_fields.get("job_board"), input_fields.get("jobBoard"), raw_context.get("jobBoard"), max_length=120),
        "source_channel": first_text_value(payload.get("source_channel"), payload.get("sourceChannel"), input_fields.get("source_channel"), input_fields.get("sourceChannel"), raw_context.get("sourceChannel"), max_length=120),
        "salesforce_campaign_id": first_text_value(payload.get("salesforce_campaign_id"), payload.get("salesforceCampaignId"), input_fields.get("salesforce_campaign_id"), input_fields.get("salesforceCampaignId"), max_length=160),
        "salesforce_opportunity_id": first_text_value(payload.get("salesforce_opportunity_id"), payload.get("salesforceOpportunityId"), input_fields.get("salesforce_opportunity_id"), input_fields.get("salesforceOpportunityId"), max_length=160),
        "salesforce_lead_id": first_text_value(payload.get("salesforce_lead_id"), payload.get("salesforceLeadId"), input_fields.get("salesforce_lead_id"), input_fields.get("salesforceLeadId"), max_length=160),
        "salesforce_contact_id": first_text_value(payload.get("salesforce_contact_id"), payload.get("salesforceContactId"), input_fields.get("salesforce_contact_id"), input_fields.get("salesforceContactId"), max_length=160),
        "headers": optional_context_object(payload.get("headers"), input_fields.get("headers")),
        "consent_context": optional_context_object(payload.get("consent_context"), input_fields.get("consent_context")),
        "delivery_context": optional_context_object(payload.get("delivery_context"), input_fields.get("delivery_context")),
        "ingress_auth": getattr(g, "hubspot_ingress_auth", {"mode": "unknown"}),
    }
    for key in (
        "workspace_id",
        "tenant_id",
        "source_system",
        "workflow",
        "analysis_mode",
        "journey_id",
        "template_id",
        "contact_id",
        "company_id",
        "deal_id",
        "owner_id",
        "portal_id",
        "object_type",
        "object_id",
        "locale",
        "audience_type",
        "region",
        "business_unit",
        "job_id",
        "job_family",
        "skill_family",
        "recruiter_id",
        "client_account_id",
        "candidate_status",
        "ats_system",
        "job_board",
        "source_channel",
        "salesforce_campaign_id",
        "salesforce_opportunity_id",
        "salesforce_lead_id",
        "salesforce_contact_id",
    ):
        context[key] = safe_hubspot_identifier(context.get(key), "", 160 if key != "locale" else 40)
    validation_error = validate_hubspot_context(context)
    if validation_error:
        context["_validation_error"] = validation_error
    return context


TEMPLATE_TOKEN_RE = re.compile(r"{{\s*([A-Za-z0-9_.-]+)\s*}}|%\s*([A-Za-z0-9_.-]+)\s*%|\[\[\s*([A-Za-z0-9_.-]+)\s*\]\]")
LINK_RE = re.compile(r"https?://[^\s<>\"]+", re.IGNORECASE)


def template_context_value(context: dict[str, Any], key: str) -> str:
    current: Any = context
    for part in key.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return ""
    if current is None:
        return ""
    return str(current)


def render_template_text(template: str, sample_context: dict[str, Any]) -> tuple[str, list[str]]:
    unresolved: list[str] = []

    def replace(match: re.Match) -> str:
        key = next((group for group in match.groups() if group), "")
        value = template_context_value(sample_context, key)
        if value == "":
            token = match.group(0)
            if token not in unresolved:
                unresolved.append(token)
            return token
        return value

    return TEMPLATE_TOKEN_RE.sub(replace, template or ""), unresolved


def template_contains_token(template_text: str, token: str) -> bool:
    clean_token = re.escape(token)
    patterns = (
        rf"{{{{\s*{clean_token}\s*}}}}",
        rf"%\s*{clean_token}\s*%",
        rf"\[\[\s*{clean_token}\s*\]\]",
    )
    return any(re.search(pattern, template_text, re.IGNORECASE) for pattern in patterns)


def hubspot_template_test_result(subject: str, body: str, sample_context: dict[str, Any], headers: dict[str, Any] | None = None, policy: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = normalized_hubspot_email_policy(policy)
    rendered_subject, subject_unresolved = render_template_text(subject, sample_context)
    rendered_body, body_unresolved = render_template_text(body, sample_context)
    unresolved = subject_unresolved + [token for token in body_unresolved if token not in subject_unresolved]
    links = LINK_RE.findall(rendered_body)
    lower_rendered = rendered_body.lower()
    unsubscribe_present = any(
        cue in lower_rendered
        for cue in ("unsubscribe", "{{unsubscribe_link}}", "%unsubscribe_link%", "[[unsubscribe_link]]")
    )
    header_warnings: list[str] = []
    clean_headers = scrub_payload(headers or {})
    required_headers = normalized_policy_list(policy.get("required_headers"), ("from", "reply_to"), limit=20)
    for required in required_headers:
        if required not in {str(key).lower() for key in clean_headers.keys()}:
            header_warnings.append(f"Missing {required.replace('_', '-')} header.")
    original_template = f"{subject}\n{body}"
    required_tokens = normalized_policy_list(policy.get("required_template_tokens"), ("unsubscribe_link",), limit=20)
    missing_required_tokens = [
        token
        for token in required_tokens
        if not template_contains_token(original_template, token) and not (token == "unsubscribe_link" and unsubscribe_present)
    ]
    checks = [
        {"id": "tokens_resolved", "label": "Merge tokens resolved", "ok": not unresolved, "detail": "All supplied tokens rendered." if not unresolved else f"Unresolved tokens: {', '.join(unresolved[:8])}."},
        {"id": "required_tokens_present", "label": "Required tokens", "ok": not missing_required_tokens, "detail": "Required rule-pack tokens are present." if not missing_required_tokens else f"Missing required token{'s' if len(missing_required_tokens) != 1 else ''}: {', '.join(missing_required_tokens[:8])}."},
        {"id": "unsubscribe_present", "label": "Unsubscribe state", "ok": unsubscribe_present, "detail": "Unsubscribe wording or token is present." if unsubscribe_present else "Add an unsubscribe token or link before automated routing."},
        {"id": "links_detected", "label": "Link inventory", "ok": True, "detail": f"{len(links)} link{'s' if len(links) != 1 else ''} detected."},
        {"id": "headers_present", "label": "Header context", "ok": not header_warnings, "detail": "Required sender headers supplied." if not header_warnings else " ".join(header_warnings)},
    ]
    return {
        "rendered_subject": rendered_subject,
        "rendered_body": rendered_body,
        "unresolved_tokens": unresolved,
        "missing_required_tokens": missing_required_tokens,
        "links": links[:25],
        "headers": clean_headers,
        "policy": {
            "version": policy.get("version"),
            "rule_pack": policy.get("rule_pack"),
            "rule_pack_label": policy.get("rule_pack_label"),
            "required_template_tokens": required_tokens,
            "required_headers": required_headers,
        },
        "checks": checks,
        "ready": all(item["ok"] for item in checks),
    }


@app.get("/")
@app.get("/explorer")
@app.get("/enterprise")
def index():
    return render_template(
        "index.html",
        metrics=predictor.metrics,
        model_info=predictor.metadata,
        public_model_info=public_model_info(),
        available_models=AVAILABLE_MODELS,
        dev_tools_enabled=ENABLE_DEV_TOOLS,
        public_app_info=public_app_info(),
        csrf_token=csrf_token(),
        csp_nonce=g.csp_nonce,
    )


@app.get("/health")
def health():
    database_ok = False
    try:
        database_ok = bool(check_database().get("ok"))
    except Exception:
        logging.exception("health_database_check_failed")
    return jsonify({"ok": not isinstance(predictor, MissingPredictor) and database_ok})


@app.get("/hubspot/setup-guide")
@rate_limited(60)
def hubspot_setup_guide():
    guide_path = Path(__file__).resolve().parents[1] / "docs/hubspot_marketplace_setup_guide.md"
    if not guide_path.exists():
        return jsonify({"error": "HubSpot setup guide is not available."}), 404
    markdown = guide_path.read_text()
    lines = []
    in_table = False
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            if in_table:
                lines.append("</table>")
                in_table = False
            continue
        if line.startswith("|") and line.endswith("|"):
            cells = [html_escape(cell.strip()) for cell in line.strip("|").split("|")]
            if len(cells) >= 2 and set(cells[0]) <= {"-", ":"}:
                continue
            if not in_table:
                lines.append("<table>")
                in_table = True
            tag = "th" if all(cell for cell in cells) and "Scope" in cells[0] else "td"
            lines.append("<tr>" + "".join(f"<{tag}>{cell}</{tag}>" for cell in cells) + "</tr>")
            continue
        if in_table:
            lines.append("</table>")
            in_table = False
        if line.startswith("# "):
            lines.append(f"<h1>{html_escape(line[2:])}</h1>")
        elif line.startswith("## "):
            lines.append(f"<h2>{html_escape(line[3:])}</h2>")
        elif line.startswith("- "):
            lines.append(f"<p>&bull; {html_escape(line[2:])}</p>")
        elif re.match(r"^\d+\.\s+", line):
            lines.append(f"<p>{html_escape(line)}</p>")
        else:
            lines.append(f"<p>{html_escape(line)}</p>")
    if in_table:
        lines.append("</table>")
    return render_template_string(
        """
        <!doctype html>
        <html lang="en">
          <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>TextTraits Email Fit HubSpot Setup Guide</title>
            <style nonce="{{ csp_nonce }}">
              body { font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #13201b; background: #f7fbf8; margin: 0; line-height: 1.55; }
              main { max-width: 920px; margin: 0 auto; padding: 48px 24px 72px; }
              h1 { font-size: clamp(2rem, 5vw, 4rem); line-height: 1; margin: 0 0 24px; }
              h2 { margin: 40px 0 12px; font-size: 1.5rem; }
              p { margin: 10px 0; font-size: 1rem; }
              table { border-collapse: collapse; width: 100%; margin: 18px 0 28px; background: white; }
              th, td { border: 1px solid #cfded8; padding: 10px 12px; text-align: left; vertical-align: top; }
              th { background: #ecf6f2; }
              code { background: #e8f0ed; padding: 0 4px; border-radius: 4px; }
            </style>
          </head>
          <body>
            <main>{{ body|safe }}</main>
          </body>
        </html>
        """,
        csp_nonce=g.csp_nonce,
        body="\n".join(lines),
    )


@app.get("/dev/model")
def dev_model():
    if not ENABLE_DEV_TOOLS:
        return jsonify({"error": "Developer tools are disabled."}), 404
    return jsonify({"metadata": predictor.metadata, "metrics": predictor.metrics})


@app.post("/evaluate")
@rate_limited()
def evaluate():
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text", "")).strip()
    model_id = str(payload.get("model", "local")).strip() or "local"
    if not text:
        return jsonify({"error": "Please enter text to evaluate."}), 400
    if len(text.split()) > MAX_TEXT_WORDS:
        return jsonify({"error": f"Please keep samples under {MAX_TEXT_WORDS} words for this workspace."}), 413
    if model_id != "local":
        return jsonify({"error": "The PANDORA cloud-trained model is not connected yet."}), 503
    try:
        log_event(current_user_id(), "evaluate", {"mode": payload.get("mode", "unknown"), "words": len(text.split())})
        predictions = predictor.predict(text)
        return jsonify(
            {
                "model": model_id,
                "demo": bool(getattr(predictor, "is_demo", False)),
                "predictions": predictions if ENABLE_DEV_TOOLS else public_prediction_payload(predictions),
            }
        )
    except RuntimeError as error:
        return jsonify({"error": str(error)}), 503


def hubspot_analysis_result(payload: dict, workflow: str) -> tuple[dict[str, Any], int]:
    if len(json.dumps(payload, default=str).encode("utf-8")) > HUBSPOT_MAX_INGRESS_BYTES:
        return {"error": f"HubSpot ingress payloads must stay under {HUBSPOT_MAX_INGRESS_BYTES} bytes."}, 413
    input_fields = payload.get("inputFields") if isinstance(payload.get("inputFields"), dict) else payload
    subject = str(input_fields.get("subject") or input_fields.get("email_subject") or input_fields.get("hs_email_subject") or "").strip()
    body = str(input_fields.get("body") or input_fields.get("email_body") or input_fields.get("hs_email_body") or input_fields.get("text") or "").strip()
    text = f"{subject}\n\n{body}".strip()
    context = hubspot_context_from_payload(payload, input_fields)
    context["workflow"] = workflow
    if context.get("_validation_error"):
        return {"error": context["_validation_error"]}, 403
    policy = hubspot_policy_for_request(payload, context)
    if not text:
        return {"error": "Enter an email subject or body to analyze."}, 400
    if len(text.split()) > MAX_TEXT_WORDS:
        return {"error": f"Please keep samples under {MAX_TEXT_WORDS} words for this workspace."}, 413
    try:
        predictions = predictor.predict(text)
    except RuntimeError as error:
        return {"error": str(error)}, 503

    confidences = prediction_confidences(predictions)
    average_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    email_quality = build_hubspot_email_quality(subject, body, text, policy, context)
    decision = email_quality["decision"]
    score = email_quality["score"]
    gate = decision["gate"]
    route = decision["route"]
    primary_finding = hubspot_best_finding({"findings": email_quality["findings"]})
    blocker_reason = first_text_value(primary_finding.get("title"), decision.get("next_step"), gate, max_length=500)
    content_hash = hubspot_content_hash(text, str(context.get("workspace_id") or "hubspot_workspace"))
    idempotency_key = first_text_value(
        payload.get("idempotency_key"),
        input_fields.get("idempotency_key"),
        request.headers.get("X-Idempotency-Key"),
        max_length=160,
    )
    if idempotency_key:
        request_id = hubspot_idempotent_request_id(workflow, str(context.get("workspace_id") or ""), idempotency_key)
        existing = get_hubspot_email_analysis(request_id)
        if existing and existing.get("content_hash") != content_hash:
            return {
                "error": "This HubSpot idempotency key was already used for different email content.",
                "request_id": request_id,
            }, 409
    else:
        request_id = f"{workflow}-{secrets.token_urlsafe(12)}"
    log_event(
        current_user_id(),
        workflow,
        {
            "words": len(text.split()),
            "score": score,
            "gate": gate,
            "workspace_id": str(payload.get("workspace_id", ""))[:120],
        },
    )
    save_hubspot_email_analysis(
        {
            **context,
            "request_id": request_id,
            "workflow": workflow,
            "idempotency_key": idempotency_key,
            "content_hash": content_hash,
            "score": score,
            "gate": gate,
            "route": route,
            "send_ready": gate == "ready",
            "word_count": len(text.split()),
            "average_model_confidence": round(average_confidence, 4),
            "score_source": email_quality["score_source"],
            "findings": email_quality["findings"],
            "checks": email_quality["checks"],
            "policy": policy,
            "context": context,
        }
    )
    public_quality = public_hubspot_email_quality(email_quality)
    public_policy = public_hubspot_policy(policy)
    public_context = public_hubspot_context(context)
    analysis_payload = {
        "request_id": request_id,
        "content_hash": content_hash,
        "idempotency_key": idempotency_key,
        "score": score,
        "gate": gate,
        "route": route,
        "word_count": len(text.split()),
        "average_model_confidence": round(average_confidence, 4),
        "decision": decision,
        "email_quality": public_quality,
        "policy": public_policy,
        "context": public_context,
        "demo": bool(getattr(predictor, "is_demo", False)),
    }
    if ENABLE_DEV_TOOLS:
        analysis_payload["predictions"] = predictions
    delivery_context = context.get("delivery_context") if isinstance(context.get("delivery_context"), dict) else {}
    asset_output_fields = {
        "texttraits_asset_type": delivery_context.get("asset_type"),
        "texttraits_asset_id": delivery_context.get("asset_id"),
        "texttraits_asset_name": delivery_context.get("asset_name"),
    }
    return {
        "workflow": workflow,
        "outputFields": {
            "texttraits_request_id": request_id,
            "texttraits_content_hash": content_hash,
            "texttraits_idempotency_key": idempotency_key,
            "texttraits_score": score,
            "texttraits_gate": gate,
            "texttraits_route": route,
            "texttraits_send_ready": gate == "ready",
            "texttraits_next_step": decision["next_step"],
            "texttraits_owner_queue": decision["owner_queue"],
            "texttraits_blocker_level": decision["blocker_level"],
            "texttraits_blocker_reason": blocker_reason,
            "texttraits_policy_version": policy.get("version"),
            **{key: value for key, value in asset_output_fields.items() if value},
        },
        "analysis": analysis_payload,
    }, 200


def hubspot_analysis_response(payload: dict, workflow: str):
    result, status_code = hubspot_analysis_result(payload, workflow)
    return jsonify(result), status_code


@app.post("/v1/integrations/hubspot/crm-card/analyze-email")
@rate_limited(60)
def hubspot_crm_card_analyze_email():
    return hubspot_analysis_response(request.get_json(silent=True) or {}, "hubspot_crm_card")


@app.post("/v1/integrations/hubspot/workflow-actions/analyze-email")
@rate_limited(60)
def hubspot_workflow_action_analyze_email():
    return hubspot_analysis_response(request.get_json(silent=True) or {}, "hubspot_workflow_action")


@app.post("/v1/integrations/hubspot/workflow-actions/analyze-asset-copy")
@rate_limited(60)
def hubspot_workflow_action_analyze_asset_copy():
    payload = request.get_json(silent=True) or {}
    normalized = normalize_hubspot_asset_payload(payload, "asset_copy_workflow_gate")
    return hubspot_analysis_response(normalized, "hubspot_asset_copy_workflow_action")


@app.post("/v1/integrations/hubspot/marketing-emails/analyze")
@rate_limited(60)
def hubspot_marketing_email_analyze():
    payload = request.get_json(silent=True) or {}
    normalized = normalize_hubspot_marketing_email_payload(payload, "marketing_email_preflight")
    return hubspot_analysis_response(normalized, "hubspot_marketing_email_preflight")


@app.post("/v1/integrations/hubspot/assets/analyze")
@rate_limited(60)
def hubspot_asset_analyze():
    payload = request.get_json(silent=True) or {}
    normalized = normalize_hubspot_asset_payload(payload, "asset_copy_preflight")
    return hubspot_analysis_response(normalized, "hubspot_asset_copy_preflight")


@app.post("/v1/integrations/hubspot/assets/fetch-and-analyze")
@rate_limited(30)
def hubspot_asset_fetch_and_analyze():
    payload, error = hubspot_payload_or_error()
    if error:
        return error
    input_fields = payload.get("inputFields") if isinstance(payload.get("inputFields"), dict) else payload
    portal_id = first_text_value(payload.get("portal_id"), payload.get("portalId"), input_fields.get("portal_id"), input_fields.get("portalId"), max_length=160)
    asset_type = normalized_hubspot_asset_type(first_text_value(payload.get("asset_type"), payload.get("assetType"), input_fields.get("asset_type"), input_fields.get("assetType"), max_length=120))
    asset_id = first_text_value(payload.get("asset_id"), payload.get("assetId"), input_fields.get("asset_id"), input_fields.get("assetId"), max_length=160)
    if not portal_id:
        return jsonify({"error": "HubSpot portal_id is required for live asset review."}), 400
    if not asset_id:
        return jsonify({"error": "HubSpot asset_id is required for live asset review."}), 400
    try:
        client = HubSpotApiClient(portal_id)
        response = client.get_campaign_asset_copy(asset_type, asset_id)
    except HubSpotClientError as hubspot_error:
        payload_body, status_code = hubspot_error_payload(hubspot_error)
        return jsonify(payload_body), status_code
    asset_body = response.get("body", {}) if isinstance(response, dict) else {}
    normalized = normalize_hubspot_asset_payload(
        {
            **payload,
            "portal_id": portal_id,
            "asset_type": asset_type,
            "asset_id": asset_id,
            "asset": asset_body,
            "copy_source": HUBSPOT_DIRECT_COPY_SOURCE_LABELS.get(asset_type, f"{asset_type.lower()}_api"),
            "analysis_mode": "live_asset_copy_review",
        },
        "live_asset_copy_review",
    )
    return hubspot_analysis_response(normalized, "hubspot_live_asset_copy_review")


def hubspot_batch_analysis_payload(payload: dict[str, Any], workflow: str, source_system: str, analysis_mode: str) -> tuple[dict[str, Any], int]:
    if len(json.dumps(payload, default=str).encode("utf-8")) > HUBSPOT_MAX_INGRESS_BYTES:
        return {"error": f"HubSpot ingress payloads must stay under {HUBSPOT_MAX_INGRESS_BYTES} bytes."}, 413
    raw_items = hubspot_email_items_from_payload(payload)
    if not raw_items:
        return {"error": "Supply emails, marketing_emails, assets, or one email-like payload to analyze."}, 400
    max_items = max(1, min(HUBSPOT_MAX_BATCH_EMAILS, 100))
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    gate_counts: dict[str, int] = {}
    scores: list[int] = []
    for index, item in enumerate(raw_items[:max_items]):
        prepared = with_campaign_context(item, payload, source_system, analysis_mode, index)
        normalized = normalize_hubspot_marketing_email_payload(prepared, analysis_mode)
        result, status_code = hubspot_analysis_result(normalized, workflow)
        if status_code == 200:
            gate = str(result.get("outputFields", {}).get("texttraits_gate") or "unknown")
            score = int(result.get("outputFields", {}).get("texttraits_score") or 0)
            gate_counts[gate] = gate_counts.get(gate, 0) + 1
            scores.append(score)
            results.append(result)
        else:
            errors.append(
                {
                    "index": index,
                    "status": status_code,
                    "error": result.get("error", "Analysis failed."),
                    "template_id": first_text_value(item.get("id"), item.get("emailId"), item.get("template_id"), item.get("templateId"), max_length=160),
                }
            )
    if not results:
        return {"error": "No valid HubSpot email assets could be analyzed.", "errors": errors[:10]}, 400
    summary = {
        "workflow": workflow,
        "source_system": source_system,
        "analysis_mode": analysis_mode,
        "received": len(raw_items),
        "analyzed": len(results),
        "dropped": max(0, len(raw_items) - max_items),
        "errors": len(errors),
        "gate_counts": gate_counts,
        "average_score": round(sum(scores) / len(scores), 1) if scores else 0,
        "campaign_id": hubspot_campaign_context(payload).get("campaign_id", ""),
        "campaign_name": hubspot_campaign_context(payload).get("campaign_name", ""),
    }
    return {"summary": summary, "analyses": results, "errors": errors[:10]}, 200


@app.post("/v1/integrations/hubspot/campaigns/analyze")
@rate_limited(30)
def hubspot_campaign_analyze():
    payload = request.get_json(silent=True) or {}
    result, status_code = hubspot_batch_analysis_payload(
        payload,
        "hubspot_campaign_preflight",
        "hubspot_campaign",
        "campaign_preflight",
    )
    return jsonify(result), status_code


@app.post("/v1/integrations/hubspot/bulk/analyze-emails")
@rate_limited(30)
def hubspot_bulk_analyze_emails():
    payload = request.get_json(silent=True) or {}
    source_system = first_text_value(payload.get("source_system"), "hubspot_bulk_email", max_length=80)
    analysis_mode = first_text_value(payload.get("analysis_mode"), "bulk_email_preflight", max_length=80)
    result, status_code = hubspot_batch_analysis_payload(
        payload,
        "hubspot_bulk_email_preflight",
        source_system,
        analysis_mode,
    )
    return jsonify(result), status_code


def hubspot_bulk_asset_items_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("assets", "items", "rows", "records"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    csv_text = first_text_value(payload.get("csv"), payload.get("csv_text"), payload.get("warehouse_export"), max_length=HUBSPOT_MAX_INGRESS_BYTES)
    if not csv_text:
        return []
    try:
        reader = csv.DictReader(io.StringIO(csv_text))
        return [dict(row) for row in reader if isinstance(row, dict)]
    except csv.Error:
        return []


@app.post("/v1/integrations/hubspot/bulk/import-assets")
@rate_limited(20)
def hubspot_bulk_import_assets():
    payload = request.get_json(silent=True) or {}
    if len(json.dumps(payload, default=str).encode("utf-8")) > HUBSPOT_MAX_INGRESS_BYTES:
        return jsonify({"error": f"HubSpot bulk import payloads must stay under {HUBSPOT_MAX_INGRESS_BYTES} bytes."}), 413
    import_id = first_text_value(payload.get("import_id"), payload.get("importId"), payload.get("batch_id"), payload.get("batchId"), f"bulk-{secrets.token_urlsafe(8)}", max_length=160)
    source_system = first_text_value(payload.get("source_system"), "hubspot_bulk_asset_import", max_length=80)
    analysis_mode = first_text_value(payload.get("analysis_mode"), "bulk_asset_preflight", max_length=80)
    raw_items = hubspot_bulk_asset_items_from_payload(payload)
    if not raw_items:
        return jsonify({"error": "Supply assets, rows, records, or CSV text with asset_type, asset_id, subject/name, and copy/body columns."}), 400
    max_items = max(1, min(HUBSPOT_MAX_BATCH_EMAILS, 100))
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    gate_counts: dict[str, int] = {}
    asset_map: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(raw_items[:max_items]):
        asset_type = normalized_hubspot_asset_type(first_text_value(item.get("asset_type"), item.get("assetType"), payload.get("asset_type"), "HUBSPOT_ASSET", max_length=120))
        asset_id = first_text_value(item.get("asset_id"), item.get("assetId"), item.get("id"), item.get("template_id"), max_length=160)
        prepared = with_campaign_context(item, payload, source_system, analysis_mode, index)
        prepared.update(
            {
                "asset_type": asset_type,
                "asset_id": asset_id,
                "asset_name": first_text_value(item.get("asset_name"), item.get("assetName"), item.get("name"), item.get("title"), asset_id, max_length=240),
                "asset_copy": first_text_value(item.get("asset_copy"), item.get("copy"), item.get("body"), item.get("html"), item.get("text"), item.get("message"), max_length=HUBSPOT_MAX_INGRESS_BYTES),
                "copy_source": first_text_value(item.get("copy_source"), payload.get("copy_source"), "bulk_import", max_length=120),
                "idempotency_key": first_text_value(item.get("idempotency_key"), item.get("idempotencyKey"), f"{import_id}:{asset_type}:{asset_id or index}", max_length=160),
            }
        )
        normalized = normalize_hubspot_asset_payload(prepared, analysis_mode)
        result, status_code = hubspot_analysis_result(normalized, "hubspot_bulk_asset_import")
        asset_map.setdefault(asset_type, {"label": HUBSPOT_CAMPAIGN_ASSET_TYPE_LABELS.get(asset_type, asset_type), "assets": [], "status": "loaded"})
        if status_code == 200:
            gate = str(result.get("outputFields", {}).get("texttraits_gate") or "unknown")
            gate_counts[gate] = gate_counts.get(gate, 0) + 1
            asset_map[asset_type]["assets"].append(
                {
                    "id": asset_id,
                    "name": prepared.get("asset_name") or asset_id,
                    "asset_type": asset_type,
                    "copy_source": prepared.get("copy_source"),
                    "status": "analyzed",
                    "gate": gate,
                    "score": int(result.get("outputFields", {}).get("texttraits_score") or 0),
                    "request_id": result.get("outputFields", {}).get("texttraits_request_id"),
                }
            )
            results.append(result)
        else:
            errors.append({"index": index, "asset_type": asset_type, "asset_id": asset_id, "status": status_code, "error": result.get("error", "Analysis failed.")})
            asset_map[asset_type]["assets"].append({"id": asset_id, "name": prepared.get("asset_name") or asset_id, "asset_type": asset_type, "status": "analysis_error"})
    summary = {
        "import_id": import_id,
        "received": len(raw_items),
        "analyzed": len(results),
        "dropped": max(0, len(raw_items) - max_items),
        "errors": len(errors),
        "gate_counts": gate_counts,
        "coverage": hubspot_campaign_copy_coverage(asset_map),
    }
    log_event(current_user_id(), "hubspot_bulk_asset_import", {"import_id": import_id, "received": len(raw_items), "analyzed": len(results), "errors": len(errors)})
    if not results:
        return jsonify({"error": "No valid imported campaign assets could be analyzed.", "summary": summary, "errors": errors[:10]}), 400
    return jsonify({"ok": not errors, "summary": summary, "analyses": results, "errors": errors[:10]}), 207 if errors else 200


@app.post("/v1/integrations/hubspot/template-test")
@rate_limited(60)
def hubspot_template_test():
    payload = request.get_json(silent=True) or {}
    if len(json.dumps(payload, default=str).encode("utf-8")) > HUBSPOT_MAX_INGRESS_BYTES:
        return jsonify({"error": f"HubSpot ingress payloads must stay under {HUBSPOT_MAX_INGRESS_BYTES} bytes."}), 413
    input_fields = payload.get("inputFields") if isinstance(payload.get("inputFields"), dict) else payload
    subject = str(input_fields.get("subject") or input_fields.get("email_subject") or "").strip()
    body = str(input_fields.get("body") or input_fields.get("email_body") or input_fields.get("text") or "").strip()
    sample_context = payload.get("sample_context") if isinstance(payload.get("sample_context"), dict) else input_fields.get("sample_context") if isinstance(input_fields.get("sample_context"), dict) else {}
    headers = payload.get("headers") if isinstance(payload.get("headers"), dict) else input_fields.get("headers") if isinstance(input_fields.get("headers"), dict) else {}
    if not subject and not body:
        return jsonify({"error": "Enter a template subject or body to test."}), 400
    if len(f"{subject}\n\n{body}".split()) > MAX_TEXT_WORDS:
        return jsonify({"error": f"Please keep templates under {MAX_TEXT_WORDS} words for this workspace."}), 413
    context = hubspot_context_from_payload(payload, input_fields)
    if context.get("_validation_error"):
        return jsonify({"error": context["_validation_error"]}), 403
    policy = hubspot_policy_for_request(payload, context)
    result = hubspot_template_test_result(subject, body, scrub_payload(sample_context), scrub_payload(headers), policy)
    return jsonify({"template_test": result})


def hubspot_payload_or_error() -> tuple[dict[str, Any], tuple | None]:
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return {}, (jsonify({"error": "HubSpot action payload must be a JSON object."}), 400)
    if len(json.dumps(payload, default=str).encode("utf-8")) > HUBSPOT_MAX_INGRESS_BYTES:
        return {}, (jsonify({"error": f"HubSpot ingress payloads must stay under {HUBSPOT_MAX_INGRESS_BYTES} bytes."}), 413)
    return payload, None


def hubspot_error_response(error: Exception) -> tuple:
    payload, status_code = hubspot_error_payload(error)
    return jsonify(payload), status_code


def hubspot_error_payload(error: Exception) -> tuple[dict[str, Any], int]:
    status_code = int(getattr(error, "status_code", 502) or 502)
    details = getattr(error, "payload", {}) if isinstance(getattr(error, "payload", {}), dict) else {}
    return {"error": str(error), "details": scrub_payload(details)}, status_code


def hubspot_client_and_context(payload: dict[str, Any]) -> tuple[HubSpotApiClient | None, dict[str, Any], tuple | None]:
    input_fields = payload.get("inputFields") if isinstance(payload.get("inputFields"), dict) else payload
    context = hubspot_context_from_payload(payload, input_fields)
    if context.get("_validation_error"):
        return None, context, (jsonify({"error": context["_validation_error"]}), 403)
    portal_id = first_text_value(
        payload.get("portal_id"),
        payload.get("portalId"),
        payload.get("tenant_id"),
        input_fields.get("portal_id"),
        input_fields.get("portalId"),
        context.get("portal_id"),
        max_length=160,
    )
    if not portal_id:
        return None, context, (jsonify({"error": "HubSpot portal_id is required for live HubSpot API actions."}), 400)
    try:
        return HubSpotApiClient(portal_id), context, None
    except HubSpotClientError as error:
        return None, context, hubspot_error_response(error)


def hubspot_idempotency_key(payload: dict[str, Any], *parts: Any) -> str:
    explicit = first_text_value(payload.get("idempotency_key"), payload.get("idempotencyKey"), request.headers.get("X-Idempotency-Key"), max_length=180)
    if explicit:
        return explicit
    clean_parts = [str(part or "").strip() for part in parts if str(part or "").strip()]
    return ":".join(clean_parts)[:180]


def hubspot_object_api_type(value: Any) -> str:
    clean = str(value or "").strip()
    lower = clean.lower()
    mapping = {
        "contact": "contacts",
        "contacts": "contacts",
        "0-1": "contacts",
        "company": "companies",
        "companies": "companies",
        "0-2": "companies",
        "deal": "deals",
        "deals": "deals",
        "0-3": "deals",
        "ticket": "tickets",
        "tickets": "tickets",
        "0-5": "tickets",
    }
    return mapping.get(lower, clean)


def hubspot_analysis_for_action(payload: dict[str, Any]) -> tuple[dict[str, Any] | None, tuple | None]:
    request_id = first_text_value(payload.get("request_id"), payload.get("texttraits_request_id"), nested_value(payload, ("outputFields", "texttraits_request_id")), max_length=160)
    if not request_id:
        return None, (jsonify({"error": "A TextTraits request_id is required for this HubSpot action."}), 400)
    analysis = get_hubspot_email_analysis(request_id)
    if not analysis:
        return None, (jsonify({"error": "No TextTraits analysis was found for that request_id.", "request_id": request_id}), 404)
    return analysis, None


def hubspot_best_finding(analysis: dict[str, Any]) -> dict[str, Any]:
    findings = analysis.get("findings") if isinstance(analysis.get("findings"), list) else []
    for severity in ("high", "medium", "low"):
        for finding in findings:
            if str(finding.get("severity") or "").lower() == severity:
                return finding
    return findings[0] if findings else {}


def hubspot_queue_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def hubspot_portal_from_payload(payload: dict[str, Any]) -> str:
    input_fields = payload.get("inputFields") if isinstance(payload.get("inputFields"), dict) else {}
    return first_text_value(
        payload.get("portal_id"),
        payload.get("portalId"),
        payload.get("tenant_id"),
        input_fields.get("portal_id"),
        input_fields.get("portalId"),
        max_length=160,
    )


def hubspot_workspace_from_payload(payload: dict[str, Any], portal_id: str = "") -> str:
    input_fields = payload.get("inputFields") if isinstance(payload.get("inputFields"), dict) else {}
    return first_text_value(
        payload.get("workspace_id"),
        input_fields.get("workspace_id"),
        f"hubspot_{portal_id}" if portal_id else "",
        max_length=160,
    )


def hubspot_route_owner_map(payload: dict[str, Any] | None = None) -> dict[str, str]:
    configured: dict[str, str] = {}
    raw_env = os.getenv("TEXTTRAITS_HUBSPOT_ROUTE_OWNER_MAP", "").strip()
    if raw_env:
        try:
            env_map = json.loads(raw_env)
        except json.JSONDecodeError:
            env_map = {}
        if isinstance(env_map, dict):
            configured.update({hubspot_queue_key(key): str(value).strip()[:160] for key, value in env_map.items() if str(value or "").strip()})
    raw_payload = {}
    if isinstance(payload, dict):
        for key in ("route_owner_map", "review_owner_map", "owner_map", "queue_owner_map"):
            if isinstance(payload.get(key), dict):
                raw_payload.update(payload[key])
    configured.update({hubspot_queue_key(key): str(value).strip()[:160] for key, value in raw_payload.items() if str(value or "").strip()})
    if isinstance(payload, dict):
        portal_id = hubspot_portal_from_payload(payload)
        workspace_id = hubspot_workspace_from_payload(payload, portal_id)
        stored = get_hubspot_route_owner_map(portal_id, workspace_id) if portal_id else None
        if stored and isinstance(stored.get("route_owner_map"), dict):
            configured.update(
                {
                    hubspot_queue_key(key): str(value).strip()[:160]
                    for key, value in stored["route_owner_map"].items()
                    if str(value or "").strip()
                }
            )
    configured.update({hubspot_queue_key(key): str(value).strip()[:160] for key, value in raw_payload.items() if str(value or "").strip()})
    return {key: value for key, value in configured.items() if key and value}


def hubspot_owner_for_analysis(payload: dict[str, Any], analysis: dict[str, Any], output_fields: dict[str, Any] | None = None) -> tuple[str, str]:
    explicit = first_text_value(
        payload.get("hubspot_owner_id"),
        payload.get("owner_id"),
        nested_value(payload, ("inputFields", "hubspot_owner_id")),
        nested_value(payload, ("inputFields", "owner_id")),
        analysis.get("owner_id"),
        max_length=160,
    )
    if explicit:
        return explicit, "explicit"
    owner_map = hubspot_route_owner_map(payload)
    finding = hubspot_best_finding(analysis)
    output = output_fields if isinstance(output_fields, dict) else {}
    candidates = [
        analysis.get("route"),
        output.get("texttraits_owner_queue"),
        output.get("texttraits_route"),
        finding.get("owner_queue"),
        finding.get("blocker_level"),
        analysis.get("gate"),
    ]
    for candidate in candidates:
        owner_id = owner_map.get(hubspot_queue_key(candidate))
        if owner_id:
            return owner_id, f"route:{candidate}"
    default_owner = first_text_value(
        payload.get("default_hubspot_owner_id"),
        payload.get("default_owner_id"),
        os.getenv("TEXTTRAITS_HUBSPOT_DEFAULT_REVIEW_OWNER_ID"),
        max_length=160,
    )
    if not default_owner:
        portal_id = hubspot_portal_from_payload(payload)
        workspace_id = hubspot_workspace_from_payload(payload, portal_id)
        stored = get_hubspot_route_owner_map(portal_id, workspace_id) if portal_id else None
        default_owner = first_text_value(stored.get("default_owner_id") if stored else "", max_length=160)
    if default_owner:
        return default_owner, "default"
    return "", ""


def normalize_hubspot_owner(item: dict[str, Any]) -> dict[str, Any]:
    owner_id = first_text_value(item.get("id"), item.get("ownerId"), item.get("hubspot_owner_id"), max_length=160)
    first_name = first_text_value(item.get("firstName"), item.get("first_name"), max_length=120)
    last_name = first_text_value(item.get("lastName"), item.get("last_name"), max_length=120)
    email = first_text_value(item.get("email"), item.get("userEmail"), max_length=240)
    name = " ".join(part for part in (first_name, last_name) if part).strip() or email or owner_id
    teams = []
    raw_teams = item.get("teams") if isinstance(item.get("teams"), list) else []
    for team in raw_teams:
        if isinstance(team, dict):
            teams.append(
                {
                    "id": first_text_value(team.get("id"), team.get("teamId"), max_length=160),
                    "name": first_text_value(team.get("name"), team.get("teamName"), max_length=200),
                    "primary": bool(team.get("primary") or team.get("isPrimary")),
                }
            )
    return {
        "id": owner_id,
        "user_id": first_text_value(item.get("userId"), item.get("user_id"), max_length=160),
        "user_id_including_inactive": first_text_value(item.get("userIdIncludingInactive"), max_length=160),
        "name": name,
        "email": email,
        "archived": bool(item.get("archived")),
        "teams": teams,
        "created_at": first_text_value(item.get("createdAt"), item.get("created_at"), max_length=80),
        "updated_at": first_text_value(item.get("updatedAt"), item.get("updated_at"), max_length=80),
    }


def hubspot_analysis_association_type_map(payload: dict[str, Any] | None = None) -> dict[str, str]:
    configured: dict[str, str] = {}

    def merge(raw: Any) -> None:
        if isinstance(raw, str) and raw.strip():
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                return
        if not isinstance(raw, dict):
            return
        for key, value in raw.items():
            clean_key = hubspot_object_api_type(key).strip().lower()
            clean_value = str(value or "").strip()
            if clean_key and clean_value:
                configured[clean_key] = clean_value[:80]

    raw_env = os.getenv("TEXTTRAITS_HUBSPOT_ANALYSIS_ASSOCIATION_TYPE_IDS", "").strip()
    if raw_env:
        try:
            merge(json.loads(raw_env))
        except json.JSONDecodeError:
            logging.warning("Invalid TEXTTRAITS_HUBSPOT_ANALYSIS_ASSOCIATION_TYPE_IDS JSON.")
    if isinstance(payload, dict):
        input_fields = payload.get("inputFields") if isinstance(payload.get("inputFields"), dict) else {}
        for key in ("analysis_association_type_ids", "association_type_ids", "analysisAssociationTypeIds", "associationTypeIds"):
            merge(payload.get(key))
            merge(input_fields.get(key))
    return configured


def hubspot_association_payload(to_id: Any, association_type_id: Any, category: str = "USER_DEFINED") -> dict[str, Any]:
    clean_id = first_text_value(to_id, max_length=160)
    clean_type_id = first_text_value(association_type_id, max_length=80)
    if not clean_id or not clean_type_id:
        return {}
    try:
        association_type: int | str = int(clean_type_id)
    except ValueError:
        association_type = clean_type_id
    return {
        "to": {"id": clean_id},
        "types": [
            {
                "associationCategory": first_text_value(category, "USER_DEFINED", max_length=80),
                "associationTypeId": association_type,
            }
        ],
    }


def hubspot_analysis_record_associations(payload: dict[str, Any], analysis: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    input_fields = payload.get("inputFields") if isinstance(payload.get("inputFields"), dict) else {}
    supplied = payload.get("analysis_record_associations")
    if supplied is None:
        supplied = payload.get("analysisRecordAssociations")
    if supplied is None:
        supplied = payload.get("associations")
    if supplied is None:
        supplied = input_fields.get("analysis_record_associations") or input_fields.get("analysisRecordAssociations") or input_fields.get("associations")
    if isinstance(supplied, str) and supplied.strip():
        try:
            supplied = json.loads(supplied)
        except json.JSONDecodeError:
            supplied = None
    if isinstance(supplied, list) and supplied:
        return [item for item in supplied if isinstance(item, dict)][:20], []

    type_map = hubspot_analysis_association_type_map(payload)
    category = first_text_value(
        payload.get("analysis_association_category"),
        input_fields.get("analysis_association_category"),
        payload.get("association_category"),
        input_fields.get("association_category"),
        payload.get("associationCategory"),
        input_fields.get("associationCategory"),
        os.getenv("TEXTTRAITS_HUBSPOT_ANALYSIS_ASSOCIATION_CATEGORY"),
        "USER_DEFINED",
        max_length=80,
    )
    candidate_ids = {
        "contacts": first_text_value(payload.get("contact_id"), payload.get("contactId"), input_fields.get("contact_id"), input_fields.get("contactId"), analysis.get("contact_id"), max_length=160),
        "companies": first_text_value(payload.get("company_id"), payload.get("companyId"), input_fields.get("company_id"), input_fields.get("companyId"), analysis.get("company_id"), max_length=160),
        "deals": first_text_value(payload.get("deal_id"), payload.get("dealId"), input_fields.get("deal_id"), input_fields.get("dealId"), analysis.get("deal_id"), max_length=160),
        "tickets": first_text_value(payload.get("ticket_id"), payload.get("ticketId"), input_fields.get("ticket_id"), input_fields.get("ticketId"), analysis.get("ticket_id"), max_length=160),
        "campaigns": first_text_value(payload.get("campaign_id"), payload.get("campaignId"), input_fields.get("campaign_id"), input_fields.get("campaignId"), analysis.get("campaign_id"), max_length=160),
        "marketing_emails": first_text_value(payload.get("email_id"), payload.get("emailId"), input_fields.get("email_id"), input_fields.get("emailId"), payload.get("template_id"), input_fields.get("template_id"), analysis.get("template_id"), max_length=160),
    }
    object_type = hubspot_object_api_type(first_text_value(payload.get("object_type"), payload.get("objectType"), input_fields.get("object_type"), input_fields.get("objectType"), analysis.get("object_type"), max_length=160)).lower()
    object_id = first_text_value(payload.get("object_id"), payload.get("objectId"), input_fields.get("object_id"), input_fields.get("objectId"), analysis.get("object_id"), max_length=160)
    if object_type and object_id:
        candidate_ids[object_type] = object_id

    associations: list[dict[str, Any]] = []
    missing: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for object_key, target_id in candidate_ids.items():
        if not target_id:
            continue
        association_type_id = type_map.get(object_key)
        if not association_type_id:
            missing.append({"object_type": object_key, "object_id": target_id, "reason": "association_type_id_required"})
            continue
        association = hubspot_association_payload(target_id, association_type_id, category)
        if not association:
            continue
        dedupe_key = (str(association["to"]["id"]), str(association["types"][0]["associationTypeId"]))
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        associations.append(association)
    return associations[:20], missing[:20]


def hubspot_writeback_properties(analysis: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, str]:
    finding = hubspot_best_finding(analysis)
    policy = analysis.get("policy") if isinstance(analysis.get("policy"), dict) else {}
    properties = {
        "texttraits_score": str(int(analysis.get("score") or 0)),
        "texttraits_gate": str(analysis.get("gate") or ""),
        "texttraits_route": str(analysis.get("route") or ""),
        "texttraits_policy_version": str(policy.get("version") or ""),
        "texttraits_last_checked_at": str(analysis.get("created_at") or utc_now()),
        "texttraits_blocker_reason": first_text_value(finding.get("title"), finding.get("next_step"), analysis.get("gate"), max_length=500),
        "texttraits_request_id": str(analysis.get("request_id") or ""),
        "texttraits_content_hash": str(analysis.get("content_hash") or ""),
    }
    for key, value in (extra or {}).items():
        if value not in (None, ""):
            properties[str(key)[:120]] = str(value)[:500]
    return properties


def hubspot_review_status_from_event(event: dict[str, Any]) -> str:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    status = first_text_value(payload.get("review_status"), payload.get("status"), max_length=80)
    action = str(event.get("action") or "")
    if status:
        return status
    if action == "send_to_marketing_review":
        return "queued"
    if action == "assign_reviewer":
        return "assigned"
    if action == "approve_review":
        return "approved"
    if action == "reject_review":
        return "rejected"
    if action in {"mark_reviewed", "resolve_review"}:
        return "resolved"
    if action == "rerun_analysis":
        return "rerun_requested"
    return "open"


def hubspot_review_sync_properties(analysis: dict[str, Any], event: dict[str, Any]) -> dict[str, str]:
    properties = hubspot_writeback_properties(analysis)
    properties.update(
        {
            "texttraits_review_status": hubspot_review_status_from_event(event),
            "texttraits_review_action": str(event.get("action") or "")[:80],
            "texttraits_review_updated_at": str(event.get("created_at") or utc_now())[:80],
            "texttraits_review_updated_by": str(event.get("actor_id") or "")[:160],
        }
    )
    return properties


def hubspot_review_task_properties(event: dict[str, Any]) -> dict[str, str]:
    status = hubspot_review_status_from_event(event)
    action = str(event.get("action") or "")
    actor = str(event.get("actor_id") or "")[:160]
    task_status = "COMPLETED" if status in {"approved", "resolved"} else "NOT_STARTED"
    body = f"TextTraits review action: {action or status}."
    if actor:
        body += f"\nUpdated by: {actor}"
    if status == "rejected":
        body += "\nStatus: rejected. Keep this review task open until the draft is corrected."
    elif status in {"approved", "resolved"}:
        body += "\nStatus: completed in TextTraits."
    return {
        "hs_task_status": task_status,
        "hs_task_body": body[:1200],
        "hs_task_priority": "HIGH" if status == "rejected" else "MEDIUM",
    }


def hubspot_task_id_from_payload(payload: dict[str, Any], event: dict[str, Any]) -> str:
    event_payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    task = event_payload.get("task") if isinstance(event_payload.get("task"), dict) else {}
    return first_text_value(
        payload.get("task_id"),
        payload.get("taskId"),
        payload.get("hubspot_task_id"),
        payload.get("hubspotTaskId"),
        event_payload.get("task_id"),
        event_payload.get("hubspot_task_id"),
        task.get("id"),
        task.get("hs_object_id"),
        max_length=160,
    )


def hubspot_analysis_object_type_from_payload(payload: dict[str, Any]) -> str:
    return first_text_value(
        payload.get("analysis_object_type"),
        payload.get("analysisObjectType"),
        os.getenv("TEXTTRAITS_HUBSPOT_ANALYSIS_OBJECT_TYPE"),
        max_length=160,
    )


def hubspot_search_analysis_record_payload(request_id: str) -> dict[str, Any]:
    return {
        "filterGroups": [
            {
                "filters": [
                    {
                        "propertyName": "texttraits_request_id",
                        "operator": "EQ",
                        "value": request_id,
                    }
                ]
            }
        ],
        "properties": [
            "texttraits_request_id",
            "texttraits_review_status",
            "texttraits_review_action",
            "texttraits_review_updated_at",
            "texttraits_review_updated_by",
        ],
        "limit": 1,
    }


def hubspot_sync_review_action_to_portal(payload: dict[str, Any], event: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    sync_actions: list[dict[str, Any]] = []
    sync_errors: list[dict[str, Any]] = []
    sync_skipped: list[dict[str, str]] = []
    portal_id = hubspot_portal_from_payload(payload) or str(analysis.get("portal_id") or "")
    if not portal_id:
        return {"status": "local_only", "actions": sync_actions, "skipped": [{"action": "hubspot_review_sync", "reason": "portal_id was not supplied."}], "errors": sync_errors}
    try:
        client = HubSpotApiClient(portal_id)
        client.require_scopes(())
    except HubSpotClientError as error:
        return {"status": "failed", "actions": sync_actions, "skipped": sync_skipped, "errors": [hubspot_sync_error("hubspot_connection", error)]}

    properties = hubspot_review_sync_properties(analysis, event)
    object_type, object_id = hubspot_analysis_object_target(payload, analysis)
    if hubspot_payload_flag(payload, "writeback_properties", True):
        if object_type and object_id:
            try:
                response = client.update_crm_object_properties(
                    object_type,
                    object_id,
                    properties,
                    idempotency_key=hubspot_idempotency_key(payload, "review-action-writeback", event.get("request_id"), event.get("action"), object_type, object_id),
                )
                sync_actions.append({"action": "review_crm_property_writeback", "object_type": object_type, "object_id": object_id, "hubspot": scrub_payload(response.get("body", {}))})
            except HubSpotClientError as error:
                sync_errors.append(hubspot_sync_error("review_crm_property_writeback", error))
        else:
            sync_skipped.append({"action": "review_crm_property_writeback", "reason": "object_type and object_id were not supplied."})

    task_id = hubspot_task_id_from_payload(payload, event)
    if hubspot_payload_flag(payload, "update_review_task", True):
        if task_id:
            try:
                response = client.update_task(
                    task_id,
                    hubspot_review_task_properties(event),
                    idempotency_key=hubspot_idempotency_key(payload, "review-action-task", event.get("request_id"), event.get("action"), task_id),
                )
                sync_actions.append({"action": "review_task_updated", "task_id": task_id, "hubspot": scrub_payload(response.get("body", {}))})
            except HubSpotClientError as error:
                sync_errors.append(hubspot_sync_error("review_task_updated", error))
        else:
            sync_skipped.append({"action": "review_task_updated", "reason": "task_id was not supplied."})

    analysis_object_type = hubspot_analysis_object_type_from_payload(payload)
    if hubspot_payload_flag(payload, "sync_analysis_object", True):
        if analysis_object_type:
            try:
                search_response = client.search_crm_objects(analysis_object_type, hubspot_search_analysis_record_payload(str(event.get("request_id") or "")))
                results = search_response.get("body", {}).get("results") if isinstance(search_response.get("body", {}).get("results"), list) else []
                record_id = first_text_value(results[0].get("id") if results else "", max_length=160)
                if record_id:
                    response = client.update_crm_object_properties(
                        analysis_object_type,
                        record_id,
                        properties,
                        idempotency_key=hubspot_idempotency_key(payload, "review-action-analysis-object-update", event.get("request_id"), event.get("action"), record_id),
                    )
                    sync_actions.append({"action": "analysis_object_review_state_updated", "object_type": analysis_object_type, "record_id": record_id, "hubspot": scrub_payload(response.get("body", {}))})
                else:
                    response = client.create_custom_object_record(
                        analysis_object_type,
                        properties,
                        idempotency_key=hubspot_idempotency_key(payload, "review-action-analysis-object-create", event.get("request_id"), event.get("action")),
                    )
                    sync_actions.append({"action": "analysis_object_review_state_created", "object_type": analysis_object_type, "hubspot": scrub_payload(response.get("body", {}))})
            except HubSpotClientError as error:
                sync_errors.append(hubspot_sync_error("analysis_object_review_state_sync", error))
        else:
            sync_skipped.append({"action": "analysis_object_review_state_sync", "reason": "analysis_object_type or TEXTTRAITS_HUBSPOT_ANALYSIS_OBJECT_TYPE is required."})

    return {"status": hubspot_sync_status(sync_actions, sync_errors), "actions": sync_actions, "skipped": sync_skipped, "errors": sync_errors}


def hubspot_marketing_email_payload(payload: dict[str, Any]) -> dict[str, Any]:
    email = payload.get("email") if isinstance(payload.get("email"), dict) else payload.get("marketing_email") if isinstance(payload.get("marketing_email"), dict) else {}
    source = dict(email or payload)
    for key in (
        "portal_id",
        "portalId",
        "tenant_id",
        "workspace_id",
        "source_system",
        "analysis_mode",
        "idempotency_key",
        "idempotencyKey",
        "analyze",
        "analyze_after_create",
        "inputFields",
        "hubspotContext",
        "crmContext",
    ):
        source.pop(key, None)
    if "template_path" in source and "templatePath" not in source:
        source["templatePath"] = source.pop("template_path")
    return source


def hubspot_portal_connections_for_context(context: dict[str, Any]) -> list[dict[str, Any]]:
    portal_id = str(context.get("portal_id") or "").strip()
    if not portal_id:
        return list_hubspot_portal_connections(limit=10)
    connection = get_hubspot_portal_connection(portal_id)
    return [connection] if connection else []


def hubspot_default_property_payload(object_type: str, property_def: dict[str, Any]) -> dict[str, Any]:
    clean_object_type = hubspot_object_api_type(object_type)
    payload = {
        "groupName": HUBSPOT_OBJECT_PROPERTY_GROUPS.get(clean_object_type, "texttraits"),
        "name": property_def["name"],
        "label": property_def["label"],
        "type": property_def["type"],
        "fieldType": property_def["fieldType"],
        "description": property_def.get("description", ""),
    }
    if property_def.get("options"):
        payload["options"] = property_def["options"]
    return payload


def hubspot_analysis_schema_payload(payload: dict[str, Any]) -> dict[str, Any]:
    object_name = first_text_value(payload.get("object_name"), payload.get("name"), "texttraits_analysis", max_length=80)
    object_name = re.sub(r"[^a-zA-Z0-9_]+", "_", object_name).strip("_") or "texttraits_analysis"
    if not re.match(r"^[A-Za-z]", object_name):
        object_name = f"texttraits_{object_name}"
    associated = payload.get("associatedObjects") if isinstance(payload.get("associatedObjects"), list) else payload.get("associated_objects") if isinstance(payload.get("associated_objects"), list) else ["0-1", "0-2", "0-3", "0-5"]
    return {
        "name": object_name[:80],
        "description": "TextTraits email and campaign review decisions, joined to HubSpot records for reporting and governance.",
        "labels": {"singular": "TextTraits Analysis", "plural": "TextTraits Analyses"},
        "primaryDisplayProperty": "texttraits_request_id",
        "secondaryDisplayProperties": ["texttraits_score", "texttraits_gate", "texttraits_route", "texttraits_policy_version"],
        "searchableProperties": ["texttraits_request_id", "texttraits_content_hash", "texttraits_campaign_id", "texttraits_template_id"],
        "requiredProperties": ["texttraits_request_id"],
        "associatedObjects": [str(item)[:80] for item in associated if str(item or "").strip()][:12],
        "properties": list(TEXTTRAITS_ANALYSIS_SCHEMA_PROPERTIES),
    }


def hubspot_default_webhook_subscriptions(payload: dict[str, Any]) -> list[dict[str, Any]]:
    supplied = payload.get("subscriptions")
    if isinstance(supplied, list) and supplied:
        return [scrub_payload(item) for item in supplied if isinstance(item, dict)][:25]
    return [
        {"eventType": "contact.propertyChange", "propertyName": "email", "active": True},
        {"eventType": "contact.propertyChange", "propertyName": "lifecyclestage", "active": True},
        {"eventType": "company.propertyChange", "propertyName": "name", "active": True},
        {"eventType": "deal.propertyChange", "propertyName": "dealstage", "active": True},
        {"eventType": "ticket.propertyChange", "propertyName": "hs_pipeline_stage", "active": True},
    ]


def hubspot_webhook_property_copy_fields(raw_event: dict[str, Any]) -> dict[str, str]:
    property_name = first_text_value(raw_event.get("propertyName"), raw_event.get("property_name"), raw_event.get("property"), max_length=120).lower()
    property_value = first_text_value(raw_event.get("propertyValue"), raw_event.get("property_value"), raw_event.get("value"), max_length=HUBSPOT_MAX_INGRESS_BYTES)
    if not property_name or not property_value:
        return {}
    subject_names = {"subject", "email_subject", "hs_email_subject", "hs_subject"}
    body_names = {"body", "email_body", "hs_email_body", "html", "html_body", "email_html", "hs_email_html", "rich_text", "richtext"}
    if property_name in subject_names:
        return {"email_subject": property_value}
    if property_name in body_names:
        return {"email_body": property_value}
    return {}


def hubspot_webhook_should_report_rescore(raw_event: dict[str, Any], event_type: str) -> bool:
    marker = " ".join(
        str(value or "")
        for value in (
            event_type,
            raw_event.get("objectType"),
            raw_event.get("objectTypeId"),
            raw_event.get("propertyName"),
            raw_event.get("subscriptionType"),
        )
    ).lower()
    return any(token in marker for token in ("email", "marketing", "campaign", "template", "draft"))


def hubspot_webhook_rescore_payload(raw_event: dict[str, Any], portal_id: str, event_type: str, event_id: str) -> tuple[dict[str, Any] | None, dict[str, str]]:
    if not isinstance(raw_event, dict):
        return None, {"status": "ignored", "reason": "Webhook event was not an object."}
    input_fields = raw_event.get("inputFields") if isinstance(raw_event.get("inputFields"), dict) else {}
    mapped_input_fields = {**input_fields, **hubspot_webhook_property_copy_fields(raw_event)}
    event_payload = {
        **raw_event,
        "portal_id": portal_id,
        "tenant_id": portal_id,
        "source_system": "hubspot_webhook_rescore",
        "analysis_mode": "webhook_rescore",
        "inputFields": mapped_input_fields,
        "campaign_id": first_text_value(raw_event.get("campaign_id"), raw_event.get("campaignId"), nested_value(raw_event, ("campaign", "id")), max_length=160),
        "template_id": first_text_value(raw_event.get("template_id"), raw_event.get("templateId"), raw_event.get("email_id"), raw_event.get("emailId"), raw_event.get("objectId"), max_length=160),
        "idempotency_key": hubspot_idempotency_key(
            raw_event,
            "webhook-rescore",
            portal_id,
            event_type,
            event_id,
            raw_event.get("objectId"),
            raw_event.get("occurredAt") or raw_event.get("occurred_at"),
        ),
    }
    normalized = normalize_hubspot_marketing_email_payload(event_payload, "webhook_rescore")
    normalized_fields = normalized.get("inputFields") if isinstance(normalized.get("inputFields"), dict) else {}
    subject = first_text_value(normalized_fields.get("email_subject"), normalized_fields.get("subject"), max_length=300)
    body = first_text_value(normalized_fields.get("email_body"), normalized_fields.get("body"), normalized_fields.get("text"), max_length=HUBSPOT_MAX_INGRESS_BYTES)
    if not subject and not body:
        if hubspot_webhook_should_report_rescore(raw_event, event_type):
            return None, {"status": "copy_unavailable", "reason": "Webhook event did not include reviewable subject/body/html copy."}
        return None, {"status": "ignored", "reason": "Webhook event is not a copy-bearing draft change."}
    return normalized, {"status": "ready"}


def hubspot_review_segment_payloads(payload: dict[str, Any]) -> list[dict[str, Any]]:
    supplied = payload.get("segments")
    if isinstance(supplied, list) and supplied:
        return [scrub_payload(item) for item in supplied if isinstance(item, dict)][:10]
    object_type_id = first_text_value(payload.get("objectTypeId"), payload.get("object_type_id"), "0-1", max_length=80)
    property_name = first_text_value(payload.get("propertyName"), payload.get("property_name"), "texttraits_gate", max_length=120)
    prefix = first_text_value(payload.get("name_prefix"), "TextTraits", max_length=120)

    def segment(label: str, value: str) -> dict[str, Any]:
        return {
            "name": f"{prefix} - {label}",
            "objectTypeId": object_type_id,
            "processingType": "DYNAMIC",
            "filterBranch": {
                "filterBranchType": "OR",
                "filterBranches": [
                    {
                        "filterBranchType": "AND",
                        "filterBranches": [],
                        "filters": [
                            {
                                "filterType": "PROPERTY",
                                "property": property_name,
                                "operation": {
                                    "operationType": "ENUMERATION",
                                    "operator": "IS_EQUAL_TO",
                                    "value": value,
                                },
                            }
                        ],
                    }
                ],
                "filters": [],
            },
        }

    return [
        segment("Ready to send", "ready"),
        segment("Needs review", "needs_review"),
        segment("Blocked", "blocked"),
    ]


def hubspot_live_action_response(action: str, response: dict[str, Any], context: dict[str, Any], extra: dict[str, Any] | None = None):
    body = response.get("body") if isinstance(response, dict) else {}
    log_event(current_user_id(), action, {"portal_id": context.get("portal_id"), **scrub_payload(extra or {})})
    return jsonify({"ok": True, "action": action, "hubspot": scrub_payload(body), "context": public_hubspot_context(context), "details": scrub_payload(extra or {})})


@app.post("/v1/integrations/hubspot/app-card/latest")
@rate_limited(120)
def hubspot_app_card_latest():
    payload, error = hubspot_payload_or_error()
    if error:
        return error
    input_fields = payload.get("inputFields") if isinstance(payload.get("inputFields"), dict) else payload
    context = hubspot_context_from_payload(payload, input_fields)
    if context.get("_validation_error"):
        return jsonify({"error": context["_validation_error"]}), 403
    filters = {
        "workspace_id": context.get("workspace_id"),
        "portal_id": context.get("portal_id"),
        "object_type": context.get("object_type"),
        "object_id": context.get("object_id"),
        "campaign_id": context.get("campaign_id"),
        "template_id": context.get("template_id"),
        "contact_id": context.get("contact_id"),
        "company_id": context.get("company_id"),
        "deal_id": context.get("deal_id"),
    }
    analyses = list_hubspot_email_analyses(limit=10, filters={key: value for key, value in filters.items() if value})
    latest = analyses[0] if analyses else None
    review_states = list_hubspot_review_states(limit=10, filters={"request_id": latest["request_id"]} if latest else {})
    return jsonify(
        {
            "ok": True,
            "latest": latest,
            "review_states": review_states,
            "context": public_hubspot_context(context),
            "connections": hubspot_portal_connections_for_context(context),
        }
    )


def hubspot_payload_flag(payload: dict[str, Any], key: str, default: bool = True) -> bool:
    value = payload.get(key)
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def hubspot_analyze_sync_payload(payload: dict[str, Any]) -> dict[str, Any]:
    input_fields = payload.get("inputFields") if isinstance(payload.get("inputFields"), dict) else {}
    analysis_mode = first_text_value(payload.get("analysis_mode"), input_fields.get("analysis_mode"), "hubspot_analyze_and_sync", max_length=80)
    marketing_shape = any(
        key in payload
        for key in ("marketingEmail", "marketing_email", "email", "html", "html_body", "email_html", "emailId", "email_id")
    ) or any(key in input_fields for key in ("html", "html_body", "email_html", "emailId", "email_id"))
    if marketing_shape:
        return normalize_hubspot_marketing_email_payload(payload, analysis_mode)
    normalized = {**payload}
    normalized["analysis_mode"] = analysis_mode
    normalized["source_system"] = first_text_value(payload.get("source_system"), input_fields.get("source_system"), "hubspot_analyze_and_sync", max_length=80)
    return normalized


def hubspot_analysis_object_target(payload: dict[str, Any], analysis: dict[str, Any]) -> tuple[str, str]:
    object_type = hubspot_object_api_type(
        first_text_value(payload.get("object_type"), payload.get("objectType"), analysis.get("object_type"), max_length=160)
    )
    object_id = first_text_value(
        payload.get("object_id"),
        payload.get("objectId"),
        analysis.get("object_id"),
        analysis.get("contact_id"),
        analysis.get("company_id"),
        analysis.get("deal_id"),
        max_length=160,
    )
    if not object_type:
        if analysis.get("contact_id"):
            object_type = "contacts"
        elif analysis.get("company_id"):
            object_type = "companies"
        elif analysis.get("deal_id"):
            object_type = "deals"
    return object_type, object_id


def hubspot_sync_status(actions: list[dict[str, Any]], errors: list[dict[str, Any]]) -> str:
    if errors and actions:
        return "partial"
    if errors:
        return "failed"
    if actions:
        return "synced"
    return "analysis_only"


def hubspot_sync_error(action: str, error: Exception) -> dict[str, Any]:
    return {
        "action": action,
        "error": str(error),
        "status_code": int(getattr(error, "status_code", 502) or 502),
        "details": scrub_payload(getattr(error, "payload", {}) if isinstance(getattr(error, "payload", {}), dict) else {}),
    }


@app.post("/v1/integrations/hubspot/analyze-and-sync")
@rate_limited(30)
def hubspot_analyze_and_sync():
    payload, error = hubspot_payload_or_error()
    if error:
        return error
    client, context, error = hubspot_client_and_context(payload)
    if error:
        return error
    try:
        client.ensure_connected(())
    except HubSpotClientError as connection_error:
        return hubspot_error_response(connection_error)

    analysis_payload = hubspot_analyze_sync_payload(payload)
    result, status_code = hubspot_analysis_result(analysis_payload, "hubspot_analyze_and_sync")
    if status_code != 200:
        return jsonify(result), status_code

    output_fields = result.get("outputFields") if isinstance(result.get("outputFields"), dict) else {}
    request_id = str(output_fields.get("texttraits_request_id") or "")
    analysis = get_hubspot_email_analysis(request_id) or {}
    sync_actions: list[dict[str, Any]] = []
    sync_errors: list[dict[str, Any]] = []
    sync_skipped: list[dict[str, str]] = []
    object_type, object_id = hubspot_analysis_object_target(payload, analysis)
    extra_properties = payload.get("properties") if isinstance(payload.get("properties"), dict) else {}

    if hubspot_payload_flag(payload, "writeback_properties", True):
        if object_type and object_id:
            try:
                response = client.update_crm_object_properties(
                    object_type,
                    object_id,
                    hubspot_writeback_properties(analysis, extra=extra_properties),
                    idempotency_key=hubspot_idempotency_key(payload, "analyze-sync-writeback", request_id, object_type, object_id),
                )
                sync_actions.append({"action": "crm_property_writeback", "object_type": object_type, "object_id": object_id, "hubspot": scrub_payload(response.get("body", {}))})
            except HubSpotClientError as sync_error:
                sync_errors.append(hubspot_sync_error("crm_property_writeback", sync_error))
        else:
            sync_skipped.append({"action": "crm_property_writeback", "reason": "object_type and object_id were not supplied by HubSpot context."})

    if hubspot_payload_flag(payload, "record_review_state", True) and analysis.get("gate") != "ready":
        finding = hubspot_best_finding(analysis)
        try:
            review_event = save_hubspot_review_event(
                request_id,
                "send_to_marketing_review",
                {
                    "review_status": "queued",
                    "owner_queue": analysis.get("route") or output_fields.get("texttraits_owner_queue") or "",
                    "blocker_level": finding.get("blocker_level") or output_fields.get("texttraits_blocker_level") or "",
                    "recommendation": finding.get("next_step") or output_fields.get("texttraits_next_step") or "",
                },
                actor_id=first_text_value(payload.get("actor_id"), nested_value(payload, ("hubspotContext", "user", "email")), max_length=160),
                status="queued",
            )
            sync_actions.append({"action": "review_state_queued", "review_event": review_event})
        except ValueError as sync_error:
            sync_errors.append({"action": "review_state_queued", "error": str(sync_error), "status_code": 400, "details": {}})

    if hubspot_payload_flag(payload, "create_review_task", True) and analysis.get("gate") != "ready":
        finding = hubspot_best_finding(analysis)
        task_properties = {
            "hs_timestamp": first_text_value(payload.get("due_at"), payload.get("hs_timestamp"), utc_now(), max_length=80),
            "hs_task_body": first_text_value(
                payload.get("task_body"),
                f"TextTraits routed this draft to {analysis.get('route')}.\nRequest ID: {request_id}\nScore: {analysis.get('score')}\nGate: {analysis.get('gate')}\nNext step: {finding.get('next_step') or output_fields.get('texttraits_next_step') or 'Review the finding and resolve before sending.'}",
                max_length=1200,
            ),
            "hs_task_subject": first_text_value(payload.get("task_subject"), f"Review TextTraits {analysis.get('gate')} draft", max_length=240),
            "hs_task_status": first_text_value(payload.get("task_status"), "NOT_STARTED", max_length=80),
            "hs_task_priority": first_text_value(payload.get("task_priority"), "HIGH" if analysis.get("gate") == "blocked" else "MEDIUM", max_length=80),
            "hs_task_type": first_text_value(payload.get("task_type"), "TODO", max_length=80),
        }
        owner_id, owner_source = hubspot_owner_for_analysis(payload, analysis, output_fields)
        if owner_id:
            task_properties["hubspot_owner_id"] = owner_id
        associations = payload.get("associations") if isinstance(payload.get("associations"), list) else None
        try:
            response = client.create_task(
                task_properties,
                associations=associations,
                idempotency_key=hubspot_idempotency_key(payload, "analyze-sync-task", request_id),
            )
            sync_actions.append({"action": "review_task_created", "owner_source": owner_source, "hubspot": scrub_payload(response.get("body", {}))})
        except HubSpotClientError as sync_error:
            sync_errors.append(hubspot_sync_error("review_task_created", sync_error))

    analysis_object_type = first_text_value(
        payload.get("analysis_object_type"),
        payload.get("analysisObjectType"),
        os.getenv("TEXTTRAITS_HUBSPOT_ANALYSIS_OBJECT_TYPE"),
        max_length=160,
    )
    if hubspot_payload_flag(payload, "create_analysis_record", True):
        if analysis_object_type:
            properties = hubspot_writeback_properties(analysis, extra=extra_properties)
            properties.update(
                {
                    "texttraits_campaign_id": str(analysis.get("campaign_id") or ""),
                    "texttraits_template_id": str(analysis.get("template_id") or ""),
                    "texttraits_source_system": str(analysis.get("source_system") or ""),
                }
            )
            associations, missing_associations = hubspot_analysis_record_associations(payload, analysis)
            try:
                response = client.create_custom_object_record(
                    analysis_object_type,
                    properties,
                    associations=associations,
                    idempotency_key=hubspot_idempotency_key(payload, "analyze-sync-analysis-object", request_id),
                )
                sync_actions.append(
                    {
                        "action": "analysis_object_record_created",
                        "object_type": analysis_object_type,
                        "association_count": len(associations),
                        "hubspot": scrub_payload(response.get("body", {})),
                    }
                )
                if missing_associations and not associations:
                    sync_skipped.append(
                        {
                            "action": "analysis_object_associations",
                            "reason": "Real HubSpot association type IDs are required before TextTraits can associate the analysis record.",
                        }
                    )
            except HubSpotClientError as sync_error:
                sync_errors.append(hubspot_sync_error("analysis_object_record_created", sync_error))
        else:
            sync_skipped.append({"action": "analysis_object_record_created", "reason": "analysis_object_type or TEXTTRAITS_HUBSPOT_ANALYSIS_OBJECT_TYPE is required."})

    app_id = first_text_value(payload.get("app_id"), payload.get("appId"), os.getenv("TEXTTRAITS_HUBSPOT_APP_ID"), max_length=160)
    event_template_id = first_text_value(payload.get("eventTemplateId"), payload.get("event_template_id"), os.getenv("TEXTTRAITS_HUBSPOT_TIMELINE_EVENT_TEMPLATE_ID"), max_length=160)
    timeline_object_id = first_text_value(payload.get("timeline_object_id"), payload.get("objectId"), object_id, max_length=160)
    if hubspot_payload_flag(payload, "create_timeline_event", True):
        if app_id and event_template_id and timeline_object_id:
            try:
                response = client.create_timeline_event(
                    app_id,
                    {
                        "eventTemplateId": event_template_id,
                        "objectId": timeline_object_id,
                        "tokens": {
                            "texttraits_score": str(analysis.get("score") or ""),
                            "texttraits_gate": str(analysis.get("gate") or ""),
                            "texttraits_route": str(analysis.get("route") or ""),
                            "texttraits_request_id": request_id,
                            "texttraits_blocker_reason": str(output_fields.get("texttraits_blocker_reason") or ""),
                        },
                    },
                    idempotency_key=hubspot_idempotency_key(payload, "analyze-sync-timeline", request_id, timeline_object_id),
                )
                sync_actions.append({"action": "timeline_event_created", "hubspot": scrub_payload(response.get("body", {}))})
            except HubSpotClientError as sync_error:
                sync_errors.append(hubspot_sync_error("timeline_event_created", sync_error))
        else:
            sync_skipped.append({"action": "timeline_event_created", "reason": "app_id, eventTemplateId, and objectId are required for HubSpot timeline events."})

    if hubspot_payload_flag(payload, "associate_campaign_asset", False):
        campaign_id = first_text_value(payload.get("campaign_id"), analysis.get("campaign_id"), max_length=160)
        asset_id = first_text_value(payload.get("asset_id"), payload.get("assetId"), payload.get("email_id"), payload.get("emailId"), analysis.get("template_id"), max_length=160)
        asset_type = first_text_value(payload.get("asset_type"), payload.get("assetType"), "MARKETING_EMAIL", max_length=80)
        if campaign_id and asset_id:
            try:
                response = client.associate_campaign_asset(
                    campaign_id,
                    asset_type,
                    asset_id,
                    idempotency_key=hubspot_idempotency_key(payload, "analyze-sync-campaign-asset", campaign_id, asset_type, asset_id),
                )
                sync_actions.append({"action": "campaign_asset_associated", "campaign_id": campaign_id, "asset_type": asset_type, "asset_id": asset_id, "hubspot": scrub_payload(response.get("body", {}))})
            except HubSpotClientError as sync_error:
                sync_errors.append(hubspot_sync_error("campaign_asset_associated", sync_error))
        else:
            sync_skipped.append({"action": "campaign_asset_associated", "reason": "campaign_id and asset_id are required."})

    status = hubspot_sync_status(sync_actions, sync_errors)
    output_fields["texttraits_sync_status"] = status
    output_fields["texttraits_sync_actions"] = ", ".join(action.get("action", "") for action in sync_actions)[:500]
    result["outputFields"] = output_fields
    result["sync"] = {"status": status, "actions": sync_actions, "skipped": sync_skipped, "errors": sync_errors}
    log_event(current_user_id(), "hubspot_analyze_and_sync", {"portal_id": context.get("portal_id"), "request_id": request_id, "status": status, "errors": len(sync_errors)})
    return jsonify(result), 207 if sync_errors else 200


@app.post("/v1/integrations/hubspot/campaigns/create")
@rate_limited(30)
def hubspot_campaign_create():
    payload, error = hubspot_payload_or_error()
    if error:
        return error
    client, context, error = hubspot_client_and_context(payload)
    if error:
        return error
    properties = payload.get("properties") if isinstance(payload.get("properties"), dict) else {}
    properties = {**properties}
    name = first_text_value(payload.get("name"), properties.get("hs_name"), max_length=240)
    if name and not properties.get("hs_name"):
        properties["hs_name"] = name
    if not properties.get("hs_name"):
        return jsonify({"error": "HubSpot campaign creation requires properties.hs_name or name."}), 400
    try:
        response = client.create_campaign(properties, idempotency_key=hubspot_idempotency_key(payload, "campaign", context.get("portal_id"), properties.get("hs_name")))
    except HubSpotClientError as error:
        return hubspot_error_response(error)
    return hubspot_live_action_response("hubspot_campaign_created", response, context, {"campaign_name": properties.get("hs_name")})


@app.post("/v1/integrations/hubspot/campaigns/update")
@rate_limited(30)
def hubspot_campaign_update():
    payload, error = hubspot_payload_or_error()
    if error:
        return error
    client, context, error = hubspot_client_and_context(payload)
    if error:
        return error
    campaign_id = first_text_value(payload.get("campaign_id"), payload.get("campaignGuid"), payload.get("id"), max_length=160)
    properties = payload.get("properties") if isinstance(payload.get("properties"), dict) else {}
    if not campaign_id or not properties:
        return jsonify({"error": "HubSpot campaign update requires campaign_id and properties."}), 400
    try:
        response = client.update_campaign(campaign_id, properties, idempotency_key=hubspot_idempotency_key(payload, "campaign-update", context.get("portal_id"), campaign_id))
    except HubSpotClientError as error:
        return hubspot_error_response(error)
    return hubspot_live_action_response("hubspot_campaign_updated", response, context, {"campaign_id": campaign_id})


@app.post("/v1/integrations/hubspot/campaigns/list")
@rate_limited(60)
def hubspot_campaign_list():
    payload, error = hubspot_payload_or_error()
    if error:
        return error
    client, context, error = hubspot_client_and_context(payload)
    if error:
        return error
    params = {
        key: payload.get(key)
        for key in ("after", "limit", "sort", "createdAfter", "createdBefore", "updatedAfter", "updatedBefore")
        if payload.get(key) not in (None, "")
    }
    params["limit"] = clamp_int(params.get("limit"), 1, 100, 20)
    query = first_text_value(payload.get("query"), payload.get("search"), payload.get("name"), max_length=120).lower()
    try:
        response = client.list_campaigns(params=params)
    except HubSpotClientError as error:
        return hubspot_error_response(error)
    body = response.get("body", {}) if isinstance(response, dict) else {}
    results = body.get("results") if isinstance(body.get("results"), list) else []
    if query:
        results = [
            item
            for item in results
            if query
            in json.dumps(
                {
                    "id": item.get("id") or item.get("campaignGuid") if isinstance(item, dict) else "",
                    "name": nested_value(item, ("properties", "hs_name")) if isinstance(item, dict) else "",
                    "raw": item if isinstance(item, dict) else {},
                },
                default=str,
            ).lower()
        ]
    campaigns = []
    for item in results[: int(params["limit"])]:
        if not isinstance(item, dict):
            continue
        properties = item.get("properties") if isinstance(item.get("properties"), dict) else {}
        campaign_id = first_text_value(item.get("id"), item.get("campaignGuid"), properties.get("hs_campaign_guid"), max_length=160)
        campaigns.append(
            {
                "id": campaign_id,
                "name": first_text_value(properties.get("hs_name"), item.get("name"), item.get("title"), campaign_id, max_length=240),
                "start_date": first_text_value(properties.get("hs_start_date"), item.get("startDate"), max_length=80),
                "end_date": first_text_value(properties.get("hs_end_date"), item.get("endDate"), max_length=80),
                "status": first_text_value(properties.get("hs_campaign_status"), item.get("status"), max_length=80),
                "hubspot": scrub_payload(item),
            }
        )
    return jsonify({"ok": True, "campaigns": campaigns, "paging": scrub_payload(body.get("paging", {})), "context": public_hubspot_context(context)})


@app.post("/v1/integrations/hubspot/campaigns/associate-asset")
@rate_limited(60)
def hubspot_campaign_associate_asset():
    payload, error = hubspot_payload_or_error()
    if error:
        return error
    client, context, error = hubspot_client_and_context(payload)
    if error:
        return error
    campaign_id = first_text_value(payload.get("campaign_id"), payload.get("campaignGuid"), max_length=160)
    asset_type = first_text_value(payload.get("asset_type"), payload.get("assetType"), "MARKETING_EMAIL", max_length=80)
    asset_id = first_text_value(payload.get("asset_id"), payload.get("assetId"), payload.get("email_id"), payload.get("emailId"), max_length=160)
    remove = bool(payload.get("remove") or payload.get("delete"))
    if not campaign_id or not asset_id:
        return jsonify({"error": "Campaign asset association requires campaign_id and asset_id."}), 400
    try:
        if remove:
            response = client.remove_campaign_asset(campaign_id, asset_type, asset_id, idempotency_key=hubspot_idempotency_key(payload, "campaign-asset-remove", campaign_id, asset_type, asset_id))
        else:
            response = client.associate_campaign_asset(campaign_id, asset_type, asset_id, idempotency_key=hubspot_idempotency_key(payload, "campaign-asset", campaign_id, asset_type, asset_id))
    except HubSpotClientError as error:
        return hubspot_error_response(error)
    return hubspot_live_action_response("hubspot_campaign_asset_associated", response, context, {"campaign_id": campaign_id, "asset_type": asset_type, "asset_id": asset_id, "remove": remove})


@app.post("/v1/integrations/hubspot/campaigns/assets")
@rate_limited(60)
def hubspot_campaign_assets():
    payload, error = hubspot_payload_or_error()
    if error:
        return error
    client, context, error = hubspot_client_and_context(payload)
    if error:
        return error
    campaign_id = first_text_value(payload.get("campaign_id"), payload.get("campaignGuid"), payload.get("id"), max_length=160)
    asset_type = first_text_value(payload.get("asset_type"), payload.get("assetType"), "MARKETING_EMAIL", max_length=80)
    params = {key: payload.get(key) for key in ("after", "limit", "startDate", "endDate") if payload.get(key) not in (None, "")}
    if not campaign_id:
        return jsonify({"error": "Campaign asset lookup requires campaign_id."}), 400
    try:
        response = client.list_campaign_assets(campaign_id, asset_type, params=params)
    except HubSpotClientError as error:
        return hubspot_error_response(error)
    return hubspot_live_action_response("hubspot_campaign_assets_fetched", response, context, {"campaign_id": campaign_id, "asset_type": asset_type})


def hubspot_campaign_review_result(payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    input_fields = payload.get("inputFields") if isinstance(payload.get("inputFields"), dict) else payload
    context = hubspot_context_from_payload(payload, input_fields)
    if context.get("_validation_error"):
        return {"error": context["_validation_error"]}, 403
    portal_id = first_text_value(
        payload.get("portal_id"),
        payload.get("portalId"),
        payload.get("tenant_id"),
        input_fields.get("portal_id"),
        input_fields.get("portalId"),
        context.get("portal_id"),
        max_length=160,
    )
    if not portal_id:
        return {"error": "HubSpot portal_id is required for live HubSpot API actions."}, 400
    try:
        client = HubSpotApiClient(portal_id)
    except HubSpotClientError as error:
        return hubspot_error_payload(error)
    campaign_id = first_text_value(payload.get("campaign_id"), payload.get("campaignGuid"), payload.get("id"), max_length=160)
    asset_types = hubspot_asset_types_from_payload(payload)
    limit = clamp_int(payload.get("limit"), 1, min(HUBSPOT_MAX_BATCH_EMAILS, 100), 25)
    if not campaign_id:
        return {"error": "Live campaign review requires campaign_id."}, 400
    try:
        client.require_scopes(("marketing.campaigns.read",))
    except HubSpotClientError as scope_error:
        return hubspot_error_payload(scope_error)
    analyses: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    asset_map: dict[str, dict[str, Any]] = {}
    raw_asset_count = 0
    for asset_type in asset_types:
        try:
            assets_response = client.list_campaign_assets(campaign_id, asset_type, params={"limit": limit})
        except HubSpotClientError as error:
            errors.append({"asset_type": asset_type, "stage": "list_assets", "error": str(error), "details": scrub_payload(getattr(error, "payload", {}))})
            asset_map[asset_type] = {"label": HUBSPOT_CAMPAIGN_ASSET_TYPE_LABELS.get(asset_type, asset_type), "assets": [], "status": "error"}
            continue
        assets_body = assets_response.get("body", {}) if isinstance(assets_response, dict) else {}
        raw_assets = assets_body.get("results") if isinstance(assets_body.get("results"), list) else nested_value(assets_body, ("paging", "results"))
        if not isinstance(raw_assets, list):
            raw_assets = []
        raw_asset_count += len(raw_assets)
        asset_map[asset_type] = {
            "label": HUBSPOT_CAMPAIGN_ASSET_TYPE_LABELS.get(asset_type, asset_type),
            "assets": [],
            "paging": scrub_payload(assets_body.get("paging", {})),
            "status": "loaded",
        }
        for index, asset in enumerate(raw_assets[:limit]):
            if not isinstance(asset, dict):
                continue
            asset_id = hubspot_asset_id(asset)
            if not asset_id:
                skipped.append({"asset_type": asset_type, "stage": "asset_id", "reason": "Campaign asset did not expose an ID.", "asset": scrub_payload(asset)})
                continue
            review_asset = asset
            copy_source = "campaign_asset_metadata"
            if asset_type in HUBSPOT_DIRECT_COPY_ASSET_TYPES:
                try:
                    asset_response = client.get_campaign_asset_copy(asset_type, asset_id)
                    review_asset = asset_response.get("body", {}) if isinstance(asset_response, dict) else {}
                    copy_source = HUBSPOT_DIRECT_COPY_SOURCE_LABELS.get(asset_type, f"{asset_type.lower()}_api")
                except HubSpotClientError as fetch_error:
                    errors.append({"asset_type": asset_type, "asset_id": asset_id, "stage": "fetch", "error": str(fetch_error), "details": scrub_payload(getattr(fetch_error, "payload", {}))})
                    asset_map[asset_type]["assets"].append({"id": asset_id, "name": hubspot_asset_label(asset, asset_type, asset_id), "status": "fetch_error"})
                    continue
            candidate_text = hubspot_asset_candidate_text(review_asset)
            asset_name = hubspot_asset_label(review_asset if isinstance(review_asset, dict) else asset, asset_type, asset_id)
            map_item = {"id": asset_id, "name": asset_name, "asset_type": asset_type, "copy_source": copy_source}
            if not candidate_text or len(candidate_text.split()) < 3:
                map_item["status"] = "metadata_only"
                skipped.append({"asset_type": asset_type, "asset_id": asset_id, "asset_name": asset_name, "reason": "No reviewable copy was returned by the available HubSpot asset payload."})
                asset_map[asset_type]["assets"].append(map_item)
                continue
            normalized = hubspot_campaign_asset_review_payload(payload, context, campaign_id, asset_type, review_asset, index, copy_source)
            analysis, status_code = hubspot_analysis_result(normalized, "hubspot_live_campaign_review")
            if status_code == 200:
                gate = str(analysis.get("outputFields", {}).get("texttraits_gate") or "unknown")
                score = int(analysis.get("outputFields", {}).get("texttraits_score") or 0)
                map_item.update({"status": "analyzed", "gate": gate, "score": score, "request_id": analysis.get("outputFields", {}).get("texttraits_request_id")})
                asset_map[asset_type]["assets"].append(map_item)
                analyses.append(analysis)
            else:
                map_item["status"] = "analysis_error"
                asset_map[asset_type]["assets"].append(map_item)
                errors.append({"asset_type": asset_type, "asset_id": asset_id, "stage": "analysis", "status": status_code, "error": analysis.get("error", "Analysis failed.")})
    gate_counts: dict[str, int] = {}
    scores: list[int] = []
    for analysis in analyses:
        gate = str(analysis.get("outputFields", {}).get("texttraits_gate") or "unknown")
        score = int(analysis.get("outputFields", {}).get("texttraits_score") or 0)
        gate_counts[gate] = gate_counts.get(gate, 0) + 1
        scores.append(score)
    summary = {
        "campaign_id": campaign_id,
        "asset_types": asset_types,
        "assets_seen": raw_asset_count,
        "analyzed": len(analyses),
        "skipped": len(skipped),
        "errors": len(errors),
        "gate_counts": gate_counts,
        "average_score": round(sum(scores) / len(scores), 1) if scores else 0,
        "health": "blocked" if gate_counts.get("blocked") else "needs_review" if gate_counts.get("needs_review") else "ready" if analyses else "not_reviewed",
        "copy_coverage": hubspot_campaign_copy_coverage(asset_map),
    }
    log_event(current_user_id(), "hubspot_live_campaign_review", {"portal_id": context.get("portal_id"), "campaign_id": campaign_id, "analyzed": len(analyses), "asset_types": asset_types})
    return {"ok": True, "summary": summary, "analyses": analyses, "errors": errors[:10], "skipped": skipped[:25], "asset_map": scrub_payload(asset_map), "context": public_hubspot_context(context)}, 200


@app.post("/v1/integrations/hubspot/campaigns/review")
@rate_limited(20)
def hubspot_campaign_review():
    payload, error = hubspot_payload_or_error()
    if error:
        return error
    result, status_code = hubspot_campaign_review_result(payload)
    return jsonify(result), status_code


def hubspot_campaign_workflow_output(result: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    gate_counts = summary.get("gate_counts") if isinstance(summary.get("gate_counts"), dict) else {}
    health = first_text_value(summary.get("health"), "not_reviewed", max_length=80)
    asset_types = [str(item) for item in summary.get("asset_types", []) if str(item or "").strip()] if isinstance(summary.get("asset_types"), list) else []
    blocked = int(gate_counts.get("blocked") or 0)
    needs_review = int(gate_counts.get("needs_review") or 0)
    ready = int(gate_counts.get("ready") or 0)
    if health == "blocked":
        route = "Compliance Review"
        next_step = "Route blocked campaign assets to the configured compliance or legal review queue before scheduling."
    elif health == "needs_review":
        route = "Marketing Review"
        next_step = "Route needs-review campaign assets to the lifecycle or marketing review queue before scheduling."
    elif health == "ready":
        route = "Sending System"
        next_step = "All reviewable campaign assets are ready under the active TextTraits policy."
    else:
        route = "Campaign Mapping"
        next_step = "No reviewable copy was found. Confirm mapped campaign assets and granted HubSpot scopes before scheduling."
    workspace_id = first_text_value(payload.get("workspace_id"), f"hubspot_{payload.get('portal_id') or payload.get('portalId') or ''}", "hubspot_campaign", max_length=160)
    content_hash = hubspot_content_hash(
        f"{summary.get('campaign_id')}:{','.join(asset_types)}:{summary.get('assets_seen')}:{summary.get('analyzed')}:{summary.get('skipped')}:{summary.get('errors')}",
        workspace_id,
    )
    return {
        "texttraits_campaign_health": health,
        "texttraits_gate": health,
        "texttraits_route": route,
        "texttraits_next_step": next_step,
        "texttraits_campaign_id": str(summary.get("campaign_id") or ""),
        "texttraits_asset_types": ", ".join(asset_types)[:500],
        "texttraits_assets_seen": int(summary.get("assets_seen") or 0),
        "texttraits_analyzed_count": int(summary.get("analyzed") or 0),
        "texttraits_ready_count": ready,
        "texttraits_needs_review_count": needs_review,
        "texttraits_blocked_count": blocked,
        "texttraits_skipped_count": int(summary.get("skipped") or 0),
        "texttraits_error_count": int(summary.get("errors") or 0),
        "texttraits_average_score": float(summary.get("average_score") or 0),
        "texttraits_copy_coverage": ", ".join(summary.get("copy_coverage", {}).get("reviewed_asset_types", []))[:500],
        "texttraits_coverage_score": float(summary.get("copy_coverage", {}).get("coverage_score") or 0),
        "texttraits_coverage_label": str(summary.get("copy_coverage", {}).get("coverage_label") or "")[:120],
        "texttraits_content_hash": content_hash,
    }


@app.post("/v1/integrations/hubspot/workflow-actions/review-campaign-assets")
@rate_limited(20)
def hubspot_workflow_action_review_campaign_assets():
    payload, error = hubspot_payload_or_error()
    if error:
        return error
    result, status_code = hubspot_campaign_review_result(payload)
    if status_code != 200:
        return jsonify(result), status_code
    output_fields = hubspot_campaign_workflow_output(result, payload)
    return jsonify(
        {
            "ok": True,
            "workflow": "hubspot_campaign_asset_workflow_action",
            "outputFields": output_fields,
            "summary": result.get("summary", {}),
            "asset_map": result.get("asset_map", {}),
            "errors": result.get("errors", []),
            "skipped": result.get("skipped", []),
        }
    )


@app.post("/v1/integrations/hubspot/marketing-emails/create-draft")
@rate_limited(30)
def hubspot_marketing_email_create_draft():
    payload, error = hubspot_payload_or_error()
    if error:
        return error
    client, context, error = hubspot_client_and_context(payload)
    if error:
        return error
    email_payload = hubspot_marketing_email_payload(payload)
    if not (email_payload.get("name") and email_payload.get("subject") and email_payload.get("templatePath")):
        return jsonify({"error": "Marketing email creation requires name, subject, and templatePath."}), 400
    try:
        response = client.create_marketing_email(email_payload, idempotency_key=hubspot_idempotency_key(payload, "marketing-email", context.get("portal_id"), email_payload.get("name"), email_payload.get("subject")))
    except HubSpotClientError as error:
        return hubspot_error_response(error)
    result = {"ok": True, "action": "hubspot_marketing_email_created", "hubspot": scrub_payload(response.get("body", {})), "context": public_hubspot_context(context)}
    if payload.get("analyze_after_create", True):
        analysis_payload = normalize_hubspot_marketing_email_payload({**payload, "marketingEmail": response.get("body", {}), "portal_id": context.get("portal_id")}, "marketing_email_preflight")
        analysis, status_code = hubspot_analysis_result(analysis_payload, "hubspot_marketing_email_preflight")
        result["analysis"] = analysis if status_code == 200 else {"error": analysis.get("error"), "status": status_code}
    log_event(current_user_id(), "hubspot_marketing_email_created", {"portal_id": context.get("portal_id"), "name": email_payload.get("name")})
    return jsonify(result)


@app.post("/v1/integrations/hubspot/marketing-emails/update-draft")
@rate_limited(30)
def hubspot_marketing_email_update_draft():
    payload, error = hubspot_payload_or_error()
    if error:
        return error
    client, context, error = hubspot_client_and_context(payload)
    if error:
        return error
    email_id = first_text_value(payload.get("email_id"), payload.get("emailId"), payload.get("id"), max_length=160)
    email_payload = hubspot_marketing_email_payload(payload)
    email_payload.pop("id", None)
    if not email_id or not email_payload:
        return jsonify({"error": "Marketing email update requires email_id and fields to update."}), 400
    try:
        response = client.update_marketing_email(email_id, email_payload, idempotency_key=hubspot_idempotency_key(payload, "marketing-email-update", context.get("portal_id"), email_id))
    except HubSpotClientError as error:
        return hubspot_error_response(error)
    return hubspot_live_action_response("hubspot_marketing_email_updated", response, context, {"email_id": email_id})


@app.post("/v1/integrations/hubspot/marketing-emails/fetch")
@rate_limited(60)
def hubspot_marketing_email_fetch():
    payload, error = hubspot_payload_or_error()
    if error:
        return error
    client, context, error = hubspot_client_and_context(payload)
    if error:
        return error
    email_id = first_text_value(payload.get("email_id"), payload.get("emailId"), payload.get("id"), max_length=160)
    if not email_id:
        return jsonify({"error": "Marketing email fetch requires email_id."}), 400
    try:
        response = client.get_marketing_email(email_id)
    except HubSpotClientError as error:
        return hubspot_error_response(error)
    result = {"ok": True, "email": scrub_payload(response.get("body", {})), "context": public_hubspot_context(context)}
    if payload.get("analyze", True):
        analysis_payload = normalize_hubspot_marketing_email_payload({**payload, "marketingEmail": response.get("body", {}), "portal_id": context.get("portal_id")}, "marketing_email_preflight")
        analysis, status_code = hubspot_analysis_result(analysis_payload, "hubspot_marketing_email_preflight")
        result["analysis"] = analysis if status_code == 200 else {"error": analysis.get("error"), "status": status_code}
    log_event(current_user_id(), "hubspot_marketing_email_fetched", {"portal_id": context.get("portal_id"), "email_id": email_id})
    return jsonify(result)


@app.post("/v1/integrations/hubspot/marketing-emails/pre-publish-guardrail")
@rate_limited(30)
def hubspot_marketing_email_pre_publish_guardrail():
    payload, error = hubspot_payload_or_error()
    if error:
        return error
    client, context, error = hubspot_client_and_context(payload)
    if error:
        return error
    email_id = first_text_value(payload.get("email_id"), payload.get("emailId"), payload.get("id"), max_length=160)
    if not email_id:
        return jsonify({"error": "Pre-publish guardrail requires email_id."}), 400
    try:
        response = client.get_marketing_email(email_id)
    except HubSpotClientError as error:
        return hubspot_error_response(error)
    email_body = response.get("body", {}) if isinstance(response, dict) else {}
    analysis_payload = normalize_hubspot_marketing_email_payload(
        {
            **payload,
            "marketingEmail": email_body,
            "portal_id": context.get("portal_id"),
            "template_id": email_id,
            "analysis_mode": "marketing_email_pre_publish_guardrail",
            "delivery_context": {
                **(payload.get("delivery_context") if isinstance(payload.get("delivery_context"), dict) else {}),
                "guardrail_surface": "hubspot_marketing_email_pre_publish",
                "email_state": first_text_value(email_body.get("state"), email_body.get("status"), max_length=80),
            },
        },
        "marketing_email_pre_publish_guardrail",
    )
    analysis, status_code = hubspot_analysis_result(analysis_payload, "hubspot_marketing_email_pre_publish_guardrail")
    if status_code != 200:
        return jsonify(analysis), status_code
    gate = str(analysis.get("outputFields", {}).get("texttraits_gate") or "")
    decision = {
        "publish_allowed": gate == "ready",
        "gate": gate,
        "route": analysis.get("outputFields", {}).get("texttraits_route"),
        "next_step": analysis.get("outputFields", {}).get("texttraits_next_step"),
        "blocker_reason": analysis.get("outputFields", {}).get("texttraits_blocker_reason"),
        "score": analysis.get("outputFields", {}).get("texttraits_score"),
        "policy_version": analysis.get("outputFields", {}).get("texttraits_policy_version"),
        "note": "This guardrail returns a pre-publish decision. It does not publish, unpublish, or mutate the HubSpot email unless a separate approved update action is run.",
    }
    log_event(current_user_id(), "hubspot_marketing_email_pre_publish_guardrail", {"portal_id": context.get("portal_id"), "email_id": email_id, "gate": gate})
    return jsonify({"ok": True, "email": scrub_payload(email_body), "guardrail": decision, "analysis": analysis, "context": public_hubspot_context(context)})


@app.post("/v1/integrations/hubspot/marketing-emails/list")
@rate_limited(60)
def hubspot_marketing_email_list():
    payload, error = hubspot_payload_or_error()
    if error:
        return error
    client, context, error = hubspot_client_and_context(payload)
    if error:
        return error
    params = {
        key: payload.get(key)
        for key in ("after", "limit", "createdAfter", "createdBefore", "updatedAfter", "updatedBefore", "state")
        if payload.get(key) not in (None, "")
    }
    params["limit"] = clamp_int(params.get("limit"), 1, 100, 20)
    query = first_text_value(payload.get("query"), payload.get("search"), payload.get("name"), max_length=120).lower()
    try:
        response = client.list_marketing_emails(params=params)
    except HubSpotClientError as error:
        return hubspot_error_response(error)
    body = response.get("body", {}) if isinstance(response, dict) else {}
    results = body.get("results") if isinstance(body.get("results"), list) else []
    if query:
        results = [
            item
            for item in results
            if isinstance(item, dict)
            and query
            in json.dumps(
                {
                    "id": item.get("id") or item.get("emailId"),
                    "name": item.get("name"),
                    "subject": item.get("subject"),
                    "campaign": item.get("campaignId") or item.get("campaignGuid"),
                },
                default=str,
            ).lower()
        ]
    emails = []
    for item in results[: int(params["limit"])]:
        if not isinstance(item, dict):
            continue
        email_id = first_text_value(item.get("id"), item.get("emailId"), item.get("hs_email_id"), max_length=160)
        emails.append(
            {
                "id": email_id,
                "name": first_text_value(item.get("name"), item.get("subject"), email_id, max_length=240),
                "subject": first_text_value(item.get("subject"), nested_value(item, ("content", "subject")), max_length=300),
                "campaign_id": first_text_value(item.get("campaignId"), item.get("campaignGuid"), nested_value(item, ("campaign", "id")), max_length=160),
                "state": first_text_value(item.get("state"), item.get("status"), max_length=80),
                "updated_at": first_text_value(item.get("updatedAt"), item.get("updated"), max_length=80),
                "hubspot": scrub_payload(item),
            }
        )
    return jsonify({"ok": True, "emails": emails, "paging": scrub_payload(body.get("paging", {})), "context": public_hubspot_context(context)})


@app.post("/v1/integrations/hubspot/owners/list")
@rate_limited(30)
def hubspot_owners_list():
    payload, error = hubspot_payload_or_error()
    if error:
        return error
    client, context, error = hubspot_client_and_context(payload)
    if error:
        return error
    params = {
        key: payload.get(key)
        for key in ("after", "archived")
        if payload.get(key) not in (None, "")
    }
    params["limit"] = clamp_int(payload.get("limit"), 1, 500, 100)
    query = first_text_value(payload.get("query"), payload.get("search"), max_length=120).lower()
    try:
        response = client.list_owners(params=params)
    except HubSpotClientError as error:
        return hubspot_error_response(error)
    body = response.get("body", {}) if isinstance(response, dict) else {}
    results = body.get("results") if isinstance(body.get("results"), list) else []
    owners = [normalize_hubspot_owner(item) for item in results if isinstance(item, dict)]
    if query:
        owners = [
            owner
            for owner in owners
            if query
            in json.dumps(
                {"id": owner["id"], "name": owner["name"], "email": owner["email"], "teams": owner["teams"]},
                default=str,
            ).lower()
        ]
    portal_id = hubspot_portal_from_payload(payload) or str(context.get("portal_id") or "")
    workspace_id = hubspot_workspace_from_payload(payload, portal_id)
    routing = get_hubspot_route_owner_map(portal_id, workspace_id) if portal_id else None
    return jsonify(
        {
            "ok": True,
            "owners": owners,
            "paging": scrub_payload(body.get("paging", {})),
            "routing": routing or {"portal_id": portal_id, "workspace_id": workspace_id, "route_owner_map": {}, "default_owner_id": ""},
            "context": public_hubspot_context(context),
        }
    )


def hubspot_route_map_from_payload(payload: dict[str, Any]) -> dict[str, str]:
    raw = payload.get("route_owner_map") or payload.get("review_owner_map") or payload.get("owner_map") or payload.get("queue_owner_map") or {}
    if isinstance(raw, str) and raw.strip():
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}
    if not isinstance(raw, dict):
        return {}
    return {
        str(key).strip()[:160]: str(value).strip()[:160]
        for key, value in raw.items()
        if str(key or "").strip() and str(value or "").strip()
    }


@app.post("/v1/integrations/hubspot/review-routing/config")
@rate_limited(30)
def hubspot_review_routing_config():
    payload, error = hubspot_payload_or_error()
    if error:
        return error
    portal_id = hubspot_portal_from_payload(payload)
    if not portal_id:
        return jsonify({"error": "HubSpot portal_id is required to configure review routing."}), 400
    workspace_id = hubspot_workspace_from_payload(payload, portal_id)
    route_map = hubspot_route_map_from_payload(payload)
    default_owner_id = first_text_value(payload.get("default_owner_id"), payload.get("default_hubspot_owner_id"), max_length=160)
    should_save = bool(route_map or default_owner_id or str(payload.get("action") or "").lower() == "save")
    try:
        if should_save:
            routing = save_hubspot_route_owner_map(
                portal_id,
                workspace_id,
                route_map,
                default_owner_id=default_owner_id,
                updated_by=first_text_value(payload.get("actor_id"), payload.get("updated_by"), max_length=160),
            )
            log_event(current_user_id(), "hubspot_review_routing_config_saved", {"portal_id": portal_id, "workspace_id": workspace_id, "routes": sorted(route_map.keys())})
        else:
            routing = get_hubspot_route_owner_map(portal_id, workspace_id) or {
                "portal_id": portal_id,
                "workspace_id": workspace_id,
                "route_owner_map": {},
                "default_owner_id": "",
                "updated_at": "",
            }
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify({"ok": True, "routing": routing})


@app.post("/v1/integrations/hubspot/tasks/create-review")
@rate_limited(60)
def hubspot_create_review_task():
    payload, error = hubspot_payload_or_error()
    if error:
        return error
    client, context, error = hubspot_client_and_context(payload)
    if error:
        return error
    analysis, error = hubspot_analysis_for_action(payload)
    if error:
        return error
    finding = hubspot_best_finding(analysis)
    task_body = "\n".join(
        line
        for line in (
            first_text_value(payload.get("body"), payload.get("hs_task_body"), max_length=1200)
            or f"TextTraits routed this draft to {analysis.get('route')}.\nRequest ID: {analysis.get('request_id')}\nScore: {analysis.get('score')}\nGate: {analysis.get('gate')}\nNext step: {finding.get('next_step') or 'Review the finding and resolve before sending.'}",
            first_text_value(payload.get("campaign_url"), payload.get("email_url"), payload.get("hubspot_url"), max_length=500),
        )
        if line
    )
    properties = {
        "hs_timestamp": first_text_value(payload.get("due_at"), payload.get("hs_timestamp"), utc_now(), max_length=80),
        "hs_task_body": task_body,
        "hs_task_subject": first_text_value(payload.get("subject"), payload.get("hs_task_subject"), f"Review TextTraits {analysis.get('gate')} draft", max_length=240),
        "hs_task_status": first_text_value(payload.get("status"), payload.get("hs_task_status"), "NOT_STARTED", max_length=80),
        "hs_task_priority": first_text_value(payload.get("priority"), payload.get("hs_task_priority"), "HIGH" if analysis.get("gate") == "blocked" else "MEDIUM", max_length=80),
        "hs_task_type": first_text_value(payload.get("task_type"), payload.get("hs_task_type"), "TODO", max_length=80),
    }
    owner_id, owner_source = hubspot_owner_for_analysis(payload, analysis)
    if owner_id:
        properties["hubspot_owner_id"] = owner_id
    associations = payload.get("associations") if isinstance(payload.get("associations"), list) else None
    try:
        response = client.create_task(properties, associations=associations, idempotency_key=hubspot_idempotency_key(payload, "review-task", analysis.get("request_id")))
    except HubSpotClientError as error:
        return hubspot_error_response(error)
    save_hubspot_review_event(
        str(analysis.get("request_id") or ""),
        "send_to_marketing_review",
        {"task": scrub_payload(response.get("body", {})), "owner_queue": analysis.get("route"), "owner_source": owner_source, "blocker_level": finding.get("blocker_level") or ""},
        actor_id=first_text_value(payload.get("actor_id"), max_length=160),
        status="created",
    )
    return hubspot_live_action_response("hubspot_review_task_created", response, context, {"request_id": analysis.get("request_id"), "owner_source": owner_source})


@app.post("/v1/integrations/hubspot/properties/writeback")
@rate_limited(60)
def hubspot_properties_writeback():
    payload, error = hubspot_payload_or_error()
    if error:
        return error
    client, context, error = hubspot_client_and_context(payload)
    if error:
        return error
    analysis, error = hubspot_analysis_for_action(payload)
    if error:
        return error
    object_type = hubspot_object_api_type(first_text_value(payload.get("object_type"), analysis.get("object_type"), max_length=160))
    object_id = first_text_value(payload.get("object_id"), analysis.get("object_id"), analysis.get("contact_id"), analysis.get("company_id"), analysis.get("deal_id"), max_length=160)
    if not object_type or not object_id:
        return jsonify({"error": "Property writeback requires object_type and object_id."}), 400
    extra = payload.get("properties") if isinstance(payload.get("properties"), dict) else {}
    properties = hubspot_writeback_properties(analysis, extra=extra)
    try:
        response = client.update_crm_object_properties(object_type, object_id, properties, idempotency_key=hubspot_idempotency_key(payload, "writeback", analysis.get("request_id"), object_type, object_id))
    except HubSpotClientError as error:
        return hubspot_error_response(error)
    return hubspot_live_action_response("hubspot_properties_written_back", response, context, {"request_id": analysis.get("request_id"), "object_type": object_type})


@app.post("/v1/integrations/hubspot/analysis-records/create")
@rate_limited(60)
def hubspot_analysis_record_create():
    payload, error = hubspot_payload_or_error()
    if error:
        return error
    client, context, error = hubspot_client_and_context(payload)
    if error:
        return error
    analysis, error = hubspot_analysis_for_action(payload)
    if error:
        return error
    object_type = first_text_value(payload.get("object_type"), os.getenv("TEXTTRAITS_HUBSPOT_ANALYSIS_OBJECT_TYPE"), max_length=160)
    if not object_type:
        return jsonify({"error": "Set TEXTTRAITS_HUBSPOT_ANALYSIS_OBJECT_TYPE or pass object_type for the TextTraits Analysis custom object."}), 409
    properties = hubspot_writeback_properties(analysis, extra=payload.get("properties") if isinstance(payload.get("properties"), dict) else {})
    properties.update(
        {
            "texttraits_content_hash": str(analysis.get("content_hash") or ""),
            "texttraits_campaign_id": str(analysis.get("campaign_id") or ""),
            "texttraits_template_id": str(analysis.get("template_id") or ""),
            "texttraits_source_system": str(analysis.get("source_system") or ""),
        }
    )
    associations, missing_associations = hubspot_analysis_record_associations(payload, analysis)
    try:
        response = client.create_custom_object_record(
            object_type,
            properties,
            associations=associations,
            idempotency_key=hubspot_idempotency_key(payload, "analysis-object", analysis.get("request_id")),
        )
    except HubSpotClientError as error:
        return hubspot_error_response(error)
    return hubspot_live_action_response(
        "hubspot_analysis_object_created",
        response,
        context,
        {
            "request_id": analysis.get("request_id"),
            "object_type": object_type,
            "association_count": len(associations),
            "missing_associations": missing_associations if not associations else [],
        },
    )


@app.post("/v1/integrations/hubspot/timeline-events/create")
@rate_limited(60)
def hubspot_timeline_event_create():
    payload, error = hubspot_payload_or_error()
    if error:
        return error
    client, context, error = hubspot_client_and_context(payload)
    if error:
        return error
    event_payload = payload.get("event") if isinstance(payload.get("event"), dict) else {}
    app_id = first_text_value(payload.get("app_id"), os.getenv("TEXTTRAITS_HUBSPOT_APP_ID"), max_length=160)
    request_id = first_text_value(payload.get("request_id"), payload.get("texttraits_request_id"), max_length=160)
    if request_id and "tokens" not in event_payload:
        analysis = get_hubspot_email_analysis(request_id) or {}
        finding = hubspot_best_finding(analysis)
        event_payload["tokens"] = {
            "texttraits_score": str(analysis.get("score") or ""),
            "texttraits_gate": str(analysis.get("gate") or ""),
            "texttraits_route": str(analysis.get("route") or ""),
            "texttraits_request_id": request_id,
            "texttraits_blocker_reason": first_text_value(finding.get("title"), max_length=240),
        }
    if payload.get("eventTemplateId") and "eventTemplateId" not in event_payload:
        event_payload["eventTemplateId"] = payload.get("eventTemplateId")
    if payload.get("objectId") and "objectId" not in event_payload:
        event_payload["objectId"] = payload.get("objectId")
    if not app_id or not event_payload.get("eventTemplateId"):
        return jsonify({"error": "Timeline sync requires TEXTTRAITS_HUBSPOT_APP_ID/app_id and eventTemplateId."}), 409
    try:
        response = client.create_timeline_event(app_id, event_payload, idempotency_key=hubspot_idempotency_key(payload, "timeline", request_id, event_payload.get("objectId")))
    except HubSpotClientError as error:
        return hubspot_error_response(error)
    return hubspot_live_action_response("hubspot_timeline_event_created", response, context, {"request_id": request_id, "eventTemplateId": event_payload.get("eventTemplateId")})


@app.post("/v1/integrations/hubspot/lists/create")
@rate_limited(30)
def hubspot_list_create():
    payload, error = hubspot_payload_or_error()
    if error:
        return error
    client, context, error = hubspot_client_and_context(payload)
    if error:
        return error
    list_payload = {
        "name": first_text_value(payload.get("name"), max_length=240),
        "objectTypeId": first_text_value(payload.get("objectTypeId"), payload.get("object_type_id"), "0-1", max_length=80),
        "processingType": first_text_value(payload.get("processingType"), payload.get("processing_type"), "MANUAL", max_length=80).upper(),
    }
    for key in ("filterBranch", "membershipSettings", "listPermissions"):
        if isinstance(payload.get(key), dict):
            list_payload[key] = scrub_payload(payload[key])
    if not list_payload["name"]:
        return jsonify({"error": "HubSpot list creation requires name."}), 400
    try:
        response = client.create_list(list_payload, idempotency_key=hubspot_idempotency_key(payload, "list", context.get("portal_id"), list_payload["name"]))
    except HubSpotClientError as error:
        return hubspot_error_response(error)
    return hubspot_live_action_response("hubspot_list_created", response, context, {"list_name": list_payload["name"]})


def hubspot_list_search_payload(payload: dict[str, Any]) -> dict[str, Any]:
    search_payload: dict[str, Any] = {}
    aliases = {
        "objectTypeId": "object_type_id",
        "processingType": "processing_type",
    }
    for key in ("query", "objectTypeId", "offset", "count"):
        value = payload.get(key)
        if value in (None, "") and aliases.get(key):
            value = payload.get(aliases[key])
        if value not in (None, ""):
            search_payload[key] = value
    if "count" not in search_payload:
        search_payload["count"] = clamp_int(payload.get("limit"), 1, 100, 25)
    if isinstance(payload.get("processingTypes"), list):
        search_payload["processingTypes"] = [str(item).upper() for item in payload["processingTypes"] if str(item or "").strip()][:10]
    elif isinstance(payload.get("processing_types"), list):
        search_payload["processingTypes"] = [str(item).upper() for item in payload["processing_types"] if str(item or "").strip()][:10]
    elif payload.get("processingType") or payload.get("processing_type"):
        search_payload["processingTypes"] = [first_text_value(payload.get("processingType"), payload.get("processing_type"), max_length=80).upper()]
    if isinstance(payload.get("additionalProperties"), list):
        search_payload["additionalProperties"] = [str(item)[:120] for item in payload["additionalProperties"] if str(item or "").strip()][:20]
    return scrub_payload(search_payload)


def normalize_hubspot_list(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "list_id": first_text_value(item.get("listId"), item.get("list_id"), item.get("id"), max_length=160),
        "name": first_text_value(item.get("name"), item.get("listName"), item.get("title"), max_length=240),
        "object_type_id": first_text_value(item.get("objectTypeId"), item.get("object_type_id"), max_length=80),
        "processing_type": first_text_value(item.get("processingType"), item.get("processing_type"), max_length=80),
        "list_version": item.get("listVersion") or item.get("version"),
        "created_at": first_text_value(item.get("createdAt"), item.get("created_at"), max_length=80),
        "updated_at": first_text_value(item.get("updatedAt"), item.get("updated_at"), max_length=80),
        "size": item.get("listSize") or item.get("size") or item.get("hs_list_size"),
        "hubspot": scrub_payload(item),
    }


@app.post("/v1/integrations/hubspot/lists/search")
@rate_limited(30)
def hubspot_lists_search():
    payload, error = hubspot_payload_or_error()
    if error:
        return error
    client, context, error = hubspot_client_and_context(payload)
    if error:
        return error
    list_ids = payload.get("listIds") if isinstance(payload.get("listIds"), list) else payload.get("list_ids") if isinstance(payload.get("list_ids"), list) else []
    include_filters = hubspot_payload_flag(payload, "includeFilters", bool(payload.get("include_filters")))
    try:
        if list_ids:
            response = client.get_lists(params={"listIds": [str(item) for item in list_ids[:100]], "includeFilters": "true" if include_filters else "false"})
            body = response.get("body", {})
            results = body.get("lists") if isinstance(body.get("lists"), list) else body.get("results") if isinstance(body.get("results"), list) else []
        elif payload.get("list_id") or payload.get("listId"):
            list_id = first_text_value(payload.get("list_id"), payload.get("listId"), max_length=160)
            response = client.get_list(list_id, params={"includeFilters": "true" if include_filters else "false"})
            body = response.get("body", {})
            results = [body] if isinstance(body, dict) else []
        else:
            search_payload = hubspot_list_search_payload(payload)
            response = client.search_lists(search_payload)
            body = response.get("body", {})
            results = body.get("lists") if isinstance(body.get("lists"), list) else body.get("results") if isinstance(body.get("results"), list) else []
    except HubSpotClientError as error:
        return hubspot_error_response(error)
    lists = [normalize_hubspot_list(item) for item in results if isinstance(item, dict)]
    return jsonify({"ok": True, "lists": lists, "paging": scrub_payload(body.get("paging", {})), "raw": scrub_payload(body), "context": public_hubspot_context(context)})


@app.post("/v1/integrations/hubspot/lists/memberships")
@rate_limited(30)
def hubspot_list_memberships():
    payload, error = hubspot_payload_or_error()
    if error:
        return error
    client, context, error = hubspot_client_and_context(payload)
    if error:
        return error
    list_id = first_text_value(payload.get("list_id"), payload.get("listId"), max_length=160)
    if not list_id:
        return jsonify({"error": "HubSpot list membership lookup requires list_id."}), 400
    params = {key: payload.get(key) for key in ("after", "offset") if payload.get(key) not in (None, "")}
    params["limit"] = clamp_int(payload.get("limit"), 1, 500, 100)
    try:
        response = client.get_list_memberships(list_id, params=params)
    except HubSpotClientError as error:
        return hubspot_error_response(error)
    body = response.get("body", {}) if isinstance(response, dict) else {}
    results = body.get("results") if isinstance(body.get("results"), list) else []
    return jsonify({"ok": True, "list_id": list_id, "memberships": scrub_payload(results), "paging": scrub_payload(body.get("paging", {})), "context": public_hubspot_context(context)})


def hubspot_record_ids_from_payload(payload: dict[str, Any], *keys: str) -> list[str]:
    values: list[str] = []
    for key in keys:
        raw = payload.get(key)
        if isinstance(raw, list):
            values.extend(str(item).strip() for item in raw if str(item or "").strip())
        elif isinstance(raw, str):
            values.extend(item.strip() for item in re.split(r"[\s,]+", raw) if item.strip())
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = value[:80]
        if clean and clean not in seen:
            seen.add(clean)
            deduped.append(clean)
    return deduped[:1000]


@app.post("/v1/integrations/hubspot/lists/memberships/update")
@rate_limited(30)
def hubspot_list_memberships_update():
    payload, error = hubspot_payload_or_error()
    if error:
        return error
    client, context, error = hubspot_client_and_context(payload)
    if error:
        return error
    list_id = first_text_value(payload.get("list_id"), payload.get("listId"), max_length=160)
    record_ids_to_add = hubspot_record_ids_from_payload(payload, "recordIdsToAdd", "record_ids_to_add", "add_record_ids", "add")
    record_ids_to_remove = hubspot_record_ids_from_payload(payload, "recordIdsToRemove", "record_ids_to_remove", "remove_record_ids", "remove")
    if not list_id:
        return jsonify({"error": "HubSpot list membership update requires list_id."}), 400
    if not record_ids_to_add and not record_ids_to_remove:
        return jsonify({"error": "Provide recordIdsToAdd or recordIdsToRemove for the HubSpot list membership update."}), 400
    try:
        if record_ids_to_add and record_ids_to_remove:
            response = client.add_and_remove_list_memberships(
                list_id,
                record_ids_to_add,
                record_ids_to_remove,
                idempotency_key=hubspot_idempotency_key(payload, "list-memberships-add-remove", context.get("portal_id"), list_id, ",".join(record_ids_to_add), ",".join(record_ids_to_remove)),
            )
            operation = "add_and_remove"
        elif record_ids_to_add:
            response = client.add_list_memberships(
                list_id,
                record_ids_to_add,
                idempotency_key=hubspot_idempotency_key(payload, "list-memberships-add", context.get("portal_id"), list_id, ",".join(record_ids_to_add)),
            )
            operation = "add"
        else:
            response = client.remove_list_memberships(
                list_id,
                record_ids_to_remove,
                idempotency_key=hubspot_idempotency_key(payload, "list-memberships-remove", context.get("portal_id"), list_id, ",".join(record_ids_to_remove)),
            )
            operation = "remove"
    except HubSpotClientError as error:
        return hubspot_error_response(error)
    return hubspot_live_action_response(
        "hubspot_list_memberships_updated",
        response,
        context,
        {"list_id": list_id, "operation": operation, "added": len(record_ids_to_add), "removed": len(record_ids_to_remove)},
    )


@app.post("/v1/integrations/hubspot/lists/create-review-segments")
@rate_limited(20)
def hubspot_review_segments_create():
    payload, error = hubspot_payload_or_error()
    if error:
        return error
    client, context, error = hubspot_client_and_context(payload)
    if error:
        return error
    try:
        client.require_scopes(("crm.lists.write",))
    except HubSpotClientError as scope_error:
        return hubspot_error_response(scope_error)
    created: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for index, segment_payload in enumerate(hubspot_review_segment_payloads(payload)):
        name = first_text_value(segment_payload.get("name"), max_length=240)
        if not name:
            errors.append({"index": index, "error": "Segment payload requires name."})
            continue
        try:
            response = client.create_list(
                segment_payload,
                idempotency_key=hubspot_idempotency_key(payload, "review-segment", context.get("portal_id"), name),
            )
            created.append({"name": name, "hubspot": scrub_payload(response.get("body", {}))})
        except HubSpotClientError as create_error:
            errors.append({"index": index, "name": name, "error": str(create_error), "details": scrub_payload(getattr(create_error, "payload", {}))})
    log_event(current_user_id(), "hubspot_review_segments_created", {"portal_id": context.get("portal_id"), "created": len(created), "errors": len(errors)})
    return jsonify({"ok": not errors, "created": created, "errors": errors, "context": public_hubspot_context(context)}), 207 if errors else 200


@app.post("/v1/integrations/hubspot/properties/provision")
@rate_limited(20)
def hubspot_properties_provision():
    payload, error = hubspot_payload_or_error()
    if error:
        return error
    client, context, error = hubspot_client_and_context(payload)
    if error:
        return error
    supplied_types = payload.get("object_types") if isinstance(payload.get("object_types"), list) else payload.get("objectTypes") if isinstance(payload.get("objectTypes"), list) else ["contacts", "companies", "deals", "tickets"]
    object_types = [hubspot_object_api_type(item) for item in supplied_types if str(item or "").strip()][:8]
    property_defs = payload.get("properties") if isinstance(payload.get("properties"), list) and payload.get("properties") else list(TEXTTRAITS_HUBSPOT_PROPERTIES)
    try:
        client.require_scopes(tuple(crm_write_scope(object_type) for object_type in object_types))
    except HubSpotClientError as scope_error:
        return hubspot_error_response(scope_error)
    results: list[dict[str, Any]] = []
    for object_type in object_types:
        for property_def in property_defs[:20]:
            if not isinstance(property_def, dict) or not property_def.get("name"):
                continue
            property_payload = hubspot_default_property_payload(object_type, property_def)
            try:
                response = client.create_property(
                    object_type,
                    property_payload,
                    idempotency_key=hubspot_idempotency_key(payload, "property", context.get("portal_id"), object_type, property_payload["name"]),
                )
                status = "created"
                body = response.get("body", {})
            except HubSpotClientError as create_error:
                if int(getattr(create_error, "status_code", 0) or 0) == 409:
                    try:
                        response = client.get_property(object_type, str(property_payload["name"]))
                        status = "exists"
                        body = response.get("body", {})
                    except HubSpotClientError as get_error:
                        results.append({"object_type": object_type, "property": property_payload["name"], "status": "error", "error": str(get_error), "details": scrub_payload(getattr(get_error, "payload", {}))})
                        continue
                else:
                    results.append({"object_type": object_type, "property": property_payload["name"], "status": "error", "error": str(create_error), "details": scrub_payload(getattr(create_error, "payload", {}))})
                    continue
            results.append({"object_type": object_type, "property": property_payload["name"], "status": status, "hubspot": scrub_payload(body)})
    has_error = any(item["status"] == "error" for item in results)
    log_event(current_user_id(), "hubspot_properties_provisioned", {"portal_id": context.get("portal_id"), "count": len(results), "has_error": has_error})
    return jsonify({"ok": not has_error, "results": results, "context": public_hubspot_context(context)}), 207 if has_error else 200


@app.post("/v1/integrations/hubspot/analysis-schema/provision")
@rate_limited(10)
def hubspot_analysis_schema_provision():
    payload, error = hubspot_payload_or_error()
    if error:
        return error
    client, context, error = hubspot_client_and_context(payload)
    if error:
        return error
    schema_payload = hubspot_analysis_schema_payload(payload)
    object_name = schema_payload["name"]
    portal_id = str(context.get("portal_id") or "")
    lookup_name = first_text_value(payload.get("object_type"), payload.get("fullyQualifiedName"), f"p{portal_id}_{object_name}" if portal_id else object_name, max_length=160)
    try:
        response = client.create_custom_object_schema(
            schema_payload,
            idempotency_key=hubspot_idempotency_key(payload, "analysis-schema", context.get("portal_id"), object_name),
        )
        status = "created"
        body = response.get("body", {})
    except HubSpotClientError as create_error:
        if int(getattr(create_error, "status_code", 0) or 0) == 409:
            try:
                response = client.get_custom_object_schema(lookup_name)
                status = "exists"
                body = response.get("body", {})
            except HubSpotClientError as get_error:
                return hubspot_error_response(get_error)
        else:
            return hubspot_error_response(create_error)
    log_event(current_user_id(), "hubspot_analysis_schema_provisioned", {"portal_id": context.get("portal_id"), "status": status, "object_name": object_name})
    return jsonify({"ok": True, "status": status, "schema": scrub_payload(body), "requested_schema": scrub_payload(schema_payload), "context": public_hubspot_context(context)})


@app.post("/v1/integrations/hubspot/webhooks/configure")
@rate_limited(10)
def hubspot_webhooks_configure():
    payload, error = hubspot_payload_or_error()
    if error:
        return error
    client, context, error = hubspot_client_and_context(payload)
    if error:
        return error
    app_id = first_text_value(payload.get("app_id"), payload.get("appId"), os.getenv("TEXTTRAITS_HUBSPOT_APP_ID"), max_length=160)
    if not app_id:
        return jsonify({"error": "Webhook configuration requires TEXTTRAITS_HUBSPOT_APP_ID or app_id."}), 409
    target_url = first_text_value(payload.get("targetUrl"), payload.get("target_url"), f"{PUBLIC_BASE_URL.rstrip('/')}/v1/integrations/hubspot/webhooks/receive", max_length=500)
    throttling = payload.get("throttling") if isinstance(payload.get("throttling"), dict) else {}
    max_concurrent = clamp_int(throttling.get("maxConcurrentRequests") or payload.get("maxConcurrentRequests"), 6, 50, 10)
    try:
        settings_response = client.update_webhook_settings(
            app_id,
            {"targetUrl": target_url, "throttling": {"maxConcurrentRequests": max_concurrent}},
            idempotency_key=hubspot_idempotency_key(payload, "webhook-settings", app_id, target_url),
        )
        existing_response = client.list_webhook_subscriptions(app_id)
    except HubSpotClientError as settings_error:
        return hubspot_error_response(settings_error)
    existing_body = existing_response.get("body", {}) if isinstance(existing_response, dict) else {}
    existing_items = existing_body if isinstance(existing_body, list) else existing_body.get("results") if isinstance(existing_body.get("results"), list) else []
    existing_keys = {
        (str(item.get("eventType") or item.get("eventTypeName") or ""), str(item.get("propertyName") or ""))
        for item in existing_items
        if isinstance(item, dict)
    }
    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for subscription in hubspot_default_webhook_subscriptions(payload):
        event_type = first_text_value(subscription.get("eventType"), subscription.get("eventTypeName"), max_length=120)
        property_name = first_text_value(subscription.get("propertyName"), max_length=120)
        if not event_type:
            continue
        if (event_type, property_name) in existing_keys:
            skipped.append({"eventType": event_type, "propertyName": property_name, "status": "exists"})
            continue
        subscription_payload = {"eventType": event_type, "active": bool(subscription.get("active", True))}
        if property_name:
            subscription_payload["propertyName"] = property_name
        try:
            response = client.create_webhook_subscription(
                app_id,
                subscription_payload,
                idempotency_key=hubspot_idempotency_key(payload, "webhook-subscription", app_id, event_type, property_name),
            )
            created.append({"eventType": event_type, "propertyName": property_name, "hubspot": scrub_payload(response.get("body", {}))})
        except HubSpotClientError as subscription_error:
            errors.append({"eventType": event_type, "propertyName": property_name, "error": str(subscription_error), "details": scrub_payload(getattr(subscription_error, "payload", {}))})
    log_event(current_user_id(), "hubspot_webhooks_configured", {"portal_id": context.get("portal_id"), "app_id": app_id, "created": len(created), "errors": len(errors)})
    return jsonify(
        {
            "ok": not errors,
            "settings": scrub_payload(settings_response.get("body", {})),
            "subscriptions": {"created": created, "skipped": skipped, "errors": errors},
            "context": public_hubspot_context(context),
        }
    ), 207 if errors else 200


@app.post("/v1/integrations/hubspot/stats/sync")
@rate_limited(30)
def hubspot_stats_sync():
    payload, error = hubspot_payload_or_error()
    if error:
        return error
    client, context, error = hubspot_client_and_context(payload)
    if error:
        return error
    email_id = first_text_value(payload.get("email_id"), payload.get("emailId"), max_length=160)
    campaign_id = first_text_value(payload.get("campaign_id"), payload.get("campaignGuid"), max_length=160)
    workspace_id = str(context.get("workspace_id") or "hubspot_workspace")
    portal_id = str(context.get("portal_id") or "")
    limit = clamp_int(payload.get("limit"), 1, 50, 10)
    snapshots: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    try:
        if email_id:
            response = client.get_marketing_email(email_id)
            snapshots.append({"target": f"email:{email_id}", "kind": "marketing_email", "campaign_id": campaign_id, "template_id": email_id, "hubspot": response.get("body", {})})
        if campaign_id:
            params = {key: payload.get(key) for key in ("properties", "startDate", "endDate") if payload.get(key) not in (None, "")}
            response = client.get_campaign(campaign_id, params=params)
            campaign_body = response.get("body", {})
            snapshots.append({"target": f"campaign:{campaign_id}", "kind": "campaign", "campaign_id": campaign_id, "template_id": "", "hubspot": campaign_body})
            if hubspot_payload_flag(payload, "include_assets", True):
                for asset_type in hubspot_asset_types_from_payload(payload):
                    try:
                        assets_response = client.list_campaign_assets(campaign_id, asset_type, params={"limit": limit})
                        assets_body = assets_response.get("body", {})
                        asset_results = assets_body.get("results") if isinstance(assets_body.get("results"), list) else []
                        snapshots.append({"target": f"campaign:{campaign_id}:assets:{asset_type}", "kind": "campaign_assets", "campaign_id": campaign_id, "asset_type": asset_type, "template_id": "", "hubspot": assets_body})
                        if asset_type == "MARKETING_EMAIL" and hubspot_payload_flag(payload, "fetch_email_assets", True):
                            for asset in asset_results[:limit]:
                                if not isinstance(asset, dict):
                                    continue
                                asset_id = first_text_value(asset.get("id"), asset.get("assetId"), asset.get("emailId"), asset.get("objectId"), max_length=160)
                                if not asset_id:
                                    continue
                                try:
                                    email_response = client.get_marketing_email(asset_id)
                                    snapshots.append({"target": f"campaign:{campaign_id}:email:{asset_id}", "kind": "campaign_marketing_email", "campaign_id": campaign_id, "template_id": asset_id, "asset_type": asset_type, "hubspot": email_response.get("body", {})})
                                except HubSpotClientError as email_error:
                                    errors.append({"target": f"campaign:{campaign_id}:email:{asset_id}", "error": str(email_error), "details": scrub_payload(getattr(email_error, "payload", {}))})
                    except HubSpotClientError as asset_error:
                        errors.append({"target": f"campaign:{campaign_id}:assets:{asset_type}", "error": str(asset_error), "details": scrub_payload(getattr(asset_error, "payload", {}))})
        if not snapshots:
            return jsonify({"error": "Stats sync requires email_id or campaign_id."}), 400
    except HubSpotClientError as error:
        return hubspot_error_response(error)
    events = []
    now_seconds = int(time.time())
    explicit_request_id = first_text_value(payload.get("request_id"), payload.get("texttraits_request_id"), max_length=160)
    explicit_content_hash = first_text_value(payload.get("content_hash"), max_length=128)
    for snapshot in snapshots:
        body = snapshot.get("hubspot") if isinstance(snapshot.get("hubspot"), dict) else {}
        matched = find_hubspot_email_analysis_for_context(
            workspace_id=workspace_id,
            portal_id=portal_id,
            campaign_id=str(snapshot.get("campaign_id") or ""),
            template_id=str(snapshot.get("template_id") or ""),
        )
        request_id = explicit_request_id or (matched or {}).get("request_id", "")
        content_hash = explicit_content_hash or (matched or {}).get("content_hash", "") or hubspot_content_hash(
            f"{portal_id}:{snapshot.get('target')}:{json.dumps(body, sort_keys=True, default=str)[:2000]}",
            workspace_id,
        )
        event = save_hubspot_outcome_event(
            {
                "request_id": request_id,
                "content_hash": content_hash,
                "workspace_id": workspace_id,
                "tenant_id": context.get("tenant_id"),
                "source_system": "hubspot_stats",
                "event_type": str(snapshot.get("kind") or "stats_sync")[:80],
                "event_id": f"{snapshot.get('target')}:{now_seconds}",
                "payload": {"target": snapshot.get("target"), "campaign_id": snapshot.get("campaign_id"), "template_id": snapshot.get("template_id"), "asset_type": snapshot.get("asset_type"), "hubspot": scrub_payload(body)},
                "occurred_at": utc_now(),
            }
        )
        events.append(event)
    first_snapshot = snapshots[0]
    return jsonify(
        {
            "ok": not errors,
            "target": first_snapshot.get("target"),
            "hubspot": scrub_payload(first_snapshot.get("hubspot", {})),
            "outcome_event": events[0] if events else None,
            "snapshots": [{"target": item.get("target"), "kind": item.get("kind"), "campaign_id": item.get("campaign_id"), "template_id": item.get("template_id"), "asset_type": item.get("asset_type")} for item in snapshots],
            "outcome_events": events,
            "errors": errors,
            "context": public_hubspot_context(context),
        }
    ), 207 if errors else 200


@app.post("/v1/integrations/hubspot/webhooks/receive")
@rate_limited(240)
def hubspot_webhook_receive():
    raw_body = request.get_data(cache=True)
    if len(raw_body) > HUBSPOT_MAX_INGRESS_BYTES:
        return jsonify({"error": f"HubSpot webhook payloads must stay under {HUBSPOT_MAX_INGRESS_BYTES} bytes."}), 413
    auth = getattr(g, "hubspot_ingress_auth", {"mode": "unknown"})
    if PRODUCTION and auth.get("mode") == "unsigned":
        return jsonify({"error": "HubSpot webhook signature validation is required in production."}), 401
    raw_payload = request.get_json(silent=True)
    raw_events = raw_payload if isinstance(raw_payload, list) else raw_payload.get("events") if isinstance(raw_payload, dict) and isinstance(raw_payload.get("events"), list) else [raw_payload] if isinstance(raw_payload, dict) else []
    saved = []
    rescores: list[dict[str, Any]] = []
    errors: list[str] = []
    for raw_event in raw_events[:HUBSPOT_MAX_OUTCOME_EVENTS]:
        if not isinstance(raw_event, dict):
            continue
        portal_id = first_text_value(raw_event.get("portalId"), raw_event.get("portal_id"), max_length=160)
        event_type = first_text_value(raw_event.get("eventType"), raw_event.get("subscriptionType"), raw_event.get("type"), "hubspot_webhook", max_length=120)
        event_id = first_text_value(raw_event.get("eventId"), raw_event.get("event_id"), raw_event.get("subscriptionId"), raw_event.get("objectId"), max_length=160)
        workspace_id = hubspot_workspace_for_portal(portal_id) or "hubspot_webhooks"
        event_hash = hubspot_content_hash(f"{portal_id}:{event_type}:{event_id}:{raw_event.get('objectId')}:{raw_event.get('occurredAt')}", workspace_id)
        record = {
            "request_id": first_text_value(raw_event.get("request_id"), raw_event.get("texttraits_request_id"), max_length=160),
            "content_hash": first_text_value(raw_event.get("content_hash"), raw_event.get("texttraits_content_hash"), event_hash, max_length=128),
            "workspace_id": workspace_id,
            "tenant_id": portal_id,
            "source_system": "hubspot_webhook",
            "event_type": event_type,
            "event_id": event_id,
            "payload": raw_event,
            "occurred_at": str(raw_event.get("occurredAt") or raw_event.get("occurred_at") or utc_now()),
        }
        try:
            saved.append(save_hubspot_outcome_event(record))
        except ValueError as error:
            errors.append(str(error))
        rescore_payload, rescore_status = hubspot_webhook_rescore_payload(raw_event, portal_id, event_type, event_id)
        if rescore_payload:
            analysis_result, analysis_status = hubspot_analysis_result(rescore_payload, "hubspot_webhook_rescore")
            if analysis_status == 200:
                rescores.append(
                    {
                        "event_id": event_id,
                        "status": "analyzed",
                        "request_id": analysis_result.get("outputFields", {}).get("texttraits_request_id"),
                        "gate": analysis_result.get("outputFields", {}).get("texttraits_gate"),
                        "score": analysis_result.get("outputFields", {}).get("texttraits_score"),
                    }
                )
            else:
                rescores.append({"event_id": event_id, "status": "analysis_error", "status_code": analysis_status, "error": analysis_result.get("error", "Analysis failed.")})
        elif rescore_status.get("status") == "copy_unavailable":
            rescores.append({"event_id": event_id, **rescore_status})
    if not saved:
        return jsonify({"error": "No valid HubSpot webhook events were supplied.", "errors": errors[:5]}), 400
    return jsonify({"ok": True, "events": saved, "rescores": rescores, "errors": errors[:5], "ingress_auth": auth, "dropped_events": max(0, len(raw_events) - HUBSPOT_MAX_OUTCOME_EVENTS)})


def hubspot_uninstall_portal_id(payload: Any) -> str:
    events = payload if isinstance(payload, list) else payload.get("events") if isinstance(payload, dict) and isinstance(payload.get("events"), list) else [payload] if isinstance(payload, dict) else []
    for event in events:
        if not isinstance(event, dict):
            continue
        portal_id = first_text_value(
            event.get("portalId"),
            event.get("portal_id"),
            event.get("hubId"),
            event.get("hub_id"),
            event.get("accountId"),
            event.get("account_id"),
            nested_value(event, ("portal", "id")),
            nested_value(event, ("account", "id")),
            max_length=160,
        )
        if portal_id:
            return portal_id
    return ""


@app.post("/v1/integrations/hubspot/app-uninstalled")
@rate_limited(120)
def hubspot_app_uninstalled():
    raw_body = request.get_data(cache=True)
    if len(raw_body) > HUBSPOT_MAX_INGRESS_BYTES:
        return jsonify({"error": f"HubSpot lifecycle payloads must stay under {HUBSPOT_MAX_INGRESS_BYTES} bytes."}), 413
    auth = getattr(g, "hubspot_ingress_auth", {"mode": "unknown"})
    if PRODUCTION and auth.get("mode") == "unsigned":
        return jsonify({"error": "HubSpot uninstall callbacks require signature validation in production."}), 401
    payload = request.get_json(silent=True) or {}
    portal_id = hubspot_uninstall_portal_id(payload)
    if not portal_id:
        return jsonify({"error": "HubSpot uninstall callback did not include a portal ID."}), 400
    actor = first_text_value(
        nested_value(payload, ("user", "email")) if isinstance(payload, dict) else "",
        nested_value(payload, ("installer", "email")) if isinstance(payload, dict) else "",
        "hubspot_app_uninstall",
        max_length=160,
    )
    connection = disconnect_hubspot_portal(portal_id, actor=actor)
    event = None
    try:
        event = save_hubspot_outcome_event(
            {
                "request_id": "",
                "content_hash": hubspot_content_hash(f"hubspot_uninstall:{portal_id}:{utc_now()}", hubspot_workspace_for_portal(portal_id) or "hubspot_uninstall"),
                "workspace_id": hubspot_workspace_for_portal(portal_id) or "hubspot_uninstall",
                "tenant_id": portal_id,
                "source_system": "hubspot_app_lifecycle",
                "event_type": "app_uninstalled",
                "event_id": first_text_value(payload.get("eventId") if isinstance(payload, dict) else "", f"uninstall:{portal_id}:{int(time.time())}", max_length=160),
                "payload": scrub_payload(payload),
                "occurred_at": str(payload.get("occurredAt") if isinstance(payload, dict) else utc_now()),
            }
        )
    except ValueError:
        logging.exception("hubspot_uninstall_outcome_save_failed")
    log_event(current_user_id(), "hubspot_app_uninstalled", {"portal_id": portal_id, "connection_found": bool(connection), "ingress_auth": auth.get("mode")})
    return jsonify(
        {
            "ok": True,
            "portal_id": portal_id,
            "connection_found": bool(connection),
            "connection": connection,
            "tokens_cleared": bool(connection and not connection.get("tokens_available")),
            "retention": {
                "analyses_retained": True,
                "reason": "TextTraits keeps existing analysis and outcome rows for governance audit until the configured retention policy or an admin retention purge removes them.",
                "admin_retention_endpoint": "/api/enterprise/hubspot/retention",
            },
            "outcome_event": event,
            "ingress_auth": auth,
        }
    )


def hubspot_analysis_filters_from_request() -> dict[str, str]:
    allowed = ("workspace_id", "tenant_id", "source_system", "gate", "route", "campaign_id", "template_id", "contact_id", "company_id", "deal_id", "portal_id", "object_type", "object_id")
    return {key: request.args.get(key, "").strip() for key in allowed if request.args.get(key, "").strip()}


def hubspot_outcome_filters_from_request() -> dict[str, str]:
    allowed = ("request_id", "content_hash", "workspace_id", "tenant_id", "source_system", "event_type")
    return {key: request.args.get(key, "").strip() for key in allowed if request.args.get(key, "").strip()}


def hubspot_surface_readiness(surface: dict[str, Any], connections: list[dict[str, Any]], token_status: dict[str, Any]) -> dict[str, Any]:
    surface_id = str(surface.get("id") or "")
    status = str(surface.get("status") or "")
    required_scopes = tuple(HUBSPOT_SURFACE_REQUIRED_SCOPES.get(surface_id, ()))
    recommended_scopes = tuple(HUBSPOT_SURFACE_RECOMMENDED_SCOPES.get(surface_id, ()))
    requires_oauth = status == "implemented_requires_oauth" or bool(required_scopes)
    connected = [connection for connection in connections if connection.get("status") != "disconnected"]
    portal_statuses: list[dict[str, Any]] = []
    ready_portals: list[str] = []
    for connection in connected[:50]:
        portal_id = str(connection.get("portal_id") or "")
        granted = {str(scope).strip() for scope in connection.get("scopes", []) if str(scope).strip()}
        missing_required = [scope for scope in required_scopes if scope not in granted]
        missing_recommended = [scope for scope in recommended_scopes if scope not in granted]
        tokens_available = bool(connection.get("tokens_available"))
        portal_ready = (not requires_oauth or tokens_available) and hubspot_connection_has_scopes(connection, required_scopes)
        if portal_ready and portal_id:
            ready_portals.append(portal_id)
        portal_statuses.append(
            {
                "portal_id": portal_id,
                "status": connection.get("status") or "unknown",
                "tokens_available": tokens_available,
                "missing_required_scopes": missing_required,
                "missing_recommended_scopes": missing_recommended,
                "ready": portal_ready,
            }
        )
    if not requires_oauth:
        readiness = "ready"
        readiness_label = "Ready with signed or mapped payloads"
    elif ready_portals:
        readiness = "ready"
        readiness_label = "Ready for connected portals"
    elif not token_status.get("ready"):
        readiness = "needs_token_storage"
        readiness_label = "Needs encrypted token storage"
    elif connected:
        readiness = "needs_scopes"
        readiness_label = "Needs HubSpot scopes or mapping"
    else:
        readiness = "needs_connection"
        readiness_label = "Needs HubSpot OAuth connection"
    return {
        "requires_oauth": requires_oauth,
        "required_scopes": list(required_scopes),
        "recommended_scopes": list(recommended_scopes),
        "portal_statuses": portal_statuses,
        "ready_portals": ready_portals[:20],
        "readiness": readiness,
        "readiness_label": readiness_label,
    }


def hubspot_surface_status_for_portal(surface: dict[str, Any], portal_id: str) -> dict[str, Any]:
    if not portal_id:
        return {"ready": surface.get("readiness") == "ready", "missing_required_scopes": [], "missing_recommended_scopes": [], "status": surface.get("readiness") or surface.get("status")}
    for portal_status in surface.get("portal_statuses", []) if isinstance(surface.get("portal_statuses"), list) else []:
        if str(portal_status.get("portal_id") or "") == str(portal_id or ""):
            return portal_status
    return {"ready": False, "missing_required_scopes": list(surface.get("required_scopes", [])), "missing_recommended_scopes": list(surface.get("recommended_scopes", [])), "status": "not_connected"}


def latest_hubspot_timestamp(*items: Any) -> str:
    timestamps: list[str] = []
    for item in items:
        if isinstance(item, list):
            for nested in item:
                if isinstance(nested, dict):
                    timestamps.extend(str(nested.get(key) or "") for key in ("updated_at", "created_at", "occurred_at", "connected_at") if nested.get(key))
        elif isinstance(item, dict):
            timestamps.extend(str(item.get(key) or "") for key in ("updated_at", "created_at", "occurred_at", "connected_at") if item.get(key))
        elif item:
            timestamps.append(str(item))
    return sorted([value for value in timestamps if value], reverse=True)[0] if timestamps else ""


def hubspot_setup_group(label: str, surface_ids: list[str], surfaces_by_id: dict[str, dict[str, Any]], portal_id: str, last_sync_at: str) -> dict[str, Any]:
    surfaces = [surfaces_by_id[surface_id] for surface_id in surface_ids if surface_id in surfaces_by_id]
    statuses = [hubspot_surface_status_for_portal(surface, portal_id) for surface in surfaces]
    missing_required = sorted({scope for status in statuses for scope in status.get("missing_required_scopes", [])})
    missing_recommended = sorted({scope for status in statuses for scope in status.get("missing_recommended_scopes", [])})
    ready_count = sum(1 for status in statuses if status.get("ready"))
    status = "ready" if surfaces and ready_count == len(surfaces) else "needs_setup" if surfaces else "not_configured"
    if surfaces and not portal_id and all(surface.get("requires_oauth") is False for surface in surfaces):
        status = "ready"
    return {
        "label": label,
        "status": status,
        "ready": status == "ready",
        "ready_count": ready_count,
        "total": len(surfaces),
        "surface_ids": surface_ids,
        "missing_required_scopes": missing_required,
        "missing_recommended_scopes": missing_recommended,
        "last_sync_at": last_sync_at,
    }


def hubspot_setup_status_report(portal_id: str = "") -> dict[str, Any]:
    connections = list_hubspot_portal_connections(limit=100)
    token_status = token_storage_status()
    selected_connection = next((connection for connection in connections if str(connection.get("portal_id") or "") == str(portal_id or "")), None) if portal_id else connections[0] if connections else None
    selected_portal_id = str(portal_id or (selected_connection.get("portal_id") if selected_connection else ""))
    surfaces = [
        {
            **surface,
            **hubspot_surface_readiness(surface, connections, token_status),
            "mapping": list(surface.get("mapping", ())),
            "status_label": HUBSPOT_SURFACE_STATUS_LABELS.get(str(surface.get("status") or ""), str(surface.get("status") or "Unknown")),
        }
        for surface in HUBSPOT_INTEGRATION_SURFACES
    ]
    surfaces_by_id = {str(surface.get("id") or ""): surface for surface in surfaces}
    analysis_filters = {"portal_id": selected_portal_id} if selected_portal_id else {}
    tenant_filters = {"tenant_id": selected_portal_id} if selected_portal_id else {}
    latest_analysis = list_hubspot_email_analyses(limit=1, filters=analysis_filters)
    latest_outcome = list_hubspot_outcome_events(limit=1, filters=tenant_filters)
    latest_review_state = list_hubspot_review_states(limit=1)
    last_sync_at = latest_hubspot_timestamp(selected_connection or {}, latest_analysis, latest_outcome, latest_review_state)
    groups = [
        hubspot_setup_group("Campaign sync", ["campaign_create_update", "campaign_picker", "campaign_asset_association", "live_campaign_review", "stats_sync", "bulk_asset_import"], surfaces_by_id, selected_portal_id, last_sync_at),
        hubspot_setup_group("Workflow actions", ["workflow_action", "analyze_and_sync", "asset_copy_workflow_action", "campaign_workflow_action", "marketing_email_pre_publish_guardrail"], surfaces_by_id, selected_portal_id, last_sync_at),
        hubspot_setup_group("Webhook re-scoring", ["webhook_sync", "webhook_management"], surfaces_by_id, selected_portal_id, last_sync_at),
        hubspot_setup_group("Approval workflow", ["approval_workflow_sync", "review_task_creation", "review_route_owner_mapping", "approval_chain_templates"], surfaces_by_id, selected_portal_id, last_sync_at),
        hubspot_setup_group("Reporting writeback", ["crm_property_writeback", "crm_property_provisioning", "analysis_custom_object", "analysis_schema_provisioning", "timeline_events", "lists_segments", "lists_segments_search"], surfaces_by_id, selected_portal_id, last_sync_at),
        hubspot_setup_group("Staffing workflow fit", ["staffing_workflow_templates", "hubspot_setup_wizard", "salesforce_outcome_mapping"], surfaces_by_id, selected_portal_id, last_sync_at),
    ]
    attention: list[dict[str, Any]] = []
    if not selected_connection:
        attention.append({"severity": "high", "area": "Connection", "message": "No connected HubSpot portal was found for this settings view."})
    elif selected_connection.get("status") == "disconnected":
        attention.append({"severity": "high", "area": "Connection", "message": "The selected HubSpot portal is disconnected. Reinstall or reconnect TextTraits."})
    elif not selected_connection.get("tokens_available"):
        attention.append({"severity": "high", "area": "OAuth tokens", "message": "The selected portal has no stored OAuth tokens, so live HubSpot writeback and sync actions cannot run."})
    if not token_status.get("ready"):
        attention.append({"severity": "high", "area": "Token storage", "message": "Encrypted token storage is not ready. Configure TEXTTRAITS_STORE_OAUTH_TOKENS and TEXTTRAITS_TOKEN_ENCRYPTION_KEY."})
    for group in groups:
        if group["status"] != "ready":
            missing = ", ".join(group["missing_required_scopes"][:6])
            message = f"{group['label']} needs setup."
            if missing:
                message += f" Missing scopes: {missing}."
            attention.append({"severity": "medium", "area": group["label"], "message": message, "missing_required_scopes": group["missing_required_scopes"]})
    dashboard = hubspot_email_dashboard(limit=200)
    return {
        "portal_id": selected_portal_id,
        "connection": selected_connection,
        "connections_count": len(connections),
        "granted_scopes": selected_connection.get("scopes", []) if selected_connection else [],
        "token_storage": token_status,
        "groups": groups,
        "enabled_surfaces": surfaces,
        "last_sync_at": last_sync_at,
        "admin_attention": attention[:20],
        "dashboard_summary": {
            "total_analyses": dashboard.get("total_analyses", 0),
            "gate_counts": dashboard.get("gate_counts", {}),
            "outcome_counts": dashboard.get("outcome_counts", {}),
        },
        "latest": {
            "analysis": latest_analysis[0] if latest_analysis else None,
            "outcome": latest_outcome[0] if latest_outcome else None,
            "review_state": latest_review_state[0] if latest_review_state else None,
        },
    }


def safe_csv_cell(value: Any) -> str:
    if isinstance(value, (dict, list)):
        clean = json.dumps(value, separators=(",", ":"), sort_keys=True)
    else:
        clean = str(value or "")
    clean = clean.replace("\r", " ").replace("\n", " ").strip()
    if clean.startswith(("=", "+", "-", "@")):
        return "'" + clean
    return clean


def hubspot_analysis_context_value(row: dict[str, Any], key: str, fallback: str = "") -> str:
    context = row.get("context") if isinstance(row.get("context"), dict) else {}
    delivery = context.get("delivery_context") if isinstance(context.get("delivery_context"), dict) else {}
    value = context.get(key) or delivery.get(key) or row.get(key) or fallback
    return str(value or "")[:300]


def hubspot_analysis_policy_version(row: dict[str, Any]) -> str:
    policy = row.get("policy") if isinstance(row.get("policy"), dict) else {}
    return first_text_value(policy.get("version"), row.get("policy_version"), max_length=120)


def hubspot_analysis_top_blocker(row: dict[str, Any]) -> str:
    findings = row.get("findings") if isinstance(row.get("findings"), list) else []
    if not findings:
        return ""
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    finding = sorted(findings, key=lambda item: severity_rank.get(str(item.get("severity") or ""), 9))[0]
    return first_text_value(finding.get("title"), finding.get("next_step"), finding.get("id"), max_length=500)


def hubspot_enriched_analysis_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    review_states = {state.get("request_id"): state for state in list_hubspot_review_states(limit=1000)}
    enriched: list[dict[str, Any]] = []
    for row in rows:
        state = review_states.get(row.get("request_id")) or {}
        enriched.append(
            {
                **row,
                "policy_version": hubspot_analysis_policy_version(row),
                "reviewer": state.get("assigned_to") or state.get("updated_by") or "",
                "decision": row.get("gate") or "",
                "timestamp": row.get("created_at") or "",
                "blocker": hubspot_analysis_top_blocker(row),
                "review_status": state.get("status") or "",
                "final_resolution": state.get("notes") or state.get("status") or "",
                "review_updated_at": state.get("updated_at") or "",
                "review_resolved_at": state.get("resolved_at") or "",
                "audience_type": hubspot_analysis_context_value(row, "audience_type"),
                "region": hubspot_analysis_context_value(row, "region"),
                "business_unit": hubspot_analysis_context_value(row, "business_unit"),
                "job_id": hubspot_analysis_context_value(row, "job_id"),
                "job_family": hubspot_analysis_context_value(row, "job_family"),
                "skill_family": hubspot_analysis_context_value(row, "skill_family"),
                "recruiter": hubspot_analysis_context_value(row, "recruiter"),
                "recruiter_id": hubspot_analysis_context_value(row, "recruiter_id"),
                "client_account": hubspot_analysis_context_value(row, "client_account"),
                "client_account_id": hubspot_analysis_context_value(row, "client_account_id"),
                "candidate_status": hubspot_analysis_context_value(row, "candidate_status"),
                "ats_system": hubspot_analysis_context_value(row, "ats_system"),
                "job_board": hubspot_analysis_context_value(row, "job_board"),
                "salesforce_campaign_id": hubspot_analysis_context_value(row, "salesforce_campaign_id"),
                "salesforce_opportunity_id": hubspot_analysis_context_value(row, "salesforce_opportunity_id"),
            }
        )
    return enriched


HUBSPOT_ANALYSIS_EXPORT_COLUMNS = (
    "created_at",
    "request_id",
    "workspace_id",
    "tenant_id",
    "source_system",
    "workflow",
    "analysis_mode",
    "campaign_id",
    "journey_id",
    "template_id",
    "contact_id",
    "company_id",
    "deal_id",
    "owner_id",
    "portal_id",
    "object_type",
    "object_id",
    "locale",
    "content_hash",
    "score",
    "gate",
    "route",
    "send_ready",
    "word_count",
    "average_model_confidence",
    "score_source",
    "policy_version",
    "reviewer",
    "decision",
    "timestamp",
    "blocker",
    "review_status",
    "final_resolution",
    "review_updated_at",
    "review_resolved_at",
    "audience_type",
    "region",
    "business_unit",
    "job_id",
    "job_family",
    "skill_family",
    "recruiter",
    "recruiter_id",
    "client_account",
    "client_account_id",
    "candidate_status",
    "ats_system",
    "job_board",
    "salesforce_campaign_id",
    "salesforce_opportunity_id",
)


@app.post("/v1/integrations/hubspot/review-action")
@rate_limited(120)
def hubspot_review_action():
    payload = request.get_json(silent=True) or {}
    if len(json.dumps(payload, default=str).encode("utf-8")) > MAX_EVENT_BYTES:
        return jsonify({"error": f"Review action payloads must stay under {MAX_EVENT_BYTES} bytes."}), 413
    try:
        event = save_hubspot_review_event(
            str(payload.get("request_id") or payload.get("texttraits_request_id") or ""),
            str(payload.get("action") or ""),
            payload.get("payload") if isinstance(payload.get("payload"), dict) else {},
            actor_id=str(payload.get("actor_id") or payload.get("user_id") or ""),
            status=str(payload.get("status") or "recorded"),
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    analysis = get_hubspot_email_analysis(event["request_id"]) or {}
    sync = {"status": "local_only", "actions": [], "skipped": [{"action": "hubspot_review_sync", "reason": "No TextTraits analysis was found for that request_id."}], "errors": []}
    if analysis and hubspot_payload_flag(payload, "sync_hubspot", bool(hubspot_portal_from_payload(payload) or analysis.get("portal_id"))):
        sync = hubspot_sync_review_action_to_portal(payload, event, analysis)
    log_event(current_user_id(), "hubspot_review_action", {"request_id": event["request_id"], "action": event["action"], "sync_status": sync.get("status")})
    return jsonify({"ok": True, "event": event, "sync": sync})


@app.post("/v1/integrations/hubspot/outcomes")
@rate_limited(120)
def hubspot_outcomes_ingest():
    payload = request.get_json(silent=True) or {}
    if len(json.dumps(payload, default=str).encode("utf-8")) > HUBSPOT_MAX_INGRESS_BYTES:
        return jsonify({"error": f"HubSpot outcome payloads must stay under {HUBSPOT_MAX_INGRESS_BYTES} bytes."}), 413
    raw_events = payload.get("events") if isinstance(payload.get("events"), list) else [payload]
    saved = []
    errors: list[str] = []
    for raw_event in raw_events[:HUBSPOT_MAX_OUTCOME_EVENTS]:
        if not isinstance(raw_event, dict):
            continue
        record = {
            "request_id": raw_event.get("request_id") or raw_event.get("texttraits_request_id") or payload.get("request_id"),
            "content_hash": raw_event.get("content_hash") or raw_event.get("texttraits_content_hash") or payload.get("content_hash"),
            "workspace_id": raw_event.get("workspace_id") or payload.get("workspace_id"),
            "tenant_id": raw_event.get("tenant_id") or payload.get("tenant_id"),
            "source_system": raw_event.get("source_system") or payload.get("source_system") or "hubspot",
            "event_type": raw_event.get("event_type") or raw_event.get("type"),
            "event_id": raw_event.get("event_id") or raw_event.get("id"),
            "payload": raw_event.get("payload") if isinstance(raw_event.get("payload"), dict) else raw_event,
            "occurred_at": raw_event.get("occurred_at") or raw_event.get("timestamp") or payload.get("occurred_at"),
        }
        try:
            saved.append(save_hubspot_outcome_event(record))
        except ValueError as error:
            errors.append(str(error))
    if not saved:
        return jsonify({"error": "No valid outcome events were supplied.", "errors": errors[:5]}), 400
    return jsonify({"ok": True, "events": saved, "errors": errors[:5], "dropped_events": max(0, len(raw_events) - HUBSPOT_MAX_OUTCOME_EVENTS)})


@app.post("/v1/integrations/hubspot/salesforce/outcomes/import")
@rate_limited(60)
def hubspot_salesforce_outcomes_import():
    payload = request.get_json(silent=True) or {}
    if len(json.dumps(payload, default=str).encode("utf-8")) > HUBSPOT_MAX_INGRESS_BYTES:
        return jsonify({"error": f"Salesforce outcome import payloads must stay under {HUBSPOT_MAX_INGRESS_BYTES} bytes."}), 413
    raw_events = payload.get("events") if isinstance(payload.get("events"), list) else payload.get("rows") if isinstance(payload.get("rows"), list) else [payload]
    saved = []
    errors: list[str] = []
    workspace_id = first_text_value(payload.get("workspace_id"), payload.get("workspaceId"), "hubspot_salesforce_import", max_length=160)
    tenant_id = first_text_value(payload.get("tenant_id"), payload.get("tenantId"), payload.get("portal_id"), payload.get("portalId"), max_length=160)
    for index, raw_event in enumerate(raw_events[:HUBSPOT_MAX_OUTCOME_EVENTS]):
        if not isinstance(raw_event, dict):
            continue
        request_id = first_text_value(raw_event.get("request_id"), raw_event.get("texttraits_request_id"), payload.get("request_id"), max_length=160)
        campaign_id = first_text_value(raw_event.get("campaign_id"), raw_event.get("hubspot_campaign_id"), raw_event.get("salesforce_campaign_id"), payload.get("campaign_id"), max_length=160)
        opportunity_id = first_text_value(raw_event.get("salesforce_opportunity_id"), raw_event.get("opportunity_id"), max_length=160)
        lead_id = first_text_value(raw_event.get("salesforce_lead_id"), raw_event.get("lead_id"), max_length=160)
        contact_id = first_text_value(raw_event.get("salesforce_contact_id"), raw_event.get("contact_id"), max_length=160)
        event_type = first_text_value(raw_event.get("event_type"), raw_event.get("type"), raw_event.get("stage"), "salesforce_outcome", max_length=80)
        content_hash = first_text_value(raw_event.get("content_hash"), raw_event.get("texttraits_content_hash"), payload.get("content_hash"), max_length=128)
        if not request_id and not content_hash:
            content_hash = hubspot_content_hash(
                f"salesforce:{campaign_id}:{opportunity_id}:{lead_id}:{contact_id}:{event_type}:{raw_event.get('occurred_at') or raw_event.get('timestamp') or index}",
                workspace_id,
            )
        mapped_payload = {
            "source": "salesforce_mapping",
            "campaign_id": campaign_id,
            "salesforce_campaign_id": first_text_value(raw_event.get("salesforce_campaign_id"), campaign_id, max_length=160),
            "salesforce_opportunity_id": opportunity_id,
            "salesforce_lead_id": lead_id,
            "salesforce_contact_id": contact_id,
            "audience_type": first_text_value(raw_event.get("audience_type"), raw_event.get("audienceType"), max_length=80),
            "region": first_text_value(raw_event.get("region"), max_length=120),
            "business_unit": first_text_value(raw_event.get("business_unit"), raw_event.get("businessUnit"), max_length=160),
            "skill_family": first_text_value(raw_event.get("skill_family"), raw_event.get("skillFamily"), max_length=160),
            "job_family": first_text_value(raw_event.get("job_family"), raw_event.get("jobFamily"), max_length=160),
            "raw": scrub_payload(raw_event),
        }
        try:
            saved.append(
                save_hubspot_outcome_event(
                    {
                        "request_id": request_id,
                        "content_hash": content_hash,
                        "workspace_id": workspace_id,
                        "tenant_id": tenant_id,
                        "source_system": "salesforce",
                        "event_type": event_type,
                        "event_id": first_text_value(raw_event.get("event_id"), raw_event.get("id"), opportunity_id, lead_id, contact_id, f"salesforce:{index}", max_length=160),
                        "payload": mapped_payload,
                        "occurred_at": raw_event.get("occurred_at") or raw_event.get("timestamp") or utc_now(),
                    }
                )
            )
        except ValueError as error:
            errors.append(str(error))
    if not saved:
        return jsonify({"error": "No valid Salesforce outcome rows were supplied.", "errors": errors[:5]}), 400
    return jsonify({"ok": True, "events": saved, "errors": errors[:5], "dropped_events": max(0, len(raw_events) - HUBSPOT_MAX_OUTCOME_EVENTS)})


@app.get("/api/enterprise/hubspot/analyses")
@rate_limited(60)
def api_enterprise_hubspot_analyses():
    user_id, error = require_enterprise_admin()
    if error:
        return error
    limit = clamp_int(request.args.get("limit"), 1, 1000, 100)
    analyses = list_hubspot_email_analyses(limit=limit, filters=hubspot_analysis_filters_from_request())
    log_event(user_id, "hubspot_analyses_viewed", {"count": len(analyses)})
    return jsonify(
        {
            "analyses": analyses,
            "review_events": list_hubspot_review_events(limit=100),
            "review_states": list_hubspot_review_states(limit=100),
        }
    )


@app.get("/api/enterprise/hubspot/findings")
@rate_limited(60)
def api_enterprise_hubspot_findings():
    user_id, error = require_enterprise_admin()
    if error:
        return error
    filters = {key: request.args.get(key, "").strip() for key in ("request_id", "finding_id", "severity", "owner_queue", "blocker_level") if request.args.get(key, "").strip()}
    findings = list_hubspot_normalized_findings(limit=clamp_int(request.args.get("limit"), 1, 1000, 100), filters=filters)
    log_event(user_id, "hubspot_findings_viewed", {"count": len(findings)})
    return jsonify({"findings": findings})


@app.get("/api/enterprise/hubspot/checks")
@rate_limited(60)
def api_enterprise_hubspot_checks():
    user_id, error = require_enterprise_admin()
    if error:
        return error
    filters = {key: request.args.get(key, "").strip() for key in ("request_id", "check_id", "status") if request.args.get(key, "").strip()}
    checks = list_hubspot_normalized_checks(limit=clamp_int(request.args.get("limit"), 1, 1000, 100), filters=filters)
    log_event(user_id, "hubspot_checks_viewed", {"count": len(checks)})
    return jsonify({"checks": checks})


@app.get("/api/enterprise/hubspot/review-states")
@rate_limited(60)
def api_enterprise_hubspot_review_states():
    user_id, error = require_enterprise_admin()
    if error:
        return error
    filters = {key: request.args.get(key, "").strip() for key in ("request_id", "status", "owner_queue", "assigned_to") if request.args.get(key, "").strip()}
    states = list_hubspot_review_states(limit=clamp_int(request.args.get("limit"), 1, 1000, 100), filters=filters)
    log_event(user_id, "hubspot_review_states_viewed", {"count": len(states)})
    return jsonify({"review_states": states})


@app.get("/api/enterprise/hubspot/outcomes")
@rate_limited(60)
def api_enterprise_hubspot_outcomes():
    user_id, error = require_enterprise_admin()
    if error:
        return error
    events = list_hubspot_outcome_events(limit=clamp_int(request.args.get("limit"), 1, 1000, 100), filters=hubspot_outcome_filters_from_request())
    log_event(user_id, "hubspot_outcomes_viewed", {"count": len(events)})
    return jsonify({"events": events})


@app.get("/api/enterprise/hubspot/dashboard")
@rate_limited(60)
def api_enterprise_hubspot_dashboard():
    user_id, error = require_enterprise_admin()
    if error:
        return error
    limit = clamp_int(request.args.get("limit"), 1, 1000, 500)
    dashboard = hubspot_email_dashboard(limit=limit)
    log_event(user_id, "hubspot_dashboard_viewed", {"total": dashboard["total_analyses"]})
    return jsonify({"dashboard": dashboard})


@app.get("/api/enterprise/hubspot/staffing-workflow-templates")
@rate_limited(60)
def api_enterprise_hubspot_staffing_workflow_templates():
    user_id, error = require_enterprise_admin()
    if error:
        return error
    log_event(user_id, "hubspot_staffing_workflow_templates_viewed", {"count": len(HUBSPOT_STAFFING_WORKFLOW_TEMPLATES)})
    return jsonify(
        {
            "templates": [dict(template) for template in HUBSPOT_STAFFING_WORKFLOW_TEMPLATES],
            "object_specialization": HUBSPOT_STAFFING_OBJECT_SPECIALIZATION,
            "asset_copy_support": HUBSPOT_ASSET_COPY_SUPPORT,
        }
    )


@app.get("/api/enterprise/hubspot/approval-chain-templates")
@rate_limited(60)
def api_enterprise_hubspot_approval_chain_templates():
    user_id, error = require_enterprise_admin()
    if error:
        return error
    log_event(user_id, "hubspot_approval_chain_templates_viewed", {"count": len(HUBSPOT_APPROVAL_CHAIN_TEMPLATES)})
    return jsonify({"approval_chains": [dict(template) for template in HUBSPOT_APPROVAL_CHAIN_TEMPLATES]})


@app.get("/api/enterprise/hubspot/setup-wizard")
@rate_limited(60)
def api_enterprise_hubspot_setup_wizard():
    user_id, error = require_enterprise_admin()
    if error:
        return error
    portal_id = first_text_value(request.args.get("portal_id"), request.args.get("portalId"), max_length=160)
    setup_status = hubspot_setup_status_report(portal_id)
    log_event(user_id, "hubspot_setup_wizard_viewed", {"portal_id": portal_id})
    return jsonify({"steps": [dict(step) for step in HUBSPOT_SETUP_WIZARD_STEPS], "setup_status": setup_status})


def hubspot_randstad_readiness_report() -> dict[str, Any]:
    dashboard = hubspot_email_dashboard(limit=500)
    surface_ids = {surface["id"] for surface in HUBSPOT_INTEGRATION_SURFACES}
    categories = [
        {
            "category": "Campaigns and multi-asset review",
            "score": 8.4,
            "usefulness": "High",
            "hubspot_areas": ("Campaigns", "Marketing email", "Forms", "Landing pages", "Blog posts", "Social", "SMS", "Ads", "CTAs"),
            "implemented": "Campaign create/list/update, asset association, live campaign review, coverage scoring, and mapped-copy fallback.",
            "gap": "Ads, SMS, social, CTA, and workflow-step copy still need mapped payloads unless HubSpot exposes reviewable copy in the campaign asset response.",
        },
        {
            "category": "Marketing email pre-publish governance",
            "score": 8.8,
            "usefulness": "High",
            "hubspot_areas": ("Marketing Emails", "Workflows", "Campaigns"),
            "implemented": "Direct draft fetch/update, analyze-and-sync, pre-publish guardrail, workflow actions, review tasks, and writeback.",
            "gap": "Not embedded inside HubSpot's native email editor toolbar; it runs from app home/card/workflow/API surfaces.",
        },
        {
            "category": "Staffing/recruiting workflow fit",
            "score": 8.1,
            "usefulness": "High",
            "hubspot_areas": ("Contacts", "Companies", "Deals", "Tickets", "Lists", "Owners", "Workflows"),
            "implemented": "Candidate/client/job-order object specialization, workflow templates, ATS/job-board context, regional policy packs, and approval chains.",
            "gap": "Customer-specific property names and ATS mappings still need setup with each enterprise.",
        },
        {
            "category": "Governance dashboards and auditability",
            "score": 8.6,
            "usefulness": "High",
            "hubspot_areas": ("Reports", "Custom objects", "CRM properties", "Exports"),
            "implemented": "Normalized checks/findings, review states, outcome events, blocked-by-region, risky claim type, review SLA, send-ready by business unit, and enriched audit exports.",
            "gap": "Native HubSpot report templates still need to be configured in the customer's portal after field provisioning.",
        },
        {
            "category": "Outcome analytics and revenue/placement attribution",
            "score": 7.4,
            "usefulness": "Medium-high",
            "hubspot_areas": ("Marketing email stats", "Campaigns", "Salesforce mapping", "Outcome events"),
            "implemented": "HubSpot stats sync, outcome ingestion, Salesforce outcome mapping, and segment rollups by audience, region, skill family, and job family.",
            "gap": "A live Salesforce connector and customer placement/outcome schema require credentials and field mapping.",
        },
        {
            "category": "Setup/admin readiness",
            "score": 8.0,
            "usefulness": "High",
            "hubspot_areas": ("Connected apps", "OAuth scopes", "Webhooks", "Owners", "Lists", "Custom objects"),
            "implemented": "Setup status, setup wizard data, owner routing, field/schema/segment/webhook provisioning, token storage checks, and surfaces registry.",
            "gap": "Marketplace review, verified domain, and customer-specific scope approval are external steps.",
        },
    ]
    return {
        "generated_at": analyzedTimeForServer(),
        "overall_usefulness_score": 8.3,
        "overall_connection_score": 7.9,
        "dashboard_snapshot": {
            "total_analyses": dashboard.get("total_analyses", 0),
            "gate_counts": dashboard.get("gate_counts", {}),
            "blocked_by_region": dashboard.get("blocked_by_region", [])[:5],
            "send_ready_by_business_unit": dashboard.get("send_ready_by_business_unit", [])[:5],
        },
        "implemented_surface_count": len(surface_ids),
        "categories": categories,
        "remaining_non_fake_work": [
            "Configure customer-specific HubSpot field mappings and ATS property names.",
            "Add native HubSpot report/dashboard templates inside each customer portal after install.",
            "Complete marketplace listing, verified domain, and external security/legal artifacts.",
            "Connect real Salesforce OAuth and customer outcome schemas when credentials are available.",
            "Install in a real staffing customer sandbox and capture validation data from live workflows.",
        ],
    }


@app.get("/api/enterprise/hubspot/randstad-readiness")
@rate_limited(30)
def api_enterprise_hubspot_randstad_readiness():
    user_id, error = require_enterprise_admin()
    if error:
        return error
    report = hubspot_randstad_readiness_report()
    log_event(user_id, "hubspot_randstad_readiness_viewed", {"overall": report["overall_usefulness_score"]})
    return jsonify({"readiness": report})


@app.get("/api/enterprise/hubspot/surfaces")
@rate_limited(60)
def api_enterprise_hubspot_surfaces():
    user_id, error = require_enterprise_admin()
    if error:
        return error
    connections = list_hubspot_portal_connections(limit=100)
    token_status = token_storage_status()
    surfaces = [
        {
            **surface,
            **hubspot_surface_readiness(surface, connections, token_status),
            "mapping": list(surface.get("mapping", ())),
            "auth": "HubSpot ingress signature or shared API key for server-to-server use.",
            "status_label": HUBSPOT_SURFACE_STATUS_LABELS.get(str(surface.get("status") or ""), str(surface.get("status") or "Unknown")),
        }
        for surface in HUBSPOT_INTEGRATION_SURFACES
    ]
    log_event(user_id, "hubspot_surfaces_viewed", {"count": len(surfaces)})
    return jsonify(
        {
            "surfaces": surfaces,
            "connections": connections,
            "token_storage": token_status,
            "max_batch_emails": max(1, min(HUBSPOT_MAX_BATCH_EMAILS, 100)),
            "note": "Backend surfaces are ready to receive mapped HubSpot payloads. Live in-HubSpot placement still depends on the installed app configuration and granted scopes.",
        }
    )


@app.get("/api/enterprise/hubspot/marketplace-readiness")
@rate_limited(30)
def api_enterprise_hubspot_marketplace_readiness():
    user_id, error = require_enterprise_admin()
    if error:
        return error
    report = hubspot_marketplace_readiness_report()
    log_event(user_id, "hubspot_marketplace_readiness_viewed", {"checks": len(report.get("checks", []))})
    return jsonify({"marketplace_readiness": report})


@app.get("/api/enterprise/hubspot/connections")
@rate_limited(60)
def api_enterprise_hubspot_connections():
    user_id, error = require_enterprise_admin()
    if error:
        return error
    connections = list_hubspot_portal_connections(limit=clamp_int(request.args.get("limit"), 1, 500, 100))
    log_event(user_id, "hubspot_connections_viewed", {"count": len(connections)})
    return jsonify({"connections": connections, "token_storage": token_storage_status()})


@app.get("/api/enterprise/hubspot/setup-status")
@rate_limited(60)
def api_enterprise_hubspot_setup_status():
    user_id, error = require_enterprise_admin()
    if error:
        return error
    portal_id = first_text_value(request.args.get("portal_id"), request.args.get("portalId"), max_length=160)
    report = hubspot_setup_status_report(portal_id)
    log_event(user_id, "hubspot_setup_status_viewed", {"portal_id": report.get("portal_id"), "attention": len(report.get("admin_attention", []))})
    return jsonify({"setup_status": report})


@app.post("/api/enterprise/hubspot/connections/<portal_id>/disconnect")
@rate_limited(30)
def api_enterprise_hubspot_disconnect(portal_id: str):
    user_id, error = require_enterprise_admin()
    if error:
        return error
    actor = str((get_user_by_id(user_id) or {}).get("email") or user_id or "")[:160]
    connection = disconnect_hubspot_portal(portal_id, actor=actor)
    if not connection:
        return jsonify({"error": "No HubSpot portal connection was found for that portal_id."}), 404
    log_event(user_id, "hubspot_connection_disconnected", {"portal_id": portal_id})
    return jsonify({"ok": True, "connection": connection})


@app.get("/api/enterprise/readiness")
@rate_limited(30)
def api_enterprise_readiness():
    user_id, error = require_enterprise_admin()
    if error:
        return error
    report = enterprise_readiness_report()
    log_event(user_id, "enterprise_readiness_viewed", {"production_ready": report["production_ready"], "counts": report["counts"]})
    return jsonify({"readiness": report})


@app.get("/api/enterprise/hubspot/score-validation")
@rate_limited(30)
def api_enterprise_hubspot_score_validation():
    user_id, error = require_enterprise_admin()
    if error:
        return error
    workspace_id = safe_hubspot_identifier(request.args.get("workspace_id", "default"), "default")
    environment = safe_hubspot_identifier(request.args.get("environment", "production"), "production", limit=80).lower()
    saved = get_hubspot_policy_config(workspace_id, environment)
    if saved is None and workspace_id != "default":
        saved = get_hubspot_policy_config("default", environment)
    policy = normalized_hubspot_email_policy(saved["policy"] if saved else {})
    context = {
        "workspace_id": workspace_id,
        "environment": environment,
        "source_system": "hubspot",
        "analysis_mode": "score_validation",
    }
    report = hubspot_score_validation_report(policy, context)
    log_event(user_id, "hubspot_score_validation_viewed", {"passed": report["passed"], "cases_passed": report["cases_passed"]})
    return jsonify({"validation": report})


@app.get("/api/enterprise/hubspot/retention")
@rate_limited(30)
def api_enterprise_hubspot_retention_get():
    user_id, error = require_enterprise_admin()
    if error:
        return error
    days = clamp_int(request.args.get("days"), 1, 3650, int(os.getenv("TEXTTRAITS_HUBSPOT_RETENTION_DAYS", "90")))
    summary = hubspot_retention_summary(days=days, dry_run=True)
    log_event(user_id, "hubspot_retention_previewed", {"days": days, "total_records": summary["total_records"]})
    return jsonify({"retention": summary})


@app.post("/api/enterprise/hubspot/retention")
@rate_limited(10)
def api_enterprise_hubspot_retention_post():
    user_id, error = require_enterprise_admin()
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    days = clamp_int(payload.get("days"), 1, 3650, int(os.getenv("TEXTTRAITS_HUBSPOT_RETENTION_DAYS", "90")))
    dry_run = payload.get("dry_run", True) is not False
    if not dry_run and str(payload.get("confirm") or "") != "purge_hubspot_records":
        return jsonify({"error": "Set confirm to purge_hubspot_records to run a non-dry-run retention purge."}), 400
    summary = hubspot_retention_summary(days=days, dry_run=dry_run)
    log_event(user_id, "hubspot_retention_run", {"days": days, "dry_run": dry_run, "total_records": summary["total_records"]})
    return jsonify({"retention": summary})


@app.get("/api/enterprise/hubspot/exports/analyses.json")
@rate_limited(30)
def api_enterprise_hubspot_export_json():
    user_id, error = require_enterprise_admin()
    if error:
        return error
    analyses = hubspot_enriched_analysis_rows(list_hubspot_email_analyses(limit=clamp_int(request.args.get("limit"), 1, 1000, 1000), filters=hubspot_analysis_filters_from_request()))
    log_event(user_id, "hubspot_analyses_exported", {"format": "json", "count": len(analyses)})
    return jsonify({"analyses": analyses, "exported_at": analyzedTimeForServer()})


@app.get("/api/enterprise/hubspot/exports/analyses.csv")
@rate_limited(30)
def api_enterprise_hubspot_export_csv():
    user_id, error = require_enterprise_admin()
    if error:
        return error
    analyses = hubspot_enriched_analysis_rows(list_hubspot_email_analyses(limit=clamp_int(request.args.get("limit"), 1, 1000, 1000), filters=hubspot_analysis_filters_from_request()))
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=HUBSPOT_ANALYSIS_EXPORT_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in analyses:
        writer.writerow({key: safe_csv_cell(row.get(key)) for key in HUBSPOT_ANALYSIS_EXPORT_COLUMNS})
    log_event(user_id, "hubspot_analyses_exported", {"format": "csv", "count": len(analyses)})
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=texttraits-hubspot-analyses.csv"},
    )


def analyzedTimeForServer() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@app.get("/api/enterprise/hubspot/policy")
@rate_limited(60)
def api_enterprise_hubspot_policy_get():
    user_id, error = require_enterprise_admin()
    if error:
        return error
    workspace_id = request.args.get("workspace_id", "default").strip() or "default"
    environment = request.args.get("environment", "production").strip() or "production"
    saved = get_hubspot_policy_config(workspace_id, environment)
    policy = normalized_hubspot_email_policy(saved["policy"] if saved else {})
    history = list_hubspot_policy_versions(workspace_id=workspace_id, environment=environment, limit=25)
    rule_packs = [
        {
            "id": key,
            "label": value["label"],
            "risk_phrase_count": len(value.get("risk_phrases", ())),
            "vague_phrase_count": len(value.get("vague_phrases", ())),
            "required_template_tokens": list(value.get("required_template_tokens", ())),
            "required_headers": list(value.get("required_headers", ())),
        }
        for key, value in HUBSPOT_EMAIL_RULE_PACKS.items()
    ]
    return jsonify({"workspace_id": workspace_id, "environment": environment, "policy": policy, "rule_packs": rule_packs, "source": "saved" if saved else "default", "updated_at": saved["updated_at"] if saved else "", "history": history})


@app.get("/api/enterprise/hubspot/policy/history")
@rate_limited(60)
def api_enterprise_hubspot_policy_history():
    user_id, error = require_enterprise_admin()
    if error:
        return error
    history = list_hubspot_policy_versions(
        workspace_id=request.args.get("workspace_id", "").strip(),
        environment=request.args.get("environment", "").strip(),
        limit=clamp_int(request.args.get("limit"), 1, 1000, 100),
    )
    log_event(user_id, "hubspot_policy_history_viewed", {"count": len(history)})
    return jsonify({"history": history})


@app.put("/api/enterprise/hubspot/policy")
@rate_limited(30)
def api_enterprise_hubspot_policy_put():
    user_id, error = require_enterprise_admin()
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    workspace_id = str(payload.get("workspace_id") or "default").strip() or "default"
    environment = str(payload.get("environment") or "production").strip() or "production"
    raw_policy = payload.get("policy")
    if not isinstance(raw_policy, dict):
        return jsonify({"error": "Policy must be an object."}), 400
    allowed_keys = {"version", "rule_pack", *HUBSPOT_POLICY_BOOLEAN_KEYS, *HUBSPOT_POLICY_INTEGER_BOUNDS.keys(), *HUBSPOT_POLICY_LIST_KEYS}
    unsupported = sorted(set(raw_policy.keys()) - allowed_keys)
    if unsupported:
        return jsonify({"error": "Policy contains unsupported fields.", "fields": unsupported[:10]}), 400
    user = get_user_by_id(user_id)
    saved = save_hubspot_policy_config(
        workspace_id,
        environment,
        normalized_hubspot_email_policy(raw_policy),
        updated_by=(user or {}).get("email", ""),
    )
    log_event(user_id, "hubspot_policy_updated", {"workspace_id": workspace_id, "environment": environment})
    return jsonify(saved)


@app.get("/api/session")
def api_session():
    user_id = current_user_id()
    user = get_user_by_id(user_id) if user_id else None
    if user and not user.get("email_verified"):
        csrf = csrf_token()
        session.clear()
        session["csrf_token"] = csrf
        user = None
    return jsonify(
        {
            "authenticated": bool(user),
            "user": user,
            "app": public_app_info(),
            "csrf_token": csrf_token(),
        }
    )


@app.post("/api/signup")
@rate_limited(12)
def api_signup():
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))
    name = str(payload.get("name", "")).strip()
    if "@" not in email or "." not in email:
        return jsonify({"error": "Enter a valid email address."}), 400
    password_error = password_policy_error(password, email)
    if password_error:
        return jsonify({"error": password_error}), 400
    try:
        pending = create_pending_signup(email, password, name)
    except Exception:
        return jsonify(
            {
                "authenticated": False,
                "pending_verification": True,
                "message": "If this email can be used, check it for a 6-digit verification code.",
            }
        )
    verification_token = pending.get("token")
    email_result = send_verification_email(pending, verification_token)
    message = "Check your email for a 6-digit verification code before signing in."
    if pending.get("already_sent"):
        message = "We already emailed a 6-digit code. Use that code to create your account."
    elif not verification_token:
        message = "If this email can be used, check it for a 6-digit verification code."
    elif not email_result.get("sent"):
        if PRODUCTION:
            message = "We could not send a verification code right now. Try again in a moment."
        elif email_status()["configured"]:
            message = "A code was created, but the email provider rejected this recipient. With Resend testing, use the email address on your Resend account or verify a sending domain."
        else:
            message = "A code was created, but email delivery is not configured for this environment."
    response = {
        "authenticated": False,
        "pending_verification": True,
        "email": email,
        "message": message,
        "email_delivery": {"sent": bool(email_result.get("sent")), "provider": email_result.get("provider")},
    }
    if ALLOW_DEV_ACCOUNT_LINKS and not email_result.get("sent") and verification_token:
        response["dev_verify_code"] = verification_token
    return jsonify(response)


@app.post("/api/login")
@rate_limited(20)
def api_login():
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))
    user = authenticate_user(email, password)
    if not user:
        if needs_email_verification(email, password):
            return jsonify({"error": "Verify your email with the 6-digit code before signing in."}), 403
        return jsonify({"error": "Email or password did not match."}), 401
    start_user_session(user)
    log_event(user["id"], "login", {})
    return jsonify({"authenticated": True, "user": user, "workspace": get_workspace(user["id"])})


@app.post("/api/auth/google")
@rate_limited(20)
def api_google_auth():
    payload = request.get_json(silent=True) or {}
    credential = str(payload.get("credential", "")).strip()
    try:
        profile = verify_google_identity_token(credential)
    except ValueError as error:
        status = 409 if not GOOGLE_AUTH_CLIENT_ID else 400
        return jsonify({"error": str(error), "configured": bool(GOOGLE_AUTH_CLIENT_ID)}), status
    except Exception:
        logging.exception("google_auth_failed")
        return jsonify({"error": "Google sign-in could not be verified. Try email sign-in instead."}), 502
    user = upsert_oauth_user(profile["email"], profile.get("name", ""), provider="Google")
    start_user_session(user)
    log_event(user["id"], "login_google", {})
    return jsonify({"authenticated": True, "user": user, "workspace": get_workspace(user["id"])})


@app.post("/api/logout")
def api_logout():
    user_id = current_user_id()
    if user_id:
        log_event(user_id, "logout", {})
    session.clear()
    return jsonify({"authenticated": False})


@app.post("/api/request-password-reset")
@rate_limited(8)
def api_request_password_reset():
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email", "")).strip().lower()
    reset = create_password_reset(email)
    response = {"ok": True, "message": "If an account exists, reset instructions are ready."}
    if reset:
        delivery = send_password_reset_email(email, reset["token"])
        if not PRODUCTION:
            response["email_delivery"] = {"sent": bool(delivery.get("sent")), "provider": delivery.get("provider")}
    if ALLOW_DEV_ACCOUNT_LINKS and reset and not email_status()["configured"]:
        response["dev_reset_url"] = public_url(f"/api/reset-password/{reset['token']}")
        response["expires_at"] = reset["expires_at"]
    return jsonify(response)


@app.post("/api/reset-password")
@rate_limited(8)
def api_reset_password():
    payload = request.get_json(silent=True) or {}
    token = str(payload.get("token", ""))
    password = str(payload.get("password", ""))
    password_error = password_policy_error(password)
    if password_error:
        return jsonify({"error": password_error}), 400
    user = reset_password(token, password)
    if not user:
        return jsonify({"error": "Reset link is invalid or expired."}), 400
    start_user_session(user)
    return jsonify({"authenticated": True, "user": user, "workspace": get_workspace(user["id"])})


@app.get("/api/reset-password")
@app.get("/api/reset-password/<token>")
def api_reset_password_link(token: str | None = None):
    if not ALLOW_DEV_ACCOUNT_LINKS:
        return redirect("/")
    clean = token or request.args.get("token", "")
    return redirect("/#" + urlencode({"reset_token": clean}))


@app.post("/api/verify-email")
@rate_limited(20)
def api_verify_email():
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email", "")).strip().lower()
    token = str(payload.get("token", ""))
    if not email or not token:
        return jsonify({"error": "Enter the email address and 6-digit verification code."}), 400
    user = verify_email_token(token, email)
    if not user:
        return jsonify({"error": "Verification code is invalid or expired."}), 400
    start_user_session(user)
    return jsonify({"authenticated": True, "user": user, "workspace": get_workspace(user["id"])})


@app.get("/api/verify-email")
@app.get("/api/verify-email/<token>")
def api_verify_email_link(token: str | None = None):
    if not ALLOW_DEV_ACCOUNT_LINKS:
        return redirect("/")
    clean = token or request.args.get("token", "")
    return redirect("/#" + urlencode({"verify_token": clean}))


@app.post("/api/account/export")
@rate_limited(12)
def api_account_export():
    user_id, error = require_user()
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    if not confirmed_password(user_id, str(payload.get("password", ""))):
        return jsonify({"error": "Confirm your password to export account data."}), 403
    data = export_user_data(user_id)
    log_event(user_id, "account_exported", {})
    return jsonify(data)


@app.delete("/api/account")
@rate_limited(6)
def api_account_delete():
    user_id, error = require_user()
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    if not confirmed_password(user_id, str(payload.get("password", ""))):
        return jsonify({"error": "Confirm your password to delete this account."}), 403
    delete_user(user_id)
    session.clear()
    return jsonify({"deleted": True})


@app.get("/api/workspace")
def api_workspace_get():
    user_id, error = require_user()
    if error:
        return error
    return jsonify({"workspace": get_workspace(user_id), "events": recent_events(user_id)})


@app.put("/api/workspace")
@rate_limited(60)
def api_workspace_put():
    user_id, error = require_user()
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    data = payload.get("data")
    if not isinstance(data, dict):
        return jsonify({"error": "Workspace data must be an object."}), 400
    if len(str(payload).encode("utf-8")) > MAX_WORKSPACE_BYTES:
        return jsonify({"error": f"Workspace data is too large. Keep sync payloads under {MAX_WORKSPACE_BYTES} bytes."}), 413
    unknown_keys = sorted(set(data.keys()) - ALLOWED_WORKSPACE_KEYS)
    if unknown_keys:
        return jsonify({"error": "Workspace data contains unsupported fields.", "fields": unknown_keys[:10]}), 400
    clean_data = sanitize_workspace_data(data)
    try:
        workspace = save_workspace(user_id, clean_data, payload.get("name"))
    except ValueError as error:
        return jsonify({"error": str(error)}), 413
    log_event(user_id, "workspace_saved", {"keys": sorted(clean_data.keys())[:20]})
    return jsonify({"workspace": workspace})


@app.post("/api/events")
@rate_limited(120)
def api_events():
    payload = request.get_json(silent=True) or {}
    event_payload = payload.get("payload") or {}
    if len(str(event_payload).encode("utf-8")) > MAX_EVENT_BYTES:
        return jsonify({"error": "Event payload is too large."}), 413
    log_event(current_user_id(), str(payload.get("event_type", "client_event"))[:80], event_payload)
    return jsonify({"ok": True})


@app.post("/api/client-errors")
@rate_limited(60)
def api_client_errors():
    payload = request.get_json(silent=True) or {}
    safe_payload = scrub_payload({key: str(value)[:500] for key, value in payload.items() if key in {"message", "source", "line", "column"}})
    logging.error("client_error %s", safe_payload)
    log_event(current_user_id(), "client_error", safe_payload)
    return jsonify({"ok": True})


@app.get("/api/integrations")
def api_integrations_get():
    user_id, error = require_user()
    if error:
        return error
    return jsonify({"integrations": integrations(user_id)})


@app.get("/api/integration-providers")
def api_integration_providers():
    return jsonify({"providers": public_providers()})


@app.post("/api/integrations")
@rate_limited(30)
def api_integrations_post():
    user_id, error = require_user()
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    provider = str(payload.get("provider", "")).strip()
    status = str(payload.get("status", "needs credentials")).strip()
    if provider not in provider_names():
        return jsonify({"error": "Unsupported integration provider."}), 400
    config = payload.get("config") or {}
    if len(str(config).encode("utf-8")) > MAX_EVENT_BYTES:
        return jsonify({"error": "Integration config is too large."}), 413
    if contains_sensitive_key(config):
        return jsonify({"error": "Do not store raw credentials in integration config."}), 400
    return jsonify({"integration": upsert_integration(user_id, provider, status, config)})


@app.post("/api/integrations/<provider>/oauth/start")
@rate_limited(20)
def api_integration_oauth_start(provider: str):
    user_id, error = require_user()
    if error:
        return error
    entry = get_provider(provider)
    if not entry:
        return jsonify({"error": "Unsupported integration provider."}), 404
    if not entry.configured() or not entry.auth_url:
        return (
            jsonify(
                {
                    "error": "Provider credentials are not configured for this deployment.",
                    "provider": entry.public_dict(),
                }
            ),
            409,
        )
    nonce = secrets.token_urlsafe(16)
    state = encoded_state(user_id, entry.name, nonce)
    session[f"oauth_nonce_{provider_slug(entry.name)}"] = nonce
    redirect_uri = public_url(f"/api/integrations/{provider_slug(entry.name)}/oauth/callback")
    authorize_url = build_authorization_url(entry, redirect_uri, state)
    return jsonify({"authorize_url": authorize_url, "provider": entry.public_dict()})


@app.get("/api/integrations/<provider>/oauth/callback")
@rate_limited(20)
def api_integration_oauth_callback(provider: str):
    entry = get_provider(provider)
    if not entry:
        return jsonify({"error": "Unsupported integration provider."}), 404
    code = request.args.get("code", "")
    state = request.args.get("state", "")
    if not code:
        return jsonify({"error": "OAuth callback is missing code."}), 400
    try:
        decoded = decoded_state(state) if state else None
    except Exception:
        decoded = None

    if decoded is None and provider_slug(entry.name) == "hubspot":
        redirect_uri = public_url(f"/api/integrations/{provider_slug(entry.name)}/oauth/callback")
        try:
            token_payload = exchange_oauth_code(entry, redirect_uri, code)
            marketplace_install_user(entry, token_payload, state)
        except Exception:
            logging.exception("hubspot_marketplace_oauth_exchange_failed")
            return oauth_completion_page(
                "HubSpot install reached TextTraits",
                "TextTraits received the HubSpot install callback, but the token exchange failed. Check the deployed HubSpot client ID, client secret, and redirect URL before trying again.",
                502,
            )
        return oauth_completion_page(
            "HubSpot app installed",
            "The HubSpot account was connected to TextTraits. Return to HubSpot and add the TextTraits email fit card from record customization.",
        )

    if decoded is None:
        return jsonify({"error": "OAuth state is invalid."}), 400

    user_id, error = require_user()
    if error:
        return error
    expected_nonce = session.get(f"oauth_nonce_{provider_slug(entry.name)}")
    if decoded.get("user_id") != user_id or decoded.get("provider") != entry.name or decoded.get("nonce") != expected_nonce:
        return jsonify({"error": "OAuth state did not match this session."}), 400

    redirect_uri = public_url(f"/api/integrations/{provider_slug(entry.name)}/oauth/callback")
    try:
        token_payload = exchange_oauth_code(entry, redirect_uri, code)
    except Exception as oauth_error:
        logging.exception("oauth_exchange_failed")
        return jsonify({"error": "OAuth exchange failed. Check provider credentials and redirect URL."}), 502

    config = {
        "connected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "token_type": token_payload.get("token_type"),
        "expires_in": token_payload.get("expires_in"),
        "scope": token_payload.get("scope"),
        "tokens_stored": False,
    }
    if provider_slug(entry.name) == "hubspot":
        try:
            portal_connection = save_hubspot_portal_tokens(token_payload, installed_by=(get_user_by_id(user_id) or {}).get("email", ""))
            config["hubspot_portal_id"] = portal_connection.get("portal_id")
            config["hubspot_domain"] = portal_connection.get("hub_domain")
            config["portal_connection_status"] = portal_connection.get("status")
            config["tokens_available"] = portal_connection.get("tokens_available")
            config["tokens_stored"] = bool(portal_connection.get("tokens_available"))
        except Exception:
            logging.exception("hubspot_portal_token_store_failed")
            if os.getenv("TEXTTRAITS_STORE_OAUTH_TOKENS", "").strip().lower() in {"1", "true", "yes", "on"}:
                return jsonify({"error": "HubSpot connected, but encrypted token storage failed. Check TEXTTRAITS_TOKEN_ENCRYPTION_KEY."}), 503
    integration = upsert_integration(user_id, entry.name, "connected", config)
    session.pop(f"oauth_nonce_{provider_slug(entry.name)}", None)
    return jsonify({"integration": integration})


@app.get("/privacy")
def privacy():
    return render_template_string(
        """
        <!doctype html>
        <html lang="en">
          <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>TextTraits Privacy</title>
            <link rel="stylesheet" href="/static/styles.css">
            <script
              src="https://js.sentry-cdn.com/e02e26721e10ee55975fc73c5b7dfd57.min.js"
              crossorigin="anonymous"
            ></script>
          </head>
          <body>
        <main class="legal-page">
          <h1>Privacy</h1>
          <p>TextTraits stores account and workspace data for signed-in users, including saved writing history, campaigns, drafts, outcomes, settings, and integration connection status.</p>
          <p>Text submitted for analysis is processed by the TextTraits application. Raw pasted text is not included in normal workspace sync unless a user saves a reading, draft, or campaign that contains it.</p>
          <p>Signed-in users can export their account data and delete their account from the account menu. Deletion removes the synced workspace and integration connection records for that account.</p>
          <p>Enterprise integrations require administrator setup before any CRM or email data is exchanged. Preview integrations do not connect to third-party systems.</p>
          <p>Operational logs and error reports are used to keep the service reliable and should avoid storing passwords, reset codes, API keys, and OAuth credentials.</p>
          <p><a href="/">Back to TextTraits</a></p>
        </main>
          </body>
        </html>
        """
    )


@app.get("/terms")
def terms():
    return render_template_string(
        """
        <!doctype html>
        <html lang="en">
          <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>TextTraits Terms</title>
            <link rel="stylesheet" href="/static/styles.css">
            <script
              src="https://js.sentry-cdn.com/e02e26721e10ee55975fc73c5b7dfd57.min.js"
              crossorigin="anonymous"
            ></script>
          </head>
          <body>
        <main class="legal-page">
          <h1>Terms</h1>
          <p>TextTraits is a writing coach and outreach workflow tool. Users are responsible for reviewing generated drafts before using them.</p>
          <p>Team administrators are responsible for approved claims, compliance requirements, permissions, retention settings, external integration credentials, and user access.</p>
          <p>Preview integrations are disabled until real credentials, provider approvals, and field mappings are configured by the workspace owner.</p>
          <p>Users must not upload content they do not have the right to process, and must review outreach copy for accuracy, consent, opt-out handling, and applicable laws before sending.</p>
          <p><a href="/">Back to TextTraits</a></p>
        </main>
          </body>
        </html>
        """
    )


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=port, debug=ENABLE_DEV_TOOLS)
