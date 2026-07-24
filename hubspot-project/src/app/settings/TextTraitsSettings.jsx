import React, {useEffect, useMemo, useState} from "react";
import {Accordion, Alert, Box, Button, Divider, Flex, Input, LoadingSpinner, Select, StatusTag, Text, hubspot} from "@hubspot/ui-extensions";
import {hubspotApi} from "../lib/api";
import {portalIdFromContext} from "../lib/context";

hubspot.extend(({context}) => <TextTraitsSettings context={context} />);

const CUSTOMER_FACING_SURFACES = new Set([
  "crm_card",
  "workflow_action",
  "campaign_workflow_action",
  "asset_copy_workflow_action",
  "marketing_email_pre_publish_guardrail",
  "live_asset_copy_review",
  "campaign_picker",
  "marketing_email_picker",
  "owner_directory",
  "approval_workflow_sync",
]);

function listLabel(items) {
  return Array.isArray(items) && items.length ? items.join(", ") : "None";
}

function selectedPortalStatus(surface, portalId) {
  return (surface.portal_statuses || []).find((portal) => String(portal.portal_id || "") === String(portalId || "")) || null;
}

function ownerLabel(owner) {
  const teams = Array.isArray(owner.teams) ? owner.teams.map((team) => team.name).filter(Boolean).join(", ") : "";
  return `${owner.name || owner.email || owner.id}${teams ? ` · ${teams}` : ""}`;
}

function statusLabel(value) {
  if (value === "ready" || value === "connected") return "Ready";
  if (value === "needs_setup") return "Needs setup";
  if (value === "not_configured") return "Not configured";
  if (value === "needs_token_storage") return "Needs secure token storage";
  if (value === "needs_connection") return "Needs connection";
  if (value === "needs_scopes") return "Needs permissions";
  return value || "Unknown";
}

function statusVariant(value) {
  if (value === "ready" || value === "connected") return "success";
  if (value === "needs_setup" || value === "needs_scopes" || value === "needs_token_storage") return "warning";
  if (value === "not_configured" || value === "needs_connection" || value === "disconnected") return "danger";
  return "default";
}

