# TextTraits Enterprise Pitch Readiness

This branch is positioned as a non-generative email optimization layer for companies that already use email, CRM, marketing automation, or warehouse workflows. The free pitch path should prove workflow value without claiming paid infrastructure, live credentials, customer data, or legal approval.

## What is ready to show now

- Analyze: paste an existing email and return score, gate decision, findings, routes, hashes, and model signals.
- Governance: inspect campaign, template, source-system, finding, policy, and outcome panels.
- Simulator: paste provider-shaped payloads for HubSpot, Salesforce, Braze, Marketo, Iterable, SendGrid/SES, or warehouse feedback.
- Integrations: save recommended field mappings and export the OpenAPI contract.
- HubSpot scaffold: render a developer-platform project template for a CRM app card and custom workflow action once a public TextTraits HTTPS URL and HubSpot developer credentials exist.
- Admin: show role scaffolding, scoped API-key planning, webhook signing tests, policy history, and audit events.
- Trust: show Privacy, Terms, Security, Deployment, Model Card, and Pilot Plan pages.
- Demo data: empty dashboards show clearly labeled synthetic examples only; real workspace rows replace them after analyses/imports/webhooks run.

## Free demo script

1. Open the app and explain that TextTraits does not write email copy; it scores existing messages before they leave existing tools.
2. Analyze a strong sample email and point to the gate decision, request ID, content hash, policy version, and model confidence summary.
3. Analyze a risky sample with claims, vague language, unresolved tokens, or missing unsubscribe paths and show the review queue.
4. Open Dashboard and explain the example-data label if the workspace is fresh.
5. Open Simulator, load a provider example, run it, and show normalized decision/writeback fields.
6. Open Integrations and save a recommended mapping for one provider.
7. Open Admin, run the webhook signature test with a temporary local secret, and show that no credential material is stored.
8. Open Security, Deployment, Model Card, and Pilot Plan to show what is ready versus what still requires customer input.

## Optional local seed

To create synthetic rows in the local database for a more realistic demo, run:

```bash
python3 scripts/seed_enterprise_demo.py --workspace-id demo_enterprise
```

These rows are sample data only. Do not present them as customer data.

## Free validation metrics

- Review capture rate: percent of messages routed to review or block.
- Reviewer agreement: percent of gate decisions a human reviewer accepts.
- False pass rate: percent of messages marked ready that reviewers would have held.
- False review rate: percent of messages held that reviewers consider safe.
- Template risk: top template versions by review/block count and average score.
- Outcome join coverage: percent of delivery/open/click/complaint/unsubscribe events joined to request IDs or content hashes.
- Send-path latency: median and p95 analysis latency from API logs or local harness output.

## Do not claim yet

- Live HubSpot, Salesforce, Braze, Marketo, Iterable, SendGrid, SES, or warehouse connections without credentials.
- A verified HubSpot install until the rendered project has been uploaded through an authenticated HubSpot developer account.
- SSO/SAML, enterprise legal approval, production hosting, SOC 2, DPA, SLA, paid monitoring, or customer-specific compliance signoff.
- Automatic production send gates until the customer has validated policy thresholds and model behavior on approved samples.
