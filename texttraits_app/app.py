from __future__ import annotations

import json
import logging
import os
import secrets
import hashlib
import hmac
import csv
import io
import re
import time
import urllib.request
from html import escape as html_escape
from collections import defaultdict, deque
from functools import wraps
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode, urlparse

from flask import Flask, g, jsonify, make_response, redirect, render_template, render_template_string, request, session
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from demo_predictor import DemoPredictor
from email_delivery import send_account_email, status as email_status
from email_analysis import (
    build_email_analysis,
    compact_analysis,
    integration_flow_catalog,
    rendered_template_harness,
    safe_template_summary,
    utc_now,
)
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
from integration_contracts import (
    CONTRACT_VERSION as INTEGRATION_CONTRACT_VERSION,
    all_manifests,
    mapping_template,
    normalize_provider,
    provider_manifest,
    validate_field_mapping,
)
from openapi_contract import build_install_kit, build_openapi_spec
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
    enterprise_governance_snapshot,
    export_user_data,
    get_governance_policy,
    get_user_by_id,
    get_workspace,
    init_db,
    integrations,
    log_event,
    needs_email_verification,
    recent_events,
    recent_integration_field_mappings,
    governance_export_rows,
    save_email_analysis,
    save_email_outcome,
    save_integration_field_mapping,
    save_sample_import,
    reset_password,
    save_governance_policy,
    save_workspace,
    contains_sensitive_key,
    scrub_payload,
    upsert_webhook_event,
    get_integration_field_mapping,
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
WEBHOOK_SIGNATURE_TOLERANCE_SECONDS = int(os.getenv("TEXTTRAITS_WEBHOOK_SIGNATURE_TOLERANCE_SECONDS", "300"))
GOOGLE_AUTH_CLIENT_ID = (os.getenv("TEXTTRAITS_GOOGLE_AUTH_CLIENT_ID") or os.getenv("GOOGLE_CLIENT_ID") or "").strip()
TRUSTED_PUBLIC_HOSTS = {
    host.strip().lower()
    for host in os.getenv("TEXTTRAITS_ALLOWED_PUBLIC_HOSTS", "").split(",")
    if host.strip()
}
UNSPECIFIED_IPV4 = ".".join(("0", "0", "0", "0"))
LOCAL_PUBLIC_HOSTS = {"localhost", "127.0.0.1", "::1", UNSPECIFIED_IPV4}
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
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
DATA_DIR = Path(__file__).resolve().parent / "data"
ENTERPRISE_PLAN_PATH = DATA_DIR / "enterprise_integration_plan.json"
ENTERPRISE_DATA_GET_PREFIXES = (
    "/v1/governance",
    "/v1/integrations/manifests",
    "/v1/integrations/field-mappings",
)
ENTERPRISE_DATA_GET_SUFFIXES = (
    "/manifest",
)
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
        if not env_flag("TEXTTRAITS_REQUIRE_ENTERPRISE_BROWSER_AUTH", True):
            failures.append("TEXTTRAITS_REQUIRE_ENTERPRISE_BROWSER_AUTH=true is required in production.")
        if os.getenv("TEXTTRAITS_API_KEY", "").strip() and not (
            os.getenv("TEXTTRAITS_API_KEY_SHA256", "").strip() or os.getenv("TEXTTRAITS_API_KEY_HASHES", "").strip()
        ):
            failures.append("Use TEXTTRAITS_API_KEY_SHA256 or TEXTTRAITS_API_KEY_HASHES instead of plaintext TEXTTRAITS_API_KEY in production.")
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
        "id": "external_connector",
        "name": "External model connector",
        "available": False,
        "description": "Not configured in this local build",
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
    window_seconds = 60

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            identity = f"user:{current_user_id()}" if current_user_id() else f"ip:{request.remote_addr or 'local'}"
            key = f"{identity}:{request.endpoint or fn.__name__}"
            now = time.time()
            bucket = rate_buckets[key]
            while bucket and now - bucket[0] > window_seconds:
                bucket.popleft()
            if len(bucket) >= max_calls:
                retry_after = max(1, int(window_seconds - (now - bucket[0])) + 1)
                response = jsonify(
                    {
                        "error": "Too many requests. Please wait a moment and try again.",
                        "rate_limit": {
                            "limit": max_calls,
                            "remaining": 0,
                            "window_seconds": window_seconds,
                            "retry_after_seconds": retry_after,
                        },
                    }
                )
                response.status_code = 429
                response.headers["Retry-After"] = str(retry_after)
                response.headers["X-RateLimit-Limit"] = str(max_calls)
                response.headers["X-RateLimit-Remaining"] = "0"
                response.headers["X-RateLimit-Reset"] = str(int(now + retry_after))
                return response
            bucket.append(now)
            response = make_response(fn(*args, **kwargs))
            response.headers["X-RateLimit-Limit"] = str(max_calls)
            response.headers["X-RateLimit-Remaining"] = str(max(max_calls - len(bucket), 0))
            response.headers["X-RateLimit-Reset"] = str(int(bucket[0] + window_seconds))
            return response

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


def public_url(path: str) -> str:
    return f"{PUBLIC_BASE_URL.rstrip('/')}/{path.lstrip('/')}"


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
    if private_response_path():
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
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


def api_key_header_supplied() -> bool:
    return bool(request.headers.get("X-TextTraits-Api-Key", "").strip())


def normalized_sha256_digest(value: str) -> str:
    clean = value.strip().lower()
    if clean.startswith("sha256:"):
        clean = clean.split(":", 1)[1]
    return clean if re.fullmatch(r"[a-f0-9]{64}", clean) else ""


def configured_api_key_hashes() -> tuple[str, ...]:
    hashes: list[str] = []
    for env_name in ("TEXTTRAITS_API_KEY_HASHES", "TEXTTRAITS_API_KEY_SHA256"):
        for item in os.getenv(env_name, "").split(","):
            digest = normalized_sha256_digest(item)
            if digest:
                hashes.append(digest)
    legacy_key = os.getenv("TEXTTRAITS_API_KEY", "").strip()
    if legacy_key:
        hashes.append(hashlib.sha256(legacy_key.encode("utf-8")).hexdigest())
    return tuple(dict.fromkeys(hashes))


