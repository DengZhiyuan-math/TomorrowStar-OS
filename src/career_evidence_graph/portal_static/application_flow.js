"use strict";

(() => {
  const root = $("flow-root");
  if (!root) return;
  let flow = null, intake = null, pipeline = null, selectedTask = null, busy = false, observing = false, rendering = false;
  const pipelineRequests = new Map();
  const admissionScope = payload => `admission:${payload.application_id ? "application" : "recommendation"}:${payload.application_id || payload.recommendation_id}`;
  let followingPipeline = true;
  let timer = null, renderedTask = "", renderedSavedJobs = "", renderedPipeline = "", taskDetailsOpen = false;
  const uncertainScopes = new Set();
  const pipelineTask = task => flow?.mode === "application" && (!!pipeline?.id || !!pipeline?.items?.length || pipeline?.active_task_id === task?.id);
  // The backend projects the active task's saved stage activity; the page does not classify stages.
  const preparationActivity = task => flow?.preparation_activity?.task_id === task?.id ? flow.preparation_activity.status : "needs_recheck";
  const stagesRunning = task => preparationActivity(task) === "running";
  const stagesUnresolved = task => preparationActivity(task) !== "idle";
  const taskScope = () => flow?.active_task?.application_id ? `flow:${flow.active_task.application_id}` : null;
  const pipelineScope = () => {
    const current = pipeline?.current_recommendation_id;
    const item = pipeline?.items?.find(item => item.recommendation_id === current);
    return current ? `pipeline:${item?.application_id || current}` : "pipeline";
  };
  const visibleScope = () => taskScope() || pipelineScope();
  const isUncertain = (scope = visibleScope()) => {
    const related = scope?.startsWith("flow:") ? scope.replace("flow:", "pipeline:") : scope?.startsWith("pipeline:") ? scope.replace("pipeline:", "flow:") : null;
    return uncertainScopes.has("pipeline") || uncertainScopes.has(scope) || uncertainScopes.has(related);
  };
  const readable = { flow: false, intake: false, pipeline: false };
  const diagnosticTasks = new Set();
  const manualTasks = new Set();
  const conditionDrafts = new Map();
  const preparationDrafts = new Map();
  const prismDrafts = new Map();
  const latexImportDrafts = new Map();
  const latexBaseDrafts = new Map();
  const exportReceipts = new Map();
  const groupEditDrafts = new Map();
  const answerDrafts = new Map();
  const materialDrafts = new Map();
  const materialTextDrafts = new Map();
  const materialTextEditors = new Map();
  const automaticSourceDrafts = new Map();
  const automaticSourceEditors = new Map();
  let answerSaving = false;
  const emailCorrectionDrafts = new Map();
  const resolutionDrafts = new Map();
  const formDifferenceDrafts = new Map();
  const batchSelections = new Map();
  let batchRequest = null;
  let ownsLease = false, lastHeartbeat = 0;
  let runtimeCheck = null, runtimeChecking = false;
  let controller = crypto.randomUUID();
  try {
    const saved = sessionStorage.getItem("tomorrowstar-flow-controller");
    if (/^[a-zA-Z0-9-]{8,100}$/.test(saved || "")) controller = saved;
    sessionStorage.setItem("tomorrowstar-flow-controller", controller);
  } catch { /* A storage-restricted web view can still control this page session. */ }
  const statusLabels = { draft: "等待分析", analyzing: "正在分析岗位", analysis_ready: "分析已完成", resume_generating: "正在生成简历", draft_ready: "草稿已保存", exporting: "正在导出 PDF", export_failed: "PDF 导出失败", resume_ready: "PDF 已生成", materials_ready: "当前 PDF 已保存", queued: "已准备 · 等待开始填写", filling: "正在填写并核验", needs_input: "等待你补充信息", ready_for_review: "等待你在原页复核", cancelled: "任务已取消", failed: "操作失败", needs_recheck: "结果待核验" };
  const pdfEnvironmentErrors = {
    resume_chrome_registration_denied: "PDF 导出已停止：当前执行环境拒绝浏览器注册所需的系统服务。不会自动重试；请先核对执行环境。",
    resume_chrome_registration_unknown: "PDF 导出已停止：无法核验浏览器注册服务的访问状态。不会自动重试；请先核对执行环境。",
  };
  const mailLabels = { idle: "尚未读取推荐邮件", running: "正在读取邮件与原岗位页面…", partial: "已读取部分推荐，范围尚未完成", complete: "推荐岗位已载入", no_matches: "没有找到推荐岗位", unavailable: "邮件连接暂不可用", failed: "读取失败，可明确重试", interrupted: "读取已中断，可明确继续", needs_recheck: "读取结果待核验" };

  function button(text, action, id, secondary = false) {
    const element = node("button", `button button-${secondary ? "secondary" : "primary"}`, text);
    element.type = "button";
    if (id) element.id = id;
    element.addEventListener("click", action);
    element.dataset.flowWrite = "true";
    return element;
  }
  function message(text, error = false) {
    const target = $("flow-notice");
    target.textContent = text;
    target.hidden = !text;
    target.classList.toggle("is-error", error);
  }
  function retainedMaterialAccepted(task) {
    const acceptance = task?.material_acceptance;
    return task?.origin === "existing_latex" && task.materials_confirmed === true && acceptance?.kind === "retained_human_material_acceptance" && acceptance.resume_id === task.resume_id && acceptance.pdf_sha256 === task.resume_sha256;
  }
  function lock() {
    const automatic = pipeline?.control === "running";
    const prismEditing = ["editing", "finishing", "open_failed"].includes(flow?.active_task?.prism_edit?.status);
    const prismFinishing = flow?.active_task?.prism_edit?.status === "finishing" || !!flow?.active_task?.prism_edit?.opening;
    const manualStages = new Set(["flow-start-analysis", "flow-start-resume", "flow-start-filling", "flow-prepare-worker", "flow-worker-resume", "flow-sync-inputs", "flow-cancel"]);
    for (const element of root.querySelectorAll("[data-flow-write]")) {
      const automationControl = element.closest("#flow-automation");
      const requiresPaused = element.dataset.flowRequiresPaused === "true";
      const unsavedSource = element.id === "flow-pipeline-start" && (prismEditing || automaticSourceDrafts.has(pipeline?.active_task_id) || [...materialTextDrafts.values()].some(draft => draft.task_id === pipeline?.active_task_id));
      const opportunityControl = element.closest("#flow-opportunities, #flow-intake-settings, #flow-batch-selection, #flow-job-management");
      const fresh = (automationControl ? readable.pipeline && readable.flow : opportunityControl ? readable.intake && readable.flow : readable.flow) && (!requiresPaused || readable.pipeline);
      element.disabled = element.dataset.flowStop !== "true" && (busy || isUncertain(element.dataset.flowScope || (automationControl ? pipelineScope() : visibleScope())) || !fresh) || !stateReady || element.dataset.blocked === "true" || unsavedSource || prismEditing && manualStages.has(element.id) && element.id !== "flow-cancel" || prismFinishing && element.id === "flow-cancel" || automatic && (manualStages.has(element.id) || requiresPaused);
    }
    root.setAttribute("aria-busy", String(busy));
  }
  function section(title, id) {
    const element = node("section", "panel flow-panel");
    if (id) element.id = id;
    element.append(node("h2", "", title));
    return element;
  }
  const heading = node("div", "page-heading");
  const headingCopy = node("div");
  const title = node("h1", "", "自动申请"); title.id = "flow-title";
  headingCopy.append(node("div", "eyebrow", "APPLICATIONS"), title, node("p", "", "邮件推荐、岗位匹配、专用简历和申请填写自动衔接，完成后通知你最终确认。"));
  const observe = button("读取最新状态", () => refresh(true), "flow-observe", true);
  delete observe.dataset.flowWrite;
  heading.append(headingCopy, observe);
  const alert = node("div", "notice"); alert.id = "flow-notice"; alert.hidden = true; alert.setAttribute("role", "status");
  const automation = section("自动申请流程", "flow-automation");
  const columns = node("div", "flow-columns");
  const opportunities = section("待处理岗位", "flow-opportunities");
  opportunities.append(node("p", "flow-muted", "自动流程会读取推荐并整理岗位。也可在这里补充 JD 或单独查看来源。"));
  const mailAfter = node("input"); mailAfter.type = "date"; mailAfter.id = "flow-mail-after";
  const mailBefore = node("input"); mailBefore.type = "date"; mailBefore.id = "flow-mail-before";
  const afterLabel = node("label", "", "读取起始日期（UTC，含）"); afterLabel.append(mailAfter);
  const beforeLabel = node("label", "", "读取截止日期（UTC，不含）"); beforeLabel.append(mailBefore);
  const mailDates = node("div", "flow-condition"); mailDates.append(afterLabel, beforeLabel);
  opportunities.append(mailDates, node("p", "flow-muted", "两项留空时读取最近七天。填写日期后，请同时指定起止范围。"));
  opportunities.append(button("从 Gmail 刷新推荐", () => {
    if (flow?.mode === "application") return pipelineAction("capture");
    const range = mailRange();
    if (range) mutate(async () => {
      intake = await api("/api/recommendations/refresh", { method: "POST", body: JSON.stringify(range) });
    });
  }, "flow-refresh-mail"));
  const continueMail = button("继续读取推荐", () => {
    const range = mailRange();
    if (range) mutate(async () => {
      intake = await api("/api/recommendations/continue", { method: "POST", body: JSON.stringify({ revision: intake.revision, ...range }) });
    });
  }, "flow-continue-mail", true);
  const mailStatus = node("p", "flow-muted"); mailStatus.id = "flow-mail-status"; mailStatus.setAttribute("role", "status");
  const mailProgress = node("div", "flow-muted"); mailProgress.id = "flow-mail-progress"; mailProgress.setAttribute("role", "status");
  const candidates = node("div", "flow-candidates"); candidates.id = "flow-candidates";
  const manual = button("粘贴 JD 或岗位链接", () => openApplication(), "flow-manual", true);
  delete manual.dataset.flowWrite;
  const savedJobs = node("div", "flow-candidates"); savedJobs.id = "flow-saved-jobs"; savedJobs.hidden = true;
  const batchSelection = node("div", "flow-stage"); batchSelection.id = "flow-batch-selection"; batchSelection.hidden = true;
  const batchSelectionCount = node("p", "flow-muted"); batchSelectionCount.id = "flow-batch-selection-count";
  const createBatch = button("保存材料批次", () => mutate(async () => {
    batchRequest ||= { request_id: crypto.randomUUID().replaceAll("-", ""), items: [...batchSelections.values()] };
    await api("/api/flow/batch-create", { method: "POST", body: JSON.stringify(batchRequest) });
    batchSelections.clear(); batchRequest = null; renderedSavedJobs = "";
  }), "flow-batch-create");
  batchSelection.append(batchSelectionCount, createBatch, node("p", "flow-muted", "仅保存你勾选的岗位，默认暂停。开始后一次处理一岗，真实申请继续暂停。"));
  opportunities.insertBefore(manual, opportunities.children[1]);
  opportunities.append(continueMail, mailStatus, mailProgress, candidates);
  const intakeSettings = node("details", "flow-details flow-intake-settings"); intakeSettings.id = "flow-intake-settings";
  intakeSettings.append(node("summary", "", "导入岗位与邮件设置"));
  for (const child of [...opportunities.children].slice(1)) if (child !== candidates) intakeSettings.append(child);
  opportunities.append(savedJobs, candidates);
  const jobManagement = section("岗位资料与排序", "flow-job-management");
  const jobSettings = node("div"); jobSettings.id = "flow-job-management-list"; jobManagement.append(jobSettings);
  const recommendationSettings = node("div"); recommendationSettings.id = "flow-recommendation-management"; intakeSettings.append(recommendationSettings);
  const taskManagement = section("当前任务详情", "flow-task-management");
  const work = node("div", "flow-work");
  const history = section("已保存任务", "flow-history");
  const tasks = node("div", "flow-task-list"); tasks.id = "flow-task-list"; history.append(tasks);
  const current = section("当前进度", "flow-task");
  const readiness = section("准备就绪检查", "flow-readiness"); readiness.hidden = true;
  const runtimePanel = section("当前准备服务", "flow-runtime"); runtimePanel.hidden = true;
  const materialBatch = node("details", "panel flow-panel flow-details"); materialBatch.id = "flow-material-batch"; materialBatch.hidden = true;
  const preparationDiagnostics = node("details", "panel flow-details"); preparationDiagnostics.id = "flow-preparation-diagnostics";
  preparationDiagnostics.append(node("summary", "", "技术诊断"), runtimePanel, readiness);
  const internalManagement = node("details", "panel flow-panel flow-details"); internalManagement.id = "flow-internal-management";
  const batchWarning = node("p", "notice is-error"); batchWarning.id = "flow-batch-warning"; batchWarning.hidden = true;
  internalManagement.append(node("summary", "", "设置与历史"), opportunities, intakeSettings, batchSelection, materialBatch, jobManagement, taskManagement, history, preparationDiagnostics);
  work.append(current, internalManagement); columns.append(work); root.append(heading, alert, batchWarning, automation, columns);

  function batchChoice(kind, row) {
    const key = `${kind}/${row.id}`;
    const label = node("label", "flow-check");
    const conflicted = row.selection_status === "source_conflict";
    if (conflicted && batchSelections.delete(key)) batchRequest = null;
    const check = node("input"); check.type = "checkbox"; check.checked = batchSelections.has(key); check.dataset.flowWrite = "true"; check.dataset.blocked = String(conflicted);
    check.addEventListener("change", () => {
      if (check.checked) batchSelections.set(key, { kind, id: row.id, revision: row.revision });
      else batchSelections.delete(key);
      batchRequest = null; renderBatchSelection(); lock();
    });
    label.append(check, node("span", "", "加入材料批次")); return label;
  }
  function renderBatchSelection() {
    batchSelection.hidden = flow?.mode !== "preparation";
    batchSelectionCount.textContent = `已勾选 ${batchSelections.size} 个岗位（每批最多 100 个）。`;
    createBatch.dataset.blocked = String(!batchSelections.size || batchSelections.size > 100 || !!flow?.preparation_batch && flow.preparation_batch.control !== "cancelled");
  }
  function batchReason(reason, task = null) {
    const labels = { selected: "已保存本次选择，尚未开始。", selecting: "正在核对本岗来源与历史记录。", user_selection: "批次已保存，等待你明确开始。", user_pause: "已按你的操作暂停。", user_resume: "已按你的操作继续。", user_cancel: "已按你的操作取消，已有进度保留。", user_retry: "已手动恢复待处理；批次暂停时需明确继续。", no_processable_items: "当前没有可继续的岗位；待处理岗位需你手动重试。", flow_restarted: "服务已重启，材料批次保持暂停。", draft: "等待开始岗位分析。", analyzing: "正在分析本岗 JD 与来源。", analysis_ready: "分析已保存，正在核对资格与语言政策。", resume_generating: "正在生成本岗简历草稿。", draft_review_required: "草稿已保存，等待你逐来源审阅。", draft_reviewed: "草稿审阅已记录，等待导出此版本 PDF。", exporting: "正在导出已审阅草稿，不重新生成内容。", pdf_review_required: "PDF 已生成，系统会核验并保存当前版本。", waiting_application_record: "材料已保存，等待投递结果记录；真实申请继续暂停。", flow_qualification_required: "必需资格待补充或存在冲突；补齐事实后手动重试该岗。", flow_resume_language_required: "岗位要求的简历语言需单独处理；确认后手动重试该岗。", flow_inputs_changed: "岗位或资料版本已变化，旧进度保留；请核对后手动重试。", flow_inputs_stale: "岗位或资料版本已变化，旧进度保留；请核对后手动重试。", source_required: "尚未取得完整 JD。请先在来源入口取得全文，再手动重试该岗。", application_already_in_progress: "该岗位已有申请进度，需先核验原记录。", resume_material_insufficient: "简历材料不足，请补齐可核验来源后手动重试。", resume_export_failed: "PDF 导出失败，已保留草稿；手动重试只继续导出。", flow_export_not_started: "上次 PDF 导出尚未开始，已保留草稿；可手动重试。", flow_result_needs_recheck: "结果尚未核验，整个材料批次已停止；先核验本岗已保存回执。", resume_export_needs_recheck: "PDF 导出结果尚未核验；先核验导出回执，不能直接重试。", flow_batch_needs_recheck: "本岗操作结果未知，请先核验已保存记录。", flow_interrupted: "本地阶段已中断，已有进度保留；请核对后手动重试。" };
    if (pdfEnvironmentErrors[reason]) return pdfEnvironmentErrors[reason];
    if (labels[reason]) return labels[reason];
    const error = Object.values(task?.stages || {}).find(stage => stage.error_code === reason)?.error_message;
    return error || `原因代码：${reason || "尚未取得"}。请核对本岗记录后继续。`;
  }
  function renderMaterialBatch() {
    const batch = flow?.preparation_batch;
    const expanded = new Set([...materialBatch.querySelectorAll("details[data-batch-review][open]")].map(item => item.dataset.batchReview));
    materialBatch.hidden = flow?.mode !== "preparation" || !batch;
    batchWarning.hidden = true;
    batchWarning.textContent = "";
    materialBatch.replaceChildren(node("summary", "", "材料批次与控制"));
    if (materialBatch.hidden) return;
    materialBatch.append(node("p", "flow-badges", { paused: "材料批次已暂停", running: "材料批次进行中", cancelled: "材料批次已取消", needs_recheck: "材料批次结果待核验" }[batch.control] || "材料批次状态待核验"));
    materialBatch.append(node("p", "flow-muted", batchReason(batch.reason)));
    const retainedBatch = batch.kind === "accepted_material_reuse";
    if (retainedBatch) materialBatch.append(node("p", "flow-muted", "已复用此前接受的具体 PDF 和原用户决定，不重新分析、生成或编译。此批次只登记已有材料，真实申请继续暂停。"));
    const waitingApplication = batch.items?.some(row => row.status === "waiting_application_record");
    if (waitingApplication) materialBatch.append(node("p", "flow-muted", "材料已保存，等待投递结果记录；真实申请继续暂停"));
    const needsRecheck = batch.control === "needs_recheck" || batch.items?.some(row => row.status === "needs_recheck");
    batchWarning.hidden = !needsRecheck;
    batchWarning.textContent = needsRecheck ? "操作结果待核验，后续处理已停止。已有任务和材料保留，请在设置与历史中核对已保存记录。" : "";
    if (needsRecheck) materialBatch.append(node("p", "flow-error", "先在本岗来源或 PDF 导出入口核验已保存结果，再点击“核验后继续材料批次”。未核验的结果会阻止恢复；核验通过后才继续本岗后续材料阶段。"));
    const resume = button(needsRecheck ? "核验后继续材料批次" : "开始／继续材料批次", () => batchControl("resume"), "flow-batch-resume");
    resume.dataset.blocked = String(!["paused", "needs_recheck"].includes(batch.control) || waitingApplication);
    const pause = button("暂停材料批次", () => batchControl("pause"), "flow-batch-pause", true);
    pause.dataset.blocked = String(batch.control !== "running");
    const cancel = button("取消材料批次", () => batchControl("cancel"), "flow-batch-cancel", true);
    cancel.dataset.blocked = String(retainedBatch || ["cancelled", "needs_recheck"].includes(batch.control) || batch.items?.some(row => row.status === "needs_recheck"));
    const controls = node("div", "flow-actions"); controls.append(resume, pause, cancel); materialBatch.append(controls);
    if (batch.control === "paused") materialBatch.append(node("p", "flow-muted", "已开始的当前本地阶段会完成并保存；后续阶段保持暂停。刷新页面不会开始处理。"));
    const labels = { pending: "等待处理", active: "当前正在处理", needs_input: "待补充 · 手动重试", deferred: "待处理 · 手动重试", stale: "输入已变化 · 手动重试", needs_recheck: "结果待核验 · 批次已停止", waiting_draft_review: "等待草稿审阅", waiting_pdf_review: "正在保存 PDF", waiting_application_record: "等待投递结果记录", cancelled: "本岗已取消" };
    const pending = (batch.items || []).filter(row => row.status === "pending");
    for (const row of batch.items || []) {
      const card = node("article", "flow-recommendation"); card.dataset.batchItem = row.item_id;
      card.append(node("h3", "", [row.company, row.role_title].filter(Boolean).join(" · ") || "已选岗位"), node("p", "flow-muted", labels[row.status] || "处置状态待核验"));
      const task = flow.tasks?.find(task => task.id === row.task_id);
      card.append(node("p", "flow-muted", batchReason(row.reason, task)));
      if (task) {
        const open = button("打开此岗任务", () => openTask(task.id), null, true); open.dataset.batchTask = task.id;
        delete open.dataset.flowWrite; card.append(open);
        const details = node("details", "flow-details"); details.dataset.batchReview = row.item_id; details.open = expanded.has(row.item_id);
        details.append(node("summary", "", "核对本岗 JD、来源与材料版本"));
        details.append(node("p", "flow-muted flow-hash", `任务 ${task.id} · ${statusLabels[task.status] || task.status}`), node("pre", "flow-text", task.job_description));
        details.append(node("p", "flow-muted flow-hash", `JD 版本 ${task.inputs?.jd_revision || "尚未核验"} · 来源版本 ${task.inputs?.sources_revision || "尚未核验"}`));
        const explanation = flow.explanations?.find(item => item.task_id === task.id);
        if (explanation) details.append(explanationDetails(explanation));
        const draft = task.artifacts?.slice().reverse().find(item => item.stage === "resume" && item.adopted && item.result?.kind === "draft" && item.result.id === task.draft_id)?.result;
        if (draft) {
          details.append(node("h4", "", "本岗草稿与来源"), node("p", "flow-muted flow-hash", `草稿 ${draft.id} · SHA256 ${draft.draft_sha256}`));
          details.append(node("p", "flow-muted", task.draft_review?.status === "reviewed" && task.draft_review.draft_id === draft.id && task.draft_review.draft_sha256 === draft.draft_sha256 ? "此草稿已审阅" : "此草稿待审阅"));
          if (task.draft_review) details.append(node("p", "flow-muted flow-hash", `审核草稿 ${task.draft_review.draft_id} · SHA256 ${task.draft_review.draft_sha256} · 输入版本 ${task.draft_review.input_revision}`));
          details.append(sourceReview(draft, true));
        }
        const pdf = task.artifacts?.slice().reverse().find(item => item.stage === "export" && item.adopted && item.result?.id === task.resume_id)?.result;
        if (pdf) {
          details.append(node("h4", "", "本岗 PDF 版本"), node("p", "flow-muted flow-hash", `PDF ${pdf.id} · SHA256 ${pdf.pdf_sha256}`), node("p", "flow-muted", task.materials_confirmed ? "当前 PDF 已保存" : "PDF 已生成"));
          if (/^\/api\/flow\/resumes\/[a-f0-9]{32}\/pdf$/.test(pdf.preview_url || "")) {
            const link = node("a", "text-link", "查看此岗 PDF ↗"); link.href = pdf.preview_url; link.target = "_blank"; link.rel = "noopener noreferrer"; details.append(link);
          }
        }
        card.append(details);
      }
      if (["deferred", "needs_input", "stale"].includes(row.status)) {
        const retry = button("重试该岗", () => mutate(() => api("/api/flow/batch-retry", { method: "POST", body: JSON.stringify({ batch_id: batch.id, batch_revision: batch.revision, item_id: row.item_id }) })), null, true);
        retry.dataset.blocked = String(["cancelled", "needs_recheck"].includes(batch.control)); card.append(retry);
      }
      const order = node("div", "flow-actions");
      for (const [direction, label, edge] of [["up", "上移", pending[0] === row], ["down", "下移", pending[pending.length - 1] === row]]) {
        const move = button(label, () => mutate(() => api("/api/flow/batch-reorder", { method: "POST", body: JSON.stringify({ batch_id: batch.id, batch_revision: batch.revision, item_id: row.item_id, direction }) })), null, true);
        move.dataset.blocked = String(row.status !== "pending" || edge || ["cancelled", "needs_recheck"].includes(batch.control)); order.append(move);
      }
      card.append(order);
      materialBatch.append(card);
    }
  }
  function batchControl(operation) {
    const batch = flow?.preparation_batch;
    if (!batch) return;
    return mutate(async () => {
      await api("/api/flow/batch-control", { method: "POST", body: JSON.stringify({ batch_id: batch.id, batch_revision: batch.revision, operation }) });
      if (operation === "resume") selectedTask = null;
    });
  }

  function renderMode() {
    const preparing = flow?.mode === "preparation";
    title.textContent = preparing ? "投递工作台" : "自动申请";
    headingCopy.querySelector(".eyebrow").textContent = preparing ? "MATERIAL PREPARATION" : "APPLICATIONS";
    headingCopy.querySelector("p").textContent = preparing ? "查看当前岗位进度与最终简历。" : "邮件推荐、岗位匹配、专用简历和申请填写自动衔接，完成后通知你最终确认。";
    const label = preparing ? "投递工作台" : "自动申请";
    if (viewLabels.flow !== label) {
      viewLabels.flow = label;
      const navigation = document.querySelector('[data-view="flow"]');
      if (navigation) navigation.lastChild.textContent = label;
      setView();
    }
    preparationDiagnostics.hidden = !preparing;
    readiness.hidden = !preparing;
    runtimePanel.hidden = !preparing;
    if (!preparing) return;
    runtimePanel.replaceChildren(node("h2", "", "当前准备服务"));
    const runtime = flow.runtime;
    if (runtime) {
      runtimePanel.append(node("p", "flow-muted", `服务版本 ${runtime.version} · Python ${runtime.python_version} · 材料准备模式`), node("p", "flow-muted flow-hash", `服务会话 ${runtime.session_id}`));
      const versions = node("details", "flow-details"); versions.append(node("summary", "", "核对已加载的代码与界面版本"), node("p", "flow-muted flow-hash", `运行代码版本 ${runtime.engine_revision}`), node("p", "flow-muted flow-hash", `本会话界面版本 ${runtime.ui_revision}`)); runtimePanel.append(versions);
    } else runtimePanel.append(node("p", "flow-error", "当前服务版本尚未核验，请读取最新状态。"));
    runtimePanel.append(node("p", "flow-muted", "重开后只读取已保存进度；分析、生成与导出仍需明确操作。此处为当前服务身份，安装版验收另行记录。"));
    readiness.replaceChildren(node("h2", "", "准备就绪检查"));
    const labels = { gmail: "Gmail", model: "模型", sources: "职业资料", pdf: "PDF 导出", policy: "筛选与生成政策", draft: "当前材料" };
    for (const [key, name] of Object.entries(labels)) {
      const check = flow.preparation?.checks?.[key];
      const row = node("p", check?.status === "available" ? "flow-source" : "flow-muted");
      row.append(node("strong", "", `${name}：`), document.createTextNode(check?.message || "尚未取得就绪状态，请读取最新状态。"));
      readiness.append(row);
    }
  }

  function renderPipeline() {
    automation.hidden = flow?.mode === "preparation";
    automation.dataset.taskId = `${pipeline?.id || ""}/${pipelineScope()}/${pipeline?.active_task_id || ""}`;
    const key = JSON.stringify([flow?.mode, pipeline?.enabled, pipeline?.id, pipeline?.control, pipeline?.status, pipeline?.current_recommendation_id, pipeline?.active_task_id, pipeline?.wait_reason, pipeline?.notice?.message || pipeline?.notice?.title, pipeline?.items?.map(item => [item.application_id, item.recommendation_id, item.company, item.role_title, item.status, item.score?.lower, item.score?.upper, item.score?.coverage])]);
    if (renderedPipeline === key) return;
    renderedPipeline = key;
    automation.replaceChildren(node("h2", "", "自动申请流程"));
    if (automation.hidden) return;
    const labels = { idle: "尚未开始", reading_email: "正在收录推荐邮件", starting_email: "正在启动邮件读取", selecting_job: "正在选择下一个待处理岗位", acquiring_source: "正在取得当前岗位的完整 JD", starting_source: "正在启动当前岗位读取", waiting_for_mail: "正在等待新的推荐邮件", matching: "正在计算当前岗位匹配度", generating_resume: "正在生成并检查完整岗位材料", preparing: "正在准备申请", starting_worker: "正在检查并启动填写", admitting_worker: "正在启动填写", awaiting_native_check: "正在后台检查填写环境", recovering_worker: "正在核验原页面并恢复当前岗位", filling: "正在填写并上传申请材料", ready_for_review: "申请已准备好，请到原网站最终确认", needs_input: "需要补充信息", needs_recheck: "结果待核验，已停止", blocked: "流程已停止，请查看具体原因", paused: "自动流程已暂停", interrupted: "上次流程已中断，进度已保留", expired: "本次运行窗口已结束，进度已保留", no_matches: "本次未取得可处理的完整岗位", complete: "本次处理已完成", unavailable: "自动流程暂不可用" };
    const status = node("p", "flow-badges", labels[pipeline?.status] || (pipeline?.control === "running" ? "自动流程进行中" : "尚未开始"));
    status.setAttribute("role", "status"); automation.append(status);
    automation.append(node("p", "flow-muted", "开启后，系统持续收录推荐邮件，并按顺序处理当前岗位的 JD、匹配、完整材料、填写和上传。等待你处理信息或最终确认时，仍可收录新邮件；最终 Submit 由你操作。"));
    const actions = node("div", "flow-actions");
    // A flow saved before the queue (no queue_mode) resumes through start.
    const startPipeline = button(pipeline?.id ? "继续当前岗位" : "开启自动流程", () => pipelineAction(pipeline?.queue_mode ? "continue" : "start"), "flow-pipeline-start");
    startPipeline.dataset.blocked = String(!pipeline?.enabled || pipeline.control === "running");
    const pausePipeline = button("暂停自动流程", () => mutate(async () => {
      pipeline = await api("/api/pipeline/pause", { method: "POST", body: "{}" });
    }, { stopping: true, scope: pipelineScope(), domain: "pipeline" }), "flow-pipeline-pause", true);
    pausePipeline.dataset.flowStop = "true";
    pausePipeline.dataset.blocked = String(pipeline?.control !== "running");
    // Sign in once in the App's own browser; later job pages open signed in.
    const signIn = button("登录领英", () => mutate(async () => {
      await api("/api/browser-sign-in", { method: "POST", body: JSON.stringify({ site: "linkedin" }) });
      signInNote.hidden = false;
    }, { domain: "pipeline" }), "flow-sign-in", true);
    const signInNote = node("p", "flow-muted", "已打开领英登录窗口：登录后关闭该窗口即可，之后的岗位页会保持登录。");
    signInNote.hidden = true;
    actions.append(startPipeline, pausePipeline, signIn);
    if (pipeline?.current_recommendation_id) {
      const skip = button("跳过当前岗位", () => pipelineAction("skip", {}, true), "flow-pipeline-skip", true);
      skip.dataset.flowStop = "true";
      actions.append(skip);
    }
    automation.append(actions, signInNote);
    if (pipeline?.wait_reason === "codex_resume_required") automation.append(node("p", "flow-muted", "当前岗位等待 Codex 完成分经历写作、程序组装和单一终审；完成后自动继续，其他岗位保持等待。"));
    if (pipeline?.wait_reason === "score_approval") automation.append(node("p", "flow-muted", "此岗位匹配分在 55–75 区间，或两个模型分差较大：已完成分析、尚未生成材料。查看匹配概览后，点击“继续当前岗位”即批准生成材料；不投可点跳过。"));
    if (pipeline?.wait_reason === "precision_adjustment") automation.append(node("p", "flow-muted", "此岗位已完成分析、完整简历与已发现的必要附稿。你可以先调整材料，再点击“继续当前岗位”使用当前版本填写。"));
    if (pipeline?.notice) automation.append(node("p", "flow-muted", pipeline.notice.message || pipeline.notice.title));
    for (const item of pipeline?.items || []) {
      const score = item.score;
      const line = node("p", "flow-muted", `${item.company || "岗位"}${item.role_title ? ` · ${item.role_title}` : ""}${score && typeof score.lower === "number" ? ` · 匹配 ${Math.round(score.lower) === Math.round(score.upper) ? Math.round(score.upper) : `${Math.round(score.lower)}–${Math.round(score.upper)}`}` : ""}${item.status === "analysis_failed" ? " · 分析结果未通过校验，已保留记录并跳过" : ""}${item.status === "skipped" && item.reason === "low_match_score" ? " · 匹配分低于 15，已自动跳过；可返回此岗位继续" : ""}`);
      automation.append(line);
      if (item.status === "skipped") {
        const restore = button("返回此岗位", () => pipelineAction("return", { application_id: item.application_id || item.recommendation_id }, true), "", true);
        restore.dataset.flowStop = "true";
        line.append(restore);
      }
    }
    if (pipeline?.active_task_id) {
      const open = button("跟随当前岗位与材料", () => { followingPipeline = true; selectedTask = pipeline.active_task_id; refresh(); }, "flow-pipeline-current", true);
      delete open.dataset.flowWrite; automation.append(open);
    }
  }

  function pipelineAction(action, payload = {}, stopping = false) {
    return mutate(async () => {
      const key = JSON.stringify([action, payload]);
      if (!pipelineRequests.has(key)) pipelineRequests.set(key, crypto.randomUUID().replaceAll("-", ""));
      pipeline = await api(`/api/pipeline/${action}`, { method: "POST", body: JSON.stringify({ request_id: pipelineRequests.get(key), ...payload }) });
      pipelineRequests.delete(key);
      followingPipeline = true;
      selectedTask = pipeline.active_task_id || null;
    }, { stopping, scope: pipelineScope(), domain: "pipeline" });
  }

  function adopted(stage) {
    const task = flow?.active_task;
    return task?.artifacts?.slice().reverse().find(item => item.stage === stage && item.adopted && item.result?.id === (item.result?.kind === "draft" ? task.draft_id : stage === "export" ? task.resume_id : task[`${stage}_id`]))?.result;
  }
  function batchStageBlocked(task) {
    const batch = flow?.preparation_batch;
    return !!batch && batch.control !== "cancelled" && (batch.control !== "running" || batch.active_task_id !== task.id);
  }
  function applicationTitle(id) {
    const application = data.applications.find(item => item.id === id);
    return application ? [application.company, application.role_title].filter(Boolean).join(" · ") : "已保存岗位";
  }
  function mailRange() {
    if (!mailAfter.value && !mailBefore.value) return {};
    if (!mailAfter.value || !mailBefore.value || mailAfter.value >= mailBefore.value) {
      message("请同时填写有序的起始与截止日期（UTC）。", true); return null;
    }
    return { after: mailAfter.value, before: mailBefore.value };
  }
  function renderIntake() {
    const unavailable = flow?.mode === "preparation" && flow.preparation?.checks?.gmail?.status === "unavailable";
    const failed = ["failed", "unavailable", "interrupted", "needs_recheck"].includes(intake?.status);
    const accountChanged = intake?.error_code === "gmail_account_changed";
    mailStatus.textContent = accountChanged ? "邮箱账号已变化，请重新刷新推荐。" : intake?.message || (failed ? mailLabels[intake.status] : unavailable ? flow.preparation.checks.gmail.message : mailLabels[intake?.status]) || "尚未读取推荐邮件";
    const blocked = (flow?.mode === "preparation" && flow.capabilities?.codex_cli === "unavailable") || intake?.enabled !== true || intake?.status === "running";
    $("flow-refresh-mail").dataset.blocked = String(blocked);
    const progress = intake?.progress;
    const applicationMode = flow?.mode === "application";
    mailDates.hidden = applicationMode; mailDates.nextElementSibling.hidden = applicationMode;
    $("flow-refresh-mail").textContent = applicationMode ? "收录推荐邮件" : "从 Gmail 刷新推荐";
    continueMail.hidden = applicationMode || !progress;
    continueMail.dataset.blocked = String(blocked || progress?.can_continue !== true);
    mailProgress.replaceChildren();
    if (progress) {
      mailProgress.append(node("p", "", `读取范围：${progress.window || "尚未开始读取邮件"}`));
      if (typeof progress.account_verified === "boolean") mailProgress.append(node("p", "", progress.account_verified ? "本读取范围账号已核验。" : "本读取范围账号尚未核验。"));
      mailProgress.append(node("p", "", `已读取 ${progress.pages || 0} 页 · ${intake.message_count || 0} 封邮件`));
      mailProgress.append(node("p", "", `邮件处理：本地收录 ${progress.mail_captured || 0} · 已标记 ${progress.mail_labeled || 0} · 已归档 ${progress.mail_archived || 0} · 待核对 ${progress.mail_needs_recheck || 0}`));
      if (progress.mail_processing_error === "gmail_processing_invalid") mailProgress.append(node("p", "flow-error", "邮件处理标签配置无效；仍可收录推荐；未执行标记或归档。请在设置中更正标签。"));
      else if (progress.mail_label_configured === false) mailProgress.append(node("p", "", "未配置邮件处理标签；仍可收录推荐，不执行标记或归档。"));
      if (progress.mail_needs_recheck) mailProgress.append(node("p", "flow-error", "邮件处理结果待核对；核对前不会重复标记或归档。"));
      mailProgress.append(node("p", "", `待处理岗位 ${progress.pending_candidates || 0} · 未完整邮件 ${progress.incomplete_messages || 0} · 未读邮件 ${progress.unread_messages || 0}`));
      mailProgress.append(node("p", "", `岗位来源：已完成 ${progress.source_complete || 0} · 失败 ${progress.source_failed || 0} · 待核验 ${progress.source_needs_recheck || 0}`));
      mailProgress.append(node("p", "", progress.has_more ? "仍有后续页，请明确继续读取。" : "暂无后续页记录。"));
      if (progress.range_incomplete || progress.incomplete_messages || progress.unread_messages) mailProgress.append(node("p", "flow-error", "当前读取范围尚未完整核验，未完整邮件与未读范围仍待处理。"));
      if (failed) mailProgress.append(node("p", "flow-error", accountChanged ? "账号已变化，旧读取范围不能续读；请重新刷新推荐建立新范围。" : "读取尚未完成，已读结果保留；可在连接恢复后明确继续读取。"));
    }
    const openedSources = new Set([...recommendationSettings.querySelectorAll("details[data-recommendation][open]")].map(item => item.dataset.recommendation));
    const openedRecommendations = new Set([...recommendationSettings.querySelectorAll("details[data-recommendation-settings][open]")].map(item => item.dataset.recommendationSettings));
    candidates.replaceChildren();
    recommendationSettings.replaceChildren();
    for (const row of intake?.recommendations || []) {
      const card = node("article", "flow-recommendation");
      card.append(node("h3", "", [row.company, row.role_title].filter(Boolean).join(" · ") || "岗位信息待补齐"));
      const management = node("details", "flow-details flow-job-settings"); management.dataset.recommendationSettings = row.id; management.open = openedRecommendations.has(row.id); management.append(node("summary", "", [row.company, row.role_title].filter(Boolean).join(" · ") || "岗位信息待补齐"));
      if (flow?.mode === "preparation") management.append(batchChoice("recommendation", row));
      if (row.location) card.append(node("p", "flow-muted", row.location));
      const labels = [row.jd_completeness === "full" ? "完整 JD" : row.jd_completeness === "excerpt" ? "摘要 · 待补全文" : "完整性未知"];
      const acquisition = { login_required: "需要登录原岗位页面", expired: "岗位已失效", unavailable: "原页面暂不可用" }[row.acquisition_status];
      if (acquisition) labels.push(acquisition);
      const checkpoint = row.acquisition_checkpoint || (row.jd_completeness === "full" ? "complete" : "not_started");
      const checkpointLabel = { not_started: "尚未取得完整 JD", complete: "取源结果已保存", failed: "取源失败 · 可明确重试", needs_recheck: "取源结果待核验" }[checkpoint];
      if (checkpointLabel) labels.push(checkpointLabel);
      if (row.existing_application) labels.push(`已有申请 · ${statusLabel(row.existing_application.status)}`);
      if (row.possible_applications?.length) labels.push("存在相似历史记录 · 需核验重复");
      if (row.selection_status === "needs_recheck") labels.push("保存结果待核验");
      if (row.selection_status === "source_conflict") labels.push("新来源与已有记录冲突 · 待核对来源，已有记录保持不变");
      card.append(node("p", "flow-badges", labels.join(" · ")));
      const source = node("details", "flow-details"); source.dataset.recommendation = row.id; source.open = openedSources.has(row.id); source.append(node("summary", "", "邮件与 JD 来源"));
      for (const mail of row.source_messages || []) source.append(node("p", "flow-muted", [mail.subject, mail.from, mail.received_at].filter(Boolean).join(" · ")));
      source.append(node("p", "flow-muted", `公司：${row.company || "尚未取得"} · 岗位：${row.role_title || "尚未取得"}`));
      source.append(node("p", "flow-muted", `来源 URL：${row.jd_source?.url || row.jd_source_url || row.url || "尚未取得"}`));
      source.append(node("p", "flow-muted", `捕获时间：${row.captured_at || "尚未取得"}`));
      source.append(node("p", "flow-muted", `JD 完整性：${row.jd_completeness || "unknown"}`));
      if (row.source_error_code) source.append(node("p", "flow-error", `取源错误：${row.source_error_code}`));
      const href = safeURL(row.url);
      if (href) { const link = node("a", "text-link", "查看原岗位 ↗"); link.href = href; link.target = "_blank"; link.rel = "noopener noreferrer"; source.append(link); }
      source.append(node("pre", "flow-text", row.job_description || row.context || "未取得 JD 正文。")); management.append(source);
      if (["not_started", "failed", "needs_recheck"].includes(checkpoint) && (!applicationMode || checkpoint === "needs_recheck")) {
        const reconcile = checkpoint === "needs_recheck";
        const acquire = button(reconcile ? "核验已保存取源结果" : checkpoint === "failed" ? "重试取得 JD" : "取得完整 JD", () => mutate(async () => {
          intake = await api(`/api/recommendations/${reconcile ? "reconcile-source" : "acquire"}`, { method: "POST", body: JSON.stringify({ id: row.id, ...(!reconcile ? { revision: row.revision, ...(checkpoint === "failed" ? { retry: true } : {}) } : {}) }) });
        }), null, true);
        acquire.dataset.blocked = String(intake?.enabled !== true || intake?.status === "running"); card.append(acquire);
      }
      const existingTask = flow?.tasks?.find(task => task.application_id === row.existing_application?.id);
      const queued = pipeline?.items?.some(item => item.recommendation_id === row.id);
      const choose = button(applicationMode ? (existingTask ? "查看已有申请任务" : queued ? "已加入申请队列" : "加入申请队列") : row.existing_application ? "打开已有申请任务" : "选择此岗位", () => existingTask && applicationMode ? openTask(existingTask.id) : selectRecommendation(row));
      choose.dataset.blocked = String(applicationMode ? (!existingTask && (queued || !readable.pipeline || !pipeline?.enabled || ["needs_recheck", "source_conflict"].includes(row.selection_status))) : (intake?.enabled !== true || intake?.status === "running" || checkpoint === "needs_recheck" || ["needs_recheck", "source_conflict"].includes(row.selection_status) || !!row.possible_applications?.length || (!row.existing_application && (row.jd_completeness !== "full" || row.acquisition_status !== "available"))));
      if (applicationMode && existingTask) delete choose.dataset.flowWrite;
      else if (applicationMode) choose.dataset.flowScope = admissionScope({ recommendation_id: row.id });
      card.append(choose); candidates.append(card);
      recommendationSettings.append(management);
    }
  }
  function renderSavedJobs() {
    const key = JSON.stringify([flow?.mode, flow?.explanations, flow?.order_revision, flow?.order_mode, flow?.active_task?.application_id, data.connections?.applications, data.applications.map(item => [item.id, item.revision])]);
    if (renderedSavedJobs === key) return;
    renderedSavedJobs = key;
    savedJobs.hidden = flow?.mode !== "preparation";
    savedJobs.replaceChildren();
    jobSettings.replaceChildren();
    jobManagement.hidden = savedJobs.hidden;
    if (savedJobs.hidden) return;
    if (data.connections?.applications !== true) {
      savedJobs.append(node("p", "flow-error", "岗位记录尚未连接，请恢复数据连接后读取最新状态。")); return;
    }
    const available = data.applications.filter(item => item.job_description?.trim());
    if (flow?.explanations) {
      const positions = new Map(flow.explanations.map((item, index) => [item.application_id, index]));
      available.sort((left, right) => (positions.get(left.id) ?? Infinity) - (positions.get(right.id) ?? Infinity));
      jobSettings.append(node("p", "flow-muted", flow.order_mode === "manual" ? "当前顺序：手动调整" : "当前顺序：按匹配分"));
    }
    if (!available.length) savedJobs.append(node("p", "flow-muted", "尚无已保存 JD。可手动记录完整 JD 后，在此选择岗位。"));
    for (const [index, application] of available.entries()) {
      const card = node("article", "flow-recommendation flow-saved-job"); card.dataset.applicationId = application.id;
      card.classList.toggle("is-current", application.id === flow?.active_task?.application_id);
      if (application.id === flow?.active_task?.application_id) card.setAttribute("aria-current", "true");
      card.append(node("h3", "", applicationTitle(application.id)));
      const explanation = flow?.explanations?.find(item => item.application_id === application.id);
      if (explanation) card.append(node("p", "flow-job-summary", explanation.progress?.label || "尚未分析"));
      card.append(button(application.id === flow?.active_task?.application_id ? "查看当前岗位" : "选择已有岗位", () => mutate(() => createForApplication(application.id)), null, true));
      const settings = node("details", "flow-details flow-job-settings"); settings.dataset.applicationId = application.id; settings.append(node("summary", "", applicationTitle(application.id)), batchChoice("application", application));
      const jd = node("details", "flow-details"); jd.append(node("summary", "", "核对已保存 JD 全文"), node("pre", "flow-text", application.job_description)); settings.append(jd, latexImportForm(application));
      if (flow?.order_revision) {
        const order = node("div", "flow-actions");
        for (const [direction, label, edge] of [["up", "上移岗位", index === 0], ["down", "下移岗位", index === available.length - 1]]) {
          const move = button(label, () => mutate(() => api("/api/flow/reorder", { method: "POST", body: JSON.stringify({ application_id: application.id, direction, order_revision: flow.order_revision }) })), null, true);
          move.dataset.blocked = String(edge); order.append(move);
        }
        settings.append(order);
      }
      jobSettings.append(settings); savedJobs.append(card);
    }
  }
  function latexImportForm(application) {
    const details = node("details", "flow-details"); details.id = `flow-import-latex-${application.id}`;
    details.append(node("summary", "", "使用已有 LaTeX 简历"));
    details.append(node("p", "flow-muted", "保存已有简历的独立岗位版本；不调用模型。技术导出与事实审核分别记录，旧任务和 PDF 保留。"));
    const form = node("form", "flow-condition");
    const saved = latexImportDrafts.get(application.id) || { project_root: "", main: "main.tex" };
    const directory = node("input"); directory.required = true; directory.value = saved.project_root; directory.setAttribute("aria-label", "已有简历 LaTeX 项目目录");
    const main = node("input"); main.required = true; main.value = saved.main; main.setAttribute("aria-label", "已有简历 LaTeX 主文件");
    for (const input of [directory, main]) input.dataset.flowWrite = "true";
    const remember = () => latexImportDrafts.set(application.id, { project_root: directory.value, main: main.value });
    directory.addEventListener("input", remember); main.addEventListener("input", remember);
    const directoryLabel = node("label", "", "已有简历 LaTeX 项目目录"); directoryLabel.append(directory);
    const mainLabel = node("label", "", "已有简历 LaTeX 主文件"); mainLabel.append(main);
    const submit = button("接入此 LaTeX 新版本", () => {}, null, true); submit.type = "submit";
    form.append(directoryLabel, mainLabel, submit);
    form.addEventListener("submit", event => {
      event.preventDefault(); remember();
      if (!directory.value.trim() || !main.value.trim()) return;
      mutate(async () => {
        const task = await api("/api/flow/import-latex", { method: "POST", body: JSON.stringify({ application_id: application.id, application_revision: application.revision, project_root: directory.value.trim(), main: main.value.trim() }) });
        selectedTask = task.id;
      });
    });
    details.append(form); return details;
  }
  function systemDetails() {
    let details = taskManagement.querySelector("#flow-system-details");
    if (!details) {
      details = node("details", "flow-details flow-system-details"); details.id = "flow-system-details";
      details.open = taskDetailsOpen;
      details.append(node("summary", "", "系统处理详情与手动编辑")); taskManagement.append(details);
    }
    return details;
  }
  function renderSystem(render) {
    const details = systemDetails(), previous = new Set(current.children);
    render();
    for (const child of Array.from(current.children)) if (!previous.has(child)) {
      for (const warning of child.querySelectorAll(".flow-error")) {
        if (!Array.from(current.children).some(item => item.classList.contains("flow-error") && item.textContent === warning.textContent)) current.append(node("p", "flow-error", warning.textContent));
      }
      details.append(child);
    }
  }
  function renderFinalPdf(task) {
    const exported = adopted("export"), resumed = adopted("resume");
    const pdf = exported || (resumed?.kind !== "draft" ? resumed : null);
    const panel = node("section", "flow-stage flow-final-pdf"); panel.id = "flow-final-pdf";
    const factualPending = task.origin === "existing_latex" && !retainedMaterialAccepted(task);
    const path = pdf?.preview_url;
    const identified = /^\/api\/flow\/resumes\/[a-f0-9]{32}\/pdf$/.test(path || "") && /^[a-f0-9]{64}$/.test(pdf?.pdf_sha256 || "");
    const local = flow?.local_materials === true;
    const stale = !local && (flow?.preparation?.checks?.draft?.status === "stale" || flow?.active_explanation?.fresh === false || flow?.active_explanation?.materials_fresh === false);
    const invalid = flow?.pdf_integrity?.status === "invalid" || !local && (flow?.draft_integrity?.status === "invalid" || flow?.preparation?.checks?.draft?.status === "invalid" || flow?.mode === "preparation" && !prismCurrent(task));
    panel.append(node("h3", "", pdf && (factualPending || stale || invalid || !identified) ? "已保存简历 PDF" : "最终简历 PDF"));
    if (factualPending && pdf) panel.append(node("p", "flow-error", "此 PDF 的事实审核尚未完成，当前仅为已保存的技术核对版本。"));
    if (!pdf) {
      panel.append(node("p", "flow-muted", "最终 PDF 尚未生成。"));
      if (["resume_generating", "exporting"].includes(task.status)) panel.append(node("p", "flow-muted", "系统正在处理，完成后会在这里显示。"));
    } else if (!identified) panel.append(node("p", "flow-error", "PDF 标识不完整，当前版本尚不能核验。请保留已有材料并核对记录。"));
    else {
      if (stale || invalid) panel.append(node("p", "flow-error", "当前版本已变化或尚不能核验；此处保留已保存的 PDF，请先核对版本。"));
      const link = node("a", "button button-secondary", stale || invalid || factualPending ? "打开已保存 PDF ↗" : "打开最终 PDF ↗");
      link.id = "flow-pdf-link"; link.href = path; link.target = "_blank"; link.rel = "noopener noreferrer"; panel.append(link);
      if (!stale && !invalid) {
        const frame = node("iframe", "flow-pdf"); frame.id = "flow-final-pdf-preview"; frame.title = factualPending ? "已保存简历 PDF · 事实审核待完成" : "当前岗位最终简历 PDF"; frame.src = path; panel.append(frame);
      }
    }
    if (task.automatic_materials && task.origin === "generated_latex" && task.draft_id) {
      const session = task.prism_edit || {};
      const editing = ["editing", "finishing"].includes(session.status);
      const running = stagesRunning(task);
      const actions = node("div", "flow-actions");
      const edit = button("在 Prism 中编辑", () => groupAction(task, "begin-prism-edit"), "flow-begin-prism-edit", true);
      edit.dataset.flowRequiresPaused = "true";
      edit.dataset.blocked = String(editing || running || task.status === "cancelled");
      actions.append(edit);
      if (editing) {
        const finish = button(session.status === "finishing" ? "核验编辑返回结果" : "完成编辑，返回校对", () => groupAction(task, "finish-prism-edit"), "flow-finish-prism-edit", true);
        finish.dataset.flowRequiresPaused = "true";
        finish.dataset.blocked = String(running || session.opening || task.status === "cancelled");
        actions.append(finish);
        panel.append(node("p", "flow-muted", "人工编辑期间系统停止修改此 TeX。关闭编辑器不会完成交接；请明确返回，仅校对拼写、语法、大小写、标点和重复词。"));
      }
      if (/^http:\/\/(?:127\.0\.0\.1|localhost|\[::1\]):\d+\/$/.test(session.editor_url || "")) {
        const editor = node("a", "text-link", "打开当前 Prism 编辑器 ↗"); editor.href = session.editor_url; editor.target = "_blank"; editor.rel = "noopener noreferrer"; actions.append(editor);
      }
      if (local && !editing) {
        const capture = button("编译并接回 PDF", () => groupAction(task, "capture-prism-result"), "flow-capture-prism-result", true);
        capture.dataset.flowRequiresPaused = "true";
        capture.dataset.blocked = String(running || task.status === "cancelled");
        actions.append(capture);
      }
      panel.append(actions);
      const sourceStates = { editing: "正在人工编辑，上一版最终 PDF 保留。", open_failed: "Prism 连接结果尚未核验。系统保持停止修改原稿，请明确重新进入编辑。", proofreading: "正在快速文字校对，上一版最终 PDF 保留。", unexported_changes: "有未导出的修改，等待编译当前源。上一版最终 PDF 仍可查看。", waiting_for_result: "尚无对应的成功编译结果。人工源文和上一版最终 PDF 已保留。", proofreading_unavailable: "快速校对未完成，人工原文和上一版最终 PDF 已保留；不会自动重试模型。", source_changed: "返回校对期间又有修改。新原文和上一版最终 PDF 已保留，请重新进入编辑后明确返回。", return_needs_recheck: "编辑返回结果尚未核验。请核验已有结果；系统保持停止写入。" };
      if (sourceStates[task.material_source_state]) panel.append(node("p", "flow-muted", sourceStates[task.material_source_state]));
      for (const warning of session.notices || session.warnings || []) panel.append(node("p", "flow-muted", typeof warning === "string" ? warning : warning.message || warning.reason || JSON.stringify(warning)));
      if (session.patches?.length) {
        const patches = node("details", "flow-details"); patches.append(node("summary", "", "查看快速校对修改"));
        for (const patch of session.patches) patches.append(node("pre", "flow-text", `${patch.original || patch.before || ""}\n→ ${patch.replacement || patch.after || ""}`));
        panel.append(patches);
      }
      for (const historical of task.final_pdf_history || []) {
        const old = node("a", "text-link", `查看历史最终 PDF · ${historical.resume_id.slice(0, 8)} ↗`); old.href = `/api/flow/resumes/${historical.resume_id}/pdf`; old.target = "_blank"; old.rel = "noopener noreferrer"; panel.append(old);
      }
    }
    current.append(panel);
  }
  function renderTask() {
    const task = flow?.active_task;
    const worker = flow?.worker;
    const stale = flow?.mode === "preparation" && flow.preparation?.checks?.draft?.status === "stale";
    const jobs = worker?.jobs?.map(job => job.page_observation
      ? { ...job, page_observation: { ...job.page_observation, at: undefined } }
      : job);
    const key = JSON.stringify([task, flow?.preparation_activity, pipeline?.id, pipeline?.active_task_id, pipeline?.items?.map(item => item.task_id), flow?.active_explanation, flow?.match_explanation, flow?.resume_language, flow?.draft_integrity, flow?.pdf_integrity, flow?.prism, flow?.group_review, flow?.mode, flow?.preparation, flow?.eligibility, flow?.capabilities, flow?.experience_generation, [worker?.enabled, worker?.control, worker?.controller, jobs, worker?.input_items, worker?.runtime_status?.observation, worker?.worker_error, worker?.runtime?.id], [runtimeCheck, runtimeChecking, runtimeCheckFresh(task)], flow?.tasks?.map(item => [item.id, item.revision]), data.applications.map(item => [item.id, item.company, item.role_title, item.url])]);
    if (renderedTask === key) return;
    renderedTask = key;
    const sameTask = current.dataset.taskId === task?.id;
    const fitOpen = sameTask && current.querySelector("#flow-fit-details")?.open === true;
    taskDetailsOpen = sameTask && taskManagement.querySelector("#flow-system-details")?.open === true;
    current.dataset.taskId = task?.id || "";
    current.replaceChildren(node("h2", "", "当前进度"));
    taskManagement.replaceChildren(node("h2", "", "当前任务详情"));
    if (flow?.capabilities?.codex_cli === "unavailable") current.append(node("p", "flow-error", "Codex 可执行文件不可用。请将 TOMORROWSTAR_CODEX_EXECUTABLE 或启动参数 --codex-executable 修正为有执行权限的现有文件绝对路径，再重开。已保存的岗位和材料仍可查看；新分析和简历生成等待工具路径修复。"));
    tasks.replaceChildren();
    for (const item of flow?.tasks?.slice().reverse() || []) {
      const open = button(`${applicationTitle(item.application_id)} · ${statusLabels[item.status] || item.status}`, () => openTask(item.id), null, true);
      delete open.dataset.flowWrite; open.disabled = busy; open.setAttribute("aria-pressed", String(item.id === task?.id)); tasks.append(open);
    }
    if (!task) { current.append(node("p", "flow-muted", flow?.enabled === false ? "单岗位服务尚未连接。" : flow?.mode === "application" ? "将岗位加入申请队列，开启后按顺序处理。查看历史任务不会改变当前岗位。" : "选择一个完整岗位，或从岗位详情打开工作台。")); return; }
    current.append(node("h3", "flow-job-title", applicationTitle(task.application_id)), node("p", "flow-badges", statusLabels[task.status] || task.status));
    // The automatic flow shows the same overview for display; its gates never read it.
    const pipelineScore = flow.active_explanation || flow.match_explanation ? null : pipeline?.items?.find(item => item.task_id === task.id)?.score;
    if (pipelineScore && typeof pipelineScore.lower === "number") current.append(node("p", "flow-badges", `${pipelineScore.lower === pipelineScore.upper ? `匹配 ${Math.round(pipelineScore.lower)}/100` : `匹配 ${Math.round(pipelineScore.lower)}–${Math.round(pipelineScore.upper)}/100`} · 分数确定度 ${Math.round(pipelineScore.coverage)}%`));
    if (!flow.active_explanation && flow.match_explanation) {
      const explanation = explanationPanel(flow.match_explanation); explanation.id = "flow-explanation";
      explanation.querySelector("#flow-fit-details").open = fitOpen; current.append(explanation);
    }
    if (flow.active_explanation) {
      const explanation = explanationPanel(flow.active_explanation); explanation.id = "flow-explanation";
      explanation.querySelector("#flow-fit-details").open = fitOpen; current.append(explanation);
      if (flow.active_explanation.fresh === false) current.append(node("p", "flow-error", "岗位资料已变化，适配结论待核验；原分析和材料保留。"));
      if (flow.active_explanation.qualification?.status === "conflict") current.append(node("p", "flow-error", "存在硬条件冲突，请展开岗位适配概览核对。"));
    }
    renderFinalPdf(task);
    if (task.codex_handoff_restart) {
      const panel = node("section", "flow-stage"); panel.id = "flow-current-handoff";
      panel.append(node("h3", "", "准备本岗位的新页填写"), node("p", "flow-muted", "材料和填写记录已保留。本次准备尚未完成，不代表新页面已填写或附件已上传。"));
      if (task.status !== "cancelled") panel.append(button("继续准备本次填写任务", () => restartSavedHandoff(task), "flow-retry-handoff-restart"));
      current.append(panel);
      return;
    }
    if (task.codex_handoff_attempt) {
      const attempt = task.codex_handoff_attempt;
      const status = task.status === "cancelled" ? "cancelled" : attempt.status;
      const panel = node("section", "flow-stage"); panel.id = "flow-current-handoff";
      const messages = {
        prepared: "本次新页尚未完成填写。复用现有材料和有来源的填写记录，先读取新表单再补空白。",
        claimed: "正在处理本次填写。旧页面记录不代表本次字段或附件已完成。",
        needs_input: "本次填写需要补充信息。当前页面和已填内容保留。",
        needs_recheck: "本次结果仍需核验。保留当前页面，不重复未知动作。",
        ready_for_review: "执行者已核验本次字段与附件。请在当前页面复核，最终 Submit 由你手动完成。",
        reviewed: "当前页面已交给你处理，最终 Submit 由你操作。",
        submitted: "已有提交记录，不再重新填写。",
        confirmed: "已记录接收结果，不再重新申请。",
        cancelled: "本次填写已停止，材料和历史记录保留。",
      };
      panel.append(node("h3", "", "本次填写尝试"), node("p", status === "needs_recheck" ? "flow-error" : "flow-muted", messages[status] || "本次填写状态尚不能核验。"));
      if (Number.isInteger(attempt.reuse_field_count)) panel.append(node("p", "flow-muted", `已保留 ${attempt.reuse_field_count} 条同岗位填写提示；不会替代新页面的实际回读。`));
      const link = node("a", "", "打开岗位申请页"); link.href = /^https?:\/\//.test(attempt.job_url || "") ? attempt.job_url : "#"; link.target = "_blank"; link.rel = "noopener noreferrer"; panel.append(link);
      if (attempt.prompt && !["cancelled", "submitted", "confirmed"].includes(status)) {
        const details = node("details", "flow-details"); details.append(node("summary", "", "查看本次填写任务"));
        const prompt = node("textarea"); prompt.readOnly = true; prompt.value = attempt.prompt; prompt.setAttribute("aria-label", "本次填写任务说明"); details.append(prompt);
        panel.append(button("复制本次填写任务", async () => {
          try { await navigator.clipboard.writeText(prompt.value); message("本次任务已复制。使用现有材料填写，最终 Submit 仍由你操作。"); }
          catch { details.open = true; prompt.focus(); prompt.select(); message("请按 ⌘C 或 Ctrl+C 复制本次任务。"); }
        }, "flow-copy-current-handoff"), details);
      }
      if (status === "ready_for_review") panel.append(button("重新识别并使用现有材料", () => restartSavedHandoff(task), "flow-restart-existing-handoff"));
      current.append(panel);
      return;
    }
    if (task.codex_handoff_ref) {
      const reference = task.codex_handoff_ref;
      const panel = node("section", "flow-stage"); panel.id = "flow-existing-handoff";
      panel.append(node("h3", "", "已保存的填写与附件记录"), node("p", reference.status === "ready_for_review" ? "flow-muted" : "flow-error", reference.status === "ready_for_review" ? "上次执行者的填写和附件记录已保存。原页关闭后可复用资料重新填写；旧报告不代表当前页面仍已完成。最终 Submit 由你手动操作。" : "既有上传状态需要核对。保留原页面、填写和附件，不重新填表或上传。"), node("p", "flow-hash", reference.filename || ""));
      const link = node("a", "", "打开原岗位申请页"); link.href = /^https?:\/\//.test(reference.job_url || "") ? reference.job_url : "#"; link.target = "_blank"; link.rel = "noopener noreferrer"; panel.append(link);
      if (reference.status === "ready_for_review" && task.status !== "cancelled") panel.append(button("重新识别并使用现有材料", () => restartSavedHandoff(task), "flow-restart-existing-handoff"));
      current.append(panel);
      return;
    }
    if (task.experience_handoff) {
      const generation = flow.experience_generation || task.experience_handoff;
      const panel = node("section", "flow-stage"); panel.id = "flow-experience-generation";
      const phases = { codex_required: generation.mapping_required ? "等待 Codex 核对经历与来源对应" : "等待 Codex 按经历写作并组装", review_required: "完整稿已组装，等待单一 Codex agent 终审", adopted: "终审通过，已采用当前完整稿", unavailable: "经历生成进度暂时不能核验，请保留已保存片段" };
      panel.append(node("h3", "", "分经历简历生成"), node("p", "flow-muted", phases[generation.status] || "等待 Codex 接续已保存的经历片段"), node("p", "flow-muted", "各经历片段和原稿已保留。Codex 完成写作、组装和终审后继续导出 PDF，无需逐段确认。"), node("p", "flow-hash", `生成记录 ${generation.id}`));
      for (const experience of generation.experiences || []) systemDetails().append(node("p", "flow-source", experience.title || experience.experience_id));
      if (generation.status === "adopted" && !pipelineTask(task)) {
        const resume = button("继续采用已终审材料", () => mutate(() => api("/api/flow/resume-experience-generation", { method: "POST", body: JSON.stringify({ task_id: task.id, task_revision: task.revision, generation_id: generation.id }) })), "flow-resume-experience-generation");
        panel.append(resume);
      }
      if (generation.status === "unavailable") current.append(node("p", "flow-error", "简历生成进度暂时不能核验，请保留已保存材料并核对记录。"));
      systemDetails().append(panel);
    }
    if (flow?.mode === "preparation" && task.origin !== "existing_latex") renderPreparationRecovery(task, stale);
    const jd = node("details", "flow-details"); jd.append(node("summary", "", "本任务完整 JD"), node("pre", "flow-text", task.job_description)); systemDetails().append(jd);
    if (task.origin === "existing_latex") {
      current.append(node("p", "flow-muted", retainedMaterialAccepted(task) ? "此版本 PDF 的内容和排版已接受，原决定及历史保留。" : "当前材料尚有事实审核待完成，系统处理详情和历史已保留。"));
      const draft = adopted("resume"), pdf = adopted("export");
      if (draft?.kind === "draft") renderSystem(() => { renderDraft(draft, task); renderPdfExport(draft, task); });
      if (pdf) renderMaterials(pdf, task);
      for (const stage of Object.values(task.stages || {})) if (stage.status === "failed") current.append(node("p", "flow-error", stage.error_message || "本地导出未完成，请核验记录后重试。"));
      return;
    }
    const languageBlocked = flow?.mode === "preparation" && flow.resume_language?.status === "needs_input";
    if (flow?.mode === "preparation" && flow.resume_language) {
      const language = node("section", "flow-stage"); language.id = "flow-resume-language";
      language.append(node("h3", "", "简历草稿语言"), node("p", languageBlocked ? "flow-error" : "flow-muted", flow.resume_language.message || "默认语言：English（英文）。"));
      for (const requirement of flow.resume_language.requirements || []) language.append(node("p", "flow-source", requirement.text));
      if (languageBlocked) language.append(node("p", "flow-error", "本岗位的简历语言要求等待单独处理；请先核对原要求。"));
      (languageBlocked ? current : systemDetails()).append(language);
    }
    if (task.status === "cancelled") {
      if (flow?.mode === "preparation") {
        const draft = adopted("resume"), pdf = adopted("export");
        if (draft?.kind === "draft") renderSystem(() => renderDraft(draft, task));
        if (pdf) renderMaterials(pdf, task);
      }
      if (task.worker_ref) renderWorker(task); return;
    }
    const actions = node("div", "flow-actions");
    const edit = button("修改岗位或 JD", () => openApplication(data.applications.find(item => item.id === task.application_id)), "flow-edit-job", true); delete edit.dataset.flowWrite;
    const sync = button("同步最新岗位与资料", async () => {
      if (!await confirmAction("同步会按最新 JD、资料与模型配置更新任务，受影响的分析、简历和确认需要重做；旧版本仍保留。此操作不会自动分析或填写。", "同步最新输入")) return;
      mutate(async () => {
        const response = await api(`/api/applications/${encodeURIComponent(task.application_id)}`);
        await api("/api/flow/update-inputs", { method: "POST", body: JSON.stringify({ task_id: task.id, task_revision: task.revision, application_revision: response.application.revision }) });
      });
    }, "flow-sync-inputs", true);
    const cancel = button("取消此任务", async () => {
      if (await confirmAction("取消后停止本任务的后续阶段，并保留已保存资料。已有页面或填写结果须单独核验。", "取消任务")) mutate(() => api("/api/flow/cancel", { method: "POST", body: JSON.stringify({ task_id: task.id, task_revision: task.revision }) }));
    }, "flow-cancel", true);
    actions.append(edit, sync); if (!pipelineTask(task)) actions.append(cancel); systemDetails().append(actions);
    if (stale) current.append(node("p", "flow-error", `${flow.preparation.checks.draft.message} 请点击“同步最新岗位与资料”后继续。`));
    const analyze = button("分析此岗位", () => start("analysis", task.stages?.analysis?.status === "failed"), "flow-start-analysis");
    const manual = node("details", "flow-details"); manual.append(node("summary", "", "手动操作"));
    manual.open = manualTasks.has(task.id);
    manual.addEventListener("toggle", () => { if (manual.isConnected) { if (manual.open) manualTasks.add(task.id); else manualTasks.delete(task.id); } });
    if (pipeline?.enabled && !pipelineTask(task)) systemDetails().append(manual);
    const analysisStatus = task.stages?.analysis?.status;
    analyze.textContent = analysisStatus === "failed" ? "重试岗位分析" : "分析此岗位";
    analyze.dataset.blocked = String(stale || batchStageBlocked(task) || flow?.capabilities?.analysis === false || !["pending", "failed"].includes(analysisStatus));
    if (!pipelineTask(task)) (pipeline?.enabled ? manual : systemDetails()).append(analyze);
    const analysis = adopted("analysis");
    if (analysis) renderSystem(() => renderAnalysis(analysis));
    const resume = adopted("resume");
    if (task.cover_letter) {
      const letter = task.cover_letter;
      const letterLabels = { pending: "等待写作", queued: "等待写作", running: "正在写作与检查", ready: "正文已保存", failed: "生成失败，可稍后补充", needs_recheck: "结果待核验", cancelled: "已停止，原稿保留" };
      const panel = node("section", "flow-stage"); panel.id = "flow-cover-letter";
      panel.append(node("h3", "", "Cover Letter"), node("p", "flow-muted", letterLabels[letter.status] || letter.status));
      if (letter.error_message) panel.append(node("p", "flow-error", letter.error_message));
      if (["failed", "cancelled"].includes(letter.status)) panel.append(button("仅重试 Cover Letter", () => mutate(() => api("/api/flow/start-cover-letter", { method: "POST", body: JSON.stringify({ task_id: task.id, task_revision: task.revision, retry: true }) })), "flow-retry-cover-letter", true));
      if (letter.status === "needs_recheck") panel.append(button("只读核验 Cover Letter 结果", () => mutate(() => api("/api/flow/recheck-cover-letter", { method: "POST", body: JSON.stringify({ task_id: task.id, task_revision: task.revision }) })), "flow-recheck-cover-letter", true));
      if (letter.result?.text) {
        const details = node("details", "flow-details");
        details.append(node("summary", "", "查看已保存正文"), node("p", "flow-material-text", letter.result.text));
        panel.append(details);
      }
      current.append(panel);
    }
    if (task.material_consistency) {
      const check = task.material_consistency;
      const labels = { queued: "等待核对两份材料的一致性", running: "正在核对两份材料的一致性", passed: "两份材料的一致性检查已通过", conflict: "两份材料存在事实冲突，请核对", needs_recheck: "材料一致性检查结果待核验", failed: "一致性检查尚未开始，可仅重试检查", cancelled: "一致性检查已停止，材料保留" };
      const panel = node("section", "flow-stage"); panel.append(node("p", "flow-muted", labels[check.status] || check.status));
      if (check.status === "needs_recheck") panel.append(button("只读核验材料一致性结果", () => mutate(() => api("/api/flow/recheck-material-consistency", { method: "POST", body: JSON.stringify({ task_id: task.id, task_revision: task.revision }) })), "flow-recheck-material-consistency", true));
      if (check.status === "cancelled" || check.status === "failed" && check.error_code === "material_consistency_not_started") {
        const retry = button("仅重试材料一致性检查", () => mutate(() => api("/api/flow/retry-material-consistency", { method: "POST", body: JSON.stringify({ task_id: task.id, task_revision: task.revision }) })), "flow-retry-material-consistency", true);
        retry.dataset.flowRequiresPaused = "true"; panel.append(retry);
      }
      current.append(panel);
    }
    if (task.experience_handoff && task.stages?.resume?.error_code === "resume_author_needs_recheck") {
      current.append(button("只读核验简历作者结果", () => mutate(() => api("/api/flow/recheck-resume-author", { method: "POST", body: JSON.stringify({ task_id: task.id, task_revision: task.revision }) })), "flow-recheck-resume-author", true));
    }
    if (analysis) {
      if (flow?.mode === "preparation") systemDetails().append(renderLatexBase(task));
      const generate = button(task.latex_base ? (task.stages?.resume?.status === "failed" ? "重试生成完整 LaTeX 岗位版本" : "生成完整 LaTeX 岗位版本") : flow?.mode === "preparation" ? (task.stages?.resume?.status === "failed" ? "重试生成简历草稿" : "生成岗位简历草稿") : (task.stages?.resume?.status === "failed" ? "重试生成简历" : "生成岗位专用简历"), () => start("resume", task.stages?.resume?.status === "failed"), "flow-start-resume");
      const qualificationBlocked = flow?.mode === "preparation" && flow.active_explanation && !["supported", "not_specified"].includes(flow.active_explanation.qualification?.status);
      generate.dataset.blocked = String(!!task.experience_handoff || stale || batchStageBlocked(task) || languageBlocked || qualificationBlocked || flow?.capabilities?.resume === false || !["pending", "failed"].includes(task.stages?.resume?.status));
      if (!pipelineTask(task)) systemDetails().append(generate);
    }
    if (resume?.kind === "draft") renderSystem(() => { renderDraft(resume, task); renderPdfExport(resume, task); });
    else if (resume && !adopted("export")) renderMaterials(resume, task);
    const pdf = adopted("export");
    if ((flow?.mode === "preparation" || task.automatic_materials) && pdf) renderMaterials(pdf, task);
    if (resume || task.worker_ref) renderWorker(task);
    for (const [stage, value] of Object.entries(task.stages || {})) {
      if (value.status === "failed") {
        const error = pdfEnvironmentErrors[value.error_code] || value.error_message || { resume_material_insufficient: "材料不足，请补齐可核验来源并重新分析。", resume_latex_context_too_large: "本次取材超出处理范围，尚未启动模型。原资料已保留；请先核对并调整本次取材范围。", flow_latex_base_changed: "完整 LaTeX 底稿已变化。核对后重新绑定当前底稿，再生成独立版本；原记录保留。", flow_draft_mismatch: "生成结果与当前岗位、底稿或资料版本不符，请保留原记录并核验。", resume_export_failed: "PDF 导出未完成，可仅重试导出。", flow_export_not_started: "上次 PDF 导出尚未开始，可明确仅重试导出。", flow_cancelled: "任务已取消，导出保持停止。" }[flow?.mode === "preparation" ? value.error_code : ""] || value.error_code || "请核对资料后重试。";
        current.append(node("p", "flow-error", `${stage === "analysis" ? "岗位分析" : stage === "export" ? "PDF 导出" : "简历生成"}失败：${error}`));
      }
    }
    if (task.runtime_error) current.append(node("p", "flow-error", task.runtime_error));
  }
  function renderPreparationRecovery(task, stale) {
    const binding = node("details", "flow-details"); binding.id = "flow-task-binding";
    binding.append(node("summary", "", "核对任务身份与输入版本"), node("p", "flow-muted flow-hash", `任务 ${task.id} · 记录版本 ${task.revision} · 输入轮次 ${task.input_epoch || 0}`), node("p", "flow-muted flow-hash", `岗位 ${task.application_id} · 岗位记录版本 ${task.application_revision}`));
    const inputLabels = { jd_revision: "JD 版本", sources_revision: "职业来源版本", analysis_configuration_revision: "分析配置版本", resume_configuration_revision: "简历配置版本", information_library_revision: "通用信息库版本", preparation_policy_revision: "政策版本" };
    for (const [key, label] of Object.entries(inputLabels)) if (task.inputs?.[key]) binding.append(node("p", "flow-muted flow-hash", `${label} ${task.inputs[key]}`));
    systemDetails().append(binding);
    const panel = node("section", "flow-stage"); panel.id = "flow-recovery"; panel.append(node("h3", "", "已保存进度与下一步"));
    const recovery = task.recovery_history?.at(-1);
    if (recovery) {
      const stage = { analysis: "岗位分析", resume: "简历生成", export: "PDF 导出" }[recovery.stage] || "准备阶段";
      const disposition = recovery.status === "needs_recheck" ? "恢复时已开始，结果待核验" : recovery.previous_status === "queued" ? "恢复时尚未开始，保留为手动重试" : "恢复时执行已中断，保留为手动重试";
      panel.append(node("p", "flow-muted", `上次恢复记录 · ${stage}：${disposition}。当前操作以以下进度为准。`));
      const record = node("details", "flow-details"); record.append(node("summary", "", "上次恢复记录"), node("p", "flow-muted flow-hash", `${recovery.at} · 输入轮次 ${recovery.input_epoch} · 输入版本 ${recovery.inputs_revision} · 尝试 ${recovery.attempt_id || "尚未开始"}`)); panel.append(record);
    }
    const unknown = Object.entries(task.stages || {}).find(([, stage]) => stage.status === "needs_recheck");
    if (unknown) panel.append(node("p", "flow-muted flow-hash", `未决${unknown[0] === "export" ? "导出" : "阶段"}尝试 ${unknown[1].attempt_id || "尚未核验"} · 草稿 ${task.draft_id || "尚未生成"}`));
    let next;
    if (unknown) next = unknown[0] === "export" ? "导出结果待核验。先点击“核验导出结果”只读核对原回执，不会重新导出或调用模型。" : "上次结果待核验。保留原任务并读取最新状态，核验前不要重试。";
    else if (stale) next = "输入已变化。请先核对原材料，明确同步最新岗位与资料，再决定重做受影响的阶段。";
    else if (task.stages?.resume?.status === "failed" && task.stages.resume.error_code === "resume_latex_context_too_large") next = "本次尚未启动模型。原输入和历史记录已保留；请先确定有界取材范围，相同输入直接重试不会解决。";
    else if (task.status === "materials_ready") next = "材料已保存，真实申请继续暂停。等待另行处理投递与结果记录。";
    else if (task.status === "resume_ready") next = "PDF 已保存。可直接预览；开始填写前会自动核验并绑定此版本。";
    else if (task.status === "export_failed") next = pdfEnvironmentErrors[task.stages?.export?.error_code] || "草稿与审阅记录已保留。需要时点击“仅重试 PDF 导出”，不会重新生成简历。";
    else if (task.status === "draft_ready" && task.origin === "generated_latex") next = "完整 LaTeX 岗位版本已保存，分组事实审核待完成。PDF 导出和当前版本绑定保持阻止，真实申请继续暂停。";
    else if (task.status === "draft_ready") next = task.draft_review?.status === "reviewed" ? "草稿及审阅已保存。需要时明确导出此版本 PDF。" : "草稿已保存。请逐来源审阅，再记录此草稿已审阅。";
    else if (task.status === "analysis_ready") next = "岗位分析已保存。核对资格与具体理由后，可明确生成简历草稿。";
    else if (task.status === "cancelled") next = "任务已取消，已有材料保留供核对；不会自动恢复。";
    else if (stagesRunning(task)) next = "当前阶段仍有执行记录，请等候持久结果或读取最新状态；不要重复启动。";
    else if (task.stages?.resume?.status === "failed") next = "简历生成未完成。核对输入与失败原因后，可手动重试生成草稿。";
    else if (task.stages?.analysis?.status === "failed") next = "岗位分析未完成。核对输入后，可点击“重试岗位分析”。";
    else next = "任务已保存，尚未开始分析。核对完整 JD 后，明确点击“分析此岗位”。";
    panel.append(node("p", unknown ? "flow-error" : "flow-muted", next));
    const batch = flow.preparation_batch;
    if (batch && batch.control !== "cancelled" && batch.items?.some(row => row.task_id === task.id) && batch.control !== "running") panel.append(node("p", "flow-muted", "材料批次保持停止。待处理岗位需手动重试，其余阶段需在批次中明确继续。"));
    current.append(panel);
  }
  const number = value => typeof value === "number" && Number.isFinite(value) ? String(Math.round(value * 100) / 100) : "—";
  const matchScoreText = score => score.lower === score.upper ? `${number(score.lower)}/100` : `${number(score.lower)}–${number(score.upper)}/100`;
  const judgmentLabels = { supported: "有支持", partial: "部分支持", gap: "已知缺口", unknown: "资料未知" };
  const FIT_LEGEND = "每项满足度由模型在判档范围内给出（支持 75–100、部分支持 30–75、资料未知 0–15、缺口 0，按 5 分取整），再按固定业务组权重折算 100 分；引用待核验或资料未读完的项保留可能范围。";
  function sourceDescription(item) {
    if (item.confirmed_information) return "信息库 · 本人已确认的资料";
    if (item.application_trusted) return "职业经历库 · 已保存资料";
    const labels = [item.source_name || item.title || item.source_id || item.id, item.document_locator || item.locator, item.review_status === "documentary" ? "文献资料 · 未作能力审核" : item.review_status, item.attribution, item.boundaries];
    return labels.filter(Boolean).join(" · ");
  }
  function appendLines(container, lines, className = "flow-muted") {
    for (const line of lines || []) container.append(node("p", className, typeof line === "string" ? line : JSON.stringify(line)));
  }
  function explanationPanel(explanation) {
    const panel = node("section", "flow-fit-overview"); panel.setAttribute("aria-label", "岗位匹配概览");
    const qualification = explanation.qualification || {};
    const labels = { supported: "硬条件已确认支持", not_specified: "未列独立硬条件", conflict: "存在硬条件冲突", needs_input: "资格信息待核对", analysis_required: "尚未分析", unassessed: "资格尚未评估" };
    const heading = node("div", "flow-fit-heading");
    heading.append(node("h3", "", "岗位适配概览"), node("span", `flow-fit-status ${qualification.status === "conflict" ? "flow-fit-gap" : ""}`, labels[qualification.status] || "资格尚未评估")); panel.append(heading);
    if (explanation.fresh === false) panel.append(node("p", "flow-error", "历史分析：资料已变化，结论待更新。"));
    const score = explanation.score;
    const scored = score && [score.lower, score.upper, score.coverage].every(value => typeof value === "number" && Number.isFinite(value));
    const scorePanel = node("div", "flow-fit-score"); scorePanel.id = "flow-fit-score";
    if (scored) {
      const metrics = node("div", "flow-fit-metrics");
      const material = explanation.material_read_coverage;
      const resume = explanation.resume_coverage;
      const metricValues = [[matchScoreText(score), score.lower === score.upper ? "背景匹配分" : "背景匹配区间"],
        ...(material ? [[material.complete ? "读取完成" : "读取未完成", "资料读取"], [resume?.status === "generated" ? `${number(resume.percent)}%` : resume?.status === "unavailable" ? "采用来源待核验" : "尚未成稿", "简历覆盖"]] : [[`${number(score.coverage)}%`, "分数确定度"]])];
      for (const [value, label] of metricValues) {
        const metric = node("div"); metric.append(node("strong", "", value), node("span", "", label)); metrics.append(metric);
      }
      const bar = node("div", "flow-fit-score-bar"); bar.setAttribute("role", "img"); bar.setAttribute("aria-label", `已支持 ${number(score.lower)}%，未知项最多增加 ${number(score.upper - score.lower)}%`);
      for (const [name, width] of [["supported", score.lower], ["uncertain", score.upper - score.lower]]) { const segment = node("span", `flow-fit-score-${name}`); segment.style.width = `${Math.max(0, Math.min(100, width))}%`; bar.append(segment); }
      scorePanel.append(metrics, bar);
    } else scorePanel.append(node("p", "flow-muted", "尚无已保存的匹配分。"));
    const business = explanation.business_summary;
    if (business) scorePanel.append(node("p", "flow-fit-business", [business.business_objective, business.work_outputs?.length ? `产出：${business.work_outputs.join("、")}` : ""].filter(Boolean).join(" · ")));
    panel.append(scorePanel);
    const models = explanation.model_scores;
    if (models) {
      // Decided 2026-10-31: sol and Opus score side by side; a large gap needs the user's review.
      const middle = value => (value.lower + value.upper) / 2;
      const line = `sol ${number(middle(models.primary))} · Opus ${number(middle(models.second))} · 分差 ${number(models.gap)}`;
      panel.append(node("p", models.needs_review ? "flow-error" : "flow-fit-note", models.needs_review ? `两个模型分差较大，需你审核：${line}` : `两个模型一致，取平均：${line}`));
      const differing = (models.differing_requirements || []).map(index => (explanation.reasons || [])[index]).filter(Boolean);
      if (models.needs_review && differing.length) {
        const list = node("ul", "flow-fit-list");
        for (const reason of differing.slice(0, 6)) list.append(node("li", "", reason.text));
        panel.append(node("p", "flow-muted", "两个模型判断不一致的要求："), list);
      }
    } else if (explanation.reasons?.some(reason => typeof reason.fit === "number")) {
      panel.append(node("p", "flow-fit-note", "仅单模型评分（第二模型未运行或未完成）。"));
    }
    if (explanation.factual_rechecks?.some(item => item.status === "supported")) panel.append(node("p", "flow-fit-note", "已复用信息库中的确认事实核验学历与实习安排。"));
    if (explanation.match_recheck) panel.append(node("p", "flow-fit-note", "已结合经历库与 GitHub 库中按需读取的原始证据复核。"));
    if (explanation.match_recheck_stale) panel.append(node("p", "flow-error", "经历库来源已变化，原复核保留为历史；当前展示原分析及仍适用的确认事实。"));
    const reasons = explanation.reasons || [];
    const conflicts = (qualification.conditions || []).filter(condition => condition.status === "conflict");
    const normalize = text => String(text || "").trim().replace(/\s+/g, " ").toLowerCase();
    const displayItems = reasons.map(reason => ({ ...reason }));
    for (const condition of conflicts) {
      const index = Number.isInteger(condition.requirement_index) && displayItems[condition.requirement_index]
        ? condition.requirement_index : displayItems.findIndex(reason => normalize(reason.text) === normalize(condition.text));
      if (index >= 0) displayItems[index] = { ...displayItems[index], judgment: "gap", qualification_conflict: true };
      else displayItems.push({ text: condition.text, judgment: "gap", qualification_conflict: true });
    }
    const counts = node("div", "flow-fit-counts"); counts.setAttribute("aria-label", "要求支持情况");
    for (const [judgment, label] of [["supported", "资料支持"], ["partial", "部分支持"], ["gap", "已知缺口"], ["unknown", "待核对"]]) {
      const count = displayItems.filter(reason => (reason.judgment || "unknown") === judgment).length;
      const item = node("div", `flow-fit-count flow-fit-${judgment}`); item.append(node("strong", "", String(count)), node("span", "", label)); counts.append(item);
    }
    panel.append(counts);
    const columns = node("div", "flow-fit-reasons");
    const topic = item => {
      if (item.scoring_framework?.group?.label) return item.scoring_framework.group.label;
      const text = String(item.text || "").toLowerCase();
      for (const [pattern, label] of [[/visa|work permit|authori[sz]ation|right to work|签证|工作许可/, "工作资格与签证"], [/student|degree|bachelor|master|phd|graduate|学位|在读|毕业/, "学历与在读状态"], [/english|language|英语|语言/, "语言要求"], [/internship|available|start|month|实习|入职|月份/, "实习时间与地点"], [/python|c\+\+|programming|coding|software|编程|开发/, "编程与工程"], [/quantitative|mathemat|statistic|probability|统计|数学|量化/, "数理与量化"], [/research|analys|data|研究|分析|数据/, "研究与数据分析"], [/team|communicat|collaborat|团队|沟通/, "协作与沟通"]]) if (pattern.test(text)) return label;
      return "其他岗位要求";
    };
    const summarized = displayItems.filter(reason => !reason.qualification_conflict);
    const importance = item => item.importance === "required" ? 0 : 1;
    const strengths = summarized.filter(reason => reason.judgment === "supported").sort((left, right) => importance(left) - importance(right));
    const priority = item => item.judgment === "gap" ? 0 : item.hard_condition && item.judgment === "unknown" ? 1 : item.judgment === "partial" ? 2 : 3;
    const concerns = summarized.filter(reason => reason.judgment !== "supported").sort((left, right) => priority(left) - priority(right) || importance(left) - importance(right));
    for (const [title, items, positive] of [["匹配依据", strengths, true], ["缺口与待核对", concerns, false]]) {
      const column = node("section", "flow-fit-reason-column"); column.append(node("h4", "", title));
      if (!items.length) column.append(node("p", "flow-muted", positive ? "尚无已保存的支持依据。" : conflicts.length ? "条件分支详情见下方。" : reasons.length ? "未记录缺口或未知项。" : "等待岗位分析。"));
      const list = node("ul", "flow-fit-list");
      const topicKey = item => `${topic(item)}:${item.judgment || "unknown"}:${!!item.citation_warning}`;
      const topics = [...new Map(items.map(item => [topicKey(item), item])).values()];
      for (const item of topics.slice(0, business ? 2 : 3)) {
        const row = node("li", `flow-fit-${item.judgment || "unknown"}`);
        row.append(node("span", "flow-fit-marker", item.citation_warning ? "引用待核验" : `${judgmentLabels[item.judgment] || "资料未知"}${typeof item.fit === "number" ? ` ${item.fit}` : ""}`));
        const content = node("span", "flow-fit-topic", topic(item));
        if (business) {
          const inferredJudgment = { supports: "supported", partial_support: "partial", contradicts: "gap", unresolved: "unknown" }[item.inference?.relation];
          const basis = inferredJudgment === item.judgment ? item.inference?.basis || item.explanation : item.explanation;
          content.append(node("span", "flow-fit-basis", basis || "资料尚未明确。"));
        }
        row.append(content); list.append(row);
      }
      column.append(list);
      const limit = business ? 2 : 3;
      if (topics.length > limit) column.append(node("p", "flow-fit-more", `另有 ${topics.length - limit} 类，见完整依据。`));
      columns.append(column);
    }
    panel.append(columns);
    if (conflicts.length) {
      const alert = node("div", "flow-fit-conflicts"); alert.append(node("strong", "", qualification.status === "conflict" ? `${conflicts.length} 项硬条件冲突 · 需先处理` : `${conflicts.length} 项条件分支不符 · 资格按原组关系汇总`));
      alert.append(node("span", "", `：${[...new Set(conflicts.map(topic))].join("、")}。展开完整依据核对。`)); panel.append(alert);
    }
    panel.append(node("p", "flow-fit-note", explanation.reasons?.some(reason => typeof reason.fit === "number") ? FIT_LEGEND : business ? `分数确定度 ${number(score?.coverage)}% 按固定组关系表示分数已确定程度，不表示每个原子事实都齐全；资料读取与简历覆盖均不改变背景分。` : "资料支持不等于资格已确认；待核对不代表不符合，可能需要核验引用或补充信息。"));
    const details = node("details", "flow-details flow-fit-details"); details.id = "flow-fit-details"; details.append(node("summary", "", "查看逐项 JD 分析、资格与完整依据"), explanationDetails(explanation, true)); panel.append(details);
    return panel;
  }
  function explanationDetails(explanation, primary = false) {
    const panel = node("section", "flow-stage flow-explanation");
    panel.append(node("p", "flow-muted", `政策版本：${explanation.policy_version || flow?.policy_version || "尚未载入"}`));
    if (explanation.fresh === false) panel.append(node("p", "flow-error", "历史结果 · 输入已变化，当前解释待重新分析；旧分数、资格和理由保留供核对。"));
    panel.append(node("h4", "", "匹配分"));
    const score = explanation.score;
    if (score) panel.append(node("p", "flow-badges", explanation.business_summary ? `${matchScoreText(score)} · 分数确定度 ${number(score.coverage)}%` : `已支持 ${number(score.lower)}/100 · 可能 ${number(score.lower)}–${number(score.upper)} · 证据覆盖 ${number(score.coverage)}%`));
    else panel.append(node("p", "flow-muted", "尚未分析匹配分。"));
    const fixedFramework = explanation.reasons?.some(reason => reason.scoring_framework);
    const fitScored = explanation.reasons?.some(reason => typeof reason.fit === "number");
    const legend = node("p", "flow-fit-note", fitScored ? FIT_LEGEND : fixedFramework ? "按固定业务组权重及原条件关系折算 100 分；支持计全分、缺口计 0；部分支持计半分，未知保留可能范围。" : "按权重折算 100 分：必需 ×3，加分 ×1；支持计全分、部分支持计半分、缺口计 0；未知仅扩大可能范围。"); if (primary) legend.id = "flow-fit-score-legend"; panel.append(legend);
    if (explanation.material_read_coverage) {
      const coverage = explanation.material_read_coverage;
      panel.append(node("p", "flow-muted", `资料读取：${coverage.complete ? "完成" : "未完成"} · 来源 ${coverage.sources_complete}/${coverage.sources_total} · 已读范围 ${coverage.ranges_complete}/${coverage.ranges_total}`));
      panel.append(node("p", "flow-muted", "简历覆盖仅按当前成稿实际使用的来源与背景要求来源的交集计算，不代表背景适配分。"));
    }
    if (explanation.factual_rechecks?.length && explanation.documentary_score) panel.append(node("p", "flow-muted", `原文档分析分 ${number(explanation.documentary_score.lower)}/100；当前分数已结合适用的确认事实重新核验，原分析保留。`));
    panel.append(node("h4", "", "资格结论"));
    const qualification = explanation.qualification || {};
    const qualificationLabels = { analysis_required: "需先分析岗位", needs_input: "资格待补充", conflict: "资格冲突", supported: "资格已确认支持", not_specified: "JD 未列出独立硬条件", unassessed: "资格尚未评估" };
    panel.append(node("p", ["needs_input", "conflict", "unassessed"].includes(qualification.status) ? "flow-error" : "flow-muted", qualificationLabels[qualification.status] || "资格尚未评估"));
    if (qualification.message) panel.append(node("p", "flow-muted", qualification.message));
    for (const condition of qualification.conditions || []) {
      panel.append(node("p", "flow-muted", [condition.text, { supported: "已确认支持", needs_input: "待提供事实", conflict: "已知冲突", unknown: "资料未知", unassessed: "尚未评估" }[condition.status] || condition.status, condition.explanation].filter(Boolean).join(" · ")));
      if (condition.resolution?.source) panel.append(node("p", "flow-source", `用户说明：${condition.resolution.source}`));
    }
    panel.append(node("h4", "", "当前进度"), node("p", "flow-muted", explanation.progress?.label || "尚未建立准备任务"));
    if (explanation.progress?.application_label) panel.append(node("p", "flow-muted", `申请记录：${explanation.progress.application_label}`));
    panel.append(node("h4", "", "具体理由"));
    if (!explanation.reasons?.length) panel.append(node("p", "flow-muted", "尚无已保存的岗位分析理由。"));
    for (const reason of explanation.reasons || []) {
      const row = node("div", "flow-requirement");
      row.append(node("h5", "", reason.text), node("p", "flow-badges", `${reason.importance === "required" ? "必需" : "加分"} · ${judgmentLabels[reason.judgment] || "资料未知"}${typeof reason.fit === "number" ? ` · 满足度 ${reason.fit}` : ""}`), node("p", "flow-muted", reason.explanation));
      if (reason.inference) {
        const inference = reason.inference;
        const type = { direct: "直接记录", deterministic: "确定性推导", semantic: "语义推断" }[inference.type] || inference.type;
        const relation = { supports: "支持", partial_support: "部分支持", contradicts: "明确不符", unresolved: "尚不明确" }[inference.relation] || inference.relation;
        row.append(node("p", "flow-source", `判断类型：${type} · 关系：${relation}`));
        if (inference.basis) row.append(node("p", "flow-muted", `短依据：${inference.basis}`));
        if (inference.expression_scope) row.append(node("p", "flow-muted", `表达范围：${inference.expression_scope}`));
        if (inference.calculation) row.append(node("p", "flow-source", `计算记录：${JSON.stringify(inference.calculation)}`));
        if (inference.facts?.length) appendLines(row, inference.facts, "flow-source");
      }
      if (reason.library?.references?.length) row.append(node("p", "flow-source", "依据：信息库中已确认的资料。"));
      for (const source of reason.sources || []) {
        row.append(node("p", "flow-source", sourceDescription(source)));
        if (source.quote && !source.confirmed_information) row.append(node("blockquote", "flow-text", source.quote));
      }
      panel.append(row);
    }
    panel.append(node("h4", "", "偏好与未知项"));
    const preferences = explanation.preferences || {};
    const preferenceLabels = { personal_priority: "个人偏好", target_company: "目标公司", compensation_priority: "薪酬偏好" };
    const preferenceValues = { high: "优先", normal: "一般", low: "较低", target: "目标公司", exceptional: "高薪例外" };
    for (const [key, label] of Object.entries(preferenceLabels)) panel.append(node("p", "flow-muted", `${label}：${preferenceValues[preferences[key]] || "未知"}`));
    const unknown = preferences.unknown || [];
    const unknownLabels = { ...preferenceLabels, company: "目标公司", salary: "薪酬偏好" };
    panel.append(node("p", "flow-muted", `偏好未知：${unknown.length ? unknown.map(item => unknownLabels[item] || item).join("、") : "无已记录未知项"}`));
    if (explanation.limitations?.length) {
      const limits = node("div", "flow-muted"); limits.append(node("h5", "", "解释范围与限制")); appendLines(limits, explanation.limitations); panel.append(limits);
    }
    return panel;
  }
  function renderAnalysis(analysis) {
    const panel = node("section", "flow-stage"); panel.id = "flow-analysis"; panel.append(node("h3", "", "岗位匹配 · 来源证据"));
    const score = analysis.score || {};
    const scores = node("div", "flow-score");
    if (analysis.job_brief && analysis.material_packet) scores.append(node("strong", "", matchScoreText(score)), node("span", "", `分数确定度 ${number(score.coverage)}%`));
    else scores.append(node("strong", "", `已支持 ${number(score.lower)}/100`), node("span", "", `可能 ${number(score.lower)}–${number(score.upper)}`), node("span", "", `证据覆盖 ${number(score.coverage)}%`));
    const groupTotal = analysis.job_brief?.groups?.reduce((sum, group) => sum + group.weight, 0) || 1;
    panel.append(scores, node("p", "flow-muted", analysis.job_brief ? "按固定岗位说明的业务组权重及原条件关系计算；待明确条件保留区间，重复资料不加分。" : "必需项 3 · 加分项 1 · 部分支持 0.5。未知不代表能力不足；重复资料不加分。"));
    const requirements = node("div", "flow-requirements");
    for (const requirement of analysis.requirements || []) {
      const row = node("article", "flow-requirement");
      const group = requirement.scoring_framework?.group;
      const weightLabel = group ? `${group.label} · 组权重 ${number(100 * group.weight / groupTotal)}%` : requirement.importance === "required" ? "必需 · 权重 3" : "加分 · 权重 1";
      row.append(node("h4", "", requirement.text), node("p", "flow-badges", `${weightLabel} · ${judgmentLabels[requirement.judgment] || "资料未知"}${requirement.hard_condition ? " · 硬条件" : ""}`), node("p", "flow-muted", requirement.explanation));
      for (const source of requirement.sources || []) {
        row.append(node("p", "flow-source", sourceDescription(source)));
        if (source.quote && !source.confirmed_information) row.append(node("blockquote", "flow-text", source.quote));
      }
      requirements.append(row);
    }
    panel.append(requirements);
    const eligibility = flow?.eligibility;
    const eligibilityLabels = { supported: "硬条件已确认支持", not_specified: "JD 未列出独立硬条件", needs_input: "资格信息尚不明确，继续准备；表单缺少必要事实时再补充", conflict: "存在硬条件冲突 · 停止自动填写" };
    panel.append(node("h4", "", eligibilityLabels[eligibility?.status] || "资格状态待确认"));
    for (const condition of eligibility?.conditions || []) {
      panel.append(node("p", "flow-muted", `${condition.text} · ${{ supported: "已确认支持", needs_input: "资料尚不明确", conflict: "已知冲突" }[condition.status] || "待确认"}`));
      if (condition.resolution) panel.append(node("p", "flow-source", `用户说明：${condition.resolution.source}。此说明独立于匹配分。`));
      if (!pipeline?.enabled && (["unknown", "partial"].includes(condition.judgment) || (flow?.mode === "preparation" && condition.judgment === "supported")) && !flow.active_task.worker_ref) {
        const task = flow.active_task;
        const draftKey = `${task.id}/${analysis.id}/${condition.requirement_index}`;
        const saved = conditionDrafts.get(draftKey);
        const form = node("form", "flow-condition");
        const source = node("textarea"); source.required = true; source.maxLength = 1000; source.rows = 3; source.setAttribute("aria-label", `${condition.text} · 事实说明`);
        source.value = saved?.source ?? condition.resolution?.source ?? "";
        const eligible = node("select"); eligible.required = true; eligible.setAttribute("aria-label", `${condition.text} · 是否符合`);
        for (const [value, text] of [["", "请选择是否符合"], ["true", "符合此硬条件"], ["false", "不符合此硬条件"]]) { const option = node("option", "", text); option.value = value; eligible.append(option); }
        eligible.value = saved?.eligible ?? (condition.resolution ? String(condition.resolution.eligible) : "");
        const remember = () => conditionDrafts.set(draftKey, { source: source.value, eligible: eligible.value });
        source.addEventListener("input", remember); eligible.addEventListener("change", remember);
        const sourceLabel = node("label", "", "事实说明"); sourceLabel.append(source);
        const eligibleLabel = node("label", "", "是否符合"); eligibleLabel.append(eligible);
        const save = button("保存硬条件说明", () => {}, null, true); save.type = "submit";
        form.append(sourceLabel, eligibleLabel, save);
        form.addEventListener("submit", event => {
          event.preventDefault(); remember();
          if (!source.value.trim() || !["true", "false"].includes(eligible.value)) return;
          mutate(async () => {
            await api("/api/flow/clarify-condition", { method: "POST", body: JSON.stringify({ task_id: task.id, task_revision: task.revision, requirement_index: condition.requirement_index, eligible: eligible.value === "true", source: source.value.trim() }) });
            conditionDrafts.delete(draftKey);
          });
        }); panel.append(form);
      }
    }
    const limitations = node("details", "flow-details"); limitations.append(node("summary", "", "分析范围与限制")); appendLines(limitations, analysis.limitations); panel.append(limitations);
    const historical = analysis.historical_reference;
    const reference = node("details", "flow-details"); reference.append(node("summary", "", "历史参考"));
    if (historical?.status === "ready") {
      reference.append(node("p", "flow-muted", `历史参考区间 ${number(historical.reference_range?.lower)}–${number(historical.reference_range?.upper)}，保留原始分值。`));
      for (const item of historical.comparisons || []) reference.append(node("p", "flow-muted", `${item.company} · ${item.role_title}：${number(item.score?.lower)}–${number(item.score?.upper)}；${{ above: "当前区间高于此参考", below: "当前区间低于此参考", overlaps: "区间重叠" }[item.position] || "位置未知"}`));
    } else reference.append(node("p", "flow-muted", "历史参考尚不可用。当前分数不代表面试概率。"));
    appendLines(reference, historical?.limitations); panel.append(reference);
    const details = node("details", "flow-details"); details.id = "flow-analysis-details"; details.append(node("summary", "", "核对分析来源与补充资格事实"), panel); current.append(details);
  }
  function sourceReview(resume, expanded = false) {
    const sources = node("details", "flow-details"); sources.open = expanded; sources.append(node("summary", "", "采用来源、未采用来源与改写说明"));
    for (const item of resume.items || []) {
      sources.append(node("h4", "", "已采用 · " + (item.title || item.source_name || item.source_id)), node("p", "flow-source", sourceDescription(item)));
      sources.append(node("p", "flow-muted", "原文"), node("pre", "flow-text", item.source_text || item.text), node("p", "flow-muted", "简历表述"), node("pre", "flow-text", item.text));
      if (item.review_findings) {
        sources.append(node("h5", "", "逐来源机械提示 · 待人工核验"), node("p", "flow-muted", item.review_findings.message));
        for (const check of item.review_findings.checks || []) {
          const category = { numbers: "数字", dates: "日期", technical_terms: "技术词" }[check.category] || check.category;
          sources.append(node("p", "flow-muted", `${category} · 新增：${check.added?.join("、") || "无"} · 遗漏：${check.omitted?.join("、") || "无"}`));
        }
      }
    }
    for (const item of resume.unused_sources || []) sources.append(node("p", "flow-source", `分析已选择，简历未采用：${sourceDescription(item)}`));
    for (const item of resume.not_selected_sources || []) sources.append(node("p", "flow-source", `${item.reason === "ineligible" ? "归属或使用范围不允许写入个人简历" : "分析未选择"}：${sourceDescription(item)}`));
    appendLines(sources, resume.limitations); return sources;
  }
  function prismCurrent(task) {
    return !task.prism || flow.prism?.status === "current";
  }
  function draftReviewed(draft, task) {
    return task.draft_review?.status === "reviewed" && task.draft_review.draft_id === draft.id && task.draft_review.draft_sha256 === draft.draft_sha256 && (!task.prism || prismCurrent(task) && task.draft_review.prism_source_revision === task.prism.source_revision);
  }
  function technicalExportAuthorized(draft, task) {
    const authorization = task.export_authorization;
    return authorization?.status === "authorized" && authorization.scope === "technical_export" && authorization.draft_id === draft.id && authorization.draft_sha256 === draft.draft_sha256 && prismCurrent(task) && authorization.prism_source_revision === task.prism?.source_revision;
  }
  function renderPrism(task, stale, invalid) {
    const panel = node("section", "flow-stage"); panel.id = "flow-prism";
    panel.append(node("h4", "", "LaTeX 编辑与 PDF 预览"), node("p", "flow-muted", task.origin === "existing_latex" ? "在 Prism 中编辑完整简历。保存后从已有 JD 接入新版本，再授权技术导出；历史任务继续对应原 LaTeX 和 PDF。" : "在 Prism 中编辑完整简历。保存并编译后返回此处，读取当前版本并审阅；导出采用同一份 LaTeX。"));
    const binding = task.prism;
    const blocked = stale || invalid || !!task.worker_ref || ["cancelled", "needs_recheck"].includes(task.status) || stagesUnresolved(task);
    if (binding) {
      const currentSource = prismCurrent(task);
      panel.append(node("p", currentSource ? "flow-muted" : "flow-error", currentSource ? "当前 LaTeX 版本可审阅" : flow.prism?.status === "changed" ? task.origin === "existing_latex" ? "LaTeX 源已变化，请从已有 JD 接入新版本；此任务保留原版本和 PDF。" : "LaTeX 源已变化，请读取当前版本后重新审阅。" : flow.prism?.message || "当前 LaTeX 源暂不能核验。"));
      panel.append(node("p", "flow-source", `${binding.project_root} · ${binding.main}`));
      const actions = node("div", "flow-actions");
      const open = button("连接 Prism 编辑器", () => mutate(() => api("/api/flow/open-prism", { method: "POST", body: JSON.stringify({ task_id: task.id, task_revision: task.revision }) })), "flow-open-prism", true);
      const refresh = button("读取编辑后的 LaTeX", () => mutate(() => api("/api/flow/refresh-prism", { method: "POST", body: JSON.stringify({ task_id: task.id, task_revision: task.revision }) })), "flow-refresh-prism", true);
      open.dataset.blocked = refresh.dataset.blocked = String(blocked);
      actions.append(open);
      if (task.origin !== "existing_latex") actions.append(refresh);
      if (/^http:\/\/(?:127\.0\.0\.1|localhost|\[::1\]):\d+\/$/.test(binding.editor_url || "")) {
        const link = node("a", "button button-secondary", "打开 Prism 编辑与预览 ↗"); link.id = "flow-prism-editor-link"; link.href = binding.editor_url; link.target = "_blank"; link.rel = "noopener noreferrer"; actions.append(link);
      }
      panel.append(actions, node("p", "flow-muted", task.origin === "existing_latex" ? "保存修改后，从已有 JD 接入新版本。此任务的来源与 PDF 历史保留；打开编辑器不表示事实已审核。" : "读取当前版本会保留历史记录，并清除当前源的旧审阅和 PDF 绑定；打开编辑器本身不表示已审阅。"));
      const version = node("details", "flow-details"); version.append(node("summary", "", "LaTeX 源版本"), node("p", "flow-muted flow-hash", binding.source_revision)); panel.append(version);
    }
    if (task.origin === "existing_latex") return panel;
    const form = node("form", "flow-condition");
    const saved = prismDrafts.get(task.id) || { project_root: binding?.project_root || "", main: binding?.main || "main.tex" };
    const directory = node("input"); directory.required = true; directory.value = saved.project_root; directory.setAttribute("aria-label", "简历 LaTeX 项目目录");
    const main = node("input"); main.required = true; main.value = saved.main; main.setAttribute("aria-label", "简历 LaTeX 主文件");
    for (const input of [directory, main]) { input.dataset.flowWrite = "true"; input.dataset.blocked = String(blocked); }
    const remember = () => prismDrafts.set(task.id, { project_root: directory.value, main: main.value });
    directory.addEventListener("input", remember); main.addEventListener("input", remember);
    const directoryLabel = node("label", "", "简历 LaTeX 项目目录"); directoryLabel.append(directory);
    const mainLabel = node("label", "", "简历 LaTeX 主文件"); mainLabel.append(main);
    const bind = button(binding ? "更换 LaTeX 项目" : "使用此 LaTeX 项目", () => {}, "flow-bind-prism", true); bind.type = "submit"; bind.dataset.blocked = String(blocked);
    form.append(directoryLabel, mainLabel, bind);
    form.addEventListener("submit", event => {
      event.preventDefault(); remember();
      if (!directory.value.trim() || !main.value.trim()) return;
      mutate(async () => {
        await api("/api/flow/bind-prism", { method: "POST", body: JSON.stringify({ task_id: task.id, task_revision: task.revision, project_root: directory.value.trim(), main: main.value.trim() }) });
        prismDrafts.delete(task.id);
      });
    });
    panel.append(form); return panel;
  }
  function renderLatexBase(task) {
    const panel = node("section", "flow-stage"); panel.id = "flow-latex-base";
    panel.append(node("h3", "", "完整 LaTeX 简历底稿"), node("p", "flow-muted", "选择已有完整简历。绑定仅读取当前版本；生成会另存岗位版本，并保留底稿。事实审核完成后自动核验并保存 PDF。"));
    const binding = task.latex_base;
    if (binding) panel.append(node("p", "flow-source", `${binding.project_root} · ${binding.main}`), node("p", "flow-muted flow-hash", `底稿版本 ${binding.source_revision}`));
    const saved = latexBaseDrafts.get(task.id) || binding || { project_root: "", main: "main.tex" };
    const form = node("form", "flow-condition");
    const directory = node("input"); directory.required = true; directory.value = saved.project_root; directory.setAttribute("aria-label", "完整简历底稿目录");
    const main = node("input"); main.required = true; main.value = saved.main; main.setAttribute("aria-label", "完整简历底稿主文件");
    const blocked = !!task.worker_ref || ["cancelled", "needs_recheck"].includes(task.status) || stagesUnresolved(task);
    for (const input of [directory, main]) { input.dataset.flowWrite = "true"; input.dataset.blocked = String(blocked); }
    const remember = () => latexBaseDrafts.set(task.id, { project_root: directory.value, main: main.value });
    directory.addEventListener("input", remember); main.addEventListener("input", remember);
    const directoryLabel = node("label", "", "完整简历底稿目录"); directoryLabel.append(directory);
    const mainLabel = node("label", "", "完整简历底稿主文件"); mainLabel.append(main);
    const bind = button(binding ? "重新绑定当前底稿" : "绑定完整 LaTeX 底稿", () => {}, "flow-bind-latex-base", true); bind.type = "submit"; bind.dataset.blocked = String(blocked);
    form.append(directoryLabel, mainLabel, bind);
    form.addEventListener("submit", event => {
      event.preventDefault(); remember();
      if (!directory.value.trim() || !main.value.trim()) return;
      mutate(async () => {
        await api("/api/flow/bind-latex-base", { method: "POST", body: JSON.stringify({ task_id: task.id, task_revision: task.revision, project_root: directory.value.trim(), main: main.value.trim() }) });
        latexBaseDrafts.delete(task.id);
      });
    });
    panel.append(form); return panel;
  }
  function groupAction(task, action, extra = {}) {
    return mutate(() => api(`/api/flow/${action}`, { method: "POST", body: JSON.stringify({task_id: task.id, task_revision: task.revision, ...extra}) }));
  }
  function groupEditor(draft, task, group, blocked) {
    const key = `${task.id}/${draft.id}/${group?.id || "new"}`;
    const saved = groupEditDrafts.get(key) || {title: group?.title || "", latex: group?.rewritten || "", source_ids: (group?.sources || []).map(row => row.source_id).join("\n")};
    const details = node("details", "flow-details"); details.append(node("summary", "", group ? "修改表述或来源／恢复此组" : "新增有来源的经历组"));
    const title = node("input"); title.value = saved.title; title.setAttribute("aria-label", "经历组名称");
    const latex = node("textarea"); latex.value = saved.latex; latex.rows = 7; latex.setAttribute("aria-label", "经历组 LaTeX 表述");
    const sourceIds = new Set(saved.source_ids.split(/\n/).filter(Boolean));
    const sourceChoices = node("fieldset", "flow-details"); sourceChoices.append(node("legend", "", "选择已存在的事实来源与责任归属"));
    const available = draft.available_review_sources || group?.sources || [];
    const remember = () => groupEditDrafts.set(key,{title:title.value,latex:latex.value,source_ids:[...sourceIds].join("\n")});
    for (const source of available) {
      const label=node("label","flow-check");
      const check=node("input");check.type="checkbox";check.checked=sourceIds.has(source.source_id);check.dataset.flowWrite="true";check.dataset.blocked=String(blocked || (source.resume_eligible===false && !check.checked));
      check.addEventListener("change",()=>{if(check.checked)sourceIds.add(source.source_id);else sourceIds.delete(source.source_id);check.dataset.blocked=String(blocked || (source.resume_eligible===false && !check.checked));remember();lock();});
      const attribution=Array.isArray(source.attribution) ? source.attribution.join("；") : source.attribution || "责任待核对";
      label.append(check,node("span","",`${source.title || source.source_name || "事实来源"} · ${source.locator || ""} · ${attribution}`));
      const evidence=node("details","flow-details");evidence.append(node("summary","","查看来源原文与标识"),node("pre","flow-text",source.text || source.original || ""),node("p","flow-muted flow-hash",source.source_id));
      sourceChoices.append(label,evidence);
    }
    if (!available.length) sourceChoices.append(node("p","flow-muted","当前没有可读取的来源。请保留原版本并核验资料。"));
    for (const input of [title,latex]) { input.dataset.flowWrite="true"; input.dataset.blocked=String(blocked); input.addEventListener("input",remember); }
    details.append(node("label", "", "名称"),title,node("label", "", "完整 LaTeX 表述"),latex,sourceChoices);
    const submit = disposition => {
      remember();
      return groupAction(task,"edit-review-group",{payload:{...(group ? {group_id:group.id} : {}),title:title.value,latex:latex.value,source_ids:[...sourceIds],disposition}});
    };
    const include=button(group?.disposition === "include" ? "保存修改并重新审核" : "采用此组并重新审核",()=>submit("include"),null,true); include.dataset.blocked=String(blocked); details.append(include);
    if (group?.disposition === "include") { const omit=button("按本岗相关性暂不采用",()=>submit("omit"),null,true);omit.dataset.blocked=String(blocked);details.append(omit); }
    details.append(node("p","flow-muted","保存后建立独立版本，保留原文和历史。新增、恢复或来源变化的组需要重新审核；待核对陈述须先有可核验来源和责任归属。"));
    return details;
  }
  function groupedPrism(draft,task,blocked) {
    const panel=node("section","flow-stage");panel.id="flow-grouped-review";
    panel.append(node("h4","","Prism 编辑与分组事实审核"));
    const groupState=flow.group_review || {};
    const unknown=["running","needs_recheck"].includes(task.group_read?.status) || !!groupState.pending_attempt_id;
    if (!draft.group_session) {
      const begin=button("建立独立分组审阅版本",()=>groupAction(task,"begin-group-review"),"flow-begin-group-review");begin.dataset.blocked=String(blocked || unknown);panel.append(begin);return panel;
    }
    const open=button("连接 Prism 编辑器",()=>groupAction(task,"open-prism"),"flow-open-prism",true);open.dataset.blocked=String(blocked || unknown);panel.append(open);
    if (/^http:\/\/(?:127\.0\.0\.1|localhost|\[::1\]):\d+\/$/.test(task.prism?.editor_url || "")) {const link=node("a","text-link","打开 Prism 编辑与预览 ↗");link.href=task.prism.editor_url;link.target="_blank";link.rel="noopener noreferrer";panel.append(link);}
    const capture=button(unknown ? "核验已有预览回执" : "读取并编译当前 LaTeX 预览",()=>groupAction(task,unknown ? "recheck-group-review" : "capture-group-review",unknown ? {} : {expected_source_revision:groupState.live_source_revision}),"flow-capture-group-review",true);
    capture.dataset.blocked=String(blocked || task.group_read?.status==="running" || (!unknown && !groupState.live_source_revision));panel.append(capture);
    if (unknown) panel.append(node("p","flow-error","上次读取结果尚未核验。先核验已有回执，不能重复编译、重新生成或替换任务。"));
    if (groupState.live_source_revision && groupState.live_source_revision !== draft.source_checkpoint?.source_revision) panel.append(node("p","flow-error","检测到 Prism 已保存新改动。下方保留上次读取版本，请读取当前源和技术预览后重审受影响的经历组。"));
    if (task.group_mapping?.status==="mapping_required") panel.append(node("p","flow-error",task.group_mapping.message || "当前源不能对应到经历组。请在 Prism 修复分组边界后重新读取；事实确认保持暂停。"));
    const preview=task.group_mapping?.status==="mapping_required" ? task.group_mapping.preview : draft.group_preview;
    if (preview) {
      const url=`/api/flow/group-previews/${draft.id}/${preview.id}/pdf`;
      const link=node("a","text-link","打开当前技术预览 PDF ↗");link.href=url;link.target="_blank";link.rel="noopener noreferrer";panel.append(link);
      const frame=node("iframe");frame.title="完整 LaTeX 同源技术预览";frame.src=url;frame.style.width="100%";frame.style.height="620px";panel.append(frame);
      if (task.group_mapping?.status==="mapping_required" && preview.latex_source) panel.append(node("pre","flow-text",preview.latex_source));
    }
    panel.append(node("p","flow-muted","技术预览只核对同一份源。教育经历按固定记录复用；其余岗位表述请按来源核对。新 PDF 将自动核验并保存，可随时预览，真实申请继续暂停。"));
    return panel;
  }
  function renderAutomaticSource(draft, task, panel) {
    panel.querySelector("h3").textContent = "当前岗位简历";
    if (draft.generation_contract === "fixed-writing/v1" || draft.material_version_contract === "local-material/v1" || task.prism_edit) {
      panel.append(node("p", "flow-muted", "人工编辑使用上方 Prism 入口。返回后只做快速文字校对，不重新进行内容终审；源文、修改和最终 PDF 分别保留版本。"));
      const source = node("details", "flow-details"); source.append(node("summary", "", "查看已保存完整源文"), node("pre", "flow-text", draft.latex_source || "当前源文暂不可读取。")); panel.append(source);
      return;
    }
    const update = task.material_update;
    const editable = update?.editable_draft || draft;
    const pending = update && !["staged", "complete"].includes(update.status);
    const running = stagesUnresolved(task);
    const blocked = task.status === "cancelled" || running || pending || !!task.worker_ref && flow.worker?.control !== "paused";
    panel.append(node("p", "flow-muted", "可修改完整简历源文。保存后点击一次“继续当前岗位”，系统会检查材料并继续剩余步骤。旧版本保留，最终 Submit 由你操作。"));
    if (update) {
      const labels = { staged: "简历更新已保存，继续当前岗位时将检查并采用", preparing: "正在准备更新后的简历", awaiting_page: "正在核对原页面与原附件", page_verified: "原页面已核对，正在更新材料", committing: "正在保存当前材料绑定", bound: "正在原页面更新简历附件", complete: "简历附件已更新", needs_recheck: "材料更新结果待核验，已停止", failed: "简历更新未完成" };
      panel.append(node("p", ["needs_recheck", "failed"].includes(update.status) ? "flow-error" : "flow-muted", labels[update.status] || "简历更新进度已保存"));
    }
    if (!editable.group_session || task.worker_ref && (update?.status !== "staged" || !update?.editable_draft)) {
      const open = button("编辑当前简历", () => mutate(() => api("/api/flow/begin-automatic-edit", { method: "POST", body: JSON.stringify({ task_id: task.id, task_revision: task.revision }) })), "flow-edit-automatic-source", true);
      open.dataset.flowRequiresPaused = "true";
      open.dataset.blocked = String(blocked || pending);
      panel.append(open);
      const pendingSource = automaticSourceDrafts.get(task.id);
      const original = node("details", "flow-details"); original.append(node("summary", "", pendingSource ? "待保存的简历源文已保留" : "查看完整简历源文"), node("pre", "flow-text", pendingSource?.value ?? editable.latex_source ?? "当前源文尚不能读取。")); panel.append(original);
      return;
    }
    const version = editable.source_checkpoint?.source_revision;
    let saved = automaticSourceDrafts.get(task.id);
    if (saved && saved.version !== version && saved.value === editable.latex_source) {
      automaticSourceDrafts.delete(task.id);
      saved = null;
    }
    const staleEdit = saved && saved.version !== version;
    const details = node("details", "flow-details"); details.open = automaticSourceEditors.get(task.id) ?? true; details.id = "flow-automatic-source-editor";
    details.addEventListener("toggle", () => { if (details.isConnected) automaticSourceEditors.set(task.id, details.open); });
    details.append(node("summary", "", "修改完整简历源文"));
    const source = node("textarea"); source.id = "flow-automatic-source"; source.rows = 18; source.setAttribute("aria-label", "完整简历 LaTeX 源文");
    source.value = saved?.value ?? editable.latex_source ?? ""; source.dataset.flowWrite = "true"; source.dataset.blocked = String(blocked);
    source.dataset.flowRequiresPaused = "true";
    source.addEventListener("input", () => {
      if (!staleEdit && source.value === editable.latex_source) automaticSourceDrafts.delete(task.id);
      else automaticSourceDrafts.set(task.id, { version: saved?.version || version, value: source.value });
      lock();
    });
    details.append(source);
    if (staleEdit) {
      details.append(node("p", "flow-error", "源版本已变化。正在编辑的内容已保留，请比较当前已保存版本并合并需要的修改，再继续保存。"));
      const latest = node("details", "flow-details"); latest.append(node("summary", "", "查看当前已保存源文"), node("pre", "flow-text", editable.latex_source || "")); details.append(latest);
      const rebase = button("保留编辑并采用当前源版本", () => {
        automaticSourceDrafts.set(task.id, { version, value: source.value });
        renderedTask = ""; render();
      }, "flow-rebase-automatic-source", true);
      rebase.dataset.flowRequiresPaused = "true"; rebase.dataset.blocked = String(blocked || pending || !version); details.append(rebase);
    }
    const save = button("保存简历修改", () => mutate(async () => {
      const edit = automaticSourceDrafts.get(task.id) || { version, value: source.value };
      await api("/api/flow/save-automatic-source", { method: "POST", body: JSON.stringify({ task_id: task.id, task_revision: task.revision, expected_source_revision: edit.version, latex_source: edit.value }) });
      automaticSourceDrafts.delete(task.id);
      message("简历修改已保存。点击继续当前岗位后续填，最终 Submit 由你操作。");
    }), "flow-save-automatic-source", true);
    save.dataset.flowRequiresPaused = "true";
    save.dataset.blocked = String(blocked || staleEdit || !version || pending && !update?.editable_draft);
    details.append(save); panel.append(details);
  }
  function renderFullLatex(draft, task, panel) {
    if (task.automatic_materials) { renderAutomaticSource(draft, task, panel); return; }
    panel.querySelector("h3").textContent = task.factual_review === "groups_reviewed" ? "完整 LaTeX 岗位版本 · 经历组已审核" : "完整 LaTeX 岗位版本 · 事实审核待完成";
    const blocked = flow.active_explanation?.fresh === false || flow.draft_integrity?.status === "invalid" || task.status === "cancelled" || !!task.worker_ref || stagesUnresolved(task);
    const unknown = ["running","needs_recheck"].includes(task.group_read?.status) || !!flow.group_review?.pending_attempt_id;
    panel.append(groupedPrism(draft,task,blocked));
    const unresolvedEducation = draft.presentation_policy === "resume-presentation/v1" && ["review_groups", "omitted_groups", "verification_queue"].some(key => (draft[key] || []).some(group => group.content_policy === "education_verification_required" || ((group.sources || []).some(source => source.source_kind === "education") && (key !== "review_groups" || group.content_policy !== "fixed_education"))));
    if (unresolvedEducation) panel.append(node("p", "flow-error", "教育经历存在来源或状态冲突，请先核对已有记录。其余组可继续审阅；当前版本不能导出 PDF。"));
    panel.append(node("p", "flow-muted", task.factual_review === "groups_reviewed" ? "此版本经历组已审核。新 PDF 将自动核验并保存，可随时预览，真实申请继续暂停。" : "此版本按本岗 JD 单独生成。教育经历按固定记录复用；技能与工作表述按本岗 JD 修订。下方列出原文、改写、来源与责任归属，供核对。新 PDF 将自动核验并保存，可随时预览，真实申请继续暂停。"));
    if (flow.active_explanation?.fresh === false) panel.append(node("p", "flow-error", "输入或底稿已变化。此处保留原版本供核对，不能沿用其审核或材料绑定。"));
    panel.append(node("p", "flow-muted flow-hash", `草稿版本 ${draft.id} · SHA256 ${draft.draft_sha256}`));
    const source = node("details", "flow-details"); source.id = "flow-full-latex-source";
    source.append(node("summary", "", "完整 LaTeX 源文"), node("pre", "flow-text", draft.latex_source || "当前源文不能读取，请核验保存记录。")); panel.append(source);
    if (draft.source_checkpoint) panel.append(node("p", "flow-source", `${draft.source_checkpoint.project_root} · ${draft.source_checkpoint.main}`));
    for (const [key, heading] of [["review_groups", "已采用经历／项目 · 待分组审核"], ["omitted_groups", "按 JD 未采用 · 可恢复原记录"], ["verification_queue", "待核对 · 暂不进入正文"]]) {
      const groups = node("section", "flow-stage"); groups.id = `flow-${key.replaceAll("_", "-")}`; groups.append(node("h4", "", heading));
      for (const group of draft[key] || []) {
        const fixedEducation = draft.presentation_policy === "resume-presentation/v1" && group.content_policy === "fixed_education";
        const detail = node("details", "flow-details"); detail.append(node("summary", "", group.title || group.id));
        detail.append(node("h5", "", "原文"), node("pre", "flow-text", group.original || ""), node("h5", "", "岗位版本表述"), node("pre", "flow-text", group.rewritten || "未纳入正文"));
        for (const item of group.sources || []) detail.append(node("pre", "flow-text", JSON.stringify(item, null, 2)));
        detail.append(node("p", "flow-source", `责任归属：${(group.attribution || []).join("；") || "待核对"}`));
        if (group.reason) detail.append(node("p", "flow-muted", `理由：${group.reason}`));
        if (fixedEducation) detail.append(node("p", "flow-muted", "教育经历已按固定记录复用，无需重复事实确认。PDF 会自动核验并保存。"));
        if (draft.group_session && key === "review_groups" && !fixedEducation) {
          const receipt=(task.group_reviews || []).find(row=>row.group_id===group.id && row.draft_id===draft.id && row.draft_sha256===draft.draft_sha256 && row.review_fingerprint===group.review_fingerprint);
          detail.append(node("p","flow-muted",receipt ? (receipt.inherited_from ? "已核验内容、来源与责任未变，沿用此组确认记录。" : "此组当前版本已确认。") : "此组当前版本待你确认。"));
          const confirm=button("确认此经历组的事实与责任归属",()=>groupAction(task,"review-group",{draft_id:draft.id,draft_sha256:draft.draft_sha256,group_id:group.id,review_fingerprint:group.review_fingerprint}),null,true);confirm.dataset.groupReview=group.id;
          confirm.dataset.blocked=String(blocked || unknown || !!receipt || task.group_mapping?.status!=="ready" || !draft.group_preview || flow.group_review?.live_source_revision!==draft.source_checkpoint?.source_revision);detail.append(confirm);
        }
        if (draft.group_session && !fixedEducation) detail.append(groupEditor(draft,task,group,blocked || unknown || task.group_mapping?.status==="mapping_required"));
        groups.append(detail);
      }
      if (!(draft[key] || []).length) groups.append(node("p", "flow-muted", "当前版本没有此类条目。"));
      panel.append(groups);
    }
    if (draft.group_session) panel.append(groupEditor(draft,task,null,blocked || unknown || task.group_mapping?.status==="mapping_required"));
    const regenerate = button("重新生成完整 LaTeX 岗位版本", async () => {
      if (await confirmAction("重新生成会保留旧版本。新版本仍需分组事实审核，再自动核验并保存新 PDF。", "重新生成岗位版本")) start("resume", true);
    }, "flow-regenerate-resume", true);
    const stale = flow.active_explanation?.fresh === false || flow.draft_integrity?.status === "invalid";
    const qualificationBlocked = flow.active_explanation && !["supported", "not_specified"].includes(flow.active_explanation.qualification?.status);
    regenerate.dataset.blocked = String(unknown || stale || qualificationBlocked || task.status === "cancelled" || !!task.worker_ref || batchStageBlocked(task) || flow.resume_language?.status === "needs_input" || flow.capabilities?.resume === false || stagesUnresolved(task));
    panel.append(regenerate);
    if (!draft.group_session) return;
    const exportStatus = task.stages?.export?.status || "pending";
    const retry = exportStatus === "failed" || (exportStatus === "complete" && flow.pdf_integrity?.status === "invalid");
    const exportPdf = button(retry ? "重新绑定完整源与新 PDF" : "绑定完整源与新 PDF", () => mutate(() => api("/api/flow/export-pdf", { method: "POST", body: JSON.stringify({ task_id: task.id, task_revision: task.revision, draft_id: draft.id, draft_sha256: draft.draft_sha256, ...(retry ? { retry: true } : {}) }) })), "flow-export-pdf");
    exportPdf.dataset.blocked = String(blocked || unknown || stale || batchStageBlocked(task) || task.factual_review !== "groups_reviewed" || task.group_mapping?.status !== "ready" || flow.group_review?.live_source_revision !== draft.source_checkpoint?.source_revision || !draft.group_preview || (exportStatus !== "pending" && !retry));
    panel.append(exportPdf, node("p", "flow-muted", "分组审核完成后，绑定已核验同源预览的完整源与 PDF。PDF 自动核验并保存后可直接预览；真实申请继续暂停。"));
    if (exportStatus === "needs_recheck") {
      const recheck = button("核验已绑定 PDF 回执", () => mutate(() => api("/api/flow/recheck-export", { method: "POST", body: JSON.stringify({ task_id: task.id, task_revision: task.revision }) })), "flow-recheck-export", true);
      recheck.dataset.blocked = String(unknown || stagesRunning(task));
      panel.append(recheck);
    }
  }
  function renderDraft(draft, task) {
    const panel = node("section", "flow-stage"); panel.id = "flow-draft"; panel.append(node("h3", "", "岗位专用简历草稿"));
    const stale = flow.preparation?.checks?.draft?.status === "stale" || flow.active_explanation?.fresh === false;
    const invalid = flow.draft_integrity?.status === "invalid";
    const reviewedDraft = task.origin === "existing_latex" ? technicalExportAuthorized(draft, task) : draftReviewed(draft, task);
    if (draft.origin === "generated_latex") { renderFullLatex(draft, task, panel); current.append(panel); return; }
    if (task.origin === "existing_latex") {
      panel.querySelector("h3").textContent = retainedMaterialAccepted(task) ? "已有 LaTeX 岗位材料 · 此版本已接受" : "已有 LaTeX 岗位材料 · 事实审核待完成";
      panel.append(node("p", "flow-muted", "采用已保存 LaTeX，不生成或改写内容。技术导出授权不记录事实审阅结论。"));
      panel.append(node("p", "flow-muted flow-hash", `草稿版本 ${draft.id} · SHA256 ${draft.draft_sha256}`));
      panel.append(renderPrism(task, stale, invalid));
      const authorize = button(reviewedDraft ? "此版本已授权技术导出" : "仅授权此版本的技术导出", () => mutate(() => api("/api/flow/authorize-latex-export", { method: "POST", body: JSON.stringify({ task_id: task.id, task_revision: task.revision, draft_id: draft.id, draft_sha256: draft.draft_sha256 }) })), "flow-authorize-latex-export");
      authorize.dataset.blocked = String(stale || invalid || !prismCurrent(task) || reviewedDraft || task.status !== "draft_ready");
      panel.append(authorize); current.append(panel); return;
    }
    panel.append(node("p", "flow-muted", "旧 HTML 简历已弃用；历史记录保留，请通过 LaTeX 材料流程准备新简历。"));
    current.append(panel);
  }
  function renderPdfExport(draft, task) {
    if (draft.origin !== "existing_latex" && task.origin !== "existing_latex") return;
    const panel = node("section", "flow-stage"); panel.id = "flow-export"; panel.append(node("h3", "", "PDF 导出"));
    const status = task.stages?.export?.status || "pending";
    const stale = flow.preparation?.checks?.draft?.status === "stale" || flow.active_explanation?.fresh === false;
    const invalid = flow.draft_integrity?.status === "invalid";
    const reviewedDraft = task.origin === "existing_latex" ? technicalExportAuthorized(draft, task) : draftReviewed(draft, task);
    const running = stagesRunning(task);
    const retryExport = status === "failed" || (status === "complete" && flow.pdf_integrity?.status === "invalid");
    panel.append(node("p", "flow-muted", retainedMaterialAccepted(task) ? "此具体 PDF 已有接受记录，继续使用保存版本。" : task.origin === "existing_latex" ? "从已授权的 LaTeX 版本经 Prism 严格编译并保存 PDF；事实审核保持待完成。" : task.prism ? "从已审阅的 LaTeX 经 Prism 严格编译并保存 PDF；导出与重试均不改写简历。" : "从已审阅草稿导出 PDF；导出与重试均不重新生成简历。"));
    if (!reviewedDraft) panel.append(node("p", "flow-muted", task.origin === "existing_latex" ? "请先授权此版本的本地技术导出。源变化后需接入新版本。" : "请先审阅并记录当前草稿，再明确导出 PDF。"));
    if (["queued", "running"].includes(status)) panel.append(node("p", "flow-muted", "正在导出，请等待持久结果。"));
    if (status === "failed") panel.append(node("p", "flow-error", pdfEnvironmentErrors[task.stages?.export?.error_code] || "PDF 导出未完成。草稿与审阅记录已保留，可仅重试导出。"));
    if (status === "needs_recheck") panel.append(node("p", "flow-error", "导出结果尚未核验。请先核验已保存回执，再决定后续操作。"));
    const exportPdf = button(retryExport ? "仅重试 PDF 导出" : "导出 PDF", () => mutate(() => api("/api/flow/export-pdf", { method: "POST", body: JSON.stringify({ task_id: task.id, task_revision: task.revision, draft_id: draft.id, draft_sha256: draft.draft_sha256, ...(retryExport ? { retry: true } : {}) }) })), "flow-export-pdf");
    exportPdf.dataset.blocked = String(stale || batchStageBlocked(task) || invalid || !reviewedDraft || running || (status !== "pending" && !retryExport)); panel.append(exportPdf);
    if (batchStageBlocked(task)) panel.append(node("p", "flow-muted", "此岗需在材料批次中明确继续或手动重试后，才会启动后续阶段。"));
    if (status === "needs_recheck") {
      const recheck = button("核验导出结果", () => mutate(() => api("/api/flow/recheck-export", { method: "POST", body: JSON.stringify({ task_id: task.id, task_revision: task.revision }) })), "flow-recheck-export", true);
      recheck.dataset.blocked = String(running); panel.append(recheck);
      for (const snapshot of flow.review_snapshots || []) {
        const saved = node("div", "flow-source");
        saved.append(node("p", "", `已有严格审阅快照 · ${snapshot.page_count} 页 · ${snapshot.created_at}`), node("p", "flow-muted flow-hash", `PDF SHA256 ${snapshot.pdf_sha256}`));
        const adopt = button("采用已核验审阅快照", () => mutate(() => api("/api/flow/adopt-review-snapshot", { method: "POST", body: JSON.stringify({ task_id: task.id, task_revision: task.revision, review_version_id: snapshot.id, expected_pdf_sha256: snapshot.pdf_sha256 }) })), "flow-adopt-review-snapshot");
        adopt.dataset.blocked = String(stale || invalid || running || !reviewedDraft);
        saved.append(adopt, node("p", "flow-muted", "复用此源版本已完成的 PDF，不重新编译。原未知导出记录保留，真实申请继续暂停。")); panel.append(saved);
      }
    }
    current.append(panel);
  }
  function renderMaterials(resume, task) {
    const stale = !flow?.local_materials && flow?.mode === "preparation" && flow.preparation?.checks?.draft?.status === "stale";
    const invalid = flow?.mode === "preparation" && (flow.pdf_integrity?.status === "invalid" || !flow?.local_materials && (flow.preparation?.checks?.draft?.status === "invalid" || !prismCurrent(task)));
    const panel = node("section", "flow-stage"); panel.id = "flow-materials";
    panel.append(node("h3", "", "材料校验与历史"));
    if (invalid) panel.append(node("p", "flow-error", flow.pdf_integrity?.message || flow.prism?.message || flow.preparation?.checks?.draft?.message || "当前材料版本暂不能核验。"));
    const path = resume.preview_url;
    if (!/^\/api\/flow\/resumes\/[a-f0-9]{32}\/pdf$/.test(path || "") || !/^[a-f0-9]{64}$/.test(resume.pdf_sha256 || "")) {
      panel.append(node("p", "flow-error", "PDF 标识不完整，请核验材料记录。")); systemDetails().append(panel); return;
    }
    const version = node("details", "flow-details"); version.append(node("summary", "", `材料版本 ${resume.id.slice(0, 8)} · 查看校验信息`), node("p", "flow-muted flow-hash", `版本 ${resume.id} · SHA256 ${resume.pdf_sha256}`));
    panel.append(version);
    if (resume.operation_kind === "reuse_completed_review") panel.append(node("p", "flow-muted", "此 PDF 采用已核验的审阅快照。原导出结果仍待核验，已保留历史并阻止此任务再次执行。"));
    if (task.origin === "existing_latex") {
      const accepted = retainedMaterialAccepted(task);
      panel.append(node("p", "flow-muted", accepted ? "已复用此前用户对这版 PDF 内容和排版的接受记录，无需重复确认。资格结论与生成来源审核分别保留；真实申请继续暂停。" : "事实审核待完成。此 PDF 为本地技术核对版本；真实申请继续暂停。"));
      if (accepted) {
        const batch = flow.preparation_batch;
        const adopted = batch?.kind === "accepted_material_reuse" && batch.retained_material?.task_id === task.id && batch.retained_material?.material_acceptance_revision === task.material_acceptance.revision;
        const adopt = button(adopted ? "此已接受材料已纳入暂停批次" : "将此已接受材料纳入暂停批次", () => mutate(() => api("/api/flow/batch-adopt-accepted-material", { method: "POST", body: JSON.stringify({ request_id: crypto.randomUUID().replaceAll("-", ""), task_id: task.id, task_revision: task.revision }) })), "flow-adopt-accepted-material");
        adopt.dataset.blocked = String(stale || invalid || adopted || !!batch && batch.control !== "cancelled");
        panel.append(adopt);
      }
      const receipt = node("div"); receipt.id = "flow-export-receipt";
      const token = `${resume.id}/${resume.pdf_sha256}`;
      const showReceipt = saved => {
        receipt.replaceChildren(node("p", "flow-source", accepted ? "导出回执已核验 · 已保留此版 PDF 的用户接受记录" : "导出回执已核验 · 事实审核待完成"));
        const details = node("details", "flow-details"); details.open = true;
        details.append(node("summary", "", "导出、LaTeX 与 PDF 版本"), node("p", "flow-muted flow-hash", `导出版本 ${saved.id}`), node("p", "flow-muted flow-hash", `LaTeX 版本 ${saved.prism_source_revision}`), node("p", "flow-muted flow-hash", `PDF SHA256 ${saved.pdf_sha256}`));
        receipt.append(details);
      };
      if (exportReceipts.has(token)) showReceipt(exportReceipts.get(token));
      const read = button("读取导出回执", async () => {
        read.disabled = true;
        try {
          const saved = await api(`/api/flow/exports/${encodeURIComponent(resume.id)}`);
          if (saved.id !== resume.id || saved.pdf_sha256 !== resume.pdf_sha256 || saved.prism_source_revision !== task.prism?.source_revision) throw new Error("导出回执与此任务版本不匹配，请保留历史并重新核验。");
          exportReceipts.set(token, saved); showReceipt(saved);
        } catch (error) { receipt.replaceChildren(node("p", "flow-error", error.message)); }
        finally { read.disabled = false; }
      }, "flow-read-export-receipt", true);
      delete read.dataset.flowWrite;
      panel.append(read, receipt); systemDetails().append(panel); return;
    }
    panel.append(sourceReview(resume));
    panel.append(node("p", "flow-muted", "系统已保存当前 PDF。填写前会自动核验并绑定此版本；需要时可直接预览。"));
    if (flow?.mode === "preparation") { systemDetails().append(panel); return; }
    const regenerate = button("重新生成简历", async () => {
      if (await confirmAction("重新生成会保存新版本。旧 PDF 与来源记录仍保留。", "重新生成")) start("resume", true);
    }, "flow-regenerate-resume", true);
    const qualificationBlocked = flow?.mode === "preparation" && flow.active_explanation && !["supported", "not_specified"].includes(flow.active_explanation.qualification?.status);
    regenerate.dataset.blocked = String(stale || qualificationBlocked || flow?.capabilities?.resume === false || !!task.worker_ref || ["queued", "running"].includes(task.stages?.resume?.status)); panel.append(regenerate);
    systemDetails().append(panel);
  }
  function renderWorker(task) {
    if (flow?.mode === "preparation" || !["resume_ready", "materials_ready"].includes(task.status) && !task.worker_ref) return;
    const panel = node("section", "flow-stage"); panel.id = "flow-worker"; panel.append(node("h3", "", "03 · 自动填写"));
    const diagnostics = node("details", "flow-details"); diagnostics.id = "flow-worker-diagnostics";
    diagnostics.open = diagnosticTasks.has(task.id);
    diagnostics.append(node("summary", "", "技术诊断"));
    diagnostics.addEventListener("toggle", () => { if (diagnostics.open) diagnosticTasks.add(task.id); else diagnosticTasks.delete(task.id); });
    renderRuntimeReadiness(diagnostics, task);
    if (!task.worker_ref && pipelineTask(task)) {
      panel.append(node("p", "flow-muted", "材料与填写由自动申请流程继续；需要时暂停后修改，再继续当前岗位。"));
    } else if (!task.worker_ref) {
      const application = data.applications.find(item => item.id === task.application_id);
      const eligibility = flow.eligibility?.status;
      const enabled = flow.capabilities?.worker === true;
      const draftKey = `${task.id}/${task.resume_id}`;
      const knownCountry = task.send_approval?.country || task.country || application?.country || "";
      const draft = preparationDrafts.get(draftKey) || { country: knownCountry, confirmed: false };
      const country = node("select"); country.required = true; country.setAttribute("aria-label", "此岗位的申请国家");
      for (const [value, text] of [["", "请选择申请国家"], ["CHE", "瑞士"], ["USA", "美国"], ["GBR", "英国"], ["DEU", "德国"], ["FRA", "法国"], ["CAN", "加拿大"], ["OTHER", "其他（答案仅限当前岗位）"]]) { const option = node("option", "", text); option.value = value; country.append(option); }
      country.value = draft.country;
      const label = node("label", "flow-country-label", "这份申请属于哪个国家？"); label.append(country); label.hidden = !!knownCountry;
      const send = node("input"); send.type = "checkbox"; send.id = "flow-send-confirmed"; send.checked = draft.confirmed;
      const consent = node("label", "flow-check"); consent.append(send, node("span", "", `我确认开始填写后，将此岗位当前 PDF 和已保存信息发送到岗位网站：${application?.url || "尚未提供申请链接"}。`));
      const prepare = button("仅准备并保持暂停", () => mutate(() => api("/api/flow/prepare-worker", { method: "POST", body: JSON.stringify({ task_id: task.id, task_revision: task.revision, country: country.value, send_confirmed: send.checked }) })), "flow-prepare-worker");
      const startFilling = button("开始自动填写", () => mutate(async () => {
        const prepared = await api("/api/flow/prepare-worker", { method: "POST", body: JSON.stringify({ task_id: task.id, task_revision: task.revision, country: country.value, send_confirmed: send.checked }) });
        if (!prepared?.id || !prepared?.revision || !prepared.worker_ref) throw new Error("准备结果尚未核验，填写保持暂停。");
        flow = await api(`/api/flow/${encodeURIComponent(prepared.id)}`);
        const currentTask = flow?.active_task;
        if (currentTask?.id !== prepared.id || currentTask.revision !== prepared.revision || currentTask.status !== "queued") throw new Error("当前任务已变化，填写保持暂停。");
        await api("/api/flow/worker-action", { method: "POST", body: JSON.stringify({ task_id: currentTask.id, task_revision: currentTask.revision, operation: "resume", payload: { controller } }) });
        ownsLease = true; lastHeartbeat = Date.now();
      }), "flow-start-filling");
      const update = () => { preparationDrafts.set(draftKey, { country: country.value, confirmed: send.checked });
        const blocked = String(!enabled || !application?.url || !["resume_ready", "materials_ready"].includes(task.status) || !["supported", "not_specified", "needs_input"].includes(eligibility) || !country.value || !send.checked);
        prepare.dataset.blocked = blocked; startFilling.dataset.blocked = blocked; lock(); };
      country.addEventListener("change", update); send.addEventListener("change", update); update();
      if (pipeline?.enabled) {
        panel.append(node("p", "flow-muted", "后台自动准备填写。完成后会通知你前往原申请页确认，最终 Submit 由你操作。"));
        diagnostics.append(label, consent, startFilling);
      } else panel.append(label, consent, startFilling, node("p", "flow-muted", "开始后自动检查并填写。完成后直接去原申请网站复核；最终 Submit 由你操作。"));
      diagnostics.append(prepare);
      if (!enabled) panel.append(node("p", "flow-muted", "填写服务尚未连接。你仍可分析与预览已保存的材料。"));
      if (!application?.url) panel.append(node("p", "flow-muted", "填写前请在岗位详情补齐申请链接，再同步最新输入。"));
      if (eligibility === "conflict") panel.append(node("p", "flow-error", "硬条件存在冲突，不能启动填写。"));
    } else {
      const state = flow.worker;
      if (!state?.enabled) { panel.append(node("p", "flow-error", state?.message || "填写状态尚不能核验。请保留原任务和页面，重新读取状态。"), diagnostics); current.append(panel); return; }
      const job = state.jobs?.find(item => item.application_id === task.application_id);
      panel.append(node("p", "flow-badges", state.control === "running" ? "填写运行中" : state.control === "cancelled" ? "填写已取消" : "填写已暂停"));
      diagnostics.append(node("p", "flow-muted", state.runtime_status?.observation === "current" ? "当前运行观察有效。" : "进程与页面的当前状态尚未核验。历史检查点不能证明原页面已恢复。"));
      if (job) panel.append(node("p", "flow-muted", statusLabels[job.status] || job.status));
      const controls = node("div", "flow-actions");
      const resume = button("开始／继续填写", () => workerAction("resume", { controller }), "flow-worker-resume");
      resume.dataset.blocked = String(task.status === "cancelled" || state.control === "running" || !job || !["queued", "filling", "needs_input"].includes(job.status) || job.handed_off);
      const pause = button("暂停填写", () => workerAction("pause", { controller }), "flow-worker-pause", true);
      pause.dataset.flowStop = "true";
      pause.dataset.blocked = String(state.control !== "running" || state.controller !== controller);
      if (!pipelineTask(task)) controls.append(resume); controls.append(pause); (pipeline?.id ? diagnostics : panel).append(controls);
      for (const item of state.input_items || []) {
        const target = item.jobs?.find(row => row.id === task.application_id);
        if (!target) continue;
        const key = `${task.id}/${item.id}`;
        const saved = answerDrafts.get(key) || { value: "", message: "填写完成后自动保存到信息库。" };
        saved.taskId = task.id;
        saved.question = item.question;
        saved.payload = { application_id: task.application_id, question_id: target.question_id, scope: { ...item.scope }, only_this: false };
        const form = node("form", "flow-condition"); form.append(node("h4", "", item.question));
        const answer = node(item.options?.length ? "select" : "textarea"); answer.required = true; answer.setAttribute("aria-label", `${item.question} · 补充信息`);
        answer.dataset.answerKey = key;
        if (item.options?.length) for (const value of ["", ...item.options]) { const option = node("option", "", value || "请选择"); option.value = value; answer.append(option); }
        answer.value = saved.value; answer.disabled = !!saved.saving; saved.input = answer;
        const notice = node("p", "flow-muted", saved.message); notice.setAttribute("role", "status"); saved.notice = notice;
        const reuse = item.scope?.application_id ? "仅此岗位" : item.scope?.country ? "仅相同国家" : Object.keys(item.scope || {}).length ? "仅相同适用范围" : "基本信息，可跨岗位复用";
        const keep = () => { if (saved.saving) return; if (saved.value !== answer.value) saved.attemptedValue = undefined; saved.value = answer.value; saved.pending = false; answerDrafts.set(key, saved); answerMessage(saved, "尚未保存。填写完成并离开此项后自动保存。"); };
        answer.addEventListener("input", keep);
        answer.addEventListener(item.options?.length ? "change" : "blur", () => {
          if (rendering || !answer.isConnected || saved.saving) return;
          saved.value = answer.value; answerDrafts.set(key, saved);
          if (!saved.value.trim()) { saved.pending = false; answerMessage(saved, "尚未保存，请补充信息。"); return; }
          if (saved.attemptedValue === saved.value) return;
          saved.pending = true; answerMessage(saved, "等待自动保存到信息库…"); saveNextAnswer();
        });
        form.addEventListener("submit", event => event.preventDefault());
        form.append(answer, node("p", "flow-muted", `自动保存到信息库（${reuse}）。保存不会恢复已暂停的填写。`), notice); panel.append(form);
      }
      if (job) { renderFormDifferences(panel, task, job); renderRequiredMaterials(panel, task, job, state); renderOwnedPageInspection(diagnostics, task, job); renderEmailCorrection(diagnostics, task, job); renderWorkerRecovery(panel, task, job, state); }
    }
    panel.append(diagnostics);
    current.append(panel);
  }
  function renderRequiredMaterials(panel, task, job, state) {
    if (job.cover_letter_delivery) {
      const delivery = job.cover_letter_delivery;
      const requirementLabels = { required: "必需", optional: "可选，有入口默认交付", none: "无交付入口", unverified: "交付需求未核实" };
      panel.append(node("p", "flow-muted", `Cover Letter：${requirementLabels[delivery.requirement] || delivery.requirement || "需求未核实"} · ${delivery.status}`));
      if (delivery.error_message || delivery.reason) panel.append(node("p", "flow-muted", delivery.error_message || delivery.reason));
    }
    for (const material of job.materials || []) {
      const card = node("section", "flow-condition");
      if (material.id) card.dataset.flowMaterialId = material.id;
      card.append(node("h4", "", material.question || "申请附件"));
      if (material.status === "ready") {
        card.append(node("p", "flow-source", material.filename || "本岗文本已生成并核验"));
        if (material.actor === "system") card.append(node("p", "flow-muted", "系统按本岗资料生成；来源核验记录已保存。"));
        if (material.text) {
          const text = node("details", "flow-details");
          text.append(node("summary", "", "查看附稿正文"), node("pre", "flow-text", material.text)); card.append(text);
        }
        if (/^[a-f0-9]{32}$/.test(material.id || "") && /^[a-f0-9]{64}$/.test(material.sha256 || "")) {
          const path = `/api/flow/worker-materials/${task.id}/${material.id}/pdf`;
          const link = node("a", "button button-secondary", "打开附稿 PDF 预览"); link.href = path; link.target = "_blank"; link.rel = "noopener noreferrer"; card.append(link);
          const preview = button("在此预览附稿 PDF", () => {
            const frame = node("iframe", "flow-pdf"); frame.title = `${material.question || "附稿"} PDF`; frame.src = path; preview.replaceWith(frame);
          }, null, true); delete preview.dataset.flowWrite; card.append(preview);
        }
        renderMaterialEditor(card, task, job, material, state);
        if (material.letter_content && material.tex_path) {
          const capture = button("接回 LaTeX 正文修改", () => mutate(() => api("/api/flow/capture-material-tex", { method: "POST", body: JSON.stringify({ task_id: task.id, task_revision: task.revision, material_id: material.id, expected_content_revision: material.content_revision, request_id: crypto.randomUUID().replaceAll("-", "") }) })), null, true);
          capture.dataset.blocked = String(state.control !== "paused" || job.precision_preparation?.status !== "ready");
          card.append(capture);
        }
        panel.append(card); continue;
      }
      if (material.status !== "needs_input" || material.kind === "motivation_text") {
        card.append(node("p", "flow-muted", material.status === "needs_recheck" ? "材料结果尚未核验，已停止自动重试。" : "当前材料尚未完成，请核对需要补充的事实。"));
        if (material.status === "failed" && material.kind === "cover_letter" && material.material_revision) {
          const retry = button("仅重试求职信文件构建", () => workerAction("retry-cover-letter-file", { application_id: task.application_id, material_id: material.id, expected_material_revision: material.material_revision, request_id: crypto.randomUUID().replaceAll("-", "") }), null, true);
          retry.dataset.blocked = String(state.control !== "paused"); card.append(retry);
        }
        if (material.status === "needs_recheck" && material.kind === "cover_letter" && material.letter_content && material.material_revision) {
          const recheck = button("只读核验求职信文件结果", () => workerAction("recheck-cover-letter-file", { application_id: task.application_id, material_id: material.id, expected_material_revision: material.material_revision, request_id: crypto.randomUUID().replaceAll("-", "") }), null, true);
          recheck.dataset.blocked = String(state.control !== "paused"); card.append(recheck);
        }
        panel.append(card); continue;
      }
      const jdOnly = material.origin === "jd" && !material.field_id && !!material.requirement_id;
      if (!jdOnly && !material.field_id) { card.append(node("p", "flow-muted", "当前附件位置尚不能核验，请保留原申请要求。")); panel.append(card); continue; }
      const target = jdOnly ? { requirement_id: material.requirement_id } : { field_id: material.field_id, draft_path: material.draft_path || "" };
      const key = `${task.id}/${material.field_id || material.requirement_id}/${material.draft_path || ""}`;
      const draft = materialDrafts.get(key) || { request_id: crypto.randomUUID().replaceAll("-", "") };
      const form = node("form");
      const file = node("input"); file.type = "file"; file.accept = ".pdf,application/pdf"; file.dataset.flowWrite = "true";
      file.setAttribute("aria-label", `${material.question || "申请附件"} · 提供真实附件`);
      const selected = node("p", "flow-muted", draft.file?.name || "请选择不超过 700 KB 的真实 PDF，保存后保持暂停。");
      file.addEventListener("change", () => { draft.file = file.files[0]; materialDrafts.set(key, draft); selected.textContent = draft.file?.name || "尚未选择文件"; });
      const save = button("保存真实附件", () => {}, null, true); save.type = "submit"; save.dataset.blocked = String(state.control !== "paused");
      form.addEventListener("submit", event => {
        event.preventDefault();
        if (!draft.file || draft.file.size > 700000 || !/\.pdf$/i.test(draft.file.name)) { selected.textContent = "请选择不超过 700 KB 的真实 PDF。"; return; }
        mutate(async () => {
          const bytes = new Uint8Array(await draft.file.arrayBuffer());
          const encoded = btoa(Array.from(bytes, byte => String.fromCharCode(byte)).join(""));
          await api("/api/flow/worker-action", { method: "POST", body: JSON.stringify({ task_id: task.id, task_revision: task.revision, operation: "provide-material", payload: { application_id: task.application_id, ...target, kind: material.kind, filename: draft.file.name, file_base64: encoded, request_id: draft.request_id } }) });
          materialDrafts.delete(key); message("真实附件已保存。点击继续当前岗位后续填，最终 Submit 由你操作。");
        });
      });
      form.append(file, selected, save); card.append(form); panel.append(card);
    }
  }
  function renderMaterialEditor(card, task, job, material, state) {
    if (!["motivation_text", "cover_letter"].includes(material.kind) || !material.text || job.precision_preparation?.status !== "ready") return;
    const key = `${task.id}/${material.field_id || material.requirement_id}/${material.draft_path || ""}`;
    let local = materialTextDrafts.get(key);
    const receipt = job.material_edit;
    if (local && receipt?.status === "complete" && receipt.request_id === local.request_id && receipt.new_material_id === material.id && material.text === local.text) {
      materialTextDrafts.delete(key); local = null;
    }
    const blocked = state.control !== "paused" || job.status !== "needs_input" || state.current_job_id !== task.application_id || ["preparing", "needs_recheck"].includes(job.material_edit?.status);
    const details = node("details", "flow-details"); details.append(node("summary", "", "修改附稿正文"));
    details.open = materialTextEditors.get(key) ?? false;
    details.addEventListener("toggle", () => { if (details.isConnected) materialTextEditors.set(key, details.open); });
    const input = node("textarea"); input.rows = 8; input.value = local?.text ?? material.text;
    input.setAttribute("aria-label", `${material.question} · 附稿正文`); input.dataset.flowWrite = "true"; input.dataset.flowRequiresPaused = "true";
    input.dataset.blocked = String(blocked);
    input.addEventListener("input", () => {
      const draft = materialTextDrafts.get(key) || { task_id: task.id, material_id: material.id, expected_text_sha256: material.text_sha256, request_id: crypto.randomUUID().replaceAll("-", "") };
      draft.text = input.value;
      if (input.value === material.text && draft.material_id === material.id) materialTextDrafts.delete(key);
      else materialTextDrafts.set(key, draft);
      save.dataset.blocked = String(blocked || !materialTextDrafts.has(key) || draft.material_id !== material.id); lock();
    });
    const save = button("保存附稿修改", () => mutate(async () => {
      const draft = materialTextDrafts.get(key);
      if (!draft) return;
      await api("/api/flow/edit-material", { method: "POST", body: JSON.stringify({ ...draft, task_revision: task.revision }) });
      materialTextDrafts.delete(key); message("附稿修改已保存。点击继续当前岗位后再填写和上传，最终 Submit 由你操作。");
    }), null, true);
    save.dataset.flowRequiresPaused = "true"; save.dataset.blocked = String(blocked || !local || local.material_id !== material.id);
    details.append(input, save);
    if (local && local.material_id !== material.id) {
      details.append(node("p", "flow-muted", "此附稿已有新的保存版本。你的文字仍保留，请比较当前正文后再保存。"));
      const rebase = button("保留编辑并采用当前附稿版本", () => {
        materialTextDrafts.set(key, { ...local, material_id: material.id, expected_text_sha256: material.text_sha256, request_id: crypto.randomUUID().replaceAll("-", "") });
        renderedTask = null; renderTask(); lock();
      }, null, true);
      rebase.dataset.flowRequiresPaused = "true"; rebase.dataset.blocked = String(blocked); details.append(rebase);
    }
    if (receipt?.status === "needs_recheck" && receipt.old_material_id === material.id) {
      const reconcile = button("核验附稿保存结果", () => mutate(async () => {
        await api("/api/flow/reconcile-material-edit", { method: "POST", body: JSON.stringify({ task_id: task.id, task_revision: task.revision, request_id: receipt.request_id }) });
        message("已核验并保存附稿。填写保持暂停，点击继续当前岗位后续填。");
      }), null, true);
      reconcile.dataset.flowRequiresPaused = "true";
      reconcile.dataset.blocked = String(state.control !== "paused" || job.status !== "needs_input" || state.current_job_id !== task.application_id);
      details.append(reconcile);
    }
    card.append(details);
  }
  function answerMessage(draft, text) {
    draft.message = text;
    if (draft.notice) draft.notice.textContent = text;
  }
  async function saveNextAnswer() {
    if (answerSaving || busy || isUncertain(taskScope()) || !readable.flow || !readable.pipeline || !stateReady) return;
    const next = [...answerDrafts].find(([, draft]) => draft.pending && draft.taskId === flow?.active_task?.id);
    if (!next || !flow.active_task.worker_ref) return;
    const [key, draft] = next, value = draft.value;
    draft.pending = false; draft.saving = true; draft.attemptedValue = value; answerSaving = true;
    if (draft.input) draft.input.disabled = true;
    answerMessage(draft, "正在自动保存到信息库…");
    let saved = false;
    await workerAction("answer", { ...draft.payload, value }, () => {
      saved = true;
      answerDrafts.delete(key);
      message("已自动保存到信息库。填写保持当前状态。" );
    });
    draft.saving = false; answerSaving = false;
    if (draft.input) draft.input.disabled = false;
    if (!saved) {
      answerMessage(draft, isUncertain() ? "保存结果未知，已停止自动保存。请先读取最新状态核验；不会自动重试。" : "尚未保存。请核对提示，重新编辑后再离开此项。");
      for (const item of answerDrafts.values()) if (item.pending) { item.pending = false; answerMessage(item, "尚未保存。自动保存已停止，请重新编辑后离开此项。"); }
      return;
    }
    saveNextAnswer();
  }
  function samePageBinding(left, right) {
    return !!left && !!right && ["batch_id", "run_id", "page_id"].every(key => left[key] === right[key]);
  }
  async function observeBeforeResume(task) {
    const stop = () => { const error = new Error("原页面尚未核验或绑定已变化，填写保持暂停。请保留原页面。"); error.status = 409; throw error; };
    let snapshot = await api(`/api/flow/${encodeURIComponent(task.id)}`);
    if (snapshot.active_task?.id !== task.id || snapshot.active_task.revision !== task.revision || snapshot.worker?.control !== "paused") stop();
    const job = snapshot.worker?.jobs?.find(item => item.application_id === task.application_id);
    if (!job) stop();
    const target = job.page_inspection_target;
    const bootstrap = !snapshot.worker.runtime && !snapshot.worker.worker_pid && job.status === "queued" && !job.page_open && !job.page_observation && !job.intent && !job.manual_submission && !job.handed_off && !job.observations?.length && !job.answer_refs?.length && !job.questions?.length;
    if (!target && bootstrap) { flow = snapshot; return; }
    if (!target || job.owned_page_inspection_state === "pending") stop();
    const previous = job.owned_page_inspection?.request_id;
    message("正在后台核验原申请页面，检查通过后继续…");
    await api("/api/flow/worker-action", { method: "POST", body: JSON.stringify({ task_id: task.id, task_revision: task.revision, operation: "observe-page", payload: { application_id: task.application_id, binding: target } }) });
    for (let attempt = 0; attempt < 32; attempt++) {
      snapshot = await api(`/api/flow/${encodeURIComponent(task.id)}`);
      const currentJob = snapshot.worker?.jobs?.find(item => item.application_id === task.application_id);
      if (snapshot.active_task?.id !== task.id || snapshot.active_task.revision !== task.revision || snapshot.worker?.control !== "paused" || !samePageBinding(currentJob?.page_inspection_target, target)) stop();
      const inspection = currentJob.owned_page_inspection;
      if (inspection?.status === "captured" && currentJob.owned_page_inspection_state === "current" && inspection.request_id && inspection.request_id !== previous && samePageBinding(inspection.binding, target)) { flow = snapshot; return; }
      if (inspection?.status !== "pending" || currentJob.owned_page_inspection_state !== "pending") stop();
      await new Promise(resolve => setTimeout(resolve, 250));
    }
    stop();
  }
  function runtimeCheckBinding(task) {
    return JSON.stringify([task.id, task.revision, flow?.worker?.runtime?.id || null]);
  }
  function runtimeCheckFresh(task) {
    const at = runtimeCheck?.receipt?.checked_at;
    const age = Date.now() / 1000 - at;
    return !!task && Number.isFinite(at) && age >= 0 && age < 10 && runtimeCheck.binding === runtimeCheckBinding(task)
      && runtimeCheck.receipt.inputs?.task_revision === task.revision
      && (runtimeCheck.receipt.worker?.run_id || null) === (flow?.worker?.runtime?.id || null);
  }
  function renderRuntimeReadiness(panel, task) {
    const section = node("section", "flow-stage"); section.id = "flow-runtime-readiness";
    section.append(node("h4", "", "当前运行与版本核验"));
    const check = button("核验当前运行与版本", async () => {
      if (runtimeChecking) return;
      const binding = runtimeCheckBinding(task);
      runtimeChecking = true; check.disabled = true;
      try {
        const receipt = await api(`/api/flow/readiness/${encodeURIComponent(task.id)}`);
        if (receipt?.protocol !== "installed-readiness/v1" || receipt.schemaVersion !== 1) throw new Error("核验回执版本无法识别。");
        runtimeCheck = { taskId: task.id, binding, receipt };
      } catch (error) { runtimeCheck = { taskId: task.id, binding, error: error.message }; }
      finally { runtimeChecking = false; render(); }
    }, "flow-check-runtime-readiness", true);
    delete check.dataset.flowWrite; check.disabled = runtimeChecking;
    section.append(check, node("p", "flow-muted", "本次核验只读，不恢复填写或确认材料。开始填写时会自动检查当前 App 权限；这里不会请求授权或打开浏览器。"));
    const saved = runtimeCheck?.taskId === task.id ? runtimeCheck : null;
    if (!saved) section.append(node("p", "flow-muted", "尚未读取本任务的运行核验证据。"));
    else if (saved.error) section.append(node("p", "flow-error", `未取得核验结果，保持暂停。${saved.error}`));
    else {
      const receipt = saved.receipt;
      const fresh = runtimeCheckFresh(task);
      const labels = { unknown: "尚未核验完整，保持暂停", blocked: "核验发现阻断，保持暂停", verified_paused: "技术核验通过，保持暂停" };
      section.append(node("p", receipt.status === "blocked" && fresh ? "flow-error" : "flow-muted", fresh ? labels[receipt.status] || labels.unknown : "历史核验；不能作为当前就绪依据，请重新核验。"));
      if (Number.isFinite(receipt.checked_at)) section.append(node("p", "flow-muted", `核验时刻：${new Date(receipt.checked_at * 1000).toLocaleString()}`));
      const status = value => ({ current: "当前证据有效", stale: "证据已过期", historical: "历史证据", verified: "已核验", supported: "支持", unknown: "尚未核验", state_changed: "核验期间状态发生变化", missing: "尚未创建", exited: "执行器已退出", failed: "观察失败", blocked: "存在阻断", granted: "已获权", denied: "未获权" })[value] || value || "尚未核验";
      const permission = value => value === true ? "已获权" : value === false ? "未获权" : "尚未核验";
      const table = node("table", "flow-source-table");
      const rows = [
        ["控制端", `实际加载版本：${receipt.controller?.loaded_engine_revision || "未报告"}；界面版本：${receipt.controller?.ui_revision || "未报告"}`],
        ["磁盘包", `${status(receipt.package?.status)}；包清单：${receipt.package?.manifest_revision || "未取得"}；签名：${receipt.package?.signature === "not_checked" ? "本次未核验" : status(receipt.package?.signature)}`],
        ["填写执行器", `${status(receipt.worker?.state)}；实际加载版本：${receipt.worker?.loaded_engine_revision || "未报告"}；启动来源版本：${receipt.worker?.startup_source_revision || "未报告"}；停止代码：${receipt.worker?.last_error || "未记录"}`],
        ["当前宿主权限", `${status(receipt.native_host?.state)}；辅助功能：${permission(receipt.native_host?.accessibility)}；录屏：${permission(receipt.native_host?.screen_recording)}；宿主：${receipt.native_host?.bundle_id || "尚未核验"}；执行路径：${receipt.native_host?.executable || "尚未核验"}；${receipt.native_host?.reason || "尚未取得当前实例责任链回执"}`],
        ["所属原页与连接", `${status(receipt.page?.state)}；连接归属：${status(receipt.page?.owner?.status)}`],
        ["岗位与材料输入", status(receipt.inputs?.state)],
        ["命令兼容性", `${receipt.compatibility?.state === "verified" ? "兼容性已核验" : "兼容性未核验"}；读取状态：${status(receipt.compatibility?.commands?.read_state)}；只读观察：${status(receipt.compatibility?.commands?.observe_page)}；继续填写：${status(receipt.compatibility?.commands?.resume)}`],
        ["用户停止决定", "核验不改变原停止决定；继续填写仍需单独明确操作。"],
      ];
      for (const [label, text] of rows) { const row = node("tr"); row.append(node("th", "", label), node("td", "", text)); table.append(row); }
      section.append(table);
      if (Array.isArray(receipt.reasons) && receipt.reasons.length) section.append(node("p", "flow-muted", `待处理依据：${receipt.reasons.join(" · ")}`));
      const details = node("details"); details.append(node("summary", "", "查看本次版本、绑定与权限证据"), node("pre", "flow-text", JSON.stringify(receipt, null, 2))); section.append(details);
    }
    panel.append(section);
  }
  function renderOwnedPageInspection(panel, task, job) {
    const section = node("section", "flow-stage"); section.id = "flow-page-inspection";
    section.append(node("h4", "", "所属原页 · 只读观察"));
    const target = job.page_inspection_target;
    const receipt = job.owned_page_inspection;
    const state = job.owned_page_inspection_state;
    const read = button("只读观察所属原页", () => workerAction("observe-page", { application_id: task.application_id, binding: target }), "flow-worker-observe-page", true);
    read.dataset.blocked = String(!target || state === "pending");
    section.append(read, node("p", "flow-muted", "只读取所属原页，不导航、刷新、填写、重传或提交；观察不能证明远端草稿已保存。"));
    if (!target) section.append(node("p", "flow-muted", "请保持暂停。原执行器须支持此接口，且原页与连接必须有效；不会另开页面或接管其他浏览器。"));
    if (receipt) {
      const labels = { pending: "等候所属执行器只读回读", timed_out: "观察未完成或所属连接已失效，请保留原页核验", failed: "本次观察失败，未取得新鲜内容", current: "本次观察已完成（采集时刻的页面状态）", historical: "历史观察；不能作为当前字段或附件状态" };
      section.append(node("p", state === "failed" || state === "timed_out" ? "flow-error" : "flow-muted", labels[state] || "观察状态尚未核验"));
      if (receipt.at) section.append(node("p", "flow-muted", `采集时刻：${new Date(receipt.at * 1000).toLocaleString()}`));
      if (receipt.reason) section.append(node("p", "flow-muted", `停止原因：${receipt.reason}`));
      if (receipt.status === "captured" && receipt.data) {
        section.append(node("p", "", receipt.data.title || "无页面标题"), node("p", "flow-muted", receipt.data.url));
        const table = node("table", "flow-source-table");
        const head = node("tr"); for (const name of ["字段", "只读值", "有效性", "附件（页面可见状态）"]) head.append(node("th", "", name)); table.append(head);
        for (const field of receipt.data.fields || []) {
          const row = node("tr");
          for (const value of [field.label || field.id || field.name || field.type, field.redacted ? "已隐藏" : field.value, field.valid === true ? "有效" : field.valid === false ? "无效" : "未提供", (field.files || []).map(file => `${file.name} · ${file.size} bytes`).join("；")]) row.append(node("td", "", String(value ?? "")));
          table.append(row);
        }
        section.append(table);
        section.append(node("p", "flow-muted", receipt.data.attachments?.length ? `页面可见附件名称：${receipt.data.attachments.map(file => file.name).join("；")}。这不是服务器保存回执。` : "未取得其他可读附件凭据；不能据此断言未上传。"));
        if (receipt.screenshot?.mime_type === "image/png" && receipt.screenshot.base64) {
          const picture = node("img"); picture.alt = "同一所属原页在采集时刻的视口截图"; picture.src = `data:image/png;base64,${receipt.screenshot.base64}`; picture.style.maxWidth = "100%"; section.append(picture);
        }
      }
      const details = node("details"); details.append(node("summary", "", "观察绑定与版本"), node("pre", "flow-muted", JSON.stringify({ binding: receipt.binding, controller_protocol: receipt.controller_protocol, executor: receipt.executor, worker_source: receipt.worker_source, owner: receipt.owner }, null, 2))); section.append(details);
    }
    panel.append(section);
  }
  function renderEmailCorrection(panel, task, job) {
    const binding = job.email_correction_target;
    const history = job.email_corrections || [];
    if (!binding && !history.length) return;
    const section = node("section", "flow-condition"); section.id = "flow-email-correction";
    section.append(node("h4", "", "仅本岗位邮箱更正"), node("p", "flow-muted", "只更正当前岗位的邮箱。保存不改 PDF 或信息库，不恢复填写；更正记录不代替旧动作结论。"));
    if (history.length) {
      const latest = history[history.length - 1];
      section.append(node("p", "flow-source", `本岗位邮箱更正记录：${latest.value}。${job.email_correction_status === "queued" ? "已通过明确接管，曾排入本岗位一次性答案队列。排队记录不证明字段已回读、附件已核验或已进入原页复核阶段。" : "仅保存在本地，尚未排入填写器；继续前核对旧动作结论并明确接管。"}`));
      if (job.email_correction_readback?.source === "worker_verified_fill") section.append(node("p", "flow-source", `程序字段回读记录：此邮箱更正曾核验匹配（${new Date(job.email_correction_readback.at * 1000).toLocaleString()}）。来源：填写器核验。这是采集时刻的记录，不证明当前字段或附件状态。`));
      const details = node("details", "flow-details"); details.append(node("summary", "", "查看本岗位邮箱更正记录"));
      for (const item of history) details.append(node("p", "flow-muted", item.value));
      section.append(details);
    }
    if (binding) {
      const key = `${task.id}/${JSON.stringify(binding)}`;
      const form = node("form");
      const input = node("input"); input.type = "email"; input.required = true; input.maxLength = 254; input.autocomplete = "off"; input.setAttribute("aria-label", "仅本岗位的新邮箱"); input.value = emailCorrectionDrafts.get(key) || "";
      input.addEventListener("input", () => emailCorrectionDrafts.set(key, input.value));
      const save = button("记录本岗位邮箱更正", () => {}, "flow-save-email-correction", true); save.type = "submit";
      form.append(input, save);
      form.addEventListener("submit", event => {
        event.preventDefault();
        if (!input.value || !input.checkValidity()) return;
        workerAction("correct-email", { application_id: task.application_id, binding, value: input.value }, () => { emailCorrectionDrafts.delete(key); message("本岗位邮箱更正已记录。更正记录不代替旧动作结论；填写保持暂停。" ); });
      });
      section.append(form);
    }
    panel.append(section);
  }
  function renderFormDifferences(panel, task, job) {
    const current = job.form_state;
    if (current?.schema !== "form-state/v1" || !current.differences?.length) return;
    const section = node("section", "flow-condition"); section.id = "flow-form-differences";
    section.append(node("h4", "", "申请表差异 · 集中选择"), node("p", "flow-muted", "核对当前页面与已有资料，集中选择后保存。仅用于本次申请；保存后使用继续，在原页重新读取并补剩余步骤。最终 Submit 由你操作。"));
    const key = `${task.id}/${JSON.stringify(current.binding)}/${current.revision}`;
    const pending = formDifferenceDrafts.get(key) || {};
    const form = node("form");
    const controls = [];
    const show = value => value === undefined || value === null ? "来源未知" : typeof value === "string" ? value : JSON.stringify(value);
    for (const difference of current.differences) {
      const row = node("div", "flow-stage"); row.dataset.differenceId = difference.id;
      row.append(node("h5", "", `${difference.question || difference.field_id}${difference.important ? "（重要）" : ""}`), node("p", "", `当前页面：${show(difference.current_value)}`), node("p", "", `资料建议：${show(difference.proposed_value)}`), node("p", "flow-source", `来源：${show(difference.source)}`));
      if (Object.hasOwn(difference, "baseline_value") && JSON.stringify(difference.baseline_value) !== JSON.stringify(difference.current_value)) row.append(node("p", "flow-source", `进入时的值：${show(difference.baseline_value)}`));
      const select = node("select"); select.required = !!difference.important; select.setAttribute("aria-label", `${difference.question || difference.field_id}的差异选择`);
      for (const [value, label] of [["", "请选择处理方式"], ["keep", "保留当前页面"], ["use", "采用已有资料"], ["edit", "手动修改本次值"]]) { const option = node("option", "", label); option.value = value; select.append(option); }
      const saved = pending[difference.id] || (!current.choices?.[difference.id]?.expired && current.choices?.[difference.id]) || {};
      select.value = saved.action || "";
      const edit = node("textarea"); edit.maxLength = 20000; edit.setAttribute("aria-label", `${difference.question || difference.field_id}的手动值`); edit.value = saved.action === "edit" ? saved.value || "" : ""; edit.hidden = select.value !== "edit";
      const remember = () => { pending[difference.id] = { action: select.value, value: edit.value }; formDifferenceDrafts.set(key, pending); edit.hidden = select.value !== "edit"; };
      select.addEventListener("change", remember); edit.addEventListener("input", remember);
      row.append(select, edit); form.append(row); controls.push({ difference, select, edit });
      if (current.choices?.[difference.id] && !current.choices[difference.id].expired) row.append(node("p", "flow-source", "已记录本次选择；尚需继续时现场核对。"));
    }
    const save = button("保存本次集中选择", () => {}, "flow-save-form-differences", true); save.type = "submit";
    save.dataset.blocked = String(!job.page_current || !!job.intent || current.parser?.status !== "stable" || job.status === "cancelled" || !!job.manual_submission || !!job.handed_off);
    form.append(save);
    form.addEventListener("submit", event => { event.preventDefault(); if (save.dataset.blocked === "true") return; const choices = controls.filter(({ select }) => select.value).map(({ difference, select, edit }) => ({ difference_id: difference.id, action: select.value, ...(select.value === "edit" ? { value: edit.value } : {}) })); if (!choices.length) return; workerAction("resolve-form-differences", { application_id: task.application_id, binding: current.binding, revision: current.revision, choices }, () => { formDifferenceDrafts.delete(key); message("本次差异选择已保存。使用继续，在原页核对并补剩余步骤。"); }); });
    section.append(form); panel.append(section);
  }
  function renderWorkerRecovery(panel, task, job, state) {
    if (job.status === "ready_for_review") {
      const verified = job.observations?.filter(item => item.action === "draft_transport_verified").slice(-1)[0];
      panel.append(node("p", "flow-source", verified?.server_readback && verified.resume_sha256 === task.resume_sha256
        ? `填写完成时：${number(verified.required_field_count)} 个必填项已核验服务端保存，批准的 PDF 已挂接。最终 Submit 仍待你在原页面操作。`
        : "尚未取得与当前批准 PDF 一致的完整保存证据。请接管原页逐项核验。"));
    }
    const reasons = { email_correction_pending: "邮箱更正已记录，请核验后明确重新接管。", upload_result_unknown: "上传结果尚未核验，原动作已保留。", draft_result_unknown: "草稿保存结果尚未核验，原动作已保留。", action_result_unknown: "旧动作结果尚未核验。", page_closed: "原岗位页面已关闭。", page_crashed: "原岗位页面报告崩溃。", browser_disconnected: "浏览器连接已断开。", worker_restarted: "填写器已重启，原页需要重新核验。", file_changed: "批准的 PDF 文件发生变化。", handoff_unknown: "人工交接结果尚未核验。" };
    Object.assign(reasons, { form_differences: "当前页面与资料有差异，请集中选择本次处理方式。", awaiting_parser: "简历已上传，正在观察网站解析与页面稳定。", parser_unstable: "网站解析或人工修改尚未稳定，已暂停填写。", form_changed: "页面值发生变化，已保留现场，请核对当前差异。", form_validation_errors: "网站仍有必填或校验错误，请核对原页。" });
    reasons.manual_submit_required = "此操作会最终提交申请，请在原页面手动 Submit。";
    reasons.unverified_send_path = "尚不能确定此页面操作是否会最终提交，已保留原页，请核验。";
    const last = job.action_resolutions?.filter(item => item.intent_ref === job.intent_ref).slice(-1)[0];
    const resolved = !!job.intent && ["current_matches", "not_applied"].includes(last?.conclusion);
    const unresolved = !!job.intent && !resolved;
    const actionReason = ["email_correction_pending", "upload_result_unknown", "draft_result_unknown", "action_result_unknown"].includes(job.reason);
    if (resolved) panel.append(node("p", "flow-source", "旧结果已核验，待明确接管。填写保持暂停，原动作与核验记录仍保留。"));
    if (job.reason && !(resolved && actionReason)) panel.append(node("p", "flow-error", reasons[job.reason] || `填写已停止，原因：${job.reason}。请核验原记录、页面与资料。`));
    if (job.intent) {
      const action = { upload: "上传与附件挂接", fill: "字段保存", open: "打开原页" }[job.intent.action] || "旧动作";
      panel.append(node("p", "flow-muted", `${action} · ${job.intent_ref || "历史动作"}。${resolved ? "已有此动作的明确结论；重新接管仍需单独操作。" : "尚未取得明确结论，不视为成功或未发送，也不会自动重传。"}`));
      const evidence = node("details", "flow-details"); evidence.append(node("summary", "", "查看旧动作观察记录"));
      for (const event of job.observations || []) if (event.attempt_id === job.intent_ref) evidence.append(node("p", "flow-muted", [event.kind, event.stage, event.event, event.http_status ? `HTTP ${event.http_status}` : ""].filter(Boolean).join(" · ")));
      panel.append(evidence);
      const key = `${task.id}/${job.intent_ref}`;
      const saved = resolutionDrafts.get(key) || { conclusion: "", source: "" };
      const form = node("form", "flow-condition");
      const conclusion = node("select"); conclusion.required = true; conclusion.setAttribute("aria-label", "旧动作处理结论");
      for (const [value, text] of [["", "请选择核验结论"], ["current_matches", "当前结果已核验匹配"], ["not_applied", "有证据确认尚未应用"], ["manual_stop", "仍未知，保持停止并人工处理"]]) { const option = node("option", "", text); option.value = value; conclusion.append(option); }
      const source = node("textarea"); source.required = true; source.maxLength = 1000; source.setAttribute("aria-label", "旧动作核验来源"); source.placeholder = "当前页面、服务端草稿或人工检查的具体依据";
      conclusion.value = saved.conclusion; source.value = saved.source;
      const remember = () => resolutionDrafts.set(key, { conclusion: conclusion.value, source: source.value });
      conclusion.addEventListener("change", remember); source.addEventListener("input", remember);
      const save = button("保存旧动作核验结论", () => {}, null, true); save.type = "submit";
      form.append(conclusion, source, save);
      form.addEventListener("submit", event => { event.preventDefault(); remember(); if (!conclusion.value || !source.value.trim()) return; workerAction("resolve-action", { application_id: task.application_id, intent_ref: job.intent_ref, conclusion: conclusion.value, source: source.value.trim() }, () => resolutionDrafts.delete(key)); });
      panel.append(form);
      if (last) panel.append(node("p", "flow-source", `已记录结论：${{ current_matches: "当前结果匹配", not_applied: "已核验未应用", manual_stop: "未知，人工处理并停止" }[last.conclusion]}。${last.verified_by === "user" ? "人工核验" : "已记录的核验"}来源：${last.source}。恢复仍需明确操作。`));
    }
    const actions = node("div", "flow-actions");
    if (job.status === "ready_for_review" || (state.live_enabled && job.page_current && ["needs_input", "needs_recheck"].includes(job.status))) {
      actions.append(button("去原申请网站复核", async () => {
        workerAction("review", { application_id: task.application_id, ...(["needs_input", "needs_recheck"].includes(job.status) ? { acknowledge: true } : {}) });
      }, "flow-worker-review"));
    }
    if (job.handed_off) panel.append(node("p", "flow-muted", job.handoff?.status === "complete" ? "已交给你在原页面处理，自动填写已停止。最终 Submit 由你操作。" : "人工交接尚未核验，自动填写保持停止。"));
    if (!pipelineTask(task) && (job.status === "needs_recheck" || (job.handed_off && job.manual_intervention && !job.manual_submission))) {
      const reclaim = button("核验后重新接管", async () => {
        if (await confirmAction("请先核实投递历史、旧动作结论、岗位资料和原页附件。重新接管会允许自动层继续；不清楚提交结果时应保持停止。", "已核验，允许重新接管")) workerAction("recheck", { application_id: task.application_id, acknowledge: true, reclaim: !!job.handed_off, handoff_source: job.handed_off ? "用户已核验原页、旧动作与提交状态，并明确允许自动层接管。" : "" });
      }, "flow-worker-recheck", true); reclaim.dataset.blocked = String(unresolved); actions.append(reclaim);
    }
    if (job.sync_error) actions.append(button("核验后仅重试记录同步", async () => {
      try {
        const latest = (await api(`/api/applications/${encodeURIComponent(task.application_id)}`)).application;
        if (await confirmAction(`当前记录下一步：${latest.next_action || "未设置"}。待同步：${job.pending_sync || "原填写结果"}。只同步记录，不重复页面动作。`, "已核验，仅同步记录")) workerAction("retry-sync", { application_id: task.application_id, revision: latest.revision, acknowledge: true });
      } catch (error) { message(error.message, true); }
    }, "flow-worker-sync", true));
    if (job.page_open && (job.handed_off || job.status === "cancelled")) actions.append(button("关闭并释放原页", async () => {
      if (await confirmAction("关闭原招聘页面。网站未保存的内容可能丢失；原动作与核验记录仍保留。", "关闭原页面")) workerAction("release", { application_id: task.application_id });
    }, "flow-worker-release", true));
    if (job.status === "cancelled" && job.intent && last && ["current_matches", "not_applied"].includes(last.conclusion) && !job.page_open) actions.append(button("结算已取消的旧动作", async () => {
      if (await confirmAction("结算已核验的旧动作。岗位保持取消，自动填写不会恢复。", "结算旧动作")) workerAction("settle-cancelled", { application_id: task.application_id, intent_ref: job.intent_ref, acknowledge: true });
    }, "flow-worker-settle", true));
    if (!pipelineTask(task) && job.status !== "cancelled") actions.append(button("取消此岗位填写", async () => {
      if (await confirmAction("取消后停止后续填写，保留当前页面和待核验旧动作。", "取消填写")) workerAction("cancel-job", { application_id: task.application_id });
    }, "flow-worker-cancel", true));
    panel.append(actions);
  }
  function workerAction(operation, payload = {}, onSuccess = () => {}) {
    const task = flow?.active_task;
    if (!task?.worker_ref) return;
    return mutate(async () => {
      if (["resume", "recheck"].includes(operation)) await observeBeforeResume(task);
      await api("/api/flow/worker-action", { method: "POST", body: JSON.stringify({ task_id: task.id, task_revision: task.revision, operation, payload }) });
      if (operation === "resume") { ownsLease = true; lastHeartbeat = Date.now(); }
      if (["pause", "cancel-job", "review"].includes(operation)) ownsLease = false;
      onSuccess();
    }, { stopping: operation === "pause", scope: taskScope() });
  }
  function restartSavedHandoff(task) {
    return mutate(() => api("/api/flow/restart-existing-handoff", { method: "POST", body: JSON.stringify({
      task_id: task.id, task_revision: task.codex_handoff_restart?.origin_task_revision || task.revision,
    }) }), { scope: taskScope() });
  }
  function render() {
    const focused = document.activeElement;
    const focusArea = [current, automation].find(area => area.contains(focused));
    const focusedTask = focusArea?.dataset.taskId;
    const focusKey = focusArea && (focused.dataset.answerKey || focused.id || focused.getAttribute("aria-label"));
    const selection = focusKey && typeof focused.selectionStart === "number" ? [focused.selectionStart, focused.selectionEnd, focused.selectionDirection] : null;
    rendering = true;
    try {
      renderMode(); renderPipeline(); renderIntake(); renderSavedJobs(); renderBatchSelection(); renderMaterialBatch(); renderTask(); lock();
      if (focusKey && focusedTask === focusArea.dataset.taskId && !focused.isConnected) {
        const replacement = [...focusArea.querySelectorAll("input, textarea, select, button")].find(input => (input.dataset.answerKey || input.id || input.getAttribute("aria-label")) === focusKey);
        if (replacement && !replacement.disabled) { replacement.focus({ preventScroll: true }); if (selection) replacement.setSelectionRange(...selection); }
      }
      window.dispatchEvent(new CustomEvent("application-flow-state", { detail: { flow, pipeline, readable: { ...readable }, statusText: automation.querySelector('[role="status"]')?.textContent } }));
    }
    finally { rendering = false; }
  }
  async function refresh(reconcile = false) {
    if (observing || busy || !stateReady) return;
    observing = true; observe.disabled = true;
    try {
      const observations = await Promise.allSettled([
        api(selectedTask ? `/api/flow/${encodeURIComponent(selectedTask)}` : "/api/flow/state"), api("/api/recommendations/state"), api("/api/pipeline/state"),
      ]);
      readable.flow = observations[0].status === "fulfilled";
      readable.intake = observations[1].status === "fulfilled";
      readable.pipeline = observations[2].status === "fulfilled";
      let nextFlow = observations[0].status === "fulfilled" ? observations[0].value : flow;
      const nextIntake = observations[1].status === "fulfilled" ? observations[1].value : { ...intake, enabled: false, status: "unavailable", message: observations[1].reason.message };
      const nextPipeline = observations[2].status === "fulfilled" ? observations[2].value : pipeline;
      if (followingPipeline && nextPipeline?.active_task_id && selectedTask !== nextPipeline.active_task_id) {
        try {
          nextFlow = await api(`/api/flow/${encodeURIComponent(nextPipeline.active_task_id)}`);
          selectedTask = nextPipeline.active_task_id;
          readable.flow = true;
        } catch (error) { readable.flow = false; observations.push({ status: "rejected", reason: error }); }
      }
      flow = nextFlow; intake = nextIntake; pipeline = nextPipeline;
      if (readable.pipeline) for (const [key, requestId] of pipelineRequests) {
        if (!key.startsWith("{")) continue;
        const payload = JSON.parse(key);
        if (!payload.application_id && !payload.recommendation_id) continue;
        if (pipeline?.admission_requests?.some(receipt => receipt.request_id === requestId && Object.keys(receipt).length === Object.keys(payload).length + 1 && Object.entries(payload).every(([name, value]) => receipt[name] === value))) {
          pipelineRequests.delete(key); uncertainScopes.delete(admissionScope(payload));
          message("已核验岗位接纳记录，岗位已加入申请队列。");
        }
      }
      if (reconcile && readable.flow && readable.pipeline) {
        uncertainScopes.delete(taskScope()); uncertainScopes.delete(pipelineScope()); uncertainScopes.delete("pipeline");
        const job = flow?.worker?.jobs?.find(item => item.application_id === flow?.active_task?.application_id);
        for (const [key, draft] of answerDrafts) if (draft.taskId === flow?.active_task?.id && flow?.worker?.library?.some(record => {
          const scope = record.scope;
          return job && scope && typeof scope === "object" && !Array.isArray(scope) && record.state === "confirmed" && record.question === draft.question && record.value === draft.value
            && Object.entries(scope).every(([name, value]) => ["country", "company", "application_id"].includes(name) && typeof value === "string" && value.trim() && job[name] === value)
            && Object.entries(draft.payload.scope).every(([name, value]) => scope[name] === value);
        })) answerDrafts.delete(key);
        message("已读取持久状态。操作是否完成，以当前岗位和任务记录为准。");
      }
      render();
      const unavailable = observations.filter(observation => observation.status === "rejected");
      if (unavailable.length) message(unavailable.map(observation => observation.reason.message).join(" "), true);
    } catch (error) { message(`${error.message} 可重新读取状态。`, true); }
    finally { observing = false; observe.disabled = false; schedule(); }
    if (readable.flow && readable.pipeline && location.hash === "#flow") saveNextAnswer();
    if (ownsLease && !isUncertain() && !document.hidden && location.hash === "#flow" && flow?.worker?.control === "running" && flow.worker.controller === controller && Date.now() - lastHeartbeat > 4000) { lastHeartbeat = Date.now(); workerAction("heartbeat", { controller }); }
  }
  function schedule() {
    clearTimeout(timer);
    if (["flow", "overview"].includes(view)) timer = setTimeout(() => refresh(), 1200);
  }
  async function mutate(action, { stopping = false, scope = visibleScope(), domain = "flow" } = {}) {
    const fresh = domain === "application" ? stateReady : readable[domain] && (domain !== "pipeline" || readable.flow);
    if ((!stopping && (busy || isUncertain(scope) || !fresh)) || !stateReady) return;
    if (!stopping) busy = true;
    message(""); lock();
    try { await action(); }
    catch (error) {
      if (!error.status || error.status >= 500) uncertainScopes.add(scope);
      message(`${error.message}${uncertainScopes.has(scope) ? " 操作结果尚未核验。请读取最新状态，核对已保存记录后再继续。" : " 输入已保留，请核对最新状态。"}`, true);
    } finally { if (!stopping) busy = false; await loadState({ silent: true }); await refresh(); lock(); saveNextAnswer(); }
  }
  async function admit(payload) {
    const key = JSON.stringify(payload);
    if (!pipelineRequests.has(key)) pipelineRequests.set(key, crypto.randomUUID().replaceAll("-", ""));
    pipeline = await api("/api/pipeline/admit", { method: "POST", body: JSON.stringify({ request_id: pipelineRequests.get(key), ...payload }) });
    pipelineRequests.delete(key);
    message("已加入申请队列。当前岗位与运行状态保持，开启后按队列继续。");
  }
  async function createForApplication(id) {
    if (!flow?.mode) {
      flow = await api("/api/flow/state");
      if (!["application", "preparation"].includes(flow?.mode)) throw new Error("尚未核验工作台模式，请读取最新状态。");
    }
    if (flow?.mode === "application") {
      const existing = flow?.tasks?.find(task => task.application_id === id);
      if (existing) { followingPipeline = false; selectedTask = existing.id; return; }
    }
    const response = await api(`/api/applications/${encodeURIComponent(id)}`);
    if (response.application?.id !== id || !response.application?.revision) throw new Error("尚未取得岗位最新版本。");
    if (flow?.mode === "application") return admit({ application_id: id, application_revision: response.application.revision });
    const task = await api("/api/flow/create", { method: "POST", body: JSON.stringify({ application_id: id, application_revision: response.application.revision }) });
    selectedTask = task.id;
  }
  function selectRecommendation(row) {
    return mutate(async () => {
      if (flow?.mode === "application") return admit({ recommendation_id: row.id, recommendation_revision: row.revision });
      const result = await api("/api/recommendations/select", { method: "POST", body: JSON.stringify({ id: row.id, revision: row.revision }) });
      if (!result.application?.id) throw new Error("选岗结果不完整，请核验已保存记录。");
      await createForApplication(result.application.id);
    }, flow?.mode === "application" ? { scope: admissionScope({ recommendation_id: row.id }), domain: "pipeline" } : {});
  }
  async function openTask(id) { if (busy) return; followingPipeline = false; selectedTask = id; await refresh(); }
  function start(stage, retry = false) {
    const task = flow?.active_task;
    if (!task) return;
    return mutate(() => api("/api/flow/start", { method: "POST", body: JSON.stringify({ task_id: task.id, task_revision: task.revision, stage, ...(retry ? { retry: true } : {}) }) }));
  }
  window.addEventListener("flow-open", event => {
    const id = event.detail?.applicationId;
    if (typeof id === "string") mutate(() => createForApplication(id), { domain: "application", scope: flow?.mode === "preparation" ? `flow:${id}` : admissionScope({ application_id: id }) });
  });
  window.addEventListener("portal-state", () => { if (["flow", "overview"].includes(view)) refresh(); });
  window.addEventListener("hashchange", () => { if (["flow", "overview"].includes(view)) refresh(); else clearTimeout(timer); });
  window.addEventListener("beforeunload", event => { if (conditionDrafts.size || prismDrafts.size || latexBaseDrafts.size || answerDrafts.size || materialDrafts.size || materialTextDrafts.size || automaticSourceDrafts.size || resolutionDrafts.size || formDifferenceDrafts.size || uncertainScopes.size || busy) { event.preventDefault(); event.returnValue = ""; } });
  window.addEventListener("pagehide", () => {
    const task = flow?.active_task;
    if (ownsLease && task?.worker_ref && flow?.worker?.control === "running" && flow.worker.controller === controller) fetch("/api/flow/worker-action", { method: "POST", keepalive: true, headers: { "Content-Type": "application/json", "X-CSRF-Token": data.csrf_token }, body: JSON.stringify({ task_id: task.id, task_revision: task.revision, operation: "pause", payload: { controller } }) }).catch(() => {});
    ownsLease = false;
  });
  if (stateReady && ["flow", "overview"].includes(view)) refresh();
})();
