import React from "react";
import {Alert, Box, Button, Divider, Flex, Input, Text, TextArea} from "@hubspot/ui-extensions";


function statusCounts(assets) {
  return assets.reduce((counts, asset) => {
    const status = asset.status || "unknown";
    return {...counts, [status]: (counts[status] || 0) + 1};
  }, {});
}


export function EnterpriseContextFields({values, onChange}) {
  return (
    <Flex direction="column" gap="sm">
      <Input label="Audience type" name="audience_type" value={values.audienceType} onInput={onChange.audienceType} placeholder="candidate, client, employee" />
      <Input label="Region" name="region" value={values.region} onInput={onChange.region} placeholder="US, EU, APAC" />
      <Input label="Business unit" name="business_unit" value={values.businessUnit} onInput={onChange.businessUnit} placeholder="Staffing, Enterprise, Healthcare" />
      <Input label="Job ID" name="job_id" value={values.jobId} onInput={onChange.jobId} placeholder="ATS or HubSpot job ID" />
      <Input label="Skill family" name="skill_family" value={values.skillFamily} onInput={onChange.skillFamily} placeholder="Logistics, Nursing, Finance" />
      <Input label="Job family" name="job_family" value={values.jobFamily} onInput={onChange.jobFamily} placeholder="Operations, Clinical, Technology" />
      <Input label="Recruiter" name="recruiter" value={values.recruiter} onInput={onChange.recruiter} placeholder="Recruiter or delivery owner" />
      <Input label="Client account" name="client_account" value={values.clientAccount} onInput={onChange.clientAccount} placeholder="Hiring client account" />
      <Input label="Candidate status" name="candidate_status" value={values.candidateStatus} onInput={onChange.candidateStatus} placeholder="New, nurtured, passive, placed" />
      <Input label="ATS system" name="ats_system" value={values.atsSystem} onInput={onChange.atsSystem} placeholder="Bullhorn, Workday, Greenhouse, custom" />
      <Input label="Job board" name="job_board" value={values.jobBoard} onInput={onChange.jobBoard} placeholder="Indeed, LinkedIn, internal board" />
    </Flex>
  );
}


export function CampaignPanel({assetOptions, assetTypes, values, onChange, onAction, actionLoading, reviewState, campaignResults}) {
  const assetMapEntries = Object.entries(reviewState.result?.asset_map || {});
  const copyCoverage = reviewState.result?.summary?.copy_coverage || {};
  return (
    <>
      <Divider />
      <Text format={{fontWeight: "bold"}}>Review a HubSpot campaign</Text>
      <Text>Fetch campaign assets, score reviewable copy, and map unsupported assets clearly before scheduling.</Text>
      <Flex direction="column" gap="sm">
        <Input label="Portal ID" name="portal_id" value={values.portalId} onInput={onChange.portalId} placeholder="246356639" />
        <Input label="Campaign name" name="campaign_name" value={values.campaignName} onInput={onChange.campaignName} placeholder="Q3 lifecycle campaign" />
        <Input label="Campaign ID" name="campaign_id" value={values.campaignId} onInput={onChange.campaignId} placeholder="Campaign GUID" />
        <Text format={{fontWeight: "bold"}}>Asset types to review</Text>
        <Flex direction="column" gap="xs">
          {assetOptions.map((asset) => (
            <Button key={asset.value} variant={assetTypes.includes(asset.value) ? "primary" : undefined} onClick={() => onAction.toggleAssetType(asset.value)}>
              {assetTypes.includes(asset.value) ? "Selected: " : "Add: "}{asset.label}
            </Button>
          ))}
        </Flex>
        <Button onClick={onAction.searchCampaigns} disabled={actionLoading || !values.portalId}>
          {actionLoading === "Search campaigns" ? "Searching..." : "Find HubSpot campaigns"}
        </Button>
        <Button onClick={onAction.createCampaign} disabled={actionLoading || !values.portalId || !values.campaignName}>
          {actionLoading === "Create campaign" ? "Creating..." : "Create HubSpot campaign"}
        </Button>
        <Button variant="primary" onClick={onAction.reviewCampaign} disabled={reviewState.loading || !values.portalId || !values.campaignId}>
          {reviewState.loading ? "Reviewing..." : "Review campaign assets"}
        </Button>
      </Flex>
      {campaignResults.length ? (
        <Box>
          <Text format={{fontWeight: "bold"}}>Campaign matches</Text>
          <Flex direction="column" gap="xs">
            {campaignResults.slice(0, 6).map((campaign) => (
              <Button key={campaign.id || campaign.name} onClick={() => onAction.selectCampaign(campaign)}>{campaign.name || campaign.id}</Button>
            ))}
          </Flex>
        </Box>
      ) : null}
      {reviewState.error ? <Alert variant="error" title="Campaign review unavailable">{reviewState.error}</Alert> : null}
      {reviewState.result ? (
        <Box>
          <Text format={{fontWeight: "bold"}}>Campaign health: {reviewState.result.summary?.health || "Not reviewed"}</Text>
          <Text>Asset types: {(reviewState.result.summary?.asset_types || []).join(", ") || "Marketing emails"}</Text>
          <Text>Analyzed: {reviewState.result.summary?.analyzed || 0} · Skipped: {reviewState.result.summary?.skipped || 0}</Text>
          <Text>Ready: {reviewState.result.summary?.gate_counts?.ready || 0} · Needs review: {reviewState.result.summary?.gate_counts?.needs_review || 0} · Blocked: {reviewState.result.summary?.gate_counts?.blocked || 0}</Text>
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
              const label = assetOptions.find((asset) => asset.value === assetType)?.label || group.label || assetType;
              return (
                <Box key={assetType}>
                  <Text format={{fontWeight: "bold"}}>{label} ({assets.length})</Text>
                  <Text>Analyzed: {counts.analyzed || 0} · Metadata only: {counts.metadata_only || 0} · Fetch errors: {counts.fetch_error || 0}</Text>
                  {assets.slice(0, 4).map((asset) => (
                    <Text key={`${assetType}-${asset.id || asset.name}`}>{asset.name || asset.id || "Unnamed asset"}: {asset.status || "unknown"}{asset.score !== undefined ? `, score ${asset.score}` : ""}</Text>
                  ))}
                </Box>
              );
            })}
          </Flex>
        </Box>
      ) : null}
    </>
  );
}


