import React, {useEffect, useState} from "react";
import {Alert, Box, Button, Divider, Flex, Input, LoadingSpinner, Text, TextArea, hubspot} from "@hubspot/ui-extensions";
import {hubspotApi} from "../lib/api";
import {portalIdFromContext} from "../lib/context";
import {useFormState} from "../lib/form-state";
import {CampaignPanel, EnterpriseContextFields, HubSpotActionResult, MarketingEmailPanel, SegmentPanel} from "../components/HomePanels";

const CAMPAIGN_ASSET_OPTIONS = [
  {value: "MARKETING_EMAIL", label: "Marketing email"},
  {value: "FORM", label: "Form"},
  {value: "LANDING_PAGE", label: "Landing page"},
  {value: "AD_CAMPAIGN", label: "Ad campaign"},
  {value: "WEB_INTERACTIVE", label: "CTA"},
  {value: "AUTOMATION_PLATFORM_FLOW", label: "Workflow"},
  {value: "OBJECT_LIST", label: "Static list"},
  {value: "SOCIAL_BROADCAST", label: "Social post"},
  {value: "MARKETING_SMS", label: "SMS"},
  {value: "SEQUENCE", label: "Sequence"},
  {value: "SITE_PAGE", label: "Website page"},
  {value: "BLOG_POST", label: "Blog post"},
];

const DEFAULT_CAMPAIGN_ASSET_TYPES = CAMPAIGN_ASSET_OPTIONS.map((asset) => asset.value);
const DEFAULT_FORM_VALUES = {
  portalId: "",
  campaignId: "",
  campaignName: "",
  emailId: "",
  emailName: "",
  emailSubject: "",
  emailBody: "",
  templatePath: "@hubspot/email/dnd/welcome.html",
  assetType: "LANDING_PAGE",
  assetId: "",
  assetName: "",
  assetCopy: "",
  assetTypes: DEFAULT_CAMPAIGN_ASSET_TYPES,
  segmentQuery: "TextTraits",
  segmentObjectTypeId: "0-1",
  segmentProcessingType: "",
  segmentId: "",
  segmentAddIds: "",
  segmentRemoveIds: "",
  audienceType: "candidate",
  region: "US",
  businessUnit: "Staffing",
  jobId: "",
  skillFamily: "",
  jobFamily: "",
  recruiter: "",
  clientAccount: "",
  candidateStatus: "",
  atsSystem: "",
  jobBoard: "",
  bulkCsv: "asset_type,asset_id,asset_name,asset_copy,region,business_unit,audience_type\nMARKETING_SMS,sms-1,Job alert SMS,\"Hi {{first_name}}, reply by Friday if you want details on job JR-204 in logistics.\",US,Staffing,candidate",
  salesforceJson: '{"event_type":"placement_created","salesforce_campaign_id":"701-demo","salesforce_opportunity_id":"006-demo","audience_type":"client","region":"US","skill_family":"Logistics"}',
};

hubspot.extend(({context}) => <TextTraitsHome context={context} />);

