from __future__ import annotations

import os
import sys
from urllib.parse import urlparse


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

    if production:
        for name in REQUIRED_PRODUCTION_ENV:
            if not os.getenv(name):
                fail(f"Missing {name}.", failures)
        if os.getenv("TEXTTRAITS_SECRET_KEY", "").startswith(("dev-", "replace-")):
            fail("TEXTTRAITS_SECRET_KEY must be a real high-entropy secret.", failures)
        if not database_url.startswith(("postgres://", "postgresql://")):
            fail("Production must use DATABASE_URL or TEXTTRAITS_DATABASE_URL pointing to hosted Postgres.", failures)
        if os.getenv("TEXTTRAITS_SECURE_COOKIES", "").lower() not in {"1", "true", "yes", "on"}:
            fail("TEXTTRAITS_SECURE_COOKIES=true is required behind HTTPS.", failures)
        public_origin = urlparse(os.getenv("TEXTTRAITS_PUBLIC_BASE_URL", ""))
        if public_origin.scheme != "https":
            fail("TEXTTRAITS_PUBLIC_BASE_URL must be an HTTPS URL in production.", failures)

    if email_provider == "smtp":
        for name in ("TEXTTRAITS_FROM_EMAIL", "TEXTTRAITS_SMTP_HOST", "TEXTTRAITS_SMTP_USERNAME", "TEXTTRAITS_SMTP_PASSWORD"):
            if not os.getenv(name):
                fail(f"SMTP delivery selected but {name} is missing.", failures)
    elif email_provider == "sendgrid":
        for name in ("TEXTTRAITS_FROM_EMAIL", "TEXTTRAITS_SENDGRID_API_KEY"):
            if not os.getenv(name):
                fail(f"SendGrid delivery selected but {name} is missing.", failures)
    elif production:
        fail("Configure TEXTTRAITS_EMAIL_PROVIDER=smtp or sendgrid for production account emails.", failures)

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
