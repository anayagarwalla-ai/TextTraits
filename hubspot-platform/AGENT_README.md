# Agent Handoff: HubSpot Project Build And Upload

This file is for agents taking over the TextTraits HubSpot developer-platform work.
It explains how to connect to the HubSpot project, render the local project files,
validate/lint, and push new HubSpot builds.

## Current HubSpot Project

- HubSpot account: `simeon-sayer [standard]`
- Account ID: `246356639`
- Project name: `texttraits-hubspot-platform`
- Project ID: `317122346`
- App name: `TextTraits Email Fit`
- App ID: `41302866`
- Platform version: `2026.03`
- Last verified deployed build: `#4`
- Project URL: `https://app.hubspot.com/developer-projects/246356639/project/texttraits-hubspot-platform`

Deployed components:

- `CARD` `texttraits_email_fit_card`
- `WORKFLOW_ACTION` `texttraits_score_email_workflow_action`

## Repo Paths

Run commands from the repo root unless a step says otherwise:

```powershell
C:\Users\simsa\OneDrive\Desktop\TextTraits\TextTraits-hubspot-platform
```

Tracked HubSpot templates live in:

```text
hubspot-platform/templates/
```

Rendered HubSpot project files are generated into:

```text
hubspot-platform/rendered/
```

`hubspot-platform/rendered/` is ignored by Git because it may contain account-specific rendered files and local `node_modules`.

## Do Not Commit

Never commit or print:

- `.env`
- `C:\Users\simsa\.hscli\config.yml`
- HubSpot personal access keys
- HubSpot client secrets
- `hubspot-platform/rendered/`
- `node_modules/`

## First-Time HubSpot CLI Setup

Install the HubSpot CLI if `hs --version` fails:

```powershell
npm install -g @hubspot/cli
hs --version
```

Authenticate to the HubSpot account:

```powershell
hs account auth
```

The CLI uses a HubSpot personal access key. Paste it into the terminal prompt only.
Do not paste keys into Codex chat.

Verify account access:

```powershell
hs account list
```

Expected account:

```text
simeon-sayer [standard] (246356639)
```

## Render The HubSpot Project

Render from templates before every upload:

```powershell
python scripts\render_hubspot_project.py --base-url https://texttraits.onrender.com --support-email support@example.com
```

If the backend is deployed somewhere else, replace `--base-url` with that public HTTPS origin.

Important: the HubSpot app currently points to:

```text
https://texttraits.onrender.com
```

If that backend URL is down or does not contain the current branch, the HubSpot shell can still build and deploy, but the CRM card/workflow action will not complete live TextTraits callback requests.

## Validate, Lint, And Upload

From the rendered project directory:

```powershell
cd hubspot-platform\rendered
hs project validate
```

Install UI extension lint dependencies after rendering:

```powershell
Push-Location src\app\cards
npm install
Pop-Location
```

Run lint:

```powershell
hs project lint --install-missing-deps=false
```

Upload and deploy:

```powershell
hs project upload
```

The project has auto-deploy enabled, so successful uploads deploy automatically.

Verify:

```powershell
hs project info
hs project list-builds --limit 4
```

Expected healthy state:

```text
Deployed Build: #4 or newer
Components:
CARD              texttraits_email_fit_card
WORKFLOW_ACTION   texttraits_score_email_workflow_action
```

## Backend Env For Live Callback Testing

The Flask backend needs HubSpot env values before live OAuth/signature callback testing:

```powershell
python scripts\setup_hubspot_env.py
```

Required backend keys:

```text
TEXTTRAITS_PUBLIC_BASE_URL=https://texttraits.onrender.com
HUBSPOT_CLIENT_ID=<HubSpot developer app client ID>
HUBSPOT_CLIENT_SECRET=<HubSpot developer app client secret>
HUBSPOT_REQUIRE_SIGNATURE=true
HUBSPOT_SIGNATURE_TOLERANCE_SECONDS=300
```

The env helper writes `.env`, which is ignored by Git.

## Local Verification Commands

Run these before committing backend/template changes:

```powershell
python -m compileall scripts texttraits_app tests
python tests\hubspot_platform_test.py
python tests\v1_email_api_test.py
python tests\security_regression_test.py
hs project validate
hs project lint --install-missing-deps=false
```

## Common HubSpot Build Issues

- Workflow action input fields must have exactly one `supportedValueType`.
- OAuth apps should include the `oauth` required scope explicitly.
- UI extension card packages need `eslint.config.js`, lint scripts, and pinned lint dependencies.
- Render and lint sequentially on Windows; do not run `npm install` inside `hubspot-platform/rendered` while re-rendering that same folder.
- If the CLI says the project does not exist, run `hs project upload --forceCreate` only after confirming the account ID is `246356639`.