function TextTraitsHome({context}) {
  const [state, setState] = useState({loading: true, dashboard: null, readiness: null, templates: [], error: ""});
  const form = useFormState({...DEFAULT_FORM_VALUES, portalId: portalIdFromContext(context)});
  const {
    portalId, campaignId, campaignName, emailId, emailName, emailSubject, emailBody, templatePath,
    assetType, assetId, assetName, assetCopy, assetTypes, segmentQuery, segmentObjectTypeId,
    segmentProcessingType, segmentId, segmentAddIds, segmentRemoveIds, audienceType, region,
    businessUnit, jobId, skillFamily, jobFamily, recruiter, clientAccount, candidateStatus,
    atsSystem, jobBoard, bulkCsv, salesforceJson,
  } = form.values;
  const [campaignResults, setCampaignResults] = useState([]);
  const [emailResults, setEmailResults] = useState([]);
  const [segmentResults, setSegmentResults] = useState([]);
  const [segmentMemberships, setSegmentMemberships] = useState([]);
  const [reviewState, setReviewState] = useState({loading: false, result: null, error: ""});
  const [actionState, setActionState] = useState({loading: "", result: null, error: ""});

  useEffect(() => {
    let cancelled = false;
    async function loadDashboard() {
      try {
        const {payload} = await hubspotApi("/api/enterprise/hubspot/home-bootstrap", {timeout: 15000});
        if (!cancelled) {
          setState({
            loading: false,
            dashboard: payload.dashboard || {},
            templates: payload.templates || [],
            readiness: payload.readiness || null,
            error: "",
          });
        }
      } catch (error) {
        if (!cancelled) setState({loading: false, dashboard: null, readiness: null, templates: [], error: "Open TextTraits as an admin to load the governance dashboard."});
      }
    }
    loadDashboard();
    return () => {
      cancelled = true;
    };
  }, []);

  const dashboard = state.dashboard || {};
  const gateCounts = dashboard.gate_counts || {};

  function enterpriseContextPayload() {
    return {
      audience_type: audienceType,
      region,
      business_unit: businessUnit,
      job_id: jobId,
      skill_family: skillFamily,
      job_family: jobFamily,
      recruiter,
      client_account: clientAccount,
      candidate_status: candidateStatus,
      ats_system: atsSystem,
      job_board: jobBoard,
    };
  }

  async function runHubSpotAction(action, endpoint, body, timeout = 30000) {
    setActionState({loading: action, result: null, error: ""});
    try {
      const {payload, status} = await hubspotApi(endpoint, {
        method: "POST",
        body,
        timeout,
        allowStatuses: [207],
        errorMessage: `${action} failed.`,
      });
      setActionState({loading: "", result: {action, status, payload}, error: ""});
      const nextCampaignId = payload?.hubspot?.id || payload?.hubspot?.guid || payload?.campaign_id || payload?.summary?.campaign_id || "";
      const nextEmailId = payload?.hubspot?.id || payload?.email?.id || payload?.analysis?.context?.template_id || "";
      if (action === "Create campaign" && nextCampaignId) form.setField("campaignId", String(nextCampaignId));
      if ((action === "Create marketing email" || action === "Fetch marketing email") && nextEmailId) form.setField("emailId", String(nextEmailId));
    } catch (error) {
      setActionState({loading: "", result: null, error: error.message || `${action} failed.`});
    }
  }

  function createCampaign() {
    runHubSpotAction("Create campaign", "/v1/integrations/hubspot/campaigns/create", {
      portal_id: portalId,
      name: campaignName,
      ...enterpriseContextPayload(),
      properties: {hs_name: campaignName},
    });
  }

  async function searchCampaigns() {
    setActionState({loading: "Search campaigns", result: null, error: ""});
    try {
      const {payload, status} = await hubspotApi("/v1/integrations/hubspot/campaigns/list", {
        method: "POST",
        body: {portal_id: portalId, query: campaignName, limit: 10},
        timeout: 30000,
        errorMessage: "Campaign search failed.",
      });
      setCampaignResults(payload.campaigns || []);
      setActionState({loading: "", result: {action: "Search campaigns", status, payload}, error: ""});
    } catch (error) {
      setActionState({loading: "", result: null, error: error.message || "Campaign search failed."});
    }
  }

  async function searchMarketingEmails() {
    setActionState({loading: "Search marketing emails", result: null, error: ""});
    try {
      const {payload, status} = await hubspotApi("/v1/integrations/hubspot/marketing-emails/list", {
        method: "POST",
        body: {portal_id: portalId, query: emailName || emailSubject, limit: 10},
        timeout: 30000,
        errorMessage: "Marketing email search failed.",
      });
      setEmailResults(payload.emails || []);
      setActionState({loading: "", result: {action: "Search marketing emails", status, payload}, error: ""});
    } catch (error) {
      setActionState({loading: "", result: null, error: error.message || "Marketing email search failed."});
    }
  }

  async function searchSegments() {
    setActionState({loading: "Search segments", result: null, error: ""});
    try {
      const body = {
        portal_id: portalId,
        query: segmentQuery,
        objectTypeId: segmentObjectTypeId,
        limit: 10,
        includeFilters: false,
      };
      if (segmentProcessingType) body.processingTypes = [segmentProcessingType];
      const {payload, status} = await hubspotApi("/v1/integrations/hubspot/lists/search", {
        method: "POST",
        body,
        timeout: 30000,
        errorMessage: "Segment search failed.",
      });
      const lists = payload.lists || [];
      setSegmentResults(lists);
      if (lists[0]?.list_id) form.setField("segmentId", String(lists[0].list_id));
      setActionState({loading: "", result: {action: "Search segments", status, payload}, error: ""});
    } catch (error) {
      setActionState({loading: "", result: null, error: error.message || "Segment search failed."});
    }
  }

  async function previewSegmentMembers() {
    setActionState({loading: "Preview segment members", result: null, error: ""});
    try {
      const {payload, status} = await hubspotApi("/v1/integrations/hubspot/lists/memberships", {
        method: "POST",
        body: {portal_id: portalId, list_id: segmentId, limit: 25},
        timeout: 30000,
        errorMessage: "Segment membership preview failed.",
      });
      setSegmentMemberships(payload.memberships || []);
      setActionState({loading: "", result: {action: "Preview segment members", status, payload}, error: ""});
    } catch (error) {
      setActionState({loading: "", result: null, error: error.message || "Segment membership preview failed."});
    }
  }

  async function updateSegmentMembers() {
    setActionState({loading: "Update segment members", result: null, error: ""});
    try {
      const {payload, status} = await hubspotApi("/v1/integrations/hubspot/lists/memberships/update", {
        method: "POST",
        body: {
          portal_id: portalId,
          list_id: segmentId,
          recordIdsToAdd: segmentAddIds.split(/[\s,]+/).filter(Boolean),
          recordIdsToRemove: segmentRemoveIds.split(/[\s,]+/).filter(Boolean),
        },
        timeout: 30000,
        errorMessage: "Segment membership update failed.",
      });
      try {
        const {payload: previewPayload} = await hubspotApi("/v1/integrations/hubspot/lists/memberships", {
          method: "POST",
          body: {portal_id: portalId, list_id: segmentId, limit: 25},
          timeout: 30000,
        });
        setSegmentMemberships(previewPayload.memberships || []);
      } catch (_error) {
        // Keep the update result visible even if the follow-up preview cannot refresh.
      }
      setActionState({loading: "", result: {action: "Update segment members", status, payload}, error: ""});
    } catch (error) {
      setActionState({loading: "", result: null, error: error.message || "Segment membership update failed."});
    }
  }

  function createMarketingEmail() {
    runHubSpotAction("Create marketing email", "/v1/integrations/hubspot/marketing-emails/create-draft", {
      portal_id: portalId,
      name: emailName,
      subject: emailSubject,
      templatePath,
      campaign_id: campaignId,
      ...enterpriseContextPayload(),
      analyze_after_create: true,
    });
  }

  function updateMarketingEmail() {
    runHubSpotAction("Update marketing email", "/v1/integrations/hubspot/marketing-emails/update-draft", {
      portal_id: portalId,
      email_id: emailId,
      ...enterpriseContextPayload(),
      email: {
        name: emailName,
        subject: emailSubject,
        templatePath,
        html: emailBody,
      },
    });
  }

  function fetchMarketingEmail() {
    runHubSpotAction("Fetch marketing email", "/v1/integrations/hubspot/marketing-emails/fetch", {
      portal_id: portalId,
      email_id: emailId,
      campaign_id: campaignId,
      ...enterpriseContextPayload(),
      analyze: true,
    });
  }

  function prePublishGuardrail() {
    runHubSpotAction("Pre-publish guardrail", "/v1/integrations/hubspot/marketing-emails/pre-publish-guardrail", {
      portal_id: portalId,
      email_id: emailId,
      campaign_id: campaignId,
      ...enterpriseContextPayload(),
    });
  }

  function analyzeAndSyncDraft() {
    runHubSpotAction("Analyze and sync draft", "/v1/integrations/hubspot/analyze-and-sync", {
      portal_id: portalId,
      campaign_id: campaignId,
      email_id: emailId,
      template_id: emailId,
      ...enterpriseContextPayload(),
      inputFields: {
        email_subject: emailSubject,
        email_body: emailBody,
        ...enterpriseContextPayload(),
      },
      writeback_properties: false,
      record_review_state: true,
      create_review_task: true,
      create_analysis_record: true,
      create_timeline_event: true,
    });
  }

  function associateEmailToCampaign() {
    runHubSpotAction("Associate email to campaign", "/v1/integrations/hubspot/campaigns/associate-asset", {
      portal_id: portalId,
      campaign_id: campaignId,
      asset_type: "MARKETING_EMAIL",
      asset_id: emailId,
    });
  }

  function analyzeAssetCopy() {
    runHubSpotAction("Analyze asset copy", "/v1/integrations/hubspot/assets/analyze", {
      portal_id: portalId,
      campaign_id: campaignId,
      asset_type: assetType,
      asset_id: assetId,
      ...enterpriseContextPayload(),
      asset: {
        id: assetId,
        name: assetName,
        html: assetCopy,
      },
    });
  }

  function fetchAndAnalyzeAsset() {
    runHubSpotAction("Fetch and analyze asset", "/v1/integrations/hubspot/assets/fetch-and-analyze", {
      portal_id: portalId,
      campaign_id: campaignId,
      asset_type: assetType,
      asset_id: assetId,
      ...enterpriseContextPayload(),
    });
  }

  function bulkImportAssets() {
    runHubSpotAction("Bulk import assets", "/v1/integrations/hubspot/bulk/import-assets", {
      portal_id: portalId,
      campaign_id: campaignId,
      import_id: campaignId ? `hubspot-campaign-${campaignId}` : "hubspot-app-home-import",
      csv_text: bulkCsv,
      ...enterpriseContextPayload(),
    }, 45000);
  }

  function importSalesforceOutcomes() {
    let parsed = {};
    try {
      parsed = JSON.parse(salesforceJson || "{}");
    } catch (_error) {
      parsed = {raw: salesforceJson};
    }
    runHubSpotAction("Import Salesforce outcomes", "/v1/integrations/hubspot/salesforce/outcomes/import", {
      portal_id: portalId,
      tenant_id: portalId,
      workspace_id: portalId ? `hubspot_${portalId}` : "hubspot_salesforce_import",
      campaign_id: campaignId,
      ...enterpriseContextPayload(),
      ...parsed,
    });
  }

  function toggleAssetType(assetType) {
    form.setField("assetTypes", (current) => {
      if (current.includes(assetType)) {
        const next = current.filter((item) => item !== assetType);
        return next.length ? next : [assetType];
      }
      return [...current, assetType];
    });
  }

  async function reviewCampaign() {
    setReviewState({loading: true, result: null, error: ""});
    try {
      const {payload} = await hubspotApi("/v1/integrations/hubspot/campaigns/review", {
        method: "POST",
        body: {
          portal_id: portalId,
          campaign_id: campaignId,
          asset_types: assetTypes,
          ...enterpriseContextPayload(),
          limit: 25,
        },
        timeout: 30000,
        errorMessage: "Campaign review failed.",
      });
      setReviewState({loading: false, result: payload, error: ""});
    } catch (error) {
      setReviewState({loading: false, result: null, error: error.message || "Campaign review failed."});
    }
  }

  return (
    <Box>
      <Text format={{fontWeight: "bold"}}>TextTraits campaign review</Text>
      <Text>Governance health for HubSpot campaign and email workflows.</Text>
      <Divider />
      {state.loading ? <LoadingSpinner label="Loading TextTraits dashboard" /> : null}
      {state.error ? <Alert variant="warning" title="Dashboard unavailable">{state.error}</Alert> : null}
      <Flex direction="column" gap="sm">
        <Text>Total analyses: {dashboard.total_analyses || 0}</Text>
        <Text>Ready: {gateCounts.ready || 0}</Text>
        <Text>Needs review: {gateCounts.needs_review || 0}</Text>
        <Text>Blocked: {gateCounts.blocked || 0}</Text>
        {state.readiness ? <Text>Randstad-style usefulness: {state.readiness.overall_usefulness_score}/10 · HubSpot connection: {state.readiness.overall_connection_score}/10</Text> : null}
      </Flex>
      <Divider />
      <Text format={{fontWeight: "bold"}}>Enterprise staffing context</Text>
      <Text>Attach ATS, region, audience, job, recruiter, and client context to every score so dashboards and exports stay useful.</Text>
      <EnterpriseContextFields
        values={{audienceType, region, businessUnit, jobId, skillFamily, jobFamily, recruiter, clientAccount, candidateStatus, atsSystem, jobBoard}}
        onChange={form.handlers}
      />
      <Divider />
      <Text format={{fontWeight: "bold"}}>Staffing workflow templates</Text>
      <Flex direction="column" gap="xs">
        {state.templates.slice(0, 5).map((template) => (
          <Box key={template.id}>
            <Text format={{fontWeight: "bold"}}>{template.name} · {template.policy_pack}</Text>
            <Text>Surfaces: {(template.hubspot_surfaces || []).join(", ")}</Text>
            <Text>Required context: {(template.required_context || []).join(", ")}</Text>
          </Box>
        ))}
      </Flex>
      <Divider />
      <Text format={{fontWeight: "bold"}}>Campaign dashboard rollups</Text>
      <Flex direction="column" gap="xs">
        {(dashboard.blocked_by_region || []).slice(0, 4).map((row) => (
          <Text key={`region-${row.region}`}>Region {row.region}: {row.blocked || 0} blocked of {row.total || 0}</Text>
        ))}
        {(dashboard.send_ready_by_business_unit || []).slice(0, 4).map((row) => (
          <Text key={`bu-${row.business_unit}`}>Business unit {row.business_unit}: {row.send_ready || 0} send-ready of {row.total || 0}</Text>
        ))}
        {(dashboard.risky_claim_types || []).slice(0, 3).map((row) => (
          <Text key={`risk-${row.claim_type}`}>Risk type: {row.claim_type} ({row.count})</Text>
        ))}
        {dashboard.review_sla ? <Text>Review SLA: {dashboard.review_sla.open || 0} open · {dashboard.review_sla.overdue || 0} overdue · {dashboard.review_sla.resolved || 0} resolved</Text> : null}
      </Flex>
      <CampaignPanel
        assetOptions={CAMPAIGN_ASSET_OPTIONS}
        assetTypes={assetTypes}
        values={{portalId, campaignName, campaignId}}
        onChange={form.handlers}
        onAction={{
          toggleAssetType,
          searchCampaigns,
          createCampaign,
          reviewCampaign,
          selectCampaign: (campaign) => {
            form.setField("campaignId", String(campaign.id || ""));
            form.setField("campaignName", String(campaign.name || ""));
          },
        }}
        actionLoading={actionState.loading}
        reviewState={reviewState}
        campaignResults={campaignResults}
      />
      <Divider />
      <Text format={{fontWeight: "bold"}}>Single asset copy review</Text>
      <Text>Score one HubSpot asset when a campaign, workflow action, or custom integration already has mapped copy.</Text>
      <Flex direction="column" gap="sm">
        <Input label="Asset type" name="asset_type" value={assetType} onInput={form.handlers.assetType} placeholder="FORM, LANDING_PAGE, SITE_PAGE, BLOG_POST, SMS, SOCIAL_BROADCAST" />
        <Input label="Asset ID" name="asset_id" value={assetId} onInput={form.handlers.assetId} placeholder="HubSpot asset ID" />
        <Input label="Asset name" name="asset_name" value={assetName} onInput={form.handlers.assetName} placeholder="Renewal landing page" />
        <TextArea label="Mapped asset copy" name="asset_copy" value={assetCopy} onInput={form.handlers.assetCopy} placeholder="Paste form, page, SMS, social, or CTA copy for review." rows={4} />
        <Button onClick={analyzeAssetCopy} disabled={actionState.loading || !portalId || (!assetName && !assetCopy)}>
          {actionState.loading === "Analyze asset copy" ? "Analyzing..." : "Analyze mapped asset copy"}
        </Button>
        <Button onClick={fetchAndAnalyzeAsset} disabled={actionState.loading || !portalId || !assetType || !assetId}>
          {actionState.loading === "Fetch and analyze asset" ? "Fetching..." : "Fetch and review supported asset"}
        </Button>
      </Flex>
      <MarketingEmailPanel
        values={{portalId, campaignId, emailId, emailName, emailSubject, emailBody, templatePath}}
        onChange={form.handlers}
        onAction={{
          searchMarketingEmails,
          createMarketingEmail,
          updateMarketingEmail,
          fetchMarketingEmail,
          prePublishGuardrail,
          analyzeAndSyncDraft,
          associateEmailToCampaign,
          selectEmail: (email) => {
            form.setField("emailId", String(email.id || ""));
            form.setField("emailName", String(email.name || ""));
            form.setField("emailSubject", String(email.subject || email.name || ""));
            if (email.campaign_id) form.setField("campaignId", String(email.campaign_id));
          },
        }}
        actionLoading={actionState.loading}
        emailResults={emailResults}
      />
      <Divider />
      <Text format={{fontWeight: "bold"}}>Bulk asset import</Text>
      <Text>Paste a CSV or warehouse export of campaign assets to score ads, SMS, social, CTAs, sequences, and workflow-step copy before scheduling.</Text>
      <Flex direction="column" gap="sm">
        <TextArea label="CSV rows" name="bulk_csv" value={bulkCsv} onInput={form.handlers.bulkCsv} placeholder="asset_type,asset_id,asset_name,asset_copy,region,business_unit,audience_type" rows={5} />
        <Button onClick={bulkImportAssets} disabled={actionState.loading || !portalId || !bulkCsv}>
          {actionState.loading === "Bulk import assets" ? "Importing..." : "Score imported assets"}
        </Button>
      </Flex>
      <Divider />
      <Text format={{fontWeight: "bold"}}>Salesforce outcome mapping</Text>
      <Text>Import mapped Salesforce outcome rows after a HubSpot campaign touches pipeline, placement, or opportunity records.</Text>
      <Flex direction="column" gap="sm">
        <TextArea label="Salesforce outcome JSON" name="salesforce_json" value={salesforceJson} onInput={form.handlers.salesforceJson} placeholder='{"event_type":"placement_created","salesforce_opportunity_id":"006..."}' rows={4} />
        <Button onClick={importSalesforceOutcomes} disabled={actionState.loading || !portalId || !salesforceJson}>
          {actionState.loading === "Import Salesforce outcomes" ? "Importing..." : "Import Salesforce outcome"}
        </Button>
      </Flex>
      <SegmentPanel
        values={{portalId, segmentQuery, segmentObjectTypeId, segmentProcessingType, segmentId, segmentAddIds, segmentRemoveIds}}
        onChange={form.handlers}
        onAction={{searchSegments, previewSegmentMembers, updateSegmentMembers}}
        actionLoading={actionState.loading}
        segmentResults={segmentResults}
        segmentMemberships={segmentMemberships}
      />
      <HubSpotActionResult state={actionState} />
    </Box>
  );
}
