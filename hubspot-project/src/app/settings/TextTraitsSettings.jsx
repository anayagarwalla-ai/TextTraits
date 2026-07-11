import React, {useEffect, useState} from "react";
import {Accordion, Alert, Box, Button, Divider, Flex, Input, LoadingSpinner, Select, StatusTag, Text, hubspot} from "@hubspot/ui-extensions";
import {hubspotApi} from "../lib/api";
import {portalIdFromContext} from "../lib/context";

hubspot.extend(({context}) => <TextTraitsSettings context={context} />);

function listLabel(items) {
  return Array.isArray(items) && items.length ? items.join(", ") : "None";
}

function selectedPortalStatus(surface, portalId) {
  return (surface.portal_statuses || []).find((portal) => String(portal.portal_id || "") === String(portalId || "")) || null;
}

function ownerSummary(owner) {
  const teams = Array.isArray(owner.teams) ? owner.teams.map((team) => team.name).filter(Boolean).join(", ") : "";
  return `${owner.name || owner.email || owner.id} · ${owner.id}${teams ? ` · ${teams}` : ""}`;
}

function statusLabel(value) {
  if (value === "ready") return "Ready";
  if (value === "needs_setup") return "Needs setup";
  if (value === "not_configured") return "Not configured";
  if (value === "needs_token_storage") return "Needs token storage";
  if (value === "needs_connection") return "Needs connection";
  if (value === "needs_scopes") return "Needs scopes";
  return value || "Unknown";
}

function statusVariant(value) {
  if (value === "ready" || value === "connected") return "success";
  if (value === "needs_setup" || value === "needs_scopes" || value === "needs_token_storage") return "warning";
  if (value === "not_configured" || value === "needs_connection" || value === "disconnected") return "danger";
  return "default";
}

