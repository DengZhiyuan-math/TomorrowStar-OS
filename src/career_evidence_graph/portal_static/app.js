"use strict";

const $ = (id) => document.getElementById(id);
const fields = ["company", "role_title", "status", "track", "location", "url", "application_date", "deadline", "next_action", "notes", "job_description", "application_strategy", "jd_match", "evidence_match", "personal_priority", "target_company", "compensation_priority", "strategy_notes"];
const viewLabels = { "resume-review": "简历审阅（Prism）", flow: "单岗位工作台", handoff: "申请交接", overview: "今日工作", applications: "岗位与进度", evidence: "职业证据", interview: "项目访谈", website: "公开展示" };
const kindLabels = { project_report: "项目报告", report: "项目报告", reports: "项目报告", candidate: "候选经历", experience: "经历", contribution: "贡献", skill: "技能记录", assessment: "评估记录", evidence: "证据", source: "来源材料", inventory: "经历清单", context: "背景材料", profile: "个人资料" };
const evidenceStatusLabels = { documentary: "来源材料 · 未作能力审核", candidate: "候选 · 待审核", pending: "待审核", unreviewed: "未审核", proposed: "候选 · 待审核", reviewed: "已审核", accepted: "已确认", confirmed: "已确认", verified: "已验证", rejected: "未采纳", superseded: "已被后继版本替代", draft: "草稿" };
let data = { applications: [], evidence: [], statuses: [], tracks: [], connections: {}, csrf_token: "" };
let view = "overview";
let stateReady = false;
let refreshing = false;
let editing = null;
let initialForm = null;
let selectedEvidence = new Set();
let saving = false;
let creationRequest = null;
let sourceRequest = null, sourceBusy = false, sourceUnknown = false, sourceTimer = null, sourceStateLoaded = false;
const unknownEdits = new Set();
let detailRequest = 0;
let evidenceRequest = 0;
const evidenceDrafts = new Map();
let toastTimer;
let evidenceView = "table";
let libraryData = null;
let libraryLoading = false;
let libraryRequest = 0;
const closedGroups = new Set();
const categoryLabels = { internship: "实习", project: "项目", open_source: "开源贡献", research: "研究", publication: "论文", teaching: "教学", education: "学历", related: "其他" };
const categoryOrder = Object.keys(categoryLabels);
let interviewLayer = 0;
let checkedInterview = null;
let interviewRequest = 0;
let protocolLoaded = false;
let protocolLoading = false;
let overviewHandoff = null, overviewFlow = null;
const interviewLayers = [
  { title: "项目介绍", description: "像面试开场一样，简要介绍项目要解决的问题、主要内容、技术主线、本人贡献和结果。时间只作为表达目标，不做计时考试。", criteria: ["整体介绍准确、有结构，能让人理解项目为什么做、怎样做。", "本人贡献与团队、他人、工具的工作分开，结果和限制讲清楚。"], boundary: "介绍流畅可以支持沟通判断，但不能单独证明技术掌握程度。" },
  { title: "技术深挖", description: "围绕实际贡献，考察能否解释技术机制、选择依据、实现或研究推理，以及验证方式。允许先查看相关资料，再回答一个具体问题。", criteria: ["能解释机制和取舍，并用验证依据说明为什么成立。", "能识别假设、限制和合理替代方案，明确自己的责任与协助范围。"], boundary: "不考察精确旧数值或文件名。理解团队或工具产物，不等于原先由本人编写。" },
  { title: "举一反三", description: "从项目中已经查阅的技术机制出发，改变一个明确条件，再考察如何应用于相似问题。拓展问题必须与原项目有关。", criteria: ["能指出仍可复用的机制，以及变化后不再成立的假设。", "能提出合理调整、适用限制和可验证的检查方案。"], boundary: "迁移回答是推理证据，不代表新场景已经实施、部署或形成另一项真实成果。" },
];

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined && text !== null) element.textContent = String(text);
  return element;
}