def api_key_request_allowed() -> bool:
    supplied = request.headers.get("X-TextTraits-Api-Key", "").strip()
    supplied_digest = hashlib.sha256(supplied.encode("utf-8")).hexdigest() if supplied else ""
    if not (supplied_digest and any(secrets.compare_digest(supplied_digest, expected) for expected in configured_api_key_hashes())):
        return False
    raw_scopes = os.getenv("TEXTTRAITS_API_KEY_SCOPES", "").strip()
    if not raw_scopes:
        g.api_key_scope = "unscoped"
        return True
    workspace_id = integration_workspace_id(request.get_json(silent=True) if request.is_json else None) if request.path.startswith("/v1/") else "default"
    method_path = f"{request.method}:{request.path}"
    for raw_scope in raw_scopes.split(","):
        scope = raw_scope.strip()
        if not scope or ":" not in scope:
            continue
        workspace_scope, path_scope = scope.split(":", 1)
        workspace_match = workspace_scope in {"*", workspace_id}
        endpoint_match = path_scope in {"*", request.path} or method_path.startswith(path_scope) or request.path.startswith(path_scope)
        if workspace_match and endpoint_match:
            g.api_key_scope = scope
            return True
    return False


def enterprise_data_read_path() -> bool:
    if request.method not in {"GET", "HEAD"}:
        return False
    if any(request.path.startswith(prefix) for prefix in ENTERPRISE_DATA_GET_PREFIXES):
        return True
    return request.path.startswith("/v1/integrations/") and request.path.endswith(ENTERPRISE_DATA_GET_SUFFIXES)


def private_response_path() -> bool:
    return request.path.startswith("/api/") or request.path.startswith("/v1/")


def browser_session_request_allowed() -> bool:
    if not (session.get("csrf_token") and request_origin_allowed()):
        return False
    if env_flag("TEXTTRAITS_REQUIRE_ENTERPRISE_BROWSER_AUTH", PRODUCTION) and not current_user_id():
        return False
    return True


@app.before_request
def protect_unsafe_requests():
    g.csp_nonce = secrets.token_urlsafe(16)
    if enterprise_data_read_path():
        if api_key_header_supplied():
            if api_key_request_allowed():
                return None
            return jsonify({"error": "API key is invalid or not scoped for this endpoint."}), 401
        if browser_session_request_allowed():
            return None
        return jsonify({"error": "Authentication required for enterprise governance and integration data."}), 401
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    if request.path.startswith("/v1/") and api_key_header_supplied():
        if api_key_request_allowed():
            return None
        return jsonify({"error": "API key is invalid or not scoped for this endpoint."}), 401
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


def load_enterprise_integration_plan() -> dict[str, Any]:
    with ENTERPRISE_PLAN_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@app.get("/api/enterprise/integration-plan")
def api_enterprise_integration_plan():
    try:
        return jsonify(load_enterprise_integration_plan())
    except Exception:
        logging.exception("enterprise_integration_plan_unavailable")
        return jsonify({"error": "Enterprise integration plan is unavailable."}), 503


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
        return jsonify({"error": "External model connectors are not configured in this local build."}), 503
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


def normalize_email_analysis_payload(payload: dict[str, Any]) -> dict[str, Any]:
    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    normalized = {**payload}
    normalized["subject"] = payload.get("subject") or message.get("subject") or ""
    normalized["body"] = payload.get("body") or payload.get("text") or message.get("content") or message.get("body") or message.get("text") or message.get("html") or ""
    normalized["headers"] = payload.get("headers") if isinstance(payload.get("headers"), dict) else message.get("headers") if isinstance(message.get("headers"), dict) else {}
    normalized["tenant_id"] = payload.get("tenant_id") or message.get("tenant_id") or ""
    normalized["source_system"] = payload.get("source_system") or message.get("source_system") or payload.get("source") or payload.get("channel") or ""
    normalized["analysis_mode"] = payload.get("analysis_mode") or message.get("analysis_mode") or payload.get("channel") or "direct_api"
    for key in ("campaign_id", "journey_id", "step_id", "template_id", "template_version", "locale"):
        normalized[key] = payload.get(key) or message.get(key) or ""
    if "links" not in normalized and message.get("links"):
        normalized["links"] = message.get("links")
    return normalized


def analyze_email_payload(payload: dict[str, Any], request_id: str | None = None) -> dict[str, Any]:
    payload = normalize_email_analysis_payload(payload)
    subject = str(payload.get("subject") or "").strip()
    body = str(payload.get("body") or payload.get("text") or "").strip()
    model_id = str(payload.get("model", "local")).strip() or "local"
    workspace_id = str(payload.get("workspace_id") or "default").strip()[:120] or "default"
    if not body:
        raise ValueError("Email body is required.")
    if len(f"{subject} {body}".split()) > MAX_TEXT_WORDS:
        raise ValueError(f"Please keep email samples under {MAX_TEXT_WORDS} words for this workspace.")
    if model_id != "local":
        raise RuntimeError("External model connectors are not configured in this local build.")
    governance_policy = get_governance_policy(workspace_id)
    predictions = predictor.predict(f"{subject}\n\n{body}".strip())
    public_predictions = predictions if ENABLE_DEV_TOOLS else public_prediction_payload(predictions)
    analysis = build_email_analysis(
        {**payload, "subject": subject, "body": body, "model": model_id, "workspace_id": workspace_id},
        public_predictions,
        model_metadata=getattr(predictor, "metadata", {}),
        demo=bool(getattr(predictor, "is_demo", False)),
        request_id=request_id,
        policy_controls=governance_policy,
    )
    save_email_analysis(analysis, source=str(payload.get("source") or payload.get("channel") or "direct_api"), workspace_id=workspace_id)
    log_event(
        current_user_id(),
        "v1_email_analyze",
        {
            "request_id": analysis["request_id"],
            "workspace_id": workspace_id,
            "score": analysis["scores"]["overall"],
            "gate": analysis["policy"]["gate"]["status"],
            "finding_count": len(analysis["findings"]),
        },
    )
    return analysis


def analysis_error_response(error: Exception):
    if isinstance(error, ValueError):
        return jsonify({"error": str(error)}), 400
    if isinstance(error, RuntimeError):
        return jsonify({"error": str(error)}), 503
    logging.exception("v1_email_analysis_failed")
    return jsonify({"error": "Email analysis failed. Retry in a moment."}), 500


