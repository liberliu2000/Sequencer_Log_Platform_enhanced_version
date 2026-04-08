(() => {
  const config = window.__APP_CONFIG__ || {};
  const state = {
    currentPage: "home",
    tasks: [],
    selectedTaskUuid: "",
    currentUser: null,
    latestDiagnosisResult: null,
    latestDiagnosisSignature: "",
    latestReviewResult: null,
    latestSimilarCases: [],
    selectedHistoryTaskUuid: "",
    timelineFilters: {
      cycleNo: "",
      sideScope: "all",
      trackOrder: "default",
      trackGranularity: "side_chip",
    },
    parameterFilters: {
      parameterName: "",
      axisMode: "cycle",
      unit: "s",
      sideScope: "all",
    },
    solutionDraft: {
      error_name: "",
      error_category: "",
      error_code: "",
      impact_scope: "",
      owner_department: "",
      root_cause_analysis: "",
      verified_solution: "",
      workaround: "",
      submitter: "",
      reusable: true,
    },
  };

  const TOKEN_KEY = "slp-web-auth-token";
  const TASK_KEY = "slp-web-selected-task";
  const BEIJING_TIMEZONE = "Asia/Shanghai";
  const TIMELINE_COLOR_SEQUENCE = [
    "#0B5CAD",
    "#1E8E6A",
    "#D97706",
    "#C2410C",
    "#7C3AED",
    "#0F766E",
    "#B45309",
    "#DC2626",
    "#2563EB",
    "#9333EA",
    "#059669",
    "#CA8A04",
    "#BE185D",
    "#0369A1",
    "#4F46E5",
    "#15803D",
    "#EA580C",
    "#7E22CE",
    "#047857",
    "#B91C1C",
  ];

  const navLabels = {
    home: "Home / Dashboard",
    history: "History",
    upload: "Upload",
    events: "Events",
    timing: "Timing",
    timeline: "Timeline",
    errors: "Errors",
    parameters: "Parameters",
    diagnosis: "LLM Diagnosis",
    files: "File Preview",
    unknown: "Unknown Logs",
    rules: "Rule Review",
    config: "Config",
    solutions: "Solutions",
    exports: "Exports",
    admin: "User Admin",
  };

  const dom = {
    pageMount: document.getElementById("pageMount"),
    pageTitle: document.getElementById("pageTitle"),
    globalTaskSelect: document.getElementById("globalTaskSelect"),
    refreshGlobalTaskButton: document.getElementById("refreshGlobalTaskButton"),
    openDocsButton: document.getElementById("openDocsButton"),
    quickRefreshButton: document.getElementById("quickRefreshButton"),
    healthBadge: document.getElementById("healthBadge"),
    topStatusMessage: document.getElementById("topStatusMessage"),
    userBadge: document.getElementById("userBadge"),
    heroTask: document.getElementById("heroTask"),
    heroUser: document.getElementById("heroUser"),
    authMessage: document.getElementById("authMessage"),
    loginForm: document.getElementById("loginForm"),
    logoutButton: document.getElementById("logoutButton"),
    registerStartForm: document.getElementById("registerStartForm"),
    changePasswordForm: document.getElementById("changePasswordForm"),
  };

  function byId(id) {
    return document.getElementById(id);
  }

  function qsa(selector, root = document) {
    return Array.from(root.querySelectorAll(selector));
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function safeString(value, fallback = "") {
    if (value === null || value === undefined) {
      return fallback;
    }
    return String(value);
  }

  function safeArray(value) {
    return Array.isArray(value) ? value : [];
  }

  function safeObject(value) {
    return value && typeof value === "object" && !Array.isArray(value) ? value : {};
  }

  function clip(value, limit = 88) {
    const text = safeString(value);
    return text.length > limit ? `${text.slice(0, limit - 1)}...` : text;
  }

  function emptyState(message) {
    return `<div class="empty-state">${escapeHtml(message || "No data.")}</div>`;
  }

  function formatNumber(value) {
    if (value === null || value === undefined || value === "") {
      return "-";
    }
    const numeric = Number(value);
    if (Number.isFinite(numeric)) {
      return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(numeric);
    }
    return safeString(value);
  }

  function parseUtcApiDate(value) {
    if (!value) {
      return null;
    }
    if (value instanceof Date) {
      return Number.isNaN(value.getTime()) ? null : value;
    }
    const text = safeString(value).trim();
    if (!text) {
      return null;
    }
    const normalized = text.includes("T") ? text : text.replace(" ", "T");
    if (/^\d{4}-\d{2}-\d{2}$/.test(normalized)) {
      const date = new Date(`${normalized}T00:00:00Z`);
      return Number.isNaN(date.getTime()) ? null : date;
    }
    const hasTimezone = /[zZ]$|[+\-]\d{2}:\d{2}$/.test(normalized);
    const candidate = hasTimezone ? normalized : `${normalized}Z`;
    const date = new Date(candidate);
    return Number.isNaN(date.getTime()) ? null : date;
  }

  function formatDateTime(value) {
    if (!value) {
      return "-";
    }
    const date = parseUtcApiDate(value);
    if (!date) {
      return safeString(value);
    }
    return date.toLocaleString("zh-CN", { hour12: false, timeZone: BEIJING_TIMEZONE });
  }

  function formatFileSize(value) {
    const bytes = Number(value || 0);
    if (!Number.isFinite(bytes) || bytes <= 0) {
      return "0 B";
    }
    const units = ["B", "KB", "MB", "GB", "TB"];
    let size = bytes;
    let unitIndex = 0;
    while (size >= 1024 && unitIndex < units.length - 1) {
      size /= 1024;
      unitIndex += 1;
    }
    return `${size.toFixed(unitIndex === 0 ? 0 : 2)} ${units[unitIndex]}`;
  }

  function firstNonEmpty(...values) {
    for (const value of values) {
      const text = safeString(value).trim();
      if (text) {
        return text;
      }
    }
    return "";
  }

  function hashText(value) {
    const text = safeString(value, "");
    let hash = 0;
    for (let index = 0; index < text.length; index += 1) {
      hash = (hash * 31 + text.charCodeAt(index)) >>> 0;
    }
    return hash;
  }

  function pickTimelineColor(...parts) {
    const key = parts.map((part) => safeString(part, "")).join("|");
    return TIMELINE_COLOR_SEQUENCE[hashText(key) % TIMELINE_COLOR_SEQUENCE.length];
  }

  function statusTone(status) {
    const normalized = safeString(status).toLowerCase();
    if (["ok", "healthy", "completed", "approved", "enabled", "active"].includes(normalized)) {
      return "";
    }
    if (["warning", "warn", "pending_review", "submitted_for_review", "needs_revision", "processing"].includes(normalized)) {
      return "warn";
    }
    if (["error", "failed", "fatal", "rejected", "disabled"].includes(normalized)) {
      return "danger";
    }
    return "muted";
  }

  function pill(text, tone) {
    return `<span class="status-pill ${escapeHtml(tone || statusTone(text))}">${escapeHtml(safeString(text, "-"))}</span>`;
  }

  function setTopStatus(message) {
    dom.topStatusMessage.textContent = message || "";
  }

  function setAuthMessage(message) {
    dom.authMessage.textContent = message || "";
  }

  function getToken() {
    return window.localStorage.getItem(TOKEN_KEY) || "";
  }

  function setToken(token) {
    if (token) {
      window.localStorage.setItem(TOKEN_KEY, token);
    } else {
      window.localStorage.removeItem(TOKEN_KEY);
    }
  }

  function saveSelectedTask(taskUuid) {
    state.selectedTaskUuid = taskUuid || "";
    if (state.selectedTaskUuid) {
      window.localStorage.setItem(TASK_KEY, state.selectedTaskUuid);
    } else {
      window.localStorage.removeItem(TASK_KEY);
    }
    dom.heroTask.textContent = state.selectedTaskUuid || "鏈€夋嫨";
  }

  function getSelectedTask() {
    return state.selectedTaskUuid || "";
  }

  function isAdmin() {
    return Boolean(state.currentUser && state.currentUser.is_admin);
  }

  function isReviewer() {
    return Boolean(state.currentUser && (state.currentUser.is_admin || state.currentUser.is_reviewer));
  }

  function updateNavVisibility() {
    qsa(".nav-button").forEach((button) => {
      if (button.getAttribute("data-page") === "admin") {
        button.classList.toggle("hidden", !isAdmin());
      }
    });
  }

  function updateUserBadge() {
    if (!state.currentUser) {
      dom.userBadge.textContent = "Not logged in";
      dom.userBadge.className = "status-pill muted";
      dom.heroUser.textContent = "Guest";
      updateNavVisibility();
      return;
    }
    const roles = Array.isArray(state.currentUser.roles) ? state.currentUser.roles.join(", ") : "user";
    dom.userBadge.textContent = `${state.currentUser.username} 路 ${roles}`;
    dom.userBadge.className = "status-pill";
    dom.heroUser.textContent = state.currentUser.username || "User";
    updateNavVisibility();
  }

  async function apiRequest(path, options = {}, requireAuth = true) {
    const headers = new Headers(options.headers || {});
    if (requireAuth && getToken()) {
      headers.set("Authorization", `Bearer ${getToken()}`);
    }
    const response = await fetch(path, { ...options, headers });
    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("application/json") ? await response.json() : await response.text();
    if (!response.ok) {
      const detail =
        payload && typeof payload === "object" && "detail" in payload
          ? payload.detail
          : typeof payload === "string" && payload
            ? payload
            : `${response.status} ${response.statusText}`;
      throw new Error(detail);
    }
    return payload;
  }

  async function apiJson(path, method, payload, requireAuth = true) {
    return apiRequest(
      path,
      {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload ?? {}),
      },
      requireAuth
    );
  }

  function fmtJson(data) {
    return `<pre>${escapeHtml(JSON.stringify(data ?? {}, null, 2))}</pre>`;
  }

  function renderCards(items) {
    return `
      <div class="cards">
        ${items
          .map(
            (item) => `
              <div class="info-card">
                <span class="k">${escapeHtml(item.label)}</span>
                <span class="v">${escapeHtml(item.value)}</span>
              </div>
            `
          )
          .join("")}
      </div>
    `;
  }

  function renderDefinitionList(items) {
    if (!items || !items.length) {
      return `<div class="empty-state">No data.</div>`;
    }
    return `
      <div class="kv-grid">
        ${items
          .map(
            (item) => `
              <div class="kv-card">
                <span class="kv-key">${escapeHtml(item.label)}</span>
                <span class="kv-value">${item.html || escapeHtml(safeString(item.value, "-"))}</span>
                ${item.note ? `<p class="small-note">${escapeHtml(item.note)}</p>` : ""}
              </div>
            `
          )
          .join("")}
      </div>
    `;
  }

  function renderTable(columns, rows, rowActions = []) {
    if (!rows || !rows.length) {
      return emptyState("暂无数据。");
    }
    return `
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              ${columns.map((col) => `<th>${escapeHtml(col.label)}</th>`).join("")}
              ${rowActions.length ? "<th>鎿嶄綔</th>" : ""}
            </tr>
          </thead>
          <tbody>
            ${rows
              .map((row, index) => {
                const cells = columns
                  .map((col) => {
                    const value = typeof col.render === "function" ? col.render(row, index) : escapeHtml(row[col.key]);
                    return `<td>${value ?? "-"}</td>`;
                  })
                  .join("");
                const actions = rowActions.length
                  ? `<td>${rowActions
                      .map(
                        (action) => `
                          <button class="table-action${action.className ? ` ${escapeHtml(action.className)}` : ""}" type="button" data-action="${escapeHtml(action.action)}" data-group="${escapeHtml(action.group || "")}" data-row="${index}">
                            ${escapeHtml(action.label)}
                          </button>
                        `
                      )
                      .join("")}</td>`
                  : "";
                return `<tr>${cells}${actions}</tr>`;
              })
              .join("")}
          </tbody>
        </table>
      </div>
    `;
  }

  function pagePanel(title, subtitle, body) {
    return `
      <section class="panel">
        <div class="panel-heading">
          <div>
            <p class="section-kicker">${escapeHtml(navLabels[state.currentPage] || state.currentPage)}</p>
            <h3>${escapeHtml(title)}</h3>
          </div>
        </div>
        ${subtitle ? `<p class="panel-copy">${escapeHtml(subtitle)}</p>` : ""}
        ${body}
      </section>
    `;
  }

  function renderTabs(groupId, tabs) {
    return `
      <div class="tabs">
        ${tabs
          .map(
            (tab, index) => `
              <button
                class="tab"
                type="button"
                data-tab-group="${escapeHtml(groupId)}"
                data-tab-target="${escapeHtml(tab.key)}"
                data-active="${index === 0 ? "true" : "false"}"
              >
                ${escapeHtml(tab.label)}
              </button>
            `
          )
          .join("")}
      </div>
      <div class="tab-panels">
        ${tabs
          .map(
            (tab, index) => `
              <section
                class="tab-panel ${index === 0 ? "" : "hidden"}"
                data-tab-panel-group="${escapeHtml(groupId)}"
                data-tab-panel="${escapeHtml(tab.key)}"
              >
                ${tab.content}
              </section>
            `
          )
          .join("")}
      </div>
    `;
  }

  function hydrateTabs(root = dom.pageMount) {
    qsa("[data-tab-target]", root).forEach((button) => {
      button.addEventListener("click", () => {
        const group = button.getAttribute("data-tab-group");
        const target = button.getAttribute("data-tab-target");
        qsa(`[data-tab-target][data-tab-group="${group}"]`, root).forEach((item) => {
          item.setAttribute("data-active", item === button ? "true" : "false");
        });
        qsa(`[data-tab-panel-group="${group}"]`, root).forEach((panel) => {
          panel.classList.toggle("hidden", panel.getAttribute("data-tab-panel") !== target);
        });
      });
    });
  }

  function drawPlot(id, data, layout = {}) {
    if (!window.Plotly) {
      return;
    }
    const target = byId(id);
    if (!target) {
      return;
    }
    window.Plotly.newPlot(
      target,
      data,
      {
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        margin: { l: 48, r: 20, t: 36, b: 44 },
        legend: { orientation: "h" },
        ...layout,
      },
      { responsive: true, displayModeBar: false, displaylogo: false }
    );
  }

  function buildDownloadUrl(path) {
    const url = new URL(path, window.location.origin);
    if (getToken()) {
      url.searchParams.set("access_token", getToken());
    }
    return url.toString();
  }

  function hydrateActionTable(rows, handler) {
    let targetRows = rows;
    let targetHandler = handler;
    let selector = "[data-action]";
    if (typeof rows === "string") {
      selector = `[data-action][data-group="${rows}"]`;
      targetRows = arguments[1];
      targetHandler = arguments[2];
    }
    dom.pageMount.querySelectorAll(selector).forEach((button) => {
      button.addEventListener("click", async () => {
        const row = targetRows[Number(button.getAttribute("data-row"))];
        const action = button.getAttribute("data-action");
        await targetHandler(action, row);
      });
    });
  }

  async function refreshHealth() {
    try {
      const data = await apiRequest(config.healthUrl, {}, false);
      dom.healthBadge.textContent = `API ${data.status || "ok"}`;
      dom.healthBadge.className = "status-pill";
      setTopStatus("Backend health check passed.");
    } catch (error) {
      dom.healthBadge.textContent = "API 寮傚父";
      dom.healthBadge.className = "status-pill danger";
      setTopStatus(error.message);
    }
  }

  async function refreshCurrentUser() {
    if (!getToken()) {
      state.currentUser = null;
      updateUserBadge();
      return;
    }
    try {
      state.currentUser = await apiRequest(`${config.apiPrefix}/auth/me`);
      updateUserBadge();
    } catch (error) {
      state.currentUser = null;
      setToken("");
      updateUserBadge();
      setAuthMessage(error.message);
    }
  }

  async function refreshTasks() {
    try {
      const data = await apiRequest(`${config.apiPrefix}/tasks?page=1&page_size=50`);
      state.tasks = safeArray(data.items);
      if (!state.selectedTaskUuid && state.tasks.length) {
        saveSelectedTask(state.tasks[0].task_uuid);
      }
      if (!state.selectedHistoryTaskUuid && state.tasks.length) {
        state.selectedHistoryTaskUuid = state.tasks[0].task_uuid;
      }
      dom.globalTaskSelect.innerHTML =
        ['<option value="">鏈€夋嫨浠诲姟</option>']
          .concat(
            state.tasks.map(
              (item) => `
                <option value="${escapeHtml(item.task_uuid)}" ${item.task_uuid === getSelectedTask() ? "selected" : ""}>
                  ${escapeHtml(`${item.task_uuid} · ${item.filename || item.status || ""} · ${item.uploaded_by || "unknown"} · ${item.total_size_text || formatFileSize(item.total_size_bytes)}`)}
                </option>
              `
            )
          )
          .join("");
    } catch (error) {
      state.tasks = [];
      dom.globalTaskSelect.innerHTML = '<option value="">鏈€夋嫨浠诲姟</option>';
      setTopStatus(error.message);
    }
  }

  function requireTask() {
    const taskUuid = getSelectedTask();
    if (!taskUuid) {
      throw new Error("Please select a task in the sidebar first.");
    }
    return taskUuid;
  }

  function renderAnnouncementCards(items, { compact = false } = {}) {
    return safeArray(items)
      .map((item) => {
        const latestEdit = safeArray(item.edit_history).slice(-1)[0] || {};
        const editor = firstNonEmpty(latestEdit.editor, item.updated_by, "system");
        const editedAt = firstNonEmpty(latestEdit.edited_at, item.updated_at, item.created_at);
        return `
          <article class="subpanel">
            <div class="button-row" style="justify-content:space-between;">
              <strong>${escapeHtml(firstNonEmpty(item.title, "未命名公告"))}</strong>
              <span class="status-pill ${item.is_pinned ? "" : "muted"}">${escapeHtml(item.is_pinned ? "置顶" : "公告")}</span>
            </div>
            <p class="panel-copy" style="margin-top:10px;">${escapeHtml(firstNonEmpty(item.summary, "暂无摘要"))}</p>
            <p class="small-note" style="margin-top:8px;">最近编辑: ${escapeHtml(editor)} · ${escapeHtml(formatDateTime(editedAt))}</p>
            ${compact ? "" : safeArray(item.edit_history).length ? `<details style="margin-top:10px;"><summary>编辑历史</summary>${fmtJson(item.edit_history)}</details>` : ""}
          </article>
        `;
      })
      .join("");
  }

  function buildLineSeries(rows, xKey, yKey, seriesKey) {
    const grouped = new Map();
    safeArray(rows).forEach((row) => {
      const seriesName = firstNonEmpty(row?.[seriesKey], row?.series_name, "Series");
      if (!grouped.has(seriesName)) {
        grouped.set(seriesName, []);
      }
      grouped.get(seriesName).push(row);
    });
    return Array.from(grouped.entries()).map(([seriesName, seriesRows]) => ({
      type: "scatter",
      mode: "lines+markers",
      name: seriesName,
      x: seriesRows.map((row) => row?.[xKey]),
      y: seriesRows.map((row) => Number(row?.[yKey] ?? 0)),
    }));
  }

  function buildTimelineTraces(rows, errors) {
    const traces = [];
    const groupedRows = new Map();
    safeArray(rows).forEach((item) => {
      const renderSide = firstNonEmpty(item?.render_side_scope, item?.side_scope, "Unassigned");
      const componentName = firstNonEmpty(item?.component, item?.sub_step, "Movement");
      const uncertain = Boolean(item?.is_uncertain_side);
      const groupKey = `${uncertain ? "uncertain" : "known"}|${renderSide}|${componentName}`;
      if (!groupedRows.has(groupKey)) {
        groupedRows.set(groupKey, {
          sideScope: renderSide,
          componentName,
          uncertain,
          rows: [],
        });
      }
      groupedRows.get(groupKey).rows.push(item);
    });
    groupedRows.forEach((group) => {
      const color = pickTimelineColor(group.sideScope, group.componentName);
      traces.push({
        type: "bar",
        orientation: "h",
        name: group.uncertain ? `[?] ${group.sideScope} · ${group.componentName}` : `${group.sideScope} · ${group.componentName}`,
        legendgroup: `${group.sideScope}|${group.componentName}`,
        x: group.rows.map((item) => Math.max(Number(item.duration_ms || 0), 1)),
        base: group.rows.map((item) => item.start),
        y: group.rows.map((item) => item.track || item.sub_step || "-"),
        customdata: group.rows.map((item) => [
          firstNonEmpty(item?.render_side_scope, item?.side_scope, "Unassigned"),
          firstNonEmpty(item?.component, item?.sub_step, "Movement"),
          item?.cycle_no ?? "-",
          firstNonEmpty(item?.start_time_sec, item?.start, "-"),
          firstNonEmpty(item?.end_time_sec, item?.end, "-"),
          Number(item?.duration_ms || 0),
          firstNonEmpty(item?.message, "-"),
          group.uncertain ? firstNonEmpty(item?.original_side_scope, item?.side_scope, "Unknown") : "-",
        ]),
        marker: {
          color,
          opacity: group.uncertain ? 0.42 : 0.82,
          line: { color: group.uncertain ? "#b42318" : "rgba(255,255,255,0.25)", width: group.uncertain ? 1.5 : 1 },
        },
        hovertemplate:
          "边位: %{customdata[0]}<br>" +
          "部件: %{customdata[1]}<br>" +
          "Cycle: %{customdata[2]}<br>" +
          "开始: %{customdata[3]}<br>" +
          "结束: %{customdata[4]}<br>" +
          "时长(ms): %{customdata[5]}<br>" +
          "原始边位: %{customdata[7]}<br>" +
          "说明: %{customdata[6]}<extra></extra>",
      });
    });
    const errorGroups = new Map();
    safeArray(errors).forEach((item) => {
      const severity = firstNonEmpty(item?.severity, "unknown");
      if (!errorGroups.has(severity)) {
        errorGroups.set(severity, []);
      }
      errorGroups.get(severity).push(item);
    });
    errorGroups.forEach((groupRows, severity) => {
      traces.push({
        type: "scatter",
        mode: "markers",
        name: `Error · ${severity}`,
        x: groupRows.map((item) => item.time),
        y: groupRows.map((item) => item.track || item.component || "-"),
        marker: { size: 10, symbol: "diamond", color: severity === "error" ? "#b42318" : "#bf6b3f" },
      });
    });
    return traces;
  }

  async function renderHomePage() {
    const task = getSelectedTask();
    const announcementResp = await apiRequest(`${config.apiPrefix}/announcements?limit=6`, {}, false).catch(() => ({ items: [] }));
    const announcements = safeArray(announcementResp.items);
    if (!task) {
      mountPage(
        "Home Overview",
        "Upload logs first or pick a historical task.",
        `
          ${renderCards([
            { label: "Tasks", value: formatNumber(state.tasks.length) },
            { label: "Environment", value: config.environment || "dev" },
            { label: "Current User", value: state.currentUser ? state.currentUser.username : "Guest" },
            { label: "API Prefix", value: config.apiPrefix || "/api/v1" },
          ])}
          <div class="split-grid">
            <div class="subpanel">
              <h4>Recent Announcements</h4>
              ${announcements.length ? renderAnnouncementCards(announcements.slice(0, 3), { compact: true }) : emptyState("暂无公告。")}
            </div>
            <div class="subpanel">
              <h4>Tips</h4>
              ${renderDefinitionList([
                { label: "Timeline", value: "按边拆分显示多边甘特图" },
                { label: "Parameters", value: "支持 cycle / time 横轴切换" },
                { label: "History", value: "支持下载原始上传文件" },
                { label: "Announcements", value: "支持查看编辑人和编辑时间" },
              ])}
            </div>
          </div>
        `
      );
      return;
    }
    const [status, dashboard, performance] = await Promise.all([
      apiRequest(`${config.apiPrefix}/tasks/${encodeURIComponent(task)}/status`),
      apiRequest(`${config.apiPrefix}/tasks/${encodeURIComponent(task)}/dashboard`),
      apiRequest(`${config.apiPrefix}/tasks/${encodeURIComponent(task)}/performance-summary`),
    ]);
    const topErrors = safeArray(dashboard.top_errors).slice(0, 10);
    const components = safeArray(dashboard.component_distribution);
    mountPage(
      "Home Overview",
      "Task status, density, distribution and performance summary.",
      `
        ${renderCards([
          { label: "Status", value: status.status || "-" },
          { label: "Progress", value: `${formatNumber(status.progress_percent || 0)}%` },
          { label: "Events", value: formatNumber(dashboard.total_events || 0) },
          { label: "Errors", value: formatNumber(dashboard.total_errors || 0) },
          { label: "Unique Errors", value: formatNumber(dashboard.unique_error_count || 0) },
          { label: "Stage", value: status.current_stage || "-" },
          { label: "Files", value: formatNumber(status.file_count || 0) },
          { label: "Queue", value: formatNumber(status.queue_position || "-") },
          { label: "Uploader", value: status.uploaded_by || "-" },
          { label: "Upload Size", value: status.total_size_text || formatFileSize(status.total_size_bytes) },
        ])}
        <div class="chart-grid">
          <div class="chart-card"><h4>Top Error Clusters</h4><div class="chart-box" id="homeTopErrorsChart"></div></div>
          <div class="chart-card"><h4>Component Distribution</h4><div class="chart-box" id="homeComponentsChart"></div></div>
        </div>
        <div class="split-grid">
          <div class="subpanel">
            <h4>Announcements</h4>
            ${announcements.length ? renderAnnouncementCards(announcements.slice(0, 4), { compact: true }) : emptyState("暂无公告。")}
          </div>
          <div class="subpanel">
            <h4>Task Detail</h4>
            ${renderDefinitionList([
              { label: "Task UUID", value: task },
              { label: "Filename", value: status.filename || "-" },
              { label: "Uploaded By", value: status.uploaded_by || "-" },
              { label: "File Size", value: status.total_size_text || formatFileSize(status.total_size_bytes) },
              { label: "Created At", value: formatDateTime(status.created_at) },
              { label: "Updated At", value: formatDateTime(status.updated_at) },
            ])}
          </div>
        </div>
        <div class="split-grid">
          <div class="subpanel"><h4>Dashboard</h4>${fmtJson(dashboard)}</div>
          <div class="subpanel"><h4>Performance</h4>${fmtJson(performance)}</div>
        </div>
      `,
      () => {
        if (topErrors.length) {
          drawPlot("homeTopErrorsChart", [{ type: "bar", orientation: "h", x: topErrors.map((item) => Number(item.count || 0)), y: topErrors.map((item) => clip(item.display_signature || item.normalized_signature || "-", 60)), marker: { color: "#0d5c63" } }], { yaxis: { automargin: true } });
        }
        if (components.length) {
          drawPlot("homeComponentsChart", [{ type: "pie", labels: components.map((item) => item.component || "unknown"), values: components.map((item) => Number(item.count || 0)), hole: 0.56 }]);
        }
      }
    );
  }

  async function renderHistoryPage() {
    const rows = state.tasks || [];
    const selectedTask =
      rows.find((item) => item.task_uuid === state.selectedHistoryTaskUuid) ||
      rows.find((item) => item.task_uuid === getSelectedTask()) ||
      rows[0] ||
      null;
    if (selectedTask) {
      state.selectedHistoryTaskUuid = selectedTask.task_uuid;
    }
    mountPage(
      "History Center",
      "Review uploader, file size, status and download the original uploaded package.",
      `
        <div id="historyMessage" class="inline-message"></div>
        ${renderTable(
          [
            { key: "task_uuid", label: "Task UUID", render: (row) => escapeHtml(row.task_uuid) },
            { key: "filename", label: "Filename", render: (row) => escapeHtml(safeString(row.filename, "-")) },
            { key: "uploaded_by", label: "Uploader", render: (row) => escapeHtml(safeString(row.uploaded_by, "-")) },
            { key: "total_size_text", label: "File Size", render: (row) => escapeHtml(row.total_size_text || formatFileSize(row.total_size_bytes)) },
            { key: "status", label: "Status", render: (row) => pill(row.status || "-") },
            { key: "progress_percent", label: "Progress", render: (row) => `${formatNumber(row.progress_percent || 0)}%` },
            { key: "total_errors", label: "Errors", render: (row) => formatNumber(row.total_errors || 0) },
            { key: "updated_at", label: "Updated At", render: (row) => formatDateTime(row.updated_at) },
          ],
          rows,
          [
            { action: "pick", label: "Use", group: "history" },
            { action: "download", label: "Download", group: "history" },
            { action: "delete", label: "Delete", className: "danger", group: "history" },
          ]
        )}
        <div class="split-grid" style="margin-top:16px;">
          <div class="subpanel">
            <h4>Selected Task</h4>
            ${
              selectedTask
                ? renderDefinitionList([
                    { label: "Task UUID", value: selectedTask.task_uuid },
                    { label: "Filename", value: selectedTask.filename || "-" },
                    { label: "Uploader", value: selectedTask.uploaded_by || "-" },
                    { label: "File Size", value: selectedTask.total_size_text || formatFileSize(selectedTask.total_size_bytes) },
                    { label: "Status", html: pill(selectedTask.status || "-") },
                    { label: "Progress", value: `${formatNumber(selectedTask.progress_percent || 0)}%` },
                    { label: "Errors", value: formatNumber(selectedTask.total_errors || 0) },
                    { label: "Updated At", value: formatDateTime(selectedTask.updated_at) },
                  ])
                : emptyState("暂无历史任务。")
            }
            ${
              selectedTask
                ? `<div class="button-row" style="margin-top:14px;">
                    <button type="button" id="historyUseCurrentButton">设为当前任务</button>
                    <a class="button-link ghost" href="${escapeHtml(buildDownloadUrl(`${config.apiPrefix}/tasks/${encodeURIComponent(selectedTask.task_uuid)}/download`))}" target="_blank" rel="noreferrer">下载上传文件</a>
                  </div>`
                : ""
            }
          </div>
          <div class="subpanel">
            <h4>Raw Task Payload</h4>
            ${selectedTask ? fmtJson(selectedTask) : emptyState("暂无详情。")}
          </div>
        </div>
      `,
      () => {
        hydrateActionTable("history", rows, async (action, row) => {
          const message = byId("historyMessage");
          if (!row) return;
          if (action === "pick") {
            state.selectedHistoryTaskUuid = row.task_uuid;
            saveSelectedTask(row.task_uuid);
            await refreshTasks();
            await renderHistoryPage();
            message.textContent = `Switched to ${row.task_uuid}`;
            return;
          }
          if (action === "download") {
            window.open(buildDownloadUrl(`${config.apiPrefix}/tasks/${encodeURIComponent(row.task_uuid)}/download`), "_blank", "noreferrer");
            return;
          }
          if (action === "delete") {
            if (!window.confirm(`Delete task ${row.task_uuid}?`)) return;
            await apiRequest(`${config.apiPrefix}/tasks/${encodeURIComponent(row.task_uuid)}`, { method: "DELETE" });
            if (getSelectedTask() === row.task_uuid) saveSelectedTask("");
            if (state.selectedHistoryTaskUuid === row.task_uuid) {
              state.selectedHistoryTaskUuid = "";
            }
            await refreshTasks();
            await renderHistoryPage();
            message.textContent = `Deleted task ${row.task_uuid}.`;
          }
        });
        const useCurrentButton = byId("historyUseCurrentButton");
        if (useCurrentButton && selectedTask) {
          useCurrentButton.addEventListener("click", async () => {
            saveSelectedTask(selectedTask.task_uuid);
            await refreshTasks();
            await renderHistoryPage();
            byId("historyMessage").textContent = `Switched to ${selectedTask.task_uuid}`;
          });
        }
      }
    );
  }

  async function renderUploadPage() {
    let currentStatus = null;
    if (getSelectedTask()) {
      try {
        currentStatus = await apiRequest(`${config.apiPrefix}/tasks/${encodeURIComponent(getSelectedTask())}/status`);
      } catch (_error) {
        currentStatus = null;
      }
    }
    mountPage(
      "Upload Files",
      "Upload multiple log files or archives and trigger backend analysis.",
      `
        <form id="uploadFormPage" class="form-grid">
          <label>Log Files<input id="uploadFilesPage" type="file" multiple /></label>
          <label>CPU Cores<input id="uploadCpuPage" type="number" min="1" max="16" value="1" /></label>
          <div class="button-row"><button type="submit">Upload and Analyze</button></div>
        </form>
        <div id="uploadPageMessage" class="inline-message"></div>
        <div id="uploadPageResult"></div>
        ${currentStatus ? `<div class="subpanel" style="margin-top:16px;">${fmtJson(currentStatus)}</div>` : ""}
      `,
      () => {
        byId("uploadFormPage").addEventListener("submit", async (event) => {
          event.preventDefault();
          const files = byId("uploadFilesPage").files;
          const message = byId("uploadPageMessage");
          if (!files || !files.length) {
            message.textContent = "Select files first.";
            return;
          }
          const formData = new FormData();
          Array.from(files).forEach((file) => formData.append("files", file));
          formData.append("cpu_cores", byId("uploadCpuPage").value || "1");
          message.textContent = "Creating analysis task...";
          const result = await apiRequest(`${config.apiPrefix}/tasks/upload`, { method: "POST", body: formData });
          byId("uploadPageResult").innerHTML = fmtJson(result);
          message.textContent = `Created task: ${result.task_uuid}`;
          saveSelectedTask(result.task_uuid);
          await refreshTasks();
        });
      }
    );
  }

  async function renderEventsPage() {
    const task = requireTask();
    const [cycles, events] = await Promise.all([
      apiRequest(`${config.apiPrefix}/tasks/${encodeURIComponent(task)}/cycles`),
      apiRequest(`${config.apiPrefix}/tasks/${encodeURIComponent(task)}/events?limit=120&offset=0`),
    ]);
    mountPage("Events", "Unified event stream and cycle context.", `<div class="split-grid"><div class="subpanel"><h4>Cycles</h4>${fmtJson(cycles)}</div><div class="subpanel"><h4>Events</h4>${fmtJson(events)}</div></div>`);
  }

  async function renderTimingPage() {
    const task = requireTask();
    const [cycleSummary, steps, operationalMetrics, validation] = await Promise.all([
      apiRequest(`${config.apiPrefix}/tasks/${encodeURIComponent(task)}/cycle-summary?unit=ms`),
      apiRequest(`${config.apiPrefix}/tasks/${encodeURIComponent(task)}/steps?limit=200&offset=0`),
      apiRequest(`${config.apiPrefix}/tasks/${encodeURIComponent(task)}/operational-metrics`),
      apiRequest(`${config.apiPrefix}/tasks/${encodeURIComponent(task)}/temperature-cycle-validation`),
    ]);
    const rows = Array.isArray(cycleSummary) ? cycleSummary : [];
    mountPage(
      "Timing Analysis",
      "Cycle timing, step details and operational metrics.",
      `
        ${renderCards([
          { label: "Cycles", value: formatNumber(rows.length) },
          { label: "Steps", value: formatNumber((steps.items || []).length) },
          { label: "Photo Summary", value: formatNumber((operationalMetrics.photo_summary || []).length) },
          { label: "Unit", value: "ms" },
        ])}
        <div class="chart-grid"><div class="chart-card"><h4>Cycle Duration</h4><div class="chart-box" id="timingCycleChart"></div></div></div>
        ${renderTabs("timingTabs", [
          { key: "steps", label: "Steps", content: fmtJson(steps) },
          { key: "metrics", label: "Metrics", content: fmtJson(operationalMetrics) },
          { key: "validation", label: "Validation", content: fmtJson(validation) },
        ])}
      `,
      () => {
        if (rows.length) {
          drawPlot("timingCycleChart", [{ type: "scatter", mode: "lines+markers", x: rows.map((item) => item.cycle_no), y: rows.map((item) => Number(item.total_duration_value || 0)), marker: { color: "#0d5c63" } }], { xaxis: { title: "Cycle" }, yaxis: { title: "ms" } });
        }
      }
    );
  }

  async function renderTimelinePage() {
    const task = requireTask();
    const [cycles, scopeCatalog] = await Promise.all([
      apiRequest(`${config.apiPrefix}/tasks/${encodeURIComponent(task)}/cycles`),
      apiRequest(`${config.apiPrefix}/tasks/${encodeURIComponent(task)}/scope-catalog`),
    ]);
    const query = new URLSearchParams();
    if (state.timelineFilters.cycleNo) {
      query.set("cycle_no", state.timelineFilters.cycleNo);
    }
    if (state.timelineFilters.trackOrder) {
      query.set("track_order", state.timelineFilters.trackOrder);
    }
    if (state.timelineFilters.trackGranularity) {
      query.set("track_granularity", state.timelineFilters.trackGranularity);
    }
    if (state.timelineFilters.sideScope && state.timelineFilters.sideScope !== "all") {
      query.set("side_scope", state.timelineFilters.sideScope);
    }
    const [rows, errorRows] = await Promise.all([
      apiRequest(`${config.apiPrefix}/tasks/${encodeURIComponent(task)}/movement-timeline?${query.toString()}`),
      apiRequest(`${config.apiPrefix}/tasks/${encodeURIComponent(task)}/movement-timeline/errors?${query.toString()}`),
    ]);
    const movementPayload = safeObject(rows);
    const errorPayload = safeObject(errorRows);
    const sideGroups = safeArray(movementPayload.by_side);
    const errorBySide = new Map(safeArray(errorPayload.by_side).map((item) => [item.side_scope || "", safeArray(item.points)]));
    const sideOptions = [{ value: "all", label: "All sides" }].concat(
      safeArray(scopeCatalog.sides).map((item) => ({ value: item.value, label: item.label || item.value }))
    );
    mountPage(
      "Timeline",
      "View separate movement timelines per side. Uncertain rows stay visible and are highlighted inside each side chart.",
      `
        ${renderCards([
          { label: "Movements", value: formatNumber(safeArray(movementPayload.rows).length) },
          { label: "Error Points", value: formatNumber(safeArray(errorPayload.points).length) },
          { label: "Sides", value: formatNumber(sideGroups.length) },
          { label: "Uncertain Rows", value: formatNumber(safeArray(movementPayload.unassigned_side_rows).length) },
          { label: "Task", value: task },
        ])}
        <div class="inline-form">
          <label>Cycle
            <select id="timelineCycleSelect">
              <option value="">All</option>
              ${safeArray(cycles).map((value) => `<option value="${escapeHtml(value)}" ${String(state.timelineFilters.cycleNo) === String(value) ? "selected" : ""}>${escapeHtml(value)}</option>`).join("")}
            </select>
          </label>
          <label>Side
            <select id="timelineSideSelect">
              ${sideOptions.map((item) => `<option value="${escapeHtml(item.value)}" ${state.timelineFilters.sideScope === item.value ? "selected" : ""}>${escapeHtml(item.label)}</option>`).join("")}
            </select>
          </label>
          <label>Track Granularity
            <select id="timelineGranularitySelect">
              ${["component", "side", "side_chip"].map((value) => `<option value="${value}" ${state.timelineFilters.trackGranularity === value ? "selected" : ""}>${escapeHtml(value)}</option>`).join("")}
            </select>
          </label>
          <label>Track Order
            <select id="timelineOrderSelect">
              ${["default", "cycle"].map((value) => `<option value="${value}" ${state.timelineFilters.trackOrder === value ? "selected" : ""}>${escapeHtml(value)}</option>`).join("")}
            </select>
          </label>
        </div>
        <div class="chart-stack">
          ${
            sideGroups.length
              ? sideGroups
                  .map((group, index) => `
                    <div class="chart-card">
                      <h4>Timeline · ${escapeHtml(firstNonEmpty(group.side_label, group.side_scope, "Unassigned"))}</h4>
                      <p class="small-note">
                        ${Number(group.uncertain_count || 0) > 0 ? `Includes ${Number(group.uncertain_count || 0)} uncertain-side rows highlighted below.` : "Only rows assigned to this side are shown."}
                      </p>
                      <div class="chart-box" id="timelineChart_${index}"></div>
                    </div>
                  `)
                  .join("")
              : emptyState("No timeline rows match the current filters.")
          }
        </div>
        ${renderTabs("timelineTabs", [
          { key: "movements", label: "Movement Payload", content: fmtJson(movementPayload) },
          { key: "errors", label: "Error Payload", content: fmtJson(errorPayload) },
        ])}
      `,
      () => {
        [["timelineCycleSelect", "cycleNo"], ["timelineSideSelect", "sideScope"], ["timelineGranularitySelect", "trackGranularity"], ["timelineOrderSelect", "trackOrder"]].forEach(([id, key]) => {
          const target = byId(id);
          if (!target) {
            return;
          }
          target.addEventListener("change", async () => {
            state.timelineFilters[key] = target.value;
            await renderTimelinePage();
          });
        });
        sideGroups.forEach((group, index) => {
          const traces = buildTimelineTraces(group.rows, errorBySide.get(group.side_scope || ""));
          if (!traces.length) {
            return;
          }
          drawPlot(`timelineChart_${index}`, traces, {
            barmode: "overlay",
            xaxis: { type: "date", title: "Original Log Time" },
            yaxis: { automargin: true, autorange: "reversed" },
          });
        });
      }
    );
  }

  async function renderErrorsPage() {
    const task = requireTask();
    const errors = await apiRequest(`${config.apiPrefix}/tasks/${encodeURIComponent(task)}/errors?limit=200&offset=0`);
    const rows = Array.isArray(errors.items) ? errors.items : Array.isArray(errors) ? errors : [];
    const signature = rows[0] ? rows[0].normalized_signature : "";
    const trend = signature ? await apiRequest(`${config.apiPrefix}/tasks/${encodeURIComponent(task)}/errors/trend?signature=${encodeURIComponent(signature)}&bucket=day`) : [];
    mountPage(
      "Error Analysis",
      "Error clusters, trends and representative samples.",
      `
        ${renderCards([
          { label: "Error Clusters", value: formatNumber(rows.length) },
          { label: "Trend Points", value: formatNumber((trend || []).length) },
          { label: "Signature", value: signature || "-" },
          { label: "Task", value: task },
        ])}
        <div class="chart-grid">
          <div class="chart-card"><h4>Top Error Clusters</h4><div class="chart-box" id="errorsTopChart"></div></div>
          <div class="chart-card"><h4>Error Trend</h4><div class="chart-box" id="errorsTrendChart"></div></div>
        </div>
        <div class="split-grid"><div class="subpanel"><h4>Error List</h4>${fmtJson(rows)}</div><div class="subpanel"><h4>Trend Detail</h4>${fmtJson(trend)}</div></div>
      `,
      () => {
        if (rows.length) {
          const top = rows.slice(0, 12);
          drawPlot("errorsTopChart", [{ type: "bar", orientation: "h", x: top.map((item) => Number(item.count || 0)), y: top.map((item) => clip(item.display_signature || item.normalized_signature || "-", 60)), marker: { color: "#bf6b3f" } }], { yaxis: { automargin: true } });
        }
        if (trend && trend.length) {
          drawPlot("errorsTrendChart", [{ type: "scatter", mode: "lines+markers", x: trend.map((item) => item.bucket || item.date || item.ts), y: trend.map((item) => Number(item.count || 0)), marker: { color: "#0d5c63" } }]);
        }
      }
    );
  }

  async function renderParametersPage() {
    const task = requireTask();
    const [definitions, scopeCatalog] = await Promise.all([
      apiRequest(`${config.apiPrefix}/parameter-definitions`),
      apiRequest(`${config.apiPrefix}/tasks/${encodeURIComponent(task)}/scope-catalog`),
    ]);
    const items = safeArray(Array.isArray(definitions) ? definitions : definitions.items).filter((item) => item?.parameter_name !== "imaging_time");
    if (!state.parameterFilters.parameterName && items[0]) {
      state.parameterFilters.parameterName = items[0].parameter_name;
    }
    const sideScope = state.parameterFilters.sideScope !== "all" ? state.parameterFilters.sideScope : "";
    const parameterQuery = new URLSearchParams({
      unit: state.parameterFilters.unit,
      axis_mode: state.parameterFilters.axisMode,
    });
    if (sideScope) {
      parameterQuery.set("side_scope", sideScope);
    }
    const payload = {
      parameter_definitions: items,
      parameter_series: state.parameterFilters.parameterName
        ? await apiRequest(`${config.apiPrefix}/tasks/${encodeURIComponent(task)}/parameter-series/${encodeURIComponent(state.parameterFilters.parameterName)}?${parameterQuery.toString()}`)
        : [],
      row_scan_metric_series: await apiRequest(`${config.apiPrefix}/tasks/${encodeURIComponent(task)}/row-scan-metric-series?unit=ms&axis_mode=${encodeURIComponent(state.parameterFilters.axisMode)}${sideScope ? `&side_scope=${encodeURIComponent(sideScope)}` : ""}`),
      substep_cycle_series: await apiRequest(`${config.apiPrefix}/tasks/${encodeURIComponent(task)}/substep-cycle-series?agg_mode=mean&unit=${encodeURIComponent(state.parameterFilters.unit)}&axis_mode=${encodeURIComponent(state.parameterFilters.axisMode)}${sideScope ? `&side_scope=${encodeURIComponent(sideScope)}` : ""}`),
    };
    const parameterRows = safeArray(payload.parameter_series);
    const substepRows = safeArray(payload.substep_cycle_series);
    const metricRows = safeArray(payload.row_scan_metric_series);
    const sideOptions = [{ value: "all", label: "All sides" }].concat(
      safeArray(scopeCatalog.sides).map((item) => ({ value: item.value, label: item.label || item.value }))
    );
    mountPage(
      "Parameter Analysis",
      "Switch parameter axis between cycle and original log time, with optional side filtering.",
      `
        ${renderCards([
          { label: "Definitions", value: formatNumber(items.length) },
          { label: "Current Parameter", value: state.parameterFilters.parameterName || "-" },
          { label: "Axis Mode", value: state.parameterFilters.axisMode },
          { label: "Series Points", value: formatNumber(parameterRows.length) },
          { label: "Sub-step Points", value: formatNumber(substepRows.length) },
          { label: "Row Scan Points", value: formatNumber(metricRows.length) },
        ])}
        <div class="inline-form">
          <label>Parameter
            <select id="parameterNameSelect">
              ${items.map((item) => `<option value="${escapeHtml(item.parameter_name)}" ${state.parameterFilters.parameterName === item.parameter_name ? "selected" : ""}>${escapeHtml(item.parameter_name)}</option>`).join("")}
            </select>
          </label>
          <label>Axis Mode
            <select id="parameterAxisModeSelect">
              ${["cycle", "time"].map((value) => `<option value="${value}" ${state.parameterFilters.axisMode === value ? "selected" : ""}>${escapeHtml(value)}</option>`).join("")}
            </select>
          </label>
          <label>Unit
            <select id="parameterUnitSelect">
              ${["ms", "s", "min", "h"].map((value) => `<option value="${value}" ${state.parameterFilters.unit === value ? "selected" : ""}>${escapeHtml(value)}</option>`).join("")}
            </select>
          </label>
          <label>Side
            <select id="parameterSideSelect">
              ${sideOptions.map((item) => `<option value="${escapeHtml(item.value)}" ${state.parameterFilters.sideScope === item.value ? "selected" : ""}>${escapeHtml(item.label)}</option>`).join("")}
            </select>
          </label>
        </div>
        <div class="chart-grid">
          <div class="chart-card"><h4>Parameter Series</h4><div class="chart-box" id="parameterSeriesChart"></div></div>
          <div class="chart-card"><h4>Sub-step / Cycle</h4><div class="chart-box" id="parameterSubstepChart"></div></div>
        </div>
        <div class="chart-grid">
          <div class="chart-card"><h4>Row Scan Metrics</h4><div class="chart-box" id="parameterMetricChart"></div></div>
          <div class="chart-card"><h4>Definition Detail</h4>${fmtJson(items.find((item) => item.parameter_name === state.parameterFilters.parameterName) || {})}</div>
        </div>
        ${renderTabs("parameterTabs", [
          { key: "definitions", label: "Definitions", content: fmtJson(items) },
          { key: "rowScan", label: "Row Scan", content: fmtJson(metricRows) },
          { key: "raw", label: "Raw", content: fmtJson(payload) },
        ])}
      `,
      () => {
        [["parameterNameSelect", "parameterName"], ["parameterAxisModeSelect", "axisMode"], ["parameterUnitSelect", "unit"], ["parameterSideSelect", "sideScope"]].forEach(([id, key]) => {
          const target = byId(id);
          if (!target) {
            return;
          }
          target.addEventListener("change", async () => {
            state.parameterFilters[key] = target.value;
            await renderParametersPage();
          });
        });
        if (parameterRows.length) {
          drawPlot("parameterSeriesChart", buildLineSeries(parameterRows, "x_axis_label", "duration_value", "series_name"), {
            xaxis: { title: state.parameterFilters.axisMode === "time" ? "Original Log Time" : "Cycle" },
          });
        }
        if (substepRows.length) {
          drawPlot("parameterSubstepChart", buildLineSeries(substepRows, "x_axis_label", "duration_value", "series_name"), {
            xaxis: { title: state.parameterFilters.axisMode === "time" ? "Original Log Time" : "Cycle" },
          });
        }
        if (metricRows.length) {
          drawPlot("parameterMetricChart", buildLineSeries(metricRows, "x_axis_label", "duration_value", "series_name"), {
            xaxis: { title: state.parameterFilters.axisMode === "time" ? "Original Log Time" : "Cycle" },
          });
        }
      }
    );
  }

  async function renderDiagnosisPage() {
    const task = requireTask();
    const [errors, repoConfig, historyRows, configData] = await Promise.all([
      apiRequest(`${config.apiPrefix}/tasks/${encodeURIComponent(task)}/errors?limit=200&offset=0`),
      apiRequest(`${config.apiPrefix}/solution-repository/config`),
      apiRequest(`${config.apiPrefix}/tasks/${encodeURIComponent(task)}/llm-results`),
      apiRequest(`${config.apiPrefix}/config`),
    ]);

    const errorRows = Array.isArray(errors.items) ? errors.items : Array.isArray(errors) ? errors : [];
    const historyItems = Array.isArray(historyRows.items) ? historyRows.items : Array.isArray(historyRows) ? historyRows : [];
    const moduleTree = Array.isArray(repoConfig.module_tree) ? repoConfig.module_tree : [];
    const moduleOptions = moduleTree.map((item) => item.name).filter(Boolean);
    const depthConfig = configData && configData.llm && configData.llm.analysis_depths ? configData.llm.analysis_depths : {};
    const depthOptions = Object.keys(depthConfig);

    if (!errorRows.length) {
      mountPage("LLM 诊断", "当前任务暂无可诊断的错误簇。", emptyState("当前任务暂无可诊断的错误簇。"));
      return;
    }

    if (!state.solutionDraft.error_name) {
      state.solutionDraft.error_name = safeString(errorRows[0].display_signature || errorRows[0].normalized_signature || "").slice(0, 80);
    }

    mountPage(
      "LLM 诊断",
      "历史诊断、综合诊断、已有方案录入、方案库和审核中心。",
      renderTabs("diagnosisTabs", [
        {
          key: "history",
          label: "历史诊断",
          content: `
            <div class="inline-form">
              <label>签名过滤
                <select id="diagHistorySignatureFilter">
                  <option value="">全部</option>
                  ${Array.from(new Set(historyItems.map((item) => item.normalized_signature).filter(Boolean)))
                    .map((signature) => `<option value="${escapeHtml(signature)}">${escapeHtml(clip(signature, 90))}</option>`)
                    .join("")}
                </select>
              </label>
              <button id="diagHistoryRefresh" type="button">刷新历史诊断</button>
            </div>
            <div id="diagHistorySummary"></div>
            <div class="split-grid">
              <div class="subpanel"><h4>历史记录</h4><div id="diagHistoryTable"></div></div>
              <div class="subpanel"><h4>选中记录详情</h4><div id="diagHistoryDetail"></div></div>
            </div>
          `,
        },
        {
          key: "diagnose",
          label: "综合诊断",
          content: `
            <form id="diagnosisFormPage" class="form-grid">
              <div class="triple-grid">
                <label>错误簇
                  <select id="diagnosisSignaturePage">
                    ${errorRows
                      .map(
                        (row) => `
                          <option value="${escapeHtml(row.normalized_signature)}">
                            ${escapeHtml(clip(`${row.display_signature || row.normalized_signature} | count=${row.count || 0}`, 100))}
                          </option>
                        `
                      )
                      .join("")}
                  </select>
                </label>
                <label>分析深度
                  <select id="diagnosisDepthPage">
                    ${(depthOptions.length ? depthOptions : ["low", "medium", "high"])
                      .map((depth) => `<option value="${escapeHtml(depth)}" ${depth === "medium" ? "selected" : ""}>${escapeHtml(depth)}</option>`)
                      .join("")}
                  </select>
                </label>
                <label>模块
                  <select id="diagnosisModulePage">
                    ${(moduleOptions.length ? moduleOptions : ["软件控制"])
                      .map((item) => `<option value="${escapeHtml(item)}">${escapeHtml(item)}</option>`)
                      .join("")}
                  </select>
                </label>
              </div>
              <div class="split-grid">
                <label>子模块<input id="diagnosisSubmodulePage" /></label>
                <label>前端等待超时(秒)<input id="diagnosisTimeoutPage" type="number" min="30" max="300" value="120" /></label>
              </div>
              <label>触发场景<textarea id="diagnosisScenarioPage"></textarea></label>
              <div class="split-grid">
                <label>操作路径 / 前置动作<textarea id="diagnosisOperationPathPage"></textarea></label>
                <label>客户现象<textarea id="diagnosisCustomerSymptomPage"></textarea></label>
              </div>
              <div class="split-grid">
                <label>环境信息<textarea id="diagnosisEnvironmentInfoPage"></textarea></label>
                <label>复现步骤<textarea id="diagnosisReproductionStepsPage"></textarea></label>
              </div>
              <label>源码补充说明<textarea id="diagnosisSourceNotesPage"></textarea></label>
              <label>源码附件<input id="diagnosisFilesPage" type="file" multiple /></label>
              <label class="checkbox-row"><input id="diagnosisForcePage" type="checkbox" />忽略缓存，重新调用 LLM</label>
              <div class="button-row">
                <button type="submit">开始综合诊断</button>
                <button id="loadDiagnosisHistoryButton" type="button" class="ghost">加载历史结果</button>
                <button id="loadSimilarCasesButton" type="button" class="ghost">检索相似案例</button>
                <button id="submitDiagnosisReviewButton" type="button" class="ghost">提交入库审核</button>
              </div>
            </form>
            <div id="diagnosisPageMessage" class="inline-message"></div>
            <div id="diagnosisTopSummary"></div>
            <div class="split-grid">
              <div class="subpanel"><h4>方案录入草稿</h4>${renderSolutionDraftForm("diagnosisDraft")}</div>
              <div class="subpanel"><h4>诊断输出</h4><div id="diagnosisOutput"></div></div>
            </div>
          `,
        },
        {
          key: "entry",
          label: "已有方案录入",
          content: `
            <div class="subpanel">
              <h4>方案录入字段</h4>
              ${renderSolutionDraftForm("solutionDraft")}
              <div class="button-row" style="margin-top:14px;"><button id="saveSolutionDraftButton" type="button">保存当前草稿</button></div>
              <p id="solutionDraftMessage" class="inline-message"></p>
            </div>
          `,
        },
        {
          key: "repo",
          label: "解决方案库",
          content: `
            <form id="diagRepoForm" class="inline-form">
              <label>关键字<input id="diagRepoSearch" /></label>
              <label>模块
                <select id="diagRepoModule">
                  <option value="">全部</option>
                  ${moduleOptions.map((item) => `<option value="${escapeHtml(item)}">${escapeHtml(item)}</option>`).join("")}
                </select>
              </label>
              <label>审核状态
                <select id="diagRepoStatus">
                  <option value="">全部</option>
                  <option value="approved">approved</option>
                  <option value="needs_revision">needs_revision</option>
                  <option value="rejected">rejected</option>
                </select>
              </label>
              <button type="submit">查询方案库</button>
            </form>
            <div class="button-row">
              <a class="button-link ghost" href="${escapeHtml(buildDownloadUrl(`${config.apiPrefix}/solution-repository/export?format=json`))}" target="_blank" rel="noreferrer">导出 JSON</a>
              <a class="button-link ghost" href="${escapeHtml(buildDownloadUrl(`${config.apiPrefix}/solution-repository/export?format=csv`))}" target="_blank" rel="noreferrer">导出 CSV</a>
              <a class="button-link ghost" href="${escapeHtml(buildDownloadUrl(`${config.apiPrefix}/solution-repository/export?format=xlsx`))}" target="_blank" rel="noreferrer">导出 Excel</a>
              <a class="button-link ghost" href="${escapeHtml(buildDownloadUrl(`${config.apiPrefix}/solution-repository/export?format=sqlite`))}" target="_blank" rel="noreferrer">导出 SQLite</a>
            </div>
            <div class="split-grid">
              <div class="subpanel"><h4>方案列表</h4><div id="diagRepoTable"></div></div>
              <div class="subpanel"><h4>方案编辑</h4><div id="diagRepoEditor"></div></div>
            </div>
          `,
        },
        {
          key: "review",
          label: "审核中心",
          content: `
            <form id="diagReviewForm" class="inline-form">
              <label>审核状态
                <select id="diagReviewStatus">
                  <option value="">全部</option>
                  <option value="pending_review">pending_review</option>
                  <option value="approved">approved</option>
                  <option value="needs_revision">needs_revision</option>
                  <option value="rejected">rejected</option>
                </select>
              </label>
              <button type="submit">刷新审核记录</button>
            </form>
            <div class="split-grid">
              <div class="subpanel"><h4>审核记录</h4><div id="diagReviewTable"></div></div>
              <div class="subpanel"><h4>人工审核</h4><div id="diagReviewEditor"></div></div>
            </div>
          `,
        },
      ]),
      () => {
        const renderHistory = async () => {
          const selectedSignature = byId("diagHistorySignatureFilter").value;
          const filtered = selectedSignature ? historyItems.filter((item) => item.normalized_signature === selectedSignature) : historyItems;
          byId("diagHistorySummary").innerHTML = renderCards([
            { label: "历史记录数", value: formatNumber(filtered.length) },
            { label: "筛选签名", value: selectedSignature || "全部" },
            { label: "最近诊断时间", value: filtered[0] ? formatDateTime(filtered[0].created_at) : "-" },
            { label: "最近状态", value: filtered[0] ? filtered[0].llm_status || "-" : "-" },
          ]);
          byId("diagHistoryTable").innerHTML = renderTable(
            [
              { key: "normalized_signature", label: "签名", render: (row) => escapeHtml(clip(row.normalized_signature || "-", 84)) },
              { key: "analysis_stage", label: "深度", render: (row) => escapeHtml(safeString(row.analysis_stage, "-")) },
              { key: "prompt_version", label: "Prompt", render: (row) => escapeHtml(safeString(row.prompt_version, "-")) },
              { key: "llm_status", label: "LLM 状态", render: (row) => pill(row.llm_status || "-") },
              { key: "created_at", label: "创建时间", render: (row) => formatDateTime(row.created_at) },
            ],
            filtered,
            [{ action: "pick", label: "查看", group: "diagHistory" }]
          );
          hydrateActionTable("diagHistory", filtered, async (_action, row) => {
            if (!row) return;
            byId("diagHistoryDetail").innerHTML = renderTabs("diagHistoryDetailTabs", [
              { key: "summary", label: "结构化结果", content: fmtJson((row.response_payload || {}).structured_result || row.response_payload || {}) },
              { key: "context", label: "上下文摘要", content: fmtJson(row.context_summary || {}) },
              { key: "source", label: "源码片段", content: fmtJson(row.source_context_snippets || []) },
              { key: "cases", label: "相似案例", content: fmtJson(row.similar_cases || []) },
              { key: "raw", label: "完整片段", content: fmtJson(row) },
            ]);
            hydrateTabs(byId("diagHistoryDetail"));
          });
          byId("diagHistoryDetail").innerHTML = filtered[0] ? fmtJson(filtered[0]) : emptyState("暂无历史诊断。");
        };

        const renderRepo = async () => {
          const query = new URLSearchParams({ limit: "200" });
          const search = byId("diagRepoSearch").value.trim();
          const module = byId("diagRepoModule").value;
          const reviewStatus = byId("diagRepoStatus").value;
          if (search) query.set("search", search);
          if (module) query.set("module", module);
          if (reviewStatus) query.set("review_status", reviewStatus);
          const repoRows = await apiRequest(`${config.apiPrefix}/solution-repository/records?${query.toString()}`);
          const items = Array.isArray(repoRows.items) ? repoRows.items : [];
          byId("diagRepoTable").innerHTML = renderTable(
            [
              { key: "id", label: "ID", render: (row) => formatNumber(row.id) },
              { key: "error_name", label: "错误名", render: (row) => escapeHtml(clip(row.error_name || "-", 60)) },
              { key: "module", label: "模块", render: (row) => escapeHtml(safeString(row.module, "-")) },
              { key: "review_status", label: "审核状态", render: (row) => pill(row.review_status || "-") },
              { key: "updated_at", label: "更新时间", render: (row) => formatDateTime(row.updated_at) },
            ],
            items,
            [{ action: "edit", label: "编辑", group: "diagRepo" }]
          );
          hydrateActionTable("diagRepo", items, async (_action, row) => {
            if (!isReviewer()) {
              byId("diagRepoEditor").innerHTML = emptyState("当前账号没有编辑方案库的权限。");
              return;
            }
            byId("diagRepoEditor").innerHTML = `
              <label>根因分析<textarea id="diagRepoRoot">${escapeHtml(row.root_cause_analysis || "")}</textarea></label>
              <label>已验证解决方案<textarea id="diagRepoSolution">${escapeHtml(row.verified_solution || "")}</textarea></label>
              <label>临时绕过方案<textarea id="diagRepoWorkaround">${escapeHtml(row.workaround || "")}</textarea></label>
              <label class="checkbox-row"><input id="diagRepoReusable" type="checkbox" ${row.reusable ? "checked" : ""} />可复用</label>
              <div class="button-row"><button id="diagRepoSaveButton" type="button">保存当前记录</button></div>
              <p id="diagRepoMessage" class="inline-message"></p>
              ${fmtJson(row)}
            `;
            byId("diagRepoSaveButton").addEventListener("click", async () => {
              const payloadToSave = {
                ...row,
                root_cause_analysis: byId("diagRepoRoot").value,
                verified_solution: byId("diagRepoSolution").value,
                workaround: byId("diagRepoWorkaround").value,
                reusable: byId("diagRepoReusable").checked,
              };
              const resp = await apiJson(`${config.apiPrefix}/solution-repository/records/${encodeURIComponent(row.id)}`, "PUT", payloadToSave);
              byId("diagRepoMessage").textContent = `记录 ${resp.item.id} 已更新。`;
            });
          });
          if (!items.length) {
            byId("diagRepoEditor").innerHTML = emptyState("当前没有符合条件的方案记录。");
          }
        };

        const renderReviewCenter = async () => {
          const status = byId("diagReviewStatus").value;
          const query = new URLSearchParams({ limit: "200" });
          if (status) query.set("status", status);
          const reviewRows = await apiRequest(`${config.apiPrefix}/solution-reviews?${query.toString()}`);
          const items = Array.isArray(reviewRows.items) ? reviewRows.items : [];
          byId("diagReviewTable").innerHTML = renderTable(
            [
              { key: "id", label: "ID", render: (row) => formatNumber(row.id) },
              { key: "review_status", label: "审核状态", render: (row) => pill(row.review_status || "-") },
              { key: "module", label: "模块", render: (row) => escapeHtml(safeString(row.module, "-")) },
              { key: "normalized_signature", label: "签名", render: (row) => escapeHtml(clip(row.normalized_signature || "-", 70)) },
              { key: "updated_at", label: "更新时间", render: (row) => formatDateTime(row.updated_at) },
            ],
            items,
            [{ action: "review", label: "审核", group: "diagReview" }]
          );
          hydrateActionTable("diagReview", items, async (_action, row) => {
            if (!isReviewer()) {
              byId("diagReviewEditor").innerHTML = emptyState("当前账号没有人工审核权限。");
              return;
            }
            byId("diagReviewEditor").innerHTML = `
              ${fmtJson(row)}
              <label>人工复核人<input id="diagReviewReviewer" value="${escapeHtml(state.currentUser ? state.currentUser.username : "")}" /></label>
              <label>审核意见<textarea id="diagReviewNotes"></textarea></label>
              <div class="button-row">
                <button data-manual-status="approved" type="button">人工通过</button>
                <button data-manual-status="needs_revision" class="warn" type="button">退回修改</button>
                <button data-manual-status="rejected" class="danger" type="button">拒绝入库</button>
              </div>
              <p id="diagReviewMessage" class="inline-message"></p>
            `;
            qsa("[data-manual-status]", byId("diagReviewEditor")).forEach((button) => {
              button.addEventListener("click", async () => {
                const reviewStatus = button.getAttribute("data-manual-status");
                const resp = await apiJson(`${config.apiPrefix}/solution-reviews/${encodeURIComponent(row.id)}/manual-review`, "POST", {
                  review_status: reviewStatus,
                  reviewer: byId("diagReviewReviewer").value.trim(),
                  notes: byId("diagReviewNotes").value,
                });
                byId("diagReviewMessage").textContent = `审核记录 ${resp.item.id} 已更新为 ${reviewStatus}。`;
              });
            });
          });
          if (!items.length) {
            byId("diagReviewEditor").innerHTML = emptyState("当前没有审核记录。");
          }
        };

        const renderLatestDiagnosis = (result) => {
          if (!result) {
            byId("diagnosisOutput").innerHTML = emptyState("还没有诊断结果。");
            byId("diagnosisTopSummary").innerHTML = "";
            return;
          }
          byId("diagnosisTopSummary").innerHTML = renderCards([
            { label: "分析深度", value: result.analysis_stage || "-" },
            { label: "缓存命中", value: result.from_cache ? "是" : "否" },
            { label: "LLM 状态", value: result.llm_status || "-" },
            { label: "总 Token", value: formatNumber((result.token_summary || {}).final_total_tokens || "-") },
          ]);
          byId("diagnosisOutput").innerHTML = `
            ${result.chinese_summary ? `<div class="result-note">${escapeHtml(result.chinese_summary)}</div>` : ""}
            ${renderTabs("diagResultTabs", [
              { key: "structured", label: "结构化结果", content: fmtJson(result.structured_result || {}) },
              { key: "context", label: "日志与证据摘要", content: fmtJson(result.context_summary || {}) },
              { key: "source", label: "源码片段", content: fmtJson(result.source_context_snippets || []) },
              { key: "cases", label: "相似案例", content: fmtJson(result.similar_cases || []) },
              { key: "raw", label: "请求/响应", content: fmtJson({ request_payload: result.request_payload || {}, response_payload: result.response_payload || {} }) },
            ])}
            ${state.latestReviewResult ? `<h4 style="margin-top:16px;">最近审核提交结果</h4>${fmtJson(state.latestReviewResult)}` : ""}
          `;
          hydrateTabs(byId("diagnosisOutput"));
        };

        byId("diagHistoryRefresh").addEventListener("click", async () => renderHistory());
        byId("diagHistorySignatureFilter").addEventListener("change", async () => renderHistory());
        byId("saveSolutionDraftButton").addEventListener("click", () => {
          readSolutionDraftFromInputs("solutionDraft");
          byId("solutionDraftMessage").textContent = "方案草稿已更新。";
        });
        byId("diagRepoForm").addEventListener("submit", async (event) => {
          event.preventDefault();
          await renderRepo();
        });
        byId("diagReviewForm").addEventListener("submit", async (event) => {
          event.preventDefault();
          await renderReviewCenter();
        });
        byId("loadDiagnosisHistoryButton").addEventListener("click", async () => {
          const result = await apiRequest(`${config.apiPrefix}/tasks/${encodeURIComponent(task)}/llm-results`);
          byId("diagnosisOutput").innerHTML = fmtJson(result);
        });
        byId("loadSimilarCasesButton").addEventListener("click", async () => {
          const signature = byId("diagnosisSignaturePage").value;
          const moduleValue = byId("diagnosisModulePage").value;
          const triggerScenario = byId("diagnosisScenarioPage").value.trim();
          const url = new URL(`${config.apiPrefix}/tasks/${encodeURIComponent(task)}/errors/${encodeURIComponent(signature)}/similar-cases`, window.location.origin);
          if (moduleValue) url.searchParams.set("module", moduleValue);
          if (triggerScenario) url.searchParams.set("trigger_scenario", triggerScenario);
          const result = await apiRequest(`${url.pathname}${url.search}`);
          state.latestSimilarCases = Array.isArray(result.items) ? result.items : [];
          byId("diagnosisOutput").innerHTML = fmtJson(result);
        });
        byId("submitDiagnosisReviewButton").addEventListener("click", async () => {
          readSolutionDraftFromInputs("diagnosisDraft");
          const signature = byId("diagnosisSignaturePage").value;
          const selectedRow = errorRows.find((item) => item.normalized_signature === signature) || errorRows[0];
          const payloadToSubmit = {
            task_uuid: task,
            submission_type: "solution_record",
            error_name: state.solutionDraft.error_name || safeString(selectedRow.display_signature || signature, "").slice(0, 80),
            error_category: state.solutionDraft.error_category,
            module: byId("diagnosisModulePage").value,
            submodule: byId("diagnosisSubmodulePage").value.trim() || null,
            error_code: state.solutionDraft.error_code,
            message: safeString(selectedRow.representative_message || selectedRow.display_signature || ""),
            normalized_signature: signature,
            exception_description: safeString(selectedRow.error_family_display || selectedRow.error_family || ""),
            trigger_scenario: byId("diagnosisScenarioPage").value,
            impact_scope: state.solutionDraft.impact_scope,
            report_source: `task:${task}`,
            related_logs: {
              display_signature: selectedRow.display_signature,
              representative_message: selectedRow.representative_message,
              count: selectedRow.count,
            },
            related_source_files: state.latestDiagnosisResult ? state.latestDiagnosisResult.source_context_snippets || [] : [],
            root_cause_analysis: state.solutionDraft.root_cause_analysis,
            verified_solution: state.solutionDraft.verified_solution,
            workaround: state.solutionDraft.workaround,
            owner_department: state.solutionDraft.owner_department,
            submitter: state.solutionDraft.submitter || "web_console",
            source: "web_submit_review",
            reusable: Boolean(state.solutionDraft.reusable),
            metadata: {
              analysis_depth: byId("diagnosisDepthPage").value,
              customer_symptom: byId("diagnosisCustomerSymptomPage").value,
              environment_info: byId("diagnosisEnvironmentInfoPage").value,
              reproduction_steps: byId("diagnosisReproductionStepsPage").value,
              operation_path: byId("diagnosisOperationPathPage").value,
            },
            attachments: state.latestDiagnosisResult ? state.latestDiagnosisResult.source_context_snippets || [] : [],
          };
          const response = await apiJson(`${config.apiPrefix}/solution-reviews`, "POST", payloadToSubmit);
          state.latestReviewResult = response.item;
          byId("diagnosisPageMessage").textContent = `审核记录 ${response.item.id} 已提交。`;
          renderLatestDiagnosis(state.latestDiagnosisResult);
        });
        byId("diagnosisFormPage").addEventListener("submit", async (event) => {
          event.preventDefault();
          readSolutionDraftFromInputs("diagnosisDraft");
          const signature = byId("diagnosisSignaturePage").value;
          const formData = new FormData();
          formData.append("analysis_depth", byId("diagnosisDepthPage").value || "medium");
          formData.append("trigger_scenario", byId("diagnosisScenarioPage").value || "");
          formData.append("module", byId("diagnosisModulePage").value || "");
          formData.append("submodule", byId("diagnosisSubmodulePage").value || "");
          formData.append("environment_info", byId("diagnosisEnvironmentInfoPage").value || "");
          formData.append("reproduction_steps", byId("diagnosisReproductionStepsPage").value || "");
          formData.append("customer_symptom", byId("diagnosisCustomerSymptomPage").value || "");
          formData.append("operation_path", byId("diagnosisOperationPathPage").value || "");
          formData.append("source_notes", byId("diagnosisSourceNotesPage").value || "");
          formData.append(
            "existing_solution_json",
            JSON.stringify({
              error_name: state.solutionDraft.error_name,
              error_category: state.solutionDraft.error_category,
              error_code: state.solutionDraft.error_code,
              impact_scope: state.solutionDraft.impact_scope,
              root_cause_analysis: state.solutionDraft.root_cause_analysis,
              verified_solution: state.solutionDraft.verified_solution,
              workaround: state.solutionDraft.workaround,
              owner_department: state.solutionDraft.owner_department,
              submitter: state.solutionDraft.submitter,
              reusable: state.solutionDraft.reusable,
            })
          );
          Array.from(byId("diagnosisFilesPage").files || []).forEach((file) => formData.append("source_files", file));
          byId("diagnosisPageMessage").textContent = "正在请求 LLM 诊断...";
          const response = await fetch(
            `${config.apiPrefix}/tasks/${encodeURIComponent(task)}/errors/${encodeURIComponent(signature)}/analyze?force=${byId("diagnosisForcePage").checked ? "true" : "false"}`,
            {
              method: "POST",
              body: formData,
              headers: getToken() ? { Authorization: `Bearer ${getToken()}` } : {},
            }
          );
          const payload = await response.json();
          if (!response.ok) {
            throw new Error(payload.detail || "诊断失败");
          }
          state.latestDiagnosisResult = payload;
          state.latestDiagnosisSignature = signature;
          byId("diagnosisPageMessage").textContent = "诊断完成。";
          renderLatestDiagnosis(payload);
        });

        renderHistory().catch((error) => { byId("diagHistoryDetail").innerHTML = emptyState(error.message); });
        renderRepo().catch((error) => { byId("diagRepoEditor").innerHTML = emptyState(error.message); });
        renderReviewCenter().catch((error) => { byId("diagReviewEditor").innerHTML = emptyState(error.message); });
        renderLatestDiagnosis(state.latestDiagnosisResult);
      }
    );
  }

  async function renderFilesPage() {
    const task = requireTask();
    const files = await apiRequest(`${config.apiPrefix}/tasks/${encodeURIComponent(task)}/files?limit=200&offset=0`);
    const items = Array.isArray(files.items) ? files.items : [];
    mountPage(
      "File Preview",
      "View raw files and load preview snippets.",
      `
        <div class="split-grid">
          <div class="subpanel"><h4>Raw File List</h4>${fmtJson(files)}</div>
          <div class="subpanel">
            <h4>Preview</h4>
            <label>Select File<select id="filesSelect">${items.map((item) => `<option value="${escapeHtml(item.relative_path)}">${escapeHtml(item.relative_path)}</option>`).join("")}</select></label>
            <label>Preview Lines<input id="filesMaxLines" type="number" min="20" max="500" value="120" /></label>
            <div class="button-row"><button id="loadFilePreviewButton" type="button">Load Preview</button></div>
            <div id="filePreviewWrap"></div>
          </div>
        </div>
      `,
      () => {
        const loadPreview = async () => {
          const relativePath = byId("filesSelect").value;
          if (!relativePath) {
            byId("filePreviewWrap").innerHTML = emptyState("Select a file first.");
            return;
          }
          const preview = await apiRequest(`${config.apiPrefix}/tasks/${encodeURIComponent(task)}/files/preview?relative_path=${encodeURIComponent(relativePath)}&max_lines=${encodeURIComponent(byId("filesMaxLines").value || "120")}`);
          byId("filePreviewWrap").innerHTML = `${renderDefinitionList([{ label: "File", value: preview.relative_path || "-" }, { label: "Type", value: preview.mime_type || "unknown" }, { label: "Encoding", value: preview.encoding || "unknown" }, { label: "Line Count", value: preview.line_count || 0 }])}<pre>${escapeHtml((preview.preview || []).join("\n"))}</pre>`;
        };
        byId("loadFilePreviewButton").addEventListener("click", loadPreview);
        byId("filePreviewWrap").innerHTML = items.length ? emptyState("Click to load a file preview.") : emptyState("No raw files in the current task.");
      }
    );
  }

  async function renderUnknownPage() {
    const [unknownClusters, feedbackRecords, feedbackClusters] = await Promise.all([
      apiRequest(`${config.apiPrefix}/active-learning/unknown-clusters?limit=100&min_occurrence=1`),
      apiRequest(`${config.apiPrefix}/active-learning/feedback-records?limit=100`),
      apiRequest(`${config.apiPrefix}/active-learning/feedback-clusters?limit=100`),
    ]);
    const items = Array.isArray(unknownClusters.items) ? unknownClusters.items : [];

    mountPage(
      "未知日志待标注池",
      "查看未知日志簇、反馈记录和审核动作。",
      `
        ${renderCards([
          { label: "未知簇数", value: formatNumber(items.length) },
          { label: "反馈记录数", value: formatNumber((feedbackRecords.items || []).length) },
          { label: "反馈簇数", value: formatNumber((feedbackClusters.items || []).length) },
          { label: "当前模式", value: "active-learning" },
        ])}
        <div class="split-grid">
          <div class="subpanel"><h4>未知日志簇</h4><div id="unknownTableWrap"></div></div>
          <div class="subpanel"><h4>未知簇详情</h4><div id="unknownDetailWrap"></div></div>
        </div>
        <div class="subpanel"><h4>反馈记录 / 反馈簇</h4>${renderTabs("unknownFeedbackTabs", [
          { key: "records", label: "反馈记录", content: fmtJson(feedbackRecords) },
          { key: "clusters", label: "反馈簇", content: fmtJson(feedbackClusters) },
        ])}</div>
      `,
      () => {
        byId("unknownTableWrap").innerHTML = renderTable(
          [
            { key: "signature", label: "签名", render: (row) => escapeHtml(clip(row.signature || "-", 84)) },
            { key: "occurrence_count", label: "出现次数", render: (row) => formatNumber(row.occurrence_count) },
            { key: "review_status", label: "审核状态", render: (row) => pill(row.review_status || "pending_review") },
            { key: "representative_source_file", label: "代表文件", render: (row) => escapeHtml(clip(row.representative_source_file || "-", 60)) },
            { key: "last_seen_at", label: "最近出现", render: (row) => formatDateTime(row.last_seen_at) },
          ],
          items,
          [{ action: "inspect", label: "查看", group: "unknown" }]
        );

        hydrateActionTable("unknown", items, async (_action, row) => {
          byId("unknownDetailWrap").innerHTML = `
            ${renderCards([
              { label: "当前状态", value: row.review_status || "pending_review" },
              { label: "出现次数", value: formatNumber(row.occurrence_count || 0) },
              { label: "源文件数", value: formatNumber(Object.keys(row.source_files || {}).length) },
              { label: "最近出现", value: formatDateTime(row.last_seen_at) },
            ])}
            <h4>代表性样本</h4>
            <pre>${escapeHtml(safeString(row.representative_text, ""))}</pre>
            <label>reviewer<input id="unknownReviewer" value="${escapeHtml(state.currentUser ? state.currentUser.username : "")}" /></label>
            <label>review notes<textarea id="unknownNotes"></textarea></label>
            <div class="button-row">
              <button data-unknown-status="submitted_for_review" type="button">提交审核</button>
              <button data-unknown-status="approved" type="button">批准</button>
              <button data-unknown-status="rejected" class="danger" type="button">驳回</button>
              <button data-unknown-status="ignored" class="ghost" type="button">忽略</button>
            </div>
            <div class="split-grid" style="margin-top:16px;">
              <div class="subpanel"><h4>尝试过的 Parsers</h4>${fmtJson(row.attempted_parsers || [])}</div>
              <div class="subpanel"><h4>尝试过的 Rules</h4>${fmtJson(row.attempted_rules || [])}</div>
            </div>
            <h4 style="margin-top:16px;">上下文样本</h4>
            ${fmtJson(row.context_examples || [])}
            ${row.review_history && row.review_history.length ? `<h4 style="margin-top:16px;">审核历史</h4>${fmtJson(row.review_history)}` : ""}
            <p id="unknownActionMessage" class="inline-message"></p>
          `;
          qsa("[data-unknown-status]", byId("unknownDetailWrap")).forEach((button) => {
            button.addEventListener("click", async () => {
              const reviewStatusValue = button.getAttribute("data-unknown-status");
              await apiJson(`${config.apiPrefix}/active-learning/unknown-clusters/${encodeURIComponent(row.signature)}/review`, "POST", {
                review_status: reviewStatusValue,
                reviewer: byId("unknownReviewer").value.trim(),
                notes: byId("unknownNotes").value,
              });
              byId("unknownActionMessage").textContent = `状态已更新为 ${reviewStatusValue}。`;
            });
          });
        });

        byId("unknownDetailWrap").innerHTML = items.length ? emptyState("请选择一个未知日志簇查看详情。") : emptyState("当前没有未知日志待标注样本。");
      }
    );
  }

  async function renderRulesPage() {
    const unknownPool = await apiRequest(`${config.apiPrefix}/active-learning/unknown-clusters?min_occurrence=1&limit=200`);
    const preview = await apiRequest(`${config.apiPrefix}/active-learning/rule-suggestions/preview?use_llm=false&force_refresh=false`);
    const reviews = await apiRequest(`${config.apiPrefix}/active-learning/rule-suggestions/reviews?limit=200`);
    const files = await apiRequest(`${config.apiPrefix}/active-learning/rule-suggestions/files?limit=50`);
    const unknownItems = Array.isArray(unknownPool.items) ? unknownPool.items : [];

    mountPage(
      "规则建议审核",
      "本地建议、LLM 建议、审核记录和候选 YAML 片段。",
      `
        <form id="rulesForm" class="form-grid">
          <div class="split-grid">
            <label class="checkbox-row"><input id="rulesUseLlm" type="checkbox" />启用 LLM 规则建议</label>
            <label class="checkbox-row"><input id="rulesForceRefresh" type="checkbox" />忽略 LLM 预览缓存并重新生成</label>
          </div>
          <label>送入 LLM 的未知日志簇
            <select id="rulesUnknownSignatures" multiple size="6">
              ${unknownItems
                .map(
                  (row, index) => `
                    <option value="${escapeHtml(row.signature)}" ${index < 3 ? "selected" : ""}>
                      ${escapeHtml(clip(`${row.signature} | count=${row.occurrence_count || 0}`, 120))}
                    </option>
                  `
                )
                .join("")}
            </select>
          </label>
          <div class="button-row"><button type="submit">刷新规则建议</button></div>
        </form>
        ${renderCards([
          { label: "未知簇总数", value: formatNumber((preview.summary || {}).unknown_clusters_total || 0) },
          { label: "反馈记录总数", value: formatNumber((preview.summary || {}).feedback_records_total || 0) },
          { label: "本地新规则建议", value: formatNumber((preview.summary || {}).new_rule_suggestions || 0) },
          { label: "本地修正规则建议", value: formatNumber((preview.summary || {}).rule_fix_suggestions || 0) },
        ])}
        <div id="rulesLlmMeta" class="subpanel" style="margin-top:16px;"></div>
        <div id="rulesTabsWrap" style="margin-top:16px;"></div>
      `,
      () => {
        const renderReviewActions = (containerId, suggestions) => {
          const detail = byId(containerId);
          if (!suggestions.length) {
            detail.innerHTML = emptyState("暂无可审核建议。");
            return;
          }
          detail.innerHTML = renderTable(
            [
              { key: "suggestion_id", label: "Suggestion ID", render: (row) => escapeHtml(safeString(row.suggestion_id, "-")) },
              { key: "review_status", label: "审核状态", render: (row) => pill(row.review_status || "pending_review") },
              { key: "rule_name", label: "规则名", render: (row) => escapeHtml(clip(row.rule_name || row.signature || "-", 60)) },
              { key: "occurrence_count", label: "次数", render: (row) => formatNumber(row.occurrence_count || row.feedback_count || 0) },
            ],
            suggestions,
            [{ action: "pick", label: "查看/审核", group: containerId }]
          ) + `<div id="${containerId}Detail" style="margin-top:16px;"></div>`;
          hydrateActionTable(containerId, suggestions, async (_action, row) => {
            const detailPanel = byId(`${containerId}Detail`);
            detailPanel.innerHTML = `
              ${fmtJson(row)}
              <label>reviewer<input id="${containerId}Reviewer" value="${escapeHtml(state.currentUser ? state.currentUser.username : "")}" /></label>
              <label>review notes<textarea id="${containerId}Notes"></textarea></label>
              <div class="button-row">
                <button data-rule-status="submitted_for_review" data-rule-container="${containerId}" type="button">提交审核</button>
                <button data-rule-status="approved" data-rule-container="${containerId}" type="button">批准</button>
                <button data-rule-status="rejected" data-rule-container="${containerId}" class="danger" type="button">驳回</button>
                <button data-rule-status="ignored" data-rule-container="${containerId}" class="ghost" type="button">忽略</button>
              </div>
              <p id="${containerId}Message" class="inline-message"></p>
            `;
            qsa(`[data-rule-container="${containerId}"]`, detailPanel).forEach((button) => {
              button.addEventListener("click", async () => {
                const reviewStatus = button.getAttribute("data-rule-status");
                await apiJson(`${config.apiPrefix}/active-learning/rule-suggestions/${encodeURIComponent(row.suggestion_id)}/review`, "POST", {
                  review_status: reviewStatus,
                  reviewer: byId(`${containerId}Reviewer`).value.trim(),
                  notes: byId(`${containerId}Notes`).value,
                });
                byId(`${containerId}Message`).textContent = `规则建议已更新为 ${reviewStatus}。`;
              });
            });
          });
        };

        const renderPreview = (data) => {
          const llmMeta = data.llm_assisted || {};
          byId("rulesLlmMeta").innerHTML = fmtJson(llmMeta);
          byId("rulesTabsWrap").innerHTML = renderTabs("rulesTabs", [
            { key: "localNew", label: "本地新规则建议", content: '<div id="rulesLocalNew"></div>' },
            { key: "localFix", label: "本地修正规则建议", content: '<div id="rulesLocalFix"></div>' },
            { key: "llmNew", label: "LLM 新规则建议", content: fmtJson(((llmMeta.result || {}).new_rule_suggestions) || []) },
            { key: "llmFix", label: "LLM 修正规则建议", content: fmtJson(((llmMeta.result || {}).rule_fix_suggestions) || []) },
            { key: "yaml", label: "YAML 候选片段", content: fmtJson(data.parser_rules_yaml_fragment || {}) },
            { key: "reviews", label: "审核记录", content: fmtJson(reviews) },
            { key: "files", label: "建议文件", content: fmtJson(files) },
          ]);
          hydrateTabs(byId("rulesTabsWrap"));
          renderReviewActions("rulesLocalNew", Array.isArray(data.new_rule_suggestions) ? data.new_rule_suggestions : []);
          renderReviewActions("rulesLocalFix", Array.isArray(data.rule_fix_suggestions) ? data.rule_fix_suggestions : []);
        };

        byId("rulesForm").addEventListener("submit", async (event) => {
          event.preventDefault();
          const params = new URLSearchParams({
            use_llm: byId("rulesUseLlm").checked ? "true" : "false",
            force_refresh: byId("rulesForceRefresh").checked ? "true" : "false",
          });
          const selectedSignatures = readMultiselectValues("rulesUnknownSignatures");
          if (selectedSignatures.length) {
            params.set("selected_signatures", selectedSignatures.join(","));
          }
          const nextPreview = await apiRequest(`${config.apiPrefix}/active-learning/rule-suggestions/preview?${params.toString()}`);
          renderPreview(nextPreview);
        });

        renderPreview(preview);
      }
    );
  }

  async function renderConfigPage() {
    const payload = {
      config: await apiRequest(`${config.apiPrefix}/config`),
      env: await apiRequest(`${config.apiPrefix}/config/env`),
      promptTemplates: await apiRequest(`${config.apiPrefix}/config/prompt-templates`),
    };
    const configData = payload.config || {};
    const thresholds = configData.thresholds || {};
    const parserRules = configData.parser_rules || {};
    const errorRules = configData.error_rules || {};
    const llmConfig = configData.llm || {};
    const repoConfig = configData.solution_repository || {};
    const promptTemplates = payload.promptTemplates || {};
    const promptVersions = promptTemplates.templates || {};
    const activePromptVersion = promptTemplates.active_version || "-";

    mountPage(
      "配置页面",
      "查看系统配置、维护阈值、检查异常识别规则和 Prompt 模板。",
      `
        <div class="split-grid">
          <div class="subpanel">
            <h4>运行配置概况</h4>
            ${renderCards([
              { label: "步骤级阈值", value: formatNumber(Object.values(thresholds.step_thresholds_ms || {}).reduce((sum, item) => sum + Object.keys(item || {}).length, 0)) },
              { label: "参数判定项", value: formatNumber(Object.keys(thresholds.parameter_thresholds_seconds || {}).length) },
              { label: "异常家族", value: formatNumber((errorRules.family_rules || []).length) },
              { label: "当前 Prompt", value: activePromptVersion },
            ])}
          </div>
          <div class="subpanel">
            <h4>快捷配置操作</h4>
            <form id="configOpsForm" class="form-grid">
              <label>Env Key<input id="configEnvKey" /></label>
              <label>Env Value<textarea id="configEnvValue"></textarea></label>
              <label>Prompt Version<input id="configPromptVersion" value="${escapeHtml(activePromptVersion)}" /></label>
              <div class="button-row">
                <button type="button" id="configUpdateEnvButton">更新 Env</button>
                <button type="button" id="configResetEnvButton" class="ghost">重置 Env</button>
                <button type="button" id="configPromptButton" class="ghost">切换 Prompt</button>
              </div>
            </form>
            <p id="configOpsMessage" class="inline-message"></p>
          </div>
        </div>
        ${renderTabs("configTabs", [
          {
            key: "overview",
            label: "总览",
            content: `
              ${renderDefinitionList([
                { label: "默认超时阈值(ms)", value: thresholds.default_threshold_ms || 0 },
                { label: "LLM 开关", value: llmConfig.enabled ? "开启" : "关闭" },
                { label: "诊断模型", value: llmConfig.model || "-" },
                { label: "Prompt 版本", value: activePromptVersion },
                { label: "模块数", value: formatNumber((repoConfig.module_tree || []).length) },
                { label: "组件映射规则", value: formatNumber(Object.keys(parserRules.component_filename_rules || {}).length) },
              ])}
              <h4 style="margin-top:16px;">环境变量</h4>
              ${fmtJson(payload.env)}
            `,
          },
          {
            key: "thresholds",
            label: "时间与阈值",
            content: `
              <form id="configThresholdForm" class="form-grid">
                <label>默认超时阈值(ms)<input id="configDefaultThreshold" type="number" min="0" value="${escapeHtml(String(thresholds.default_threshold_ms || 0))}" /></label>
                <label>参数阈值 JSON<textarea id="configParameterThresholds">${escapeHtml(JSON.stringify(thresholds.parameter_thresholds_seconds || {}, null, 2))}</textarea></label>
                <label>参数期望值 JSON<textarea id="configParameterExpected">${escapeHtml(JSON.stringify(thresholds.parameter_expected_seconds || {}, null, 2))}</textarea></label>
                <label>步骤级阈值 JSON<textarea id="configStepThresholds">${escapeHtml(JSON.stringify(thresholds.step_thresholds_ms || {}, null, 2))}</textarea></label>
                <label>诊断上下文窗口 JSON<textarea id="configContextThresholds">${escapeHtml(JSON.stringify(thresholds.llm_context || {}, null, 2))}</textarea></label>
                <div class="button-row"><button type="submit">保存阈值配置</button></div>
              </form>
              <p id="configThresholdMessage" class="inline-message"></p>
            `,
          },
          {
            key: "rules",
            label: "异常与审核",
            content: fmtJson({
              time_formats: parserRules.time_formats || [],
              cycle_patterns: parserRules.cycle_patterns || [],
              chip_patterns: parserRules.chip_patterns || [],
              component_filename_rules: parserRules.component_filename_rules || {},
              family_rules: errorRules.family_rules || [],
              active_learning: parserRules.active_learning || {},
            }),
          },
          {
            key: "knowledge",
            label: "Prompt 与方案库",
            content: `${fmtJson(promptVersions)}<h4 style="margin-top:16px;">诊断深度策略</h4>${fmtJson(llmConfig.analysis_depths || {})}<h4 style="margin-top:16px;">方案库模块树</h4>${fmtJson(repoConfig.module_tree || [])}`,
          },
        ])}
      `,
      () => {
        byId("configUpdateEnvButton").addEventListener("click", async () => {
          const key = byId("configEnvKey").value.trim();
          if (!key) throw new Error("请先填写 Env Key。");
          await apiJson(`${config.apiPrefix}/config/env/${encodeURIComponent(key)}`, "PUT", { value: byId("configEnvValue").value });
          byId("configOpsMessage").textContent = `Env ${key} 已更新。`;
        });
        byId("configResetEnvButton").addEventListener("click", async () => {
          const key = byId("configEnvKey").value.trim();
          if (!key) throw new Error("请先填写 Env Key。");
          await apiRequest(`${config.apiPrefix}/config/env/${encodeURIComponent(key)}/reset`, { method: "POST" });
          byId("configOpsMessage").textContent = `Env ${key} 已重置。`;
        });
        byId("configPromptButton").addEventListener("click", async () => {
          const version = byId("configPromptVersion").value.trim();
          await apiJson(`${config.apiPrefix}/config/prompt-templates/active`, "PUT", { version });
          byId("configOpsMessage").textContent = `Prompt 已切换到 ${version}。`;
        });
        byId("configThresholdForm").addEventListener("submit", async (event) => {
          event.preventDefault();
          const body = {
            default_threshold_ms: Number(byId("configDefaultThreshold").value || 0),
            parameter_thresholds_seconds: parseJsonOrThrow(byId("configParameterThresholds").value, "参数阈值"),
            parameter_expected_seconds: parseJsonOrThrow(byId("configParameterExpected").value, "参数期望值"),
            step_thresholds_ms: parseJsonOrThrow(byId("configStepThresholds").value, "步骤级阈值"),
            llm_context: parseJsonOrThrow(byId("configContextThresholds").value, "诊断上下文窗口"),
          };
          await apiJson(`${config.apiPrefix}/config/thresholds`, "PUT", body);
          byId("configThresholdMessage").textContent = "阈值配置已保存。";
        });
      }
    );
  }

  async function renderSolutionsPage() {
    const payload = {
      repositoryConfig: await apiRequest(`${config.apiPrefix}/solution-repository/config`),
      modules: await apiRequest(`${config.apiPrefix}/solution-repository/modules`),
      taskClusters: await apiRequest(`${config.apiPrefix}/solution-repository/task-clusters?include_pending=true`),
      reviews: await apiRequest(`${config.apiPrefix}/solution-reviews?limit=100`),
    };
    const moduleItems = Array.isArray(payload.modules.items) ? payload.modules.items : [];
    const clusterItems = Array.isArray(payload.taskClusters.items) ? payload.taskClusters.items : [];

    mountPage(
      "方案库中心",
      "围绕可复用方案、检索索引、任务簇管理和审核流的统一入口。",
      renderTabs("solutionsTabs", [
        {
          key: "submit",
          label: "方案提交",
          content: `
            <form id="solutionSubmitForm" class="form-grid">
              <div class="triple-grid">
                <label>模块
                  <select id="solutionSubmitModule">${moduleItems.map((item) => `<option value="${escapeHtml(item.module_key)}">${escapeHtml(item.display_name || item.module_key)}</option>`).join("")}</select>
                </label>
                <label>任务簇
                  <select id="solutionSubmitClusters" multiple size="5">${clusterItems.map((item) => `<option value="${escapeHtml(item.display_name)}">${escapeHtml(item.display_name)}</option>`).join("")}</select>
                </label>
                <label>新增任务簇候选<input id="solutionNewCluster" /></label>
              </div>
              <div class="triple-grid">
                <label>错误名<input id="solutionErrorName" /></label>
                <label>message 关键词<input id="solutionMessageKeywords" /></label>
                <label>标签<input id="solutionTags" /></label>
              </div>
              <label>message 关键词 / 现象描述<textarea id="solutionMessage"></textarea></label>
              <label>根因分析<textarea id="solutionRootCause"></textarea></label>
              <label>已验证解决方案<textarea id="solutionVerifiedSolution"></textarea></label>
              <label>临时绕过方案<textarea id="solutionWorkaround"></textarea></label>
              <label>触发场景 / 问题簇<textarea id="solutionTriggerScenario"></textarea></label>
              <div class="split-grid">
                <label>关联 task_uuid<input id="solutionTaskUuid" /></label>
                <label>关联 normalized_signature<input id="solutionSignature" /></label>
              </div>
              <div class="button-row"><button type="submit">提交方案</button></div>
            </form>
            <p id="solutionSubmitMessage" class="inline-message"></p>
          `,
        },
        {
          key: "query",
          label: "方案检索",
          content: `
            <form id="solutionQueryForm" class="inline-form">
              <label>关键字<input id="solutionQuerySearch" /></label>
              <label>模块
                <select id="solutionQueryModule"><option value="">全部</option>${moduleItems.map((item) => `<option value="${escapeHtml(item.module_key)}">${escapeHtml(item.display_name || item.module_key)}</option>`).join("")}</select>
              </label>
              <label>任务簇
                <select id="solutionQueryCluster"><option value="">全部</option>${clusterItems.map((item) => `<option value="${escapeHtml(item.display_name)}">${escapeHtml(item.display_name)}</option>`).join("")}</select>
              </label>
              <label>审核状态
                <select id="solutionQueryStatus">
                  <option value="">全部</option>
                  <option value="approved">approved</option>
                  <option value="pending_review">pending_review</option>
                  <option value="needs_revision">needs_revision</option>
                  <option value="rejected">rejected</option>
                </select>
              </label>
              <label>可复用
                <select id="solutionQueryReusable"><option value="">全部</option><option value="true">true</option><option value="false">false</option></select>
              </label>
              <button type="submit">查询方案库</button>
            </form>
            <div class="button-row" style="margin-bottom:16px;">
              <a class="button-link ghost" href="${escapeHtml(buildDownloadUrl(`${config.apiPrefix}/solution-repository/export?format=json`))}" target="_blank" rel="noreferrer">导出 JSON</a>
              <a class="button-link ghost" href="${escapeHtml(buildDownloadUrl(`${config.apiPrefix}/solution-repository/export?format=csv`))}" target="_blank" rel="noreferrer">导出 CSV</a>
              <a class="button-link ghost" href="${escapeHtml(buildDownloadUrl(`${config.apiPrefix}/solution-repository/export?format=xlsx`))}" target="_blank" rel="noreferrer">导出 Excel</a>
              <a class="button-link ghost" href="${escapeHtml(buildDownloadUrl(`${config.apiPrefix}/solution-repository/export?format=sqlite`))}" target="_blank" rel="noreferrer">导出 SQLite</a>
            </div>
            <div class="split-grid">
              <div class="subpanel"><h4>方案记录</h4><div id="solutionsQueryTable"></div></div>
              <div class="subpanel"><h4>记录详情 / 编辑</h4><div id="solutionsQueryDetail"></div></div>
            </div>
          `,
        },
        {
          key: "review",
          label: "方案审核",
          content: `
            <form id="solutionReviewForm" class="inline-form">
              <label>审核状态
                <select id="solutionReviewStatus">
                  <option value="">全部</option>
                  <option value="pending_review">pending_review</option>
                  <option value="approved">approved</option>
                  <option value="needs_revision">needs_revision</option>
                  <option value="rejected">rejected</option>
                </select>
              </label>
              <button type="submit">刷新审核列表</button>
            </form>
            <div class="split-grid">
              <div class="subpanel"><h4>审核记录</h4><div id="solutionsReviewTable"></div></div>
              <div class="subpanel"><h4>人工审核</h4><div id="solutionsReviewDetail"></div></div>
            </div>
          `,
        },
        {
          key: "taxonomy",
          label: "任务簇与模块",
          content: `
            <div class="split-grid">
              <div class="subpanel">
                <h4>任务簇</h4>
                ${fmtJson(clusterItems)}
                <label>新任务簇名称<input id="solutionsClusterName" /></label>
                <label>任务簇说明<textarea id="solutionsClusterDescription"></textarea></label>
                <div class="button-row"><button id="solutionsCreateClusterButton" type="button">提交任务簇</button></div>
                <p id="solutionsClusterMessage" class="inline-message"></p>
              </div>
              <div class="subpanel">
                <h4>模块</h4>
                ${fmtJson(moduleItems)}
                <label>module_key<input id="solutionsModuleKey" /></label>
                <label>display_name<input id="solutionsModuleDisplayName" /></label>
                <label>prefix<input id="solutionsModulePrefix" /></label>
                <label>description<textarea id="solutionsModuleDescription"></textarea></label>
                <div class="button-row"><button id="solutionsCreateModuleButton" type="button">保存模块</button></div>
                <p id="solutionsModuleMessage" class="inline-message"></p>
              </div>
            </div>
          `,
        },
      ]),
      () => {
        const queryRecords = async () => {
          const params = new URLSearchParams({ limit: "200" });
          const search = byId("solutionQuerySearch").value.trim();
          const module = byId("solutionQueryModule").value;
          const cluster = byId("solutionQueryCluster").value;
          const status = byId("solutionQueryStatus").value;
          const reusable = byId("solutionQueryReusable").value;
          if (search) params.set("search", search);
          if (module) params.set("module", module);
          if (cluster) params.set("task_cluster", cluster);
          if (status) params.set("review_status", status);
          if (reusable) params.set("reusable", reusable);
          const rows = await apiRequest(`${config.apiPrefix}/solution-repository/records?${params.toString()}`);
          const items = Array.isArray(rows.items) ? rows.items : [];
          byId("solutionsQueryTable").innerHTML = renderTable(
            [
              { key: "id", label: "ID", render: (row) => formatNumber(row.id) },
              { key: "error_name", label: "错误名", render: (row) => escapeHtml(clip(row.error_name || "-", 60)) },
              { key: "module", label: "模块", render: (row) => escapeHtml(safeString(row.module, "-")) },
              { key: "review_status", label: "审核状态", render: (row) => pill(row.review_status || "-") },
              { key: "updated_at", label: "更新时间", render: (row) => formatDateTime(row.updated_at) },
            ],
            items,
            [{ action: "pick", label: "查看", group: "solutionsQuery" }]
          );
          hydrateActionTable("solutionsQuery", items, async (_action, row) => {
            if (!isReviewer()) {
              byId("solutionsQueryDetail").innerHTML = fmtJson(row);
              return;
            }
            byId("solutionsQueryDetail").innerHTML = `
              ${fmtJson(row)}
              <label>编辑根因分析<textarea id="solutionsEditRootCause">${escapeHtml(row.root_cause_analysis || "")}</textarea></label>
              <label>编辑已验证解决方案<textarea id="solutionsEditVerifiedSolution">${escapeHtml(row.verified_solution || "")}</textarea></label>
              <label>编辑临时绕过方案<textarea id="solutionsEditWorkaround">${escapeHtml(row.workaround || "")}</textarea></label>
              <label class="checkbox-row"><input id="solutionsEditReusable" type="checkbox" ${row.reusable ? "checked" : ""} />可复用</label>
              <div class="button-row"><button id="solutionsSaveRecordButton" type="button">保存当前记录</button></div>
              <p id="solutionsEditMessage" class="inline-message"></p>
            `;
            byId("solutionsSaveRecordButton").addEventListener("click", async () => {
              const payloadToSave = {
                ...row,
                root_cause_analysis: byId("solutionsEditRootCause").value,
                verified_solution: byId("solutionsEditVerifiedSolution").value,
                workaround: byId("solutionsEditWorkaround").value,
                reusable: byId("solutionsEditReusable").checked,
              };
              const response = await apiJson(`${config.apiPrefix}/solution-repository/records/${encodeURIComponent(row.id)}`, "PUT", payloadToSave);
              byId("solutionsEditMessage").textContent = `记录 ${response.item.id} 已更新。`;
              await queryRecords();
            });
          });
          if (!items.length) {
            byId("solutionsQueryDetail").innerHTML = emptyState("当前没有方案记录。");
          }
        };

        const queryReviews = async () => {
          const params = new URLSearchParams({ limit: "200" });
          const status = byId("solutionReviewStatus").value;
          if (status) params.set("status", status);
          const rows = await apiRequest(`${config.apiPrefix}/solution-reviews?${params.toString()}`);
          const items = Array.isArray(rows.items) ? rows.items : [];
          byId("solutionsReviewTable").innerHTML = renderTable(
            [
              { key: "id", label: "ID", render: (row) => formatNumber(row.id) },
              { key: "review_status", label: "审核状态", render: (row) => pill(row.review_status || "-") },
              { key: "module", label: "模块", render: (row) => escapeHtml(safeString(row.module, "-")) },
              { key: "created_by", label: "创建人", render: (row) => escapeHtml(safeString(row.created_by, "-")) },
              { key: "updated_at", label: "更新时间", render: (row) => formatDateTime(row.updated_at) },
            ],
            items,
            [{ action: "pick", label: "审核", group: "solutionsReview" }]
          );
          hydrateActionTable("solutionsReview", items, async (_action, row) => {
            if (!isReviewer()) {
              byId("solutionsReviewDetail").innerHTML = fmtJson(row);
              return;
            }
            byId("solutionsReviewDetail").innerHTML = `
              ${fmtJson(row)}
              <label>人工复核人<input id="solutionsReviewer" value="${escapeHtml(state.currentUser ? state.currentUser.username : "")}" /></label>
              <label>审核意见<textarea id="solutionsReviewNotes"></textarea></label>
              <div class="button-row">
                <button data-solution-review-status="approved" type="button">人工通过</button>
                <button data-solution-review-status="needs_revision" class="warn" type="button">退回修改</button>
                <button data-solution-review-status="rejected" class="danger" type="button">拒绝入库</button>
              </div>
              <p id="solutionsReviewMessage" class="inline-message"></p>
            `;
            qsa("[data-solution-review-status]", byId("solutionsReviewDetail")).forEach((button) => {
              button.addEventListener("click", async () => {
                const reviewStatusValue = button.getAttribute("data-solution-review-status");
                const response = await apiJson(`${config.apiPrefix}/solution-reviews/${encodeURIComponent(row.id)}/manual-review`, "POST", {
                  review_status: reviewStatusValue,
                  reviewer: byId("solutionsReviewer").value.trim(),
                  notes: byId("solutionsReviewNotes").value,
                });
                byId("solutionsReviewMessage").textContent = `审核记录 ${response.item.id} 已更新为 ${reviewStatusValue}。`;
                await queryReviews();
              });
            });
          });
          if (!items.length) {
            byId("solutionsReviewDetail").innerHTML = emptyState("当前没有审核记录。");
          }
        };

        byId("solutionSubmitForm").addEventListener("submit", async (event) => {
          event.preventDefault();
          const newCluster = byId("solutionNewCluster").value.trim();
          const selectedClusters = readMultiselectValues("solutionSubmitClusters");
          if (newCluster) {
            const clusterResponse = await apiJson(`${config.apiPrefix}/solution-repository/task-clusters`, "POST", {
              display_name: newCluster,
              description: `Created from web console on ${new Date().toISOString()}`,
            });
            selectedClusters.push(clusterResponse.item.display_name);
          }
          const payloadToSubmit = {
            submission_type: "solution_record",
            module: byId("solutionSubmitModule").value,
            error_name: byId("solutionErrorName").value.trim(),
            message: byId("solutionMessage").value.trim(),
            message_keywords: parseTextareaLines(byId("solutionMessageKeywords").value.replaceAll(",", "\n")),
            tags: parseTextareaLines(byId("solutionTags").value.replaceAll(",", "\n")),
            root_cause_analysis: byId("solutionRootCause").value,
            verified_solution: byId("solutionVerifiedSolution").value,
            workaround: byId("solutionWorkaround").value,
            trigger_scenario: byId("solutionTriggerScenario").value,
            task_uuid: byId("solutionTaskUuid").value.trim() || null,
            normalized_signature: byId("solutionSignature").value.trim() || null,
            task_clusters: selectedClusters,
            submitter: state.currentUser ? state.currentUser.username : "web_console",
            source: "web_solution_hub",
          };
          const response = await apiJson(`${config.apiPrefix}/solution-reviews`, "POST", payloadToSubmit);
          byId("solutionSubmitMessage").textContent = `方案已提交，审核记录 ID: ${response.item.id}`;
          await queryReviews();
        });

        byId("solutionQueryForm").addEventListener("submit", async (event) => {
          event.preventDefault();
          await queryRecords();
        });
        byId("solutionReviewForm").addEventListener("submit", async (event) => {
          event.preventDefault();
          await queryReviews();
        });
        byId("solutionsCreateClusterButton").addEventListener("click", async () => {
          const response = await apiJson(`${config.apiPrefix}/solution-repository/task-clusters`, "POST", {
            display_name: byId("solutionsClusterName").value.trim(),
            description: byId("solutionsClusterDescription").value,
          });
          byId("solutionsClusterMessage").textContent = `任务簇 ${response.item.display_name} 已提交。`;
        });
        byId("solutionsCreateModuleButton").addEventListener("click", async () => {
          if (!isReviewer()) {
            byId("solutionsModuleMessage").textContent = "当前账号没有模块维护权限。";
            return;
          }
          const response = await apiJson(`${config.apiPrefix}/solution-repository/modules`, "POST", {
            module_key: byId("solutionsModuleKey").value.trim(),
            display_name: byId("solutionsModuleDisplayName").value.trim(),
            prefix: byId("solutionsModulePrefix").value.trim(),
            description: byId("solutionsModuleDescription").value,
            is_active: true,
          });
          byId("solutionsModuleMessage").textContent = `模块 ${response.item.module_key} 已保存。`;
        });

        queryRecords().catch((error) => { byId("solutionsQueryDetail").innerHTML = emptyState(error.message); });
        queryReviews().catch((error) => { byId("solutionsReviewDetail").innerHTML = emptyState(error.message); });
      }
    );
  }

  async function renderExportsPage() {
    const task = requireTask();
    mountPage(
      "Exports",
      "Task artifacts and solution repository exports.",
      `
        <div class="form-grid">
          <a class="button-link" href="${escapeHtml(buildDownloadUrl(`${config.apiPrefix}/tasks/${encodeURIComponent(task)}/export/events`))}" target="_blank" rel="noreferrer">Export Events CSV</a>
          <a class="button-link" href="${escapeHtml(buildDownloadUrl(`${config.apiPrefix}/tasks/${encodeURIComponent(task)}/export/errors`))}" target="_blank" rel="noreferrer">Export Errors CSV</a>
          <a class="button-link" href="${escapeHtml(buildDownloadUrl(`${config.apiPrefix}/tasks/${encodeURIComponent(task)}/export/parameters`))}" target="_blank" rel="noreferrer">Export Parameters CSV</a>
          <a class="button-link" href="${escapeHtml(buildDownloadUrl(`${config.apiPrefix}/tasks/${encodeURIComponent(task)}/export/report.html`))}" target="_blank" rel="noreferrer">Export HTML Report</a>
          <a class="button-link" href="${escapeHtml(buildDownloadUrl(`${config.apiPrefix}/tasks/${encodeURIComponent(task)}/export/report.json`))}" target="_blank" rel="noreferrer">Export JSON Report</a>
          <a class="button-link" href="${escapeHtml(buildDownloadUrl(`${config.apiPrefix}/tasks/${encodeURIComponent(task)}/export/report.xlsx`))}" target="_blank" rel="noreferrer">Export Excel Report</a>
          <a class="button-link" href="${escapeHtml(buildDownloadUrl(`${config.apiPrefix}/tasks/${encodeURIComponent(task)}/export/report.pdf`))}" target="_blank" rel="noreferrer">Export PDF Report</a>
          <a class="button-link ghost" href="${escapeHtml(buildDownloadUrl(`${config.apiPrefix}/solution-repository/export?format=json`))}" target="_blank" rel="noreferrer">Export Solutions JSON</a>
          <a class="button-link ghost" href="${escapeHtml(buildDownloadUrl(`${config.apiPrefix}/solution-repository/export?format=xlsx`))}" target="_blank" rel="noreferrer">Export Solutions XLSX</a>
        </div>
      `
    );
  }

  async function renderAdminPage() {
    if (!isAdmin()) {
      mountPage("User Admin", "", emptyState("Current user is not an admin."));
      return;
    }
    const [users, announcementResp] = await Promise.all([
      apiRequest(`${config.apiPrefix}/admin/users`),
      apiRequest(`${config.apiPrefix}/announcements?limit=50`),
    ]);
    const rows = safeArray(users.items);
    const announcements = safeArray(announcementResp.items);
    mountPage(
      "User Admin",
      "Approve registrations, update roles, and manage announcement history.",
      `
        ${renderTabs("adminTabs", [
          {
            key: "users",
            label: "Users",
            content: `
              ${renderTable(
                [
                  { key: "id", label: "ID", render: (row) => formatNumber(row.id) },
                  { key: "username", label: "Username", render: (row) => escapeHtml(safeString(row.username, "-")) },
                  { key: "email", label: "Email", render: (row) => escapeHtml(safeString(row.email, "-")) },
                  { key: "status", label: "Status", render: (row) => pill(row.status || "-") },
                  { key: "roles", label: "Roles", render: (row) => escapeHtml((row.roles || []).join(", ")) },
                ],
                rows,
                [
                  { action: "approve", label: "Approve", group: "adminUsers" },
                  { action: "reject", label: "Reject", className: "danger", group: "adminUsers" },
                  { action: "disable", label: "Disable", className: "warn", group: "adminUsers" },
                  { action: "enable", label: "Enable", group: "adminUsers" },
                  { action: "roles", label: "Roles", group: "adminUsers" },
                ]
              )}
              <div id="adminEditor" class="subpanel" style="margin-top:16px;"></div>
            `,
          },
          {
            key: "announcements",
            label: "Announcements",
            content: `
              <div class="split-grid">
                <div class="subpanel">
                  <h4>Create Announcement</h4>
                  <label>Title<input id="announcementCreateTitle" /></label>
                  <label>Summary<textarea id="announcementCreateSummary"></textarea></label>
                  <label class="checkbox-row"><input id="announcementCreatePinned" type="checkbox" />Pin announcement</label>
                  <div class="button-row"><button id="announcementCreateButton" type="button">Publish</button></div>
                  <p id="announcementCreateMessage" class="inline-message"></p>
                </div>
                <div class="subpanel">
                  <h4>Announcement Feed</h4>
                  ${announcements.length ? renderAnnouncementCards(announcements) : emptyState("暂无公告。")}
                </div>
              </div>
              <div class="split-grid" style="margin-top:16px;">
                <div class="subpanel">
                  <h4>Manage Announcements</h4>
                  ${renderTable(
                    [
                      { key: "title", label: "Title", render: (row) => escapeHtml(firstNonEmpty(row.title, "未命名公告")) },
                      { key: "is_pinned", label: "Pinned", render: (row) => pill(row.is_pinned ? "Pinned" : "Normal", row.is_pinned ? "" : "muted") },
                      { key: "updated_by", label: "Editor", render: (row) => escapeHtml(firstNonEmpty(row.updated_by, "-")) },
                      { key: "updated_at", label: "Updated At", render: (row) => formatDateTime(row.updated_at) },
                    ],
                    announcements,
                    [
                      { action: "edit", label: "Edit", group: "adminAnnouncements" },
                      { action: "delete", label: "Delete", className: "danger", group: "adminAnnouncements" },
                    ]
                  )}
                </div>
                <div id="announcementEditor" class="subpanel">
                  <h4>Editor</h4>
                  ${announcements[0] ? fmtJson(announcements[0]) : emptyState("暂无公告。")}
                </div>
              </div>
            `,
          },
        ])}
      `,
      () => {
        hydrateTabs(dom.pageMount);
        hydrateActionTable("adminUsers", rows, async (action, row) => {
          if (action === "roles") {
            byId("adminEditor").innerHTML = `
              <h4>Role Settings: ${escapeHtml(row.username)}</h4>
              <label class="checkbox-row"><input id="adminRoleReviewer" type="checkbox" ${row.is_reviewer ? "checked" : ""} />Reviewer</label>
              <label class="checkbox-row"><input id="adminRoleAdmin" type="checkbox" ${row.is_admin ? "checked" : ""} />Admin</label>
              <div class="button-row"><button id="adminRoleSaveButton" type="button">Save Roles</button></div>
              <p id="adminRoleMessage" class="inline-message"></p>
            `;
            byId("adminRoleSaveButton").addEventListener("click", async () => {
              const response = await apiJson(`${config.apiPrefix}/admin/users/${encodeURIComponent(row.id)}/roles`, "POST", {
                is_reviewer: byId("adminRoleReviewer").checked,
                is_admin: byId("adminRoleAdmin").checked,
              });
              byId("adminRoleMessage").textContent = `Updated roles for ${response.item.username}.`;
            });
            return;
          }
          const response = await apiJson(`${config.apiPrefix}/admin/users/${encodeURIComponent(row.id)}/status`, "POST", { action });
          byId("adminEditor").innerHTML = `${fmtJson(response.item)}<p class="inline-message">Executed ${action} for ${row.username}.</p>`;
        });
        const createButton = byId("announcementCreateButton");
        if (createButton) {
          createButton.addEventListener("click", async () => {
            const response = await apiJson(`${config.apiPrefix}/admin/announcements`, "POST", {
              title: byId("announcementCreateTitle").value.trim(),
              summary: byId("announcementCreateSummary").value,
              is_pinned: byId("announcementCreatePinned").checked,
            });
            byId("announcementCreateMessage").textContent = `Published announcement #${response.item.id}.`;
            await renderAdminPage();
          });
        }
        hydrateActionTable("adminAnnouncements", announcements, async (action, row) => {
          if (!row) {
            return;
          }
          if (action === "delete") {
            if (!window.confirm(`Delete announcement ${row.id}?`)) {
              return;
            }
            await apiRequest(`${config.apiPrefix}/admin/announcements/${encodeURIComponent(row.id)}`, { method: "DELETE" });
            await renderAdminPage();
            return;
          }
          byId("announcementEditor").innerHTML = `
            <h4>Edit Announcement #${escapeHtml(row.id)}</h4>
            <label>Title<input id="announcementEditTitle" value="${escapeHtml(firstNonEmpty(row.title))}" /></label>
            <label>Summary<textarea id="announcementEditSummary">${escapeHtml(firstNonEmpty(row.summary))}</textarea></label>
            <label class="checkbox-row"><input id="announcementEditPinned" type="checkbox" ${row.is_pinned ? "checked" : ""} />Pin announcement</label>
            <div class="button-row"><button id="announcementSaveButton" type="button">Save</button></div>
            <p id="announcementEditMessage" class="inline-message"></p>
            <h4 style="margin-top:16px;">Edit History</h4>
            ${safeArray(row.edit_history).length ? fmtJson(row.edit_history) : emptyState("No edit history yet.")}
          `;
          byId("announcementSaveButton").addEventListener("click", async () => {
            const response = await apiJson(`${config.apiPrefix}/admin/announcements/${encodeURIComponent(row.id)}`, "PUT", {
              title: byId("announcementEditTitle").value.trim(),
              summary: byId("announcementEditSummary").value,
              is_pinned: byId("announcementEditPinned").checked,
            });
            byId("announcementEditMessage").textContent = `Announcement #${response.item.id} updated.`;
            await renderAdminPage();
          });
        });
      }
    );
  }

  const pageRenderers = {
    home: renderHomePage,
    history: renderHistoryPage,
    upload: renderUploadPage,
    events: renderEventsPage,
    timing: renderTimingPage,
    timeline: renderTimelinePage,
    errors: renderErrorsPage,
    parameters: renderParametersPage,
    diagnosis: renderDiagnosisPage,
    files: renderFilesPage,
    unknown: renderUnknownPage,
    rules: renderRulesPage,
    config: renderConfigPage,
    solutions: renderSolutionsPage,
    exports: renderExportsPage,
    admin: renderAdminPage,
  };

  async function renderCurrentPage() {
    dom.pageTitle.textContent = navLabels[state.currentPage] || state.currentPage;
    document.querySelectorAll(".nav-button").forEach((button) => {
      button.setAttribute("data-active", button.getAttribute("data-page") === state.currentPage ? "true" : "false");
    });
    dom.pageMount.innerHTML = pagePanel(navLabels[state.currentPage] || state.currentPage, "", `<div class="empty-state">Loading page...</div>`);
    try {
      await pageRenderers[state.currentPage]();
    } catch (error) {
      dom.pageMount.innerHTML = pagePanel(navLabels[state.currentPage] || state.currentPage, "", `<div class="empty-state">${escapeHtml(error.message)}</div>`);
    }
  }

  async function handleLogin(event) {
    event.preventDefault();
    try {
      const result = await apiRequest(
        `${config.apiPrefix}/auth/login`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            login_name: byId("loginName").value.trim(),
            password: byId("loginPassword").value,
          }),
        },
        false
      );
      setToken(result.token || "");
      await refreshCurrentUser();
      setAuthMessage("Login succeeded.");
      await renderCurrentPage();
    } catch (error) {
      setAuthMessage(error.message);
    }
  }

  async function handleLogout() {
    try {
      if (getToken()) {
        await apiRequest(`${config.apiPrefix}/auth/logout`, { method: "POST" });
      }
    } catch (_error) {
    } finally {
      setToken("");
      state.currentUser = null;
      updateUserBadge();
      setAuthMessage("Logged out.");
      await renderCurrentPage();
    }
  }

  async function handleRegisterStart(event) {
    event.preventDefault();
    const password = byId("registerPassword").value;
    const confirmPassword = byId("registerPasswordConfirm").value;
    if (password !== confirmPassword) {
      setAuthMessage("两次输入的密码不一致。");
      return;
    }
    await apiRequest(
      `${config.apiPrefix}/auth/register`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: byId("registerUsername").value.trim(),
          email: byId("registerEmail").value.trim(),
          password,
          registration_note: byId("registerNote").value,
        }),
      },
      false
    );
    setAuthMessage("注册申请已提交，等待管理员审核。");
    byId("registerUsername").value = "";
    byId("registerEmail").value = "";
    byId("registerPassword").value = "";
    byId("registerPasswordConfirm").value = "";
    byId("registerNote").value = "";
  }

  async function bootstrap() {
    saveSelectedTask(window.localStorage.getItem(TASK_KEY) || "");
    updateUserBadge();
    dom.globalTaskSelect.addEventListener("change", async () => {
      saveSelectedTask(dom.globalTaskSelect.value);
      await refreshTasks();
      await renderCurrentPage();
    });
    dom.refreshGlobalTaskButton.addEventListener("click", async () => {
      await refreshTasks();
      await renderCurrentPage();
    });
    dom.quickRefreshButton.addEventListener("click", renderCurrentPage);
    dom.openDocsButton.addEventListener("click", () => window.open(config.docsUrl || "/docs", "_blank", "noreferrer"));
    document.querySelectorAll(".nav-button").forEach((button) => {
      button.addEventListener("click", async () => {
        state.currentPage = button.getAttribute("data-page") || "home";
        await renderCurrentPage();
      });
    });
    dom.loginForm.addEventListener("submit", handleLogin);
    dom.logoutButton.addEventListener("click", handleLogout);
    dom.registerStartForm.addEventListener("submit", handleRegisterStart);
    dom.changePasswordForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (byId("newPassword").value !== byId("confirmNewPassword").value) {
        setAuthMessage("New passwords do not match.");
        return;
      }
      await apiRequest(`${config.apiPrefix}/auth/change-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          current_password: byId("currentPassword").value,
          new_password: byId("newPassword").value,
        }),
      });
      setAuthMessage("Password changed successfully.");
    });
    await refreshHealth();
    await refreshCurrentUser();
    await refreshTasks();
    await renderCurrentPage();
  }

  bootstrap().catch((error) => {
    console.error(error);
    dom.pageMount.innerHTML = pagePanel("Initialization Failed", "", `<div class="empty-state">${escapeHtml(error.message)}</div>`);
  });
})();









