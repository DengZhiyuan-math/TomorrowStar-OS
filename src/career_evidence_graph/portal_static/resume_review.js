"use strict";

let prismReviewState = null;
let prismSelectedVersion = null;
let prismReviewRequest = 0;
let prismSourceRequest = 0;
let prismCaptureBusy = false;

let prismReviewLoading = false;
let prismReviewCheckError = null;
let prismReviewActionError = null;

async function loadPrismReview() {
  if (prismCaptureBusy || prismReviewLoading) return;
  prismReviewLoading = true;
  const request = ++prismReviewRequest;
  try {
    const state = await api("/api/resume-review/state");
    if (request !== prismReviewRequest) return;
    const previous = prismReviewState;
    prismReviewState = state;
    prismReviewCheckError = null;
    if (!previous || previous.enabled !== state.enabled ||
        JSON.stringify(previous.versions) !== JSON.stringify(state.versions) ||
        JSON.stringify(previous.latest) !== JSON.stringify(state.latest)) renderPrismReview();
    else updatePrismReviewStatus();
  } catch (error) {
    if (request !== prismReviewRequest) return;
    prismReviewCheckError = `自动检查暂不可用，将继续重试。${error.message}`;
    if ($("prism-review-message")) updatePrismReviewStatus();
    else $("resume-review-root").replaceChildren(node("p", "notice", prismReviewCheckError));
  } finally { prismReviewLoading = false; }
}

function updatePrismReviewStatus() {
  const state = prismReviewState;
  const message = $("prism-review-message");
  if (!state?.enabled || !message) return;
  const parts = [prismReviewCheckError, prismReviewActionError, state.error?.message].filter(Boolean);
  if (state.status === "needs_recheck") parts.push("上次读取结果尚未核验，请先核验原尝试。当前版本与历史均保留。");
  if (state.source_changed) parts.push("Prism 源已变化。检测到 Prism 已保存新改动，请接回新版本；当前仍显示原快照。");
  if (!parts.length) parts.push("自动检测已开启。读取只保存待审阅快照，不确认材料，也不授权填写、上传或提交。");
  const text = parts.join(" ");
  if (message.textContent !== text) message.textContent = text;
  const capture = $("prism-review-capture");
  capture.disabled = prismCaptureBusy || !state.live_source_revision || state.status === "needs_recheck";
  $("prism-review-refresh").disabled = prismCaptureBusy;
  $("prism-review-reconcile").hidden = state.status !== "needs_recheck";
  $("prism-review-reconcile").disabled = prismCaptureBusy;
  const live = $("prism-review-live");
  live.hidden = !state.live_source_revision;
  const revision = state.live_source_revision || "";
  const summary = `当前已保存 LaTeX：${revision.slice(0, 12)}`;
  if ($("prism-review-source-summary").textContent !== summary) $("prism-review-source-summary").textContent = summary;
  if ($("prism-review-source-revision").textContent !== revision) $("prism-review-source-revision").textContent = revision;
}

function checkVisiblePrismReview() {
  if (stateReady && !document.hidden && location.hash === "#resume-review") loadPrismReview();
}
window.setInterval(checkVisiblePrismReview, 3000);
window.addEventListener("focus", checkVisiblePrismReview);
document.addEventListener("visibilitychange", checkVisiblePrismReview);

