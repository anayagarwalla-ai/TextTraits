# HubSpot Reliability And Security Notes

## Storage

For HubSpot email-fit analyses, TextTraits stores:

- Request ID
- Workspace/tenant/source metadata
- Campaign, journey, template, contact, company, deal, owner, portal, object, and locale IDs when supplied
- Tenant-scoped keyed content digest
- Score, gate, route, send-ready state
- Word count and average model confidence
- Findings, checks, policy, and non-secret context metadata
- Timestamp

TextTraits does not store the raw subject or body in the HubSpot analysis history tables.
Content digests use an HMAC with `TEXTTRAITS_CONTENT_HASH_SECRET` or the app secret, so exports can still join outcomes without exposing a plain SHA-256 of customer email content.
Findings and checks are also normalized into queryable governance tables so dashboards can aggregate by failed rule, severity, owner queue, and status without parsing JSON blobs.

## Ingress Authentication

HubSpot ingress endpoints validate native HubSpot request signatures when HubSpot sends signed traffic:

- `X-HubSpot-Signature-v3` with `X-HubSpot-Request-Timestamp` is validated against `HUBSPOT_CLIENT_SECRET`.
- TextTraits rejects v3 timestamps outside `TEXTTRAITS_HUBSPOT_SIGNATURE_MAX_AGE_SECONDS` and canonicalizes the signed URI using HubSpot's documented query-string decoding rules.
- Legacy `X-HubSpot-Signature` requests with `X-HubSpot-Signature-Version: v2` are accepted only when they match the HubSpot v2 source string.

HubSpot ingress endpoints also support shared-secret authentication for TextTraits-owned send-path middleware:

- `X-TextTraits-API-Key: <TEXTTRAITS_HUBSPOT_INGRESS_SECRET>`
- or `X-TextTraits-Signature: sha256=<hex hmac>` where the HMAC uses the raw request body and `TEXTTRAITS_HUBSPOT_INGRESS_SECRET`.
- For production HMAC, include `X-TextTraits-Timestamp: <unix seconds>` and sign `<timestamp>.<raw body>`. Requests outside `TEXTTRAITS_HUBSPOT_SIGNATURE_MAX_AGE_SECONDS` are rejected.

When a HubSpot signature is present, `HUBSPOT_CLIENT_SECRET` must be configured or the request is rejected. When `TEXTTRAITS_HUBSPOT_INGRESS_SECRET` is configured, unsigned non-HubSpot ingress requests are rejected. `TEXTTRAITS_REQUIRE_HUBSPOT_INGRESS_AUTH=true` can be used to fail closed if neither HubSpot nor TextTraits authentication is available.
Set `TEXTTRAITS_REQUIRE_HUBSPOT_SIGNATURE_TIMESTAMP=true` in non-production environments when you want staging to enforce the same replay-window behavior as production.

HubSpot portal IDs are bound to `workspace_id` values such as `hubspot_246356639`. If a request supplies both a portal ID and a mismatched workspace, TextTraits rejects it.
HubSpot source-system values are constrained to HubSpot identifiers on the card/template analysis endpoints to reduce source spoofing.

## Public Card Response

The CRM card, workflow action, synced analyze-and-writeback action, marketing-email preflight, campaign preflight, and bulk preflight responses return the decision, checks, findings, route, policy version, sync status, and safe context IDs needed by HubSpot UI or automation surfaces. They do not expose full configured risk/vague phrase lists or model prediction internals unless developer tools are explicitly enabled.

Idempotency keys are stable by workspace and workflow. Reusing the same key for different content returns `409 Conflict` instead of silently creating a second analysis or overwriting a prior one.

## Review Events

The HubSpot card can record:

- `copy_recommendation`
- `mark_reviewed`
- `send_to_marketing_review`
- `rerun_analysis`
- `assign_reviewer`
- `approve_review`
- `reject_review`
- `resolve_review`
- `add_review_note`

These events store the request ID, action, actor ID when supplied, status, and scrubbed metadata.
Review state is maintained separately with status (`open`, `queued`, `assigned`, `approved`, `rejected`, `resolved`, or `rerun_requested`), assigned reviewer, owner queue, blocker level, SLA due date, resolution timestamp, and notes.
When a connected portal and object context are supplied, `/v1/integrations/hubspot/review-action` also syncs the review state back to HubSpot. It writes `texttraits_review_status`, `texttraits_review_action`, `texttraits_review_updated_at`, and `texttraits_review_updated_by` to the CRM record, updates the HubSpot review task when a task ID is present, and updates or creates the TextTraits Analysis custom-object record by searching for the same `texttraits_request_id`.

HubSpot review-task assignment is configurable. Use a payload owner map or `TEXTTRAITS_HUBSPOT_ROUTE_OWNER_MAP` with real HubSpot owner IDs to map routes such as `Compliance review` or `Marketing review` to the correct reviewer. TextTraits can also use `TEXTTRAITS_HUBSPOT_DEFAULT_REVIEW_OWNER_ID` as a fallback. No reviewer IDs are hardcoded.
The HubSpot settings extension can fetch owners through `/v1/integrations/hubspot/owners/list` and persist portal-specific routing through `/v1/integrations/hubspot/review-routing/config`, so production review tasks can be assigned without copying owner maps into every workflow action.

