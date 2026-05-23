(function () {
  function loadingCard(mode) {
    const title = mode === "enterprise-optimizer" ? "Scoring the existing email..." : "Reading your writing...";
    const copy = mode === "enterprise-optimizer" ? "Send-readiness checks and local model signals are being prepared." : "TextTraits is preparing the objective readout.";
    return `
      <div class="loading-card fade-in" role="status" aria-live="polite" tabindex="-1">
        <span class="status-pill">Working</span>
        <h2>${title}</h2>
        <p class="muted">${copy}</p>
        <div class="skeleton-stack" aria-hidden="true">
          <span></span>
          <span></span>
          <span></span>
        </div>
      </div>
    `;
  }

  function errorCard(message) {
    return `
      <div class="empty-hero error-card" role="alert">
        <span class="status-pill">Needs retry</span>
        <h2>The analysis did not run.</h2>
        <p class="muted">${message}</p>
        <button class="button-secondary" id="retry-run" type="button">Retry</button>
      </div>
    `;
  }

  function focusWithin(root, selector) {
    requestAnimationFrame(() => {
      const target = root?.querySelector?.(selector) || root;
      target?.focus?.();
    });
  }

  function announce(element, message) {
    if (element) element.textContent = message;
  }

  function workflowLabels() {
    return ["Paste", "Score", "Review", "Export"];
  }

  window.TextTraitsUi = {
    loadingCard,
    errorCard,
    focusWithin,
    announce,
    workflowLabels,
  };
})();
