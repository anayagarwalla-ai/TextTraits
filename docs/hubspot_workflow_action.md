# HubSpot Workflow Action

TextTraits exposes a HubSpot workflow gate at:

`POST /v1/integrations/hubspot/workflow-actions/analyze-email`

The action accepts the same payload shape as the CRM card:

```json
{
  "workspace_id": "hubspot_246356639",
  "source_system": "hubspot",
  "analysis_mode": "send_path_gate",
  "campaign_id": "renewal-q3",
  "template_id": "renewal-follow-up-v2",
  "idempotency_key": "workflow-123:email-456",
  "inputFields": {
    "email_subject": "Renewal workflow follow-up",
    "email_body": "Existing email draft body",
    "workflow_name": "Renewal workflow"
  }
}
```

HubSpot workflow subject/body inputs are configured as mapped object-property fields. Use enrolled-record properties or prior action outputs for real send-path routing; keep `workflow_name` as the static label for the workflow/campaign.

The response includes workflow output fields:

- `texttraits_score`
- `texttraits_gate`
- `texttraits_route`
- `texttraits_send_ready`
- `texttraits_next_step`
- `texttraits_owner_queue`
- `texttraits_blocker_level`
- `texttraits_policy_version`
- `texttraits_request_id`
- `texttraits_content_hash`

Recommended workflow branches:

- If `texttraits_gate = ready`, continue to the sending system.
- If `texttraits_gate = needs_review`, route to marketing or lifecycle-review queue.
- If `texttraits_gate = blocked`, create a task for the owner and stop automated send progression.
- If `texttraits_route = Compliance review`, route to the compliance/legal review queue.

The HubSpot project definition for this workflow action lives at:

`hubspot-project/src/app/workflow-actions/texttraits-analyze-email-hsmeta.json`

For workflows that should update HubSpot as part of the same step, TextTraits also registers:

`hubspot-project/src/app/workflow-actions/texttraits-analyze-and-sync-hsmeta.json`

That action calls:

`POST /v1/integrations/hubspot/analyze-and-sync`

The synced action analyzes the draft, returns the same branchable score/gate/route fields, writes TextTraits properties back to the enrolled HubSpot record when object context is supplied, opens review state/task work for non-ready drafts, and can create a TextTraits Analysis custom-object record or timeline event when the portal setup provides those object/template IDs. The extra workflow outputs are:

- `texttraits_sync_status`
- `texttraits_sync_actions`

If the TextTraits Analysis custom object should be associated to the enrolled contact, company, deal, ticket, campaign, or email context, configure real HubSpot association type IDs instead of relying on placeholders. Use the synced workflow input `analysis_association_type_ids`, a payload field with the same name, or `TEXTTRAITS_HUBSPOT_ANALYSIS_ASSOCIATION_TYPE_IDS`, formatted as JSON such as `{"contacts":123,"companies":456}`. TextTraits can also accept a full HubSpot `analysis_record_associations` / `associations` array when a portal already has exact association payloads. If no real association type ID is supplied, TextTraits creates the durable custom-object record and reports that associations were skipped.

The HubSpot CRM app card shows a workflow branch preview after each analysis. It mirrors these output fields so admins can demo the ready/review/blocked path before wiring workflow branches.

For asset-level gates outside the email object, TextTraits also registers:

`hubspot-project/src/app/workflow-actions/texttraits-analyze-asset-copy-hsmeta.json`

That action calls:

`POST /v1/integrations/hubspot/workflow-actions/analyze-asset-copy`

Use it when a HubSpot workflow, prior custom action, or mapped record property already has reviewable copy from a form, landing page, site page, blog post, SMS, social post, CTA, or similar campaign asset. It returns the same score/gate/route fields as the email workflow action plus:

- `texttraits_asset_type`
- `texttraits_asset_id`
- `texttraits_asset_name`

Those fields let HubSpot branches and audit reports identify which asset was reviewed without opening the saved analysis payload.

For campaign-level gates, TextTraits also registers:

`hubspot-project/src/app/workflow-actions/texttraits-review-campaign-assets-hsmeta.json`

That action calls:

`POST /v1/integrations/hubspot/workflow-actions/review-campaign-assets`

It fetches the selected campaign asset types through the live HubSpot Campaigns API, scores reviewable assets, and returns workflow branch fields:

- `texttraits_campaign_health`
- `texttraits_gate`
- `texttraits_route`
- `texttraits_next_step`
- `texttraits_assets_seen`
- `texttraits_analyzed_count`
- `texttraits_ready_count`
- `texttraits_needs_review_count`
- `texttraits_blocked_count`
- `texttraits_skipped_count`
- `texttraits_error_count`
- `texttraits_average_score`
- `texttraits_copy_coverage`
- `texttraits_content_hash`