export function MarketingEmailPanel({values, onChange, onAction, actionLoading, emailResults}) {
  return (
    <>
      <Divider />
      <Text format={{fontWeight: "bold"}}>Marketing email draft</Text>
      <Text>Create, fetch, score, and attach a HubSpot marketing email draft without leaving the TextTraits app home page.</Text>
      <Flex direction="column" gap="sm">
        <Input label="Email ID" name="email_id" value={values.emailId} onInput={onChange.emailId} placeholder="HubSpot marketing email ID" />
        <Input label="Email name" name="email_name" value={values.emailName} onInput={onChange.emailName} placeholder="Renewal workflow follow-up" />
        <Input label="Subject" name="email_subject" value={values.emailSubject} onInput={onChange.emailSubject} placeholder="Renewal workflow follow-up" />
        <Input label="Template path" name="template_path" value={values.templatePath} onInput={onChange.templatePath} placeholder="@hubspot/email/dnd/welcome.html" />
        <TextArea label="Draft body for review" name="email_body" value={values.emailBody} onInput={onChange.emailBody} placeholder="Paste the existing draft body before routing." rows={5} />
        <Button onClick={onAction.searchMarketingEmails} disabled={actionLoading || !values.portalId}>{actionLoading === "Search marketing emails" ? "Searching..." : "Find marketing email drafts"}</Button>
        <Button onClick={onAction.createMarketingEmail} disabled={actionLoading || !values.portalId || !values.emailName || !values.emailSubject || !values.templatePath}>{actionLoading === "Create marketing email" ? "Creating..." : "Create marketing email draft"}</Button>
        <Button onClick={onAction.updateMarketingEmail} disabled={actionLoading || !values.portalId || !values.emailId || (!values.emailName && !values.emailSubject && !values.emailBody)}>{actionLoading === "Update marketing email" ? "Updating..." : "Update marketing email draft"}</Button>
        <Button onClick={onAction.fetchMarketingEmail} disabled={actionLoading || !values.portalId || !values.emailId}>{actionLoading === "Fetch marketing email" ? "Fetching..." : "Fetch and review email draft"}</Button>
        <Button variant="primary" onClick={onAction.prePublishGuardrail} disabled={actionLoading || !values.portalId || !values.emailId}>{actionLoading === "Pre-publish guardrail" ? "Checking..." : "Run pre-publish guardrail"}</Button>
        <Button onClick={onAction.analyzeAndSyncDraft} disabled={actionLoading || !values.portalId || (!values.emailSubject && !values.emailBody)}>{actionLoading === "Analyze and sync draft" ? "Syncing..." : "Analyze and sync draft"}</Button>
        <Button onClick={onAction.associateEmailToCampaign} disabled={actionLoading || !values.portalId || !values.campaignId || !values.emailId}>{actionLoading === "Associate email to campaign" ? "Associating..." : "Attach email to campaign"}</Button>
      </Flex>
      {emailResults.length ? (
        <Box>
          <Text format={{fontWeight: "bold"}}>Marketing email matches</Text>
          <Flex direction="column" gap="xs">
            {emailResults.slice(0, 6).map((email) => (
              <Button key={email.id || email.name} onClick={() => onAction.selectEmail(email)}>{email.name || email.subject || email.id}</Button>
            ))}
          </Flex>
        </Box>
      ) : null}
    </>
  );
}


