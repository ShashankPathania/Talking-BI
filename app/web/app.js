const state = {
  datasets: [],
  sessions: [],
  activeDatasetId: "",
  activeSessionId: "",
};

const elements = {
  systemStatus: document.getElementById("system-status"),
  datasetSelect: document.getElementById("dataset-select"),
  sessionSelect: document.getElementById("session-select"),
  sessionIdDisplay: document.getElementById("session-id-display"),
  activeDatasetPill: document.getElementById("active-dataset-pill"),
  
  queryInput: document.getElementById("query-input"),
  chatStream: document.getElementById("chat-stream"),
  emptyState: document.getElementById("empty-state"),
  
  resultsCanvas: document.getElementById("results-canvas"),
  kpiGrid: document.getElementById("kpi-grid"),
  primaryChart: document.getElementById("primary-chart"),
  chartGallery: document.getElementById("chart-gallery"),
  chartTypeLabel: document.getElementById("chart-type-label"),
  reportSections: document.getElementById("report-sections"),
  reportSectionContainer: document.getElementById("report-section-container"),
  insightsStrip: document.getElementById("insights-strip"),
  warningsStrip: document.getElementById("warnings-strip"),
  preview: document.getElementById("preview"),
  
  debugDrawer: document.getElementById("debug-drawer"),
  debugSummary: document.getElementById("debug-summary"),
  queryState: document.getElementById("query-state"),
  executionPlan: document.getElementById("execution-plan"),
  queryHistory: document.getElementById("query-history"),
  debugSql: document.getElementById("debug-sql"),
  executedSql: document.getElementById("executed-sql"),
  
  sidebarStatus: document.getElementById("sidebar-status"),
  sendBtn: document.getElementById("send-btn"),
  loadingSpinner: document.getElementById("loading-spinner"),
  exportPdf: document.getElementById("export-pdf"),
};

// --- Dark Plotly Theme setup ---
const plotlyDarkTemplate = {
  layout: {
    paper_bgcolor: 'transparent',
    plot_bgcolor: 'transparent',
    font: { color: '#94a3b8', family: "'Inter', sans-serif" },
    title: { font: { color: '#f8fafc', size: 16 } },
    xaxis: { gridcolor: 'rgba(255,255,255,0.05)', zerolinecolor: 'rgba(255,255,255,0.1)' },
    yaxis: { gridcolor: 'rgba(255,255,255,0.05)', zerolinecolor: 'rgba(255,255,255,0.1)' },
    colorway: ['#8b5cf6', '#3b82f6', '#10b981', '#f59e0b', '#ec4899', '#6366f1']
  }
};

// Deep-merge layout objects so axis titles from Plotly Express aren't overwritten
function mergeLayouts(figureLayout, darkTemplate) {
  const merged = { ...figureLayout };
  for (const [key, value] of Object.entries(darkTemplate)) {
    if (key === 'xaxis' || key === 'yaxis') {
      merged[key] = { ...(figureLayout[key] || {}), ...value };
    } else if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
      merged[key] = { ...(figureLayout[key] || {}), ...value };
    } else {
      if (!(key in merged)) merged[key] = value;
    }
  }
  return merged;
}

function toast(message, isError = false) {
  elements.sidebarStatus.textContent = message;
  elements.sidebarStatus.style.color = isError ? "var(--color-error)" : "var(--text-secondary)";
  setTimeout(() => { if(elements.sidebarStatus.textContent === message) elements.sidebarStatus.textContent = ""; }, 5000);
}

function exportDashboardToPdf() {
  if (elements.resultsCanvas.classList.contains("hidden")) {
    toast("Run a query first so there is something to export.", true);
    return;
  }
  const originalTitle = document.title;
  const dataset = state.datasets.find((item) => item.dataset_id === state.activeDatasetId);
  const sessionSuffix = state.activeSessionId ? ` - ${state.activeSessionId.slice(0, 8)}` : "";
  document.title = `Talking BI Dashboard${dataset ? ` - ${dataset.name}` : ""}${sessionSuffix}`;
  document.body.classList.add("print-mode");
  window.print();
  setTimeout(() => {
    document.body.classList.remove("print-mode");
    document.title = originalTitle;
  }, 300);
}

