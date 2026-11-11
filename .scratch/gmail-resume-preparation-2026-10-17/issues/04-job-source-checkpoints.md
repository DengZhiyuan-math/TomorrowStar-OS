# 将候选转成可核验的完整岗位

Type: task
Label: wayfinder:task
Status: closed
Triage: done
Closure reason: completed
Completion: source-and-synthetic-verified
Priority: P0
Interaction: AFK
Assignee: 01a14a95/job_source
Created: 2026-10-17
Updated: 2026-10-17
Parent: [交付 Gmail 岗位筛选与专用简历稳定版](../map.md)
Publication order: 04
Blocked by: [打开独立材料准备入口](02-preparation-only-runtime.md)

**What to build:** 用户从已有或新推荐候选进入岗位详情，取得完整JD、来源与获取状态，失败可逐岗继续。

## Acceptance criteria

- [x] 用现有结构化候选或合成候选独立演示，不等待新增Gmail分页实现。
- [x] 一封邮件多岗位逐项处理；跨页跨邮件同岗合并来源，保存逐岗位获取进度。
- [x] 原JD、公司岗位身份、原始来源、获取时间与完整性状态可查看；登录墙、摘要和错岗不能冒充全文。
- [x] 单岗失败不丢其他岗位；继续或保存结果未知时保留待核验，不盲目重取。
- [x] 列出确有普通HTTP缺口的来源证据；无此缺口时不强制引入浏览器。

## Standing boundaries

复用已有能力和已完成研究；每票形成可独立演示或验证的用户行为。先做本票必要的最小整理，不引入推测性框架。个人材料留私有；保持真实申请暂停、未知动作停止及人工最终Submit。规划发布不授权真实邮箱／模型／ATS执行。任何代码变更均需本切片的有效验证。

## Ownership

沿用票头Status和Assignee；本次仅发布，未领取或执行。先核对frontier并写入唯一领取人，再做工作；多人共享模块时协调，不回退其他人的改动。HITL必须由用户实际参与，不能由代理代答。

## Comments

### 2026-10-17 — Resolution: source and synthetic job acquisition verified

已有结构化候选可独立取得完整 JD，无需新增 Gmail 页。每岗先写 pending，再保存页面回执，最后发布岗位结果。完整结果复用，已知失败须明确逐岗重试；保存结果未知保留 needs_recheck，重开后也不得盲目取源或选择，只有本地回执核验可以继续。

邮件内多岗位全部保留，跨页／跨邮件追加来源，已证明重定向才合并身份。后来的空候选或摘要不能覆盖完整 JD、公司岗位和原来源。详情可查看原 JD、公司岗位、来源 URL、获取时间、完整性及错误。登录墙、摘要、错岗、缺身份或明确截断不能标为 full；选岗再次核验捕获，单岗失败不丢其他结果。

- [最终验证与源码指纹](../../gmail-source-continuation-2026-10-17/verification.json)：完整离线 **2209 passed / 200 deselected**；受影响 **374 passed**（包含在完整离线内）；新旧合成浏览器 **18 passed**。Ruff、JavaScript 语法、diff 和文档链接检查通过。
- [逐岗持久化反例](../../../tests/test_application_recommendations.py)、[来源完整性与身份](../../../tests/test_application_job_source.py)、[独立候选／未知保存整合](../../../tests/test_intake_continuation.py)及[逐岗界面流程](../../../tests/test_intake_continuation_browser.py)均已验证。
- [HTTP 缺口证据清单](../../gmail-source-continuation-2026-10-17/source-gaps.json)区分既有安装验收观察到的 unknown／login 页面与本轮 401／403、登录／验证页、失效、服务错误和响应限制的合成反例。没有新鲜真实来源预检，不声称任何当前具体站点必需浏览器；本票不引入浏览器取源。后继只读来源票须先选择有当前证据的具体来源。
- [独立审查及修正](../../gmail-source-continuation-2026-10-17/review.json)已回读；重定向合并不再丢续队列，保留全文时也保留原 mail_url 和来源字段。

本票关闭范围为源码与合成验收。真实邮箱／模型／岗位页面／ATS／上传／最终 Submit 均为零，安装版未改，真实申请继续暂停。没有 commit、暂存或远端写入。完整材料批次仍等待可信 PDF 前置，政策、安装版和真实人审门槛保持独立。

### 2026-10-17 — Implementation claim

用户明确要求本轮完成 Gmail 续读与完整岗位取源两票，覆盖本图默认单票会话限制。已确认材料入口前置 closed；由 `01a14a95/job_source` 领取本票。采用合成邮件、页面与假连接器完成实现和验收，不执行真实邮箱、模型、ATS、申请或上传。

### 2026-10-17 — Approved ticket migration

用户已批准23张拆分及迁移。此票沿用原路径和身份，采用批准后的纵向交付契约；此前内容保存在不可覆盖的历史快照中，不丢失原问题、依赖、评论或验收记录。

- [批准的逐票草案](../../tomorrowstar-ticket-consolidation-2026-10-17/drafts/04-complete-job-source.md)。
- [迁移前完整原文](../../tomorrowstar-ticket-consolidation-2026-10-17/history/pre-publication/.scratch/gmail-resume-preparation-2026-10-17/issues/04-job-source-checkpoints.md)。
- [当前正式导航与全部承接关系](../../tomorrowstar-ticket-consolidation-2026-10-17/README.md)。

本次迁移不是实现完成或用户产品接受；真实申请继续暂停。
