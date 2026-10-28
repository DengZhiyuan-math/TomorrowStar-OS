# 完成可暂停的多岗位材料批次

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
Publication order: 08
Blocked by: [在推荐列表中继续读取Gmail](03-gmail-incremental-paging.md)、[将候选转成可核验的完整岗位](04-job-source-checkpoints.md)、[导出可信PDF并单独重试导出](09-draft-checkpoint-pdf-retry.md)

**What to build:** 用户选择有界推荐批次，逐岗分析与生成材料，在同一工作台查看阶段、暂停、继续和失败。

## 当前契约定位 — 2026-10-20

保留逐岗串行与断点；取消固定总轮cap/时间窗、逐材料批准及手填application_record才能下一岗，34/37按明确提交结果或skip推进。

当前产品规范与执行顺序分别见[单岗位流程](../../../docs/single-job-flow.md)和[统一开发计划](../../../docs/development-plan.md)。本票既有Status、Assignee、完成记录和收据不变；关闭仅证明当时范围，不证明新规范已实现。下方与现行规范冲突的旧审批、白名单、总时间窗及运行门槛保留为历史，由现有后继承接，不重开、不追认，也不据此执行真实申请。

## Acceptance criteria

- [x] 读取链、分级链及单岗草稿/PDF链从实际用户入口贯通；沿用确认后的批次与生成政策。
- [x] 明确未提交的单岗故障或资格待补充不阻塞其他可处理岗位；保存原因与进度，待处理故障岗仅手动重试，提交／外部动作结果未知时先停止核验。
- [x] 重复点击、晚返回和A→B→A输入变化不复活旧结果；所有候选都有可解释的当前处置。
- [x] 集中审核逐岗绑定正确JD、资料、草稿、PDF及审核版本；默认不启动填写器。

## Standing boundaries

复用已有能力和已完成研究；每票形成可独立演示或验证的用户行为。先做本票必要的最小整理，不引入推测性框架。个人材料留私有；保持真实申请暂停、未知动作停止及人工最终Submit。规划发布不授权真实邮箱／模型／ATS执行。任何代码变更均需本切片的有效验证。

## Ownership

沿用票头Status和Assignee；本次仅发布，未领取或执行。先核对frontier并写入唯一领取人，再做工作；多人共享模块时协调，不回退其他人的改动。HITL必须由用户实际参与，不能由代理代答。

## Comments

### 2026-10-17 — Resolution: pausable serial material batch verified under policy v1.0

用户明确勾选有限候选后创建暂停批次；复用现有 Gmail 读取、完整岗位取源、解释性分级、草稿审阅和独立 PDF 导出。创建、刷新、重开均不自动开始工作。复用原有存储、锁与串行队列，最多一个活动岗位；排序沿用已有匹配分和手动调整，未知分数保持未知，不加 A/B 等级。

每岗依次分析、生成草稿、明确审阅、导出并确认具体 PDF。材料完成进入 `waiting_application_record` 并暂停，不自动开始下一岗、不修改真实申请状态、不假报完成投递或记录。完整“生成→投递→记录→下一岗”仍由独立申请流程衔接，本票没有为绕过暂停而增加虚假记录入口。

已知未提交故障、必需资格缺失／冲突、明确其他简历语言要求、岗位原文未完整取得，均保存原因和进度并隔离该岗，允许其他可处理岗位继续。岗位原文继续使用已有取源入口；待处理故障仅由用户手动重试恢复。未知外部结果使批次停止，取消、资格修改或新建任务均不能绕过核验；原始回执的只读核验绑定本次尝试、草稿及输入。已核验尝试归档后，后续未知尝试使用独立绑定。

集中审核逐岗保留正确 JD、资料、草稿、PDF 和审阅版本。重复请求、晚返回、输入 A→B→A、暂停和重启均有版本与历史保护；不采用旧任务结果，不覆盖与推荐内容冲突的既有岗位，不恢复已有非草稿申请，不构造自动填写 worker。

