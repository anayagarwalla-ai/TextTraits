import React from "react";
import {Accordion, Alert, Box, Button, Flex, Input, StatusTag, Text} from "@hubspot/ui-extensions";

function statusCounts(assets) {
  return assets.reduce((counts, asset) => {
    const status = asset.status || "unknown";
    return {...counts, [status]: (counts[status] || 0) + 1};
  }, {});
}

function statusLabel(value) {
  const labels = {
    ready: "Ready",
    blocked: "Blocked",
    needs_review: "Review required",
    analyzed: "Checked",
    metadata_only: "Copy unavailable",
    fetch_error: "Could not load",
    analysis_error: "Check failed",
    idempotency_conflict: "Import conflict",
    not_reviewed: "Not checked",
    analysis_only: "Read-only check",
  };
  return labels[value] || String(value || "Unknown").replaceAll("_", " ");
}

function gateVariant(value) {
  if (value === "ready") return "success";
  if (value === "blocked") return "danger";
  if (value === "needs_review") return "warning";
  return "default";
}

export function EnterpriseContextFields({values, onChange}) {
  return (
    <Flex direction="column" gap="sm">
      <Input label="Audience" name="audience_type" value={values.audienceType} onInput={onChange.audienceType} placeholder="Candidates, clients, employees" />
      <Input label="Region" name="region" value={values.region} onInput={onChange.region} placeholder="US, EU, APAC" />
      <Input label="Business unit" name="business_unit" value={values.businessUnit} onInput={onChange.businessUnit} placeholder="Staffing, Enterprise, Healthcare" />
      <Input label="Job or campaign reference" name="job_id" value={values.jobId} onInput={onChange.jobId} placeholder="Optional internal ID" />
      <Input label="Skill or product family" name="skill_family" value={values.skillFamily} onInput={onChange.skillFamily} placeholder="Logistics, Nursing, Finance" />
      <Input label="Reviewer" name="recruiter" value={values.recruiter} onInput={onChange.recruiter} placeholder="Reviewer or delivery owner" />
      <Input label="Client account" name="client_account" value={values.clientAccount} onInput={onChange.clientAccount} placeholder="Customer or business account" />
    </Flex>
  );
}

export function CampaignPanel({assetOptions, assetTypes, values, onChange, onAction, actionLoading, reviewState, campaignResults}) {
  const assetMapEntries = Object.entries(reviewState.result?.asset_map || {});
  const summary = reviewState.result?.summary || {};
  const copyCoverage = summary.copy_coverage || {};
  return (
    <>
      <Text>Choose an existing campaign, then check the copy HubSpot can provide. TextTraits does not create or edit campaign assets.</Text>
      <Flex direction="column" gap="sm">
        <Input
          label="Find a campaign"
          name="campaign_name"
          value={values.campaignName}
          onInput={onChange.campaignName}
          placeholder="Campaign name"
        />
        <Button onClick={onAction.searchCampaigns} disabled={actionLoading || !values.campaignName}>
          {actionLoading === "Search campaigns" ? "Searching..." : "Search campaigns"}
        </Button>
        {campaignResults.length ? (
          <Box>
            <Text format={{fontWeight: "bold"}}>Matches</Text>
            <Flex direction="column" gap="xs">
              {campaignResults.slice(0, 6).map((campaign) => (
                <Button key={campaign.id || campaign.name} onClick={() => onAction.selectCampaign(campaign)}>
                  {campaign.name || campaign.id}
                </Button>
              ))}
            </Flex>
          </Box>
        ) : null}
        {values.campaignId ? (
          <Alert variant="info" title="Selected campaign">
            {values.campaignName || values.campaignId}
          </Alert>
        ) : null}
        <Button variant="primary" onClick={onAction.reviewCampaign} disabled={reviewState.loading || !values.campaignId}>
          {reviewState.loading ? "Checking campaign..." : "Check campaign copy"}
        </Button>
      </Flex>

      <Accordion title="Copy sources included" size="sm">
        <Text>Select only the source types used by this campaign.</Text>
        <Flex direction="column" gap="xs">
          {assetOptions.map((asset) => (
            <Button
              key={asset.value}
              variant={assetTypes.includes(asset.value) ? "primary" : undefined}
              onClick={() => onAction.toggleAssetType(asset.value)}
            >
              {assetTypes.includes(asset.value) ? "Included: " : "Include: "}{asset.label}
            </Button>
          ))}
        </Flex>
      </Accordion>

      {reviewState.error ? <Alert variant="error" title="Campaign check unavailable">{reviewState.error}</Alert> : null}
      {reviewState.result ? (
        <Box>
          <Flex align="center" justify="between" gap="sm" wrap>
            <Text format={{fontWeight: "bold"}}>Campaign decision</Text>
            <StatusTag variant={gateVariant(summary.health)}>{statusLabel(summary.health)}</StatusTag>
          </Flex>
          <Text>Ready: {summary.gate_counts?.ready || 0} · Review required: {summary.gate_counts?.needs_review || 0} · Blocked: {summary.gate_counts?.blocked || 0}</Text>
          <Text>Checked: {summary.analyzed || 0} · Copy unavailable: {summary.skipped || 0}</Text>
          <Text>Copy coverage: {copyCoverage.coverage_score ?? 0}% · {copyCoverage.coverage_label || "Not measured"}</Text>
          <Text>{copyCoverage.note || "TextTraits checks only copy returned by HubSpot or deliberately mapped by your team."}</Text>
        </Box>
      ) : null}
      {assetMapEntries.length ? (
        <Accordion title="Asset-level results" size="sm">
          <Flex direction="column" gap="sm">
            {assetMapEntries.map(([assetType, group]) => {
              const assets = Array.isArray(group.assets) ? group.assets : [];
              const counts = statusCounts(assets);
              const label = assetOptions.find((asset) => asset.value === assetType)?.label || group.label || assetType;
              return (
                <Box key={assetType}>
                  <Text format={{fontWeight: "bold"}}>{label} ({assets.length})</Text>
                  <Text>Checked: {counts.analyzed || 0} · Copy unavailable: {counts.metadata_only || 0} · Errors: {counts.fetch_error || 0}</Text>
                  {assets.slice(0, 4).map((asset) => (
                    <Text key={`${assetType}-${asset.id || asset.name}`}>
                      {asset.name || asset.id || "Unnamed asset"}: {statusLabel(asset.status)}{asset.score !== undefined ? ` · ${asset.score}/100` : ""}
                    </Text>
                  ))}
                </Box>
              );
            })}
          </Flex>
        </Accordion>
      ) : null}
    </>
  );
}

