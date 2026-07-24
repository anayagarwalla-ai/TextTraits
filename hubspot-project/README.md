# TextTraits for HubSpot

This HubSpot project installs TextTraits as a copy decision and review layer inside HubSpot.

## Product contract

TextTraits checks existing copy. It does **not** generate, rewrite, edit, replace, publish, or send the source content.

- Running **Check email** is read-only.
- A check may store a structured TextTraits audit record and source hash.
- It does not update HubSpot fields, create tasks, or change an email.
- Recording a decision in HubSpot is a separate action with an explicit confirmation.
- Server-side writeback flags default to off and require `confirm_side_effects: true`.
- Reviewer guidance describes what must be verified; it never supplies replacement copy.

## Included surfaces

- CRM record sidebar card for contacts, companies, deals, and tickets.
- Compact CRM preview card for the latest decision.
- CRM record tab for checking copy and reading audit detail.
- Help desk sidebar card for existing support-reply copy.
- App home centered on the review queue, campaign checks, and read-only source lookup.
- Settings page for connection status, least-privilege permissions, policy paths, named review owners, feature readiness, and confirmed admin provisioning.
- Flagship **Check copy with TextTraits** workflow action with branchable outputs.
- Read-only asset-copy and campaign-copy workflow actions.

The legacy analyze-and-sync workflow definition is unpublished. It remains in source only to make existing-install migration explicit.

## Source handling

The CRM card prefers associated email engagements, supports marketing email drafts by ID, and falls back to manual paste. It shows source type, source ID, owner, modified time, CRM record, source hash, checker, and check time when those values are available.

The backend stores structured checks, findings, decisions, policy context, and a tenant-scoped content hash. It does not have a separate raw subject/body column in the HubSpot analysis table.

## Workflow outputs

Successful checks return `hs_execution_state=SUCCESS`, including checks whose policy decision is `blocked`. Workflows should branch on:

- `texttraits_gate`
- `texttraits_route`
- `texttraits_reviewer_guidance`
- `texttraits_blocker_level`
- `texttraits_blocker_reason`
- `texttraits_policy_version`
- `texttraits_request_id`
- `texttraits_content_hash`

A blocked content decision means the check succeeded and the workflow should route it for review.

## Backend dependency

The extension calls:

```text
https://texttraits.onrender.com
```

For local testing, run Flask on port `5001`, copy `src/app/local.json.example` to the HubSpot CLI location, and use `hs project dev`. Production `permittedUrls.fetch` remains HTTPS-only.

## Commands

```bash
npm ci
npm run validate
hs project upload
hs project dev
```

## Permissions

OAuth starts with the safe read-oriented HubSpot scope set by default. Write scopes stay optional and are needed only for explicitly enabled features such as CRM decision fields, custom analysis objects, review segments, or timelines.

The settings page shows readiness by feature. Customer admins should grant only the scopes for the surfaces they plan to use.

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

## Pilot checklist

1. Install in a HubSpot sandbox.
2. Confirm read-only checks create no CRM changes.
3. Confirm a review decision requires the in-card confirmation.
4. Map review routes to named HubSpot owners.
5. Verify policy version and retention settings.
6. Test one contact, company, deal, and ticket.
7. Test associated-email, marketing-email, and manual-paste sources.
8. Test workflow branches for ready, review-required, blocked, and technical error.
9. Export an audit sample and verify no raw copy appears in logs.
10. Capture pilot metrics: checks, review rate, blocked rate, median review time, repeat checks, and resolved reviews.
