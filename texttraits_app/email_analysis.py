from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import re
import uuid
from typing import Any


API_VERSION = "v1"
POLICY_BUNDLE_ID = "enterprise_email_readiness"
POLICY_BUNDLE_VERSION = "2026.05.25"
MODEL_CONTRACT_VERSION = "local-texttraits-bundle"

VAGUE_TERMS = (
    "stuff",
    "things",
    "maybe",
    "probably",
    "kind of",
    "sort of",
    "really",
    "very",
    "a lot",
    "somewhat",
)
HYPE_TERMS = (
    "revolutionary",
    "game-changing",
    "guaranteed",
    "disruptive",
    "world-class",
    "best-in-class",
)
COMPLIANCE_TERMS = (
    "free",
    "guaranteed",
    "no risk",
    "act now",
    "limited time",
)
CTA_PATTERN = re.compile(
    r"(would you|could we|can we|are you open|does .* work|reply|send|share|schedule|meet|call|next step|fit check|\?)",
    re.I,
)
SPECIFICITY_PATTERN = re.compile(
    r"\b(today|tomorrow|monday|tuesday|wednesday|thursday|friday|next week|this week|q[1-4]|\d{1,2}/\d{1,2}|\d+%|\$\d+|\d+\s?(minute|day|week|month|year)s?)\b",
    re.I,
)
UNSUBSCRIBE_PATTERN = re.compile(r"\b(unsubscribe|opt out|opt-out|manage preferences|stop receiving)\b", re.I)
LINK_PATTERN = re.compile(r"https?://[^\s<>)\"']+", re.I)
IMAGE_PATTERN = re.compile(r"(<img\b|!\[[^\]]*\]\(|cid:|data:image/)", re.I)
TOKEN_PATTERN = re.compile(r"(\{\{[^}]+\}\}|%{1,2}[^%]+%{1,2}|\[[A-Z_]+])")
WORD_PATTERN = re.compile(r"\b[\w'-]+\b")
LIQUID_HANDLEBARS_PATTERN = re.compile(r"\{\{\s*([^}|]+)(?:\|[^}]*)?\s*\}\}")
PERCENT_TOKEN_PATTERN = re.compile(r"%{1,2}\s*([A-Za-z0-9_.-]+)\s*%{1,2}")
BRACKET_TOKEN_PATTERN = re.compile(r"\[([A-Z][A-Z0-9_.-]+)\]")


@dataclass(frozen=True)
class Rule:
    id: str
    category: str
    severity: str
    title: str
    remediation: str


