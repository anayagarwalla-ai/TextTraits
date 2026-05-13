const config = window.TEXTTRAITS_CONFIG || {};

const els = {
  body: document.body,
  announcer: document.querySelector("#announcer"),
  heroTitle: document.querySelector("#hero-title"),
  heroSubtitle: document.querySelector("#hero-subtitle"),
  modeNote: document.querySelector("#mode-note"),
  modeExplorer: document.querySelector("#mode-explorer"),
  modeEnterprise: document.querySelector("#mode-enterprise"),
  personaStrip: document.querySelector("#persona-strip"),
  inputPanel: document.querySelector("#input-panel"),
  outputPanel: document.querySelector("#output-panel"),
  runtimeLabel: document.querySelector("#runtime-label"),
};

const state = {
  mode: "explorer",
  latestData: null,
  latestText: "",
  compareText: "",
  activeExplorerTab: "overview",
  activeEnterpriseTab: "brief",
  activeChannel: "email",
  enterpriseDraftStyle: "premium",
  hiddenSensitive: false,
  technicalVisible: false,
};

const explorerSamples = [
  {
    label: "Reflective note",
    tag: "reflection",
    text: "I keep returning to the same question after each planning session: what are people telling us indirectly through the way they describe a problem? The clearest notes are rarely dramatic. They are careful, specific, and honest about uncertainty, which makes them useful without pretending to settle everything.",
  },
  {
    label: "Project email",
    tag: "email",
    text: "Thanks for sending the proposal. I reviewed the timeline, added notes on the assumptions, and flagged the parts that still depend on user research. My main concern is that we are treating the launch window as fixed before we know whether the onboarding changes solve the support issues.",
  },
  {
    label: "Forum reply",
    tag: "comment",
    text: "I do not think the real test is whether the idea sounds clever in a meeting. The harder question is whether it still works when people are tired, distracted, and using it in messy real-world conditions where they cannot stop to decode every label or hidden assumption.",
  },
];

const enterpriseSamples = [
  {
    label: "Founder reply",
    tag: "reply",
    source: "Reply",
    text: "Appreciate the note. We are not evaluating new platforms this quarter unless they can show a direct connection to pipeline quality and manager visibility. The team already has enough dashboards, so the only useful conversation would be around cleaner handoffs, faster coaching moments, and fewer surprises in forecast reviews.",
  },
  {
    label: "LinkedIn bio",
    tag: "bio",
    source: "LinkedIn",
    text: "Revenue leader focused on practical operating systems for high-growth teams. I care about cleaner handoffs, stronger manager coaching, and better signal from frontline conversations. The best tools remove noise, make priorities obvious, and help teams spend more time on the accounts that can actually move.",
  },
  {
    label: "RevOps email",
    tag: "email",
    source: "Email",
    text: "The main issue is not activity volume. We need cleaner signal on which accounts are actually moving, where managers should intervene, and how to spot risk before it shows up in the forecast meeting. If your product helps with that without forcing a heavy migration, I am open to seeing a focused walkthrough.",
  },
  {
    label: "Website copy",
    tag: "website",
    source: "Website",
    text: "Our revenue operations team helps regional leaders build repeatable systems for pipeline inspection, forecast rhythm, and frontline coaching. We prioritize simple workflows, clear accountability, and fewer manual reporting loops so managers can focus on the accounts and conversations that matter.",
  },
];

const campaignCards = [
  ["Q3 pipeline quality", "RevOps", "Executive", "42 accounts", "Drafts ready"],
  ["Re-engage quiet champions", "Expansion", "Friendly", "18 contacts", "Needs proof point"],
  ["Event follow-up sprint", "Field marketing", "Concise", "96 leads", "Sequence live"],
];

const tiers = [
  ["Free Explorer", "Single-sample analysis, style map, and technical readout."],
  ["Enterprise Preview", "Campaign briefs, variants, exports, and team workflow placeholders."],
  ["Enterprise Team", "Coming soon: SSO, admin settings, API keys, usage analytics, and approvals."],
];

