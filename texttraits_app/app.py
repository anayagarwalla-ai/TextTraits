from __future__ import annotations

import logging
import os
import secrets
import time
from collections import defaultdict, deque
from functools import wraps
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from flask import Flask, Response, jsonify, redirect, render_template, render_template_string, request, session
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
    create_password_reset,
    create_user,
    database_status,
    database_backend,
    database_url,
    delete_user,
    export_user_data,
    get_verification_token,
    get_user_by_id,
    get_workspace,
    init_db,
    integrations,
    log_event,
    recent_events,
    reset_password,
    save_workspace,
    upsert_integration,
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
ALLOW_DEMO_MODE = env_flag("TEXTTRAITS_ALLOW_DEMO", True)
MAX_TEXT_WORDS = int(os.getenv("TEXTTRAITS_MAX_TEXT_WORDS", "1800"))
RATE_LIMIT_PER_MINUTE = int(os.getenv("TEXTTRAITS_RATE_LIMIT_PER_MINUTE", "80"))
APP_SECRET = os.getenv("TEXTTRAITS_SECRET_KEY", "dev-texttraits-change-me")
PUBLIC_BASE_URL = os.getenv("TEXTTRAITS_PUBLIC_BASE_URL", "http://127.0.0.1:5000")
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
configure_logging(ARTIFACT_DIR / "app.log")


def validate_runtime_config() -> None:
    production = os.getenv("TEXTTRAITS_ENV", "").strip().lower() == "production"
    failures: list[str] = []
    if APP_SECRET.startswith(("dev-", "replace-")):
        message = "TEXTTRAITS_SECRET_KEY must be a real high-entropy secret."
        if production:
            failures.append(message)
        else:
            logging.warning(message)
    if production:
        public_origin = urlparse(PUBLIC_BASE_URL)
        if public_origin.scheme != "https":
            failures.append("TEXTTRAITS_PUBLIC_BASE_URL must use HTTPS in production.")
        if not env_flag("TEXTTRAITS_SECURE_COOKIES", False):
            failures.append("TEXTTRAITS_SECURE_COOKIES=true is required in production.")
        if database_backend() != "postgres":
            failures.append("Production requires DATABASE_URL or TEXTTRAITS_DATABASE_URL for hosted Postgres.")
        elif "sslmode=require" not in database_url():
            failures.append("Production Postgres must use SSL. Set TEXTTRAITS_DB_SSLMODE=require or include sslmode=require.")
        if not email_status()["configured"]:
            failures.append("Production requires TEXTTRAITS_EMAIL_PROVIDER with working SMTP or SendGrid settings.")
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
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
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
    return int(value) if value else None


def require_user() -> tuple[int | None, tuple | None]:
    user_id = current_user_id()
    if not user_id:
        return None, (jsonify({"error": "Please sign in to sync this workspace."}), 401)
    return user_id, None


def public_url(path: str) -> str:
    return f"{PUBLIC_BASE_URL.rstrip('/')}/{path.lstrip('/')}"


def send_verification_email(user: dict) -> dict:
    token = get_verification_token(int(user["id"]))
    if not token:
        return {"sent": False, "provider": "already_verified"}
    url = public_url(f"/api/verify-email?token={token}")
    try:
        return send_account_email(
            user["email"],
            "Verify your TextTraits account",
            f"Verify your TextTraits account by opening this link:\n\n{url}\n\nIf you did not create this account, you can ignore this email.",
            f"<p>Verify your TextTraits account by opening this link:</p><p><a href=\"{url}\">Verify email</a></p>",
        )
    except Exception as error:
        logging.exception("verification_email_failed")
        return {"sent": False, "provider": email_status()["provider"], "error": str(error)}


