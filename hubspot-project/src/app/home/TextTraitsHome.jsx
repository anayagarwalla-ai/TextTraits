import React, {useEffect, useState} from "react";
import {Accordion, Alert, Box, Button, Divider, Flex, Input, LoadingSpinner, StatusTag, Text, TextArea, hubspot} from "@hubspot/ui-extensions";
import {hubspotApi} from "../lib/api";
import {portalIdFromContext} from "../lib/context";
import {useFormState} from "../lib/form-state";
import {CampaignPanel, EnterpriseContextFields, HubSpotActionResult, MarketingEmailPanel, SegmentPanel} from "../components/HomePanels";

const CAMPAIGN_ASSET_OPTIONS = [
  {value: "MARKETING_EMAIL", label: "Marketing email"},
  {value: "FORM", label: "Form"},
  {value: "LANDING_PAGE", label: "Landing page"},
  {value: "MARKETING_SMS", label: "SMS"},
  {value: "SOCIAL_BROADCAST", label: "Social post"},
  {value: "SEQUENCE", label: "Sequence"},
  {value: "SITE_PAGE", label: "Website page"},
  {value: "BLOG_POST", label: "Blog post"},
];

const DEFAULT_FORM_VALUES = {
  campaignId: "",
  campaignName: "",
  emailId: "",
  emailName: "",
  emailSubject: "",
  assetType: "LANDING_PAGE",
  assetId: "",
  assetName: "",
  assetCopy: "",
  assetTypes: ["MARKETING_EMAIL", "FORM", "LANDING_PAGE"],
  segmentQuery: "",
  segmentId: "",
  audienceType: "",
  region: "",
  businessUnit: "",
  jobId: "",
  skillFamily: "",
  recruiter: "",
  clientAccount: "",
  bulkCsv: "",
};

hubspot.extend(({context}) => <TextTraitsHome context={context} />);

function decisionVariant(gate) {
  if (gate === "ready") return "success";
  if (gate === "blocked") return "danger";
  if (gate === "needs_review") return "warning";
  return "default";
}

function decisionLabel(gate) {
  if (gate === "ready") return "Ready";
  if (gate === "blocked") return "Blocked";
  if (gate === "needs_review") return "Review required";
  return "Not checked";
}

