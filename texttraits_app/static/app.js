(function () {
  const utils = window.TextTraitsUtils || {};
  const apiClient = window.TextTraitsApi || {};

  const escapeHtml = utils.escapeHtml || ((value) => String(value ?? ""));
  const localStats = utils.localStats || ((text) => ({
    words: String(text || "").trim().split(/\s+/).filter(Boolean).length,
    characters: String(text || "").length,
    sentences: 1,
    punctuation_density: 0,
    reading_level: "Unavailable",
  }));
  const titleCase = utils.titleCase || ((value) => String(value || ""));
  const words = utils.words || ((text) => String(text || "").trim().match(/\b[\w'-]+\b/g) || []);

  const els = {
    announcer: document.querySelector("#announcer"),
    inputPanel: document.querySelector("#input-panel"),
    outputPanel: document.querySelector("#output-panel"),
  };

  const state = {
    subject: "",
    email: "",
    audience: "Prospect",
    intent: "Follow-up",
    latestData: null,
    latestOptimization: null,
    latestError: "",
    busy: false,
  };

  const samples = [
    {
      label: "Follow-up",
      subject: "Next step after Tuesday",
      audience: "Prospect",
      intent: "Follow-up",
      email: "Hi Maya, thanks for walking through the renewal workflow on Tuesday. The strongest gap I heard was that managers see risk after the forecast is already under pressure. If helpful, I can send a two-minute benchmark showing how teams flag coaching moments earlier. Would Thursday afternoon work for a quick fit check?",
    },
    {
      label: "Cold outreach",
      subject: "Forecast risk visibility",
      audience: "Prospect",
      intent: "Cold outreach",
      email: "Hi Jordan, I noticed Northwind is hiring more RevOps support, which usually makes weekly forecast inspection harder to keep consistent. TextTraits helps teams grade existing outreach and manager notes for clarity, specificity, and send readiness before messages leave Gmail or Outreach. Is improving review quality a priority this quarter?",
    },
    {
      label: "Reply",
      subject: "Re: dashboard question",
      audience: "Prospect",
      intent: "Reply",
      email: "Thanks for saying this directly. If the concern is adding another writing tool, the better fit is using TextTraits as a scoring layer beside the tools your team already uses. The report flags length, specificity, CTA clarity, and model separation without drafting the response. Should I share the checklist format?",
    },
  ];

  const audiences = ["Prospect", "Customer", "Executive buyer", "Internal reviewer"];
  const intents = ["Cold outreach", "Follow-up", "Reply", "Renewal", "Internal handoff"];

  const modelTargets = [
    {key: "gender", title: "Language-association target"},
    {key: "mbti", title: "16-class style target"},
    {key: "age_bucket", title: "Age-bucket target"},
    {key: "age_estimate", title: "Age-estimate target"},
  ];

  const dimensionTargets = [
    {key: "energy", title: "Energy"},
    {key: "information", title: "Information"},
    {key: "decisions", title: "Decision"},
    {key: "structure", title: "Structure"},
  ];

  const vagueTerms = ["stuff", "things", "maybe", "probably", "kind of", "sort of", "really", "very", "a lot", "somewhat"];
  const hypeTerms = ["revolutionary", "game-changing", "guaranteed", "disruptive", "world-class", "best-in-class"];
  const ctaPattern = /(would you|could we|can we|are you open|does .* work|reply|send|share|schedule|meet|call|next step|fit check|\?)/i;
  const datePattern = /\b(today|tomorrow|monday|tuesday|wednesday|thursday|friday|next week|this week|q[1-4]|\d{1,2}\/\d{1,2}|\d+%|\$\d+|\d+\s?(minute|day|week|month|year)s?)\b/i;

  function announce(message) {
    if (els.announcer) els.announcer.textContent = message;
  }

  function trackEvent(event_type, payload = {}) {
    apiClient.event?.(event_type, payload).catch(() => {});
  }

  function percent(value) {
    return `${Math.round(Number(value || 0) * 100)}%`;
  }

  function numberLabel(value, digits = 3) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "n/a";
    return number.toFixed(digits);
  }

  function cleanModelLabel(value) {
    const raw = String(value || "Unavailable").replace(/^source label:\s*/i, "");
    if (/^[a-z]{4}$/i.test(raw)) return raw.toUpperCase();
    if (/\d/.test(raw)) return raw;
    return titleCase(raw);
  }

  function predictionLabel(prediction) {
    return cleanModelLabel(prediction?.label);
  }

  function getPrediction(predictions, key) {
    if (key === "age_estimate") return predictions?.age_estimate;
    return predictions?.[key];
  }

  function confidenceBand(prediction) {
    const value = Number(prediction?.confidence || 0);
    const margin = Number(prediction?.margin || 0);
    if (!prediction?.alternatives?.length) return "No distribution";
    if (value >= 0.78 && margin >= 0.18) return "High separation";
    if (value >= 0.58 && margin >= 0.08) return "Medium separation";
    return "Low separation";
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
      <div class="bars optimizer-bars">
        ${alternatives.slice(0, 5).map((item) => `
          <div class="bar-row">
            <span>${escapeHtml(cleanModelLabel(item.label))}</span>
            <meter class="bar-meter" min="0" max="1" value="${Math.max(Number(item.probability || 0), 0.02)}"></meter>
            <strong>${escapeHtml(percent(item.probability))}</strong>
          </div>
        `).join("")}
      </div>
    `;
  }

  function countPhraseMatches(text, phrases) {
    const clean = text.toLowerCase();
    return phrases.reduce((count, phrase) => count + (clean.includes(phrase) ? 1 : 0), 0);
  }

  function scoreLength(wordCount) {
    if (wordCount >= 70 && wordCount <= 170) return 20;
    if (wordCount >= 45 && wordCount <= 210) return 15;
    if (wordCount >= 25 && wordCount <= 260) return 10;
    return 5;
  }

  function scoreSubject(subject) {
    const length = subject.trim().length;
    if (!length) return 3;
    if (length >= 18 && length <= 58) return 10;
    if (length >= 12 && length <= 72) return 7;
    return 4;
  }

  function scoreClarity(stats, text) {
    const avgSentence = stats.words / Math.max(stats.sentences, 1);
    const vagueCount = countPhraseMatches(text, vagueTerms);
    let score = 20;
    if (avgSentence > 24) score -= 7;
    if (avgSentence > 32) score -= 5;
    score -= Math.min(vagueCount * 3, 8);
    if ((text.match(/!/g) || []).length > 1) score -= 3;
    return Math.max(score, 4);
  }

  function scoreBuyerFocus(text) {
    const tokens = words(text.toLowerCase());
    const you = tokens.filter((word) => ["you", "your", "yours", "team"].includes(word)).length;
    const me = tokens.filter((word) => ["i", "we", "our", "me", "my"].includes(word)).length;
    if (you >= 3 && you >= me - 1) return 20;
    if (you >= 2) return 15;
    if (you >= 1) return 10;
    return 5;
  }

  function emailOptimization(subject, email) {
    const stats = localStats(email);
    const cleanEmail = email.trim();
    const hasCta = ctaPattern.test(cleanEmail);
    const hasSpecifics = datePattern.test(`${subject} ${cleanEmail}`);
    const vagueCount = countPhraseMatches(cleanEmail, vagueTerms);
    const hypeCount = countPhraseMatches(cleanEmail, hypeTerms);
    const ctaScore = hasCta ? 20 : 6;
    const specificityScore = hasSpecifics ? 20 : Math.max(8, 16 - vagueCount * 2);
    const subjectScore = scoreSubject(subject);
    const lengthScore = scoreLength(stats.words);
    const clarityScore = scoreClarity(stats, cleanEmail);
    const buyerFocusScore = scoreBuyerFocus(cleanEmail);
    const total = subjectScore + lengthScore + ctaScore + specificityScore + clarityScore + buyerFocusScore;
    const score = Math.round((total / 110) * 100);
    const checks = [
      {
        label: "Subject line",
        value: subjectScore >= 8 ? "Optimized" : "Needs work",
        detail: subject.trim() ? `${subject.trim().length} characters` : "No subject line provided",
        action: subjectScore >= 8 ? "Keep the subject concise and concrete." : "Add a specific subject that previews the email's reason.",
        status: subjectScore >= 8 ? "ok" : "risk",
      },
      {
        label: "Body length",
        value: lengthScore >= 15 ? "Scannable" : "Review length",
        detail: `${stats.words} words across ${stats.sentences} sentences`,
        action: lengthScore >= 15 ? "Length fits a reviewable business email." : "Aim for a tighter email body before sending.",
        status: lengthScore >= 15 ? "ok" : "risk",
      },
      {
        label: "Next step",
        value: hasCta ? "Clear CTA found" : "CTA missing",
        detail: hasCta ? "The email includes a question or next-step cue." : "No obvious question or next-step cue detected.",
        action: hasCta ? "Keep one next step easy to answer." : "Add one explicit next action for the reader.",
        status: hasCta ? "ok" : "risk",
      },
      {
        label: "Specificity",
        value: hasSpecifics ? "Concrete" : "Could be more concrete",
        detail: hasSpecifics ? "Detected a date, number, timeframe, or measurable proof point." : "No date, number, timeframe, or measurable proof point detected.",
        action: hasSpecifics ? "Use the concrete detail as the anchor of the message." : "Add one concrete signal, proof point, or timeframe.",
        status: hasSpecifics ? "ok" : "risk",
      },
      {
        label: "Clarity",
        value: clarityScore >= 15 ? "Readable" : "Dense or vague",
        detail: `${vagueCount} vague cue${vagueCount === 1 ? "" : "s"} detected`,
        action: clarityScore >= 15 ? "Sentence density is reasonable." : "Remove vague qualifiers and split long sentences.",
        status: clarityScore >= 15 ? "ok" : "risk",
      },
      {
        label: "Buyer focus",
        value: buyerFocusScore >= 15 ? "Reader-centered" : "Sender-centered",
        detail: "Compares reader-facing language with sender-facing language.",
        action: buyerFocusScore >= 15 ? "The message keeps attention on the reader." : "Shift more sentences toward the reader's problem or decision.",
        status: buyerFocusScore >= 15 ? "ok" : "risk",
      },
    ];

    if (hypeCount) {
      checks.push({
        label: "Sales language",
        value: "Hype risk",
        detail: `${hypeCount} hype cue${hypeCount === 1 ? "" : "s"} detected`,
        action: "Replace broad claims with a concrete proof point.",
        status: "risk",
      });
    }

    const risks = checks.filter((check) => check.status === "risk");
    return {
      score,
      readiness: score >= 82 && risks.length <= 1 ? "Ready to send" : score >= 68 ? "Needs light review" : "Needs revision",
      stats,
      checks,
      risks,
      calculation: {
        subjectScore,
        lengthScore,
        ctaScore,
        specificityScore,
        clarityScore,
        buyerFocusScore,
        total,
      },
    };
  }

  function renderInput() {
    const stats = localStats(state.email);
    els.inputPanel.innerHTML = `
      <form id="optimizer-form" class="optimizer-form">
        <div class="panel-head">
          <div>
            <span class="interface-label">Enterprise input</span>
            <h2>Analyze an existing email</h2>
            <p class="helper">Paste a draft from Gmail, Outlook, Outreach, Salesloft, or your editor. TextTraits scores it without writing a replacement.</p>
          </div>
        </div>

        <label class="field">
          <span>Subject line</span>
          <input id="email-subject" type="text" value="${escapeHtml(state.subject)}" placeholder="e.g. Next step after Tuesday">
        </label>

        <div class="field-grid optimizer-field-grid">
          <label class="field">
            <span>Audience</span>
            <select id="email-audience">
              ${audiences.map((item) => `<option ${item === state.audience ? "selected" : ""}>${escapeHtml(item)}</option>`).join("")}
            </select>
          </label>
          <label class="field">
            <span>Email type</span>
            <select id="email-intent">
              ${intents.map((item) => `<option ${item === state.intent ? "selected" : ""}>${escapeHtml(item)}</option>`).join("")}
            </select>
          </label>
        </div>

        <label class="field">
          <span>Email body</span>
          <textarea id="email-body" placeholder="Paste an existing email draft here.">${escapeHtml(state.email)}</textarea>
        </label>

        <div class="quality-row">
          <span id="optimizer-count">${escapeHtml(stats.words)} words</span>
          <span>${escapeHtml(stats.reading_level || "Unavailable")} input density</span>
        </div>

        <div class="sample-grid optimizer-samples" aria-label="Example enterprise emails">
          ${samples.map((sample, index) => `
            <button class="sample-card" type="button" data-optimizer-sample="${index}">
              <strong>${escapeHtml(sample.label)}</strong>
              <span>${escapeHtml(localStats(sample.email).words)} words</span>
            </button>
          `).join("")}
        </div>

        <div class="action-row optimizer-actions">
          <button id="analyze-email" type="submit" ${state.email.trim() ? "" : "disabled"}>${state.busy ? "Analyzing..." : "Analyze email optimization"}</button>
          <button id="clear-email" class="button-secondary" type="button" ${state.email || state.subject ? "" : "disabled"}>Clear</button>
        </div>
      </form>
    `;
    bindInput();
  }

  function renderEmpty() {
    els.outputPanel.innerHTML = `
      <div class="empty-layout fade-in optimizer-empty">
        <section class="empty-hero optimizer-hero-card">
          <span class="status-pill">Optimization layer</span>
          <h2>Email quality report will appear here.</h2>
          <p class="muted">This version is built for teams that already have email tools and need objective review before sending.</p>
        </section>
        <section class="optimizer-grid optimizer-grid-compact">
          ${[
            ["Optimization score", "Deterministic checks"],
            ["Send readiness", "Enterprise QA"],
            ["Model signals", "Local inference"],
            ["Report export", "No generated copy"],
          ].map(([label, value]) => `
            <article class="metric-card">
              <span>${escapeHtml(label)}</span>
              <strong>${escapeHtml(value)}</strong>
            </article>
          `).join("")}
        </section>
      </div>
    `;
  }

  function renderLoading() {
    els.outputPanel.innerHTML = `
      <div class="loading-card fade-in" role="status" aria-live="polite" tabindex="-1">
        <span class="status-pill">Analyzing email</span>
        <h2>Scoring the existing draft...</h2>
        <p class="muted">Combining send-readiness checks with local model inference.</p>
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
        <h2>The email optimization did not run.</h2>
        <p class="muted">${escapeHtml(message)}</p>
        <button class="button-secondary" id="retry-run" type="button" ${state.email.trim() ? "" : "disabled"}>Retry</button>
      </div>
    `;
    document.querySelector("#retry-run")?.addEventListener("click", analyze);
  }

  function scoreRing(optimization) {
    return `
      <article class="optimizer-score-card">
        <span class="interface-label">Optimization score</span>
        <strong>${escapeHtml(optimization.score)}/100</strong>
        <p>${escapeHtml(optimization.readiness)}</p>
        <div class="score-track" aria-hidden="true">
          <span style="width: ${Math.max(0, Math.min(optimization.score, 100))}%"></span>
        </div>
      </article>
    `;
  }

  function checkCards(optimization) {
    return optimization.checks.map((check) => `
      <article class="optimizer-check-card ${check.status === "risk" ? "needs-work" : "is-ok"}">
        <span class="label">${escapeHtml(check.label)}</span>
        <strong>${escapeHtml(check.value)}</strong>
        <p>${escapeHtml(check.detail)}</p>
        <small>${escapeHtml(check.action)}</small>
      </article>
    `).join("");
  }

  function modelSignalCard(target, prediction) {
    return `
      <article class="optimizer-model-card">
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

  function modelSignals(predictions) {
    const dims = predictions?.mbti_dimensions || {};
    return `
      <section class="optimizer-section" aria-label="Objective model signals">
        <div class="section-title">
          <span class="label">Objective model signals</span>
          <strong>Shown as evidence, not generated writing</strong>
        </div>
        <div class="optimizer-grid primary-optimizer-grid">
          ${modelTargets.map((target) => modelSignalCard(target, getPrediction(predictions, target.key))).join("")}
        </div>
        <div class="detail-grid optimizer-detail-grid">
          ${dimensionTargets.map((target) => {
            const prediction = dims[target.key];
            return `
              <article class="strategy-card optimizer-detail-card">
                <div class="section-title">
                  <span class="label">${escapeHtml(target.title)} dimension</span>
                  <strong>${escapeHtml(predictionLabel(prediction))}</strong>
                </div>
                ${distributionBars(prediction)}
                <div class="cue-row" aria-label="${escapeHtml(target.title)} cue terms">
                  ${cueTerms(prediction)}
                </div>
              </article>
            `;
          }).join("")}
        </div>
      </section>
    `;
  }

  function reportJson(data, optimization) {
    return JSON.stringify({
      subject: state.subject,
      audience: state.audience,
      intent: state.intent,
      optimization,
      model: data.model,
      demo: data.demo,
      predictions: data.predictions,
      privacy_note: "Report excludes the full email body.",
    }, null, 2);
  }

  async function copyReport(button) {
    if (!state.latestData || !state.latestOptimization) return;
    const original = button.textContent;
    try {
      await navigator.clipboard.writeText(reportJson(state.latestData, state.latestOptimization));
      button.textContent = "Copied";
      announce("Optimization report copied.");
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
    if (!state.latestData || !state.latestOptimization) return;
    const blob = new Blob([reportJson(state.latestData, state.latestOptimization)], {type: "application/json"});
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `texttraits-email-optimization-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(link);
    link.click();
    const href = link.href;
    link.remove();
    URL.revokeObjectURL(href);
    announce("Optimization report downloaded.");
  }

  function rawJsonBlock(data) {
    return `
      <details class="secondary-result-details optimizer-json">
        <summary>Raw model response</summary>
        <pre>${escapeHtml(JSON.stringify(data, null, 2))}</pre>
      </details>
    `;
  }

  function renderResult(data, optimization) {
    const predictions = data.predictions || {};
    els.outputPanel.innerHTML = `
      <div class="result-layout optimizer-result fade-in">
        <div class="result-header">
          <div>
            <p class="label">Enterprise email report</p>
            <h2>Optimization readout for the existing draft</h2>
            <p class="muted">No replacement email was generated. The report evaluates send readiness, clarity, specificity, and local model signals.</p>
          </div>
          <div class="toolbar">
            <button class="button-secondary" type="button" data-copy-report>Copy report</button>
            <button class="button-secondary" type="button" data-download-report>Download JSON</button>
          </div>
        </div>

        <section class="optimizer-summary-grid" aria-label="Email optimization summary">
          ${scoreRing(optimization)}
          <article class="optimizer-context-card">
            <span class="interface-label">Draft context</span>
            <strong>${escapeHtml(state.intent)} for ${escapeHtml(state.audience)}</strong>
            <p>${escapeHtml(optimization.stats.words)} words, ${escapeHtml(optimization.stats.sentences)} sentences, ${escapeHtml(state.subject.trim() || "no subject line")}.</p>
          </article>
          <article class="optimizer-context-card">
            <span class="interface-label">Positioning</span>
            <strong>Works beside existing tools</strong>
            <p>Use the report as a QA layer before sending from Gmail, Outlook, Outreach, Salesloft, or a CRM workflow.</p>
          </article>
        </section>

        <section class="optimizer-section" aria-label="Send readiness checks">
          <div class="section-title">
            <span class="label">Send-readiness checks</span>
            <strong>What to optimize before sending</strong>
          </div>
          <div class="optimizer-grid optimizer-check-grid">
            ${checkCards(optimization)}
          </div>
        </section>

        ${modelSignals(predictions)}
        ${rawJsonBlock(data)}
      </div>
    `;
    document.querySelector("[data-copy-report]")?.addEventListener("click", (event) => copyReport(event.currentTarget));
    document.querySelector("[data-download-report]")?.addEventListener("click", downloadReport);
    els.outputPanel.focus();
  }

  function bindInput() {
    const subject = document.querySelector("#email-subject");
    const body = document.querySelector("#email-body");
    const audience = document.querySelector("#email-audience");
    const intent = document.querySelector("#email-intent");
    const form = document.querySelector("#optimizer-form");
    const clear = document.querySelector("#clear-email");

    subject?.addEventListener("input", () => {
      state.subject = subject.value;
      if (clear) clear.disabled = !state.email && !state.subject;
    });
    body?.addEventListener("input", () => {
      state.email = body.value;
      const stats = localStats(state.email);
      const count = document.querySelector("#optimizer-count");
      const action = document.querySelector("#analyze-email");
      if (count) count.textContent = `${stats.words} words`;
      if (action) action.disabled = !state.email.trim() || state.busy;
      if (clear) clear.disabled = !state.email && !state.subject;
    });
    audience?.addEventListener("change", () => {
      state.audience = audience.value;
    });
    intent?.addEventListener("change", () => {
      state.intent = intent.value;
    });
    form?.addEventListener("submit", (event) => {
      event.preventDefault();
      analyze();
    });
    clear?.addEventListener("click", () => {
      state.subject = "";
      state.email = "";
      state.latestData = null;
      state.latestOptimization = null;
      renderInput();
      renderEmpty();
      announce("Email cleared.");
    });
    document.querySelectorAll("[data-optimizer-sample]").forEach((button) => {
      button.addEventListener("click", () => {
        const sample = samples[Number(button.dataset.optimizerSample)];
        state.subject = sample?.subject || "";
        state.email = sample?.email || "";
        state.audience = sample?.audience || state.audience;
        state.intent = sample?.intent || state.intent;
        renderInput();
        renderEmpty();
        document.querySelector("#email-body")?.focus();
        announce(`${sample?.label || "Sample"} email loaded.`);
      });
    });
  }

  async function analyze() {
    const email = state.email.trim();
    if (!email || state.busy) return;
    state.busy = true;
    renderInput();
    renderLoading();
    try {
      const optimization = emailOptimization(state.subject, email);
      const data = await apiClient.evaluate({
        text: `${state.subject}\n\n${email}`,
        model: "local",
        mode: "enterprise-email-optimizer",
      });
      state.latestData = data;
      state.latestOptimization = optimization;
      state.latestError = "";
      renderResult(data, optimization);
      trackEvent("enterprise_email_optimization", {words: optimization.stats.words, score: optimization.score});
      announce("Email optimization complete.");
    } catch (error) {
      state.latestError = error.message || "The email optimization failed.";
      renderError(state.latestError);
      apiClient.clientError?.({message: state.latestError, source: "enterprise-email-optimizer"}).catch(() => {});
    } finally {
      state.busy = false;
      renderInput();
    }
  }

  function init() {
    renderInput();
    renderEmpty();
    apiClient.session?.().catch(() => {});
    announce("TextTraits enterprise email optimizer ready.");
  }

  init();
})();
