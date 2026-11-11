"use strict";

(() => {
  const root = document.getElementById("handoff-root");
  const statusLabels = { prepared: "待 Codex 领取", claimed: "Codex 操作中", needs_input: "等待已确认答案", needs_recheck: "结果未知，先核验原页面", ready_for_review: "等待你复核", reviewed: "已复核，等待你在原页面提交", submitted: "你已确认提交，等待回执", confirmed: "回执已记录", cancelled: "已停止" };
  let preparationApplication = "";
  let snapshot = null, selected = null, busy = false, stale = true, request = 0;
  function el(tag, text, cls) { const item = document.createElement(tag); if (text) item.textContent = text; if (cls) item.className = cls; return item; }
  function input(label, type = "text") { const control = el(type === "textarea" || type === "select" ? type : "input"); if (control.tagName === "INPUT") control.type = type; control.setAttribute("aria-label", label); const wrap = el("label", label); wrap.append(control); return [wrap, control]; }
  function button(label, action) { const item = el("button", label, "button button-secondary"); item.type = "button"; item.addEventListener("click", action); return item; }
  function check(label) { const [wrap, control] = input(label, "checkbox"); wrap.className = "handoff-check"; return [wrap, control]; }
  const heading = el("div", "", "page-heading handoff-heading"); const intro = el("div"); intro.append(el("div", "CODEX HANDOFF", "eyebrow"), el("h1", "一份任务，一次交接"), el("p", "准备已批准的资料，交给 Codex 操作，再由你复核并在原页面提交。")); heading.append(intro);
  const message = el("p", "正在读取持久交接记录…", "handoff-message"); message.setAttribute("role", "status");
  const refresh = button("刷新交接记录", async () => { if (body.dataset.dirty === "true" && !await confirmAction("刷新后放弃当前未保存的交接输入，并读取持久记录核对结果。", "刷新并核对")) return; refreshState(); });
  const body = el("div", "", "handoff-body"); heading.append(refresh); root.append(heading, message, body);
  function checkedSnapshot(value, expected = null) {
    if (!expected && value?.enabled === false) return value;
    const validTask = item => item && typeof item.id === "string" && item.id && typeof item.revision === "string" && item.revision && Object.hasOwn(statusLabels, item.status);
    if (value?.enabled !== true || value.execution_lane !== "codex" || !Array.isArray(value.tasks) || !value.tasks.every(validTask) || !(value.active_task === null || (validTask(value.active_task) && value.tasks.some(item => item.id === value.active_task.id && item.revision === value.active_task.revision)))) throw new Error("交接响应不完整，保存结果尚未核验。");
    if (expected?.task_id && !value.tasks.some(item => item.id === expected.task_id && item.revision !== expected.task_revision)) throw new Error("任务版本未更新，操作结果尚未核验。");
    if (expected?.application_id && value.active_task?.application_id !== expected.application_id) throw new Error("返回任务与所选岗位不一致，操作结果尚未核验。");
    return value;
  }
  function task() { return snapshot?.tasks?.find(item => item.id === selected) || null; }
  function publishState() { window.dispatchEvent(new CustomEvent("handoff-state", { detail: { enabled: snapshot.enabled, activeTask: snapshot.active_task, tasks: snapshot.tasks } })); }
  function publishStale() { window.dispatchEvent(new CustomEvent("handoff-state", { detail: { stale: true } })); }
  function lock(value) { busy = value; refresh.disabled = value; body.querySelectorAll("fieldset").forEach(field => { field.disabled = value || stale; }); const selector = body.querySelector("select[aria-label=\"查看交接任务\"]"); if (selector) selector.disabled = value || stale; }
  function report(text, error = false) { message.textContent = text; message.className = error ? "handoff-message handoff-warning" : "handoff-message"; }
  async function refreshState() {
    if (!stateReady || busy) return;
    const id = ++request; lock(true);
    try { const next = checkedSnapshot(await api("/api/handoff/state")); if (id !== request) return; snapshot = next; stale = false; render(); publishState(); report(next.enabled ? "持久记录已核验 · 网页当前状态以原页面回读为准" : "尚未启用 Codex 交接。用独立 --handoff-root 启动；高度自动化 worker 在另一入口继续开发。", !next.enabled); }
    catch (error) { stale = true; publishStale(); report(`${error.message} 当前显示上次记录；操作已停。`, true); }
    finally { if (id === request) lock(false); }
  }
  async function mutate(action, payload) {
    if (busy || stale) return false;
    lock(true); ++request;
    try { const next = checkedSnapshot(await api(`/api/handoff/${action}`, { method: "POST", body: JSON.stringify(payload) }), payload); snapshot = next; stale = false; if (action === "prepare" && next.active_task?.id) selected = next.active_task.id; else if (payload.task_id) selected = payload.task_id; render(); publishState(); if (["submitted", "receipt", "retry-sync"].includes(action)) await loadState({ silent: true }); const saved = next.tasks.find(item => item.id === selected); report(saved?.release_pending && saved.status === "cancelled" ? "操作已停止，操作权释放尚未核验。请完成释放收尾。" : saved?.pending_sync || saved?.sync_error ? "提交证据已保存，投递记录同步待核验。请核对后处理同步。" : "已保存，并已回读持久记录。请按当前任务状态继续。", Boolean(saved?.release_pending || saved?.pending_sync || saved?.sync_error)); return true; }
    catch (error) { stale = true; publishStale(); report(`${error.message} 操作结果尚未核验；请保留输入，刷新记录后核对，勿重复上传或提交。`, true); return false; }
    finally { lock(false); }
  }
  function form(title, submitLabel, submit) { const panel = el("form", "", "panel"); const fields = el("fieldset"); fields.append(el("h2", title)); panel.append(fields); const save = el("button", submitLabel, "button button-primary"); save.type = "submit"; fields.append(save); panel.addEventListener("submit", event => { event.preventDefault(); submit(); }); return { panel, fields, save }; }
  function addBefore(fields, save, ...nodes) { nodes.forEach(item => fields.insertBefore(item, save)); }
  function progress(current) {
    const steps = [["准备资料", "已有岗位 · 批准 PDF"], ["Codex 领取", "明确唯一执行者"], ["操作并回读", "核对字段与附件"], ["复核并提交", "由你操作 Submit"], ["同步与回执", "保存记录与接收来源"]];
    const stage = current ? ({ prepared: 1, claimed: 2, needs_input: 2, needs_recheck: 2, ready_for_review: 3, reviewed: 3, submitted: 4, confirmed: 4, cancelled: -1 })[current.status] : 0;
    const complete = current?.status === "confirmed" && !current.pending_sync && !current.sync_error && !current.release_pending;
    const list = el("ol", "", "handoff-progress"); list.setAttribute("aria-label", "单岗位交接主流程");
    steps.forEach(([title, note], index) => {
      const done = complete || (stage >= 0 && index < stage), active = !complete && index === stage;
      const item = el("li", "", `handoff-step${done ? " is-complete" : active ? " is-current" : ""}`);
      if (active) item.setAttribute("aria-current", "step");
      const number = el("span", done ? "✓" : String(index + 1), "handoff-step-number"); number.setAttribute("aria-hidden", "true");
      const copy = el("div", "", "handoff-step-copy"); copy.append(el("strong", title), el("span", note)); item.append(number, copy); list.append(item);
    });
    return list;
  }
  function guidance(current) {
    if (current.pending_sync || current.sync_error || (current.release_pending && current.status !== "cancelled")) return ["核对后恢复记录同步", "提交证据已保留。核对当前投递记录后重试同步，不重复网页提交。"];
    if (current.status === "cancelled") return current.release_pending ? ["完成操作权释放", "确认执行者已停止并处置原页面，再保存释放核验。"] : ["本次交接已停止", "这份任务保留在历史中。准备下一份任务时，从任务列表选择“准备新任务”。"];
    return ({
      prepared: ["复制任务，交给 Codex 领取", "将领取任务粘贴到 Codex。领取成功后，由同一执行者操作原页面。"],
      claimed: ["等待 Codex 完成页面操作与回读", "由当前执行者核对实际岗位、字段和批准附件，再保存结构化回读证据。"],
      needs_input: ["补充网站问题的已确认答案", "在下方保存仅限此岗位的答案，再核验原页面后继续。"],
      needs_recheck: ["先核验原页面，再决定是否继续", "当前结果或资料状态待核验。保留原页面，记录明确结论后再继续。"],
      ready_for_review: ["核对原页面的字段和附件", "确认回读与原页面一致后，在下方保存人工复核。"],
      reviewed: ["在原页面手动点击 Submit", "完成提交后，再在下方记录已提交及核验来源。"],
      submitted: ["保存提交回执", "核验确认页或邮件，在下方记录回执位置或编号。"],
      confirmed: ["本次交接记录已完成", "已保存你核验的接收来源。可在历史记录中查看回读、复核和回执。"]
    })[current.status];
  }
  function render() {
    body.replaceChildren(); if (!snapshot?.enabled) return;
    if (selected === null || (!selected && snapshot.active_task) || (selected && !snapshot.tasks?.some(item => item.id === selected))) selected = snapshot.active_task?.id || snapshot.tasks?.findLast(item => item.status === "submitted")?.id || snapshot.tasks?.at(-1)?.id || "";
    const [selection, selector] = input("查看交接任务", "select"); const blank = el("option", snapshot.active_task ? "先完成当前任务，再准备新任务" : "准备新任务"); blank.value = ""; blank.disabled = Boolean(snapshot.active_task); selector.append(blank);
    for (const item of snapshot.tasks || []) { const option = el("option", `${item.company || item.application_id} · ${item.role_title || ""} · ${statusLabels[item.status] || item.status}`); option.value = item.id; selector.append(option); }
    selector.value = selected;
    let switching = false;
    selector.addEventListener("change", async () => { if (switching) return; const old = selected; const next = selector.value; selector.value = old; switching = true; selector.disabled = true; try { if (body.dataset.dirty === "true" && !await confirmAction("切换后放弃当前未保存的交接输入。持久记录保持。", "放弃输入并切换")) return; selected = next; render(); } finally { switching = false; selector.disabled = busy || stale; } });
    const current = task(); body.append(progress(current));
    const toolbar = el("div", "", "handoff-toolbar"); toolbar.append(selection, el("span", `${snapshot.tasks.length} 份持久任务`, "handoff-task-count")); body.append(toolbar); body.dataset.dirty = "false";
    body.oninput = event => { if (event.target !== selector) body.dataset.dirty = "true"; };
    if (!current) prepareForm(); else taskForms(current);
    lock(busy);
  }
  function prepareForm() {
    const { panel, fields, save } = form("准备单岗位任务", "冻结资料并准备交接", async () => {
      const app = data.applications.find(item => item.id === application.value); const file = pdf.files[0];
      if (!app || !file || !ack.checked) { report("请选择已有岗位、已复核 PDF，并确认其他执行者已停止。", true); return; }
      if ($("application-dialog").open && isDirty()) { report("请先保存岗位修改，再准备交接。", true); return; }
      if (file.size > 700_000) { report("PDF 不得超过 700 KB。", true); return; }
      const revision = app.revision, identifier = app.id, countryCode = country.value; lock(true);
      try { const bytes = new Uint8Array(await file.arrayBuffer()); let binary = ""; for (let i = 0; i < bytes.length; i += 8192) binary += String.fromCharCode(...bytes.subarray(i, i + 8192)); lock(false); await mutate("prepare", { application_id: identifier, revision, country: countryCode, filename: file.name, file_base64: btoa(binary), acknowledge: true }); }
      catch (error) { lock(false); report(error.message, true); }
    });
    addBefore(fields, save, el("p", "选择一个已保存岗位和已人工复核的 PDF。准备后，系统会为这次交接保存固定资料副本。", "handoff-form-intro"));
    const [appWrap, application] = input("已保存岗位", "select");
    for (const app of data.applications) { const option = el("option", `${app.company} · ${app.role_title}`); option.value = app.id; application.append(option); }
    if (preparationApplication) application.value = preparationApplication;
    const [countryWrap, country] = input("申请国家", "select");
    for (const [value, label] of Object.entries({ CHE: "瑞士", USA: "美国", GBR: "英国", DEU: "德国", FRA: "法国", CAN: "加拿大", OTHER: "其他，仅当前岗位" })) { const option = el("option", label); option.value = value; country.append(option); }
    const [pdfWrap, pdf] = input("已人工复核的简历 PDF", "file"); pdf.accept = ".pdf,application/pdf"; pdf.required = true;
    const [ackWrap, ack] = check("我已复核该 PDF，确认此岗位其他执行者已停止；交接后只由领取的 Codex 操作原页面，最终 Submit 由我操作。"); ack.required = true;
    addBefore(fields, save, appWrap, countryWrap, pdfWrap, ackWrap); body.append(panel);
  }
  function taskForms(current) {
    const info = el("section", "", "panel handoff-current");
    const status = el("div", "", "handoff-current-heading");
    const identity = el("div"); identity.append(el("div", selected === snapshot.active_task?.id ? "当前交接任务" : "已保存的交接任务", "eyebrow"), el("h3", `${current.company || ""} · ${current.role_title || ""}`), el("p", current.filename, "handoff-file"));
    const state = el("h2", statusLabels[current.status] || current.status, "handoff-status"); state.dataset.status = current.status; status.append(identity, state); info.append(status);
    const next = el("div", "", "handoff-next"); const [title, description] = guidance(current); next.append(el("span", "下一步", "handoff-next-label"), el("h3", title), el("p", description)); info.append(next);
    if (current.claim?.owner) info.append(el("p", `当前执行者：${current.claim.owner}`, "handoff-meta handoff-owner"));
    if (current.release_pending) info.append(el("p", current.status === "cancelled" ? "任务已停止，操作权释放尚未核验。请重试释放收尾，不要开始新任务。" : "提交证据已保存，记录同步或操作权释放尚未核验。请核对并重试同步；不重复网页提交。", "handoff-warning"));
    if (current.pending_sync || current.sync_error) info.append(el("p", `记录同步待核验：${current.sync_error || "pending"}`, "handoff-warning"));
    const [promptWrap, prompt] = input(current.status === "prepared" ? "复制给 Codex 的领取任务" : "当前任务执行说明", "textarea"); prompt.value = current.prompt || ""; prompt.readOnly = true;
    const details = el("details", "", "handoff-details"); details.append(el("summary", "任务资料与 Codex 执行说明"), el("p", `任务 ${current.id} · 版本 ${current.revision}`, "handoff-meta"), el("p", `PDF SHA-256：${current.file_sha256}`, "handoff-meta"), el("p", current.job_url, "handoff-meta"), promptWrap);
    const copy = button(current.status === "prepared" ? "复制领取任务" : "复制任务说明", async () => { try { await navigator.clipboard.writeText(prompt.value); report("任务已复制。由 Codex 通过交接 CLI 领取后操作。"); } catch { details.open = true; prompt.focus(); prompt.select(); report("请按 ⌘C 或 Ctrl+C 复制任务。"); } });
    if (current.status === "prepared") { copy.className = "button button-primary"; next.append(copy); } else details.append(copy);
    const history = el("details", "", "handoff-details"); history.append(el("summary", "查看完整回读、复核、回执和事件"), el("pre", JSON.stringify({ readbacks: current.readbacks, review: current.review, submission: current.submission, receipt: current.receipt, events: current.events }, null, 2))); info.append(details, history); body.append(info);
    const binding = () => ({ task_id: current.id, task_revision: current.revision });
    if (current.status === "needs_input") {
      const answer = form("补充已确认答案", "保存答案", () => mutate("answer", { ...binding(), question: question.value, value: value.value, scope: { application_id: current.application_id }, acknowledge: ack.checked }));
      const [questionWrap, question] = input("网站问题"); question.required = true; const [valueWrap, value] = input("已确认答案", "textarea"); value.required = true; const [ackWrap, ack] = check("我确认答案准确，仅限此岗位。"); ack.required = true; addBefore(answer.fields, answer.save, questionWrap, valueWrap, ackWrap); body.append(answer.panel);
    }
    let readbackTools = null;
    if (["claimed", "needs_input", "needs_recheck"].includes(current.status)) {
      const read = form("保存 Codex 回读证据", "保存回读证据", async () => { let payload; try { payload = JSON.parse(readback.value); if (!payload || Array.isArray(payload) || typeof payload !== "object") throw new Error(); } catch { report("请输入有效的回读 JSON 对象。", true); return; } await mutate("readback", { ...payload, ...binding() }); });
      const [wrap, readback] = input("Codex 回读 JSON（包含 claim_token）", "textarea"); readback.placeholder = '{"claim_token":"…","result":"ready","page_url":"…","source":"…","fields":[],"attachment":{"filename":"…","sha256":"…"},"missing":[]}'; addBefore(read.fields, read.save, wrap);
      readbackTools = el("details", "", "handoff-recovery"); readbackTools.append(el("summary", "手动导入 Codex 回读"), el("p", "通常由 Codex 直接保存。仅在需要手动恢复记录时，展开并导入执行者提供的完整回读。", "handoff-form-intro"), read.panel);
    }
    if (!current.pending_sync && ((current.status === "cancelled" && current.release_pending) || ["prepared", "ready_for_review", "reviewed", "submitted", "needs_recheck", "claimed", "needs_input"].includes(current.status))) {
      const controls = form(["ready_for_review", "reviewed", "submitted"].includes(current.status) ? "人工复核与结果记录" : "核验或停止当前任务", "保存人工确认", async () => { const payload = { ...binding(), acknowledge: ack.checked, source: source.value }; if (operation.value === "receipt") payload.locator = locator.value; if (operation.value === "resolve") { payload.conclusion = conclusion.value; payload.revision = revision.value; } await mutate(operation.value, payload); });
      const [operationWrap, operation] = input("人工操作", "select"); const actions = [];
      if (current.status === "ready_for_review") actions.push(["review", "我已核对当前页面字段和附件"]);
      if (current.status === "reviewed") actions.push(["submitted", "我已在原页面手动点击 Submit"]);
      if (current.status === "submitted") actions.push(["receipt", "我已看到并保存提交回执"]);
      if (["prepared", "claimed", "needs_input", "needs_recheck", "ready_for_review", "reviewed"].includes(current.status)) actions.push(["resolve", "核验资料变化或未知结果"]);
      if ((current.status === "cancelled" && current.release_pending) || ["prepared", "claimed", "needs_input", "ready_for_review", "reviewed", "needs_recheck"].includes(current.status)) actions.push(["release", current.status === "cancelled" && current.release_pending ? "核验并完成操作权释放" : "停止并释放操作权"]);
      for (const [value, label] of actions) { const option = el("option", label); option.value = value; operation.append(option); }
      const [sourceWrap, source] = input("核验来源（页面、截图或本地证据路径）"); source.required = true;
      const [locatorWrap, locator] = input("回执位置或编号"); const [conclusionWrap, conclusion] = input("未知结果核验结论", "select");
      for (const [value, label] of [["current_matches", "当前字段及附件与任务一致"], ["not_applied", "未申请，已核验原页面"], ["manual_stop", "停止，由我接管"]]) { const option = el("option", label); option.value = value; conclusion.append(option); }
      const [revisionWrap, revision] = input("核验后接纳的投递记录版本"); revision.value = data.applications.find(item => item.id === current.application_id)?.revision || current.application_revision;
      const [ackWrap, ack] = check("我已亲自核验；如释放任务，我已停止操作并处置原页面。此按钮只保存记录，不会点击招聘网站 Submit。"); ack.required = true;
      const update = () => { locatorWrap.hidden = operation.value !== "receipt"; locator.required = operation.value === "receipt"; conclusionWrap.hidden = operation.value !== "resolve"; revisionWrap.hidden = operation.value !== "resolve"; }; operation.addEventListener("change", update); update();
      addBefore(controls.fields, controls.save, operationWrap, sourceWrap, locatorWrap, conclusionWrap, revisionWrap, ackWrap); body.append(controls.panel);
    }
    if (current.pending_sync || current.sync_error) {
      const sync = form("恢复投递记录同步", "核对并重试同步", () => mutate("retry-sync", { ...binding(), revision: revision.value, acknowledge: ack.checked, source: source.value, preserve_note: preserve.checked }));
      const [revisionWrap, revision] = input("已核对的当前投递记录版本"); revision.value = data.applications.find(item => item.id === current.application_id)?.revision || current.application_revision; revision.required = true;
      const [sourceWrap, source] = input("同步核对来源"); source.required = true;
      const [preserveWrap, preserve] = check("保留原笔记，结束此次同步（已核验）");
      const [ackWrap, ack] = check("我已核对当前投递记录和原提交证据，确认仅恢复记录同步，不重复提交。"); ack.required = true;
      addBefore(sync.fields, sync.save, revisionWrap, sourceWrap, preserveWrap, ackWrap); body.append(sync.panel);
    }
    if (readbackTools) body.append(readbackTools);
  }
  window.addEventListener("handoff-prepare", event => { preparationApplication = event.detail.applicationId; selected = snapshot?.active_task?.id || ""; if (snapshot) render(); else refreshState(); });
  window.addEventListener("handoff-focus", () => {
    if (snapshot && body.dataset.dirty !== "true" && !stale) { selected = snapshot.active_task?.id || snapshot.tasks?.findLast(item => item.status === "submitted")?.id || ""; render(); }
  });
  window.addEventListener("portal-state", () => { if (body.dataset.dirty !== "true") refreshState(); });
  window.addEventListener("hashchange", () => { if (location.hash === "#handoff" && !snapshot) refreshState(); });
})();