function appendAssistantMessage(message) {
  const currentMessages = [];
  const messageElements = elements.chatStream.querySelectorAll(".message-wrapper");
  messageElements.forEach((element) => {
    const role = element.classList.contains("user") ? "user" : "assistant";
    currentMessages.push({ role, content: element.querySelector(".message-content")?.innerText || "" });
  });
  currentMessages.push({ role: "assistant", content: message });
  renderChatStream(currentMessages);
}

function toggleLoading(isLoading) {
  if(isLoading) {
    elements.sendBtn.classList.add("hidden");
    elements.loadingSpinner.classList.remove("hidden");
  } else {
    elements.sendBtn.classList.remove("hidden");
    elements.loadingSpinner.classList.add("hidden");
  }
}

// --- Sidebar Sync ---
function updateSessionLabel() {
  elements.sessionIdDisplay.textContent = state.activeSessionId ? state.activeSessionId.slice(0, 12) : "Not started";
}

function updateDatasetPill() {
  const dataset = state.datasets.find((item) => item.dataset_id === state.activeDatasetId);
  elements.activeDatasetPill.textContent = dataset ? `${dataset.name} (${dataset.source_type})` : "None";
}

function renderDatasetOptions() {
  const options = ['<option value="">Select a dataset</option>'];
  for (const dataset of state.datasets) {
    options.push(`<option value="${dataset.dataset_id}">${dataset.name} (${dataset.source_type})</option>`);
  }
  elements.datasetSelect.innerHTML = options.join("");
  elements.datasetSelect.value = state.activeDatasetId;
  updateDatasetPill();
}

function renderSessionOptions() {
  const options = ['<option value="">New session</option>'];
  for (const session of state.sessions) {
    options.push(`<option value="${session.session_id}">${session.session_id.slice(0, 8)} (${session.query_count} queries)</option>`);
  }
  elements.sessionSelect.innerHTML = options.join("");
  elements.sessionSelect.value = state.activeSessionId;
  updateSessionLabel();
}

// --- Chat & NLP render ---
function renderChatStream(messages, stateMeta = null) {
  if (!messages || messages.length === 0) {
    elements.chatStream.innerHTML = "";
    elements.chatStream.appendChild(elements.emptyState);
    elements.emptyState.classList.remove("hidden");
    return;
  }
  
  elements.emptyState.classList.add("hidden");
  
  let html = "";
  messages.forEach(msg => {
    // Only parse markdown for assistant role
    let contentHtml = msg.role === "assistant" && window.marked ? marked.parse(msg.content) : escapeHtml(msg.content);
    
    html += `
      <div class="message-wrapper ${msg.role}">
        <div class="message-content">
          ${contentHtml}
        </div>
    `;
    
    // Attach metric pills to latest assistant message if available
    if (msg.role === "assistant" && stateMeta && msg === messages[messages.length-1]) {
        let pills = [];
        if (stateMeta.intent?.goal) pills.push(stateMeta.intent.goal);
        if (stateMeta.visualization?.chart_type) pills.push(stateMeta.visualization.chart_type);
        if (stateMeta.transformation?.group_by?.length) pills.push(`grouped by ${stateMeta.transformation.group_by.join(',')}`);
        
        if (pills.length > 0) {
             html += `<div class="ai-reasoning-pills">`;
             pills.forEach(p => html += `<span class="pill">${escapeHtml(p)}</span>`);
             html += `</div>`;
        }
    }
    
    html += `</div>`;
  });
  
  elements.chatStream.innerHTML = html;
}

// --- Canvas Components ---
function renderKpis(kpis) {
  if (!kpis || !kpis.length) {
    elements.kpiGrid.innerHTML = "";
    return;
  }
  elements.kpiGrid.innerHTML = kpis.map(item => `
    <article class="kpi-card">
      <span class="kpi-label">${escapeHtml(item.label)}</span>
      <strong class="kpi-value">${escapeHtml(item.value)}</strong>
      <small class="muted">${escapeHtml(item.context || "")}</small>
    </article>
  `).join("");
}