@app.post("/v1/email/analyze")
@rate_limited()
def v1_email_analyze():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(analyze_email_payload(payload, request.headers.get("X-Request-ID")))
    except Exception as error:
        return analysis_error_response(error)


@app.get("/v1/openapi.json")
def v1_openapi_contract():
    return jsonify(build_openapi_spec(PUBLIC_BASE_URL))


@app.get("/v1/install-kit")
def v1_install_kit():
    return jsonify(build_install_kit(PUBLIC_BASE_URL))


@app.get("/v1/integrations/sandbox-flows")
def v1_sandbox_integration_flows():
    return jsonify({"api_version": "v1", "flows": integration_flow_catalog()})


@app.get("/v1/integrations/mock-flows")
def v1_mock_integration_flows():
    return v1_sandbox_integration_flows()


def integration_workspace_id(payload: dict[str, Any] | None = None) -> str:
    candidate = (
        request.headers.get("X-TextTraits-Workspace")
        or request.args.get("workspace_id")
        or (payload or {}).get("workspace_id")
        or "default"
    )
    return str(candidate).strip()[:120] or "default"


def nested_value(data: Any, path: str) -> Any:
    for candidate in str(path or "").split("|"):
        current = data
        for part in candidate.strip().split("."):
            if not part:
                continue
            if not isinstance(current, dict) or part not in current:
                current = None
                break
            current = current[part]
        if current not in (None, ""):
            return current
    return None


def mapped_input(data: dict[str, Any], mapping_record: dict[str, Any] | None, logical_key: str, fallback_paths: list[str]) -> Any:
    configured_path = (mapping_record or {}).get("mapping", {}).get("inputs", {}).get(logical_key)
    paths = [configured_path] if configured_path else []
    paths.extend(fallback_paths)
    for path in paths:
        value = nested_value(data, str(path))
        if value not in (None, ""):
            return value
    return ""


def analysis_output_values(analysis: dict[str, Any]) -> dict[str, Any]:
    gate = analysis.get("policy", {}).get("gate", {})
    return {
        "request_id": analysis.get("request_id"),
        "content_hash": analysis.get("content_hash"),
        "score": analysis.get("scores", {}).get("overall"),
        "gate_status": gate.get("status"),
        "send_ready": gate.get("send_ready"),
        "route": gate.get("route"),
        "highest_severity": gate.get("highest_severity"),
        "findings_count": len(analysis.get("findings") or []),
        "policy_bundle_version": analysis.get("policy", {}).get("bundle_version"),
    }


def mapped_outputs(analysis: dict[str, Any], mapping_record: dict[str, Any] | None, defaults: dict[str, Any]) -> dict[str, Any]:
    output_values = analysis_output_values(analysis)
    configured_outputs = (mapping_record or {}).get("mapping", {}).get("outputs", {})
    if not configured_outputs:
        return defaults
    fields = {}
    for provider_field, logical_key in configured_outputs.items():
        if logical_key in output_values:
            fields[provider_field] = output_values[logical_key]
    return fields or defaults


@app.get("/v1/integrations/manifests")
def v1_integration_manifests():
    workspace_id = integration_workspace_id()
    return jsonify(
        {
            "api_version": "v1",
            "contract_version": INTEGRATION_CONTRACT_VERSION,
            "manifests": all_manifests(),
            "field_mappings": recent_integration_field_mappings(workspace_id=workspace_id, limit=20),
            "workspace_id": workspace_id,
        }
    )


@app.get("/v1/integrations/<provider>/manifest")
def v1_integration_manifest(provider: str):
    manifest = provider_manifest(provider)
    if not manifest:
        return jsonify({"error": "Unsupported integration provider.", "provider": normalize_provider(provider)}), 404
    workspace_id = integration_workspace_id()
    return jsonify(
        {
            "api_version": "v1",
            "contract_version": INTEGRATION_CONTRACT_VERSION,
            "manifest": manifest,
            "mapping_template": mapping_template(provider),
            "saved_mapping": get_integration_field_mapping(workspace_id, normalize_provider(provider)),
            "workspace_id": workspace_id,
        }
    )


@app.get("/v1/integrations/field-mappings")
def v1_integration_field_mappings():
    workspace_id = integration_workspace_id()
    return jsonify(
        {
            "api_version": "v1",
            "contract_version": INTEGRATION_CONTRACT_VERSION,
            "workspace_id": workspace_id,
            "field_mappings": recent_integration_field_mappings(workspace_id=workspace_id, limit=50),
        }
    )


@app.post("/v1/integrations/<provider>/field-mapping/validate")
@rate_limited(60)
def v1_integration_field_mapping_validate(provider: str):
    payload = request.get_json(silent=True) or {}
    manifest = provider_manifest(provider)
    if not manifest:
        return jsonify({"error": "Unsupported integration provider.", "provider": normalize_provider(provider)}), 404
    mapping = payload.get("mapping") if isinstance(payload.get("mapping"), dict) else payload
    validation = validate_field_mapping(provider, mapping)
    return jsonify(
        {
            "api_version": "v1",
            "contract_version": INTEGRATION_CONTRACT_VERSION,
            "provider": manifest["provider"],
            "manifest": manifest,
            "validation": validation,
            "mapping_template": mapping_template(provider),
        }
    )


@app.post("/v1/integrations/<provider>/field-mapping")
@rate_limited(40)
def v1_integration_field_mapping_save(provider: str):
    payload = request.get_json(silent=True) or {}
    manifest = provider_manifest(provider)
    if not manifest:
        return jsonify({"error": "Unsupported integration provider.", "provider": normalize_provider(provider)}), 404
    workspace_id = integration_workspace_id(payload)
    mapping = payload.get("mapping") if isinstance(payload.get("mapping"), dict) else payload
    validation = validate_field_mapping(provider, mapping)
    if not validation["valid"] and not payload.get("save_draft"):
        return (
            jsonify(
                {
                    "error": "Field mapping is incomplete.",
                    "validation": validation,
                    "mapping_template": mapping_template(provider),
                }
            ),
            400,
        )
    saved = save_integration_field_mapping(
        workspace_id,
        manifest["provider"],
        validation["normalized_mapping"],
        validation,
        INTEGRATION_CONTRACT_VERSION,
    )
    return jsonify(
        {
            "api_version": "v1",
            "contract_version": INTEGRATION_CONTRACT_VERSION,
            "provider": manifest["provider"],
            "workspace_id": workspace_id,
            "field_mapping": saved,
        }
    )