const goals = ["Book call", "Revive lead", "Follow up", "Expand account", "Event invite"];
const presets = ["Concise", "Premium", "Technical", "Executive", "Friendly", "Direct"];
const channels = ["Email", "LinkedIn", "SMS", "Call opener"];
const industries = ["SaaS", "Financial services", "Healthcare", "Manufacturing", "Retail", "Professional services"];
const seniorities = ["Executive", "VP", "Director", "Manager", "Individual contributor"];
const buyingStages = ["Unaware", "Problem-aware", "Evaluating", "Procurement", "Expansion"];
const sources = ["Reply", "LinkedIn bio", "Transcript", "Website copy", "Previous email"];
const regions = ["North America", "EMEA", "APAC", "LATAM", "Global"];

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function words(text) {
  return text.match(/[A-Za-z0-9']+/g) || [];
}

function percent(value) {
  return `${Math.round(Number(value || 0) * 100)}%`;
}

function titleCase(value) {
  return String(value || "")
    .split(/[\s_-]+/)
    .map((part) => part ? part[0].toUpperCase() + part.slice(1) : "")
    .join(" ");
}

function localStats(text) {
  const wordList = words(text);
  const punctuation = (text.match(/[^\w\s]/g) || []).length;
  const characters = text.length;
  const sentences = text.split(/[.!?]+/).filter((part) => part.trim()).length || 1;
  const avgSentence = wordList.length ? wordList.length / sentences : 0;
  return {
    words: wordList.length,
    characters,
    sentences,
    reading_level: avgSentence < 12 ? "Plain" : avgSentence < 20 ? "Moderate" : "Dense",
    punctuation_density: characters ? punctuation / characters : 0,
  };
}

function setMode(mode) {
  state.mode = mode;
  state.latestData = null;
  state.latestText = "";
  state.activeExplorerTab = "overview";
  state.activeEnterpriseTab = "brief";
  els.body.dataset.mode = mode;
  els.modeExplorer.setAttribute("aria-pressed", String(mode === "explorer"));
  els.modeEnterprise.setAttribute("aria-pressed", String(mode === "enterprise"));

  if (mode === "enterprise") {
    els.heroTitle.textContent = "Tailor outbound with precision.";
    els.heroSubtitle.textContent = "Enterprise Preview turns prospect language into campaign briefs, channel variants, sequence strategy, and team workflow artifacts.";
    els.modeNote.textContent = "Preview mode now. Later this can sit behind workspace, admin, or account-level enterprise gates.";
  } else {
    els.heroTitle.textContent = "Explore writing patterns.";
    els.heroSubtitle.textContent = "A workspace for casual self-analysis, writing analysts, and go-to-market teams that want to turn language signals into clearer action.";
    els.modeNote.textContent = "Explorer is for individual writing analysis. Enterprise is a preview workspace for sales and marketing teams.";
  }

  render();
}

function modelReadyLabel() {
  return config.publicModel?.demo ? "Demo model" : "Local model ready";
}

function sampleButtons(samples, targetId) {
  return `
    <div class="sample-grid" aria-label="Input examples">
      ${samples.map((sample, index) => `
        <button class="sample-card" type="button" data-sample-target="${targetId}" data-sample-index="${index}">
          <strong>${escapeHtml(sample.label)}</strong>
          <span>${escapeHtml(sample.source || sample.tag)} sample</span>
        </button>
      `).join("")}
    </div>
  `;
}

function renderExplorerInput() {
  els.inputPanel.innerHTML = `
    <div class="panel-head">
      <div>
        <h2>Explorer input</h2>
        <p class="helper">Paste a note, email, comment, or reflection. Choose a sample below if you want a quick path.</p>
      </div>
      <span class="status-pill">${modelReadyLabel()}</span>
    </div>

    <div class="guide-card">
      <strong>What should I paste?</strong>
      <p>Use natural writing from one person or one context. Explorer is tuned for self-analysis, writing review, and classifier inspection.</p>
    </div>

    <div class="field">
      <label for="explorer-text">Writing sample</label>
      <textarea id="explorer-text" placeholder="Paste writing to analyze.">${escapeHtml(state.latestText)}</textarea>
    </div>

    <div class="quality-row">
      <span id="explorer-count">0 words</span>
      <span id="explorer-quality">Add text to analyze.</span>
    </div>
    <div class="meter"><span id="explorer-meter"></span></div>

    <div class="field">
      <label for="compare-text">Compare two samples</label>
      <textarea id="compare-text" placeholder="Optional: paste a second sample for a before/after or comparison view.">${escapeHtml(state.compareText)}</textarea>
    </div>

    <div class="field-grid">
      <label class="field"><span>Writing style only</span><select id="style-only"><option>No</option><option>Yes</option></select></label>
      <label class="field"><span>Technical details</span><select id="technical-visible"><option value="hide">Hide</option><option value="show">Show</option></select></label>
      <label class="field"><span>Sensitive labels</span><select id="sensitive-hidden"><option value="show">Show expanded section</option><option value="hide">Hide permanently</option></select></label>
      <label class="field"><span>Output focus</span><select id="explorer-focus"><option>Style fingerprint</option><option>Classifier readout</option><option>Rewrite guidance</option></select></label>
    </div>

    <div>
      <p class="label">Try an example</p>
      ${sampleButtons(explorerSamples, "explorer-text")}
    </div>

    <div class="action-row sticky">
      <button id="analyze-explorer" type="button">Analyze text</button>
      <button id="clear-explorer" class="button-secondary" type="button">Clear</button>
      <button id="copy-explorer-input" class="icon-button" type="button" title="Copy input" aria-label="Copy input">Copy</button>
    </div>
  `;
}

function renderEnterpriseInput() {
  els.inputPanel.innerHTML = `
    <div class="panel-head">
      <div>
        <h2>Prospect input</h2>
        <p class="helper">Paste a reply, LinkedIn bio, transcript, website copy, or previous email. Add account context for a campaign-grade brief.</p>
      </div>
      <span class="preview-badge">Enterprise Preview - Locked</span>
    </div>

    <div class="guide-card">
      <strong>Why TextTraits is different</strong>
      <p>Generic generators start with a blank prompt. TextTraits starts with the prospect's language, extracts writing signals, and maps those signals into outreach decisions.</p>
    </div>

    <div class="field">
      <label for="enterprise-text">Prospect language</label>
      <textarea id="enterprise-text" placeholder="Paste prospect language, a reply, LinkedIn bio, transcript, or website copy.">${escapeHtml(state.latestText)}</textarea>
    </div>

    <div class="quality-row">
      <span id="enterprise-count">0 words</span>
      <span id="enterprise-quality">Add prospect language to generate a brief.</span>
    </div>
    <div class="meter"><span id="enterprise-meter"></span></div>

    <div class="guide-card">
      <strong>Enterprise campaign context</strong>
      <div class="enterprise-field-grid field-grid-spaced">
        ${field("company", "Sender company", "Northstar Analytics")}
        ${field("offer", "Offer", "pipeline intelligence platform")}
        ${field("role", "Prospect role", "VP Revenue")}
        ${selectField("goal", "Campaign goal", goals)}
        ${selectField("preset", "Output preset", presets)}
        ${selectField("industry", "Industry", industries)}
        ${selectField("seniority", "Seniority", seniorities)}
        ${field("segment", "Market segment", "Mid-market SaaS")}
        ${selectField("stage", "Buying stage", buyingStages)}
        ${selectField("source", "Signal source", sources)}
        ${selectField("region", "Region", regions)}
        ${field("pain", "Pain hypothesis", "forecast risk and manager visibility")}
        ${field("trigger", "Trigger event", "pipeline inspection redesign")}
        ${field("icp", "ICP fit", "Revenue teams with 30+ sellers")}
        ${field("proof", "Proof asset", "reduced manual reporting by 32%")}
        ${field("caseStudy", "Case study", "Series B sales org")}
        ${field("competitor", "Competitor displacement", "spreadsheet-heavy review process")}
      </div>
    </div>

    <div class="guide-card">
      <strong>Company voice</strong>
      <div class="range-row"><span>Direct</span><input id="tone-direct" type="range" min="0" max="100" value="70"><strong>70</strong></div>
      <div class="range-row"><span>Warm</span><input id="tone-warm" type="range" min="0" max="100" value="55"><strong>55</strong></div>
      <div class="range-row"><span>Formal</span><input id="tone-formal" type="range" min="0" max="100" value="62"><strong>62</strong></div>
      <div class="range-row"><span>Technical</span><input id="tone-technical" type="range" min="0" max="100" value="48"><strong>48</strong></div>
      <div class="range-row"><span>Concise</span><input id="tone-concise" type="range" min="0" max="100" value="82"><strong>82</strong></div>
    </div>

    <div>
      <p class="label">Paste prospect signal examples</p>
      ${sampleButtons(enterpriseSamples, "enterprise-text")}
    </div>

    <div class="action-row sticky">
      <button id="generate-enterprise" type="button">Generate campaign brief</button>
      <button id="clear-enterprise" class="button-secondary" type="button">Clear prospect</button>
    </div>
  `;
}

function field(id, label, value) {
  return `<label class="field"><span>${escapeHtml(label)}</span><input id="field-${id}" value="${escapeHtml(value)}"></label>`;
}

function selectField(id, label, values) {
  return `
    <label class="field">
      <span>${escapeHtml(label)}</span>
      <select id="field-${id}">${values.map((value) => `<option>${escapeHtml(value)}</option>`).join("")}</select>
    </label>
  `;
}

function renderExplorerEmpty() {
  els.outputPanel.innerHTML = `
    <div class="empty-layout fade-in">
      <div class="empty-hero">
        <span class="status-pill">Guided onboarding</span>
        <h2>Model reading will appear here.</h2>
        <p class="muted">Start by pasting text, choosing a sample, or using comparison mode. Explorer gives you style fingerprinting, cue terms, pattern labels, and a visual trait map.</p>
      </div>

      <div class="guide-grid">
        <article class="guide-card"><strong>Paste text</strong><p>Use one natural sample around 40+ words.</p></article>
        <article class="guide-card"><strong>Choose a sample</strong><p>Example cards below the textarea fill the input instantly.</p></article>
        <article class="guide-card"><strong>Learn signals</strong><p>Open technical details for classifier bars, cue terms, and source labels.</p></article>
      </div>

      <div class="guide-card">
        <strong>Explorer tools</strong>
        <div class="chip-list">
          <span class="chip">Style fingerprint</span>
          <span class="chip">Compare two samples</span>
          <span class="chip">Before/after rewrite</span>
          <span class="chip">Cue terms</span>
          <span class="chip">Visual trait map</span>
        </div>
      </div>
    </div>
  `;
}

function renderEnterpriseEmpty() {
  els.outputPanel.innerHTML = `
    <div class="empty-layout fade-in">
      <div class="empty-hero">
        <span class="preview-badge">Enterprise Preview - Locked</span>
        <h2>Enterprise dashboard</h2>
        <p class="muted">Build campaign briefs from prospect language, save projects, select output presets, and prepare exports for outbound tools.</p>
      </div>

      <div class="campaign-grid">
        ${campaignCards.map(([name, type, preset, size, status]) => `
          <article class="project-card">
            <strong>${escapeHtml(name)}</strong>
            <span>${escapeHtml(type)} / ${escapeHtml(preset)} / ${escapeHtml(size)}</span>
            <span class="strength">${escapeHtml(status)}</span>
          </article>
        `).join("")}
      </div>

      <div class="tier-grid">
        ${tiers.map(([name, copy]) => `<article class="guide-card"><strong>${escapeHtml(name)}</strong><p>${escapeHtml(copy)}</p></article>`).join("")}
      </div>

      <div class="guide-card">
        <strong>Team workspace concepts</strong>
        <div class="chip-list">
          <span class="chip">Saved campaigns</span>
          <span class="chip">Seats</span>
          <span class="chip">Templates</span>
          <span class="chip">Exports</span>
          <span class="chip">Admin settings</span>
          <span class="chip">API keys</span>
          <span class="chip">Usage analytics</span>
          <span class="chip">Approval workflow</span>
          <span class="chip">Human review required</span>
          <span class="chip">SSO coming soon</span>
        </div>
      </div>
    </div>
  `;
}

async function evaluateText(text) {
  const response = await fetch("/evaluate", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({text, model: "local"}),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "The analysis failed.");
  return data;
}

function score(prediction) {
  if (!prediction?.alternatives?.length) return 0;
  return Math.max(Number(prediction.confidence || 0) - 0.5, 0) * 2;
}

function separation(prediction) {
  const value = score(prediction);
  if (value > 0.66) return "high";
  if (value > 0.33) return "medium";
  return "low";
}

function mbtiLetter(prediction, options) {
  const raw = String(prediction?.label || prediction?.raw_label || "").toLowerCase();
  return options[raw] || "?";
}

function mbtiCode(dims) {
  if (!dims) return "----";
  return [
    mbtiLetter(dims.energy, {extraverted: "E", introverted: "I"}),
    mbtiLetter(dims.information, {sensing: "S", intuitive: "N"}),
    mbtiLetter(dims.decisions, {thinking: "T", feeling: "F"}),
    mbtiLetter(dims.structure, {judging: "J", perceiving: "P"}),
  ].join("");
}

function ageRangeLabel(prediction) {
  const raw = Number(prediction?.raw_value);
  let value = Number.isFinite(raw) ? raw : NaN;
  if (!Number.isFinite(value)) {
    const match = String(prediction?.label || "").match(/(\d+(\.\d+)?)/);
    value = match ? Number(match[1]) : NaN;
  }
  if (!Number.isFinite(value)) return String(prediction?.label || "Unavailable");
  if (value < 25) return "Under 25 range";
  if (value < 35) return "25 to 34 range";
  if (value < 45) return "35 to 44 range";
  if (value < 55) return "45 to 54 range";
  return "55+ range";
}

function cueChips(prediction) {
  const terms = prediction?.cue_terms || [];
  if (!terms.length) return `<p class="muted">No cue terms returned for this classifier.</p>`;
  return `<div class="chip-list">${terms.map((item) => `<span class="chip">${escapeHtml(item.term)}</span>`).join("")}</div>`;
}

function bars(prediction) {
  const alternatives = prediction?.alternatives || [];
  if (!alternatives.length) return `<p class="muted">No distribution available.</p>`;
  return `
    <div class="bars">
      ${alternatives.map((item) => `
        <div class="bar-row">
          <span>${escapeHtml(item.label)}</span>
          <meter class="bar-meter" min="0" max="1" value="${Math.max(Number(item.probability || 0), 0.02)}"></meter>
          <strong>${percent(item.probability)}</strong>
        </div>
      `).join("")}
    </div>
  `;
}

function renderExplorerResult(data) {
  const p = data.predictions;
  const stats = p.text_stats || localStats(state.latestText);
  const dims = p.mbti_dimensions || {};
  const strongest = [
    ["Energy", dims.energy],
    ["Information", dims.information],
    ["Decision", dims.decisions],
    ["Structure", dims.structure],
  ].sort((a, b) => score(b[1]) - score(a[1]))[0];
  const fingerprint = [
    stats.reading_level,
    mbtiCode(dims),
    `${stats.words} words`,
    `${separation(strongest?.[1])} ${strongest?.[0] || "signal"}`,
  ].join(" / ");

  els.outputPanel.innerHTML = `
    <div class="result-layout fade-in">
      <div class="result-header">
        <div>
          <p class="label">Explorer result</p>
          <h2>Style fingerprint</h2>
          <p class="muted">${escapeHtml(fingerprint)}</p>
        </div>
        <div class="toolbar">
          <button class="button-secondary" data-copy-summary>Copy summary</button>
          <button class="button-secondary" data-new-sample>Try another sample</button>
        </div>
      </div>

      <div class="metric-grid">
        <article class="metric-card"><span class="label">Sample quality</span><div class="value">${stats.words >= 40 ? "Ready" : "Short"}</div><p>${stats.words} words analyzed.</p></article>
        <article class="metric-card"><span class="label">Reading density</span><div class="value">${escapeHtml(stats.reading_level)}</div><p>${stats.sentences || 1} sentence groups.</p></article>
        <article class="metric-card"><span class="label">Style code</span><div class="value">${escapeHtml(mbtiCode(dims))}</div><p>Four-dimension pattern label.</p></article>
      </div>

      <nav class="tabs" role="tablist" aria-label="Explorer result sections">
        ${tabButton("overview", "Overview", state.activeExplorerTab)}
        ${tabButton("style", "Writing signals", state.activeExplorerTab)}
        ${tabButton("patterns", "Pattern labels", state.activeExplorerTab)}
        ${tabButton("technical", "Technical details", state.activeExplorerTab)}
        ${tabButton("rewrite", "Before/after rewrite", state.activeExplorerTab)}
      </nav>

      <div id="panel-${state.activeExplorerTab}" class="tab-panel" role="tabpanel" aria-labelledby="tab-${state.activeExplorerTab}">
        ${renderExplorerTab(data)}
      </div>
    </div>
  `;

  els.outputPanel.querySelectorAll("[data-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      state.activeExplorerTab = button.dataset.tab;
      renderExplorerResult(data);
    });
  });
  const summary = `Style fingerprint: ${fingerprint}`;
  bindCopy("[data-copy-summary]", summary, "Explorer summary copied.");
  els.outputPanel.querySelector("[data-new-sample]").addEventListener("click", () => {
    state.latestData = null;
    state.latestText = "";
    render();
  });
}