## Outcomes

Outcome events can be ingested with `POST /v1/integrations/hubspot/outcomes` and joined by `request_id` or `content_hash`.
Supported event types are intentionally open-ended so send systems can report events such as delivered, bounced, complained, opened, clicked, suppressed, unsubscribed, replied, or converted.
HubSpot webhook ingest stores incoming events with tenant/workspace context and can automatically re-score a changed draft when the webhook payload includes reviewable subject/body/html copy. If a HubSpot webhook only supplies metadata, TextTraits returns `copy_unavailable` for that event and leaves the original analysis untouched rather than guessing from metadata.
HubSpot stats sync fetches marketing-email and campaign snapshots through OAuth, stores them as outcome events, and joins them to matching TextTraits analyses by request ID, content hash, or campaign/template context. This keeps performance joins queryable without storing raw draft text.

## OAuth

HubSpot OAuth install is supported. Live campaign, marketing-email, task, list, timeline, and writeback actions require encrypted per-portal token storage:

- Set `TEXTTRAITS_STORE_OAUTH_TOKENS=true`.
- Set `TEXTTRAITS_TOKEN_ENCRYPTION_KEY` to a Fernet key.
- Store HubSpot access and refresh tokens per portal ID.
- Refresh access tokens through HubSpot's OAuth token endpoint.
- Use `POST /api/enterprise/hubspot/connections/<portal_id>/disconnect` to mark a portal disconnected and prevent live API use.

Without encrypted storage, TextTraits can still accept signed HubSpot analysis payloads, but live HubSpot API actions fail closed with a connection/scopes error.

## HubSpot API Audit Logs

Every live HubSpot API request made through the TextTraits client writes a scrubbed audit event. The event records portal ID, method, API path template, HubSpot API version, status code, attempt count, required scopes, duration, and whether an idempotency key was present. It never records access tokens, refresh tokens, request bodies, raw email copy, or the idempotency key itself. Retry and token-refresh retry events are logged separately so admins can diagnose rate limits and auth refreshes without exposing credentials.

## Exports

Admin endpoints provide CSV and JSON exports of analysis history. CSV values are neutralized against spreadsheet formula injection.

Set `TEXTTRAITS_ENTERPRISE_ADMIN_EMAILS` to a comma-separated allowlist before using admin exports, dashboard, or policy controls in production.
Production admin endpoints fail closed if the allowlist is missing.
Set `TEXTTRAITS_REQUIRE_ENTERPRISE_ADMIN_ALLOWLIST=true` in staging to enforce the same admin allowlist behavior before production.

## Policy History

Every policy save writes the current policy and appends an immutable history row. Use:

- `GET /api/enterprise/hubspot/analyses`
- `GET /api/enterprise/hubspot/policy/history`
- `GET /api/enterprise/hubspot/findings`
- `GET /api/enterprise/hubspot/checks`
- `GET /api/enterprise/hubspot/review-states`
- `GET /api/enterprise/hubspot/outcomes`
- `GET /api/enterprise/hubspot/surfaces`
- `GET /api/enterprise/readiness`
- `GET /api/enterprise/hubspot/score-validation`
- `GET /api/enterprise/hubspot/retention`
- `POST /api/enterprise/hubspot/retention`

These endpoints are admin-only.

The readiness endpoint reports deployment blockers without exposing secret values. The score-validation endpoint runs the active policy against built-in clear, vague, and risky email QA cases. The retention endpoint previews old HubSpot analysis records by default; destructive purges require an explicit confirmation payload.

## HubSpot Developer Project

The deployable HubSpot project lives in `hubspot-project/` and includes:

- `hsproject.json`
- `src/app/app-hsmeta.json`
- CRM sidebar app card UI extension for contacts, companies, deals, and tickets
- HubSpot workflow action definitions
- HubSpot app settings page
- HubSpot app home page
- `scripts/validate-project.mjs`

Run:

```bash
cd hubspot-project
npm install
npm run validate
hs project upload
hs project dev
```

## HubSpot Integration Surfaces

TextTraits is not limited to contact-record cards. The same scoring and governance path is exposed for:

- CRM record app cards
- Custom workflow actions
- Synced analyze-and-writeback actions for HubSpot workflows and app cards
- Campaign picker/search
- Marketing email picker/search
- Marketing-email draft/revision preflight
- Generic HubSpot asset snapshot preflight
- Live single-asset fetch and review for copy-bearing assets
- Campaign asset batch preflight
- Campaign creation/update
- Campaign asset association/removal
- Live campaign review across selected HubSpot campaign asset types, with copy-coverage reporting that separates scored assets from metadata-only assets
- Marketing email draft create/update/fetch
- HubSpot review task creation
- HubSpot owner lookup
- Review route owner mapping
- CRM property writeback
- CRM property provisioning for TextTraits score/gate/route/reporting fields
- TextTraits Analysis custom-object record creation
- TextTraits Analysis custom-object schema provisioning
- Timeline event push
- Lists/segments creation
- Lists/segments search and membership preview
- Review segment template creation
- HubSpot webhook ingest
- HubSpot webhook target/subscription management
- HubSpot app uninstall cleanup
- Asset-copy workflow action
- Campaign/email stats sync
- Generic HubSpot bulk email preflight
- Rendered-template tests
- Email outcome/event joins