@app.post("/v1/integrations/hubspot/workflow-actions/analyze-email")
@rate_limited()
def v1_hubspot_workflow_action():
    payload = request.get_json(silent=True) or {}
    workspace_id = integration_workspace_id(payload)
    mapping_record = get_integration_field_mapping(workspace_id, "hubspot")
    fields = payload.get("inputFields") if isinstance(payload.get("inputFields"), dict) else payload
    analysis_payload = {
        "workspace_id": workspace_id,
        "subject": mapped_input(fields, mapping_record, "subject", ["subject", "email_subject"]),
        "body": mapped_input(fields, mapping_record, "body", ["body", "email_body", "message"]),
        "audience": mapped_input(fields, mapping_record, "audience", ["audience"]) or "HubSpot contact",
        "intent": mapped_input(fields, mapping_record, "intent", ["intent"]) or "Workflow email",
        "channel": "hubspot_workflow",
        "source": "hubspot_workflow_action",
    }
    try:
        analysis = analyze_email_payload(analysis_payload, payload.get("requestId"))
    except Exception as error:
        return analysis_error_response(error)
    gate = analysis["policy"]["gate"]
    default_outputs = {
        "texttraits_request_id": analysis["request_id"],
        "texttraits_content_hash": analysis["content_hash"],
        "texttraits_score": analysis["scores"]["overall"],
        "texttraits_gate": gate["status"],
        "texttraits_route": gate["route"],
        "texttraits_send_ready": gate["send_ready"],
    }
    return jsonify(
        {
            "workflow": "hubspot_workflow_action",
            "workspace_id": workspace_id,
            "mapping_status": (mapping_record or {}).get("status", "default_mapping"),
            "outputFields": mapped_outputs(analysis, mapping_record, default_outputs),
            "analysis": compact_analysis(analysis),
        }
    )


@app.post("/v1/integrations/salesforce/journey-builder/activity")
@rate_limited()
def v1_salesforce_journey_activity():
    payload = request.get_json(silent=True) or {}
    workspace_id = integration_workspace_id(payload)
    mapping_record = get_integration_field_mapping(workspace_id, "salesforce")
    in_arguments = payload.get("inArguments") if isinstance(payload.get("inArguments"), list) else []
    fields: dict[str, Any] = {}
    for item in in_arguments:
        if isinstance(item, dict):
            fields.update(item)
    fields.update({key: value for key, value in payload.items() if key in {"subject", "body", "email_body", "audience", "intent"}})
    analysis_payload = {
        "workspace_id": workspace_id,
        "subject": mapped_input(fields, mapping_record, "subject", ["subject", "EmailSubject"]),
        "body": mapped_input(fields, mapping_record, "body", ["body", "email_body", "EmailBody"]),
        "audience": mapped_input(fields, mapping_record, "audience", ["audience", "ContactType"]) or "Salesforce contact",
        "intent": mapped_input(fields, mapping_record, "intent", ["intent", "JourneyName"]) or "Journey email",
        "channel": "salesforce_journey_builder",
        "source": "salesforce_journey_builder_activity",
    }
    try:
        analysis = analyze_email_payload(analysis_payload, payload.get("requestId"))
    except Exception as error:
        return analysis_error_response(error)
    gate = analysis["policy"]["gate"]
    default_arguments = {
        "texttraits_request_id": analysis["request_id"],
        "texttraits_score": analysis["scores"]["overall"],
        "texttraits_gate": gate["status"],
        "texttraits_route": gate["route"],
    }
    return jsonify(
        {
            "activity": "salesforce_journey_builder_activity",
            "branchResult": "send" if gate["send_ready"] else "review",
            "workspace_id": workspace_id,
            "mapping_status": (mapping_record or {}).get("status", "default_mapping"),
            "arguments": mapped_outputs(analysis, mapping_record, default_arguments),
            "analysis": compact_analysis(analysis),
        }
    )


@app.post("/v1/integrations/sendgrid-ses/middleware")
@rate_limited()
def v1_sendgrid_ses_middleware():
    started = time.perf_counter()
    payload = request.get_json(silent=True) or {}
    workspace_id = integration_workspace_id(payload)
    governance_policy = get_governance_policy(workspace_id)
    mapping_record = get_integration_field_mapping(workspace_id, "sendgrid_ses")
    message = payload.get("message") if isinstance(payload.get("message"), dict) else payload
    body = message.get("text") or message.get("body") or message.get("html") or ""
    analysis_payload = {
        "workspace_id": workspace_id,
        "subject": mapped_input(payload, mapping_record, "subject", ["message.subject", "subject"]),
        "body": mapped_input(payload, mapping_record, "body", ["message.text", "message.body", "message.html", "text", "body", "html"]) or body,
        "audience": mapped_input(payload, mapping_record, "audience", ["message.audience", "audience"]) or "Outbound recipient",
        "intent": mapped_input(payload, mapping_record, "intent", ["message.intent", "intent"]) or "Transactional or campaign email",
        "channel": str(payload.get("provider") or "sendgrid_ses_middleware"),
        "source": "sendgrid_ses_middleware",
        "assets": message.get("assets") or {},
        "tenant_id": payload.get("tenant_id") or "",
        "source_system": payload.get("source_system") or payload.get("provider") or "sendgrid_ses",
        "analysis_mode": payload.get("analysis_mode") or "send_path_middleware",
        "campaign_id": payload.get("campaign_id") or message.get("campaign_id") or "",
        "template_id": payload.get("template_id") or message.get("template_id") or "",
        "headers": message.get("headers") or payload.get("headers") or {},
        "delivery_context": payload.get("delivery_context") if isinstance(payload.get("delivery_context"), dict) else {},
    }
    try:
        analysis = analyze_email_payload(analysis_payload, payload.get("request_id"))
    except Exception as error:
        return analysis_error_response(error)
    gate = analysis["policy"]["gate"]
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    timeout_ms = int(governance_policy.get("send_path_timeout_ms") or 500)
    return jsonify(
        {
            "middleware": "sendgrid_ses",
            "workspace_id": workspace_id,
            "mapping_status": (mapping_record or {}).get("status", "default_mapping"),
            "allow_send": gate["send_ready"],
            "provider_action": "forward_to_provider" if gate["send_ready"] else "hold_for_review",
            "latency_budget": {
                "elapsed_ms": elapsed_ms,
                "timeout_ms": timeout_ms,
                "within_budget": elapsed_ms <= timeout_ms,
                "idempotency_window_seconds": governance_policy.get("idempotency_window_seconds"),
                "idempotency_key": str(payload.get("idempotency_key") or payload.get("request_id") or analysis["request_id"])[:180],
            },
            "headers": {
                "X-TextTraits-Request-ID": analysis["request_id"],
                "X-TextTraits-Policy-Version": analysis["policy"]["bundle_version"],
                "X-TextTraits-Gate": gate["status"],
            },
            "analysis": compact_analysis(analysis),
        }
    )