function renderCharts(primaryChart, additionalCharts) {
  // Primary
  if (!primaryChart || !primaryChart.figure) {
    elements.primaryChart.innerHTML = '<p class="muted" style="text-align:center; padding: 40px;">No visualization generated.</p>';
    elements.chartTypeLabel.textContent = "None";
    elements.chartGallery.innerHTML = "";
    return;
  }
  
  // Show both chart type and title in the badge
  const chartLabel = primaryChart.title && primaryChart.title !== primaryChart.chart_type
    ? `${primaryChart.chart_type} — ${primaryChart.title}`
    : primaryChart.chart_type;
  elements.chartTypeLabel.textContent = chartLabel;
  
  // Deep-merge dark theme so axis titles from Plotly Express are preserved
  const layout = mergeLayouts(primaryChart.figure.layout || {}, plotlyDarkTemplate.layout);
  Object.assign(layout, { margin: { l: 40, r: 20, t: 60, b: 40 }, autosize: true });
  
  Plotly.react(elements.primaryChart, primaryChart.figure.data, layout, { responsive: true, displaylogo: false });
  
  // Gallery
  if (!additionalCharts || additionalCharts.length <= 1) {
    elements.chartGallery.innerHTML = "";
    return;
  }
  
  elements.chartGallery.innerHTML = additionalCharts.slice(1).map((chart, i) => `
    <article class="chart-card">
      <h3>${escapeHtml(chart.title || "Detail Chart")}</h3>
      <div id="chart-gallery-${i}" class="chart-surface" style="min-height:300px;"></div>
    </article>
  `).join("");
  
  additionalCharts.slice(1).forEach((chart, i) => {
    const target = document.getElementById(`chart-gallery-${i}`);
    if (target && chart.figure) {
      const glayout = mergeLayouts(chart.figure.layout || {}, plotlyDarkTemplate.layout);
      Object.assign(glayout, { margin: { l: 40, r: 20, t: 40, b: 40 } });
      Plotly.react(target, chart.figure.data, glayout, { responsive: true, displaylogo: false });
    }
  });
}

function renderReportSections(sections) {
  if (!sections || !sections.length) {
    elements.reportSectionContainer.classList.add("hidden");
    return;
  }
  elements.reportSectionContainer.classList.remove("hidden");
  
  elements.reportSections.innerHTML = sections.map(section => `
    <article class="report-card">
      <h3>${escapeHtml(section.title)}</h3>
      <p>${escapeHtml(section.summary)}</p>
      ${section.bullets?.length ? `<ul>${section.bullets.map(b => `<li>${escapeHtml(b)}</li>`).join("")}</ul>` : ""}
    </article>
  `).join("");
}

function renderInsightsAndWarnings(insights, warnings) {
  if (!insights || !insights.length) {
    elements.insightsStrip.innerHTML = '<p class="muted">No key insights detected.</p>';
  } else {
    elements.insightsStrip.innerHTML = insights.map(i => `
      <article class="insight-card" data-confidence="${escapeHtml(i.confidence)}">
        <h4 style="margin-bottom:8px;">${escapeHtml(i.title)}</h4>
        <p class="muted" style="font-size:0.875rem;">${escapeHtml(i.detail)}</p>
      </article>
    `).join("");
  }
  
  if (!warnings || !warnings.length) {
    elements.warningsStrip.innerHTML = "";
  } else {
    elements.warningsStrip.innerHTML = warnings.map(w => `
      <article class="insight-card" style="border-left: 3px solid var(--color-error);">
        <h4 style="margin-bottom:8px; color: var(--color-error);">Warning</h4>
        <p class="muted" style="font-size:0.875rem;">${escapeHtml(w)}</p>
      </article>
    `).join("");
  }
}

function renderPreview(rows) {
  if (!rows || !rows.length) {
    elements.preview.innerHTML = '<p class="muted" style="padding:16px;">No preview rows returned.</p>';
    return;
  }
  const columns = Object.keys(rows[0]);
  const header = columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("");
  const body = rows.map((row) => `<tr>${columns.map((column) => `<td>${escapeHtml(String(row[column] ?? ""))}</td>`).join("")}</tr>`).join("");
  elements.preview.innerHTML = `<table><thead><tr>${header}</tr></thead><tbody>${body}</tbody></table>`;
}

function renderDebug(response) {
  if(!response) return;
  const safeDebug = response.debug || {};
  elements.debugSummary.innerHTML = [
    { title: "Reasoning mode", value: safeDebug.reasoning_mode || "unknown" },
    { title: "SQL mode", value: safeDebug.sql_mode || "none" },
    { title: "Matched col", value: (safeDebug.matched_columns || []).join(", ") || "None" }
  ].map(card => `
    <article class="debug-card">
      <h3>${escapeHtml(card.title)}</h3>
      <p>${escapeHtml(card.value)}</p>
    </article>
  `).join("");
  
  elements.queryState.textContent = JSON.stringify(response.query_state || {}, null, 2);
  elements.executionPlan.textContent = JSON.stringify(response.execution_plan || {}, null, 2);
  elements.debugSql.textContent = safeDebug.generated_sql || "-- No generated SQL";
  elements.executedSql.textContent = safeDebug.executed_sql || "-- No executed SQL";
}

