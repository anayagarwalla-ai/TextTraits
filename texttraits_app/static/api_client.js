(function () {
  async function request(path, options = {}) {
    const response = await fetch(path, {
      headers: {"Content-Type": "application/json", ...(options.headers || {})},
      ...options,
    });
    const data = await response.json().catch(() => ({}));
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
    session: () => request("/api/session"),
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
    logout: () => request("/api/logout", {method: "POST"}),
    requestPasswordReset: (email) => request("/api/request-password-reset", {
      method: "POST",
      body: JSON.stringify({email}),
    }),
    resetPassword: (token, password) => request("/api/reset-password", {
      method: "POST",
      body: JSON.stringify({token, password}),
    }),
    verifyEmail: (token) => request("/api/verify-email", {
      method: "POST",
      body: JSON.stringify({token}),
    }),
    exportAccount: () => request("/api/account/export"),
    deleteAccount: () => request("/api/account", {method: "DELETE"}),
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
    startIntegrationOAuth: (provider) => request(`/api/integrations/${encodeURIComponent(provider)}/oauth/start`),
    saveIntegration: (provider, status, config = {}) => request("/api/integrations", {
      method: "POST",
      body: JSON.stringify({provider, status, config}),
    }),
  };
})();