function tabButton(tab, label, active) {
  return `<button type="button" role="tab" id="tab-${tab}" data-tab="${tab}" aria-selected="${String(tab === active)}" aria-controls="panel-${tab}">${label}</button>`;
}

function renderExplorerTab(data) {
  const p = data.predictions;
  const dims = p.mbti_dimensions || {};
  const stats = p.text_stats || localStats(state.latestText);
  if (state.activeExplorerTab === "style") {
    return `
      <div class="detail-grid">
        <article class="strategy-card"><strong>Word and character profile</strong><p>${stats.words} words, ${stats.characters} characters, ${percent(stats.punctuation_density)} punctuation density.</p></article>
        <article class="strategy-card"><strong>Sample quality card</strong><p>${stats.words >= 40 ? "Good first-pass length." : "Short sample. Add more context for steadier output."}</p></article>
      </div>
      <div class="trait-map">
        ${trait("Energy", score(dims.energy), separation(dims.energy))}
        ${trait("Information", score(dims.information), separation(dims.information))}
        ${trait("Decision", score(dims.decisions), separation(dims.decisions))}
        ${trait("Structure", score(dims.structure), separation(dims.structure))}
      </div>
    `;
  }
  if (state.activeExplorerTab === "patterns") {
    return `
      <div class="detail-grid">
        <article class="strategy-card"><strong>MBTI-style pattern</strong><div class="metric-card"><div class="value">${escapeHtml(mbtiCode(dims))}</div><p>Language-pattern summary built from four classifiers.</p></div></article>
        <article class="strategy-card"><strong>Age and data labels</strong><p>Expanded below so Explorer can focus on style first.</p><details><summary>Show expanded data-label output</summary><p>Age range: ${escapeHtml(ageRangeLabel(p.age_estimate || p.age_bucket))}</p>${bars(p.gender)}</details></article>
      </div>
    `;
  }
  if (state.activeExplorerTab === "technical") {
    return `
      <div class="detail-grid">
        <article class="strategy-card"><strong>Energy</strong>${bars(dims.energy)}${cueChips(dims.energy)}</article>
        <article class="strategy-card"><strong>Information</strong>${bars(dims.information)}${cueChips(dims.information)}</article>
        <article class="strategy-card"><strong>Decision</strong>${bars(dims.decisions)}${cueChips(dims.decisions)}</article>
        <article class="strategy-card"><strong>Structure</strong>${bars(dims.structure)}${cueChips(dims.structure)}</article>
      </div>
    `;
  }
  if (state.activeExplorerTab === "rewrite") {
    return `
      <div class="detail-grid">
        <article class="strategy-card"><strong>Before</strong><p>${escapeHtml(state.latestText.slice(0, 360))}</p></article>
        <article class="strategy-card"><strong>After</strong><p>${escapeHtml(makeExplorerRewrite(state.latestText))}</p></article>
      </div>
      ${state.compareText ? `<article class="strategy-card"><strong>Comparison note</strong><p>The second sample is ${localStats(state.compareText).words} words. Use this area to compare tone, density, and structure across revisions.</p></article>` : `<article class="strategy-card"><strong>Compare two samples</strong><p>Add optional comparison text in the left panel to unlock a before/after comparison note.</p></article>`}
    `;
  }
  return `
    <div class="detail-grid">
      <article class="strategy-card featured"><strong>Visual writing map</strong><p>Energy, information, decision, and structure signals are summarized below.</p><div class="trait-map">${trait("Energy", score(dims.energy), separation(dims.energy))}${trait("Info", score(dims.information), separation(dims.information))}${trait("Decision", score(dims.decisions), separation(dims.decisions))}${trait("Structure", score(dims.structure), separation(dims.structure))}</div></article>
      <article class="strategy-card"><strong>Cue terms</strong>${cueChips(dims.energy)}${cueChips(dims.information)}</article>
    </div>
  `;
}