// --- API Calls ---
async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || `HTTP ${response.status}`);
  }
  return response.json();
}

async function loadDatasets() {
  const payload = await fetchJson("/v1/datasets");
  state.datasets = payload.datasets || [];
  if (!state.activeDatasetId && state.datasets.length) {
    state.activeDatasetId = state.datasets[0].dataset_id;
  }
  renderDatasetOptions();
}

async function loadSessions() {
  const payload = await fetchJson("/v1/sessions");
  state.sessions = payload.sessions || [];
  renderSessionOptions();
}

async function loadSession(sessionId) {
  if (!sessionId) {
    resetForNewSession();
    return;
  }
  const payload = await fetchJson(`/v1/sessions/${sessionId}`);
  state.activeSessionId = payload.session_id;
  if (payload.dataset_id) {
    state.activeDatasetId = payload.dataset_id;
    renderDatasetOptions();
  }
  
  renderChatStream(payload.messages || []);
  
  // When restoring session, we don't have the rich BIResponse (charts/kpis) from the history endpoint easily, 
  // so we clear canvas. The user can ask a new question to repopulate.
  elements.resultsCanvas.classList.add("hidden");
  
  elements.queryState.textContent = JSON.stringify(payload.query_state || {}, null, 2);
  elements.queryHistory.textContent = JSON.stringify(payload.query_history || [], null, 2);
  renderSessionOptions();
  updateSessionLabel();
}

async function runQuery(event) {
  event.preventDefault();
  const message = elements.queryInput.value.trim();
  if (!message) return;
  if (!state.activeDatasetId) { toast("Select a dataset first.", true); return; }

  toggleLoading(true);
  
  // Optimistic UI for user message
  const currentMessages = [];
  const pMessageElements = elements.chatStream.querySelectorAll(".message-wrapper");
  pMessageElements.forEach(el => {
      // Very basic extraction just to keep visual context, but true context comes from session
      let role = el.classList.contains("user") ? "user" : "assistant";
      currentMessages.push({role: role, content: el.querySelector(".message-content").innerText});
  });
  currentMessages.push({role: "user", content: message});
  renderChatStream(currentMessages);

  let response;
  try {
    response = await fetchJson("/v1/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, dataset_id: state.activeDatasetId, session_id: state.activeSessionId || undefined }),
    });
  } catch (error) {
    toast(`Query Error: ${error.message}`, true);
    appendAssistantMessage(`**AI Generation Error**\n\nI encountered a technical issue while processing that request: _"${error.message}"_. \n\nThis usually happens during high traffic or if a provider is rate-limited. Please try again in a few moments.`);
    toggleLoading(false);
    return;
  }

  try {
    state.activeSessionId = response.session_id;
    elements.queryInput.value = "";

    currentMessages.push({role: "assistant", content: response.explanation});
    renderChatStream(currentMessages, response.query_state);

    elements.resultsCanvas.classList.remove("hidden");
    renderKpis(response.kpis);
    renderCharts(response.chart, response.charts);
    renderReportSections(response.report_sections);
    renderInsightsAndWarnings(response.insights, response.warnings);
    renderPreview(response.data_preview);
    renderDebug(response);

    window.scrollTo({ top: 0, behavior: 'smooth' });

    try {
      await loadSessions();
    } catch (sessionError) {
      console.error("Session refresh failed after successful query", sessionError);
      toast("The analysis succeeded, but refreshing the session list failed.", true);
    }
  } catch (renderError) {
    console.error("Client-side render failure after successful query", renderError, response);
    currentMessages.push({role: "assistant", content: response.explanation || "The analysis completed, but the UI could not render the full response."});
    renderChatStream(currentMessages, response.query_state || null);
    toast(`Render Error: ${renderError.message}`, true);
    appendAssistantMessage("The backend returned a valid analysis, but the browser could not render part of the response. Open the debug panel or refresh the page and try again.");
  } finally {
    toggleLoading(false);
  }
}

