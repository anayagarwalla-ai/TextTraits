from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "texttraits_app"))
from env_loader import load_env_file  # noqa: E402

load_env_file(ROOT / ".env")

REQUIRED_PRODUCTION_ENV = (
    "TEXTTRAITS_SECRET_KEY",
    "TEXTTRAITS_PUBLIC_BASE_URL",
)


def fail(message: str, failures: list[str]) -> None:
    failures.append(message)


def main() -> int:
    failures: list[str] = []
    warnings: list[str] = []
    production = os.getenv("TEXTTRAITS_ENV", "").lower() == "production"
    database_url = os.getenv("TEXTTRAITS_DATABASE_URL") or os.getenv("DATABASE_URL") or ""
    email_provider = os.getenv("TEXTTRAITS_EMAIL_PROVIDER", "").lower()
    db_origin = urlparse(database_url)

    if production:
        for name in REQUIRED_PRODUCTION_ENV:
            if not os.getenv(name):
                fail(f"Missing {name}.", failures)
        if os.getenv("TEXTTRAITS_SECRET_KEY", "").startswith(("dev-", "replace-")):
            fail("TEXTTRAITS_SECRET_KEY must be a real high-entropy secret.", failures)
        if not database_url.startswith(("postgres://", "postgresql://")):
            fail("Production must use DATABASE_URL or TEXTTRAITS_DATABASE_URL pointing to hosted Postgres.", failures)
        elif db_origin.hostname not in {"localhost", "127.0.0.1", "::1", ""} and "sslmode=require" not in database_url and os.getenv("TEXTTRAITS_DB_SSLMODE") != "require":
            fail("Production Postgres must require SSL. Set TEXTTRAITS_DB_SSLMODE=require or include sslmode=require in the URL.", failures)
        if os.getenv("TEXTTRAITS_SECURE_COOKIES", "").lower() not in {"1", "true", "yes", "on"}:
            fail("TEXTTRAITS_SECURE_COOKIES=true is required behind HTTPS.", failures)
        if os.getenv("ENABLE_DEV_TOOLS", "").lower() in {"1", "true", "yes", "on"}:
            fail("ENABLE_DEV_TOOLS=false is required in production.", failures)
        if os.getenv("TEXTTRAITS_ALLOW_DEMO", "").lower() in {"1", "true", "yes", "on"}:
            fail("TEXTTRAITS_ALLOW_DEMO=false is required in production.", failures)
        if os.getenv("TEXTTRAITS_DEV_ACCOUNT_LINKS", "").lower() in {"1", "true", "yes", "on"}:
            fail("TEXTTRAITS_DEV_ACCOUNT_LINKS=false is required in production.", failures)
        if os.getenv("TEXTTRAITS_REQUIRE_ENTERPRISE_BROWSER_AUTH", "true").lower() not in {"1", "true", "yes", "on"}:
            fail("TEXTTRAITS_REQUIRE_ENTERPRISE_BROWSER_AUTH=true is required in production.", failures)
        if os.getenv("TEXTTRAITS_API_KEY", "").strip() and not (
            os.getenv("TEXTTRAITS_API_KEY_SHA256", "").strip() or os.getenv("TEXTTRAITS_API_KEY_HASHES", "").strip()
        ):
            fail("Use TEXTTRAITS_API_KEY_SHA256 or TEXTTRAITS_API_KEY_HASHES instead of plaintext TEXTTRAITS_API_KEY in production.", failures)
        public_origin = urlparse(os.getenv("TEXTTRAITS_PUBLIC_BASE_URL", ""))
        public_hostname = (public_origin.hostname or "").lower()
        if public_origin.scheme != "https":
            fail("TEXTTRAITS_PUBLIC_BASE_URL must be an HTTPS URL in production.", failures)
        if not public_origin.netloc:
            fail("TEXTTRAITS_PUBLIC_BASE_URL must include a public host.", failures)
        unspecified_ipv4 = ".".join(("0", "0", "0", "0"))
        if public_hostname in {"localhost", "127.0.0.1", "::1", unspecified_ipv4}:
            fail("TEXTTRAITS_PUBLIC_BASE_URL cannot point to localhost in production.", failures)
        allowed_hosts = {
            host.strip().lower()
            for host in os.getenv("TEXTTRAITS_ALLOWED_PUBLIC_HOSTS", "").split(",")
            if host.strip()
        }
        if allowed_hosts and public_hostname not in allowed_hosts:
            fail("TEXTTRAITS_PUBLIC_BASE_URL host must be listed in TEXTTRAITS_ALLOWED_PUBLIC_HOSTS.", failures)

    if email_provider == "smtp":
        for name in ("TEXTTRAITS_FROM_EMAIL", "TEXTTRAITS_SMTP_HOST", "TEXTTRAITS_SMTP_USERNAME", "TEXTTRAITS_SMTP_PASSWORD"):
            if not os.getenv(name):
                fail(f"SMTP delivery selected but {name} is missing.", failures)
        if production and os.getenv("TEXTTRAITS_SMTP_TLS", "true").lower() not in {"1", "true", "yes", "on"}:
            fail("TEXTTRAITS_SMTP_TLS=true is required in production.", failures)
    elif email_provider == "sendgrid":
        for name in ("TEXTTRAITS_FROM_EMAIL", "TEXTTRAITS_SENDGRID_API_KEY"):
            if not os.getenv(name):
                fail(f"SendGrid delivery selected but {name} is missing.", failures)
    elif production:
        fail("Configure TEXTTRAITS_EMAIL_PROVIDER=smtp or sendgrid for production account emails.", failures)
    if production and email_provider == "console":
        fail("TEXTTRAITS_EMAIL_PROVIDER=console is not allowed in production.", failures)

    if production and not os.getenv("SENTRY_DSN"):
        warnings.append("SENTRY_DSN is not set; server/client error reporting will be log-only.")

    oauth_groups = {
        "HubSpot": ("HUBSPOT_CLIENT_ID", "HUBSPOT_CLIENT_SECRET"),
        "Salesforce": ("SALESFORCE_CLIENT_ID", "SALESFORCE_CLIENT_SECRET"),
        "Gmail": ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"),
        "Outlook": ("MICROSOFT_CLIENT_ID", "MICROSOFT_CLIENT_SECRET"),
    }
    for provider, names in oauth_groups.items():
        if any(os.getenv(name) for name in names) and not all(os.getenv(name) for name in names):
            fail(f"{provider} OAuth is partially configured; set both {', '.join(names)}.", failures)

    for warning in warnings:
        print(f"WARNING: {warning}")
    if failures:
        for failure in failures:
            print(f"ERROR: {failure}", file=sys.stderr)
        return 1
    print("TextTraits preflight checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
