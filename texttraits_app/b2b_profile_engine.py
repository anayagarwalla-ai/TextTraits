from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import re
from typing import Any


PROFILE_ENGINE_VERSION = "b2b-profile-v0.1"
WORD_PATTERN = re.compile(r"\b[\w'-]+\b")
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)")
URL_PATTERN = re.compile(r"https?://[^\s<>)\"']+", re.I)
MONEY_PATTERN = re.compile(r"(\$|usd|budget|pricing|price|cost|renewal|contract)", re.I)
DATE_PATTERN = re.compile(r"\b(today|tomorrow|monday|tuesday|wednesday|thursday|friday|next week|this week|quarter|q[1-4]|\d{1,2}/\d{1,2}|\d+\s?(day|week|month|year)s?)\b", re.I)


@dataclass(frozen=True)
class SignalRule:
    label: str
    category: str
    keywords: tuple[str, ...]
    sales_use: str
    avoid: str


PRIORITY_RULES = (
    SignalRule(
        "Operational risk visibility",
        "priority",
        ("risk", "forecast", "pipeline", "renewal", "visibility", "slipping", "late", "surprise"),
        "Lead with early-warning dashboards, manager coaching moments, and fewer last-minute surprises.",
        "Do not open with generic productivity claims.",
    ),
    SignalRule(
        "Integration and workflow fit",
        "priority",
        ("integrate", "integration", "workflow", "hubspot", "salesforce", "crm", "outreach", "salesloft", "api", "stack"),
        "Show how TextTraits sits beside existing CRM, workflow, and email tools instead of replacing them.",
        "Do not imply a rip-and-replace deployment.",
    ),
    SignalRule(
        "Compliance and governance",
        "priority",
        ("compliance", "legal", "security", "approval", "governance", "audit", "policy", "privacy", "consent"),
        "Emphasize policy gates, audit trails, content hashes, and admin controls.",
        "Do not position this as an ungoverned writing assistant.",
    ),
    SignalRule(
        "Revenue efficiency",
        "priority",
        ("roi", "conversion", "win rate", "response rate", "pipeline", "revenue", "quota", "efficiency"),
        "Connect the product to better prioritization, cleaner follow-ups, and measurable funnel improvements.",
        "Avoid unsupported performance guarantees.",
    ),
)

OBJECTION_RULES = (
    SignalRule(
        "Another tool concern",
        "objection",
        ("another tool", "tool fatigue", "adoption", "change management", "workflow disruption"),
        "Frame the product as an embedded scoring layer and show where it appears inside existing tools.",
        "Do not pitch a separate daily destination first.",
    ),
    SignalRule(
        "Security review",
        "objection",
        ("security review", "infosec", "soc2", "data residency", "vendor review", "procurement"),
        "Offer a minimal-data deployment model, retention controls, and a sandbox API contract.",
        "Do not ask for raw historical inbox exports before trust is established.",
    ),
    SignalRule(
        "Budget timing",
        "objection",
        ("budget", "not this quarter", "pricing", "cost", "renewal timing", "finance"),
        "Propose a narrow pilot tied to one measurable workflow before budget expansion.",
        "Do not lead with broad platform pricing.",
    ),
)

