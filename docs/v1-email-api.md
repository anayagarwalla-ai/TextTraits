# TextTraits V1 Enterprise Email API

TextTraits v1 is a non-generative email optimization layer. It scores existing
emails, returns deterministic policy findings, and stores governance data that
can be joined back to campaign, template, and delivery outcomes.

## Product Data

The deep-research integration plan is available as product data at
`GET /api/enterprise/integration-plan` and is also included in the governance
dashboard response. It captures the target matrix, integration layers, request
schema, recommended platforms, and recommended primary target:
`journey_workflow_gate`.

The current target list is HubSpot workflows, Salesforce Marketing Cloud,
Braze Canvas/Currents, SendGrid or SES middleware, and warehouse/CDP feedback.

## Analyze Email

`POST /v1/email/analyze`

Browser clients use the normal CSRF token. Server-to-server clients can set
`TEXTTRAITS_API_KEY` and send `X-TextTraits-Api-Key`. To restrict server keys,
set `TEXTTRAITS_API_KEY_SCOPES` to comma-separated `workspace:path` scopes, for
example `marketing-prod:/v1/email/analyze,*:/v1/webhooks/post-send`.

### Enterprise Request Fields

In addition to `subject`, `body`, `audience`, `intent`, `channel`, and
`assets`, the endpoint accepts enterprise context:

- `tenant_id`, `workspace_id`, `source_system`, `analysis_mode`
- `campaign_id`, `journey_id`, `step_id`, `template_id`, `template_version`
- `locale`, `headers`, `consent_context`, `delivery_context`
- `recipient_context`, `personalization_context`, and nested `message`

`analysis_mode` is expected to be one of `authoring_lint`, `pre_send_gate`,
`send_path_middleware`, `post_send_analytics`, `batch_feedback`, or
`direct_api`.

The response never returns the raw email body. It does return request IDs,
content hashes, content hash variants, policy version, gate decision, structured
findings, local model metadata, enterprise context, and a safe template-render
summary.

See `samples/enterprise-context-analyze-request.json`.

## Template Render Tests

`POST /v1/templates/render-test`

The render-test harness checks Liquid-style `{{ first_name }}`,
Handlebars-style `{{user.firstName}}`, `%FIRST_NAME%`, and `[first_name]`
tokens against sample context. It reports resolved and unresolved tokens,
headers, links, unsubscribe state, and safe body/subject length. Set
`include_rendered_preview` only for internal testing when an admin needs to see
the rendered preview.

## Mock Enterprise Flows

The mock adapters route through the same v1 policy engine:

- `POST /v1/integrations/hubspot/workflow-actions/analyze-email`
- `POST /v1/integrations/salesforce/journey-builder/activity`
- `POST /v1/integrations/sendgrid-ses/middleware`
- `POST /v1/integrations/braze/canvas-gate`
- `POST /v1/integrations/marketo/smart-campaign-gate`
- `POST /v1/integrations/iterable/workflow-gate`
- `POST /v1/integrations/warehouse/feedback-import`

`POST /v1/integrations/simulate` lets an admin paste a HubSpot, Salesforce,
SendGrid/SES, Braze, Marketo, Iterable, or warehouse payload and inspect the
mapped TextTraits inputs, output writeback, manifest, and render-test summary.

## Failure Behavior

Workspace policy is managed through `GET` and `PUT /v1/governance/policy`.
Policies include environment separation with `policy_environment` set to
`sandbox`, `staging`, or `production`.

Rule-family behavior is configured through `rule_family_modes`:

- `fail_closed`: a high finding blocks send.
- `review`: a high finding routes to review.
- `fail_open`: a high finding is reported but does not block when score passes.

Critical findings still block. Global thresholds such as `min_ready_score` and
`high_severity_requires_review` remain available for compatibility.

## Send-Path Budgets

`POST /v1/integrations/sendgrid-ses/middleware` reports a `latency_budget`
object with elapsed time, configured timeout, budget pass/fail, idempotency
window, and idempotency key. Configure `send_path_timeout_ms` and
`idempotency_window_seconds` in the workspace policy.

## Webhooks And Outcome Joins

`POST /v1/webhooks/post-send` accepts provider outcomes such as delivered,
bounced, complained, opened, clicked, suppressed, and unsubscribed. Events join
back to analyses by `request_id` or `content_hash`.

Webhook signature hooks are available with `TEXTTRAITS_WEBHOOK_SECRET`. When the
secret is configured, send `X-TextTraits-Signature: sha256=<hmac>` over the raw
request body. When the secret is not configured, events are accepted with
`signature_status: not_configured` so local mock flows can still run.

## Governance Storage

The migration layer creates normalized tables for enterprise reporting:

- `email_analyses` stores request metadata, gate status, score, model version,
  policy version, campaign IDs, template IDs, source system, and content hashes.
- `email_findings` stores one queryable row per finding with rule pack,
  severity, category, title, remediation, and request/content join keys.
- `email_outcomes` stores normalized delivery and engagement events.
- `webhook_events` stores deduped webhook deliveries and signature status.
- `sample_imports` stores chunked batch summaries with replay-safe resume
  metadata.
- `policy_bundle_versions` stores policy history by workspace and environment.

`GET /v1/governance/dashboard` includes gate counts, source trends, top failing
rule packs, worst campaigns, risky template versions, joined outcomes, recent
webhooks, imports, field mappings, policy history, and the integration plan.

`GET /v1/governance/export?type=analyses|findings|outcomes|joins&format=json|csv`
exports normalized rows for admin reporting.

## Batch Imports

`POST /v1/samples/import` and
`POST /v1/integrations/warehouse/feedback-import` support `chunk_index`,
`chunk_total`, and an opaque `resume_token`. The API stores whether a resume
cursor was supplied and a digest of it, while redacting the raw token from
responses.

See `samples/warehouse-feedback-import-request.json`.