function TextTraitsSettings({context}) {
  const [state, setState] = useState({loading: true, surfaces: [], connections: [], tokenStorage: {}, setupStatus: null, setupWizard: [], approvalChains: [], error: ""});
  const [portalId, setPortalId] = useState(portalIdFromContext(context));
  const [appId, setAppId] = useState("");
  const [setup, setSetup] = useState({loading: "", message: "", error: ""});
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
        setState({loading: false, surfaces: [], connections: [], tokenStorage: {}, setupStatus: null, setupWizard: [], approvalChains: [], error: "HubSpot portal context is unavailable for this settings page."});
        return;
      }
      try {
        const {payload} = await hubspotApi("/v1/integrations/hubspot/settings/bootstrap", {
          method: "POST",
          body: {portal_id: portalId},
          timeout: 15000,
        });
        const nextConnections = payload.connections || [];
        if (!cancelled) {
          setState({
            loading: false,
            surfaces: payload.surfaces || [],
            connections: nextConnections,
            tokenStorage: payload.token_storage || {},
            setupStatus: payload.setup_status || null,
            setupWizard: payload.setup_steps || [],
            approvalChains: payload.approval_chains || [],
            error: "",
          });
        }
      } catch (error) {
        if (!cancelled) setState({loading: false, surfaces: [], connections: [], tokenStorage: {}, setupStatus: null, setupWizard: [], approvalChains: [], error: error.message || "TextTraits settings could not load for this portal."});
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
    setSetup({loading: action, message: "", error: ""});
    try {
      const {payload, status} = await hubspotApi(endpointByAction[action], {
        method: "POST",
        body: {
          portal_id: portalId,
          app_id: appId,
        },
        timeout: 30000,
        allowStatuses: [207],
        errorMessage: "Setup action failed.",
      });
      setSetup({loading: "", message: `${action} setup returned ${status}.`, error: ""});
      refreshSetupStatus(portalId);
    } catch (error) {
      setSetup({loading: "", message: "", error: error.message || "Setup action failed."});
    }
  }

  function applyRoutingConfig(config) {
    const routeMap = config?.route_owner_map || {};
    setRouting((current) => ({
      ...current,
      marketingOwnerId: routeMap["Marketing review"] || current.marketingOwnerId,
      complianceOwnerId: routeMap["Compliance review"] || current.complianceOwnerId,
      regionalOwnerId: routeMap["Regional owner review"] || current.regionalOwnerId,
      defaultOwnerId: config?.default_owner_id || current.defaultOwnerId,
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

  return (
    <Box>
      <Text format={{fontWeight: "bold"}}>TextTraits settings</Text>
      <Text>Review portal connection, granted scopes, enabled HubSpot surfaces, and readiness for writeback.</Text>
      <Divider />
      {state.loading ? <LoadingSpinner label="Loading TextTraits settings" /> : null}
      {state.error ? <Alert variant="warning" title="Settings could not load for this portal">{state.error}</Alert> : null}
      <Flex direction="column" gap="sm">
        <Text>Connected portals: {state.connections.length}</Text>
        <Text>Token storage: {state.tokenStorage?.ready ? "Encrypted storage ready" : "Needs encryption configuration"}</Text>
        {knownPortalIsMissing ? <Alert variant="warning" title="Portal is not connected">Install the TextTraits HubSpot app for this portal before running live setup.</Alert> : null}
        {knownPortalNeedsTokens ? <Alert variant="warning" title="Portal has no stored tokens">Reconnect with encrypted token storage enabled before running live HubSpot setup actions.</Alert> : null}
        {state.connections.map((connection) => (
          <Box key={connection.portal_id}>
            <Text format={{fontWeight: "bold"}}>{connection.account_name || connection.hub_domain || connection.portal_id}</Text>
            <Flex align="center" gap="sm" wrap>
              <StatusTag variant={statusVariant(connection.status)}>{statusLabel(connection.status)}</StatusTag>
              <Text>Portal {connection.portal_id}</Text>
            </Flex>
            <Text>Tokens: {connection.tokens_available ? "available" : "not stored"} · Scopes: {(connection.scopes || []).length}</Text>
            <Text>Granted scopes: {listLabel(connection.scopes)}</Text>
            <Text>Updated: {connection.updated_at || "not recorded"}</Text>
          </Box>
        ))}
      </Flex>
      <Divider />
      <Text format={{fontWeight: "bold"}}>Setup status</Text>
      <Text>Campaign sync, workflow action, webhook, approval, and reporting readiness for the selected HubSpot portal.</Text>
      <Text>Status groups: Campaign sync, Workflow actions, Webhook re-scoring, Approval workflow, Reporting writeback.</Text>
      <Button onClick={() => refreshSetupStatus()} disabled={setup.loading}>
        {setup.loading === "status" ? "Refreshing status..." : "Refresh setup status"}
      </Button>
      {setupStatus.last_sync_at ? <Text>Last sync activity: {setupStatus.last_sync_at}</Text> : <Text>Last sync activity: not recorded yet</Text>}
      <Flex direction="column" gap="xs">
        {(setupStatus.groups || []).map((group) => (
          <Box key={group.label}>
            <Flex align="center" gap="sm" wrap>
              <Text format={{fontWeight: "bold"}}>{group.label}</Text>
              <StatusTag variant={statusVariant(group.status)}>{statusLabel(group.status)}</StatusTag>
            </Flex>
            <Text>Ready surfaces: {group.ready_count || 0} of {group.total || 0}</Text>
            {group.missing_required_scopes?.length ? <Text>Missing required scopes: {group.missing_required_scopes.join(", ")}</Text> : null}
            {group.last_sync_at ? <Text>Last sync: {group.last_sync_at}</Text> : null}
          </Box>
        ))}
      </Flex>
      <Text format={{fontWeight: "bold"}}>Admin attention</Text>
      {attentionItems.length ? (
        <Flex direction="column" gap="xs">
          {attentionItems.slice(0, 8).map((item, index) => (
            <Alert key={`${item.area}-${index}`} variant="warning" title={item.area || "Setup item"}>
              {item.message}
            </Alert>
          ))}
        </Flex>
      ) : (
        <Alert variant="success" title="No setup blockers">No admin attention items are currently reported for this portal.</Alert>
      )}
      <Divider />
      <Accordion title="Guided setup checklist" size="md">
        <Flex direction="column" gap="xs">
          {state.setupWizard.map((step) => (
            <Box key={step.id}>
              <Text format={{fontWeight: "bold"}}>{step.label}</Text>
              <Text>{step.action}</Text>
            </Box>
          ))}
        </Flex>
      </Accordion>
      <Accordion title="Approval chain templates" size="md">
        <Flex direction="column" gap="xs">
          {state.approvalChains.map((chain) => (
            <Box key={chain.id}>
              <Text format={{fontWeight: "bold"}}>{chain.name}</Text>
              <Text>Steps: {(chain.steps || []).join(" → ")}</Text>
              <Text>Blocked routes: {(chain.blocked_routes || []).join(", ")}</Text>
            </Box>
          ))}
        </Flex>
      </Accordion>
      <Accordion title={`Integration surfaces (${state.surfaces.length})`} size="md">
        <Flex direction="column" gap="xs">
          {state.surfaces.map((surface) => {
            const portalStatus = selectedPortalStatus(surface, portalId);
            const readiness = portalStatus?.ready ? "ready" : portalStatus ? "needs_setup" : surface.status;
            return (
              <Box key={surface.id}>
                <Flex align="center" gap="sm" wrap>
                  <Text format={{fontWeight: "bold"}}>{surface.label}</Text>
                  <StatusTag variant={statusVariant(readiness)}>{portalStatus?.ready ? "Ready" : surface.readiness_label || surface.status_label || statusLabel(surface.status)}</StatusTag>
                </Flex>
                <Text>{surface.hubspot_area}</Text>
                <Text>Required scopes: {listLabel(surface.required_scopes)}</Text>
                {portalStatus?.missing_required_scopes?.length ? <Text>Missing: {portalStatus.missing_required_scopes.join(", ")}</Text> : null}
              </Box>
            );
          })}
        </Flex>
      </Accordion>
      <Divider />
      <Text format={{fontWeight: "bold"}}>Provision HubSpot setup</Text>
      <Text>Create the HubSpot fields, analysis schema, and webhook configuration TextTraits needs for native reporting and re-scoring.</Text>
      <Flex direction="column" gap="sm">
        {state.connections.length ? (
          <Select
            label="HubSpot portal"
            name="portal_id"
            value={portalId}
            onChange={(value) => setPortalId(String(value))}
            options={state.connections.map((connection) => ({label: connection.account_name || connection.hub_domain || connection.portal_id, value: String(connection.portal_id)}))}
          />
        ) : (
          <Input label="Portal ID" name="portal_id" value={portalId} onInput={setPortalId} placeholder="HubSpot portal ID" />
        )}
        <Input label="App ID" name="app_id" value={appId} onInput={setAppId} placeholder="HubSpot app ID for webhook setup" />
        <Button onClick={() => runSetup("properties")} disabled={setupDisabled}>
          {setup.loading === "properties" ? "Creating fields..." : "Create TextTraits CRM fields"}
        </Button>
        <Button onClick={() => runSetup("schema")} disabled={setupDisabled}>
          {setup.loading === "schema" ? "Creating schema..." : "Create analysis object schema"}
        </Button>
        <Button onClick={() => runSetup("segments")} disabled={setupDisabled}>
          {setup.loading === "segments" ? "Creating segments..." : "Create review segments"}
        </Button>
        <Button onClick={() => runSetup("webhooks")} disabled={setupDisabled || !appId}>
          {setup.loading === "webhooks" ? "Configuring webhooks..." : "Configure webhooks"}
        </Button>
      </Flex>
      {setup.message ? <Alert variant="success" title="Setup request complete">{setup.message}</Alert> : null}
      {setup.error ? <Alert variant="error" title="Setup request failed">{setup.error}</Alert> : null}
      <Divider />
      <Text format={{fontWeight: "bold"}}>Review routing owners</Text>
      <Text>Map TextTraits review routes to real HubSpot owner IDs for review task assignment.</Text>
      <Flex direction="column" gap="sm">
        <Button onClick={loadOwners} disabled={setupDisabled}>
          {routing.loading === "owners" ? "Loading owners..." : "Load HubSpot owners"}
        </Button>
        {routing.owners.slice(0, 8).map((owner) => (
          <Text key={owner.id}>{ownerSummary(owner)}</Text>
        ))}
        <Input label="Marketing review owner ID" name="marketing_owner_id" value={routing.marketingOwnerId} onInput={(value) => setRouting((current) => ({...current, marketingOwnerId: value}))} placeholder="HubSpot owner ID" />
        <Input label="Compliance review owner ID" name="compliance_owner_id" value={routing.complianceOwnerId} onInput={(value) => setRouting((current) => ({...current, complianceOwnerId: value}))} placeholder="HubSpot owner ID" />
        <Input label="Regional owner review ID" name="regional_owner_id" value={routing.regionalOwnerId} onInput={(value) => setRouting((current) => ({...current, regionalOwnerId: value}))} placeholder="HubSpot owner ID" />
        <Input label="Default review owner ID" name="default_owner_id" value={routing.defaultOwnerId} onInput={(value) => setRouting((current) => ({...current, defaultOwnerId: value}))} placeholder="Fallback HubSpot owner ID" />
        <Button onClick={saveRouting} disabled={setupDisabled || routing.loading}>
          {routing.loading === "save" ? "Saving routing..." : "Save review routing"}
        </Button>
        {routing.updatedAt ? <Text>Last routing update: {routing.updatedAt}</Text> : null}
      </Flex>
      {routing.message ? <Alert variant="success" title="Review routing">{routing.message}</Alert> : null}
      {routing.error ? <Alert variant="error" title="Review routing failed">{routing.error}</Alert> : null}
    </Box>
  );
}
