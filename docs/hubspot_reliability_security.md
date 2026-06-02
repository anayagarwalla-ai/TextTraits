# HubSpot Reliability And Security Notes

## Storage

For HubSpot email-fit analyses, TextTraits stores:

- Request ID
- Workspace/tenant/source metadata
- Campaign, journey, template, contact, company, deal, owner, portal, object, and locale IDs when supplied
- Content hash
- Score, gate, route, send-ready state
- Word count and average model confidence
- Findings, checks, policy, and non-secret context metadata
- Timestamp

TextTraits does not store the raw subject or body in the HubSpot analysis history tables.
Findings and checks are also normalized into queryable governance tables so dashboards can aggregate by failed rule, severity, owner queue, and status without parsing JSON blobs.

## Ingress Authentication

HubSpot ingress endpoints support shared-secret authentication for production routing middleware:

- `X-TextTraits-API-Key: <TEXTTRAITS_HUBSPOT_INGRESS_SECRET>`
- or `X-TextTraits-Signature: sha256=<hex hmac>` where the HMAC uses the raw request body and `TEXTTRAITS_HUBSPOT_INGRESS_SECRET`.

When `TEXTTRAITS_HUBSPOT_INGRESS_SECRET` is configured, unsigned HubSpot ingress requests are rejected. `TEXTTRAITS_REQUIRE_HUBSPOT_INGRESS_AUTH=true` can be used to fail closed if the secret is missing.

HubSpot portal IDs are bound to `workspace_id` values such as `hubspot_246356639`. If a request supplies both a portal ID and a mismatched workspace, TextTraits rejects it.

## Review Events

The HubSpot card can record:

- `copy_recommendation`
- `mark_reviewed`
- `send_to_marketing_review`
- `rerun_analysis`
- `assign_reviewer`
- `resolve_review`
- `add_review_note`

These events store the request ID, action, actor ID when supplied, status, and scrubbed metadata.
Review state is maintained separately with status, assigned reviewer, owner queue, blocker level, SLA due date, resolution timestamp, and notes.

## Outcomes

Outcome events can be ingested with `POST /v1/integrations/hubspot/outcomes` and joined by `request_id` or `content_hash`.
Supported event types are intentionally open-ended so send systems can report events such as delivered, bounced, complained, opened, clicked, suppressed, unsubscribed, replied, or converted.

## OAuth

HubSpot OAuth install is supported. OAuth access and refresh tokens are not stored by default. Do not enable `TEXTTRAITS_STORE_OAUTH_TOKENS=true` until encryption and key-management are reviewed.

## Exports

Admin endpoints provide CSV and JSON exports of analysis history. CSV values are neutralized against spreadsheet formula injection.

Set `TEXTTRAITS_ENTERPRISE_ADMIN_EMAILS` to a comma-separated allowlist before using admin exports, dashboard, or policy controls in production.
Production admin endpoints fail closed if the allowlist is missing.

## Policy History

Every policy save writes the current policy and appends an immutable history row. Use:

- `GET /api/enterprise/hubspot/policy/history`
- `GET /api/enterprise/hubspot/findings`
- `GET /api/enterprise/hubspot/checks`
- `GET /api/enterprise/hubspot/review-states`
- `GET /api/enterprise/hubspot/outcomes`

These endpoints are admin-only.

## Production Requirements

Before an enterprise rollout:

- Use HTTPS and a reviewed public base URL.
- Set `TEXTTRAITS_ENV=production`.
- Set `TEXTTRAITS_ALLOW_DEMO=false`.
- Use hosted Postgres for persistence.
- Configure HubSpot OAuth credentials in the deployment environment.
- Configure `TEXTTRAITS_ENTERPRISE_ADMIN_EMAILS`.
- Configure `TEXTTRAITS_HUBSPOT_INGRESS_SECRET` before using this as send-path middleware.
- Run `python3 tests/production_smoke_test.py` and `python3 tests/security_regression_test.py`.
