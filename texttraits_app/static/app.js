const config = window.TEXTTRAITS_CONFIG || {};
const apiClient = window.TextTraitsApi;
const productConfig = window.TextTraitsProduct || {};
const textUtils = window.TextTraitsUtils || {};
const uiHelpers = window.TextTraitsUi || {};
const csvUtils = window.TextTraitsCsv || {};
const enterpriseCopy = window.TextTraitsEnterpriseCopy || {};
const {escapeHtml, words, percent, titleCase, localStats, todayKey} = textUtils;
const {parseCsvLine, csvCell} = csvUtils;

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
  accountCard: document.querySelector("#account-card"),
  toastStack: document.querySelector("#toast-stack"),
  runtimeLabel: document.querySelector("#runtime-label"),
  runtimeCopy: document.querySelector("#runtime-copy"),
};

const state = {
  mode: "explorer",
  latestData: null,
  latestText: "",
  compareText: "",
  activeExplorerTab: "style",
  activeEnterpriseTab: "dashboard",
  activeEnterpriseTool: "batch",
  activeChannel: "email",
  enterpriseDraftStyle: "premium",
  enterpriseContext: null,
  enterpriseDrafts: [],
  selectedVariant: "A",
  enterpriseLandingTab: "",
  enterpriseInputsCollapsed: false,
  enterpriseSetupOpen: false,
  enterpriseFocusMode: false,
  integrationSetupOpen: false,
  campaignSaved: false,
  lastGeneratedAt: "",
  lastActionNote: "",
  lastDraftChange: "",
  recipient: {
    firstName: "Maya",
    company: "Acme Revenue",
    role: "VP Revenue",
  },
  savedCampaigns: [],
  workspaceSearch: "",
  workspaceFolder: "All",
  workspaceStatus: "All",
  batchInput: "",
  batchRows: [],
  batchErrors: [],
  batchProgress: 0,
  selectedProspectId: 1,
  selectedInboxId: 0,
  crmConnections: {
    HubSpot: "needs credentials",
    Salesforce: "needs credentials",
    Outreach: "needs credentials",
    Salesloft: "needs credentials",
    Gmail: "needs credentials",
    Outlook: "needs credentials",
    "Chrome Sidebar": "packaging required",
  },
  inboxThreads: [],
  winnerSamples: [],
  outcomeStats: {
    generated: 18,
    sent: 11,
    opened: 7,
    replied: 3,
    booked: 1,
    rejected: 2,
  },
  personaLibrary: [],
  sequenceSettings: {
    length: 4,
    startDay: "Monday",
    channels: ["Email", "LinkedIn", "Email", "Call opener"],
  },
  explorerProfiles: [
    {name: "Clear operator", goal: "Make decisions easier to scan", samples: 3},
    {name: "Reflective analyst", goal: "Preserve nuance while tightening", samples: 5},
  ],
  explorerHistory: [],
  explorerJournalSearch: "",
  explorerJournalFolder: "All",
  explorerJournalOpen: false,
  explorerQuickChecksOpen: false,
  explorerStyleDetailsOpen: false,
  explorerReadingName: "",
  explorerFolder: "Daily",
  explorerWritingGoal: "Make this clearer",
  explorerRewriteGoal: "Email",
  explorerRewriteMode: "clearer",
  explorerSavedMessage: "",
  explorerPromptTitle: "",
  explorerPromptText: "",
  explorerPromptSource: "",
  batchMapping: {
    first_name: "first_name",
    company: "company",
    role: "role",
    industry: "industry",
    signal: "signal",
  },
  exportHistory: [],
  reviewQueue: [],
  teamComments: [],
  versionHistory: [],
  feedbackMemory: {
    better: 0,
    tooFormal: 0,
    tooVague: 0,
    tooLong: 0,
    moreLikeMe: 0,
  },
  onboarding: {
    complete: false,
    explorerGoal: "Clearer everyday writing",
    enterpriseGoal: "Review outbound drafts",
    teamSize: "1-5",
  },
  account: {
    authenticated: false,
    user: null,
    workspaceName: "Local workspace",
    syncStatus: "Local only",
    lastSyncedAt: "",
  },
  accountDraft: {
    name: "",
    email: "",
    verifyToken: "",
    resetToken: "",
  },
  accountResetToken: "",
  accountCodePanelOpen: false,
  accountDeletePending: false,
  adminSettings: {
    workspaceName: "TextTraits Team",
    seats: 3,
    sso: "Not configured",
    apiKey: "Not generated",
    retention: "90 days",
    auditLog: "Enabled",
  },
  tabScroll: {},
  hiddenSensitive: false,
  technicalVisible: false,
  sampleWorkspaceLoaded: false,
  accountModalOpen: false,
  accountError: "",
};

const STORAGE_KEY = "texttraits.workspace.v2";

const defaultCampaigns = [
  {name: "Forecast risk pilot", folder: "RevOps", status: "Drafts ready", updated: "Today", prospects: 42},
  {name: "Re-engage quiet champions", folder: "Expansion", status: "Needs proof point", updated: "Yesterday", prospects: 18},
  {name: "Event follow-up sprint", folder: "Field marketing", status: "Sequence live", updated: "May 10", prospects: 96},
  {name: "Procurement revive", folder: "Pipeline", status: "Needs review", updated: "May 8", prospects: 24},
];

const brandVoiceProfiles = [
  {name: "Executive concise", direct: 78, warm: 46, formal: 72, technical: 52, concise: 88, claims: ["32% less manual reporting", "2-week pilot"], forbidden: ["revolutionary", "guaranteed"], proof: ["Series B sales org", "RevOps workflow study"]},
  {name: "Founder warm", direct: 58, warm: 78, formal: 44, technical: 38, concise: 72, claims: ["fast setup", "cleaner follow-up"], forbidden: ["synergy", "blast"], proof: ["founder-led rollout"]},
  {name: "Technical buyer", direct: 68, warm: 42, formal: 66, technical: 84, concise: 70, claims: ["API-ready", "field-level audit trail"], forbidden: ["magic", "hands-off"], proof: ["implementation checklist"]},
];

const defaultPersonas = [
  {role: "VP Revenue", industry: "SaaS", icp: "30+ seller teams", objection: "already has dashboards", trigger: "forecast risk"},
  {role: "RevOps Director", industry: "SaaS", icp: "manual reporting teams", objection: "migration cost", trigger: "pipeline inspection"},
  {role: "Founder", industry: "B2B software", icp: "lean GTM team", objection: "not this quarter", trigger: "growth planning"},
];

const sampleCsv = `first_name,company,role,industry,signal
Maya,Acme Revenue,VP Revenue,SaaS,"Needs an earlier warning when renewal risk appears before the board forecast"
Jordan,Northwind Ops,RevOps Director,SaaS,"Weekly deal inspection is manual and late-stage risks are hard to coach"
Taylor,Bluepeak,Founder,B2B software,"Wants cleaner handoffs from sales calls to follow-up without adding another dashboard"`;

const sampleInboxThreads = [
  {from: "Maya at Acme", type: "objection", source: "Gmail", urgency: "High", sentiment: "Skeptical", confidence: 91, text: "We already have dashboards, but the weekly coaching gap is real.", next: "Send proof-led reply with implementation angle.", why: "The reply rejects category noise but repeats the coaching pain."},
  {from: "Jordan at Northwind", type: "interested", source: "Outlook", urgency: "High", sentiment: "Open", confidence: 88, text: "If this does not require a migration, I can look next week.", next: "Suggest focused 15-minute fit call.", why: "The buyer named a condition and offered a near-term window."},
  {from: "Taylor at Bluepeak", type: "referral", source: "LinkedIn", urgency: "Medium", sentiment: "Helpful", confidence: 84, text: "Our RevOps lead owns this now.", next: "Ask for referral intro and send two-bullet context.", why: "Ownership moved to another stakeholder, so the next step is an easy handoff."},
  {from: "Priya at Gable", type: "not-now", source: "HubSpot", urgency: "Low", sentiment: "Deferred", confidence: 80, text: "Circle back after planning. We are heads down on the board deck this month.", next: "Schedule a light follow-up tied to planning completion.", why: "Timing is the blocker, not the problem fit."},
  {from: "Sam at Meridian", type: "unsubscribe", source: "Gmail", urgency: "High", sentiment: "Closed", confidence: 96, text: "Please remove me from this sequence.", next: "Mark handled and suppress future outreach.", why: "Explicit opt-out language should stop the workflow."},
];

const sampleWinnerEmails = [
  "Short opener, one specific pain, proof before product, direct 15-minute CTA.",
  "Referenced forecast risk, avoided dashboard language, used manager coaching proof.",
  "Won reply by naming the handoff problem and offering a two-bullet summary.",
];

const outboundTemplates = [
  "Pain-led cold email",
  "Reply follow-up",
  "Executive referral ask",
  "Event follow-up",
  "Competitor displacement",
];

const industryPlaybooks = [
  "SaaS pipeline inspection",
  "Healthcare workflow risk",
  "Financial services compliance",
  "Manufacturing operations",
  "Retail field teams",
];

const dailyPrompts = [
  {
    title: "One thing you understood better today",
    prompt: "Write about one thing that became clearer today. Use your own words and include what changed in how you see it.",
  },
  {
    title: "A decision you made today",
    prompt: "Write about a decision you made today, why you made it, and what the next step is.",
  },
  {
    title: "A problem you are working through",
    prompt: "Write about a problem you are working through. Name what feels messy and what would make the next step smaller.",
  },
  {
    title: "Something harder than expected",
    prompt: "Write about something that felt harder than expected. Try to separate the facts from the worry around it.",
  },
  {
    title: "One idea to remember tomorrow",
    prompt: "Write down one idea you want to remember tomorrow and why it matters.",
  },
  {
    title: "A message that could be clearer and kinder",
    prompt: "Draft a message that could be clearer and kinder. Keep the boundary, remove extra frustration, and make the next step obvious.",
  },
  {
    title: "Something you noticed today",
    prompt: "Write about something you noticed today. Include what happened and what it might teach you for tomorrow.",
  },
];

const consumerPromptLibrary = [
  {name: "Journal", prompt: "Write six sentences about what felt most important today.", goal: "Build a daily reflection habit"},
  {name: "Hard message", prompt: "Draft the message you are avoiding in the kindest clear version you can.", goal: "Make hard conversations easier"},
  {name: "Work email", prompt: "Explain the decision, the reason, and the next step in one short email.", goal: "Write clearer at work"},
  {name: "Essay", prompt: "State your main idea, then add one example that makes it easier to picture.", goal: "Make school writing stronger"},
  {name: "Feedback", prompt: "Describe what worked, what was confusing, and one useful next step.", goal: "Give clearer feedback"},
  {name: "Apology", prompt: "Say what happened, what you understand now, and what you will do differently.", goal: "Sound accountable"},
];

const explorerFolders = ["Daily", "Work", "School", "Personal", "Drafts"];
const explorerGoals = ["Make this clearer", "Make this warmer", "Make this shorter", "Sound more confident", "Sound less harsh"];
const explorerRewriteGoals = productConfig.rewriteGoals || ["Email", "Apology", "Essay", "Feedback", "Conflict", "Cover letter", "Text message"];
const primaryRewriteGoals = explorerRewriteGoals.slice(0, 4);
const secondaryRewriteGoals = explorerRewriteGoals.slice(4);

function loadWorkspace() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
    if (saved.recipient) state.recipient = {...state.recipient, ...saved.recipient};
    if (Array.isArray(saved.savedCampaigns)) state.savedCampaigns = saved.savedCampaigns;
    if (Array.isArray(saved.batchRows)) state.batchRows = saved.batchRows;
    if (Array.isArray(saved.batchErrors)) state.batchErrors = saved.batchErrors;
    if (Array.isArray(saved.inboxThreads)) state.inboxThreads = saved.inboxThreads;
    if (Array.isArray(saved.winnerSamples)) state.winnerSamples = saved.winnerSamples;
    if (Array.isArray(saved.personaLibrary)) state.personaLibrary = saved.personaLibrary;
    if (saved.outcomeStats) state.outcomeStats = {...state.outcomeStats, ...saved.outcomeStats};
    if (saved.crmConnections) state.crmConnections = {...state.crmConnections, ...saved.crmConnections};
    if (saved.sequenceSettings) state.sequenceSettings = {...state.sequenceSettings, ...saved.sequenceSettings};
    if (Array.isArray(saved.explorerHistory)) state.explorerHistory = saved.explorerHistory;
    if (Array.isArray(saved.exportHistory)) state.exportHistory = saved.exportHistory;
    if (Array.isArray(saved.reviewQueue)) state.reviewQueue = saved.reviewQueue;
    if (Array.isArray(saved.teamComments)) state.teamComments = saved.teamComments;
    if (saved.batchMapping) state.batchMapping = {...state.batchMapping, ...saved.batchMapping};
    if (Array.isArray(saved.versionHistory)) state.versionHistory = saved.versionHistory;
    if (saved.feedbackMemory) state.feedbackMemory = {...state.feedbackMemory, ...saved.feedbackMemory};
    if (saved.onboarding) state.onboarding = {...state.onboarding, ...saved.onboarding};
    if (saved.adminSettings) state.adminSettings = {...state.adminSettings, ...saved.adminSettings};
    if (typeof saved.explorerFolder === "string") state.explorerFolder = saved.explorerFolder;
    if (typeof saved.explorerJournalSearch === "string") state.explorerJournalSearch = saved.explorerJournalSearch;
    if (typeof saved.explorerJournalFolder === "string") state.explorerJournalFolder = saved.explorerJournalFolder;
    if (typeof saved.explorerWritingGoal === "string") state.explorerWritingGoal = saved.explorerWritingGoal;
    if (typeof saved.explorerRewriteGoal === "string") state.explorerRewriteGoal = saved.explorerRewriteGoal;
    if (typeof saved.explorerPromptTitle === "string") state.explorerPromptTitle = saved.explorerPromptTitle;
    if (typeof saved.explorerPromptText === "string") state.explorerPromptText = saved.explorerPromptText;
    if (typeof saved.explorerPromptSource === "string") state.explorerPromptSource = saved.explorerPromptSource;
    if (saved.enterpriseContext) state.enterpriseContext = saved.enterpriseContext;
    if (typeof saved.mode === "string") state.mode = saved.mode;
  } catch (error) {
    console.warn("Workspace restore failed", error);
  }
  if (!state.savedCampaigns.length) state.savedCampaigns = [...defaultCampaigns];
  if (!state.inboxThreads.length) state.inboxThreads = [...sampleInboxThreads];
  if (!state.winnerSamples.length) state.winnerSamples = [...sampleWinnerEmails];
  if (!state.personaLibrary.length) state.personaLibrary = [...defaultPersonas];
  normalizePreviewConnections();
}

function persistWorkspace() {
  const payload = workspacePayload();
  localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  queueServerSync(payload);
}

function workspacePayload() {
  return {
    mode: state.mode,
    latestText: "",
    recipient: state.recipient,
    enterpriseContext: state.enterpriseContext,
    savedCampaigns: state.savedCampaigns.slice(0, 12),
    batchRows: state.batchRows.slice(0, 150),
    batchErrors: state.batchErrors.slice(0, 20),
    inboxThreads: state.inboxThreads.slice(0, 25),
    winnerSamples: state.winnerSamples.slice(0, 25),
    personaLibrary: state.personaLibrary.slice(0, 25),
    outcomeStats: state.outcomeStats,
    crmConnections: state.crmConnections,
    sequenceSettings: state.sequenceSettings,
    explorerHistory: state.explorerHistory.slice(0, 20),
    explorerFolder: state.explorerFolder,
    explorerJournalSearch: state.explorerJournalSearch,
    explorerJournalFolder: state.explorerJournalFolder,
    explorerWritingGoal: state.explorerWritingGoal,
    explorerRewriteGoal: state.explorerRewriteGoal,
    explorerPromptTitle: state.explorerPromptTitle,
    explorerPromptText: state.explorerPromptText,
    explorerPromptSource: state.explorerPromptSource,
    batchMapping: state.batchMapping,
    exportHistory: state.exportHistory.slice(0, 30),
    reviewQueue: state.reviewQueue.slice(0, 50),
    teamComments: state.teamComments.slice(0, 25),
    versionHistory: state.versionHistory.slice(0, 80),
    feedbackMemory: state.feedbackMemory,
    onboarding: state.onboarding,
    adminSettings: state.adminSettings,
  };
}

function applyWorkspacePayload(payload = {}) {
  const currentMode = state.mode;
  Object.entries(payload).forEach(([key, value]) => {
    if (key === "account") return;
    if (key in state) state[key] = value;
  });
  state.mode = payload.mode || currentMode || state.mode;
  if (!state.savedCampaigns.length) state.savedCampaigns = [...defaultCampaigns];
  if (!state.inboxThreads.length) state.inboxThreads = [...sampleInboxThreads];
  if (!state.winnerSamples.length) state.winnerSamples = [...sampleWinnerEmails];
  if (!state.personaLibrary.length) state.personaLibrary = [...defaultPersonas];
  normalizePreviewConnections();
}

function normalizePreviewConnections() {
  if (config.app?.integrations_live) return;
  Object.keys(state.crmConnections).forEach((name) => {
    if (state.crmConnections[name] === "connected" || state.crmConnections[name] === "exported") {
      state.crmConnections[name] = name === "Chrome Sidebar" ? "packaging required" : "needs credentials";
    }
  });
}

let workspaceSyncTimer = null;
function queueServerSync(payload = workspacePayload()) {
  if (!state.account.authenticated) return;
  state.account.syncStatus = "Saving...";
  renderAccountCard();
  clearTimeout(workspaceSyncTimer);
  workspaceSyncTimer = setTimeout(() => syncWorkspace(payload), 450);
}

async function syncWorkspace(payload = workspacePayload()) {
  if (!state.account.authenticated) return;
  try {
    const data = await apiClient.saveWorkspace(state.account.workspaceName, payload);
    state.account.workspaceName = data.workspace?.name || state.account.workspaceName;
    state.account.lastSyncedAt = new Date().toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"});
    state.account.syncStatus = `Synced ${state.account.lastSyncedAt}`;
  } catch (error) {
    state.account.syncStatus = "Sync paused";
  }
  renderAccountCard();
}

function trackEvent(eventType, payload = {}) {
  apiClient.event(eventType, {mode: state.mode, ...payload}).catch(() => {});
}

window.addEventListener("error", (event) => {
  apiClient.clientError?.({
    message: event.message,
    source: event.filename,
    line: event.lineno,
    column: event.colno,
  }).catch(() => {});
});

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
    note: "Use when a prospect has already pushed back or named a buying condition.",
    text: "Appreciate the note. We are not evaluating new platforms this quarter unless they can show a direct connection to renewal risk and the weekly coaching moments managers keep missing. The team already has enough dashboards, so the only useful conversation would be around cleaner handoffs, faster account reviews, and fewer surprises before board forecast.",
    context: {stage: "Evaluating", source: "Reply", pain: "renewal risk and missed coaching moments", trigger: "board forecast cleanup"},
  },
  {
    label: "LinkedIn bio",
    tag: "bio",
    source: "LinkedIn",
    note: "Use when you only have public profile language.",
    text: "Revenue leader focused on practical operating systems for high-growth teams. I care about cleaner handoffs, stronger manager coaching, and better signal from frontline conversations. The best tools remove noise, make priorities obvious, and help teams spend more time on the accounts that can actually move.",
    context: {stage: "Problem-aware", source: "LinkedIn bio", pain: "cleaner handoffs and stronger coaching", trigger: "profile research"},
  },
  {
    label: "RevOps email",
    tag: "email",
    source: "Email",
    note: "Use when a buyer has explained what would make a meeting worthwhile.",
    text: "The main issue is not activity volume. We need a cleaner way to see which accounts are actually moving, where managers should intervene, and how to spot renewal risk before it becomes a forecast problem. If your product helps with that without forcing a heavy migration, I am open to seeing a focused walkthrough.",
    context: {stage: "Evaluating", source: "Previous email", pain: "late renewal risk and coaching gaps", trigger: "focused walkthrough request"},
  },
  {
    label: "Website copy",
    tag: "website",
    source: "Website",
    note: "Use when you are researching an account before first touch.",
    text: "Our revenue operations team helps regional leaders build repeatable systems for pipeline inspection, forecast rhythm, and frontline coaching. We prioritize simple workflows, clear accountability, and fewer manual reporting loops so managers can focus on the accounts and conversations that matter.",
    context: {stage: "Unaware", source: "Website copy", pain: "manual reporting loops", trigger: "account research"},
  },
];

const campaignCards = [
  ["Forecast risk pilot", "RevOps", "Executive", "42 accounts", "Drafts ready"],
  ["Re-engage quiet champions", "Expansion", "Friendly", "18 contacts", "Needs proof point"],
  ["Event follow-up sprint", "Field marketing", "Concise", "96 leads", "Sequence live"],
];

const tiers = [
  ["Free Explorer", "Single-sample analysis, style map, and technical readout."],
  ["Enterprise Workspace", "Campaign briefs, variants, exports, and team review screens."],
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

function dailyPrompt() {
  const start = new Date(new Date().getFullYear(), 0, 0);
  const diff = new Date() - start;
  const day = Math.floor(diff / 86400000);
  return dailyPrompts[day % dailyPrompts.length];
}

function dailyPromptTitle() {
  return dailyPrompt().title || dailyPrompt();
}

function dailyPromptInstruction() {
  const prompt = dailyPrompt();
  return prompt.prompt || `Write your own response to this prompt: ${dailyPromptTitle()}.`;
}

function activeExplorerPrompt() {
  if (!state.explorerPromptTitle || !state.explorerPromptText) return null;
  return {
    title: state.explorerPromptTitle,
    text: state.explorerPromptText,
    source: state.explorerPromptSource || "Prompt",
  };
}

function explorerPlaceholder() {
  const prompt = activeExplorerPrompt();
  if (!prompt) return "Paste an email, journal note, comment, essay paragraph, or message draft.";
  return `Write your own response to: ${prompt.title}. Nothing will be filled in for you.`;
}

function explorerPromptGuidance() {
  const prompt = activeExplorerPrompt();
  if (!prompt) return "";
  return `
    <aside class="selected-prompt" aria-label="Selected writing prompt">
      <span class="label">${escapeHtml(prompt.source)}</span>
      <strong>${escapeHtml(prompt.title)}</strong>
      <p>${escapeHtml(prompt.text)}</p>
      <button class="quiet-button" type="button" data-clear-explorer-prompt>Clear prompt</button>
    </aside>
  `;
}

function selectExplorerPrompt({title, text, source = "Prompt"}) {
  state.explorerPromptTitle = title;
  state.explorerPromptText = text;
  state.explorerPromptSource = source;
  if (!state.explorerReadingName) state.explorerReadingName = title;
  state.latestData = null;
  persistWorkspace();
  render();
  requestAnimationFrame(() => {
    document.querySelector("#explorer-text")?.focus();
    uiHelpers.announce?.(els.announcer, `${title} selected. Write your own response in the writing sample box.`);
  });
}

function modeFromPath(pathname = window.location.pathname) {
  const clean = String(pathname || "").replace(/\/+$/, "");
  if (clean.endsWith("/enterprise")) return "enterprise";
  if (clean.endsWith("/explorer")) return "explorer";
  return "";
}

function productPath(mode) {
  return mode === "enterprise" ? "/enterprise" : "/explorer";
}

function updateModeRoute(mode, replace = false) {
  if (!window.history?.pushState) return;
  const nextPath = productPath(mode);
  if (window.location.pathname === nextPath) return;
  const method = replace ? "replaceState" : "pushState";
  const query = replace ? window.location.search : "";
  window.history[method]({mode}, "", `${nextPath}${query}`);
}

function setMode(mode) {
  state.mode = mode;
  state.latestData = null;
  state.latestText = "";
  state.enterpriseDrafts = [];
  state.campaignSaved = false;
  state.enterpriseSetupOpen = false;
  state.activeExplorerTab = "style";
  state.activeEnterpriseTab = "dashboard";
  state.activeEnterpriseTool = "batch";
  els.body.dataset.mode = mode;
  els.modeExplorer.setAttribute("aria-pressed", String(mode === "explorer"));
  els.modeEnterprise.setAttribute("aria-pressed", String(mode === "enterprise"));
  updateModeRoute(mode);

  renderModeChrome();

  persistWorkspace();
  render();
  uiHelpers.announce?.(els.announcer, mode === "enterprise" ? "Enterprise workspace opened." : "Explorer writing coach opened.");
  uiHelpers.focusWithin?.(els.body, mode === "enterprise" ? "#enterprise-text, #output-panel" : "#explorer-text, #output-panel");
}

function renderModeChrome() {
  if (state.mode === "enterprise") {
    els.heroTitle.textContent = state.latestData ? "Enterprise" : "Today’s outreach work";
    els.heroSubtitle.textContent = state.latestData ? "Review queue, focused editor, exports, and outcomes." : "One quiet workspace for importing prospects, reviewing drafts, and tracking what happened.";
    els.modeNote.textContent = "Enterprise keeps integrations visibly disabled until real accounts are connected.";
    els.personaStrip.setAttribute("hidden", "");
    els.personaStrip.innerHTML = "";
    return;
  }

  els.heroTitle.textContent = state.latestData ? "Explorer" : "Write one better paragraph today";
  els.heroSubtitle.textContent = state.latestData ? "One paragraph, one plain read, one better draft." : "A calm daily coach for noticing how your words land and making one useful edit.";
  els.modeNote.textContent = "Explorer is for personal writing. Enterprise is a separate outreach workspace.";
  els.personaStrip.setAttribute("hidden", "");
  els.personaStrip.innerHTML = "";
}

function renderAccountCard() {
  if (!els.accountCard) return;
  const signedIn = state.account.authenticated && state.account.user;
  const label = signedIn ? (state.account.user.name || "Account") : "Account";
  const avatar = signedIn
    ? (state.account.user.name || state.account.user.email || "U").slice(0, 1).toUpperCase()
    : "TT";
  const status = signedIn
    ? `${state.account.workspaceName || "Personal workspace"} / ${state.account.syncStatus || "Synced"}`
    : "Local workspace";
  const errorHtml = state.accountError ? `<p class="error-text">${escapeHtml(state.accountError)}</p>` : "";
  const deleteWarning = state.accountDeletePending
    ? `<div class="account-warning" role="status"><strong>Delete account?</strong><span>Enter your password, then confirm. This removes synced workspace data for this account.</span></div>`
    : "";

  if (signedIn) {
    els.accountCard.innerHTML = `
      <button class="account-trigger" type="button" data-open-account aria-haspopup="dialog" aria-expanded="${String(state.accountModalOpen)}">
        <span class="avatar-dot">${escapeHtml(avatar)}</span>
        <span>${escapeHtml(label)}</span>
      </button>
      <div class="account-overlay ${state.accountModalOpen ? "is-open" : ""}" ${state.accountModalOpen ? "" : "hidden"} data-account-overlay>
        <section class="account-sheet" role="dialog" aria-modal="true" aria-labelledby="account-title">
          <div class="sheet-head">
            <div>
              <p class="label">Account</p>
              <h2 id="account-title">${escapeHtml(label)}</h2>
              <p class="muted">${escapeHtml(status)} / ${state.account.user.email_verified ? "Email verified" : "Email not verified"}</p>
            </div>
            <button class="button-secondary sheet-close" type="button" data-close-account>Close</button>
          </div>
          ${errorHtml}
          ${deleteWarning}
          <label class="field"><span>Password for export/delete</span><input id="account-password" type="password" autocomplete="current-password" placeholder="Enter password before sensitive account actions"></label>
          <div class="account-actions sheet-actions">
            <button class="button-secondary" type="button" data-sync-now>Sync now</button>
            <button class="button-secondary" type="button" data-open-onboarding>Preferences</button>
            <button class="button-secondary" type="button" data-export-account>Export data</button>
            <button class="button-secondary danger-button" type="button" data-delete-account>${state.accountDeletePending ? "Confirm delete account" : "Delete account"}</button>
            <button class="button-secondary" type="button" data-logout>Sign out</button>
          </div>
        </section>
      </div>
    `;
  } else {
    const demoButton = config.devTools ? `<button class="button-secondary" type="button" data-demo-account>Use demo sync</button>` : "";
    els.accountCard.innerHTML = `
      <button class="account-trigger" type="button" data-open-account aria-haspopup="dialog" aria-expanded="${String(state.accountModalOpen)}">
        <span class="avatar-dot">${escapeHtml(avatar)}</span>
        <span>${escapeHtml(label)}</span>
      </button>
      <div class="account-overlay ${state.accountModalOpen ? "is-open" : ""}" ${state.accountModalOpen ? "" : "hidden"} data-account-overlay>
        <section class="account-sheet" role="dialog" aria-modal="true" aria-labelledby="account-title">
          <div class="sheet-head">
            <div>
              <p class="label">Account</p>
              <h2 id="account-title">Save your workspace</h2>
              <p class="muted">Create an account when you want your work to follow you across devices.</p>
            </div>
            <button class="button-secondary sheet-close" type="button" data-close-account>Close</button>
          </div>
          ${errorHtml}
          <div class="account-benefits" aria-label="What account sync saves">
            <article><strong>Explorer</strong><span>Writing journal, streaks, weekly recap, and saved rewrites.</span></article>
            <article><strong>Enterprise</strong><span>Campaigns, draft history, review queues, exports, and team settings.</span></article>
          </div>
          <div class="auth-grid">
            <label class="field"><span>Name</span><input id="auth-name" autocomplete="name" value="${escapeHtml(state.accountDraft.name)}" placeholder="Your name"></label>
            <label class="field"><span>Email</span><input id="auth-email" autocomplete="email" value="${escapeHtml(state.accountDraft.email)}" placeholder="you@example.com"></label>
            <label class="field"><span>Password</span><input id="auth-password" type="password" autocomplete="current-password" placeholder="At least 12 characters"></label>
            <div class="auth-actions">
              <button type="button" data-signup>Create account</button>
              <button class="button-secondary" type="button" data-login>Sign in</button>
              ${demoButton}
              <button class="button-secondary" type="button" data-request-reset>Reset password</button>
            </div>
            <details class="account-code-panel" ${state.accountCodePanelOpen || state.accountResetToken ? "open" : ""}>
              <summary>Have an email code?</summary>
              <label class="field"><span>Verification code</span><input id="verify-token" autocomplete="one-time-code" value="${escapeHtml(state.accountDraft.verifyToken)}" placeholder="Paste verification code"></label>
              <button class="button-secondary" type="button" data-submit-verification>Verify email</button>
              <label class="field"><span>Reset code</span><input id="reset-token" autocomplete="one-time-code" value="${escapeHtml(state.accountResetToken || state.accountDraft.resetToken)}" placeholder="Paste reset code"></label>
              <label class="field"><span>New password</span><input id="reset-new-password" type="password" autocomplete="new-password" placeholder="At least 12 characters"></label>
              <button class="button-secondary" type="button" data-submit-reset>Update password</button>
            </details>
          </div>
        </section>
      </div>
    `;
  }
  wireAccountCard();
}

function isValidEmail(value) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(value || "").trim());
}

