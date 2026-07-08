import React, {useEffect, useMemo, useState} from "react";
import {
  Alert,
  Box,
  Button,
  Divider,
  Flex,
  Input,
  LoadingSpinner,
  Text,
  TextArea,
  hubspot,
} from "@hubspot/ui-extensions";

const API_BASE = "https://texttraits.onrender.com";

hubspot.extend(({context, actions}) => (
  <TextTraitsEmailFitCard context={context} actions={actions} />
));

function portalIdFromContext(context) {
  return String(context?.portal?.id || context?.portalId || "");
}

function recordIdFromContext(context) {
  return String(context?.crm?.objectId || context?.objectId || context?.recordId || "");
}

function objectTypeFromContext(context) {
  return String(context?.crm?.objectType || context?.objectType || context?.objectTypeId || "");
}

function gateLabel(gate) {
  if (gate === "ready") return "Ready";
  if (gate === "blocked") return "Blocked";
  if (gate === "needs_review") return "Needs review";
  return gate || "Not analyzed";
}

function valueFrom(...values) {
  for (const value of values) {
    if (value === null || value === undefined) continue;
    const clean = String(value).trim();
    if (clean) return clean;
  }
  return "";
}

function firstFinding(visible) {
  return visible?.email_quality?.findings?.[0] || visible?.findings?.[0] || {};
}

function taskIdFromSync(result, latestReviewState) {
  const taskAction = (result?.sync?.actions || []).find((item) => item?.action === "review_task_created" || item?.action === "review_task_updated");
  return valueFrom(
    taskAction?.hubspot?.id,
    taskAction?.hubspot?.hs_object_id,
    latestReviewState?.payload?.task_id,
    latestReviewState?.payload?.hubspot_task_id,
    latestReviewState?.payload?.task?.id,
    latestReviewState?.payload?.task?.hs_object_id,
  );
}

function FieldRow({label, value}) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <Box>
      <Text>{label}</Text>
      <Text format={{fontWeight: "bold"}}>{String(value)}</Text>
    </Box>
  );
}