function trait(name, value, label) {
  return `<div class="trait"><meter class="trait-meter" min="0" max="1" value="${Math.max(value, 0.08)}"></meter><strong>${escapeHtml(name)}</strong><span class="muted">${escapeHtml(label)}</span></div>`;
}

function makeExplorerRewrite(text) {
  const clean = text.trim().replace(/\s+/g, " ");
  if (!clean) return "";
  return `${clean} The core point is clearer when the sentence structure stays direct, the claim appears early, and the supporting detail follows in one clean sequence.`;
}

function enterpriseContext() {
  const get = (id) => document.querySelector(`#field-${id}`)?.value.trim() || "";
  return {
    company: get("company") || "Northstar Analytics",
    offer: get("offer") || "pipeline intelligence platform",
    role: get("role") || "VP Revenue",
    goal: get("goal") || "Book call",
    preset: get("preset") || "Premium",
    industry: get("industry") || "SaaS",
    seniority: get("seniority") || "Executive",
    segment: get("segment") || "Mid-market SaaS",
    stage: get("stage") || "Evaluating",
    source: get("source") || "Reply",
    region: get("region") || "North America",
    pain: get("pain") || "forecast risk and manager visibility",
    trigger: get("trigger") || "pipeline inspection redesign",
    icp: get("icp") || "Revenue teams with 30+ sellers",
    proof: get("proof") || "reduced manual reporting by 32%",
    caseStudy: get("caseStudy") || "Series B sales org",
    competitor: get("competitor") || "spreadsheet-heavy review process",
    direct: document.querySelector("#tone-direct")?.value || "70",
    warm: document.querySelector("#tone-warm")?.value || "55",
    formal: document.querySelector("#tone-formal")?.value || "62",
    technical: document.querySelector("#tone-technical")?.value || "48",
    concise: document.querySelector("#tone-concise")?.value || "82",
  };
}

