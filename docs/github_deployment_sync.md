# GitHub Deployment Sync

This repo is configured so GitHub can be the source of truth for both deployed
parts of TextTraits.

## Render Backend

Render deploys the Flask backend from the repository root using `render.yaml`.

The current Render blueprint setting is:

```yaml
autoDeployTrigger: checksPass
```

That means Render should deploy the linked branch only after GitHub checks pass.
If the existing Render service was created manually instead of from the blueprint,
open the Render dashboard and set **Auto-Deploy** to **After CI Checks Pass** for
the `texttraits` service.

## HubSpot Project

HubSpot does not need to pull from a local folder anymore. The GitHub Actions
workflow at `.github/workflows/hubspot-project-deploy.yml` validates and deploys
the project from:

```text
hubspot-project/
```

The workflow runs on pushes to `main` that touch `hubspot-project/**`, and it can
also be run manually from the GitHub Actions tab.

## Required GitHub Secrets

Add these repository secrets in GitHub before expecting HubSpot deploys to run:

```text
HUBSPOT_ACCOUNT_ID
HUBSPOT_PERSONAL_ACCESS_KEY
```

Do not commit these values to the repo. The workflow intentionally skips the
HubSpot upload when the secrets are missing.

## Expected Flow

```text
Push to GitHub main
  -> GitHub CI validates the Flask app and HubSpot project
  -> Render deploys backend after checks pass
  -> HubSpot GitHub Action uploads hubspot-project/
  -> HubSpot deploys the uploaded project build
```

