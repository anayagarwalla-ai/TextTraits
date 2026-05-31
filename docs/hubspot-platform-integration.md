# HubSpot Platform Integration

TextTraits now has a first HubSpot developer-platform path for the Enterprise-Only branch. The goal is to let a HubSpot user invoke TextTraits from inside HubSpot while keeping TextTraits non-generative: it scores existing email text and returns governance fields for review, routing, and audit joins.

## Integration shape

| Layer | HubSpot surface | TextTraits endpoint | Purpose |
| --- | --- | --- | --- |
| CRM record | App card / UI extension | `GET /v1/integrations/hubspot/crm-card` | Show a safe TextTraits card context on contact, company, or deal records. |
| CRM record action | App card fetch | `POST /v1/integrations/hubspot/crm-card/analyze-email` | Analyze an existing draft pasted or supplied from HubSpot context. |
| Workflow automation | Custom workflow action | `POST /v1/integrations/hubspot/workflow-actions/analyze-email` | Score workflow email fields and return output fields for branching. |
| Setup | Platform config | `GET /v1/integrations/hubspot/platform-config` | Expose required env, callback URLs, writeback fields, and local scaffold commands. |
| OAuth | HubSpot OAuth app | `/api/integrations/hubspot/oauth/start` and `/api/integrations/hubspot/oauth/callback` | Connect a HubSpot account once credentials and redirect URLs are configured. |

## Backend env

Add these to `.env` with `python scripts/setup_hubspot_env.py`:

```text
TEXTTRAITS_PUBLIC_BASE_URL=https://your-public-texttraits-domain.example
HUBSPOT_CLIENT_ID=<from HubSpot developer app>
HUBSPOT_CLIENT_SECRET=<from HubSpot developer app>
HUBSPOT_REQUIRE_SIGNATURE=true
HUBSPOT_SIGNATURE_TOLERANCE_SECONDS=300
```

`HUBSPOT_CLIENT_SECRET` is used for OAuth token exchange and HubSpot request-signature validation. Do not commit `.env`.

## HubSpot project files

Templates live in:

```text
hubspot-platform/templates/
```

Render account/domain-specific project files with:

```powershell
python scripts/render_hubspot_project.py --base-url https://your-public-texttraits-domain.example --support-email support@example.com
```

Rendered files are written to `hubspot-platform/rendered/`, which is ignored by Git.

## HubSpot CLI flow

The local machine needs the HubSpot CLI authenticated to the developer account:

```powershell
npm install -g @hubspot/cli
hs account auth
cd hubspot-platform/rendered
hs project upload
```

Use `hs project dev` after upload for iterative UI extension testing.

## Security behavior

- Sandbox/local calls work without HubSpot keys.
- Production HubSpot callbacks should set `HUBSPOT_REQUIRE_SIGNATURE=true`.
- The backend validates HubSpot v3 signatures using `X-HubSpot-Signature-v3` and `X-HubSpot-Request-Timestamp` when configured.
- Responses return compact analysis and workflow fields, not raw stored email bodies.
- TextTraits does not send, rewrite, or generate HubSpot emails in this branch.

## Current caveats

- This is a scaffold plus backend callback layer, not a verified live HubSpot install.
- HubSpot CLI upload requires developer-account authentication outside this repo.
- The card UI is intentionally simple so we can test invocation first; deeper CRM property prefill can be added after HubSpot account testing confirms the available context payload.
