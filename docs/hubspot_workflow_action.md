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
  "inputFields": {
    "subject": "Renewal workflow follow-up",
    "body": "Existing email draft body"
  }
}
```

The response includes workflow output fields:

- `texttraits_score`
- `texttraits_gate`
- `texttraits_route`
- `texttraits_send_ready`
- `texttraits_next_step`
- `texttraits_owner_queue`
- `texttraits_blocker_level`
- `texttraits_policy_version`

Recommended workflow branches:

- If `texttraits_gate = ready`, continue to the sending system.
- If `texttraits_gate = needs_review`, route to marketing or lifecycle-review queue.
- If `texttraits_gate = blocked`, create a task for the owner and stop automated send progression.
- If `texttraits_route = Compliance review`, route to the compliance/legal review queue.

Task creation and field-writeback should be configured in HubSpot using these output fields. TextTraits does not create HubSpot tasks by itself unless a future private-app token and workspace policy explicitly allow that action.

