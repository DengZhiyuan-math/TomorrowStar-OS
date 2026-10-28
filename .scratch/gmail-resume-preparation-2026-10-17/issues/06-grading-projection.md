# 查看单岗的解释性分级

Type: task
Label: wayfinder:task
Status: closed
Triage: done
Closure reason: completed
Completion: source-and-synthetic-verified
Policy version: preparation-policy/v1.0
Priority: P1
Interaction: AFK
Assignee: 01a14a95/root
Created: 2026-10-17
Updated: 2026-10-17
Parent: [交付 Gmail 岗位筛选与专用简历稳定版](../map.md)
Publication order: 05
Blocked by: [打开独立材料准备入口](02-preparation-only-runtime.md)、[确认筛选与生成政策](05-preference-grading-policy.md)

**What to build:** 用户对已有完整JD进行分析，在列表和详情查看匹配分、资格结论、当前进度和具体理由；首版不增加 A/B 字母等级。

## 当前契约定位 — 2026-10-20

保留解释性匹配分、要求和来源；未知资格不再普遍阻止简历生成，单个问题不拒绝整个分析，34/36承接。

当前产品规范与执行顺序分别见[单岗位流程](../../../docs/single-job-flow.md)和[统一开发计划](../../../docs/development-plan.md)。本票既有Status、Assignee、完成记录和收据不变；关闭仅证明当时范围，不证明新规范已实现。下方与现行规范冲突的旧审批、白名单、总时间窗及运行门槛保留为历史，由现有后继承接，不重开、不追认，也不据此执行真实申请。

## Acceptance criteria

- [x] 合成或已存在完整JD可从分析直达四项解释性展示，不依赖新增Gmail读取链。
- [x] 首版不增加 A/B 等级或新分档阈值；沿用已确认匹配公式，保留未知、来源依据及政策版本。
- [x] 资格、证据支持和偏好分别呈现；空要求、零分母、未知硬资格均不会被标成确认合适。
- [x] 人工调整保留原理由和资格冲突，不能删除或覆盖必要确认。
- [x] 政策、JD或资料变化只使相关分析失效；结果绑定实际输入版本。

## Standing boundaries

复用已有能力和已完成研究；每票形成可独立演示或验证的用户行为。先做本票必要的最小整理，不引入推测性框架。个人材料留私有；保持真实申请暂停、未知动作停止及人工最终Submit。规划发布不授权真实邮箱／模型／ATS执行。任何代码变更均需本切片的有效验证。

## Ownership

沿用票头Status和Assignee；本次仅发布，未领取或执行。先核对frontier并写入唯一领取人，再做工作；多人共享模块时协调，不回退其他人的改动。HITL必须由用户实际参与，不能由代理代答。

## Comments

### 2026-10-17 — Resolution: v1.0 single-job explanations verified

已有完整 JD 可直接分析，在岗位列表与单岗详情查看匹配分、资格结论、当前进度和具体理由。沿用 `documentary-match/v1` 原公式，显示支持分、未知区间、证据覆盖与来源，不增加 A/B 等级或新阈值。政策版本为 `preparation-policy/v1.0`。

默认按匹配分排序，可持久保存手动上移／下移；只改变顺序，不改分数、原理由、来源或资格说明。资格与文档匹配、偏好分别展示。空／损坏要求、未知或冲突的必需事实不能被标为确认合适，服务端同时阻止本岗简历生成。岗位、资料或政策变化保留历史解释并要求明确同步；单岗 JD 变化或读取失败不隐藏其他岗位。信息库／政策同步可保留仍适用的文档匹配，旧事实说明需重新绑定当前输入。

准备模式只读既有通用信息库，不初始化、迁移或启动旧 worker，不读取旧 run／owner。当前只自动核对已审核的单一法语／德语 CEFR 最低条件；复合条件、其他硬资格仍需适用事实说明，不声称已自动复用所有资格答案。电话等资料不会因此强制加入简历；自由格式偏好不被推断为新硬限制。

- [最终验证与源码指纹](../../single-job-explanations-2026-10-17/verification.json)：完整离线 **2294 passed / 204 deselected**，使用仓库默认排除规则；针对性 **110 passed**（含在完整离线内），新旧合成浏览器 **22 passed**。Ruff 检查、233 文件格式检查、JavaScript 语法和 diff 检查通过。
- [浏览器用户路径](../../../tests/test_job_explanation_browser.py)、[资格／排序／输入／历史与竞态](../../../tests/test_job_explanations.py)、[真实 loopback HTTP](../../../tests/test_job_explanations_http.py)、[信息库只读与保守核对](../../../tests/test_application_information.py)及[原生后端隔离](../../../tests/test_macos_portal.py)已验证。
- [独立审查与修复](../../single-job-explanations-2026-10-17/review.json)：修复资格更正期间仍采用旧简历的竞态；复合语言＋工作许可条件不能被单一语言事实误放行。最终复核无新增必改项。
- [领取前基线与本票变更](../../single-job-explanations-2026-10-17/README.md)已保存，17 项源码指纹在最终 gates 期间一致；原匹配公式与旧申请流程测试保持原字节。

本票关闭范围为源码与合成验证。真实邮箱／模型／岗位页面／ATS／上传／Submit 均为零，未启动真实 App、未替换安装版、未暂存或提交，真实申请继续暂停。后继「生成并审阅单岗简历草稿」解除本前置，但本轮不自动领取；安装版与真实人审验收保持独立。

### 2026-10-17 — Implementation claim

用户明确要求按 v1.0 完成本票的实现、验证和回写。已回读两个前置均真实完成，由 `01a14a95/root` 领取。使用已有完整 JD 或合成候选，从现有分析服务进入匹配分、资格结论、当前进度与具体理由展示；不增加 A/B 等级，不改匹配公式。人工调整不能抹掉原理由或资格冲突，结果绑定政策与实际输入版本。

本轮采用隔离合成信息库、假模型及本机测试；真实邮箱、模型、岗位页面、App、ATS、上传／Submit 和旧申请恢复均不执行。保留所有既有脏工作、私有目录及历史证据。

### 2026-10-17 — Display contract confirmed; implementation not started

[确认筛选与生成政策](05-preference-grading-policy.md)的 P8 是本票最终展示规则的决策来源；原票标题与路径保留，不能将“分级”继续实现为额外 A/B 评级。本次只更新契约，Status、Assignee 与依赖保持，不领取、不实现、不声明验证通过；真实申请继续暂停。

### 2026-10-17 — Approved ticket migration

用户已批准23张拆分及迁移。此票沿用原路径和身份，采用批准后的纵向交付契约；此前内容保存在不可覆盖的历史快照中，不丢失原问题、依赖、评论或验收记录。

- [批准的逐票草案](../../tomorrowstar-ticket-consolidation-2026-10-17/drafts/05-explainable-grading.md)。
- [迁移前完整原文](../../tomorrowstar-ticket-consolidation-2026-10-17/history/pre-publication/.scratch/gmail-resume-preparation-2026-10-17/issues/06-grading-projection.md)。
- [当前正式导航与全部承接关系](../../tomorrowstar-ticket-consolidation-2026-10-17/README.md)。

本次迁移不是实现完成或用户产品接受；真实申请继续暂停。