def generic_enterprise_adapter_payload(payload: dict[str, Any], provider: str) -> dict[str, Any]:
    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    canvas_step = payload.get("canvas_step") if isinstance(payload.get("canvas_step"), dict) else {}
    asset = payload.get("asset") if isinstance(payload.get("asset"), dict) else {}
    input_fields = payload.get("inputFields") if isinstance(payload.get("inputFields"), dict) else {}
    in_arguments = payload.get("inArguments") if isinstance(payload.get("inArguments"), list) else []
    argument_fields: dict[str, Any] = {}
    for item in in_arguments:
        if isinstance(item, dict):
            argument_fields.update(item)
    source = {**payload, **input_fields, **argument_fields, **message, **canvas_step, **asset}
    body = (
        source.get("body")
        or source.get("content")
        or source.get("text")
        or source.get("html")
        or message.get("html")
        or asset.get("html")
        or canvas_step.get("body")
        or ""
    )
    return {
        "workspace_id": integration_workspace_id(payload),
        "tenant_id": payload.get("tenant_id") or "",
        "source_system": payload.get("source_system") or provider,
        "analysis_mode": payload.get("analysis_mode") or "pre_send_gate",
        "campaign_id": payload.get("campaign_id") or source.get("campaign_id") or source.get("campaignId") or source.get("program_id") or source.get("canvas_id") or source.get("email_campaign_id") or "",
        "journey_id": payload.get("journey_id") or source.get("journey_id") or source.get("workflow_id") or source.get("canvas_id") or "",
        "step_id": payload.get("step_id") or source.get("step_id") or source.get("activity_id") or "",
        "template_id": payload.get("template_id") or source.get("template_id") or source.get("asset_id") or source.get("id") or "",
        "template_version": payload.get("template_version") or source.get("template_version") or source.get("version") or "",
        "locale": payload.get("locale") or source.get("locale") or "",
        "subject": source.get("subject") or source.get("email_subject") or source.get("EmailSubject") or "",
        "body": body or source.get("email_body") or source.get("EmailBody") or "",
        "audience": payload.get("audience") or source.get("segment") or provider,
        "intent": payload.get("intent") or source.get("intent") or "Enterprise workflow gate",
        "channel": provider,
        "source": f"{provider}_sandbox_adapter",
        "headers": payload.get("headers") if isinstance(payload.get("headers"), dict) else message.get("headers") if isinstance(message.get("headers"), dict) else {},
        "personalization_context": payload.get("personalization_context") if isinstance(payload.get("personalization_context"), dict) else {},
        "recipient_context": payload.get("recipient_context") if isinstance(payload.get("recipient_context"), dict) else {},
        "consent_context": payload.get("consent_context") if isinstance(payload.get("consent_context"), dict) else {},
        "delivery_context": payload.get("delivery_context") if isinstance(payload.get("delivery_context"), dict) else {},
        "assets": source.get("assets") if isinstance(source.get("assets"), dict) else {},
    }


def adapter_response(provider: str, payload: dict[str, Any], request_id: str | None = None) -> tuple[dict[str, Any], int]:
    analysis_payload = generic_enterprise_adapter_payload(payload, provider)
    try:
        analysis = analyze_email_payload(analysis_payload, request_id or payload.get("request_id") or payload.get("requestId"))
    except Exception as error:
        response, status = analysis_error_response(error)
        return response.get_json() or {"error": str(error)}, status
    gate = analysis["policy"]["gate"]
    return {
        "adapter": provider,
        "workspace_id": analysis_payload["workspace_id"],
        "decision": "send" if gate["send_ready"] else "review",
        "writeback": {
            "texttraits_request_id": analysis["request_id"],
            "texttraits_content_hash": analysis["content_hash"],
            "texttraits_score": analysis["scores"]["overall"],
            "texttraits_gate": gate["status"],
            "texttraits_route": gate["route"],
        },
        "render_test": analysis["input"].get("rendered_template", {}),
        "analysis": compact_analysis(analysis),
    }, 200


@app.post("/v1/integrations/braze/canvas-gate")
@rate_limited()
def v1_braze_canvas_gate():
    payload = request.get_json(silent=True) or {}
    response, status = adapter_response("braze", payload)
    return jsonify(response), status


@app.post("/v1/integrations/marketo/smart-campaign-gate")
@rate_limited()
def v1_marketo_smart_campaign_gate():
    payload = request.get_json(silent=True) or {}
    response, status = adapter_response("marketo", payload)
    return jsonify(response), status


@app.post("/v1/integrations/iterable/workflow-gate")
@rate_limited()
def v1_iterable_workflow_gate():
    payload = request.get_json(silent=True) or {}
    response, status = adapter_response("iterable", payload)
    return jsonify(response), status


