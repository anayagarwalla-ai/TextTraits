import fs from "node:fs";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "..");
const requiredFiles = [
  "hsproject.json",
  "src/app/app-hsmeta.json",
  "src/app/cards/texttraits-email-fit-card-hsmeta.json",
  "src/app/cards/TextTraitsEmailFitCard.jsx",
  "src/app/workflow-actions/texttraits-analyze-email-hsmeta.json",
  "src/app/workflow-actions/texttraits-analyze-asset-copy-hsmeta.json",
  "src/app/workflow-actions/texttraits-analyze-and-sync-hsmeta.json",
  "src/app/workflow-actions/texttraits-review-campaign-assets-hsmeta.json",
  "src/app/settings/texttraits-settings-hsmeta.json",
  "src/app/settings/TextTraitsSettings.jsx",
  "src/app/home/texttraits-home-hsmeta.json",
  "src/app/home/TextTraitsHome.jsx",
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
const scopes = [
  ...appConfig.config.auth.requiredScopes,
  ...appConfig.config.auth.optionalScopes,
];
for (const requiredScope of ["oauth", "marketing-email", "marketing.campaigns.read", "marketing.campaigns.write", "crm.lists.read", "crm.lists.write"]) {
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
for (const expected of [
  "/v1/integrations/hubspot/campaigns/review",
  "/v1/integrations/hubspot/campaigns/list",
  "/v1/integrations/hubspot/campaigns/create",
  "/v1/integrations/hubspot/marketing-emails/list",
  "/v1/integrations/hubspot/marketing-emails/create-draft",
  "/v1/integrations/hubspot/marketing-emails/update-draft",
  "/v1/integrations/hubspot/marketing-emails/fetch",
  "/v1/integrations/hubspot/marketing-emails/pre-publish-guardrail",
  "/v1/integrations/hubspot/bulk/import-assets",
  "/v1/integrations/hubspot/salesforce/outcomes/import",
  "/api/enterprise/hubspot/staffing-workflow-templates",
  "/api/enterprise/hubspot/randstad-readiness",
  "/v1/integrations/hubspot/lists/search",
  "/v1/integrations/hubspot/lists/memberships",
  "/v1/integrations/hubspot/lists/memberships/update",
  "/v1/integrations/hubspot/assets/analyze",
  "/v1/integrations/hubspot/assets/fetch-and-analyze",
  "/v1/integrations/hubspot/analyze-and-sync",
  "Review campaign assets",
  "Find HubSpot campaigns",
  "Find marketing email drafts",
  "Create HubSpot campaign",
  "Update marketing email draft",
  "Run pre-publish guardrail",
  "Enterprise staffing context",
  "Staffing workflow templates",
  "Campaign dashboard rollups",
  "Bulk asset import",
  "Score imported assets",
  "Salesforce outcome mapping",
  "Import Salesforce outcome",
  "Single asset copy review",
  "Analyze mapped asset copy",
  "Fetch and review supported asset",
  "Marketing email draft",
  "HubSpot segments",
  "Find segments",
  "Preview segment members",
  "Update segment members",
  "Record IDs to add",
  "Record IDs to remove",
  "Segment matches",
  "Segment member preview",
  "WEB_INTERACTIVE",
  "AUTOMATION_PLATFORM_FLOW",
  "OBJECT_LIST",
  "SOCIAL_BROADCAST",
  "MARKETING_SMS",
  "AD_CAMPAIGN",
  "SEQUENCE",
  "Coverage:",
  "Reviewed asset types",
  "Metadata-only asset types",
]) {
  if (!homeSource.includes(expected)) {
    throw new Error(`HubSpot home page missing campaign review control: ${expected}`);
  }
}

const settingsSource = fs.readFileSync(path.join(root, "src/app/settings/TextTraitsSettings.jsx"), "utf8");
for (const expected of [
  "/v1/integrations/hubspot/properties/provision",
  "/v1/integrations/hubspot/analysis-schema/provision",
  "/v1/integrations/hubspot/lists/create-review-segments",
  "/v1/integrations/hubspot/webhooks/configure",
  "/api/enterprise/hubspot/setup-status",
  "/api/enterprise/hubspot/setup-wizard",
  "/api/enterprise/hubspot/approval-chain-templates",
  "Setup status",
  "Guided HubSpot setup",
  "Approval chain templates",
  "Campaign sync",
  "Workflow actions",
  "Webhook re-scoring",
  "Admin attention",
  "Refresh setup status",
  "Required scopes",
  "Selected portal",
  "Portal has no stored tokens",
  "/v1/integrations/hubspot/owners/list",
  "/v1/integrations/hubspot/review-routing/config",
  "Review routing owners",
  "Marketing review owner ID",
  "Compliance review owner ID",
  "Regional owner review ID",
]) {
  if (!settingsSource.includes(expected)) {
    throw new Error(`HubSpot settings page missing setup endpoint: ${expected}`);
  }
}

const cardSource = fs.readFileSync(path.join(root, "src/app/cards/TextTraitsEmailFitCard.jsx"), "utf8");
if (!cardSource.includes("Open campaign analysis")) {
  throw new Error("HubSpot card should expose an Open campaign analysis action.");
}
for (const expected of ["/v1/integrations/hubspot/analyze-and-sync", "texttraits_sync_status"]) {
  if (!cardSource.includes(expected)) {
    throw new Error(`HubSpot card missing synced analysis behavior: ${expected}`);
  }
}
for (const expected of ["approve_review", "reject_review", "Approve", "Reject"]) {
  if (!cardSource.includes(expected)) {
    throw new Error(`HubSpot card missing approval workflow control: ${expected}`);
  }
}
for (const expected of ["sync_hubspot", "task_id", "taskIdFromSync"]) {
  if (!cardSource.includes(expected)) {
    throw new Error(`HubSpot card missing approval workflow sync behavior: ${expected}`);
  }
}

const syncedWorkflowDefinition = JSON.parse(fs.readFileSync(path.join(root, "src/app/workflow-actions/texttraits-analyze-and-sync-hsmeta.json"), "utf8"));
const syncedInputNames = new Set(syncedWorkflowDefinition.config.inputFields.map((field) => field.typeDefinition.name));
if (!syncedInputNames.has("analysis_association_type_ids")) {
  throw new Error("Synced workflow action missing analysis association type ID input.");
}
const syncedOutputNames = new Set(syncedWorkflowDefinition.config.outputFields.map((field) => field.name));
for (const expected of ["texttraits_score", "texttraits_gate", "texttraits_sync_status", "texttraits_sync_actions"]) {
  if (!syncedOutputNames.has(expected)) {
    throw new Error(`Synced workflow action missing output field: ${expected}`);
  }
}

const assetCopyWorkflowDefinition = JSON.parse(fs.readFileSync(path.join(root, "src/app/workflow-actions/texttraits-analyze-asset-copy-hsmeta.json"), "utf8"));
if (!assetCopyWorkflowDefinition.config.actionUrl.includes("/v1/integrations/hubspot/workflow-actions/analyze-asset-copy")) {
  throw new Error("Asset copy workflow action should call the asset copy workflow endpoint.");
}
const assetCopyInputNames = new Set(assetCopyWorkflowDefinition.config.inputFields.map((field) => field.typeDefinition.name));
for (const expected of ["asset_type", "asset_id", "asset_name", "asset_copy", "campaign_id", "analysis_mode"]) {
  if (!assetCopyInputNames.has(expected)) {
    throw new Error(`Asset copy workflow action missing input field: ${expected}`);
  }
}
const assetCopyOutputNames = new Set(assetCopyWorkflowDefinition.config.outputFields.map((field) => field.name));
for (const expected of ["texttraits_score", "texttraits_gate", "texttraits_route", "texttraits_asset_type", "texttraits_asset_id", "texttraits_asset_name", "texttraits_request_id", "texttraits_content_hash"]) {
  if (!assetCopyOutputNames.has(expected)) {
    throw new Error(`Asset copy workflow action missing output field: ${expected}`);
  }
}

const campaignWorkflowDefinition = JSON.parse(fs.readFileSync(path.join(root, "src/app/workflow-actions/texttraits-review-campaign-assets-hsmeta.json"), "utf8"));
if (!campaignWorkflowDefinition.config.actionUrl.includes("/v1/integrations/hubspot/workflow-actions/review-campaign-assets")) {
  throw new Error("Campaign workflow action should call the campaign asset review workflow endpoint.");
}
const campaignOutputNames = new Set(campaignWorkflowDefinition.config.outputFields.map((field) => field.name));
for (const expected of ["texttraits_campaign_health", "texttraits_gate", "texttraits_route", "texttraits_analyzed_count", "texttraits_blocked_count", "texttraits_copy_coverage"]) {
  if (!campaignOutputNames.has(expected)) {
    throw new Error(`Campaign workflow action missing output field: ${expected}`);
  }
}
for (const expected of ["texttraits_coverage_score", "texttraits_coverage_label"]) {
  if (!campaignOutputNames.has(expected)) {
    throw new Error(`Campaign workflow action missing coverage output field: ${expected}`);
  }
}

console.log("HubSpot project scaffold validated.");
