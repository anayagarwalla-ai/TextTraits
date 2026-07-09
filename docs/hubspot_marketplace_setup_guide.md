# TextTraits Email Fit HubSpot Setup Guide

TextTraits Email Fit is a HubSpot app that reviews existing campaign and email copy before it is routed or sent. It does not generate copy. It returns structured decision-support fields such as score, gate, blocker reason, route, reviewer queue, policy version, request ID, and content hash.

## Before You Start

- Use a HubSpot account where you can install apps, configure workflows, and manage marketing assets.
- Use the TextTraits production URL configured in `TEXTTRAITS_PUBLIC_BASE_URL`.
- Confirm the TextTraits backend has HubSpot OAuth credentials, token encryption, ingress authentication, and a hosted database configured.
- Confirm the HubSpot project in `hubspot-project/` has been uploaded and deployed.

## Install The App

1. Open the TextTraits HubSpot install URL from the deployed TextTraits app or the HubSpot Marketplace listing.
2. Review the required and optional scopes in HubSpot.
3. Approve the OAuth authorization request.
4. Return to HubSpot after the install callback completes.
5. Open the TextTraits app settings page in HubSpot and confirm the connected portal appears.

## Configure TextTraits In HubSpot

1. Open the TextTraits settings page in HubSpot.
2. Confirm encrypted token storage is ready.
3. Review the granted scopes and missing optional scopes for the selected portal.
4. Run CRM property provisioning for the object types your team wants to report on.
5. Run TextTraits Analysis custom-object schema provisioning if your team wants durable analysis records.
6. Run review-segment provisioning if your team wants HubSpot lists for ready, needs-review, and blocked records.
7. Load HubSpot owners and save review-route owner mappings for Marketing review, Compliance review, and fallback review tasks.
8. Configure webhook subscriptions if your team wants automatic re-scoring for copy-bearing draft changes.
9. Configure real association type IDs before associating TextTraits Analysis custom-object records with CRM records.

## Use The App

- CRM card: paste or inspect an existing draft on contacts, companies, deals, or tickets.
- Workflow action: branch automations using `ready`, `needs_review`, and `blocked`.
- Campaign review: fetch campaign assets, score reviewable copy, and map metadata-only assets.
- Marketing email sync: create, update, fetch, score, and route marketing-email drafts.
- Generic asset review: score mapped copy from forms, landing pages, site pages, blog posts, SMS, social posts, CTAs, or similar assets.
- Review tasks: route blocked or needs-review drafts to the configured HubSpot owner or review queue.
- Owner routing: fetch HubSpot owners and persist portal-specific review-route assignments.
- Reporting: use TextTraits CRM properties, custom objects, findings, review states, approval statuses, and outcomes in HubSpot or TextTraits dashboards.

## Scope Summary

Required scopes are kept small so the app can install with core CRM functionality. Optional scopes unlock deeper HubSpot surfaces only when the customer wants them.

| Scope | Why TextTraits Uses It |
| --- | --- |
| `oauth` | Complete OAuth install, refresh access tokens, and identify the connected portal. |
| `crm.objects.contacts.read` / `write` | Read CRM context and write TextTraits score/gate/route fields on contact records. |
| `crm.objects.companies.read` / `write` | Read and write company-level review context. |
| `crm.objects.deals.read` / `write` | Read and write deal-level review context. |
| `crm.objects.owners.read` | Support owner-aware review routing and admin setup. |
| `crm.objects.custom.read` / `write` | Provision and write TextTraits Analysis custom-object records. |
| `crm.lists.read` / `write` | Read existing HubSpot segments, preview memberships, and create review segments for ready, needs-review, and blocked records. |
| `tickets` | Support ticket-side review cards and property writeback where enabled. |
| `marketing-email` | Create, update, fetch, score, and sync marketing-email drafts. |
| `marketing.campaigns.read` / `write` | Create campaigns, fetch campaign assets, associate assets, and produce campaign-level health. |
| `marketing.campaigns.revenue.read` | Join campaign performance context when enabled. |
| `forms` | Fetch and score HubSpot form copy when granted. |
| `content` | Fetch and score CMS landing page, site page, and blog-post copy when granted. |
| `timeline` | Write TextTraits review events into HubSpot record timelines. |
| `automation` | Register and run workflow actions where the portal supports it. |

## Data Handling

- TextTraits stores structured analysis rows, normalized findings/checks, review states, outcome events, and tenant-scoped content hashes.
- Full draft bodies are not required for long-term governance joins; content hashes and structured findings are used for reporting.
- OAuth tokens are encrypted per portal when token storage is enabled.
- Access and refresh tokens are never returned by public API responses.
- Audit events scrub tokens, secrets, request bodies, and direct personal contact details.
- Retention controls are available from the enterprise admin API and should be configured per customer.

## Disconnect And Uninstall

- Disconnect: an enterprise admin can disconnect a portal from TextTraits. This clears stored HubSpot OAuth tokens and prevents further live HubSpot API calls.
- Uninstall: HubSpot can call `/v1/integrations/hubspot/app-uninstalled`. TextTraits clears stored OAuth tokens, marks the portal disconnected, and records a safe lifecycle event.
- Existing analyses, findings, review states, and outcome rows are retained for governance audit until the configured retention policy or an admin retention purge removes them.

## Troubleshooting

- If live campaign review says `metadata_only`, HubSpot returned asset metadata without reviewable copy or the portal has not granted the optional scope needed for direct fetch.
- If a live action returns missing-scope details, reconnect the app with the required optional scope enabled.
- If custom-object associations are skipped, configure real HubSpot association type IDs for the portal.
- If webhook or workflow calls fail in production, verify HubSpot request signing and `TEXTTRAITS_HUBSPOT_INGRESS_SECRET`.

## Support Notes

For a pilot, start with CRM card review, marketing-email preflight, and campaign review. Add property writeback, custom-object records, workflow actions, webhooks, and stats sync after the customer's HubSpot admin approves field mappings and scopes.
Once review owners are mapped, enable approval workflow sync so approved, rejected, resolved, assigned, and queued states update HubSpot tasks, CRM properties, and the TextTraits Analysis custom object from the same card actions reviewers already use.
