from __future__ import annotations

import json
import logging
import os
import re
import socket
import threading
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any

import certifi
import urllib3
from runtime_config import env_int

from storage import (
    get_hubspot_portal_connection,
    hubspot_connection_has_scopes,
    log_event,
    token_storage_status,
    update_hubspot_portal_access_token,
)


HUBSPOT_API_BASE_URL = os.getenv("HUBSPOT_API_BASE_URL", "https://api.hubapi.com").rstrip("/")
HUBSPOT_OAUTH_TOKEN_URL = os.getenv("HUBSPOT_OAUTH_TOKEN_URL", "https://api.hubapi.com/oauth/2026-03/token")
DEFAULT_TIMEOUT_SECONDS = env_int("TEXTTRAITS_HUBSPOT_API_TIMEOUT_SECONDS", 20, minimum=1, maximum=120)
CRM_WRITE_SCOPES = {
    "contacts": "crm.objects.contacts.write",
    "companies": "crm.objects.companies.write",
    "deals": "crm.objects.deals.write",
    "tickets": "tickets",
}
CRM_READ_SCOPES = {
    "contacts": "crm.objects.contacts.read",
    "companies": "crm.objects.companies.read",
    "deals": "crm.objects.deals.read",
    "tickets": "tickets",
}
_REFRESH_LOCKS: dict[str, threading.Lock] = {}
_REFRESH_LOCKS_GUARD = threading.Lock()
_HTTP_POOL = urllib3.PoolManager(
    num_pools=20,
    maxsize=20,
    block=True,
    cert_reqs="CERT_REQUIRED",
    ca_certs=certifi.where(),
)


class HubSpotClientError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502, payload: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}


class HubSpotNotConnectedError(HubSpotClientError):
    pass