- [最终验证](../../material-batch-2026-10-17/verification.json)：完整离线 **2430 passed / 219 deselected**，沿用默认排除规则；针对性 **24 passed**，包含于完整离线；浏览器 **39 passed / 72 deselected**，其中新增7条批次路径及保留32条既有路径。Ruff检查、248文件格式、JS语法和diff检查通过。
- [独立审查](../../material-batch-2026-10-17/review.json)发现并修复未知结果通过取消／资格变更／新任务绕过、重启恢复投影及连续两次未知导出的问题，最终无未解决阻断。
- [冻结源码](../../material-batch-2026-10-17/source-manifest.json)12项在最终验证期间未变；[既有测试与读取链](../../material-batch-2026-10-17/preserved-baseline.json)12项保持原字节。[原 PDF 契约](../../material-batch-2026-10-17/retained-pdf-contract.json)保持，未修改模板、renderer或此前两页A4质量证据；本票合成PDF传输夹具仅验证编排。
- [证据说明](../../material-batch-2026-10-17/README.md)保留RED、原始失败及修复后验证。[本轮浏览器启动事件](../../material-batch-2026-10-17/observed-browser-startup-failure.json)对应用户所贴测试Chrome崩溃，后续隔离测试通过；不据此声称安装版或旧故障已修复。

**关闭范围：** 源码及隔离合成验证完成。安装、真实样本和真实简历人审保持后继门槛；真实申请继续暂停。没有私人资料读取、真实邮箱／模型／岗位／ATS操作、上传、Submit、旧申请恢复、App启动、安装替换、Git提交或远端写入。本次只关闭本票，不领取后继票。

### 2026-10-17 — Implementation claim under policy v1.0

用户明确要求完成本票实现、验证和回写；唯一前置03／04／09均已closed，由 `01a14a95/root` 领取。政策以已定稿 `preparation-policy/v1.0` 为准，历史待确认评论保留。

批次只选择本次明确勾选的有限候选，复用既有读取、取源、分析、草稿及独立PDF链；最多推进一个岗位。资格待补充或已知失败保存原因与进度，故障仅手动重试；未知外部结果先核验。已完成材料不等于已投递或已完成申请闭环，不预生成整批简历，真实申请继续暂停。

验证使用隔离合成资料、loopback与假模型／邮箱／取源回调；不读取私人信息库或真实邮箱、不调用真实模型／岗位／ATS、不上传或Submit、不启动TomorrowStar App或替换安装版、不恢复旧申请、不提交Git或写远端。保存已有脏工作与封存证据，仅关闭本票源码及合成验证范围；安装和真实人审保持后继门槛。

### 2026-10-17 — Manual retry and failure distinction confirmed

[确认筛选与生成政策](05-preference-grading-policy.md)的 P6、P11 持有延期处置与手动重试的详细决定；验收项已据此区分明确未提交的故障和未知外部结果。P4、P5 持有逐岗顺序与匹配优先决定。整体政策待最终汇总确认；本轮只同步契约，Status、Assignee 与依赖保持，不领取、不实施、不恢复真实申请。

### 2026-10-17 — Policy contract update pending implementation

用户在[确认筛选与生成政策](05-preference-grading-policy.md)的 P4 明确采用“生成一岗 → 投递一岗 → 记录结果 → 完成后下一岗”。该处是决定的唯一详细记录。本票原“整批分析／生成”的行为须在开工前按该政策重新核对，不能预生成所有岗位；材料阶段与完整申请闭环分别验收。本轮不领取、不实施本票，不恢复真实申请；排序、失败／跳过边界与整体政策仍在 HITL 确认中。

### 2026-10-17 — Approved ticket migration

用户已批准23张拆分及迁移。此票沿用原路径和身份，采用批准后的纵向交付契约；此前内容保存在不可覆盖的历史快照中，不丢失原问题、依赖、评论或验收记录。

- [批准的逐票草案](../../tomorrowstar-ticket-consolidation-2026-10-17/drafts/08-bounded-material-batch.md)。
- [迁移前完整原文](../../tomorrowstar-ticket-consolidation-2026-10-17/history/pre-publication/.scratch/gmail-resume-preparation-2026-10-17/issues/07-bounded-batch-orchestration.md)。
- [当前正式导航与全部承接关系](../../tomorrowstar-ticket-consolidation-2026-10-17/README.md)。

本次迁移不是实现完成或用户产品接受；真实申请继续暂停。
