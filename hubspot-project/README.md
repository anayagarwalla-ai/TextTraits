# TextTraits HubSpot Project

This folder contains the HubSpot developer-platform project that installs TextTraits inside HubSpot instead of leaving it as only external Flask endpoints.

## Included surfaces

- CRM record sidebar app card for contacts, companies, deals, and tickets.
- Custom workflow action that returns score, gate, route, next step, owner queue, blocker level, policy version, request ID, and content hash.
- Synced workflow action that scores a draft, writes TextTraits results back to HubSpot, and opens review work in one step.
- Campaign asset workflow action that fetches a campaign asset map, scores reviewable assets, and returns branchable campaign-health fields.
- App settings page for portal connection, token storage, scopes, enabled surfaces, owner routing, property/schema/segment/webhook setup provisioning, and admin readiness.
- App home page for campaign search/selection, campaign review health, campaign creation, marketing-email search/draft review, asset association, multi-asset campaign maps, and governance summaries.

The campaign review UI sends current HubSpot Campaigns API asset type IDs such as `MARKETING_EMAIL`, `FORM`, `LANDING_PAGE`, `WEB_INTERACTIVE`, `AUTOMATION_PLATFORM_FLOW`, `OBJECT_LIST`, `SOCIAL_BROADCAST`, `MARKETING_SMS`, `SITE_PAGE`, and `BLOG_POST`. The backend still accepts legacy-friendly labels like `WORKFLOW`, `STATIC_LIST`, `SOCIAL_POST`, `SMS`, and `WEBSITE_PAGE`, then normalizes them before calling HubSpot.

## Backend dependency

The UI extension calls the deployed TextTraits backend:

```text
https://texttraits.onrender.com
```

For local testing, run Flask on port `5001` and use HubSpot's local-development proxy. Production `permittedUrls.fetch` stays HTTPS-only; do not add localhost URLs to the uploaded app manifest.
Copy `src/app/local.json.example` to the HubSpot CLI's expected `local.json` location for this project, upload the project configuration, and run `hs project dev`. The example remaps the real production origin to local Flask without changing committed production URLs.

## Commands

```bash
npm ci
npm run validate
hs project upload
hs project dev
```

The home and settings extensions load portal-scoped bootstrap data from signed `/v1/integrations/hubspot/app-home/bootstrap` and `/v1/integrations/hubspot/settings/bootstrap` requests. They do not depend on a separate browser login to TextTraits and never receive data for another portal. Settings can load `/v1/integrations/hubspot/owners/list` and save `/v1/integrations/hubspot/review-routing/config` so review tasks route to real HubSpot owners.

When creating TextTraits Analysis custom-object records, associations require real portal-specific HubSpot association type IDs. Configure the synced workflow input `analysis_association_type_ids` or set `TEXTTRAITS_HUBSPOT_ANALYSIS_ASSOCIATION_TYPE_IDS` to JSON such as `{"contacts":123,"companies":456}`. TextTraits will not invent these IDs; without them it creates the analysis record and reports association setup as skipped.

Live HubSpot API calls write scrubbed audit events with method, path template, API version, status, attempts, required scopes, and idempotency-key presence. Tokens, raw email content, request bodies, and the idempotency key itself are not logged.

## Required production environment

- `HUBSPOT_CLIENT_ID`
- `HUBSPOT_CLIENT_SECRET`
- `TEXTTRAITS_PUBLIC_BASE_URL`
- `TEXTTRAITS_STORE_OAUTH_TOKENS=true`
- `TEXTTRAITS_TOKEN_ENCRYPTION_KEY`
- `TEXTTRAITS_HUBSPOT_INGRESS_SECRET`
- `TEXTTRAITS_REQUIRE_HUBSPOT_INGRESS_AUTH=true`
- `TEXTTRAITS_CONTENT_HASH_SECRET`
- `TEXTTRAITS_ENTERPRISE_ADMIN_EMAILS`

The app requests optional HubSpot marketing/campaign/content/forms/revenue/timeline/automation/owners scopes so portals can install the CRM-only subset first, then reconnect when they want campaign creation, marketing email sync, form or CMS asset scoring, campaign revenue reporting, timeline events, workflow automation, or owner-aware review routing. `npm run validate` verifies that the manifest scope list matches the backend OAuth allowlist.