function passwordPolicyMessage(password, email = "") {
  const clean = String(password || "").trim();
  if (clean.length < 12) return "Use at least 12 characters for the password.";
  const localPart = String(email || "").split("@", 1)[0].toLowerCase();
  if (localPart && clean.toLowerCase().includes(localPart)) return "Use a password that does not include your email name.";
  return "";
}

function syncAccountDraftFromFields() {
  const name = els.accountCard?.querySelector("#auth-name");
  const email = els.accountCard?.querySelector("#auth-email");
  const verifyToken = els.accountCard?.querySelector("#verify-token");
  const resetToken = els.accountCard?.querySelector("#reset-token");
  if (name) state.accountDraft.name = name.value;
  if (email) state.accountDraft.email = email.value;
  if (verifyToken) state.accountDraft.verifyToken = verifyToken.value;
  if (resetToken) state.accountDraft.resetToken = resetToken.value;
}

function showAccountError(message) {
  syncAccountDraftFromFields();
  state.accountError = message;
  state.accountModalOpen = true;
  els.announcer.textContent = message;
  renderAccountCard();
}

function scrollAccountCodePanelIntoView() {
  requestAnimationFrame(() => {
    const panel = els.accountCard?.querySelector(".account-code-panel");
    if (!panel?.open) return;
    panel.scrollIntoView({block: "nearest", behavior: "smooth"});
  });
}

function wireAccountCard() {
  els.accountCard?.querySelector("[data-open-account]")?.addEventListener("click", () => {
    state.accountModalOpen = true;
    state.accountError = "";
    state.accountDeletePending = false;
    renderAccountCard();
    requestAnimationFrame(() => {
      els.accountCard.querySelector("#auth-email, [data-sync-now], [data-close-account]")?.focus?.();
    });
  });
  els.accountCard?.querySelector("[data-close-account]")?.addEventListener("click", () => {
    state.accountModalOpen = false;
    state.accountError = "";
    state.accountDeletePending = false;
    state.accountCodePanelOpen = false;
    renderAccountCard();
  });
  els.accountCard?.querySelector("[data-account-overlay]")?.addEventListener("click", (event) => {
    if (event.target !== event.currentTarget) return;
    state.accountModalOpen = false;
    state.accountError = "";
    state.accountDeletePending = false;
    state.accountCodePanelOpen = false;
    renderAccountCard();
  });
  els.accountCard?.querySelector("[data-sync-now]")?.addEventListener("click", () => syncWorkspace());
  els.accountCard?.querySelectorAll("#auth-name, #auth-email, #verify-token, #reset-token").forEach((field) => {
    field.addEventListener("input", syncAccountDraftFromFields);
  });
  els.accountCard?.querySelector(".account-code-panel")?.addEventListener("toggle", (event) => {
    state.accountCodePanelOpen = event.currentTarget.open;
    if (state.accountCodePanelOpen) scrollAccountCodePanelIntoView();
  });
  els.accountCard?.querySelector("[data-open-onboarding]")?.addEventListener("click", () => {
    state.onboarding.complete = false;
    state.accountModalOpen = false;
    render();
  });
  els.accountCard?.querySelector("[data-logout]")?.addEventListener("click", async () => {
    try {
      await apiClient.logout();
      state.account = {...state.account, authenticated: false, user: null, syncStatus: "Local only", workspaceName: "Local workspace"};
      state.accountModalOpen = false;
      state.accountDeletePending = false;
      state.accountCodePanelOpen = false;
      renderAccountCard();
    } catch (error) {
      state.accountError = error.message || "Sign out failed.";
      renderAccountCard();
    }
  });
  els.accountCard?.querySelector("[data-export-account]")?.addEventListener("click", async (event) => {
    const password = els.accountCard.querySelector("#account-password")?.value || "";
    if (!password) {
      showToast(event.currentTarget, "Enter your password before exporting account data.");
      return;
    }
    try {
      const data = await apiClient.exportAccount(password);
      downloadText("texttraits-account-export.json", JSON.stringify(data, null, 2));
      showToast(event.currentTarget, "Account export downloaded.");
    } catch (error) {
      showToast(event.currentTarget, error.message || "Account export failed.");
    }
  });
  els.accountCard?.querySelector("[data-delete-account]")?.addEventListener("click", async (event) => {
    if (!state.accountDeletePending) {
      state.accountDeletePending = true;
      state.accountError = "";
      renderAccountCard();
      requestAnimationFrame(() => els.accountCard.querySelector("#account-password")?.focus?.());
      return;
    }
    const password = els.accountCard.querySelector("#account-password")?.value || "";
    if (!password) {
      showToast(event.currentTarget, "Enter your password before deleting the account.");
      return;
    }
    try {
      await apiClient.deleteAccount(password);
      state.account = {...state.account, authenticated: false, user: null, syncStatus: "Local only", workspaceName: "Local workspace"};
      state.accountModalOpen = false;
      state.accountDeletePending = false;
      renderAccountCard();
      showToast(event.currentTarget, "Account deleted.");
      render();
    } catch (error) {
      showToast(event.currentTarget, error.message || "Account deletion failed.");
    }
  });
  els.accountCard?.querySelector("[data-signup]")?.addEventListener("click", () => authRequest("signup"));
  els.accountCard?.querySelector("[data-login]")?.addEventListener("click", () => authRequest("login"));
  els.accountCard?.querySelector("[data-demo-account]")?.addEventListener("click", () => authRequest("demo"));
  els.accountCard?.querySelector("[data-request-reset]")?.addEventListener("click", async (event) => {
    const email = els.accountCard.querySelector("#auth-email")?.value || "";
    if (!isValidEmail(email)) {
      showAccountError("Enter the email for your account first.");
      return;
    }
    try {
      const response = await apiClient.requestPasswordReset(email);
      state.accountCodePanelOpen = true;
      showToast(event.currentTarget, response.dev_reset_url ? "Reset helper created for local development." : "Check your email for a reset code.");
      renderAccountCard();
      scrollAccountCodePanelIntoView();
    } catch (error) {
      showToast(event.currentTarget, error.message || "Enter the email for your account.");
    }
  });
  els.accountCard?.querySelector("[data-submit-verification]")?.addEventListener("click", async (event) => {
    const token = els.accountCard.querySelector("#verify-token")?.value || "";
    if (!token.trim()) {
      state.accountCodePanelOpen = true;
      showAccountError("Enter the verification code from your email.");
      scrollAccountCodePanelIntoView();
      return;
    }
    try {
      const data = await apiClient.verifyEmail(token);
      applyAuthenticatedAccount(data, "Email verified");
      showToast(event.currentTarget, "Email verified.");
    } catch (error) {
      showToast(event.currentTarget, error.message || "Verification code expired.");
    }
  });
  els.accountCard?.querySelector("[data-submit-reset]")?.addEventListener("click", async (event) => {
    const token = els.accountCard.querySelector("#reset-token")?.value || "";
    const password = els.accountCard.querySelector("#reset-new-password")?.value || "";
    if (!token.trim()) {
      state.accountCodePanelOpen = true;
      showAccountError("Enter the reset code from your email.");
      scrollAccountCodePanelIntoView();
      return;
    }
    const policyMessage = passwordPolicyMessage(password);
    if (policyMessage) {
      state.accountCodePanelOpen = true;
      showAccountError(policyMessage);
      scrollAccountCodePanelIntoView();
      return;
    }
    try {
      const data = await apiClient.resetPassword(token, password);
      state.accountResetToken = "";
      applyAuthenticatedAccount(data, "Password reset");
      showToast(event.currentTarget, "Password updated.");
    } catch (error) {
      showToast(event.currentTarget, error.message || "Reset code expired.");
    }
  });
}

function applyAuthenticatedAccount(data, statusText = "Signed in") {
  state.account.authenticated = true;
  state.account.user = data.user;
  state.account.workspaceName = data.workspace?.name || `${data.user.name}'s workspace`;
  state.account.syncStatus = statusText;
  state.accountModalOpen = false;
  state.accountError = "";
  state.accountDeletePending = false;
  state.accountCodePanelOpen = false;
  state.accountDraft = {name: "", email: "", verifyToken: "", resetToken: ""};
  if (data.workspace?.data) applyWorkspacePayload(data.workspace.data);
  persistWorkspace();
  renderAccountCard();
  renderModeChrome();
  render();
}

async function authRequest(action) {
  const emailField = els.accountCard.querySelector("#auth-email");
  const passwordField = els.accountCard.querySelector("#auth-password");
  const nameField = els.accountCard.querySelector("#auth-name");
  const payload = action === "demo"
    ? {email: "demo@texttraits.local", password: "texttraits-demo", name: "Demo Workspace"}
    : {email: emailField?.value || "", password: passwordField?.value || "", name: nameField?.value || ""};
  if (action !== "demo") {
    if (!isValidEmail(payload.email)) {
      showAccountError("Enter a valid email address.");
      return;
    }
    if (!payload.password) {
      showAccountError("Enter your password.");
      return;
    }
    if (action === "signup") {
      const policyMessage = passwordPolicyMessage(payload.password, payload.email);
      if (policyMessage) {
        showAccountError(policyMessage);
        return;
      }
    }
  }
  try {
    let data;
    if (action === "login") data = await apiClient.login(payload);
    else {
      try {
        data = await apiClient.signup(payload);
      } catch (error) {
        if (action === "demo" && error.status === 409) data = await apiClient.login(payload);
        else throw error;
      }
    }
    if (!data.authenticated || !data.user) {
      if (action === "demo") {
        data = await apiClient.login(payload);
        applyAuthenticatedAccount(data);
        return;
      }
      els.announcer.textContent = data.message || "Check your account details.";
      state.accountError = data.message || "Check your account details.";
      state.accountModalOpen = true;
      renderAccountCard();
      return;
    }
    applyAuthenticatedAccount(data);
  } catch (error) {
    els.announcer.textContent = error.message || "Sign-in failed.";
    state.account.syncStatus = error.message || "Sign-in failed";
    state.accountError = error.message || "Sign-in failed.";
    state.accountModalOpen = true;
    renderAccountCard();
  }
}

async function initAccount() {
  renderAccountCard();
  try {
    const sessionData = await apiClient.session();
    if (!sessionData.authenticated) return;
    const workspaceData = await apiClient.workspace();
    state.account.authenticated = true;
    state.account.user = sessionData.user;
    state.account.workspaceName = workspaceData.workspace?.name || `${sessionData.user.name}'s workspace`;
    state.account.syncStatus = `Synced ${new Date().toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"})}`;
    applyWorkspacePayload(workspaceData.workspace?.data || {});
    renderAccountCard();
    renderModeChrome();
    render();
  } catch (error) {
    state.account.syncStatus = "Local only";
    renderAccountCard();
  }
}

