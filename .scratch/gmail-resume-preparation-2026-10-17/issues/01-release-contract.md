# 确定材料准备版范围、记录身份与验收契约

Type: task
Label: wayfinder:task
Status: closed
Closure reason: superseded
Completion: not-implemented-by-migration
Superseded by: [打开独立材料准备入口](02-preparation-only-runtime.md)、[确认筛选与生成政策](05-preference-grading-policy.md)
Priority: P0
Interaction: AFK
Assignee: none
Created: 2026-10-17
Parent: [交付 Gmail 岗位筛选与专用简历稳定版](../map.md)
Blocked by: 无

## Question

如何把已明确的 Gmail→筛选分级→专用简历目标，落实为共用的身份、阶段、输入版本与完成条件，供各工程票独立实现？

## Work and reuse

- 复用现有 recommendation、application、flow task 和 source revision；只定义必要批次引用，不另建数据库或任务框架。
- 区分推荐获取状态、岗位资格、材料优先级、任务阶段、材料审核；保留旧申请状态，不将生成材料写成已投递。
- 记录首版手动更新、现有邮件来源、最多20岗位串行分析及明确的续读边界；提案参数与用户已确认事实分开。

## Ownership

application_flow.py、application_intake.py 的共用契约及现有测试；必要时 CONTEXT.md、docs/single-job-flow.md。 多人执行时先协调共享文件；不得回退其他人的工作。

## Acceptance criteria

- [ ] 契约覆盖完整／部分／不可用读取、关键条件未知、明确冲突、材料不足、失败、取消与过期派生结果。
- [ ] 定义任务／批次防重键、JD／资料／规则／偏好／模型配置的失效边界，旧任务不被自动迁移或复活。
- [ ] 明确单模型任务中断结果未知时先核验，不承诺模型计费 exactly-once；不得隐式重跑。
- [ ] 验收矩阵和接口交接文档可供其他票复用；此票不代替偏好、人审或安装版验收。

## Verification and boundaries

先读[执行导航](../README.md)及依赖当前状态。共用约束见[地图](../map.md)、[开发约定](../../../CONVENTIONS.md)和[数据边界](../../../docs/data-boundaries.md)。源码、合成、安装、真实内容人审分别留证；无最终投递动作。该票只在后续明确领取后执行，本轮仅建票。

## Resolution comment

尚未领取或执行；此处不是完成结论。


## Comments

### 2026-10-17 — Administrative migration only

用户已批准23张纵向交付票及迁移。此票的工作由[打开独立材料准备入口](02-preparation-only-runtime.md)、[确认筛选与生成政策](05-preference-grading-policy.md)承接。仅行政关闭避免重复领取，不表示实现完成、通过验收或已取得用户接受；原Assignee保留。

[迁移前完整原文](../../tomorrowstar-ticket-consolidation-2026-10-17/history/pre-publication/.scratch/gmail-resume-preparation-2026-10-17/issues/01-release-contract.md) · [正式发布导航](../../tomorrowstar-ticket-consolidation-2026-10-17/README.md)。

不得因本票Status为closed将承接工作视为已完成；当前活动依赖全部改指承接票。真实申请继续暂停。
