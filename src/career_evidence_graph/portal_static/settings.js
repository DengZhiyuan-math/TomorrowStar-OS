"use strict";
// 2026-11-16 (user request): one page for the settings the App already reads. Each
// section saves on its own; mail and automatic-flow options apply after the App reopens.

let settingsLoading = false;

function settingsField(label, input, hint) {
  const field = node("label", "settings-field");
  field.append(node("span", "settings-label", label), input);
  if (hint) field.append(node("small", "settings-hint", hint));
  return field;
}

function settingsSection(title, available, body, save, note) {
  const panel = node("section", "panel settings-panel");
  panel.append(node("h2", "", title));
  if (!available) {
    panel.append(node("p", "settings-hint", "当前环境不可用。"));
    return panel;
  }
  const status = node("p", "settings-status");
  status.setAttribute("role", "status");
  const button = node("button", "button button-primary", "保存");
  button.type = "button";
  button.addEventListener("click", async () => {
    button.disabled = true; status.textContent = "正在保存…"; status.classList.remove("is-error");
    try {
      const result = await api("/api/settings", { method: "POST", body: JSON.stringify(save()) });
      status.textContent = result.restart_required ? "已保存。重新打开 App 后生效。" : "已保存，立即生效。";
      renderSettings(result, false);
    } catch (error) {
      status.textContent = error.message; status.classList.add("is-error");
    } finally { button.disabled = false; }
  });
  panel.append(...body);
  if (note) panel.append(node("p", "settings-hint", note));
  const actions = node("div", "settings-actions");
  actions.append(button, status);
  panel.append(actions);
  return panel;
}

function renderSettings(settings, replace = true) {
  const root = $("settings-root");
  const executor = node("select");
  for (const [value, label] of [["codex", "Codex"], ["claude", "Claude（Chrome 扩展）"]]) {
    const option = node("option", "", label); option.value = value; executor.append(option);
  }
  executor.value = settings.fill_executor.value;

  const thresholds = settings.score_thresholds.value;
  const skip = node("input"); skip.type = "number"; skip.min = "0"; skip.max = "99"; skip.value = thresholds.skip_below;
  const manual = node("input"); manual.type = "number"; manual.min = "1"; manual.max = "100"; manual.value = thresholds.manual_from;
  const defaults = settings.score_thresholds.default;

  const companies = node("textarea"); companies.rows = 6;
  companies.value = settings.target_companies.value.join("\n");

  const mail = settings.mail_and_flow.value;
  const label = node("input"); label.type = "text"; label.value = mail.application_processed_label;
  label.placeholder = "例如 Jobs/已处理";
  const takeover = node("input"); takeover.type = "checkbox"; takeover.checked = mail.automatic_takeover;
  const takeoverField = node("label", "settings-check");
  takeoverField.append(takeover, node("span", "", "自动接管：脚本无法继续的页面交给填表执行者"));
  const claude = node("input"); claude.type = "text"; claude.value = mail.match_second_opinion_claude_config;
  claude.placeholder = "例如 ~/.claude-STOA";

  const sections = [
    settingsSection("填表执行者", settings.fill_executor.available, [
      settingsField("由谁在 Chrome 里填写申请表", executor, "选择 Claude 需要先设置下方的 Claude 配置目录；Codex 用量用完时也会自动改用 Claude。"),
    ], () => ({ fill_executor: executor.value }), "从下一个开始填写的岗位起生效。"),
    settingsSection("匹配分门槛", settings.score_thresholds.available, [
      settingsField("低于此分自动跳过", skip),
      settingsField("达到此分转为手动准备", manual, `默认 ${defaults.skip_below} 和 ${defaults.manual_from}；两者之间的岗位自动生成材料并填写。`),
    ], () => ({ score_thresholds: { skip_below: Number(skip.value), manual_from: Number(manual.value) } }), "从下一次匹配起生效，已匹配的岗位不变。"),
    settingsSection("目标公司", settings.target_companies.available, [
      settingsField("每行一个公司名", companies, "目标公司的岗位会单独标出并排在前面。"),
    ], () => ({ target_companies: companies.value.split("\n").map(name => name.trim()).filter(Boolean) })),
    settingsSection("邮件与自动流程", settings.mail_and_flow.available, [
      settingsField("Gmail 已处理标签", label, "留空时只收录邮件，不加标签也不归档。"),
      takeoverField,
      settingsField("第二评分模型（Claude 配置目录）", claude, "留空时只用一个模型评分；Claude 填表也使用这个配置。"),
    ], () => ({ mail_and_flow: { application_processed_label: label.value, automatic_takeover: takeover.checked, match_second_opinion_claude_config: claude.value } }), "这三项在重新打开 App 后生效。"),
  ];
  if (!replace && root.childElementCount) {
    // Swap values in place so the saved section keeps its status message.
    sections.forEach((section, index) => {
      const old = root.children[index];
      const status = old?.querySelector(".settings-status")?.textContent;
      if (status) section.querySelector(".settings-status").textContent = status;
    });
  }
  root.replaceChildren(...sections);
}

async function loadSettings() {
  if (settingsLoading) return;
  settingsLoading = true;
  try { renderSettings(await api("/api/settings")); }
  catch (error) { $("settings-root").replaceChildren(node("p", "notice is-error", error.message)); }
  finally { settingsLoading = false; }
}

if (location.hash === "#settings") loadSettings();