@app.post("/v1/integrations/warehouse/feedback-import")
@rate_limited(20)
def v1_warehouse_feedback_import():
    payload = request.get_json(silent=True) or {}
    rows = payload.get("rows") if isinstance(payload.get("rows"), list) else payload.get("samples")
    if not isinstance(rows, list) or not rows:
        return jsonify({"error": "Provide non-empty rows or samples for warehouse feedback import."}), 400
    workspace_id = integration_workspace_id(payload)
    import_payload = {**payload, "workspace_id": workspace_id, "samples": rows, "source_system": "warehouse"}
    summaries = []
    errors = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append({"index": index, "error": "Warehouse row must be an object."})
            continue
        response, status = adapter_response("warehouse", {**payload, **row, "workspace_id": workspace_id}, f"{stable_import_id(import_payload)}:{index}")
        if status == 200:
            summaries.append({"index": index, **response["analysis"]})
            event_type = str(row.get("event_type") or row.get("delivery_status") or "").strip()
            if event_type:
                save_email_outcome(
                    {
                        "workspace_id": workspace_id,
                        "request_id": response["analysis"]["request_id"],
                        "content_hash": response["analysis"]["content_hash"],
                        "provider": row.get("provider") or row.get("source_system") or "warehouse",
                        "event_type": event_type,
                        "delivery_status": row.get("delivery_status") or event_type,
                        "campaign_id": row.get("campaign_id") or "",
                        "template_id": row.get("template_id") or "",
                        "event_timestamp": row.get("event_timestamp") or utc_now(),
                    },
                    workspace_id=workspace_id,
                )
        else:
            errors.append({"index": index, "error": response.get("error", "Warehouse row failed analysis.")})
    summary = save_sample_import(
        {
            "import_id": stable_import_id(import_payload),
            "workspace_id": workspace_id,
            "accepted": len(summaries),
            "rejected": len(errors),
            "chunk_index": int(payload.get("chunk_index") or 0),
            "chunk_total": int(payload.get("chunk_total") or 1),
            "resume_token": str(payload.get("resume_token") or ""),
            "average_score": round(sum(row["score"] for row in summaries) / len(summaries), 1) if summaries else 0,
            "blocked_or_review": sum(1 for row in summaries if row["gate"]["status"] != "ready"),
            "created_at": utc_now(),
        },
        workspace_id=workspace_id,
    )
    return jsonify({"summary": summary, "rows": summaries, "errors": errors})


@app.post("/v1/integrations/simulate")
@rate_limited(40)
def v1_adapter_simulator():
    payload = request.get_json(silent=True) or {}
    provider = normalize_provider(str(payload.get("provider") or "hubspot"))
    adapter_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
    response, status = adapter_response(provider, adapter_payload)
    response["manifest"] = provider_manifest(provider)
    response["mapping_template"] = mapping_template(provider)
    return jsonify(response), status


@app.post("/v1/templates/render-test")
@rate_limited(60)
def v1_template_render_test():
    payload = request.get_json(silent=True) or {}
    harness = rendered_template_harness(payload)
    include_preview = bool(payload.get("include_rendered_preview"))
    response = {
        "api_version": "v1",
        "workspace_id": integration_workspace_id(payload),
        "render_test": safe_template_summary(harness),
    }
    if include_preview:
        response["rendered_preview"] = {
            "subject": harness.get("rendered_subject", ""),
            "body": harness.get("rendered_body", ""),
        }
    return jsonify(response)


def webhook_dedupe_key(payload: dict[str, Any]) -> str:
    explicit = str(payload.get("event_id") or payload.get("id") or payload.get("message_id") or "").strip()
    if explicit:
        return explicit[:180]
    canonical = json.dumps(scrub_payload(payload), sort_keys=True, separators=(",", ":"))[:4000]
    return "event_hash:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def supplied_webhook_signature() -> str:
    for header in ("X-TextTraits-Signature", "X-Hub-Signature-256", "X-Signature-SHA256"):
        value = request.headers.get(header, "").strip()
        if value:
            return value if value.lower().startswith("sha256=") else f"sha256={value}"
    return ""


def supplied_webhook_timestamp() -> str:
    for header in ("X-TextTraits-Timestamp", "X-Webhook-Timestamp", "X-Request-Timestamp"):
        value = request.headers.get(header, "").strip()
        if value:
            return value
    return ""


def webhook_timestamp_valid(timestamp: str) -> str:
    if not timestamp:
        return "missing_timestamp" if env_flag("TEXTTRAITS_WEBHOOK_REQUIRE_TIMESTAMP", PRODUCTION) else "not_required"
    try:
        supplied = float(timestamp)
    except ValueError:
        return "malformed_timestamp"
    now = time.time()
    if abs(now - supplied) > max(WEBHOOK_SIGNATURE_TOLERANCE_SECONDS, 1):
        return "stale_timestamp"
    return "ok"


def webhook_signature_status() -> str:
    secret = os.getenv("TEXTTRAITS_WEBHOOK_SECRET", "").strip()
    if not secret:
        return "not_configured"
    supplied = supplied_webhook_signature()
    if not supplied:
        return "missing"
    raw_body = request.get_data(cache=True)
    timestamp = supplied_webhook_timestamp()
    timestamp_status = webhook_timestamp_valid(timestamp)
    if timestamp_status not in {"ok", "not_required"}:
        return timestamp_status
    signed_payloads = [raw_body]
    if timestamp_status == "ok":
        signed_payloads.insert(0, f"{timestamp}.".encode("utf-8") + raw_body)
    for signed_payload in signed_payloads:
        expected = "sha256=" + hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected, supplied):
            return "verified"
    return "invalid"


@app.post("/v1/webhooks/post-send")
@rate_limited(180)
def v1_post_send_webhook():
    payload = request.get_json(silent=True) or {}
    workspace_id = integration_workspace_id(payload)
    governance_policy = get_governance_policy(workspace_id)
    signature_status = webhook_signature_status()
    if signature_status in {"invalid", "missing", "missing_timestamp", "malformed_timestamp", "stale_timestamp"}:
        return jsonify({"accepted": False, "retry": False, "error": "Webhook signature verification failed."}), 401
    provider = str(payload.get("provider") or "").strip()
    event_type = str(payload.get("event_type") or payload.get("event") or "").strip()
    if not provider or not event_type:
        return (
            jsonify(
                {
                    "accepted": False,
                    "retry": True,
                    "retry_after_seconds": 300,
                    "error": "Webhook event requires provider and event_type.",
                }
            ),
            202,
        )
    key = webhook_dedupe_key(payload)
    record = {
        "workspace_id": workspace_id,
        "dedupe_key": key,
        "provider": provider[:80],
        "event_type": event_type[:80],
        "request_id": str(payload.get("request_id") or payload.get("texttraits_request_id") or "")[:120],
        "content_hash": str(payload.get("content_hash") or "")[:120],
        "first_seen_at": utc_now(),
        "last_seen_at": utc_now(),
        "seen_count": 1,
        "delivery_status": str(payload.get("delivery_status") or payload.get("status") or "received")[:80],
        "signature_status": signature_status,
        "campaign_id": str(payload.get("campaign_id") or "")[:160],
        "template_id": str(payload.get("template_id") or "")[:160],
    }
    event, duplicate = upsert_webhook_event(
        key,
        record,
        payload,
        workspace_id=workspace_id,
        dedupe_window_days=int(governance_policy.get("webhook_dedupe_window_days") or 30),
    )
    outcome = save_email_outcome({**record, "event_timestamp": event["last_seen_at"]}, workspace_id=workspace_id)
    return jsonify(
        {
            "accepted": True,
            "duplicate": duplicate,
            "workspace_id": workspace_id,
            "dedupe_key": key,
            "dedupe_window_days": governance_policy.get("webhook_dedupe_window_days"),
            "signature_status": signature_status,
            "event": event,
            "outcome": outcome,
        }
    )