function TextTraitsHome({context}) {
  const portalId = portalIdFromContext(context);
  const [state, setState] = useState({loading: true, dashboard: null, readiness: null, error: ""});
  const form = useFormState(DEFAULT_FORM_VALUES);
  const {
    campaignId, campaignName, emailId, emailName, emailSubject, assetType, assetId, assetName,
    assetCopy, assetTypes, segmentQuery, segmentId, audienceType, region, businessUnit, jobId,
    skillFamily, recruiter, clientAccount, bulkCsv,
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
      if (!portalId) {
        setState({loading: false, dashboard: null, readiness: null, error: "HubSpot portal context is unavailable for this app home."});
        return;
      }
      try {
        const {payload} = await hubspotApi("/v1/integrations/hubspot/app-home/bootstrap", {
          method: "POST",
          body: {portal_id: portalId},
          timeout: 15000,
        });
        if (!cancelled) {
          setState({
            loading: false,
            dashboard: payload.dashboard || {},
            readiness: payload.readiness || null,
            error: "",
          });
        }
      } catch (error) {
        if (!cancelled) {
          setState({
            loading: false,
            dashboard: null,
            readiness: null,
            error: error.message || "The TextTraits review dashboard could not load.",
          });
        }
      }
    }
    loadDashboard();
    return () => {
      cancelled = true;
    };
  }, [portalId]);

  const dashboard = state.dashboard || {};
  const gateCounts = dashboard.gate_counts || {};
  const reviewSla = dashboard.review_sla || {};
  const operatingMetrics = dashboard.operating_metrics || {};
  const blockedDrafts = dashboard.recent_blocked_drafts || [];

  function enterpriseContextPayload() {
    return {
      audience_type: audienceType,
      region,
      business_unit: businessUnit,
      job_id: jobId,
      skill_family: skillFamily,
      recruiter,
      client_account: clientAccount,
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
      return payload;
    } catch (error) {
      setActionState({loading: "", result: null, error: error.message || `${action} failed.`});
      return null;
    }
  }

  async function searchCampaigns() {
    const payload = await runHubSpotAction("Search campaigns", "/v1/integrations/hubspot/campaigns/list", {
      portal_id: portalId,
      query: campaignName,
      limit: 10,
    });
    setCampaignResults(payload?.campaigns || []);
  }

  async function searchMarketingEmails() {
    const payload = await runHubSpotAction("Search marketing emails", "/v1/integrations/hubspot/marketing-emails/list", {
      portal_id: portalId,
      query: emailName,
      limit: 10,
    });
    setEmailResults(payload?.emails || []);
  }

  async function searchSegments() {
    const payload = await runHubSpotAction("Search segments", "/v1/integrations/hubspot/lists/search", {
      portal_id: portalId,
      query: segmentQuery,
      objectTypeId: "0-1",
      limit: 10,
      includeFilters: false,
    });
    setSegmentResults(payload?.lists || []);
  }

  async function previewSegmentMembers() {
    const payload = await runHubSpotAction("Preview segment members", "/v1/integrations/hubspot/lists/memberships", {
      portal_id: portalId,
      list_id: segmentId,
      limit: 25,
    });
    setSegmentMemberships(payload?.memberships || []);
  }

  function prePublishGuardrail() {
    runHubSpotAction("Pre-send check", "/v1/integrations/hubspot/marketing-emails/pre-publish-guardrail", {
      portal_id: portalId,
      email_id: emailId,
      campaign_id: campaignId,
      ...enterpriseContextPayload(),
    });
  }

  function analyzeAssetCopy() {
    runHubSpotAction("Check mapped asset copy", "/v1/integrations/hubspot/assets/analyze", {
      portal_id: portalId,
      campaign_id: campaignId,
      asset_type: assetType,
      asset_id: assetId,
      ...enterpriseContextPayload(),
      asset: {id: assetId, name: assetName, html: assetCopy},
    });
  }

  function fetchAndAnalyzeAsset() {
    runHubSpotAction("Fetch and check asset", "/v1/integrations/hubspot/assets/fetch-and-analyze", {
      portal_id: portalId,
      campaign_id: campaignId,
      asset_type: assetType,
      asset_id: assetId,
      ...enterpriseContextPayload(),
    });
  }

  function bulkImportAssets() {
    runHubSpotAction("Import copy for checking", "/v1/integrations/hubspot/bulk/import-assets", {
      portal_id: portalId,
      campaign_id: campaignId,
      import_id: campaignId ? `hubspot-campaign-${campaignId}` : "hubspot-app-home-import",
      csv_text: bulkCsv,
      ...enterpriseContextPayload(),
    }, 45000);
  }

  function toggleAssetType(value) {
    form.setField("assetTypes", (current) => {
      if (current.includes(value)) {
        const next = current.filter((item) => item !== value);
        return next.length ? next : [value];
      }
      return [...current, value];
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
        errorMessage: "Campaign check failed.",
      });
      setReviewState({loading: false, result: payload, error: ""});
    } catch (error) {
      setReviewState({loading: false, result: null, error: error.message || "Campaign check failed."});
    }
  }

  return (
    <Box>
      <Text format={{fontWeight: "bold"}}>Today’s review work</Text>
      <Text>Check existing HubSpot copy, route exceptions, and keep an auditable decision trail. TextTraits never rewrites source copy.</Text>
      <Divider />

      {state.loading ? <LoadingSpinner label="Loading TextTraits dashboard" /> : null}
      {state.error ? <Alert variant="warning" title="Dashboard unavailable">{state.error}</Alert> : null}

      <Flex direction="column" gap="sm">
        <Box>
          <Text format={{fontWeight: "bold"}}>{reviewSla.open || 0} reviews open</Text>
          <Text>{reviewSla.overdue || 0} overdue · {gateCounts.blocked || 0} blocked checks · {gateCounts.needs_review || 0} needing review</Text>
        </Box>
        {blockedDrafts.slice(0, 4).map((item) => (
          <Box key={item.request_id}>
            <Flex align="center" justify="between" gap="sm" wrap>
              <Text format={{fontWeight: "bold"}}>{item.context?.asset_name || item.template_id || item.campaign_id || "Blocked copy"}</Text>
              <StatusTag variant={decisionVariant(item.gate)}>{decisionLabel(item.gate)}</StatusTag>
            </Flex>
            <Text>{item.route || "Review owner not assigned"} · score {item.score ?? "not available"}</Text>
          </Box>
        ))}
        {!blockedDrafts.length && !state.loading ? (
          <Alert variant="success" title="No blocked copy in the current review window">
            Start by choosing an existing campaign below.
          </Alert>
        ) : null}
      </Flex>

      <Divider />
      <Accordion title="Check a campaign" size="md" defaultOpen>
        <CampaignPanel
          assetOptions={CAMPAIGN_ASSET_OPTIONS}
          assetTypes={assetTypes}
          values={{campaignName, campaignId}}
          onChange={form.handlers}
          onAction={{
            toggleAssetType,
            searchCampaigns,
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
      </Accordion>

      <Accordion title="Check one marketing email" size="md">
        <MarketingEmailPanel
          values={{emailId, emailName, emailSubject}}
          onChange={form.handlers}
          onAction={{
            searchMarketingEmails,
            prePublishGuardrail,
            selectEmail: (email) => {
              form.setField("emailId", String(email.id || ""));
              form.setField("emailName", String(email.name || email.subject || ""));
              form.setField("emailSubject", String(email.subject || ""));
              if (email.campaign_id) form.setField("campaignId", String(email.campaign_id));
            },
          }}
          actionLoading={actionState.loading}
          emailResults={emailResults}
        />
      </Accordion>

      <Accordion title="Other copy sources" size="md">
        <Text>Use this only when HubSpot cannot return the copy directly.</Text>
        <Flex direction="column" gap="sm">
          <Input label="Asset type" name="asset_type" value={assetType} onInput={form.handlers.assetType} placeholder="FORM, LANDING_PAGE, SITE_PAGE, BLOG_POST, SMS" />
          <Input label="Asset ID" name="asset_id" value={assetId} onInput={form.handlers.assetId} placeholder="HubSpot asset ID" />
          <Input label="Asset name" name="asset_name" value={assetName} onInput={form.handlers.assetName} placeholder="Existing asset name" />
          <TextArea label="Mapped copy" name="asset_copy" value={assetCopy} onInput={form.handlers.assetCopy} placeholder="Existing copy to check" rows={4} />
          <Button onClick={analyzeAssetCopy} disabled={actionState.loading || (!assetName && !assetCopy)}>
            {actionState.loading === "Check mapped asset copy" ? "Checking..." : "Check pasted asset copy"}
          </Button>
          <Button onClick={fetchAndAnalyzeAsset} disabled={actionState.loading || !assetType || !assetId}>
            {actionState.loading === "Fetch and check asset" ? "Fetching..." : "Fetch supported asset from HubSpot"}
          </Button>
        </Flex>
      </Accordion>

      <Accordion title="Review context" size="md">
        <Text>Add optional context only when it changes the policy or review route.</Text>
        <EnterpriseContextFields
          values={{audienceType, region, businessUnit, jobId, skillFamily, recruiter, clientAccount}}
          onChange={form.handlers}
        />
      </Accordion>

      <Accordion title="Read-only segment inspection" size="md">
        <SegmentPanel
          values={{segmentQuery, segmentId}}
          onChange={form.handlers}
          onAction={{searchSegments, previewSegmentMembers}}
          actionLoading={actionState.loading}
          segmentResults={segmentResults}
          segmentMemberships={segmentMemberships}
        />
      </Accordion>

      <Accordion title="Bulk copy import" size="md">
        <Text>Import mapped source copy for checking. This does not create or edit HubSpot campaign assets.</Text>
        <TextArea
          label="CSV rows"
          name="bulk_csv"
          value={bulkCsv}
          onInput={form.handlers.bulkCsv}
          placeholder="asset_type,asset_id,asset_name,asset_copy,region,business_unit,audience_type"
          rows={5}
        />
        <Button onClick={bulkImportAssets} disabled={actionState.loading || !bulkCsv}>
          {actionState.loading === "Import copy for checking" ? "Importing..." : "Import and check copy"}
        </Button>
      </Accordion>

      <Accordion title="Program health" size="md">
        <Text>Total checks: {dashboard.total_analyses || 0}</Text>
        <Text>Ready: {gateCounts.ready || 0} · Review required: {gateCounts.needs_review || 0} · Blocked: {gateCounts.blocked || 0}</Text>
        <Text>Resolved reviews: {reviewSla.resolved || 0}</Text>
        <Text>Review rate: {operatingMetrics.review_rate ?? 0}% · Approval rate: {operatingMetrics.approval_rate ?? 0}%</Text>
        <Text>Median review time: {operatingMetrics.median_review_hours ?? 0} hours · Repeat-check rate: {operatingMetrics.repeat_check_rate ?? 0}%</Text>
        {operatingMetrics.most_common_failed_check ? (
          <Text>Most common finding: {operatingMetrics.most_common_failed_check.check} ({operatingMetrics.most_common_failed_check.count})</Text>
        ) : null}
        {state.readiness ? (
          <Text>Configured HubSpot surfaces: {state.readiness.implemented_surface_count || 0}</Text>
        ) : null}
      </Accordion>

      <HubSpotActionResult state={actionState} />
    </Box>
  );
}