async function handleAccountLinkTokens() {
  const params = new URLSearchParams(window.location.search);
  const hashParams = new URLSearchParams(window.location.hash.replace(/^#\??/, ""));
  const verifyToken = params.get("verify_token") || hashParams.get("verify_token");
  const resetToken = params.get("reset_token") || hashParams.get("reset_token");
  let changed = false;

  if (verifyToken) {
    try {
      const data = await apiClient.verifyEmail(verifyToken);
      state.account.authenticated = true;
      state.account.user = data.user;
      state.account.workspaceName = data.workspace?.name || `${data.user.name}'s workspace`;
      state.account.syncStatus = "Email verified";
      state.accountDraft = {name: "", email: "", verifyToken: "", resetToken: ""};
      state.accountCodePanelOpen = false;
      if (data.workspace?.data) applyWorkspacePayload(data.workspace.data);
      renderAccountCard();
      renderModeChrome();
      showToast(els.accountCard, "Email verified.");
      render();
    } catch (error) {
      showToast(els.accountCard, error.message || "Verification link expired.");
    }
    params.delete("verify_token");
    hashParams.delete("verify_token");
    changed = true;
  }

  if (resetToken) {
    state.accountResetToken = resetToken;
    state.accountCodePanelOpen = true;
    state.accountModalOpen = true;
    state.accountError = "Enter a new password to finish resetting your account.";
    renderAccountCard();
    requestAnimationFrame(() => els.accountCard.querySelector("#reset-new-password")?.focus?.());
    params.delete("reset_token");
    hashParams.delete("reset_token");
    changed = true;
  }

  if (changed && window.history?.replaceState) {
    const query = params.toString();
    const hash = hashParams.toString();
    window.history.replaceState({mode: state.mode}, "", `${window.location.pathname}${query ? `?${query}` : ""}${hash ? `#${hash}` : ""}`);
  }
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
          <span>${escapeHtml(sample.source || sample.tag)} sample / ${words(sample.text).length} words</span>
          ${sample.note ? `<small>${escapeHtml(sample.note)}</small>` : ""}
        </button>
      `).join("")}
    </div>
  `;
}

function renderExplorerInput() {
  if (state.latestData) {
    const stats = localStats(state.latestText);
    els.inputPanel.innerHTML = `
      <div class="panel-head compact-head">
        <div>
          <h2>Explorer sample</h2>
          <p class="helper">${stats.words} words / ${escapeHtml(stats.reading_level)} density</p>
        </div>
        <button id="clear-explorer" class="button-secondary" type="button">New sample</button>
      </div>
      <details class="advanced-card">
        <summary>Show analyzed text</summary>
        <p class="muted">${escapeHtml(state.latestText.slice(0, 340))}${state.latestText.length > 340 ? "..." : ""}</p>
      </details>
    `;
    return;
  }
  els.inputPanel.innerHTML = `
    <div class="panel-head">
      <div>
        <h2>Today’s writing</h2>
        <p class="helper">Paste one paragraph. Get one plain summary and one useful rewrite.</p>
      </div>
      <span class="status-pill">Ready</span>
    </div>

    <div class="field">
      <label for="explorer-text">Writing sample</label>
      ${explorerPromptGuidance()}
      <textarea id="explorer-text" placeholder="${escapeHtml(explorerPlaceholder())}">${escapeHtml(state.latestText)}</textarea>
    </div>

    <div class="quality-row">
      <span id="explorer-count">0 words</span>
      <span id="explorer-quality">Add text to analyze.</span>
    </div>
    <div class="meter"><progress id="explorer-meter" max="100" value="0">0%</progress></div>

    <details class="advanced-card quiet-more-drawer">
      <summary>More</summary>
      <p class="muted">Optional extras live here so the main path stays simple: write, read, rewrite, save.</p>
      <div class="field">
        <label for="reading-name">Name this sample</label>
        <input id="reading-name" value="${escapeHtml(state.explorerReadingName)}" placeholder="Daily journal, project email, class note">
      </div>
      <div class="field-grid">
        ${selectField("explorerFolder", "Private folder", explorerFolders, state.explorerFolder)}
        ${selectField("explorerWritingGoal", "Writing goal", explorerGoals, state.explorerWritingGoal)}
      </div>
      <div class="field">
        <label for="compare-text">Compare two samples</label>
        <textarea id="compare-text" class="compact-textarea" placeholder="Optional: paste a second sample for a before/after or comparison view.">${escapeHtml(state.compareText)}</textarea>
      </div>

      <div class="field-grid">
        <label class="field"><span>Writing style only</span><select id="style-only"><option>No</option><option>Yes</option></select></label>
        <label class="field"><span>Technical details</span><select id="technical-visible"><option value="hide">Hide</option><option value="show">Show</option></select></label>
        <label class="field"><span>Sensitive labels</span><select id="sensitive-hidden"><option value="show">Show expanded section</option><option value="hide">Hide permanently</option></select></label>
        <label class="field"><span>Output focus</span><select id="explorer-focus"><option>Simple summary</option><option>What stands out</option><option>Rewrite guidance</option></select></label>
      </div>
      <details class="history-card">
        <summary>Writing log</summary>
        ${explorerHistoryList()}
      </details>
      <details class="history-card">
        <summary>Prompt library</summary>
        <div class="prompt-library">
          ${consumerPromptLibrary.map((item, index) => `
            <button class="prompt-card" type="button" data-prompt-index="${index}">
              <strong>${escapeHtml(item.name)}</strong>
              <span>${escapeHtml(item.goal)}</span>
              <small>${escapeHtml(item.prompt)}</small>
            </button>
          `).join("")}
        </div>
      </details>
      <details class="history-card sample-drawer">
        <summary>Try an example</summary>
        ${sampleButtons(explorerSamples, "explorer-text")}
      </details>
    </details>

    <div class="action-row sticky">
      <button id="analyze-explorer" type="button">Analyze text</button>
      <button id="clear-explorer" class="button-secondary" type="button">Clear</button>
      <button id="copy-explorer-input" class="button-secondary" type="button">Copy input</button>
    </div>
  `;
}

function renderEnterpriseInput() {
  const ctx = state.enterpriseContext || {};
  if (state.latestData && state.enterpriseInputsCollapsed) {
    els.inputPanel.innerHTML = `
      <div class="panel-head compact-head input-mini-head">
        <div>
          <h2>${escapeHtml(ctx.project || "Outbound campaign")}</h2>
          <p class="helper">${escapeHtml(ctx.role || "VP Revenue")} / ${escapeHtml(ctx.company || "TextTraits")} / ${escapeHtml(ctx.goal || "Book call")}</p>
        </div>
        <button id="edit-enterprise-inputs" class="button-secondary" type="button">Edit inputs</button>
      </div>
      <div class="compact-summary compact-summary-tight">
        ${summaryItem("Prospect words", `${localStats(state.latestText).words}`)}
        ${summaryItem("Pain", ctx.pain || "forecast risk")}
      </div>
    `;
    return;
  }

  els.inputPanel.innerHTML = `
    <div class="panel-head enterprise-setup-head">
      <div>
        <h2>Quick draft setup</h2>
        <p class="helper">Paste the buyer's own words first. Use the rest only when it helps the draft sound more specific.</p>
      </div>
      <span class="preview-badge">Draft setup</span>
    </div>

    <div class="field">
      <label for="enterprise-text">Prospect context</label>
      <textarea id="enterprise-text" class="enterprise-compact-textarea" placeholder="Paste a reply, LinkedIn bio, transcript, website paragraph, or previous email.">${escapeHtml(state.latestText)}</textarea>
    </div>

    <div class="starter-sample-panel">
      <div>
        <strong>Need a fast demo?</strong>
        <span>Load one buyer example, then generate drafts.</span>
      </div>
      ${sampleButtons(enterpriseSamples.slice(0, 2), "enterprise-text")}
    </div>

    <div class="quality-row">
      <span id="enterprise-count">0 words</span>
      <span id="enterprise-quality">Add prospect language to generate a brief.</span>
    </div>
    <div class="meter"><progress id="enterprise-meter" max="100" value="0">0%</progress></div>

    <details class="advanced-card primary-context compact-context">
      <summary>Campaign basics</summary>
      <div class="enterprise-field-grid field-grid-spaced compact-enterprise-fields">
        ${field("project", "Campaign name", ctx.project || "Forecast risk pilot")}
        ${field("offer", "What do you sell?", ctx.offer || "a review workspace for outbound drafts, replies, and campaign outcomes")}
      </div>
    </details>

    <details class="advanced-card">
      <summary>Edit setup</summary>
      <div class="enterprise-field-grid">
        ${field("role", "Who are you writing to?", ctx.role || "VP Revenue")}
        ${selectField("goal", "Campaign goal", goals, ctx.goal)}
        ${field("folder", "Folder", ctx.folder || "RevOps")}
        ${field("company", "Your company", ctx.company || "TextTraits")}
        ${field("pain", "Pain hypothesis", ctx.pain || "renewal risk and missed coaching moments")}
        ${field("proof", "Proof point", ctx.proof || "reduced manual reporting by 32%")}
        ${selectField("preset", "Output preset", presets, ctx.preset)}
        ${selectField("industry", "Industry", industries, ctx.industry)}
        ${selectField("seniority", "Seniority", seniorities, ctx.seniority)}
        ${field("segment", "Market segment", ctx.segment || "Mid-market SaaS")}
        ${selectField("stage", "Buying stage", buyingStages, ctx.stage)}
        ${selectField("source", "Signal source", sources, ctx.source)}
        ${selectField("region", "Region", regions, ctx.region)}
        ${field("trigger", "Trigger event", ctx.trigger || "pipeline inspection redesign")}
        ${field("icp", "ICP fit", ctx.icp || "Revenue teams with 30+ sellers")}
        ${field("caseStudy", "Case study", ctx.caseStudy || "Series B sales org")}
        ${field("competitor", "Competitor displacement", ctx.competitor || "spreadsheet-heavy review process")}
      </div>
    </details>

    <details class="advanced-card">
      <summary>Brand voice and recipient preview</summary>
      <div class="section-title">
        <strong>Company voice</strong>
        ${selectField("brandVoice", "Saved profile", brandVoiceProfiles.map((profile) => profile.name), ctx.brandVoice)}
      </div>
      <div class="range-row"><span>Direct</span><input id="tone-direct" type="range" min="0" max="100" value="${escapeHtml(ctx.direct || 70)}"><strong>${escapeHtml(ctx.direct || 70)}</strong></div>
      <div class="range-row"><span>Warm</span><input id="tone-warm" type="range" min="0" max="100" value="${escapeHtml(ctx.warm || 55)}"><strong>${escapeHtml(ctx.warm || 55)}</strong></div>
      <div class="range-row"><span>Formal</span><input id="tone-formal" type="range" min="0" max="100" value="${escapeHtml(ctx.formal || 62)}"><strong>${escapeHtml(ctx.formal || 62)}</strong></div>
      <div class="range-row"><span>Technical</span><input id="tone-technical" type="range" min="0" max="100" value="${escapeHtml(ctx.technical || 48)}"><strong>${escapeHtml(ctx.technical || 48)}</strong></div>
      <div class="range-row"><span>Concise</span><input id="tone-concise" type="range" min="0" max="100" value="${escapeHtml(ctx.concise || 82)}"><strong>${escapeHtml(ctx.concise || 82)}</strong></div>
      <div class="enterprise-field-grid field-grid-spaced">
        ${field("firstName", "First name", state.recipient.firstName)}
        ${field("recipientCompany", "Recipient company", state.recipient.company)}
        ${field("recipientRole", "Recipient role", state.recipient.role)}
        ${selectField("template", "Template", outboundTemplates, ctx.template)}
      </div>
    </details>

    <details class="advanced-card quiet-samples">
      <summary>Load example prospect</summary>
      <p class="muted">Use a reply when you have one; use a bio, transcript, or website copy when you are starting cold.</p>
      ${sampleButtons(enterpriseSamples, "enterprise-text")}
    </details>

    <div class="action-row enterprise-actions">
      <button id="generate-enterprise" type="button">Generate drafts</button>
      <button id="clear-enterprise" class="button-secondary" type="button">Clear prospect</button>
    </div>
  `;
}

function summaryItem(label, value) {
  return `<article><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></article>`;
}

function field(id, label, value) {
  return `<label class="field"><span>${escapeHtml(label)}</span><input id="field-${id}" value="${escapeHtml(value)}"></label>`;
}

function selectField(id, label, values, selected = "") {
  return `
    <label class="field">
      <span>${escapeHtml(label)}</span>
      <select id="field-${id}">${values.map((value) => `<option ${value === selected ? "selected" : ""}>${escapeHtml(value)}</option>`).join("")}</select>
    </label>
  `;
}

function renderExplorerEmpty() {
  const profile = explorerProfileSummary();
  const hasJournal = state.explorerHistory.length >= 2;
  const latest = state.explorerHistory[0];
  const streak = explorerStreak();
  els.outputPanel.innerHTML = `
    <div class="empty-layout fade-in calm-empty explorer-daily-home">
      <section class="daily-home-card">
        <div>
          <span class="label">Today’s coach</span>
          <h2>${escapeHtml(dailyPromptTitle())}</h2>
          <p>${escapeHtml(dailyPromptInstruction())}</p>
        </div>
        <button type="button" data-use-daily-prompt>Use prompt</button>
      </section>

      <div class="daily-home-stats">
        <article>
          <span>Streak</span>
          <strong>${streak ? `${streak} day${streak === 1 ? "" : "s"}` : "Start today"}</strong>
          <p>${escapeHtml(streakMilestone())}</p>
        </article>
        <article>
          <span>Last entry</span>
          <strong>${latest ? escapeHtml(latest.name || "Saved reading") : "None yet"}</strong>
          <p>${latest ? escapeHtml(latest.summary || latest.sourceExcerpt || "Ready for the next reading.") : "Paste one paragraph to begin."}</p>
        </article>
        <article>
          <span>One goal</span>
          <strong>${escapeHtml(state.explorerWritingGoal || "Make this clearer")}</strong>
          <p>${escapeHtml(profile.ready ? todayVsLastWeek() || profile.traits.join(" / ") : profile.copy)}</p>
        </article>
        <article>
          <span>Weekly preview</span>
          <strong>${escapeHtml(state.explorerHistory.length >= 3 ? weeklyRecap() : "Build your recap")}</strong>
          <p>${escapeHtml(state.explorerHistory.length >= 3 ? "Your weekly recap updates as you save readings." : "Save three readings to unlock trends.")}</p>
        </article>
      </div>

      ${hasJournal ? `
      <div class="daily-product-grid daily-home-focus">
        <article class="guide-card profile-preview-card">
          <span class="label">${escapeHtml(profile.title)}</span>
          <strong>${escapeHtml(profile.ready ? "Profile ready" : "Keep saving readings")}</strong>
          <p>${escapeHtml(profile.copy)}</p>
        </article>
        <article class="guide-card">
          <span class="label">Weekly recap</span>
          <strong>${escapeHtml(weeklyRecap())}</strong>
          <p>Save a few short readings to see how your writing changes over time.</p>
        </article>
      </div>
      ` : `
      <article class="guide-card one-action-card">
        <span class="label">First step</span>
        <strong>Write one paragraph.</strong>
        <p>After the first read, Explorer shows how it comes across, one practical edit, and a rewrite you can use.</p>
      </article>
      `}

      ${renderOnboardingCard("explorer")}

      <details class="advanced-card">
        <summary>Privacy controls</summary>
        <p class="muted">Unsigned work stays in this browser. Signed-in work syncs to your TextTraits workspace so you can recover history, drafts, and reports on another device.</p>
        <div class="chip-list">
          <span class="chip">Account sync optional</span>
          <span class="chip">Workspace export ready</span>
          <span class="chip">Privacy and terms routes included</span>
        </div>
      </details>
    </div>
  `;
}

function renderEnterpriseEmpty() {
  els.outputPanel.innerHTML = `
    <div class="empty-layout fade-in enterprise-empty calm-enterprise-home">
      <div class="empty-hero enterprise-home-hero">
        <span class="preview-badge">Workspace</span>
        <h2>Today’s work</h2>
        <p class="muted">One operating loop: import prospects, generate drafts, review the queue, export, then track outcomes.</p>
      </div>

      <div class="flow-path">
        ${["Import prospects", "Generate drafts", "Review", "Export/send", "Track outcomes"].map((step, index) => `
          <article>
            <span>${index + 1}</span>
            <strong>${escapeHtml(step)}</strong>
          </article>
        `).join("")}
      </div>

      <div class="today-grid quiet-dashboard">
        <article class="strategy-card featured">
          <strong>Start here: create campaign</strong>
          <p>Paste one buyer signal, generate the first drafts, then review from the queue. Everything else can wait.</p>
          <div class="result-actions">
            <button type="button" data-focus-enterprise-input>Create campaign</button>
            <details class="inline-sample-menu">
              <summary>Load sample workspace</summary>
              <button class="button-secondary" type="button" data-generate-sample-drafts>Generate sample drafts</button>
            </details>
          </div>
        </article>
        <article class="strategy-card">
          <strong>${state.sampleWorkspaceLoaded ? "Sample workspace" : "Preview workspace"}</strong>
          ${state.sampleWorkspaceLoaded ? `
            <div class="queue-list">
              <span>${state.batchRows.length ? `${state.batchRows.length} prospects to draft` : "Sample: 12 prospects to draft"}</span>
              <span>${state.inboxThreads.filter((thread) => !thread.handled).length ? `${state.inboxThreads.filter((thread) => !thread.handled).length} replies to answer` : "Sample: 5 replies to answer"}</span>
              <span>${state.savedCampaigns.filter((campaign) => /review|draft/i.test(campaign.status)).length ? `${state.savedCampaigns.filter((campaign) => /review|draft/i.test(campaign.status)).length} campaigns needing review` : "Sample: 3 campaigns needing review"}</span>
            </div>
          ` : `
            <p class="muted">Preview-only tools stay clearly marked until real credentials and accounts are connected.</p>
            <button class="button-secondary" type="button" data-load-sample-workspace>Load full sample data</button>
          `}
        </article>
      </div>

      ${renderOnboardingCard("enterprise")}

      <details class="advanced-card preview-note">
        <summary>Integration setup and admin</summary>
        <div class="campaign-grid">
        ${state.savedCampaigns.map((campaign) => `
          <article class="project-card">
            <strong>${escapeHtml(campaign.name)}</strong>
            <span>${escapeHtml(campaign.folder)} / ${escapeHtml(campaign.updated)}</span>
            <span class="strength">${escapeHtml(campaign.status)}</span>
          </article>
        `).join("")}
        </div>
        <div class="tier-grid">
        ${tiers.map(([name, copy]) => `<article class="guide-card"><strong>${escapeHtml(name)}</strong><p>${escapeHtml(copy)}</p></article>`).join("")}
        </div>
        <div class="feature-list">
          ${[
            "Saved campaigns",
            "Project sidebar tree",
            "Admin settings",
            "API keys",
            "Usage analytics",
            "Approval workflow",
            "Reusable outbound templates",
            "Inbox and reply analysis mode",
            "Sequence calendar with follow-up timing",
            "Team comments and approvals",
            "Learn from winning replies",
            "Manager coaching dashboard",
          ].map((item) => `<span>${escapeHtml(item)} / setup</span>`).join("")}
        </div>
      </details>
    </div>
  `;
  els.outputPanel.querySelector("[data-focus-enterprise-input]")?.addEventListener("click", () => {
    state.enterpriseSetupOpen = true;
    render();
    requestAnimationFrame(() => document.querySelector("#enterprise-text")?.focus());
  });
  els.outputPanel.querySelector("[data-load-sample-workspace]")?.addEventListener("click", (event) => {
    state.sampleWorkspaceLoaded = true;
    state.lastActionNote = "Sample workspace loaded for preview.";
    persistWorkspace();
    showToast(event.currentTarget, "Sample workspace loaded.");
    renderEnterpriseEmpty();
  });
  els.outputPanel.querySelector("[data-generate-sample-drafts]")?.addEventListener("click", () => {
    const sample = enterpriseSamples[0];
    state.latestText = sample.text;
    state.latestData = null;
    state.enterpriseDrafts = [];
    state.enterpriseContext = {...(state.enterpriseContext || {}), ...(sample.context || {})};
    state.enterpriseSetupOpen = false;
    state.enterpriseLandingTab = "dashboard";
    persistWorkspace();
    runAnalysis(sample.text);
  });
}

function renderOnboardingCard(mode) {
  if (state.onboarding.complete) return "";
  if (mode === "enterprise") {
    return `
      <details class="onboarding-card onboarding-drawer">
        <summary><span><strong>Personalize workspace</strong><small>Optional first-run setup</small></span></summary>
        <strong>What should this workspace help your team improve?</strong>
        <div class="field-grid">
          ${selectField("onboardingEnterpriseGoal", "Primary workflow", ["Review outbound drafts", "Answer replies faster", "Import and approve batches", "Track campaign outcomes"], state.onboarding.enterpriseGoal)}
          ${selectField("onboardingTeamSize", "Team size", ["1-5", "6-25", "26-100", "100+"], state.onboarding.teamSize)}
        </div>
        <div class="result-actions">
          <button type="button" data-save-onboarding="enterprise">Save workspace setup</button>
          <button class="button-secondary" type="button" data-skip-onboarding>Skip for now</button>
        </div>
      </details>
    `;
  }
  return `
    <details class="onboarding-card onboarding-drawer">
      <summary><span><strong>Personalize your coach</strong><small>Optional first-run setup</small></span></summary>
      <strong>What are you here to improve?</strong>
      <div class="field-grid">
        ${selectField("onboardingExplorerGoal", "Writing goal", ["Clearer everyday writing", "Warmer messages", "Better essays", "Professional confidence", "Hard conversations"], state.onboarding.explorerGoal)}
        ${selectField("onboardingPlan", "Coach plan", ["7-day plan", "30-day plan", "Weekly check-in"], state.onboarding.plan || "7-day plan")}
      </div>
      <div class="result-actions">
        <button type="button" data-save-onboarding="explorer">Save writing setup</button>
        <button class="button-secondary" type="button" data-skip-onboarding>Skip for now</button>
      </div>
    </details>
  `;
}

async function evaluateText(text) {
  return apiClient.evaluate({text, model: "local"});
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

function mbtiMeaning(code) {
  const map = {
    E: "expressive energy",
    I: "measured energy",
    S: "concrete detail",
    N: "conceptual framing",
    T: "logic-led decisions",
    F: "people-aware decisions",
    J: "structured pacing",
    P: "open-ended pacing",
  };
  return code.split("").map((letter) => map[letter] || "mixed signal").join(", ");
}

function readingEffortLabel(stats) {
  const wordsPerSentence = Number(stats?.words || 0) / Math.max(Number(stats?.sentences || 1), 1);
  if (wordsPerSentence < 12) return "Easy read";
  if (wordsPerSentence < 20) return "Comfortable read";
  return "Needs a slower read";
}

function readingEffortCopy(stats) {
  const label = readingEffortLabel(stats);
  if (label === "Easy read") return "Shorter sentence groups make this quick to follow.";
  if (label === "Comfortable read") return "The writing has useful detail without feeling too heavy.";
  return "The writing asks the reader to hold several ideas at once, so breaking it up may help.";
}

function dimensionLabel(prediction, dimension) {
  const raw = String(prediction?.label || prediction?.raw_label || "").toLowerCase();
  const labels = {
    energy: {extraverted: "Sounds energetic", introverted: "Sounds calm"},
    information: {sensing: "You explain with examples", intuitive: "You lead with the big idea"},
    decisions: {thinking: "You make the point directly", feeling: "You consider how it lands"},
    structure: {judging: "It feels organized", perceiving: "It leaves room to explore"},
  };
  return labels[dimension]?.[raw] || "Mixed";
}

function dimensionCopy(prediction, dimension) {
  const raw = String(prediction?.label || prediction?.raw_label || "").toLowerCase();
  const copy = {
    energy: {
      extraverted: "This sounds animated and outward-facing, like it is trying to move the reader along.",
      introverted: "This sounds calm and careful, like it is choosing words without extra drama.",
    },
    information: {
      sensing: "This uses practical details and real situations instead of staying abstract.",
      intuitive: "This focuses on the bigger idea more than step-by-step details.",
    },
    decisions: {
      thinking: "This gets to the point and explains the reason behind the thought.",
      feeling: "This pays attention to people, expectations, and how the message might land.",
    },
    structure: {
      judging: "This feels organized and moves toward a clear takeaway.",
      perceiving: "This feels more exploratory and leaves room for possibilities.",
    },
  };
  return copy[dimension]?.[raw] || "This part of the style is mixed, so treat it as a light clue.";
}

function signalStrength(prediction) {
  const value = score(prediction);
  if (value > 0.66) return "clear";
  if (value > 0.33) return "moderate";
  return "subtle";
}

function dimensionRows(dims) {
  return [
    {key: "energy", title: "How it sounds", prediction: dims.energy},
    {key: "information", title: "What it pays attention to", prediction: dims.information},
    {key: "decisions", title: "How it makes its point", prediction: dims.decisions},
    {key: "structure", title: "How organized it feels", prediction: dims.structure},
  ];
}

function plainStyleSummary(stats, dims, strongest) {
  const strongestKey = strongest?.[2] || "information";
  const strongestPrediction = strongest?.[1];
  const strongestLabel = dimensionLabel(strongestPrediction, strongestKey);
  return `${readingEffortCopy(stats)} The clearest thing about it: ${styleSentence(strongestLabel)} Keep that strength, then make the main point easy to spot.`;
}

function styleSentence(label) {
  const clean = String(label || "Mixed").toLowerCase();
  if (clean.startsWith("you ")) return `${clean}.`;
  if (clean.startsWith("it ")) return `${clean}.`;
  if (clean.startsWith("sounds ")) return `it ${clean}.`;
  return `${clean}.`;
}

function nextWritingAction(stats, strongest) {
  const strongestKey = strongest?.[2] || "";
  const label = dimensionLabel(strongest?.[1], strongestKey);
  if (readingEffortLabel(stats) === "Needs a slower read") return "Try splitting the longest sentence into two shorter ones.";
  if (strongestKey === "energy" && label === "Sounds calm") return "Add one sentence that says what you want the reader to do next.";
  if (strongestKey === "energy" && label === "Sounds energetic") return "Keep the energy, but cut one extra phrase so the point lands faster.";
  if (strongestKey === "information" && label === "You explain with examples") return "Keep the examples and add one short sentence that explains why they matter.";
  if (strongestKey === "information" && label === "You lead with the big idea") return "Add one concrete example so the idea is easier to picture.";
  if (strongestKey === "decisions") return "Make the main takeaway visible in the first or last sentence.";
  return "Read it once out loud and mark the sentence you would keep if you could only keep one.";
}

function explorerLogSummary() {
  const runs = state.explorerHistory.length;
  const today = state.explorerHistory.filter((item) => item.day === todayKey()).length;
  if (!runs) return "No saved readings yet. Analyze a sample to start your writing log.";
  return `${runs} saved ${runs === 1 ? "reading" : "readings"}${today ? `, ${today} today` : ""}.`;
}

function explorerStreak() {
  const days = [...new Set(state.explorerHistory.map((item) => item.day))].sort().reverse();
  if (!days.length) return 0;
  let streak = 0;
  const current = new Date();
  for (let offset = 0; offset < 30; offset += 1) {
    const key = new Date(current.getFullYear(), current.getMonth(), current.getDate() - offset).toISOString().slice(0, 10);
    if (!days.includes(key)) break;
    streak += 1;
  }
  return streak;
}

function usualWritingSummary() {
  if (state.explorerHistory.length < 3) return "Save 3 readings to unlock your usual writing profile.";
  const recent = state.explorerHistory.slice(0, 5);
  const counts = recent.reduce((acc, item) => {
    acc[item.feel] = (acc[item.feel] || 0) + 1;
    return acc;
  }, {});
  const [feel] = Object.entries(counts).sort((a, b) => b[1] - a[1])[0] || ["steady"];
  return `You usually write in a ${String(feel).toLowerCase()} style, with ${recent.length} recent samples saved.`;
}

function clarityScore(stats, strongest) {
  const base = 72;
  const lengthBoost = Math.min(Number(stats.words || 0), 90) / 90 * 10;
  const sentencePenalty = readingEffortLabel(stats) === "Needs a slower read" ? -8 : readingEffortLabel(stats) === "Easy read" ? 5 : 2;
  const strengthBoost = score(strongest?.prediction) * 10;
  return Math.max(42, Math.min(98, Math.round(base + lengthBoost + sentencePenalty + strengthBoost)));
}

function clarityBand(scoreValue) {
  if (scoreValue >= 86) return "Easy to follow";
  if (scoreValue >= 72) return "Mostly clear";
  if (scoreValue >= 58) return "Needs a little cleanup";
  return "Hard to follow";
}

function streakCopy() {
  const streak = explorerStreak();
  if (!streak) return "Save today’s reading, then come back tomorrow for the next prompt.";
  if (streak === 1) return "You wrote today. Come back tomorrow to keep the rhythm.";
  return `${streak} days in a row. Come back tomorrow for the next small improvement.`;
}

function streakMilestone() {
  const streak = explorerStreak();
  if (!streak) return "Today can be day one.";
  if (streak < 3) return `${3 - streak} more day${3 - streak === 1 ? "" : "s"} to a 3-day rhythm.`;
  if (streak < 7) return `${7 - streak} more day${7 - streak === 1 ? "" : "s"} to a weekly streak.`;
  return "Weekly rhythm unlocked. Keep it light and repeatable.";
}

function todayVsLastWeek() {
  if (state.explorerHistory.length < 6) return "";
  const recent = state.explorerHistory.slice(0, 3);
  const previous = state.explorerHistory.slice(3, 6);
  const avg = (items) => Math.round(items.reduce((sum, item) => sum + Number(item.clarity || 70), 0) / Math.max(items.length, 1));
  const diff = avg(recent) - avg(previous);
  if (Math.abs(diff) < 2) return "Your clarity is holding steady compared with your previous saved samples.";
  return diff > 0 ? `Your recent writing is ${diff} points easier to follow than the previous set.` : `Your recent writing needs ${Math.abs(diff)} points more cleanup than the previous set.`;
}

function filteredExplorerHistory() {
  const query = state.explorerJournalSearch.trim().toLowerCase();
  return state.explorerHistory.filter((entry) => {
    const folder = entry.folder || "Daily";
    const matchesFolder = state.explorerJournalFolder === "All" || folder === state.explorerJournalFolder;
    const haystack = `${entry.name || ""} ${folder} ${entry.goal || ""} ${entry.clue || ""} ${entry.summary || ""} ${entry.sourceExcerpt || ""}`.toLowerCase();
    return matchesFolder && (!query || haystack.includes(query));
  });
}

function weeklyRecapCards(profile) {
  const entries = state.explorerHistory;
  const streak = explorerStreak();
  const avgClarity = entries.length ? Math.round(entries.reduce((sum, item) => sum + Number(item.clarity || 70), 0) / entries.length) : 0;
  const avgWords = entries.length ? Math.round(entries.reduce((sum, item) => sum + Number(item.words || 0), 0) / entries.length) : 0;
  const folderSummary = folderCounts().filter(([, count]) => count).map(([folder, count]) => `${folder}: ${count}`).join(" / ") || "No folders yet";
  return `
    <div class="weekly-recap-page">
      <article>
        <span class="label">Streak</span>
        <strong>${streak ? `${streak} day${streak === 1 ? "" : "s"}` : "Start today"}</strong>
        <p>${escapeHtml(streakCopy())}</p>
      </article>
      <article>
        <span class="label">Average clarity</span>
        <strong>${avgClarity ? clarityBand(avgClarity) : "Not enough yet"}</strong>
        <p>${avgClarity ? `${avgClarity}/100 across ${entries.length} saved readings.` : "Save readings to build a weekly trend."}</p>
      </article>
      <article>
        <span class="label">Usual length</span>
        <strong>${avgWords ? `${avgWords} words` : "No average yet"}</strong>
        <p>${escapeHtml(folderSummary)}</p>
      </article>
      <article>
        <span class="label">${escapeHtml(profile.title)}</span>
        <strong>${escapeHtml(profile.ready ? profile.traits[0] : "Keep saving")}</strong>
        <p>${escapeHtml(profile.copy)}</p>
      </article>
    </div>
  `;
}

function explorerJournalPanel() {
  const entries = filteredExplorerHistory().slice(0, 8);
  const total = state.explorerHistory.length;
  if (!total) return `<p class="muted">No saved readings yet. Save a reading to start your journal.</p>`;
  return `
    <div class="journal-tools">
      <label class="field"><span>Search journal</span><input id="journal-search" value="${escapeHtml(state.explorerJournalSearch)}" placeholder="Search saved readings"></label>
      ${selectField("journalFolder", "Folder", ["All", ...explorerFolders], state.explorerJournalFolder)}
      <div class="journal-filter-actions">
        <button class="button-secondary" type="button" data-apply-journal-filter>Apply</button>
        <button class="button-secondary quiet-button" type="button" data-clear-journal-filter>Clear</button>
      </div>
      <span class="saved-state">${entries.length} of ${total} shown</span>
    </div>
    ${entries.length ? "" : `<p class="muted">No readings match this filter.</p>`}
    <div class="journal-list">
      ${entries.map((entry, index) => `
        <article>
          <div>
            <strong>${escapeHtml(entry.name || `Reading ${index + 1}`)}</strong>
            <span>${escapeHtml(entry.folder || "Daily")} / ${escapeHtml(entry.day || "")} / ${escapeHtml(clarityBand(entry.clarity || 70))}</span>
          </div>
          <p>${escapeHtml(entry.summary || entry.sourceExcerpt || entry.feel || "Saved writing sample")}</p>
          <small>${escapeHtml(entry.goal || "Make this clearer")} / ${escapeHtml(entry.clue || "Style note")}</small>
        </article>
      `).join("")}
    </div>
  `;
}

function weeklyRecapPanel(profile) {
  return `
    <div class="weekly-recap-panel">
      <article>
        <span class="label">This week</span>
        <strong>${escapeHtml(weeklyRecap())}</strong>
        <p>${escapeHtml(todayVsLastWeek() || "Save a few more readings to compare this week with previous samples.")}</p>
      </article>
      <article>
        <span class="label">${escapeHtml(profile.title)}</span>
        <strong>${escapeHtml(profile.ready ? profile.traits[0] : "Profile in progress")}</strong>
        <p>${escapeHtml(profile.copy)}</p>
      </article>
    </div>
  `;
}

function explorerProfileSummary() {
  if (state.explorerHistory.length < 5) {
    return {
      ready: false,
      title: "Personal style profile",
      copy: `${Math.max(0, 5 - state.explorerHistory.length)} more saved readings unlock a more useful profile.`,
      traits: ["Clarity trend", "Common tone", "Usual length"],
    };
  }
  const recent = state.explorerHistory.slice(0, 8);
  const avgWords = Math.round(recent.reduce((sum, item) => sum + Number(item.words || 0), 0) / recent.length);
  const avgScore = Math.round(recent.reduce((sum, item) => sum + Number(item.clarity || 70), 0) / recent.length);
  const common = Object.entries(recent.reduce((acc, item) => {
    acc[item.primaryClue || item.feel] = (acc[item.primaryClue || item.feel] || 0) + 1;
    return acc;
  }, {})).sort((a, b) => b[1] - a[1])[0]?.[0] || "clear and steady";
  return {
    ready: true,
    title: "You usually write...",
    copy: `Your recent samples average ${avgWords} words with a ${avgScore}/100 clarity score. The most common pattern is ${common.toLowerCase()}.`,
    traits: [`${avgScore}/100 clarity`, `${avgWords} words`, common],
  };
}

function weeklyRecap() {
  if (!state.explorerHistory.length) return "Save readings this week to get a recap.";
  const now = new Date();
  const weekAgo = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 7);
  const recent = state.explorerHistory.filter((item) => new Date(item.timestamp || item.day) >= weekAgo);
  if (!recent.length) return "No saved readings in the last 7 days yet.";
  const avg = Math.round(recent.reduce((sum, item) => sum + Number(item.clarity || 70), 0) / recent.length);
  const best = [...recent].sort((a, b) => Number(b.clarity || 0) - Number(a.clarity || 0))[0];
  return `${recent.length} readings this week. Average clarity: ${avg}/100. Clearest sample: ${best?.name || "untitled reading"}.`;
}

function folderCounts() {
  return explorerFolders.map((folder) => [folder, state.explorerHistory.filter((item) => (item.folder || "Daily") === folder).length]);
}

function explorerHistoryList() {
  if (!state.explorerHistory.length) return `<p class="muted">No saved readings yet.</p>`;
  return `
    <div class="history-list">
      ${state.explorerHistory.slice(0, 8).map((item, index) => `
        <article>
          <strong>${escapeHtml(item.name || `Reading ${state.explorerHistory.length - index}`)}</strong>
          <span>${escapeHtml(item.date)} / ${escapeHtml(item.folder || "Daily")} / ${escapeHtml(item.words)} words / ${escapeHtml(item.clarity || 70)} clarity</span>
          <small>${escapeHtml(item.clue)}</small>
        </article>
      `).join("")}
    </div>
  `;
}

function explorerComparison(stats) {
  const previous = state.explorerHistory[1];
  if (!previous) return "Save another reading to compare how today's writing differs from your last sample.";
  const delta = stats.words - Number(previous.words || 0);
  const direction = delta === 0 ? "the same length as" : delta > 0 ? `${delta} words longer than` : `${Math.abs(delta)} words shorter than`;
  return `Today is ${direction} your previous saved sample. Last time felt ${String(previous.feel).toLowerCase()}.`;
}

function explorerSnapshot(data, text) {
  const stats = data.predictions.text_stats || localStats(text);
  const dims = data.predictions.mbti_dimensions || {};
  const strongest = dimensionRows(dims).sort((a, b) => score(b.prediction) - score(a.prediction))[0];
  return {
    day: todayKey(),
    timestamp: new Date().toISOString(),
    date: new Date().toLocaleString([], {month: "short", day: "numeric", hour: "2-digit", minute: "2-digit"}),
    name: state.explorerReadingName || "",
    folder: state.explorerFolder || "Daily",
    goal: state.explorerWritingGoal || "Make this clearer",
    words: localStats(text).words,
    sourceExcerpt: text.trim().replace(/\s+/g, " ").slice(0, 240),
    feel: readingEffortLabel(stats),
    clarity: clarityScore(stats, strongest),
    primaryClue: dimensionLabel(strongest?.prediction, strongest?.key),
    clue: `${strongest?.title || "Style"}: ${dimensionLabel(strongest?.prediction, strongest?.key)}`,
    summary: plainStyleSummary(stats, dims, [strongest?.title, strongest?.prediction, strongest?.key]),
  };
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
  if (!terms.length) return `<p class="muted">No standout words returned for this part.</p>`;
  return `<div class="chip-list">${terms.map((item) => `<span class="chip">${escapeHtml(item.term)}</span>`).join("")}</div>`;
}

function cueGroups(dims) {
  const groups = dimensionRows(dims).map((row) => [row.title, row.prediction]);
  return `
    <div class="cue-groups">
      ${groups.map(([label, prediction]) => `
        <article>
          <strong>${escapeHtml(label)}</strong>
          ${cueChips(prediction)}
        </article>
      `).join("")}
    </div>
  `;
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
  syncBodyState();
  const p = data.predictions;
  const stats = p.text_stats || localStats(state.latestText);
  const dims = p.mbti_dimensions || {};
  const rows = dimensionRows(dims);
  const strongestRow = rows.sort((a, b) => score(b.prediction) - score(a.prediction))[0];
  const strongest = [strongestRow?.title, strongestRow?.prediction, strongestRow?.key];
  const strongestLabel = dimensionLabel(strongest?.[1], strongest?.[2]);
  const summary = plainStyleSummary(stats, dims, strongest);
  const nextAction = nextWritingAction(stats, strongest);
  const profile = explorerProfileSummary();
  const currentClarity = clarityScore(stats, strongestRow);
  const rewritePreview = makeExplorerRewrite(state.latestText, state.explorerRewriteMode);
  const latestEntry = state.explorerHistory[0];
  const streak = explorerStreak();
  if (!["overview", "style", "rewrite", "technical"].includes(state.activeExplorerTab)) {
    state.activeExplorerTab = "style";
  }
  if (state.activeExplorerTab === "overview" || state.activeExplorerTab === "rewrite") {
    state.activeExplorerTab = "style";
  }

  els.outputPanel.innerHTML = `
    <div class="result-layout explorer-result fade-in">
      <div class="result-header">
        <div>
          <p class="label">Explorer coach</p>
          <h2>How this comes across</h2>
          <p class="muted">${stats.words} words analyzed. Start with the plain read, then choose one small rewrite.</p>
        </div>
        <div class="toolbar">
          <button class="button-secondary" data-edit-explorer-input>Edit input</button>
          <button class="button-secondary" data-new-sample>Analyze another piece</button>
          <button class="button-secondary" type="button" data-open-journal aria-controls="explorer-journal" aria-expanded="${String(state.explorerJournalOpen)}">Open journal</button>
        </div>
      </div>

      <div class="habit-strip" aria-label="Writing journal status">
        <article>
          <span>Journal</span>
          <strong>${latestEntry ? "Saved locally" : "Ready to save"}</strong>
        </article>
        <article>
          <span>Streak</span>
          <strong>${streak ? `${streak} day${streak === 1 ? "" : "s"}` : "Start today"}</strong>
        </article>
        <article>
          <span>Folder</span>
          <strong>${escapeHtml(latestEntry?.folder || state.explorerFolder || "Daily")}</strong>
        </article>
        <article>
          <span>Next</span>
          <strong>${state.explorerHistory.length >= 3 ? "Weekly recap" : "Come back tomorrow"}</strong>
        </article>
      </div>

      <div class="coach-flow">
        <article class="strategy-card coach-card primary-read">
          <span class="label">How does this come across?</span>
          <strong>${escapeHtml(strongestLabel)}</strong>
          <p>${escapeHtml(summary)}</p>
          <div class="friendly-score">
            <strong>${escapeHtml(clarityBand(currentClarity))}</strong>
            <span>${stats.words} words / ${escapeHtml(streakCopy())}</span>
          </div>
          <details class="feedback-menu">
            <summary>Feedback</summary>
            ${feedbackButtons("Explorer reading")}
          </details>
        </article>
        <article class="strategy-card coach-card next-edit-card">
          <span class="label">What should I change?</span>
          <strong>${escapeHtml(nextAction)}</strong>
          <p>Pick one goal. The rewrite keeps your meaning and changes only the delivery.</p>
          <div class="quick-rewrite-actions primary-rewrite-actions">
            <button type="button" data-explorer-rewrite="clearer" aria-pressed="${String(state.explorerRewriteMode === "clearer")}">Make clearer</button>
            <button class="button-secondary" type="button" data-explorer-rewrite="warmer" aria-pressed="${String(state.explorerRewriteMode === "warmer")}">Make warmer</button>
            <button class="button-secondary" type="button" data-explorer-rewrite="shorter" aria-pressed="${String(state.explorerRewriteMode === "shorter")}">Make shorter</button>
          </div>
          <div class="rewrite-goals">
            ${primaryRewriteGoals.map((goal) => `<button class="button-secondary" type="button" data-rewrite-goal="${escapeHtml(goal)}" aria-pressed="${String(goal === state.explorerRewriteGoal)}">${escapeHtml(goal)}</button>`).join("")}
          </div>
          ${secondaryRewriteGoals.length ? `
            <details class="more-rewrite-goals">
              <summary>More goals</summary>
              <div class="rewrite-goals">
                ${secondaryRewriteGoals.map((goal) => `<button class="button-secondary" type="button" data-rewrite-goal="${escapeHtml(goal)}" aria-pressed="${String(goal === state.explorerRewriteGoal)}">${escapeHtml(goal)}</button>`).join("")}
              </div>
            </details>
          ` : ""}
        </article>
        <article class="strategy-card coach-card rewrite-card">
          <span class="label">Try this rewrite</span>
          <strong data-rewrite-title>${escapeHtml(state.explorerRewriteGoal)} version</strong>
          <p data-rewrite-preview>${escapeHtml(rewritePreview)}</p>
          <div class="result-actions">
            <button type="button" data-copy-rewrite>Copy rewrite</button>
            <button class="button-secondary" type="button" data-save-reading>Update journal</button>
          </div>
        </article>
      </div>

      <div class="mobile-result-actions" aria-label="Explorer quick actions">
        <button type="button" data-copy-rewrite>Copy rewrite</button>
        <button class="button-secondary" type="button" data-save-reading>Save</button>
        <button class="button-secondary" data-edit-explorer-input>Edit</button>
      </div>

      <details id="explorer-journal" class="secondary-result-details journal-drawer" ${state.explorerJournalOpen ? "open" : ""}>
        <summary>Writing journal and weekly recap</summary>
        <div class="save-reading-row">
          <label class="field"><span>Name this reading</span><input id="result-reading-name" value="${escapeHtml(state.explorerReadingName || state.explorerHistory[0]?.name || "")}" placeholder="Daily journal, work email, class note"></label>
          ${selectField("resultExplorerFolder", "Folder", explorerFolders, state.explorerFolder)}
          <button class="button-secondary" type="button" data-save-reading>Update this reading</button>
          ${state.explorerSavedMessage ? `<span class="saved-state">${escapeHtml(state.explorerSavedMessage)}</span>` : ""}
        </div>
        ${weeklyRecapPanel(profile)}
        <details class="weekly-recap-drawer">
          <summary>Open weekly writing recap</summary>
          ${weeklyRecapCards(profile)}
        </details>
        ${explorerJournalPanel()}
        <div class="result-actions">
          <button class="button-secondary" data-copy-summary>Copy summary</button>
          <button class="button-secondary" type="button" data-copy-explorer-report>Copy clean report</button>
        </div>
      </details>

      <details class="secondary-result-details quick-checks" ${state.explorerQuickChecksOpen ? "open" : ""}>
        <summary>Show quick checks</summary>
        <div class="metric-grid">
          <article class="metric-card"><span class="label">Length</span><div class="value">${stats.words >= 40 ? "Enough text" : "Short sample"}</div><p>${stats.words} words analyzed.</p></article>
          <article class="metric-card"><span class="label">How easy it is to read</span><div class="value">${escapeHtml(readingEffortLabel(stats))}</div><p>${escapeHtml(readingEffortCopy(stats))}</p></article>
          <article class="metric-card"><span class="label">How it sounds</span><div class="value">${escapeHtml(strongestLabel)}</div><p>${escapeHtml(dimensionCopy(strongest?.[1], strongest?.[2]))}</p></article>
        </div>
      </details>

      <details class="secondary-result-details style-details" ${state.explorerStyleDetailsOpen ? "open" : ""}>
        <summary>See what the app noticed</summary>
        <nav class="tabs" role="tablist" aria-label="Explorer result sections">
          ${tabButton("style", "What stands out", state.activeExplorerTab)}
          ${tabButton("technical", "Technical details", state.activeExplorerTab)}
        </nav>

        <div id="panel-${state.activeExplorerTab}" class="tab-panel" role="tabpanel" tabindex="-1" aria-labelledby="tab-${state.activeExplorerTab}">
          ${renderExplorerTab(data)}
        </div>
      </details>
    </div>
  `;

  els.outputPanel.querySelectorAll("[data-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      state.activeExplorerTab = button.dataset.tab;
      state.explorerStyleDetailsOpen = true;
      renderExplorerResult(data);
      els.outputPanel.querySelector(".tab-panel")?.focus?.();
    });
  });
  const quickChecks = els.outputPanel.querySelector(".quick-checks");
  quickChecks?.addEventListener("toggle", (event) => {
    state.explorerQuickChecksOpen = event.currentTarget.open;
  });
  const styleDetails = els.outputPanel.querySelector(".style-details");
  styleDetails?.addEventListener("toggle", (event) => {
    state.explorerStyleDetailsOpen = event.currentTarget.open;
  });
  bindCopy("[data-copy-summary]", `Writing style summary: ${summary}`, "Explorer summary copied.");
  bindCopy("[data-copy-explorer-report]", explorerReportText(summary, nextAction, profile), "Clean writing report copied.");
  els.outputPanel.querySelectorAll("[data-copy-rewrite]").forEach((button) => {
    button.addEventListener("click", async (event) => {
      await copyTextFromButton(event.currentTarget, makeExplorerRewrite(state.latestText, state.explorerRewriteMode), "Rewrite copied.");
    });
  });
  const nameField = els.outputPanel.querySelector("#result-reading-name");
  const folderField = els.outputPanel.querySelector("#field-resultExplorerFolder");
  const journalSearch = els.outputPanel.querySelector("#journal-search");
  const journalFolder = els.outputPanel.querySelector("#field-journalFolder");
  nameField?.addEventListener("input", () => {
    state.explorerReadingName = nameField.value;
  });
  journalSearch?.addEventListener("change", () => {
    state.explorerJournalSearch = journalSearch.value;
    state.explorerJournalOpen = true;
    persistWorkspace();
    renderExplorerResult(data);
  });
  els.outputPanel.querySelector("[data-apply-journal-filter]")?.addEventListener("click", () => {
    state.explorerJournalSearch = journalSearch?.value || "";
    state.explorerJournalFolder = journalFolder?.value || state.explorerJournalFolder;
    state.explorerJournalOpen = true;
    persistWorkspace();
    renderExplorerResult(data);
  });
  els.outputPanel.querySelector("[data-clear-journal-filter]")?.addEventListener("click", () => {
    state.explorerJournalSearch = "";
    state.explorerJournalFolder = "All";
    state.explorerJournalOpen = true;
    persistWorkspace();
    renderExplorerResult(data);
  });
  journalFolder?.addEventListener("change", () => {
    state.explorerJournalFolder = journalFolder.value;
    state.explorerJournalOpen = true;
    persistWorkspace();
    renderExplorerResult(data);
  });
  folderField?.addEventListener("change", () => {
    state.explorerFolder = folderField.value;
    if (state.explorerHistory[0]) state.explorerHistory[0].folder = folderField.value;
    persistWorkspace();
  });
  els.outputPanel.querySelectorAll("[data-save-reading]").forEach((button) => {
    button.addEventListener("click", () => {
      const name = nameField?.value.trim() || state.explorerReadingName || `Reading ${state.explorerHistory.length || 1}`;
      state.explorerReadingName = name;
      if (folderField) state.explorerFolder = folderField.value;
      if (state.explorerHistory[0]) {
        state.explorerHistory[0].name = name;
        state.explorerHistory[0].folder = state.explorerFolder;
        state.explorerHistory[0].goal = state.explorerWritingGoal;
      }
      state.explorerSavedMessage = `Saved as ${name}.`;
      trackEvent("explorer_save_reading", {folder: state.explorerFolder});
      persistWorkspace();
      renderExplorerResult(data);
    });
  });
  els.outputPanel.querySelectorAll("[data-explorer-rewrite]").forEach((button) => {
    button.addEventListener("click", () => {
      const before = state.latestText;
      const after = makeExplorerRewrite(state.latestText, button.dataset.explorerRewrite);
      recordVersion("Explorer rewrite", button.textContent.trim(), before, after, `${button.textContent.trim()} generated`);
      state.activeExplorerTab = "style";
      state.explorerRewriteMode = button.dataset.explorerRewrite;
      persistWorkspace();
      const title = els.outputPanel.querySelector("[data-rewrite-title]");
      const preview = els.outputPanel.querySelector("[data-rewrite-preview]");
      if (title) title.textContent = `${state.explorerRewriteGoal} version`;
      if (preview) preview.textContent = after;
      els.outputPanel.querySelectorAll("[data-explorer-rewrite]").forEach((item) => {
        item.setAttribute("aria-pressed", String(item.dataset.explorerRewrite === state.explorerRewriteMode));
      });
      showToast(button, `${button.textContent.trim()} version ready.`);
    });
  });
  els.outputPanel.querySelector("[data-open-journal]")?.addEventListener("click", () => {
    const drawer = els.outputPanel.querySelector(".journal-drawer");
    if (!drawer) return;
    state.explorerJournalOpen = true;
    drawer.open = true;
    persistWorkspace();
    drawer.scrollIntoView({behavior: "smooth", block: "start"});
    drawer.querySelector("summary")?.focus?.();
  });
  els.outputPanel.querySelector(".journal-drawer")?.addEventListener("toggle", (event) => {
    state.explorerJournalOpen = event.currentTarget.open;
    persistWorkspace();
  });
  els.outputPanel.querySelectorAll("[data-rewrite-goal]").forEach((button) => {
    button.addEventListener("click", () => {
      state.explorerRewriteGoal = button.dataset.rewriteGoal;
      state.activeExplorerTab = "style";
      trackEvent("explorer_rewrite_goal", {goal: state.explorerRewriteGoal});
      persistWorkspace();
      renderExplorerResult(data);
    });
  });
  els.outputPanel.querySelectorAll("[data-feedback]").forEach((button) => {
    button.addEventListener("click", () => {
      recordFeedback(button.dataset.feedback, button.dataset.feedbackScope || "Explorer");
      showToast(button, "Feedback saved. Future suggestions will adapt.");
    });
  });
  els.outputPanel.querySelectorAll("[data-restore-version]").forEach((button) => {
    button.addEventListener("click", () => {
      restoreVersion(button.dataset.restoreVersion, "Explorer rewrite");
      showToast(button, "Version restored into this workspace.");
      renderExplorerResult(data);
    });
  });
  els.outputPanel.querySelector("[data-new-sample]").addEventListener("click", () => {
    state.latestData = null;
    state.latestText = "";
    state.explorerReadingName = "";
    state.explorerSavedMessage = "";
    state.explorerPromptTitle = "";
    state.explorerPromptText = "";
    state.explorerPromptSource = "";
    state.explorerQuickChecksOpen = false;
    state.explorerStyleDetailsOpen = false;
    render();
  });
  els.outputPanel.querySelector("[data-edit-explorer-input]")?.addEventListener("click", () => {
    state.latestData = null;
    render();
    document.querySelector("#explorer-text")?.focus();
  });
}