Marketing-email and campaign endpoints can accept mapped payload snapshots, or use encrypted OAuth token storage to fetch and update HubSpot assets directly. Campaign review can inspect multiple HubSpot Campaigns API asset types in one pass, including `MARKETING_EMAIL`, `FORM`, `LANDING_PAGE`, `WEB_INTERACTIVE`, `AUTOMATION_PLATFORM_FLOW`, `OBJECT_LIST`, `SOCIAL_BROADCAST`, `MARKETING_SMS`, `SITE_PAGE`, and `BLOG_POST`. Campaign and marketing-email actions use HubSpot's documented v3 Marketing APIs, while CMS page/blog fetches use the 2026-03 date-versioned CMS endpoints. Marketing emails, forms, landing pages, site pages, and blog posts are fetched and scored directly when the portal grants those scopes. Owner lookup uses HubSpot's 2026-03 Owners API with the optional `crm.objects.owners.read` scope so reviewer queues can map to real HubSpot owner IDs. The standalone `/v1/integrations/hubspot/assets/analyze` route and the deployable `/v1/integrations/hubspot/workflow-actions/analyze-asset-copy` action let teams map reviewable copy from SMS, social, CTA, and other HubSpot assets without waiting for direct API fetch support. CTAs, workflows, lists, SMS, social posts, and other campaign assets are included in the asset map and marked `metadata_only` unless HubSpot returns enough reviewable copy in the Campaigns API payload or a mapped asset-copy payload is supplied. Live sync still requires granted OAuth scopes, installed app configuration, and customer-approved field mappings.

TextTraits Analysis custom-object records can be associated to HubSpot CRM/campaign/email context only when the portal provides real association type IDs. Configure `TEXTTRAITS_HUBSPOT_ANALYSIS_ASSOCIATION_TYPE_IDS` or pass `analysis_association_type_ids` as JSON, for example `{"contacts":123,"companies":456}`. TextTraits also accepts a full HubSpot `analysis_record_associations` payload. If these IDs are not supplied, the custom-object record is still created with reportable TextTraits fields, but associations are skipped rather than fabricated.

`GET /api/enterprise/hubspot/surfaces` now returns readiness metadata for each surface: required scopes, recommended scopes, whether OAuth/token storage is needed, ready connected portal IDs, and per-portal missing scopes. The HubSpot settings extension renders that data so admins can see whether campaign review, marketing-email sync, CRM writeback, custom-object records, lists, timeline events, webhooks, and stats sync are actually ready for the selected portal instead of seeing a flat implemented label.
`GET /api/enterprise/hubspot/setup-status` adds an admin-facing setup summary grouped by Campaign sync, Workflow actions, Webhook re-scoring, Approval workflow, and Reporting writeback. It also returns last sync activity and attention items such as missing OAuth tokens, missing scopes, disconnected portals, and token-storage blockers.

## Production Requirements

Before an enterprise rollout:

- Use HTTPS and a reviewed public base URL.
- Set `TEXTTRAITS_ENV=production`.
- Set `TEXTTRAITS_ALLOW_DEMO=false`.
- Use hosted Postgres for persistence.
- Configure HubSpot OAuth credentials in the deployment environment.
- Configure encrypted HubSpot OAuth token storage before using live HubSpot API actions.
- Configure `TEXTTRAITS_ENTERPRISE_ADMIN_EMAILS`.
- Configure `HUBSPOT_CLIENT_SECRET` so HubSpot-signed webhooks, lifecycle callbacks, workflow actions, and app-card callbacks can be validated.
- Configure `TEXTTRAITS_HUBSPOT_INGRESS_SECRET` before using TextTraits-owned send-path middleware.
- Upload the HubSpot project from `hubspot-project/`.
- From the HubSpot settings page, run property provisioning, analysis-schema provisioning, and webhook setup for the connected portal.
- Run `python3 tests/production_smoke_test.py` and `python3 tests/security_regression_test.py`.

## HubSpot Uninstall Behavior

HubSpot lifecycle callbacks can call:

`POST /v1/integrations/hubspot/app-uninstalled`

The endpoint uses the same HubSpot ingress authentication path as workflow actions and webhooks. In production it rejects unsigned uninstall callbacks. When a portal ID is supplied, TextTraits clears encrypted access and refresh tokens, marks the portal connection `disconnected`, stores a safe lifecycle outcome event, and returns retention guidance.

Existing analyses, findings, review states, and outcome rows are retained for governance audit until the configured retention policy removes them or an enterprise admin runs the retention purge endpoint. This avoids losing the evidence trail for emails that were scored before uninstall while still removing credentials immediately.