class HubSpotScopeError(HubSpotClientError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_expires_at(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _json_request(url: str, method: str, body: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> tuple[int, dict[str, Any]]:
    data: bytes | None = None
    request_headers = dict(headers or {})
    if body is not None:
        data = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    try:
        response = _HTTP_POOL.request(
            method.upper(),
            url,
            body=data,
            headers=request_headers,
            timeout=urllib3.Timeout(total=timeout),
            retries=False,
        )
        raw = response.data.decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"raw": raw[:1000]}
        return int(response.status), payload
    except (urllib3.exceptions.HTTPError, TimeoutError, socket.timeout) as error:
        return 599, {"error": "HubSpot network request failed.", "reason": str(getattr(error, "reason", error))[:240]}


def _form_request(url: str, payload: dict[str, Any], timeout: int = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    data = urllib.parse.urlencode(payload).encode("utf-8")
    try:
        response = _HTTP_POOL.request(
            "POST",
            url,
            body=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=urllib3.Timeout(total=timeout),
            retries=False,
        )
        raw = response.data.decode("utf-8", errors="replace")
        try:
            details = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            details = {"raw": raw[:1000]}
        if 200 <= int(response.status) < 300:
            return details
        raise HubSpotClientError("HubSpot OAuth token refresh failed.", status_code=502, payload=details)
    except HubSpotClientError:
        raise
    except (urllib3.exceptions.HTTPError, TimeoutError, socket.timeout) as error:
        raise HubSpotClientError(
            "HubSpot OAuth token refresh could not reach HubSpot.",
            status_code=502,
            payload={"reason": str(getattr(error, "reason", error))[:240]},
        ) from error


def _append_query(path: str, params: dict[str, Any] | None) -> str:
    clean_params = {key: value for key, value in (params or {}).items() if value not in (None, "")}
    if not clean_params:
        return path
    separator = "&" if "?" in path else "?"
    return path + separator + urllib.parse.urlencode(clean_params, doseq=True)


def _safe_path_segment(value: Any) -> str:
    return urllib.parse.quote(str(value or "").strip(), safe="")


def crm_write_scope(object_type: str) -> str:
    clean = str(object_type or "").strip().lower()
    return CRM_WRITE_SCOPES.get(clean, "crm.objects.custom.write" if clean.startswith(("2-", "p_")) else f"crm.objects.{clean}.write")


def crm_read_scope(object_type: str) -> str:
    clean = str(object_type or "").strip().lower()
    return CRM_READ_SCOPES.get(clean, "crm.objects.custom.read" if clean.startswith(("2-", "p_")) else f"crm.objects.{clean}.read")


def _audit_path_template(path: str) -> str:
    route = str(path or "").split("?", 1)[0]
    clean_segments: list[str] = []
    for segment in route.split("/"):
        if not segment:
            continue
        decoded = urllib.parse.unquote(segment)
        if decoded in {"v1", "v3", "2026-03"}:
            clean_segments.append(decoded)
        elif decoded.isdigit() or re.fullmatch(r"[0-9a-fA-F-]{12,}", decoded) or (len(decoded) > 10 and any(char.isdigit() for char in decoded)):
            clean_segments.append("{id}")
        else:
            clean_segments.append(decoded[:80])
    return "/" + "/".join(clean_segments)


def _api_version_from_path(path: str) -> str:
    match = re.search(r"/(\d{4}-\d{2})(?:/|$)", path)
    return match.group(1) if match else "unversioned"


def _request_is_replay_safe(method: str, idempotency_key: str) -> bool:
    return method.upper() in {"GET", "HEAD", "OPTIONS", "PUT", "DELETE"} or bool(idempotency_key)


def _audit_hubspot_api_event(portal_id: str, event_type: str, payload: dict[str, Any]) -> None:
    if os.getenv("TEXTTRAITS_DISABLE_HUBSPOT_API_AUDIT", "").strip().lower() in {"1", "true", "yes", "on"}:
        return
    try:
        log_event(None, event_type, {"portal_id": str(portal_id or "")[:160], **payload})
    except Exception:
        logging.exception("hubspot_api_audit_failed")


def _refresh_lock(portal_id: str) -> threading.Lock:
    with _REFRESH_LOCKS_GUARD:
        return _REFRESH_LOCKS.setdefault(portal_id, threading.Lock())


class HubSpotApiClient:
    def __init__(self, portal_id: str) -> None:
        self.portal_id = str(portal_id or "").strip()
        if not self.portal_id:
            raise HubSpotNotConnectedError("HubSpot portal_id is required.", status_code=400)
        self._connection_cache: dict[str, Any] | None = None

    def _connection(self, include_tokens: bool = False, refresh: bool = False) -> dict[str, Any]:
        cached = self._connection_cache
        if cached is not None and not refresh:
            tokens_available = bool(cached.get("access_token") or cached.get("refresh_token"))
            if not include_tokens or tokens_available:
                return cached
        connection = get_hubspot_portal_connection(self.portal_id, include_tokens=include_tokens)
        if not connection or connection.get("status") == "disconnected":
            raise HubSpotNotConnectedError(
                "This HubSpot portal is not connected to TextTraits with stored OAuth tokens.",
                status_code=409,
                payload={"portal_id": self.portal_id, "token_storage": token_storage_status()},
            )
        if include_tokens and not (connection.get("access_token") or connection.get("refresh_token")):
            raise HubSpotNotConnectedError(
                "This HubSpot portal was installed, but encrypted OAuth tokens are not available.",
                status_code=409,
                payload={"portal_id": self.portal_id, "token_storage": token_storage_status()},
            )
        self._connection_cache = connection
        return connection

    @staticmethod
    def _validate_scopes(connection: dict[str, Any], required_scopes: tuple[str, ...]) -> None:
        if not hubspot_connection_has_scopes(connection, required_scopes):
            raise HubSpotScopeError(
                "The installed HubSpot app is missing scopes required for this action.",
                status_code=403,
                payload={"required_scopes": list(required_scopes), "granted_scopes": connection.get("scopes", [])},
            )

    def require_scopes(self, required_scopes: tuple[str, ...] = ()) -> None:
        connection = self._connection(include_tokens=False)
        self._validate_scopes(connection, required_scopes)

    def ensure_connected(self, required_scopes: tuple[str, ...] = ()) -> dict[str, Any]:
        connection = self._connection(include_tokens=True)
        self._validate_scopes(connection, required_scopes)
        return connection

    def _access_token(self, required_scopes: tuple[str, ...] = ()) -> str:
        connection = self._connection(include_tokens=True)
        self._validate_scopes(connection, required_scopes)
        expires_at = _parse_expires_at(str(connection.get("expires_at") or ""))
        if expires_at and expires_at <= _utc_now() + timedelta(seconds=60) and connection.get("refresh_token"):
            connection = self.refresh_access_token(force=False)
        token = str(connection.get("access_token") or "")
        if not token:
            connection = self.refresh_access_token(force=False)
            token = str(connection.get("access_token") or "")
        if not token:
            raise HubSpotNotConnectedError("HubSpot access token is unavailable for this portal.", status_code=409)
        return token

    def refresh_access_token(self, force: bool = True) -> dict[str, Any]:
        with _refresh_lock(self.portal_id):
            connection = self._connection(include_tokens=True, refresh=True)
            expires_at = _parse_expires_at(str(connection.get("expires_at") or ""))
            if not force and connection.get("access_token") and expires_at and expires_at > _utc_now() + timedelta(seconds=60):
                return connection
            refresh_token = str(connection.get("refresh_token") or "")
            if not refresh_token:
                raise HubSpotNotConnectedError("HubSpot refresh token is unavailable for this portal.", status_code=409)
            client_id = os.getenv("HUBSPOT_CLIENT_ID", "").strip()
            client_secret = os.getenv("HUBSPOT_CLIENT_SECRET", "").strip()
            if not client_id or not client_secret:
                raise HubSpotClientError("Configure HUBSPOT_CLIENT_ID and HUBSPOT_CLIENT_SECRET before refreshing HubSpot tokens.", status_code=503)
            payload = _form_request(
                HUBSPOT_OAUTH_TOKEN_URL,
                {
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
            )
            if not payload.get("refresh_token"):
                payload["refresh_token"] = refresh_token
            updated = update_hubspot_portal_access_token(self.portal_id, payload) | {
                "access_token": payload.get("access_token", ""),
                "refresh_token": payload.get("refresh_token", refresh_token),
            }
            self._connection_cache = updated
            _audit_hubspot_api_event(
                self.portal_id,
                "hubspot_oauth_token_refreshed",
                {"expires_at": updated.get("expires_at"), "scopes": updated.get("scopes", [])},
            )
            return updated

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        required_scopes: tuple[str, ...] = (),
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        token = self._access_token(required_scopes)
        url = f"{HUBSPOT_API_BASE_URL}{_append_query(path, params)}"
        headers = {"Authorization": f"Bearer {token}"}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        last_payload: dict[str, Any] = {}
        started = time.monotonic()
        path_template = _audit_path_template(path)
        api_version = _api_version_from_path(path)
        for attempt in range(3):
            status_code, payload = _json_request(url, method, body=body, headers=headers)
            last_payload = payload
            if status_code == 401 and attempt == 0:
                _audit_hubspot_api_event(
                    self.portal_id,
                    "hubspot_api_token_refresh_retry",
                    {
                        "method": method.upper(),
                        "path": path_template,
                        "api_version": api_version,
                        "status_code": status_code,
                        "attempt": attempt + 1,
                    },
                )
                token = str(self.refresh_access_token(force=True).get("access_token") or "")
                headers["Authorization"] = f"Bearer {token}"
                continue
            if status_code in {429, 500, 502, 503, 504, 599} and attempt < 2 and _request_is_replay_safe(method, idempotency_key):
                retry_after = payload.get("retryAfter") or payload.get("retry_after") or ""
                try:
                    delay = min(3.0, max(0.25, float(retry_after)))
                except (TypeError, ValueError):
                    delay = 0.5 * (attempt + 1)
                _audit_hubspot_api_event(
                    self.portal_id,
                    "hubspot_api_retry_scheduled",
                    {
                        "method": method.upper(),
                        "path": path_template,
                        "api_version": api_version,
                        "status_code": status_code,
                        "attempt": attempt + 1,
                        "delay_seconds": round(delay, 3),
                    },
                )
                time.sleep(delay)
                continue
            if 200 <= status_code < 300:
                _audit_hubspot_api_event(
                    self.portal_id,
                    "hubspot_api_request",
                    {
                        "method": method.upper(),
                        "path": path_template,
                        "api_version": api_version,
                        "status_code": status_code,
                        "attempts": attempt + 1,
                        "duration_ms": round((time.monotonic() - started) * 1000, 2),
                        "required_scopes": list(required_scopes),
                        "idempotency_key_present": bool(idempotency_key),
                    },
                )
                return {"status_code": status_code, "body": payload}
            logging.warning(
                "hubspot_api_error status=%s method=%s path=%s error_keys=%s",
                status_code,
                method.upper(),
                path_template,
                sorted(str(key)[:80] for key in payload.keys())[:20] if isinstance(payload, dict) else [],
            )
            _audit_hubspot_api_event(
                self.portal_id,
                "hubspot_api_request_failed",
                {
                    "method": method.upper(),
                    "path": path_template,
                    "api_version": api_version,
                    "status_code": status_code,
                    "attempts": attempt + 1,
                    "duration_ms": round((time.monotonic() - started) * 1000, 2),
                    "required_scopes": list(required_scopes),
                    "idempotency_key_present": bool(idempotency_key),
                    "error_keys": sorted(str(key)[:80] for key in payload.keys())[:20] if isinstance(payload, dict) else [],
                },
            )
            raise HubSpotClientError("HubSpot API request failed.", status_code=status_code, payload=payload)
        _audit_hubspot_api_event(
            self.portal_id,
            "hubspot_api_request_failed",
            {
                "method": method.upper(),
                "path": path_template,
                "api_version": api_version,
                "status_code": 502,
                "attempts": 3,
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
                "required_scopes": list(required_scopes),
                "idempotency_key_present": bool(idempotency_key),
                "error_keys": sorted(str(key)[:80] for key in last_payload.keys())[:20] if isinstance(last_payload, dict) else [],
            },
        )
        raise HubSpotClientError("HubSpot API request failed after retries.", status_code=502, payload=last_payload)

    def create_campaign(self, properties: dict[str, Any], idempotency_key: str = "") -> dict[str, Any]:
        return self.request(
            "POST",
            "/marketing/v3/campaigns",
            body={"properties": properties},
            required_scopes=("marketing.campaigns.write",),
            idempotency_key=idempotency_key,
        )

    def get_property(self, object_type: str, property_name: str) -> dict[str, Any]:
        return self.request(
            "GET",
            f"/crm/properties/2026-03/{_safe_path_segment(object_type)}/{_safe_path_segment(property_name)}",
            required_scopes=(crm_write_scope(object_type),),
        )

    def create_property(self, object_type: str, payload: dict[str, Any], idempotency_key: str = "") -> dict[str, Any]:
        return self.request(
            "POST",
            f"/crm/properties/2026-03/{_safe_path_segment(object_type)}",
            body=payload,
            required_scopes=(crm_write_scope(object_type),),
            idempotency_key=idempotency_key,
        )

    def list_custom_object_schemas(self) -> dict[str, Any]:
        return self.request(
            "GET",
            "/crm-object-schemas/2026-03/schemas",
            required_scopes=("crm.objects.custom.read",),
        )

    def get_custom_object_schema(self, object_type: str) -> dict[str, Any]:
        return self.request(
            "GET",
            f"/crm-object-schemas/2026-03/schemas/{_safe_path_segment(object_type)}",
            required_scopes=("crm.objects.custom.read",),
        )

    def create_custom_object_schema(self, payload: dict[str, Any], idempotency_key: str = "") -> dict[str, Any]:
        return self.request(
            "POST",
            "/crm-object-schemas/2026-03/schemas",
            body=payload,
            required_scopes=("crm.objects.custom.write",),
            idempotency_key=idempotency_key,
        )

    def get_webhook_settings(self, app_id: str) -> dict[str, Any]:
        return self.request(
            "GET",
            f"/webhooks/2026-03/{_safe_path_segment(app_id)}/settings",
            required_scopes=(),
        )

    def update_webhook_settings(self, app_id: str, payload: dict[str, Any], idempotency_key: str = "") -> dict[str, Any]:
        return self.request(
            "PUT",
            f"/webhooks/2026-03/{_safe_path_segment(app_id)}/settings",
            body=payload,
            required_scopes=(),
            idempotency_key=idempotency_key,
        )

    def list_webhook_subscriptions(self, app_id: str) -> dict[str, Any]:
        return self.request(
            "GET",
            f"/webhooks/2026-03/{_safe_path_segment(app_id)}/subscriptions",
            required_scopes=(),
        )

    def create_webhook_subscription(self, app_id: str, payload: dict[str, Any], idempotency_key: str = "") -> dict[str, Any]:
        return self.request(
            "POST",
            f"/webhooks/2026-03/{_safe_path_segment(app_id)}/subscriptions",
            body=payload,
            required_scopes=(),
            idempotency_key=idempotency_key,
        )

    def get_campaign(self, campaign_guid: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.request(
            "GET",
            f"/marketing/v3/campaigns/{_safe_path_segment(campaign_guid)}",
            params=params,
            required_scopes=("marketing.campaigns.read",),
        )

    def list_campaigns(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.request(
            "GET",
            "/marketing/v3/campaigns",
            params=params,
            required_scopes=("marketing.campaigns.read",),
        )

    def update_campaign(self, campaign_guid: str, properties: dict[str, Any], idempotency_key: str = "") -> dict[str, Any]:
        return self.request(
            "PATCH",
            f"/marketing/v3/campaigns/{_safe_path_segment(campaign_guid)}",
            body={"properties": properties},
            required_scopes=("marketing.campaigns.write",),
            idempotency_key=idempotency_key,
        )

    def associate_campaign_asset(self, campaign_guid: str, asset_type: str, asset_id: str, idempotency_key: str = "") -> dict[str, Any]:
        return self.request(
            "PUT",
            f"/marketing/v3/campaigns/{_safe_path_segment(campaign_guid)}/assets/{_safe_path_segment(asset_type)}/{_safe_path_segment(asset_id)}",
            required_scopes=("marketing.campaigns.write",),
            idempotency_key=idempotency_key,
        )

    def remove_campaign_asset(self, campaign_guid: str, asset_type: str, asset_id: str, idempotency_key: str = "") -> dict[str, Any]:
        return self.request(
            "DELETE",
            f"/marketing/v3/campaigns/{_safe_path_segment(campaign_guid)}/assets/{_safe_path_segment(asset_type)}/{_safe_path_segment(asset_id)}",
            required_scopes=("marketing.campaigns.write",),
            idempotency_key=idempotency_key,
        )

    def list_campaign_assets(self, campaign_guid: str, asset_type: str = "MARKETING_EMAIL", params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.request(
            "GET",
            f"/marketing/v3/campaigns/{_safe_path_segment(campaign_guid)}/assets/{_safe_path_segment(asset_type)}",
            params=params,
            required_scopes=("marketing.campaigns.read",),
        )

    def create_marketing_email(self, payload: dict[str, Any], idempotency_key: str = "") -> dict[str, Any]:
        return self.request(
            "POST",
            "/marketing/v3/emails",
            body=payload,
            required_scopes=("marketing-email",),
            idempotency_key=idempotency_key,
        )

    def update_marketing_email(self, email_id: str, payload: dict[str, Any], idempotency_key: str = "") -> dict[str, Any]:
        return self.request(
            "PATCH",
            f"/marketing/v3/emails/{_safe_path_segment(email_id)}",
            body=payload,
            required_scopes=("marketing-email",),
            idempotency_key=idempotency_key,
        )

    def get_marketing_email(self, email_id: str) -> dict[str, Any]:
        return self.request(
            "GET",
            f"/marketing/v3/emails/{_safe_path_segment(email_id)}",
            required_scopes=("marketing-email",),
        )

    def list_marketing_emails(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.request(
            "GET",
            "/marketing/v3/emails",
            params=params,
            required_scopes=("marketing-email",),
        )

    def list_owners(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.request(
            "GET",
            "/crm/owners/2026-03",
            params=params,
            required_scopes=("crm.objects.owners.read",),
        )

    def get_campaign_asset_copy(self, asset_type: str, asset_id: str) -> dict[str, Any]:
        clean_type = str(asset_type or "").strip().upper()
        safe_id = _safe_path_segment(asset_id)
        paths = {
            "MARKETING_EMAIL": f"/marketing/v3/emails/{safe_id}",
            "FORM": f"/marketing/v3/forms/{safe_id}",
            "LANDING_PAGE": f"/cms/pages/2026-03/landing-pages/{safe_id}",
            "SITE_PAGE": f"/cms/pages/2026-03/site-pages/{safe_id}",
            "BLOG_POST": f"/cms/blogs/2026-03/posts/{safe_id}",
            "SEQUENCE": f"/automation/sequences/2026-03/{safe_id}",
        }
        scopes = {
            "MARKETING_EMAIL": ("marketing-email",),
            "FORM": ("forms",),
            "SEQUENCE": ("automation",),
        }
        path = paths.get(clean_type)
        if not path:
            raise HubSpotClientError(
                "Direct copy fetch is not configured for this HubSpot campaign asset type.",
                status_code=422,
                payload={"asset_type": clean_type},
            )
        return self.request("GET", path, required_scopes=scopes.get(clean_type, ()))

    def create_task(self, properties: dict[str, Any], associations: list[dict[str, Any]] | None = None, idempotency_key: str = "") -> dict[str, Any]:
        body: dict[str, Any] = {"properties": properties}
        if associations:
            body["associations"] = associations
        return self.request(
            "POST",
            "/crm/objects/2026-03/tasks",
            body=body,
            required_scopes=(),
            idempotency_key=idempotency_key,
        )

    def update_task(self, task_id: str, properties: dict[str, Any], idempotency_key: str = "") -> dict[str, Any]:
        return self.request(
            "PATCH",
            f"/crm/objects/2026-03/tasks/{_safe_path_segment(task_id)}",
            body={"properties": properties},
            required_scopes=(),
            idempotency_key=idempotency_key,
        )

    def search_crm_objects(self, object_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request(
            "POST",
            f"/crm/objects/2026-03/{_safe_path_segment(object_type)}/search",
            body=payload,
            required_scopes=(crm_read_scope(object_type),),
        )

    def update_crm_object_properties(self, object_type: str, object_id: str, properties: dict[str, Any], idempotency_key: str = "") -> dict[str, Any]:
        return self.request(
            "PATCH",
            f"/crm/objects/2026-03/{_safe_path_segment(object_type)}/{_safe_path_segment(object_id)}",
            body={"properties": properties},
            required_scopes=(crm_write_scope(object_type),),
            idempotency_key=idempotency_key,
        )

    def create_custom_object_record(
        self,
        object_type: str,
        properties: dict[str, Any],
        associations: list[dict[str, Any]] | None = None,
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"properties": properties}
        if associations:
            body["associations"] = associations
        return self.request(
            "POST",
            f"/crm/objects/2026-03/{_safe_path_segment(object_type)}",
            body=body,
            required_scopes=("crm.objects.custom.write",),
            idempotency_key=idempotency_key,
        )

    def create_list(self, payload: dict[str, Any], idempotency_key: str = "") -> dict[str, Any]:
        return self.request(
            "POST",
            "/crm/lists/2026-03",
            body=payload,
            required_scopes=("crm.lists.write",),
            idempotency_key=idempotency_key,
        )

    def search_lists(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request(
            "POST",
            "/crm/lists/2026-03/search",
            body=payload,
            required_scopes=("crm.lists.read",),
        )

    def get_lists(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.request(
            "GET",
            "/crm/lists/2026-03",
            params=params,
            required_scopes=("crm.lists.read",),
        )

    def get_list(self, list_id: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.request(
            "GET",
            f"/crm/lists/2026-03/{_safe_path_segment(list_id)}",
            params=params,
            required_scopes=("crm.lists.read",),
        )

    def get_list_memberships(self, list_id: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.request(
            "GET",
            f"/crm/lists/2026-03/{_safe_path_segment(list_id)}/memberships",
            params=params,
            required_scopes=("crm.lists.read",),
        )

    def add_list_memberships(self, list_id: str, record_ids: list[str], idempotency_key: str = "") -> dict[str, Any]:
        return self.request(
            "PUT",
            f"/crm/lists/2026-03/{_safe_path_segment(list_id)}/memberships/add",
            body=[str(record_id) for record_id in record_ids],
            required_scopes=("crm.lists.write",),
            idempotency_key=idempotency_key,
        )

    def remove_list_memberships(self, list_id: str, record_ids: list[str], idempotency_key: str = "") -> dict[str, Any]:
        return self.request(
            "PUT",
            f"/crm/lists/2026-03/{_safe_path_segment(list_id)}/memberships/remove",
            body=[str(record_id) for record_id in record_ids],
            required_scopes=("crm.lists.write",),
            idempotency_key=idempotency_key,
        )

    def add_and_remove_list_memberships(self, list_id: str, record_ids_to_add: list[str], record_ids_to_remove: list[str], idempotency_key: str = "") -> dict[str, Any]:
        return self.request(
            "PUT",
            f"/crm/lists/2026-03/{_safe_path_segment(list_id)}/memberships/add-and-remove",
            body={
                "recordIdsToAdd": [str(record_id) for record_id in record_ids_to_add],
                "recordIdsToRemove": [str(record_id) for record_id in record_ids_to_remove],
            },
            required_scopes=("crm.lists.write",),
            idempotency_key=idempotency_key,
        )

    def create_timeline_event(self, app_id: str, payload: dict[str, Any], idempotency_key: str = "") -> dict[str, Any]:
        return self.request(
            "POST",
            f"/integrations/v1/{_safe_path_segment(app_id)}/timeline/event",
            body=payload,
            required_scopes=("timeline",),
            idempotency_key=idempotency_key,
        )
