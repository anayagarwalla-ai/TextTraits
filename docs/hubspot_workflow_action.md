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

The HubSpot CRM card shows a workflow branch preview after each analysis. It mirrors these output fields so admins can demo the ready/review/blocked path before wiring workflow branches.

Task creation and field-writeback should be configured in HubSpot using these output fields. TextTraits does not create HubSpot tasks by itself unless a future private-app token and workspace policy explicitly allow that action.

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