// --- Uploads & Connections ---
async function uploadDataset(event) {
  event.preventDefault();
  const fileInput = document.getElementById("dataset-file");
  const nameInput = document.getElementById("dataset-name");
  
  if (!fileInput.files.length) return;
  
  const formData = new FormData();
  formData.append("file", fileInput.files[0]);
  if (nameInput.value.trim()) formData.append("dataset_name", nameInput.value.trim());

  toast("Uploading...");
  try {
    const payload = await fetchJson("/v1/datasets/upload", { method: "POST", body: formData });
    state.activeDatasetId = payload.dataset.dataset_id;
    await loadDatasets();
    fileInput.value = ""; nameInput.value = "";
    toast("Upload complete.");
  } catch (error) {
    toast(`Upload failed: ${error.message}`, true);
  }
}

async function connectDatabase(event) {
  event.preventDefault();
  const req = {
    name: document.getElementById("db-name").value.trim(),
    database_url: document.getElementById("db-url").value.trim(),
    table_name: document.getElementById("db-table").value.trim(),
    dialect: document.getElementById("db-dialect").value
  };

  toast("Connecting...");
  try {
    const payload = await fetchJson("/v1/datasets/register-database", { 
      method: "POST", 
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req)
    });
    state.activeDatasetId = payload.dataset.dataset_id;
    await loadDatasets();
    event.target.reset();
    toast("Database connected.");
  } catch (error) {
    toast(`Connection failed: ${error.message}`, true);
  }
}

// --- Utils & Wireups ---
function resetForNewSession() {
  state.activeSessionId = "";
  renderSessionOptions();
  renderChatStream([]);
  elements.resultsCanvas.classList.add("hidden");
  renderDebug(null);
  elements.queryHistory.textContent = "";
  toast("New session context started.");
}

function escapeHtml(value) {
  if(value === null || value === undefined) return "";
  return String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

document.getElementById("query-form").addEventListener("submit", runQuery);
document.getElementById("query-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); runQuery(e); }
});

document.getElementById("upload-form").addEventListener("submit", uploadDataset);
document.getElementById("connect-db-form").addEventListener("submit", connectDatabase);

document.getElementById("refresh-datasets").addEventListener("click", async () => {
  await loadDatasets(); await loadSessions(); toast("Refreshed");
});
document.getElementById("new-session").addEventListener("click", resetForNewSession);
elements.exportPdf.addEventListener("click", exportDashboardToPdf);

elements.datasetSelect.addEventListener("change", (e) => {
  state.activeDatasetId = e.target.value; updateDatasetPill();
});
elements.sessionSelect.addEventListener("change", async (e) => {
  await loadSession(e.target.value);
});

// UI Tabs
document.getElementById("btn-show-upload").addEventListener("click", (e) => {
  e.target.classList.add("active");
  document.getElementById("btn-show-connect").classList.remove("active");
  document.getElementById("upload-form").classList.add("active");
  document.getElementById("connect-db-form").classList.remove("active");
});
document.getElementById("btn-show-connect").addEventListener("click", (e) => {
  e.target.classList.add("active");
  document.getElementById("btn-show-upload").classList.remove("active");
  document.getElementById("connect-db-form").classList.add("active");
  document.getElementById("upload-form").classList.remove("active");
});

// Debug Toggle
document.getElementById("toggle-debug").addEventListener("click", () => {
  elements.debugDrawer.classList.toggle("hidden");
  window.scrollTo({ left:0, top: document.body.scrollHeight, behavior: 'smooth' });
});

for (const chip of document.querySelectorAll(".prompt-chip")) {
  chip.addEventListener("click", () => {
    elements.queryInput.value = chip.dataset.prompt || "";
    elements.queryInput.focus();
  });
}

// Intercept marked.js initialization if present
if (window.marked) {
    marked.setOptions({
        gfm: true,
        breaks: true,
    });
}

(async function bootstrap() {
  try {
    const sys = await fetchJson("/v1/system/status");
    elements.systemStatus.textContent = sys.llm_enabled ? `Hybrid Mode` : `Deterministic`;
    elements.systemStatus.style.background = sys.llm_enabled ? "var(--color-high)" : "var(--color-low)";
    elements.systemStatus.style.color = sys.llm_enabled ? "var(--color-high-text)" : "var(--color-low-text)";
    
    await loadDatasets();
    await loadSessions();
    renderChatStream([]);
    updateSessionLabel();
    updateDatasetPill();
  } catch (error) {
    toast(`Startup failed: ${error.message}`, true);
  }
})();