RULES = {
    "clarity.long_sentences": Rule(
        "clarity.long_sentences",
        "clarity",
        "medium",
        "Sentences are dense",
        "Split long sentences so a reviewer can scan the point and the ask quickly.",
    ),
    "clarity.vague_language": Rule(
        "clarity.vague_language",
        "clarity",
        "medium",
        "Vague language detected",
        "Replace vague qualifiers with the actual detail, proof point, or concrete constraint.",
    ),
    "cta.missing": Rule(
        "cta.missing",
        "cta",
        "high",
        "No clear next step",
        "Add one specific action the reader can take or answer.",
    ),
    "specificity.missing": Rule(
        "specificity.missing",
        "specificity",
        "medium",
        "Concrete detail is missing",
        "Add a date, number, timeframe, customer signal, or measurable proof point.",
    ),
    "compliance.promotional_claim": Rule(
        "compliance.promotional_claim",
        "compliance",
        "high",
        "Promotional claim needs review",
        "Route this claim through the approved messaging or legal-review policy before sending.",
    ),
    "unsubscribe.missing_bulk": Rule(
        "unsubscribe.missing_bulk",
        "unsubscribe",
        "high",
        "Bulk email needs opt-out language",
        "Add an unsubscribe, opt-out, or preference-management path for outbound campaign sends.",
    ),
    "personalization.unresolved_token": Rule(
        "personalization.unresolved_token",
        "personalization",
        "high",
        "Unresolved personalization token",
        "Resolve or remove personalization placeholders before the message enters a sending system.",
    ),
    "link_count.high": Rule(
        "link_count.high",
        "format",
        "medium",
        "Too many links",
        "Reduce links so the primary action stays obvious and deliverability risk is lower.",
    ),
    "image_ratio.high": Rule(
        "image_ratio.high",
        "format",
        "medium",
        "Image-heavy content",
        "Balance images with enough plain text for accessibility, scanning, and deliverability.",
    ),
    "subject.missing": Rule(
        "subject.missing",
        "subject",
        "medium",
        "Subject line is missing",
        "Add a concise subject that previews the reason for the email.",
    ),
    "subject.length": Rule(
        "subject.length",
        "subject",
        "low",
        "Subject line may be hard to scan",
        "Keep the subject specific and short enough to read in an inbox preview.",
    ),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_request_id(value: str | None = None) -> str:
    clean = str(value or "").strip()
    return clean[:120] if clean else f"req_{uuid.uuid4().hex}"


def words(text: str) -> list[str]:
    return WORD_PATTERN.findall(text or "")


def content_hash(subject: str, body: str) -> str:
    canonical = f"{subject.strip()}\n\n{body.strip()}".encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def content_hashes(subject: str, body: str, headers: dict[str, Any] | None = None) -> dict[str, str]:
    header_text = "\n".join(f"{key}:{value}" for key, value in sorted((headers or {}).items()))
    return {
        "subject_body": content_hash(subject, body),
        "headers": "sha256:" + hashlib.sha256(header_text.encode("utf-8")).hexdigest(),
        "full_message": "sha256:" + hashlib.sha256(f"{header_text}\n\n{subject}\n\n{body}".encode("utf-8")).hexdigest(),
    }


def text_stats(body: str) -> dict[str, Any]:
    word_list = words(body)
    punctuation = len(re.findall(r"[^\w\s]", body or ""))
    characters = len(body or "")
    sentences = len([part for part in re.split(r"[.!?]+", body or "") if part.strip()]) or 1
    avg_sentence = len(word_list) / max(sentences, 1)
    return {
        "words": len(word_list),
        "characters": characters,
        "sentences": sentences,
        "average_sentence_words": round(avg_sentence, 1),
        "punctuation_density": round(punctuation / characters, 4) if characters else 0,
        "reading_level": "Plain" if avg_sentence < 12 else "Moderate" if avg_sentence < 20 else "Dense",
    }


def score_subject(subject: str) -> int:
    length = len(subject.strip())
    if not length:
        return 30
    if 18 <= length <= 58:
        return 100
    if 12 <= length <= 72:
        return 74
    return 48


def score_length(word_count: int) -> int:
    if 70 <= word_count <= 170:
        return 100
    if 45 <= word_count <= 210:
        return 78
    if 25 <= word_count <= 260:
        return 58
    return 38


def score_buyer_focus(body: str) -> int:
    tokens = [word.lower() for word in words(body)]
    reader = sum(1 for word in tokens if word in {"you", "your", "yours", "team", "teams"})
    sender = sum(1 for word in tokens if word in {"i", "we", "our", "me", "my", "us"})
    if reader >= 3 and reader >= sender - 1:
        return 100
    if reader >= 2:
        return 76
    if reader >= 1:
        return 58
    return 35


def nested_context_value(data: Any, path: str) -> Any:
    current = data
    for part in str(path or "").replace("-", "_").split("."):
        if not part:
            continue
        if isinstance(current, dict):
            candidates = {str(key).lower().replace("-", "_"): value for key, value in current.items()}
            current = candidates.get(part.lower().replace("-", "_"))
        else:
            return None
    return current


def token_value(context: dict[str, Any], token_name: str) -> str | None:
    clean = str(token_name or "").strip()
    if not clean:
        return None
    for candidate in (clean, clean.lower(), clean.replace("_", "."), clean.lower().replace("_", ".")):
        value = nested_context_value(context, candidate)
        if value not in (None, ""):
            return str(value)
    return None


def render_template_text(template: str, context: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    unresolved: list[dict[str, Any]] = []

    def replace_liquid(match: re.Match) -> str:
        key = match.group(1).strip()
        value = token_value(context, key)
        if value is None:
            unresolved.append({"token": match.group(0), "key": key, "offset": match.start(), "syntax": "liquid_handlebars"})
            return match.group(0)
        return value

    def replace_percent(match: re.Match) -> str:
        key = match.group(1).strip()
        value = token_value(context, key)
        if value is None:
            unresolved.append({"token": match.group(0), "key": key, "offset": match.start(), "syntax": "percent"})
            return match.group(0)
        return value

    def replace_bracket(match: re.Match) -> str:
        key = match.group(1).strip()
        value = token_value(context, key)
        if value is None:
            unresolved.append({"token": match.group(0), "key": key, "offset": match.start(), "syntax": "bracket"})
            return match.group(0)
        return value

    rendered = LIQUID_HANDLEBARS_PATTERN.sub(replace_liquid, template or "")
    rendered = PERCENT_TOKEN_PATTERN.sub(replace_percent, rendered)
    rendered = BRACKET_TOKEN_PATTERN.sub(replace_bracket, rendered)
    return rendered, unresolved


def header_dict(payload: dict[str, Any]) -> dict[str, Any]:
    headers = payload.get("headers")
    if isinstance(headers, dict):
        return {str(key): value for key, value in headers.items()}
    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    headers = message.get("headers")
    return {str(key): value for key, value in headers.items()} if isinstance(headers, dict) else {}


def enterprise_context(payload: dict[str, Any]) -> dict[str, Any]:
    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    return {
        "tenant_id": str(payload.get("tenant_id") or message.get("tenant_id") or "").strip()[:120],
        "workspace_id": str(payload.get("workspace_id") or message.get("workspace_id") or "default").strip()[:120] or "default",
        "source_system": str(payload.get("source_system") or payload.get("source") or payload.get("channel") or message.get("source_system") or "direct_api").strip()[:120],
        "analysis_mode": str(payload.get("analysis_mode") or message.get("analysis_mode") or payload.get("channel") or "direct_api").strip()[:80],
        "campaign_id": str(payload.get("campaign_id") or message.get("campaign_id") or "").strip()[:160],
        "journey_id": str(payload.get("journey_id") or message.get("journey_id") or "").strip()[:160],
        "step_id": str(payload.get("step_id") or message.get("step_id") or "").strip()[:160],
        "template_id": str(payload.get("template_id") or message.get("template_id") or "").strip()[:160],
        "template_version": str(payload.get("template_version") or message.get("template_version") or "").strip()[:80],
        "locale": str(payload.get("locale") or message.get("locale") or "").strip()[:32],
        "headers": header_dict(payload),
        "consent_context": payload.get("consent_context") if isinstance(payload.get("consent_context"), dict) else {},
        "delivery_context": payload.get("delivery_context") if isinstance(payload.get("delivery_context"), dict) else {},
        "recipient_context": payload.get("recipient_context") if isinstance(payload.get("recipient_context"), dict) else {},
        "personalization_context": payload.get("personalization_context") if isinstance(payload.get("personalization_context"), dict) else {},
        "experiment_ids": payload.get("experiment_ids") if isinstance(payload.get("experiment_ids"), list) else [],
    }


def rendered_template_harness(payload: dict[str, Any]) -> dict[str, Any]:
    context = enterprise_context(payload)
    personalization = {
        **context.get("recipient_context", {}),
        **context.get("personalization_context", {}),
    }
    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    subject_template = str(payload.get("subject") or message.get("subject") or "")
    body_template = str(payload.get("body") or payload.get("text") or message.get("content") or message.get("body") or message.get("html") or "")
    rendered_subject, subject_unresolved = render_template_text(subject_template, personalization)
    rendered_body, body_unresolved = render_template_text(body_template, personalization)
    headers = header_dict(payload)
    links = list(payload.get("links") or [])
    if not links:
        links = LINK_PATTERN.findall(rendered_body)
    unsubscribe_header = any(str(key).lower() == "list-unsubscribe" for key in headers)
    unsubscribe_body = bool(UNSUBSCRIBE_PATTERN.search(rendered_body.lower()))
    return {
        "context": context,
        "rendered_subject": rendered_subject,
        "rendered_body": rendered_body,
        "unresolved_tokens": [
            {**item, "location": "subject"} for item in subject_unresolved
        ] + [
            {**item, "location": "body"} for item in body_unresolved
        ],
        "headers": headers,
        "links": links[:25],
        "unsubscribe": {
            "header_present": unsubscribe_header,
            "body_present": unsubscribe_body,
            "state": str(context.get("consent_context", {}).get("state") or "unknown"),
        },
        "content_hashes": content_hashes(rendered_subject, rendered_body, headers),
    }


def safe_template_summary(harness: dict[str, Any]) -> dict[str, Any]:
    return {
        "unresolved_tokens": harness.get("unresolved_tokens", []),
        "header_names": sorted(harness.get("headers", {}).keys()),
        "link_count": len(harness.get("links") or []),
        "unsubscribe": harness.get("unsubscribe", {}),
        "content_hashes": harness.get("content_hashes", {}),
    }


def evidence_for_terms(text: str, terms: tuple[str, ...], location: str) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    lowered = text.lower()
    for term in terms:
        start = lowered.find(term.lower())
        if start >= 0:
            evidence.append({"text": text[start : start + len(term)], "location": location, "offset": start})
    return evidence[:8]


def regex_evidence(pattern: re.Pattern, text: str, location: str, limit: int = 8) -> list[dict[str, Any]]:
    return [
        {"text": match.group(0), "location": location, "offset": match.start()}
        for match in pattern.finditer(text or "")
    ][:limit]


def finding(rule_id: str, evidence: list[dict[str, Any]] | None = None, details: str = "") -> dict[str, Any]:
    rule = RULES[rule_id]
    payload = {
        "id": rule.id,
        "severity": rule.severity,
        "category": rule.category,
        "title": rule.title,
        "evidence": evidence or [],
        "remediation": rule.remediation,
    }
    if details:
        payload["details"] = details
    return payload


def score_from_findings(base: int, findings: list[dict[str, Any]], category: str) -> int:
    penalties = {"critical": 40, "high": 28, "medium": 16, "low": 7, "info": 0}
    total = base
    for item in findings:
        if item["category"] == category:
            total -= penalties.get(item["severity"], 0)
    return max(0, min(100, total))


def detect_assets(payload: dict[str, Any], body: str) -> dict[str, Any]:
    assets = payload.get("assets") if isinstance(payload.get("assets"), dict) else {}
    links = list(assets.get("links") or [])
    if not links:
        links = LINK_PATTERN.findall(body)
    image_count = int(assets.get("image_count") or len(IMAGE_PATTERN.findall(body)))
    html_bytes = int(assets.get("html_bytes") or len(body.encode("utf-8")))
    image_bytes = int(assets.get("image_bytes") or 0)
    return {
        "links": links[:25],
        "link_count": len(links),
        "image_count": image_count,
        "image_bytes": image_bytes,
        "html_bytes": html_bytes,
        "image_ratio": round(image_bytes / max(html_bytes, 1), 3) if image_bytes else 0,
    }


def build_findings(subject: str, body: str, payload: dict[str, Any], stats: dict[str, Any], assets: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    body_lower = body.lower()
    audience = str(payload.get("audience", "")).lower()
    intent = str(payload.get("intent", "")).lower()
    channel = str(payload.get("channel", "email")).lower()
    headers = header_dict(payload)
    is_bulk = any(term in f"{audience} {intent} {channel}" for term in ("bulk", "campaign", "newsletter", "marketing", "sequence"))

    if not subject.strip():
        findings.append(finding("subject.missing", details="Subject is empty."))
    elif len(subject.strip()) < 12 or len(subject.strip()) > 72:
        findings.append(finding("subject.length", [{"text": subject.strip(), "location": "subject", "offset": 0}], f"{len(subject.strip())} characters."))

    if stats["average_sentence_words"] > 24:
        findings.append(finding("clarity.long_sentences", details=f"{stats['average_sentence_words']} words per sentence on average."))

    vague_evidence = evidence_for_terms(body, VAGUE_TERMS, "body")
    if vague_evidence:
        findings.append(finding("clarity.vague_language", vague_evidence))

    if not CTA_PATTERN.search(body):
        findings.append(finding("cta.missing"))

    if not SPECIFICITY_PATTERN.search(f"{subject} {body}"):
        findings.append(finding("specificity.missing"))

    compliance_evidence = evidence_for_terms(body, COMPLIANCE_TERMS + HYPE_TERMS, "body")
    if compliance_evidence:
        findings.append(finding("compliance.promotional_claim", compliance_evidence))

    unsubscribe_header = any(str(key).lower() == "list-unsubscribe" for key in headers)
    if is_bulk and not unsubscribe_header and not UNSUBSCRIBE_PATTERN.search(body_lower):
        findings.append(finding("unsubscribe.missing_bulk"))

    token_evidence = regex_evidence(TOKEN_PATTERN, f"{subject}\n{body}", "email")
    if token_evidence:
        findings.append(finding("personalization.unresolved_token", token_evidence))

    if assets["link_count"] > 3:
        findings.append(finding("link_count.high", [{"text": str(assets["link_count"]), "location": "assets", "offset": 0}]))

    if assets["image_count"] >= 3 or assets["image_ratio"] > 0.55:
        findings.append(
            finding(
                "image_ratio.high",
                [{"text": str(assets["image_ratio"]), "location": "assets.image_ratio", "offset": 0}],
                f"{assets['image_count']} images detected.",
            )
        )

    return findings


def gate_from_scores(
    scores: dict[str, int],
    findings: list[dict[str, Any]],
    policy_controls: dict[str, Any] | None = None,
) -> dict[str, Any]:
    controls = policy_controls or {}
    ready_minimum_score = int(controls.get("min_ready_score") or 72)
    rule_family_modes = controls.get("rule_family_modes") if isinstance(controls.get("rule_family_modes"), dict) else {}
    default_high_action = "review" if bool(controls.get("high_severity_requires_review", True)) else "fail_open"
    highest = highest_severity(findings)
    blocking_findings = []
    review_findings = []
    for item in findings:
        if item["severity"] not in {"critical", "high"}:
            continue
        mode = str(rule_family_modes.get(item["category"]) or default_high_action).strip().lower()
        if item["severity"] == "critical" or mode == "fail_closed":
            blocking_findings.append(item)
        elif mode in {"review", "needs_review"}:
            review_findings.append(item)
    if blocking_findings:
        status = "blocked"
        send_ready = False
        route = "compliance_or_manager_review"
    elif review_findings or scores["overall"] < ready_minimum_score:
        status = "needs_review"
        send_ready = False
        route = "human_review_queue"
    else:
        status = "ready"
        send_ready = True
        route = "approved_to_send"
    return {
        "status": status,
        "send_ready": send_ready,
        "route": route,
        "highest_severity": highest,
        "thresholds": {
            "ready_minimum_score": ready_minimum_score,
            "block_on_critical": True,
            "default_high_action": default_high_action,
            "rule_family_modes": rule_family_modes,
            "policy_controls_version": str(controls.get("version") or "default"),
        },
    }


def highest_severity(findings: list[dict[str, Any]]) -> str:
    order = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
    if not findings:
        return "none"
    return max((item["severity"] for item in findings), key=lambda value: order.get(value, -1))


def policy_scores(subject: str, body: str, stats: dict[str, Any], findings: list[dict[str, Any]]) -> dict[str, int]:
    clarity = score_from_findings(100, findings, "clarity")
    cta = score_from_findings(100, findings, "cta")
    specificity = score_from_findings(100, findings, "specificity")
    compliance = score_from_findings(100, findings, "compliance")
    unsubscribe = score_from_findings(100, findings, "unsubscribe")
    personalization = score_from_findings(100, findings, "personalization")
    format_score = score_from_findings(100, findings, "format")
    subject_score = score_subject(subject)
    length = score_length(stats["words"])
    buyer_focus = score_buyer_focus(body)
    overall = round(
        (
            clarity * 0.17
            + cta * 0.16
            + specificity * 0.14
            + compliance * 0.14
            + unsubscribe * 0.1
            + personalization * 0.1
            + format_score * 0.08
            + subject_score * 0.06
            + length * 0.03
            + buyer_focus * 0.02
        )
    )
    return {
        "overall": int(overall),
        "clarity": clarity,
        "cta": cta,
        "specificity": specificity,
        "compliance": compliance,
        "unsubscribe": unsubscribe,
        "personalization": personalization,
        "format": format_score,
        "subject": subject_score,
        "length": length,
        "buyer_focus": buyer_focus,
    }


def routes_for_gate(gate: dict[str, Any], findings: list[dict[str, Any]]) -> list[dict[str, str]]:
    if gate["send_ready"]:
        return [{"target": "sending_system", "reason": "Policy gate passed with no high-severity findings."}]
    routes = [{"target": gate["route"], "reason": f"Policy gate status is {gate['status']}."}]
    categories = sorted({item["category"] for item in findings if item["severity"] in {"critical", "high"}})
    for category in categories:
        routes.append({"target": f"{category}_owner", "reason": f"High-severity {category} finding requires review."})
    return routes


def build_email_analysis(
    payload: dict[str, Any],
    predictions: dict[str, Any],
    *,
    model_metadata: dict[str, Any] | None = None,
    demo: bool = False,
    request_id: str | None = None,
    policy_controls: dict[str, Any] | None = None,
) -> dict[str, Any]:
    harness = rendered_template_harness(payload)
    subject = str(harness.get("rendered_subject") or payload.get("subject") or "").strip()
    body = str(harness.get("rendered_body") or payload.get("body") or payload.get("text") or "").strip()
    if not body:
        raise ValueError("Email body is required.")
    stats = text_stats(body)
    assets = detect_assets(payload, body)
    findings = build_findings(subject, body, payload, stats, assets)
    scores = policy_scores(subject, body, stats, findings)
    gate = gate_from_scores(scores, findings, policy_controls)
    metadata = model_metadata or {}
    model_version = str(metadata.get("trained_at") or metadata.get("bundle_version") or MODEL_CONTRACT_VERSION)
    request_id_value = stable_request_id(request_id or payload.get("request_id"))
    controls = policy_controls or {}
    context = enterprise_context({**payload, "subject": subject, "body": body})
    hashes = content_hashes(subject, body, context.get("headers") or {})
    return {
        "api_version": API_VERSION,
        "request_id": request_id_value,
        "content_hash": hashes["subject_body"],
        "content_hashes": hashes,
        "created_at": utc_now(),
        "policy": {
            "bundle_id": str(payload.get("policy_bundle") or POLICY_BUNDLE_ID),
            "bundle_version": POLICY_BUNDLE_VERSION,
            "gate": gate,
            "controls": {
                "workspace_id": str(controls.get("workspace_id") or payload.get("workspace_id") or "default"),
                "min_ready_score": int(controls.get("min_ready_score") or 72),
                "high_severity_requires_review": bool(controls.get("high_severity_requires_review", True)),
                "rule_family_modes": controls.get("rule_family_modes") if isinstance(controls.get("rule_family_modes"), dict) else {},
                "environment": str(controls.get("policy_environment") or "production"),
                "content_storage_mode": str(controls.get("content_storage_mode") or "hash_only"),
            },
            "rule_packs": [
                "clarity",
                "cta",
                "specificity",
                "compliance",
                "unsubscribe",
                "personalization_tokens",
                "link_count",
                "image_ratio",
                "subject",
                "length",
                "buyer_focus",
            ],
        },
        "model": {
            "id": str(payload.get("model") or "local"),
            "version": model_version,
            "contract_version": MODEL_CONTRACT_VERSION,
            "demo": bool(demo),
            "targets": metadata.get("targets", []),
        },
        "input": {
            "subject_present": bool(subject),
            "audience": str(payload.get("audience") or "unspecified"),
            "intent": str(payload.get("intent") or "unspecified"),
            "channel": str(payload.get("channel") or "email"),
            "enterprise_context": context,
            "workspace_id": str(context.get("workspace_id") or controls.get("workspace_id") or "default"),
            "assets": assets,
            "rendered_template": safe_template_summary(harness),
        },
        "stats": stats,
        "scores": scores,
        "findings": findings,
        "routes": routes_for_gate(gate, findings),
        "predictions": predictions,
        "privacy": {
            "raw_body_returned": False,
            "stored_text_policy": str(controls.get("content_storage_mode") or "hash_only"),
        },
    }


def integration_flow_catalog() -> list[dict[str, Any]]:
    return [
        {
            "id": "hubspot_workflow_action",
            "name": "HubSpot workflow action",
            "entrypoint": "/v1/integrations/hubspot/workflow-actions/analyze-email",
            "flow": ["workflow enrollment", "email property mapping", "TextTraits policy gate", "write route fields"],
        },
        {
            "id": "salesforce_journey_builder_activity",
            "name": "Salesforce Journey Builder activity",
            "entrypoint": "/v1/integrations/salesforce/journey-builder/activity",
            "flow": ["journey activity payload", "contact data merge check", "send-readiness score", "journey branch decision"],
        },
        {
            "id": "sendgrid_ses_middleware",
            "name": "SendGrid/SES middleware",
            "entrypoint": "/v1/integrations/sendgrid-ses/middleware",
            "flow": ["message send request", "policy analysis", "allow or hold", "provider handoff"],
        },
        {
            "id": "braze_canvas_currents",
            "name": "Braze Canvas and Currents loop",
            "entrypoint": "/v1/integrations/braze/canvas-gate",
            "flow": ["Canvas email step", "Liquid render test", "policy gate", "Currents outcome join"],
        },
        {
            "id": "marketo_smart_campaign_gate",
            "name": "Marketo smart campaign gate",
            "entrypoint": "/v1/integrations/marketo/smart-campaign-gate",
            "flow": ["program asset", "token/sample context", "send-readiness gate", "review route fields"],
        },
        {
            "id": "iterable_workflow_gate",
            "name": "Iterable workflow gate",
            "entrypoint": "/v1/integrations/iterable/workflow-gate",
            "flow": ["workflow message", "Handlebars render test", "policy gate", "event stream join key"],
        },
        {
            "id": "warehouse_feedback_import",
            "name": "Warehouse feedback import",
            "entrypoint": "/v1/integrations/warehouse/feedback-import",
            "flow": ["campaign/template rows", "batch analysis", "normalized findings", "outcome trend dashboard"],
        },
        {
            "id": "post_send_webhook_ingestion",
            "name": "Post-send webhook ingestion",
            "entrypoint": "/v1/webhooks/post-send",
            "flow": ["provider event", "request/event dedupe", "delivery outcome mapping", "governance dashboard update"],
        },
    ]


def compact_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": analysis["request_id"],
        "content_hash": analysis["content_hash"],
        "score": analysis["scores"]["overall"],
        "gate": analysis["policy"]["gate"],
        "finding_count": len(analysis["findings"]),
        "highest_severity": analysis["policy"]["gate"]["highest_severity"],
        "routes": analysis["routes"],
    }