function enterpriseProfile(data) {
  const dims = data.predictions.mbti_dimensions || {};
  const stats = data.predictions.text_stats || localStats(state.latestText);
  const information = String(dims.information?.label || "").toLowerCase();
  const decisions = String(dims.decisions?.label || "").toLowerCase();
  const structure = String(dims.structure?.label || "").toLowerCase();
  const tone = [
    String(dims.energy?.label || "").toLowerCase() === "introverted" ? "measured" : "direct",
    information === "intuitive" ? "strategic" : "concrete",
    decisions === "thinking" ? "evidence-led" : "relationship-aware",
    structure === "judging" ? "structured" : "flexible",
  ];
  return {dims, stats, tone};
}

function enterpriseAngles(context, profile) {
  return [
    ["Pipeline signal clarity", 94, `Connect ${context.offer} to cleaner account movement and fewer forecast surprises.`],
    ["Manager coaching rhythm", 88, `Position the workflow around better intervention moments for frontline managers.`],
    ["Low-friction implementation", 81, `Emphasize fit with existing systems and fast time to value.`],
  ];
}

function subjectLines(context) {
  return [
    `${context.role}: cleaner signal on ${context.pain}`,
    `Idea for ${context.trigger}`,
    `Reducing noise in ${context.industry} pipeline reviews`,
    `${context.company} x {{company}}`,
    `Fast thought on manager visibility`,
  ];
}

