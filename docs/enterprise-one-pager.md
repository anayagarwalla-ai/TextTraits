# TextTraits Enterprise One-Pager

## Positioning

TextTraits is a non-generative email optimization layer for enterprises that already use email, CRM, marketing automation, warehouse, or send-path workflows. It evaluates existing messages before they leave current systems and returns objective scoring, policy findings, send-readiness gates, routing metadata, content hashes, and outcome-join fields.

## Why it is different

- It does not write email copy or replace the company’s current authoring tools.
- It returns structured evidence that workflow systems can use: score, gate status, route, owner queue, findings, request ID, content hash, model version, and policy version.
- It supports governance questions that ordinary writing assistants do not answer well: which campaigns fail, which templates are risky, which sources create review load, and which outcomes join back to analyzed content.
- It can be tested locally with no paid providers by using the analyzer, adapter simulator, OpenAPI contract, governance exports, webhook signature test, and synthetic demo rows.

## Enterprise workflow

1. A draft already exists in a platform such as HubSpot, Salesforce, Braze, Marketo, Iterable, SendGrid/SES, or a warehouse import.
2. The platform sends subject, body, headers, consent context, delivery context, and IDs to `/v1/email/analyze`.
3. TextTraits returns a send-readiness decision: ready, needs review, or blocked.
4. The workflow writes back score, route, request ID, content hash, and findings.
5. Post-send events join back through request ID or content hash for governance dashboards.

## What can be shown today

- Existing-email analyzer with policy score and structured findings.
- Enterprise context fields for campaign, journey, template, locale, headers, consent, and delivery provider.
- Rendered-template testing for Liquid/Handlebars-style tokens.
- Governance dashboard with campaigns, templates, source systems, rule packs, outcomes, and approval queues.
- Adapter simulator for provider-shaped payloads.
- Integration setup wizard with field mappings and OpenAPI export.
- Admin views for roles, scoped key planning, webhook signing tests, policy history, audit events, privacy, terms, security, deployment, model card, and pilot plan.

## What must wait for a customer pilot

- Live provider credentials and production writeback.
- Customer-specific policies and approval rules.
- SSO/SAML, legal agreements, production hosting, and customer security review.
- Real false-pass, false-review, latency, and outcome-join metrics from approved customer sample data.

## Free pilot ask

Ask for 20 to 50 approved, non-secret sample emails or templates, plus the fields their workflow can provide. Use those samples to calibrate thresholds, confirm reviewer agreement, and identify whether TextTraits catches meaningful issues before any live send path changes.
