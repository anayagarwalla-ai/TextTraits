# Enterprise Rollout Readiness

TextTraits now exposes admin-only readiness and validation surfaces that are meant to support enterprise pilots without overstating the current deployment.

## Implemented In The App

- Production readiness report: `GET /api/enterprise/readiness`
- HubSpot score validation report: `GET /api/enterprise/hubspot/score-validation`
- HubSpot retention preview and purge controls:
  - `GET /api/enterprise/hubspot/retention?days=90`
  - `POST /api/enterprise/hubspot/retention`
- HubSpot developer project scaffold in `hubspot-project/`
- HubSpot live API actions for one-call analyze-and-sync, campaign/email picker search, campaigns, multi-asset live campaign review, single-asset fetch-and-review, generic asset copy preflight, marketing emails, tasks, approval workflow sync, lists/segments search and review segments, timeline events, webhooks, property/schema provisioning, writeback, and stats sync
- HubSpot owner lookup and portal-specific review-route owner mapping for review task assignment
- HubSpot Marketplace setup guide at `/hubspot/setup-guide` with scope, install, disconnect, uninstall, and data-handling notes
- HubSpot Marketplace readiness manifest: `GET /api/enterprise/hubspot/marketplace-readiness`
- Governance dashboard rollups for:
  - gate counts
  - route counts
  - outcome counts and rates
  - source health
  - campaign health
  - template health
  - top failing checks
  - recent blocked drafts
- Admin console UI sections for readiness, score QA, retention, campaign health, template health, source trends, and outcome rates.

## What The Readiness Report Checks

- Runtime model availability
- Score validation harness availability
- Production environment mode
- HTTPS public URL
- Hosted Postgres with SSL
- Transactional email configuration
- Enterprise admin allowlist
- Secure session cookies
- HubSpot OAuth credentials
- HubSpot developer project scaffold
- Encrypted HubSpot token storage
- HubSpot ingress authentication
- Tenant-scoped content hashing secret
- OAuth token storage posture
- Developer tools and demo mode
- Error reporting
- Retention controls

## What Still Requires External Setup

These items cannot be honestly completed in code without real enterprise infrastructure or customer decisions:

- Real production domain and HTTPS deployment
- Production environment variables and secrets
- HubSpot OAuth client ID and client secret
- `TEXTTRAITS_STORE_OAUTH_TOKENS=true`
- `TEXTTRAITS_TOKEN_ENCRYPTION_KEY`
- HubSpot HMAC ingress secret shared with routing middleware
- Uploaded HubSpot project from `hubspot-project/`
- Connected HubSpot portal with granted scopes for campaign, marketing email, custom-object, property, list, timeline, and webhook actions
- Portal-approved TextTraits CRM property/schema provisioning
- Enterprise admin email allowlist
- Transactional email provider
- Hosted Postgres database with SSL
- Error-reporting destination
- Customer-approved retention window
- Customer-approved historical samples for outcome validation
- Legal/compliance materials such as DPA, SOC 2 plan, security questionnaire, and support/SLA terms
- Optional SSO/SAML/SCIM provider setup

## Recommended Pilot Positioning

Pitch TextTraits as a controlled HubSpot email-quality governance pilot:

- Score existing email drafts before routing.
- Use the synced HubSpot workflow action when teams want one step to score the draft, write TextTraits fields back to HubSpot, and open review work.
- Use the asset-copy workflow action when non-email HubSpot assets, such as forms, pages, SMS, social posts, or CTAs, already have mapped copy available in a workflow.
- Save route-owner mappings in the HubSpot settings page so Marketing review and Compliance review tasks land with real HubSpot owners.
- Explain every decision with checks, findings, policy version, owner queue, and next step.
- Route risky or vague drafts to the right review queue.
- Store normalized governance and outcome data without storing raw HubSpot email body text in analysis history.
- Use readiness and score-validation reports during the demo to show what is configured and what remains customer-owned.