export function SegmentPanel({values, onChange, onAction, actionLoading, segmentResults, segmentMemberships}) {
  return (
    <>
      <Divider />
      <Text format={{fontWeight: "bold"}}>HubSpot segments</Text>
      <Text>Find existing HubSpot segments before creating review lists for ready, needs-review, or blocked records.</Text>
      <Flex direction="column" gap="sm">
        <Input label="Segment search" name="segment_query" value={values.segmentQuery} onInput={onChange.segmentQuery} placeholder="TextTraits, needs review, blocked" />
        <Input label="Object type ID" name="segment_object_type_id" value={values.segmentObjectTypeId} onInput={onChange.segmentObjectTypeId} placeholder="0-1 for contacts" />
        <Input label="Processing type" name="segment_processing_type" value={values.segmentProcessingType} onInput={onChange.segmentProcessingType} placeholder="Optional: MANUAL, DYNAMIC, SNAPSHOT" />
        <Input label="Segment ID" name="segment_id" value={values.segmentId} onInput={onChange.segmentId} placeholder="HubSpot list or segment ID" />
        <Button onClick={onAction.searchSegments} disabled={actionLoading || !values.portalId}>{actionLoading === "Search segments" ? "Searching..." : "Find segments"}</Button>
        <Button onClick={onAction.previewSegmentMembers} disabled={actionLoading || !values.portalId || !values.segmentId}>{actionLoading === "Preview segment members" ? "Loading..." : "Preview segment members"}</Button>
        <Input label="Record IDs to add" name="segment_add_ids" value={values.segmentAddIds} onInput={onChange.segmentAddIds} placeholder="Comma-separated HubSpot record IDs" />
        <Input label="Record IDs to remove" name="segment_remove_ids" value={values.segmentRemoveIds} onInput={onChange.segmentRemoveIds} placeholder="Optional record IDs to remove" />
        <Button onClick={onAction.updateSegmentMembers} disabled={actionLoading || !values.portalId || !values.segmentId || (!values.segmentAddIds && !values.segmentRemoveIds)}>{actionLoading === "Update segment members" ? "Updating..." : "Update segment members"}</Button>
      </Flex>
      {segmentResults.length ? (
        <Box>
          <Text format={{fontWeight: "bold"}}>Segment matches</Text>
          <Flex direction="column" gap="xs">
            {segmentResults.slice(0, 6).map((segment) => (
              <Button key={segment.list_id || segment.name} onClick={() => onChange.segmentId(String(segment.list_id || ""))}>{segment.name || segment.list_id} · {segment.processing_type || "Unknown type"} · {segment.size ?? "Unknown size"}</Button>
            ))}
          </Flex>
        </Box>
      ) : null}
      {segmentMemberships.length ? (
        <Box>
          <Text format={{fontWeight: "bold"}}>Segment member preview</Text>
          <Flex direction="column" gap="xs">
            {segmentMemberships.slice(0, 6).map((member, index) => (
              <Text key={member.recordId || member.record_id || index}>Record {member.recordId || member.record_id || member.id || "unknown"}{member.membershipTimestamp ? ` · ${member.membershipTimestamp}` : ""}</Text>
            ))}
          </Flex>
        </Box>
      ) : null}
    </>
  );
}


export function HubSpotActionResult({state}) {
  if (state.error) return <Alert variant="error" title="HubSpot action unavailable">{state.error}</Alert>;
  if (!state.result) return null;
  const payload = state.result.payload || {};
  return (
    <Box>
      <Text format={{fontWeight: "bold"}}>{state.result.action}: {state.result.status}</Text>
      <Text>{payload?.sync?.status ? `Sync status: ${payload.sync.status}` : "HubSpot request completed."}</Text>
      {payload.campaigns ? <Text>Campaigns found: {payload.campaigns.length}</Text> : null}
      {payload.emails ? <Text>Emails found: {payload.emails.length}</Text> : null}
      {payload.lists ? <Text>Segments found: {payload.lists.length}</Text> : null}
      {payload.memberships ? <Text>Segment members: {payload.memberships.length}</Text> : null}
      {payload.guardrail ? <Text>Guardrail: {payload.guardrail.gate} · score {payload.guardrail.score} · publish allowed: {String(payload.guardrail.publish_allowed)}</Text> : null}
      {payload.summary?.coverage ? <Text>Bulk coverage: {payload.summary.coverage.coverage_score}% · {payload.summary.coverage.coverage_label}</Text> : null}
      {payload.events ? <Text>Outcome events imported: {payload.events.length}</Text> : null}
      {payload.details?.operation ? <Text>Segment update: {payload.details.operation} ({payload.details.added || 0} added, {payload.details.removed || 0} removed)</Text> : null}
    </Box>
  );
}