function TextTraitsEmailFitCard({context, actions}) {
  const portalId = portalIdFromContext(context);
  const objectId = recordIdFromContext(context);
  const objectType = objectTypeFromContext(context);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [latest, setLatest] = useState(null);
  const [reviewStates, setReviewStates] = useState([]);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  const contextPayload = useMemo(() => ({
    portal_id: portalId,
    object_id: objectId,
    object_type: objectType,
    source_system: "hubspot_ui_extension",
    analysis_mode: "crm_record_sidebar_review",
    hubspotContext: context,
  }), [portalId, objectId, objectType, context]);

  useEffect(() => {
    let cancelled = false;
    async function loadLatest() {
      setLoading(true);
      setError("");
      try {
        const response = await hubspot.fetch(`${API_BASE}/v1/integrations/hubspot/app-card/latest`, {
          method: "POST",
          body: contextPayload,
          timeout: 15000,
        });
        const payload = await response.json();
        if (!cancelled) {
          setLatest(payload.latest || null);
          setReviewStates(payload.review_states || []);
        }
      } catch (fetchError) {
        if (!cancelled) setError("TextTraits latest review could not load.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    loadLatest();
    return () => {
      cancelled = true;
    };
  }, [contextPayload]);

  async function analyzeDraft() {
    setSubmitting(true);
    setError("");
    try {
      const response = await hubspot.fetch(`${API_BASE}/v1/integrations/hubspot/analyze-and-sync`, {
        method: "POST",
        body: {
          ...contextPayload,
          inputFields: {
            subject,
            body,
            portal_id: portalId,
            object_id: objectId,
            object_type: objectType,
          },
          writeback_properties: true,
          record_review_state: true,
          create_review_task: true,
        },
        timeout: 15000,
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Analysis failed.");
      setResult(payload);
      setLatest(payload.analysis || null);
      setReviewStates([]);
      actions?.addAlert?.({type: "success", message: "TextTraits analysis synced."});
    } catch (submitError) {
      setError(submitError.message || "TextTraits analysis failed.");
    } finally {
      setSubmitting(false);
    }
  }

  async function reviewAction(action) {
    const requestId = result?.outputFields?.texttraits_request_id || latest?.request_id;
    if (!requestId) return;
    const latestReviewState = reviewStates?.[0] || {};
    const taskId = taskIdFromSync(result, latestReviewState);
    setSubmitting(true);
    setError("");
    try {
      const response = await hubspot.fetch(`${API_BASE}/v1/integrations/hubspot/review-action`, {
        method: "POST",
        body: {
          ...contextPayload,
          request_id: requestId,
          action,
          actor_id: context?.user?.email || "",
          task_id: taskId,
          sync_hubspot: true,
          payload: {
            review_status: action === "approve_review" ? "approved" : action === "reject_review" ? "rejected" : action === "resolve_review" ? "resolved" : "queued",
            owner_queue: result?.outputFields?.texttraits_owner_queue || latest?.route || "",
            blocker_level: result?.outputFields?.texttraits_blocker_level || "",
            task_id: taskId,
          },
        },
        timeout: 15000,
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Review action failed.");
      const message = action === "approve_review" ? "Marked approved." : action === "reject_review" ? "Marked rejected." : action === "resolve_review" ? "Marked resolved." : "Sent to review.";
      actions?.addAlert?.({type: "success", message});
      setReviewStates(payload.event ? [{...payload.event, status: payload.event.payload?.review_status || payload.event.status}] : reviewStates);
    } catch (actionError) {
      setError(actionError.message || "Review action failed.");
    } finally {
      setSubmitting(false);
    }
  }

  function openCampaignAnalysis() {
    const campaignId = result?.analysis?.context?.campaign_id || latest?.campaign_id || latest?.context?.campaign_id || "";
    if (!campaignId) {
      actions?.addAlert?.({type: "warning", message: "No HubSpot campaign ID is attached to this TextTraits review yet."});
      return;
    }
    const url = `${API_BASE}/?mode=enterprise&hubspot_campaign=${encodeURIComponent(campaignId)}`;
    if (actions?.openExternalUrl) {
      actions.openExternalUrl({url});
    } else {
      actions?.addAlert?.({type: "info", message: `Open TextTraits campaign analysis for ${campaignId}.`});
    }
  }

  const visible = result?.analysis || latest;
  const output = result?.outputFields || {};
  const findings = visible?.email_quality?.findings || visible?.findings || [];
  const finding = firstFinding(visible);
  const latestReviewState = reviewStates?.[0] || {};
  const gate = visible?.gate || output.texttraits_gate;
  const route = visible?.route || output.texttraits_route;
  const score = visible?.score ?? output.texttraits_score;
  const requestId = valueFrom(visible?.request_id, output.texttraits_request_id);
  const contentHash = valueFrom(visible?.content_hash, output.texttraits_content_hash);
  const nextStep = valueFrom(finding?.next_step, output.texttraits_next_step);
  const ownerQueue = valueFrom(output.texttraits_owner_queue, latestReviewState?.payload?.owner_queue, route);
  const blockerLevel = valueFrom(finding?.blocker_level, output.texttraits_blocker_level, latestReviewState?.payload?.blocker_level);
  const blockerReason = valueFrom(output.texttraits_blocker_reason, finding?.title, finding?.label);
  const policyVersion = valueFrom(visible?.policy?.version, output.texttraits_policy_version);
  const syncStatus = valueFrom(output.texttraits_sync_status, result?.sync?.status);

  return (
    <Box>
      <Text format={{fontWeight: "bold"}}>TextTraits email fit</Text>
      <Text>Score existing drafts before routing. TextTraits returns decision fields, not generated copy.</Text>
      <Divider />
      {loading ? <LoadingSpinner label="Loading TextTraits" /> : null}
      {error ? <Alert title="TextTraits needs attention" variant="error">{error}</Alert> : null}
      {visible ? (
        <Box>
          <Text format={{fontWeight: "bold"}}>{score} out of 100</Text>
          <Text>{gateLabel(gate)} · {route || "No route yet"}</Text>
          <Flex direction="column" gap="xs">
            <FieldRow label="Blocker" value={blockerReason || "No blocker detected"} />
            <FieldRow label="Next step" value={nextStep} />
            <FieldRow label="Owner or queue" value={ownerQueue} />
            <FieldRow label="Blocker level" value={blockerLevel} />
            <FieldRow label="Review status" value={latestReviewState?.status || (gate === "ready" ? "ready" : "")} />
            <FieldRow label="Sync status" value={syncStatus} />
            <FieldRow label="Policy version" value={policyVersion} />
            <FieldRow label="Request ID" value={requestId} />
            <FieldRow label="Content hash" value={contentHash} />
          </Flex>
          {findings.length > 1 ? (
            <Box>
              <Text format={{fontWeight: "bold"}}>Additional findings</Text>
              {findings.slice(1, 3).map((item) => (
                <Text key={item.id || item.title}>{item.title || item.label}: {item.next_step || item.status}</Text>
              ))}
            </Box>
          ) : null}
        </Box>
      ) : (
        <Text>No TextTraits review has been recorded for this record yet.</Text>
      )}
      <Divider />
      <Input label="Subject" name="subject" value={subject} onInput={setSubject} placeholder="Paste an existing subject" />
      <TextArea label="Body" name="body" value={body} onInput={setBody} placeholder="Paste an existing draft body" rows={6} />
      <Flex direction="column" gap="sm">
        <Button variant="primary" onClick={analyzeDraft} disabled={submitting || (!subject && !body)}>
          {submitting ? "Working..." : "Analyze draft"}
        </Button>
        <Button onClick={() => reviewAction("send_to_marketing_review")} disabled={submitting || !visible}>
          Send to review
        </Button>
        <Button onClick={() => reviewAction("approve_review")} disabled={submitting || !visible}>
          Approve
        </Button>
        <Button onClick={() => reviewAction("reject_review")} disabled={submitting || !visible}>
          Reject
        </Button>
        <Button onClick={() => reviewAction("resolve_review")} disabled={submitting || !visible}>
          Mark resolved
        </Button>
        <Button onClick={openCampaignAnalysis} disabled={submitting || !visible}>
          Open campaign analysis
        </Button>
      </Flex>
    </Box>
  );
}
