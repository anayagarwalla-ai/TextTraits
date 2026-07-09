from __future__ import annotations

from dataclasses import dataclass, asdict
import base64
import hashlib
import hmac
import json
import os
import urllib.parse
import urllib.request


@dataclass(frozen=True)
class IntegrationProvider:
    name: str
    category: str
    status: str
    auth: str
    scopes: tuple[str, ...]
    setup_steps: tuple[str, ...]
    client_id_env: str = ""
    client_secret_env: str = ""
    auth_url: str = ""
    token_url: str = ""

    def public_dict(self) -> dict:
        payload = asdict(self)
        payload["slug"] = slug(self.name)
        payload["configured"] = self.configured()
        missing = self.missing_env()
        payload["missing_env"] = tuple(name for name in missing if name != self.client_secret_env)
        payload["missing_credentials"] = bool(missing)
        payload["missing_secret"] = bool(self.client_secret_env and not os.getenv(self.client_secret_env))
        payload.pop("client_secret_env", None)
        return payload

    def configured(self) -> bool:
        if not self.client_id_env:
            return self.status != "needs_credentials"
        return bool(os.getenv(self.client_id_env) and os.getenv(self.client_secret_env))

    def missing_env(self) -> tuple[str, ...]:
        missing = []
        if self.client_id_env and not os.getenv(self.client_id_env):
            missing.append(self.client_id_env)
        if self.client_secret_env and not os.getenv(self.client_secret_env):
            missing.append(self.client_secret_env)
        return tuple(missing)


# client_secret_env values below are environment variable names, not secret values.
PROVIDERS: tuple[IntegrationProvider, ...] = (
    IntegrationProvider(
        name="HubSpot",
        category="CRM",
        status="needs_credentials",
        auth="OAuth 2.0",
        scopes=(
            "oauth",
            "crm.objects.contacts.read",
            "crm.objects.contacts.write",
            "crm.objects.companies.read",
            "crm.objects.companies.write",
            "crm.objects.deals.read",
            "crm.objects.deals.write",
            "tickets",
            "crm.objects.owners.read",
            "crm.objects.custom.read",
            "crm.objects.custom.write",
            "crm.lists.read",
            "crm.lists.write",
            "marketing.campaigns.read",
            "marketing.campaigns.write",
            "marketing.campaigns.revenue.read",
            "marketing-email",
            "timeline",
            "automation",
        ),
        setup_steps=("Create a HubSpot project app.", "Add OAuth redirect URL.", "Map CRM objects, campaign assets, workflow outputs, and review writeback fields."),
        client_id_env="HUBSPOT_CLIENT_ID",
        client_secret_env="HUBSPOT_CLIENT_SECRET",  # nosec B106
        auth_url="https://app.hubspot.com/oauth/authorize",
        token_url="https://api.hubapi.com/oauth/2026-03/token",
    ),
    IntegrationProvider(
        name="Salesforce",
        category="CRM",
        status="needs_credentials",
        auth="OAuth 2.0",
        scopes=("api", "refresh_token", "contacts", "leads", "tasks"),
        setup_steps=("Create a connected app.", "Configure OAuth scopes.", "Map lead/contact fields and activity export fields."),
        client_id_env="SALESFORCE_CLIENT_ID",
        client_secret_env="SALESFORCE_CLIENT_SECRET",  # nosec B106
        auth_url="https://login.salesforce.com/services/oauth2/authorize",
        token_url="https://login.salesforce.com/services/oauth2/token",
    ),
    IntegrationProvider(
        name="Outreach",
        category="Sales engagement",
        status="needs_credentials",
        auth="OAuth 2.0",
        scopes=("prospects.read", "prospects.write", "sequences.write"),
        setup_steps=("Create an Outreach app.", "Configure OAuth redirect.", "Map sequence and prospect fields."),
        client_id_env="OUTREACH_CLIENT_ID",
        client_secret_env="OUTREACH_CLIENT_SECRET",  # nosec B106
        auth_url="https://api.outreach.io/oauth/authorize",
        token_url="https://api.outreach.io/oauth/token",
    ),
    IntegrationProvider(
        name="Salesloft",
        category="Sales engagement",
        status="needs_credentials",
        auth="OAuth 2.0",
        scopes=("people:read", "people:write", "cadences:write"),
        setup_steps=("Create a Salesloft app.", "Configure scopes.", "Map cadence and person fields."),
        client_id_env="SALESLOFT_CLIENT_ID",
        client_secret_env="SALESLOFT_CLIENT_SECRET",  # nosec B106
        auth_url="https://accounts.salesloft.com/oauth/authorize",
        token_url="https://accounts.salesloft.com/oauth/token",
    ),
    IntegrationProvider(
        name="Gmail",
        category="Inbox",
        status="needs_credentials",
        auth="Google OAuth",
        scopes=("gmail.readonly", "gmail.modify", "gmail.compose"),
        setup_steps=("Create a Google Cloud OAuth client.", "Verify consent screen.", "Connect reply triage and draft creation."),
        client_id_env="GOOGLE_CLIENT_ID",
        client_secret_env="GOOGLE_CLIENT_SECRET",  # nosec B106
        auth_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
    ),
    IntegrationProvider(
        name="Outlook",
        category="Inbox",
        status="needs_credentials",
        auth="Microsoft OAuth",
        scopes=("Mail.Read", "Mail.ReadWrite", "Mail.Send"),
        setup_steps=("Create an Azure app registration.", "Configure delegated mail scopes.", "Connect reply triage and draft creation."),
        client_id_env="MICROSOFT_CLIENT_ID",
        client_secret_env="MICROSOFT_CLIENT_SECRET",  # nosec B106
        auth_url="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        token_url="https://login.microsoftonline.com/common/oauth2/v2.0/token",
    ),
    IntegrationProvider(
        name="Chrome Sidebar",
        category="Browser extension",
        status="packaging_required",
        auth="Extension bridge",
        scopes=("activeTab", "storage", "identity"),
        setup_steps=("Package the extension shell.", "Add allowed origins.", "Wire current-page extraction and write-back actions."),
    ),
)