function tabButton(tab, label, active) {
  return `<button type="button" role="tab" id="tab-${tab}" data-tab="${tab}" aria-selected="${String(tab === active)}" aria-controls="panel-${tab}">${label}</button>`;
}

function enterpriseTabNote(tab) {
  const notes = {
    dashboard: "Dashboard open. Next: review the queue, then approve or export.",
    drafts: "Draft editor open. Pick one variant, polish it, then approve.",
    tools: "Operations open. Work through batch, sequence, replies, libraries, or insights from one place.",
    analytics: "Insights open. Review outcomes, exports, integrations, and coaching notes.",
  };
  return notes[tab] || "Workspace ready.";
}

function enterpriseToolNote(tool) {
  const notes = {
    batch: "Batch tool open. Paste CSV rows or load the sample before generating.",
    sequence: "Sequence builder open. Tune timing, channels, and stop rules.",
    inbox: "Reply queue open. Load sample replies or connect mail later.",
    libraries: "Libraries open. Review voice, personas, templates, and approved proof.",
    insights: "Insights open. Review outcomes, export history, integrations, and coaching notes.",
  };
  return notes[tool] || "Workspace tool open.";
}

function renderExplorerTab(data) {
  const p = data.predictions;
  const dims = p.mbti_dimensions || {};
  const stats = p.text_stats || localStats(state.latestText);
  const rows = dimensionRows(dims);
  if (state.activeExplorerTab === "style") {
    return `
      <div class="signal-list">
        ${rows.map((row) => signalCard(row)).join("")}
      </div>
      <article class="strategy-card cue-section">
        <strong>Words the app noticed</strong>
        <p class="muted">These words helped shape the reading. They live here instead of the first summary so the main result stays easy to read.</p>
        ${cueGroups(dims)}
      </article>
    `;
  }
  if (state.activeExplorerTab === "patterns") {
    return `
      <div class="detail-grid">
        <article class="strategy-card"><strong>MBTI-style pattern</strong><div class="metric-card"><div class="value">${escapeHtml(mbtiCode(dims))}</div><p>${escapeHtml(mbtiMeaning(mbtiCode(dims)))}.</p></div></article>
        <article class="strategy-card"><strong>Age and data labels</strong><p>Expanded below so Explorer can focus on style first.</p><details><summary>Show expanded data-label output</summary><p>Age range: ${escapeHtml(ageRangeLabel(p.age_estimate || p.age_bucket))}</p>${bars(p.gender)}</details></article>
      </div>
    `;
  }
  if (state.activeExplorerTab === "technical") {
    return `
      <div class="detail-grid technical-grid">
        <article class="strategy-card details-soft"><strong>Pattern label</strong><div class="metric-card flat-metric"><div class="value">${escapeHtml(mbtiCode(dims))}</div><p>${escapeHtml(mbtiMeaning(mbtiCode(dims)))}.</p></div></article>
        <article class="strategy-card details-soft"><strong>Sample profile</strong><p>${stats.words} words, ${stats.characters} characters, ${percent(stats.punctuation_density)} punctuation density.</p></article>
        <article class="strategy-card details-soft"><strong>Age and data labels</strong><p>Expanded below so Explorer can focus on style first.</p><details><summary>Show expanded data-label output</summary><p>Age range: ${escapeHtml(ageRangeLabel(p.age_estimate || p.age_bucket))}</p>${bars(p.gender)}</details></article>
        <article class="strategy-card details-soft"><strong>Technical bars</strong><details><summary>Show detailed bars</summary>${rows.map((row) => `<div class="technical-bars"><strong>${escapeHtml(row.title)}</strong>${bars(row.prediction)}</div>`).join("")}</details></article>
      </div>
    `;
  }
  if (state.activeExplorerTab === "rewrite") {
    return `
      <div class="quick-rewrite-actions primary-rewrite-actions">
        ${["clearer", "warmer", "shorter"].map((mode) => `<button class="button-secondary" type="button" data-explorer-rewrite="${mode}" aria-pressed="${String(state.explorerRewriteMode === mode)}">Make ${escapeHtml(mode)}</button>`).join("")}
      </div>
      <div class="detail-grid">
        <article class="strategy-card"><strong>Before</strong><p>${escapeHtml(state.latestText.slice(0, 360))}</p></article>
        <article class="strategy-card"><strong>After</strong><p>${escapeHtml(makeExplorerRewrite(state.latestText, state.explorerRewriteMode))}</p></article>
      </div>
      <article class="strategy-card"><strong>Today vs previous</strong><p>${escapeHtml(explorerComparison(stats))}</p></article>
      <article class="strategy-card"><strong>Version history</strong>${versionHistoryHtml("Explorer rewrite")}</article>
      ${state.compareText ? `<article class="strategy-card"><strong>Comparison note</strong><p>The second sample is ${localStats(state.compareText).words} words. Use this area to compare how easy each version is to follow.</p></article>` : `<article class="strategy-card"><strong>Compare two samples</strong><p>Add optional comparison text in the left panel to unlock a before/after comparison note.</p></article>`}
    `;
  }
  return `
    <details class="secondary-result-details">
      <summary>What else stands out</summary>
      <div class="explorer-overview-grid">
        <article class="strategy-card">
          <strong>What stands out</strong>
          <div class="signal-pills">
            ${rows.map((row) => `<span>${escapeHtml(row.title)}: ${escapeHtml(dimensionLabel(row.prediction, row.key))}</span>`).join("")}
          </div>
        </article>
        <article class="strategy-card">
          <strong>Today vs previous</strong>
          <p>${escapeHtml(explorerComparison(stats))}</p>
        </article>
      </div>
    </details>
  `;
}

function explorerReportText(summary, nextAction, profile) {
  return [
    "TextTraits writing report",
    "",
    `First read: ${summary}`,
    `Next tiny edit: ${nextAction}`,
    `Writing goal: ${state.explorerWritingGoal}`,
    `Writing log: ${explorerLogSummary()}`,
    `Profile: ${profile.copy}`,
    `Weekly recap: ${weeklyRecap()}`,
  ].join("\n");
}

function feedbackButtons(scope) {
  return `
    <div class="feedback-row" aria-label="${escapeHtml(scope)} feedback">
      ${[
        ["better", "Better"],
        ["tooFormal", "Too formal"],
        ["tooVague", "Too vague"],
        ["tooLong", "Too long"],
        ["moreLikeMe", "More like me"],
      ].map(([key, label]) => `<button class="button-secondary" type="button" data-feedback="${key}" data-feedback-scope="${escapeHtml(scope)}">${escapeHtml(label)}</button>`).join("")}
    </div>
  `;
}

function recordFeedback(key, scope) {
  state.feedbackMemory[key] = Number(state.feedbackMemory[key] || 0) + 1;
  state.versionHistory = [{
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    scope,
    title: `${titleCase(key)} feedback`,
    before: "",
    after: "",
    change: `User marked ${scope} as ${titleCase(key)}.`,
    date: new Date().toLocaleString([], {month: "short", day: "numeric", hour: "2-digit", minute: "2-digit"}),
  }, ...state.versionHistory].slice(0, 80);
  persistWorkspace();
}

function recordVersion(scope, title, before, after, change) {
  state.versionHistory = [{
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    scope,
    title,
    before,
    after,
    change,
    date: new Date().toLocaleString([], {month: "short", day: "numeric", hour: "2-digit", minute: "2-digit"}),
  }, ...state.versionHistory].slice(0, 80);
  persistWorkspace();
}

function versionHistoryHtml(scope = "") {
  const items = state.versionHistory.filter((item) => !scope || item.scope === scope).slice(0, 8);
  if (!items.length) return `<p class="muted">No saved versions yet. Rewrites, draft transforms, and feedback will appear here.</p>`;
  return `
    <div class="version-list">
      ${items.map((item) => `
        <article>
          <strong>${escapeHtml(item.title)}</strong>
          <span>${escapeHtml(item.date)} / ${escapeHtml(item.change)}</span>
          ${item.after ? `<details><summary>Restoreable version</summary><p><strong>Before:</strong> ${escapeHtml(String(item.before).slice(0, 260))}</p><p><strong>After:</strong> ${escapeHtml(String(item.after).slice(0, 260))}</p><button class="button-secondary" type="button" data-restore-version="${escapeHtml(item.id)}">Restore this version</button></details>` : ""}
        </article>
      `).join("")}
    </div>
  `;
}

function restoreVersion(id, scope) {
  const item = state.versionHistory.find((entry) => entry.id === id);
  if (!item?.after) return;
  if (scope === "Enterprise draft") {
    const draft = selectedDraft();
    if (draft) {
      draft.body = item.after;
      draft.history.push(`Restored ${item.title}`);
      state.lastActionNote = "Draft version restored.";
    }
  } else {
    state.latestText = item.after;
    state.lastActionNote = "Explorer rewrite restored.";
  }
  persistWorkspace();
}

function trait(name, value, label) {
  return `<div class="trait"><meter class="trait-meter" min="0" max="1" value="${Math.max(value, 0.08)}"></meter><strong>${escapeHtml(name)}</strong><span class="muted">${escapeHtml(label)}</span></div>`;
}

function signalCard(row) {
  const value = Math.round(score(row.prediction) * 100);
  const width = Math.max(value, 8);
  return `
    <article class="signal-card">
      <div>
        <span class="label">${escapeHtml(row.title)}</span>
        <strong>${escapeHtml(dimensionLabel(row.prediction, row.key))}</strong>
        <p>${escapeHtml(dimensionCopy(row.prediction, row.key))}</p>
      </div>
      <div class="signal-meter" aria-label="${escapeHtml(row.title)} clue strength">
        <progress max="100" value="${width}">${width}%</progress>
      </div>
      <span class="signal-strength">${escapeHtml(signalStrength(row.prediction))} clue</span>
    </article>
  `;
}

