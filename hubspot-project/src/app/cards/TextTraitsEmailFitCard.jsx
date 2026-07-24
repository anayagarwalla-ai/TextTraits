import React, {useEffect, useMemo, useState} from "react";
import {
  Accordion,
  Alert,
  Box,
  Button,
  Divider,
  Flex,
  Input,
  LoadingSpinner,
  Select,
  StatusTag,
  Text,
  TextArea,
  hubspot,
} from "@hubspot/ui-extensions";
import {useAssociations, useCrmProperties} from "@hubspot/ui-extensions/crm";
import {hubspotApi} from "../lib/api";
import {objectTypeFromContext, portalIdFromContext, recordIdFromContext} from "../lib/context";

hubspot.extend(({context, actions}) => (
  <TextTraitsEmailFitCard context={context} actions={actions} />
));

const EMAIL_PROPERTIES = [
  "hs_email_subject",
  "hs_email_text",
  "hs_email_html",
  "hs_timestamp",
  "hs_lastmodifieddate",
  "hubspot_owner_id",
];

const CRM_PROPERTIES = {
  contacts: ["firstname", "lastname", "email"],
  companies: ["name", "domain"],
  deals: ["dealname", "dealstage"],
  tickets: ["subject", "hs_pipeline_stage"],
};

function normalizeObjectType(value) {
  const clean = String(value || "").toLowerCase();
  if (clean === "0-1" || clean.includes("contact")) return "contacts";
  if (clean === "0-2" || clean.includes("compan")) return "companies";
  if (clean === "0-3" || clean.includes("deal")) return "deals";
  if (clean === "0-5" || clean.includes("ticket")) return "tickets";
  return clean || "records";
}

function gateLabel(gate) {
  if (gate === "ready") return "Ready";
  if (gate === "blocked") return "Blocked";
  if (gate === "needs_review") return "Review required";
  return gate || "Not checked";
}