function TextTraitsSettings({context}) {
  const [state, setState] = useState({
    loading: true,
    surfaces: [],
    connections: [],
    tokenStorage: {},
    setupStatus: null,
    setupWizard: [],
    approvalChains: [],
    error: "",
  });
  const [portalId, setPortalId] = useState(portalIdFromContext(context));
  const [appId, setAppId] = useState("");
  const [setup, setSetup] = useState({loading: "", message: "", error: "", pending: ""});
  const [routing, setRouting] = useState({
    loading: "",
    message: "",
    error: "",
    owners: [],
    marketingOwnerId: "",
    complianceOwnerId: "",
    regionalOwnerId: "",
    defaultOwnerId: "",
    updatedAt: "",
  });

  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!portalId) {
        setState((current) => ({...current, loading: false, error: "HubSpot portal context is unavailable for this settings page."}));
        return;
      }
      try {
        const {payload} = await hubspotApi("/v1/integrations/hubspot/settings/bootstrap", {
          method: "POST",
          body: {portal_id: portalId},
          timeout: 15000,
        });
        if (!cancelled) {
          setState({
            loading: false,
            surfaces: payload.surfaces || [],
            connections: payload.connections || [],
            tokenStorage: payload.token_storage || {},
            setupStatus: payload.setup_status || null,
            setupWizard: payload.setup_steps || [],
            approvalChains: payload.approval_chains || [],
            error: "",
          });
        }
      } catch (error) {
        if (!cancelled) {
          setState((current) => ({
            ...current,
            loading: false,
            error: error.message || "TextTraits settings could not load for this portal.",
          }));
        }
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [portalId]);

  const selectedConnection = state.connections.find((connection) => String(connection.portal_id || "") === String(portalId || ""));
  const knownPortalIsMissing = Boolean(portalId && state.connections.length && !selectedConnection);
  const knownPortalNeedsTokens = Boolean(selectedConnection && !selectedConnection.tokens_available);
  const setupDisabled = Boolean(!portalId || setup.loading || knownPortalIsMissing || knownPortalNeedsTokens);
  const setupStatus = state.setupStatus || {};
  const attentionItems = setupStatus.admin_attention || [];
  const ownerOptions = useMemo(
    () => [
      {label: "Unassigned", value: ""},
      ...routing.owners.map((owner) => ({label: ownerLabel(owner), value: String(owner.id)})),
    ],
    [routing.owners],
  );
  const visibleSurfaces = useMemo(
    () => state.surfaces.filter((surface) => CUSTOMER_FACING_SURFACES.has(surface.id)),
    [state.surfaces],
  );

  async function refreshSetupStatus(nextPortalId = portalId) {
    setSetup((current) => ({...current, loading: current.loading || "status", message: "", error: ""}));
    try {
      const {payload} = await hubspotApi("/v1/integrations/hubspot/settings/bootstrap", {
        method: "POST",
        body: {portal_id: nextPortalId},
        timeout: 15000,
        errorMessage: "Setup status refresh failed.",
      });
      setState((current) => ({...current, setupStatus: payload.setup_status || null}));
      setSetup((current) => ({...current, loading: "", message: "Setup status refreshed.", error: ""}));
    } catch (error) {
      setSetup((current) => ({...current, loading: "", message: "", error: error.message || "Setup status refresh failed."}));
    }
  }

  async function runSetup(action) {
    const endpointByAction = {
      properties: "/v1/integrations/hubspot/properties/provision",
      schema: "/v1/integrations/hubspot/analysis-schema/provision",
      segments: "/v1/integrations/hubspot/lists/create-review-segments",
      webhooks: "/v1/integrations/hubspot/webhooks/configure",
    };
    setSetup({loading: action, message: "", error: "", pending: ""});
    try {
      const {status} = await hubspotApi(endpointByAction[action], {
        method: "POST",
        body: {portal_id: portalId, app_id: appId},
        timeout: 30000,
        allowStatuses: [207],
        errorMessage: "Setup action failed.",
      });
      setSetup({loading: "", message: `${action} setup returned ${status}.`, error: "", pending: ""});
      refreshSetupStatus(portalId);
    } catch (error) {
      setSetup({loading: "", message: "", error: error.message || "Setup action failed.", pending: ""});
    }
  }

  function applyRoutingConfig(config) {
    const routeMap = config?.route_owner_map || {};
    setRouting((current) => ({
      ...current,
      marketingOwnerId: routeMap["Marketing review"] || "",
      complianceOwnerId: routeMap["Compliance review"] || "",
      regionalOwnerId: routeMap["Regional owner review"] || "",
      defaultOwnerId: config?.default_owner_id || "",
      updatedAt: config?.updated_at || current.updatedAt,
    }));
  }

  async function loadOwners() {
    setRouting((current) => ({...current, loading: "owners", message: "", error: ""}));
    try {
      const {payload} = await hubspotApi("/v1/integrations/hubspot/owners/list", {
        method: "POST",
        body: {portal_id: portalId, limit: 100},
        timeout: 30000,
        errorMessage: "Owner lookup failed.",
      });
      applyRoutingConfig(payload.routing);
      setRouting((current) => ({
        ...current,
        loading: "",
        owners: payload.owners || [],
        message: `Loaded ${(payload.owners || []).length} HubSpot owners.`,
        error: "",
      }));
    } catch (error) {
      setRouting((current) => ({...current, loading: "", message: "", error: error.message || "Owner lookup failed."}));
    }
  }

  async function saveRouting() {
    setRouting((current) => ({...current, loading: "save", message: "", error: ""}));
    try {
      const {payload} = await hubspotApi("/v1/integrations/hubspot/review-routing/config", {
        method: "POST",
        body: {
          portal_id: portalId,
          route_owner_map: {
            "Marketing review": routing.marketingOwnerId,
            "Compliance review": routing.complianceOwnerId,
            "Regional owner review": routing.regionalOwnerId,
          },
          default_owner_id: routing.defaultOwnerId,
          action: "save",
        },
        timeout: 30000,
        errorMessage: "Review routing save failed.",
      });
      applyRoutingConfig(payload.routing);
      setRouting((current) => ({...current, loading: "", message: "Review routing saved.", error: ""}));
    } catch (error) {
      setRouting((current) => ({...current, loading: "", message: "", error: error.message || "Review routing save failed."}));
    }
  }

  function requestSetupConfirmation(action) {
    setSetup((current) => ({...current, pending: action, message: "", error: ""}));
  }

  return (
    <Box>
      <Text format={{fontWeight: "bold"}}>TextTraits administration</Text>
      <Text>Connect the portal, choose the minimum permissions each feature needs, and define who reviews exceptions.</Text>
      <Divider />

      {state.loading ? <LoadingSpinner label="Loading TextTraits settings" /> : null}
      {state.error ? <Alert variant="warning" title="Settings unavailable">{state.error}</Alert> : null}

      <Accordion title="Connection and permissions" size="md" defaultOpen>
        <Alert variant="info" title="Read-only by default">
          Copy checks do not update CRM records. Write permissions are used only after an admin enables setup or a reviewer explicitly confirms a decision.
        </Alert>
        {state.connections.length > 1 ? (
          <Select
            label="HubSpot portal"
            name="portal_id"
            value={portalId}
            onChange={(value) => setPortalId(String(value))}
            options={state.connections.map((connection) => ({
              label: connection.account_name || connection.hub_domain || connection.portal_id,
              value: String(connection.portal_id),
            }))}
          />
        ) : null}
        {selectedConnection ? (
          <Box>
            <Flex align="center" gap="sm" wrap>
              <Text format={{fontWeight: "bold"}}>{selectedConnection.account_name || selectedConnection.hub_domain || selectedConnection.portal_id}</Text>
              <StatusTag variant={statusVariant(selectedConnection.status)}>{statusLabel(selectedConnection.status)}</StatusTag>
            </Flex>
            <Text>Secure tokens: {selectedConnection.tokens_available ? "Available" : "Not stored"}</Text>
            <Text>Granted permissions: {listLabel(selectedConnection.scopes)}</Text>
            <Text>Connection updated: {selectedConnection.updated_at || "Not recorded"}</Text>
          </Box>
        ) : null}
        <Text>Token storage: {state.tokenStorage?.ready ? "Encrypted storage ready" : "Encryption setup required"}</Text>
        {knownPortalIsMissing ? <Alert variant="warning" title="Portal not connected">Install or reconnect TextTraits for this portal.</Alert> : null}
        {knownPortalNeedsTokens ? <Alert variant="warning" title="Tokens unavailable">Reconnect after encrypted token storage is configured.</Alert> : null}
      </Accordion>

      <Accordion title="Policies and approval paths" size="md">
        <Text>These paths route findings only. TextTraits does not provide replacement copy.</Text>
        <Flex direction="column" gap="sm">
          {state.approvalChains.map((chain) => (
            <Box key={chain.id}>
              <Text format={{fontWeight: "bold"}}>{chain.name}</Text>
              <Text>{(chain.steps || []).join(" → ")}</Text>
              <Text>Used for: {(chain.blocked_routes || []).join(", ") || "Configured routes"}</Text>
            </Box>
          ))}
        </Flex>
        <Accordion title="Setup checklist" size="sm">
          {state.setupWizard.map((step) => (
            <Box key={step.id}>
              <Text format={{fontWeight: "bold"}}>{step.label}</Text>
              <Text>{step.action}</Text>
            </Box>
          ))}
        </Accordion>
      </Accordion>

      <Accordion title="Review owners" size="md">
        <Text>Assign real HubSpot owners to each exception route.</Text>
        <Button onClick={loadOwners} disabled={setupDisabled || routing.loading}>
          {routing.loading === "owners" ? "Loading owners..." : routing.owners.length ? "Refresh owners" : "Load HubSpot owners"}
        </Button>
        {routing.owners.length ? (
          <Flex direction="column" gap="sm">
            <Select label="Marketing review" name="marketing_owner_id" value={routing.marketingOwnerId} options={ownerOptions} onChange={(value) => setRouting((current) => ({...current, marketingOwnerId: String(value)}))} />
            <Select label="Compliance review" name="compliance_owner_id" value={routing.complianceOwnerId} options={ownerOptions} onChange={(value) => setRouting((current) => ({...current, complianceOwnerId: String(value)}))} />
            <Select label="Regional review" name="regional_owner_id" value={routing.regionalOwnerId} options={ownerOptions} onChange={(value) => setRouting((current) => ({...current, regionalOwnerId: String(value)}))} />
            <Select label="Fallback reviewer" name="default_owner_id" value={routing.defaultOwnerId} options={ownerOptions} onChange={(value) => setRouting((current) => ({...current, defaultOwnerId: String(value)}))} />
            <Button variant="primary" onClick={saveRouting} disabled={setupDisabled || routing.loading}>
              {routing.loading === "save" ? "Saving..." : "Save review owners"}
            </Button>
          </Flex>
        ) : (
          <Text>Load owners to choose people by name instead of entering IDs.</Text>
        )}
        {routing.updatedAt ? <Text>Last updated: {routing.updatedAt}</Text> : null}
        {routing.message ? <Alert variant="success" title="Review routing">{routing.message}</Alert> : null}
        {routing.error ? <Alert variant="error" title="Review routing failed">{routing.error}</Alert> : null}
      </Accordion>

      <Accordion title="Workflow readiness" size="md">
        <Button onClick={() => refreshSetupStatus()} disabled={setup.loading}>
          {setup.loading === "status" ? "Refreshing..." : "Refresh readiness"}
        </Button>
        <Flex direction="column" gap="sm">
          {(setupStatus.groups || []).map((group) => (
            <Box key={group.label}>
              <Flex align="center" gap="sm" wrap>
                <Text format={{fontWeight: "bold"}}>{group.label}</Text>
                <StatusTag variant={statusVariant(group.status)}>{statusLabel(group.status)}</StatusTag>
              </Flex>
              <Text>Ready: {group.ready_count || 0} of {group.total || 0}</Text>
              {group.missing_required_scopes?.length ? <Text>Permissions needed: {group.missing_required_scopes.join(", ")}</Text> : null}
              {group.last_sync_at ? <Text>Last activity: {group.last_sync_at}</Text> : null}
            </Box>
          ))}
        </Flex>
        {attentionItems.length ? (
          <Flex direction="column" gap="xs">
            {attentionItems.slice(0, 8).map((item, index) => (
              <Alert key={`${item.area}-${index}`} variant="warning" title={item.area || "Setup item"}>{item.message}</Alert>
            ))}
          </Flex>
        ) : (
          <Alert variant="success" title="No reported setup blockers">Configured features are ready for this portal.</Alert>
        )}
      </Accordion>

      <Accordion title="CRM fields and automation setup" size="md">
        <Alert variant="warning" title="Admin action">
          The actions below create fields, a custom analysis schema, review segments, or webhooks in this HubSpot portal. TextTraits will ask for confirmation before each change.
        </Alert>
        <Flex direction="column" gap="sm">
          <Button onClick={() => requestSetupConfirmation("properties")} disabled={setupDisabled}>Create TextTraits CRM fields</Button>
          <Button onClick={() => requestSetupConfirmation("schema")} disabled={setupDisabled}>Create analysis object schema</Button>
          <Button onClick={() => requestSetupConfirmation("segments")} disabled={setupDisabled}>Create review segments</Button>
          <Input label="HubSpot app ID" name="app_id" value={appId} onInput={setAppId} placeholder="Required only for webhook setup" />
          <Button onClick={() => requestSetupConfirmation("webhooks")} disabled={setupDisabled || !appId}>Configure webhooks</Button>
        </Flex>
        {setup.pending ? (
          <Alert variant="warning" title="Confirm portal change">
            <Text>Run {setup.pending} setup in portal {portalId}? This changes HubSpot configuration.</Text>
            <Flex gap="sm" wrap>
              <Button variant="primary" onClick={() => runSetup(setup.pending)} disabled={setup.loading}>Confirm setup</Button>
              <Button onClick={() => setSetup((current) => ({...current, pending: ""}))} disabled={setup.loading}>Cancel</Button>
            </Flex>
          </Alert>
        ) : null}
        {setup.message ? <Alert variant="success" title="Setup complete">{setup.message}</Alert> : null}
        {setup.error ? <Alert variant="error" title="Setup failed">{setup.error}</Alert> : null}
      </Accordion>

      <Accordion title={`Feature permissions (${visibleSurfaces.length})`} size="md">
        <Text>Enable only the surfaces your team plans to use.</Text>
        <Flex direction="column" gap="sm">
          {visibleSurfaces.map((surface) => {
            const portalStatus = selectedPortalStatus(surface, portalId);
            const readiness = portalStatus?.ready ? "ready" : portalStatus ? "needs_setup" : surface.status;
            return (
              <Box key={surface.id}>
                <Flex align="center" gap="sm" wrap>
                  <Text format={{fontWeight: "bold"}}>{surface.label}</Text>
                  <StatusTag variant={statusVariant(readiness)}>{portalStatus?.ready ? "Ready" : surface.readiness_label || statusLabel(surface.status)}</StatusTag>
                </Flex>
                <Text>{surface.hubspot_area}</Text>
                <Text>Required permissions: {listLabel(surface.required_scopes)}</Text>
                {portalStatus?.missing_required_scopes?.length ? <Text>Missing: {portalStatus.missing_required_scopes.join(", ")}</Text> : null}
              </Box>
            );
          })}
        </Flex>
      </Accordion>

      <Accordion title="Data controls" size="md">
        <Text>TextTraits stores structured checks, source hashes, review decisions, and outcomes for audit. It does not store a separate raw-email-body field in the analysis table.</Text>
        <Text>Retention preview, audit export, and deletion require a verified TextTraits enterprise administrator in the web app.</Text>
        <Text>Confirm your company retention period and legal basis before a production rollout.</Text>
      </Accordion>
    </Box>
  );
}
