import fs from "node:fs";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "..");
const requiredFiles = [
  "hsproject.json",
  "contracts/analysis-contract.json",
  "src/app/app-hsmeta.json",
  "src/app/cards/texttraits-email-fit-card-hsmeta.json",
  "src/app/cards/texttraits-email-fit-preview-hsmeta.json",
  "src/app/cards/texttraits-email-fit-tab-hsmeta.json",
  "src/app/cards/texttraits-email-fit-helpdesk-hsmeta.json",
  "src/app/cards/TextTraitsEmailFitCard.jsx",
  "src/app/workflow-actions/texttraits-analyze-email-hsmeta.json",
  "src/app/workflow-actions/texttraits-analyze-asset-copy-hsmeta.json",
  "src/app/workflow-actions/texttraits-analyze-and-sync-hsmeta.json",
  "src/app/workflow-actions/texttraits-review-campaign-assets-hsmeta.json",
  "src/app/settings/texttraits-settings-hsmeta.json",
  "src/app/settings/TextTraitsSettings.jsx",
  "src/app/home/texttraits-home-hsmeta.json",
  "src/app/home/TextTraitsHome.jsx",
  "src/app/components/HomePanels.jsx",
  "src/app/lib/api.js",
  "src/app/lib/context.js",
  "src/app/lib/form-state.js",
];

for (const relativePath of requiredFiles) {
  const absolutePath = path.join(root, relativePath);
  if (!fs.existsSync(absolutePath)) {
    throw new Error(`Missing HubSpot project file: ${relativePath}`);
  }
  if (relativePath.endsWith(".json")) {
    JSON.parse(fs.readFileSync(absolutePath, "utf8"));
  }
}

const appConfig = JSON.parse(fs.readFileSync(path.join(root, "src/app/app-hsmeta.json"), "utf8"));
const analysisContract = JSON.parse(fs.readFileSync(path.join(root, "contracts/analysis-contract.json"), "utf8"));
const scopes = [
  ...appConfig.config.auth.requiredScopes,
  ...appConfig.config.auth.optionalScopes,
];
for (const fetchUrl of appConfig.config?.permittedUrls?.fetch || []) {
  if (new URL(fetchUrl).protocol !== "https:") {
    throw new Error(`HubSpot production fetch allowlist must use HTTPS: ${fetchUrl}`);
  }
}
for (const requiredScope of ["oauth", "marketing-email", "marketing.campaigns.read", "crm.lists.read"]) {
  if (!scopes.includes(requiredScope)) {
    throw new Error(`Missing expected HubSpot scope: ${requiredScope}`);
  }
}
for (const optionalScope of ["forms", "content", "crm.objects.owners.read"]) {
  if (!scopes.includes(optionalScope)) {
    throw new Error(`Missing optional HubSpot asset-copy scope: ${optionalScope}`);
  }
}

const homeSource = fs.readFileSync(path.join(root, "src/app/home/TextTraitsHome.jsx"), "utf8");
const homePanelSource = fs.readFileSync(path.join(root, "src/app/components/HomePanels.jsx"), "utf8");
const homeSources = `${homeSource}\n${homePanelSource}`;
for (const expected of [
  "/v1/integrations/hubspot/app-home/bootstrap",
  "/v1/integrations/hubspot/campaigns/review",
  "/v1/integrations/hubspot/campaigns/list",
  "/v1/integrations/hubspot/marketing-emails/list",
  "/v1/integrations/hubspot/marketing-emails/pre-publish-guardrail",
  "/v1/integrations/hubspot/bulk/import-assets",
  "/v1/integrations/hubspot/lists/search",
  "/v1/integrations/hubspot/lists/memberships",
  "/v1/integrations/hubspot/assets/analyze",
  "/v1/integrations/hubspot/assets/fetch-and-analyze",
  "Today’s review work",
  "Check a campaign",
  "Search campaigns",
  "Search marketing emails",
  "Run pre-send check",
  "Review context",
  "Bulk copy import",
  "Import and check copy",
  "Other copy sources",
  "Check pasted asset copy",
  "Fetch supported asset from HubSpot",
  "Read-only segment inspection",
  "Search segments",
  "Preview selected segment",
  "TextTraits never rewrites source copy",
  "SOCIAL_BROADCAST",
  "MARKETING_SMS",
  "SEQUENCE",
  "Copy coverage:",
  "Asset-level results",
]) {
  if (!homeSources.includes(expected)) {
    throw new Error(`HubSpot home page missing campaign review control: ${expected}`);
  }
}
for (const forbidden of [
  "Create HubSpot campaign",
  "Create marketing email draft",
  "Update marketing email draft",
  "Attach email to campaign",
  "Update segment members",
  "/v1/integrations/hubspot/analyze-and-sync",
]) {
  if (homeSources.includes(forbidden)) {
    throw new Error(`HubSpot home must not expose copy or campaign mutation control: ${forbidden}`);
  }
}

