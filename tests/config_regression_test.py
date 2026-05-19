from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_preflight(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged.update(env)
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "preflight.py")],
        cwd=ROOT,
        env=merged,
        text=True,
        capture_output=True,
        check=False,
    )


def main() -> int:
    supabase_ref = "olacwelhrgzxzrxtmvto"
    supabase_docs = (ROOT / "SUPABASE_POSTGRES_SETUP.md").read_text(encoding="utf-8")
    supabase_script = (ROOT / "scripts" / "setup_supabase_cli.sh").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    render_yaml = (ROOT / "render.yaml").read_text(encoding="utf-8")
    procfile = (ROOT / "Procfile").read_text(encoding="utf-8")
    root_entrypoint = (ROOT / "app.py").read_text(encoding="utf-8")
    assert_true(supabase_ref in supabase_docs, "Supabase docs should include the project ref")
    assert_true(f"supabase link --project-ref {supabase_ref}" in supabase_docs, "Supabase docs should include the CLI link command")
    assert_true(supabase_ref in supabase_script and "supabase login" in supabase_script and "supabase init" in supabase_script, "Supabase helper should run login/init/link flow")
    assert_true(supabase_ref in env_example and "DATABASE_URL=" in env_example, ".env example should point DATABASE_URL users to the Supabase project")
    assert_true("startCommand: gunicorn app:app" in render_yaml, "Render should use the root app:app entrypoint")
    assert_true("env: python" in render_yaml and "buildCommand: pip install -r requirements.txt" in render_yaml, "Render blueprint should be a native Python service")
    assert_true("gunicorn app:app" in procfile, "Procfile should match Render's app:app entrypoint")
    assert_true("APP_DIR" in root_entrypoint and "application = app" in root_entrypoint, "Root app.py should expose app and application for WSGI hosts")

    render_import = subprocess.run(
        [sys.executable, "-c", "from app import app, application; assert app is application; print(app.name)"],
        cwd=ROOT,
        env={
            **os.environ,
            "TEXTTRAITS_ENV": "development",
            "TEXTTRAITS_SECRET_KEY": "render-entrypoint-test-secret",
            "TEXTTRAITS_EMAIL_PROVIDER": "console",
            "TEXTTRAITS_DATABASE_URL": "",
            "DATABASE_URL": "",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert_true(render_import.returncode == 0, render_import.stderr)

    local = run_preflight({"TEXTTRAITS_ENV": "development", "TEXTTRAITS_EMAIL_PROVIDER": ""})
    assert_true(local.returncode == 0, local.stderr)

    broken_prod = run_preflight(
        {
            "TEXTTRAITS_ENV": "production",
            "TEXTTRAITS_SECRET_KEY": "replace-with-a-long-random-secret",
            "TEXTTRAITS_PUBLIC_BASE_URL": "http://example.com",
            "TEXTTRAITS_DATABASE_URL": "",
            "DATABASE_URL": "",
            "TEXTTRAITS_EMAIL_PROVIDER": "",
        }
    )
    assert_true(broken_prod.returncode == 1, "broken production config should fail")
    assert_true("hosted Postgres" in broken_prod.stderr, "preflight should require hosted Postgres")
    assert_true("HTTPS" in broken_prod.stderr, "preflight should require HTTPS")

    good_prod = run_preflight(
        {
            "TEXTTRAITS_ENV": "production",
            "TEXTTRAITS_SECRET_KEY": "a-realistic-test-secret-with-more-than-enough-entropy",
            "TEXTTRAITS_PUBLIC_BASE_URL": "https://texttraits.example",
            "TEXTTRAITS_ALLOWED_PUBLIC_HOSTS": "texttraits.example",
            "TEXTTRAITS_DATABASE_URL": "",
            "DATABASE_URL": "postgresql://postgres.projectref:secret@aws-0-us-east-1.pooler.supabase.com:5432/postgres",
            "TEXTTRAITS_DB_SSLMODE": "require",
            "TEXTTRAITS_SECURE_COOKIES": "true",
            "TEXTTRAITS_EMAIL_PROVIDER": "smtp",
            "TEXTTRAITS_FROM_EMAIL": "no-reply@texttraits.example",
            "TEXTTRAITS_SMTP_HOST": "smtp.example.com",
            "TEXTTRAITS_SMTP_USERNAME": "apikey",
            "TEXTTRAITS_SMTP_PASSWORD": "secret",
        }
    )
    assert_true(good_prod.returncode == 0, good_prod.stderr)

    wrong_host = run_preflight(
        {
            "TEXTTRAITS_ENV": "production",
            "TEXTTRAITS_SECRET_KEY": "a-realistic-test-secret-with-more-than-enough-entropy",
            "TEXTTRAITS_PUBLIC_BASE_URL": "https://evil.example",
            "TEXTTRAITS_ALLOWED_PUBLIC_HOSTS": "texttraits.example",
            "TEXTTRAITS_DATABASE_URL": "",
            "DATABASE_URL": "postgresql://postgres.projectref:secret@aws-0-us-east-1.pooler.supabase.com:5432/postgres",
            "TEXTTRAITS_DB_SSLMODE": "require",
            "TEXTTRAITS_SECURE_COOKIES": "true",
            "TEXTTRAITS_EMAIL_PROVIDER": "smtp",
            "TEXTTRAITS_FROM_EMAIL": "no-reply@texttraits.example",
            "TEXTTRAITS_SMTP_HOST": "smtp.example.com",
            "TEXTTRAITS_SMTP_USERNAME": "apikey",
            "TEXTTRAITS_SMTP_PASSWORD": "secret",
        }
    )
    assert_true(wrong_host.returncode == 1, "production base URL should be checked against allowed hosts")

    print("Configuration regression checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
