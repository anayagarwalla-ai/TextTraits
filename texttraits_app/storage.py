from __future__ import annotations

import json
import os
import sqlite3
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from werkzeug.security import check_password_hash, generate_password_hash

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - optional production dependency
    psycopg = None
    dict_row = None


APP_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = APP_DIR / "artifacts" / "texttraits_workspace.sqlite3"


def db_path() -> Path:
    return Path(os.getenv("TEXTTRAITS_DB_PATH", str(DEFAULT_DB_PATH))).expanduser()


def database_url() -> str:
    return (os.getenv("TEXTTRAITS_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()


def uses_postgres() -> bool:
    return database_url().startswith(("postgres://", "postgresql://"))


def database_backend() -> str:
    return "postgres" if uses_postgres() else "sqlite"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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
                  created_at TEXT NOT NULL,
                  last_login_at TEXT
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
        ensure_column(conn, "users", "email_verified_at", "TEXT")
        ensure_column(conn, "users", "verification_token", "TEXT")
        ensure_column(conn, "users", "reset_token", "TEXT")
        ensure_column(conn, "users", "reset_expires_at", "TEXT")


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


def create_user(email: str, password: str, name: str = "") -> dict[str, Any]:
    clean_email = email.strip().lower()
    clean_name = name.strip() or clean_email.split("@")[0].replace(".", " ").title()
    now = utc_now()
    verification_token = secrets.token_urlsafe(24)
    with connect() as conn:
        if uses_postgres():
            row = conn.execute(
                """
                INSERT INTO users (email, name, password_hash, verification_token, created_at)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (clean_email, clean_name, generate_password_hash(password), verification_token, now),
            ).fetchone()
            user_id = int(row["id"])
        else:
            cursor = execute(
                conn,
                "INSERT INTO users (email, name, password_hash, verification_token, created_at) VALUES (?, ?, ?, ?, ?)",
                (clean_email, clean_name, generate_password_hash(password), verification_token, now),
            )
            user_id = int(cursor.lastrowid)
        execute(
            conn,
            "INSERT INTO workspaces (user_id, name, data, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, f"{clean_name}'s workspace", "{}", now, now),
        )
        row = execute(conn, "SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return public_user(row) or {}


def authenticate_user(email: str, password: str) -> dict[str, Any] | None:
    row = get_user_by_email(email)
    if row is None or not check_password_hash(row["password_hash"], password):
        return None
    now = utc_now()
    with connect() as conn:
        execute(conn, "UPDATE users SET last_login_at = ? WHERE id = ?", (now, row["id"]))
        updated = execute(conn, "SELECT * FROM users WHERE id = ?", (row["id"],)).fetchone()
    return public_user(updated)


def get_verification_token(user_id: int) -> str | None:
    with connect() as conn:
        row = execute(conn, "SELECT verification_token FROM users WHERE id = ?", (user_id,)).fetchone()
    return row["verification_token"] if row else None


def verify_email_token(token: str) -> dict[str, Any] | None:
    clean = token.strip()
    if not clean:
        return None
    with connect() as conn:
        row = execute(conn, "SELECT * FROM users WHERE verification_token = ?", (clean,)).fetchone()
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
    expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(timespec="seconds")
    with connect() as conn:
        execute(
            conn,
            "UPDATE users SET reset_token = ?, reset_expires_at = ? WHERE id = ?",
            (token, expires, row["id"]),
        )
    log_event(int(row["id"]), "password_reset_requested", {})
    return {"token": token, "expires_at": expires}


def reset_password(token: str, password: str) -> dict[str, Any] | None:
    clean = token.strip()
    if not clean:
        return None
    now = datetime.now(timezone.utc)
    with connect() as conn:
        row = execute(conn, "SELECT * FROM users WHERE reset_token = ?", (clean,)).fetchone()
        if row is None:
            return None
        expires = datetime.fromisoformat(row["reset_expires_at"]) if row["reset_expires_at"] else now
        if expires < now:
            return None
        execute(
            conn,
            "UPDATE users SET password_hash = ?, reset_token = NULL, reset_expires_at = NULL WHERE id = ?",
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
    with connect() as conn:
        execute(
            conn,
            "UPDATE workspaces SET name = ?, data = ?, updated_at = ? WHERE user_id = ?",
            (workspace_name, serialized, now, user_id),
        )
    return get_workspace(user_id)


def log_event(user_id: int | None, event_type: str, payload: dict[str, Any] | None = None) -> None:
    with connect() as conn:
        execute(
            conn,
            "INSERT INTO audit_events (user_id, event_type, payload, created_at) VALUES (?, ?, ?, ?)",
            (user_id, event_type, json.dumps(payload or {}, separators=(",", ":")), utc_now()),
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


def upsert_integration(user_id: int, provider: str, status: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    now = utc_now()
    with connect() as conn:
        execute(
            conn,
            """
            INSERT INTO integration_connections (user_id, provider, status, config, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, provider)
            DO UPDATE SET status = excluded.status, config = excluded.config, updated_at = excluded.updated_at
            """,
            (user_id, provider, status, json.dumps(config or {}, separators=(",", ":")), now),
        )
    log_event(user_id, "integration_updated", {"provider": provider, "status": status})
    return {"provider": provider, "status": status, "config": config or {}, "updated_at": now}


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