function makeExplorerRewrite(text, mode = "clearer") {
  const clean = text.trim().replace(/\s+/g, " ");
  if (!clean) return "";
  const sentences = clean.split(/(?<=[.!?])\s+/).filter(Boolean);
  const first = sentences[0] || clean;
  const goal = state.explorerRewriteGoal || "Email";
  const source = inferExplorerSource(clean, goal);
  const goalNoun = `${/^[aeiou]/i.test(source) ? "an" : "a"} ${source.toLowerCase()}`;
  const mainPoint = sentences.slice(0, 2).join(" ").replace(/\s+/g, " ").trim() || first;
  const warmerClose = "I want this to be easy to respond to, so the next step is clear.";
  const clearerClose = "The main point is simple: name what changed, why it matters, and what should happen next.";
  const shorterClose = "The shorter version keeps the point and trims the setup.";
  if (state.feedbackMemory.tooLong > state.feedbackMemory.better && mode !== "warmer") {
    return `${first} ${shorterClose}`;
  }
  if (state.feedbackMemory.moreLikeMe > 1 && mode !== "shorter") {
    return `${mainPoint} ${clearerClose}`;
  }
  if (mode === "shorter") return `${first} ${goalRewriteClose(goal, "shorter") || shorterClose}`;
  if (mode === "warmer") return `${mainPoint} ${goalRewriteClose(goal, "warmer") || warmerClose}`;
  return `${mainPoint} ${goalRewriteClose(goal, "clearer") || `For ${goalNoun}, it is easier to follow when the main idea appears early and the last sentence says what should happen.`}`;
}

function inferExplorerSource(text, goal) {
  const clean = `${goal} ${text}`.toLowerCase();
  if (clean.includes("apolog") || clean.includes("sorry")) return "apology";
  if (clean.includes("essay") || clean.includes("paragraph") || clean.includes("thesis")) return "essay";
  if (clean.includes("feedback") || clean.includes("what worked")) return "feedback note";
  if (clean.includes("cover letter") || clean.includes("application")) return "cover letter";
  if (clean.includes("text message") || clean.includes("texting")) return "text message";
  if (clean.includes("email") || clean.includes("thanks") || clean.includes("proposal")) return "email";
  if (clean.includes("conflict") || clean.includes("hard conversation") || clean.includes("frustrat")) return "hard message";
  return goal || "writing sample";
}

function goalRewriteClose(goal, mode) {
  const clean = String(goal || "").toLowerCase();
  const map = {
    email: {
      clearer: "I would put the ask in the first or last sentence so the reader knows what to do.",
      warmer: "I would add one line of context or appreciation before the ask so it feels easier to answer.",
      shorter: "I would keep the decision, the reason, and the ask; everything else can be optional.",
    },
    apology: {
      clearer: "I would say what happened, what I understand now, and what I will do differently.",
      warmer: "I would keep the accountability and add one sentence that acknowledges the other person’s experience.",
      shorter: "I would remove the explanation that sounds defensive and keep the repair step.",
    },
    essay: {
      clearer: "I would make the main idea explicit, then give one example that proves it.",
      warmer: "I would keep the argument, but make the transition smoother so the reader can follow the turn.",
      shorter: "I would keep the claim and strongest example, then cut repeated setup.",
    },
    feedback: {
      clearer: "I would separate what worked, what was confusing, and the next useful step.",
      warmer: "I would keep the point, but frame it as help for the next attempt.",
      shorter: "I would keep one observation and one next step.",
    },
    conflict: {
      clearer: "I would name the issue without escalating it, then ask for one concrete next step.",
      warmer: "I would include one sentence that lowers the temperature before naming the boundary.",
      shorter: "I would cut the extra history and keep the boundary plus the next step.",
    },
    cover: {
      clearer: "I would connect the experience to the role in one direct sentence.",
      warmer: "I would keep the confidence and add one human reason this role matters.",
      shorter: "I would keep the strongest fit point and remove broad claims.",
    },
    text: {
      clearer: "I would make the point in one sentence and make the next step easy.",
      warmer: "I would add one softening phrase without hiding the ask.",
      shorter: "I would keep it conversational and remove anything that sounds like a paragraph.",
    },
  };
  const key = Object.keys(map).find((item) => clean.includes(item));
  return key ? map[key][mode] : "";
}

function enterpriseContext() {
  const fallback = state.enterpriseContext || {};
  const get = (id) => document.querySelector(`#field-${id}`)?.value.trim() || fallback[id] || "";
  const tone = (id, value) => document.querySelector(`#tone-${id}`)?.value || fallback[id] || value;
  return {
    project: get("project") || "Forecast risk pilot",
    folder: get("folder") || "RevOps",
    company: get("company") || "TextTraits",
    offer: get("offer") || "a review workspace for outbound drafts, replies, and campaign outcomes",
    role: get("role") || "VP Revenue",
    goal: get("goal") || "Book call",
    preset: get("preset") || "Premium",
    industry: get("industry") || "SaaS",
    seniority: get("seniority") || "Executive",
    segment: get("segment") || "Mid-market SaaS",
    stage: get("stage") || "Evaluating",
    source: get("source") || "Reply",
    region: get("region") || "North America",
    pain: get("pain") || "renewal risk and missed coaching moments",
    trigger: get("trigger") || "board forecast cleanup",
    icp: get("icp") || "Revenue teams with 30+ sellers",
    proof: get("proof") || "reduced manual reporting by 32%",
    caseStudy: get("caseStudy") || "Series B sales org",
    competitor: get("competitor") || "spreadsheet-heavy review process",
    brandVoice: get("brandVoice") || "Executive concise",
    template: get("template") || "Pain-led cold email",
    firstName: get("firstName") || state.recipient.firstName,
    recipientCompany: get("recipientCompany") || state.recipient.company,
    recipientRole: get("recipientRole") || state.recipient.role,
    direct: tone("direct", "70"),
    warm: tone("warm", "55"),
    formal: tone("formal", "62"),
    technical: tone("technical", "48"),
    concise: tone("concise", "82"),
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
    ["Earlier risk visibility", 94, `Connect ${context.offer} to the buyer's need for earlier, cleaner pipeline warnings.`],
    ["Manager coaching rhythm", 88, `Position the workflow around the exact moment managers need to intervene.`],
    ["Low-friction implementation", 81, `Emphasize a focused pilot, not another broad reporting platform.`],
  ];
}

function compactPhrase(value, limit = 5) {
  return enterpriseCopy.compactPhrase(value, limit);
}

function subjectLines(context) {
  return enterpriseCopy.subjectLines(context);
}

function ctaText(context) {
  return enterpriseCopy.ctaText(context);
}

function buildEmailVariant(context, profile, variant) {
  return enterpriseCopy.buildEmailVariant(context, variant, {
    learned: winnerPatterns(),
    feedback: state.feedbackMemory,
  });
}

function generateDraftObjects(context, profile) {
  return ["A", "B", "C"].map((key, index) => {
    const raw = buildEmailVariant(context, profile, key);
    const [subjectLine, ...body] = raw.split("\n");
    const scores = [
      {clarity: 94, specificity: 88, cta: 91, skimmability: 90},
      {clarity: 89, specificity: 92, cta: 86, skimmability: 88},
      {clarity: 87, specificity: 85, cta: 84, skimmability: 93},
    ][index];
    return {
      key,
      name: key === "A" ? "Signal-led" : key === "B" ? "Problem-led" : "Operations-led",
      subject: subjectLine.replace(/^Subject:\s*/, ""),
      body: body.join("\n").trim(),
      scores,
      status: index === 0 ? "Needs review" : "Draft",
      owner: index === 0 ? "Maya" : "Unassigned",
      due: index === 0 ? "Today" : "This week",
      history: [`Generated ${new Date().toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"})}`],
      note: key === "A" ? "Best variant: highest clarity and CTA strength." : key === "B" ? "Strong when the buyer named a pain directly." : "Useful for senior operations audiences.",
    };
  });
}

function draftText(draft) {
  return `Subject: ${draft.subject}\n\nHi {{first_name}},\n\n${draft.body.replace(/^Hi \{\{first_name\}\},\s*/i, "").trim()}`;
}

function selectedDraft() {
  return state.enterpriseDrafts.find((draft) => draft.key === state.selectedVariant) || state.enterpriseDrafts[0];
}

function averageScore(draft) {
  const values = Object.values(draft.scores || {});
  if (!values.length) return 0;
  return Math.round(values.reduce((total, value) => total + Number(value || 0), 0) / values.length);
}

function bestDraft() {
  return [...state.enterpriseDrafts].sort((a, b) => averageScore(b) - averageScore(a))[0];
}

function buildSequence(context) {
  return enterpriseCopy.buildSequence(context);
}

function renderEnterpriseResult(data) {
  syncBodyState();
  const context = enterpriseContext();
  state.enterpriseContext = context;
  state.recipient = {
    firstName: context.firstName,
    company: context.recipientCompany,
    role: context.recipientRole,
  };
  const profile = enterpriseProfile(data);
  if (!state.enterpriseDrafts.length) {
    state.enterpriseDrafts = generateDraftObjects(context, profile);
  }
  const variants = state.enterpriseDrafts;
  const angles = enterpriseAngles(context, profile);
  const sequence = buildSequence(context);
  const csv = makeCsv(context, variants);
  const best = bestDraft();
  const active = selectedDraft();
  if (state.activeEnterpriseTab === "analytics") {
    state.activeEnterpriseTab = "tools";
    state.activeEnterpriseTool = "insights";
  }
  const validTabs = ["dashboard", "drafts", "tools"];
  if (!validTabs.includes(state.activeEnterpriseTab)) {
    state.activeEnterpriseTool = ["batch", "sequence", "inbox", "libraries", "insights"].includes(state.activeEnterpriseTab) ? state.activeEnterpriseTab : state.activeEnterpriseTool;
    state.activeEnterpriseTab = state.activeEnterpriseTab === "signals" || state.activeEnterpriseTab === "workspace" || state.activeEnterpriseTab === "brief" || state.activeEnterpriseTab === "campaign" ? "dashboard" : "tools";
  }
  if (!["batch", "sequence", "inbox", "libraries", "insights"].includes(state.activeEnterpriseTool)) {
    state.activeEnterpriseTool = "batch";
  }

  els.outputPanel.innerHTML = `
    <div class="result-layout fade-in">
      <div class="enterprise-command-header">
        <div class="enterprise-command-title">
          <p class="label">Enterprise workspace</p>
          <h2>${state.activeEnterpriseTab === "drafts" ? "Review generated drafts" : escapeHtml(context.project || `${context.role} outreach system`)}</h2>
          <div class="command-meta">
            <span>${escapeHtml(context.project)} / ${variants.length} drafts / ${state.lastGeneratedAt || "Just now"}</span>
            <span class="demo-badge">Local demo / preview integrations</span>
          </div>
        </div>
        <div class="command-actions">
          ${state.activeEnterpriseTab !== "dashboard" ? `<button class="button-secondary" data-enterprise-primary-tab="dashboard">Dashboard</button>` : ""}
          <button class="button-secondary" data-toggle-inputs>${state.enterpriseInputsCollapsed ? "Edit setup" : "Hide setup"}</button>
          <button class="button-secondary save-campaign-button" data-save-campaign aria-label="Save campaign">${state.campaignSaved ? "Saved" : "Save"}</button>
          <details class="action-menu">
            <summary>More</summary>
            <div>
              <button class="button-secondary" data-export-csv>Export CSV</button>
              <button class="button-secondary" data-copy-all>Copy campaign brief</button>
              <button class="button-secondary" data-copy-subjects>Copy subject lines</button>
              <button class="button-secondary" data-regenerate>Regenerate drafts</button>
              <button class="button-secondary" data-open-crm-setup>CRM setup</button>
              <button class="button-secondary" data-open-inbox-setup>Email setup</button>
            </div>
          </details>
        </div>
        <nav class="tabs workspace-tabs grouped-tabs compact-workspace-nav" role="tablist" aria-label="Enterprise workspace areas">
          ${tabButton("dashboard", "Dashboard", state.activeEnterpriseTab)}
          ${tabButton("drafts", "Drafts", state.activeEnterpriseTab)}
          ${tabButton("tools", "Operations", state.activeEnterpriseTab)}
        </nav>
        <span class="next-action">${escapeHtml(state.lastActionNote || "Next: review generated drafts or import a prospect batch.")}</span>
      </div>

      <div class="enterprise-workspace-grid">
        ${projectSidebar(context)}
        <section class="workspace-main">
          <div id="panel-${state.activeEnterpriseTab}" class="tab-panel workspace-panel" role="tabpanel" tabindex="-1" aria-labelledby="tab-${state.activeEnterpriseTab}">${renderEnterpriseTab(data, context, profile, variants, angles, sequence)}</div>
        </section>
      </div>
    </div>
  `;

  els.outputPanel.querySelectorAll("[data-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      state.tabScroll[state.activeEnterpriseTab] = window.scrollY;
      state.activeEnterpriseTab = button.dataset.tab;
      state.lastActionNote = enterpriseTabNote(state.activeEnterpriseTab);
      renderEnterpriseResult(data);
      els.outputPanel.querySelector(".tab-panel")?.focus?.();
      requestAnimationFrame(() => window.scrollTo(0, state.tabScroll[state.activeEnterpriseTab] || 0));
    });
  });
  els.outputPanel.querySelectorAll("[data-tool]").forEach((button) => {
    button.addEventListener("click", () => {
      state.activeEnterpriseTool = button.dataset.tool;
      state.activeEnterpriseTab = "tools";
      state.lastActionNote = enterpriseToolNote(state.activeEnterpriseTool);
      renderEnterpriseResult(data);
      els.outputPanel.querySelector(".workspace-panel")?.focus?.();
    });
  });
  els.outputPanel.querySelectorAll("[data-tree-shortcut]").forEach((button) => {
    button.addEventListener("click", () => {
      const shortcut = button.dataset.treeShortcut;
      if (shortcut === "campaigns") {
        state.activeEnterpriseTab = "dashboard";
        state.lastActionNote = "Opened the campaign dashboard.";
      } else if (shortcut === "batch" || shortcut === "inbox") {
        state.activeEnterpriseTab = "tools";
        state.activeEnterpriseTool = shortcut;
        state.lastActionNote = enterpriseToolNote(shortcut);
      } else if (shortcut === "personas" || shortcut === "templates") {
        state.activeEnterpriseTab = "tools";
        state.activeEnterpriseTool = "libraries";
        state.lastActionNote = shortcut === "personas" ? "Opened persona and ICP libraries." : "Opened team templates and brand voice.";
      }
      renderEnterpriseResult(data);
      els.outputPanel.querySelector(".workspace-panel")?.focus?.();
    });
  });
  els.outputPanel.querySelectorAll("[data-enterprise-primary-tab]").forEach((button) => {
    button.addEventListener("click", (event) => {
      state.activeEnterpriseTab = event.currentTarget.dataset.enterprisePrimaryTab;
      state.lastActionNote = enterpriseTabNote(state.activeEnterpriseTab);
      renderEnterpriseResult(data);
      els.outputPanel.querySelector(".workspace-panel")?.focus?.();
    });
  });

  const allText = enterpriseBriefText(context, variants, angles, sequence);
  bindCopy("[data-copy-all]", allText, "Enterprise brief copied.");
  bindCopy("[data-copy-subjects]", variants.map((draft) => draft.subject).join("\\n"), "Subject lines copied.");
  els.outputPanel.querySelector("[data-export-csv]").addEventListener("click", (event) => {
    const validation = validateMergeFields(variants);
    if (!validation.ok) {
      showToast(event.currentTarget, validation.message);
      return;
    }
    downloadCsv(csv);
    recordExport("Campaign CSV", context.project, variants.length);
    showToast(event.currentTarget, "CSV exported and merge fields validated.");
  });
  els.outputPanel.querySelector("[data-regenerate]").addEventListener("click", () => {
    state.enterpriseDrafts = generateDraftObjects(context, profile).map((draft) => ({
      ...draft,
      history: [...draft.history, "Regenerated from current campaign context"],
    }));
    state.lastActionNote = "Regenerated variants from current inputs.";
    state.lastGeneratedAt = new Date().toLocaleString([], {month: "short", day: "numeric", hour: "2-digit", minute: "2-digit"});
    renderEnterpriseResult(data);
  });
  els.outputPanel.querySelector("[data-open-crm-setup]")?.addEventListener("click", () => {
    state.activeEnterpriseTab = "tools";
    state.activeEnterpriseTool = "insights";
    state.integrationSetupOpen = true;
    state.lastActionNote = enterpriseToolNote("insights");
    renderEnterpriseResult(data);
  });
  els.outputPanel.querySelector("[data-open-inbox-setup]")?.addEventListener("click", () => {
    state.activeEnterpriseTab = "tools";
    state.activeEnterpriseTool = "inbox";
    state.lastActionNote = "Connect Gmail or Outlook before reply triage.";
    renderEnterpriseResult(data);
  });
  els.outputPanel.querySelector("[data-toggle-inputs]").addEventListener("click", () => {
    state.enterpriseInputsCollapsed = !state.enterpriseInputsCollapsed;
    render();
  });
  els.outputPanel.querySelector("[data-toggle-editor-focus]")?.addEventListener("click", () => {
    state.enterpriseFocusMode = !state.enterpriseFocusMode;
    state.lastActionNote = state.enterpriseFocusMode ? "Focused editor mode on." : "Review queue visible.";
    persistWorkspace();
    renderEnterpriseResult(data);
  });
  els.outputPanel.querySelector("[data-save-campaign]").addEventListener("click", (event) => {
    saveCurrentCampaign(context);
    showToast(event.currentTarget, "Campaign saved to workspace.");
    renderEnterpriseResult(data);
  });
  els.outputPanel.querySelectorAll("[data-copy-draft]").forEach((button) => {
    button.addEventListener("click", async () => {
      const draft = state.enterpriseDrafts.find((item) => item.key === button.dataset.copyDraft);
      await copyTextFromButton(button, draft ? draftText(draft) : "", "Variant copied.");
    });
  });
  els.outputPanel.querySelectorAll("[data-copy-row]").forEach((button) => {
    button.addEventListener("click", async () => {
      const row = state.batchRows.find((item) => String(item.id) === String(button.dataset.copyRow));
      await copyTextFromButton(button, row ? `${row.subject}\n${row.signal}` : "", "Brief copied.");
    });
  });
  els.outputPanel.querySelectorAll("[data-review-row]").forEach((button) => {
    button.addEventListener("click", () => {
      const row = state.batchRows.find((item) => String(item.id) === String(button.dataset.reviewRow));
      if (!row) return;
      row.status = "Needs review";
      row.next = "Approve or edit";
      state.selectedProspectId = Number(row.id);
      state.activeEnterpriseTab = "drafts";
      state.lastActionNote = `${row.first_name} at ${row.company} moved into review.`;
      persistWorkspace();
      renderEnterpriseResult(data);
      els.outputPanel.querySelector(".prospect-detail-card")?.setAttribute("open", "");
      els.outputPanel.querySelector(".draft-editor")?.focus?.();
    });
  });
  els.outputPanel.querySelectorAll("[data-export-row]").forEach((button) => {
    button.addEventListener("click", () => {
      const row = state.batchRows.find((item) => String(item.id) === String(button.dataset.exportRow));
      if (!row) return;
      row.status = "Exported";
      row.next = "Track outcome";
      state.selectedProspectId = Number(row.id);
      recordExport(`Batch row: ${row.company}`, context.project, 1);
      state.lastActionNote = `${row.first_name} at ${row.company} marked exported.`;
      persistWorkspace();
      renderEnterpriseResult(data);
    });
  });
  els.outputPanel.querySelectorAll("[data-transform]").forEach((button) => {
    button.addEventListener("click", () => {
      transformDraft(button.dataset.transform, button.dataset.variant || state.selectedVariant, context);
      state.lastActionNote = `${button.textContent.trim()} applied to Variant ${state.selectedVariant}.`;
      renderEnterpriseResult(data);
    });
  });
  els.outputPanel.querySelectorAll("[data-feedback]").forEach((button) => {
    button.addEventListener("click", () => {
      recordFeedback(button.dataset.feedback, button.dataset.feedbackScope || "Enterprise");
      state.lastActionNote = "Feedback saved. Draft guidance will adapt.";
      updateVisibleActionNote();
      showToast(button, "Feedback saved. Draft guidance will adapt.");
    });
  });
  els.outputPanel.querySelectorAll("[data-restore-version]").forEach((button) => {
    button.addEventListener("click", () => {
      restoreVersion(button.dataset.restoreVersion, "Enterprise draft");
      showToast(button, "Draft version restored.");
      renderEnterpriseResult(data);
    });
  });
  els.outputPanel.querySelectorAll("[data-select-variant]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedVariant = button.dataset.selectVariant;
      state.activeEnterpriseTab = "drafts";
      renderEnterpriseResult(data);
    });
  });
  els.outputPanel.querySelectorAll("[data-review-draft]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedVariant = button.dataset.reviewDraft;
      state.activeEnterpriseTab = "drafts";
      state.lastActionNote = `Opened Variant ${state.selectedVariant} in the draft editor.`;
      renderEnterpriseResult(data);
      els.outputPanel.querySelector(".draft-editor")?.focus?.();
    });
  });
  els.outputPanel.querySelectorAll("[data-review-prospect]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedProspectId = Number(button.dataset.reviewProspect);
      state.selectedVariant = bestDraft()?.key || state.selectedVariant;
      state.activeEnterpriseTab = "drafts";
      state.lastActionNote = "Opened the prospect detail with the recommended draft.";
      renderEnterpriseResult(data);
      const detail = els.outputPanel.querySelector(".prospect-detail-card");
      if (detail) detail.open = true;
      detail?.scrollIntoView?.({behavior: "smooth", block: "nearest"});
    });
  });
  els.outputPanel.querySelectorAll("[data-approve-draft]").forEach((button) => {
    button.addEventListener("click", () => {
      const draft = state.enterpriseDrafts.find((item) => item.key === button.dataset.approveDraft);
      if (!draft) return;
      draft.status = "Approved";
      draft.history.push("Approved for export");
      state.lastActionNote = `Variant ${draft.key} approved.`;
      persistWorkspace();
      renderEnterpriseResult(data);
    });
  });
  els.outputPanel.querySelectorAll("[data-export-draft]").forEach((button) => {
    button.addEventListener("click", () => {
      const draft = state.enterpriseDrafts.find((item) => item.key === button.dataset.exportDraft);
      if (!draft) return;
      draft.status = "Exported";
      draft.history.push("Marked exported");
      recordExport(`Variant ${draft.key}`, context.project, 1);
      state.outcomeStats.sent = Number(state.outcomeStats.sent || 0) + 1;
      state.lastActionNote = `Variant ${draft.key} marked exported.`;
      persistWorkspace();
      renderEnterpriseResult(data);
    });
  });
  els.outputPanel.querySelectorAll("[data-draft-field]").forEach((field) => {
    field.addEventListener("input", () => {
      const draft = state.enterpriseDrafts.find((item) => item.key === field.dataset.variant);
      if (!draft) return;
      draft[field.dataset.draftField] = field.value;
      if (!draft.history.includes("Edited manually")) draft.history.push("Edited manually");
      persistWorkspace();
      const preview = els.outputPanel.querySelector("[data-resolved-preview]");
      if (preview) preview.textContent = resolveMergeFields(draftText(draft));
    });
  });
  els.outputPanel.querySelectorAll("[data-recipient-field]").forEach((field) => {
    field.addEventListener("input", () => {
      state.recipient[field.dataset.recipientField] = field.value;
      persistWorkspace();
      const preview = els.outputPanel.querySelector("[data-resolved-preview]");
      if (preview) preview.textContent = resolveMergeFields(draftText(selectedDraft()));
    });
  });
  els.outputPanel.querySelectorAll("[data-insert-field]").forEach((button) => {
    button.addEventListener("click", () => insertMergeField(button.dataset.insertField));
  });
  const workspaceSearch = els.outputPanel.querySelector("#workspace-search");
  if (workspaceSearch) {
    workspaceSearch.addEventListener("input", () => {
      state.workspaceSearch = workspaceSearch.value;
      renderEnterpriseResult(data);
    });
  }
  ["workspaceFolder", "workspaceStatus"].forEach((key) => {
    const field = els.outputPanel.querySelector(`#field-${key}`);
    if (!field) return;
    field.addEventListener("change", () => {
      state[key] = field.value;
      renderEnterpriseResult(data);
    });
  });
  els.outputPanel.querySelectorAll("[data-load-campaign]").forEach((button) => {
    button.addEventListener("click", () => {
      const campaign = state.savedCampaigns.find((item) => item.name === button.dataset.loadCampaign);
      if (!campaign) return;
      state.enterpriseContext = {...context, project: campaign.name, folder: campaign.folder};
      state.lastActionNote = `${campaign.name} loaded.`;
      renderEnterpriseResult(data);
    });
  });
  els.outputPanel.querySelectorAll("[data-status-campaign]").forEach((button) => {
    button.addEventListener("click", () => {
      const campaign = state.savedCampaigns.find((item) => item.name === button.dataset.statusCampaign);
      if (campaign) campaign.status = "Reviewed";
      state.lastActionNote = "Campaign marked reviewed.";
      persistWorkspace();
      renderEnterpriseResult(data);
    });
  });
  els.outputPanel.querySelectorAll("[data-crm]").forEach((button) => {
    button.addEventListener("click", () => {
      const name = button.dataset.crm;
      const current = state.crmConnections[name];
      if (current !== "connected") {
        state.activeEnterpriseTab = "tools";
        state.activeEnterpriseTool = "insights";
        state.integrationSetupOpen = true;
        state.lastActionNote = `${name} setup requires real credentials and provider approval.`;
        showToast(button, `${name} needs credentials before export.`);
        renderEnterpriseResult(data);
        return;
      }
      state.crmConnections[name] = "exported";
      state.lastActionNote = `${name} export recorded.`;
      if (state.account.authenticated) {
        apiClient.saveIntegration(name, state.crmConnections[name], {workspace: state.account.workspaceName}).catch(() => {});
      }
      persistWorkspace();
      renderEnterpriseResult(data);
    });
  });
  els.outputPanel.querySelectorAll("[data-outcome]").forEach((button) => {
    button.addEventListener("click", () => {
      state.outcomeStats[button.dataset.outcome] = Number(state.outcomeStats[button.dataset.outcome] || 0) + 1;
      state.lastActionNote = `${titleCase(button.dataset.outcome)} outcome recorded.`;
      persistWorkspace();
      updateVisibleActionNote();
      showToast(button, state.lastActionNote);
    });
  });
  els.outputPanel.querySelector("[data-load-sample-csv]")?.addEventListener("click", () => {
    state.batchInput = sampleCsv;
    state.sampleWorkspaceLoaded = true;
    state.lastActionNote = "Loaded sample CSV with prospect rows.";
    renderEnterpriseResult(data);
  });
  const batchInput = els.outputPanel.querySelector("#batch-input");
  batchInput?.addEventListener("input", () => {
    state.batchInput = batchInput.value;
    state.batchProgress = 0;
    state.batchErrors = [];
    persistWorkspace();
  });
  els.outputPanel.querySelector("[data-generate-batch]")?.addEventListener("click", () => {
    const input = els.outputPanel.querySelector("#batch-input")?.value || "";
    state.batchInput = input;
    if (!input.trim()) {
      state.batchErrors = ["Paste CSV rows or load the sample CSV first."];
      state.batchProgress = 0;
      state.lastActionNote = "Batch generation needs CSV input first.";
      renderEnterpriseResult(data);
      return;
    }
    ["first_name", "company", "role", "industry", "signal"].forEach((column) => {
      const field = els.outputPanel.querySelector(`#map-${column}`);
      if (field) state.batchMapping[column] = field.value.trim() || column;
    });
    state.batchRows = parseCsv(input, state.batchMapping);
    state.batchProgress = state.batchRows.length ? 100 : 0;
    state.outcomeStats.generated += state.batchRows.length;
    state.lastActionNote = state.batchRows.length ? `${state.batchRows.length} batch briefs generated. Next: review rows.` : "Fix CSV issues before generating briefs.";
    persistWorkspace();
    renderEnterpriseResult(data);
  });
  els.outputPanel.querySelector("[data-export-batch]")?.addEventListener("click", (event) => {
    downloadCsv(batchCsv());
    recordExport("Batch CSV", context.project, state.batchRows.length);
    showToast(event.currentTarget, "Batch CSV exported.");
  });
  els.outputPanel.querySelector("[data-load-inbox]")?.addEventListener("click", () => {
    state.inboxThreads = [...sampleInboxThreads];
    state.lastActionNote = "Sample inbox replies loaded.";
    persistWorkspace();
    renderEnterpriseResult(data);
  });
  els.outputPanel.querySelector("[data-generate-next-replies]")?.addEventListener("click", () => {
    state.inboxThreads = state.inboxThreads.map((thread) => ({
      ...thread,
      reply: inboxReply(thread, context),
    }));
    state.lastActionNote = "Next responses suggested for inbox replies.";
    persistWorkspace();
    renderEnterpriseResult(data);
  });
  els.outputPanel.querySelectorAll("[data-inbox-reply]").forEach((field) => {
    field.addEventListener("input", () => {
      const thread = state.inboxThreads[Number(field.dataset.inboxReply)];
      if (!thread) return;
      thread.reply = field.value;
      thread.status = "Edited reply";
      persistWorkspace();
    });
  });
  els.outputPanel.querySelectorAll("[data-copy-inbox]").forEach((button) => {
    button.addEventListener("click", async () => {
      const thread = state.inboxThreads[Number(button.dataset.copyInbox)];
      const editor = button.closest("article")?.querySelector(".suggested-editor");
      const replyText = editor?.value || thread?.reply || (thread ? inboxReply(thread, context) : "");
      if (thread) {
        thread.reply = replyText;
        persistWorkspace();
      }
      await copyTextFromButton(button, replyText, "Next response copied.");
    });
  });
  els.outputPanel.querySelectorAll("[data-draft-inbox]").forEach((button) => {
    button.addEventListener("click", () => {
      const thread = state.inboxThreads[Number(button.dataset.draftInbox)];
      if (thread) {
        thread.reply = inboxReply(thread, context);
        thread.status = "Draft reply";
      }
      state.lastActionNote = "Reply draft prepared.";
      persistWorkspace();
      renderEnterpriseResult(data);
    });
  });
  els.outputPanel.querySelectorAll("[data-snooze-inbox]").forEach((button) => {
    button.addEventListener("click", () => {
      const thread = state.inboxThreads[Number(button.dataset.snoozeInbox)];
      if (thread) thread.status = "Snoozed";
      state.lastActionNote = "Inbox reply snoozed.";
      persistWorkspace();
      renderEnterpriseResult(data);
    });
  });
  els.outputPanel.querySelectorAll("[data-mark-handled]").forEach((button) => {
    button.addEventListener("click", () => {
      const thread = state.inboxThreads[Number(button.dataset.markHandled)];
      if (thread) thread.handled = true;
      state.lastActionNote = "Inbox reply marked handled.";
      persistWorkspace();
      renderEnterpriseResult(data);
    });
  });
  els.outputPanel.querySelector("[data-learn-winners]")?.addEventListener("click", () => {
    const text = els.outputPanel.querySelector("#winner-input")?.value || "";
    state.winnerSamples = text.split(/\n+/).map((item) => item.trim()).filter(Boolean);
    state.lastActionNote = "Winner patterns updated.";
    persistWorkspace();
    renderEnterpriseResult(data);
  });
  const sequenceLength = els.outputPanel.querySelector("#sequence-length");
  if (sequenceLength) {
    sequenceLength.addEventListener("input", () => {
      state.sequenceSettings.length = Math.max(2, Math.min(8, Number(sequenceLength.value || 4)));
      persistWorkspace();
      renderEnterpriseResult(data);
    });
  }
  ["sequenceStart", "sequenceLogic"].forEach((key) => {
    const field = els.outputPanel.querySelector(`#field-${key}`);
    if (!field) return;
    field.addEventListener("change", () => {
      if (key === "sequenceStart") state.sequenceSettings.startDay = field.value;
      else state.sequenceSettings.logic = field.value;
      persistWorkspace();
      renderEnterpriseResult(data);
    });
  });
  persistWorkspace();
}