`texttraits_copy_coverage` lists asset types that were actually scored. The detailed API summary also reports metadata-only, fetch-error, and analysis-error asset types so admins can tell whether a campaign was fully reviewed or only mapped because HubSpot did not return reviewable copy for a non-email asset.

TextTraits can also create HubSpot review tasks and write structured results back to CRM records when encrypted OAuth token storage is enabled:

- `POST /v1/integrations/hubspot/tasks/create-review`
- `POST /v1/integrations/hubspot/properties/writeback`
- `POST /v1/integrations/hubspot/analysis-records/create`
- `POST /v1/integrations/hubspot/timeline-events/create`

Review-task ownership can be configured without hardcoding IDs. Pass `route_owner_map`, `review_owner_map`, `owner_map`, or `queue_owner_map` in the action payload, or set `TEXTTRAITS_HUBSPOT_ROUTE_OWNER_MAP` to a JSON object such as `{"Compliance review":"12345","Marketing review":"67890"}`. TextTraits resolves the owner from the route, owner queue, blocker level, or gate. `TEXTTRAITS_HUBSPOT_DEFAULT_REVIEW_OWNER_ID` can provide a fallback owner when no route-specific mapping exists.

For native HubSpot setup, the app settings page can fetch real owners with:

`POST /v1/integrations/hubspot/owners/list`

That route uses HubSpot's 2026-03 Owners API and the optional `crm.objects.owners.read` scope. Admins can then persist a portal-specific route map with:

`POST /v1/integrations/hubspot/review-routing/config`

Saved mappings are used automatically by review-task creation, so workflow payloads do not need to include owner IDs on every call.

## Marketing Email Preflight

TextTraits also accepts HubSpot marketing-email draft snapshots at:

`POST /v1/integrations/hubspot/marketing-emails/analyze`

Use this endpoint when a HubSpot marketing email asset, revision, middleware step, or export job needs a pre-send decision before scheduling:

```json
{
  "workspace_id": "hubspot_246356639",
  "portal_id": "246356639",
  "marketingEmail": {
    "id": "email-123",
    "subject": "Factory tour checklist",
    "html": "<p>Hi {{first_name}}, please review the checklist by Friday. {{unsubscribe_link}}</p>",
    "campaignId": "factory-tour-q3",
    "fromEmail": "marketing@example.com",
    "replyTo": "reply@example.com",
    "state": "DRAFT"
  }
}
```

The endpoint strips HTML to text for scoring, preserves safe HubSpot context IDs, stores only the tenant-scoped content digest plus normalized findings/checks, and returns the same `outputFields` contract as the CRM card and workflow action.

With encrypted HubSpot OAuth token storage, TextTraits can also operate on live marketing-email assets:

- `POST /v1/integrations/hubspot/marketing-emails/create-draft`
- `POST /v1/integrations/hubspot/marketing-emails/update-draft`
- `POST /v1/integrations/hubspot/marketing-emails/fetch`
- `POST /v1/integrations/hubspot/marketing-emails/pre-publish-guardrail`

The fetch route can score the actual HubSpot draft returned by the Marketing Emails API. The pre-publish guardrail fetches the real HubSpot marketing email and returns `publish_allowed`, gate, route, next step, blocker, score, and policy version without publishing or mutating the email.

### Generic HubSpot Asset Copy Review

TextTraits also accepts non-email HubSpot asset snapshots:

`POST /v1/integrations/hubspot/assets/analyze`

Use this when an app page, middleware step, or custom integration already has reviewable copy from a form, landing page, site page, blog post, SMS, social post, CTA, or similar campaign asset. HubSpot workflows should use `/workflow-actions/analyze-asset-copy`, which wraps the same normalization with workflow-specific telemetry. Both endpoints preserve `asset_type`, `asset_id`, `asset_name`, campaign context, and copy source in the saved analysis context and return branchable asset identity fields when present.

When encrypted OAuth token storage is available, TextTraits can fetch directly supported assets and then analyze them:

`POST /v1/integrations/hubspot/assets/fetch-and-analyze`

Direct fetch currently supports marketing emails, forms, landing pages, site pages, blog posts, and sequences. Ads, CTAs, workflow steps, marketing SMS, and social posts should use `/assets/analyze` with a mapped payload, or appear in campaign review as `metadata_only` until HubSpot returns reviewable copy.

## Campaign And Batch Preflight

Campaign-level analysis is available at:

`POST /v1/integrations/hubspot/campaigns/analyze`

Generic HubSpot email-like batches are available at:

`POST /v1/integrations/hubspot/bulk/analyze-emails`

CSV or warehouse-style campaign asset imports are available at:

`POST /v1/integrations/hubspot/bulk/import-assets`

