# TextTraits HubSpot Architecture

## Request Path

1. A HubSpot card, home page, settings page, workflow action, webhook, or approved middleware calls a versioned `/v1/integrations/hubspot/*` endpoint.
2. Flask enforces the payload limit and validates either HubSpot's native request signature or the timestamped TextTraits ingress signature. Production fails closed.
3. `HubSpotEmailDraft` normalizes subject/body aliases once. Portal, workspace, campaign, template, object, locale, and governance context are normalized separately.
4. The deterministic email-quality engine evaluates subject, body completeness, next step, specificity, personalization, readability, and configured risk phrases. It returns weighted checks, explicit penalties, findings, score, gate, route, policy version, and engine version.
5. The storage repository writes the analysis plus normalized checks/findings atomically. It stores a tenant-scoped HMAC content digest, not raw email copy.
6. Optional sync operations use one cached portal connection and pooled HubSpot HTTP client. Independent writebacks run concurrently. Non-idempotent writes are never retried unless they include an idempotency key.
7. Outcome/webhook events use deterministic replay keys. Governance dashboards read portal-scoped analyses, review states, outcomes, and SQL rollups from one database snapshot.

## Owned Modules

- `hubspot_analysis.py`: canonical input and output contracts plus engine identifier.
- `hubspot_routes.py`: analysis and signed extension bootstrap route groups.
- `hubspot_client.py`: pooled HubSpot API transport, scope checks, refresh locking, retries, and audit metadata.
- `hubspot_sync.py`: bounded concurrent sync operations.
- `hubspot_performance.py`: endpoint classes and latency budgets.
- `rate_limit.py`: bounded thread-safe local sliding-window limiter.
- `storage.py`: transactions, normalized governance data, retention, exports, encrypted portal tokens, and replay protection.
- `hubspot-project/contracts/analysis-contract.json`: versioned workflow, component, endpoint, and output contract consumed by Node validation and Python tests.

## Honest Capability States

- `implemented`: usable from its declared surface without live OAuth.
- `implemented_backend`: payload mapping is implemented, but a customer workflow must supply mapped data.
- `implemented_requires_oauth`: implementation is live only after portal connection, encrypted token storage, and required scopes.
- Metadata-only campaign assets remain visible as coverage gaps and are never presented as analyzed copy.

## External Setup Still Required

Production credentials, a Fernet token-encryption key, enterprise admin emails, a hosted Postgres database, customer-approved property/association mappings, HubSpot project upload, and marketplace approval cannot be generated locally. TextTraits reports these as setup requirements rather than inventing values.
