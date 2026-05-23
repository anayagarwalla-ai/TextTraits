(function () {
  const utils = window.TextTraitsUtils || {};
  const apiClient = window.TextTraitsApi || {};
  const config = window.TEXTTRAITS_CONFIG || {};

  const escapeHtml = utils.escapeHtml || ((value) => String(value ?? ""));
  const localStats = utils.localStats || ((text) => ({
    words: String(text || "").trim().split(/\s+/).filter(Boolean).length,
    characters: String(text || "").length,
    sentences: 1,
    punctuation_density: 0,
    reading_level: "Unavailable",
  }));

  const els = {
    announcer: document.querySelector("#announcer"),
    inputPanel: document.querySelector("#input-panel"),
    outputPanel: document.querySelector("#output-panel"),
    toastStack: document.querySelector("#toast-stack"),
  };

  const state = {
    text: "",
    latestData: null,
    latestError: "",
    busy: false,
  };

  const samples = [
    {
      label: "Short note",
      text: "I think the plan is clear because the next step is to email Jordan today with the final numbers and ask for approval by Friday.",
    },
    {
      label: "Reflective paragraph",
      text: "I keep returning to the same question after each planning session: what are people telling us indirectly through the way they describe a problem? The clearest notes are rarely dramatic. They are careful, specific, and honest about uncertainty, which makes them useful without pretending to settle everything.",
    },
  ];

  const primaryTargets = [
    {key: "mbti", title: "16-class style target"},
    {key: "gender", title: "Language-association target"},
    {key: "age_bucket", title: "Age-bucket target"},
    {key: "age_estimate", title: "Age-estimate target"},
  ];

  const dimensionTargets = [
    {key: "energy", title: "Energy dimension", labels: ["introverted", "extraverted"]},
    {key: "information", title: "Information dimension", labels: ["sensing", "intuitive"]},
    {key: "decisions", title: "Decision dimension", labels: ["thinking", "feeling"]},
    {key: "structure", title: "Structure dimension", labels: ["judging", "perceiving"]},
  ];

  function announce(message) {
    if (els.announcer) els.announcer.textContent = message;
  }

  function trackEvent(event_type, payload = {}) {
    apiClient.event?.(event_type, payload).catch(() => {});
  }

  function percent(value) {
    const number = Number(value || 0);
    return `${Math.round(number * 100)}%`;
  }

  function numberLabel(value, digits = 3) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "n/a";
    return number.toFixed(digits);
  }

  function titleCase(value) {
    return String(value || "")
      .replace(/[-_]/g, " ")
      .replace(/\w\S*/g, (word) => word[0].toUpperCase() + word.slice(1).toLowerCase());
  }

  function predictionLabel(prediction) {
    const raw = String(prediction?.label || "Unavailable").replace(/^source label:\s*/i, "");
    if (/^[a-z]{4}$/.test(raw)) return raw.toUpperCase();
    if (/\d/.test(raw)) return raw;
    return titleCase(raw);
  }

  function confidence(prediction) {
    return Number(prediction?.confidence || 0);
  }

  function margin(prediction) {
    return Number(prediction?.margin || 0);
  }

  function confidenceBand(prediction) {
    const value = confidence(prediction);
    if (!prediction?.alternatives?.length) return "No distribution";
    if (value >= 0.78) return "High separation";
    if (value >= 0.58) return "Medium separation";
    return "Low separation";
  }

  function getPrediction(predictions, key) {
    if (key === "age_estimate") return predictions?.age_estimate;
    return predictions?.[key];
  }

  function cueTerms(prediction) {
    const terms = prediction?.cue_terms || [];
    if (!terms.length) return `<span class="muted">No cue terms returned.</span>`;
    return terms
      .slice(0, 8)
      .map((item) => `<span class="chip">${escapeHtml(item.term || item)}</span>`)
      .join("");
  }

  function distributionBars(prediction) {
    const alternatives = prediction?.alternatives || [];
    if (!alternatives.length) {
      return `<p class="muted">This target does not include a probability distribution.</p>`;
    }
    return `
      <div class="bars objective-bars">
        ${alternatives.map((item) => `
          <div class="bar-row">
            <span>${escapeHtml(titleCase(item.label))}</span>
            <meter class="bar-meter" min="0" max="1" value="${Math.max(Number(item.probability || 0), 0.02)}"></meter>
            <strong>${escapeHtml(percent(item.probability))}</strong>
          </div>
        `).join("")}
      </div>
    `;
  }

  function targetCard(target, prediction) {
    const unavailable = !prediction;
    return `
      <article class="objective-card ${unavailable ? "is-unavailable" : ""}">
        <span class="label">${escapeHtml(target.title)}</span>
        <strong>${escapeHtml(predictionLabel(prediction))}</strong>
        <div class="objective-meta">
          <span>${escapeHtml(confidenceBand(prediction))}</span>
          <span>Confidence ${escapeHtml(prediction?.confidence ? percent(prediction.confidence) : "n/a")}</span>
          <span>Margin ${escapeHtml(prediction?.margin !== undefined ? numberLabel(prediction.margin) : "n/a")}</span>
        </div>
      </article>
    `;
  }

  function dimensionCard(row, prediction) {
    return `
      <article class="strategy-card objective-detail-card">
        <div class="section-title">
          <span class="label">${escapeHtml(row.title)}</span>
          <strong>${escapeHtml(titleCase(predictionLabel(prediction)))}</strong>
        </div>
        ${distributionBars(prediction)}
        <div class="cue-row" aria-label="${escapeHtml(row.title)} cue terms">
          ${cueTerms(prediction)}
        </div>
      </article>
    `;
  }

  function inputQualityCard(predictions) {
    const quality = predictions?.input_quality || {};
    const warnings = quality.warnings || [];
    const stats = predictions?.text_stats || localStats(state.text);
    return `
      <article class="strategy-card objective-quality-card">
        <span class="label">Input quality</span>
        <strong>${escapeHtml(titleCase(quality.level || "ok"))}</strong>
        <p>${warnings.length ? escapeHtml(warnings.join(" ")) : "No input-quality warnings returned by the model pipeline."}</p>
        <div class="mini-grid">
          <span><b>Words</b>${escapeHtml(stats.words ?? 0)}</span>
          <span><b>Sentences</b>${escapeHtml(stats.sentences ?? 0)}</span>
          <span><b>Characters</b>${escapeHtml(stats.characters ?? 0)}</span>
          <span><b>Punctuation density</b>${escapeHtml(stats.punctuation_density ?? 0)}</span>
        </div>
      </article>
    `;
  }

  function evidenceTable(predictions) {
    const rows = [
      ...primaryTargets.map((target) => [target.title, getPrediction(predictions, target.key)]),
      ...dimensionTargets.map((target) => [target.title, predictions?.mbti_dimensions?.[target.key]]),
    ];
    return `
      <section class="objective-section" aria-label="Model evidence table">
        <div class="section-title">
          <span class="label">Evidence table</span>
          <strong>Returned model fields</strong>
        </div>
        <div class="dense-table objective-table">
          <div class="table-head">
            <span>Target</span>
            <span>Top label</span>
            <span>Confidence</span>
            <span>Margin</span>
            <span>Cue terms</span>
          </div>
          ${rows.map(([label, prediction]) => `
            <div class="table-row">
              <span data-label="Target">${escapeHtml(label)}</span>
              <span data-label="Top label">${escapeHtml(predictionLabel(prediction))}</span>
              <span data-label="Confidence">${escapeHtml(prediction?.confidence ? percent(prediction.confidence) : "n/a")}</span>
              <span data-label="Margin">${escapeHtml(prediction?.margin !== undefined ? numberLabel(prediction.margin) : "n/a")}</span>
              <span data-label="Cue terms">${cueTerms(prediction)}</span>
            </div>
          `).join("")}
        </div>
      </section>
    `;
  }

  function rawJsonBlock(data) {
    const json = JSON.stringify(data, null, 2);
    return `
      <details class="secondary-result-details objective-json">
        <summary>Raw model response</summary>
        <pre>${escapeHtml(json)}</pre>
      </details>
    `;
  }

  function resultReport(data) {
    return JSON.stringify({
      model: data.model,
      demo: data.demo,
      predictions: data.predictions,
    }, null, 2);
  }

  async function copyReport(button) {
    if (!state.latestData) return;
    const original = button.textContent;
    try {
      await navigator.clipboard.writeText(resultReport(state.latestData));
      button.textContent = "Copied";
      announce("Model report copied.");
    } catch (error) {
      button.textContent = "Copy unavailable";
      announce("Clipboard unavailable.");
    } finally {
      setTimeout(() => {
        button.textContent = original;
      }, 1400);
    }
  }

  function downloadReport() {
    if (!state.latestData) return;
    const blob = new Blob([resultReport(state.latestData)], {type: "application/json"});
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `texttraits-model-report-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(link.href);
    announce("Model report downloaded.");
  }

  function renderInput() {
    const stats = localStats(state.text);
    els.inputPanel.innerHTML = `
      <form id="objective-form" class="model-input-form">
        <div class="panel-head">
          <div>
            <span class="interface-label">Input</span>
            <h2>Analyze one text sample</h2>
            <p class="helper">Results are limited to trained model targets and computed text statistics.</p>
          </div>
        </div>

        <label class="field">
          <span>Text sample</span>
          <textarea id="objective-text" placeholder="Paste a paragraph, note, reply, essay excerpt, or email here.">${escapeHtml(state.text)}</textarea>
        </label>

        <div class="quality-row">
          <span id="objective-count">${escapeHtml(stats.words)} words</span>
          <span>${escapeHtml(stats.reading_level || "Unavailable")} input density</span>
        </div>

        <div class="sample-grid objective-samples" aria-label="Example inputs">
          ${samples.map((sample, index) => `
            <button class="sample-card" type="button" data-objective-sample="${index}">
              <strong>${escapeHtml(sample.label)}</strong>
              <span>${escapeHtml(localStats(sample.text).words)} words</span>
            </button>
          `).join("")}
        </div>

        <div class="action-row objective-actions">
          <button id="analyze-objective" type="submit" ${state.text.trim() ? "" : "disabled"}>${state.busy ? "Analyzing..." : "Run model analysis"}</button>
          <button id="clear-objective" class="button-secondary" type="button" ${state.text ? "" : "disabled"}>Clear</button>
        </div>
      </form>
    `;
    bindInput();
  }

  function renderEmpty() {
    els.outputPanel.innerHTML = `
      <div class="empty-layout fade-in model-empty">
        <section class="empty-hero objective-hero-card">
          <span class="status-pill">Local inference</span>
          <h2>Prediction distributions will appear here.</h2>
          <p class="muted">The active branch removes generated writing surfaces and centers the trained TextTraits model outputs.</p>
        </section>
        <section class="objective-grid objective-grid-compact">
          ${["MBTI dimensions", "Age and language-association targets", "Confidence margins", "Cue terms"].map((item) => `
            <article class="metric-card"><span>${escapeHtml(item)}</span><strong>Model field</strong></article>
          `).join("")}
        </section>
      </div>
    `;
  }

  function renderLoading() {
    els.outputPanel.innerHTML = `
      <div class="loading-card fade-in" role="status" aria-live="polite" tabindex="-1">
        <span class="status-pill">Running model</span>
        <h2>Analyzing the submitted text...</h2>
        <p class="muted">Waiting for local inference results.</p>
        <div class="skeleton-stack" aria-hidden="true">
          <span></span>
          <span></span>
          <span></span>
        </div>
      </div>
    `;
  }

  function renderError(message) {
    els.outputPanel.innerHTML = `
      <div class="empty-hero error-card" role="alert">
        <span class="status-pill">Needs retry</span>
        <h2>The model analysis did not run.</h2>
        <p class="muted">${escapeHtml(message)}</p>
        <button class="button-secondary" id="retry-run" type="button" ${state.text.trim() ? "" : "disabled"}>Retry</button>
      </div>
    `;
    document.querySelector("#retry-run")?.addEventListener("click", analyze);
  }

  function renderResult(data) {
    const predictions = data.predictions || {};
    const dims = predictions.mbti_dimensions || {};
    const stats = predictions.text_stats || localStats(state.text);
    const targets = primaryTargets.map((target) => targetCard(target, getPrediction(predictions, target.key))).join("");
    const dimensions = dimensionTargets.map((target) => dimensionCard(target, dims[target.key])).join("");

    els.outputPanel.innerHTML = `
      <div class="result-layout objective-result fade-in">
        <div class="result-header">
          <div>
            <p class="label">Model-only result</p>
            <h2>Objective prediction output</h2>
            <p class="muted">${escapeHtml(stats.words)} words analyzed by ${escapeHtml(data.demo ? "demo predictor" : "local inference model")}.</p>
          </div>
          <div class="toolbar">
            <button class="button-secondary" type="button" data-copy-model-report>Copy JSON</button>
            <button class="button-secondary" type="button" data-download-model-report>Download JSON</button>
          </div>
        </div>

        <section class="objective-grid primary-objective-grid" aria-label="Primary model targets">
          ${targets}
        </section>

        ${inputQualityCard(predictions)}

        <section class="objective-section" aria-label="MBTI dimension distributions">
          <div class="section-title">
            <span class="label">Dimension distributions</span>
            <strong>Binary model targets</strong>
          </div>
          <div class="detail-grid objective-detail-grid">
            ${dimensions}
          </div>
        </section>

        ${evidenceTable(predictions)}
        ${rawJsonBlock(data)}
      </div>
    `;
    bindResultActions();
    els.outputPanel.focus();
  }

  function bindInput() {
    const textarea = document.querySelector("#objective-text");
    const form = document.querySelector("#objective-form");
    const clear = document.querySelector("#clear-objective");

    textarea?.addEventListener("input", () => {
      state.text = textarea.value;
      const stats = localStats(state.text);
      const count = document.querySelector("#objective-count");
      const action = document.querySelector("#analyze-objective");
      if (count) count.textContent = `${stats.words} words`;
      if (action) action.disabled = !state.text.trim() || state.busy;
      if (clear) clear.disabled = !state.text;
    });

    form?.addEventListener("submit", (event) => {
      event.preventDefault();
      analyze();
    });

    clear?.addEventListener("click", () => {
      state.text = "";
      state.latestData = null;
      renderInput();
      renderEmpty();
      announce("Input cleared.");
    });

    document.querySelectorAll("[data-objective-sample]").forEach((button) => {
      button.addEventListener("click", () => {
        const sample = samples[Number(button.dataset.objectiveSample)];
        state.text = sample?.text || "";
        renderInput();
        renderEmpty();
        document.querySelector("#objective-text")?.focus();
        announce(`${sample?.label || "Sample"} loaded.`);
      });
    });
  }

  function bindResultActions() {
    document.querySelector("[data-copy-model-report]")?.addEventListener("click", (event) => copyReport(event.currentTarget));
    document.querySelector("[data-download-model-report]")?.addEventListener("click", downloadReport);
  }

  async function analyze() {
    const text = state.text.trim();
    if (!text || state.busy) return;
    state.busy = true;
    renderInput();
    renderLoading();
    try {
      const data = await apiClient.evaluate({text, model: "local", mode: "model-only"});
      state.latestData = data;
      state.latestError = "";
      renderResult(data);
      trackEvent("model_only_evaluate", {words: localStats(text).words});
      announce("Model analysis complete.");
    } catch (error) {
      state.latestError = error.message || "The model analysis failed.";
      renderError(state.latestError);
      apiClient.clientError?.({message: state.latestError, source: "model-only"}).catch(() => {});
    } finally {
      state.busy = false;
      renderInput();
    }
  }

  function init() {
    renderInput();
    renderEmpty();
    apiClient.session?.().catch(() => {});
    announce("TextTraits model-only interface ready.");
  }

  init();
})();
