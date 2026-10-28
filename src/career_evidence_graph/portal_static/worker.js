"use strict";

(() => {
  const root = document.getElementById("worker-root");
  const selected = new Set();
  const controller = crypto.randomUUID();
  const countries = { CHE: "瑞士", USA: "美国", GBR: "英国", DEU: "德国", FRA: "法国", CAN: "加拿大", OTHER: "其他（不跨国复用）" };
  const labels = { queued: "已就绪，等待执行", filling: "填写并核验", needs_input: "等待你补充", needs_recheck: "需要重新核验", ready_for_review: "等待人工复核", cancelled: "已取消" };
  const reasons = { page_capacity: "浏览器页面容量已满。请先处理并释放已有页面。", answer_changed: "已使用答案发生变化。请核验页面后重新接管。", worker_restarted: "worker 重启，页面草稿需要重新核验。", page_lost: "招聘页面已关闭。请核实是否已提交，再重新接管。", page_released: "复核页面已释放。如需继续，请先核验是否已提交。", missing_answers: "等待补充已确认答案。", file_changed: "简历文件已变更。请重新选择并准备批次。" };
  let state = { enabled: false, jobs: [], input_items: [], library: [] };
  Object.assign(reasons, { manual_submit_required: "此操作会最终提交申请，请在原页面手动 Submit。", unverified_send_path: "尚不能确定此页面操作是否会最终提交，已保留原页，请核验。", unsupported_structure: "表单标签、页面身份或控件结构不明确。请人工核验。", unsupported_attachments: "额外附件、多选或附件发送路径需要人工处理。" });
  Object.assign(reasons, { duplicate_application: "检测到相同岗位或缺少链接的同名历史记录。已暂停此岗位，请核对求职进度。", application_not_drafting: "原记录已进入投递或后续阶段，已停止自动填表。" });
  Object.assign(reasons, { draft_result_unknown: "草稿保存或附件挂接结果不明确。页面与当前操作已保留；请核验后再恢复，避免重复发送。", draft_result_unverified: "服务端返回错误，或保存结果与批准资料不一致。请核验当前页面，不自动重试。", draft_identity_changed: "岗位或表单身份发生变化。请重新核验岗位和页面。", ambiguous_option: "选项无法唯一对应已确认答案。请核验网站选项。", upload_result_unknown: "附件上传结果不明确。请先核验页面附件，不自动重传。", browser_result_unknown: "浏览器操作结果不明确。请核验当前页面后再恢复。" });
  Object.assign(reasons, { page_closed: "此岗位页面已关闭，请核验草稿和投递历史。其他岗位可继续。", page_crashed: "此岗位页面报告崩溃。未完成动作保持未知，其他岗位可继续。", page_command_failed: "此页面命令失败。请核验页面与交接结果；自动层保持停止。" });
  Object.assign(reasons, { context_closed: "浏览器 context 已关闭。批次停止，请新运行并核验旧进度。", browser_disconnected: "浏览器连接已断开。批次停止，请新运行并核验旧进度。", checkpoint_unavailable: "运行记录无法保存或核验。自动操作已停止，存储恢复后仍须核验并明确继续。" });
  Object.assign(reasons, { action_result_unknown: "旧动作尚未核验。请记录当前结果与来源，自动层不会重传。" });
  Object.assign(reasons, { unsupported_control: "当前控件需要人工选择。请定位原页并核验后处理。", cua_unavailable: "当前自动选择方式不可用。请定位原页并核验后处理。", route_change_forbidden: "已有动作记录，自动层不会更换执行方式重做。请核验并接管原页。" });
  Object.assign(reasons, { handoff_unknown: "人工交接结果未知。自动层保持停止，请核验页面与守卫状态。" });
  Object.assign(reasons, { recovered_result_not_visible: "已确认完成的动作在当前页面不可核验。请人工处理；自动层不会重复保存或上传。" });
  Object.assign(reasons, { recovery_order_unknown: "旧动作完成与处理结论的先后顺序无法确认。请人工核验并接管；自动层不会重复保存或上传。" });
  Object.assign(reasons, { recovery_completion_unbound: "旧完成证据没有可靠的动作绑定。请人工核验并接管；自动层不会重复保存或上传。" });
  Object.assign(reasons, { form_differences: "当前页面与资料有差异，请集中选择本次处理方式。", awaiting_parser: "简历已上传，正在观察网站解析与页面稳定。", parser_unstable: "网站解析或人工修改尚未稳定，已暂停填写。", form_changed: "页面值发生变化，已保留现场，请核对当前差异。", form_validation_errors: "网站仍有必填或校验错误，请核对原页。" });
  let busy = false, lastInputs = "", lastJobs = "", lastLibrary = "";
  const drafts = new Map();
  const receiptDrafts = new Map();
  const resolutionDrafts = new Map();
  const formDifferenceDrafts = new Map();

  function el(tag, text, className = "") { const e = document.createElement(tag); if (text) e.textContent = text; if (className) e.className = className; return e; }
  function button(text, action, primary = false) { const e = el("button", text, `button button-${primary ? "primary" : "secondary"}`); e.type = "button"; e.addEventListener("click", action); return e; }
  function field(label, input) { const e = el("label", label); e.append(input); return e; }
  function option(select, value, text) { const e = el("option", text); e.value = value; select.append(e); }
  function scopeLabel(scope) { if (!Object.keys(scope).length) return "全局基本事实"; return Object.entries(scope).map(([key, value]) => key === "country" ? `${countries[value] || value}` : key === "company" ? `公司：${value}` : "当前岗位").join(" · "); }
  function verifiedDraft(job) { return job.observations?.filter(o => o.action === "draft_transport_verified").pop(); }
  async function perform(operation, payload) {
    try {
      const next = await api(`/api/worker/${operation}`, { method: "POST", body: JSON.stringify(payload) });
      state = next; show(); return next;
    } catch (error) { toast(error.message); throw error; }
  }
  const apiControl = (operation) => perform(operation, { controller }).catch(() => {});

  const heading = el("div", "", "worker-heading");
  const title = el("div"); title.append(el("div", "AUTOMATION LAB · 自动化实验", "eyebrow"), el("h2", "集中补充，逐岗位复核"));
  const controls = el("div", "", "worker-buttons");
  const resume = button("开始／继续", () => apiControl("resume"), true);
  const pause = button("暂停批次", () => apiControl("pause"));
  const cancel = button("取消批次", async () => {
    if (await confirmAction("取消后停止后续自动处理。已填写内容和页面会保留。", "取消批次")) apiControl("cancel");
  });
  controls.append(resume, pause, cancel); heading.append(title, controls);
  const banner = el("p", "Lever / Greenhouse 本地合成预览：使用独立可见浏览器。选择并开始后，所选 PDF 与确认答案仅发送到隔离测试页面。真实 ATS 尚未启用，最终 Submit 由你操作。", "worker-banner");
  const progress = el("p", "", "worker-muted");
  const prep = el("div");
  const grid = el("div", "", "worker-grid");
  const left = el("section", "", "worker-column"); left.append(el("h3", "需要你补充"));
  const inputs = el("div"); left.append(inputs);
  const right = el("section", "", "worker-column"); right.append(el("h3", "岗位与简历"));
  const jobs = el("div"); right.append(jobs); grid.append(left, right);
  const library = el("details", "", "worker-library"); library.append(el("summary", "信息库 · 已确认答案"));
  const libraryItems = el("div"); library.append(libraryItems);
  root.append(heading, banner, progress, prep, grid, library);

  function show() {
    root.hidden = !state.enabled || location.hash !== "#applications";
    const pick = document.getElementById("worker-prepare-selection"); pick.hidden = !state.enabled;
    if (!state.enabled) return;
    banner.textContent = state.live_enabled
      ? state.generic_enabled
        ? "通用真实表单试运行：最多三个岗位。复用答案库，未知项等待你补充；未验证的自动保存和上传会暂停该岗位并保留页面。最终 Submit 由你操作。"
        : "Lever / Greenhouse 真实填表：最多三个岗位。开始后，确认答案及所选 PDF 可能发送至对应招聘站点。未知问题等待你补充；最终 Submit 由你操作。"
      : "Lever / Greenhouse 本地合成预览：使用独立可见浏览器。所选 PDF 与确认答案仅发送到隔离测试页面。最终 Submit 由你操作。";
    pick.textContent = `准备批量投递${selected.size ? `（${selected.size}）` : ""}`;
    const automatic = state.jobs.some(j => !j.manual_submission && (j.status === "queued" || (["filling", "needs_input"].includes(j.status) && !j.handed_off)));
    resume.disabled = !automatic || state.control === "running" || state.control === "cancelled";
    pause.disabled = state.control !== "running" || state.controller !== controller;
    cancel.disabled = !state.jobs.length || state.control === "cancelled" || (state.control === "running" && state.controller !== controller);
    if (automatic && state.controller && state.controller !== controller && state.control === "running") resume.disabled = false;
    const alive = state.runtime_status?.observation === "current";
    const runtimeLabels = { current: "当前运行，观察有效", stale: "观察过期，进程与页面状态未知", exited: `受管 worker 已退出，退出码 ${state.runtime_status?.exit_code}`, historical: "历史检查点，当前运行未知" };
    const runtimeLabel = runtimeLabels[state.runtime_status?.observation] || "当前运行未知";
    const child = state.process_observation;
    const startup = child && child.run_id !== state.runtime?.id ? ` · 最近启动的子进程${child.exit_code === null ? "仍在启动，运行版本未核验" : `已退出，退出码 ${child.exit_code}，未绑定当前版本`}` : "";
    const version = state.runtime ? ` · 运行 ${state.runtime.id.slice(0, 8)} · 启动版本 ${state.runtime.source.sha256.slice(0, 12)}${state.runtime_status?.source_matches_disk ? "" : "（磁盘源码已变化，须新运行加载）"}` : "";
    progress.textContent = `${state.control === "running" ? "批次运行中" : state.control === "cancelled" ? "批次已取消" : "批次已暂停"} · ${runtimeLabel}${version}${startup}${state.worker_error ? ` · ${state.worker_error === "control_connection_lost" ? "控制连接失联后已暂停" : (reasons[state.worker_error] || "运行异常，请查看本地运行记录")}` : ""}`;
    const inputKey = JSON.stringify(state.input_items);
    if (inputKey !== lastInputs) { lastInputs = inputKey; renderInputs(); }
    const jobKey = JSON.stringify([alive, state.control, state.jobs.map(j => [j.application_id, j.status, j.reason, j.filename, j.sync_error, j.handed_off, j.page_open, j.page_current, j.intent, j.intent_ref, j.action_resolutions, j.observations, j.handoff, j.questions, j.form_state, j.manual_submission, j.receipt, verifiedDraft(j)])]);
    if (jobKey !== lastJobs) { lastJobs = jobKey; renderJobs(); }
    const libraryKey = JSON.stringify(state.library);
    if (libraryKey !== lastLibrary && !libraryItems.contains(document.activeElement)) { lastLibrary = libraryKey; renderLibrary(); }
  }

  function renderInputs() {
    inputs.replaceChildren();
    if (!state.input_items?.length) { inputs.append(el("p", state.jobs.length ? "目前没有待补充问题。" : "先勾选求职进度中的岗位，生成并复核各岗位简历。", "worker-muted")); return; }
    for (const item of state.input_items) {
      const form = el("form", "", "worker-card"); form.dataset.inputId = item.id;
      form.append(el("h4", item.question), el("p", item.jobs.map(j => `${j.company} · ${j.role_title}`).join(" / "), "worker-muted"));
      const original = el("details"); original.append(el("summary", "查看网站原问题")); item.jobs.forEach(j => original.append(el("p", `${j.company}：${j.original_question}`))); form.append(original);
      const value = el(item.options.length ? "select" : "textarea"); value.required = true; value.setAttribute("aria-label", "已确认答案");
      if (item.options.length) { option(value, "", "请选择"); item.options.forEach(v => option(value, v, v)); }
      const saved = drafts.get(item.id) || {}; value.value = saved.value || "";
      form.append(field("你的答案", value));
      const scope = el("select"); option(scope, "default", `默认：${scopeLabel(item.scope)}`); option(scope, "job", "仅当前岗位的范围"); option(scope, "company", item.scope.country === "OTHER" ? "当前公司（国家未明确，仍限当前岗位）" : "仅当前公司的范围"); form.append(field("适用范围（只需修改例外）", scope));
      const only = el("input"); only.type = "checkbox"; form.append(field("仅本次，不保存到信息库", only));
      const target = el("select"); item.jobs.forEach(j => option(target, j.id, `${j.company} · ${j.role_title}`)); form.append(field("仅本次或岗位范围使用的岗位", target));
      scope.value = saved.scope || "default"; only.checked = Boolean(saved.only);
      if (item.jobs.some(j => j.id === saved.target)) target.value = saved.target;
      form.addEventListener("input", () => drafts.set(item.id, { value: value.value, scope: scope.value, only: only.checked, target: target.value }));
      form.addEventListener("change", () => drafts.set(item.id, { value: value.value, scope: scope.value, only: only.checked, target: target.value }));
      const submit = el("button", "确认并保存", "button button-primary"); submit.type = "submit"; form.append(submit);
      const error = el("p", "", "worker-error"); error.setAttribute("role", "status"); form.append(error);
      form.addEventListener("submit", async event => {
        event.preventDefault(); submit.disabled = true; error.textContent = "";
        const job = item.jobs.find(j => j.id === target.value); let finalScope = { ...item.scope };
        if (scope.value === "job") finalScope.application_id = job.id;
        if (scope.value === "company") { if (finalScope.country !== "OTHER") delete finalScope.application_id; finalScope.company = job.company; }
        try { await perform("answer", { application_id: job.id, question_id: job.question_id, value: value.value, scope: finalScope, only_this: only.checked }); drafts.delete(item.id); lastInputs = ""; show(); toast(`${only.checked ? "当前岗位答案已确认，不加入信息库。" : "答案已保存。"}${state.control === "paused" ? "批次仍暂停，请点击开始／继续。" : state.control === "running" ? "符合条件的等待岗位会自动恢复。" : "批次已取消，自动层保持停止。"}`); }
        catch (e) { error.textContent = e.message; } finally { submit.disabled = false; }
      }); inputs.append(form);
    }
  }

  function renderFormDifferences(card, job) {
    const current = job.form_state;
    if (current?.schema !== "form-state/v1" || !current.differences?.length) return;
    const form = el("form", "", "worker-card"); form.classList.add("worker-form-differences");
    form.append(el("h4", "申请表差异 · 集中选择"), el("p", "仅用于本次申请，不写回信息库。集中保存后点击继续，在原页重新读取并补剩余步骤。最终 Submit 由你操作。", "worker-muted"));
    const key = `${job.application_id}/${JSON.stringify(current.binding)}/${current.revision}`;
    const pending = formDifferenceDrafts.get(key) || {};
    const controls = [];
    const show = value => value === undefined || value === null ? "来源未知" : typeof value === "string" ? value : JSON.stringify(value);
    for (const difference of current.differences) {
      const row = el("div"); row.dataset.differenceId = difference.id;
      row.append(el("h5", `${difference.question || difference.field_id}${difference.important ? "（重要）" : ""}`), el("p", `当前页面：${show(difference.current_value)}`), el("p", `资料建议：${show(difference.proposed_value)}`), el("p", `来源：${show(difference.source)}`, "worker-muted"));
      if (Object.hasOwn(difference, "baseline_value") && JSON.stringify(difference.baseline_value) !== JSON.stringify(difference.current_value)) row.append(el("p", `进入时的值：${show(difference.baseline_value)}`, "worker-muted"));
      const select = el("select"); select.required = !!difference.important; select.setAttribute("aria-label", `${difference.question || difference.field_id}的差异选择`);
      for (const [value, label] of [["", "请选择处理方式"], ["keep", "保留当前页面"], ["use", "采用已有资料"], ["edit", "手动修改本次值"]]) option(select, value, label);
      const saved = pending[difference.id] || (!current.choices?.[difference.id]?.expired && current.choices?.[difference.id]) || {};
      select.value = saved.action || "";
      const edit = el("textarea"); edit.maxLength = 20000; edit.setAttribute("aria-label", `${difference.question || difference.field_id}的手动值`); edit.value = saved.action === "edit" ? saved.value || "" : ""; edit.hidden = select.value !== "edit";
      const remember = () => { pending[difference.id] = { action: select.value, value: edit.value }; formDifferenceDrafts.set(key, pending); edit.hidden = select.value !== "edit"; };
      select.addEventListener("change", remember); edit.addEventListener("input", remember);
      row.append(select, edit); form.append(row); controls.push({ difference, select, edit });
      if (current.choices?.[difference.id] && !current.choices[difference.id].expired) row.append(el("p", "已记录本次选择；尚需继续时现场核对。", "worker-muted"));
    }
    const save = el("button", "保存本次集中选择", "button button-primary"); save.type = "submit"; save.disabled = !job.page_current || !!job.intent || current.parser?.status !== "stable" || job.status === "cancelled" || !!job.manual_submission || !!job.handed_off;
    form.append(save);
    form.addEventListener("submit", async event => { event.preventDefault(); if (save.disabled) return; const choices = controls.filter(({ select }) => select.value).map(({ difference, select, edit }) => ({ difference_id: difference.id, action: select.value, ...(select.value === "edit" ? { value: edit.value } : {}) })); if (!choices.length) return; try { await perform("resolve-form-differences", { application_id: job.application_id, binding: current.binding, revision: current.revision, choices }); formDifferenceDrafts.delete(key); } catch {} });
    card.append(form);
  }

  function renderJobs() {
    for (const [id, draft] of resolutionDrafts) {
      if (!state.jobs.some(job => job.application_id === id && job.intent && job.intent_ref === draft.intent_ref)) resolutionDrafts.delete(id);
    }
    jobs.replaceChildren();
    for (const job of state.jobs) {
      const card = el("article", "", "worker-card"); card.dataset.jobId = job.application_id;
      const platform = { greenhouse: "Greenhouse", lever: "Lever", generic: "通用表单预检" }[job.platform] || job.platform;
      card.append(el("h4", `${job.company} · ${job.role_title}`), el("span", labels[job.status] || job.status, "worker-status"), el("p", `${platform} · ${countries[job.country]} · ${job.filename}`, "worker-muted"), el("p", `内容版本：${job.file_sha256.slice(0, 12)}`, "worker-muted"));
      if (job.workflow) card.append(el("p", job.workflow === "precision" ? "人工精准投递 · 单岗位" : "批量投递", "worker-muted"));
      if (job.reason) card.append(el("p", reasons[job.reason] || "执行已停止，请核验原记录、页面和附件。", "worker-muted"));
      const lastResolution = job.action_resolutions?.filter(r => r.intent_ref === job.intent_ref).pop();
      const unresolved = Boolean(job.intent && (!lastResolution || lastResolution.conclusion === "manual_stop"));
      const originalPage = job.page_current && job.reason !== "page_crashed";
      const evidence = el("section", "", "worker-evidence"); evidence.setAttribute("role", "region"); evidence.setAttribute("aria-label", "证据与下一步");
      evidence.append(el("p", "本地记录：简历与岗位的版本绑定已保留。", "worker-muted"));
      evidence.append(el("p", job.reason === "page_crashed" ? "页面状态：原页已报告崩溃；保留故障记录，先核验旧动作与投递历史。" : originalPage ? `页面状态：当前受管原页。${["needs_input", "needs_recheck"].includes(job.status) ? "已停在当前问题处，等待人工核验。" : ""}` : job.page_open ? "页面状态：历史记录；原页是否仍可用尚未核验。" : "页面状态：当前没有可定位的原页。", "worker-muted"));
      const routeDecision = job.observations?.filter(o => o.action === "route_decision" && o.stage === "fill").pop();
      if (!job.intent && ["unsupported_control", "cua_unavailable"].includes(job.reason) && routeDecision?.dispatch === "not_sent") evidence.append(el("p", "本轮未发出新的字段动作。请在原页人工核验。", "worker-muted"));
      const nextStep = job.manual_submission ? (job.receipt ? "查看已记录的接收来源。" : "记录已核验的接收来源。")
        : job.status === "cancelled" ? "自动层保持停止；核验旧动作与投递历史。"
        : unresolved ? (originalPage ? "定位原页，核验故障点并记录具体结论与来源；自动层保持停止。" : "核对投递历史与旧动作结果，记录具体结论与来源；自动层保持停止。")
        : job.sync_error ? "核验原记录变化后仅同步；不重做浏览器动作。"
        : job.status === "needs_recheck" ? (originalPage ? "在原页核验故障点与资料，再明确重新接管。" : "核对投递历史、草稿和资料；新运行不证明原页面已恢复。")
        : job.status === "needs_input" ? "补充已确认答案；也可定位原页核验。"
        : job.status === "ready_for_review" ? "接管原页并复核；最终提交由你操作。"
        : state.control === "paused" ? "点击开始／继续；保存答案不会恢复暂停批次。" : "等待自动核验；最终提交由你操作。";
      evidence.append(el("p", `下一步：${nextStep}`)); card.append(evidence);
      renderFormDifferences(card, job);
      if (job.intent) {
        const action = { open: "打开页面", fill: "字段保存", upload: "上传及附件挂接" }[job.intent.action] || job.intent.action;
        card.append(el("p", `${action}结果待核验。操作 ${job.intent.attempt_id?.slice(0, 8) || "历史记录"}；未取得最终检查点不能视为成功，也不能视为未发送。自动层不会重传。`, "worker-error"));
        const facts = el("details"); facts.append(el("summary", "查看已观察传输事实"));
        for (const event of job.observations.filter(o => o.attempt_id === job.intent_ref && o.stage)) facts.append(el("p", `${event.kind || action} · ${event.stage}${event.http_status ? ` · HTTP ${event.http_status}` : ""}`, "worker-muted"));
        card.append(facts);
        const resolution = el("form");
        const conclusion = el("select"); conclusion.required = true; option(conclusion, "", "请选择具体处理结论");
        option(conclusion, "current_matches", "当前结果已核验匹配"); option(conclusion, "not_applied", "已有证据核验未应用"); option(conclusion, "manual_stop", "仍未知，人工处理并保持停止");
        const source = el("input"); source.required = true; source.maxLength = 1000;
        const saved = resolutionDrafts.get(job.application_id) || {};
        conclusion.value = saved.conclusion || ""; source.value = saved.source || "";
        const remember = () => resolutionDrafts.set(job.application_id, { intent_ref: job.intent_ref, conclusion: conclusion.value, source: source.value });
        resolution.addEventListener("input", remember); resolution.addEventListener("change", remember);
        resolution.append(field("动作处理结论", conclusion), field("核验来源（当前页面、服务端草稿或人工检查）", source));
        const save = el("button", "保存核验结论", "button button-secondary"); save.type = "submit"; resolution.append(save);
        resolution.addEventListener("submit", async event => {
          event.preventDefault(); save.disabled = true; remember();
          const submitted = resolutionDrafts.get(job.application_id);
          try {
            await perform("resolve-action", { application_id: job.application_id, ...submitted });
            if (resolutionDrafts.get(job.application_id) === submitted) resolutionDrafts.delete(job.application_id);
            lastJobs = ""; show();
          } catch {} finally { save.disabled = false; }
        });
        card.append(resolution);
        const last = job.action_resolutions?.filter(r => r.intent_ref === job.intent_ref).pop();
        if (last) card.append(el("p", `已记录结论：${last.conclusion === "current_matches" ? "当前结果匹配" : last.conclusion === "not_applied" ? "已核验未应用" : "人工处理，自动层保持停止"} · 来源：${last.source}。${job.status === "cancelled" ? "结算须先释放页面，岗位仍保持取消。" : "恢复仍须核验输入并明确继续。"}`, "worker-muted"));
        if (job.status === "cancelled" && last && ["current_matches", "not_applied"].includes(last.conclusion)) {
          card.append(el("p", job.page_open ? "请先关闭并释放页面，再结算已取消岗位。" : "旧动作已核验，可结算已取消岗位。结算不会恢复执行或收回人工所有权。", "worker-muted"));
          if (!job.page_open) card.append(button("结算已取消岗位", async () => {
            if (await confirmAction("结算已核验的旧动作并保留历史。岗位仍保持取消，批次不会恢复执行。", "确认结算")) perform("settle-cancelled", { application_id: job.application_id, intent_ref: job.intent_ref, acknowledge: true }).catch(() => {});
          }));
        }
      }
      const verified = verifiedDraft(job);
      if (job.status === "ready_for_review" && verified?.server_readback && verified.resume_sha256 === job.file_sha256) card.append(el("p", `自动填表完成时：${verified.required_field_count} 个必填项已核验服务端保存，批准 PDF 已挂接。最终提交待你操作。`, "worker-muted"));
      if (job.handed_off && !job.manual_submission) card.append(el("p", job.handoff?.status === "complete" ? "已转为人工处理，自动填写已停止。" : job.handoff?.status === "pending" ? "已停止自动填写，人工交接正在处理。" : "人工交接结果未知，自动层保持停止。", "worker-muted"));
      if (job.page_open && !job.page_current) card.append(el("p", "页面状态来自上次记录。worker 未连接，尚未核验页面是否仍打开。", "worker-error"));
      if (job.sync_error) card.append(el("p", "原记录同步未完成。浏览器结果已保留。", "worker-error"), button("仅重试同步", () => perform("retry-sync", { application_id: job.application_id }).catch(() => {})), button("核验冲突后同步", async () => {
        try {
          const latest = (await api(`/api/applications/${job.application_id}`)).application;
          if (await confirmAction(`原记录已变更。当前下一步：${latest.next_action || "未设置"}。准备写回：${job.pending_sync}。确认后只同步记录，不重复浏览器动作。`, "已核验，同步记录")) await perform("retry-sync", { application_id: job.application_id, revision: latest.revision, acknowledge: true });
        } catch (e) { toast(e.message); }
      }));
      const actions = el("div", "", "worker-buttons");
      if (state.live_enabled && originalPage && !job.handed_off && ["needs_input", "needs_recheck"].includes(job.status)) actions.append(button("定位原页并核验", async () => {
        if (await confirmAction("定位停在故障点的原页面，并交由你核验。worker 保持停止，不重新打开、刷新或重传。核验后再明确允许自动层接管。", "定位原页并人工核验")) perform("review", { application_id: job.application_id, acknowledge: true }).catch(() => {});
      }));
      if (job.status === "ready_for_review" && !job.manual_submission) actions.append(button(job.handed_off ? "定位复核页面" : "接管并复核", () => perform("review", { application_id: job.application_id }).catch(() => {}), true));
      if (job.handed_off && !job.manual_submission) actions.append(button("我已人工提交", async () => {
        if (await confirmAction("请确认你已在招聘页面完成最终提交。这一步只记录你的确认，不代表已核验招聘方接收。", "确认已人工提交")) perform("submitted", { application_id: job.application_id, acknowledge: true }).catch(() => {});
      }));
      if (job.manual_submission) card.append(el("p", job.receipt ? "已记录人工提交，并保存用户核验的接收来源。" : "已记录人工提交，等待接收证据。", "worker-muted"));
      if (job.manual_submission && !job.receipt) {
        const form = el("form"); const locator = el("input"); locator.type = "text"; locator.required = true; locator.maxLength = 1000; locator.value = receiptDrafts.get(job.application_id) || "";
        locator.addEventListener("input", () => receiptDrafts.set(job.application_id, locator.value));
        form.append(field("已核验的确认页、邮件或回执来源", locator)); const submit = el("button", "记录已核验接收", "button button-secondary"); submit.type = "submit"; form.append(submit);
        form.addEventListener("submit", async event => { event.preventDefault(); submit.disabled = true; try { await perform("receipt", { application_id: job.application_id, locator: locator.value }); receiptDrafts.delete(job.application_id); } catch {} finally { submit.disabled = false; } }); card.append(form);
      }
      if (job.status === "needs_recheck" || (job.handed_off && job.manual_intervention && !job.manual_submission)) {
        const recheck = button("核验后重新接管", async () => {
        if (await confirmAction("请先核实是否已提交、笔记版本和附件。重新接管后 worker 可以改写页面；不清楚提交结果时请取消该岗位。", "已核实，重新接管")) perform("recheck", { application_id: job.application_id, acknowledge: true, reclaim: Boolean(job.handed_off), handoff_source: job.handed_off ? "用户已核验人工交接与提交状态，并明确允许自动层接管" : "" }).catch(() => {});
        });
        recheck.disabled = unresolved; actions.append(recheck);
      }
      if (job.page_open && (job.handed_off || job.status === "cancelled")) actions.append(button("关闭并释放页面", async () => { if (await confirmAction("关闭该招聘页面。未由网站保存的表单内容可能丢失。", "关闭页面")) perform("release", { application_id: job.application_id }).catch(() => {}); }));
      if (job.status !== "cancelled") actions.append(button("取消此岗位", () => perform("cancel-job", { application_id: job.application_id }).catch(() => {})));
      card.append(actions); jobs.append(card);
    }
  }

  function renderLibrary() {
    libraryItems.replaceChildren();
    for (const record of state.library || []) {
      const form = el("form", "", "worker-card");
      form.append(el("h4", record.question), el("p", `${scopeLabel(record.scope)} · ${record.state === "confirmed" ? "已确认" : "已撤回"}`, "worker-muted"));
      const value = el("input"); value.type = "text"; value.value = record.value || ""; value.required = true; form.append(field("修改答案", value));
      const scope = el("select"); const choices = new Map([[JSON.stringify(record.scope), scopeLabel(record.scope)], ["{}", "全局基本事实"]]);
      for (const [code, label] of Object.entries(countries)) choices.set(JSON.stringify({ country: code }), label);
      for (const job of state.jobs) choices.set(JSON.stringify({ ...record.scope, application_id: job.application_id }), `仅岗位：${job.company}`);
      for (const [s, label] of choices) option(scope, s, label); scope.value = JSON.stringify(record.scope); form.append(field("适用范围", scope));
      const save = el("button", "确认修改", "button button-secondary"); save.type = "submit"; form.append(save);
      form.append(button("撤回", async () => {
        const revision = await revisionOf(record);
        perform("library", { key: record.key, revision, withdraw: true }).catch(() => {});
      }));
      form.addEventListener("submit", async event => { event.preventDefault(); save.disabled = true; try { await perform("library", { key: record.key, revision: await revisionOf(record), value: value.value, scope: JSON.parse(scope.value) }); } catch {} finally { save.disabled = false; } }); libraryItems.append(form);
    }
  }
  async function revisionOf(record) {
    // The backend supplies its own canonical revision; browser key ordering is irrelevant.
    return record.content_revision;
  }

  function prepareSelection(precisionId = null) {
    const precision = typeof precisionId === "string";
    for (const application of data.applications) {
      if (selected.has(application.id) && application.screening?.batch_preparable !== true) selected.delete(application.id);
    }
    const targets = data.applications.filter(a => precision ? a.id === precisionId && a.screening?.precision_preparable : selected.has(a.id));
    if (!targets.length) { toast("请先在岗位详情保存分流，再选择批量或单独精准准备。"); return; }
    prep.replaceChildren(); const form = el("form", "", "worker-card"); form.append(el("h3", precision ? "人工精准投递 · 单岗位准备" : "批量投递 · 确认每岗位简历"));
    const precisionReview = el("input"); precisionReview.type = "checkbox"; precisionReview.required = true;
    if (precision) form.append(el("p", "先核对关键 JD 要求与相关贡献，针对该岗位调整简历。按机会需要准备内推、联系人或申请材料，然后确认交给填写助手。"));
    const bindings = [];
    for (const application of targets) {
      const row = el("div"); row.append(el("h4", `${application.company} · ${application.role_title}`), el("p", application.url, "worker-muted"));
      const country = el("select"); option(country, "", "请选择申请国家"); Object.entries(countries).forEach(([code, label]) => option(country, code, label)); country.required = true;
      const file = el("input"); file.type = "file"; file.accept = ".pdf"; file.required = true;
      const binding = { application, country, file };
      row.append(field("申请国家", country), el("p", "请从单岗位 LaTeX 材料流程生成并核验 PDF，再在此选择该文件。", "worker-muted"), field("PDF 简历（最大 700 KB）", file));
      form.append(row); bindings.push(binding);
    }
    if (precision) form.append(field("我已人工复核 JD、相关证据和该岗位的定制简历", precisionReview));
    const submit = el("button", precision ? "确认精准准备 · 随后辅助填写" : "准备批次 · 随后开始填写及上传", "button button-primary"); submit.type = "submit"; form.append(submit);
    const error = el("p", "", "worker-error"); error.setAttribute("role", "status"); form.append(error);
    form.addEventListener("submit", async event => {
      event.preventDefault(); submit.disabled = true; error.textContent = "";
      try {
        const payload = [];
        for (const binding of bindings) {
          const file = binding.file.files[0]; if (!file || file.size > 700000) throw new Error("请逐岗位选择不超过 700 KB 的 PDF 简历。");
          const bytes = new Uint8Array(await file.arrayBuffer()); let binary = ""; for (const byte of bytes) binary += String.fromCharCode(byte);
          payload.push({ application_id: binding.application.id, revision: binding.application.revision, country: binding.country.value, filename: file.name, file_base64: btoa(binary) });
        }
        await perform("prepare", { jobs: payload, workflow: precision ? "precision" : "batch", precision_reviewed: precision && precisionReview.checked }); prep.replaceChildren(); toast("申请已准备。点击开始后填写并上传所选资料。");
      } catch (e) { error.textContent = e.message; } finally { submit.disabled = false; }
    }); prep.append(form); root.hidden = false; root.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  window.WorkerPreview = { enabled: false, selected, preparePrecision: prepareSelection, select(id, checked) { checked ? selected.add(id) : selected.delete(id); show(); } };
  document.getElementById("worker-prepare-selection").addEventListener("click", () => prepareSelection());
  window.addEventListener("hashchange", show);
  window.addEventListener("pagehide", () => {
    if (state.control === "running" && state.controller === controller) fetch("/api/worker/pause", { method: "POST", keepalive: true, headers: { "Content-Type": "application/json", "X-CSRF-Token": data.csrf_token }, body: JSON.stringify({ controller }) }).catch(() => {});
  });
  async function poll() {
    if (busy || !stateReady) return; busy = true;
    try {
      const next = await api("/api/worker/state"); const changed = next.enabled !== window.WorkerPreview.enabled;
      const noteChanged = JSON.stringify(state.jobs?.map(j => j.revision)) !== JSON.stringify(next.jobs?.map(j => j.revision));
      state = next; window.WorkerPreview.enabled = next.enabled; if (changed) renderApplications();
      if (noteChanged && next.enabled) loadState({ silent: true });
      if (next.enabled) {
        show();
        if (next.control === "running" && next.controller === controller) await perform("heartbeat", { controller });
      }
    } catch (error) {
      state.runtime_status = { ...state.runtime_status, observation: "stale" };
      state.jobs.forEach(job => { job.page_current = false; });
      show();
      progress.textContent = `${error.message} 当前运行无法核验，页面状态来自上次记录。失联宽限后停止新自动动作；重连后请核验并手动继续。`;
    }
    finally { busy = false; }
  }
  window.addEventListener("focus", poll);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) poll(); });
  setInterval(poll, 1500); poll();
})();