ROLE_RULES = (
    SignalRule(
        "Revenue leader",
        "role",
        ("cro", "vp sales", "revenue", "pipeline", "forecast", "quota", "manager"),
        "Prioritize pipeline risk, manager visibility, and decision speed.",
        "Avoid implementation-heavy detail in the opening note.",
    ),
    SignalRule(
        "Marketing operations",
        "role",
        ("marketing ops", "campaign", "journey", "lifecycle", "segmentation", "template", "mops"),
        "Prioritize workflow fit, governance, experimentation, and data contracts.",
        "Avoid purely sales-led language.",
    ),
    SignalRule(
        "Security or IT reviewer",
        "role",
        ("security", "it", "admin", "sso", "scim", "audit", "access control", "data retention"),
        "Prioritize controls, deployment model, data minimization, and admin workflows.",
        "Avoid claims that require unverified access to sensitive systems.",
    ),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def words(text: str) -> list[str]:
    return WORD_PATTERN.findall(text or "")


def stable_hash(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def redact_identifiers(text: str) -> str:
    clean = EMAIL_PATTERN.sub("[email]", text or "")
    clean = PHONE_PATTERN.sub("[phone]", clean)
    clean = URL_PATTERN.sub("[url]", clean)
    return clean


def count_matches(text: str, keywords: tuple[str, ...]) -> tuple[int, list[str]]:
    lower = text.lower()
    hits = [keyword for keyword in keywords if keyword in lower]
    return len(hits), hits[:5]


def score_rules(text: str, rules: tuple[SignalRule, ...]) -> list[dict[str, Any]]:
    scored = []
    for rule in rules:
        hit_count, hits = count_matches(text, rule.keywords)
        if hit_count:
            scored.append(
                {
                    "label": rule.label,
                    "category": rule.category,
                    "confidence": min(0.95, 0.52 + hit_count * 0.13),
                    "evidence_terms": hits,
                    "sales_use": rule.sales_use,
                    "avoid": rule.avoid,
                }
            )
    return sorted(scored, key=lambda item: item["confidence"], reverse=True)


def communication_style(text: str) -> dict[str, Any]:
    word_list = words(text)
    sentences = len([part for part in re.split(r"[.!?]+", text or "") if part.strip()]) or 1
    avg_sentence = len(word_list) / max(sentences, 1)
    question_count = (text or "").count("?")
    first_person = sum(1 for word in word_list if word.lower() in {"i", "we", "our", "us", "my"})
    reader_focus = sum(1 for word in word_list if word.lower() in {"you", "your", "team", "teams"})
    if avg_sentence >= 23:
        density = "dense"
    elif avg_sentence >= 14:
        density = "moderate"
    else:
        density = "plain"
    style = "collaborative" if question_count >= 2 or reader_focus >= first_person else "directive" if first_person > reader_focus + 2 else "balanced"
    return {
        "style": style,
        "density": density,
        "average_sentence_words": round(avg_sentence, 1),
        "question_count": question_count,
        "reader_focus_terms": reader_focus,
        "sender_focus_terms": first_person,
    }


def buying_stage(text: str, priorities: list[dict[str, Any]], objections: list[dict[str, Any]]) -> dict[str, Any]:
    lower = text.lower()
    if any(term in lower for term in ("procurement", "security review", "legal", "msa", "contract")):
        stage = "Procurement or security review"
        action = "Send a controls-first follow-up with data minimization, audit, and deployment options."
    elif objections:
        stage = "Evaluation with unresolved objection"
        action = "Acknowledge the top objection and propose a narrow pilot with clear success criteria."
    elif priorities:
        stage = "Active discovery"
        action = "Anchor the next note to the strongest business priority and ask for one concrete next step."
    else:
        stage = "Early awareness"
        action = "Ask a focused discovery question before pitching product depth."
    return {"stage": stage, "next_best_action": action}


def resonance_strategy(priorities: list[dict[str, Any]], objections: list[dict[str, Any]], roles: list[dict[str, Any]]) -> dict[str, Any]:
    lead_priority = priorities[0] if priorities else None
    lead_objection = objections[0] if objections else None
    lead_role = roles[0] if roles else None
    angles = []
    avoid = []
    if lead_priority:
        angles.append(lead_priority["sales_use"])
        avoid.append(lead_priority["avoid"])
    if lead_objection:
        angles.append(lead_objection["sales_use"])
        avoid.append(lead_objection["avoid"])
    if lead_role:
        angles.append(lead_role["sales_use"])
        avoid.append(lead_role["avoid"])
    if not angles:
        angles.append("Use a low-pressure discovery note that asks what workflow currently handles review quality.")
    return {
        "recommended_angles": angles[:4],
        "avoid": list(dict.fromkeys(avoid))[:4],
        "message_guidance": [
            "Use business context and stated priorities, not demographic or sensitive personal inference.",
            "Keep the first response short, evidence-led, and tied to one workflow improvement.",
            "Offer a pilot path that can be evaluated without exposing raw inbox history.",
        ],
    }


def build_b2b_profile(payload: dict[str, Any], model_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    transcript = str(payload.get("communication_history") or payload.get("transcript") or payload.get("text") or "")
    account_context = str(payload.get("account_context") or "")
    campaign_goal = str(payload.get("campaign_goal") or payload.get("goal") or "Improve outbound follow-up quality")
    combined = f"{account_context}\n\n{transcript}".strip()
    redacted = redact_identifiers(combined)
    word_count = len(words(combined))

    priorities = score_rules(redacted, PRIORITY_RULES)
    objections = score_rules(redacted, OBJECTION_RULES)
    roles = score_rules(redacted, ROLE_RULES)
    style = communication_style(redacted)
    stage = buying_stage(redacted, priorities, objections)
    strategy = resonance_strategy(priorities, objections, roles)
    pii_counts = {
        "emails": len(EMAIL_PATTERN.findall(combined)),
        "phones": len(PHONE_PATTERN.findall(combined)),
        "urls": len(URL_PATTERN.findall(combined)),
    }
    evidence_terms = sorted(
        {
            term
            for item in priorities + objections + roles
            for term in item.get("evidence_terms", [])
        }
    )

    return {
        "api_version": "v1",
        "profile_engine_version": PROFILE_ENGINE_VERSION,
        "generated_at": utc_now(),
        "profile_id": stable_hash(redacted[:2000])[:28],
        "campaign_goal": campaign_goal,
        "privacy": {
            "mode": "business-signal-minimization",
            "raw_identifiers_returned": False,
            "sensitive_attribute_inference": "disabled",
            "pii_detected_counts": pii_counts,
            "retention_recommendation": "Store findings, hashes, and business labels rather than raw communication history.",
        },
        "safe_features": {
            "word_count": word_count,
            "has_budget_language": bool(MONEY_PATTERN.search(redacted)),
            "has_timing_language": bool(DATE_PATTERN.search(redacted)),
            "communication_style": style,
            "source_hash": stable_hash(redacted),
            "evidence_terms_observed": evidence_terms[:20],
        },
        "business_profile": {
            "buying_stage": stage["stage"],
            "next_best_action": stage["next_best_action"],
            "likely_business_roles": roles[:3],
            "business_priorities": priorities[:4],
            "detected_objections": objections[:4],
        },
        "resonance_strategy": strategy,
        "activation": {
            "crm_fields": [
                "texttraits_buying_stage",
                "texttraits_priority_signal",
                "texttraits_objection_signal",
                "texttraits_next_best_action",
                "texttraits_privacy_mode",
            ],
            "workflow_uses": [
                "Route high-governance prospects to security-first follow-up.",
                "Route budget-timing objections to pilot-offer sequences.",
                "Route integration-fit accounts to workflow/API proof material.",
            ],
            "llm_generation_context": {
                "allowed": ["business_priorities", "detected_objections", "communication_style", "campaign_goal"],
                "blocked": ["raw identifiers", "sensitive personal attributes", "unverified demographics"],
            },
        },
        "model_stack": {
            "runtime": "deterministic B2B signal engine plus optional cloud-trained classifier manifest",
            "local_texttraits_model": (model_metadata or {}).get("bundle_format", "available"),
            "training_status": "No local training performed.",
        },
    }