The email batch endpoints accept `emails`, `marketing_emails`, `marketingEmails`, `assets`, or `items` arrays. Each item can use HubSpot marketing email fields such as `id`, `revision_id`, `subject`, `html`, `campaignId`, `templateId`, `fromEmail`, and `replyTo`. The asset import endpoint accepts `assets`, `rows`, `records`, or CSV text with fields such as `asset_type`, `asset_id`, `asset_name`, `asset_copy`, `region`, `business_unit`, and `audience_type`.

```json
{
  "workspace_id": "hubspot_246356639",
  "portal_id": "246356639",
  "campaign": {"id": "campaign-q3", "name": "Q3 lifecycle campaign"},
  "emails": [
    {
      "id": "email-ready",
      "revision_id": "r1",
      "subject": "Factory tour checklist",
      "html": "<p>Hi Brian, please review the checklist by Friday. {{unsubscribe_link}}</p>"
    }
  ]
}
```

The response contains a campaign summary with analyzed count, dropped count, gate counts, average score, errors, and the per-email analysis payloads. `TEXTTRAITS_HUBSPOT_MAX_BATCH_EMAILS` controls the batch cap; the default is 50.

With encrypted HubSpot OAuth token storage, TextTraits can also create/update campaigns and attach campaign assets:

- `POST /v1/integrations/hubspot/campaigns/list`
- `POST /v1/integrations/hubspot/campaigns/create`
- `POST /v1/integrations/hubspot/campaigns/update`
- `POST /v1/integrations/hubspot/campaigns/assets`
- `POST /v1/integrations/hubspot/campaigns/associate-asset`
- `POST /v1/integrations/hubspot/campaigns/review`

Campaign asset association supports HubSpot Campaigns API asset types such as ads, marketing emails, forms, landing pages, CTAs, workflows, social posts, lists, SMS, sequences, website pages, and blog posts. The live campaign review endpoint accepts current HubSpot asset IDs such as `MARKETING_EMAIL`, `FORM`, `LANDING_PAGE`, `AD_CAMPAIGN`, `WEB_INTERACTIVE`, `AUTOMATION_PLATFORM_FLOW`, `OBJECT_LIST`, `SOCIAL_BROADCAST`, `MARKETING_SMS`, `SEQUENCE`, `SITE_PAGE`, and `BLOG_POST`. Legacy-friendly labels such as `WORKFLOW`, `STATIC_LIST`, `SOCIAL_POST`, `SMS`, and `WEBSITE_PAGE` are still accepted and normalized before TextTraits calls HubSpot. TextTraits uses HubSpot's documented Campaigns and Marketing Email APIs for campaign/email actions, uses 2026-03 CMS APIs where HubSpot exposes date-versioned content endpoints, and uses the Sequences API for sequence reads when the portal grants automation access. Marketing emails, forms, landing pages, site pages, blog posts, and sequences are fetched directly when the portal grants the needed access; other asset types are included in the campaign asset map and are scored only when the Campaigns API payload or a mapped copy payload returns enough reviewable copy. If HubSpot returns only metadata for an asset, TextTraits marks it `metadata_only` and reports `coverage_score`, `coverage_label`, and `coverage_gap_assets` instead of pretending the copy was reviewed.

Mapped Salesforce outcome import is available at:

`POST /v1/integrations/hubspot/salesforce/outcomes/import`

This endpoint accepts customer-mapped Salesforce campaign, opportunity, lead, contact, and placement outcome rows. It does not call Salesforce without credentials.

Marketing-email picker/search is available at:

- `POST /v1/integrations/hubspot/marketing-emails/list`

Use these list endpoints in HubSpot app-home flows so admins can select real campaigns and email drafts instead of copying IDs between screens.

## HubSpot Setup Provisioning

Connected portals can provision the HubSpot-native reporting and re-scoring setup from TextTraits:

- `POST /v1/integrations/hubspot/properties/provision`
- `POST /v1/integrations/hubspot/analysis-schema/provision`
- `POST /v1/integrations/hubspot/owners/list`
- `POST /v1/integrations/hubspot/review-routing/config`
- `POST /v1/integrations/hubspot/review-action`
- `POST /v1/integrations/hubspot/webhooks/configure`
- `POST /v1/integrations/hubspot/lists/search`
- `POST /v1/integrations/hubspot/lists/memberships`
- `POST /v1/integrations/hubspot/lists/create-review-segments`

