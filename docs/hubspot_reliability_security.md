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

## Review Events

The HubSpot card can record:

- `copy_recommendation`
- `mark_reviewed`
- `send_to_marketing_review`
- `rerun_analysis`

These events store the request ID, action, actor ID when supplied, status, and scrubbed metadata.

## OAuth

HubSpot OAuth install is supported. OAuth access and refresh tokens are not stored by default. Do not enable `TEXTTRAITS_STORE_OAUTH_TOKENS=true` until encryption and key-management are reviewed.

## Exports

Admin endpoints provide CSV and JSON exports of analysis history. CSV values are neutralized against spreadsheet formula injection.

Set `TEXTTRAITS_ENTERPRISE_ADMIN_EMAILS` to a comma-separated allowlist before using admin exports, dashboard, or policy controls in production.

## Production Requirements

Before an enterprise rollout:

- Use HTTPS and a reviewed public base URL.
- Set `TEXTTRAITS_ENV=production`.
- Set `TEXTTRAITS_ALLOW_DEMO=false`.
- Use hosted Postgres for persistence.
- Configure HubSpot OAuth credentials in the deployment environment.
- Run `python3 tests/production_smoke_test.py` and `python3 tests/security_regression_test.py`.
