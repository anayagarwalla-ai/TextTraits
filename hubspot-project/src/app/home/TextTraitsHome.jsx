import React, {useEffect, useState} from "react";
import {Alert, Box, Button, Divider, Flex, Input, LoadingSpinner, Text, TextArea, hubspot} from "@hubspot/ui-extensions";

const API_BASE = "https://texttraits.onrender.com";

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

hubspot.extend(({context}) => <TextTraitsHome context={context} />);

function campaignAssetLabel(assetType, fallback) {
  return CAMPAIGN_ASSET_OPTIONS.find((asset) => asset.value === assetType)?.label || fallback || assetType;
}

function statusCounts(assets) {
  return assets.reduce((counts, asset) => {
    const status = asset.status || "unknown";
    return {...counts, [status]: (counts[status] || 0) + 1};
  }, {});
}

function portalIdFromContext(context) {
  return String(context?.portal?.id || context?.portalId || "");
}

function TextTraitsHome({context}) {
  const [state, setState] = useState({loading: true, dashboard: null, readiness: null, templates: [], objectSpecialization: {}, assetCopySupport: {}, error: ""});
  const [portalId, setPortalId] = useState(portalIdFromContext(context));
  const [campaignId, setCampaignId] = useState("");
  const [campaignName, setCampaignName] = useState("");
  const [emailId, setEmailId] = useState("");
  const [emailName, setEmailName] = useState("");
  const [emailSubject, setEmailSubject] = useState("");
  const [emailBody, setEmailBody] = useState("");
  const [templatePath, setTemplatePath] = useState("@hubspot/email/dnd/welcome.html");
  const [assetType, setAssetType] = useState("LANDING_PAGE");
  const [assetId, setAssetId] = useState("");
  const [assetName, setAssetName] = useState("");
  const [assetCopy, setAssetCopy] = useState("");
  const [assetTypes, setAssetTypes] = useState(DEFAULT_CAMPAIGN_ASSET_TYPES);
  const [campaignResults, setCampaignResults] = useState([]);
  const [emailResults, setEmailResults] = useState([]);
  const [segmentQuery, setSegmentQuery] = useState("TextTraits");
  const [segmentObjectTypeId, setSegmentObjectTypeId] = useState("0-1");
  const [segmentProcessingType, setSegmentProcessingType] = useState("");
  const [segmentId, setSegmentId] = useState("");
  const [segmentAddIds, setSegmentAddIds] = useState("");
  const [segmentRemoveIds, setSegmentRemoveIds] = useState("");
  const [segmentResults, setSegmentResults] = useState([]);
  const [segmentMemberships, setSegmentMemberships] = useState([]);
  const [audienceType, setAudienceType] = useState("candidate");
  const [region, setRegion] = useState("US");
  const [businessUnit, setBusinessUnit] = useState("Staffing");
  const [jobId, setJobId] = useState("");
  const [skillFamily, setSkillFamily] = useState("");
  const [jobFamily, setJobFamily] = useState("");
  const [recruiter, setRecruiter] = useState("");
  const [clientAccount, setClientAccount] = useState("");
  const [candidateStatus, setCandidateStatus] = useState("");
  const [atsSystem, setAtsSystem] = useState("");
  const [jobBoard, setJobBoard] = useState("");
  const [bulkCsv, setBulkCsv] = useState("asset_type,asset_id,asset_name,asset_copy,region,business_unit,audience_type\nMARKETING_SMS,sms-1,Job alert SMS,\"Hi {{first_name}}, reply by Friday if you want details on job JR-204 in logistics.\",US,Staffing,candidate");
  const [salesforceJson, setSalesforceJson] = useState('{"event_type":"placement_created","salesforce_campaign_id":"701-demo","salesforce_opportunity_id":"006-demo","audience_type":"client","region":"US","skill_family":"Logistics"}');
  const [reviewState, setReviewState] = useState({loading: false, result: null, error: ""});
  const [actionState, setActionState] = useState({loading: "", result: null, error: ""});

  useEffect(() => {
    let cancelled = false;
    async function loadDashboard() {
      try {
        const [dashboardResponse, templatesResponse, readinessResponse] = await Promise.all([
          hubspot.fetch(`${API_BASE}/api/enterprise/hubspot/dashboard`, {timeout: 15000}),
          hubspot.fetch(`${API_BASE}/api/enterprise/hubspot/staffing-workflow-templates`, {timeout: 15000}),
          hubspot.fetch(`${API_BASE}/api/enterprise/hubspot/randstad-readiness`, {timeout: 15000}),
        ]);
        const dashboardPayload = await dashboardResponse.json();
        const templatesPayload = await templatesResponse.json();
        const readinessPayload = await readinessResponse.json();
        if (!cancelled) {
          setState({
            loading: false,
            dashboard: dashboardPayload.dashboard || {},
            templates: templatesPayload.templates || [],
            objectSpecialization: templatesPayload.object_specialization || {},
            assetCopySupport: templatesPayload.asset_copy_support || {},
            readiness: readinessPayload.readiness || null,
            error: "",
          });
        }
      } catch (error) {
        if (!cancelled) setState({loading: false, dashboard: null, readiness: null, templates: [], objectSpecialization: {}, assetCopySupport: {}, error: "Open TextTraits as an admin to load the governance dashboard."});
      }
    }
    loadDashboard();
    return () => {
      cancelled = true;
    };
  }, []);

  const dashboard = state.dashboard || {};
  const gateCounts = dashboard.gate_counts || {};
  const assetMapEntries = Object.entries(reviewState.result?.asset_map || {});
  const copyCoverage = reviewState.result?.summary?.copy_coverage || {};

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
      const response = await hubspot.fetch(`${API_BASE}${endpoint}`, {
        method: "POST",
        body,
        timeout,
      });
      const payload = await response.json();
      if (!response.ok && response.status !== 207) throw new Error(payload.error || `${action} failed.`);
      setActionState({loading: "", result: {action, status: response.status, payload}, error: ""});
      const nextCampaignId = payload?.hubspot?.id || payload?.hubspot?.guid || payload?.campaign_id || payload?.summary?.campaign_id || "";
      const nextEmailId = payload?.hubspot?.id || payload?.email?.id || payload?.analysis?.context?.template_id || "";
      if (action === "Create campaign" && nextCampaignId) setCampaignId(String(nextCampaignId));
      if ((action === "Create marketing email" || action === "Fetch marketing email") && nextEmailId) setEmailId(String(nextEmailId));
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
      const response = await hubspot.fetch(`${API_BASE}/v1/integrations/hubspot/campaigns/list`, {
        method: "POST",
        body: {portal_id: portalId, query: campaignName, limit: 10},
        timeout: 30000,
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Campaign search failed.");
      setCampaignResults(payload.campaigns || []);
      setActionState({loading: "", result: {action: "Search campaigns", status: response.status, payload}, error: ""});
    } catch (error) {
      setActionState({loading: "", result: null, error: error.message || "Campaign search failed."});
    }
  }

  async function searchMarketingEmails() {
    setActionState({loading: "Search marketing emails", result: null, error: ""});
    try {
      const response = await hubspot.fetch(`${API_BASE}/v1/integrations/hubspot/marketing-emails/list`, {
        method: "POST",
        body: {portal_id: portalId, query: emailName || emailSubject, limit: 10},
        timeout: 30000,
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Marketing email search failed.");
      setEmailResults(payload.emails || []);
      setActionState({loading: "", result: {action: "Search marketing emails", status: response.status, payload}, error: ""});
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
      const response = await hubspot.fetch(`${API_BASE}/v1/integrations/hubspot/lists/search`, {
        method: "POST",
        body,
        timeout: 30000,
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Segment search failed.");
      const lists = payload.lists || [];
      setSegmentResults(lists);
      if (lists[0]?.list_id) setSegmentId(String(lists[0].list_id));
      setActionState({loading: "", result: {action: "Search segments", status: response.status, payload}, error: ""});
    } catch (error) {
      setActionState({loading: "", result: null, error: error.message || "Segment search failed."});
    }
  }

  async function previewSegmentMembers() {
    setActionState({loading: "Preview segment members", result: null, error: ""});
    try {
      const response = await hubspot.fetch(`${API_BASE}/v1/integrations/hubspot/lists/memberships`, {
        method: "POST",
        body: {portal_id: portalId, list_id: segmentId, limit: 25},
        timeout: 30000,
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Segment membership preview failed.");
      setSegmentMemberships(payload.memberships || []);
      setActionState({loading: "", result: {action: "Preview segment members", status: response.status, payload}, error: ""});
    } catch (error) {
      setActionState({loading: "", result: null, error: error.message || "Segment membership preview failed."});
    }
  }

  async function updateSegmentMembers() {
    setActionState({loading: "Update segment members", result: null, error: ""});
    try {
      const response = await hubspot.fetch(`${API_BASE}/v1/integrations/hubspot/lists/memberships/update`, {
        method: "POST",
        body: {
          portal_id: portalId,
          list_id: segmentId,
          recordIdsToAdd: segmentAddIds.split(/[\s,]+/).filter(Boolean),
          recordIdsToRemove: segmentRemoveIds.split(/[\s,]+/).filter(Boolean),
        },
        timeout: 30000,
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Segment membership update failed.");
      try {
        const previewResponse = await hubspot.fetch(`${API_BASE}/v1/integrations/hubspot/lists/memberships`, {
          method: "POST",
          body: {portal_id: portalId, list_id: segmentId, limit: 25},
          timeout: 30000,
        });
        const previewPayload = await previewResponse.json();
        if (previewResponse.ok) setSegmentMemberships(previewPayload.memberships || []);
      } catch (_error) {
        // Keep the update result visible even if the follow-up preview cannot refresh.
      }
      setActionState({loading: "", result: {action: "Update segment members", status: response.status, payload}, error: ""});
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
    setAssetTypes((current) => {
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
      const response = await hubspot.fetch(`${API_BASE}/v1/integrations/hubspot/campaigns/review`, {
        method: "POST",
        body: {
          portal_id: portalId,
          campaign_id: campaignId,
          asset_types: assetTypes,
          ...enterpriseContextPayload(),
          limit: 25,
        },
        timeout: 30000,
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Campaign review failed.");
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
      <Flex direction="column" gap="sm">
        <Input label="Audience type" name="audience_type" value={audienceType} onInput={setAudienceType} placeholder="candidate or client" />
        <Input label="Region" name="region" value={region} onInput={setRegion} placeholder="US, EU, APAC" />
        <Input label="Business unit" name="business_unit" value={businessUnit} onInput={setBusinessUnit} placeholder="Staffing, RiseSmart, Healthcare" />
        <Input label="Job ID" name="job_id" value={jobId} onInput={setJobId} placeholder="ATS or job-board requisition ID" />
        <Input label="Skill family" name="skill_family" value={skillFamily} onInput={setSkillFamily} placeholder="Logistics, finance, healthcare" />
        <Input label="Job family" name="job_family" value={jobFamily} onInput={setJobFamily} placeholder="Warehouse, nursing, accounting" />
        <Input label="Recruiter" name="recruiter" value={recruiter} onInput={setRecruiter} placeholder="Recruiter or owner name" />
        <Input label="Client account" name="client_account" value={clientAccount} onInput={setClientAccount} placeholder="Hiring client account" />
        <Input label="Candidate status" name="candidate_status" value={candidateStatus} onInput={setCandidateStatus} placeholder="New, nurtured, passive, placed" />
        <Input label="ATS system" name="ats_system" value={atsSystem} onInput={setAtsSystem} placeholder="Bullhorn, Workday, Greenhouse, custom" />
        <Input label="Job board" name="job_board" value={jobBoard} onInput={setJobBoard} placeholder="Indeed, LinkedIn, internal board" />
      </Flex>
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
      <Divider />
      <Text format={{fontWeight: "bold"}}>Review a HubSpot campaign</Text>
      <Text>Fetch campaign assets, score reviewable copy, and map unsupported assets clearly before scheduling.</Text>
      <Flex direction="column" gap="sm">
        <Input label="Portal ID" name="portal_id" value={portalId} onInput={setPortalId} placeholder="246356639" />
        <Input label="Campaign name" name="campaign_name" value={campaignName} onInput={setCampaignName} placeholder="Q3 lifecycle campaign" />
        <Input label="Campaign ID" name="campaign_id" value={campaignId} onInput={setCampaignId} placeholder="Campaign GUID" />
        <Text format={{fontWeight: "bold"}}>Asset types to review</Text>
        <Flex direction="column" gap="xs">
          {CAMPAIGN_ASSET_OPTIONS.map((asset) => (
            <Button key={asset.value} variant={assetTypes.includes(asset.value) ? "primary" : undefined} onClick={() => toggleAssetType(asset.value)}>
              {assetTypes.includes(asset.value) ? "Selected: " : "Add: "}{asset.label}
            </Button>
          ))}
        </Flex>
        <Button onClick={searchCampaigns} disabled={actionState.loading || !portalId}>
          {actionState.loading === "Search campaigns" ? "Searching..." : "Find HubSpot campaigns"}
        </Button>
        <Button onClick={createCampaign} disabled={actionState.loading || !portalId || !campaignName}>
          {actionState.loading === "Create campaign" ? "Creating..." : "Create HubSpot campaign"}
        </Button>
        <Button variant="primary" onClick={reviewCampaign} disabled={reviewState.loading || !portalId || !campaignId}>
          {reviewState.loading ? "Reviewing..." : "Review campaign assets"}
        </Button>
      </Flex>
      {campaignResults.length ? (
        <Box>
          <Text format={{fontWeight: "bold"}}>Campaign matches</Text>
          <Flex direction="column" gap="xs">
            {campaignResults.slice(0, 6).map((campaign) => (
              <Button key={campaign.id || campaign.name} onClick={() => { setCampaignId(String(campaign.id || "")); setCampaignName(String(campaign.name || "")); }}>
                {campaign.name || campaign.id}
              </Button>
            ))}
          </Flex>
        </Box>
      ) : null}
      {reviewState.error ? <Alert variant="error" title="Campaign review unavailable">{reviewState.error}</Alert> : null}
      {reviewState.result ? (
        <Box>
          <Text format={{fontWeight: "bold"}}>Campaign health: {reviewState.result.summary?.health || "Not reviewed"}</Text>
          <Text>Asset types: {(reviewState.result.summary?.asset_types || []).join(", ") || "Marketing emails"}</Text>
          <Text>Analyzed: {reviewState.result.summary?.analyzed || 0}</Text>
          <Text>Skipped: {reviewState.result.summary?.skipped || 0}</Text>
          <Text>Ready: {reviewState.result.summary?.gate_counts?.ready || 0}</Text>
          <Text>Needs review: {reviewState.result.summary?.gate_counts?.needs_review || 0}</Text>
          <Text>Blocked: {reviewState.result.summary?.gate_counts?.blocked || 0}</Text>
          <Text>Coverage: {copyCoverage.coverage_score ?? 0}% · {copyCoverage.coverage_label || "No coverage label"}</Text>
          <Text>Reviewed asset types: {(copyCoverage.reviewed_asset_types || []).join(", ") || "None yet"}</Text>
          <Text>Metadata-only asset types: {(copyCoverage.metadata_only_asset_types || []).join(", ") || "None"}</Text>
          {(copyCoverage.coverage_gap_assets || []).slice(0, 4).map((gap) => (
            <Text key={`${gap.asset_type}-gap`}>{gap.label || gap.asset_type}: {gap.metadata_only_assets || 0} asset(s) need mapped copy.</Text>
          ))}
          <Text>{copyCoverage.note || "Marketing emails are fetched directly; other assets are scored when HubSpot returns reviewable copy."}</Text>
        </Box>
      ) : null}
      {assetMapEntries.length ? (
        <Box>
          <Text format={{fontWeight: "bold"}}>Campaign asset map</Text>
          <Flex direction="column" gap="xs">
            {assetMapEntries.map(([assetType, group]) => {
              const assets = Array.isArray(group.assets) ? group.assets : [];
              const counts = statusCounts(assets);
              return (
                <Box key={assetType}>
                  <Text format={{fontWeight: "bold"}}>{campaignAssetLabel(assetType, group.label)} ({assets.length})</Text>
                  <Text>
                    Analyzed: {counts.analyzed || 0} · Metadata only: {counts.metadata_only || 0} · Fetch errors: {counts.fetch_error || 0}
                  </Text>
                  {assets.slice(0, 4).map((asset) => (
                    <Text key={`${assetType}-${asset.id || asset.name}`}>
                      {asset.name || asset.id || "Unnamed asset"}: {asset.status || "unknown"}{asset.score !== undefined ? `, score ${asset.score}` : ""}
                    </Text>
                  ))}
                </Box>
              );
            })}
          </Flex>
        </Box>
      ) : null}
      <Divider />
      <Text format={{fontWeight: "bold"}}>Single asset copy review</Text>
      <Text>Score one HubSpot asset when a campaign, workflow action, or custom integration already has mapped copy.</Text>
      <Flex direction="column" gap="sm">
        <Input label="Asset type" name="asset_type" value={assetType} onInput={setAssetType} placeholder="FORM, LANDING_PAGE, SITE_PAGE, BLOG_POST, SMS, SOCIAL_BROADCAST" />
        <Input label="Asset ID" name="asset_id" value={assetId} onInput={setAssetId} placeholder="HubSpot asset ID" />
        <Input label="Asset name" name="asset_name" value={assetName} onInput={setAssetName} placeholder="Renewal landing page" />
        <TextArea label="Mapped asset copy" name="asset_copy" value={assetCopy} onInput={setAssetCopy} placeholder="Paste form, page, SMS, social, or CTA copy for review." rows={4} />
        <Button onClick={analyzeAssetCopy} disabled={actionState.loading || !portalId || (!assetName && !assetCopy)}>
          {actionState.loading === "Analyze asset copy" ? "Analyzing..." : "Analyze mapped asset copy"}
        </Button>
        <Button onClick={fetchAndAnalyzeAsset} disabled={actionState.loading || !portalId || !assetType || !assetId}>
          {actionState.loading === "Fetch and analyze asset" ? "Fetching..." : "Fetch and review supported asset"}
        </Button>
      </Flex>
      <Divider />
      <Text format={{fontWeight: "bold"}}>Marketing email draft</Text>
      <Text>Create, fetch, score, and attach a HubSpot marketing email draft without leaving the TextTraits app home page.</Text>
      <Flex direction="column" gap="sm">
        <Input label="Email ID" name="email_id" value={emailId} onInput={setEmailId} placeholder="HubSpot marketing email ID" />
        <Input label="Email name" name="email_name" value={emailName} onInput={setEmailName} placeholder="Renewal workflow follow-up" />
        <Input label="Subject" name="email_subject" value={emailSubject} onInput={setEmailSubject} placeholder="Renewal workflow follow-up" />
        <Input label="Template path" name="template_path" value={templatePath} onInput={setTemplatePath} placeholder="@hubspot/email/dnd/welcome.html" />
        <TextArea label="Draft body for review" name="email_body" value={emailBody} onInput={setEmailBody} placeholder="Paste the existing draft body before routing." rows={5} />
        <Button onClick={searchMarketingEmails} disabled={actionState.loading || !portalId}>
          {actionState.loading === "Search marketing emails" ? "Searching..." : "Find marketing email drafts"}
        </Button>
        <Button onClick={createMarketingEmail} disabled={actionState.loading || !portalId || !emailName || !emailSubject || !templatePath}>
          {actionState.loading === "Create marketing email" ? "Creating..." : "Create marketing email draft"}
        </Button>
        <Button onClick={updateMarketingEmail} disabled={actionState.loading || !portalId || !emailId || (!emailName && !emailSubject && !emailBody)}>
          {actionState.loading === "Update marketing email" ? "Updating..." : "Update marketing email draft"}
        </Button>
        <Button onClick={fetchMarketingEmail} disabled={actionState.loading || !portalId || !emailId}>
          {actionState.loading === "Fetch marketing email" ? "Fetching..." : "Fetch and review email draft"}
        </Button>
        <Button variant="primary" onClick={prePublishGuardrail} disabled={actionState.loading || !portalId || !emailId}>
          {actionState.loading === "Pre-publish guardrail" ? "Checking..." : "Run pre-publish guardrail"}
        </Button>
        <Button onClick={analyzeAndSyncDraft} disabled={actionState.loading || !portalId || (!emailSubject && !emailBody)}>
          {actionState.loading === "Analyze and sync draft" ? "Syncing..." : "Analyze and sync draft"}
        </Button>
        <Button onClick={associateEmailToCampaign} disabled={actionState.loading || !portalId || !campaignId || !emailId}>
          {actionState.loading === "Associate email to campaign" ? "Associating..." : "Attach email to campaign"}
        </Button>
      </Flex>
      {emailResults.length ? (
        <Box>
          <Text format={{fontWeight: "bold"}}>Marketing email matches</Text>
          <Flex direction="column" gap="xs">
            {emailResults.slice(0, 6).map((email) => (
              <Button key={email.id || email.name} onClick={() => { setEmailId(String(email.id || "")); setEmailName(String(email.name || "")); setEmailSubject(String(email.subject || email.name || "")); if (email.campaign_id) setCampaignId(String(email.campaign_id)); }}>
                {email.name || email.subject || email.id}
              </Button>
            ))}
          </Flex>
        </Box>
      ) : null}
      <Divider />
      <Text format={{fontWeight: "bold"}}>Bulk asset import</Text>
      <Text>Paste a CSV or warehouse export of campaign assets to score ads, SMS, social, CTAs, sequences, and workflow-step copy before scheduling.</Text>
      <Flex direction="column" gap="sm">
        <TextArea label="CSV rows" name="bulk_csv" value={bulkCsv} onInput={setBulkCsv} placeholder="asset_type,asset_id,asset_name,asset_copy,region,business_unit,audience_type" rows={5} />
        <Button onClick={bulkImportAssets} disabled={actionState.loading || !portalId || !bulkCsv}>
          {actionState.loading === "Bulk import assets" ? "Importing..." : "Score imported assets"}
        </Button>
      </Flex>
      <Divider />
      <Text format={{fontWeight: "bold"}}>Salesforce outcome mapping</Text>
      <Text>Import mapped Salesforce outcome rows after a HubSpot campaign touches pipeline, placement, or opportunity records.</Text>
      <Flex direction="column" gap="sm">
        <TextArea label="Salesforce outcome JSON" name="salesforce_json" value={salesforceJson} onInput={setSalesforceJson} placeholder='{"event_type":"placement_created","salesforce_opportunity_id":"006..."}' rows={4} />
        <Button onClick={importSalesforceOutcomes} disabled={actionState.loading || !portalId || !salesforceJson}>
          {actionState.loading === "Import Salesforce outcomes" ? "Importing..." : "Import Salesforce outcome"}
        </Button>
      </Flex>
      <Divider />
      <Text format={{fontWeight: "bold"}}>HubSpot segments</Text>
      <Text>Find existing HubSpot segments before creating review lists for ready, needs-review, or blocked records.</Text>
      <Flex direction="column" gap="sm">
        <Input label="Segment search" name="segment_query" value={segmentQuery} onInput={setSegmentQuery} placeholder="TextTraits, needs review, blocked" />
        <Input label="Object type ID" name="segment_object_type_id" value={segmentObjectTypeId} onInput={setSegmentObjectTypeId} placeholder="0-1 for contacts" />
        <Input label="Processing type" name="segment_processing_type" value={segmentProcessingType} onInput={setSegmentProcessingType} placeholder="Optional: MANUAL, DYNAMIC, SNAPSHOT" />
        <Input label="Segment ID" name="segment_id" value={segmentId} onInput={setSegmentId} placeholder="HubSpot list or segment ID" />
        <Button onClick={searchSegments} disabled={actionState.loading || !portalId}>
          {actionState.loading === "Search segments" ? "Searching..." : "Find segments"}
        </Button>
        <Button onClick={previewSegmentMembers} disabled={actionState.loading || !portalId || !segmentId}>
          {actionState.loading === "Preview segment members" ? "Loading..." : "Preview segment members"}
        </Button>
        <Input label="Record IDs to add" name="segment_add_ids" value={segmentAddIds} onInput={setSegmentAddIds} placeholder="Comma-separated HubSpot record IDs" />
        <Input label="Record IDs to remove" name="segment_remove_ids" value={segmentRemoveIds} onInput={setSegmentRemoveIds} placeholder="Optional record IDs to remove" />
        <Button onClick={updateSegmentMembers} disabled={actionState.loading || !portalId || !segmentId || (!segmentAddIds && !segmentRemoveIds)}>
          {actionState.loading === "Update segment members" ? "Updating..." : "Update segment members"}
        </Button>
      </Flex>
      {segmentResults.length ? (
        <Box>
          <Text format={{fontWeight: "bold"}}>Segment matches</Text>
          <Flex direction="column" gap="xs">
            {segmentResults.slice(0, 6).map((segment) => (
              <Button key={segment.list_id || segment.name} onClick={() => setSegmentId(String(segment.list_id || ""))}>
                {segment.name || segment.list_id} · {segment.processing_type || "Unknown type"} · {segment.size ?? "Unknown size"}
              </Button>
            ))}
          </Flex>
        </Box>
      ) : null}
      {segmentMemberships.length ? (
        <Box>
          <Text format={{fontWeight: "bold"}}>Segment member preview</Text>
          <Flex direction="column" gap="xs">
            {segmentMemberships.slice(0, 6).map((member, index) => (
              <Text key={member.recordId || member.record_id || index}>
                Record {member.recordId || member.record_id || member.id || "unknown"}{member.membershipTimestamp ? ` · ${member.membershipTimestamp}` : ""}
              </Text>
            ))}
          </Flex>
        </Box>
      ) : null}
      {actionState.error ? <Alert variant="error" title="HubSpot action unavailable">{actionState.error}</Alert> : null}
      {actionState.result ? (
        <Box>
          <Text format={{fontWeight: "bold"}}>{actionState.result.action}: {actionState.result.status}</Text>
          <Text>{actionState.result.payload?.sync?.status ? `Sync status: ${actionState.result.payload.sync.status}` : "HubSpot request completed."}</Text>
          {actionState.result.payload?.campaigns ? <Text>Campaigns found: {actionState.result.payload.campaigns.length}</Text> : null}
          {actionState.result.payload?.emails ? <Text>Emails found: {actionState.result.payload.emails.length}</Text> : null}
          {actionState.result.payload?.lists ? <Text>Segments found: {actionState.result.payload.lists.length}</Text> : null}
          {actionState.result.payload?.memberships ? <Text>Segment members: {actionState.result.payload.memberships.length}</Text> : null}
          {actionState.result.payload?.guardrail ? <Text>Guardrail: {actionState.result.payload.guardrail.gate} · score {actionState.result.payload.guardrail.score} · publish allowed: {String(actionState.result.payload.guardrail.publish_allowed)}</Text> : null}
          {actionState.result.payload?.summary?.coverage ? <Text>Bulk coverage: {actionState.result.payload.summary.coverage.coverage_score}% · {actionState.result.payload.summary.coverage.coverage_label}</Text> : null}
          {actionState.result.payload?.events ? <Text>Outcome events imported: {actionState.result.payload.events.length}</Text> : null}
          {actionState.result.payload?.details?.operation ? <Text>Segment update: {actionState.result.payload.details.operation} ({actionState.result.payload.details.added || 0} added, {actionState.result.payload.details.removed || 0} removed)</Text> : null}
        </Box>
      ) : null}
    </Box>
  );
}