@app.post("/v1/samples/import")
@rate_limited(20)
def v1_samples_import():
    payload = request.get_json(silent=True) or {}
    workspace_id = integration_workspace_id(payload)
    governance_policy = get_governance_policy(workspace_id)
    samples = payload.get("samples")
    if not isinstance(samples, list) or not samples:
        return jsonify({"error": "Provide a non-empty samples array."}), 400
    sample_limit = int(governance_policy.get("sample_import_limit") or 25)
    if len(samples) > sample_limit:
        return jsonify({"error": f"Import up to {sample_limit} samples at a time for this workspace."}), 413
    import_id = stable_import_id(payload)
    rows = []
    errors = []
    for index, sample in enumerate(samples):
        if not isinstance(sample, dict):
            errors.append({"index": index, "error": "Sample must be an object."})
            continue
        try:
            analysis = analyze_email_payload(
                {
                    **sample,
                    "workspace_id": workspace_id,
                    "audience": sample.get("audience") or payload.get("audience") or "Batch import",
                    "intent": sample.get("intent") or payload.get("intent") or "Warehouse sample",
                    "channel": sample.get("channel") or "warehouse_import",
                    "source": "batch_sample_import",
                },
                f"{import_id}:{index}",
            )
            rows.append({"index": index, **compact_analysis(analysis)})
        except Exception as error:
            errors.append({"index": index, "error": str(error)})
    summary = {
        "import_id": import_id,
        "workspace_id": workspace_id,
        "chunk_index": int(payload.get("chunk_index") or 0),
        "chunk_total": int(payload.get("chunk_total") or 1),
        "resume_token": str(payload.get("resume_token") or ""),
        "accepted": len(rows),
        "rejected": len(errors),
        "average_score": round(sum(row["score"] for row in rows) / len(rows), 1) if rows else 0,
        "blocked_or_review": sum(1 for row in rows if row["gate"]["status"] != "ready"),
        "created_at": utc_now(),
    }
    summary = save_sample_import(summary, workspace_id=workspace_id)
    return jsonify({"summary": summary, "rows": rows, "errors": errors})


def stable_import_id(payload: dict[str, Any]) -> str:
    explicit = str(payload.get("import_id") or "").strip()
    if explicit:
        return explicit[:120]
    return "import_" + hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def csv_safe_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        text = json.dumps(scrub_payload(value), separators=(",", ":"), sort_keys=True)
    else:
        text = str(value)
    if text and text[0] in {"=", "+", "-", "@", "\t", "\r", "\n"}:
        return "'" + text
    return text


def csv_safe_rows(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [{key: csv_safe_cell(value) for key, value in row.items()} for row in rows]


def safe_attachment_filename(kind: str, workspace_id: str) -> str:
    stem = f"texttraits-{kind}-{workspace_id}"
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "-", stem).strip(".-")[:140]
    return f"{clean or 'texttraits-export'}.csv"


@app.get("/v1/governance/dashboard")
def v1_governance_dashboard():
    workspace_id = integration_workspace_id()
    snapshot = enterprise_governance_snapshot(limit=20, workspace_id=workspace_id)
    return jsonify(
        {
            "api_version": "v1",
            "policy_bundle_version": "2026.05.25",
            "model_version": str(getattr(predictor, "metadata", {}).get("trained_at") or "local-texttraits-bundle"),
            **snapshot,
            "integration_flows": integration_flow_catalog(),
            "enterprise_integration_plan": load_enterprise_integration_plan(),
            "field_mappings": recent_integration_field_mappings(workspace_id=workspace_id, limit=20),
        }
    )


@app.get("/v1/governance/export")
def v1_governance_export():
    workspace_id = integration_workspace_id()
    kind = str(request.args.get("type") or request.args.get("kind") or "analyses").strip().lower()
    export_format = str(request.args.get("format") or "json").strip().lower()
    limit = int(request.args.get("limit") or 1000)
    try:
        rows = governance_export_rows(kind, workspace_id=workspace_id, limit=limit)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    if export_format == "csv":
        output = io.StringIO()
        fieldnames = sorted({key for row in rows for key in row.keys()}) or ["empty"]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_safe_rows(rows))
        response = app.response_class(output.getvalue(), mimetype="text/csv")
        response.headers["Content-Disposition"] = f'attachment; filename="{safe_attachment_filename(kind, workspace_id)}"'
        return response
    return jsonify({"api_version": "v1", "workspace_id": workspace_id, "type": kind, "rows": rows})


@app.get("/v1/governance/policy")
def v1_governance_policy():
    workspace_id = integration_workspace_id()
    return jsonify(
        {
            "api_version": "v1",
            "workspace_id": workspace_id,
            "policy": get_governance_policy(workspace_id),
        }
    )