function renderPrismReview() {
  const root = $("resume-review-root");
  const state = prismReviewState;
  const heading = node("div", "page-heading");
  const intro = node("div", "");
  intro.append(node("div", "eyebrow", "LATEX RESUME REVIEW"), node("h1", "", "简历审阅（Prism）"), node("p", "", "在 Prism 编辑并保存，再将 LaTeX 与对应 PDF 接回这里。真实申请继续暂停。"));
  heading.append(intro);
  root.replaceChildren(heading);
  if (!state?.enabled) {
    root.append(node("p", "notice", "此服务未启用独立简历审阅。请使用已更新的安装版 App。"));
    return;
  }
  const actions = node("div", "prism-review-actions");
  const refresh = node("button", "button button-quiet", "检查源文件变化");
  refresh.id = "prism-review-refresh";
  refresh.addEventListener("click", loadPrismReview);
  const editor = node("button", "button button-quiet", "在 Prism 编辑");
  editor.addEventListener("click", async () => {
    editor.disabled = true;
    try {
      const result = await api("/api/resume-review/editor", { method: "POST", body: "{}" });
      const link = node("a", "button button-quiet", "打开 Prism 编辑器 ↗");
      link.href = result.editor_url; link.target = "_blank"; link.rel = "noopener noreferrer";
      editor.replaceWith(link);
      link.click();
    } catch (error) { editor.disabled = false; message.textContent = error.message; }
  });
  const capture = node("button", "button button-primary", prismCaptureBusy ? "正在读取并核验…" : "读取最新 LaTeX 并核验 PDF");
  capture.disabled = prismCaptureBusy || !state.live_source_revision || state.status === "needs_recheck";
  capture.id = "prism-review-capture";
  capture.addEventListener("click", () => prismReadback("capture", {}));
  actions.append(editor, refresh, capture);
  const reconcile = node("button", "button button-quiet", "核验上次读取结果");
  reconcile.id = "prism-review-reconcile";
  reconcile.addEventListener("click", () => prismReadback("reconcile", {}));
  actions.append(reconcile);
  const message = node("p", "notice prism-review-notice", "");
  message.id = "prism-review-message";
  message.setAttribute("role", "status");
  root.append(actions, node("p", "", "自动检测已开启：每 3 秒检查已保存的简历，返回此页时立即检查。接回时会在本机严格编译并保存独立版本；未保存的编辑不会被读取。"), message);
  const live = node("details", "prism-review-digests"); live.id = "prism-review-live";
  const summary = node("summary", "", ""); summary.id = "prism-review-source-summary";
  const revision = node("code", "", ""); revision.id = "prism-review-source-revision";
  live.append(summary, revision); root.append(live);
  updatePrismReviewStatus();
  const versions = state.versions || [];
  if (!versions.length) {
    root.append(node("p", "panel", "尚未接回审阅版本。请先在 Prism 保存简历，再点击读取。"));
    return;
  }
  if (!versions.some((version) => version.id === prismSelectedVersion)) prismSelectedVersion = state.latest?.id || versions[0].id;
  const label = node("label", "prism-review-history", "审阅版本 ");
  const select = document.createElement("select"); select.setAttribute("aria-label", "选择审阅版本");
  for (const version of versions) {
    const option = document.createElement("option");
    option.value = version.id;
    option.textContent = `${version.created_at} · ${version.source_revision.slice(0, 12)}${version.id === state.latest?.id ? " · 最近接回" : " · 历史"}`;
    select.append(option);
  }
  select.value = prismSelectedVersion;
  select.addEventListener("change", () => { prismSelectedVersion = select.value; renderPrismReview(); });
  label.append(select); root.append(label);
  const version = versions.find((item) => item.id === prismSelectedVersion);
  const banner = node("section", "panel prism-review-version");
  banner.append(node("h2", "", `当前审阅：${version.main} · ${version.source_revision.slice(0, 12)}`), node("p", "", `快照 ${version.id} · 接回时间 ${version.created_at} · ${version.page_count} 页 · 待人工审阅`));
  const details = node("details", "prism-review-digests"); details.append(node("summary", "", "核对完整版本与文件摘要"));
  for (const [title, value] of [["LaTeX 项目版本", version.source_revision], ["主文件 SHA-256", version.source_sha256], ["PDF SHA-256", version.pdf_sha256]]) {
    details.append(node("p", "", title), node("code", "", value));
  }
  banner.append(details); root.append(banner);
  const pair = node("div", "prism-review-pair");
  const sourcePanel = node("section", "panel prism-review-source");
  sourcePanel.append(node("h3", "", `LaTeX 源快照 · ${version.main}`));
  const source = node("pre", "", "正在读取此版本源文件…"); sourcePanel.append(source);
  const pdfPanel = node("section", "panel prism-review-pdf");
  const pdfURL = `/api/resume-review/versions/${encodeURIComponent(version.id)}/pdf`;
  const pdfLink = node("a", "button button-quiet", "单独打开此版 PDF ↗"); pdfLink.href = pdfURL; pdfLink.target = "_blank"; pdfLink.rel = "noopener";
  const frame = document.createElement("iframe"); frame.title = `审阅 PDF · ${version.id}`; frame.src = pdfURL;
  pdfPanel.append(node("h3", "", "对应 PDF 快照"), pdfLink, frame);
  pair.append(sourcePanel, pdfPanel); root.append(pair);
  const request = ++prismSourceRequest;
  fetch(`/api/resume-review/versions/${encodeURIComponent(version.id)}/source`, { credentials: "same-origin", cache: "no-store" }).then(async (response) => {
    if (!response.ok) throw new Error("此版本源文件不能核验，请保留记录。");
    const text = await response.text();
    if (request === prismSourceRequest) source.textContent = text;
  }).catch((error) => { if (request === prismSourceRequest) source.textContent = error.message; });
}

async function prismReadback(action, payload) {
  if (prismCaptureBusy) return;
  prismCaptureBusy = true;
  prismReviewActionError = null;
  ++prismReviewRequest;
  renderPrismReview();
  try {
    if (action === "capture") {
      const fresh = await api("/api/resume-review/state");
      prismReviewState = fresh;
      if (!fresh.live_source_revision || fresh.status === "needs_recheck") throw new Error(fresh.error?.message || "当前源或上次读取结果尚未核验，请保留原版本。");
      payload = { source_revision: fresh.live_source_revision };
    }
    const state = await api(`/api/resume-review/${action}`, { method: "POST", body: JSON.stringify(payload) });
    prismReviewState = state; prismSelectedVersion = state.latest?.id || null;
  } catch (error) {
    try { prismReviewState = await api("/api/resume-review/state"); } catch { /* Keep the displayed prior version. */ }
    prismReviewActionError = error.message;
  } finally { prismCaptureBusy = false; renderPrismReview(); }
}