def slug(name: str) -> str:
    return name.lower().replace(" ", "-")


def provider_names() -> set[str]:
    return {provider.name for provider in PROVIDERS}


def get_provider(name_or_slug: str) -> IntegrationProvider | None:
    clean = name_or_slug.strip().lower()
    for provider in PROVIDERS:
        if provider.name.lower() == clean or slug(provider.name) == clean:
            return provider
    return None


def public_providers() -> list[dict]:
    return [provider.public_dict() for provider in PROVIDERS]


def configured_count() -> int:
    return sum(1 for provider in PROVIDERS if provider.configured())


def build_authorization_url(provider: IntegrationProvider, redirect_uri: str, state: str) -> str:
    if not provider.auth_url or not provider.configured():
        raise ValueError("Provider is not configured for OAuth.")
    require_https(provider.auth_url)
    require_https(redirect_uri)
    scopes = " ".join(provider.scopes)
    query = {
        "client_id": os.getenv(provider.client_id_env, ""),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scopes,
        "state": state,
    }
    if provider.name == "Gmail":
        query["access_type"] = "offline"
        query["prompt"] = "consent"
    return f"{provider.auth_url}?{urllib.parse.urlencode(query)}"


def exchange_oauth_code(provider: IntegrationProvider, redirect_uri: str, code: str) -> dict:
    if not provider.token_url or not provider.configured():
        raise ValueError("Provider is not configured for OAuth.")
    require_https(provider.token_url)
    require_https(redirect_uri)
    payload = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": os.getenv(provider.client_id_env, ""),
            "client_secret": os.getenv(provider.client_secret_env, ""),
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        provider.token_url,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:  # nosec B310
        token_payload = json.loads(response.read().decode("utf-8"))
    store_tokens = os.getenv("TEXTTRAITS_STORE_OAUTH_TOKENS", "").strip().lower() in {"1", "true", "yes", "on"}
    if not store_tokens:
        token_payload.pop("access_token", None)
        token_payload.pop("refresh_token", None)
    return token_payload


def require_https(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
        return
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("OAuth endpoints and redirect URIs must use HTTPS.")


def encoded_state(user_id: int, provider_name: str, nonce: str) -> str:
    payload = json.dumps({"user_id": user_id, "provider": provider_name, "nonce": nonce}, separators=(",", ":"))
    encoded = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("utf-8")
    signature = hmac.new(state_secret(), encoded.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def decoded_state(value: str) -> dict:
    encoded, signature = value.rsplit(".", 1)
    expected = hmac.new(state_secret(), encoded.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise ValueError("OAuth state signature mismatch.")
    return json.loads(base64.urlsafe_b64decode(encoded.encode("utf-8")).decode("utf-8"))


def state_secret() -> bytes:
    return os.getenv("TEXTTRAITS_SECRET_KEY", "dev-texttraits-change-me").encode("utf-8")