export function MarketingEmailPanel({values, onChange, onAction, actionLoading, emailResults}) {
  return (
    <>
      <Text>Find an existing HubSpot marketing email and run a read-only pre-send check.</Text>
      <Flex direction="column" gap="sm">
        <Input
          label="Find a marketing email"
          name="email_name"
          value={values.emailName}
          onInput={onChange.emailName}
          placeholder="Email name or subject"
        />
        <Button onClick={onAction.searchMarketingEmails} disabled={actionLoading || !values.emailName}>
          {actionLoading === "Search marketing emails" ? "Searching..." : "Search marketing emails"}
        </Button>
        {emailResults.length ? (
          <Box>
            <Text format={{fontWeight: "bold"}}>Matches</Text>
            <Flex direction="column" gap="xs">
              {emailResults.slice(0, 6).map((email) => (
                <Button key={email.id || email.name} onClick={() => onAction.selectEmail(email)}>
                  {email.name || email.subject || email.id}
                </Button>
              ))}
            </Flex>
          </Box>
        ) : null}
        {values.emailId ? (
          <Alert variant="info" title="Selected email">
            {values.emailName || values.emailSubject || values.emailId}
          </Alert>
        ) : null}
        <Button variant="primary" onClick={onAction.prePublishGuardrail} disabled={actionLoading || !values.emailId}>
          {actionLoading === "Pre-send check" ? "Checking..." : "Run pre-send check"}
        </Button>
      </Flex>
      <Accordion title="Use an email ID instead" size="sm">
        <Input
          label="Marketing email ID"
          name="email_id"
          value={values.emailId}
          onInput={onChange.emailId}
          placeholder="HubSpot marketing email ID"
        />
      </Accordion>
    </>
  );
}

export function SegmentPanel({values, onChange, onAction, actionLoading, segmentResults, segmentMemberships}) {
  return (
    <>
      <Text>Inspect existing HubSpot segments used for review routing. TextTraits will not add or remove members here.</Text>
      <Flex direction="column" gap="sm">
        <Input label="Find a segment" name="segment_query" value={values.segmentQuery} onInput={onChange.segmentQuery} placeholder="Needs review, blocked, ready" />
        <Button onClick={onAction.searchSegments} disabled={actionLoading || !values.segmentQuery}>
          {actionLoading === "Search segments" ? "Searching..." : "Search segments"}
        </Button>
        {segmentResults.length ? (
          <Box>
            <Text format={{fontWeight: "bold"}}>Matches</Text>
            <Flex direction="column" gap="xs">
              {segmentResults.slice(0, 6).map((segment) => (
                <Button key={segment.list_id || segment.name} onClick={() => onChange.segmentId(String(segment.list_id || ""))}>
                  {segment.name || segment.list_id} · {segment.size ?? "Unknown size"}
                </Button>
              ))}
            </Flex>
          </Box>
        ) : null}
        <Button onClick={onAction.previewSegmentMembers} disabled={actionLoading || !values.segmentId}>
          {actionLoading === "Preview segment members" ? "Loading..." : "Preview selected segment"}
        </Button>
      </Flex>
      {segmentMemberships.length ? (
        <Box>
          <Text format={{fontWeight: "bold"}}>Member preview</Text>
          <Flex direction="column" gap="xs">
            {segmentMemberships.slice(0, 6).map((member, index) => (
              <Text key={member.recordId || member.record_id || index}>
                Record {member.recordId || member.record_id || member.id || "unknown"}
              </Text>
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
    <Alert variant="success" title={`${state.result.action} complete`}>
      {payload.guardrail ? (
        <Text>
          Decision: {statusLabel(payload.guardrail.gate)} · score {payload.guardrail.score}/100 · send allowed: {payload.guardrail.publish_allowed ? "Yes" : "No"}
        </Text>
      ) : null}
      {payload.campaigns ? <Text>Campaigns found: {payload.campaigns.length}</Text> : null}
      {payload.emails ? <Text>Emails found: {payload.emails.length}</Text> : null}
      {payload.lists ? <Text>Segments found: {payload.lists.length}</Text> : null}
      {payload.memberships ? <Text>Segment members shown: {payload.memberships.length}</Text> : null}
      {payload.summary?.coverage ? <Text>Imported copy coverage: {payload.summary.coverage.coverage_score}%</Text> : null}
      {!payload.guardrail && !payload.campaigns && !payload.emails && !payload.lists && !payload.memberships && !payload.summary?.coverage ? (
        <Text>HubSpot request completed.</Text>
      ) : null}
    </Alert>
  );
}