function clear(element) { element.replaceChildren(); return element; }
function string(value) { return typeof value === "string" ? value : ""; }
function statusLabel(status) { return data.statuses.find((item) => item.value === status)?.label || status || "未设置"; }
function kindLabel(kind) { return kindLabels[kind] || kind || "材料"; }
function evidenceStatusLabel(status) { return evidenceStatusLabels[status] || status || "审核状态未提供"; }
function localDate(date = new Date()) { return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`; }
function dateValue(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(string(value))) return null;
  const timestamp = new Date(`${value}T12:00:00`).getTime();
  return Number.isFinite(timestamp) ? timestamp : null;
}
function deadlineInfo(value) {
  const timestamp = dateValue(value);
  if (timestamp === null) return { text: value ? `截止：${value}` : "未设日期", className: "" };
  const days = Math.round((timestamp - dateValue(localDate())) / 86400000);
  if (days < 0) return { text: `逾期 ${Math.abs(days)} 天`, className: "is-overdue" };
  if (days === 0) return { text: "今天截止", className: "is-urgent" };
  if (days === 1) return { text: "明天截止", className: "is-urgent" };
  if (days <= 7) return { text: `${days} 天后截止`, className: "is-urgent" };
  return { text: `${value.slice(5).replace("-", "/")} 截止`, className: "" };
}
function isClosed(application) { return ["rejected", "withdrawn", "accepted", "closed", "no_response"].includes(application.status); }
function needsAction(application) {
  if (isClosed(application)) return false;
  const deadline = dateValue(application.deadline);
  const flagged = typeof application.needs_action === "boolean" ? application.needs_action : Boolean(string(application.next_action).trim());
  return flagged || (deadline !== null && deadline - dateValue(localDate()) <= 7 * 86400000);
}
function safeURL(value) {
  try { const url = new URL(value); return ["http:", "https:"].includes(url.protocol) ? url.href : null; } catch { return null; }
}
function statusClass(status, evidence = false) {
  if (evidence) {
    if (["reviewed", "accepted", "confirmed", "verified"].includes(status)) return "reviewed";
    if (["candidate", "pending", "unreviewed", "proposed", "draft"].includes(status)) return "candidate";
    return "unknown";
  }
  if (status === "offer") return "offer";
  if (status === "rejected") return "rejected";
  if (["withdrawn", "closed", "no_response", "likely_no_response"].includes(status)) return "withdrawn";
  if (["interview_scheduled", "assessment_pending", "recruiter_replied", "interview"].includes(status)) return "interview";
  if (["applied", "confirmation_received", "waiting", "assessment_submitted"].includes(status)) return "applied";
  return "unknown";
}
function badge(status, evidence = false) { return node("span", `status-badge status-${statusClass(status, evidence)}`, evidence ? evidenceStatusLabel(status) : statusLabel(status)); }
function avatar(company, index = 0) { return node("span", `company-avatar tone-${index % 4}`, Array.from(company || "?").slice(0, 2).join("")); }
function toast(message) {
  clearTimeout(toastTimer);
  $("toast").textContent = message;
  $("toast").hidden = false;
  toastTimer = setTimeout(() => { $("toast").hidden = true; }, 4500);
}
function notice(id, message, error = false) {
  const element = $(id);
  element.textContent = message;
  element.classList.toggle("is-error", error);
  element.hidden = !message;
}
function confirmAction(message, actionLabel = "放弃并继续") {
  const dialog = $("confirmation-dialog");
  if (dialog.open) return Promise.resolve(false);
  $("confirmation-message").textContent = message;
  $("confirmation-continue").textContent = actionLabel;
  dialog.returnValue = "cancel";
  return new Promise((resolve) => {
    dialog.addEventListener("close", () => resolve(dialog.returnValue === "continue"), { once: true });
    dialog.showModal();
  });
}
function empty(container, title, description, addButton = false) {
  const section = node("div", "empty-state");
  section.append(node("div", "empty-icon", "◇"), node("strong", "", title), node("p", "", description));
  if (addButton) { const button = node("button", "button button-secondary", "＋ 记录第一个机会"); button.type = "button"; button.addEventListener("click", () => openApplication()); section.append(button); }
  container.append(section);
}
async function api(path, options = {}) {
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, 30000);
  const abort = () => controller.abort();
  if (options.signal?.aborted) abort();
  options.signal?.addEventListener("abort", abort, { once: true });
  try {
    let response;
    try { response = await fetch(path, { credentials: "same-origin", cache: "no-store", ...options, signal: controller.signal, headers: { Accept: "application/json", ...(options.body ? { "Content-Type": "application/json", "X-CSRF-Token": data.csrf_token } : {}), ...options.headers } }); }
    catch { throw new Error(timedOut ? "工作台响应超时，操作结果尚未核验。请在当前页面核验。" : "连接中断。请确认本机工作台仍在运行，然后核验操作结果。"); }
    let body;
    try { body = await response.json(); } catch { throw new Error(timedOut ? "工作台响应超时，操作结果尚未核验。请在当前页面核验。" : options.method && options.method !== "GET" ? "工作台响应无法读取，操作结果尚未核验。请在当前页面核验并重试。" : "工作台返回了无法读取的响应，请刷新后重试。"); }
    if (!response.ok) {
      const error = new Error(string(body.message) || "操作未完成，请稍后重试。");
      error.status = response.status;
      error.code = body.error;
      throw error;
    }
    return body;
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener("abort", abort);
  }
}

function setConnection(id, connected, loading = false) {
  const element = $(id);
  element.classList.toggle("is-connected", connected === true);
  element.classList.toggle("is-disconnected", !loading && connected !== true);
  element.lastElementChild.textContent = loading ? "连接中" : connected === true ? "已连接" : "未连接";
}
async function loadState({ silent = false } = {}) {
  if (refreshing) return;
  refreshing = true;
  $("refresh-button").disabled = true;
  if (!stateReady) $("add-application").disabled = true;
  try {
    const next = await api("/api/state");
    if (!Array.isArray(next.applications) || !Array.isArray(next.evidence) || !Array.isArray(next.statuses) || !Array.isArray(next.tracks) || !string(next.csrf_token)) throw new Error("工作台数据不完整，请检查本机数据连接后重试。");
    data = next;
    stateReady = true;
    notice("page-notice", next.worker_warning?.message || "", Boolean(next.worker_warning));
    $("loading-state").hidden = true;
    $("page-content").hidden = false;
    $("add-application").disabled = data.connections?.applications !== true;
    setConnection("applications-connection", data.connections?.applications);
    setConnection("career-connection", data.connections?.career);
    populateFilters();
    render();
    window.dispatchEvent?.(new Event("portal-state"));
    resetExperienceTable();
    if (view === "evidence" && evidenceView === "table") loadExperienceTable();
    if (view === "website") loadPublicSite();
    if (view === "resume-review" && typeof loadPrismReview === "function") loadPrismReview();
    if (!silent) toast("工作台已刷新");
  } catch (error) {
    $("loading-state").hidden = true;
    notice("page-notice", `${error.message}${stateReady ? " 当前仍显示上次载入的数据。" : " 请检查数据目录，或点击右上角刷新重试。"}`, true);
    setConnection("applications-connection", false);
    setConnection("career-connection", false);
    data.connections = { applications: false, career: false };
    $("add-application").disabled = true;
  } finally { refreshing = false; $("refresh-button").disabled = false; }
}
function fillSelect(select, items, placeholder) {
  const previous = select.value;
  clear(select);
  if (placeholder) { const option = node("option", "", placeholder); option.value = ""; select.append(option); }
  for (const item of items) { const option = node("option", "", typeof item === "string" ? item : item.label); option.value = typeof item === "string" ? item : item.value; select.append(option); }
  if ([...select.options].some((option) => option.value === previous)) select.value = previous;
}
function populateFilters() {
  fillSelect($("status-filter"), data.statuses, "全部状态");
  const tracks = [...new Set([...data.tracks, ...data.applications.map((item) => item.track).filter(Boolean)])].sort((a, b) => a.localeCompare(b));
  fillSelect($("track-filter"), tracks, "全部方向");
  const datalist = clear($("track-options"));
  for (const track of tracks) { const option = node("option"); option.value = track; datalist.append(option); }
  fillSelect($("evidence-kind-filter"), [...new Set(data.evidence.map((item) => item.kind).filter(Boolean))].map((kind) => ({ value: kind, label: kindLabel(kind) })), "全部类型");
  fillSelect($("evidence-status-filter"), [...new Set(data.evidence.map((item) => item.status).filter(Boolean))].map((status) => ({ value: status, label: evidenceStatusLabel(status) })), "全部状态");
}
function render() {
  $("nav-application-count").textContent = data.applications.length;
  $("nav-evidence-count").textContent = libraryData ? libraryData.length : (Number.isInteger(data.experience_count) ? data.experience_count : "—");
  renderOverview(); renderApplications(); renderEvidence(); renderInterview();
}
function setView() {
  view = Object.hasOwn(viewLabels, location.hash.slice(1)) ? location.hash.slice(1) : "overview";
  for (const name of Object.keys(viewLabels)) $("view-" + name).hidden = name !== view;
  for (const link of document.querySelectorAll("[data-view]")) {
    if (link.dataset.view === view) link.setAttribute("aria-current", "page"); else link.removeAttribute("aria-current");
  }
  $("current-view-label").textContent = viewLabels[view];
  document.title = `${viewLabels[view]} · TomorrowStar`;
  if (view === "evidence" && stateReady && evidenceView === "table") loadExperienceTable();
  if (view === "website" && stateReady) loadPublicSite();
  if (view === "resume-review" && stateReady && typeof loadPrismReview === "function") loadPrismReview();
}

async function loadPublicSite() {
  const container = $("website-content");
  try {
    const site = await api("/api/public-site");
    const profile = site.profile;
    const projects = [...site.aiProjects, ...site.financeProjects];
    const heading = node("h2", "", profile.name);
    const intro = node("p", "", `${profile.title} · ${profile.location}`);
    const counts = node("p", "", `${profile.education.length} 段教育经历 · ${profile.experience.length} 段工作经历 · ${projects.length} 个项目 · ${site.skills.length} 个技能标签 · ${site.knowledge.length} 项公开资料`);
    const note = node("p", "", "本机预览。网站构建时同步这些内容；上线发布需要单独执行。");
    const list = node("ul", "");
    for (const project of projects) list.append(node("li", "", project.title));
    const skills = node("p", "", site.skills.map((skill) => skill.name).join(" · "));
    container.replaceChildren(heading, intro, counts, note, node("h3", "", "项目"), list, node("h3", "", "技能标签"), skills);
  } catch (error) {
    container.replaceChildren(node("p", "", error.message));
  }
}

function resetExperienceTable() {
  ++libraryRequest;
  libraryData = null;
  libraryLoading = false;
}

async function loadExperienceTable() {
  if (libraryLoading || !stateReady) return;
  const container = $("experience-table");
  if (!libraryData) {
    const request = ++libraryRequest;
    libraryLoading = true;
    const loading = node("p", "experience-table-message", "正在载入经历库…");
    loading.setAttribute("role", "status");
    container.replaceChildren(loading);
    try {
      const next = await api("/api/career-library");
      if (request !== libraryRequest) return;
      if (!Array.isArray(next.records)) throw new Error("经历库数据不完整，请刷新后重试。");
      libraryData = next.records;
      $("nav-evidence-count").textContent = libraryData.length;
    } catch (error) {
      if (request !== libraryRequest) return;
      const message = node("p", "experience-table-message", error.message);
      message.setAttribute("role", "alert");
      const retry = node("button", "button button-secondary", "重新载入经历库");
      retry.type = "button";
      retry.addEventListener("click", loadExperienceTable);
      container.replaceChildren(message, retry);
      return;
    } finally { if (request === libraryRequest) libraryLoading = false; }
  }
  renderExperienceTable();
}

function renderExperienceTable() {
  if (!libraryData) return;
  const container = clear($("experience-table"));
  const query = $("experience-search").value.trim().toLocaleLowerCase();
  const rows = libraryData.filter((item) => !query || [item.title, item.summary, item.institution, ...(Array.isArray(item.retrieval_terms) ? item.retrieval_terms : [])].some((value) => string(value).toLocaleLowerCase().includes(query)));
  const groups = new Map();
  for (const item of rows) {
    const key = item.category || "related";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(item);
  }
  const rank = (key) => (categoryOrder.includes(key) ? categoryOrder.indexOf(key) : categoryOrder.length);
  const keys = [...groups.keys()].sort((a, b) => rank(a) - rank(b));
  $("experience-result-count").textContent = `${rows.length} 段经历`;
  if (!keys.length) { empty(container, "没有找到匹配的经历", "尝试其他关键词。"); return; }
  for (const key of keys) {
    const section = node("details", "experience-group");
    section.open = !closedGroups.has(key);
    section.addEventListener("toggle", () => { if (section.open) closedGroups.delete(key); else closedGroups.add(key); });
    const summary = node("summary");
    summary.append(node("strong", "", categoryLabels[key] || key), node("span", "nav-count", groups.get(key).length));
    const table = node("table", "experience-table");
    const headRow = node("tr");
    for (const label of ["经历", "简介"]) headRow.append(node("th", "", label));
    const head = node("thead"); head.append(headRow);
    const body = node("tbody");
    for (const item of groups.get(key)) {
      const row = node("tr");
      const name = node("td", "experience-name", item.title);
      const meta = [item.institution, item.dates].map(string).filter(Boolean).join(" · ");
      if (meta) name.append(node("div", "experience-meta", meta));
      const text = node("td", "experience-summary");
      text.append(node("div", "experience-summary-text", item.summary || "—"));
      text.title = item.summary || "";
      row.append(name, text);
      body.append(row);
    }
    table.append(head, body);
    section.append(summary, table);
    container.append(section);
  }
}

function setEvidenceView(mode) {
  evidenceView = mode;
  $("evidence-table-view").hidden = mode !== "table";
  $("evidence-library-view").hidden = mode !== "library";
  $("show-evidence-table").setAttribute("aria-pressed", String(mode === "table"));
  $("show-evidence-library").setAttribute("aria-pressed", String(mode === "library"));
  if (mode === "table") loadExperienceTable();
}
function renderWorkflow() {
  const automatic = overviewFlow?.flow?.enabled === true && overviewFlow.flow.mode === "application";
  const steps = automatic ? [
    ["收录岗位", "邮件、网页或粘贴 JD"], ["自动匹配", "复用已保存的个人资料"], ["自动生成简历", "生成并检查岗位材料"], ["填写并上传", "继续当前岗位"], ["原页确认提交", "最终 Submit 由你操作"],
  ] : [
    ["准备资料", "岗位与已复核 PDF"], ["Codex 领取", "复制任务，明确执行者"], ["保存回读", "核对字段与附件"], ["复核并提交", "由你在原页面操作"], ["更新记录", "同步进度，补录回执"],
  ];
  $("overview-introduction").textContent = automatic ? "邮件推荐、岗位匹配、专用简历和填写自动衔接，完成后通知你最终确认。" : "准备好资料，交接给 Codex，再由你复核和提交。";
  $("workflow-note-title").textContent = automatic ? "自动衔接，按岗位推进" : "一次交接，一个岗位";
  $("workflow-note-description").textContent = automatic ? "系统整理岗位与资料，生成材料并填写。完成后到原申请页面最终确认。" : "批准的简历与当前岗位绑定。回读后由你核对，再手动提交。";
  $("workflow-note-path").textContent = automatic ? "收录 → 匹配 → 简历 → 填写 → 最终确认" : "资料准备 → 执行 → 人工确认";
  $("flow-navigation-label").textContent = automatic ? "自动申请" : overviewFlow?.flow?.mode === "preparation" ? "材料准备" : "单岗位工作台";
  document.querySelector('[data-view="handoff"]').hidden = automatic && overviewHandoff?.enabled === false;
  for (const item of document.querySelectorAll("[data-workflow-step]")) {
    const [title, description] = steps[Number(item.dataset.workflowStep)];
    item.querySelector("strong").textContent = title;
    item.querySelector("div > span").textContent = description;
  }
  const current = overviewHandoff?.activeTask;
  let label = "正在核对交接记录", title = "读取当前任务…", description = "根据已保存的状态，找到需要你处理的下一步。", action = "查看申请交接", destination = "#handoff", step = -1;
  if (automatic) {
    const pipeline = overviewFlow.pipeline;
    const item = pipeline?.items?.find(item => pipeline.current_recommendation_id && item.recommendation_id === pipeline.current_recommendation_id || pipeline.active_task_id && item.task_id === pipeline.active_task_id);
    const readable = overviewFlow.readable.flow && overviewFlow.readable.pipeline;
    label = readable ? overviewFlow.statusText || "自动申请流程" : "自动申请状态暂不可用";
    title = [item?.company, item?.role_title].filter(Boolean).join(" · ") || "按顺序处理推荐岗位。";
    description = readable ? pipeline?.notification?.message || "系统自动衔接岗位读取、匹配、简历、填写与上传。需要补充信息或最终确认时会通知你。" : "已保存的岗位和进度保留。进入自动申请读取最新状态。";
    action = pipeline?.active_task_id ? "查看当前岗位与材料" : "查看自动申请";
    destination = "#flow";
    // A paused or stopped job keeps the step it stopped in (resume_status), e.g. the
    // résumé plan review stays on 自动生成简历 (2026-11-12).
    const stepOf = { matching: 1, generating_resume: 2, preparing: 2, starting_worker: 3, admitting_worker: 3, awaiting_native_check: 3, recovering_worker: 3, filling: 3, ready_for_review: 4 };
    step = readable ? stepOf[pipeline?.status] ?? stepOf[pipeline?.resume_status] ?? 0 : -1;
  } else if (overviewHandoff?.stale) {
    label = "交接状态待核验"; title = "先核对记录，再继续操作。";
    description = "进入申请交接刷新持久记录。保留原页面与附件，核验后再继续。"; action = "核对交接记录";
  } else if (overviewHandoff?.enabled === false) {
    label = "交接尚未连接"; title = "先整理岗位与申请资料。";
    description = "可以导入 JD 或岗位链接并自动保存。申请交接连接后，继续处理已保存岗位。"; action = "查看连接说明";
  } else if (overviewHandoff?.enabled === true) {
    if (current) {
      const stages = {
        prepared: [1, "等待 Codex 领取", "复制领取任务，交给 Codex", "资料已准备。将任务复制到 Codex 对话，由执行者领取后操作。"],
        claimed: [2, "Codex 操作中", "等待 Codex 保存回读", "当前任务已领取。完成页面操作后，先保存字段、附件与来源证据。"],
        needs_input: [2, "需要你补充", "补充已确认的答案", "查看网站问题，确认答案及适用范围后保存，再核验当前任务。"],
        needs_recheck: [2, "需要先核验", "核验原页面与资料", "操作结果或输入已发生变化。保留原页面，核对字段与附件后记录结论。"],
        ready_for_review: [3, "等待你复核", "核对页面字段与批准附件", "Codex 已保存回读。请查看原页面并记录复核结论，再由你手动提交。"],
        reviewed: [3, "等待你手动提交", "在原页面提交后，回来记录", "复核已保存。由你在招聘页面点击 Submit，再确认已提交并说明来源。"],
        submitted: [4, "等待接收来源", "补录提交回执", "提交声明已保存。核验确认页或邮件后，记录回执位置或编号。"],
        confirmed: [4, "回执已记录", "查看本次申请记录", "本地已保存提交与接收来源声明，可以查看完整记录。"],
        cancelled: [-1, "交接已停止", "核对任务的收尾状态", "查看任务记录，确认操作权释放后再准备下一份申请。"],
      };
      [step, label, action, description] = stages[current.status] || [-1, "状态待核验", "查看任务记录", "请进入申请交接核对当前任务。"];
      title = [current.company, current.role_title].filter(Boolean).join(" · ") || "当前申请任务";
      if (current.pending_sync || current.sync_error || current.release_pending) {
        step = current.status === "cancelled" ? -1 : 4; label = "记录收尾待核验"; action = current.status === "cancelled" ? "完成操作权释放" : "核对记录同步";
        description = "先核对已保存的证据，完成记录同步或操作权释放。此步骤不重复网页操作。";
      }
    } else {
      const receipts = (overviewHandoff.tasks || []).filter(item => item.status === "submitted").length;
      step = 0; label = "可以准备下一份申请"; title = data.applications.length ? "选一个岗位，准备好再交接。" : "从记录第一个机会开始。";
      description = "从已保存岗位继续，使用已确认的材料；只补充当前申请必需的未知信息。";
      action = data.applications.length ? "准备单岗位交接" : "导入岗位来源";
      if (!data.applications.length) destination = "#applications";
      if (receipts) { label = `${receipts} 份申请待补回执`; title = "提交之后，留下接收来源。"; description = "已提交的申请仍可补录确认页或邮件来源。也可以继续准备下一份任务。"; action = "查看交接与回执"; step = 4; destination = "#handoff"; }
    }
  }
  // 2026-11-12 (user decision): with automatic applications the current application
  // card leads the 自动申请 page; 今日工作 lists 今日投递 instead.
  const card = $("workflow-focus");
  const flowHeading = document.querySelector("#flow-root > .page-heading");
  if (automatic && flowHeading && flowHeading.nextElementSibling !== card) flowHeading.after(card);
  if (!automatic && card.parentElement !== $("view-overview")) $("today-applications").before(card);
  $("workflow-state").textContent = label;
  $("workflow-title").textContent = title;
  $("workflow-description").textContent = description;
  $("workflow-primary").textContent = `${action} →`;
  $("workflow-primary").href = destination;
  for (const item of document.querySelectorAll("[data-workflow-step]")) {
    const index = Number(item.dataset.workflowStep);
    item.classList.toggle("is-current", index === step);
    item.classList.toggle("is-complete", step >= 0 && index < step);
    if (index === step) item.setAttribute("aria-current", "step"); else item.removeAttribute("aria-current");
  }
}
function renderOverview() {
  renderWorkflow();
  const active = data.applications.filter((item) => !isClosed(item));
  const action = data.applications.filter(needsAction).sort((a, b) => (dateValue(a.deadline) ?? Infinity) - (dateValue(b.deadline) ?? Infinity));
  const interview = data.applications.filter((item) => ["interview", "interview_scheduled", "assessment_pending"].includes(item.status));
  const offers = data.applications.filter((item) => item.status === "offer");
  const stats = [
    ["进行中的投递", active.length, `共 ${data.applications.length} 条投递记录`, "↗", ""],
    ["记录中的待办", action.length, action.length ? "按截止日期安排下一步" : "暂时没有记录待办", "◷", "accent"],
    ["面试与测评", interview.length, "把准备留给真正重要的机会", "◉", ""],
    ["收到的 Offer", offers.length, "值得认真比较的下一站", "✦", ""],
  ];
  const grid = clear($("overview-stats"));
  for (const [label, value, note, icon, accent] of stats) {
    const stat = node("div", `stat ${accent}`);
    const symbol = node("span", "stat-icon", icon); symbol.setAttribute("aria-hidden", "true");
    stat.append(node("span", "stat-label", label), node("strong", "stat-value", value), node("span", "stat-note", note), symbol);
    grid.append(stat);
  }
  $("action-count").textContent = `${action.length} 项待办`;
  const queue = clear($("action-queue"));
  if (!action.length) empty(queue, "下一步，留一点从容", data.applications.length ? "暂时没有需要行动的记录。可为正在跟进的岗位设置下一步和截止日期。" : "记录感兴趣的岗位，让每个机会都有下一步。", !data.applications.length);
  for (const [index, application] of action.slice(0, 5).entries()) queue.append(applicationRow(application, index, true));
  if (action.length > 5) {
    const more = node("button", "panel-footer-link action-more", `查看全部 ${action.length} 项待办 →`);
    more.type = "button"; more.addEventListener("click", () => { $("action-only").checked = true; renderApplications(); location.hash = "applications"; }); queue.append(more);
  }
  const pipeline = clear($("pipeline-summary")); pipeline.className = "pipeline-summary";
  const groups = [
    ["准备投递", data.applications.filter((item) => item.status === "drafting").length],
    ["投递与跟进", data.applications.filter((item) => ["applied", "confirmation_received", "waiting", "recruiter_replied", "follow_up_optional", "likely_no_response"].includes(item.status)).length],
    ["面试与测评", data.applications.filter((item) => ["interview", "interview_scheduled", "assessment_pending", "assessment_submitted"].includes(item.status)).length],
    ["Offer", offers.length],
  ];
  for (const [label, count] of groups) {
    const item = node("div", "pipeline-item"); const heading = node("div", "pipeline-label"); heading.append(node("span", "", label), node("strong", "", count));
    const track = node("progress", "pipeline-track"); track.max = Math.max(1, data.applications.length); track.value = count; track.setAttribute("aria-label", `${label}：${count} 条`);
    item.append(heading, track); pipeline.append(item);
  }
  const recent = clear($("recent-applications"));
  if (!data.applications.length) empty(recent, "你的新机会，从第一条记录开始", "保存岗位链接、跟进日期和相关经历，一处找到。", true);
  for (const [index, application] of data.applications.slice(0, 4).entries()) recent.append(applicationRow(application, index, false));
  const summary = clear($("evidence-summary"));
  const count = node("span"); count.append(node("strong", "", data.evidence.length), document.createTextNode("份材料"));
  const linked = node("span"); linked.append(node("strong", "", data.applications.filter((item) => item.linked_evidence?.length).length), document.createTextNode("条投递已关联"));
  summary.append(count, linked);
}
function applicationRow(application, index, action) {
  const button = node("button", `action-row ${action ? "" : "compact-row"}`); button.type = "button";
  const main = node("span", "row-main"); main.append(node("strong", "", action ? application.next_action || statusLabel(application.status) : application.company), node("small", "", action ? `${application.company} · ${application.role_title}` : application.role_title));
  const side = node("span", "row-side");
  if (action) { const deadline = deadlineInfo(application.deadline); side.append(node("span", `deadline ${deadline.className}`, deadline.text), node("small", "", statusLabel(application.status))); }
  else side.append(badge(application.status));
  button.append(avatar(application.company, index), main, side, node("span", "row-arrow", "›")); button.addEventListener("click", () => openApplication(application));
  return button;
}
function renderApplications() {
  const terms = $("application-search").value.normalize("NFKC").trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  const status = $("status-filter").value; const track = $("track-filter").value;
  const screening = $("screening-filter").value;
  const route = $("route-filter").value;
  const applications = data.applications.filter((item) => {
    const hints = item.screening || {};
    const candidate = item.status === "drafting" && hints.category !== "excluded";
    const matchesScreen = !screening || (screening === "target" && candidate && hints.target_relevant) || (screening === "worker" && hints.worker_preparable) || (screening === "review" && candidate && hints.target_relevant && hints.review_reasons?.length) || (screening === "manual" && candidate && !hints.worker_supported) || (screening === "excluded" && item.status === "drafting" && hints.category === "excluded");
    const text = [item.company, item.role_title, item.location, item.track, item.next_action, item.notes, item.job_description, statusLabel(item.status)].map(string).join(" ").normalize("NFKC").toLocaleLowerCase();
    return (!status || item.status === status) && (!track || item.track === track) && (!route || hints.application_route === route) && (!$("action-only").checked || needsAction(item)) && matchesScreen && terms.every(term => text.includes(term));
  });
  if ($("application-sort").value === "screening") applications.sort((a, b) => (a.screening?.priority ?? 4) - (b.screening?.priority ?? 4));
  $("application-result-count").textContent = applications.length === data.applications.length ? `${applications.length} 条投递记录` : `显示 ${applications.length} / ${data.applications.length} 条投递记录`;
  const list = clear($("application-list")); const emptyContainer = clear($("applications-empty")); emptyContainer.hidden = Boolean(applications.length);
  $("application-list").closest(".application-table-scroll").hidden = !applications.length;
  if (!applications.length) empty(emptyContainer, data.applications.length ? "没有找到匹配的投递" : "记录你的第一个机会", data.applications.length ? "试试其他关键词，或调整状态和方向筛选。" : "粘贴 JD 或岗位链接，系统会整理并保存。", !data.applications.length);
  for (const [index, application] of applications.entries()) {
    const row = node("tr"); const titleCell = node("td"); const button = node("button", "application-title-button"); button.type = "button";
    const main = node("span", "row-main"); main.append(node("strong", "", application.company), node("small", "", application.role_title));
    if (application.linked_evidence?.length) main.append(node("span", "table-evidence-count", `◇ ${application.linked_evidence.length} 项关联证据`));
    button.append(avatar(application.company, index), main); button.addEventListener("click", () => openApplication(application)); titleCell.append(button);
    if (window.WorkerPreview?.enabled && application.status === "drafting") {
      const choice = node("input"); choice.type = "checkbox"; choice.className = "worker-record-choice";
      choice.setAttribute("aria-label", `选择 ${application.company} ${application.role_title} 加入批次`);
      choice.disabled = application.screening?.batch_preparable !== true;
      choice.title = choice.disabled ? "当前不进入批量处理；仍可查看已保存岗位或进入单岗位工作台" : "加入批量投递";
      if (choice.disabled) window.WorkerPreview.selected.delete(application.id);
      choice.checked = window.WorkerPreview.selected.has(application.id);
      choice.addEventListener("change", () => window.WorkerPreview.select(application.id, choice.checked));
      titleCell.prepend(choice);
    }
    const statusCell = node("td"); statusCell.append(badge(application.status));
    const trackCell = node("td"); trackCell.append(node("span", "application-track", application.track || "—"));
    const actionCell = node("td"); const nextAction = node("span", "application-next-action", application.next_action || "尚未设置下一步"); nextAction.title = application.next_action || ""; actionCell.append(nextAction);
    if (application.status === "drafting" && application.screening) {
      const hints = application.screening;
      const routeNote = node("div", "application-routing");
      routeNote.append(node("strong", "application-screening-note", hints.application_route === "review" ? "未评估" : hints.route_label));
      if (hints.application_route !== "review") routeNote.append(node("small", "application-screening-note", (hints.route_reasons || []).join("；")));
      if (window.WorkerPreview?.enabled && hints.precision_preparable) {
        const precision = node("button", "button button-secondary", "单独精准准备"); precision.type = "button";
        precision.addEventListener("click", () => window.WorkerPreview.preparePrecision(application.id));
        routeNote.append(precision);
      }
      titleCell.append(routeNote);
      const note = node("small", "application-screening-note", `${hints.label} · ${hints.platform_label}`);
      const reasons = [...hints.reasons, ...hints.review_reasons].join("；");
      note.title = reasons; actionCell.append(note);
      if (reasons && hints.application_route !== "review") actionCell.append(node("small", "application-screening-note", reasons));
    }
    const dateCell = node("td"); const deadline = deadlineInfo(application.deadline); dateCell.append(node("span", `deadline ${deadline.className}`, application.deadline ? deadline.text : "—"));
    const openCell = node("td"); const open = node("button", "application-detail-button", "↗"); open.type = "button"; open.setAttribute("aria-label", `查看 ${application.company} ${application.role_title}`); open.addEventListener("click", () => openApplication(application)); openCell.append(open);
    row.append(titleCell, statusCell, trackCell, actionCell, dateCell, openCell); list.append(row);
  }
}
function renderEvidence() {
  const query = $("evidence-search").value.trim().toLocaleLowerCase();
  const kind = $("evidence-kind-filter").value; const status = $("evidence-status-filter").value;
  const items = data.evidence.filter((item) => (!kind || item.kind === kind) && (!status || item.status === status) && (!query || [item.title, item.summary, item.source_name, kindLabel(item.kind)].some((value) => string(value).toLocaleLowerCase().includes(query))));
  $("evidence-result-count").textContent = items.length === data.evidence.length ? `${items.length} 份职业材料` : `显示 ${items.length} / ${data.evidence.length} 份职业材料`;
  const container = clear($("evidence-list"));
  if (!items.length) empty(container, data.evidence.length ? "没有找到匹配的证据" : "职业证据尚未接入", data.evidence.length ? "尝试其他关键词或筛选条件。" : "私有职业工作区中的项目报告和经历材料会显示在这里。");
  for (const item of items) {
    const card = node("button", "evidence-card"); card.type = "button"; const meta = node("span", "evidence-meta"); meta.append(node("span", "kind-badge", kindLabel(item.kind)), badge(item.status, true));
    const footer = node("span", "evidence-card-footer"); const linkedCount = data.applications.filter((application) => application.linked_evidence?.includes(item.id)).length; footer.append(node("span", "", linkedCount ? `${linkedCount} 条投递已关联` : "尚未关联投递"), node("span", "", "查看原始材料 ↗"));
    card.append(meta, node("h3", "", item.title), node("p", "", item.summary || "打开查看完整来源材料。"), footer); card.addEventListener("click", () => openEvidence(item)); container.append(card);
  }
}

function renderInterview() {
  renderInterviewSources();
  renderInterviewLayer();
}
function renderInterviewSources() {
  const query = $("interview-evidence-search").value.trim().toLocaleLowerCase();
  const items = data.evidence.filter((item) => !query || [item.title, item.source_name].some((value) => string(value).toLocaleLowerCase().includes(query)));
  fillSelect($("interview-evidence"), items.map((item) => ({ value: item.id, label: `${item.title} · ${item.source_name}` })), items.length ? "请选择项目资料" : "没有匹配资料，请调整搜索");
  updateInterviewEvidence();
}
function updateInterviewEvidence() {
  const item = data.evidence.find((entry) => entry.id === $("interview-evidence").value);
  $("interview-open-evidence").disabled = !item;
  $("interview-evidence-note").textContent = item ? `${kindLabel(item.kind)} · ${evidenceStatusLabel(item.status)}。所选资料用于回忆；计划的来源引用另行检查。` : (data.evidence.length ? "资料用于理解上下文，不会自动形成能力评分。" : "当前没有可查看的职业资料；仍可浏览三层流程或检查已有计划。");
}
function renderInterviewLayer() {
  const layer = interviewLayers[interviewLayer];
  for (const button of document.querySelectorAll("[data-interview-layer]")) button.setAttribute("aria-pressed", String(Number(button.dataset.interviewLayer) === interviewLayer));
  $("interview-layer-title").textContent = layer.title;
  $("interview-layer-description").textContent = layer.description;
  const criteria = clear($("interview-layer-criteria"));
  for (const criterion of layer.criteria) criteria.append(node("li", "", criterion));
  $("interview-layer-boundary").textContent = layer.boundary;
  $("interview-difficulty-label").hidden = !checkedInterview || interviewLayer === 0;
  const preview = clear($("interview-plan-preview")); preview.hidden = !checkedInterview;
  if (!checkedInterview) return;
  preview.append(node("h3", "", "已检查计划 · 问题预览"), node("p", "small-label", "这些是准备题目。浏览预览不会开始问答或建立能力结论。"));
  const plan = checkedInterview;
  const questions = interviewLayer === 0 ? [{ prompt: plan.overview.prompt, evaluation_criteria: plan.overview.evaluation_criteria, reference: plan.overview.inspection_reference }] : plan[interviewLayer === 1 ? "depth_plans" : "transfer_plans"].flatMap((probe) => probe.areas.map((area) => ({ contribution_id: probe.contribution_id, prompt: area[{ hard: "demanding_prompt", intermediate: "intermediate_prompt", simple: "simple_prompt" }[$("interview-difficulty").value]], evaluation_criteria: area.evaluation_criteria[$("interview-difficulty").value], reference: area.inspected_fact_ids.join(" · "), changed_condition: area.changed_condition })));
  for (const question of questions) {
    const card = node("article", "interview-question");
    if (question.contribution_id) card.append(node("p", "small-label", `贡献：${question.contribution_id}`));
    if (question.changed_condition) card.append(node("p", "interview-changed-condition", `假设变化：${question.changed_condition}`));
    card.append(node("p", "interview-question-prompt", question.prompt), node("h3", "", "本题预先判据"));
    const rubric = node("ul");
    for (const criterion of question.evaluation_criteria) rubric.append(node("li", "", criterion));
    card.append(rubric, node("p", "small-label", `来源引用：${question.reference}`)); preview.append(card);
  }
}
function invalidateInterviewPlan() {
  ++interviewRequest;
  checkedInterview = null;
  notice("interview-plan-result", "");
  $("interview-check-plan").disabled = false;
  $("interview-check-plan").textContent = "检查并预览计划";
  renderInterviewLayer();
}
async function readInterviewJSON(file) {
  if (!file || file.size > 1048576) throw new Error("请选择不超过 1 MB 的 JSON 文件。");
  try { return JSON.parse(await file.text()); }
  catch { throw new Error("无法读取 JSON 文件，请检查文件格式后重试。"); }
}
async function checkInterviewPlan(event) {
  event.preventDefault();
  invalidateInterviewPlan();
  const request = interviewRequest;
  const experienceId = $("interview-experience-id").value.trim();
  const planFile = $("interview-plan-file").files[0];
  const factsFile = $("interview-facts-file").files[0];
  $("interview-check-plan").disabled = true;
  $("interview-check-plan").textContent = "正在检查…";
  try {
    const [plan, facts] = await Promise.all([readInterviewJSON(planFile), readInterviewJSON(factsFile)]);
    if (request !== interviewRequest) return;
    const body = JSON.stringify({ plan, facts_by_contribution: facts, experience_id: experienceId });
    if (new TextEncoder().encode(body).length > 1048576) throw new Error("两个文件合计内容过长，请将本次检查限制在一个项目的范围内。");
    const result = await api("/api/interview/inspect-plan", { method: "POST", body });
    if (request !== interviewRequest) return;
    if (result.valid !== true || result.status !== "preparation-only") throw new Error("检查响应不完整，请刷新工作台后重试。");
    checkedInterview = plan;
    notice("interview-plan-result", `结构与引用检查通过：${result.contribution_count} 项贡献、${result.depth_area_count} 个深挖主题、${result.transfer_area_count} 个迁移主题。可在上方切换三层预览；问题质量仍待复核。`);
    renderInterviewLayer();
  } catch (error) {
    if (request === interviewRequest) notice("interview-plan-result", error.message, true);
  } finally {
    if (request === interviewRequest) { $("interview-check-plan").disabled = false; $("interview-check-plan").textContent = "检查并预览计划"; }
  }
}
async function loadInterviewProtocol() {
  if (protocolLoaded || protocolLoading || !$("interview-protocol").open) return;
  protocolLoading = true;
  $("interview-protocol-content").textContent = "正在载入流程规范…";
  $("interview-protocol-retry").hidden = true;
  try {
    const result = await api("/api/interview/protocol");
    if (!string(result.content)) throw new Error("流程规范暂时不可用，请稍后重试。");
    $("interview-protocol-content").textContent = result.content;
    protocolLoaded = true;
  } catch (error) {
    $("interview-protocol-content").textContent = error.message;
    $("interview-protocol-retry").hidden = false;
  } finally { protocolLoading = false; }
}

function formSnapshot() {
  const values = {};
  for (const field of fields) values[field] = $("application-form").elements.namedItem(field).value;
  values.needs_action = $("application-form").elements.namedItem("needs_action").checked;
  values.linked_evidence = [...selectedEvidence].sort();
  return values;
}
function isDirty() { return initialForm && JSON.stringify(formSnapshot()) !== JSON.stringify(initialForm); }
function updateJobLink() {
  const href = safeURL($("application-form").elements.namedItem("url").value);
  $("open-job-link").hidden = !href;
  if (href) $("open-job-link").href = href; else $("open-job-link").removeAttribute("href");
}
function clearAutomation() {
  $("automation-result").hidden = true;
  $("automation-prompt").value = "";
  notice("automation-notice", "");
}
async function prepareAutomation() {
  clearAutomation();
  if (!editing || isDirty()) {
    notice("automation-notice", "请先保存修改，再重新打开记录准备填表。", true);
    return;
  }
  const request = detailRequest;
  const application = editing;
  const button = $("prepare-automation");
  button.disabled = true;
  try {
    const task = await api("/api/automation/prepare", {
      method: "POST", body: JSON.stringify({ application_id: application.id, revision: application.revision }),
    });
    if (request !== detailRequest || !$("application-dialog").open) return;
    if (isDirty()) { notice("automation-notice", "输入已变更，请保存后重新准备任务。", true); return; }
    $("automation-prompt").value = task.prompt;
    $("automation-result").hidden = false;
    notice("automation-notice", "任务已准备。复制给 Codex 后，先检查岗位与资料，再开始填写。");
  } catch (error) {
    if (request === detailRequest && $("application-dialog").open) notice("automation-notice", error.message, true);
  } finally { if (request === detailRequest) button.disabled = false; }
}
async function copyAutomation() {
  const input = $("automation-prompt");
  if (!input.value || isDirty()) { clearAutomation(); return; }
  try {
    await navigator.clipboard.writeText(input.value);
    toast("填表任务已复制，粘贴到 Codex 对话即可");
  } catch {
    input.focus(); input.select();
    notice("automation-notice", "任务已选中，请按 ⌘C（或 Ctrl+C）复制。");
  }
}
function populateApplication(application) {
  const form = $("application-form");
  const draft = !application && creationRequest?.unknown ? creationRequest.payload : null;
  const values = application || draft;
  if (!application && !draft) creationRequest = null;
  editing = application;
  if ($("application-flow-entry")) $("application-flow-entry").hidden = !application;
  if ($("flow-entry-notice")) notice("flow-entry-notice", "");
  clearAutomation();
  $("application-automation").hidden = !application;
  form.reset();
  fillSelect(form.elements.namedItem("status"), data.statuses);
  const originalStatus = string(application?.status);
  if (originalStatus && !data.statuses.some((item) => item.value === originalStatus)) {
    const option = node("option", "", `${originalStatus}（原记录状态）`); option.value = originalStatus; form.elements.namedItem("status").append(option);
  }
  for (const field of fields) form.elements.namedItem(field).value = string(values?.[field]);
  const savedScreening = data.applications.find(item => item.id === application?.id)?.screening;
  $("strategy-result").textContent = savedScreening ? `已保存分流：${savedScreening.route_label}。${(savedScreening.route_reasons || []).join("；")}。修改评价后请保存，以更新分流。` : "保存评价后显示分流结果；未评价的记录保留待判断。";
  form.elements.namedItem("needs_action").checked = values ? values.needs_action === true : true;
  if (!values) { form.elements.namedItem("status").value = data.statuses[0]?.value || ""; form.elements.namedItem("application_date").value = localDate(); }
  selectedEvidence = new Set((values?.linked_evidence || []).filter((id) => typeof id === "string"));
  $("evidence-picker-search").value = "";
  renderEvidencePicker(); updateJobLink();
  $("original-details").hidden = !application;
  $("original-details").open = false;
  $("original-content").textContent = string(application?.content) || "此记录暂无正文内容。";
  $("application-dialog-title").textContent = application ? `${application.company} · ${application.role_title}` : "新增投递";
  $("application-dialog-eyebrow").textContent = application ? "APPLICATION DETAILS" : "NEW APPLICATION";
  $("application-dialog-subtitle").textContent = "已保存的岗位、原文和来源；需要时可更正记录。";
  $("application-corrections").open = false;
  $("save-application").hidden = true;
  $("cancel-application").textContent = "关闭";
  sourceSummary($("application-summary"), application || {});
  $("save-application").textContent = application ? "保存修改" : "保存投递";
  $("save-hint").textContent = "保存到本机投递记录";
  initialForm = formSnapshot();
  if (draft) {
    setFormBusy(true, "保存结果待核验 · 重试同一次保存");
    $("save-application").disabled = false; $("save-application").textContent = "核验并重试保存";
    notice("form-notice", "上次保存结果尚未核验。重试会核验同一次保存，不会重复新增。", true);
  } else if (application && unknownEdits.has(application.id)) {
    $("save-hint").textContent = "保存结果待核验 · 请载入最新版本";
    $("load-latest").hidden = false;
  }
}
const sourceFieldLabels = { company: "公司", role_title: "岗位", location: "工作地点", url: "岗位链接", track: "求职方向", deadline: "截止日期", salary: "薪资", compensation: "薪资", job_description: "JD 原文" };
function sourceSummary(container, values, missing = [], source = "") {
  clear(container);
  const list = node("dl"); list.className = "source-summary";
  for (const [field, label] of Object.entries(sourceFieldLabels)) {
    if (field === "job_description") continue;
    if (typeof values?.[field] === "string" && values[field]) list.append(node("dt", "", label), node("dd", "", values[field]));
  }
  container.append(list);
  container.append(node("p", "small-label", missing.length ? `缺失信息：${missing.map(field => sourceFieldLabels[field] || field).join("、")}。已保留未知，不影响保存。` : "来源中未提供的信息保留未知。"));
  const details = node("details", "jd-details");
  details.append(node("summary", "", "查看原文与来源"), node("p", "small-label", values?.url || (source ? "粘贴 JD 原文" : "已有本机记录")), node("pre", "flow-text", values?.job_description || values?.content || source || "未提供 JD 原文。"));
  container.append(details);
}
function renderSourceIntake(snapshot) {
  const job = snapshot?.job;
  if (!job) throw new Error("尚未取得当前来源处理记录。");
  if (sourceRequest && job.request_id !== sourceRequest.request_id) throw new Error("来源处理记录已变化，不能据此确认本次保存。");
  const messages = { running: "正在后台读取、整理并保存…", saved: "已保存岗位信息", needs_input: "已保存来源草稿，关键资料仍待补充。", failed: "整理未完成，已保留输入。", needs_recheck: "保存结果待核验，已停止。请读取已保存状态。" };
  const running = job.status === "running";
  if (!sourceRequest && typeof job.request_id === "string") sourceRequest = { request_id: job.request_id, input: job.fields?.job_description || job.fields?.url || "" };
  sourceBusy = running; sourceUnknown = job.status === "needs_recheck";
  notice("source-intake-status", messages[job.status] || "处理状态待核验。", ["failed", "needs_recheck"].includes(job.status));
  if (job.error_code || job.error_message) {
    const explanation = job.status === "needs_recheck" ? "来源已保留。保存结果尚未核验，请先读取已保存状态。" : ({
      intake_source_incomplete: "来源已保留。尚未取得完整岗位信息，请补充 JD 全文后再次整理。",
      intake_source_unavailable: "来源已保留。岗位页面暂不可读，可粘贴 JD 全文再次整理。",
      intake_extraction_failed: "来源已保留。自动提取未完成，请查看原文后明确重试整理。",
      recommendation_source_conflict: "这个来源与已保存的同一岗位记录不符，未保存。可在“岗位与进度”核对已有记录，或粘贴其他岗位。",
    }[job.error_code] || "来源已保留。整理未完成，请查看已保存来源后明确重试整理。");
    $("source-intake-status").append(node("p", "", explanation));
    const diagnostics = node("details", "jd-details"); diagnostics.id = "source-intake-diagnostics";
    diagnostics.append(node("summary", "", "诊断信息"), node("pre", "flow-text", [job.error_code, job.error_message].filter(Boolean).join("\n")));
    $("source-intake-status").append(diagnostics);
  }
  sourceRequest.retryAllowed = job.status === "failed";
  $("source-intake-input").disabled = running || sourceUnknown;
  $("source-intake-submit").disabled = running || sourceUnknown || job.status === "saved";
  $("source-intake-recheck").hidden = !sourceUnknown;
  const result = $("source-intake-result"); result.hidden = running;
  if (!running) {
    sourceSummary(result, job.fields || {}, job.missing_fields || [], sourceRequest?.input || "");
    if (job.status === "saved") result.prepend(node("h3", "", "已保存"));
    if (job.application_id) {
      const open = node("button", "button button-secondary", "查看已保存岗位"); open.type = "button";
      open.addEventListener("click", async () => {
        await loadState({ silent: true });
        const application = data.applications.find(item => item.id === job.application_id);
        if (application) { $("source-intake-dialog").close(); openApplication(application); }
        else notice("source-intake-status", "尚未读取到已保存岗位，请重新读取状态。", true);
      }); result.append(open);
    }
    if (job.status === "saved") loadState({ silent: true });
  }
  clearTimeout(sourceTimer);
  if (running && $("source-intake-dialog").open) sourceTimer = setTimeout(readSourceIntake, 700);
}
async function readSourceIntake(recoverOnly = false) {
  try {
    const snapshot = await api("/api/intake/state");
    if (!recoverOnly || ["running", "needs_recheck"].includes(snapshot?.job?.status)) renderSourceIntake(snapshot);
    else { sourceBusy = false; $("source-intake-submit").disabled = false; }
    sourceStateLoaded = true;
  }
  catch (error) {
    sourceBusy = false; sourceUnknown = true;
    notice("source-intake-status", `${error.message} 处理结果待核验；请读取已保存状态。`, true);
    $("source-intake-input").disabled = true; $("source-intake-submit").disabled = true; $("source-intake-recheck").hidden = false;
  }
}
function openSourceIntake() {
  if (!stateReady || data.connections?.applications !== true) { toast("请先恢复投递记录的数据连接。"); return; }
  const dialog = $("source-intake-dialog");
  if (!dialog.open) dialog.showModal();
  if (!sourceBusy && !sourceUnknown) $("source-intake-input").focus();
  if (!sourceStateLoaded) {
    sourceBusy = true; $("source-intake-submit").disabled = true;
    readSourceIntake(true);
  } else if (sourceBusy || sourceUnknown) readSourceIntake();
  else $("source-intake-input").focus();
}
async function saveSourceIntake(event) {
  event.preventDefault();
  if (sourceBusy || sourceUnknown) return;
  const input = $("source-intake-input").value.trim();
  if (!input) return;
  sourceRequest ||= { request_id: crypto.randomUUID().replaceAll("-", ""), input };
  if (sourceRequest.input !== input || sourceRequest.retryAllowed) sourceRequest = { request_id: crypto.randomUUID().replaceAll("-", ""), input };
  const isLink = /^https?:\/\/\S+$/i.test(input);
  const body = { request_id: sourceRequest.request_id, [isLink ? "url" : "text"]: input };
  sourceBusy = true; $("source-intake-submit").disabled = true; $("source-intake-input").disabled = true;
  notice("source-intake-status", "正在后台读取、整理并保存…"); $("source-intake-result").hidden = true;
  try { renderSourceIntake(await api("/api/intake/ingest", { method: "POST", body: JSON.stringify(body) })); }
  catch (error) {
    sourceBusy = false; sourceUnknown = !error.status || error.status >= 500;
    $("source-intake-input").disabled = sourceUnknown; $("source-intake-submit").disabled = sourceUnknown;
    $("source-intake-recheck").hidden = !sourceUnknown;
    notice("source-intake-status", `${error.message}${sourceUnknown ? " 结果待核验，请读取已保存状态。" : " 输入已保留，请核对来源。"}`, true);
  }
}
async function openApplication(application = null) {
  if (!application) { openSourceIntake(); return; }
  if (!stateReady || data.connections?.applications !== true) { toast("请先恢复投递记录的数据连接。"); return; }
  const request = ++detailRequest;
  setFormBusy(false);
  notice("form-notice", ""); $("load-latest").hidden = true;
  populateApplication(application);
  const dialog = $("application-dialog");
  if (!dialog.open) dialog.showModal();
  dialog.querySelector(".dialog-body").scrollTop = 0;
  if (!application) { $("application-form").elements.namedItem("company").focus(); return; }
  setFormBusy(true, "正在载入完整记录…");
  let loaded = false;
  try {
    const response = await api(`/api/applications/${encodeURIComponent(application.id)}`);
    if (request !== detailRequest || !dialog.open) return;
    if (response.application?.id !== application.id || typeof response.application.revision !== "string" || !/^[a-f0-9]{64}$/.test(response.application.revision)) throw new Error("记录响应不完整，尚未核验最新版本。");
    unknownEdits.delete(application.id);
    populateApplication(response.application);
    loaded = true;
  } catch (error) {
    if (request !== detailRequest || !dialog.open) return;
    notice("form-notice", `${error.message} 请关闭后重试；本次尚未进入编辑。`, true);
    $("save-hint").textContent = "记录尚未完整载入";
    return;
  } finally { if (request === detailRequest && dialog.open && loaded) setFormBusy(false); }
  $("application-dialog-title").focus();
}
function setFormBusy(busy, hint = "") {
  for (const element of $("application-form").elements) {
    if (!["close-application", "cancel-application"].includes(element.id)) element.disabled = busy;
  }
  if (hint) $("save-hint").textContent = hint;
}
async function closeApplication() {
  if (saving) return;
  const unknown = editing ? unknownEdits.has(editing.id) : creationRequest?.unknown;
  if ((isDirty() || unknown) && !await confirmAction(unknown ? editing ? "保存结果尚未核验，记录可能已经更新。重新打开后须读取最新版本。" : "保存结果尚未核验，记录可能已经写入。关闭后仍可从新增入口继续核验同一次保存。" : "还有未保存的修改。关闭后，这些修改将不会保存。", "关闭记录")) return;
  ++detailRequest; $("application-dialog").close(); editing = null; initialForm = null;
}
function renderEvidencePicker() {
  const query = $("evidence-picker-search").value.trim().toLocaleLowerCase();
  const items = data.evidence.filter((item) => !query || [item.title, item.summary, kindLabel(item.kind)].some((value) => string(value).toLocaleLowerCase().includes(query)));
  const container = clear($("evidence-picker"));
  renderSelectedEvidence();
  if (!items.length) empty(container, data.evidence.length ? "没有匹配的证据" : "暂无可关联材料", data.evidence.length ? "更换关键词继续查找，已选内容仍会保留。" : "接入职业工作区后，可以在这里关联项目或贡献。");
  for (const item of items) {
    const label = node("label", "evidence-choice"); const input = node("input"); input.type = "checkbox"; input.value = item.id; input.checked = selectedEvidence.has(item.id);
    input.addEventListener("change", () => { if (input.checked) selectedEvidence.add(item.id); else selectedEvidence.delete(item.id); renderSelectedEvidence(); });
    const title = node("span", "", item.title); title.append(node("small", "", kindLabel(item.kind))); label.append(input, title, badge(item.status, true)); container.append(label);
  }
  const missing = [...selectedEvidence].filter((id) => !data.evidence.some((item) => item.id === id));
  for (const id of missing) {
    const label = node("label", "evidence-choice"); const input = node("input"); input.type = "checkbox"; input.checked = true; input.value = id;
    input.addEventListener("change", () => { if (input.checked) selectedEvidence.add(id); else selectedEvidence.delete(id); renderSelectedEvidence(); });
    const title = node("span", "", "原关联材料暂不可用"); title.append(node("small", "", "保留现有关系；取消勾选可解除关联。")); label.append(input, title); container.append(label);
  }
}
function renderSelectedEvidence() {
  $("selected-evidence-count").textContent = `已选 ${selectedEvidence.size} 项`;
  const chips = clear($("selected-evidence-chips"));
  for (const item of data.evidence.filter((evidence) => selectedEvidence.has(evidence.id))) {
    const button = node("button", "evidence-chip", `◇ ${item.title} ↗`);
    button.type = "button"; button.setAttribute("aria-label", `预览关联证据：${item.title}`);
    button.addEventListener("click", () => openEvidence(item)); chips.append(button);
  }
}
async function saveApplication(event) {
  event.preventDefault();
  if (saving) return;
  if (editing && unknownEdits.has(editing.id)) {
    notice("form-notice", "上次修改的保存结果尚未核验。请先复制需要保留的输入，再载入最新版本；不能按旧版本判断没有修改。", true);
    $("load-latest").hidden = false; $("save-hint").textContent = "保存结果待核验 · 请载入最新版本";
    return;
  }
  if (!$("application-form").reportValidity()) return;
  const snapshot = formSnapshot();
  const payload = editing ? { revision: editing.revision } : { ...(creationRequest?.unknown ? creationRequest.payload : snapshot) };
  if (editing) for (const key of Object.keys(snapshot)) if (JSON.stringify(snapshot[key]) !== JSON.stringify(initialForm[key])) payload[key] = snapshot[key];
  if (editing && Object.keys(payload).length === 1) { $("application-dialog").close(); toast("没有需要保存的修改"); return; }
  if (Object.hasOwn(payload, "url") && payload.url && !safeURL(payload.url)) { notice("form-notice", "岗位链接需要使用有效的 HTTP 或 HTTPS 地址。", true); $("application-form").elements.namedItem("url").focus(); return; }
  if (!editing) {
    if (!creationRequest) creationRequest = { id: crypto.randomUUID().replaceAll("-", ""), unknown: false };
    creationRequest.payload = payload;
  }
  saving = true; setFormBusy(true, "正在保存…"); $("save-application").textContent = "保存中…"; notice("form-notice", ""); $("load-latest").hidden = true;
  try {
    const response = await api(editing ? `/api/applications/${encodeURIComponent(editing.id)}` : "/api/applications", { method: editing ? "PATCH" : "POST", body: JSON.stringify(payload), headers: editing ? {} : { "Idempotency-Key": creationRequest.id } });
    if (
      typeof response.application?.id !== "string" || !/^[a-f0-9]{24}$/.test(response.application.id)
      || typeof response.application.revision !== "string" || !/^[a-f0-9]{64}$/.test(response.application.revision)
    ) throw new Error("保存响应不完整，保存结果尚未核验。");
    const index = data.applications.findIndex((item) => item.id === response.application.id);
    if (index >= 0) data.applications[index] = response.application; else data.applications.unshift(response.application);
    if (!editing) creationRequest = null; else unknownEdits.delete(editing.id);
    populateFilters(); render(); initialForm = null; $("application-dialog").close();
    notice("page-notice", response.screening_warning?.message || data.worker_warning?.message || "", Boolean(data.worker_warning));
    toast(response.screening_warning ? "记录已保存，筛选结果暂不可用。请刷新工作台。" : editing ? "修改已保存" : "投递已记录，下一步从这里开始"); editing = null;
  } catch (error) {
    const rejected = error.status >= 400 && error.status < 500 && error.code !== "save-request-conflict";
    if (!editing && creationRequest) creationRequest.unknown ||= !rejected;
    if (editing && !rejected) unknownEdits.add(editing.id);
    const unknown = !rejected || (editing ? unknownEdits.has(editing.id) : creationRequest?.unknown);
    notice("form-notice", unknown ? `${error.message} 保存结果待核验，记录可能已经写入。${editing ? "请载入最新版本核验。" : "重试将核验同一次保存，不会重复新增。"}` : error.status === 409 ? "这条记录已在其他地方修改。你的输入仍在这里；可先复制需要保留的内容，再载入最新版本。" : `${error.message} 你的输入已保留。`, true);
    $("load-latest").hidden = !editing || (error.status !== 409 && !unknown);
    $("save-hint").textContent = unknown ? "保存结果待核验 · 输入已保留" : "保存被拒绝 · 输入已保留";
    $("application-dialog").querySelector(".dialog-body").scrollTop = 0;
  } finally {
    saving = false; const unknown = editing ? unknownEdits.has(editing.id) : creationRequest?.unknown;
    setFormBusy(Boolean(!editing && unknown)); $("save-application").disabled = false;
    $("save-application").textContent = unknown ? editing ? "核验后再保存" : "核验并重试保存" : editing ? "保存修改" : "保存投递";
  }
}
async function openEvidence(item) {
  const request = ++evidenceRequest;
  $("prepare-evidence-interview").onclick = () => {
    ++evidenceRequest; $("evidence-dialog").close();
    $("interview-evidence-search").value = ""; renderInterviewSources();
    $("interview-evidence").value = item.id; updateInterviewEvidence(); location.hash = "interview";
  };
  $("evidence-dialog-title").textContent = item.title;
  const meta = clear($("evidence-dialog-meta")); meta.append(node("span", "kind-badge", kindLabel(item.kind)), badge(item.status, true));
  const content = $("evidence-content"); content.textContent = "正在载入来源材料…"; content.classList.add("is-loading");
  content.classList.remove("is-error");
  clear($("evidence-linked-applications"));
  if (!$("evidence-dialog").open) $("evidence-dialog").showModal();
  $("evidence-dialog").querySelector(".dialog-body").scrollTop = 0;
  try {
    const detail = await api(`/api/evidence/${encodeURIComponent(item.id)}`);
    if (request !== evidenceRequest || !$("evidence-dialog").open) return;
    content.textContent = string(detail.content) || "此材料暂无正文内容。";
    renderEvidenceCorrection(item, detail, content);
    if (detail.title) $("evidence-dialog-title").textContent = detail.title;
    if (detail.status) { clear(meta); meta.append(node("span", "kind-badge", kindLabel(detail.kind)), badge(detail.status, true)); }
    const linked = data.applications.filter((application) => application.linked_evidence?.includes(item.id));
    if (linked.length) {
      const section = node("section", "linked-applications"); section.append(node("h3", "", `关联此材料的投递 · ${linked.length}`));
      for (const application of linked) {
        const button = node("button", "evidence-chip", `${application.company} · ${application.role_title}`); button.type = "button";
        button.addEventListener("click", async () => {
          if ($("application-dialog").open && isDirty() && !await confirmAction("当前投递还有未保存的修改。打开另一条记录会放弃这些修改。", "放弃并打开")) return;
          $("evidence-dialog").close(); openApplication(application);
        });
        section.append(button);
      }
      $("evidence-linked-applications").append(section);
    }
  } catch (error) {
    if (request === evidenceRequest && $("evidence-dialog").open) {
      content.textContent = error.message; content.classList.add("is-error");
      const retry = node("button", "button button-secondary evidence-retry", "重新载入"); retry.type = "button";
      retry.addEventListener("click", () => openEvidence(item)); content.append(retry);
    }
  }
  finally { if (request === evidenceRequest) content.classList.remove("is-loading"); }
}

function renderEvidenceCorrection(item, detail, container) {
  const generation = evidenceRequest;
  let draft = evidenceDrafts.get(item.id);
  if (draft?.unknown && detail.content === draft.content) {
    evidenceDrafts.delete(item.id); draft = null;
    container.append(node("p", "notice", "事实更正已保存，当前正文已核验。"));
  }
  if (detail.editable) {
    const edit = node("button", "button button-secondary", "更正经历文档"); edit.type = "button";
    const form = node("form", "flow-condition"); form.hidden = !draft;
    const label = node("label", "", "经历文档正文");
    const input = node("textarea"); input.rows = 14; input.required = true; input.setAttribute("aria-label", "经历文档正文"); input.value = draft?.content ?? detail.content;
    label.append(input);
    const result = node("p", "flow-muted", draft?.message || "明确的事实更正直接保存，并保留原文和更正历史。"); result.setAttribute("role", "status");
    const save = node("button", "button button-primary", "保存事实更正"); save.type = "submit"; save.disabled = !!(draft?.unknown || draft?.saving);
    const recheck = node("button", "button button-secondary", "核验最新文档"); recheck.type = "button"; recheck.hidden = !draft?.unknown;
    recheck.addEventListener("click", () => openEvidence(item));
    edit.addEventListener("click", () => {
      draft ||= { revision: detail.revision, content: detail.content };
      evidenceDrafts.set(item.id, draft); form.hidden = false; input.focus();
    });
    input.addEventListener("input", () => {
      draft ||= { revision: detail.revision };
      draft.content = input.value; evidenceDrafts.set(item.id, draft);
    });
    form.addEventListener("submit", async event => {
      event.preventDefault();
      if (!draft || draft.unknown || draft.saving || !input.value.trim()) return;
      draft.content = input.value; draft.saving = true; save.disabled = true; input.disabled = true;
      result.textContent = "正在保存事实更正…";
      try {
        const saved = await api(`/api/evidence/${encodeURIComponent(item.id)}`, { method: "PATCH", body: JSON.stringify({ revision: draft.revision, content: draft.content, source: "explicit-career-correction" }) });
        if (saved.id !== item.id || saved.content !== draft.content || !saved.revision || !Array.isArray(saved.history)) throw new Error("保存响应不完整，事实更正结果尚未核验。");
        evidenceDrafts.delete(item.id);
        if (container.isConnected && $("evidence-dialog").open && evidenceRequest === generation) { container.textContent = saved.content; container.append(node("p", "notice", "事实更正已保存，原文和更正历史已保留。")); renderEvidenceCorrection(item, saved, container); }
        await loadState({ silent: true });
      } catch (error) {
        draft.unknown = !error.status || error.status >= 500;
        draft.message = `${error.message} 输入已保留。${draft.unknown ? "保存结果尚未核验，不会自动重试。" : "请核对当前来源版本。"}`;
        result.textContent = draft.message; recheck.hidden = false;
      } finally { draft.saving = false; input.disabled = false; save.disabled = !!draft.unknown; }
    });
    form.append(label, result, save, recheck); container.append(edit, form);
  }
  if (detail.history?.length) {
    const history = node("details", "flow-details"); history.append(node("summary", "", `更正历史 · ${detail.history.length}`));
    for (const change of detail.history.slice().reverse()) history.append(node("p", "flow-muted", `${change.at} · ${change.actor} · ${change.source} · ${change.status === "applied" ? "已保存" : "结果待核验"}`), node("p", "flow-hash", `${change.before_revision} → ${change.after_revision}`));
    container.append(history);
  }
}

$("today-label").textContent = new Intl.DateTimeFormat("zh-CN", { month: "long", day: "numeric", weekday: "long" }).format(new Date()) + "  /  TODAY'S WORKSPACE";
window.addEventListener("handoff-state", event => { overviewHandoff = event.detail; renderWorkflow(); });
window.addEventListener("application-flow-state", event => { overviewFlow = event.detail; renderWorkflow(); });
$("workflow-primary").addEventListener("click", () => {
  if ($("workflow-primary").getAttribute("href") === "#handoff") window.dispatchEvent(new Event("handoff-focus"));
  else if ($("workflow-primary").getAttribute("href") === "#flow") $("flow-pipeline-current")?.click();
});
$("add-application").addEventListener("click", () => openApplication());
$("refresh-button").addEventListener("click", () => loadState());
$("application-search").addEventListener("input", renderApplications);
$("status-filter").addEventListener("change", renderApplications);
$("track-filter").addEventListener("change", renderApplications);
$("screening-filter").addEventListener("change", renderApplications);
$("route-filter").addEventListener("change", renderApplications);
$("application-sort").addEventListener("change", renderApplications);
$("action-only").addEventListener("change", renderApplications);
$("evidence-search").addEventListener("input", renderEvidence);
$("evidence-kind-filter").addEventListener("change", renderEvidence);
$("evidence-status-filter").addEventListener("change", renderEvidence);
$("show-evidence-table").addEventListener("click", () => setEvidenceView("table"));
$("experience-search").addEventListener("input", renderExperienceTable);
$("show-evidence-library").addEventListener("click", () => setEvidenceView("library"));
$("interview-evidence").addEventListener("change", updateInterviewEvidence);
$("interview-evidence-search").addEventListener("input", renderInterviewSources);
$("interview-open-evidence").addEventListener("click", () => { const item = data.evidence.find((entry) => entry.id === $("interview-evidence").value); if (item) openEvidence(item); });
for (const button of document.querySelectorAll("[data-interview-layer]")) button.addEventListener("click", () => { interviewLayer = Number(button.dataset.interviewLayer); renderInterviewLayer(); });
$("interview-difficulty").addEventListener("change", renderInterviewLayer);
$("interview-plan-form").addEventListener("submit", checkInterviewPlan);
for (const id of ["interview-plan-file", "interview-facts-file", "interview-experience-id"]) $(id).addEventListener("input", invalidateInterviewPlan);
$("interview-clear-plan").addEventListener("click", () => { $("interview-plan-form").reset(); invalidateInterviewPlan(); });
$("interview-protocol").addEventListener("toggle", loadInterviewProtocol);
$("interview-protocol-retry").addEventListener("click", loadInterviewProtocol);
$("evidence-picker-search").addEventListener("input", renderEvidencePicker);
$("application-form").elements.namedItem("url").addEventListener("input", updateJobLink);
$("application-form").elements.namedItem("status").addEventListener("change", () => {
  $("application-form").elements.namedItem("needs_action").checked = ["drafting", "recruiter_replied", "interview_scheduled", "assessment_pending", "follow_up_optional"].includes($("application-form").elements.namedItem("status").value);
});
$("application-form").addEventListener("submit", saveApplication);
$("open-application-flow")?.addEventListener("click", () => {
  if (!editing || saving || isDirty() || unknownEdits.has(editing.id)) { notice("flow-entry-notice", "请先保存修改并核验最新记录，再进入工作台。", true); return; }
  const applicationId = editing.id;
  $("application-dialog").close();
  location.hash = "#flow";
  window.dispatchEvent(new CustomEvent("flow-open", { detail: { applicationId } }));
});
$("open-codex-handoff").addEventListener("click", () => {
  if (!editing || isDirty()) { notice("automation-notice", "请先保存岗位修改，再进入交接。", true); return; }
  const applicationId = editing.id;
  $("application-dialog").close();
  location.hash = "#handoff";
  window.dispatchEvent(new CustomEvent("handoff-prepare", { detail: { applicationId } }));
});
$("prepare-automation").addEventListener("click", prepareAutomation);
$("copy-automation").addEventListener("click", copyAutomation);
$("application-form").addEventListener("input", (event) => { if (event.target.name) clearAutomation(); });
$("application-form").addEventListener("change", (event) => { if (event.target.name || event.target.closest("#evidence-picker, #selected-evidence-chips")) clearAutomation(); });
$("close-application").addEventListener("click", closeApplication);
$("cancel-application").addEventListener("click", closeApplication);
$("application-dialog").addEventListener("cancel", (event) => { event.preventDefault(); closeApplication(); });
$("load-latest").addEventListener("click", async () => { if (editing && await confirmAction("载入最新版本会替换当前未保存的输入。请先复制需要保留的内容。", "载入最新版本")) openApplication(editing); });
for (const id of ["close-evidence", "evidence-done"]) $(id).addEventListener("click", () => { ++evidenceRequest; $("evidence-dialog").close(); });
window.addEventListener("hashchange", setView);
window.addEventListener("beforeunload", (event) => { if (($("application-dialog").open && isDirty()) || creationRequest?.unknown || unknownEdits.size || evidenceDrafts.size) { event.preventDefault(); event.returnValue = ""; } });
document.addEventListener("keydown", (event) => {
  if (event.metaKey || event.ctrlKey || event.altKey || event.isComposing || event.target.closest("input, textarea, select, [contenteditable=true]") || $("application-dialog").open || $("evidence-dialog").open) return;
  if (event.key === "/") {
    event.preventDefault();
    if (view === "interview") { $("interview-evidence-search").focus(); return; }
    if (view === "overview") { location.hash = "applications"; setView(); }
    const search = view === "evidence" ? (evidenceView === "table" ? $("experience-search") : $("evidence-search")) : $("application-search");
    search?.focus();
  }
  if (event.key.toLowerCase() === "n") { event.preventDefault(); openApplication(); }
});
setView();
loadState({ silent: true });

$("source-intake-form").addEventListener("submit", saveSourceIntake);
$("source-intake-recheck").addEventListener("click", async () => {
  if (!sourceRequest?.request_id || sourceBusy) { await readSourceIntake(); return; }
  sourceBusy = true; $("source-intake-recheck").disabled = true;
  try { renderSourceIntake(await api("/api/intake/reconcile", { method: "POST", body: JSON.stringify({ request_id: sourceRequest.request_id }) })); }
  catch (error) { sourceBusy = false; notice("source-intake-status", `${error.message} 结果仍待核验，不能重复整理。`, true); }
  finally { $("source-intake-recheck").disabled = false; }
});
$("source-intake-input").addEventListener("input", () => {
  if (!sourceBusy && !sourceUnknown) { $("source-intake-submit").disabled = false; $("source-intake-result").hidden = true; }
});
$("close-source-intake").addEventListener("click", () => { $("source-intake-dialog").close(); clearTimeout(sourceTimer); });
$("application-corrections").addEventListener("toggle", () => { $("save-application").hidden = !$("application-corrections").open; $("cancel-application").textContent = $("application-corrections").open ? "取消" : "关闭"; });
