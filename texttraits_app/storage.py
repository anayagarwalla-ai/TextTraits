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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS hubspot_email_analyses (
                  id BIGSERIAL PRIMARY KEY,
                  request_id TEXT NOT NULL UNIQUE,
                  workspace_id TEXT NOT NULL DEFAULT '',
                  tenant_id TEXT NOT NULL DEFAULT '',
                  source_system TEXT NOT NULL DEFAULT 'hubspot',
                  workflow TEXT NOT NULL DEFAULT '',
                  analysis_mode TEXT NOT NULL DEFAULT '',
                  campaign_id TEXT NOT NULL DEFAULT '',
                  journey_id TEXT NOT NULL DEFAULT '',
                  template_id TEXT NOT NULL DEFAULT '',
                  contact_id TEXT NOT NULL DEFAULT '',
                  company_id TEXT NOT NULL DEFAULT '',
                  deal_id TEXT NOT NULL DEFAULT '',
                  owner_id TEXT NOT NULL DEFAULT '',
                  portal_id TEXT NOT NULL DEFAULT '',
                  object_type TEXT NOT NULL DEFAULT '',
                  object_id TEXT NOT NULL DEFAULT '',
                  locale TEXT NOT NULL DEFAULT '',
                  content_hash TEXT NOT NULL,
                  score INTEGER NOT NULL,
                  gate TEXT NOT NULL,
                  route TEXT NOT NULL,
                  send_ready INTEGER NOT NULL DEFAULT 0,
                  word_count INTEGER NOT NULL DEFAULT 0,
                  average_model_confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
                  score_source TEXT NOT NULL DEFAULT '',
                  findings TEXT NOT NULL DEFAULT '[]',
                  checks TEXT NOT NULL DEFAULT '[]',
                  policy TEXT NOT NULL DEFAULT '{}',
                  context TEXT NOT NULL DEFAULT '{}',
                  created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS hubspot_email_review_events (
                  id BIGSERIAL PRIMARY KEY,
                  request_id TEXT NOT NULL,
                  action TEXT NOT NULL,
                  actor_id TEXT NOT NULL DEFAULT '',
                  status TEXT NOT NULL DEFAULT 'recorded',
                  payload TEXT NOT NULL DEFAULT '{}',
                  created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS hubspot_policy_configs (
                  id BIGSERIAL PRIMARY KEY,
                  workspace_id TEXT NOT NULL,
                  environment TEXT NOT NULL DEFAULT 'production',
                  policy TEXT NOT NULL DEFAULT '{}',
                  updated_by TEXT NOT NULL DEFAULT '',
                  updated_at TEXT NOT NULL,
                  UNIQUE(workspace_id, environment)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS hubspot_policy_versions (
                  id BIGSERIAL PRIMARY KEY,
                  workspace_id TEXT NOT NULL,
                  environment TEXT NOT NULL DEFAULT 'production',
                  version TEXT NOT NULL DEFAULT '',
                  policy TEXT NOT NULL DEFAULT '{}',
                  updated_by TEXT NOT NULL DEFAULT '',
                  created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS hubspot_email_checks (
                  id BIGSERIAL PRIMARY KEY,
                  request_id TEXT NOT NULL,
                  check_id TEXT NOT NULL,
                  label TEXT NOT NULL DEFAULT '',
                  weight INTEGER NOT NULL DEFAULT 0,
                  score INTEGER NOT NULL DEFAULT 0,
                  status TEXT NOT NULL DEFAULT '',
                  penalty INTEGER NOT NULL DEFAULT 0,
                  evidence TEXT NOT NULL DEFAULT '[]',
                  created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS hubspot_email_findings (
                  id BIGSERIAL PRIMARY KEY,
                  request_id TEXT NOT NULL,
                  finding_id TEXT NOT NULL,
                  severity TEXT NOT NULL DEFAULT '',
                  title TEXT NOT NULL DEFAULT '',
                  owner_queue TEXT NOT NULL DEFAULT '',
                  blocker_level TEXT NOT NULL DEFAULT '',
                  next_step TEXT NOT NULL DEFAULT '',
                  action TEXT NOT NULL DEFAULT '',
                  evidence TEXT NOT NULL DEFAULT '[]',
                  created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS hubspot_email_review_states (
                  request_id TEXT PRIMARY KEY,
                  status TEXT NOT NULL DEFAULT 'open',
                  assigned_to TEXT NOT NULL DEFAULT '',
                  owner_queue TEXT NOT NULL DEFAULT '',
                  blocker_level TEXT NOT NULL DEFAULT '',
                  sla_due_at TEXT NOT NULL DEFAULT '',
                  resolved_at TEXT NOT NULL DEFAULT '',
                  notes TEXT NOT NULL DEFAULT '',
                  updated_by TEXT NOT NULL DEFAULT '',
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS hubspot_email_outcome_events (
                  id BIGSERIAL PRIMARY KEY,
                  request_id TEXT NOT NULL DEFAULT '',
                  content_hash TEXT NOT NULL DEFAULT '',
                  workspace_id TEXT NOT NULL DEFAULT '',
                  tenant_id TEXT NOT NULL DEFAULT '',
                  source_system TEXT NOT NULL DEFAULT '',
                  event_type TEXT NOT NULL,
                  event_id TEXT NOT NULL DEFAULT '',
                  payload TEXT NOT NULL DEFAULT '{}',
                  occurred_at TEXT NOT NULL,
                  created_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_hubspot_email_analyses_created_at ON hubspot_email_analyses (created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_hubspot_email_analyses_gate ON hubspot_email_analyses (gate)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_hubspot_email_analyses_source ON hubspot_email_analyses (source_system)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_hubspot_email_review_events_request ON hubspot_email_review_events (request_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_hubspot_email_checks_request ON hubspot_email_checks (request_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_hubspot_email_findings_request ON hubspot_email_findings (request_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_hubspot_email_outcomes_request ON hubspot_email_outcome_events (request_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_hubspot_email_outcomes_hash ON hubspot_email_outcome_events (content_hash)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_hubspot_policy_versions_workspace ON hubspot_policy_versions (workspace_id, environment)")
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

            CREATE TABLE IF NOT EXISTS hubspot_email_analyses (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              request_id TEXT NOT NULL UNIQUE,
              workspace_id TEXT NOT NULL DEFAULT '',
              tenant_id TEXT NOT NULL DEFAULT '',
              source_system TEXT NOT NULL DEFAULT 'hubspot',
              workflow TEXT NOT NULL DEFAULT '',
              analysis_mode TEXT NOT NULL DEFAULT '',
              campaign_id TEXT NOT NULL DEFAULT '',
              journey_id TEXT NOT NULL DEFAULT '',
              template_id TEXT NOT NULL DEFAULT '',
              contact_id TEXT NOT NULL DEFAULT '',
              company_id TEXT NOT NULL DEFAULT '',
              deal_id TEXT NOT NULL DEFAULT '',
              owner_id TEXT NOT NULL DEFAULT '',
              portal_id TEXT NOT NULL DEFAULT '',
              object_type TEXT NOT NULL DEFAULT '',
              object_id TEXT NOT NULL DEFAULT '',
              locale TEXT NOT NULL DEFAULT '',
              content_hash TEXT NOT NULL,
              score INTEGER NOT NULL,
              gate TEXT NOT NULL,
              route TEXT NOT NULL,
              send_ready INTEGER NOT NULL DEFAULT 0,
              word_count INTEGER NOT NULL DEFAULT 0,
              average_model_confidence REAL NOT NULL DEFAULT 0,
              score_source TEXT NOT NULL DEFAULT '',
              findings TEXT NOT NULL DEFAULT '[]',
              checks TEXT NOT NULL DEFAULT '[]',
              policy TEXT NOT NULL DEFAULT '{}',
              context TEXT NOT NULL DEFAULT '{}',
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS hubspot_email_review_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              request_id TEXT NOT NULL,
              action TEXT NOT NULL,
              actor_id TEXT NOT NULL DEFAULT '',
              status TEXT NOT NULL DEFAULT 'recorded',
              payload TEXT NOT NULL DEFAULT '{}',
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS hubspot_policy_configs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              workspace_id TEXT NOT NULL,
              environment TEXT NOT NULL DEFAULT 'production',
              policy TEXT NOT NULL DEFAULT '{}',
              updated_by TEXT NOT NULL DEFAULT '',
              updated_at TEXT NOT NULL,
              UNIQUE(workspace_id, environment)
            );

            CREATE TABLE IF NOT EXISTS hubspot_policy_versions (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              workspace_id TEXT NOT NULL,
              environment TEXT NOT NULL DEFAULT 'production',
              version TEXT NOT NULL DEFAULT '',
              policy TEXT NOT NULL DEFAULT '{}',
              updated_by TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS hubspot_email_checks (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              request_id TEXT NOT NULL,
              check_id TEXT NOT NULL,
              label TEXT NOT NULL DEFAULT '',
              weight INTEGER NOT NULL DEFAULT 0,
              score INTEGER NOT NULL DEFAULT 0,
              status TEXT NOT NULL DEFAULT '',
              penalty INTEGER NOT NULL DEFAULT 0,
              evidence TEXT NOT NULL DEFAULT '[]',
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS hubspot_email_findings (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              request_id TEXT NOT NULL,
              finding_id TEXT NOT NULL,
              severity TEXT NOT NULL DEFAULT '',
              title TEXT NOT NULL DEFAULT '',
              owner_queue TEXT NOT NULL DEFAULT '',
              blocker_level TEXT NOT NULL DEFAULT '',
              next_step TEXT NOT NULL DEFAULT '',
              action TEXT NOT NULL DEFAULT '',
              evidence TEXT NOT NULL DEFAULT '[]',
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS hubspot_email_review_states (
              request_id TEXT PRIMARY KEY,
              status TEXT NOT NULL DEFAULT 'open',
              assigned_to TEXT NOT NULL DEFAULT '',
              owner_queue TEXT NOT NULL DEFAULT '',
              blocker_level TEXT NOT NULL DEFAULT '',
              sla_due_at TEXT NOT NULL DEFAULT '',
              resolved_at TEXT NOT NULL DEFAULT '',
              notes TEXT NOT NULL DEFAULT '',
              updated_by TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS hubspot_email_outcome_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              request_id TEXT NOT NULL DEFAULT '',
              content_hash TEXT NOT NULL DEFAULT '',
              workspace_id TEXT NOT NULL DEFAULT '',
              tenant_id TEXT NOT NULL DEFAULT '',
              source_system TEXT NOT NULL DEFAULT '',
              event_type TEXT NOT NULL,
              event_id TEXT NOT NULL DEFAULT '',
              payload TEXT NOT NULL DEFAULT '{}',
              occurred_at TEXT NOT NULL,
              created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_hubspot_email_analyses_created_at ON hubspot_email_analyses (created_at);
            CREATE INDEX IF NOT EXISTS idx_hubspot_email_analyses_gate ON hubspot_email_analyses (gate);
            CREATE INDEX IF NOT EXISTS idx_hubspot_email_analyses_source ON hubspot_email_analyses (source_system);
            CREATE INDEX IF NOT EXISTS idx_hubspot_email_review_events_request ON hubspot_email_review_events (request_id);
            CREATE INDEX IF NOT EXISTS idx_hubspot_email_checks_request ON hubspot_email_checks (request_id);
            CREATE INDEX IF NOT EXISTS idx_hubspot_email_findings_request ON hubspot_email_findings (request_id);
            CREATE INDEX IF NOT EXISTS idx_hubspot_email_outcomes_request ON hubspot_email_outcome_events (request_id);
            CREATE INDEX IF NOT EXISTS idx_hubspot_email_outcomes_hash ON hubspot_email_outcome_events (content_hash);
            CREATE INDEX IF NOT EXISTS idx_hubspot_policy_versions_workspace ON hubspot_policy_versions (workspace_id, environment);
            """
            )
        ensure_schema_version(conn)
        ensure_column(conn, "users", "email_verified_at", "TEXT")
        ensure_column(conn, "users", "verification_token", "TEXT")
        ensure_column(conn, "users", "reset_token", "TEXT")
        ensure_column(conn, "users", "reset_expires_at", "TEXT")
        ensure_column(conn, "users", "session_version", "INTEGER DEFAULT 0")


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
    if uses_postgres():
        conn.execute(
            """
            INSERT INTO schema_migrations (version, applied_at)
            VALUES (%s, %s)
            ON CONFLICT (version) DO NOTHING
            """,
            (SCHEMA_VERSION, utc_now()),
        )
    else:
        conn.execute(
            """
            INSERT OR IGNORE INTO schema_migrations (version, applied_at)
            VALUES (?, ?)
            """,
            (SCHEMA_VERSION, utc_now()),
        )


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


def _json_dump(value: Any) -> str:
    return json.dumps(scrub_payload(value), separators=(",", ":"), sort_keys=True)


def _json_load(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _hubspot_analysis_from_row(row) -> dict[str, Any]:
    return {
        "request_id": row["request_id"],
        "workspace_id": row["workspace_id"],
        "tenant_id": row["tenant_id"],
        "source_system": row["source_system"],
        "workflow": row["workflow"],
        "analysis_mode": row["analysis_mode"],
        "campaign_id": row["campaign_id"],
        "journey_id": row["journey_id"],
        "template_id": row["template_id"],
        "contact_id": row["contact_id"],
        "company_id": row["company_id"],
        "deal_id": row["deal_id"],
        "owner_id": row["owner_id"],
        "portal_id": row["portal_id"],
        "object_type": row["object_type"],
        "object_id": row["object_id"],
        "locale": row["locale"],
        "content_hash": row["content_hash"],
        "score": int(row["score"] or 0),
        "gate": row["gate"],
        "route": row["route"],
        "send_ready": bool(row["send_ready"]),
        "word_count": int(row["word_count"] or 0),
        "average_model_confidence": float(row["average_model_confidence"] or 0),
        "score_source": row["score_source"],
        "findings": _json_load(row["findings"], []),
        "checks": _json_load(row["checks"], []),
        "policy": _json_load(row["policy"], {}),
        "context": _json_load(row["context"], {}),
        "created_at": row["created_at"],
    }


def save_hubspot_analysis_artifacts(request_id: str, checks: list[dict[str, Any]], findings: list[dict[str, Any]], created_at: str) -> None:
    clean_request_id = str(request_id or "").strip()[:160]
    if not clean_request_id:
        return
    with connect() as conn:
        execute(conn, "DELETE FROM hubspot_email_checks WHERE request_id = ?", (clean_request_id,))
        execute(conn, "DELETE FROM hubspot_email_findings WHERE request_id = ?", (clean_request_id,))
        for check in checks[:100]:
            execute(
                conn,
                """
                INSERT INTO hubspot_email_checks (
                  request_id, check_id, label, weight, score, status, penalty, evidence, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    clean_request_id,
                    str(check.get("id", ""))[:120],
                    str(check.get("label", ""))[:160],
                    int(check.get("weight") or 0),
                    int(check.get("score") or 0),
                    str(check.get("status", ""))[:80],
                    int(check.get("penalty") or 0),
                    _json_dump(check.get("evidence") or []),
                    created_at,
                ),
            )
        for finding in findings[:100]:
            execute(
                conn,
                """
                INSERT INTO hubspot_email_findings (
                  request_id, finding_id, severity, title, owner_queue, blocker_level,
                  next_step, action, evidence, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    clean_request_id,
                    str(finding.get("id", ""))[:120],
                    str(finding.get("severity", ""))[:80],
                    str(finding.get("title", ""))[:240],
                    str(finding.get("owner_queue", ""))[:160],
                    str(finding.get("blocker_level", ""))[:80],
                    str(finding.get("next_step", ""))[:500],
                    str(finding.get("action", ""))[:500],
                    _json_dump(finding.get("evidence") or []),
                    created_at,
                ),
            )


def list_hubspot_normalized_findings(limit: int = 100, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    filters = filters or {}
    clauses: list[str] = []
    params: list[Any] = []
    for key in ("request_id", "finding_id", "severity", "owner_queue", "blocker_level"):
        value = str(filters.get(key, "")).strip()
        if value:
            clauses.append(f"{key} = ?")
            params.append(value)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    safe_limit = max(1, min(int(limit or 100), 1000))
    with connect() as conn:
        rows = execute(
            conn,
            f"SELECT * FROM hubspot_email_findings {where} ORDER BY id DESC LIMIT ?",
            (*params, safe_limit),
        ).fetchall()
    return [
        {
            "request_id": row["request_id"],
            "finding_id": row["finding_id"],
            "severity": row["severity"],
            "title": row["title"],
            "owner_queue": row["owner_queue"],
            "blocker_level": row["blocker_level"],
            "next_step": row["next_step"],
            "action": row["action"],
            "evidence": _json_load(row["evidence"], []),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def list_hubspot_normalized_checks(limit: int = 100, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    filters = filters or {}
    clauses: list[str] = []
    params: list[Any] = []
    for key in ("request_id", "check_id", "status"):
        value = str(filters.get(key, "")).strip()
        if value:
            clauses.append(f"{key} = ?")
            params.append(value)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    safe_limit = max(1, min(int(limit or 100), 1000))
    with connect() as conn:
        rows = execute(
            conn,
            f"SELECT * FROM hubspot_email_checks {where} ORDER BY id DESC LIMIT ?",
            (*params, safe_limit),
        ).fetchall()
    return [
        {
            "request_id": row["request_id"],
            "check_id": row["check_id"],
            "label": row["label"],
            "weight": int(row["weight"] or 0),
            "score": int(row["score"] or 0),
            "status": row["status"],
            "penalty": int(row["penalty"] or 0),
            "evidence": _json_load(row["evidence"], []),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def save_hubspot_email_analysis(record: dict[str, Any]) -> dict[str, Any]:
    now = record.get("created_at") or utc_now()
    values = {
        "request_id": str(record.get("request_id", ""))[:160],
        "workspace_id": str(record.get("workspace_id", ""))[:160],
        "tenant_id": str(record.get("tenant_id", ""))[:160],
        "source_system": str(record.get("source_system", "hubspot"))[:80],
        "workflow": str(record.get("workflow", ""))[:120],
        "analysis_mode": str(record.get("analysis_mode", ""))[:80],
        "campaign_id": str(record.get("campaign_id", ""))[:160],
        "journey_id": str(record.get("journey_id", ""))[:160],
        "template_id": str(record.get("template_id", ""))[:160],
        "contact_id": str(record.get("contact_id", ""))[:160],
        "company_id": str(record.get("company_id", ""))[:160],
        "deal_id": str(record.get("deal_id", ""))[:160],
        "owner_id": str(record.get("owner_id", ""))[:160],
        "portal_id": str(record.get("portal_id", ""))[:160],
        "object_type": str(record.get("object_type", ""))[:120],
        "object_id": str(record.get("object_id", ""))[:160],
        "locale": str(record.get("locale", ""))[:40],
        "content_hash": str(record.get("content_hash", ""))[:128],
        "score": int(record.get("score") or 0),
        "gate": str(record.get("gate", ""))[:80],
        "route": str(record.get("route", ""))[:120],
        "send_ready": 1 if record.get("send_ready") else 0,
        "word_count": int(record.get("word_count") or 0),
        "average_model_confidence": float(record.get("average_model_confidence") or 0),
        "score_source": str(record.get("score_source", ""))[:500],
        "findings": _json_dump(record.get("findings") or []),
        "checks": _json_dump(record.get("checks") or []),
        "policy": _json_dump(record.get("policy") or {}),
        "context": _json_dump(record.get("context") or {}),
        "created_at": now,
    }
    if not values["request_id"]:
        raise ValueError("HubSpot analysis record requires a request_id.")
    with connect() as conn:
        execute(
            conn,
            """
            INSERT INTO hubspot_email_analyses (
              request_id, workspace_id, tenant_id, source_system, workflow, analysis_mode,
              campaign_id, journey_id, template_id, contact_id, company_id, deal_id,
              owner_id, portal_id, object_type, object_id, locale, content_hash, score,
              gate, route, send_ready, word_count, average_model_confidence, score_source,
              findings, checks, policy, context, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(request_id) DO UPDATE SET
              workspace_id = excluded.workspace_id,
              tenant_id = excluded.tenant_id,
              source_system = excluded.source_system,
              workflow = excluded.workflow,
              analysis_mode = excluded.analysis_mode,
              campaign_id = excluded.campaign_id,
              journey_id = excluded.journey_id,
              template_id = excluded.template_id,
              contact_id = excluded.contact_id,
              company_id = excluded.company_id,
              deal_id = excluded.deal_id,
              owner_id = excluded.owner_id,
              portal_id = excluded.portal_id,
              object_type = excluded.object_type,
              object_id = excluded.object_id,
              locale = excluded.locale,
              content_hash = excluded.content_hash,
              score = excluded.score,
              gate = excluded.gate,
              route = excluded.route,
              send_ready = excluded.send_ready,
              word_count = excluded.word_count,
              average_model_confidence = excluded.average_model_confidence,
              score_source = excluded.score_source,
              findings = excluded.findings,
              checks = excluded.checks,
              policy = excluded.policy,
              context = excluded.context
            """,
            tuple(values[key] for key in values),
        )
    save_hubspot_analysis_artifacts(values["request_id"], record.get("checks") or [], record.get("findings") or [], now)
    return values


def list_hubspot_email_analyses(limit: int = 100, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    filters = filters or {}
    clauses: list[str] = []
    params: list[Any] = []
    for key in ("workspace_id", "tenant_id", "source_system", "gate", "route", "campaign_id", "template_id", "contact_id", "company_id", "deal_id"):
        value = str(filters.get(key, "")).strip()
        if value:
            clauses.append(f"{key} = ?")
            params.append(value)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    safe_limit = max(1, min(int(limit or 100), 1000))
    with connect() as conn:
        rows = execute(
            conn,
            f"SELECT * FROM hubspot_email_analyses {where} ORDER BY id DESC LIMIT ?",
            (*params, safe_limit),
        ).fetchall()
    return [_hubspot_analysis_from_row(row) for row in rows]


def save_hubspot_review_event(request_id: str, action: str, payload: dict[str, Any] | None = None, actor_id: str = "", status: str = "recorded") -> dict[str, Any]:
    clean_action = SAFE_EVENT_TYPE_RE.sub("_", str(action or "")).strip("_")[:80]
    if clean_action not in {"copy_recommendation", "mark_reviewed", "send_to_marketing_review", "rerun_analysis", "assign_reviewer", "resolve_review", "add_review_note"}:
        raise ValueError("Unsupported HubSpot review action.")
    clean_request_id = str(request_id or "").strip()[:160]
    if not clean_request_id:
        raise ValueError("HubSpot review action requires a request_id.")
    clean_payload = scrub_payload(payload or {})
    event = {
        "request_id": clean_request_id,
        "action": clean_action,
        "actor_id": str(actor_id or "")[:160],
        "status": str(status or "recorded")[:80],
        "payload": clean_payload,
        "created_at": utc_now(),
    }
    with connect() as conn:
        execute(
            conn,
            "INSERT INTO hubspot_email_review_events (request_id, action, actor_id, status, payload, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (event["request_id"], event["action"], event["actor_id"], event["status"], _json_dump(event["payload"]), event["created_at"]),
        )
    upsert_hubspot_review_state_from_event(event)
    return event


def upsert_hubspot_review_state_from_event(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    action = str(event.get("action") or "")
    now = utc_now()
    request_id = str(event.get("request_id") or "")[:160]
    status = str(payload.get("review_status") or payload.get("status") or "open")[:80]
    resolved_at = ""
    if action == "send_to_marketing_review":
        status = "queued"
    elif action == "assign_reviewer":
        status = "assigned"
    elif action in {"mark_reviewed", "resolve_review"}:
        status = "resolved"
        resolved_at = now
    elif action == "rerun_analysis":
        status = "rerun_requested"
    elif action == "copy_recommendation":
        status = "open"
    notes = str(payload.get("notes") or payload.get("recommendation") or "")[:1000]
    state = {
        "request_id": request_id,
        "status": status,
        "assigned_to": str(payload.get("assigned_to") or payload.get("reviewer") or "")[:160],
        "owner_queue": str(payload.get("owner_queue") or payload.get("route") or "")[:160],
        "blocker_level": str(payload.get("blocker_level") or "")[:80],
        "sla_due_at": str(payload.get("sla_due_at") or "")[:80],
        "resolved_at": resolved_at,
        "notes": notes,
        "updated_by": str(event.get("actor_id") or "")[:160],
        "created_at": now,
        "updated_at": now,
    }
    with connect() as conn:
        existing = execute(conn, "SELECT created_at, resolved_at FROM hubspot_email_review_states WHERE request_id = ?", (request_id,)).fetchone()
        created_at = existing["created_at"] if existing else now
        resolved_value = resolved_at or (existing["resolved_at"] if existing else "")
        execute(
            conn,
            """
            INSERT INTO hubspot_email_review_states (
              request_id, status, assigned_to, owner_queue, blocker_level, sla_due_at,
              resolved_at, notes, updated_by, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(request_id) DO UPDATE SET
              status = excluded.status,
              assigned_to = COALESCE(NULLIF(excluded.assigned_to, ''), hubspot_email_review_states.assigned_to),
              owner_queue = COALESCE(NULLIF(excluded.owner_queue, ''), hubspot_email_review_states.owner_queue),
              blocker_level = COALESCE(NULLIF(excluded.blocker_level, ''), hubspot_email_review_states.blocker_level),
              sla_due_at = COALESCE(NULLIF(excluded.sla_due_at, ''), hubspot_email_review_states.sla_due_at),
              resolved_at = excluded.resolved_at,
              notes = COALESCE(NULLIF(excluded.notes, ''), hubspot_email_review_states.notes),
              updated_by = excluded.updated_by,
              updated_at = excluded.updated_at
            """,
            (
                request_id,
                state["status"],
                state["assigned_to"],
                state["owner_queue"],
                state["blocker_level"],
                state["sla_due_at"],
                resolved_value,
                state["notes"],
                state["updated_by"],
                created_at,
                now,
            ),
        )
    state["created_at"] = created_at
    state["resolved_at"] = resolved_value
    return state


def list_hubspot_review_states(limit: int = 100, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    filters = filters or {}
    clauses: list[str] = []
    params: list[Any] = []
    for key in ("request_id", "status", "owner_queue", "assigned_to"):
        value = str(filters.get(key, "")).strip()
        if value:
            clauses.append(f"{key} = ?")
            params.append(value)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    safe_limit = max(1, min(int(limit or 100), 1000))
    with connect() as conn:
        rows = execute(
            conn,
            f"SELECT * FROM hubspot_email_review_states {where} ORDER BY updated_at DESC LIMIT ?",
            (*params, safe_limit),
        ).fetchall()
    return [
        {
            "request_id": row["request_id"],
            "status": row["status"],
            "assigned_to": row["assigned_to"],
            "owner_queue": row["owner_queue"],
            "blocker_level": row["blocker_level"],
            "sla_due_at": row["sla_due_at"],
            "resolved_at": row["resolved_at"],
            "notes": row["notes"],
            "updated_by": row["updated_by"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


def list_hubspot_review_events(request_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit or 100), 1000))
    params: tuple[Any, ...]
    if request_id:
        statement = "SELECT request_id, action, actor_id, status, payload, created_at FROM hubspot_email_review_events WHERE request_id = ? ORDER BY id DESC LIMIT ?"
        params = (str(request_id)[:160], safe_limit)
    else:
        statement = "SELECT request_id, action, actor_id, status, payload, created_at FROM hubspot_email_review_events ORDER BY id DESC LIMIT ?"
        params = (safe_limit,)
    with connect() as conn:
        rows = execute(conn, statement, params).fetchall()
    return [
        {
            "request_id": row["request_id"],
            "action": row["action"],
            "actor_id": row["actor_id"],
            "status": row["status"],
            "payload": _json_load(row["payload"], {}),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def get_hubspot_policy_config(workspace_id: str, environment: str = "production") -> dict[str, Any] | None:
    with connect() as conn:
        row = execute(
            conn,
            "SELECT policy, updated_by, updated_at FROM hubspot_policy_configs WHERE workspace_id = ? AND environment = ?",
            (str(workspace_id or "default")[:160], str(environment or "production")[:80]),
        ).fetchone()
    if row is None:
        return None
    return {
        "workspace_id": str(workspace_id or "default")[:160],
        "environment": str(environment or "production")[:80],
        "policy": _json_load(row["policy"], {}),
        "updated_by": row["updated_by"],
        "updated_at": row["updated_at"],
    }


def save_hubspot_policy_config(workspace_id: str, environment: str, policy: dict[str, Any], updated_by: str = "") -> dict[str, Any]:
    now = utc_now()
    clean_workspace = str(workspace_id or "default")[:160]
    clean_environment = str(environment or "production")[:80]
    clean_policy = scrub_payload(policy or {})
    clean_updated_by = str(updated_by or "")[:160]
    with connect() as conn:
        execute(
            conn,
            """
            INSERT INTO hubspot_policy_configs (workspace_id, environment, policy, updated_by, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(workspace_id, environment)
            DO UPDATE SET policy = excluded.policy, updated_by = excluded.updated_by, updated_at = excluded.updated_at
            """,
            (clean_workspace, clean_environment, _json_dump(clean_policy), clean_updated_by, now),
        )
        execute(
            conn,
            """
            INSERT INTO hubspot_policy_versions (workspace_id, environment, version, policy, updated_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                clean_workspace,
                clean_environment,
                str(clean_policy.get("version", ""))[:80],
                _json_dump(clean_policy),
                clean_updated_by,
                now,
            ),
        )
    return {
        "workspace_id": clean_workspace,
        "environment": clean_environment,
        "policy": clean_policy,
        "updated_by": clean_updated_by,
        "updated_at": now,
    }


def list_hubspot_policy_versions(workspace_id: str = "", environment: str = "", limit: int = 100) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    clean_workspace = str(workspace_id or "").strip()
    clean_environment = str(environment or "").strip()
    if clean_workspace:
        clauses.append("workspace_id = ?")
        params.append(clean_workspace[:160])
    if clean_environment:
        clauses.append("environment = ?")
        params.append(clean_environment[:80])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    safe_limit = max(1, min(int(limit or 100), 1000))
    with connect() as conn:
        rows = execute(
            conn,
            f"SELECT workspace_id, environment, version, policy, updated_by, created_at FROM hubspot_policy_versions {where} ORDER BY id DESC LIMIT ?",
            (*params, safe_limit),
        ).fetchall()
    return [
        {
            "workspace_id": row["workspace_id"],
            "environment": row["environment"],
            "version": row["version"],
            "policy": _json_load(row["policy"], {}),
            "updated_by": row["updated_by"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def save_hubspot_outcome_event(record: dict[str, Any]) -> dict[str, Any]:
    event = {
        "request_id": str(record.get("request_id", ""))[:160],
        "content_hash": str(record.get("content_hash", ""))[:128],
        "workspace_id": str(record.get("workspace_id", ""))[:160],
        "tenant_id": str(record.get("tenant_id", ""))[:160],
        "source_system": str(record.get("source_system", "hubspot"))[:80],
        "event_type": SAFE_EVENT_TYPE_RE.sub("_", str(record.get("event_type") or "")).strip("_")[:80],
        "event_id": str(record.get("event_id", ""))[:160],
        "payload": scrub_payload(record.get("payload") if isinstance(record.get("payload"), dict) else {}),
        "occurred_at": str(record.get("occurred_at") or utc_now())[:80],
        "created_at": utc_now(),
    }
    if not event["event_type"]:
        raise ValueError("Outcome event requires an event_type.")
    if not event["request_id"] and not event["content_hash"]:
        raise ValueError("Outcome event requires a request_id or content_hash.")
    with connect() as conn:
        execute(
            conn,
            """
            INSERT INTO hubspot_email_outcome_events (
              request_id, content_hash, workspace_id, tenant_id, source_system,
              event_type, event_id, payload, occurred_at, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["request_id"],
                event["content_hash"],
                event["workspace_id"],
                event["tenant_id"],
                event["source_system"],
                event["event_type"],
                event["event_id"],
                _json_dump(event["payload"]),
                event["occurred_at"],
                event["created_at"],
            ),
        )
    return event


def list_hubspot_outcome_events(limit: int = 100, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    filters = filters or {}
    clauses: list[str] = []
    params: list[Any] = []
    for key in ("request_id", "content_hash", "workspace_id", "tenant_id", "source_system", "event_type"):
        value = str(filters.get(key, "")).strip()
        if value:
            clauses.append(f"{key} = ?")
            params.append(value[:160])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    safe_limit = max(1, min(int(limit or 100), 1000))
    with connect() as conn:
        rows = execute(
            conn,
            f"SELECT * FROM hubspot_email_outcome_events {where} ORDER BY id DESC LIMIT ?",
            (*params, safe_limit),
        ).fetchall()
    return [
        {
            "request_id": row["request_id"],
            "content_hash": row["content_hash"],
            "workspace_id": row["workspace_id"],
            "tenant_id": row["tenant_id"],
            "source_system": row["source_system"],
            "event_type": row["event_type"],
            "event_id": row["event_id"],
            "payload": _json_load(row["payload"], {}),
            "occurred_at": row["occurred_at"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def hubspot_email_dashboard(limit: int = 500) -> dict[str, Any]:
    analyses = list_hubspot_email_analyses(limit=limit)
    outcomes = list_hubspot_outcome_events(limit=limit)
    total = len(analyses)
    gates: dict[str, int] = {}
    source_scores: dict[str, list[int]] = {}
    failed_checks: dict[str, int] = {}
    route_counts: dict[str, int] = {}
    outcome_counts: dict[str, int] = {}
    blocked = []
    outcomes_by_request: dict[str, list[dict[str, Any]]] = {}
    outcomes_by_hash: dict[str, list[dict[str, Any]]] = {}
    for event in outcomes:
        outcome_counts[event["event_type"]] = outcome_counts.get(event["event_type"], 0) + 1
        if event["request_id"]:
            outcomes_by_request.setdefault(event["request_id"], []).append(event)
        if event["content_hash"]:
            outcomes_by_hash.setdefault(event["content_hash"], []).append(event)
    for item in analyses:
        item_outcomes = outcomes_by_request.get(item["request_id"], []) + outcomes_by_hash.get(item["content_hash"], [])
        item["outcomes"] = item_outcomes[:20]
        gates[item["gate"]] = gates.get(item["gate"], 0) + 1
        route_counts[item["route"]] = route_counts.get(item["route"], 0) + 1
        source = item["source_system"] or "unknown"
        source_scores.setdefault(source, []).append(item["score"])
        if item["gate"] == "blocked":
            blocked.append(item)
        for check in item.get("checks", []):
            if check.get("status") != "pass":
                label = check.get("label") or check.get("id") or "Unknown check"
                failed_checks[label] = failed_checks.get(label, 0) + 1
    average_by_source = {
        source: round(sum(scores) / len(scores), 1)
        for source, scores in source_scores.items()
        if scores
    }
    return {
        "total_analyses": total,
        "gate_counts": gates,
        "route_counts": route_counts,
        "outcome_counts": outcome_counts,
        "average_score_by_source": average_by_source,
        "top_failed_checks": [
            {"check": check, "count": count}
            for check, count in sorted(failed_checks.items(), key=lambda item: item[1], reverse=True)[:10]
        ],
        "recent_blocked_drafts": blocked[:10],
        "generated_at": utc_now(),
    }


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