@app.put("/v1/governance/policy")
@rate_limited(40)
def v1_governance_policy_save():
    payload = request.get_json(silent=True) or {}
    workspace_id = integration_workspace_id(payload)
    policy_payload = payload.get("policy") if isinstance(payload.get("policy"), dict) else payload
    policy = save_governance_policy(workspace_id, policy_payload)
    log_event(current_user_id(), "governance_policy_updated", {"workspace_id": workspace_id, "policy": policy})
    return jsonify(
        {
            "api_version": "v1",
            "workspace_id": workspace_id,
            "policy": policy,
        }
    )


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
    user_id, error = require_user()
    if error:
        return error
    entry = get_provider(provider)
    if not entry:
        return jsonify({"error": "Unsupported integration provider."}), 404
    code = request.args.get("code", "")
    state = request.args.get("state", "")
    if not code or not state:
        return jsonify({"error": "OAuth callback is missing code or state."}), 400
    try:
        decoded = decoded_state(state)
    except Exception:
        return jsonify({"error": "OAuth state is invalid."}), 400
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
          <body data-mode="enterprise-optimizer">
        <main class="app-shell legal-shell">
          <header class="topbar legal-topbar">
            <div class="brand-block">
              <p class="eyebrow">TextTraits</p>
              <h1>Privacy</h1>
              <p>Enterprise-grade handling for email analysis, governance metadata, and integration setup.</p>
            </div>
            <a class="button-secondary legal-home-link" href="/">Back to TextTraits</a>
          </header>
          <section class="panel legal-page">
            <article>
              <span class="interface-label">Data handling</span>
              <p>TextTraits stores account and workspace data for signed-in users, including saved writing history, campaigns, drafts, outcomes, settings, and integration connection status.</p>
              <p>Text submitted for analysis is processed by the TextTraits application. Raw pasted text is not included in normal workspace sync unless a user saves a reading, draft, or campaign that contains it.</p>
            </article>
            <article>
              <span class="interface-label">Controls</span>
              <p>Signed-in users can export their account data and delete their account from the account menu. Deletion removes the synced workspace and integration connection records for that account.</p>
              <p>Enterprise integrations require administrator setup before any CRM or email data is exchanged. Preview integrations do not connect to third-party systems.</p>
            </article>
            <article>
              <span class="interface-label">Operational safeguards</span>
              <p>Operational logs and error reports are used to keep the service reliable and should avoid storing passwords, reset codes, API keys, and OAuth credentials.</p>
            </article>
          </section>
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
          <body data-mode="enterprise-optimizer">
        <main class="app-shell legal-shell">
          <header class="topbar legal-topbar">
            <div class="brand-block">
              <p class="eyebrow">TextTraits</p>
              <h1>Terms</h1>
              <p>Operational terms for an optimization layer that evaluates existing messages and does not generate replacement emails.</p>
            </div>
            <a class="button-secondary legal-home-link" href="/">Back to TextTraits</a>
          </header>
          <section class="panel legal-page">
            <article>
              <span class="interface-label">Product role</span>
              <p>TextTraits is an email optimization and outreach workflow scoring tool. It evaluates existing messages and does not generate replacement emails in this branch.</p>
            </article>
            <article>
              <span class="interface-label">Administrator responsibility</span>
              <p>Team administrators are responsible for approved claims, compliance requirements, permissions, retention settings, external integration credentials, and user access.</p>
              <p>Preview integrations are disabled until real credentials, provider approvals, and field mappings are configured by the workspace owner.</p>
            </article>
            <article>
              <span class="interface-label">Content and compliance</span>
              <p>Users must not upload content they do not have the right to process, and must review outreach copy for accuracy, consent, opt-out handling, and applicable laws before sending.</p>
            </article>
          </section>
        </main>
          </body>
        </html>
        """
    )


@app.get("/security")
def security():
    return render_template_string(
        """
        <!doctype html>
        <html lang="en">
          <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>TextTraits Security</title>
            <link rel="stylesheet" href="/static/styles.css">
            <script
              src="https://js.sentry-cdn.com/e02e26721e10ee55975fc73c5b7dfd57.min.js"
              crossorigin="anonymous"
            ></script>
          </head>
          <body data-mode="enterprise-optimizer">
        <main class="app-shell legal-shell">
          <header class="topbar legal-topbar">
            <div class="brand-block">
              <p class="eyebrow">TextTraits</p>
              <h1>Security</h1>
              <p>Internal enterprise trust package for data handling, retention, model limits, and integration boundaries.</p>
            </div>
            <a class="button-secondary legal-home-link" href="/">Back to TextTraits</a>
          </header>
          <section class="panel legal-page">
            <article>
              <span class="interface-label">Data handling</span>
              <p>Default governance storage is designed around request IDs, content hashes, normalized findings, policy metadata, and outcome joins. Raw email body text is excluded from normal governance responses.</p>
            </article>
            <article>
              <span class="interface-label">Retention controls</span>
              <p>Workspace policies define analysis retention, webhook retention, dedupe windows, and storage mode. Production deployments should pair these controls with database backup and restore policies.</p>
            </article>
            <article>
              <span class="interface-label">Model limits</span>
              <p>TextTraits returns policy-backed signals and confidence metadata for existing messages. It should be treated as decision support, not a legal, deliverability, or compliance authority.</p>
            </article>
            <article>
              <span class="interface-label">Integration boundaries</span>
              <p>Sandbox adapters are for payload validation and workflow design. Production connections require real provider credentials, scoped API keys, webhook signing secrets, and administrator approval.</p>
            </article>
          </section>
        </main>
          </body>
        </html>
        """
    )


@app.get("/deployment")
def deployment():
    return render_template_string(
        """
        <!doctype html>
        <html lang="en">
          <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>TextTraits Deployment</title>
            <link rel="stylesheet" href="/static/styles.css">
            <script
              src="https://js.sentry-cdn.com/e02e26721e10ee55975fc73c5b7dfd57.min.js"
              crossorigin="anonymous"
            ></script>
          </head>
          <body data-mode="enterprise-optimizer">
        <main class="app-shell legal-shell">
          <header class="topbar legal-topbar">
            <div class="brand-block">
              <p class="eyebrow">TextTraits</p>
              <h1>Deployment Readiness</h1>
              <p>Checklist for moving the enterprise optimizer from local sandbox to production workflow infrastructure.</p>
            </div>
            <a class="button-secondary legal-home-link" href="/">Back to TextTraits</a>
          </header>
          <section class="panel legal-page">
            <article>
              <span class="interface-label">Secrets</span>
              <p>Set high-entropy application secrets, scoped server-to-server API keys, webhook signing secrets, and provider OAuth credentials outside source control.</p>
            </article>
            <article>
              <span class="interface-label">Database</span>
              <p>Use hosted Postgres with SSL, backups, retention controls, restore testing, and environment separation for sandbox, staging, and production.</p>
            </article>
            <article>
              <span class="interface-label">Runtime</span>
              <p>Run behind HTTPS with secure cookies, a production WSGI server, request timeouts, monitoring, error reporting, and alerting for send-path latency.</p>
            </article>
            <article>
              <span class="interface-label">Operations</span>
              <p>Document key rotation, incident ownership, webhook replay handling, export governance, and approval workflows before connecting live enterprise traffic.</p>
            </article>
          </section>
        </main>
          </body>
        </html>
        """
    )


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=port, debug=ENABLE_DEV_TOOLS)
