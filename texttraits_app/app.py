from __future__ import annotations

import hashlib
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
from html import escape as html_escape
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
    get_user_by_id,
    get_workspace,
    get_hubspot_policy_config,
    hubspot_email_dashboard,
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
    upsert_integration,
    upsert_oauth_user,
    user_session_version,
    verify_email_token,
)

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
    "/v1/integrations/hubspot/crm-card/analyze-email",
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
DEFAULT_HUBSPOT_EMAIL_POLICY = {
    "version": "2026-06-01.default",
    "ready_score_threshold": 78,
    "review_score_threshold": 70,
    "block_score_threshold": 50,
    "block_if_no_cta": True,
    "block_high_severity_findings": True,
    "compliance_review_on_risk_terms": True,
    "require_personalization": False,
    "min_body_words": 25,
    "max_body_words": 220,
}
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
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
configure_logging(ARTIFACT_DIR / "app.log")


def validate_runtime_config() -> None:
    failures: list[str] = []
    if APP_SECRET.startswith(("dev-", "replace-")):
        message = "TEXTTRAITS_SECRET_KEY must be a real high-entropy secret."
        if PRODUCTION:
            failures.append(message)
        else:
            logging.warning(message)
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
        "description": "Cloud model placeholder",
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
    if PRODUCTION and not ENTERPRISE_ADMIN_EMAILS:
        return None, (jsonify({"error": "Configure TEXTTRAITS_ENTERPRISE_ADMIN_EMAILS before enabling enterprise admin endpoints in production."}), 503)
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
        "tokens_stored": bool(os.getenv("TEXTTRAITS_STORE_OAUTH_TOKENS", "").strip().lower() in {"1", "true", "yes", "on"}),
    }
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


def hubspot_ingress_auth_error() -> tuple | None:
    secret = hubspot_ingress_secret()
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
    body = request.get_data(cache=True) or b""
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    candidates = {expected, f"sha256={expected}"}
    if supplied_signature and any(hmac.compare_digest(supplied_signature, candidate) for candidate in candidates):
        g.hubspot_ingress_auth = {"mode": "hmac_sha256"}
        return None
    return jsonify({"error": "HubSpot ingress signature was missing or invalid."}), 401


@app.before_request
def protect_unsafe_requests():
    g.csp_nonce = secrets.token_urlsafe(16)
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    if hubspot_public_ingress_path():
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
    for key in HUBSPOT_POLICY_BOOLEAN_KEYS:
        clean[key] = bool(policy.get(key, DEFAULT_HUBSPOT_EMAIL_POLICY[key]))
    for key, (low, high) in HUBSPOT_POLICY_INTEGER_BOUNDS.items():
        clean[key] = clamp_int(policy.get(key), low, high, DEFAULT_HUBSPOT_EMAIL_POLICY[key])
    if clean["max_body_words"] <= clean["min_body_words"]:
        clean["max_body_words"] = min(1200, clean["min_body_words"] + 1)
    if clean["ready_score_threshold"] < clean["review_score_threshold"]:
        clean["ready_score_threshold"] = clean["review_score_threshold"]
    if clean["review_score_threshold"] < clean["block_score_threshold"]:
        clean["review_score_threshold"] = clean["block_score_threshold"]
    return clean