function projectSidebar(context) {
  const openReplies = state.inboxThreads.filter((thread) => !thread.handled).length;
  const rows = state.sampleWorkspaceLoaded
    ? [
      ["campaigns", "Campaigns", state.savedCampaigns.length ? `Sample: ${state.savedCampaigns.length} saved` : "No saved campaigns"],
      ["batch", "Batches", state.batchRows.length ? `${state.batchRows.length} prospects` : "Sample: 100 prospects"],
      ["inbox", "Replies", openReplies ? `Sample: ${openReplies} open` : "No open replies"],
      ["personas", "Personas", state.personaLibrary.length ? `Sample: ${state.personaLibrary.length} profiles` : "No profiles"],
      ["templates", "Templates", `Sample: ${outboundTemplates.length} approved`],
    ]
    : [
      ["campaigns", "Campaigns", "No saved campaigns"],
      ["batch", "Batches", "No imported prospects"],
      ["inbox", "Replies", "Connect inbox"],
      ["personas", "Personas", "Create library"],
      ["templates", "Templates", "Add templates"],
    ];
  return `
    <aside class="project-sidebar" aria-label="Project sidebar">
      <div>
        <span class="label">Workspace</span>
        <strong>${escapeHtml(context.folder || "RevOps")}</strong>
      </div>
      ${rows.map(([key, label, meta]) => `<button type="button" class="tree-row" data-tree-shortcut="${escapeHtml(key)}"><span>${escapeHtml(label)}</span><small>${escapeHtml(meta)}</small></button>`).join("")}
    </aside>
  `;
}

function workflowPathHtml() {
  const labels = uiHelpers.workflowLabels?.() || productConfig.workflow || ["Import", "Draft", "Review", "Export", "Track"];
  return `
    <div class="flow-path compact-flow">
      ${labels.map((step, index) => `
        <article class="${index === 2 ? "is-active" : ""}">
          <span>${index + 1}</span>
          <strong>${escapeHtml(step)}</strong>
        </article>
      `).join("")}
    </div>
  `;
}

function campaignProspects(context) {
  if (state.batchRows.length) return state.batchRows.slice(0, 8);
  return [
    {id: 1, first_name: context.firstName || "Maya", company: context.recipientCompany || "Acme Revenue", role: context.recipientRole || context.role, industry: context.industry, signal: context.pain, status: "Draft ready", subject: subjectLines(context)[0], next: "Review"},
    {id: 2, first_name: "Jordan", company: "Northwind Ops", role: "RevOps Director", industry: "SaaS", signal: "Migration concern and late pipeline risk", status: "Needs proof", subject: "Idea for pipeline inspection", next: "Add proof"},
    {id: 3, first_name: "Taylor", company: "Bluepeak", role: "Founder", industry: "B2B software", signal: "Cleaner handoffs without more dashboards", status: "Queued", subject: "Cleaner handoffs", next: "Generate"},
  ];
}

function reviewQueueItems(context, variants) {
  const variantRows = variants.map((draft, index) => ({
    id: `draft-${draft.key}`,
    draftKey: draft.key,
    target: "draft",
    title: `Variant ${draft.key}: ${draft.name}`,
    owner: draft.owner || (index === 0 ? "Maya" : "Unassigned"),
    status: draft.status || (index === 0 ? "Needs review" : "Draft"),
    due: draft.due || "This week",
    score: averageScore(draft),
    next: index === 0 ? "Approve or edit" : "Compare",
  }));
  const prospectRows = campaignProspects(context).slice(0, 3).map((row, index) => ({
    id: `prospect-${row.id || index}`,
    prospectId: row.id || index,
    target: "prospect",
    title: `${row.first_name} at ${row.company}`,
    owner: index === 0 ? "Revenue lead" : "SDR team",
    status: row.status || "Queued",
    due: index === 0 ? "Today" : "This week",
    score: 92 - index * 4,
    next: row.next || "Review",
  }));
  return [...variantRows, ...prospectRows];
}

function reviewQueueTable(context, variants) {
  const rows = reviewQueueItems(context, variants);
  return `
    <div class="review-table">
      <div class="table-head review-head"><span>Item</span><span>Owner</span><span>Status</span><span>Due</span><span>Score</span><span>Next</span></div>
      ${rows.map((row) => `
        <div class="table-row review-row">
          <span><strong>${escapeHtml(row.title)}</strong></span>
          <span data-label="Owner">${escapeHtml(row.owner)}</span>
          <span data-label="Status"><em class="status-token">${escapeHtml(row.status)}</em></span>
          <span data-label="Due">${escapeHtml(row.due)}</span>
          <span data-label="Score">${escapeHtml(row.score)}</span>
          <span data-label="Next">
            <button
              class="table-action"
              type="button"
              ${row.target === "draft" ? `data-review-draft="${escapeHtml(row.draftKey)}"` : `data-review-prospect="${escapeHtml(row.prospectId)}"`}
              aria-label="${escapeHtml(`${row.next} ${row.title}`)}"
            >${escapeHtml(row.next)}</button>
          </span>
        </div>
      `).join("")}
    </div>
  `;
}

function campaignHome(context, angles) {
  const prospects = campaignProspects(context);
  const campaigns = state.sampleWorkspaceLoaded || state.campaignSaved ? filteredCampaigns() : [];
  const variants = state.enterpriseDrafts.length ? state.enterpriseDrafts : generateDraftObjects(context, {dims: {}, stats: {}});
  return `
    <div class="campaign-workspace">
      <section class="enterprise-focus-band">
        <article class="strategy-card featured dashboard-focus-card">
          <div class="section-title compact-dashboard-title">
            <div>
              <span class="label">Today's work</span>
              <h3>${prospects.length} prospects ready for review</h3>
            </div>
          <button type="button" data-enterprise-primary-tab="drafts">Open review queue</button>
          </div>
          <p>One clean path: Import prospects, generate drafts, review the queue, export or send, then track outcomes.</p>
          <div class="focus-stats">
            ${summaryItem("Status", state.campaignSaved ? "Saved" : "Drafts ready")}
            ${summaryItem("Owner", "Revenue team")}
            ${summaryItem("Due", "This week")}
            ${summaryItem("Next", "Review queue")}
          </div>
          ${workflowPathHtml()}
        </article>
      </section>

      <article class="strategy-card">
        <div class="section-title">
          <div>
            <strong>Review queue</strong>
            <p>Approve drafts, assign owners, track due dates, and keep export work visible.</p>
          </div>
          <button class="button-secondary" type="button" data-enterprise-primary-tab="drafts">Open draft editor</button>
        </div>
        ${reviewQueueTable(context, variants)}
      </article>

      <details class="secondary-workspace-section">
        <summary>Prospects, saved workspaces, and campaign detail</summary>
        <div class="secondary-workspace-content">
          <article class="strategy-card">
            <div class="section-title">
              <div>
                <strong>Prospect list</strong>
                <p>Rows show draft status, reply status, and CRM readiness.</p>
              </div>
              <button class="button-secondary" type="button" data-tool="batch">Open batch tools</button>
            </div>
            <div class="prospect-table">
              <div class="table-head"><span><input type="checkbox" aria-label="Select all prospects"></span><span>Prospect</span><span>Score</span><span>Draft</span><span>CRM</span><span>Next</span></div>
              ${prospects.map((row, index) => `
                <div class="table-row">
                  <span><input type="checkbox" aria-label="Select ${escapeHtml(row.first_name)}"></span>
                  <span><strong>${escapeHtml(row.first_name)} at ${escapeHtml(row.company)}</strong><small>${escapeHtml(row.role)} / ${escapeHtml(row.signal)}</small></span>
                  <span data-label="Score">${92 - index * 4}</span>
                  <span data-label="Draft">${escapeHtml(row.status || "Generated")}</span>
                  <span data-label="CRM">${index === 0 ? "Connected" : "Preview only"}</span>
                  <span data-label="Next">${escapeHtml(row.next || "Review")}</span>
                </div>
              `).join("")}
            </div>
          </article>

          <article class="strategy-card saved-workspaces-card">
            <div class="section-title">
              <div>
                <strong>Saved workspaces</strong>
                <p>${campaigns.length} results match your filters.</p>
              </div>
              <div class="workspace-controls compact-controls">
                <label class="field"><span>Search</span><input id="workspace-search" value="${escapeHtml(state.workspaceSearch)}" placeholder="Search"></label>
                ${selectField("workspaceStatus", "Status", ["All", ...uniqueValues(state.savedCampaigns, "status")], state.workspaceStatus)}
              </div>
            </div>
            <div class="campaign-table dense-table">
              ${campaigns.slice(0, 4).map((campaign) => `
                <article>
                  <strong>${escapeHtml(campaign.name)}</strong>
                  <span>${escapeHtml(campaign.folder)} / ${escapeHtml(campaign.status)} / ${escapeHtml(campaign.prospects || 1)} prospects</span>
                  <div class="result-actions">
                    <button class="button-secondary" data-load-campaign="${escapeHtml(campaign.name)}">Load</button>
                    <button class="button-secondary" data-status-campaign="${escapeHtml(campaign.name)}">Mark reviewed</button>
                  </div>
                </article>
              `).join("")}
            </div>
          </article>

          <div class="detail-grid">
            <article class="strategy-card"><strong>Executive summary</strong><p>Lead with ${escapeHtml(angles[0][0].toLowerCase())} for ${escapeHtml(context.role)}. Anchor the message in ${escapeHtml(context.pain)} and support it with ${escapeHtml(context.proof)}.</p></article>
            <article class="strategy-card"><strong>Best CTA</strong><p>${escapeHtml(ctaText(context))}</p><strong>Likely objection</strong><p>"We already have dashboards." Answer with implementation clarity and fewer reporting loops.</p></article>
          </div>
        </div>
      </details>
    </div>
  `;
}

function draftsWorkspace(context, variants) {
  const best = bestDraft();
  const draft = selectedDraft();
  const prospects = campaignProspects(context);
  const selectedProspect = prospects.find((item) => item.id === state.selectedProspectId) || prospects[0];
  const previewLines = resolveMergeFields(draftText(draft)).split("\n").filter(Boolean).slice(0, 8).join("\n\n");
  return `
    <div class="drafts-workspace ${state.enterpriseFocusMode ? "is-focus-mode" : ""}">
      <aside class="review-queue">
        <strong>Review queue</strong>
        <p class="muted tiny-copy">Pick a draft, polish it, then approve or export.</p>
        ${variants.map((item) => `
          <button type="button" data-select-variant="${item.key}" aria-pressed="${String(item.key === draft.key)}">
            <span>Variant ${escapeHtml(item.key)}${item.key === best?.key ? " / best" : ""}</span>
            <small>${escapeHtml(item.name)} / ${averageScore(item)} score / ${escapeHtml(item.status || "Draft")}</small>
          </button>
        `).join("")}
        <details class="prospect-detail-card">
          <summary>Prospect detail</summary>
          <strong>${escapeHtml(selectedProspect.first_name)} at ${escapeHtml(selectedProspect.company)}</strong>
          <p>${escapeHtml(selectedProspect.role)} / ${escapeHtml(selectedProspect.signal)}</p>
          <small>Priority high / due today / CRM ${state.crmConnections.HubSpot === "connected" ? "ready" : "setup required"}</small>
        </details>
      </aside>
      <section class="email-editor focused-editor compact-draft-workspace">
        <article class="draft-focus-card">
          <div class="section-title">
            <div>
              <span class="label">Email editor</span>
              <strong>Variant ${escapeHtml(draft.key)}: ${escapeHtml(draft.name)}</strong>
              <p class="muted tiny-copy">Status: ${escapeHtml(draft.status || "Draft")} / Owner: ${escapeHtml(draft.owner || "Unassigned")} / Due: ${escapeHtml(draft.due || "This week")}</p>
            </div>
            <div class="editor-mode-actions">
              <span class="strength">Recommended: Variant ${escapeHtml(best?.key || "A")}</span>
              <button class="button-secondary" type="button" data-toggle-editor-focus>${state.enterpriseFocusMode ? "Show queue" : "Focus editor"}</button>
            </div>
          </div>
          <label class="field"><span>Subject line</span><input data-draft-field="subject" data-variant="${draft.key}" value="${escapeHtml(draft.subject)}"></label>
          <label class="field"><span>Email body</span><textarea class="draft-editor" data-draft-field="body" data-variant="${draft.key}">${escapeHtml(draft.body)}</textarea></label>
          ${state.lastDraftChange ? `<div class="editor-change-note" role="status"><strong>What changed</strong><span>${escapeHtml(state.lastDraftChange)}</span></div>` : ""}
          <details class="quality-summary">
            <summary>Quality check: ${averageScore(draft)} overall</summary>
            <div class="score-strip comparison-score compact-score-strip">
              ${Object.entries(draft.scores).map(([label, value]) => `<span><strong>${value}</strong>${escapeHtml(scoreLabel(label))}</span>`).join("")}
            </div>
          </details>
          <div class="result-actions editor-primary-actions">
            <button type="button" data-copy-draft="${escapeHtml(draft.key)}">Copy draft</button>
            <button class="button-secondary" type="button" data-approve-draft="${draft.key}">Approve</button>
            <button class="button-secondary" type="button" data-transform="shorter" data-variant="${draft.key}">Make shorter</button>
            <button class="button-secondary" type="button" data-transform="specific" data-variant="${draft.key}">Make more specific</button>
          </div>
          <div class="send-checklist editor-checklist">
            <strong>Send-ready checklist</strong>
            ${["Merge fields valid", "Proof point included", "CTA clear", "Unsubscribe token present"].map((item) => `<span>${escapeHtml(item)}</span>`).join("")}
          </div>
          <details class="editor-secondary-actions">
            <summary>More status actions</summary>
            <div class="result-actions">
            <button class="button-secondary" type="button" data-export-draft="${draft.key}">Mark exported</button>
            <button class="button-secondary" type="button" data-outcome="sent">Mark sent</button>
            <button class="button-secondary" type="button" data-outcome="replied">Mark replied</button>
            <button class="button-secondary" type="button" data-outcome="booked">Mark booked</button>
            </div>
          </details>
          <details class="feedback-menu">
            <summary>Draft feedback</summary>
            ${feedbackButtons("Enterprise draft")}
          </details>
          <details class="team-comments">
            <summary>Team comments</summary>
            <div class="comment-list">
              ${(state.teamComments.length ? state.teamComments : [{author: "Manager", text: "Check the proof point before export."}]).map((comment) => `<span><strong>${escapeHtml(comment.author || "Team")}</strong>${escapeHtml(comment.text || comment)}</span>`).join("")}
            </div>
          </details>
        </article>

        <details class="history-panel editor-collapse">
          <summary>Preview, merge fields, and history</summary>
          <article class="resolved-card">
            <strong>Resolved preview</strong>
            <pre data-resolved-preview>${escapeHtml(previewLines)}</pre>
          </article>
          <div class="editor-header">
            <label class="field"><span>Variant name</span><input data-draft-field="name" data-variant="${draft.key}" value="${escapeHtml(draft.name)}"></label>
            <span class="strength">Recommended: Variant ${escapeHtml(best?.key || "A")}</span>
          </div>
          <details class="history-panel rewrite-panel">
            <summary>Rewrite tools</summary>
            <div class="editor-actions compact-actions">
              ${transformButtons(draft.key)}
            </div>
          </details>
          <div class="recipient-preview">
            <div class="enterprise-field-grid">
              <label class="field"><span>First name</span><input data-recipient-field="firstName" value="${escapeHtml(state.recipient.firstName)}"></label>
              <label class="field"><span>Company</span><input data-recipient-field="company" value="${escapeHtml(state.recipient.company)}"></label>
              <label class="field"><span>Role</span><input data-recipient-field="role" value="${escapeHtml(state.recipient.role)}"></label>
            </div>
            <details class="merge-field-box">
              <summary>Insert merge field</summary>
              ${["{{first_name}}", "{{company}}", "{{role}}", "{{unsubscribe_link}}"].map((field) => `<button class="button-secondary" type="button" data-insert-field="${escapeHtml(field)}">${escapeHtml(field)}</button>`).join("")}
            </details>
          </div>
          <details class="history-panel">
            <summary>Draft history and version compare</summary>
            <div class="feature-list">${draft.history.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>
            ${versionHistoryHtml("Enterprise draft")}
          </details>
        </details>
      </section>
    </div>
  `;
}

function toolsWorkspace(context, sequence, angles) {
  const tools = [
    ["batch", "Batch"],
    ["sequence", "Sequence"],
    ["inbox", "Inbox"],
    ["libraries", "Libraries"],
    ["insights", "Insights"],
  ];
  return `
    <div class="tools-workspace">
      <nav class="tool-switcher" aria-label="Enterprise tools">
        ${tools.map(([key, label]) => `<button type="button" data-tool="${key}" aria-pressed="${String(state.activeEnterpriseTool === key)}">${escapeHtml(label)}</button>`).join("")}
      </nav>
      ${renderToolPanel(context, sequence, angles)}
    </div>
  `;
}

function renderToolPanel(context, sequence, angles) {
  if (state.activeEnterpriseTool === "sequence") return sequencePanel(context, sequence);
  if (state.activeEnterpriseTool === "inbox") return inboxPanel(context);
  if (state.activeEnterpriseTool === "libraries") return librariesPanel();
  if (state.activeEnterpriseTool === "insights") return analyticsWorkspace(context, angles);
  return batchPanel(context);
}

function batchPanel(context) {
  const errors = state.batchErrors.length ? `<div class="error-list">${state.batchErrors.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>` : "";
  const batchValue = state.batchInput || "";
  const canExport = state.batchRows.length > 0;
  return `
    <div class="batch-workspace">
      <article class="strategy-card">
        <strong>Batch CSV upload</strong>
        <p>Paste up to 100 prospects. Required columns: first_name, company, role, industry, signal.</p>
        <div class="batch-stepper">
          ${["Paste CSV", "Map columns", "Validate", "Generate", "Review"].map((step, index) => `<span class="${state.batchProgress && index < 5 ? "is-complete" : index === 0 ? "is-active" : ""}">${index + 1}. ${escapeHtml(step)}</span>`).join("")}
        </div>
        <div class="mapping-grid">
          ${["first_name", "company", "role", "industry", "signal"].map((column) => `<label class="field"><span>${escapeHtml(column)} column</span><input id="map-${column}" value="${escapeHtml(state.batchMapping[column] || column)}"></label>`).join("")}
        </div>
        <textarea id="batch-input" class="compact-textarea" placeholder="first_name,company,role,industry,signal">${escapeHtml(batchValue)}</textarea>
        ${errors}
        <div class="batch-progress" aria-label="Batch generation progress"><progress max="100" value="${state.batchProgress}">${state.batchProgress}%</progress></div>
        <p class="muted">${state.batchProgress ? `${state.batchRows.length} rows validated and ready for review.` : "Validate columns before generating."}</p>
        <div class="result-actions split-actions">
          <button class="button-secondary" type="button" data-load-sample-csv>Load sample CSV</button>
          <button type="button" data-generate-batch>Generate batch briefs</button>
          <button class="button-secondary" type="button" data-export-batch ${canExport ? "" : "disabled"}>Download export CSV</button>
        </div>
      </article>
      <div class="batch-table">
        ${batchRowsHtml(context)}
      </div>
    </div>
  `;
}

function sequencePanel(context, sequence) {
  return `
    <article class="strategy-card">
      <strong>Full sequence builder</strong>
      <div class="workspace-controls">
        <label class="field"><span>Sequence length</span><input id="sequence-length" type="number" min="2" max="8" value="${escapeHtml(state.sequenceSettings.length)}"></label>
        ${selectField("sequenceStart", "Start day", ["Monday", "Tuesday", "Wednesday", "Thursday"], state.sequenceSettings.startDay)}
        ${selectField("sequenceLogic", "Follow-up logic", ["Stop on reply", "Pause on open", "Continue until booked", "Manager review required"], state.sequenceSettings.logic || "Stop on reply")}
      </div>
    </article>
    <div class="stack">
      ${sequence.slice(0, Number(state.sequenceSettings.length || 4)).map(([day, title, copy], index) => `
        <article class="sequence-card">
          <span class="strength">${escapeHtml(day)}</span>
          <strong>${escapeHtml(title)}</strong>
          <small>Channel: ${escapeHtml(state.sequenceSettings.channels[index] || channels[index % channels.length])} / Rule: ${escapeHtml(state.sequenceSettings.logic || "Stop on reply")}</small>
          <pre>${escapeHtml(copy)}</pre>
        </article>
      `).join("")}
    </div>
  `;
}

