(function () {
  let csrfToken = window.TEXTTRAITS_CONFIG?.csrfToken || "";
  const unsafeMethods = new Set(["POST", "PUT", "PATCH", "DELETE"]);

  async function refreshCsrf() {
    const response = await fetch("/api/session", {
      headers: {"Accept": "application/json"},
      credentials: "same-origin",
    });
    const data = await response.json().catch(() => ({}));
    csrfToken = data.csrf_token || csrfToken;
    if (window.TEXTTRAITS_CONFIG) window.TEXTTRAITS_CONFIG.csrfToken = csrfToken;
    return data;
  }

  async function request(path, options = {}, retry = true) {
    const method = (options.method || "GET").toUpperCase();
    if (unsafeMethods.has(method) && !csrfToken) await refreshCsrf();
    const response = await fetch(path, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(unsafeMethods.has(method) && csrfToken ? {"X-CSRF-Token": csrfToken} : {}),
        ...(options.headers || {}),
      },
      credentials: "same-origin",
    });
    const data = await response.json().catch(() => ({}));
    if (response.status === 419 && retry) {
      csrfToken = "";
      await refreshCsrf();
      return request(path, options, false);
    }
    if (!response.ok) {
      const error = new Error(data.error || "Request failed");
      error.status = response.status;
      error.payload = data;
      throw error;
    }
    return data;
  }

  function query(params = {}) {
    const pairs = Object.entries(params).filter(([, value]) => value !== undefined && value !== null && value !== "");
    if (!pairs.length) return "";
    return `?${new URLSearchParams(Object.fromEntries(pairs)).toString()}`;
  }

  window.TextTraitsApi = {
    request,
    session: () => refreshCsrf(),
    csrfToken: () => csrfToken,
    evaluate: (payload) => request("/evaluate", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
    analyzeEmail: (payload) => request("/v1/email/analyze", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
    openApiContract: () => request("/v1/openapi.json"),
    installKit: () => request("/v1/install-kit"),
    enterpriseIntegrationPlan: () => request("/api/enterprise/integration-plan"),
    integrationFlows: () => request("/v1/integrations/sandbox-flows"),
    integrationManifests: () => request("/v1/integrations/manifests"),
    providerManifest: (provider) => request(`/v1/integrations/${encodeURIComponent(provider)}/manifest`),
    fieldMappings: () => request("/v1/integrations/field-mappings"),
    validateFieldMapping: (provider, mapping) => request(`/v1/integrations/${encodeURIComponent(provider)}/field-mapping/validate`, {
      method: "POST",
      body: JSON.stringify({mapping}),
    }),
    saveFieldMapping: (provider, mapping, options = {}) => request(`/v1/integrations/${encodeURIComponent(provider)}/field-mapping`, {
      method: "POST",
      body: JSON.stringify({...options, mapping}),
    }),
    governanceDashboard: (workspace_id = "") => request(`/v1/governance/dashboard${query({workspace_id})}`),
    governanceExport: (kind = "analyses", format = "json", workspace_id = "") => request(`/v1/governance/export${query({type: kind, format, workspace_id})}`),
    governancePolicy: (workspace_id = "") => request(`/v1/governance/policy${query({workspace_id})}`),
    saveGovernancePolicy: (policy, options = {}) => request("/v1/governance/policy", {
      method: "PUT",
      body: JSON.stringify({...options, policy}),
    }),
    importSamples: (samples, options = {}) => request("/v1/samples/import", {
      method: "POST",
      body: JSON.stringify({...options, samples}),
    }),
    simulateAdapter: (provider, payload) => request("/v1/integrations/simulate", {
      method: "POST",
      body: JSON.stringify({provider, payload}),
    }),
    renderTemplateTest: (payload) => request("/v1/templates/render-test", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
    workspace: () => request("/api/workspace"),
    saveWorkspace: (name, data) => request("/api/workspace", {
      method: "PUT",
      body: JSON.stringify({name, data}),
    }),
    signup: (payload) => request("/api/signup", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
    login: (payload) => request("/api/login", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
    googleLogin: (credential) => request("/api/auth/google", {
      method: "POST",
      body: JSON.stringify({credential}),
    }),
    logout: () => request("/api/logout", {method: "POST"}),
    requestPasswordReset: (email) => request("/api/request-password-reset", {
      method: "POST",
      body: JSON.stringify({email}),
    }),
    resetPassword: (token, password) => request("/api/reset-password", {
      method: "POST",
      body: JSON.stringify({token, password}),
    }),
    verifyEmail: (token, email) => request("/api/verify-email", {
      method: "POST",
      body: JSON.stringify({token, email}),
    }),
    exportAccount: (password) => request("/api/account/export", {
      method: "POST",
      body: JSON.stringify({password}),
    }),
    deleteAccount: (password) => request("/api/account", {
      method: "DELETE",
      body: JSON.stringify({password}),
    }),
    event: (event_type, payload = {}) => request("/api/events", {
      method: "POST",
      body: JSON.stringify({event_type, payload}),
    }),
    clientError: (payload = {}) => request("/api/client-errors", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
    integrations: () => request("/api/integrations"),
    integrationProviders: () => request("/api/integration-providers"),
    startIntegrationOAuth: (provider) => request(`/api/integrations/${encodeURIComponent(provider)}/oauth/start`, {method: "POST"}),
    saveIntegration: (provider, status, config = {}) => request("/api/integrations", {
      method: "POST",
      body: JSON.stringify({provider, status, config}),
    }),
  };
})();