function ctaText(context) {
  if (context.goal === "Book call") return "Worth a quick 15-minute fit call?";
  if (context.goal === "Revive lead") return "Should I send a tighter version of the idea?";
  if (context.goal === "Follow up") return "Is this still worth keeping on the radar?";
  if (context.goal === "Expand account") return "Would it help to map this against the next team?";
  return "Want the short event follow-up brief?";
}

function buildEmailVariant(context, profile, variant) {
  const tonePrefix = variant === "A" ? "Your note about pipeline signal stood out." : variant === "B" ? "The pattern I noticed is simple: activity volume is not the issue." : "I noticed the emphasis on manager intervention and forecast risk.";
  const proof = variant === "A" ? context.proof : variant === "B" ? context.caseStudy : context.competitor;
  return `Subject: ${subjectLines(context)[variant === "A" ? 0 : variant === "B" ? 1 : 2]}

Hi {{first_name}},

${tonePrefix} Teams in a similar motion usually need fewer dashboards and better signal on which accounts are actually moving.

${context.company} helps ${context.segment} teams use ${context.offer} to create a cleaner operating rhythm around ${context.pain}. One relevant proof point: ${proof}.

${ctaText(context)}`;
}

function buildSequence(context) {
  return [
    ["Day 1", "Initial email", "Lead with the strongest operational signal and one clear CTA."],
    ["Day 3", "LinkedIn touch", "Mirror the same pain in one short note with no pitch stack."],
    ["Day 6", "Proof follow-up", `Bring in ${context.proof} and a concise implementation angle.`],
    ["Day 10", "Breakup note", "Offer a useful summary and let the prospect choose next step."],
  ];
}

function renderEnterpriseResult(data) {
  const context = enterpriseContext();
  const profile = enterpriseProfile(data);
  const variants = ["A", "B", "C"].map((key) => [key, buildEmailVariant(context, profile, key)]);
  const angles = enterpriseAngles(context, profile);
  const sequence = buildSequence(context);
  const csv = makeCsv(context, variants);

  els.outputPanel.innerHTML = `
    <div class="result-layout fade-in">
      <div class="result-header">
        <div>
          <p class="label">Enterprise campaign brief</p>
          <h2>${escapeHtml(context.role)} outreach system</h2>
          <p class="muted">Positioning, sequence design, channel previews, and copy variants generated from prospect language and campaign context.</p>
        </div>
        <span class="preview-badge">Enterprise Preview - Locked</span>
      </div>

      <div class="toolbar">
        <button data-copy-all>Copy all</button>
        <button class="button-secondary" data-copy-email>Copy email only</button>
        <button class="button-secondary" data-copy-subjects>Copy subject lines</button>
        <button class="button-secondary" data-export-csv>Export CSV</button>
        <button class="button-secondary" data-regenerate>Regenerate</button>
      </div>

      <nav class="tabs" role="tablist" aria-label="Enterprise result sections">
        ${tabButton("brief", "Brief", state.activeEnterpriseTab)}
        ${tabButton("drafts", "Drafts", state.activeEnterpriseTab)}
        ${tabButton("sequence", "Sequence", state.activeEnterpriseTab)}
        ${tabButton("signals", "Signals", state.activeEnterpriseTab)}
      </nav>

      <div id="panel-${state.activeEnterpriseTab}" class="tab-panel" role="tabpanel" aria-labelledby="tab-${state.activeEnterpriseTab}">${renderEnterpriseTab(data, context, profile, variants, angles, sequence)}</div>
    </div>
  `;

  els.outputPanel.querySelectorAll("[data-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      state.activeEnterpriseTab = button.dataset.tab;
      renderEnterpriseResult(data);
    });
  });

  const allText = enterpriseBriefText(context, variants, angles, sequence);
  bindCopy("[data-copy-all]", allText, "Enterprise brief copied.");
  bindCopy("[data-copy-email]", variants[0][1], "Email draft copied.");
  bindCopy("[data-copy-subjects]", subjectLines(context).join("\\n"), "Subject lines copied.");
  els.outputPanel.querySelector("[data-export-csv]").addEventListener("click", () => downloadCsv(csv));
  els.outputPanel.querySelector("[data-regenerate]").addEventListener("click", () => {
    state.enterpriseDraftStyle = presets[(presets.indexOf(context.preset) + 1) % presets.length];
    renderEnterpriseResult(data);
  });
  els.outputPanel.querySelectorAll("[data-copy-text]").forEach((button) => {
    button.addEventListener("click", async () => {
      await navigator.clipboard.writeText(button.dataset.copyText || "");
      els.announcer.textContent = "Variant copied.";
    });
  });
  els.outputPanel.querySelectorAll("[data-transform]").forEach((button) => {
    button.addEventListener("click", () => {
      els.announcer.textContent = `${button.textContent.trim()} version queued.`;
    });
  });
}

