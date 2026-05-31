from __future__ import annotations

import json
import os
import sqlite3
import secrets
import hashlib
import hmac
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from werkzeug.security import check_password_hash, generate_password_hash

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - optional production dependency
    psycopg = None
    dict_row = None


APP_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = APP_DIR / "artifacts" / "texttraits_workspace.sqlite3"
SCHEMA_VERSION = "2026_05_15_initial_workspace_schema"
ENTERPRISE_SCHEMA_VERSION = "2026_05_25_enterprise_v1_workflows"
INTEGRATION_MAPPING_SCHEMA_VERSION = "2026_05_25_integration_field_mappings"
GOVERNANCE_POLICY_SCHEMA_VERSION = "2026_05_25_governance_policy_controls"
GOVERNANCE_ANALYTICS_SCHEMA_VERSION = "2026_05_25_enterprise_governance_analytics"

DEFAULT_RULE_FAMILY_MODES = {
    "compliance": "fail_closed",
    "unsubscribe": "fail_closed",
    "personalization": "review",
    "cta": "review",
    "specificity": "review",
    "clarity": "fail_open",
    "format": "fail_open",
    "subject": "fail_open",
}

DEFAULT_GOVERNANCE_POLICY = {
    "policy_environment": "production",
    "retention_days": 180,
    "webhook_retention_days": 365,
    "webhook_dedupe_window_days": 30,
    "min_ready_score": 72,
    "high_severity_requires_review": True,
    "rule_family_modes": DEFAULT_RULE_FAMILY_MODES,
    "content_storage_mode": "hash_only",
    "sample_import_limit": 25,
    "send_path_timeout_ms": 500,
    "idempotency_window_seconds": 900,
}


def db_path() -> Path:
    return Path(os.getenv("TEXTTRAITS_DB_PATH", str(DEFAULT_DB_PATH))).expanduser()


