from __future__ import annotations

from dataclasses import dataclass
from typing import Any


HUBSPOT_EMAIL_RULES_ENGINE_ID = "texttraits-email-quality-rules/2026-07"


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        clean = str(value).strip()
        if clean:
            return clean
    return ""


@dataclass(frozen=True)
class HubSpotEmailDraft:
    """Canonical email input shared by every HubSpot analysis surface."""

    subject: str
    body: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "HubSpotEmailDraft":
        input_fields = payload.get("inputFields") if isinstance(payload.get("inputFields"), dict) else payload
        return cls(
            subject=_first_text(
                input_fields.get("subject"),
                input_fields.get("email_subject"),
                input_fields.get("hs_email_subject"),
            ),
            body=_first_text(
                input_fields.get("body"),
                input_fields.get("email_body"),
                input_fields.get("hs_email_body"),
                input_fields.get("text"),
            ),
        )

    @property
    def text(self) -> str:
        return f"{self.subject}\n\n{self.body}".strip()

    @property
    def word_count(self) -> int:
        return len(self.text.split())


@dataclass(frozen=True)
class HubSpotAnalysisDecision:
    request_id: str
    content_hash: str
    idempotency_key: str
    score: int
    gate: str
    route: str
    next_step: str
    owner_queue: str
    blocker_level: str
    blocker_reason: str
    policy_version: str

    def output_fields(self, asset_fields: dict[str, Any] | None = None) -> dict[str, Any]:
        fields = {
            "texttraits_request_id": self.request_id,
            "texttraits_content_hash": self.content_hash,
            "texttraits_idempotency_key": self.idempotency_key,
            "texttraits_score": self.score,
            "texttraits_gate": self.gate,
            "texttraits_route": self.route,
            "texttraits_send_ready": self.gate == "ready",
            "texttraits_next_step": self.next_step,
            "texttraits_owner_queue": self.owner_queue,
            "texttraits_blocker_level": self.blocker_level,
            "texttraits_blocker_reason": self.blocker_reason,
            "texttraits_policy_version": self.policy_version,
            "texttraits_analysis_engine": HUBSPOT_EMAIL_RULES_ENGINE_ID,
        }
        fields.update({key: value for key, value in (asset_fields or {}).items() if value})
        return fields
