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
    policyBundle: "enterprise_email_readiness",
    latestData: null,
    latestOptimization: null,
    labData: null,
    labError: "",
    policyBusy: false,
    policyMessage: "",
    simulatorProvider: "hubspot",
    simulatorPayload: "",
    simulatorBusy: false,
    simulatorMessage: "",
    simulatorResult: null,
    setupBusyProvider: "",
    setupMessage: "",
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
  const simulatorPayloads = {
    hubspot: {
      inputFields: {
        email_subject: "Renewal workflow follow-up",
        email_body: "Hi Jordan, your team mentioned renewal risk reviews are happening later than planned. Could we review the current manager handoff on Thursday?",
        lifecyclestage: "Customer",
        workflow_name: "Renewal workflow",
      },
    },
    braze: {
      source_system: "braze",
      analysis_mode: "pre_send_gate",
      canvas_step: {
        subject: "Quick check for {{ first_name }}",
        body: "Hi {{ first_name }}, your team can review the renewal checklist by Thursday. Manage preferences here: https://example.test/prefs",
        template_id: "braze_canvas_email",
      },
      personalization_context: {first_name: "Maya"},
      headers: {"List-Unsubscribe": "<https://example.test/unsub>"},
    },
    warehouse: {
      rows: [
        {
          subject: "Forecast risk follow-up",
          body: "Hi Maya, could we review the forecast handoff on Thursday?",
          campaign_id: "cmp_internal_demo",
          template_id: "tmpl_followup",
          event_type: "delivered",
        },
      ],
    },
  };

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
          <span class="status-pill">Enterprise integration lab</span>
          <h2>Policy-backed email analysis will appear here.</h2>
          <p class="muted">This version is built for teams that already have email tools and need objective review before messages enter a workflow, journey, or sending system.</p>
        </section>
        <section class="optimizer-grid optimizer-grid-compact">
          ${[
            ["Stable contract", "/v1/email/analyze"],
            ["Policy gate", "Ready, review, or block"],
            ["Workflow mocks", "HubSpot, Salesforce, SendGrid/SES"],
            ["Governance", "Hashes, versions, dedupe"],
          ].map(([label, value]) => `
            <article class="metric-card">
              <span>${escapeHtml(label)}</span>
              <strong>${escapeHtml(value)}</strong>
            </article>
          `).join("")}
        </section>
        ${labOverview()}
      </div>
    `;
    bindLabControls();
  }

  function renderLoading() {
    els.outputPanel.innerHTML = `
      <div class="loading-card fade-in" role="status" aria-live="polite" tabindex="-1">
        <span class="status-pill">Analyzing email</span>
        <h2>Calling the v1 policy gate...</h2>
        <p class="muted">Combining rule packs, request metadata, and local model inference without generating copy.</p>
        <div class="skeleton-stack" aria-hidden="true">
          <span></span>
          <span></span>
          <span></span>
        </div>
      </div>
    `;
  }

  function labOverview() {
    const flows = state.labData?.flows || [];
    const manifests = state.labData?.manifests || [];
    const mappings = state.labData?.fieldMappings || [];
    const installKit = state.labData?.installKit || {};
    const dashboard = state.labData?.dashboard || {};
    const plan = state.labData?.integrationPlan || {};
    const policy = state.labData?.policy || dashboard.policy || {};
    const gateCounts = dashboard.gate_counts || {};
    const cards = [
      ["API contract", "Analyze API", "POST /v1/email/analyze with stable scoring and routing"],
      ["Contract export", `${installKit.endpoints?.length || 12} endpoints`, "OpenAPI JSON, manifests, setup sequence"],
      ["Mock adapters", `${flows.length || 4} flows`, "HubSpot, Salesforce, SendGrid/SES, webhooks"],
      ["Setup manifests", `${manifests.length || 4} providers`, `${mappings.length} saved field mapping${mappings.length === 1 ? "" : "s"}`],
      ["Governance ledger", `${dashboard.analysis_volume ?? 0} analyses`, `${gateCounts.ready || 0} ready / ${gateCounts.needs_review || 0} review / ${gateCounts.blocked || 0} blocked`],
      ["Sample imports", `${(dashboard.sample_imports || []).length} recent`, "Warehouse-style batch review"],
      ["Policy controls", `${policy.min_ready_score ?? 72} minimum score`, `${policy.content_storage_mode || "hash_only"} storage / ${policy.retention_days ?? 180} day retention`],
      ["Research targets", `${(plan.targets || []).length || manifests.length} targets`, plan.recommendation?.primary_target || "journey workflow gate"],
    ];
    return `
      <section class="optimizer-section integration-lab-overview" aria-label="Integration lab status">
        <div class="section-title">
          <span class="label">Integration lab status</span>
          <strong>${state.labError ? "Live status unavailable" : "Workflow-ready infrastructure"}</strong>
        </div>
        <div class="optimizer-grid integration-lab-grid">
          ${cards.map(([label, value, detail]) => `
            <article class="optimizer-context-card lab-status-card">
              <span class="interface-label">${escapeHtml(label)}</span>
              <strong>${escapeHtml(value)}</strong>
              <p>${escapeHtml(detail)}</p>
            </article>
          `).join("")}
        </div>
        ${governancePolicyControls(policy)}
        ${adapterSimulator(plan, manifests)}
        ${setupContracts(manifests, mappings)}
      </section>
    `;
  }

  function adapterSimulator(plan = {}, manifests = []) {
    const providers = manifests.map((manifest) => manifest.provider);
    const options = Array.from(new Set(["hubspot", "salesforce", "sendgrid_ses", "braze", "marketo", "iterable", "warehouse", ...providers]));
    const payload = state.simulatorPayload || JSON.stringify(simulatorPayloads[state.simulatorProvider] || simulatorPayloads.hubspot, null, 2);
    return `
      <section class="optimizer-section adapter-simulator" aria-label="Adapter simulator">
        <div class="section-title">
          <span class="label">Adapter simulator</span>
          <strong>Paste a provider payload and inspect mapped scoring outputs</strong>
        </div>
        ${state.simulatorMessage ? `<p class="setup-message">${escapeHtml(state.simulatorMessage)}</p>` : ""}
        <div class="adapter-simulator-grid">
          <label class="policy-control">
            <span>Provider</span>
            <select data-simulator-provider>
              ${options.map((provider) => `<option value="${escapeHtml(provider)}" ${provider === state.simulatorProvider ? "selected" : ""}>${escapeHtml(providerLabel(provider))}</option>`).join("")}
            </select>
          </label>
          <label class="policy-control adapter-simulator-payload">
            <span>Payload JSON</span>
            <textarea data-simulator-payload spellcheck="false">${escapeHtml(payload)}</textarea>
          </label>
        </div>
        <div class="setup-action-row">
          <button class="button-secondary" type="button" data-run-adapter-simulator ${state.simulatorBusy ? "disabled" : ""}>
            ${state.simulatorBusy ? "Simulating..." : "Run simulator"}
          </button>
          <span class="muted">${escapeHtml(plan.recommendation?.positioning || "Internal adapters score existing messages without connecting to external systems.")}</span>
        </div>
        ${state.simulatorResult ? `
          <pre class="adapter-simulator-result">${escapeHtml(JSON.stringify(state.simulatorResult, null, 2))}</pre>
        ` : ""}
      </section>
    `;
  }

  function policyValue(policy, key, fallback) {
    const value = policy?.[key];
    return value === undefined || value === null || value === "" ? fallback : value;
  }

  function governancePolicyControls(policy = {}) {
    const highReview = policyValue(policy, "high_severity_requires_review", true);
    const familyModes = policy?.rule_family_modes || {};
    const families = ["compliance", "unsubscribe", "personalization", "cta", "format"];
    return `
      <section class="optimizer-section governance-policy-controls" aria-label="Governance policy controls">
        <div class="section-title">
          <span class="label">Governance policy</span>
          <strong>Workspace controls for gating, retention, and storage</strong>
        </div>
        ${state.policyMessage ? `<p class="setup-message">${escapeHtml(state.policyMessage)}</p>` : ""}
        <div class="policy-control-grid">
          <label class="policy-control">
            <span>Ready score</span>
            <input type="number" min="0" max="100" step="1" value="${escapeHtml(policyValue(policy, "min_ready_score", 72))}" data-policy-field="min_ready_score">
          </label>
          <label class="policy-control">
            <span>Analysis retention days</span>
            <input type="number" min="30" max="3650" step="1" value="${escapeHtml(policyValue(policy, "retention_days", 180))}" data-policy-field="retention_days">
          </label>
          <label class="policy-control">
            <span>Webhook retention days</span>
            <input type="number" min="30" max="3650" step="1" value="${escapeHtml(policyValue(policy, "webhook_retention_days", 365))}" data-policy-field="webhook_retention_days">
          </label>
          <label class="policy-control">
            <span>Dedupe window days</span>
            <input type="number" min="1" max="365" step="1" value="${escapeHtml(policyValue(policy, "webhook_dedupe_window_days", 30))}" data-policy-field="webhook_dedupe_window_days">
          </label>
          <label class="policy-control">
            <span>Sample import limit</span>
            <input type="number" min="1" max="100" step="1" value="${escapeHtml(policyValue(policy, "sample_import_limit", 25))}" data-policy-field="sample_import_limit">
          </label>
          <label class="policy-control">
            <span>Storage mode</span>
            <select data-policy-field="content_storage_mode">
              <option value="hash_only" ${policyValue(policy, "content_storage_mode", "hash_only") === "hash_only" ? "selected" : ""}>Hash only</option>
              <option value="metadata_only" ${policyValue(policy, "content_storage_mode", "hash_only") === "metadata_only" ? "selected" : ""}>Metadata only</option>
            </select>
          </label>
          <label class="policy-control">
            <span>Environment</span>
            <select data-policy-field="policy_environment">
              ${["sandbox", "staging", "production"].map((env) => `<option value="${env}" ${policyValue(policy, "policy_environment", "production") === env ? "selected" : ""}>${titleCase(env)}</option>`).join("")}
            </select>
          </label>
          <label class="policy-control">
            <span>Send timeout ms</span>
            <input type="number" min="50" max="10000" step="50" value="${escapeHtml(policyValue(policy, "send_path_timeout_ms", 500))}" data-policy-field="send_path_timeout_ms">
          </label>
          <label class="policy-control">
            <span>Idempotency window sec</span>
            <input type="number" min="60" max="86400" step="60" value="${escapeHtml(policyValue(policy, "idempotency_window_seconds", 900))}" data-policy-field="idempotency_window_seconds">
          </label>
        </div>
        <div class="rule-family-control-group">
          <span class="interface-label">Rule family behavior</span>
          <div class="policy-control-grid rule-family-grid">
            ${families.map((family) => {
              const currentMode = familyModes[family] || (family === "compliance" || family === "unsubscribe" ? "fail_closed" : "review");
              return `
                <label class="policy-control">
                  <span>${escapeHtml(ruleFamilyLabel(family))}</span>
                  <select data-rule-family-mode="${escapeHtml(family)}">
                    ${["fail_closed", "review", "fail_open"].map((mode) => `<option value="${mode}" ${currentMode === mode ? "selected" : ""}>${escapeHtml(ruleModeLabel(mode))}</option>`).join("")}
                  </select>
                </label>
              `;
            }).join("")}
          </div>
        </div>
        <div class="policy-toggle-row">
          <label>
            <input type="checkbox" data-policy-field="high_severity_requires_review" ${highReview ? "checked" : ""}>
            <span>Route high-severity findings to review</span>
          </label>
          <button class="button-secondary" type="button" data-save-policy-controls ${state.policyBusy ? "disabled" : ""}>
            ${state.policyBusy ? "Saving..." : "Save policy controls"}
          </button>
        </div>
      </section>
    `;
  }

  function providerLabel(provider) {
    return String(provider || "")
      .replace(/_/g, " ")
      .replace(/\b\w/g, (letter) => letter.toUpperCase())
      .replace("Ses", "SES");
  }

  function ruleFamilyLabel(family) {
    const labels = {cta: "CTA"};
    return labels[family] || providerLabel(family);
  }

  function ruleModeLabel(mode) {
    const labels = {
      fail_closed: "Fail closed",
      fail_open: "Fail open",
      review: "Review",
    };
    return labels[mode] || providerLabel(mode);
  }

  function mappingForProvider(provider, mappings) {
    return mappings.find((mapping) => mapping.provider === provider);
  }

  function recommendedMapping(manifest) {
    const requiredInputs = manifest?.required_inputs || {};
    const inputs = Object.fromEntries(
      Object.entries(requiredInputs).map(([key, field]) => [
        key,
        field.hubspot_property || field.journey_attribute || field.path || key,
      ])
    );
    return {
      inputs,
      outputs: {...(manifest?.recommended_writeback || {})},
    };
  }

  function setupContracts(manifests, mappings) {
    if (!manifests.length) {
      return `
        <div class="setup-empty muted">
          Integration manifests load from the v1 setup contract.
        </div>
      `;
    }
    return `
      <section class="optimizer-section setup-contracts" aria-label="Integration setup contracts">
        <div class="section-title">
          <span class="label">Integration setup</span>
          <strong>Map provider fields before messages flow through TextTraits</strong>
        </div>
        ${state.setupMessage ? `<p class="setup-message">${escapeHtml(state.setupMessage)}</p>` : ""}
        <div class="setup-action-row">
          <button class="button-secondary" type="button" data-download-openapi>Download OpenAPI JSON</button>
          <button class="button-secondary" type="button" data-copy-install-steps>Copy install steps</button>
        </div>
        <div class="optimizer-grid setup-contract-grid">
          ${manifests.map((manifest) => {
            const mapping = mappingForProvider(manifest.provider, mappings);
            const requiredCount = Object.keys(manifest.required_inputs || {}).length;
            const outputCount = Object.keys(manifest.recommended_writeback || {}).length;
            const isBusy = state.setupBusyProvider === manifest.provider;
            return `
              <article class="optimizer-check-card setup-contract-card ${mapping?.status === "ready" ? "is-ok" : "needs-work"}">
                <span class="label">${escapeHtml(manifest.install_surface || "Integration")}</span>
                <strong>${escapeHtml(manifest.name || providerLabel(manifest.provider))}</strong>
                <p>${escapeHtml(manifest.entrypoint || "v1 integration endpoint")}</p>
                <div class="objective-meta">
                  <span>${escapeHtml(mapping?.status === "ready" ? "Mapped" : "Template ready")}</span>
                  <span>${escapeHtml(requiredCount)} required inputs</span>
                  <span>${escapeHtml(outputCount)} writeback outputs</span>
                </div>
                <small>Required inputs: ${escapeHtml(Object.keys(manifest.required_inputs || {}).join(", ") || "none")}</small>
                <button class="button-secondary" type="button" data-save-recommended-mapping="${escapeHtml(manifest.provider)}" ${isBusy ? "disabled" : ""}>
                  ${isBusy ? "Saving..." : mapping?.status === "ready" ? "Refresh recommended mapping" : "Save recommended mapping"}
                </button>
              </article>
            `;
          }).join("")}
        </div>
      </section>
    `;
  }

  function bindLabControls() {
    document.querySelectorAll("[data-save-recommended-mapping]").forEach((button) => {
      button.addEventListener("click", () => saveRecommendedMapping(button.dataset.saveRecommendedMapping));
    });
    document.querySelector("[data-download-openapi]")?.addEventListener("click", downloadOpenApiContract);
    document.querySelector("[data-copy-install-steps]")?.addEventListener("click", copyInstallSteps);
    document.querySelector("[data-save-policy-controls]")?.addEventListener("click", savePolicyControls);
    document.querySelector("[data-simulator-provider]")?.addEventListener("change", (event) => {
      state.simulatorProvider = event.currentTarget.value;
      state.simulatorPayload = JSON.stringify(simulatorPayloads[state.simulatorProvider] || simulatorPayloads.hubspot, null, 2);
      state.simulatorResult = null;
      renderEmpty();
    });
    document.querySelector("[data-run-adapter-simulator]")?.addEventListener("click", runAdapterSimulator);
  }

  function currentPolicyFromForm() {
    const policy = {};
    document.querySelectorAll("[data-policy-field]").forEach((field) => {
      const key = field.dataset.policyField;
      if (field.type === "checkbox") {
        policy[key] = field.checked;
      } else if (field.type === "number") {
        policy[key] = Number(field.value);
      } else {
        policy[key] = field.value;
      }
    });
    const ruleFamilyModes = {};
    document.querySelectorAll("[data-rule-family-mode]").forEach((field) => {
      ruleFamilyModes[field.dataset.ruleFamilyMode] = field.value;
    });
    if (Object.keys(ruleFamilyModes).length) {
      policy.rule_family_modes = ruleFamilyModes;
    }
    return policy;
  }

  async function savePolicyControls() {
    if (state.policyBusy) return;
    const policy = currentPolicyFromForm();
    state.policyBusy = true;
    state.policyMessage = "Saving governance policy controls...";
    renderEmpty();
    try {
      const response = await apiClient.saveGovernancePolicy?.(policy, {workspace_id: "default"});
      await loadLabData({rerender: false});
      if (state.labData) state.labData.policy = response?.policy || state.labData.policy;
      state.policyMessage = "Governance policy controls saved.";
      announce("Governance policy controls saved.");
    } catch (error) {
      state.policyMessage = error.message || "Governance policy controls could not be saved.";
      apiClient.clientError?.({message: state.policyMessage, source: "governance-policy-controls"}).catch(() => {});
    } finally {
      state.policyBusy = false;
      if (!state.latestData) renderEmpty();
    }
  }

  async function runAdapterSimulator() {
    if (state.simulatorBusy) return;
    const payloadField = document.querySelector("[data-simulator-payload]");
    const providerField = document.querySelector("[data-simulator-provider]");
    state.simulatorPayload = payloadField?.value || "";
    state.simulatorProvider = providerField?.value || state.simulatorProvider;
    let payload;
    try {
      payload = JSON.parse(state.simulatorPayload || "{}");
    } catch (error) {
      state.simulatorMessage = "Payload JSON is not valid.";
      renderEmpty();
      return;
    }
    state.simulatorBusy = true;
    state.simulatorMessage = "Running adapter simulator...";
    renderEmpty();
    try {
      const result = await apiClient.simulateAdapter?.(state.simulatorProvider, payload);
      state.simulatorResult = result || {};
      state.simulatorMessage = `${providerLabel(state.simulatorProvider)} simulator returned ${result?.analysis?.gate?.status || "a decision"}.`;
      announce("Adapter simulator complete.");
    } catch (error) {
      state.simulatorResult = null;
      state.simulatorMessage = error.message || "Adapter simulator could not run.";
      apiClient.clientError?.({message: state.simulatorMessage, source: "adapter-simulator"}).catch(() => {});
    } finally {
      state.simulatorBusy = false;
      if (!state.latestData) renderEmpty();
    }
  }

  async function downloadOpenApiContract() {
    try {
      const spec = await apiClient.openApiContract?.();
      const blob = new Blob([JSON.stringify(spec, null, 2)], {type: "application/json"});
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = "texttraits-v1-openapi.json";
      document.body.appendChild(link);
      link.click();
      const href = link.href;
      link.remove();
      URL.revokeObjectURL(href);
      announce("OpenAPI contract downloaded.");
    } catch (error) {
      state.setupMessage = error.message || "OpenAPI contract could not be downloaded.";
      apiClient.clientError?.({message: state.setupMessage, source: "integration-contract-download"}).catch(() => {});
      renderEmpty();
    }
  }

  async function copyInstallSteps() {
    const kit = state.labData?.installKit || await apiClient.installKit?.();
    const steps = (kit.integration_sequence || []).map((step, index) => `${index + 1}. ${step}`).join("\n");
    try {
      await navigator.clipboard.writeText(steps || "Install kit is unavailable.");
      state.setupMessage = "Integration install steps copied.";
    } catch (error) {
      state.setupMessage = "Clipboard unavailable for install steps.";
    }
    renderEmpty();
  }

  async function saveRecommendedMapping(provider) {
    if (!provider || state.setupBusyProvider) return;
    const manifest = (state.labData?.manifests || []).find((item) => item.provider === provider);
    if (!manifest) {
      state.setupMessage = "That provider manifest is not available yet.";
      renderEmpty();
      return;
    }
    state.setupBusyProvider = provider;
    state.setupMessage = `Saving ${providerLabel(provider)} field mapping...`;
    renderEmpty();
    try {
      await apiClient.saveFieldMapping?.(provider, recommendedMapping(manifest), {workspace_id: "default"});
      await loadLabData({rerender: false});
      state.setupMessage = `${providerLabel(provider)} mapping is ready for workflow routing.`;
    } catch (error) {
      state.setupMessage = error.message || "Field mapping could not be saved.";
      apiClient.clientError?.({message: state.setupMessage, source: "integration-setup"}).catch(() => {});
    } finally {
      state.setupBusyProvider = "";
      if (!state.latestData) renderEmpty();
    }
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
    const score = optimization?.scores?.overall ?? optimization?.score ?? 0;
    const gate = optimization?.policy?.gate || {};
    const readiness = gate.status ? gate.status.replace(/_/g, " ") : optimization?.readiness || "not analyzed";
    return `
      <article class="optimizer-score-card">
        <span class="interface-label">Policy score</span>
        <strong>${escapeHtml(score)}/100</strong>
        <p>${escapeHtml(titleCase(readiness))}</p>
        <div class="score-track" aria-hidden="true">
          <span style="width: ${Math.max(0, Math.min(score, 100))}%"></span>
        </div>
      </article>
    `;
  }

  function checkCards(optimization) {
    const findings = optimization.findings || [];
    if (!findings.length) {
      return `
        <article class="optimizer-check-card is-ok">
          <span class="label">Policy findings</span>
          <strong>No routed findings</strong>
          <p>The current policy bundle did not find a blocking or review-level issue.</p>
          <small>Keep the exported request ID and content hash with the send record.</small>
        </article>
      `;
    }
    return findings.map((finding) => `
      <article class="optimizer-check-card ${finding.severity === "high" || finding.severity === "critical" ? "needs-work" : "is-ok"}">
        <span class="label">${escapeHtml(finding.category)} / ${escapeHtml(finding.severity)}</span>
        <strong>${escapeHtml(finding.title)}</strong>
        <p>${escapeHtml(finding.details || (finding.evidence?.[0]?.text ? `Evidence: ${finding.evidence[0].text}` : "Detected by the policy bundle."))}</p>
        <small>${escapeHtml(finding.remediation)}</small>
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
      api_version: data.api_version,
      request_id: data.request_id,
      content_hash: data.content_hash,
      policy: data.policy,
      scores: data.scores,
      findings: data.findings,
      routes: data.routes,
      model: data.model,
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
        <summary>Raw /v1/email/analyze response</summary>
        <pre>${escapeHtml(JSON.stringify(data, null, 2))}</pre>
      </details>
    `;
  }

  function integrationLab(analysis) {
    const gate = analysis.policy?.gate || {};
    const routes = analysis.routes || [];
    return `
      <section class="optimizer-section integration-lab-section" aria-label="Integration routing">
        <div class="section-title">
          <span class="label">Integration routing</span>
          <strong>Contract fields for workflow systems</strong>
        </div>
        <div class="optimizer-grid integration-lab-grid">
          <article class="optimizer-context-card">
            <span class="interface-label">Request ID</span>
            <strong>${escapeHtml(analysis.request_id)}</strong>
            <p>${escapeHtml(analysis.content_hash)}</p>
          </article>
          <article class="optimizer-context-card">
            <span class="interface-label">Policy bundle</span>
            <strong>${escapeHtml(analysis.policy?.bundle_id || "Policy")}</strong>
            <p>Version ${escapeHtml(analysis.policy?.bundle_version || "n/a")} with ${escapeHtml((analysis.policy?.rule_packs || []).length)} rule packs.</p>
          </article>
          <article class="optimizer-context-card">
            <span class="interface-label">Gate output</span>
            <strong>${escapeHtml(titleCase(gate.status || "unknown"))}</strong>
            <p>${escapeHtml(gate.route || "No route")} / send ready: ${escapeHtml(gate.send_ready ? "yes" : "no")}</p>
          </article>
        </div>
        <div class="optimizer-grid optimizer-check-grid route-grid">
          ${routes.map((route) => `
            <article class="optimizer-check-card is-ok">
              <span class="label">Route</span>
              <strong>${escapeHtml(route.target)}</strong>
              <p>${escapeHtml(route.reason)}</p>
              <small>Mock adapters use this to branch HubSpot workflows, Salesforce journeys, and SendGrid/SES middleware.</small>
            </article>
          `).join("")}
        </div>
      </section>
    `;
  }

  function renderResult(data, optimization) {
    const analysis = optimization || data;
    const predictions = analysis.predictions || {};
    const gate = analysis.policy?.gate || {};
    els.outputPanel.innerHTML = `
      <div class="result-layout optimizer-result fade-in">
        <div class="result-header">
          <div>
            <p class="label">Enterprise email API report</p>
            <h2>Send-readiness gate for the existing draft</h2>
            <p class="muted">No replacement email was generated. The report returns structured findings, routing, content hashes, policy versions, and local model signals.</p>
          </div>
          <div class="toolbar">
            <button class="button-secondary" type="button" data-copy-report>Copy report</button>
            <button class="button-secondary" type="button" data-download-report>Download JSON</button>
          </div>
        </div>

        <section class="optimizer-summary-grid" aria-label="Email optimization summary">
          ${scoreRing(analysis)}
          <article class="optimizer-context-card">
            <span class="interface-label">Draft context</span>
            <strong>${escapeHtml(state.intent)} for ${escapeHtml(state.audience)}</strong>
            <p>${escapeHtml(analysis.stats.words)} words, ${escapeHtml(analysis.stats.sentences)} sentences, ${escapeHtml(state.subject.trim() || "no subject line")}.</p>
          </article>
          <article class="optimizer-context-card">
            <span class="interface-label">Workflow decision</span>
            <strong>${escapeHtml(titleCase(gate.status || "unknown"))}</strong>
            <p>${escapeHtml(gate.route || "No route returned")} from policy bundle ${escapeHtml(analysis.policy?.bundle_version || "n/a")}.</p>
          </article>
        </section>

        <section class="optimizer-section" aria-label="Send readiness checks">
          <div class="section-title">
            <span class="label">Structured findings</span>
            <strong>Severity, category, evidence, remediation</strong>
          </div>
          <div class="optimizer-grid optimizer-check-grid">
            ${checkCards(analysis)}
          </div>
        </section>

        ${integrationLab(analysis)}
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
      const data = await apiClient.analyzeEmail({
        request_id: `ui_${Date.now()}`,
        subject: state.subject,
        body: email,
        audience: state.audience,
        intent: state.intent,
        channel: "ui_enterprise_optimizer",
        policy_bundle: state.policyBundle,
      });
      state.latestData = data;
      state.latestOptimization = data;
      state.latestError = "";
      renderResult(data, data);
      loadLabData({rerender: false});
      trackEvent("enterprise_email_optimization", {words: data.stats.words, score: data.scores.overall, gate: data.policy?.gate?.status});
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
    loadLabData({rerender: true});
    announce("TextTraits enterprise email optimizer ready.");
  }

  async function loadLabData({rerender = false} = {}) {
    try {
      const [flowData, dashboard, manifestData, installKit, policyData, integrationPlan] = await Promise.all([
        apiClient.integrationFlows?.(),
        apiClient.governanceDashboard?.(),
        apiClient.integrationManifests?.(),
        apiClient.installKit?.(),
        apiClient.governancePolicy?.(),
        apiClient.enterpriseIntegrationPlan?.(),
      ]);
      state.labData = {
        flows: flowData?.flows || [],
        dashboard: dashboard || {},
        manifests: manifestData?.manifests || [],
        fieldMappings: manifestData?.field_mappings || [],
        installKit: installKit || {},
        policy: policyData?.policy || dashboard?.policy || {},
        integrationPlan: integrationPlan || dashboard?.enterprise_integration_plan || {},
      };
      state.labError = "";
    } catch (error) {
      state.labError = error.message || "Integration lab status is unavailable.";
    }
    if (rerender && !state.latestData) renderEmpty();
  }

  init();
})();
