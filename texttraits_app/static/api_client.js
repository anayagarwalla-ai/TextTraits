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

  window.TextTraitsApi = {
    request,
    session: () => refreshCsrf(),
    csrfToken: () => csrfToken,
    evaluate: (payload) => request("/evaluate", {
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
    enterpriseIntegrationPlan: () => request("/api/enterprise/integration-plan"),
    startIntegrationOAuth: (provider) => request(`/api/integrations/${encodeURIComponent(provider)}/oauth/start`, {method: "POST"}),
    saveIntegration: (provider, status, config = {}) => request("/api/integrations", {
      method: "POST",
      body: JSON.stringify({provider, status, config}),
    }),
  };
})();