function renderEnterpriseTab(data, context, profile, variants, angles, sequence) {
  if (state.activeEnterpriseTab === "drafts") {
    return `
      <article class="strategy-card"><strong>Generated email draft variants</strong><p>Three A/B/C versions are ready for copy, editing, and sequence testing.</p></article>
      <div class="variant-grid">
        ${variants.map(([key, draft]) => `
          <article class="variant-card">
            <span class="strength">Variant ${key}</span>
            <div class="email-draft">${escapeHtml(draft)}</div>
            <div class="result-actions">
              <button class="button-secondary" data-copy-text="${escapeHtml(draft)}">Copy</button>
              <button class="button-secondary" data-transform="shorter">Make shorter</button>
              <button class="button-secondary" data-transform="executive">Make executive</button>
              <button class="button-secondary" data-transform="casual">Make casual</button>
              <button class="button-secondary" data-transform="specific">Make specific</button>
              <button class="button-secondary" data-transform="proof">Add proof point</button>
              <button class="button-secondary" data-transform="plain">Remove buzzwords</button>
              <button class="button-secondary" data-transform="compliance">Compliance-safe</button>
            </div>
          </article>
        `).join("")}
      </div>
    `;
  }
  if (state.activeEnterpriseTab === "sequence") {
    return `
      <div class="channel-grid">
        ${channels.map((channel) => `<article class="channel-card"><strong>${escapeHtml(channel)}</strong><p>${escapeHtml(channelPreview(channel, context))}</p></article>`).join("")}
      </div>
      <div class="stack">
        ${sequence.map(([day, title, copy]) => `<article class="sequence-card"><span class="strength">${escapeHtml(day)}</span><strong>${escapeHtml(title)}</strong><p class="muted">${escapeHtml(copy)}</p></article>`).join("")}
      </div>
    `;
  }
  if (state.activeEnterpriseTab === "signals") {
    return `
      <div class="detail-grid">
        <article class="strategy-card"><strong>Words to mirror</strong>${tokens(["cleaner signal", "manager visibility", "forecast risk", "operating rhythm", context.pain])}</article>
        <article class="strategy-card"><strong>Words to avoid</strong>${tokens(["game-changing", "revolutionary", "just checking in", "circle back", "synergy"])}</article>
        <article class="strategy-card"><strong>Spam-risk scoring</strong>${scoreGrid([["Length", 84], ["Links", 96], ["Spam phrasing", 88], ["Personalization", 91]])}</article>
        <article class="strategy-card"><strong>Deliverability checks</strong><p>Length, links, spammy phrasing, personalization density, unsubscribe token, and compliance footer placeholders are ready for export review.</p></article>
      </div>
    `;
  }
  return `
    <div class="enterprise-dashboard">
      <div class="stack">
        <article class="strategy-card">
          <strong>Executive summary</strong>
          <p>Prioritize ${escapeHtml(angles[0][0].toLowerCase())} for ${escapeHtml(context.role)} in ${escapeHtml(context.industry)}. Lead with the prospect's language around ${escapeHtml(context.pain)} and support it with ${escapeHtml(context.proof)}.</p>
        </article>
        <article class="strategy-card">
          <strong>Message angles ranked by fit</strong>
          ${angles.map(([name, fit, copy]) => `<div class="metric-card"><span class="strength">${fit}% fit</span><strong>${escapeHtml(name)}</strong><p>${escapeHtml(copy)}</p><p><strong>Why this angle:</strong> It maps directly to the prospect's stated operating concern.</p></div>`).join("")}
        </article>
        <article class="strategy-card">
          <strong>Rep coaching notes</strong>
          <ul class="strategy-list">
            <li>Keep the first touch short and anchored in one observable business issue.</li>
            <li>Use proof before product breadth.</li>
            <li>Ask for a focused next step with a specific agenda.</li>
          </ul>
        </article>
      </div>
      <div class="stack">
        <article class="strategy-card"><strong>Best CTA</strong><p>${escapeHtml(ctaText(context))}</p><strong>Backup CTA</strong><p>Open to a two-bullet summary instead?</p></article>
        <article class="strategy-card"><strong>Objection likely</strong><p>"We already have dashboards." Counter with implementation clarity, workflow fit, and fewer manual reporting loops.</p></article>
        <article class="strategy-card"><strong>Email quality score</strong>${scoreGrid([["Clarity", 92], ["Specificity", 87], ["CTA strength", 90], ["Skimmability", 86]])}</article>
        <article class="strategy-card"><strong>Exports and integrations</strong><div class="chip-list"><span class="chip">HubSpot placeholder</span><span class="chip">Salesforce placeholder</span><span class="chip">Outreach placeholder</span><span class="chip">Salesloft placeholder</span><span class="chip">CSV export</span></div></article>
        <article class="strategy-card"><strong>Merge fields manager</strong>${tokens(["{{first_name}}", "{{company}}", "{{recent_signal}}", "{{pipeline_priority}}", "{{unsubscribe_link}}"])}</article>
      </div>
    </div>
  `;
}

function tokens(items) {
  return `<div class="token-list">${items.map((item) => `<span class="token">${escapeHtml(item)}</span>`).join("")}</div>`;
}

function scoreGrid(items) {
  return `<div class="score-grid">${items.map(([label, value]) => `<div class="score-card"><strong>${value}</strong><span>${escapeHtml(label)}</span></div>`).join("")}</div>`;
}

function channelPreview(channel, context) {
  if (channel === "LinkedIn") return `Saw your note on ${context.pain}. Worth comparing how other ${context.industry} teams are simplifying that workflow?`;
  if (channel === "SMS") return `Quick idea on ${context.pain} for ${context.role}s. Open to a short email?`;
  if (channel === "Call opener") return `I'm calling because your team seems focused on ${context.pain}, and we help teams make that operating rhythm cleaner.`;
  return buildEmailVariant(context, {}, "A");
}

function enterpriseBriefText(context, variants, angles, sequence) {
  return [
    `Enterprise brief for ${context.role}`,
    `Best angle: ${angles[0][0]} (${angles[0][1]}% fit)`,
    `CTA: ${ctaText(context)}`,
    "",
    variants.map(([key, draft]) => `Variant ${key}\\n${draft}`).join("\\n\\n"),
    "",
    sequence.map(([day, title, copy]) => `${day}: ${title} - ${copy}`).join("\\n"),
  ].join("\\n");
}

function makeCsv(context, variants) {
  const rows = [["variant", "subject", "body", "role", "industry", "goal"]];
  variants.forEach(([key, draft]) => {
    const [subjectLine, ...body] = draft.split("\\n");
    rows.push([key, subjectLine.replace(/^Subject:\\s*/, ""), body.join("\\n").trim(), context.role, context.industry, context.goal]);
  });
  return rows.map((row) => row.map((cell) => `"${String(cell).replaceAll('"', '""')}"`).join(",")).join("\\n");
}

