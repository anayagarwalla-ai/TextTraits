# TextTraits HubSpot Platform Scaffold

This folder is the first real HubSpot developer-platform bridge for the Enterprise-Only branch.
It keeps HubSpot-specific project files separate from the Flask app so the repo remains runnable
without a HubSpot developer account.

## What this scaffold does

- Defines a HubSpot app shell that can call the TextTraits backend from HubSpot UI extension code.
- Adds a CRM app-card concept for contacts, companies, and deals.
- Adds a custom workflow action concept that posts existing email subject/body fields to TextTraits.
- Points HubSpot callbacks at the backend endpoints implemented under `/v1/integrations/hubspot/*`.
- Keeps account-specific rendered files out of Git in `hubspot-platform/rendered/`.

## Required backend env

Run this from the repo root when you have the HubSpot developer app credentials:

```powershell
python scripts/setup_hubspot_env.py
```

Expected keys:

- `TEXTTRAITS_PUBLIC_BASE_URL`: public HTTPS URL for the TextTraits backend.
- `HUBSPOT_CLIENT_ID`: HubSpot developer app client ID.
- `HUBSPOT_CLIENT_SECRET`: HubSpot developer app client secret, also used for signed request validation.
- `HUBSPOT_REQUIRE_SIGNATURE`: set `true` before accepting live HubSpot callbacks.

## Render the HubSpot project

```powershell
python scripts/render_hubspot_project.py --base-url https://your-public-texttraits-domain.example --support-email support@example.com
```

The rendered project will appear in:

```text
hubspot-platform/rendered/
```

## HubSpot CLI flow

Install/authenticate the HubSpot CLI, then run upload/dev commands from the rendered folder:

```powershell
npm install -g @hubspot/cli
hs account auth
cd hubspot-platform/rendered
hs project upload
```

Use `hs project dev` for local iterative development after the HubSpot account is authenticated.

## Backend endpoints

- `GET /v1/integrations/hubspot/platform-config`
- `GET /v1/integrations/hubspot/crm-card`
- `POST /v1/integrations/hubspot/crm-card/analyze-email`
- `POST /v1/integrations/hubspot/workflow-actions/analyze-email`

The backend can run in sandbox mode without HubSpot keys. Live HubSpot callbacks should use request-signature validation.