function inboxPanel(context) {
  const groups = ["interested", "objection", "referral", "not-now", "unsubscribe"];
  return `
    <div class="inbox-workspace">
      <article class="strategy-card">
        <strong>Gmail / Outlook reply queue</strong>
        <p>Connectors preview: classify hot replies, objections, referrals, not-now replies, and unsubscribe requests.</p>
        <div class="setup-steps">
          <span>1. Connect Gmail or Outlook</span>
          <span>2. Pull new replies</span>
          <span>3. Review suggested response</span>
          <span>4. Write back to CRM/email</span>
        </div>
        <div class="result-actions">
          <button type="button" data-load-inbox>Load sample replies</button>
          <button class="button-secondary" type="button" data-generate-next-replies>Suggest next responses</button>
        </div>
      </article>
      <div class="inbox-queues">
        ${groups.map((group) => `<span>${escapeHtml(titleCase(group))}: ${state.inboxThreads.filter((thread) => thread.type === group && !thread.handled).length}</span>`).join("")}
      </div>
      <div class="inbox-list">
        ${state.inboxThreads.map((thread, index) => `
          <article class="${thread.handled ? "is-handled" : ""}">
            <div class="card-row"><span class="strength">${escapeHtml(titleCase(thread.type))}</span><span class="source-badge">${escapeHtml(thread.source || "Gmail")}</span></div>
            <strong>${escapeHtml(thread.from)}</strong>
            <p>${escapeHtml(thread.text)}</p>
            <small>${escapeHtml(thread.status || "Open")} / ${escapeHtml(thread.urgency || "Medium")} urgency / ${escapeHtml(thread.sentiment || "Neutral")} / ${escapeHtml(thread.confidence || 80)} confidence</small>
            <div class="suggested-reply">${escapeHtml(thread.reply || thread.next)}</div>
            <textarea class="compact-textarea suggested-editor" data-inbox-reply="${index}">${escapeHtml(thread.reply || inboxReply(thread, context))}</textarea>
            <p class="muted"><strong>Why:</strong> ${escapeHtml(thread.why || "The reply contains a clear next-step signal.")}</p>
            <div class="result-actions">
              <button class="button-secondary" type="button" data-draft-inbox="${index}">Draft reply</button>
              <button class="button-secondary" type="button" data-snooze-inbox="${index}">Snooze</button>
              <button class="button-secondary" type="button" data-copy-inbox="${index}">Copy reply</button>
              <button class="button-secondary" type="button" data-mark-handled="${index}">Mark handled</button>
            </div>
          </article>
        `).join("")}
      </div>
      <article class="strategy-card">
        <strong>Chrome sidebar preview</strong>
        <div class="sidebar-mock">
          <div class="mock-bar">TextTraits Sidebar</div>
          <div class="mock-card"><span class="source-badge">LinkedIn</span><strong>Pull from current page</strong><p>Extract name, role, company, and visible signal.</p></div>
          <div class="mock-card"><span class="source-badge">HubSpot</span><strong>Write back to CRM/email</strong><p>Preview-only until connected.</p></div>
        </div>
      </article>
    </div>
  `;
}

function inboxReply(thread, context) {
  return enterpriseCopy.inboxReply(thread, context);
}

function librariesPanel() {
  return `
    <div class="library-workspace">
      <article class="strategy-card">
        <strong>Team brand voice library</strong>
        <p>Approved tone, claims, forbidden phrases, and proof points keep drafts consistent across the team.</p>
        <div class="library-grid">
          ${brandVoiceProfiles.map((profile) => `
            <article>
              <strong>${escapeHtml(profile.name)}</strong>
              <p>Direct ${profile.direct} / Warm ${profile.warm} / Formal ${profile.formal}</p>
              ${tokens([...profile.claims, ...profile.proof])}
              <small>Avoid: ${escapeHtml(profile.forbidden.join(", "))}</small>
            </article>
          `).join("")}
        </div>
      </article>
      <article class="strategy-card">
        <strong>Contact and persona database</strong>
        <div class="library-grid">
          ${state.personaLibrary.map((persona) => `
            <article>
              <strong>${escapeHtml(persona.role)}</strong>
              <p>${escapeHtml(persona.industry)} / ${escapeHtml(persona.icp)}</p>
              <span class="strength">Objection: ${escapeHtml(persona.objection)}</span>
              <span class="strength">Trigger: ${escapeHtml(persona.trigger)}</span>
            </article>
          `).join("")}
        </div>
      </article>
      <article class="strategy-card">
        <strong>Learn from winners</strong>
        <p>Upload or paste replied-to emails. The workspace extracts reusable patterns for future variants.</p>
        <textarea id="winner-input" class="compact-textarea">${escapeHtml(state.winnerSamples.join("\n"))}</textarea>
        <div class="result-actions"><button type="button" data-learn-winners>Update winner patterns</button></div>
        <div class="feature-list">${winnerPatterns().map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>
      </article>
    </div>
  `;
}

function integrationSetupCards() {
  const steps = {
    HubSpot: ["Create OAuth app", "Add redirect URL", "Map contacts and deals"],
    Salesforce: ["Create connected app", "Enable API scopes", "Map leads and tasks"],
    Gmail: ["Create Google OAuth client", "Verify consent screen", "Enable draft creation"],
    Outlook: ["Create Azure app", "Add Mail scopes", "Enable reply queue"],
    Outreach: ["Create app", "Map prospects", "Map sequences"],
    Salesloft: ["Create app", "Map people", "Map cadences"],
    "Chrome Sidebar": ["Package extension", "Allow TextTraits origin", "Wire page extraction"],
  };
  return `
    <div class="integration-setup-grid">
      ${Object.entries(state.crmConnections).map(([name, status]) => `
        <article class="integration-setup-card">
          <div class="card-row"><strong>${escapeHtml(name)}</strong><span data-status="${escapeHtml(status)}">${escapeHtml(titleCase(status))}</span></div>
          <p class="tiny-copy muted">${status === "connected" ? "Connected in this workspace." : "Preview only until real credentials, scopes, and field mapping are configured."}</p>
          <ol>${(steps[name] || ["Create app", "Add credentials", "Map fields"]).map((step) => `<li>${escapeHtml(step)}</li>`).join("")}</ol>
          <button class="button-secondary" type="button" data-crm="${escapeHtml(name)}">${status === "connected" ? "Manage connection" : "View setup requirements"}</button>
        </article>
      `).join("")}
    </div>
  `;
}

function analyticsWorkspace(context, angles) {
  return `
    <div class="analytics-workspace">
      <article class="strategy-card">
        <strong>Reply outcome tracking</strong>
        ${outcomeGrid()}
      </article>
      <details class="analytics-section" open>
        <summary>Outcomes and exports</summary>
        <article class="strategy-card">
          <strong>Export history</strong>
          ${state.exportHistory.length ? `
            <div class="export-history">
              ${state.exportHistory.slice(0, 6).map((item) => `
                <span><strong>${escapeHtml(item.type)}</strong>${escapeHtml(item.project)} / ${escapeHtml(item.rows)} rows / ${escapeHtml(item.date)}</span>
              `).join("")}
            </div>
          ` : `<p class="muted">No exports yet. Export a campaign or batch to start the audit trail.</p>`}
        </article>
      </details>
      <details class="analytics-section" ${state.integrationSetupOpen ? "open" : ""}>
        <summary>Integrations and admin</summary>
        <article class="strategy-card">
          <strong>CRM import/export status</strong>
          <p>Integrations stay disabled until credentials, OAuth scopes, and field mappings are configured.</p>
          ${integrationSetupCards()}
        </article>
        <article class="strategy-card">
          <strong>Admin controls</strong>
          <p>Workspace settings, seats, permissions, SSO, API keys, approved assets, and audit logs are represented here for production rollout.</p>
          <div class="admin-grid">
            ${summaryItem("Workspace", state.adminSettings.workspaceName)}
            ${summaryItem("Seats", `${state.adminSettings.seats}`)}
            ${summaryItem("SSO", state.adminSettings.sso)}
            ${summaryItem("API key", state.adminSettings.apiKey)}
            ${summaryItem("Retention", state.adminSettings.retention)}
            ${summaryItem("Audit log", state.adminSettings.auditLog)}
          </div>
        </article>
      </details>
      <details class="analytics-section">
        <summary>Coaching and message quality</summary>
        <div class="detail-grid">
          <article class="strategy-card"><strong>Message angles ranked by fit</strong>${angles.map(([name, fit, copy]) => `<div class="metric-card"><span class="strength">${fit}% strength</span><strong>${escapeHtml(name)}</strong><p>${escapeHtml(copy)}</p><p><strong>Why this angle:</strong> It maps directly to the prospect's stated operating concern.</p></div>`).join("")}</article>
          <article class="strategy-card"><strong>Deliverability checks</strong>${scoreGrid([["Length", 84], ["Links", 96], ["Spam phrasing", 88], ["Personalization", 91]])}<p>Checks include length, links, spammy phrasing, personalization density, merge fields, and unsubscribe token support.</p></article>
          <article class="strategy-card"><strong>Words to mirror</strong>${tokens(["cleaner signal", "manager visibility", "forecast risk", "operating rhythm", context.pain])}</article>
          <article class="strategy-card"><strong>Words to avoid</strong>${tokens(["game-changing", "revolutionary", "just checking in", "circle back", "synergy"])}</article>
          <article class="strategy-card"><strong>Team learning system</strong><p>Winner patterns now influence review guidance and future draft variants.</p><div class="feature-list">${winnerPatterns().map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div></article>
          <article class="strategy-card"><strong>Manager coaching dashboard</strong>${scoreGrid([["Vague CTA", state.feedbackMemory.tooVague + 4], ["Missing proof", 3], ["Too generic", state.feedbackMemory.moreLikeMe + 2], ["Too long", state.feedbackMemory.tooLong + 5]])}<p>Managers can see where drafts need coaching before they reach CRM export.</p></article>
        </div>
      </details>
    </div>
  `;
}

function renderEnterpriseTab(data, context, profile, variants, angles, sequence) {
  if (state.activeEnterpriseTab === "dashboard") return campaignHome(context, angles);
  if (state.activeEnterpriseTab === "drafts") return draftsWorkspace(context, variants);
  if (state.activeEnterpriseTab === "tools") return toolsWorkspace(context, sequence, angles);
  if (state.activeEnterpriseTab === "analytics") return analyticsWorkspace(context, angles);
  if (state.activeEnterpriseTab === "workspace") {
    const campaigns = filteredCampaigns();
    return `
      <div class="workspace-command">
        <article class="strategy-card">
          <strong>Saved workspaces</strong>
          <p>Folders, status filters, search, and CRM export controls turn one-off generation into a campaign queue.</p>
          <div class="workspace-controls">
            <label class="field"><span>Search</span><input id="workspace-search" value="${escapeHtml(state.workspaceSearch)}" placeholder="Search campaigns, folders, status"></label>
            ${selectField("workspaceFolder", "Folder", ["All", ...uniqueValues(state.savedCampaigns, "folder")], state.workspaceFolder)}
            ${selectField("workspaceStatus", "Status", ["All", ...uniqueValues(state.savedCampaigns, "status")], state.workspaceStatus)}
          </div>
        </article>
        <div class="campaign-table">
          ${campaigns.map((campaign) => `
            <article>
              <strong>${escapeHtml(campaign.name)}</strong>
              <span>${escapeHtml(campaign.folder)} / ${escapeHtml(campaign.status)} / ${escapeHtml(campaign.prospects || 1)} prospects</span>
              <div class="result-actions">
                <button class="button-secondary" data-load-campaign="${escapeHtml(campaign.name)}">Load</button>
                <button class="button-secondary" data-status-campaign="${escapeHtml(campaign.name)}">Mark reviewed</button>
              </div>
            </article>
          `).join("")}
        </div>
        <article class="strategy-card">
          <strong>CRM import/export</strong>
          <div class="crm-grid">
            ${Object.entries(state.crmConnections).map(([name, status]) => `
              <button class="crm-card" type="button" data-crm="${escapeHtml(name)}" ${["preview only", "disabled"].includes(status) ? "disabled aria-disabled=\"true\"" : ""}>
                <strong>${escapeHtml(name)}</strong>
                <span data-status="${escapeHtml(status)}">${escapeHtml(titleCase(status))}</span>
              </button>
            `).join("")}
          </div>
        </article>
        <article class="strategy-card">
          <strong>Reply outcome tracking</strong>
          ${outcomeGrid()}
        </article>
      </div>
    `;
  }
  if (state.activeEnterpriseTab === "batch") {
    return `
      <div class="batch-workspace">
        <article class="strategy-card">
          <strong>Batch CSV upload</strong>
          <p>Paste CSV rows for up to 100 prospects. TextTraits creates a brief, subject, sequence status, and export row for each prospect.</p>
          <textarea id="batch-input" class="compact-textarea" placeholder="first_name,company,role,industry,signal">${escapeHtml(state.batchInput || sampleCsv)}</textarea>
          <div class="result-actions">
            <button type="button" data-load-sample-csv>Load sample CSV</button>
            <button class="button-secondary" type="button" data-generate-batch>Generate batch briefs</button>
            <button class="button-secondary" type="button" data-export-batch>Export batch CSV</button>
          </div>
        </article>
        <div class="batch-table">
          ${batchRowsHtml(context)}
        </div>
      </div>
    `;
  }
  if (state.activeEnterpriseTab === "inbox") {
    return `
      <div class="inbox-workspace">
        <article class="strategy-card">
          <strong>Gmail / Outlook inbox mode</strong>
          <p>Analyze replies, classify intent, and recommend the next response. This local preview uses sample threads until mail connectors are attached.</p>
          <div class="result-actions">
            <button type="button" data-load-inbox>Load sample replies</button>
            <button class="button-secondary" type="button" data-generate-next-replies>Suggest next responses</button>
          </div>
        </article>
        <div class="inbox-list">
          ${state.inboxThreads.map((thread, index) => `
            <article>
              <span class="strength">${escapeHtml(titleCase(thread.type))}</span>
              <strong>${escapeHtml(thread.from)}</strong>
              <p>${escapeHtml(thread.text)}</p>
              <div class="suggested-reply">${escapeHtml(thread.reply || thread.next)}</div>
              <button class="button-secondary" type="button" data-copy-inbox="${index}">Copy next response</button>
            </article>
          `).join("")}
        </div>
        <article class="strategy-card">
          <strong>Chrome sidebar preview</strong>
          <div class="sidebar-grid">
            ${["LinkedIn", "Gmail", "HubSpot", "Company website"].map((surface) => `<article><strong>${surface}</strong><p>Analyze visible context, pull prospect fields, and write approved copy back into the workflow.</p></article>`).join("")}
          </div>
        </article>
      </div>
    `;
  }
  if (state.activeEnterpriseTab === "libraries") {
    return `
      <div class="library-workspace">
        <article class="strategy-card">
          <strong>Team brand voice library</strong>
          <p>Approved tone, claims, forbidden phrases, and proof points keep drafts consistent across the team.</p>
          <div class="library-grid">
            ${brandVoiceProfiles.map((profile) => `
              <article>
                <strong>${escapeHtml(profile.name)}</strong>
                <p>Direct ${profile.direct} / Warm ${profile.warm} / Formal ${profile.formal}</p>
                ${tokens([...profile.claims, ...profile.proof])}
                <small>Avoid: ${escapeHtml(profile.forbidden.join(", "))}</small>
              </article>
            `).join("")}
          </div>
        </article>
        <article class="strategy-card">
          <strong>Contact and persona database</strong>
          <div class="library-grid">
            ${state.personaLibrary.map((persona) => `
              <article>
                <strong>${escapeHtml(persona.role)}</strong>
                <p>${escapeHtml(persona.industry)} / ${escapeHtml(persona.icp)}</p>
                <span class="strength">Objection: ${escapeHtml(persona.objection)}</span>
                <span class="strength">Trigger: ${escapeHtml(persona.trigger)}</span>
              </article>
            `).join("")}
          </div>
        </article>
        <article class="strategy-card">
          <strong>Learn from winners</strong>
          <p>Upload or paste replied-to emails. The workspace extracts reusable patterns for future variants.</p>
          <textarea id="winner-input" class="compact-textarea">${escapeHtml(state.winnerSamples.join("\n"))}</textarea>
          <div class="result-actions">
            <button type="button" data-learn-winners>Update winner patterns</button>
          </div>
          <div class="feature-list">${winnerPatterns().map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>
        </article>
      </div>
    `;
  }
  if (state.activeEnterpriseTab === "drafts") {
    const best = bestDraft();
    return `
      <article class="strategy-card">
        <strong>Generated email draft variants</strong>
        <p>Variant ${escapeHtml(best?.key || "A")} is recommended based on clarity, specificity, CTA strength, and skimmability. Select a variant to open it in the editor.</p>
      </article>
      <div class="variant-list">
        ${variants.map((draft) => variantRow(draft, best))}
      </div>
    `;
  }
  if (state.activeEnterpriseTab === "editor") {
    const draft = selectedDraft();
    return `
      <div class="editor-workspace">
        <aside class="variant-sidebar">
          <strong>Variants</strong>
          ${variants.map((item) => `
            <button type="button" data-select-variant="${item.key}" aria-pressed="${String(item.key === draft.key)}">
              <span>Variant ${escapeHtml(item.key)}</span>
              <small>${escapeHtml(item.name)} / ${averageScore(item)} score</small>
            </button>
          `).join("")}
          <div class="merge-field-box">
            <strong>Merge fields</strong>
            ${["{{first_name}}", "{{company}}", "{{role}}", "{{unsubscribe_link}}"].map((field) => `<button class="button-secondary" type="button" data-insert-field="${escapeHtml(field)}">${escapeHtml(field)}</button>`).join("")}
          </div>
        </aside>
        <section class="email-editor">
          <div class="editor-header">
            <label class="field"><span>Variant name</span><input data-draft-field="name" data-variant="${draft.key}" value="${escapeHtml(draft.name)}"></label>
            <span class="strength">Selected variant ${escapeHtml(draft.key)}</span>
          </div>
          <label class="field"><span>Subject line</span><input data-draft-field="subject" data-variant="${draft.key}" value="${escapeHtml(draft.subject)}"></label>
          <label class="field"><span>Email body</span><textarea class="draft-editor" data-draft-field="body" data-variant="${draft.key}">${escapeHtml(draft.body)}</textarea></label>
          <div class="editor-actions">
            ${transformButtons(draft.key)}
          </div>
          <div class="recipient-preview">
            <div class="enterprise-field-grid">
              <label class="field"><span>First name</span><input data-recipient-field="firstName" value="${escapeHtml(state.recipient.firstName)}"></label>
              <label class="field"><span>Company</span><input data-recipient-field="company" value="${escapeHtml(state.recipient.company)}"></label>
              <label class="field"><span>Role</span><input data-recipient-field="role" value="${escapeHtml(state.recipient.role)}"></label>
            </div>
            <strong>Resolved preview</strong>
            <pre data-resolved-preview>${escapeHtml(resolveMergeFields(draftText(draft)))}</pre>
          </div>
          <details class="history-panel">
            <summary>Draft history and version compare</summary>
            <div class="feature-list">${draft.history.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>
          </details>
        </section>
      </div>
    `;
  }
  if (state.activeEnterpriseTab === "sequence") {
    return `
      <article class="strategy-card">
        <strong>Full sequence builder</strong>
        <div class="workspace-controls">
          <label class="field"><span>Sequence length</span><input id="sequence-length" type="number" min="2" max="8" value="${escapeHtml(state.sequenceSettings.length)}"></label>
          ${selectField("sequenceStart", "Start day", ["Monday", "Tuesday", "Wednesday", "Thursday"], state.sequenceSettings.startDay)}
          ${selectField("sequenceLogic", "Follow-up logic", ["Stop on reply", "Pause on open", "Continue until booked", "Manager review required"], state.sequenceSettings.logic || "Stop on reply")}
        </div>
      </article>
      <div class="channel-grid">
        ${channels.map((channel) => `<article class="channel-card"><strong>${escapeHtml(channel)}</strong><p>${escapeHtml(channelPreview(channel, context))}</p></article>`).join("")}
      </div>
      <div class="stack">
        <article class="strategy-card"><strong>Sequence calendar</strong><p>Follow-up timing, channel choice, and ready-to-edit step copy are staged below.</p></article>
        ${sequence.slice(0, Number(state.sequenceSettings.length || 4)).map(([day, title, copy], index) => `
          <article class="sequence-card">
            <span class="strength">${escapeHtml(day)}</span>
            <strong>${escapeHtml(title)}</strong>
            <small>Channel: ${escapeHtml(state.sequenceSettings.channels[index] || channels[index % channels.length])} / Rule: ${escapeHtml(state.sequenceSettings.logic || "Stop on reply")}</small>
            <pre>${escapeHtml(copy)}</pre>
          </article>
        `).join("")}
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
        <article class="strategy-card"><strong>Outcome tracking</strong><p>Track generated, copied, exported, opened, replied, and booked outcomes by campaign.</p></article>
        <article class="strategy-card"><strong>Learn from winners</strong><p>Accepted or replied emails can seed future tone, proof, and objection patterns.</p></article>
        <article class="strategy-card"><strong>Manager coaching</strong><p>Rep-level patterns summarize where drafts need proof, specificity, or a clearer CTA.</p></article>
        <article class="strategy-card"><strong>Chrome sidebar concept</strong><p>Future browser sidebar can pull CRM/email context and write back approved copy.</p></article>
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
        <article class="strategy-card"><strong>Exports and integrations</strong><div class="integration-list"><span data-status="connected">CSV connected</span><span data-status="soon">HubSpot coming soon</span><span data-status="soon">Salesforce coming soon</span><span data-status="disabled">Outreach disabled</span><span data-status="disabled">Salesloft disabled</span></div></article>
        <article class="strategy-card"><strong>Merge fields manager</strong>${tokens(["{{first_name}}", "{{company}}", "{{recent_signal}}", "{{pipeline_priority}}", "{{unsubscribe_link}}"])}</article>
        <article class="strategy-card"><strong>Admin controls</strong><p>Approved claims, proof assets, unsubscribe tokens, API keys, seats, and prompt presets are represented in this workspace setup.</p></article>
      </div>
    </div>
  `;
}

function variantRow(draft, best) {
  return `
    <article class="variant-row ${draft.key === best?.key ? "is-best" : ""}">
      <div>
        <span class="strength">${draft.key === best?.key ? "Best variant" : `Variant ${escapeHtml(draft.key)}`}</span>
        <label class="field compact-field"><span>Name</span><input data-draft-field="name" data-variant="${draft.key}" value="${escapeHtml(draft.name)}"></label>
      </div>
      <label class="field"><span>Subject</span><input data-draft-field="subject" data-variant="${draft.key}" value="${escapeHtml(draft.subject)}"></label>
      <div class="score-strip">
        ${Object.entries(draft.scores).map(([label, value]) => `<span><strong>${value}</strong>${escapeHtml(titleCase(label))}</span>`).join("")}
      </div>
      <p class="muted">${escapeHtml(draft.note)}</p>
      <div class="result-actions">
        <button type="button" data-select-variant="${draft.key}">Open editor</button>
        <button class="button-secondary" data-copy-draft="${escapeHtml(draft.key)}">Copy</button>
      </div>
    </article>
  `;
}

function transformButtons(key) {
  return [
    ["shorter", "Make shorter"],
    ["executive", "Make executive"],
    ["casual", "Make casual"],
    ["specific", "Make specific"],
    ["proof", "Add proof point"],
    ["plain", "Remove buzzwords"],
    ["compliance", "Compliance-safe"],
    ["feedback", "Generate next variant"],
  ].map(([id, label]) => `<button class="button-secondary" type="button" data-transform="${id}" data-variant="${key}">${label}</button>`).join("");
}

function uniqueValues(items, key) {
  return [...new Set(items.map((item) => item[key]).filter(Boolean))];
}

function filteredCampaigns() {
  const query = state.workspaceSearch.toLowerCase();
  return state.savedCampaigns.filter((campaign) => {
    const text = `${campaign.name} ${campaign.folder} ${campaign.status}`.toLowerCase();
    const folderOk = state.workspaceFolder === "All" || campaign.folder === state.workspaceFolder;
    const statusOk = state.workspaceStatus === "All" || campaign.status === state.workspaceStatus;
    return folderOk && statusOk && (!query || text.includes(query));
  });
}

function outcomeGrid() {
  return `<div class="outcome-grid">${Object.entries(state.outcomeStats).map(([label, value]) => `
    <button class="outcome-card" type="button" data-outcome="${escapeHtml(label)}">
      <strong>${escapeHtml(value)}</strong>
      <span>${escapeHtml(titleCase(label))}</span>
    </button>
  `).join("")}</div>`;
}

function parseCsv(text, mapping = state.batchMapping) {
  const lines = text.trim().split(/\r?\n/).filter(Boolean);
  state.batchErrors = [];
  if (lines.length < 2) {
    state.batchErrors = ["Add a header row and at least one prospect row."];
    return [];
  }
  const parsedHeader = parseCsvLine(lines[0]);
  const headers = parsedHeader.cells.map((header) => header.trim().replaceAll('"', ""));
  if (parsedHeader.malformed) state.batchErrors.push("Header row has an unclosed quote.");
  const required = ["first_name", "company", "role", "industry", "signal"];
  const missing = required.filter((fieldName) => !headers.includes(mapping[fieldName] || fieldName));
  if (missing.length) state.batchErrors.push(`Missing mapped columns: ${missing.map((fieldName) => `${fieldName} -> ${mapping[fieldName] || fieldName}`).join(", ")}.`);
  const seen = new Set();
  return lines.slice(1, 101).map((line, index) => {
    const parsed = parseCsvLine(line);
    const cells = parsed.cells;
    if (parsed.malformed) state.batchErrors.push(`Row ${index + 2} has an unclosed quote.`);
    if (cells.length !== headers.length) state.batchErrors.push(`Row ${index + 2} has ${cells.length} cells but the header has ${headers.length}.`);
    const raw = {};
    headers.forEach((header, cellIndex) => {
      raw[header] = String(cells[cellIndex] || "").trim().replace(/^"|"$/g, "");
    });
    const row = {};
    required.forEach((fieldName) => {
      row[fieldName] = raw[mapping[fieldName] || fieldName] || "";
    });
    const duplicateKey = `${row.first_name || ""}-${row.company || ""}`.toLowerCase();
    if (seen.has(duplicateKey)) state.batchErrors.push(`Duplicate prospect detected: ${row.first_name || "Unknown"} at ${row.company || "Unknown company"}.`);
    seen.add(duplicateKey);
    if (!row.signal || words(row.signal).length < 4) state.batchErrors.push(`Missing personalization signal for row ${index + 2}.`);
    const statuses = ["Generated", "Needs review", "Approved", "Exported", "Queued"];
    return {
      id: index + 1,
      first_name: row.first_name || `Prospect ${index + 1}`,
      company: row.company || "Unknown company",
      role: row.role || "Buyer",
      industry: row.industry || "SaaS",
      signal: row.signal || "Needs clearer pipeline signal",
      status: statuses[index % statuses.length],
      subject: `Idea for ${row.company || "your team"}`,
      next: "Review draft and export to CRM",
    };
  }).filter((row) => row.company !== "Unknown company" || !missing.length);
}

function batchRowsHtml(context) {
  if (!state.batchRows.length) {
    return `<article class="empty-mini"><strong>No batch rows yet</strong><p>Load the sample CSV or paste your own prospect list to generate up to 100 briefs.</p></article>`;
  }
  return state.batchRows.map((row) => `
    <article>
      <span class="strength">${escapeHtml(row.status)}</span>
      <strong>${escapeHtml(row.first_name)} at ${escapeHtml(row.company)}</strong>
      <p>${escapeHtml(row.role)} / ${escapeHtml(row.industry)} / ${escapeHtml(row.signal)}</p>
      <div class="row-progress">
        ${["Queued", "Generated", "Needs review", "Approved", "Exported"].map((step) => `<span class="${step === row.status ? "is-current" : ""}">${escapeHtml(step)}</span>`).join("")}
      </div>
      <div class="mini-brief">Subject: ${escapeHtml(row.subject)}<br>Angle: ${escapeHtml(context.pain || "pipeline quality")} with ${escapeHtml(context.proof || "proof point")}.</div>
      <div class="result-actions">
        <button class="button-secondary" type="button" data-copy-row="${escapeHtml(row.id)}">Copy brief</button>
        <button class="button-secondary" type="button" data-review-row="${escapeHtml(row.id)}">Review</button>
        <button class="button-secondary" type="button" data-export-row="${escapeHtml(row.id)}">Export row</button>
      </div>
    </article>
  `).join("");
}

function batchCsv() {
  const rows = [["first_name", "company", "role", "industry", "status", "subject", "next_step"]];
  state.batchRows.forEach((row) => rows.push([row.first_name, row.company, row.role, row.industry, row.status, row.subject, row.next]));
  return rows.map((row) => row.map(csvCell).join(",")).join("\n");
}

function winnerPatterns() {
  const text = state.winnerSamples.join(" ").toLowerCase();
  const patterns = ["Short opener", "Specific pain", "Proof before product", "Direct CTA"];
  if (text.includes("forecast")) patterns.push("Forecast-risk language");
  if (text.includes("handoff")) patterns.push("Handoff framing");
  if (text.includes("dashboard")) patterns.push("Avoid dashboard fatigue");
  return patterns;
}

function tokens(items) {
  return `<div class="token-list">${items.map((item) => `<span class="token">${escapeHtml(item)}</span>`).join("")}</div>`;
}

function scoreGrid(items) {
  return `<div class="score-grid">${items.map(([label, value]) => `<div class="score-card"><strong>${value}</strong><span>${escapeHtml(label)}</span></div>`).join("")}</div>`;
}

function scoreLabel(label) {
  const map = {cta: "CTA strength", skimmability: "Skimmability", clarity: "Clarity", specificity: "Specificity"};
  return map[label] || titleCase(label);
}

function resolveMergeFields(text) {
  return text
    .replaceAll("{{first_name}}", state.recipient.firstName || "Maya")
    .replaceAll("{{company}}", state.recipient.company || "Acme Revenue")
    .replaceAll("{{role}}", state.recipient.role || "VP Revenue")
    .replaceAll("{{recent_signal}}", state.enterpriseContext?.pain || "forecast risk")
    .replaceAll("{{pipeline_priority}}", state.enterpriseContext?.trigger || "pipeline inspection")
    .replaceAll("{{unsubscribe_link}}", "unsubscribe.example");
}

function validateMergeFields(variants) {
  const text = variants.map((draft) => draftText(draft)).join("\n");
  const open = (text.match(/\{\{/g) || []).length;
  const close = (text.match(/\}\}/g) || []).length;
  if (open !== close) return {ok: false, message: "Merge field braces do not match."};
  if (!text.includes("{{first_name}}")) return {ok: false, message: "Add {{first_name}} before export."};
  return {ok: true, message: "Merge fields validated."};
}

function insertMergeField(field) {
  const draft = selectedDraft();
  if (!draft) return;
  draft.body = `${draft.body.trim()}\n\n${field}`;
  draft.history.push(`Inserted ${field}`);
  state.lastActionNote = `Inserted ${field} in Variant ${draft.key}.`;
  renderEnterpriseResult(state.latestData);
}

function transformDraft(action, key, context) {
  const draft = state.enterpriseDrafts.find((item) => item.key === key);
  if (!draft) return;
  state.selectedVariant = key;
  const before = draft.body;
  const clean = draft.body.replace(/\s+/g, " ").trim();
  if (action === "shorter") {
    draft.body = clean.split(". ").slice(0, 3).join(". ").replace(/\.$/, "") + ".";
    state.lastDraftChange = "Trimmed the setup and kept the clearest CTA.";
  } else if (action === "executive") {
    draft.body = `The business issue seems clear: ${context.pain}. ${context.company} helps ${context.segment} teams turn that into earlier visibility, cleaner manager coaching, and fewer forecast surprises.\n\n${ctaText(context)}`;
    state.lastDraftChange = "Reframed the draft around business impact and executive-level brevity.";
  } else if (action === "casual") {
    draft.body = `I noticed your point about ${context.pain}. That is exactly where teams often want less reporting noise and a clearer view of what is moving.\n\nOpen to a quick look at how ${context.company} approaches it?`;
    state.lastDraftChange = "Made the language more conversational and easier to reply to.";
  } else if (action === "specific") {
    draft.body = `${clean}\n\nThe specific angle I would test first: ${context.trigger} for ${context.icp}, using ${context.proof} as the proof point.`;
    state.lastDraftChange = "Added the trigger, ICP, and proof point so the email feels less generic.";
  } else if (action === "proof") {
    draft.body = `${clean}\n\nProof point to consider: ${context.proof}.`;
    state.lastDraftChange = "Added a concrete proof point for review before export.";
  } else if (action === "plain") {
    draft.body = clean
      .replaceAll("operating rhythm", "weekly workflow")
      .replaceAll("signal", "evidence")
      .replaceAll("leverage", "use")
      .replaceAll("motion", "process");
    state.lastDraftChange = "Removed salesy wording and swapped in plainer language.";
  } else if (action === "compliance") {
    draft.body = `${clean}\n\nCompliance note: includes one clear business reason for contact, avoids exaggerated claims, and keeps the unsubscribe token available as {{unsubscribe_link}}.`;
    state.lastDraftChange = "Added a compliance-safe note and unsubscribe token placeholder.";
  } else if (action === "feedback") {
    const nextKey = String.fromCharCode(65 + state.enterpriseDrafts.length);
    const nextBody = `Based on the strongest current draft, I would test a more specific version:\n\n${clean}\n\nWould a short comparison against your current ${context.competitor} be useful?`;
    state.enterpriseDrafts.push({
      ...draft,
      key: nextKey,
      name: "Feedback variant",
      subject: `Tighter idea for ${context.pain}`,
      body: nextBody,
      scores: {...(draft.scores || {clarity: 88, specificity: 88, cta: 86, skimmability: 88})},
      status: "Draft",
      owner: draft.owner || "Unassigned",
      due: draft.due || "This week",
      note: "Generated from your feedback so the team can compare one more option.",
      history: ["Generated from feedback"],
    });
    state.selectedVariant = nextKey;
    state.lastDraftChange = `Created Variant ${nextKey} from the current draft and team feedback.`;
    recordVersion("Enterprise draft", "Generated next variant", before, nextBody, `Variant ${nextKey} created from feedback`);
    persistWorkspace();
    return;
  }
  draft.history.push(`${titleCase(action)} transform`);
  recordVersion("Enterprise draft", `${titleCase(action)} transform`, before, draft.body, `Variant ${key} updated`);
  persistWorkspace();
}

function saveCurrentCampaign(context) {
  const campaign = {
    name: context.project,
    folder: context.folder,
    status: "Saved workspace",
    updated: new Date().toLocaleDateString([], {month: "short", day: "numeric"}),
    owner: "Revenue team",
    due: "This week",
    prospects: state.batchRows.length || 1,
    exports: state.exportHistory.filter((item) => item.project === context.project).length,
    drafts: state.enterpriseDrafts.map((draft) => ({
      key: draft.key,
      name: draft.name,
      subject: draft.subject,
      status: draft.status || "Draft",
      score: averageScore(draft),
    })),
    lastAction: state.lastActionNote || "Ready for review",
  };
  state.savedCampaigns = [campaign, ...state.savedCampaigns.filter((item) => item.name !== campaign.name)].slice(0, 8);
  state.campaignSaved = true;
  state.lastActionNote = `${context.project} saved to workspace. Next: approve or export drafts.`;
  persistWorkspace();
}

function recordExport(type, project, rows) {
  state.exportHistory = [{
    type,
    project,
    rows,
    date: new Date().toLocaleString([], {month: "short", day: "numeric", hour: "2-digit", minute: "2-digit"}),
  }, ...state.exportHistory].slice(0, 30);
}

function updateVisibleActionNote() {
  const note = els.outputPanel?.querySelector(".next-action");
  if (note && state.lastActionNote) note.textContent = state.lastActionNote;
}

function showToast(anchor, message) {
  els.announcer.textContent = message;
  (els.toastStack || document.body).querySelectorAll?.(".inline-toast").forEach((item) => item.remove());
  const toast = document.createElement("span");
  toast.className = "inline-toast";
  toast.textContent = message;
  (els.toastStack || document.body).appendChild(toast);
  setTimeout(() => toast.remove(), 1800);
}

function channelPreview(channel, context) {
  if (channel === "LinkedIn") return `Saw your note on ${context.pain}. I have a short idea for making that easier to see before forecast review. Worth sending?`;
  if (channel === "SMS") return `${context.firstName || "{{first_name}}"}, quick idea on ${context.pain}. Want me to send the 3-sentence version?`;
  if (channel === "Call opener") return `Hi ${context.firstName || "{{first_name}}"}, I saw your team is focused on ${context.pain}. The reason for my call is simple: we help revenue teams spot risk earlier without adding another reporting loop.`;
  return buildEmailVariant(context, {}, "A");
}

function enterpriseBriefText(context, variants, angles, sequence) {
  return [
    `Enterprise brief for ${context.role}`,
    `Best angle: ${angles[0][0]} (${angles[0][1]}% fit)`,
    `CTA: ${ctaText(context)}`,
    "",
    variants.map((draft) => `Variant ${draft.key}: ${draft.name}\\n${draftText(draft)}`).join("\\n\\n"),
    "",
    sequence.map(([day, title, copy]) => `${day}: ${title} - ${copy}`).join("\\n"),
  ].join("\\n");
}

function makeCsv(context, variants) {
  const rows = [["variant", "name", "subject", "body", "role", "industry", "goal", "score"]];
  variants.forEach((draft) => {
    rows.push([draft.key, draft.name, draft.subject, draft.body, context.role, context.industry, context.goal, averageScore(draft)]);
  });
  return rows.map((row) => row.map(csvCell).join(",")).join("\\n");
}

function downloadCsv(csv) {
  downloadText("texttraits-enterprise-campaign.csv", csv, "text/csv");
}

function downloadText(filename, text, type = "text/plain") {
  const blob = new Blob([text], {type});
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
  URL.revokeObjectURL(link.href);
}

async function copyTextFromButton(button, text, successMessage) {
  try {
    if (!navigator.clipboard?.writeText) throw new Error("Clipboard unavailable");
    await navigator.clipboard.writeText(text);
    trackEvent("copy", {message: successMessage});
    showToast(button, successMessage);
    return true;
  } catch (error) {
    showToast(button, "Copy is unavailable in this browser. Select the text and copy it manually.");
    return false;
  }
}

function bindCopy(selector, text, message) {
  const buttons = els.outputPanel.querySelectorAll(selector);
  if (!buttons.length) return;
  buttons.forEach((button) => {
    button.addEventListener("click", async () => {
      await copyTextFromButton(button, text, message);
    });
  });
}

function wireInput() {
  if (state.mode === "explorer") {
    if (state.latestData) {
      document.querySelector("#clear-explorer")?.addEventListener("click", () => {
        state.latestText = "";
        state.compareText = "";
        state.explorerReadingName = "";
        state.explorerSavedMessage = "";
        state.latestData = null;
        state.explorerPromptTitle = "";
        state.explorerPromptText = "";
        state.explorerPromptSource = "";
        persistWorkspace();
        render();
      });
      return;
    }
    const input = document.querySelector("#explorer-text");
    const compare = document.querySelector("#compare-text");
    const readingName = document.querySelector("#reading-name");
    input.addEventListener("input", () => {
      state.latestText = input.value;
      updateInputStats("explorer", input.value);
      persistWorkspace();
    });
    compare.addEventListener("input", () => {
      state.compareText = compare.value;
    });
    readingName?.addEventListener("input", () => {
      state.explorerReadingName = readingName.value;
      persistWorkspace();
    });
    document.querySelector("#field-explorerFolder")?.addEventListener("change", (event) => {
      state.explorerFolder = event.target.value;
      persistWorkspace();
    });
    document.querySelector("#field-explorerWritingGoal")?.addEventListener("change", (event) => {
      state.explorerWritingGoal = event.target.value;
      persistWorkspace();
    });
    document.querySelectorAll("[data-use-daily-prompt]").forEach((button) => {
      button.addEventListener("click", () => {
        state.latestText = input.value;
        selectExplorerPrompt({
          title: dailyPromptTitle(),
          text: dailyPromptInstruction(),
          source: "Today's prompt",
        });
      });
    });
    document.querySelector("[data-clear-explorer-prompt]")?.addEventListener("click", () => {
      state.latestText = input.value;
      state.explorerPromptTitle = "";
      state.explorerPromptText = "";
      state.explorerPromptSource = "";
      persistWorkspace();
      render();
      requestAnimationFrame(() => document.querySelector("#explorer-text")?.focus());
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
      state.explorerReadingName = "";
      state.explorerSavedMessage = "";
      state.latestData = null;
      state.explorerPromptTitle = "";
      state.explorerPromptText = "";
      state.explorerPromptSource = "";
      persistWorkspace();
      render();
    });
    document.querySelector("#copy-explorer-input").addEventListener("click", async () => {
      await copyTextFromButton(document.querySelector("#copy-explorer-input"), input.value, "Input copied.");
    });
    updateInputStats("explorer", input.value);
  } else {
    if (state.latestData && state.enterpriseInputsCollapsed) {
      document.querySelector("#edit-enterprise-inputs")?.addEventListener("click", () => {
        state.enterpriseInputsCollapsed = false;
        render();
      });
      return;
    }
    const input = document.querySelector("#enterprise-text");
    input.addEventListener("input", () => {
      state.latestText = input.value;
      updateInputStats("enterprise", input.value);
      persistWorkspace();
    });
    document.querySelector("#generate-enterprise").addEventListener("click", () => runAnalysis(input.value));
    document.querySelector("#clear-enterprise").addEventListener("click", () => {
      state.latestText = "";
      state.latestData = null;
      state.enterpriseDrafts = [];
      state.campaignSaved = false;
      state.enterpriseInputsCollapsed = false;
      state.enterpriseSetupOpen = false;
      persistWorkspace();
      render();
    });
    document.querySelectorAll('input[type="range"]').forEach((range) => {
      const value = range.nextElementSibling;
      range.addEventListener("input", () => value.textContent = range.value);
    });
    document.querySelectorAll("[id^='field-']").forEach((field) => {
      field.addEventListener("input", () => {
        state.enterpriseContext = enterpriseContext();
        state.recipient = {
          firstName: state.enterpriseContext.firstName,
          company: state.enterpriseContext.recipientCompany,
          role: state.enterpriseContext.recipientRole,
        };
        persistWorkspace();
      });
      field.addEventListener("change", () => {
        const ctx = enterpriseContext();
        state.enterpriseContext = ctx;
        if (field.id === "field-brandVoice") applyBrandVoice(ctx.brandVoice);
        persistWorkspace();
      });
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
      state.enterpriseDrafts = [];
      if (state.mode === "explorer") state.explorerReadingName = sample.label;
      if (state.mode === "enterprise" && sample.context) {
        state.enterpriseContext = {...enterpriseContext(), ...sample.context};
        Object.entries(sample.context).forEach(([key, value]) => {
          const field = document.querySelector(`#field-${key}`);
          if (field) field.value = value;
        });
      }
      updateInputStats(state.mode, sample.text);
      if (state.mode === "enterprise") renderEnterpriseEmpty();
      else renderExplorerEmpty();
      persistWorkspace();
      target.focus();
    });
  });

  document.querySelectorAll("[data-prompt-index]").forEach((button) => {
    button.addEventListener("click", () => {
      const prompt = consumerPromptLibrary[Number(button.dataset.promptIndex)];
      const input = document.querySelector("#explorer-text");
      if (!prompt || !input) return;
      state.latestText = input.value;
      state.explorerWritingGoal = prompt.goal.includes("clear") ? "Make this clearer" : prompt.goal.includes("accountable") ? "Sound less harsh" : "Make this warmer";
      selectExplorerPrompt({
        title: prompt.name,
        text: prompt.prompt,
        source: "Prompt library",
      });
    });
  });

  document.querySelector("[data-save-onboarding]")?.addEventListener("click", (event) => {
    const mode = event.currentTarget.dataset.saveOnboarding;
    if (mode === "enterprise") {
      state.onboarding.enterpriseGoal = document.querySelector("#field-onboardingEnterpriseGoal")?.value || state.onboarding.enterpriseGoal;
      state.onboarding.teamSize = document.querySelector("#field-onboardingTeamSize")?.value || state.onboarding.teamSize;
    } else {
      state.onboarding.explorerGoal = document.querySelector("#field-onboardingExplorerGoal")?.value || state.onboarding.explorerGoal;
      state.onboarding.plan = document.querySelector("#field-onboardingPlan")?.value || "7-day plan";
      state.explorerWritingGoal = state.onboarding.explorerGoal.includes("Warmer") ? "Make this warmer" : state.onboarding.explorerGoal.includes("Hard") ? "Sound less harsh" : "Make this clearer";
    }
    state.onboarding.complete = true;
    persistWorkspace();
    render();
  });
  document.querySelector("[data-skip-onboarding]")?.addEventListener("click", () => {
    state.onboarding.complete = true;
    persistWorkspace();
    render();
  });
}