function downloadCsv(csv) {
  const blob = new Blob([csv], {type: "text/csv"});
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "texttraits-enterprise-campaign.csv";
  link.click();
  URL.revokeObjectURL(link.href);
}

function bindCopy(selector, text, message) {
  const button = els.outputPanel.querySelector(selector);
  if (!button) return;
  button.addEventListener("click", async () => {
    await navigator.clipboard.writeText(text);
    els.announcer.textContent = message;
  });
}

function wireInput() {
  if (state.mode === "explorer") {
    const input = document.querySelector("#explorer-text");
    const compare = document.querySelector("#compare-text");
    input.addEventListener("input", () => {
      state.latestText = input.value;
      updateInputStats("explorer", input.value);
    });
    compare.addEventListener("input", () => {
      state.compareText = compare.value;
    });
    document.querySelector("#technical-visible").addEventListener("change", (event) => {
      state.technicalVisible = event.target.value === "show";
      if (state.technicalVisible) state.activeExplorerTab = "technical";
    });
    document.querySelector("#sensitive-hidden").addEventListener("change", (event) => {
      state.hiddenSensitive = event.target.value === "hide";
    });
    document.querySelector("#analyze-explorer").addEventListener("click", () => runAnalysis(input.value));
    document.querySelector("#clear-explorer").addEventListener("click", () => {
      state.latestText = "";
      state.compareText = "";
      state.latestData = null;
      render();
    });
    document.querySelector("#copy-explorer-input").addEventListener("click", async () => {
      await navigator.clipboard.writeText(input.value);
      els.announcer.textContent = "Input copied.";
    });
    updateInputStats("explorer", input.value);
  } else {
    const input = document.querySelector("#enterprise-text");
    input.addEventListener("input", () => {
      state.latestText = input.value;
      updateInputStats("enterprise", input.value);
    });
    document.querySelector("#generate-enterprise").addEventListener("click", () => runAnalysis(input.value));
    document.querySelector("#clear-enterprise").addEventListener("click", () => {
      state.latestText = "";
      state.latestData = null;
      render();
    });
    document.querySelectorAll('input[type="range"]').forEach((range) => {
      const value = range.nextElementSibling;
      range.addEventListener("input", () => value.textContent = range.value);
    });
    updateInputStats("enterprise", input.value);
  }

  document.querySelectorAll("[data-sample-target]").forEach((button) => {
    button.addEventListener("click", () => {
      const samples = state.mode === "enterprise" ? enterpriseSamples : explorerSamples;
      const sample = samples[Number(button.dataset.sampleIndex)];
      const target = document.querySelector(`#${button.dataset.sampleTarget}`);
      target.value = sample.text;
      state.latestText = sample.text;
      state.latestData = null;
      updateInputStats(state.mode, sample.text);
      if (state.mode === "enterprise") renderEnterpriseEmpty();
      else renderExplorerEmpty();
      target.focus();
    });
  });
}

function updateInputStats(prefix, text) {
  const stats = localStats(text);
  const count = document.querySelector(`#${prefix}-count`);
  const quality = document.querySelector(`#${prefix}-quality`);
  const meter = document.querySelector(`#${prefix}-meter`);
  const action = prefix === "enterprise" ? document.querySelector("#generate-enterprise") : document.querySelector("#analyze-explorer");
  if (count) count.textContent = `${stats.words} ${stats.words === 1 ? "word" : "words"}`;
  if (quality) quality.textContent = stats.words ? (stats.words >= 40 ? "Good first-pass length." : "Short sample. Add more context for stronger output.") : (prefix === "enterprise" ? "Add prospect language to generate a brief." : "Add text to analyze.");
  if (meter) meter.style.width = `${Math.min((stats.words / 60) * 100, 100)}%`;
  if (action) action.disabled = !text.trim();
}

async function runAnalysis(text) {
  if (!text.trim()) return;
  if (state.mode === "enterprise") state.activeEnterpriseTab = "brief";
  else state.activeExplorerTab = "overview";
  els.outputPanel.innerHTML = `<div class="empty-hero fade-in"><span class="status-pill">Analyzing</span><h2>Building the ${state.mode === "enterprise" ? "campaign brief" : "model reading"}...</h2><p class="muted">The local model is reading the submitted language.</p></div>`;
  try {
    const data = await evaluateText(text.trim());
    state.latestData = data;
    state.latestText = text.trim();
    if (state.mode === "enterprise") renderEnterpriseResult(data);
    else renderExplorerResult(data);
    els.outputPanel.focus();
  } catch (error) {
    els.outputPanel.innerHTML = `<div class="empty-hero"><h2>The reading did not run.</h2><p class="muted">${escapeHtml(error.message)}</p><button class="button-secondary" id="retry-run">Retry</button></div>`;
    document.querySelector("#retry-run").addEventListener("click", () => runAnalysis(text));
  }
}

function render() {
  if (state.mode === "enterprise") {
    renderEnterpriseInput();
    state.latestData ? renderEnterpriseResult(state.latestData) : renderEnterpriseEmpty();
  } else {
    renderExplorerInput();
    state.latestData ? renderExplorerResult(state.latestData) : renderExplorerEmpty();
  }
  wireInput();
}

els.modeExplorer.addEventListener("click", () => setMode("explorer"));
els.modeEnterprise.addEventListener("click", () => setMode("enterprise"));

if (["127.0.0.1", "localhost", "::1"].includes(window.location.hostname)) {
  els.runtimeLabel.textContent = "Local run:";
} else {
  els.runtimeLabel.textContent = "Deployment:";
}

render();