def hubspot_policy_for_request(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    workspace_id = str(payload.get("workspace_id") or context.get("workspace_id") or "default")[:160]
    environment = str(payload.get("environment") or payload.get("analysis_environment") or "production")[:80]
    saved = get_hubspot_policy_config(workspace_id, environment)
    if saved is None and workspace_id != "default":
        saved = get_hubspot_policy_config("default", environment)
    raw_policy = saved["policy"] if saved else {}
    policy = normalized_hubspot_email_policy(raw_policy)
    policy["workspace_id"] = workspace_id
    policy["environment"] = environment
    policy["source"] = "saved" if saved else "default"
    return policy


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


def email_specificity_check(text: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    anchors = email_specific_anchors(text)
    vague_hits = email_phrase_hits(text, EMAIL_VAGUE_PHRASES)
    if len(anchors) >= 2 and not vague_hits:
        return email_check("specificity", "Specificity", 20, 20, [f"Concrete anchors: {', '.join(anchors[:5])}."]), None
    if len(anchors) >= 1 and len(vague_hits) <= 1:
        return email_check("specificity", "Specificity", 20, 16, [f"Concrete anchors: {', '.join(anchors[:5])}."]), None
    finding = email_finding(
        "specificity_low",
        "medium",
        "Draft needs more concrete detail",
        "The message has too few concrete anchors or too many vague phrases.",
        [
            f"{len(anchors)} concrete anchor{'s' if len(anchors) != 1 else ''} detected.",
            f"Vague phrases: {', '.join(vague_hits[:5]) if vague_hits else 'none detected'}.",
        ],
        "Add a concrete date, topic, deliverable, person, or decision.",
        "Marketing review",
        "Medium",
        "Name the specific thing this email is about before routing.",
    )
    score = 7 if len(vague_hits) >= 2 else 10
    return email_check("specificity", "Specificity", 20, score, [f"{len(anchors)} concrete anchors.", f"{len(vague_hits)} vague phrases."], finding), finding


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


def email_risk_check(text: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    risk_hits = email_phrase_hits(text, EMAIL_RISK_PHRASES)
    if not risk_hits:
        return email_check("risk_terms", "Risk terms", 10, 10, ["No configured risk phrases detected."]), None
    severity = "high" if any(item in {"guaranteed", "guarantee", "100%"} for item in risk_hits) or len(risk_hits) >= 2 else "medium"
    risk_penalty = 45 if severity == "high" else 25
    finding = email_finding(
        "risk_terms_detected",
        severity,
        "Risky claim or pressure phrase detected",
        "The draft contains wording that may need legal, compliance, or brand review.",
        [
            f"Detected phrase{'s' if len(risk_hits) != 1 else ''}: {', '.join(risk_hits[:5])}.",
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
        [f"Risk phrases: {', '.join(risk_hits[:5])}.", f"Risk penalty: {risk_penalty} points."],
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
        lambda: email_specificity_check(text),
        lambda: email_personalization_check(subject, body, context),
        lambda: email_readability_check(body),
        lambda: email_risk_check(text),
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


def hubspot_workspace_for_portal(portal_id: str) -> str:
    clean = "".join(ch for ch in str(portal_id or "") if ch.isalnum() or ch in {"-", "_"})[:120]
    return f"hubspot_{clean}" if clean else ""


def validate_hubspot_context(context: dict[str, Any]) -> str | None:
    portal_id = str(context.get("portal_id") or "").strip()
    workspace_id = str(context.get("workspace_id") or "").strip()
    tenant_id = str(context.get("tenant_id") or "").strip()
    expected_workspace = hubspot_workspace_for_portal(portal_id)
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
        "headers": optional_context_object(payload.get("headers"), input_fields.get("headers")),
        "consent_context": optional_context_object(payload.get("consent_context"), input_fields.get("consent_context")),
        "delivery_context": optional_context_object(payload.get("delivery_context"), input_fields.get("delivery_context")),
        "ingress_auth": getattr(g, "hubspot_ingress_auth", {"mode": "unknown"}),
    }
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


def hubspot_template_test_result(subject: str, body: str, sample_context: dict[str, Any], headers: dict[str, Any] | None = None) -> dict[str, Any]:
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
    for required in ("from", "reply_to"):
        if required not in {str(key).lower() for key in clean_headers.keys()}:
            header_warnings.append(f"Missing {required.replace('_', '-')} header.")
    checks = [
        {"id": "tokens_resolved", "label": "Merge tokens resolved", "ok": not unresolved, "detail": "All supplied tokens rendered." if not unresolved else f"Unresolved tokens: {', '.join(unresolved[:8])}."},
        {"id": "unsubscribe_present", "label": "Unsubscribe state", "ok": unsubscribe_present, "detail": "Unsubscribe wording or token is present." if unsubscribe_present else "Add an unsubscribe token or link before automated routing."},
        {"id": "links_detected", "label": "Link inventory", "ok": True, "detail": f"{len(links)} link{'s' if len(links) != 1 else ''} detected."},
        {"id": "headers_present", "label": "Header context", "ok": not header_warnings, "detail": "Required sender headers supplied." if not header_warnings else " ".join(header_warnings)},
    ]
    return {
        "rendered_subject": rendered_subject,
        "rendered_body": rendered_body,
        "unresolved_tokens": unresolved,
        "links": links[:25],
        "headers": clean_headers,
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


def hubspot_analysis_response(payload: dict, workflow: str):
    input_fields = payload.get("inputFields") if isinstance(payload.get("inputFields"), dict) else payload
    subject = str(input_fields.get("subject") or input_fields.get("email_subject") or input_fields.get("hs_email_subject") or "").strip()
    body = str(input_fields.get("body") or input_fields.get("email_body") or input_fields.get("hs_email_body") or input_fields.get("text") or "").strip()
    text = f"{subject}\n\n{body}".strip()
    context = hubspot_context_from_payload(payload, input_fields)
    context["workflow"] = workflow
    if context.get("_validation_error"):
        return jsonify({"error": context["_validation_error"]}), 403
    policy = hubspot_policy_for_request(payload, context)
    if not text:
        return jsonify({"error": "Enter an email subject or body to analyze."}), 400
    if len(text.split()) > MAX_TEXT_WORDS:
        return jsonify({"error": f"Please keep samples under {MAX_TEXT_WORDS} words for this workspace."}), 413
    try:
        predictions = predictor.predict(text)
    except RuntimeError as error:
        return jsonify({"error": str(error)}), 503

    confidences = prediction_confidences(predictions)
    average_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    email_quality = build_hubspot_email_quality(subject, body, text, policy, context)
    decision = email_quality["decision"]
    score = email_quality["score"]
    gate = decision["gate"]
    route = decision["route"]
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    idempotency_key = first_text_value(
        payload.get("idempotency_key"),
        input_fields.get("idempotency_key"),
        request.headers.get("X-Idempotency-Key"),
        max_length=160,
    )
    if idempotency_key:
        digest = hashlib.sha256(f"{context.get('workspace_id')}:{workflow}:{idempotency_key}:{content_hash}".encode("utf-8")).hexdigest()[:28]
        request_id = f"{workflow}-{digest}"
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
    return jsonify(
        {
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
                "texttraits_policy_version": policy.get("version"),
            },
            "analysis": {
                "request_id": request_id,
                "content_hash": content_hash,
                "idempotency_key": idempotency_key,
                "score": score,
                "gate": gate,
                "route": route,
                "word_count": len(text.split()),
                "average_model_confidence": round(average_confidence, 4),
                "decision": decision,
                "email_quality": email_quality,
                "policy": policy,
                "context": context,
                "demo": bool(getattr(predictor, "is_demo", False)),
                "predictions": predictions if ENABLE_DEV_TOOLS else public_prediction_payload(predictions),
            },
        }
    )


@app.post("/v1/integrations/hubspot/crm-card/analyze-email")
@rate_limited(60)
def hubspot_crm_card_analyze_email():
    return hubspot_analysis_response(request.get_json(silent=True) or {}, "hubspot_crm_card")


@app.post("/v1/integrations/hubspot/workflow-actions/analyze-email")
@rate_limited(60)
def hubspot_workflow_action_analyze_email():
    return hubspot_analysis_response(request.get_json(silent=True) or {}, "hubspot_workflow_action")


@app.post("/v1/integrations/hubspot/template-test")
@rate_limited(60)
def hubspot_template_test():
    payload = request.get_json(silent=True) or {}
    input_fields = payload.get("inputFields") if isinstance(payload.get("inputFields"), dict) else payload
    subject = str(input_fields.get("subject") or input_fields.get("email_subject") or "").strip()
    body = str(input_fields.get("body") or input_fields.get("email_body") or input_fields.get("text") or "").strip()
    sample_context = payload.get("sample_context") if isinstance(payload.get("sample_context"), dict) else input_fields.get("sample_context") if isinstance(input_fields.get("sample_context"), dict) else {}
    headers = payload.get("headers") if isinstance(payload.get("headers"), dict) else input_fields.get("headers") if isinstance(input_fields.get("headers"), dict) else {}
    if not subject and not body:
        return jsonify({"error": "Enter a template subject or body to test."}), 400
    result = hubspot_template_test_result(subject, body, scrub_payload(sample_context), scrub_payload(headers))
    return jsonify({"template_test": result})


def hubspot_analysis_filters_from_request() -> dict[str, str]:
    allowed = ("workspace_id", "tenant_id", "source_system", "gate", "route", "campaign_id", "template_id", "contact_id", "company_id", "deal_id")
    return {key: request.args.get(key, "").strip() for key in allowed if request.args.get(key, "").strip()}


def hubspot_outcome_filters_from_request() -> dict[str, str]:
    allowed = ("request_id", "content_hash", "workspace_id", "tenant_id", "source_system", "event_type")
    return {key: request.args.get(key, "").strip() for key in allowed if request.args.get(key, "").strip()}


def safe_csv_cell(value: Any) -> str:
    if isinstance(value, (dict, list)):
        clean = json.dumps(value, separators=(",", ":"), sort_keys=True)
    else:
        clean = str(value or "")
    clean = clean.replace("\r", " ").replace("\n", " ").strip()
    if clean.startswith(("=", "+", "-", "@")):
        return "'" + clean
    return clean


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
)


@app.post("/v1/integrations/hubspot/review-action")
@rate_limited(120)
def hubspot_review_action():
    payload = request.get_json(silent=True) or {}
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
    log_event(current_user_id(), "hubspot_review_action", {"request_id": event["request_id"], "action": event["action"]})
    return jsonify({"ok": True, "event": event})


@app.post("/v1/integrations/hubspot/outcomes")
@rate_limited(120)
def hubspot_outcomes_ingest():
    payload = request.get_json(silent=True) or {}
    raw_events = payload.get("events") if isinstance(payload.get("events"), list) else [payload]
    saved = []
    for raw_event in raw_events[:100]:
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
        saved.append(save_hubspot_outcome_event(record))
    if not saved:
        return jsonify({"error": "No valid outcome events were supplied."}), 400
    return jsonify({"ok": True, "events": saved})


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


@app.get("/api/enterprise/hubspot/exports/analyses.json")
@rate_limited(30)
def api_enterprise_hubspot_export_json():
    user_id, error = require_enterprise_admin()
    if error:
        return error
    analyses = list_hubspot_email_analyses(limit=clamp_int(request.args.get("limit"), 1, 1000, 1000), filters=hubspot_analysis_filters_from_request())
    log_event(user_id, "hubspot_analyses_exported", {"format": "json", "count": len(analyses)})
    return jsonify({"analyses": analyses, "exported_at": analyzedTimeForServer()})


@app.get("/api/enterprise/hubspot/exports/analyses.csv")
@rate_limited(30)
def api_enterprise_hubspot_export_csv():
    user_id, error = require_enterprise_admin()
    if error:
        return error
    analyses = list_hubspot_email_analyses(limit=clamp_int(request.args.get("limit"), 1, 1000, 1000), filters=hubspot_analysis_filters_from_request())
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
    return jsonify({"workspace_id": workspace_id, "environment": environment, "policy": policy, "source": "saved" if saved else "default", "updated_at": saved["updated_at"] if saved else "", "history": history})


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
    allowed_keys = {"version", *HUBSPOT_POLICY_BOOLEAN_KEYS, *HUBSPOT_POLICY_INTEGER_BOUNDS.keys()}
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
        "tokens_stored": bool(os.getenv("TEXTTRAITS_STORE_OAUTH_TOKENS", "").strip().lower() in {"1", "true", "yes", "on"}),
    }
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