const settingsSource = fs.readFileSync(path.join(root, "src/app/settings/TextTraitsSettings.jsx"), "utf8");
for (const expected of [
  "/v1/integrations/hubspot/properties/provision",
  "/v1/integrations/hubspot/analysis-schema/provision",
  "/v1/integrations/hubspot/lists/create-review-segments",
  "/v1/integrations/hubspot/webhooks/configure",
  "/v1/integrations/hubspot/settings/bootstrap",
  "Connection and permissions",
  "Read-only by default",
  "Policies and approval paths",
  "Setup checklist",
  "Workflow readiness",
  "Refresh readiness",
  "Permissions needed",
  "HubSpot portal",
  "Tokens unavailable",
  "/v1/integrations/hubspot/owners/list",
  "/v1/integrations/hubspot/review-routing/config",
  "Review owners",
  "Marketing review",
  "Compliance review",
  "Regional review",
  "CRM fields and automation setup",
  "Confirm portal change",
  "Data controls",
]) {
  if (!settingsSource.includes(expected)) {
    throw new Error(`HubSpot settings page missing setup endpoint: ${expected}`);
  }
}

const cardSource = fs.readFileSync(path.join(root, "src/app/cards/TextTraitsEmailFitCard.jsx"), "utf8");
for (const expected of [
  "/v1/integrations/hubspot/crm-card/analyze-email",
  "/v1/integrations/hubspot/marketing-emails/fetch",
  "useCrmProperties",
  "useAssociations",
  "Check email",
  "This check is read-only",
  "Reviewer guidance",
  "Confirm and record",
  "confirm_side_effects",
  "writeback_properties",
]) {
  if (!cardSource.includes(expected)) {
    throw new Error(`HubSpot card missing safe review behavior: ${expected}`);
  }
}
for (const forbidden of ["/v1/integrations/hubspot/analyze-and-sync", "Analyze draft", "Open campaign analysis", "Generate rewrite", "Replace copy"]) {
  if (cardSource.includes(forbidden)) {
    throw new Error(`HubSpot card contains forbidden or misleading behavior: ${forbidden}`);
  }
}

const workflowUids = new Set();
const componentUids = new Set();
for (const [relativePath, expectedContract] of Object.entries(analysisContract.components || {})) {
  const definition = JSON.parse(fs.readFileSync(path.join(root, relativePath), "utf8"));
  if (!definition.uid || componentUids.has(definition.uid)) {
    throw new Error(`HubSpot component must have a unique uid: ${relativePath}`);
  }
  componentUids.add(definition.uid);
  if (definition.type !== expectedContract.type) {
    throw new Error(`${relativePath} type mismatch: expected ${expectedContract.type}, received ${definition.type}`);
  }
  if (definition.config?.entrypoint !== expectedContract.entrypoint) {
    throw new Error(`${relativePath} entrypoint mismatch: expected ${expectedContract.entrypoint}`);
  }
  const entrypoint = path.join(root, "src", expectedContract.entrypoint.replace(/^\/app\//, "app/"));
  if (!fs.existsSync(entrypoint)) {
    throw new Error(`${relativePath} references missing entrypoint: ${expectedContract.entrypoint}`);
  }
}

for (const [relativePath, expectedContract] of Object.entries(analysisContract.workflowActions || {})) {
  const definition = JSON.parse(fs.readFileSync(path.join(root, relativePath), "utf8"));
  if (!definition.uid || workflowUids.has(definition.uid)) {
    throw new Error(`Workflow action must have a unique uid: ${relativePath}`);
  }
  workflowUids.add(definition.uid);
  if (componentUids.has(definition.uid)) {
    throw new Error(`HubSpot uid is reused by a component and workflow action: ${definition.uid}`);
  }
  const config = definition.config || {};
  const actionPath = new URL(config.actionUrl).pathname;
  if (actionPath !== expectedContract.endpoint) {
    throw new Error(`${relativePath} endpoint mismatch: expected ${expectedContract.endpoint}, received ${actionPath}`);
  }
  const inputNames = (config.inputFields || []).map((field) => field?.typeDefinition?.name).filter(Boolean);
  const outputNames = (config.outputFields || []).map((field) => field?.name).filter(Boolean);
  if (new Set(inputNames).size !== inputNames.length || new Set(outputNames).size !== outputNames.length) {
    throw new Error(`${relativePath} contains duplicate input or output field names.`);
  }
  for (const expected of expectedContract.requiredInputs || []) {
    if (!inputNames.includes(expected)) throw new Error(`${relativePath} missing required input: ${expected}`);
  }
  for (const expected of expectedContract.requiredOutputs || []) {
    if (!outputNames.includes(expected)) throw new Error(`${relativePath} missing required output: ${expected}`);
  }
}

console.log("HubSpot project scaffold validated.");