def send_password_reset_email(email: str, token: str) -> dict:
    url = public_url(f"/api/reset-password?token={token}")
    try:
        return send_account_email(
            email,
            "Reset your TextTraits password",
            f"Reset your TextTraits password by opening this link:\n\n{url}\n\nThis link expires in one hour.",
            f"<p>Reset your TextTraits password by opening this link:</p><p><a href=\"{url}\">Reset password</a></p><p>This link expires in one hour.</p>",
        )
    except Exception as error:
        logging.exception("password_reset_email_failed")
        return {"sent": False, "provider": email_status()["provider"], "error": str(error)}


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    if app.config["SESSION_COOKIE_SECURE"]:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


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
        "database": database_backend(),
        "database_status": database_status(),
        "email_delivery": email_status(),
        "error_reporting": ERROR_REPORTING_STATUS,
        "configured_integrations": configured_integration_count(),
        "max_text_words": MAX_TEXT_WORDS,
        "rate_limit_per_minute": RATE_LIMIT_PER_MINUTE,
        "privacy_url": "/privacy",
        "terms_url": "/terms",
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
    )


@app.get("/health")
def health():
    db = check_database()
    return jsonify(
        {
            "ok": not isinstance(predictor, MissingPredictor),
            "demo": bool(getattr(predictor, "is_demo", False)),
            "model": public_model_info(),
            "dev_tools_enabled": ENABLE_DEV_TOOLS,
            "persistence": public_app_info()["database"],
            "database": db,
            "email": public_app_info()["email_delivery"],
            "error_reporting": public_app_info()["error_reporting"],
            "configured_integrations": public_app_info()["configured_integrations"],
            "sync": True,
        }
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
        return jsonify(
            {
                "model": model_id,
                "demo": bool(getattr(predictor, "is_demo", False)),
                "predictions": predictor.predict(text),
            }
        )
    except RuntimeError as error:
        return jsonify({"error": str(error)}), 503


@app.get("/api/session")
def api_session():
    user_id = current_user_id()
    user = get_user_by_id(user_id) if user_id else None
    return jsonify(
        {
            "authenticated": bool(user),
            "user": user,
            "app": public_app_info(),
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
    if len(password) < 8:
        return jsonify({"error": "Use at least 8 characters for the password."}), 400
    try:
        user = create_user(email, password, name)
    except Exception:
        return jsonify({"error": "That email already has an account. Try signing in."}), 409
    session["user_id"] = user["id"]
    log_event(user["id"], "signup", {"email": user["email"]})
    email_result = send_verification_email(user)
    response = {"authenticated": True, "user": user, "workspace": get_workspace(user["id"]), "email_delivery": email_result}
    if not email_result.get("sent"):
        token = get_verification_token(int(user["id"]))
        if token:
            response["dev_verify_url"] = public_url(f"/api/verify-email/{token}")
    return jsonify(response)


@app.post("/api/login")
@rate_limited(20)
def api_login():
    payload = request.get_json(silent=True) or {}
    user = authenticate_user(str(payload.get("email", "")), str(payload.get("password", "")))
    if not user:
        return jsonify({"error": "Email or password did not match."}), 401
    session["user_id"] = user["id"]
    log_event(user["id"], "login", {"email": user["email"]})
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
        response["email_delivery"] = delivery
    if reset and not email_status()["configured"]:
        response["dev_reset_url"] = public_url(f"/api/reset-password/{reset['token']}")
        response["expires_at"] = reset["expires_at"]
    return jsonify(response)


@app.post("/api/reset-password")
@rate_limited(8)
def api_reset_password():
    payload = request.get_json(silent=True) or {}
    token = str(payload.get("token", ""))
    password = str(payload.get("password", ""))
    if len(password) < 8:
        return jsonify({"error": "Use at least 8 characters for the new password."}), 400
    user = reset_password(token, password)
    if not user:
        return jsonify({"error": "Reset link is invalid or expired."}), 400
    session["user_id"] = user["id"]
    return jsonify({"authenticated": True, "user": user, "workspace": get_workspace(user["id"])})


@app.get("/api/reset-password")
@app.get("/api/reset-password/<token>")
def api_reset_password_link(token: str | None = None):
    clean = token or request.args.get("token", "")
    return redirect(f"/?reset_token={clean}")


@app.post("/api/verify-email")
@rate_limited(20)
def api_verify_email():
    payload = request.get_json(silent=True) or {}
    user = verify_email_token(str(payload.get("token", "")))
    if not user:
        return jsonify({"error": "Verification link is invalid."}), 400
    session["user_id"] = user["id"]
    return jsonify({"authenticated": True, "user": user, "workspace": get_workspace(user["id"])})


@app.get("/api/verify-email")
@app.get("/api/verify-email/<token>")
def api_verify_email_link(token: str | None = None):
    clean = token or request.args.get("token", "")
    user = verify_email_token(str(clean))
    if user:
        session["user_id"] = user["id"]
        return redirect("/?verified=1")
    return redirect("/?verified=0")


@app.get("/api/account/export")
def api_account_export():
    user_id, error = require_user()
    if error:
        return error
    data = export_user_data(user_id)
    log_event(user_id, "account_exported", {})
    return jsonify(data)


@app.delete("/api/account")
@rate_limited(6)
def api_account_delete():
    user_id, error = require_user()
    if error:
        return error
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
    workspace = save_workspace(user_id, data, payload.get("name"))
    log_event(user_id, "workspace_saved", {"keys": sorted(data.keys())[:20]})
    return jsonify({"workspace": workspace})


@app.post("/api/events")
@rate_limited(120)
def api_events():
    payload = request.get_json(silent=True) or {}
    log_event(current_user_id(), str(payload.get("event_type", "client_event")), payload.get("payload") or {})
    return jsonify({"ok": True})


@app.post("/api/client-errors")
@rate_limited(60)
def api_client_errors():
    payload = request.get_json(silent=True) or {}
    logging.error("client_error %s", payload)
    log_event(current_user_id(), "client_error", payload)
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
    return jsonify({"integration": upsert_integration(user_id, provider, status, payload.get("config") or {})})


@app.get("/api/integrations/<provider>/oauth/start")
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
        return jsonify({"error": "OAuth exchange failed. Check provider credentials and redirect URL.", "details": str(oauth_error)}), 502

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
        <!doctype html><title>TextTraits Privacy</title>
        <main style="max-width:760px;margin:40px auto;font-family:system-ui;line-height:1.6;padding:0 20px">
          <h1>Privacy</h1>
          <p>TextTraits stores signed-in workspace data so users can return to writing history, campaigns, drafts, outcomes, settings, and integration statuses.</p>
          <p>Text submitted for analysis is processed by the TextTraits Flask app and saved only when the user saves or syncs a workspace.</p>
          <p>Signed-in users can export workspace data and delete their account. Production deployments should configure hosted storage, HTTPS, backups, monitoring, and email delivery.</p>
          <p>Enterprise integrations require separate provider credentials and administrator approval before any CRM or email data is exchanged.</p>
          <p><a href="/">Back to TextTraits</a></p>
        </main>
        """
    )


@app.get("/terms")
def terms():
    return render_template_string(
        """
        <!doctype html><title>TextTraits Terms</title>
        <main style="max-width:760px;margin:40px auto;font-family:system-ui;line-height:1.6;padding:0 20px">
          <h1>Terms</h1>
          <p>TextTraits is a writing coach and outreach workflow tool. Users are responsible for reviewing generated drafts before using them.</p>
          <p>Team administrators are responsible for approved claims, compliance requirements, permissions, retention settings, and external integration credentials.</p>
          <p>Preview integrations are disabled until real credentials and provider approvals are configured.</p>
          <p><a href="/">Back to TextTraits</a></p>
        </main>
        """
    )


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=port, debug=ENABLE_DEV_TOOLS)
