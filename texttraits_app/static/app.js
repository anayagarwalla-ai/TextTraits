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
    workspaceId: "default",
    policyEnvironment: "production",
    adminMessage: "",
    apiKeyMessage: "",
    webhookMessage: "",
    approvalMessage: "",
    exportScheduleMessage: "",
    dashboardFilters: {
      date_range: "30d",
      source_system: "all",
      campaign_id: "",
      template_id: "",
      gate_status: "all",
    },
    enterpriseContext: {
      source_system: "ui_enterprise_optimizer",
      analysis_mode: "pre_send_gate",
      campaign_id: "",
      journey_id: "",
      template_id: "",
      locale: "en-US",
      headers: '{\n  "List-Unsubscribe": "<https://example.test/unsubscribe>"\n}',
      personalization_context: '{\n  "first_name": "Maya",\n  "company": "Acme"\n}',
      consent_state: "subscribed",
      delivery_provider: "ui",
    },
    renderBusy: false,
    renderMessage: "",
    renderResult: null,
    policyBusy: false,
    policyMessage: "",
    simulatorProvider: "hubspot",
    simulatorPayload: "",
    simulatorBusy: false,
    simulatorMessage: "",
    simulatorResult: null,
    exportBusy: "",
    exportMessage: "",
    exportResult: null,
    setupBusyProvider: "",
    setupProvider: "hubspot",
    setupValidationMessage: "",
    setupTestMessage: "",
    promotedProviders: [],
    apiKeys: [],
    apiKeyForm: {
      name: "Sandbox workflow key",
      scopes: "default:/v1/email/analyze, default:/v1/governance",
      environment: "sandbox",
    },
    webhookConfig: {
      endpoint: "/v1/webhooks/post-send",
      status: "Needs signing secret",
      secretDigest: "",
      lastTest: "",
      signaturePreview: "",
      eventType: "delivered",
    },
    webhookSecretDraft: "",
    approvalActions: {},
    exportSchedule: {
      enabled: false,
      cadence: "weekly",
      kind: "analyses",
      format: "csv",
      recipients: "",
      lastSaved: "",
    },
    setupMessage: "",
    profileTranscript: "",
    profileAccount: "",
    profileGoal: "Recommend the next best outreach angle",
    profileBusy: false,
    profileMessage: "",
    profileResult: null,
    workflowProvider: "hubspot",
    workflowScenario: "governance-nurture",
    workflowBusy: false,
    workflowMessage: "",
    workflowProfile: null,
    workflowAdapterResult: null,
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
  const profileSamples = [
    {
      label: "Revenue leader",
      goal: "Book a workflow-fit pilot discussion",
      account: "B2B SaaS account using Salesforce, Outreach, RevOps weekly forecast reviews, and manager coaching workflows.",
      transcript: "The VP Sales said forecast surprises and late renewal risk are the biggest issue. They asked whether TextTraits works inside Salesforce and Outreach without creating another tool. Security review matters before rollout, but they are open to a pilot if it shows manager coaching moments earlier.",
    },
    {
      label: "Marketing ops",
      goal: "Route to governance-first nurture",
      account: "Lifecycle marketing team using HubSpot workflows, campaign approvals, and legal review before outbound launches.",
      transcript: "Marketing operations is worried about another tool, adoption, policy gates, and audit trails. They asked for a HubSpot workflow action, clear consent handling, and proof that the product will not store raw inbox history before procurement.",
    },
  ];
  const workflowProviders = [
    {value: "hubspot", label: "HubSpot", layer: "Workflow custom action", surface: "Contact workflow step"},
    {value: "salesforce", label: "Salesforce", layer: "Journey Builder activity", surface: "Lead and campaign member fields"},
    {value: "marketo", label: "Marketo", layer: "Smart Campaign gate", surface: "Program asset review"},
    {value: "braze", label: "Braze", layer: "Canvas webhook step", surface: "Lifecycle journey branch"},
    {value: "sendgrid_ses", label: "SendGrid / SES", layer: "Pre-send middleware", surface: "Send API proxy"},
  ];
  const workflowScenarios = [
    {
      id: "governance-nurture",
      label: "Governance nurture",
      provider: "hubspot",
      audience: "Marketing operations",
      goal: "Route to governance-first nurture",
      account: "Lifecycle marketing team using HubSpot workflows, campaign approvals, and legal review before outbound launches.",
      transcript: "Marketing operations is worried about another tool, adoption, policy gates, audit trails, consent handling, and proof that the product will not store raw inbox history before procurement.",
      subject: "Governance-first workflow pilot",
      body: "Hi Maya, your team asked whether TextTraits can fit inside HubSpot without storing raw inbox history. The cleanest next step is a workflow-action pilot that writes back score, route, and objection signals while keeping raw message bodies out of governance storage. Would a sandbox review next week help?",
      fit: 0.82,
      governance: 0.91,
      urgency: 0.62,
      expectedDisplay: "Show governance-first nurture route, policy evidence, and writeback fields inside the workflow builder.",
    },
    {
      id: "pipeline-risk",
      label: "Pipeline risk",
      provider: "salesforce",
      audience: "Revenue operations",
      goal: "Book a workflow-fit pilot discussion",
      account: "B2B SaaS account using Salesforce, Outreach, RevOps weekly forecast reviews, and manager coaching workflows.",
      transcript: "The VP Sales said forecast surprises and late renewal risk are the biggest issue. They asked whether TextTraits works inside Salesforce and Outreach without creating another tool. Security review matters before rollout, but they are open to a pilot if it shows manager coaching moments earlier.",
      subject: "Forecast risk visibility pilot",
      body: "Hi Jordan, the clearest fit I heard was earlier visibility into forecast surprises and renewal risk. TextTraits can start as a Salesforce Journey Builder activity that flags coaching moments and writes back next-best-action fields without asking your managers to open another tool. Should we test that against one renewal workflow?",
      fit: 0.88,
      governance: 0.74,
      urgency: 0.86,
      expectedDisplay: "Show pipeline-risk priority, security-review objection, and manager-coaching next action inside CRM.",
    },
    {
      id: "campaign-review",
      label: "Campaign review",
      provider: "marketo",
      audience: "Demand generation",
      goal: "Hold risky campaign assets for review",
      account: "Demand generation team using Marketo programs, regional templates, and legal approval before event outreach.",
      transcript: "The campaign manager said they need faster asset review, cleaner segmentation evidence, and fewer last-minute legal escalations. They asked for a program-level gate and an audit trail that explains why an email should be reviewed before launch.",
      subject: "Program-level review gate",
      body: "Hi Priya, your team described the review bottleneck as a program-level governance problem. TextTraits can run as a Marketo Smart Campaign gate that routes risky assets to review and writes back why the message needs attention. Could we test this on one event program?",
      fit: 0.79,
      governance: 0.88,
      urgency: 0.69,
      expectedDisplay: "Show review gate status, audit reason, and campaign field mapping for a launch manager.",
    },
  ];
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
  const statusLabels = {
    ready: "Ready",
    sandbox: "Sandbox",
    configured: "Configured",
    needs_mapping: "Needs mapping",
    production_blocked: "Production blocked",
    needs_review: "Needs review",
    blocked: "Blocked",
    fail_open: "Fail open",
    fail_closed: "Fail closed",
    review: "Review",
    human_review_queue: "Human review queue",
    approved_to_send: "Approved to send",
    compliance_or_manager_review: "Compliance or manager review",
    forward_to_provider: "Forward to provider",
    hold_for_review: "Hold for review",
    metadata_only: "Metadata only",
    hash_only: "Hash only",
    pre_send_gate: "Pre-send gate",
    send_path_middleware: "Send-path middleware",
    post_send_analytics: "Post-send analytics",
    authoring_lint: "Authoring lint",
    batch_feedback: "Batch feedback",
    direct_api: "Direct API",
  };
  const ownerByCategory = {
    compliance: "Compliance owner",
    unsubscribe: "Lifecycle operations",
    personalization: "Marketing operations",
    cta: "Campaign owner",
    clarity: "Content reviewer",
    specificity: "Campaign owner",
    format: "Deliverability owner",
    subject: "Campaign owner",
  };
  const roleProfiles = [
    {role: "Admin", detail: "Owns workspace setup, environments, key profiles, webhooks, and policy promotion.", permissions: ["Manage policy", "Manage integrations", "Export governance data", "Approve promotion"]},
    {role: "Reviewer", detail: "Reviews routed messages, resolves findings, and approves or holds sends.", permissions: ["Review findings", "Approve or hold", "Add notes"]},
    {role: "Analyst", detail: "Reads governance dashboards, outcome trends, exports, and model-performance context.", permissions: ["View dashboards", "Download exports", "Inspect trends"]},
    {role: "Developer", detail: "Validates payloads, mapping contracts, sandbox adapters, API scopes, and webhook signatures.", permissions: ["Run simulator", "Manage key profiles", "Test webhooks"]},
  ];
  const deploymentChecks = [
    ["Secrets", "TEXTTRAITS_SECRET_KEY, API keys, webhook signing secrets, and OAuth client secrets are managed outside source control."],
    ["Postgres", "Production uses hosted Postgres with SSL instead of local SQLite."],
    ["HTTPS", "Public base URL is HTTPS and secure cookies are enabled."],
    ["Workers", "Gunicorn or an equivalent WSGI runner is configured behind the hosting platform."],
    ["Monitoring", "Error reporting, request logs, and latency alerts are connected before launch."],
    ["Backups", "Database backups, retention windows, and restore testing are owned by an admin."],
  ];

  hydrateLocalAdminState();

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

  function displayLabel(value) {
    const clean = String(value ?? "").trim();
    if (!clean) return "Not set";
    const key = clean.toLowerCase();
    if (statusLabels[key]) return statusLabels[key];
    return key
      .replace(/[_-]+/g, " ")
      .replace(/\b\w/g, (letter) => letter.toUpperCase())
      .replace(/\bApi\b/g, "API")
      .replace(/\bSes\b/g, "SES")
      .replace(/\bCta\b/g, "CTA");
  }

  function shortHash(value) {
    const clean = String(value || "");
    return clean.length > 22 ? `${clean.slice(0, 18)}...` : clean || "n/a";
  }

  function cssEscape(value) {
    return window.CSS?.escape ? window.CSS.escape(String(value)) : String(value).replace(/["\\]/g, "\\$&");
  }

  function statusBadge(label, tone = "neutral") {
    return `<span class="status-badge status-${escapeHtml(tone)}">${escapeHtml(label)}</span>`;
  }

  function readLocalSetting(key, fallback) {
    try {
      const raw = window.localStorage?.getItem(`texttraits.enterprise.${key}`);
      return raw ? JSON.parse(raw) : fallback;
    } catch (error) {
      return fallback;
    }
  }

  function writeLocalSetting(key, value) {
    try {
      window.localStorage?.setItem(`texttraits.enterprise.${key}`, JSON.stringify(value));
    } catch (error) {
      state.adminMessage = "Local browser storage is unavailable; settings will reset on refresh.";
    }
  }

  function defaultApiKeys() {
    return [
      {
        id: "sbx_default_governance",
        name: "Sandbox governance key",
        environment: "sandbox",
        scopes: ["default:/v1/email/analyze", "default:/v1/governance"],
        status: "Sandbox",
        secretPreview: "No credential material stored",
        created_at: new Date().toISOString(),
        last_used: "Not used",
      },
    ];
  }

  function normalizeLocalKeyProfile(profile) {
    return {
      ...(profile || {}),
      secretPreview: "No credential material stored",
    };
  }

  function hydrateLocalAdminState() {
    state.apiKeys = readLocalSetting("apiKeys", defaultApiKeys()).map(normalizeLocalKeyProfile);
    state.webhookConfig = readLocalSetting("webhookConfig", state.webhookConfig);
    state.approvalActions = readLocalSetting("approvalActions", {});
    state.exportSchedule = readLocalSetting("exportSchedule", state.exportSchedule);
    state.promotedProviders = readLocalSetting("promotedProviders", []);
  }

  function persistLocalAdminState() {
    writeLocalSetting("apiKeys", state.apiKeys);
    writeLocalSetting("webhookConfig", state.webhookConfig);
    writeLocalSetting("approvalActions", state.approvalActions);
    writeLocalSetting("exportSchedule", state.exportSchedule);
    writeLocalSetting("promotedProviders", state.promotedProviders);
  }

  function parseJsonObject(value, fallback = {}) {
    const clean = String(value || "").trim();
    if (!clean) return fallback;
    const parsed = JSON.parse(clean);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error("Expected a JSON object.");
    }
    return parsed;
  }

  function currentEnterpriseContext() {
    const context = state.enterpriseContext;
    return {
      workspace_id: state.workspaceId || "default",
      source_system: context.source_system || "ui_enterprise_optimizer",
      analysis_mode: context.analysis_mode || "pre_send_gate",
      campaign_id: context.campaign_id || "",
      journey_id: context.journey_id || "",
      template_id: context.template_id || "",
      locale: context.locale || "",
      headers: parseJsonObject(context.headers, {}),
      personalization_context: parseJsonObject(context.personalization_context, {}),
      consent_context: {state: context.consent_state || "unknown"},
      delivery_context: {provider: context.delivery_provider || context.source_system || "ui"},
    };
  }

  function renderTestSummary(result) {
    const test = result?.render_test || result || {};
    const unresolved = test.unresolved_tokens || [];
    const unsubscribe = test.unsubscribe || {};
    return `
      <div class="render-test-summary">
        ${statusBadge(unresolved.length ? `${unresolved.length} unresolved token${unresolved.length === 1 ? "" : "s"}` : "Tokens resolved", unresolved.length ? "warning" : "success")}
        ${statusBadge(unsubscribe.header_present ? "List-Unsubscribe header" : "No List-Unsubscribe header", unsubscribe.header_present ? "success" : "warning")}
        ${statusBadge(`${test.link_count || 0} links`, "neutral")}
        ${unresolved.length ? `<small>First unresolved token: ${escapeHtml(unresolved[0].token || unresolved[0].key || "unknown")}</small>` : `<small>Template preview is safe to analyze with the supplied sample context.</small>`}
      </div>
    `;
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

  function profileBuilder() {
    const stats = localStats(state.profileTranscript);
    return `
      <section class="b2b-profile-builder" aria-label="B2B profile intelligence">
        <div class="panel-head">
          <div>
            <span class="interface-label">B2B profile intelligence</span>
            <h2>Build a business profile</h2>
            <p class="helper">Paste consented communication history. TextTraits extracts non-sensitive business signals for outreach strategy and CRM routing.</p>
          </div>
        </div>
        <label class="field">
          <span>Campaign goal</span>
          <input id="profile-goal" type="text" value="${escapeHtml(state.profileGoal)}" placeholder="e.g. Book a security review follow-up">
        </label>
        <label class="field">
          <span>Account context</span>
          <textarea id="profile-account" class="compact-profile-textarea" placeholder="CRM notes, account stage, tools, industry, or current workflow.">${escapeHtml(state.profileAccount)}</textarea>
        </label>
        <label class="field">
          <span>Communication history</span>
          <textarea id="profile-transcript" class="profile-transcript" placeholder="Paste a consented transcript or communication history.">${escapeHtml(state.profileTranscript)}</textarea>
        </label>
        <div class="quality-row">
          <span>${escapeHtml(stats.words)} words</span>
          <span>Raw identifiers are counted, redacted, and not returned.</span>
        </div>
        <div class="sample-grid optimizer-samples" aria-label="Example B2B profiles">
          ${profileSamples.map((sample, index) => `
            <button class="sample-card" type="button" data-profile-sample="${index}">
              <strong>${escapeHtml(sample.label)}</strong>
              <span>${escapeHtml(localStats(sample.transcript).words)} words</span>
            </button>
          `).join("")}
        </div>
        ${state.profileMessage ? `<p class="setup-message">${escapeHtml(state.profileMessage)}</p>` : ""}
        <div class="action-row optimizer-actions">
          <button type="button" data-build-profile ${state.profileTranscript.trim() && !state.profileBusy ? "" : "disabled"}>${state.profileBusy ? "Building profile..." : "Build relationship profile"}</button>
          <button class="button-secondary" type="button" data-clear-profile ${state.profileTranscript || state.profileAccount ? "" : "disabled"}>Clear profile</button>
        </div>
      </section>
    `;
  }

  function signalCards(items = [], empty = "No strong signal detected yet.") {
    if (!items.length) return `<p class="muted">${escapeHtml(empty)}</p>`;
    return `
      <div class="optimizer-grid profile-card-grid">
        ${items.map((item) => `
          <article class="profile-signal-card">
            <span class="label">${escapeHtml(item.category || "Signal")}</span>
            <strong>${escapeHtml(item.label)}</strong>
            <p>${escapeHtml(item.sales_use || item.avoid || "")}</p>
            <small>${escapeHtml(item.evidence_terms?.length ? `Evidence: ${item.evidence_terms.join(", ")}` : `Confidence ${percent(item.confidence || 0)}`)}</small>
          </article>
        `).join("")}
      </div>
    `;
  }

  function b2bProfileReport() {
    const profile = state.profileResult;
    if (!profile) {
      return `
        <section class="optimizer-section b2b-profile-report" aria-label="B2B profile report">
          <div class="section-title">
            <span class="label">B2B profile report</span>
            <strong>Relationship intelligence appears after you build a profile</strong>
          </div>
          <p class="muted">The report is designed for marketing and sales teams that need a safer brief for outreach strategy, not hidden PII extraction.</p>
        </section>
      `;
    }
    const business = profile.business_profile || {};
    const strategy = profile.resonance_strategy || {};
    const privacy = profile.privacy || {};
    return `
      <section class="optimizer-section b2b-profile-report" aria-label="B2B profile report">
        <div class="section-title">
          <span class="label">B2B profile report</span>
          <strong>${escapeHtml(business.buying_stage || "Business profile")}</strong>
        </div>
        <div class="optimizer-summary-grid profile-summary-grid">
          <article class="optimizer-context-card">
            <span class="interface-label">Next best action</span>
            <strong>${escapeHtml(business.next_best_action || "Review account context")}</strong>
            <p>${escapeHtml(profile.campaign_goal || state.profileGoal)}</p>
          </article>
          <article class="optimizer-context-card">
            <span class="interface-label">Privacy mode</span>
            <strong>${escapeHtml(displayLabel(privacy.mode || "minimized"))}</strong>
            <p>Identifiers returned: ${escapeHtml(privacy.raw_identifiers_returned ? "Yes" : "No")} / sensitive inference: ${escapeHtml(privacy.sensitive_attribute_inference || "disabled")}</p>
          </article>
          <article class="optimizer-context-card">
            <span class="interface-label">Activation</span>
            <strong>${escapeHtml((profile.activation?.crm_fields || []).slice(0, 2).join(", ") || "CRM fields")}</strong>
            <p>${escapeHtml((profile.activation?.workflow_uses || [])[0] || "Route profile to the right workflow.")}</p>
          </article>
        </div>
        <div class="profile-report-grid">
          <article>
            <div class="section-title">
              <span class="label">Business priorities</span>
              <strong>What should resonate</strong>
            </div>
            ${signalCards(business.business_priorities || [], "No clear business priority detected.")}
          </article>
          <article>
            <div class="section-title">
              <span class="label">Objections</span>
              <strong>What to handle carefully</strong>
            </div>
            ${signalCards(business.detected_objections || [], "No explicit objection detected.")}
          </article>
        </div>
        <div class="profile-playbook">
          <article>
            <span class="label">Recommended angles</span>
            <ul>${(strategy.recommended_angles || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
          </article>
          <article>
            <span class="label">Avoid</span>
            <ul>${(strategy.avoid || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
          </article>
          <article>
            <span class="label">Generation guardrails</span>
            <ul>${(strategy.message_guidance || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
          </article>
        </div>
        <details class="secondary-result-details optimizer-json">
          <summary>Safe feature payload</summary>
          <pre>${escapeHtml(JSON.stringify(profile.safe_features || {}, null, 2))}</pre>
        </details>
      </section>
    `;
  }

  function selectedWorkflowScenario() {
    return workflowScenarios.find((scenario) => scenario.id === state.workflowScenario) || workflowScenarios[0];
  }

  function selectedWorkflowProvider() {
    return workflowProviders.find((provider) => provider.value === state.workflowProvider) || workflowProviders[0];
  }

  function workflowPayload(scenario, provider) {
    const base = {
      workspace_id: state.workspaceId || "default",
      source_system: provider,
      analysis_mode: "pre_send_gate",
      campaign_id: `cmp_${scenario.id.replace(/-/g, "_")}`,
      template_id: `tmpl_${provider}_${scenario.id.replace(/-/g, "_")}`,
      subject: scenario.subject,
      body: scenario.body,
      audience: scenario.audience,
      intent: scenario.goal,
      headers: {"List-Unsubscribe": "<https://example.test/unsubscribe>"},
      personalization_context: {first_name: "Maya", company: "Example account"},
      consent_context: {state: "subscribed", lawful_basis: "business_relationship"},
    };
    if (provider === "hubspot") {
      return {
        ...base,
        inputFields: {
          email_subject: scenario.subject,
          email_body: scenario.body,
          lifecyclestage: scenario.audience,
          workflow_name: scenario.goal,
        },
      };
    }
    if (provider === "salesforce") {
      return {
        ...base,
        inArguments: [{
          EmailSubject: scenario.subject,
          EmailBody: scenario.body,
          ContactType: scenario.audience,
          JourneyName: scenario.goal,
        }],
      };
    }
    if (provider === "sendgrid_ses") {
      return {
        ...base,
        message: {
          subject: scenario.subject,
          text: scenario.body,
          audience: scenario.audience,
          intent: scenario.goal,
        },
      };
    }
    if (provider === "braze") {
      return {
        ...base,
        canvas_step: {
          subject: scenario.subject,
          body: scenario.body,
          template_id: base.template_id,
        },
      };
    }
    if (provider === "marketo") {
      return {
        ...base,
        asset: {
          subject: scenario.subject,
          html: scenario.body,
          program_id: base.campaign_id,
          id: base.template_id,
        },
      };
    }
    return base;
  }

  function primaryWorkflowSignal(profile, key, fallback) {
    const business = profile?.business_profile || {};
    const items = key === "objection" ? business.detected_objections : business.business_priorities;
    return (items || [])[0]?.label || fallback;
  }

  function workflowScoreRows(profile, scenario) {
    const privacy = profile?.privacy || {};
    return [
      {
        label: "Workflow fit",
        value: scenario.fit,
        note: primaryWorkflowSignal(profile, "priority", "Integration and workflow fit"),
      },
      {
        label: "Governance need",
        value: scenario.governance,
        note: privacy.sensitive_attribute_inference === "disabled" ? "Sensitive inference disabled" : "Check governance mode",
      },
      {
        label: "Revenue urgency",
        value: scenario.urgency,
        note: primaryWorkflowSignal(profile, "objection", "No explicit objection yet"),
      },
    ];
  }

  function scoreBucketClass(value) {
    const bucket = Math.max(0, Math.min(100, Math.round(Number(value || 0) * 10) * 10));
    return `score-bucket-${bucket}`;
  }

  function workflowScoreBars(profile, scenario) {
    return `
      <div class="workflow-score-list" aria-label="Workflow fit metrics">
        ${workflowScoreRows(profile, scenario).map((row) => `
          <div class="workflow-score-row">
            <span>${escapeHtml(row.label)}</span>
            <div class="workflow-score-bar" aria-hidden="true"><b class="${escapeHtml(scoreBucketClass(row.value))}"></b></div>
            <strong>${escapeHtml(percent(row.value))}</strong>
            <small>${escapeHtml(row.note)}</small>
          </div>
        `).join("")}
      </div>
    `;
  }

  function workflowTimeline(profile, adapter, provider) {
    const business = profile?.business_profile || {};
    const gate = adapter?.analysis?.gate || {};
    const writeback = adapter?.writeback || {};
    const steps = [
      ["1", "Consent-safe history", profile ? "Profile input minimized and identifiers suppressed." : "Load a scenario or paste consented context."],
      ["2", "Business profile", business.buying_stage || "Awaiting profile run"],
      ["3", `${provider.label} adapter`, gate.status ? `${displayLabel(gate.status)} -> ${displayLabel(gate.route)}` : provider.layer],
      ["4", "Writeback", writeback.texttraits_score !== undefined ? `${writeback.texttraits_score}/100 with request hash` : "Score, route, priority, and next action"],
    ];
    return `
      <ol class="workflow-timeline" aria-label="Simulation timeline">
        ${steps.map(([number, title, detail]) => `
          <li>
            <span>${escapeHtml(number)}</span>
            <strong>${escapeHtml(title)}</strong>
            <p>${escapeHtml(detail)}</p>
          </li>
        `).join("")}
      </ol>
    `;
  }

  function workflowWritebackFields(profile, adapter) {
    const activationFields = profile?.activation?.crm_fields || [];
    const adapterFields = Object.keys(adapter?.writeback || {});
    const fields = Array.from(new Set([...activationFields, ...adapterFields])).slice(0, 8);
    if (!fields.length) {
      return ["texttraits_buying_stage", "texttraits_priority_signal", "texttraits_next_best_action", "texttraits_gate"];
    }
    return fields;
  }

  function workflowGuardrails(profile) {
    return profile?.resonance_strategy?.message_guidance || [
      "Use business priorities, not demographic or sensitive personal inference.",
      "Reference the workflow problem the account already raised.",
      "Keep raw communication history out of prompt context.",
    ];
  }

  function revenueSignalLab() {
    const scenario = selectedWorkflowScenario();
    const provider = selectedWorkflowProvider();
    const profile = state.workflowProfile;
    const adapter = state.workflowAdapterResult;
    const business = profile?.business_profile || {};
    const strategy = profile?.resonance_strategy || {};
    const gate = adapter?.analysis?.gate || {};
    const writeback = workflowWritebackFields(profile, adapter);
    return `
      <section id="revenue-lab-section" class="revenue-signal-lab" aria-label="Revenue Signal Lab">
        <div class="revenue-lab-hero">
          <div>
            <span class="interface-label">Revenue Signal Lab</span>
            <h2>Simulate the B2B workflow before a real integration exists.</h2>
            <p>Choose a platform and account scenario, then run the same profile and adapter calls a marketing or revenue team would use inside their workflow builder.</p>
          </div>
          <div class="lab-proof-stack" aria-label="Simulation safeguards">
            ${statusBadge("No raw PII returned", "success")}
            ${statusBadge("Sandbox only", "warning")}
            ${statusBadge(provider.label, "neutral")}
          </div>
        </div>
        <div class="revenue-lab-grid">
          <article class="workflow-control-panel">
            <div class="section-title">
              <span class="label">Simulate workflow</span>
              <strong>${escapeHtml(provider.layer)}</strong>
            </div>
            <label class="policy-control">
              <span>Business platform</span>
              <select data-workflow-provider>
                ${workflowProviders.map((item) => `<option value="${escapeHtml(item.value)}" ${item.value === state.workflowProvider ? "selected" : ""}>${escapeHtml(item.label)}</option>`).join("")}
              </select>
              <small>${escapeHtml(provider.surface)}</small>
            </label>
            <div class="workflow-scenario-grid" aria-label="Workflow scenarios">
              ${workflowScenarios.map((item) => `
                <button class="workflow-scenario-card ${item.id === scenario.id ? "is-selected" : ""}" type="button" data-workflow-scenario="${escapeHtml(item.id)}" aria-pressed="${item.id === scenario.id ? "true" : "false"}">
                  <span>${escapeHtml(item.audience)}</span>
                  <strong>${escapeHtml(item.label)}</strong>
                  <small>${escapeHtml(item.goal)}</small>
                </button>
              `).join("")}
            </div>
            <div class="workflow-input-preview">
              <span class="interface-label">Scenario input</span>
              <strong>${escapeHtml(scenario.goal)}</strong>
              <p>${escapeHtml(scenario.account)}</p>
              <small>${escapeHtml(scenario.expectedDisplay)}</small>
            </div>
            ${state.workflowMessage ? `<p class="setup-message">${escapeHtml(state.workflowMessage)}</p>` : ""}
            <div class="setup-action-row">
              <button type="button" data-run-workflow-lab ${state.workflowBusy ? "disabled" : ""}>${state.workflowBusy ? "Running simulation..." : "Run workflow simulation"}</button>
              <button class="button-secondary" type="button" data-load-workflow-profile>Load in profile builder</button>
            </div>
          </article>
          <article class="workflow-result-panel">
            <div class="section-title">
              <span class="label">Business profile</span>
              <strong>${escapeHtml(business.buying_stage || "Ready to simulate")}</strong>
            </div>
            <div class="workflow-decision-row">
              <div>
                <span>Next best action</span>
                <strong>${escapeHtml(business.next_best_action || "Run a sandbox profile to produce the buyer-facing action.")}</strong>
              </div>
              <div>
                <span>Adapter decision</span>
                <strong>${escapeHtml(gate.status ? `${displayLabel(gate.status)} / ${displayLabel(gate.route)}` : "Not run yet")}</strong>
              </div>
            </div>
            ${workflowScoreBars(profile, scenario)}
            <div class="workflow-output-columns">
              <div>
                <span class="interface-label">Writeback fields</span>
                <ul>${writeback.map((field) => `<li>${escapeHtml(field)}</li>`).join("")}</ul>
              </div>
              <div>
                <span class="interface-label">Message guardrails</span>
                <ul>${workflowGuardrails(profile).slice(0, 4).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
              </div>
            </div>
            ${strategy.recommended_angles?.length ? `
              <div class="workflow-angle-note">
                <span>Recommended angle</span>
                <strong>${escapeHtml(strategy.recommended_angles[0])}</strong>
              </div>
            ` : ""}
          </article>
        </div>
        <div class="workflow-timeline-shell">
          <div class="section-title">
            <span class="label">What the platform user sees</span>
            <strong>Profile, score, route, and writeback preview</strong>
          </div>
          ${workflowTimeline(profile, adapter, provider)}
        </div>
      </section>
    `;
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

        <div class="enterprise-context-strip" aria-label="Workspace and environment">
          <label class="field">
            <span>Workspace</span>
            <input id="workspace-id" type="text" value="${escapeHtml(state.workspaceId)}" placeholder="default">
          </label>
          <label class="field">
            <span>Environment</span>
            <select id="policy-environment">
              ${["sandbox", "staging", "production"].map((env) => `<option value="${env}" ${env === state.policyEnvironment ? "selected" : ""}>${escapeHtml(displayLabel(env))}</option>`).join("")}
            </select>
          </label>
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

        <details class="enterprise-context-panel">
          <summary>
            <span>Enterprise context fields</span>
            <small>Campaign, template, headers, consent, and personalization context</small>
          </summary>
          <div class="field-grid optimizer-field-grid">
            <label class="field">
              <span>Source system</span>
              <select data-enterprise-context="source_system">
                ${["ui_enterprise_optimizer", "hubspot", "salesforce", "braze", "marketo", "iterable", "sendgrid_ses", "warehouse"].map((item) => `<option value="${item}" ${item === state.enterpriseContext.source_system ? "selected" : ""}>${escapeHtml(displayLabel(item))}</option>`).join("")}
              </select>
            </label>
            <label class="field">
              <span>Analysis mode</span>
              <select data-enterprise-context="analysis_mode">
                ${["pre_send_gate", "authoring_lint", "send_path_middleware", "post_send_analytics", "batch_feedback", "direct_api"].map((item) => `<option value="${item}" ${item === state.enterpriseContext.analysis_mode ? "selected" : ""}>${escapeHtml(displayLabel(item))}</option>`).join("")}
              </select>
            </label>
            <label class="field">
              <span>Campaign ID</span>
              <input type="text" data-enterprise-context="campaign_id" value="${escapeHtml(state.enterpriseContext.campaign_id)}" placeholder="cmp_q3_pipeline">
            </label>
            <label class="field">
              <span>Journey ID</span>
              <input type="text" data-enterprise-context="journey_id" value="${escapeHtml(state.enterpriseContext.journey_id)}" placeholder="journey_42">
            </label>
            <label class="field">
              <span>Template ID</span>
              <input type="text" data-enterprise-context="template_id" value="${escapeHtml(state.enterpriseContext.template_id)}" placeholder="tmpl_119028">
            </label>
            <label class="field">
              <span>Locale</span>
              <input type="text" data-enterprise-context="locale" value="${escapeHtml(state.enterpriseContext.locale)}" placeholder="en-US">
            </label>
            <label class="field">
              <span>Consent state</span>
              <select data-enterprise-context="consent_state">
                ${["subscribed", "suppressed", "unknown"].map((item) => `<option value="${item}" ${item === state.enterpriseContext.consent_state ? "selected" : ""}>${escapeHtml(displayLabel(item))}</option>`).join("")}
              </select>
            </label>
            <label class="field">
              <span>Delivery provider</span>
              <input type="text" data-enterprise-context="delivery_provider" value="${escapeHtml(state.enterpriseContext.delivery_provider)}" placeholder="sendgrid">
            </label>
          </div>
          <label class="field">
            <span>Headers JSON</span>
            <textarea class="json-field" data-enterprise-context="headers" spellcheck="false">${escapeHtml(state.enterpriseContext.headers)}</textarea>
          </label>
          <label class="field">
            <span>Personalization context JSON</span>
            <textarea class="json-field" data-enterprise-context="personalization_context" spellcheck="false">${escapeHtml(state.enterpriseContext.personalization_context)}</textarea>
          </label>
        </details>

        <section class="render-test-card" aria-label="Rendered-template test">
          <div>
            <span class="interface-label">Rendered-template test</span>
            <strong>Check Liquid and Handlebars tokens before scoring</strong>
            <p class="helper">Runs the current subject, body, headers, and sample recipient context through the template harness.</p>
          </div>
          ${state.renderMessage ? `<p class="setup-message">${escapeHtml(state.renderMessage)}</p>` : ""}
          ${state.renderResult ? renderTestSummary(state.renderResult) : ""}
          <button class="button-secondary" type="button" data-run-render-test ${state.renderBusy || !state.email.trim() ? "disabled" : ""}>
            ${state.renderBusy ? "Testing tokens..." : "Run render test"}
          </button>
        </section>

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
      ${profileBuilder()}
    `;
    bindInput();
    bindProfileControls();
  }

  function renderEmpty() {
    els.outputPanel.innerHTML = `
      <div class="empty-layout fade-in optimizer-empty">
        ${revenueSignalLab()}
        <section class="empty-hero optimizer-hero-card">
          <span class="status-pill">Enterprise integration lab</span>
          <h2>Policy-backed email analysis will appear here.</h2>
          <p class="muted">This version is built for teams that already have email tools and need objective review before messages enter a workflow, journey, or sending system.</p>
        </section>
        <section class="optimizer-grid optimizer-grid-compact">
          ${[
            ["Stable contract", "/v1/email/analyze"],
            ["Policy gate", "Ready, review, or block"],
            ["Sandbox adapters", "HubSpot, Salesforce, SendGrid/SES"],
            ["Governance", "Hashes, versions, dedupe"],
          ].map(([label, value]) => `
            <article class="metric-card">
              <span>${escapeHtml(label)}</span>
              <strong>${escapeHtml(value)}</strong>
            </article>
          `).join("")}
        </section>
        ${labOverview()}
        ${b2bProfileReport()}
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

  function providerConnectionState(manifest, mapping) {
    const provider = manifest?.provider || "";
    if (state.promotedProviders.includes(provider) && mapping?.status === "ready") {
      return {label: "Ready", tone: "success", detail: "Mapped, tested, and promoted for production routing."};
    }
    if ((state.policyEnvironment || "").toLowerCase() === "production" && mapping?.status !== "ready") {
      return {label: "Production blocked", tone: "danger", detail: "Production cannot be promoted until required fields are mapped and tested."};
    }
    if (mapping?.status === "ready") {
      return {label: "Configured", tone: "success", detail: "Field mapping is saved and ready for sandbox validation."};
    }
    return {label: "Needs mapping", tone: "warning", detail: "Save a provider mapping before using this adapter in a workflow."};
  }

  function aggregateRows(rows, key, fallback = "Not set") {
    return Array.from((rows || []).reduce((map, row) => {
      const value = String(row?.[key] || fallback);
      map.set(value, (map.get(value) || 0) + 1);
      return map;
    }, new Map()).entries())
      .map(([label, count]) => ({label, count}))
      .sort((a, b) => b.count - a.count);
  }

  function filterAnalyses(analyses = []) {
    const filters = state.dashboardFilters;
    const now = Date.now();
    const days = filters.date_range === "7d" ? 7 : filters.date_range === "90d" ? 90 : filters.date_range === "all" ? 0 : 30;
    return analyses.filter((item) => {
      const created = item.created_at ? Date.parse(item.created_at) : 0;
      const inWindow = !days || !created || now - created <= days * 24 * 60 * 60 * 1000;
      const sourceMatch = filters.source_system === "all" || !filters.source_system || item.source_system === filters.source_system;
      const gateMatch = filters.gate_status === "all" || !filters.gate_status || item.gate_status === filters.gate_status;
      const campaignMatch = !filters.campaign_id || String(item.campaign_id || "").toLowerCase().includes(filters.campaign_id.toLowerCase());
      const templateMatch = !filters.template_id || String(item.template_id || "").toLowerCase().includes(filters.template_id.toLowerCase());
      return inWindow && sourceMatch && gateMatch && campaignMatch && templateMatch;
    });
  }

  function selectOptions(values, selected, allLabel = "All") {
    const unique = Array.from(new Set(values.filter(Boolean))).sort();
    return [`<option value="all" ${selected === "all" ? "selected" : ""}>${escapeHtml(allLabel)}</option>`]
      .concat(unique.map((value) => `<option value="${escapeHtml(value)}" ${selected === value ? "selected" : ""}>${escapeHtml(displayLabel(value))}</option>`))
      .join("");
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
      ["Sandbox adapters", `${flows.length || 4} flows`, "HubSpot, Salesforce, SendGrid/SES, webhooks"],
      ["Setup manifests", `${manifests.length || 4} providers`, `${mappings.length} saved field mapping${mappings.length === 1 ? "" : "s"}`],
      ["Governance ledger", `${dashboard.analysis_volume ?? 0} analyses`, `${gateCounts.ready || 0} Ready / ${gateCounts.needs_review || 0} Needs review / ${gateCounts.blocked || 0} Blocked`],
      ["Sample imports", `${(dashboard.sample_imports || []).length} recent`, "Warehouse-style batch review"],
      ["Policy controls", `${policy.min_ready_score ?? 72} minimum score`, `${displayLabel(policy.content_storage_mode || "hash_only")} storage / ${policy.retention_days ?? 180} day retention`],
      ["Research targets", `${(plan.targets || []).length || manifests.length} targets`, plan.recommendation?.primary_target || "journey workflow gate"],
    ];
    return `
      <section id="dashboard-section" class="optimizer-section integration-lab-overview" aria-label="Integration lab status">
        <div class="section-title">
          <span class="label">Integration lab status</span>
          <strong>${state.labError ? "Status unavailable" : "Workflow-ready infrastructure"}</strong>
        </div>
        <div class="optimizer-grid integration-lab-grid">
          ${cards.map(([label, value, detail]) => `
            <article class="optimizer-context-card lab-status-card">
              ${statusBadge(label === "Sandbox adapters" ? "Sandbox" : label === "Research targets" ? "Documented" : "Available", label === "Sandbox adapters" ? "warning" : "neutral")}
              <span class="interface-label">${escapeHtml(label)}</span>
              <strong>${escapeHtml(value)}</strong>
              <p>${escapeHtml(detail)}</p>
            </article>
          `).join("")}
        </div>
        ${enterpriseReadinessChecklist({flows, manifests, mappings, installKit, dashboard, policy})}
        ${governanceDashboardPanels(dashboard)}
        ${approvalQueuePanel(dashboard)}
        ${exportsPanel()}
        ${governancePolicyControls(policy)}
        ${adapterSimulator(plan, manifests)}
        ${setupContracts(manifests, mappings)}
        ${adminSettingsPanel({policy, manifests, mappings, dashboard, installKit})}
        ${trustAndDeploymentPanel(policy)}
      </section>
    `;
  }

  function enterpriseReadinessChecklist({flows = [], manifests = [], mappings = [], installKit = {}, dashboard = {}, policy = {}} = {}) {
    const checks = [
      {
        label: "Workflow API contract",
        status: installKit.openapi_url ? "Ready" : "Needs review",
        tone: installKit.openapi_url ? "success" : "warning",
        detail: `${installKit.endpoints?.length || 0} documented endpoints with non-generative request/response contracts.`,
      },
      {
        label: "Adapter coverage",
        status: flows.length >= 4 && manifests.length >= 4 ? "Ready" : "Needs mapping",
        tone: flows.length >= 4 && manifests.length >= 4 ? "success" : "warning",
        detail: `${flows.length || 0} sandbox flows and ${manifests.length || 0} provider manifests available for workflow testing.`,
      },
      {
        label: "Workspace data boundary",
        status: "Protected",
        tone: "success",
        detail: "Governance dashboards, exports, policy, and saved mappings require a browser session or scoped API key.",
      },
      {
        label: "Field mapping state",
        status: mappings.length ? "Mapped" : "Needs mapping",
        tone: mappings.length ? "success" : "warning",
        detail: mappings.length ? `${mappings.length} provider mapping${mappings.length === 1 ? "" : "s"} saved for this workspace.` : "Save recommended mappings before using a provider workflow.",
      },
      {
        label: "Outcome feedback loop",
        status: (dashboard.joined_outcomes || []).length ? "Joining events" : "Ready for events",
        tone: (dashboard.joined_outcomes || []).length ? "success" : "neutral",
        detail: "request_id and content_hash are available for delivered, bounced, opened, clicked, complaint, suppression, and unsubscribe joins.",
      },
      {
        label: "Policy environment",
        status: displayLabel(policy.policy_environment || state.policyEnvironment || "production"),
        tone: policy.policy_environment === "sandbox" ? "warning" : "neutral",
        detail: `${displayLabel(policy.content_storage_mode || "hash_only")} storage with ${policy.retention_days ?? 180} day analysis retention.`,
      },
    ];
    return `
      <section class="enterprise-readiness-panel" aria-label="Enterprise readiness checklist">
        <div class="section-title">
          <span class="label">Enterprise readiness checklist</span>
          <strong>Direct workflow integration controls</strong>
        </div>
        <div class="readiness-grid">
          ${checks.map((check) => `
            <article>
              <div class="finding-card-head">
                ${statusBadge(check.status, check.tone)}
                <span class="interface-label">${escapeHtml(check.label)}</span>
              </div>
              <p>${escapeHtml(check.detail)}</p>
            </article>
          `).join("")}
        </div>
      </section>
    `;
  }

  function governanceDashboardPanels(dashboard = {}) {
    const failing = dashboard.top_failing_rule_packs || [];
    const templates = dashboard.risky_templates || [];
    const trends = dashboard.trend_by_source_system || [];
    const joins = dashboard.joined_outcomes || [];
    const outcomeCounts = dashboard.outcome_counts || {};
    const analyses = dashboard.recent_analyses || [];
    const filtered = filterAnalyses(analyses);
    const sourceValues = analyses.map((item) => item.source_system).filter(Boolean);
    const gateValues = analyses.map((item) => item.gate_status).filter(Boolean);
    return `
      <section class="optimizer-section governance-dashboard" aria-label="Governance dashboard">
        <div class="section-title">
          <span class="label">Governance dashboard</span>
          <strong>Enterprise trends for campaigns, templates, sources, and outcomes</strong>
        </div>
        <div class="dashboard-filter-grid" aria-label="Dashboard filters">
          <label class="policy-control">
            <span>Date range</span>
            <select data-dashboard-filter="date_range">
              ${["7d", "30d", "90d", "all"].map((value) => `<option value="${value}" ${state.dashboardFilters.date_range === value ? "selected" : ""}>${escapeHtml(value === "all" ? "All time" : `Last ${value.replace("d", " days")}`)}</option>`).join("")}
            </select>
          </label>
          <label class="policy-control">
            <span>Source system</span>
            <select data-dashboard-filter="source_system">
              ${selectOptions(sourceValues, state.dashboardFilters.source_system, "All sources")}
            </select>
          </label>
          <label class="policy-control">
            <span>Gate status</span>
            <select data-dashboard-filter="gate_status">
              ${selectOptions(gateValues, state.dashboardFilters.gate_status, "All gates")}
            </select>
          </label>
          <label class="policy-control">
            <span>Campaign contains</span>
            <input type="text" data-dashboard-filter="campaign_id" value="${escapeHtml(state.dashboardFilters.campaign_id)}" placeholder="cmp_">
          </label>
          <label class="policy-control">
            <span>Template contains</span>
            <input type="text" data-dashboard-filter="template_id" value="${escapeHtml(state.dashboardFilters.template_id)}" placeholder="tmpl_">
          </label>
          <div class="policy-control dashboard-filter-summary">
            <span>Filtered analyses</span>
            <strong>${escapeHtml(filtered.length)} / ${escapeHtml(analyses.length)}</strong>
            <button class="button-secondary small-button" type="button" data-clear-dashboard-filters>Clear filters</button>
          </div>
        </div>
        ${dashboardTrendCharts(dashboard, filtered)}
        <div class="dashboard-panel-grid">
          ${dashboardList("Top failing rule packs", failing, (item) => `${displayLabel(item.category)} · ${displayLabel(item.severity)} · ${item.count || 0} findings`)}
          ${dashboardList("Risky template versions", templates, (item) => `${item.template_id || "unknown"} · ${item.review_or_block_count || 0} review/block · ${Math.round(Number(item.average_score || 0))} avg score`)}
          ${dashboardList("Trend by source system", trends, (item) => `${displayLabel(item.source_system)} · ${displayLabel(item.gate_status)} · ${item.count || 0} analyses`)}
          ${dashboardList("Outcome joins", joins, (item) => `${displayLabel(item.event_type || item.delivery_status)} · ${shortHash(item.request_id || item.content_hash)} · ${displayLabel(item.source_system || "source unknown")}`)}
          ${dashboardList("Outcome counts", Object.entries(outcomeCounts).map(([event, count]) => ({event, count})), (item) => `${displayLabel(item.event)} · ${item.count} events`)}
          ${dashboardList("Filtered drilldown", filtered.slice(0, 8), (item) => `${shortHash(item.request_id)} · ${displayLabel(item.gate_status)} · ${Math.round(Number(item.score || 0))}/100 · ${displayLabel(item.source_system || "direct")}`)}
        </div>
      </section>
    `;
  }

  function dashboardTrendCharts(dashboard = {}, filtered = []) {
    const gateRows = aggregateRows(filtered, "gate_status", "none");
    const sourceRows = aggregateRows(filtered, "source_system", "direct");
    const campaignRows = aggregateRows(filtered, "campaign_id", "no campaign").slice(0, 5);
    return `
      <div class="trend-chart-grid" aria-label="Governance trend charts">
        ${trendChart("Gate distribution", gateRows, filtered.length)}
        ${trendChart("Source-system trend", sourceRows, filtered.length)}
        ${trendChart("Campaign drilldown", campaignRows, filtered.length)}
      </div>
    `;
  }

  function trendChart(title, rows, total) {
    const max = Math.max(...rows.map((row) => row.count), 1);
    return `
      <article class="trend-chart-card">
        <div class="finding-card-head">
          <span class="interface-label">${escapeHtml(title)}</span>
          ${statusBadge(`${total || 0} rows`, "neutral")}
        </div>
        ${rows.length ? rows.slice(0, 6).map((row) => `
          <div class="trend-row">
            <span>${escapeHtml(displayLabel(row.label))}</span>
            <div class="trend-track" aria-hidden="true"><b style="width: ${Math.max(6, Math.round((row.count / max) * 100))}%"></b></div>
            <strong>${escapeHtml(row.count)}</strong>
          </div>
        `).join("") : dashboardEmptyState(title)}
      </article>
    `;
  }

  function dashboardEmptyState(title) {
    const guidance = {
      "Gate distribution": "Run an analysis or clear filters to compare ready, review, and blocked decisions.",
      "Source-system trend": "Set source_system in enterprise context or run a sandbox adapter test to group activity by workflow source.",
      "Campaign drilldown": "Add campaign_id values to analyses or imports to compare campaign-level readiness.",
      "Top failing rule packs": "Review/block findings will appear here after analyses produce policy findings.",
      "Risky template versions": "Add template_id values to analyses or render tests to surface risky template versions.",
      "Trend by source system": "Use enterprise context or adapter payloads to create source-system trend rows.",
      "Outcome joins": "Post delivery, bounce, complaint, click, unsubscribe, or suppression webhooks to join outcomes to analyses.",
      "Outcome counts": "Webhook events populate this panel without storing raw email body text.",
      "Filtered drilldown": "Clear filters or run analyses with matching campaign/template metadata to inspect specific records.",
    };
    return `
      <div class="dashboard-empty-state">
        <strong>No matching data yet</strong>
        <p>${escapeHtml(guidance[title] || "Run analyses, imports, or webhooks to populate this enterprise governance panel.")}</p>
      </div>
    `;
  }

  function dashboardList(title, rows, labeler) {
    const cleanRows = Array.isArray(rows) ? rows.slice(0, 4) : [];
    return `
      <article class="dashboard-panel">
        <span class="interface-label">${escapeHtml(title)}</span>
        ${cleanRows.length ? cleanRows.map((row) => `<p>${escapeHtml(labeler(row))}</p>`).join("") : dashboardEmptyState(title)}
      </article>
    `;
  }

  function approvalQueuePanel(dashboard = {}) {
    const analyses = (dashboard.recent_analyses || []).filter((item) => item.gate_status !== "ready").slice(0, 8);
    const fallbackRows = analyses.length ? analyses : (dashboard.recent_analyses || []).slice(0, 4);
    return `
      <section class="optimizer-section approval-queue-panel" aria-label="Approval queue">
        <div class="section-title">
          <span class="label">Approval queue</span>
          <strong>Assign owners, add notes, and preserve send decisions</strong>
        </div>
        ${state.approvalMessage ? `<p class="setup-message">${escapeHtml(state.approvalMessage)}</p>` : ""}
        <div class="approval-queue-grid">
          ${fallbackRows.length ? fallbackRows.map((item, index) => approvalQueueCard(item, index)).join("") : `
            <article class="approval-card">
              ${statusBadge("Ready", "success")}
              <strong>No messages are waiting for review.</strong>
              <p class="muted">Messages that need review or are blocked will appear here with owner, queue, and note controls.</p>
            </article>
          `}
        </div>
      </section>
    `;
  }

  function approvalQueueCard(item, index) {
    const key = item.request_id || `analysis-${index}`;
    const action = state.approvalActions[key] || {};
    const status = action.status || displayLabel(item.gate_status || "needs_review");
    const owner = action.owner || ownerByCategory[item.highest_severity] || "Reviewer";
    return `
      <article class="approval-card" data-approval-card="${escapeHtml(key)}">
        <div class="finding-card-head">
          ${statusBadge(status, status === "Approved" || status === "Resolved" ? "success" : status === "Held" ? "danger" : "warning")}
          <span class="interface-label">${escapeHtml(shortHash(key))}</span>
        </div>
        <strong>${escapeHtml(displayLabel(item.source_system || "Direct API"))} · ${escapeHtml(Math.round(Number(item.score || 0)))}/100</strong>
        <p>${escapeHtml(item.template_id || "No template")} · ${escapeHtml(item.campaign_id || "No campaign")} · ${escapeHtml(item.created_at || "No timestamp")}</p>
        <div class="approval-control-row">
          <label>
            <span>Owner</span>
            <select data-approval-owner="${escapeHtml(key)}">
              ${["Admin", "Reviewer", "Analyst", "Developer", "Compliance owner", "Campaign owner"].map((role) => `<option ${owner === role ? "selected" : ""}>${escapeHtml(role)}</option>`).join("")}
            </select>
          </label>
          <label>
            <span>Decision note</span>
              <input type="text" data-approval-note="${escapeHtml(key)}" value="${escapeHtml(action.note || "")}" placeholder="Add decision note">
          </label>
        </div>
        <div class="approval-action-row">
          <button class="button-secondary small-button" type="button" data-approval-action="${escapeHtml(key)}" data-status="Approved">Approve</button>
          <button class="button-secondary small-button" type="button" data-approval-action="${escapeHtml(key)}" data-status="Held">Hold</button>
          <button class="button-secondary small-button" type="button" data-approval-action="${escapeHtml(key)}" data-status="Resolved">Resolve</button>
        </div>
      </article>
    `;
  }

  function exportsPanel() {
    return `
      <section id="exports-section" class="optimizer-section export-center" aria-label="Governance exports">
        <div class="section-title">
          <span class="label">Exports</span>
          <strong>Download normalized governance data</strong>
        </div>
        ${state.exportMessage ? `<p class="setup-message">${escapeHtml(state.exportMessage)}</p>` : ""}
        <div class="setup-action-row export-action-row">
          ${["analyses", "findings", "outcomes", "joins"].map((kind) => `
            <button class="button-secondary" type="button" data-governance-export="${kind}" data-export-format="json" ${state.exportBusy ? "disabled" : ""}>${escapeHtml(displayLabel(kind))} JSON</button>
            <button class="button-secondary" type="button" data-governance-export="${kind}" data-export-format="csv" ${state.exportBusy ? "disabled" : ""}>${escapeHtml(displayLabel(kind))} CSV</button>
          `).join("")}
        </div>
        <div class="export-schedule-card">
          <div class="section-title">
            <span class="label">Export schedule</span>
            <strong>Local schedule draft, manual exports remain active</strong>
          </div>
          ${state.exportScheduleMessage ? `<p class="setup-message">${escapeHtml(state.exportScheduleMessage)}</p>` : ""}
          <div class="policy-control-grid">
            <label class="policy-control">
              <span>Cadence</span>
              <select data-export-schedule="cadence">
                ${["daily", "weekly", "monthly"].map((item) => `<option value="${item}" ${state.exportSchedule.cadence === item ? "selected" : ""}>${escapeHtml(displayLabel(item))}</option>`).join("")}
              </select>
            </label>
            <label class="policy-control">
              <span>Dataset</span>
              <select data-export-schedule="kind">
                ${["analyses", "findings", "outcomes", "joins"].map((item) => `<option value="${item}" ${state.exportSchedule.kind === item ? "selected" : ""}>${escapeHtml(displayLabel(item))}</option>`).join("")}
              </select>
            </label>
            <label class="policy-control">
              <span>Format</span>
              <select data-export-schedule="format">
                ${["csv", "json"].map((item) => `<option value="${item}" ${state.exportSchedule.format === item ? "selected" : ""}>${escapeHtml(item.toUpperCase())}</option>`).join("")}
              </select>
            </label>
            <label class="policy-control">
              <span>Recipients</span>
              <input type="text" data-export-schedule="recipients" value="${escapeHtml(state.exportSchedule.recipients)}" placeholder="ops@example.com, compliance@example.com">
            </label>
          </div>
          <div class="policy-toggle-row">
            <label>
              <input type="checkbox" data-export-schedule="enabled" ${state.exportSchedule.enabled ? "checked" : ""}>
              <span>Enable schedule draft</span>
            </label>
            <button class="button-secondary" type="button" data-save-export-schedule>Save local schedule</button>
          </div>
          <p class="muted">This stores schedule metadata in this browser only. A production scheduler still needs your deployment worker or data pipeline.</p>
        </div>
        ${state.exportResult ? `<pre class="adapter-simulator-result export-preview">${escapeHtml(JSON.stringify(state.exportResult, null, 2))}</pre>` : ""}
      </section>
    `;
  }

  function adapterSimulator(plan = {}, manifests = []) {
    const providers = manifests.map((manifest) => manifest.provider);
    const options = Array.from(new Set(["hubspot", "salesforce", "sendgrid_ses", "braze", "marketo", "iterable", "warehouse", ...providers]));
    const payload = state.simulatorPayload || JSON.stringify(simulatorPayloads[state.simulatorProvider] || simulatorPayloads.hubspot, null, 2);
    const validation = simulatorValidation(state.simulatorProvider, payload);
    return `
      <section id="simulator-section" class="optimizer-section adapter-simulator" aria-label="Adapter simulator">
        <div class="section-title">
          <span class="label">Adapter simulator</span>
          <strong>Paste a provider payload and inspect mapped scoring outputs</strong>
        </div>
        ${state.simulatorMessage ? `<p class="setup-message">${escapeHtml(state.simulatorMessage)}</p>` : ""}
        <div class="setup-action-row">
          ${Object.keys(simulatorPayloads).map((provider) => `<button class="button-secondary small-button" type="button" data-simulator-example="${escapeHtml(provider)}">${escapeHtml(providerLabel(provider))} example</button>`).join("")}
          ${statusBadge(validation.valid ? "Payload validates" : "Needs payload fields", validation.valid ? "success" : "warning")}
        </div>
        <div class="adapter-simulator-grid">
          <label class="policy-control">
            <span>Provider</span>
            <select data-simulator-provider>
              ${options.map((provider) => `<option value="${escapeHtml(provider)}" ${provider === state.simulatorProvider ? "selected" : ""}>${escapeHtml(providerLabel(provider))}</option>`).join("")}
            </select>
            <small>Choose the adapter shape to normalize.</small>
          </label>
          <label class="policy-control adapter-simulator-payload">
            <span>Payload JSON</span>
            <textarea data-simulator-payload spellcheck="false">${escapeHtml(payload)}</textarea>
            <small>${escapeHtml(validation.message)}</small>
          </label>
        </div>
        <div class="setup-action-row">
          <button class="button-secondary" type="button" data-run-adapter-simulator ${state.simulatorBusy ? "disabled" : ""}>
            ${state.simulatorBusy ? "Simulating..." : "Run simulator"}
          </button>
          <span class="muted">${escapeHtml(plan.recommendation?.positioning || "Sandbox adapters score existing messages before production connections are enabled.")}</span>
        </div>
        ${state.simulatorResult ? simulatorResultSummary(state.simulatorResult) : ""}
      </section>
    `;
  }

  function simulatorValidation(provider, payloadText) {
    try {
      const payload = typeof payloadText === "string" ? JSON.parse(payloadText || "{}") : payloadText || {};
      const text = JSON.stringify(payload).toLowerCase();
      const hasSubject = text.includes("subject") || text.includes("email_subject") || text.includes("emailsubject");
      const hasBody = text.includes("body") || text.includes("email_body") || text.includes("emailbody") || text.includes("html") || text.includes("text");
      const warehouseRows = provider === "warehouse" && Array.isArray(payload.rows || payload.samples);
      const valid = warehouseRows || (hasSubject && hasBody);
      return {valid, message: valid ? "Required subject/body signals are present." : "Add subject and body fields, or warehouse rows, before simulation."};
    } catch (error) {
      return {valid: false, message: "Payload JSON is not valid yet."};
    }
  }

  function simulatorResultSummary(result) {
    const gate = result.analysis?.gate || {};
    const writeback = result.writeback || {};
    return `
      <div class="simulator-output-grid">
        <article class="optimizer-context-card">
          <span class="interface-label">Normalized decision</span>
          <strong>${escapeHtml(displayLabel(gate.status || result.decision || "unknown"))}</strong>
          <p>${escapeHtml(displayLabel(gate.route || "No route"))}</p>
        </article>
        <article class="optimizer-context-card">
          <span class="interface-label">Writeback fields</span>
          <strong>${escapeHtml(writeback.texttraits_score ?? result.analysis?.score ?? "n/a")}/100</strong>
          <p>${escapeHtml(shortHash(writeback.texttraits_request_id || result.analysis?.request_id))}</p>
        </article>
        <article class="optimizer-context-card">
          <span class="interface-label">Render check</span>
          <strong>${escapeHtml((result.render_test?.unresolved_tokens || []).length || 0)} unresolved</strong>
          <p>${escapeHtml((result.render_test?.unsubscribe?.header_present || result.render_test?.unsubscribe?.body_present) ? "Unsubscribe path detected" : "No unsubscribe path detected")}</p>
        </article>
      </div>
      <details class="secondary-result-details optimizer-json">
        <summary>Raw simulator output</summary>
        <pre>${escapeHtml(JSON.stringify(result, null, 2))}</pre>
      </details>
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
    const policyHistory = state.labData?.dashboard?.policy_bundle_history || [];
    return `
      <section id="governance-section" class="optimizer-section governance-policy-controls" aria-label="Governance policy controls">
        <div class="section-title">
          <span class="label">Governance policy</span>
          <strong>Workspace controls for gating, retention, and storage</strong>
        </div>
        ${state.policyMessage ? `<p class="setup-message">${escapeHtml(state.policyMessage)}</p>` : ""}
        <div class="policy-control-grid">
          <label class="policy-control">
            <span>Ready score</span>
            <input type="number" min="0" max="100" step="1" value="${escapeHtml(policyValue(policy, "min_ready_score", 72))}" data-policy-field="min_ready_score">
            <small>Minimum score required before automatic send approval.</small>
          </label>
          <label class="policy-control">
            <span>Analysis retention days</span>
            <input type="number" min="30" max="3650" step="1" value="${escapeHtml(policyValue(policy, "retention_days", 180))}" data-policy-field="retention_days">
            <small>How long analysis metadata stays available for audits.</small>
          </label>
          <label class="policy-control">
            <span>Webhook retention days</span>
            <input type="number" min="30" max="3650" step="1" value="${escapeHtml(policyValue(policy, "webhook_retention_days", 365))}" data-policy-field="webhook_retention_days">
            <small>How long outcome events remain joinable.</small>
          </label>
          <label class="policy-control">
            <span>Dedupe window days</span>
            <input type="number" min="1" max="365" step="1" value="${escapeHtml(policyValue(policy, "webhook_dedupe_window_days", 30))}" data-policy-field="webhook_dedupe_window_days">
            <small>Retry window for provider webhook event IDs.</small>
          </label>
          <label class="policy-control">
            <span>Sample import limit</span>
            <input type="number" min="1" max="100" step="1" value="${escapeHtml(policyValue(policy, "sample_import_limit", 25))}" data-policy-field="sample_import_limit">
            <small>Maximum rows for one UI or API batch.</small>
          </label>
          <label class="policy-control">
            <span>Storage mode</span>
            <select data-policy-field="content_storage_mode">
              <option value="hash_only" ${policyValue(policy, "content_storage_mode", "hash_only") === "hash_only" ? "selected" : ""}>Hash only</option>
              <option value="metadata_only" ${policyValue(policy, "content_storage_mode", "hash_only") === "metadata_only" ? "selected" : ""}>Metadata only</option>
            </select>
            <small>Controls whether raw copy is excluded from stored records.</small>
          </label>
          <label class="policy-control">
            <span>Environment</span>
            <select data-policy-field="policy_environment">
              ${["sandbox", "staging", "production"].map((env) => `<option value="${env}" ${policyValue(policy, "policy_environment", "production") === env ? "selected" : ""}>${titleCase(env)}</option>`).join("")}
            </select>
            <small>Separate draft policies from production controls.</small>
          </label>
          <label class="policy-control">
            <span>Send timeout ms</span>
            <input type="number" min="50" max="10000" step="50" value="${escapeHtml(policyValue(policy, "send_path_timeout_ms", 500))}" data-policy-field="send_path_timeout_ms">
            <small>Budget used by SendGrid/SES-style middleware.</small>
          </label>
          <label class="policy-control">
            <span>Idempotency window sec</span>
            <input type="number" min="60" max="86400" step="60" value="${escapeHtml(policyValue(policy, "idempotency_window_seconds", 900))}" data-policy-field="idempotency_window_seconds">
            <small>Replay safety window for send-path requests.</small>
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
        <div class="policy-history-panel">
          <span class="interface-label">Policy history and audit log</span>
          ${policyHistory.length ? policyHistory.slice(0, 5).map((item) => `
            <article>
              <strong>${escapeHtml(displayLabel(item.policy_environment || item.environment || "production"))} policy</strong>
              <p>${escapeHtml(item.created_at || item.updated_at || "unknown time")} · ${escapeHtml(item.version || "versioned bundle")}</p>
            </article>
          `).join("") : `<p class="muted">No saved policy changes yet. Save controls to create an audit entry.</p>`}
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
    const selected = manifests.find((item) => item.provider === state.setupProvider) || manifests[0];
    const selectedMapping = mappingForProvider(selected.provider, mappings);
    const selectedState = providerConnectionState(selected, selectedMapping);
    const validation = simulatorValidation(selected.provider, state.simulatorPayload || JSON.stringify(simulatorPayloads[selected.provider] || simulatorPayloads.hubspot, null, 2));
    return `
      <section id="integrations-section" class="optimizer-section setup-contracts" aria-label="Integration setup contracts">
        <div class="section-title">
          <span class="label">Integration setup</span>
          <strong>Guided sandbox adapter wizard before production routing</strong>
        </div>
        ${state.setupMessage ? `<p class="setup-message">${escapeHtml(state.setupMessage)}</p>` : ""}
        ${state.setupValidationMessage ? `<p class="setup-message">${escapeHtml(state.setupValidationMessage)}</p>` : ""}
        ${state.setupTestMessage ? `<p class="setup-message">${escapeHtml(state.setupTestMessage)}</p>` : ""}
        <div class="setup-wizard" aria-label="Guided integration wizard">
          ${[
            ["1", "Choose platform", selected.provider ? `${providerLabel(selected.provider)} selected.` : "Select the system that owns the email workflow."],
            ["2", "Validate payload", validation.valid ? "Sample payload contains subject/body signals." : "Run validation with a realistic sample."],
            ["3", "Save mapping", selectedMapping?.status === "ready" ? "Required inputs and writeback fields are configured." : "Persist required inputs and writeback fields."],
            ["4", "Promote environment", state.promotedProviders.includes(selected.provider) ? "Production promotion recorded locally." : "Move from sandbox to staging or production after tests pass."],
          ].map(([step, title, copy]) => `
            <article>
              <span>${escapeHtml(step)}</span>
              <strong>${escapeHtml(title)}</strong>
              <p>${escapeHtml(copy)}</p>
            </article>
          `).join("")}
        </div>
        <div class="setup-action-row">
          <label class="inline-control">
            <span>Provider</span>
            <select data-setup-provider>
              ${manifests.map((manifest) => `<option value="${escapeHtml(manifest.provider)}" ${manifest.provider === selected.provider ? "selected" : ""}>${escapeHtml(providerLabel(manifest.provider))}</option>`).join("")}
            </select>
          </label>
          ${statusBadge("Sandbox", "neutral")}
          ${statusBadge(selectedState.label, selectedState.tone)}
          <button class="button-secondary" type="button" data-validate-setup-payload>Validate payload</button>
          <button class="button-secondary" type="button" data-run-setup-test>Run sandbox test</button>
          <button class="button-secondary" type="button" data-promote-provider="${escapeHtml(selected.provider)}">Promote environment</button>
          <button class="button-secondary" type="button" data-download-openapi>Download OpenAPI JSON</button>
          <button class="button-secondary" type="button" data-copy-install-steps>Copy install steps</button>
        </div>
        <div class="optimizer-grid setup-contract-grid">
          ${manifests.map((manifest) => {
            const mapping = mappingForProvider(manifest.provider, mappings);
            const connection = providerConnectionState(manifest, mapping);
            const requiredCount = Object.keys(manifest.required_inputs || {}).length;
            const outputCount = Object.keys(manifest.recommended_writeback || {}).length;
            const isBusy = state.setupBusyProvider === manifest.provider;
            return `
              <article class="optimizer-check-card setup-contract-card ${mapping?.status === "ready" ? "is-ok" : "needs-work"}">
                <div class="finding-card-head">
                  ${statusBadge("Sandbox", "neutral")}
                  ${statusBadge(connection.label, connection.tone)}
                </div>
                <span class="label">${escapeHtml(manifest.install_surface || "Integration")}</span>
                <strong>${escapeHtml(manifest.name || providerLabel(manifest.provider))}</strong>
                <p>${escapeHtml(manifest.entrypoint || "v1 integration endpoint")}</p>
                <div class="objective-meta">
                  <span>${escapeHtml(mapping?.status === "ready" ? "Mapped" : "Template ready")}</span>
                  <span>${escapeHtml(requiredCount)} required inputs</span>
                  <span>${escapeHtml(outputCount)} writeback outputs</span>
                </div>
                <small>${escapeHtml(connection.detail)}</small>
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

  function adminSettingsPanel({policy = {}, manifests = [], mappings = [], dashboard = {}, installKit = {}} = {}) {
    return `
      <section id="admin-section" class="optimizer-section admin-settings-panel" aria-label="Enterprise admin settings">
        <div class="section-title">
          <span class="label">Admin settings</span>
          <strong>Workspace, roles, API access, webhooks, mappings, and deployment controls</strong>
        </div>
        ${state.adminMessage ? `<p class="setup-message">${escapeHtml(state.adminMessage)}</p>` : ""}
        <div class="admin-overview-grid">
          <article class="dashboard-panel">
            <span class="interface-label">Workspace</span>
            <strong>${escapeHtml(state.workspaceId || "default")}</strong>
            <p>${escapeHtml(displayLabel(state.policyEnvironment))} environment · ${escapeHtml(mappings.length)} saved mappings · ${escapeHtml(dashboard.analysis_volume || 0)} analyses.</p>
          </article>
          <article class="dashboard-panel">
            <span class="interface-label">API access</span>
            <strong>${escapeHtml(state.apiKeys.length)} local key profile${state.apiKeys.length === 1 ? "" : "s"}</strong>
            <p>Profiles store scope metadata only. No production secret is created or persisted.</p>
          </article>
          <article class="dashboard-panel">
            <span class="interface-label">Webhook signing</span>
            <strong>${escapeHtml(state.webhookConfig.status)}</strong>
            <p>${escapeHtml(state.webhookConfig.secretDigest ? `Secret fingerprint ${state.webhookConfig.secretDigest}` : "No local signing test has been saved.")}</p>
          </article>
        </div>
        ${rolePermissionsPanel()}
        ${apiKeyManagementPanel()}
        ${webhookSigningPanel()}
        ${adminMappingSummary(manifests, mappings)}
        ${auditLogPanel(dashboard)}
      </section>
    `;
  }

  function rolePermissionsPanel() {
    return `
      <section class="admin-subsection" aria-label="Role and permission scaffolding">
        <div class="section-title">
          <span class="label">Roles and permissions</span>
          <strong>Admin, Reviewer, Analyst, Developer</strong>
        </div>
        <div class="role-grid">
          ${roleProfiles.map((profile) => `
            <article>
              ${statusBadge(profile.role === "Admin" ? "Configured" : "Sandbox", profile.role === "Admin" ? "success" : "neutral")}
              <strong>${escapeHtml(profile.role)}</strong>
              <p>${escapeHtml(profile.detail)}</p>
              <div class="cue-row">${profile.permissions.map((permission) => `<span>${escapeHtml(permission)}</span>`).join("")}</div>
            </article>
          `).join("")}
        </div>
      </section>
    `;
  }

  function apiKeyManagementPanel() {
    return `
      <section class="admin-subsection" aria-label="API key management">
        <div class="section-title">
          <span class="label">API key management</span>
          <strong>Local scope profiles for sandbox planning</strong>
        </div>
        ${state.apiKeyMessage ? `<p class="setup-message">${escapeHtml(state.apiKeyMessage)}</p>` : ""}
        <div class="policy-control-grid">
          <label class="policy-control">
            <span>Key name</span>
            <input type="text" data-api-key-form="name" value="${escapeHtml(state.apiKeyForm.name)}">
          </label>
          <label class="policy-control">
            <span>Environment</span>
            <select data-api-key-form="environment">
              ${["sandbox", "staging", "production"].map((env) => `<option value="${env}" ${state.apiKeyForm.environment === env ? "selected" : ""}>${escapeHtml(displayLabel(env))}</option>`).join("")}
            </select>
          </label>
          <label class="policy-control api-scope-control">
            <span>Scopes</span>
            <textarea rows="2" data-api-key-form="scopes" spellcheck="false">${escapeHtml(state.apiKeyForm.scopes)}</textarea>
            <small>Example: default:/v1/email/analyze, default:/v1/governance</small>
          </label>
        </div>
        <div class="setup-action-row">
          <button class="button-secondary" type="button" data-create-api-key-profile>Create local key profile</button>
          ${statusBadge("No credential generated", "neutral")}
        </div>
        <div class="api-key-list">
          ${state.apiKeys.map((key) => `
            <article>
              <div class="finding-card-head">
                ${statusBadge(key.status || "Sandbox", key.environment === "production" ? "warning" : "neutral")}
                <span class="interface-label">${escapeHtml(key.environment || "sandbox")}</span>
              </div>
              <strong>${escapeHtml(key.name)}</strong>
              <p>${escapeHtml((key.scopes || []).join(", "))}</p>
              <small>${escapeHtml(key.secretPreview)} · created ${escapeHtml(key.created_at || "locally")}</small>
              <button class="button-secondary small-button" type="button" data-revoke-api-key="${escapeHtml(key.id)}">Remove local profile</button>
            </article>
          `).join("")}
        </div>
      </section>
    `;
  }

  function webhookSigningPanel() {
    return `
      <section class="admin-subsection" aria-label="Webhook signing setup">
        <div class="section-title">
          <span class="label">Webhook signing setup</span>
          <strong>Local test signature flow for post-send events</strong>
        </div>
        ${state.webhookMessage ? `<p class="setup-message">${escapeHtml(state.webhookMessage)}</p>` : ""}
        <div class="policy-control-grid">
          <label class="policy-control">
            <span>Webhook endpoint</span>
            <input type="text" data-webhook-field="endpoint" value="${escapeHtml(state.webhookConfig.endpoint)}">
          </label>
          <label class="policy-control">
            <span>Event type</span>
            <select data-webhook-field="eventType">
              ${["delivered", "opened", "clicked", "bounced", "complained", "unsubscribed"].map((event) => `<option value="${event}" ${state.webhookConfig.eventType === event ? "selected" : ""}>${escapeHtml(displayLabel(event))}</option>`).join("")}
            </select>
          </label>
          <label class="policy-control">
            <span>Signing secret for test</span>
            <input type="password" data-webhook-secret value="${escapeHtml(state.webhookSecretDraft)}" placeholder="Paste a test-only secret">
            <small>The secret itself is never persisted; only a fingerprint can be stored locally.</small>
          </label>
        </div>
        <div class="setup-action-row">
          <button class="button-secondary" type="button" data-run-webhook-test>Run local signature test</button>
          ${statusBadge(state.webhookConfig.status, state.webhookConfig.status === "Configured" ? "success" : "warning")}
          ${state.webhookConfig.signaturePreview ? statusBadge(state.webhookConfig.signaturePreview, "neutral") : ""}
        </div>
        <p class="muted">Production validation still requires setting TEXTTRAITS_WEBHOOK_SECRET on the server and sending X-TextTraits-Signature with each provider event.</p>
      </section>
    `;
  }

  function adminMappingSummary(manifests, mappings) {
    return `
      <section class="admin-subsection" aria-label="Mapping administration">
        <div class="section-title">
          <span class="label">Mapping administration</span>
          <strong>Provider readiness across sandbox adapters</strong>
        </div>
        <div class="mapping-state-grid">
          ${manifests.map((manifest) => {
            const mapping = mappingForProvider(manifest.provider, mappings);
            const connection = providerConnectionState(manifest, mapping);
            return `
              <article>
                ${statusBadge("Sandbox", "neutral")}
                ${statusBadge(connection.label, connection.tone)}
                <strong>${escapeHtml(providerLabel(manifest.provider))}</strong>
                <p>${escapeHtml(connection.detail)}</p>
              </article>
            `;
          }).join("")}
        </div>
      </section>
    `;
  }

  function auditLogPanel(dashboard = {}) {
    const policyHistory = dashboard.policy_bundle_history || [];
    const webhookRows = dashboard.webhook_events || [];
    const localEvents = [
      ...policyHistory.slice(0, 4).map((item) => ({type: "Policy change", detail: `${displayLabel(item.policy_environment || "production")} · ${item.version || "versioned bundle"}`, at: item.updated_at || item.created_at})),
      ...webhookRows.slice(0, 3).map((item) => ({type: "Webhook event", detail: `${displayLabel(item.event_type || item.delivery_status)} · ${shortHash(item.dedupe_key)}`, at: item.last_seen_at || item.first_seen_at})),
      ...state.apiKeys.slice(0, 2).map((item) => ({type: "API key profile", detail: `${item.name} · ${(item.scopes || []).join(", ")}`, at: item.created_at})),
    ];
    return `
      <section class="admin-subsection" aria-label="Audit log">
        <div class="section-title">
          <span class="label">Audit log</span>
          <strong>Internal policy, webhook, and local admin events</strong>
        </div>
        <div class="audit-log-list">
          ${localEvents.length ? localEvents.map((event) => `
            <article>
              <span class="interface-label">${escapeHtml(event.type)}</span>
              <strong>${escapeHtml(event.detail)}</strong>
              <p>${escapeHtml(event.at || "Local session")}</p>
            </article>
          `).join("") : `<p class="muted">No audit events yet. Policy saves, webhook tests, and local key profiles appear here.</p>`}
        </div>
      </section>
    `;
  }

  function trustAndDeploymentPanel(policy = {}) {
    return `
      <section class="optimizer-section trust-deployment-panel" aria-label="Security and deployment readiness">
        <div class="section-title">
          <span class="label">Security and deployment readiness</span>
          <strong>Professional trust package for enterprise review</strong>
        </div>
        <div class="trust-grid">
          <article>
            ${statusBadge("Non-generative", "success")}
            <strong>Scoring layer only</strong>
            <p>TextTraits analyzes existing drafts and returns model signals, policy decisions, hashes, and routes. It does not write replacement email copy.</p>
          </article>
          <article>
            ${statusBadge("Model limitations", "neutral")}
            <strong>Use as evidence, not authority</strong>
            <p>Scores are calibrated policy indicators. Teams should still review claims, consent, legal requirements, and edge cases before sending.</p>
          </article>
          <article>
            ${statusBadge(displayLabel(policy.content_storage_mode || "hash_only"), "success")}
            <strong>Data handling</strong>
            <p>Default governance storage avoids raw body persistence and keeps request IDs/content hashes for audits and outcome joins.</p>
          </article>
          <article>
            ${statusBadge("Deployment checklist", "warning")}
            <strong>Production prerequisites</strong>
            <p>Secrets, Postgres, HTTPS, workers, monitoring, backups, and webhook signing must be configured before enterprise rollout.</p>
          </article>
        </div>
        <div class="deployment-check-grid">
          ${deploymentChecks.map(([title, detail]) => `
            <article>
              <span class="interface-label">${escapeHtml(title)}</span>
              <p>${escapeHtml(detail)}</p>
            </article>
          `).join("")}
        </div>
      </section>
    `;
  }

  function bindLabControls() {
    document.querySelector("[data-workflow-provider]")?.addEventListener("change", (event) => {
      state.workflowProvider = event.currentTarget.value;
      state.workflowAdapterResult = null;
      state.workflowMessage = `${providerLabel(state.workflowProvider)} selected for sandbox workflow simulation.`;
      renderEmpty();
    });
    document.querySelectorAll("[data-workflow-scenario]").forEach((button) => {
      button.addEventListener("click", () => {
        const scenario = workflowScenarios.find((item) => item.id === button.dataset.workflowScenario);
        if (!scenario) return;
        state.workflowScenario = scenario.id;
        state.workflowProvider = scenario.provider;
        state.workflowProfile = null;
        state.workflowAdapterResult = null;
        state.workflowMessage = `${scenario.label} scenario selected.`;
        renderEmpty();
      });
    });
    document.querySelector("[data-run-workflow-lab]")?.addEventListener("click", runRevenueSignalSimulation);
    document.querySelector("[data-load-workflow-profile]")?.addEventListener("click", loadWorkflowProfileBuilder);
    document.querySelectorAll("[data-save-recommended-mapping]").forEach((button) => {
      button.addEventListener("click", () => saveRecommendedMapping(button.dataset.saveRecommendedMapping));
    });
    document.querySelector("[data-download-openapi]")?.addEventListener("click", downloadOpenApiContract);
    document.querySelector("[data-copy-install-steps]")?.addEventListener("click", copyInstallSteps);
    document.querySelector("[data-save-policy-controls]")?.addEventListener("click", savePolicyControls);
    document.querySelector("[data-save-export-schedule]")?.addEventListener("click", saveExportSchedule);
    document.querySelector("[data-create-api-key-profile]")?.addEventListener("click", createLocalApiKeyProfile);
    document.querySelector("[data-run-webhook-test]")?.addEventListener("click", runWebhookSignatureTest);
    document.querySelector("[data-validate-setup-payload]")?.addEventListener("click", validateSetupPayload);
    document.querySelector("[data-run-setup-test]")?.addEventListener("click", runSetupSandboxTest);
    document.querySelector("[data-setup-provider]")?.addEventListener("change", (event) => {
      state.setupProvider = event.currentTarget.value;
      state.simulatorProvider = state.setupProvider;
      state.setupValidationMessage = `${providerLabel(state.setupProvider)} selected for sandbox setup.`;
      renderEmpty();
    });
    document.querySelectorAll("[data-promote-provider]").forEach((button) => {
      button.addEventListener("click", () => promoteProvider(button.dataset.promoteProvider));
    });
    document.querySelectorAll("[data-dashboard-filter]").forEach((field) => {
      field.addEventListener("input", () => {
        state.dashboardFilters[field.dataset.dashboardFilter] = field.value;
      });
      field.addEventListener("change", () => updateDashboardFilter(field));
    });
    document.querySelector("[data-clear-dashboard-filters]")?.addEventListener("click", clearDashboardFilters);
    document.querySelectorAll("[data-api-key-form]").forEach((field) => {
      field.addEventListener("input", () => {
        state.apiKeyForm[field.dataset.apiKeyForm] = field.value;
      });
      field.addEventListener("change", () => {
        state.apiKeyForm[field.dataset.apiKeyForm] = field.value;
      });
    });
    document.querySelectorAll("[data-revoke-api-key]").forEach((button) => {
      button.addEventListener("click", () => revokeLocalApiKeyProfile(button.dataset.revokeApiKey));
    });
    document.querySelectorAll("[data-webhook-field]").forEach((field) => {
      field.addEventListener("input", () => {
        state.webhookConfig[field.dataset.webhookField] = field.value;
      });
      field.addEventListener("change", () => {
        state.webhookConfig[field.dataset.webhookField] = field.value;
      });
    });
    document.querySelector("[data-webhook-secret]")?.addEventListener("input", (event) => {
      state.webhookSecretDraft = event.currentTarget.value;
    });
    document.querySelectorAll("[data-export-schedule]").forEach((field) => {
      field.addEventListener("input", () => updateExportScheduleField(field));
      field.addEventListener("change", () => updateExportScheduleField(field));
    });
    document.querySelectorAll("[data-approval-action]").forEach((button) => {
      button.addEventListener("click", () => saveApprovalDecision(button.dataset.approvalAction, button.dataset.status));
    });
    document.querySelector("[data-simulator-provider]")?.addEventListener("change", (event) => {
      state.simulatorProvider = event.currentTarget.value;
      state.setupProvider = state.simulatorProvider;
      state.simulatorPayload = JSON.stringify(simulatorPayloads[state.simulatorProvider] || simulatorPayloads.hubspot, null, 2);
      state.simulatorResult = null;
      renderEmpty();
    });
    document.querySelectorAll("[data-simulator-example]").forEach((button) => {
      button.addEventListener("click", () => {
        state.simulatorProvider = button.dataset.simulatorExample;
        state.simulatorPayload = JSON.stringify(simulatorPayloads[state.simulatorProvider] || simulatorPayloads.hubspot, null, 2);
        state.simulatorResult = null;
        state.simulatorMessage = `${providerLabel(state.simulatorProvider)} example loaded.`;
        renderEmpty();
      });
    });
    document.querySelector("[data-run-adapter-simulator]")?.addEventListener("click", runAdapterSimulator);
    document.querySelectorAll("[data-governance-export]").forEach((button) => {
      button.addEventListener("click", () => downloadGovernanceExport(button.dataset.governanceExport, button.dataset.exportFormat));
    });
  }

  function updateDashboardFilter(field) {
    state.dashboardFilters[field.dataset.dashboardFilter] = field.value;
    if (!state.latestData) renderEmpty();
    else renderResult(state.latestData, state.latestOptimization || state.latestData);
  }

  function clearDashboardFilters() {
    state.dashboardFilters = {date_range: "30d", source_system: "all", campaign_id: "", template_id: "", gate_status: "all"};
    if (!state.latestData) renderEmpty();
    else renderResult(state.latestData, state.latestOptimization || state.latestData);
  }

  function updateExportScheduleField(field) {
    const key = field.dataset.exportSchedule;
    state.exportSchedule[key] = field.type === "checkbox" ? field.checked : field.value;
  }

  function saveExportSchedule() {
    state.exportSchedule.lastSaved = new Date().toISOString();
    persistLocalAdminState();
    state.exportScheduleMessage = state.exportSchedule.enabled
      ? `${displayLabel(state.exportSchedule.cadence)} ${state.exportSchedule.kind} ${state.exportSchedule.format.toUpperCase()} schedule saved locally.`
      : "Export schedule draft saved locally but remains disabled.";
    renderEmpty();
  }

  function createLocalApiKeyProfile() {
    const name = state.apiKeyForm.name.trim() || "Sandbox workflow key";
    const scopes = state.apiKeyForm.scopes.split(",").map((scope) => scope.trim()).filter(Boolean);
    const environment = state.apiKeyForm.environment || "sandbox";
    const profile = {
      id: `key_${Date.now()}`,
      name,
      environment,
      scopes: scopes.length ? scopes : ["default:/v1/email/analyze"],
      status: environment === "production" ? "Production blocked" : "Sandbox",
      secretPreview: "No credential material stored",
      created_at: new Date().toISOString(),
      last_used: "Not used",
    };
    state.apiKeys = [profile, ...state.apiKeys].slice(0, 8);
    state.apiKeyMessage = "Local API key profile saved. No credential material was generated or stored.";
    persistLocalAdminState();
    renderEmpty();
  }

  function revokeLocalApiKeyProfile(id) {
    state.apiKeys = state.apiKeys.filter((key) => key.id !== id);
    state.apiKeyMessage = "Local API key profile removed.";
    persistLocalAdminState();
    renderEmpty();
  }

  async function digestText(text) {
    if (!window.crypto?.subtle) return Math.random().toString(36).slice(2, 10);
    const bytes = new TextEncoder().encode(text);
    const digest = await window.crypto.subtle.digest("SHA-256", bytes);
    return Array.from(new Uint8Array(digest)).slice(0, 8).map((byte) => byte.toString(16).padStart(2, "0")).join("");
  }

  async function hmacPreview(secret, payload) {
    if (!window.crypto?.subtle) return `sha256=${Math.random().toString(36).slice(2, 14)}`;
    const key = await window.crypto.subtle.importKey("raw", new TextEncoder().encode(secret), {name: "HMAC", hash: "SHA-256"}, false, ["sign"]);
    const signature = await window.crypto.subtle.sign("HMAC", key, new TextEncoder().encode(payload));
    return `sha256=${Array.from(new Uint8Array(signature)).slice(0, 6).map((byte) => byte.toString(16).padStart(2, "0")).join("")}...`;
  }

  async function runWebhookSignatureTest() {
    const secret = state.webhookSecretDraft.trim();
    if (secret.length < 12) {
      state.webhookConfig.status = "Production blocked";
      state.webhookMessage = "Webhook signing needs a test secret with at least 12 characters before production can be promoted.";
      persistLocalAdminState();
      renderEmpty();
      return;
    }
    const payload = JSON.stringify({
      event_id: `local-${Date.now()}`,
      provider: state.enterpriseContext.delivery_provider || "sendgrid",
      event_type: state.webhookConfig.eventType || "delivered",
      request_id: state.latestData?.request_id || "local-preview",
    });
    state.webhookConfig.secretDigest = await digestText(secret);
    state.webhookConfig.signaturePreview = await hmacPreview(secret, payload);
    state.webhookConfig.status = "Configured";
    state.webhookConfig.lastTest = new Date().toISOString();
    state.webhookMessage = `Local signature test passed for ${displayLabel(state.webhookConfig.eventType)}. Store the real secret on the server before production.`;
    state.webhookSecretDraft = "";
    persistLocalAdminState();
    renderEmpty();
  }

  function validateSetupPayload() {
    const provider = state.setupProvider || state.simulatorProvider;
    const payload = state.simulatorPayload || JSON.stringify(simulatorPayloads[provider] || simulatorPayloads.hubspot, null, 2);
    const validation = simulatorValidation(provider, payload);
    state.setupValidationMessage = validation.valid
      ? `${providerLabel(provider)} payload validates for sandbox adapter testing.`
      : `${providerLabel(provider)} payload needs required subject/body fields before testing.`;
    renderEmpty();
  }

  async function runSetupSandboxTest() {
    state.simulatorProvider = state.setupProvider || state.simulatorProvider;
    state.simulatorPayload = state.simulatorPayload || JSON.stringify(simulatorPayloads[state.simulatorProvider] || simulatorPayloads.hubspot, null, 2);
    await runAdapterSimulator();
    state.setupTestMessage = `${providerLabel(state.simulatorProvider)} sandbox test ran through the adapter simulator.`;
    if (!state.latestData) renderEmpty();
  }

  function promoteProvider(provider) {
    const manifest = (state.labData?.manifests || []).find((item) => item.provider === provider);
    const mapping = mappingForProvider(provider, state.labData?.fieldMappings || []);
    if (!manifest || mapping?.status !== "ready") {
      state.setupMessage = `${providerLabel(provider)} is production blocked until required fields are mapped.`;
      renderEmpty();
      return;
    }
    state.promotedProviders = Array.from(new Set([provider, ...state.promotedProviders]));
    state.setupMessage = `${providerLabel(provider)} promotion recorded locally. Real production promotion still requires provider credentials and deployment approval.`;
    persistLocalAdminState();
    renderEmpty();
  }

  function saveApprovalDecision(key, status) {
    const owner = document.querySelector(`[data-approval-owner="${cssEscape(key)}"]`)?.value || "Reviewer";
    const note = document.querySelector(`[data-approval-note="${cssEscape(key)}"]`)?.value || "";
    state.approvalActions[key] = {status, owner, note, updated_at: new Date().toISOString()};
    state.approvalMessage = `${shortHash(key)} marked ${status} by ${owner}.`;
    persistLocalAdminState();
    if (!state.latestData) renderEmpty();
    else renderResult(state.latestData, state.latestOptimization || state.latestData);
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
      const response = await apiClient.saveGovernancePolicy?.({...policy, policy_environment: policy.policy_environment || state.policyEnvironment}, {workspace_id: state.workspaceId || "default"});
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

  async function runRenderTest() {
    if (state.renderBusy) return;
    state.renderBusy = true;
    state.renderMessage = "Testing sample render context...";
    renderInput();
    try {
      const context = currentEnterpriseContext();
      const result = await apiClient.renderTemplateTest?.({
        workspace_id: state.workspaceId,
        subject: state.subject,
        body: state.email,
        ...context,
      });
      state.renderResult = result || {};
      const unresolved = result?.render_test?.unresolved_tokens?.length || 0;
      state.renderMessage = unresolved ? `${unresolved} personalization token${unresolved === 1 ? "" : "s"} still need attention.` : "Template tokens resolved for the sample recipient.";
      announce("Rendered-template test complete.");
    } catch (error) {
      state.renderResult = null;
      state.renderMessage = error.message || "Rendered-template test could not run.";
      apiClient.clientError?.({message: state.renderMessage, source: "render-template-test"}).catch(() => {});
    } finally {
      state.renderBusy = false;
      renderInput();
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
      state.simulatorMessage = `${providerLabel(state.simulatorProvider)} simulator returned ${displayLabel(result?.analysis?.gate?.status || "a decision")}.`;
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

  async function downloadGovernanceExport(kind = "analyses", format = "json") {
    state.exportBusy = `${kind}:${format}`;
    state.exportMessage = `Preparing ${displayLabel(kind)} ${format.toUpperCase()} export...`;
    renderEmpty();
    try {
      if (format === "csv") {
        const params = new URLSearchParams({type: kind, format, workspace_id: state.workspaceId || "default"});
        const response = await fetch(`/v1/governance/export?${params.toString()}`, {credentials: "same-origin"});
        if (!response.ok) throw new Error("CSV export failed.");
        const blob = await response.blob();
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = `texttraits-${kind}-${state.workspaceId || "default"}.csv`;
        document.body.appendChild(link);
        link.click();
        const href = link.href;
        link.remove();
        URL.revokeObjectURL(href);
        state.exportResult = {type: kind, format, downloaded: true};
      } else {
        const data = await apiClient.governanceExport?.(kind, "json", state.workspaceId || "default");
        state.exportResult = data || {};
        const blob = new Blob([JSON.stringify(data, null, 2)], {type: "application/json"});
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = `texttraits-${kind}-${state.workspaceId || "default"}.json`;
        document.body.appendChild(link);
        link.click();
        const href = link.href;
        link.remove();
        URL.revokeObjectURL(href);
      }
      state.exportMessage = `${displayLabel(kind)} ${format.toUpperCase()} export ready.`;
      announce("Governance export ready.");
    } catch (error) {
      state.exportMessage = error.message || "Governance export could not be prepared.";
      apiClient.clientError?.({message: state.exportMessage, source: "governance-export"}).catch(() => {});
    } finally {
      state.exportBusy = "";
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
      await apiClient.saveFieldMapping?.(provider, recommendedMapping(manifest), {workspace_id: state.workspaceId || "default"});
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
    const recovery = errorRecoverySteps(message);
    els.outputPanel.innerHTML = `
      <div class="empty-hero error-card" role="alert">
        <span class="status-pill">Needs retry</span>
        <h2>The email optimization did not run.</h2>
        <p class="muted">${escapeHtml(message)}</p>
        <div class="error-state-grid">
          ${recovery.map((item) => `
            <article>
              ${statusBadge(item.status, item.tone)}
              <strong>${escapeHtml(item.title)}</strong>
              <p>${escapeHtml(item.detail)}</p>
            </article>
          `).join("")}
        </div>
        <button class="button-secondary" id="retry-run" type="button" ${state.email.trim() ? "" : "disabled"}>Retry</button>
      </div>
    `;
    document.querySelector("#retry-run")?.addEventListener("click", analyze);
  }

  function errorRecoverySteps(message = "") {
    const text = String(message).toLowerCase();
    if (text.includes("payload") || text.includes("json")) {
      return [
        {status: "Bad payload", tone: "danger", title: "Validate JSON", detail: "Check required subject, body, headers, and personalization objects before retrying."},
        {status: "Sandbox", tone: "neutral", title: "Use simulator", detail: "Paste the same provider payload into the sandbox adapter simulator to inspect mapped inputs."},
      ];
    }
    if (text.includes("scope") || text.includes("authentication") || text.includes("api key")) {
      return [
        {status: "Missing API scope", tone: "danger", title: "Check workspace access", detail: "Use a scoped API key or browser session for governance data and saved mappings."},
        {status: "Admin", tone: "neutral", title: "Review key profiles", detail: "Open Admin settings to confirm the intended workspace and endpoint scopes."},
      ];
    }
    if (text.includes("signature")) {
      return [
        {status: "Webhook signature failure", tone: "danger", title: "Verify HMAC", detail: "Confirm X-TextTraits-Signature uses the server-side webhook secret and raw request body."},
      ];
    }
    if (text.includes("too many") || text.includes("rate")) {
      return [
        {status: "Rate limited", tone: "warning", title: "Wait and retry", detail: "The request was throttled to protect send-path latency and system stability."},
      ];
    }
    return [
      {status: "Retry", tone: "warning", title: "Check required fields", detail: "Confirm the body, enterprise context JSON, and policy settings are valid before retrying."},
      {status: "Support evidence", tone: "neutral", title: "Keep request details", detail: "Use request IDs, content hashes, and timestamps when debugging with admins."},
    ];
  }

  function scoreRing(optimization) {
    const score = optimization?.scores?.overall ?? optimization?.score ?? 0;
    const gate = optimization?.policy?.gate || {};
    const readiness = gate.status ? displayLabel(gate.status) : optimization?.readiness || "Not analyzed";
    return `
      <article class="optimizer-score-card">
        <span class="interface-label">Policy score</span>
        <strong>${escapeHtml(score)}/100</strong>
        <p>${escapeHtml(readiness)}</p>
        <div class="score-track" aria-hidden="true">
          <span style="width: ${Math.max(0, Math.min(score, 100))}%"></span>
        </div>
      </article>
    `;
  }

  function scoreExplanation(analysis) {
    const scores = analysis.scores || {};
    const gate = analysis.policy?.gate || {};
    const thresholds = gate.thresholds || {};
    const model = analysis.model || {};
    const lowDrivers = Object.entries(scores)
      .filter(([key]) => key !== "overall")
      .sort((a, b) => Number(a[1]) - Number(b[1]))
      .slice(0, 4);
    const confidence = modelConfidenceSummary(analysis.predictions || {});
    return `
      <section class="optimizer-section score-explanation-panel" aria-label="Score explanation">
        <div class="section-title">
          <span class="label">Why this score</span>
          <strong>Rules, thresholds, confidence, and model version</strong>
        </div>
        <div class="score-explanation-grid">
          <article>
            ${statusBadge(displayLabel(gate.status || "Not analyzed"), gate.status === "ready" ? "success" : gate.status === "blocked" ? "danger" : "warning")}
            <strong>${escapeHtml(scores.overall ?? 0)}/100 versus ${escapeHtml(thresholds.ready_minimum_score ?? 72)} ready threshold</strong>
            <p>${escapeHtml(gate.send_ready ? "The message can continue automatically under the current policy." : "The message should pause for review under the current policy.")}</p>
          </article>
          <article>
            ${statusBadge(confidence.label, confidence.tone)}
            <strong>Model confidence summary</strong>
            <p>${escapeHtml(confidence.detail)}</p>
          </article>
          <article>
            ${statusBadge("Versioned", "neutral")}
            <strong>${escapeHtml(model.version || "local-texttraits-bundle")}</strong>
            <p>Model contract ${escapeHtml(model.contract_version || "n/a")} · ${escapeHtml((model.targets || []).length)} trained targets · demo: ${escapeHtml(model.demo ? "yes" : "no")}.</p>
          </article>
        </div>
        <div class="driver-grid">
          ${lowDrivers.map(([key, value]) => `
            <article>
              <span class="interface-label">${escapeHtml(displayLabel(key))}</span>
              <strong>${escapeHtml(value)}/100</strong>
              <div class="score-track" aria-hidden="true"><span style="width: ${Math.max(0, Math.min(Number(value), 100))}%"></span></div>
            </article>
          `).join("")}
        </div>
      </section>
    `;
  }

  function modelConfidenceSummary(predictions = {}) {
    const items = [predictions.gender, predictions.age_bucket, predictions.age_estimate, ...(Object.values(predictions.mbti_dimensions || {}))].filter(Boolean);
    const confidences = items.map((item) => Number(item.confidence)).filter(Number.isFinite);
    if (!confidences.length) return {label: "Confidence n/a", tone: "neutral", detail: "No confidence values were returned for this model bundle."};
    const average = confidences.reduce((sum, value) => sum + value, 0) / confidences.length;
    const label = average >= 0.72 ? "High confidence" : average >= 0.55 ? "Moderate confidence" : "Low confidence";
    const tone = average >= 0.72 ? "success" : average >= 0.55 ? "warning" : "danger";
    return {label, tone, detail: `${percent(average)} average confidence across returned local model signals.`};
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
    return findings.map((finding) => {
      const meta = findingActionMeta(finding, optimization.policy?.gate || {});
      return `
        <article class="optimizer-check-card ${finding.severity === "high" || finding.severity === "critical" ? "needs-work" : "is-ok"}">
          <div class="finding-card-head">
            <span class="label">${escapeHtml(displayLabel(finding.category))} / ${escapeHtml(displayLabel(finding.severity))}</span>
            ${statusBadge(meta.level, meta.tone)}
          </div>
          <strong>${escapeHtml(finding.title)}</strong>
          <p>${escapeHtml(finding.details || (finding.evidence?.[0]?.text ? `Evidence: ${finding.evidence[0].text}` : "Detected by the policy bundle."))}</p>
          <div class="finding-action-grid">
            <span><b>Owner</b>${escapeHtml(meta.owner)}</span>
            <span><b>Queue</b>${escapeHtml(meta.queue)}</span>
            <span><b>Next step</b>${escapeHtml(meta.action)}</span>
          </div>
          <small>${escapeHtml(finding.remediation)}</small>
        </article>
      `;
    }).join("");
  }

  function findingActionMeta(finding, gate = {}) {
    const severity = String(finding?.severity || "").toLowerCase();
    const category = String(finding?.category || "policy").toLowerCase();
    const route = gate.route || (severity === "critical" ? "compliance_or_manager_review" : "human_review_queue");
    const hardBlock = severity === "critical" || gate.status === "blocked";
    const review = severity === "high" || gate.status === "needs_review";
    return {
      owner: ownerByCategory[category] || "Workflow owner",
      queue: displayLabel(route),
      level: hardBlock ? "Hard block" : review ? "Review required" : "Advisory",
      tone: hardBlock ? "danger" : review ? "warning" : "success",
      action: hardBlock ? "Do not send until resolved" : review ? "Route to owner before launch" : "Track before send",
    };
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
      <details class="secondary-result-details optimizer-json developer-json-panel">
        <summary>Developer-only raw /v1/email/analyze response</summary>
        <p class="muted">Closed by default for reviewers. Use this only when validating API contracts, mappings, or support tickets.</p>
        <pre>${escapeHtml(JSON.stringify(data, null, 2))}</pre>
      </details>
    `;
  }

  function integrationLab(analysis) {
    const gate = analysis.policy?.gate || {};
    const routes = analysis.routes || [];
    const context = analysis.input?.enterprise_context || {};
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
            <p class="hash-line">${escapeHtml(analysis.content_hash)}</p>
          </article>
          <article class="optimizer-context-card">
            <span class="interface-label">Policy bundle</span>
            <strong>${escapeHtml(analysis.policy?.bundle_id || "Policy")}</strong>
            <p>Version ${escapeHtml(analysis.policy?.bundle_version || "n/a")} with ${escapeHtml((analysis.policy?.rule_packs || []).length)} rule packs.</p>
          </article>
          <article class="optimizer-context-card">
            <span class="interface-label">Gate output</span>
            <strong>${escapeHtml(displayLabel(gate.status || "unknown"))}</strong>
            <p>${escapeHtml(displayLabel(gate.route || "No route"))} / send ready: ${escapeHtml(gate.send_ready ? "Yes" : "No")}</p>
          </article>
          <article class="optimizer-context-card">
            <span class="interface-label">Enterprise context</span>
            <strong>${escapeHtml(displayLabel(context.source_system || "Direct API"))}</strong>
            <p>${escapeHtml(context.campaign_id || "No campaign ID")} / ${escapeHtml(context.template_id || "No template ID")}</p>
          </article>
        </div>
        <div class="optimizer-grid optimizer-check-grid route-grid">
          ${routes.map((route) => `
            <article class="optimizer-check-card is-ok">
              <span class="label">Route</span>
              <strong>${escapeHtml(displayLabel(route.target))}</strong>
              <p>${escapeHtml(route.reason)}</p>
              <small>Sandbox adapters use this to branch HubSpot workflows, Salesforce journeys, and SendGrid/SES middleware before production credentials are connected.</small>
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
            <strong>${escapeHtml(displayLabel(gate.status || "unknown"))}</strong>
            <p>${escapeHtml(displayLabel(gate.route || "No route returned"))} from policy bundle ${escapeHtml(analysis.policy?.bundle_version || "n/a")}.</p>
          </article>
        </section>

        ${scoreExplanation(analysis)}

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
        ${b2bProfileReport()}
        ${rawJsonBlock(data)}
        ${labOverview()}
      </div>
    `;
    document.querySelector("[data-copy-report]")?.addEventListener("click", (event) => copyReport(event.currentTarget));
    document.querySelector("[data-download-report]")?.addEventListener("click", downloadReport);
    bindLabControls();
    els.outputPanel.focus();
  }

  function loadWorkflowProfileBuilder() {
    const scenario = selectedWorkflowScenario();
    state.profileGoal = scenario.goal;
    state.profileAccount = scenario.account;
    state.profileTranscript = scenario.transcript;
    state.profileResult = state.workflowProfile;
    state.profileMessage = `${scenario.label} scenario loaded in the profile builder.`;
    renderInput();
    announce("Workflow scenario loaded in the profile builder.");
  }

  async function runRevenueSignalSimulation() {
    if (state.workflowBusy) return;
    const scenario = selectedWorkflowScenario();
    const provider = selectedWorkflowProvider();
    state.workflowBusy = true;
    state.workflowMessage = `Running ${provider.label} sandbox profile and adapter simulation...`;
    state.profileGoal = scenario.goal;
    state.profileAccount = scenario.account;
    state.profileTranscript = scenario.transcript;
    renderInput();
    renderEmpty();
    try {
      const profile = await apiClient.b2bProfile?.({
        communication_history: scenario.transcript,
        account_context: scenario.account,
        campaign_goal: scenario.goal,
        workspace_id: state.workspaceId || "default",
      });
      const payload = workflowPayload(scenario, state.workflowProvider);
      const adapter = await apiClient.simulateAdapter?.(state.workflowProvider, payload);
      state.workflowProfile = profile;
      state.workflowAdapterResult = adapter;
      state.profileResult = profile;
      state.simulatorProvider = state.workflowProvider;
      state.simulatorPayload = JSON.stringify(payload, null, 2);
      state.simulatorResult = adapter;
      state.workflowMessage = `${provider.label} simulation ready: ${displayLabel(adapter?.analysis?.gate?.status || adapter?.decision || "decision returned")}.`;
      state.profileMessage = "Profile ready for strategy review.";
      trackEvent("b2b_workflow_simulation", {
        provider: state.workflowProvider,
        scenario: scenario.id,
        stage: profile?.business_profile?.buying_stage || "unknown",
      });
      announce("B2B workflow simulation complete.");
    } catch (error) {
      state.workflowProfile = null;
      state.workflowAdapterResult = null;
      state.workflowMessage = error.message || "Workflow simulation failed.";
      apiClient.clientError?.({message: state.workflowMessage, source: "b2b-workflow-lab"}).catch(() => {});
    } finally {
      state.workflowBusy = false;
      renderInput();
      renderEmpty();
    }
  }

  function bindProfileControls() {
    const goal = document.querySelector("#profile-goal");
    const account = document.querySelector("#profile-account");
    const transcript = document.querySelector("#profile-transcript");
    const buildButton = document.querySelector("[data-build-profile]");
    const clearButton = document.querySelector("[data-clear-profile]");
    goal?.addEventListener("input", () => {
      state.profileGoal = goal.value;
    });
    account?.addEventListener("input", () => {
      state.profileAccount = account.value;
      if (clearButton) clearButton.disabled = !state.profileTranscript && !state.profileAccount;
    });
    transcript?.addEventListener("input", () => {
      state.profileTranscript = transcript.value;
      if (buildButton) buildButton.disabled = !state.profileTranscript.trim() || state.profileBusy;
      if (clearButton) clearButton.disabled = !state.profileTranscript && !state.profileAccount;
    });
    buildButton?.addEventListener("click", buildB2BProfile);
    clearButton?.addEventListener("click", () => {
      state.profileTranscript = "";
      state.profileAccount = "";
      state.profileResult = null;
      state.profileMessage = "";
      renderInput();
      if (state.latestData && state.latestOptimization) {
        renderResult(state.latestData, state.latestOptimization);
      } else {
        renderEmpty();
      }
      announce("B2B profile cleared.");
    });
    document.querySelectorAll("[data-profile-sample]").forEach((button) => {
      button.addEventListener("click", () => {
        const sample = profileSamples[Number(button.dataset.profileSample)];
        state.profileGoal = sample?.goal || state.profileGoal;
        state.profileAccount = sample?.account || "";
        state.profileTranscript = sample?.transcript || "";
        state.profileResult = null;
        state.profileMessage = "";
        renderInput();
        if (state.latestData && state.latestOptimization) {
          renderResult(state.latestData, state.latestOptimization);
        } else {
          renderEmpty();
        }
        document.querySelector("#profile-transcript")?.focus();
        announce(`${sample?.label || "Sample"} B2B profile loaded.`);
      });
    });
  }

  async function buildB2BProfile() {
    if (!state.profileTranscript.trim() || state.profileBusy) return;
    state.profileBusy = true;
    state.profileMessage = "Building relationship profile from business-safe signals...";
    renderInput();
    try {
      const profile = await apiClient.b2bProfile?.({
        communication_history: state.profileTranscript,
        account_context: state.profileAccount,
        campaign_goal: state.profileGoal,
        workspace_id: state.workspaceId || "default",
      });
      state.profileResult = profile;
      state.profileMessage = "Profile ready for strategy review.";
      if (state.latestData && state.latestOptimization) {
        renderResult(state.latestData, state.latestOptimization);
      } else {
        renderEmpty();
      }
      trackEvent("b2b_profile_built", {stage: profile?.business_profile?.buying_stage || "unknown"});
      announce("B2B profile complete.");
    } catch (error) {
      state.profileMessage = error.message || "B2B profile analysis failed.";
      apiClient.clientError?.({message: state.profileMessage, source: "b2b-profile"}).catch(() => {});
    } finally {
      state.profileBusy = false;
      renderInput();
    }
  }

  function bindInput() {
    const subject = document.querySelector("#email-subject");
    const body = document.querySelector("#email-body");
    const audience = document.querySelector("#email-audience");
    const intent = document.querySelector("#email-intent");
    const workspace = document.querySelector("#workspace-id");
    const environment = document.querySelector("#policy-environment");
    const form = document.querySelector("#optimizer-form");
    const clear = document.querySelector("#clear-email");
    const renderButton = document.querySelector("[data-run-render-test]");

    subject?.addEventListener("input", () => {
      state.subject = subject.value;
      state.renderResult = null;
      state.renderMessage = "";
      if (clear) clear.disabled = !state.email && !state.subject;
    });
    body?.addEventListener("input", () => {
      state.email = body.value;
      state.renderResult = null;
      state.renderMessage = "";
      const stats = localStats(state.email);
      const count = document.querySelector("#optimizer-count");
      const action = document.querySelector("#analyze-email");
      if (count) count.textContent = `${stats.words} words`;
      if (action) action.disabled = !state.email.trim() || state.busy;
      if (renderButton) renderButton.disabled = !state.email.trim() || state.renderBusy;
      if (clear) clear.disabled = !state.email && !state.subject;
    });
    audience?.addEventListener("change", () => {
      state.audience = audience.value;
    });
    intent?.addEventListener("change", () => {
      state.intent = intent.value;
    });
    workspace?.addEventListener("change", () => {
      state.workspaceId = workspace.value.trim() || "default";
      loadLabData({rerender: true});
    });
    environment?.addEventListener("change", () => {
      state.policyEnvironment = environment.value;
      state.enterpriseContext.analysis_mode = state.policyEnvironment === "sandbox" ? "authoring_lint" : state.enterpriseContext.analysis_mode;
    });
    document.querySelectorAll("[data-enterprise-context]").forEach((field) => {
      field.addEventListener("input", () => {
        state.enterpriseContext[field.dataset.enterpriseContext] = field.value;
        state.renderResult = null;
        state.renderMessage = "";
      });
      field.addEventListener("change", () => {
        state.enterpriseContext[field.dataset.enterpriseContext] = field.value;
        state.renderResult = null;
        state.renderMessage = "";
      });
    });
    document.querySelector("[data-run-render-test]")?.addEventListener("click", runRenderTest);
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
    let context;
    try {
      context = currentEnterpriseContext();
    } catch (error) {
      state.latestError = `Enterprise context JSON is invalid: ${error.message}`;
      renderError(state.latestError);
      return;
    }
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
        ...context,
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

  async function init() {
    bindNavigation();
    renderInput();
    renderEmpty();
    try {
      await apiClient.session?.();
    } catch (error) {
      state.labError = "Session check failed. Governance data may require sign-in or an API key.";
    }
    await loadLabData({rerender: true});
    announce("TextTraits enterprise email optimizer ready.");
  }

  function bindNavigation() {
    document.querySelectorAll("[data-nav-section]").forEach((button) => {
      button.addEventListener("click", () => {
        const section = button.dataset.navSection;
        const targets = {
          analyze: "#input-panel",
          "revenue-lab": "#revenue-lab-section",
          dashboard: "#dashboard-section",
          governance: "#governance-section",
          simulator: "#simulator-section",
          integrations: "#integrations-section",
          admin: "#admin-section",
          exports: "#exports-section",
        };
        const target = document.querySelector(targets[section]);
        target?.scrollIntoView({behavior: "smooth", block: "start"});
        document.querySelectorAll("[data-nav-section]").forEach((item) => item.setAttribute("aria-current", item === button ? "page" : "false"));
      });
    });
  }

  async function loadLabData({rerender = false} = {}) {
    try {
      const [flowData, dashboard, manifestData, installKit, policyData, integrationPlan] = await Promise.all([
        apiClient.integrationFlows?.(),
        apiClient.governanceDashboard?.(state.workspaceId || "default"),
        apiClient.integrationManifests?.(),
        apiClient.installKit?.(),
        apiClient.governancePolicy?.(state.workspaceId || "default"),
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