def database_url() -> str:
    raw_url = (os.getenv("TEXTTRAITS_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()
    if not raw_url.startswith(("postgres://", "postgresql://")):
        return raw_url
    parsed = urlparse(raw_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if "connect_timeout" not in query:
        query["connect_timeout"] = os.getenv("TEXTTRAITS_DB_CONNECT_TIMEOUT", "10")
    sslmode = os.getenv("TEXTTRAITS_DB_SSLMODE", "").strip()
    if sslmode and "sslmode" not in query:
        query["sslmode"] = sslmode
    elif should_require_postgres_ssl(parsed.hostname or "") and "sslmode" not in query:
        query["sslmode"] = "require"
    return urlunparse(parsed._replace(query=urlencode(query)))


def should_require_postgres_ssl(hostname: str) -> bool:
    if os.getenv("TEXTTRAITS_ENV", "").strip().lower() != "production":
        return False
    return hostname not in {"localhost", "127.0.0.1", "::1", ""}


def uses_postgres() -> bool:
    return database_url().startswith(("postgres://", "postgresql://"))


def database_backend() -> str:
    return "postgres" if uses_postgres() else "sqlite"


def database_status(include_path: bool = False) -> dict[str, Any]:
    return {
        "backend": database_backend(),
        "ssl_required": bool(uses_postgres() and "sslmode=require" in database_url()),
        "path": str(db_path()) if include_path and not uses_postgres() else "",
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


SENSITIVE_PAYLOAD_KEYS = ("password", "secret", "token", "api_key", "apikey", "authorization", "credential")
SENSITIVE_VALUE_RE = re.compile(
    r"(?i)\b(password|token|secret|api[_-]?key|authorization|credential|reset_token|verify_token|access_token|refresh_token|client_secret)=([^&\s]+)"
)
BEARER_TOKEN_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
SAFE_EVENT_TYPE_RE = re.compile(r"[^a-zA-Z0-9_.:-]+")


def token_digest(token: str) -> str:
    return "sha256:" + hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_matches(stored_value: str | None, token: str) -> bool:
    if not stored_value or not token:
        return False
    return hmac.compare_digest(stored_value, token_digest(token.strip()))


def verification_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def normalize_verification_code(token: str) -> str:
    digits = re.sub(r"\D+", "", token.strip())
    return digits if len(digits) == 6 else ""


def redact_string(value: str) -> str:
    cleaned = SENSITIVE_VALUE_RE.sub(lambda match: f"{match.group(1)}=[redacted]", value)
    cleaned = BEARER_TOKEN_RE.sub("Bearer [redacted]", cleaned)
    return cleaned if len(cleaned) <= 500 else cleaned[:500] + "...[truncated]"


def contains_sensitive_key(value: Any, depth: int = 0) -> bool:
    if depth > 6:
        return False
    if isinstance(value, dict):
        for key, child in value.items():
            clean_key = str(key).lower()
            if any(marker in clean_key for marker in SENSITIVE_PAYLOAD_KEYS):
                return True
            if contains_sensitive_key(child, depth + 1):
                return True
    elif isinstance(value, list):
        return any(contains_sensitive_key(item, depth + 1) for item in value[:100])
    return False


def scrub_payload(value: Any, depth: int = 0) -> Any:
    if depth > 4:
        return "[truncated]"
    if isinstance(value, dict):
        cleaned = {}
        for key, child in value.items():
            clean_key = str(key)
            if any(marker in clean_key.lower() for marker in SENSITIVE_PAYLOAD_KEYS):
                cleaned[clean_key] = "[redacted]"
            else:
                cleaned[clean_key] = scrub_payload(child, depth + 1)
        return cleaned
    if isinstance(value, list):
        return [scrub_payload(item, depth + 1) for item in value[:50]]
    if isinstance(value, str):
        return redact_string(value)
    return value


def connect():
    if uses_postgres():
        if psycopg is None:
            raise RuntimeError("Postgres is configured but psycopg is not installed. Run `pip install psycopg[binary]`.")
        return psycopg.connect(database_url(), row_factory=dict_row)
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def check_database() -> dict[str, Any]:
    with connect() as conn:
        execute(conn, "SELECT 1").fetchone()
    return {"ok": True, **database_status()}


def sql(statement: str) -> str:
    return statement.replace("?", "%s") if uses_postgres() else statement


def execute(conn, statement: str, params: tuple[Any, ...] = ()):
    return conn.execute(sql(statement), params)


def init_db() -> None:
    with connect() as conn:
        if uses_postgres():
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                  id BIGSERIAL PRIMARY KEY,
                  email TEXT NOT NULL UNIQUE,
                  name TEXT NOT NULL,
                  password_hash TEXT NOT NULL,
                  email_verified_at TEXT,
                  verification_token TEXT,
                  reset_token TEXT,
                  reset_expires_at TEXT,
                  session_version INTEGER NOT NULL DEFAULT 0,
                  created_at TEXT NOT NULL,
                  last_login_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_signups (
                  email TEXT PRIMARY KEY,
                  name TEXT NOT NULL,
                  password_hash TEXT NOT NULL,
                  verification_token TEXT NOT NULL,
                  expires_at TEXT NOT NULL,
                  attempts INTEGER NOT NULL DEFAULT 0,
                  created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS workspaces (
                  id BIGSERIAL PRIMARY KEY,
                  user_id BIGINT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                  name TEXT NOT NULL DEFAULT 'Personal workspace',
                  data TEXT NOT NULL DEFAULT '{}',
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                  id BIGSERIAL PRIMARY KEY,
                  user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
                  event_type TEXT NOT NULL,
                  payload TEXT NOT NULL DEFAULT '{}',
                  created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS integration_connections (
                  id BIGSERIAL PRIMARY KEY,
                  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                  provider TEXT NOT NULL,
                  status TEXT NOT NULL,
                  config TEXT NOT NULL DEFAULT '{}',
                  updated_at TEXT NOT NULL,
                  UNIQUE(user_id, provider)
                )
                """
            )
        else:
            conn.executescript(
                """
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              email TEXT NOT NULL UNIQUE,
              name TEXT NOT NULL,
              password_hash TEXT NOT NULL,
              email_verified_at TEXT,
              verification_token TEXT,
              reset_token TEXT,
              reset_expires_at TEXT,
              session_version INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL,
              last_login_at TEXT
            );

            CREATE TABLE IF NOT EXISTS workspaces (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL UNIQUE,
              name TEXT NOT NULL DEFAULT 'Personal workspace',
              data TEXT NOT NULL DEFAULT '{}',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS pending_signups (
              email TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              password_hash TEXT NOT NULL,
              verification_token TEXT NOT NULL,
              expires_at TEXT NOT NULL,
              attempts INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER,
              event_type TEXT NOT NULL,
              payload TEXT NOT NULL DEFAULT '{}',
              created_at TEXT NOT NULL,
              FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS integration_connections (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL,
              provider TEXT NOT NULL,
              status TEXT NOT NULL,
              config TEXT NOT NULL DEFAULT '{}',
              updated_at TEXT NOT NULL,
              UNIQUE(user_id, provider),
              FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """
            )
        ensure_schema_version(conn)
        ensure_column(conn, "users", "email_verified_at", "TEXT")
        ensure_column(conn, "users", "verification_token", "TEXT")
        ensure_column(conn, "users", "reset_token", "TEXT")
        ensure_column(conn, "users", "reset_expires_at", "TEXT")
        ensure_column(conn, "users", "session_version", "INTEGER DEFAULT 0")
        ensure_enterprise_workflow_tables(conn)


def ensure_schema_version(conn) -> None:
    conn.execute(
        sql(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
              version TEXT PRIMARY KEY,
              applied_at TEXT NOT NULL
            )
            """
        )
    )
    record_schema_version(conn, SCHEMA_VERSION)


def record_schema_version(conn, version: str) -> None:
    if uses_postgres():
        conn.execute(
            """
            INSERT INTO schema_migrations (version, applied_at)
            VALUES (%s, %s)
            ON CONFLICT (version) DO NOTHING
            """,
            (version, utc_now()),
        )
    else:
        conn.execute(
            """
            INSERT OR IGNORE INTO schema_migrations (version, applied_at)
            VALUES (?, ?)
            """,
            (version, utc_now()),
        )


def ensure_enterprise_workflow_tables(conn) -> None:
    conn.execute(
        sql(
            """
            CREATE TABLE IF NOT EXISTS email_analyses (
              request_id TEXT PRIMARY KEY,
              content_hash TEXT NOT NULL,
              source TEXT NOT NULL,
              policy_bundle_version TEXT NOT NULL,
              model_version TEXT NOT NULL,
              gate_status TEXT NOT NULL,
              send_ready INTEGER NOT NULL,
              route TEXT NOT NULL,
              highest_severity TEXT NOT NULL,
              score INTEGER NOT NULL,
              finding_count INTEGER NOT NULL,
              analysis_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            )
            """
        )
    )
    conn.execute(
        sql(
            """
            CREATE TABLE IF NOT EXISTS webhook_events (
              dedupe_key TEXT PRIMARY KEY,
              provider TEXT NOT NULL,
              event_type TEXT NOT NULL,
              request_id TEXT,
              content_hash TEXT,
              delivery_status TEXT NOT NULL,
              event_json TEXT NOT NULL,
              first_seen_at TEXT NOT NULL,
              last_seen_at TEXT NOT NULL,
              seen_count INTEGER NOT NULL DEFAULT 1
            )
            """
        )
    )
    conn.execute(
        sql(
            """
            CREATE TABLE IF NOT EXISTS sample_imports (
              import_id TEXT PRIMARY KEY,
              summary_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            )
            """
        )
    )
    conn.execute(
        sql(
            """
            CREATE TABLE IF NOT EXISTS integration_field_mappings (
              workspace_id TEXT NOT NULL,
              provider TEXT NOT NULL,
              mapping_json TEXT NOT NULL,
              validation_json TEXT NOT NULL,
              status TEXT NOT NULL,
              version TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              PRIMARY KEY(workspace_id, provider)
            )
            """
        )
    )
    conn.execute(
        sql(
            """
            CREATE TABLE IF NOT EXISTS governance_policies (
              workspace_id TEXT PRIMARY KEY,
              policy_json TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )
    )
    conn.execute(
        sql(
            """
            CREATE TABLE IF NOT EXISTS policy_bundle_versions (
              id TEXT PRIMARY KEY,
              workspace_id TEXT NOT NULL,
              environment TEXT NOT NULL,
              policy_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            )
            """
        )
    )
    conn.execute(
        sql(
            """
            CREATE TABLE IF NOT EXISTS email_findings (
              id TEXT PRIMARY KEY,
              workspace_id TEXT NOT NULL,
              request_id TEXT NOT NULL,
              content_hash TEXT NOT NULL,
              rule_id TEXT NOT NULL,
              category TEXT NOT NULL,
              severity TEXT NOT NULL,
              title TEXT NOT NULL,
              remediation TEXT NOT NULL,
              evidence_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            )
            """
        )
    )
    conn.execute(
        sql(
            """
            CREATE TABLE IF NOT EXISTS email_outcomes (
              id TEXT PRIMARY KEY,
              workspace_id TEXT NOT NULL,
              request_id TEXT,
              content_hash TEXT,
              provider TEXT NOT NULL,
              event_type TEXT NOT NULL,
              delivery_status TEXT NOT NULL,
              campaign_id TEXT,
              template_id TEXT,
              event_timestamp TEXT NOT NULL,
              created_at TEXT NOT NULL
            )
            """
        )
    )
    ensure_column(conn, "email_analyses", "workspace_id", "TEXT DEFAULT 'default'")
    ensure_column(conn, "email_analyses", "tenant_id", "TEXT")
    ensure_column(conn, "email_analyses", "source_system", "TEXT")
    ensure_column(conn, "email_analyses", "analysis_mode", "TEXT")
    ensure_column(conn, "email_analyses", "campaign_id", "TEXT")
    ensure_column(conn, "email_analyses", "journey_id", "TEXT")
    ensure_column(conn, "email_analyses", "template_id", "TEXT")
    ensure_column(conn, "email_analyses", "locale", "TEXT")
    ensure_column(conn, "webhook_events", "workspace_id", "TEXT DEFAULT 'default'")
    ensure_column(conn, "webhook_events", "signature_status", "TEXT DEFAULT 'not_configured'")
    ensure_column(conn, "webhook_events", "campaign_id", "TEXT")
    ensure_column(conn, "webhook_events", "template_id", "TEXT")
    ensure_column(conn, "sample_imports", "workspace_id", "TEXT DEFAULT 'default'")
    ensure_column(conn, "sample_imports", "chunk_index", "INTEGER DEFAULT 0")
    ensure_column(conn, "sample_imports", "chunk_total", "INTEGER DEFAULT 1")
    ensure_column(conn, "sample_imports", "resume_token", "TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_email_analyses_created_at ON email_analyses(created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_email_analyses_gate_status ON email_analyses(gate_status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_email_analyses_workspace_id ON email_analyses(workspace_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_email_analyses_source_system ON email_analyses(source_system)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_email_analyses_campaign_id ON email_analyses(campaign_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_email_analyses_template_id ON email_analyses(template_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_webhook_events_last_seen ON webhook_events(last_seen_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_webhook_events_workspace_id ON webhook_events(workspace_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sample_imports_created_at ON sample_imports(created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sample_imports_workspace_id ON sample_imports(workspace_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_integration_field_mappings_updated_at ON integration_field_mappings(updated_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_email_findings_workspace_category ON email_findings(workspace_id, category)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_email_findings_rule_id ON email_findings(rule_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_email_outcomes_workspace_event ON email_outcomes(workspace_id, event_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_email_outcomes_request_id ON email_outcomes(request_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_email_outcomes_content_hash ON email_outcomes(content_hash)")
    record_schema_version(conn, ENTERPRISE_SCHEMA_VERSION)
    record_schema_version(conn, INTEGRATION_MAPPING_SCHEMA_VERSION)
    record_schema_version(conn, GOVERNANCE_POLICY_SCHEMA_VERSION)
    record_schema_version(conn, GOVERNANCE_ANALYTICS_SCHEMA_VERSION)


def ensure_column(conn, table: str, column: str, column_type: str) -> None:
    if uses_postgres():
        rows = conn.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = %s
            """,
            (table,),
        ).fetchall()
        columns = {row["column_name"] for row in rows}
    else:
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
        except Exception as error:
            if "duplicate column" not in str(error).lower():
                raise


def public_user(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "email": row["email"],
        "name": row["name"],
        "email_verified": bool(row["email_verified_at"]),
        "created_at": row["created_at"],
        "last_login_at": row["last_login_at"],
    }


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = execute(conn, "SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return public_user(row)


def get_user_by_email(email: str):
    with connect() as conn:
        return execute(conn, "SELECT * FROM users WHERE lower(email) = lower(?)", (email,)).fetchone()


def get_pending_signup_by_email(email: str):
    with connect() as conn:
        return execute(conn, "SELECT * FROM pending_signups WHERE lower(email) = lower(?)", (email.strip().lower(),)).fetchone()


def create_pending_signup(email: str, password: str, name: str = "") -> dict[str, Any]:
    clean_email = email.strip().lower()
    clean_name = name.strip() or clean_email.split("@")[0].replace(".", " ").title()
    now = utc_now()
    now_dt = datetime.now(timezone.utc)
    expires = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(timespec="seconds")
    code = verification_code()
    digest = token_digest(code)
    password_hash = generate_password_hash(password)
    with connect() as conn:
        existing = execute(conn, "SELECT * FROM users WHERE lower(email) = lower(?)", (clean_email,)).fetchone()
        if existing is not None:
            if existing["email_verified_at"]:
                return {"email": clean_email, "name": existing["name"], "token": None, "expires_at": None, "existing": True}
            if existing["verification_token"]:
                return {"email": clean_email, "name": existing["name"], "token": None, "expires_at": None, "existing": True, "already_sent": True}
            execute(
                conn,
                "UPDATE users SET verification_token = ? WHERE id = ?",
                (digest, existing["id"]),
            )
            return {"email": clean_email, "name": existing["name"], "token": code, "expires_at": expires, "existing": True}
        pending = execute(conn, "SELECT * FROM pending_signups WHERE lower(email) = lower(?)", (clean_email,)).fetchone()
        if pending is not None:
            pending_expires = datetime.fromisoformat(pending["expires_at"]) if pending["expires_at"] else now_dt
            if pending_expires >= now_dt:
                execute(
                    conn,
                    "UPDATE pending_signups SET name = ?, password_hash = ? WHERE email = ?",
                    (clean_name, password_hash, pending["email"]),
                )
                return {
                    "email": clean_email,
                    "name": clean_name,
                    "token": None,
                    "expires_at": pending["expires_at"],
                    "existing": False,
                    "already_sent": True,
                }
            execute(conn, "DELETE FROM pending_signups WHERE email = ?", (pending["email"],))
        execute(
            conn,
            """
            INSERT INTO pending_signups (email, name, password_hash, verification_token, expires_at, attempts, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (clean_email, clean_name, password_hash, digest, expires, 0, now),
        )
    return {"email": clean_email, "name": clean_name, "token": code, "expires_at": expires, "existing": False}


def create_user(email: str, password: str, name: str = "") -> dict[str, Any]:
    clean_email = email.strip().lower()
    clean_name = name.strip() or clean_email.split("@")[0].replace(".", " ").title()
    now = utc_now()
    verification_token = verification_code()
    verification_digest = token_digest(verification_token)
    with connect() as conn:
        if uses_postgres():
            row = conn.execute(
                """
                INSERT INTO users (email, name, password_hash, verification_token, created_at)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (clean_email, clean_name, generate_password_hash(password), verification_digest, now),
            ).fetchone()
            user_id = int(row["id"])
        else:
            cursor = execute(
                conn,
                "INSERT INTO users (email, name, password_hash, verification_token, created_at) VALUES (?, ?, ?, ?, ?)",
                (clean_email, clean_name, generate_password_hash(password), verification_digest, now),
            )
            user_id = int(cursor.lastrowid)
        execute(
            conn,
            "INSERT INTO workspaces (user_id, name, data, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, f"{clean_name}'s workspace", "{}", now, now),
        )
        row = execute(conn, "SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    user = public_user(row) or {}
    user["_verification_token"] = verification_token
    return user


def upsert_oauth_user(email: str, name: str = "", provider: str = "Google") -> dict[str, Any]:
    clean_email = email.strip().lower()
    clean_name = name.strip() or clean_email.split("@")[0].replace(".", " ").title()
    now = utc_now()
    password_hash = generate_password_hash(secrets.token_urlsafe(32))
    with connect() as conn:
        existing = execute(conn, "SELECT * FROM users WHERE lower(email) = lower(?)", (clean_email,)).fetchone()
        if existing is not None:
            execute(
                conn,
                """
                UPDATE users
                SET name = COALESCE(NULLIF(name, ''), ?),
                    email_verified_at = COALESCE(email_verified_at, ?),
                    verification_token = NULL,
                    last_login_at = ?
                WHERE id = ?
                """,
                (clean_name, now, now, existing["id"]),
            )
            row = execute(conn, "SELECT * FROM users WHERE id = ?", (existing["id"],)).fetchone()
        elif uses_postgres():
            row = conn.execute(
                """
                INSERT INTO users (email, name, password_hash, email_verified_at, verification_token, created_at, last_login_at)
                VALUES (%s, %s, %s, %s, NULL, %s, %s)
                RETURNING id
                """,
                (clean_email, clean_name, password_hash, now, now, now),
            ).fetchone()
            user_id = int(row["id"])
            execute(
                conn,
                "INSERT INTO workspaces (user_id, name, data, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, f"{clean_name}'s workspace", "{}", now, now),
            )
            row = execute(conn, "SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        else:
            cursor = execute(
                conn,
                """
                INSERT INTO users (email, name, password_hash, email_verified_at, verification_token, created_at, last_login_at)
                VALUES (?, ?, ?, ?, NULL, ?, ?)
                """,
                (clean_email, clean_name, password_hash, now, now, now),
            )
            user_id = int(cursor.lastrowid)
            execute(
                conn,
                "INSERT INTO workspaces (user_id, name, data, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, f"{clean_name}'s workspace", "{}", now, now),
            )
            row = execute(conn, "SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        execute(conn, "DELETE FROM pending_signups WHERE lower(email) = lower(?)", (clean_email,))
        execute(conn, "INSERT INTO audit_events (user_id, event_type, payload, created_at) VALUES (?, ?, ?, ?)", (row["id"], "oauth_login", json.dumps({"provider": provider}), now))
    return public_user(row) or {}


def authenticate_user(email: str, password: str) -> dict[str, Any] | None:
    row = get_user_by_email(email)
    if row is None or not check_password_hash(row["password_hash"], password):
        return None
    if not row["email_verified_at"]:
        return None
    now = utc_now()
    with connect() as conn:
        execute(conn, "UPDATE users SET last_login_at = ? WHERE id = ?", (now, row["id"]))
        updated = execute(conn, "SELECT * FROM users WHERE id = ?", (row["id"],)).fetchone()
    return public_user(updated)


def needs_email_verification(email: str, password: str) -> bool:
    clean_email = email.strip().lower()
    if not clean_email or not password:
        return False
    row = get_user_by_email(clean_email)
    if row is not None:
        return bool(not row["email_verified_at"] and check_password_hash(row["password_hash"], password))
    pending = get_pending_signup_by_email(clean_email)
    return bool(pending is not None and check_password_hash(pending["password_hash"], password))


def get_verification_token(user_id: int) -> str | None:
    # Verification tokens are stored hashed and cannot be recovered after issue.
    return None


def verify_email_token(token: str, email: str = "") -> dict[str, Any] | None:
    clean = normalize_verification_code(token)
    if not clean:
        return None
    clean_email = email.strip().lower()
    if clean_email:
        created_user: dict[str, Any] | None = None
        created_user_id: int | None = None
        with connect() as conn:
            pending = execute(conn, "SELECT * FROM pending_signups WHERE lower(email) = lower(?)", (clean_email,)).fetchone()
            if pending is not None:
                now_dt = datetime.now(timezone.utc)
                expires = datetime.fromisoformat(pending["expires_at"]) if pending["expires_at"] else now_dt
                if expires < now_dt or int(pending["attempts"] or 0) >= 8:
                    execute(conn, "DELETE FROM pending_signups WHERE email = ?", (pending["email"],))
                    return None
                if not token_matches(pending["verification_token"], clean):
                    execute(conn, "UPDATE pending_signups SET attempts = attempts + 1 WHERE email = ?", (pending["email"],))
                    return None
                existing = execute(conn, "SELECT * FROM users WHERE lower(email) = lower(?)", (clean_email,)).fetchone()
                if existing is not None:
                    execute(conn, "DELETE FROM pending_signups WHERE email = ?", (pending["email"],))
                    return None
                now = utc_now()
                if uses_postgres():
                    inserted = conn.execute(
                        """
                        INSERT INTO users (email, name, password_hash, email_verified_at, verification_token, created_at, last_login_at)
                        VALUES (%s, %s, %s, %s, NULL, %s, %s)
                        RETURNING id
                        """,
                        (pending["email"], pending["name"], pending["password_hash"], now, pending["created_at"], now),
                    ).fetchone()
                    user_id = int(inserted["id"])
                else:
                    cursor = execute(
                        conn,
                        """
                        INSERT INTO users (email, name, password_hash, email_verified_at, verification_token, created_at, last_login_at)
                        VALUES (?, ?, ?, ?, NULL, ?, ?)
                        """,
                        (pending["email"], pending["name"], pending["password_hash"], now, pending["created_at"], now),
                    )
                    user_id = int(cursor.lastrowid)
                execute(
                    conn,
                    "INSERT INTO workspaces (user_id, name, data, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (user_id, f"{pending['name']}'s workspace", "{}", now, now),
                )
                execute(conn, "DELETE FROM pending_signups WHERE email = ?", (pending["email"],))
                updated = execute(conn, "SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
                created_user = public_user(updated)
                created_user_id = int(user_id) if created_user else None
        if created_user and created_user_id:
            log_event(created_user_id, "signup", {})
            log_event(created_user_id, "email_verified", {})
            return created_user
    with connect() as conn:
        row = execute(
            conn,
            "SELECT * FROM users WHERE lower(email) = lower(?) AND verification_token = ?",
            (clean_email, token_digest(clean)),
        ).fetchone()
        if row is None:
            return None
        now = utc_now()
        execute(
            conn,
            "UPDATE users SET email_verified_at = ?, verification_token = NULL WHERE id = ?",
            (now, row["id"]),
        )
        updated = execute(conn, "SELECT * FROM users WHERE id = ?", (row["id"],)).fetchone()
    log_event(int(row["id"]), "email_verified", {})
    return public_user(updated)


def create_password_reset(email: str) -> dict[str, Any] | None:
    row = get_user_by_email(email)
    if row is None:
        return None
    token = secrets.token_urlsafe(24)
    digest = token_digest(token)
    expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(timespec="seconds")
    with connect() as conn:
        execute(
            conn,
            "UPDATE users SET reset_token = ?, reset_expires_at = ? WHERE id = ?",
            (digest, expires, row["id"]),
        )
    log_event(int(row["id"]), "password_reset_requested", {})
    return {"token": token, "expires_at": expires}


def reset_password(token: str, password: str) -> dict[str, Any] | None:
    clean = token.strip()
    if not clean:
        return None
    now = datetime.now(timezone.utc)
    with connect() as conn:
        row = execute(
            conn,
            "SELECT * FROM users WHERE reset_token = ?",
            (token_digest(clean),),
        ).fetchone()
        if row is None:
            return None
        expires = datetime.fromisoformat(row["reset_expires_at"]) if row["reset_expires_at"] else now
        if expires < now:
            return None
        execute(
            conn,
            "UPDATE users SET password_hash = ?, reset_token = NULL, reset_expires_at = NULL, session_version = COALESCE(session_version, 0) + 1 WHERE id = ?",
            (generate_password_hash(password), row["id"]),
        )
        updated = execute(conn, "SELECT * FROM users WHERE id = ?", (row["id"],)).fetchone()
    log_event(int(row["id"]), "password_reset_completed", {})
    return public_user(updated)


def get_workspace(user_id: int) -> dict[str, Any]:
    now = utc_now()
    with connect() as conn:
        row = execute(conn, "SELECT * FROM workspaces WHERE user_id = ?", (user_id,)).fetchone()
        if row is None:
            execute(
                conn,
                "INSERT INTO workspaces (user_id, name, data, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, "Personal workspace", "{}", now, now),
            )
            row = execute(conn, "SELECT * FROM workspaces WHERE user_id = ?", (user_id,)).fetchone()
    data = json.loads(row["data"] or "{}")
    return {
        "id": row["id"],
        "name": row["name"],
        "data": data,
        "updated_at": row["updated_at"],
    }


def save_workspace(user_id: int, data: dict[str, Any], name: str | None = None) -> dict[str, Any]:
    now = utc_now()
    current = get_workspace(user_id)
    workspace_name = (name or current["name"] or "Personal workspace").strip()
    serialized = json.dumps(data, separators=(",", ":"), sort_keys=True)
    max_bytes = int(os.getenv("TEXTTRAITS_MAX_WORKSPACE_BYTES", "500000"))
    if len(serialized.encode("utf-8")) > max_bytes:
        raise ValueError(f"Workspace data is too large. Keep sync payloads under {max_bytes} bytes.")
    with connect() as conn:
        execute(
            conn,
            "UPDATE workspaces SET name = ?, data = ?, updated_at = ? WHERE user_id = ?",
            (workspace_name, serialized, now, user_id),
        )
    return get_workspace(user_id)


def log_event(user_id: int | None, event_type: str, payload: dict[str, Any] | None = None) -> None:
    clean_payload = scrub_payload(payload or {})
    clean_event_type = SAFE_EVENT_TYPE_RE.sub("_", str(event_type or "client_event")).strip("_")[:80] or "client_event"
    with connect() as conn:
        execute(
            conn,
            "INSERT INTO audit_events (user_id, event_type, payload, created_at) VALUES (?, ?, ?, ?)",
            (user_id, clean_event_type, json.dumps(clean_payload, separators=(",", ":"))[:12000], utc_now()),
        )


def recent_events(user_id: int, limit: int = 25) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = execute(
            conn,
            "SELECT event_type, payload, created_at FROM audit_events WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [
        {
            "event_type": row["event_type"],
            "payload": json.loads(row["payload"] or "{}"),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def analysis_summary_from_row(row) -> dict[str, Any]:
    return {
        "workspace_id": row["workspace_id"] if "workspace_id" in row.keys() else "default",
        "request_id": row["request_id"],
        "content_hash": row["content_hash"],
        "score": int(row["score"] or 0),
        "gate": {
            "status": row["gate_status"],
            "send_ready": bool(row["send_ready"]),
            "route": row["route"],
            "highest_severity": row["highest_severity"],
        },
        "finding_count": int(row["finding_count"] or 0),
        "highest_severity": row["highest_severity"],
        "created_at": row["created_at"],
        "source": row["source"],
        "tenant_id": row["tenant_id"] if "tenant_id" in row.keys() else "",
        "source_system": row["source_system"] if "source_system" in row.keys() else "",
        "analysis_mode": row["analysis_mode"] if "analysis_mode" in row.keys() else "",
        "campaign_id": row["campaign_id"] if "campaign_id" in row.keys() else "",
        "journey_id": row["journey_id"] if "journey_id" in row.keys() else "",
        "template_id": row["template_id"] if "template_id" in row.keys() else "",
        "locale": row["locale"] if "locale" in row.keys() else "",
        "policy_bundle_version": row["policy_bundle_version"],
        "model_version": row["model_version"],
    }


def clean_workspace_id(workspace_id: str | None = None) -> str:
    return str(workspace_id or "default").strip()[:120] or "default"


def clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(number, maximum))


def normalize_governance_policy(policy: dict[str, Any] | None = None, workspace_id: str = "default") -> dict[str, Any]:
    raw = {**DEFAULT_GOVERNANCE_POLICY, **(policy or {})}
    storage_mode = str(raw.get("content_storage_mode") or DEFAULT_GOVERNANCE_POLICY["content_storage_mode"]).strip().lower()
    if storage_mode not in {"hash_only", "metadata_only"}:
        storage_mode = DEFAULT_GOVERNANCE_POLICY["content_storage_mode"]
    policy_environment = str(raw.get("policy_environment") or "production").strip().lower()
    if policy_environment not in {"sandbox", "staging", "production"}:
        policy_environment = "production"
    raw_modes = raw.get("rule_family_modes") if isinstance(raw.get("rule_family_modes"), dict) else {}
    valid_modes = {"fail_open", "review", "fail_closed"}
    rule_family_modes = {}
    for category, default_mode in DEFAULT_RULE_FAMILY_MODES.items():
        mode = str(raw_modes.get(category) or default_mode).strip().lower()
        rule_family_modes[category] = mode if mode in valid_modes else default_mode
    return {
        "workspace_id": clean_workspace_id(workspace_id or raw.get("workspace_id")),
        "version": GOVERNANCE_POLICY_SCHEMA_VERSION,
        "policy_environment": policy_environment,
        "retention_days": clamp_int(raw.get("retention_days"), DEFAULT_GOVERNANCE_POLICY["retention_days"], 30, 3650),
        "webhook_retention_days": clamp_int(raw.get("webhook_retention_days"), DEFAULT_GOVERNANCE_POLICY["webhook_retention_days"], 30, 3650),
        "webhook_dedupe_window_days": clamp_int(raw.get("webhook_dedupe_window_days"), DEFAULT_GOVERNANCE_POLICY["webhook_dedupe_window_days"], 1, 365),
        "min_ready_score": clamp_int(raw.get("min_ready_score"), DEFAULT_GOVERNANCE_POLICY["min_ready_score"], 0, 100),
        "high_severity_requires_review": bool(raw.get("high_severity_requires_review", True)),
        "rule_family_modes": rule_family_modes,
        "content_storage_mode": storage_mode,
        "sample_import_limit": clamp_int(raw.get("sample_import_limit"), DEFAULT_GOVERNANCE_POLICY["sample_import_limit"], 1, 100),
        "send_path_timeout_ms": clamp_int(raw.get("send_path_timeout_ms"), DEFAULT_GOVERNANCE_POLICY["send_path_timeout_ms"], 50, 10000),
        "idempotency_window_seconds": clamp_int(raw.get("idempotency_window_seconds"), DEFAULT_GOVERNANCE_POLICY["idempotency_window_seconds"], 60, 86400),
        "updated_at": str(raw.get("updated_at") or utc_now()),
    }


def get_governance_policy(workspace_id: str = "default") -> dict[str, Any]:
    workspace_clean = clean_workspace_id(workspace_id)
    with connect() as conn:
        row = execute(
            conn,
            "SELECT policy_json, updated_at FROM governance_policies WHERE workspace_id = ?",
            (workspace_clean,),
        ).fetchone()
    if not row:
        return normalize_governance_policy(workspace_id=workspace_clean)
    try:
        saved = json.loads(row["policy_json"] or "{}")
    except json.JSONDecodeError:
        saved = {}
    return normalize_governance_policy({**saved, "updated_at": row["updated_at"]}, workspace_clean)


def save_governance_policy(workspace_id: str, policy: dict[str, Any]) -> dict[str, Any]:
    workspace_clean = clean_workspace_id(workspace_id)
    normalized = normalize_governance_policy(policy, workspace_clean)
    normalized["updated_at"] = utc_now()
    with connect() as conn:
        execute(
            conn,
            """
            INSERT INTO governance_policies (workspace_id, policy_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(workspace_id)
            DO UPDATE SET policy_json = excluded.policy_json, updated_at = excluded.updated_at
            """,
            (
                workspace_clean,
                json.dumps(normalized, separators=(",", ":"), sort_keys=True),
                normalized["updated_at"],
            ),
        )
        history_id = f"{workspace_clean}:{normalized['policy_environment']}:{normalized['updated_at']}"
        execute(
            conn,
            """
            INSERT INTO policy_bundle_versions (id, workspace_id, environment, policy_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO NOTHING
            """,
            (
                history_id[:240],
                workspace_clean,
                normalized["policy_environment"],
                json.dumps(normalized, separators=(",", ":"), sort_keys=True),
                normalized["updated_at"],
            ),
        )
    return normalized


def policy_bundle_history(workspace_id: str = "default", limit: int = 20) -> list[dict[str, Any]]:
    workspace_clean = clean_workspace_id(workspace_id)
    clean_limit = max(1, min(int(limit or 20), 100))
    with connect() as conn:
        rows = execute(
            conn,
            """
            SELECT workspace_id, environment, policy_json, created_at
            FROM policy_bundle_versions
            WHERE workspace_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (workspace_clean, clean_limit),
        ).fetchall()
    return [
        {
            "workspace_id": row["workspace_id"],
            "environment": row["environment"],
            "policy": json.loads(row["policy_json"] or "{}"),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def analysis_enterprise_context(analysis: dict[str, Any]) -> dict[str, str]:
    context = analysis.get("input", {}).get("enterprise_context")
    if not isinstance(context, dict):
        context = {}
    return {
        "tenant_id": str(context.get("tenant_id") or "")[:120],
        "source_system": SAFE_EVENT_TYPE_RE.sub("_", str(context.get("source_system") or analysis.get("input", {}).get("channel") or "")).strip("_").lower()[:120],
        "analysis_mode": SAFE_EVENT_TYPE_RE.sub("_", str(context.get("analysis_mode") or analysis.get("input", {}).get("channel") or "direct_api")).strip("_").lower()[:80],
        "campaign_id": str(context.get("campaign_id") or "")[:160],
        "journey_id": str(context.get("journey_id") or "")[:160],
        "template_id": str(context.get("template_id") or "")[:160],
        "locale": str(context.get("locale") or "")[:32],
    }


def save_email_findings(conn, analysis: dict[str, Any], workspace_id: str, context: dict[str, str]) -> None:
    request_id = str(analysis.get("request_id") or "")
    execute(conn, "DELETE FROM email_findings WHERE request_id = ?", (request_id,))
    content_hash_value = str(analysis.get("content_hash") or "")
    created_at = str(analysis.get("created_at") or utc_now())
    for index, item in enumerate(analysis.get("findings") or []):
        finding_id = f"{request_id}:{item.get('id') or index}"[:240]
        execute(
            conn,
            """
            INSERT INTO email_findings (
              id, workspace_id, request_id, content_hash, rule_id, category, severity, title,
              remediation, evidence_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id)
            DO UPDATE SET
              workspace_id = excluded.workspace_id,
              content_hash = excluded.content_hash,
              rule_id = excluded.rule_id,
              category = excluded.category,
              severity = excluded.severity,
              title = excluded.title,
              remediation = excluded.remediation,
              evidence_json = excluded.evidence_json,
              created_at = excluded.created_at
            """,
            (
                finding_id,
                workspace_id,
                request_id,
                content_hash_value,
                str(item.get("id") or "")[:120],
                str(item.get("category") or "unknown")[:80],
                str(item.get("severity") or "info")[:40],
                str(item.get("title") or "")[:240],
                str(item.get("remediation") or "")[:1000],
                json.dumps(scrub_payload(item.get("evidence") or []), separators=(",", ":"), sort_keys=True)[:12000],
                created_at,
            ),
        )


def save_email_analysis(analysis: dict[str, Any], source: str = "direct_api", workspace_id: str = "default") -> dict[str, Any]:
    gate = analysis.get("policy", {}).get("gate", {})
    request_id = str(analysis.get("request_id") or "").strip()
    if not request_id:
        raise ValueError("Email analysis is missing request_id.")
    source_clean = SAFE_EVENT_TYPE_RE.sub("_", str(source or "direct_api")).strip("_")[:80] or "direct_api"
    workspace_clean = clean_workspace_id(workspace_id or analysis.get("input", {}).get("workspace_id") or analysis.get("workspace_id"))
    context = analysis_enterprise_context(analysis)
    record = {
        "workspace_id": workspace_clean,
        "request_id": request_id,
        "content_hash": str(analysis.get("content_hash") or ""),
        "source": source_clean,
        **context,
        "policy_bundle_version": str(analysis.get("policy", {}).get("bundle_version") or ""),
        "model_version": str(analysis.get("model", {}).get("version") or ""),
        "gate_status": str(gate.get("status") or "unknown"),
        "send_ready": 1 if gate.get("send_ready") else 0,
        "route": str(gate.get("route") or ""),
        "highest_severity": str(gate.get("highest_severity") or "none"),
        "score": int(analysis.get("scores", {}).get("overall") or 0),
        "finding_count": len(analysis.get("findings") or []),
        "analysis_json": json.dumps(analysis, separators=(",", ":"), sort_keys=True),
        "created_at": str(analysis.get("created_at") or utc_now()),
    }
    with connect() as conn:
        execute(
            conn,
            """
            INSERT INTO email_analyses (
              workspace_id, request_id, content_hash, source, tenant_id, source_system, analysis_mode,
              campaign_id, journey_id, template_id, locale, policy_bundle_version, model_version,
              gate_status, send_ready, route, highest_severity, score, finding_count,
              analysis_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(request_id)
            DO UPDATE SET
              workspace_id = excluded.workspace_id,
              content_hash = excluded.content_hash,
              source = excluded.source,
              tenant_id = excluded.tenant_id,
              source_system = excluded.source_system,
              analysis_mode = excluded.analysis_mode,
              campaign_id = excluded.campaign_id,
              journey_id = excluded.journey_id,
              template_id = excluded.template_id,
              locale = excluded.locale,
              policy_bundle_version = excluded.policy_bundle_version,
              model_version = excluded.model_version,
              gate_status = excluded.gate_status,
              send_ready = excluded.send_ready,
              route = excluded.route,
              highest_severity = excluded.highest_severity,
              score = excluded.score,
              finding_count = excluded.finding_count,
              analysis_json = excluded.analysis_json,
              created_at = excluded.created_at
            """,
            (
                record["workspace_id"],
                record["request_id"],
                record["content_hash"],
                record["source"],
                record["tenant_id"],
                record["source_system"],
                record["analysis_mode"],
                record["campaign_id"],
                record["journey_id"],
                record["template_id"],
                record["locale"],
                record["policy_bundle_version"],
                record["model_version"],
                record["gate_status"],
                record["send_ready"],
                record["route"],
                record["highest_severity"],
                record["score"],
                record["finding_count"],
                record["analysis_json"],
                record["created_at"],
            ),
        )
        save_email_findings(conn, analysis, workspace_clean, context)
    return {
        "workspace_id": record["workspace_id"],
        "request_id": record["request_id"],
        "content_hash": record["content_hash"],
        "score": record["score"],
        "gate": {
            "status": record["gate_status"],
            "send_ready": bool(record["send_ready"]),
            "route": record["route"],
            "highest_severity": record["highest_severity"],
        },
        "finding_count": record["finding_count"],
        "highest_severity": record["highest_severity"],
        "created_at": record["created_at"],
        "source": record["source"],
        "tenant_id": record["tenant_id"],
        "source_system": record["source_system"],
        "analysis_mode": record["analysis_mode"],
        "campaign_id": record["campaign_id"],
        "journey_id": record["journey_id"],
        "template_id": record["template_id"],
        "locale": record["locale"],
        "policy_bundle_version": record["policy_bundle_version"],
        "model_version": record["model_version"],
    }


def recent_email_analyses(limit: int = 20, workspace_id: str = "default") -> list[dict[str, Any]]:
    clean_limit = max(1, min(int(limit or 20), 500))
    workspace_clean = clean_workspace_id(workspace_id)
    with connect() as conn:
        rows = execute(
            conn,
            """
            SELECT workspace_id, request_id, content_hash, source, tenant_id, source_system, analysis_mode,
                   campaign_id, journey_id, template_id, locale, policy_bundle_version, model_version,
                   gate_status, send_ready, route, highest_severity, score, finding_count, created_at
            FROM email_analyses
            WHERE workspace_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (workspace_clean, clean_limit),
        ).fetchall()
    return [analysis_summary_from_row(row) for row in rows]


def webhook_event_from_row(row) -> dict[str, Any]:
    return {
        "workspace_id": row["workspace_id"] if "workspace_id" in row.keys() else "default",
        "dedupe_key": row["dedupe_key"],
        "provider": row["provider"],
        "event_type": row["event_type"],
        "request_id": row["request_id"] or "",
        "content_hash": row["content_hash"] or "",
        "delivery_status": row["delivery_status"],
        "signature_status": row["signature_status"] if "signature_status" in row.keys() else "not_configured",
        "campaign_id": row["campaign_id"] if "campaign_id" in row.keys() else "",
        "template_id": row["template_id"] if "template_id" in row.keys() else "",
        "first_seen_at": row["first_seen_at"],
        "last_seen_at": row["last_seen_at"],
        "seen_count": int(row["seen_count"] or 0),
    }


def parse_utc_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def upsert_webhook_event(
    dedupe_key: str,
    record: dict[str, Any],
    raw_payload: dict[str, Any] | None = None,
    workspace_id: str = "default",
    dedupe_window_days: int | None = None,
) -> tuple[dict[str, Any], bool]:
    clean_key = str(dedupe_key or "").strip()[:180]
    if not clean_key:
        raise ValueError("Webhook event is missing a dedupe key.")
    workspace_clean = clean_workspace_id(workspace_id or record.get("workspace_id"))
    storage_key = clean_key if workspace_clean == "default" else f"{workspace_clean}:{clean_key}"[:180]
    event_json = json.dumps(scrub_payload(raw_payload or record), separators=(",", ":"), sort_keys=True)[:12000]
    signature_status = str(record.get("signature_status") or "not_configured")[:80]
    campaign_id = str(record.get("campaign_id") or (raw_payload or {}).get("campaign_id") or "")[:160]
    template_id = str(record.get("template_id") or (raw_payload or {}).get("template_id") or "")[:160]
    with connect() as conn:
        existing = execute(conn, "SELECT * FROM webhook_events WHERE workspace_id = ? AND dedupe_key = ?", (workspace_clean, storage_key)).fetchone()
        if existing is not None:
            last_seen = utc_now()
            existing_last_seen = parse_utc_timestamp(existing["last_seen_at"])
            window_days = clamp_int(dedupe_window_days, 30, 1, 365) if dedupe_window_days else None
            outside_window = bool(
                window_days
                and existing_last_seen
                and datetime.now(timezone.utc) - existing_last_seen > timedelta(days=window_days)
            )
            if outside_window:
                execute(
                    conn,
                    """
                    UPDATE webhook_events
                    SET provider = ?, event_type = ?, request_id = ?, content_hash = ?, delivery_status = ?,
                        signature_status = ?, campaign_id = ?, template_id = ?,
                        event_json = ?, first_seen_at = ?, last_seen_at = ?, seen_count = 1
                    WHERE workspace_id = ? AND dedupe_key = ?
                    """,
                    (
                        str(record.get("provider") or "")[:80],
                        str(record.get("event_type") or "")[:80],
                        str(record.get("request_id") or "")[:120],
                        str(record.get("content_hash") or "")[:120],
                        str(record.get("delivery_status") or "received")[:80],
                        signature_status,
                        campaign_id,
                        template_id,
                        event_json,
                        last_seen,
                        last_seen,
                        workspace_clean,
                        storage_key,
                    ),
                )
                updated = execute(conn, "SELECT * FROM webhook_events WHERE workspace_id = ? AND dedupe_key = ?", (workspace_clean, storage_key)).fetchone()
                return webhook_event_from_row(updated), False
            execute(
                conn,
                """
                UPDATE webhook_events
                SET last_seen_at = ?, seen_count = seen_count + 1, event_json = ?, signature_status = ?
                WHERE workspace_id = ? AND dedupe_key = ?
                """,
                (last_seen, event_json, signature_status, workspace_clean, storage_key),
            )
            updated = execute(conn, "SELECT * FROM webhook_events WHERE workspace_id = ? AND dedupe_key = ?", (workspace_clean, storage_key)).fetchone()
            return webhook_event_from_row(updated), True
        execute(
            conn,
            """
            INSERT INTO webhook_events (
              workspace_id, dedupe_key, provider, event_type, request_id, content_hash, delivery_status,
              signature_status, campaign_id, template_id, event_json, first_seen_at, last_seen_at, seen_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workspace_clean,
                storage_key,
                str(record.get("provider") or "")[:80],
                str(record.get("event_type") or "")[:80],
                str(record.get("request_id") or "")[:120],
                str(record.get("content_hash") or "")[:120],
                str(record.get("delivery_status") or "received")[:80],
                signature_status,
                campaign_id,
                template_id,
                event_json,
                str(record.get("first_seen_at") or utc_now()),
                str(record.get("last_seen_at") or utc_now()),
                int(record.get("seen_count") or 1),
            ),
        )
        created = execute(conn, "SELECT * FROM webhook_events WHERE workspace_id = ? AND dedupe_key = ?", (workspace_clean, storage_key)).fetchone()
    return webhook_event_from_row(created), False


def recent_webhook_events(limit: int = 20, workspace_id: str = "default") -> list[dict[str, Any]]:
    clean_limit = max(1, min(int(limit or 20), 200))
    workspace_clean = clean_workspace_id(workspace_id)
    with connect() as conn:
        rows = execute(
            conn,
            "SELECT * FROM webhook_events WHERE workspace_id = ? ORDER BY last_seen_at DESC LIMIT ?",
            (workspace_clean, clean_limit),
        ).fetchall()
    return [webhook_event_from_row(row) for row in rows]


def normalize_outcome_event_type(event_type: str, delivery_status: str = "") -> str:
    clean = SAFE_EVENT_TYPE_RE.sub("_", str(event_type or delivery_status or "received")).strip("_").lower()
    aliases = {
        "delivered": "delivered",
        "delivery": "delivered",
        "processed": "processed",
        "open": "opened",
        "opened": "opened",
        "click": "clicked",
        "clicked": "clicked",
        "bounce": "bounced",
        "bounced": "bounced",
        "dropped": "suppressed",
        "suppressed": "suppressed",
        "spamreport": "complained",
        "spam_report": "complained",
        "complaint": "complained",
        "complained": "complained",
        "unsubscribe": "unsubscribed",
        "unsubscribed": "unsubscribed",
    }
    return aliases.get(clean, clean or "received")


def save_email_outcome(record: dict[str, Any], workspace_id: str = "default") -> dict[str, Any]:
    workspace_clean = clean_workspace_id(workspace_id or record.get("workspace_id"))
    event_type = normalize_outcome_event_type(str(record.get("event_type") or ""), str(record.get("delivery_status") or ""))
    request_id = str(record.get("request_id") or "")[:120]
    content_hash_value = str(record.get("content_hash") or "")[:120]
    provider = SAFE_EVENT_TYPE_RE.sub("_", str(record.get("provider") or "unknown")).strip("_").lower()[:80] or "unknown"
    campaign_id = str(record.get("campaign_id") or "")[:160]
    template_id = str(record.get("template_id") or "")[:160]
    timestamp = str(record.get("event_timestamp") or record.get("last_seen_at") or utc_now())
    outcome_id_source = "|".join([workspace_clean, request_id, content_hash_value, provider, event_type, campaign_id, template_id, timestamp])
    outcome_id = "outcome:" + hashlib.sha256(outcome_id_source.encode("utf-8")).hexdigest()
    with connect() as conn:
        execute(
            conn,
            """
            INSERT INTO email_outcomes (
              id, workspace_id, request_id, content_hash, provider, event_type, delivery_status,
              campaign_id, template_id, event_timestamp, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id)
            DO UPDATE SET
              request_id = excluded.request_id,
              content_hash = excluded.content_hash,
              delivery_status = excluded.delivery_status,
              event_timestamp = excluded.event_timestamp
            """,
            (
                outcome_id,
                workspace_clean,
                request_id,
                content_hash_value,
                provider,
                event_type,
                str(record.get("delivery_status") or event_type)[:80],
                campaign_id,
                template_id,
                timestamp,
                utc_now(),
            ),
        )
    return {
        "id": outcome_id,
        "workspace_id": workspace_clean,
        "request_id": request_id,
        "content_hash": content_hash_value,
        "provider": provider,
        "event_type": event_type,
        "delivery_status": str(record.get("delivery_status") or event_type)[:80],
        "campaign_id": campaign_id,
        "template_id": template_id,
        "event_timestamp": timestamp,
    }


def recent_email_outcomes(limit: int = 50, workspace_id: str = "default") -> list[dict[str, Any]]:
    clean_limit = max(1, min(int(limit or 50), 500))
    workspace_clean = clean_workspace_id(workspace_id)
    with connect() as conn:
        rows = execute(
            conn,
            """
            SELECT id, workspace_id, request_id, content_hash, provider, event_type, delivery_status,
                   campaign_id, template_id, event_timestamp, created_at
            FROM email_outcomes
            WHERE workspace_id = ?
            ORDER BY event_timestamp DESC
            LIMIT ?
            """,
            (workspace_clean, clean_limit),
        ).fetchall()
    return [dict(row) for row in rows]


def joined_outcomes(limit: int = 50, workspace_id: str = "default") -> list[dict[str, Any]]:
    clean_limit = max(1, min(int(limit or 50), 500))
    workspace_clean = clean_workspace_id(workspace_id)
    with connect() as conn:
        rows = execute(
            conn,
            """
            SELECT o.id, o.provider, o.event_type, o.delivery_status, o.request_id, o.content_hash,
                   o.campaign_id AS outcome_campaign_id, o.template_id AS outcome_template_id,
                   o.event_timestamp, a.score, a.gate_status, a.source_system, a.campaign_id, a.template_id
            FROM email_outcomes o
            LEFT JOIN email_analyses a
              ON a.workspace_id = o.workspace_id
             AND ((o.request_id <> '' AND a.request_id = o.request_id)
               OR (o.content_hash <> '' AND a.content_hash = o.content_hash))
            WHERE o.workspace_id = ?
            ORDER BY o.event_timestamp DESC
            LIMIT ?
            """,
            (workspace_clean, clean_limit),
        ).fetchall()
    return [dict(row) for row in rows]


def save_sample_import(summary: dict[str, Any], workspace_id: str = "default") -> dict[str, Any]:
    import_id = str(summary.get("import_id") or "").strip()
    if not import_id:
        raise ValueError("Sample import is missing import_id.")
    workspace_clean = clean_workspace_id(workspace_id or summary.get("workspace_id"))
    created_at = str(summary.get("created_at") or utc_now())
    chunk_index = clamp_int(summary.get("chunk_index"), 0, 0, 100000)
    chunk_total = clamp_int(summary.get("chunk_total"), 1, 1, 100000)
    resume_token = str(summary.get("resume_token") or "")[:180]
    clean_summary = scrub_payload(
        {
            **summary,
            "workspace_id": workspace_clean,
            "created_at": created_at,
            "chunk_index": chunk_index,
            "chunk_total": chunk_total,
            "resume_token": resume_token,
            "resume_available": bool(resume_token),
            "resume_digest": token_digest(resume_token) if resume_token else "",
        }
    )
    storage_import_id = import_id if workspace_clean == "default" else f"{workspace_clean}:{import_id}"[:180]
    with connect() as conn:
        execute(
            conn,
            """
            INSERT INTO sample_imports (workspace_id, import_id, summary_json, created_at, chunk_index, chunk_total, resume_token)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(import_id)
            DO UPDATE SET
              workspace_id = excluded.workspace_id,
              summary_json = excluded.summary_json,
              created_at = excluded.created_at,
              chunk_index = excluded.chunk_index,
              chunk_total = excluded.chunk_total,
              resume_token = excluded.resume_token
            """,
            (workspace_clean, storage_import_id, json.dumps(clean_summary, separators=(",", ":"), sort_keys=True), created_at, chunk_index, chunk_total, resume_token),
        )
    return clean_summary


def recent_sample_imports(limit: int = 10, workspace_id: str = "default") -> list[dict[str, Any]]:
    clean_limit = max(1, min(int(limit or 10), 100))
    workspace_clean = clean_workspace_id(workspace_id)
    with connect() as conn:
        rows = execute(
            conn,
            "SELECT summary_json FROM sample_imports WHERE workspace_id = ? ORDER BY created_at DESC LIMIT ?",
            (workspace_clean, clean_limit),
        ).fetchall()
    return [json.loads(row["summary_json"] or "{}") for row in rows]


def count_by(items: list[dict[str, Any]], key_fn) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        key = str(key_fn(item) or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return counts


def query_counts(workspace_id: str, statement: str, limit: int = 20) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = execute(conn, statement, (clean_workspace_id(workspace_id), max(1, min(int(limit or 20), 100)))).fetchall()
    normalized = []
    for row in rows:
        item = dict(row)
        if "average_score" in item and item["average_score"] is not None:
            item["average_score"] = round(float(item["average_score"]), 1)
        normalized.append(item)
    return normalized


def top_failing_rule_packs(workspace_id: str = "default", limit: int = 12) -> list[dict[str, Any]]:
    return query_counts(
        workspace_id,
        """
        SELECT category, rule_id, severity, COUNT(*) AS count
        FROM email_findings
        WHERE workspace_id = ?
        GROUP BY category, rule_id, severity
        ORDER BY count DESC, category ASC
        LIMIT ?
        """,
        limit,
    )


def risky_templates(workspace_id: str = "default", limit: int = 12) -> list[dict[str, Any]]:
    return query_counts(
        workspace_id,
        """
        SELECT COALESCE(NULLIF(template_id, ''), 'unknown') AS template_id,
               COALESCE(NULLIF(campaign_id, ''), 'unknown') AS campaign_id,
               COUNT(*) AS analysis_count,
               AVG(score) AS average_score,
               SUM(CASE WHEN gate_status <> 'ready' THEN 1 ELSE 0 END) AS review_or_block_count
        FROM email_analyses
        WHERE workspace_id = ?
        GROUP BY COALESCE(NULLIF(template_id, ''), 'unknown'), COALESCE(NULLIF(campaign_id, ''), 'unknown')
        HAVING COUNT(*) > 0
        ORDER BY review_or_block_count DESC, average_score ASC
        LIMIT ?
        """,
        limit,
    )


def trend_by_source_system(workspace_id: str = "default", limit: int = 20) -> list[dict[str, Any]]:
    return query_counts(
        workspace_id,
        """
        SELECT COALESCE(NULLIF(source_system, ''), source) AS source_system,
               gate_status,
               COUNT(*) AS count,
               AVG(score) AS average_score
        FROM email_analyses
        WHERE workspace_id = ?
        GROUP BY COALESCE(NULLIF(source_system, ''), source), gate_status
        ORDER BY source_system ASC, count DESC
        LIMIT ?
        """,
        limit,
    )


def enterprise_governance_snapshot(limit: int = 20, workspace_id: str = "default") -> dict[str, Any]:
    workspace_clean = clean_workspace_id(workspace_id)
    analyses = recent_email_analyses(limit=500, workspace_id=workspace_clean)
    webhook_events = recent_webhook_events(limit=limit, workspace_id=workspace_clean)
    outcomes = recent_email_outcomes(limit=limit, workspace_id=workspace_clean)
    sample_imports = recent_sample_imports(10, workspace_id=workspace_clean)
    total = len(analyses)
    gate_counts = {"ready": 0, "needs_review": 0, "blocked": 0}
    severity_counts: dict[str, int] = {}
    for item in analyses:
        gate_status = item["gate"]["status"]
        gate_counts[gate_status] = gate_counts.get(gate_status, 0) + 1
        severity = item["highest_severity"]
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
    return {
        "workspace_id": workspace_clean,
        "policy": get_governance_policy(workspace_clean),
        "analysis_volume": total,
        "average_score": round(sum(item["score"] for item in analyses) / total, 1) if total else 0,
        "gate_counts": gate_counts,
        "severity_counts": severity_counts,
        "source_counts": count_by(analyses, lambda item: item.get("source")),
        "route_counts": count_by(analyses, lambda item: item.get("gate", {}).get("route")),
        "model_version_counts": count_by(analyses, lambda item: item.get("model_version")),
        "webhook_status_counts": count_by(webhook_events, lambda item: item.get("delivery_status")),
        "outcome_counts": count_by(outcomes, lambda item: item.get("event_type")),
        "top_failing_rule_packs": top_failing_rule_packs(workspace_clean),
        "risky_templates": risky_templates(workspace_clean),
        "trend_by_source_system": trend_by_source_system(workspace_clean),
        "joined_outcomes": joined_outcomes(limit=limit, workspace_id=workspace_clean),
        "policy_bundle_history": policy_bundle_history(workspace_clean, limit=10),
        "recent_analyses": recent_email_analyses(limit, workspace_id=workspace_clean),
        "webhook_events": webhook_events,
        "outcomes": outcomes,
        "sample_imports": sample_imports,
    }


def field_mapping_from_row(row) -> dict[str, Any]:
    return {
        "workspace_id": row["workspace_id"],
        "provider": row["provider"],
        "mapping": json.loads(row["mapping_json"] or "{}"),
        "validation": json.loads(row["validation_json"] or "{}"),
        "status": row["status"],
        "version": row["version"],
        "updated_at": row["updated_at"],
    }


def save_integration_field_mapping(
    workspace_id: str,
    provider: str,
    mapping: dict[str, Any],
    validation: dict[str, Any],
    version: str,
) -> dict[str, Any]:
    clean_workspace = str(workspace_id or "default").strip()[:120] or "default"
    clean_provider = SAFE_EVENT_TYPE_RE.sub("_", str(provider or "")).strip("_").lower()[:80]
    if not clean_provider:
        raise ValueError("Integration field mapping is missing provider.")
    status = str(validation.get("status") or "needs_mapping")[:80]
    now = utc_now()
    clean_mapping = scrub_payload(mapping or {})
    clean_validation = scrub_payload(validation or {})
    with connect() as conn:
        execute(
            conn,
            """
            INSERT INTO integration_field_mappings (
              workspace_id, provider, mapping_json, validation_json, status, version, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(workspace_id, provider)
            DO UPDATE SET
              mapping_json = excluded.mapping_json,
              validation_json = excluded.validation_json,
              status = excluded.status,
              version = excluded.version,
              updated_at = excluded.updated_at
            """,
            (
                clean_workspace,
                clean_provider,
                json.dumps(clean_mapping, separators=(",", ":"), sort_keys=True),
                json.dumps(clean_validation, separators=(",", ":"), sort_keys=True),
                status,
                str(version or "")[:80],
                now,
            ),
        )
        row = execute(
            conn,
            "SELECT * FROM integration_field_mappings WHERE workspace_id = ? AND provider = ?",
            (clean_workspace, clean_provider),
        ).fetchone()
    return field_mapping_from_row(row)


def get_integration_field_mapping(workspace_id: str, provider: str) -> dict[str, Any] | None:
    clean_workspace = str(workspace_id or "default").strip()[:120] or "default"
    clean_provider = SAFE_EVENT_TYPE_RE.sub("_", str(provider or "")).strip("_").lower()[:80]
    with connect() as conn:
        row = execute(
            conn,
            "SELECT * FROM integration_field_mappings WHERE workspace_id = ? AND provider = ?",
            (clean_workspace, clean_provider),
        ).fetchone()
    return field_mapping_from_row(row) if row else None


def recent_integration_field_mappings(workspace_id: str = "default", limit: int = 20) -> list[dict[str, Any]]:
    clean_workspace = str(workspace_id or "default").strip()[:120] or "default"
    clean_limit = max(1, min(int(limit or 20), 100))
    with connect() as conn:
        rows = execute(
            conn,
            """
            SELECT * FROM integration_field_mappings
            WHERE workspace_id = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (clean_workspace, clean_limit),
        ).fetchall()
    return [field_mapping_from_row(row) for row in rows]


def governance_export_rows(kind: str, workspace_id: str = "default", limit: int = 1000) -> list[dict[str, Any]]:
    workspace_clean = clean_workspace_id(workspace_id)
    clean_limit = max(1, min(int(limit or 1000), 5000))
    kind_clean = str(kind or "analyses").strip().lower()
    statements = {
        "analyses": """
            SELECT workspace_id, request_id, content_hash, source, source_system, analysis_mode,
                   campaign_id, journey_id, template_id, locale, gate_status, send_ready,
                   route, highest_severity, score, finding_count, policy_bundle_version,
                   model_version, created_at
            FROM email_analyses
            WHERE workspace_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """,
        "findings": """
            SELECT workspace_id, request_id, content_hash, rule_id, category, severity,
                   title, remediation, evidence_json, created_at
            FROM email_findings
            WHERE workspace_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """,
        "outcomes": """
            SELECT workspace_id, request_id, content_hash, provider, event_type,
                   delivery_status, campaign_id, template_id, event_timestamp, created_at
            FROM email_outcomes
            WHERE workspace_id = ?
            ORDER BY event_timestamp DESC
            LIMIT ?
        """,
        "joins": """
            SELECT o.workspace_id, o.provider, o.event_type, o.delivery_status, o.request_id,
                   o.content_hash, o.campaign_id AS outcome_campaign_id, o.template_id AS outcome_template_id,
                   o.event_timestamp, a.score, a.gate_status, a.source_system,
                   a.campaign_id AS analysis_campaign_id, a.template_id AS analysis_template_id
            FROM email_outcomes o
            LEFT JOIN email_analyses a
              ON a.workspace_id = o.workspace_id
             AND ((o.request_id <> '' AND a.request_id = o.request_id)
               OR (o.content_hash <> '' AND a.content_hash = o.content_hash))
            WHERE o.workspace_id = ?
            ORDER BY o.event_timestamp DESC
            LIMIT ?
        """,
    }
    if kind_clean not in statements:
        raise ValueError("Export kind must be analyses, findings, outcomes, or joins.")
    with connect() as conn:
        rows = execute(conn, statements[kind_clean], (workspace_clean, clean_limit)).fetchall()
    return [dict(row) for row in rows]


def upsert_integration(user_id: int, provider: str, status: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    now = utc_now()
    clean_config = scrub_payload(config or {})
    with connect() as conn:
        execute(
            conn,
            """
            INSERT INTO integration_connections (user_id, provider, status, config, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, provider)
            DO UPDATE SET status = excluded.status, config = excluded.config, updated_at = excluded.updated_at
            """,
            (user_id, provider, status, json.dumps(clean_config, separators=(",", ":")), now),
        )
    log_event(user_id, "integration_updated", {"provider": provider, "status": status})
    return {"provider": provider, "status": status, "config": clean_config, "updated_at": now}


def integrations(user_id: int) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = execute(
            conn,
            "SELECT provider, status, config, updated_at FROM integration_connections WHERE user_id = ? ORDER BY provider",
            (user_id,),
        ).fetchall()
    return [
        {
            "provider": row["provider"],
            "status": row["status"],
            "config": json.loads(row["config"] or "{}"),
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


def export_user_data(user_id: int) -> dict[str, Any]:
    return {
        "user": get_user_by_id(user_id),
        "workspace": get_workspace(user_id),
        "integrations": integrations(user_id),
        "events": recent_events(user_id, limit=200),
        "exported_at": utc_now(),
    }


def delete_user(user_id: int) -> None:
    log_event(user_id, "account_deleted", {})
    with connect() as conn:
        execute(conn, "DELETE FROM users WHERE id = ?", (user_id,))


def user_session_version(user_id: int) -> int | None:
    with connect() as conn:
        row = execute(conn, "SELECT session_version FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        return None
    return int(row["session_version"] or 0)