The property provisioning endpoint creates the CRM fields needed for HubSpot workflows, filters, reports, and lists: score, gate, route, policy version, last checked timestamp, blocker reason, request ID, content hash, review status, review action, review updated timestamp, and review actor. The analysis-schema endpoint creates or verifies a TextTraits Analysis custom-object schema for durable analysis records. The review-action endpoint records approvals, rejections, resolutions, and queue changes locally, then syncs them to CRM properties, HubSpot review tasks, and the TextTraits Analysis custom object when OAuth context and IDs are present. The segment search and membership endpoints read existing HubSpot segments through the 2026-03 Lists API before creating duplicates. The review-segment endpoint creates default Ready, Needs review, and Blocked HubSpot segments from the TextTraits gate field. The owner lookup and review-routing endpoints let admins map Marketing review, Compliance review, and fallback review work to real HubSpot owners. The webhook configuration endpoint sets the HubSpot app webhook target and subscribes to record-change events that can trigger re-scoring.

## Template Testing

Use `POST /v1/integrations/hubspot/template-test` to render Liquid/Handlebars-style tokens against sample recipient context before routing:

```json
{
  "sample_context": {
    "first_name": "Brian",
    "company": "HubSpot",
    "unsubscribe_link": "https://example.com/unsubscribe"
  },
  "headers": {
    "from": "marketing@example.com",
    "reply_to": "sales@example.com"
  },
  "inputFields": {
    "email_subject": "Hi {{first_name}}",
    "email_body": "Please review {{company}} before Friday. {{unsubscribe_link}}"
  }
}
```

The response reports rendered subject/body, unresolved tokens, links, unsubscribe state, and header checks.

## Outcome Joins

Send systems can report outcomes back to TextTraits with `POST /v1/integrations/hubspot/outcomes`:

```json
{
  "request_id": "hubspot_workflow_action-abc123",
  "content_hash": "sha256...",
  "workspace_id": "hubspot_246356639",
  "event_type": "opened",
  "event_id": "provider-event-id"
}
```

Outcomes are queryable in admin dashboards and exports by request ID or content hash.

HubSpot webhooks and stats sync can also feed outcome records:

- `POST /v1/integrations/hubspot/webhooks/receive`
- `POST /v1/integrations/hubspot/stats/sync`

Webhook ingest validates HubSpot or TextTraits ingress signatures, stores the event for outcome/governance joins, and automatically re-scores only when the webhook payload contains reviewable email copy such as subject/body/html or a marketing-email snapshot. Metadata-only campaign/email events are returned with `copy_unavailable` so admins know they need a HubSpot fetch/sync step or richer webhook mapping before TextTraits can re-score the draft.

Stats sync can fetch a single marketing email by ID, or fetch a campaign, its selected asset lists, and marketing-email asset details. Each snapshot is stored as an outcome event and joined back to the matching TextTraits analysis by request ID, content hash, or campaign/template context when available.

HubSpot segment operations are available for review queues and campaign hygiene:

- `POST /v1/integrations/hubspot/lists/create`
- `POST /v1/integrations/hubspot/lists/search`
- `POST /v1/integrations/hubspot/lists/memberships`
- `POST /v1/integrations/hubspot/lists/memberships/update`
- `POST /v1/integrations/hubspot/lists/create-review-segments`

Membership updates call HubSpot's 2026-03 Lists API add, remove, or add-and-remove endpoints. Use them for `MANUAL` or `SNAPSHOT` segments; `DYNAMIC` segments should be updated by changing the filter branch or the record properties that drive the segment.

## HubSpot Surface Registry

Admins can inspect the implemented HubSpot coverage at:

`GET /api/enterprise/hubspot/surfaces`

For an install-specific setup summary, use:

`GET /api/enterprise/hubspot/setup-status?portal_id=<portal-id>`

The registry lists CRM record cards, email workflow actions, asset-copy workflow actions, synced analyze-and-writeback actions, campaign/email picker surfaces, marketing-email preflight and pre-publish guardrail, campaign preflight, live campaign review, campaign creation, campaign asset association, draft sync, owner lookup, review-route owner mapping, staffing workflow templates, approval-chain templates, setup wizard, task creation, approval workflow sync, property writeback/provisioning, custom-object records/schema provisioning, timeline events, lists/segments create and search, review-segment templates, webhook ingest/management, stats sync, bulk email/asset preflight, rendered-template testing, Salesforce outcome mapping, and outcome joins, including the expected mapping fields for each surface.
The setup-status endpoint groups those surfaces into Campaign sync, Workflow actions, Webhook re-scoring, Approval workflow, Reporting writeback, and Staffing workflow fit, with last sync activity and admin-attention items.

Marketplace lifecycle cleanup is available at:

`POST /v1/integrations/hubspot/app-uninstalled`

HubSpot or an admin automation can send the uninstall callback with `portalId` / `hubId`. TextTraits clears stored OAuth tokens, marks the portal disconnected, records a safe lifecycle event, and leaves scored-analysis records under the configured retention policy for audit.