function gateVariant(gate) {
  if (gate === "ready") return "success";
  if (gate === "blocked") return "danger";
  if (gate === "needs_review") return "warning";
  return "default";
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

function sourceText(properties) {
  return valueFrom(properties?.hs_email_text, properties?.hs_email_html);
}

function sourceTimestamp(properties) {
  return valueFrom(properties?.hs_lastmodifieddate, properties?.hs_timestamp);
}

function formatTimestamp(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
}

function recordLabel(objectType, properties) {
  if (objectType === "contacts") {
    return valueFrom(`${properties.firstname || ""} ${properties.lastname || ""}`.trim(), properties.email, "Contact");
  }
  if (objectType === "companies") return valueFrom(properties.name, properties.domain, "Company");
  if (objectType === "deals") return valueFrom(properties.dealname, "Deal");
  if (objectType === "tickets") return valueFrom(properties.subject, "Ticket");
  return "CRM record";
}

function singularObjectLabel(objectType) {
  if (objectType === "contacts") return "contact";
  if (objectType === "companies") return "company";
  if (objectType === "deals") return "deal";
  if (objectType === "tickets") return "ticket";
  return "CRM record";
}

function taskIdFromState(latestReviewState) {
  return valueFrom(
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

function decisionAction(gate) {
  if (gate === "ready") {
    return {action: "mark_reviewed", label: "Mark reviewed", status: "resolved"};
  }
  if (gate === "blocked") {
    return {action: "assign_reviewer", label: "Record blocked decision", status: "assigned"};
  }
  return {action: "send_to_marketing_review", label: "Record review request", status: "queued"};
}

function TextTraitsEmailFitCard({context, actions}) {
  const portalId = portalIdFromContext(context);
  const objectId = recordIdFromContext(context);
  const objectType = normalizeObjectType(objectTypeFromContext(context));
  const crmPropertyNames = CRM_PROPERTIES[objectType] || [];
  const crmState = useCrmProperties(crmPropertyNames);
  const emailAssociations = useAssociations(
    {toObjectType: "emails", properties: EMAIL_PROPERTIES, pageLength: 5},
    {propertiesToFormat: EMAIL_PROPERTIES},
  );
  const [sourceChoice, setSourceChoice] = useState("manual");
  const [sourceTouched, setSourceTouched] = useState(false);
  const [sourceMetadata, setSourceMetadata] = useState({type: "Manual paste"});
  const [marketingEmailId, setMarketingEmailId] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [latest, setLatest] = useState(null);
  const [history, setHistory] = useState([]);
  const [reviewStates, setReviewStates] = useState([]);
  const [result, setResult] = useState(null);
  const [checkedFingerprint, setCheckedFingerprint] = useState("");
  const [pendingDecision, setPendingDecision] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  const contextPayload = useMemo(() => ({
    portal_id: portalId,
    object_id: objectId,
    object_type: objectType,
    source_system: "hubspot_ui_extension",
    analysis_mode: "crm_record_sidebar_check",
    hubspotContext: context,
  }), [portalId, objectId, objectType, context]);

  const associatedEmails = emailAssociations.results || [];
  const sourceFingerprint = `${subject}\n${body}`;
  const sourceIsStale = Boolean(checkedFingerprint && checkedFingerprint !== sourceFingerprint);
  const activeRecordLabel = recordLabel(objectType, crmState.properties || {});

  const sourceOptions = useMemo(() => {
    const crmEmailOptions = associatedEmails.map((item, index) => ({
      value: `crm-email:${item.toObjectId}`,
      label: valueFrom(item.properties?.hs_email_subject, `Associated email ${index + 1}`),
    }));
    return [
      ...crmEmailOptions,
      {value: "marketing-email", label: "Marketing email draft by ID"},
      {value: "manual", label: "Paste existing copy"},
    ];
  }, [associatedEmails]);

  useEffect(() => {
    if (sourceTouched || emailAssociations.isLoading || !associatedEmails.length) return;
    applySourceChoice(`crm-email:${associatedEmails[0].toObjectId}`, associatedEmails);
  }, [associatedEmails, emailAssociations.isLoading, sourceTouched]);

  useEffect(() => {
    let cancelled = false;
    async function loadLatest() {
      setLoading(true);
      setError("");
      try {
        const {payload} = await hubspotApi("/v1/integrations/hubspot/app-card/latest", {
          method: "POST",
          body: contextPayload,
          timeout: 15000,
          errorMessage: "The latest TextTraits check could not load.",
        });
        if (!cancelled) {
          setLatest(payload.latest || null);
          setHistory(payload.analyses || []);
          setReviewStates(payload.review_states || []);
        }
      } catch (fetchError) {
        if (!cancelled) setError(fetchError.message || "The latest TextTraits check could not load.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    loadLatest();
    return () => {
      cancelled = true;
    };
  }, [contextPayload]);

  function applySourceChoice(value, availableEmails = associatedEmails) {
    setSourceChoice(value);
    setSourceTouched(true);
    setPendingDecision(null);
    if (value === "manual") {
      setSubject("");
      setBody("");
      setSourceMetadata({type: "Manual paste"});
      return;
    }
    if (value === "marketing-email") {
      setSubject("");
      setBody("");
      setSourceMetadata({type: "Marketing email draft", id: marketingEmailId});
      return;
    }
    const emailId = value.split(":")[1] || "";
    const selected = availableEmails.find((item) => String(item.toObjectId) === emailId);
    if (!selected) return;
    const properties = selected.properties || {};
    setSubject(valueFrom(properties.hs_email_subject));
    setBody(sourceText(properties));
    setSourceMetadata({
      type: "Associated CRM email",
      id: emailId,
      owner: valueFrom(properties.hubspot_owner_id),
      modifiedAt: sourceTimestamp(properties),
    });
  }

  async function checkMarketingEmail() {
    const {payload} = await hubspotApi("/v1/integrations/hubspot/marketing-emails/fetch", {
      method: "POST",
      body: {
        ...contextPayload,
        email_id: marketingEmailId,
        analyze: true,
      },
      timeout: 15000,
      errorMessage: "The marketing email draft could not be checked.",
    });
    const analysisResult = payload.analysis || {};
    if (analysisResult.error) throw new Error(analysisResult.error);
    const email = payload.email || {};
    setSubject(valueFrom(email.subject, email.name));
    setBody(valueFrom(email.html, email.htmlBody, email.body, email.content));
    setSourceMetadata({
      type: "Marketing email draft",
      id: valueFrom(email.id, marketingEmailId),
      name: valueFrom(email.name, email.subject),
      owner: valueFrom(email.createdBy, email.updatedBy),
      modifiedAt: valueFrom(email.updatedAt, email.updated, email.lastUpdatedAt),
    });
    return analysisResult;
  }

  async function checkEmail() {
    setSubmitting(true);
    setError("");
    setPendingDecision(null);
    try {
      let payload;
      if (sourceChoice === "marketing-email") {
        payload = await checkMarketingEmail();
      } else {
        const response = await hubspotApi("/v1/integrations/hubspot/crm-card/analyze-email", {
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
          },
          timeout: 15000,
          errorMessage: "The email check failed.",
        });
        payload = response.payload;
      }
      setResult(payload);
      setLatest(payload.analysis || null);
      if (payload.analysis) {
        setHistory((current) => [
          payload.analysis,
          ...current.filter((item) => item.request_id !== payload.analysis.request_id),
        ].slice(0, 10));
      }
      setCheckedFingerprint(sourceChoice === "marketing-email" ? "" : sourceFingerprint);
      actions?.addAlert?.({
        type: "success",
        message: "Check complete. No HubSpot records were changed.",
      });
    } catch (submitError) {
      setError(submitError.message || "The TextTraits check failed.");
    } finally {
      setSubmitting(false);
    }
  }

  async function recordDecision() {
    const requestId = result?.outputFields?.texttraits_request_id || latest?.request_id;
    if (!requestId || !pendingDecision) return;
    const latestReviewState = reviewStates?.[0] || {};
    const taskId = taskIdFromState(latestReviewState);
    setSubmitting(true);
    setError("");
    try {
      const {payload} = await hubspotApi("/v1/integrations/hubspot/review-action", {
        method: "POST",
        body: {
          ...contextPayload,
          request_id: requestId,
          action: pendingDecision.action,
          actor_id: context?.user?.email || "",
          task_id: taskId,
          sync_hubspot: true,
          confirm_side_effects: true,
          writeback_properties: true,
          update_review_task: Boolean(taskId),
          sync_analysis_object: false,
          payload: {
            review_status: pendingDecision.status,
            owner_queue: result?.outputFields?.texttraits_owner_queue || latest?.route || "",
            blocker_level: result?.outputFields?.texttraits_blocker_level || "",
            task_id: taskId,
          },
        },
        timeout: 15000,
        errorMessage: "The review decision could not be recorded.",
      });
      actions?.addAlert?.({type: "success", message: "Review decision recorded in HubSpot."});
      if (payload.event) {
        setReviewStates((current) => [
          {...payload.event, status: payload.event.payload?.review_status || payload.event.status},
          ...current.filter((item) => item.created_at !== payload.event.created_at),
        ]);
      }
      setPendingDecision(null);
    } catch (actionError) {
      setError(actionError.message || "The review decision could not be recorded.");
    } finally {
      setSubmitting(false);
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
  const reviewerGuidance = valueFrom(finding?.next_step, output.texttraits_next_step);
  const ownerQueue = valueFrom(output.texttraits_owner_queue, latestReviewState?.payload?.owner_queue, route);
  const blockerLevel = valueFrom(finding?.blocker_level, output.texttraits_blocker_level, latestReviewState?.payload?.blocker_level);
  const primaryReason = valueFrom(output.texttraits_blocker_reason, finding?.title, finding?.label, "No blocking issue detected.");
  const policyVersion = valueFrom(visible?.policy?.version, output.texttraits_policy_version);
  const analysisEngine = valueFrom(visible?.analysis_engine, output.texttraits_analysis_engine);
  const createdAt = valueFrom(visible?.checked_at, visible?.created_at, latest?.created_at);
  const sourceReady = sourceChoice === "marketing-email" ? Boolean(marketingEmailId) : Boolean(subject || body);
  const actionForDecision = decisionAction(gate);

  return (
    <Box>
      {loading ? <LoadingSpinner label="Loading TextTraits" /> : null}
      {error ? <Alert title="TextTraits needs attention" variant="error">{error}</Alert> : null}

      {visible ? (
        <Box>
          <Flex align="center" justify="between" gap="sm" wrap>
            <Text format={{fontWeight: "bold"}}>{gateLabel(gate)}</Text>
            <StatusTag variant={gateVariant(gate)}>{sourceIsStale ? "Check again" : gateLabel(gate)}</StatusTag>
          </Flex>
          <Text>{primaryReason}</Text>
          <Divider />
          <Flex direction="column" gap="sm">
            <Box>
              <Text format={{fontWeight: "bold"}}>What triggered it</Text>
              {findings.length ? (
                findings.slice(0, 3).map((item) => (
                  <Text key={item.id || item.title}>{item.title || item.label}</Text>
                ))
              ) : (
                <Text>No blocking issue was detected in this copy.</Text>
              )}
            </Box>
            <Box>
              <Text format={{fontWeight: "bold"}}>Reviewer guidance</Text>
              <Text>{reviewerGuidance || "Confirm the copy matches the intended audience, evidence, and policy before sending."}</Text>
            </Box>
          </Flex>
          <Accordion title="Score and audit details" size="sm">
            <Flex direction="column" gap="xs">
              <FieldRow label="Email-quality score" value={score === "" || score === undefined ? "" : `${score} out of 100`} />
              <FieldRow label="Route" value={route} />
              <FieldRow label="Owner or queue" value={ownerQueue} />
              <FieldRow label="Blocker level" value={blockerLevel} />
              <FieldRow label="Review status" value={latestReviewState?.status || "Not recorded in HubSpot"} />
              <FieldRow label="Checked" value={formatTimestamp(createdAt)} />
              <FieldRow label="Checked by" value={context?.user?.email} />
              <FieldRow label="Source mode" value={sourceMetadata.type} />
              <FieldRow label="Policy version" value={policyVersion} />
              <FieldRow label="Analysis engine" value={analysisEngine} />
              <FieldRow label="Request ID" value={requestId} />
              <FieldRow label="Source hash" value={contentHash} />
            </Flex>
          </Accordion>
          {history.length > 1 ? (
            <Accordion title={`Recent checks (${history.length})`} size="sm">
              <Flex direction="column" gap="sm">
                {history.slice(0, 6).map((item) => (
                  <Box key={item.request_id}>
                    <Flex align="center" justify="between" gap="sm" wrap>
                      <Text format={{fontWeight: "bold"}}>{formatTimestamp(item.checked_at || item.created_at) || "Stored check"}</Text>
                      <StatusTag variant={gateVariant(item.gate)}>{gateLabel(item.gate)}</StatusTag>
                    </Flex>
                    <Text>Score {item.score ?? "not available"} · {item.route || "No route"}</Text>
                  </Box>
                ))}
              </Flex>
            </Accordion>
          ) : null}
        </Box>
      ) : (
        <Box>
          <Text format={{fontWeight: "bold"}}>Check existing email copy before it is sent</Text>
          <Text>TextTraits returns a decision and reviewer guidance. It never rewrites the email.</Text>
        </Box>
      )}

      <Divider />
      <Accordion title={visible ? "Source and copy" : "Choose copy to check"} size="sm" defaultOpen={!visible}>
        <Flex direction="column" gap="sm">
          <Select
            label="Copy source"
            name="copy_source"
            value={sourceChoice}
            onChange={(value) => applySourceChoice(String(value))}
            options={sourceOptions}
          />
          {emailAssociations.isLoading ? <LoadingSpinner label="Loading associated emails" /> : null}
          {emailAssociations.error ? (
            <Alert variant="warning" title="Associated emails unavailable">
              Paste existing copy or enter a marketing email draft ID instead.
            </Alert>
          ) : null}
          {sourceChoice === "marketing-email" ? (
            <Input
              label="Marketing email ID"
              name="marketing_email_id"
              value={marketingEmailId}
              onInput={(value) => {
                setMarketingEmailId(value);
                setSourceMetadata({type: "Marketing email draft", id: value});
              }}
              placeholder="HubSpot marketing email ID"
            />
          ) : (
            <>
              <Input
                label="Subject"
                name="subject"
                value={subject}
                onInput={(value) => {
                  setSubject(value);
                  if (sourceChoice !== "manual") {
                    setSourceChoice("manual");
                    setSourceMetadata({type: "Manual paste"});
                  }
                }}
                placeholder="Existing subject"
              />
              <TextArea
                label="Body"
                name="body"
                value={body}
                onInput={(value) => {
                  setBody(value);
                  if (sourceChoice !== "manual") {
                    setSourceChoice("manual");
                    setSourceMetadata({type: "Manual paste"});
                  }
                }}
                placeholder="Existing email body"
                rows={6}
              />
            </>
          )}
          <Box>
            <Text format={{fontWeight: "bold"}}>Source details</Text>
            <Text>{sourceMetadata.type}{sourceMetadata.name ? ` · ${sourceMetadata.name}` : ""}</Text>
            {sourceMetadata.id ? <Text>ID: {sourceMetadata.id}</Text> : null}
            {sourceMetadata.owner ? <Text>Owner: {sourceMetadata.owner}</Text> : null}
            {sourceMetadata.modifiedAt ? <Text>Last changed: {formatTimestamp(sourceMetadata.modifiedAt)}</Text> : null}
            <Text>CRM record: {activeRecordLabel}</Text>
          </Box>
          {sourceIsStale ? (
            <Alert variant="warning" title="Copy changed after the last check">
              Run the check again before recording a decision.
            </Alert>
          ) : null}
          <Button variant="primary" onClick={checkEmail} disabled={submitting || !sourceReady}>
            {submitting ? "Checking..." : visible ? "Check again" : "Check email"}
          </Button>
          <Text>This check is read-only. It does not update CRM fields, create tasks, or change the email.</Text>
        </Flex>
      </Accordion>

      {visible ? (
        <>
          <Divider />
          {pendingDecision ? (
            <Alert variant="warning" title="Confirm HubSpot update">
              <Text>{pendingDecision.label} will update TextTraits review fields on this {singularObjectLabel(objectType)}. It will not alter the email copy.</Text>
              <Flex gap="sm" wrap>
                <Button variant="primary" onClick={recordDecision} disabled={submitting || sourceIsStale}>
                  {submitting ? "Recording..." : "Confirm and record"}
                </Button>
                <Button onClick={() => setPendingDecision(null)} disabled={submitting}>Cancel</Button>
              </Flex>
            </Alert>
          ) : (
            <Button
              onClick={() => setPendingDecision(actionForDecision)}
              disabled={submitting || sourceIsStale}
            >
              {actionForDecision.label}
            </Button>
          )}
        </>
      ) : null}
    </Box>
  );
}