function applyBrandVoice(name) {
  const profile = brandVoiceProfiles.find((item) => item.name === name);
  if (!profile) return;
  ["direct", "warm", "formal", "technical", "concise"].forEach((key) => {
    const range = document.querySelector(`#tone-${key}`);
    if (!range) return;
    range.value = profile[key];
    if (range.nextElementSibling) range.nextElementSibling.textContent = profile[key];
  });
}

function updateInputStats(prefix, text) {
  const stats = localStats(text);
  const count = document.querySelector(`#${prefix}-count`);
  const quality = document.querySelector(`#${prefix}-quality`);
  const meter = document.querySelector(`#${prefix}-meter`);
  const action = prefix === "enterprise" ? document.querySelector("#generate-enterprise") : document.querySelector("#analyze-explorer");
  const copyInput = prefix === "explorer" ? document.querySelector("#copy-explorer-input") : null;
  if (count) count.textContent = `${stats.words} ${stats.words === 1 ? "word" : "words"}`;
  if (quality) {
    if (!stats.words) quality.textContent = prefix === "enterprise" ? "Add prospect language to generate a brief." : "Add text to analyze.";
    else if (prefix === "enterprise" && stats.words > 900) quality.textContent = "Large input. Use batch tools for many prospects.";
    else if (prefix === "explorer" && stats.words > 500) quality.textContent = "Long sample. Analyze one section at a time for cleaner coaching.";
    else quality.textContent = stats.words >= 40 ? "Good first-pass length." : "Short sample. Add more context for stronger output.";
  }
  if (meter) {
    const value = Math.min((stats.words / 60) * 100, 100);
    meter.value = value;
    meter.textContent = `${Math.round(value)}%`;
  }
  if (action) action.disabled = !text.trim();
  if (copyInput) copyInput.disabled = !text.trim();
}

async function runAnalysis(text) {
  if (!text.trim()) return;
  if (state.mode === "enterprise") {
    const landingTab = state.enterpriseLandingTab || "drafts";
    state.activeEnterpriseTab = landingTab;
    state.enterpriseLandingTab = "";
    state.activeEnterpriseTool = "batch";
    state.enterpriseContext = enterpriseContext();
    state.enterpriseDrafts = [];
    state.enterpriseInputsCollapsed = true;
    state.enterpriseSetupOpen = false;
    state.integrationSetupOpen = false;
    state.campaignSaved = false;
    state.lastActionNote = landingTab === "dashboard" ? "Sample workspace ready. Next: open the review queue." : "Next: review the recommended draft, then approve or export.";
  } else {
    state.activeExplorerTab = "style";
    state.explorerSavedMessage = "";
    state.explorerQuickChecksOpen = false;
    state.explorerStyleDetailsOpen = false;
  }
  els.outputPanel.innerHTML = uiHelpers.loadingCard?.(state.mode) || `<div class="empty-hero fade-in"><span class="status-pill">Working</span><h2>Reading the submitted text...</h2><p class="muted">Preparing the next view.</p></div>`;
  uiHelpers.focusWithin?.(els.outputPanel, ".loading-card");
  try {
    const data = await evaluateText(text.trim());
    state.latestData = data;
    state.latestText = text.trim();
    state.lastGeneratedAt = new Date().toLocaleString([], {month: "short", day: "numeric", hour: "2-digit", minute: "2-digit"});
    if (state.mode === "explorer") {
      state.explorerHistory = [explorerSnapshot(data, text), ...state.explorerHistory].slice(0, 12);
    }
    persistWorkspace();
    renderModeChrome();
    if (state.mode === "enterprise") render();
    else renderExplorerResult(data);
    trackEvent("analysis_completed", {words: text.trim().split(/\s+/).length});
    uiHelpers.announce?.(els.announcer, state.mode === "enterprise" ? "Enterprise drafts are ready." : "Explorer reading is ready.");
    els.outputPanel.focus();
    requestAnimationFrame(() => {
      const top = Math.max(0, els.outputPanel.getBoundingClientRect().top + window.scrollY - 12);
      window.scrollTo({top, behavior: "auto"});
    });
  } catch (error) {
    els.outputPanel.innerHTML = uiHelpers.errorCard?.(escapeHtml(error.message)) || `<div class="empty-hero"><h2>The reading did not run.</h2><p class="muted">${escapeHtml(error.message)}</p><button class="button-secondary" id="retry-run">Retry</button></div>`;
    document.querySelector("#retry-run").addEventListener("click", () => runAnalysis(text));
    uiHelpers.announce?.(els.announcer, "The reading did not run. Retry is available.");
    uiHelpers.focusWithin?.(els.outputPanel, "#retry-run");
  }
}

function render() {
  syncBodyState();
  if (state.mode === "enterprise") {
    renderEnterpriseInput();
    state.latestData ? renderEnterpriseResult(state.latestData) : renderEnterpriseEmpty();
  } else {
    renderExplorerInput();
    state.latestData ? renderExplorerResult(state.latestData) : renderExplorerEmpty();
  }
  wireInput();
}

function syncBodyState() {
  els.body.classList.toggle("has-work", Boolean(state.latestText || state.latestData));
  els.body.classList.toggle("app-compact", Boolean(state.latestText || state.latestData || state.explorerHistory.length || state.savedCampaigns.length));
  els.body.classList.toggle("explorer-collapsed", state.mode === "explorer" && Boolean(state.latestData));
  els.body.classList.toggle("enterprise-collapsed", state.mode === "enterprise" && Boolean(state.latestData) && state.enterpriseInputsCollapsed);
  els.body.classList.toggle("enterprise-setup-open", state.mode === "enterprise" && Boolean(state.enterpriseSetupOpen));
}

function trapAccountFocus(event) {
  const sheet = els.accountCard?.querySelector(".account-sheet");
  if (!sheet) return;
  const focusable = [...sheet.querySelectorAll('a[href], button, input, select, textarea, summary, [tabindex]:not([tabindex="-1"])')]
    .filter((item) => !item.disabled && item.offsetParent !== null);
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

loadWorkspace();
const routedMode = modeFromPath();
if (routedMode) {
  if (routedMode !== state.mode) {
    state.latestData = null;
    state.latestText = "";
    state.enterpriseDrafts = [];
    state.campaignSaved = false;
    state.enterpriseSetupOpen = false;
  }
  state.mode = routedMode;
} else {
  updateModeRoute(state.mode, true);
}
els.body.dataset.mode = state.mode;
els.modeExplorer.setAttribute("aria-pressed", String(state.mode === "explorer"));
els.modeEnterprise.setAttribute("aria-pressed", String(state.mode === "enterprise"));
renderModeChrome();
els.modeExplorer.addEventListener("click", () => setMode("explorer"));
els.modeEnterprise.addEventListener("click", () => setMode("enterprise"));
window.addEventListener("popstate", () => {
  const nextMode = modeFromPath() || "explorer";
  if (nextMode === state.mode) return;
  state.mode = nextMode;
  state.latestData = null;
  state.latestText = "";
  state.enterpriseDrafts = [];
  state.enterpriseSetupOpen = false;
  state.activeExplorerTab = "style";
  state.activeEnterpriseTab = "dashboard";
  state.activeEnterpriseTool = "batch";
  els.body.dataset.mode = state.mode;
  els.modeExplorer.setAttribute("aria-pressed", String(state.mode === "explorer"));
  els.modeEnterprise.setAttribute("aria-pressed", String(state.mode === "enterprise"));
  renderModeChrome();
  render();
});
document.addEventListener("keydown", (event) => {
  if (!state.accountModalOpen) return;
  if (event.key === "Tab") {
    trapAccountFocus(event);
    return;
  }
  if (event.key !== "Escape") return;
  state.accountModalOpen = false;
  state.accountError = "";
  state.accountDeletePending = false;
  state.accountCodePanelOpen = false;
  renderAccountCard();
});

const isLocalRuntime = ["127.0.0.1", "localhost", "::1"].includes(window.location.hostname);
els.body.classList.toggle("is-local-runtime", isLocalRuntime);
if (isLocalRuntime) {
  els.runtimeLabel.textContent = "Local demo:";
  if (els.runtimeCopy) els.runtimeCopy.textContent = "CRM, email, and sidebar integrations stay preview-only until credentials are connected.";
} else {
  els.runtimeLabel.textContent = "Deployment:";
  if (els.runtimeCopy) els.runtimeCopy.textContent = "connected services depend on your configured credentials, database, and workspace settings.";
}

render();
initAccount().finally(handleAccountLinkTokens);
