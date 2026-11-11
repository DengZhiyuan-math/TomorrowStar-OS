# 提供候选分级与简历集中审核工作台

Type: task
Label: wayfinder:task
Status: closed
Closure reason: superseded
Completion: not-implemented-by-migration
Superseded by: [打开独立材料准备入口](02-preparation-only-runtime.md)、[在推荐列表中继续读取Gmail](03-gmail-incremental-paging.md)、[将候选转成可核验的完整岗位](04-job-source-checkpoints.md)、[查看单岗的解释性分级](06-grading-projection.md)、[生成并审阅单岗简历草稿](08-source-bound-fact-findings.md)、[导出可信PDF并单独重试导出](09-draft-checkpoint-pdf-retry.md)、[完成可暂停的多岗位材料批次](07-bounded-batch-orchestration.md)
Priority: P1
Interaction: AFK
Assignee: none
Created: 2026-10-17
Parent: [交付 Gmail 岗位筛选与专用简历稳定版](../map.md)
Blocked by: [提供不启动填写器的材料准备入口](02-preparation-only-runtime.md)、[保存逐岗位获取进度并核验完整 JD](04-job-source-checkpoints.md)、[实现独立于投递平台的岗位分级与排序](06-grading-projection.md)、[串联有界多岗位分析与简历生成队列](07-bounded-batch-orchestration.md)、[阻止空选材简历并核验 PDF 输出质量](10-resume-output-quality.md)

## Question

如何在现有App内让用户看清整批推荐、等级理由、待确认事项及每份简历版本，并控制下一步？

## Work and reuse

- 复用现有原文／改写、使用／未使用来源和PDF预览；展示推荐来源、全文状态、资格、等级和材料阶段。
- 提供明确的更新／继续读取、选择生成范围、暂停／继续／仅重试失败项；默认主流程没有填写入口。
- 集中展示待补事实，已确认事实按适用范围复用，避免逐字段重复弹窗。

## Ownership

portal_static/application_flow.js、现有CSS、career_portal.py的HTTP展示衔接及现有浏览器／HTTP测试。 多人执行时先协调共享文件；不得回退其他人的工作。

## Acceptance criteria

- [ ] 待确认、失败、资料过期、已生成待审核与已批准互不混淆；剩余读取范围可见。
- [ ] PDF与差异预览对应当前岗位及具体版本，切换候选不串用草稿或确认。
- [ ] 用户能定位并处理单项异常，不需Terminal或复制任务去外部聊天。
- [ ] 代表性窗口尺寸可操作，长理由可读；界面审阅不能代替真实简历内容验收。

## Verification and boundaries

先读[执行导航](../README.md)及依赖当前状态。共用约束见[地图](../map.md)、[开发约定](../../../CONVENTIONS.md)和[数据边界](../../../docs/data-boundaries.md)。源码、合成、安装、真实内容人审分别留证；无最终投递动作。该票只在后续明确领取后执行，本轮仅建票。

## Resolution comment

尚未领取或执行；此处不是完成结论。


## Comments

### 2026-10-17 — Administrative migration only

用户已批准23张纵向交付票及迁移。此票的工作由[打开独立材料准备入口](02-preparation-only-runtime.md)、[在推荐列表中继续读取Gmail](03-gmail-incremental-paging.md)、[将候选转成可核验的完整岗位](04-job-source-checkpoints.md)、[查看单岗的解释性分级](06-grading-projection.md)、[生成并审阅单岗简历草稿](08-source-bound-fact-findings.md)、[导出可信PDF并单独重试导出](09-draft-checkpoint-pdf-retry.md)、[完成可暂停的多岗位材料批次](07-bounded-batch-orchestration.md)承接。仅行政关闭避免重复领取，不表示实现完成、通过验收或已取得用户接受；原Assignee保留。

[迁移前完整原文](../../tomorrowstar-ticket-consolidation-2026-10-17/history/pre-publication/.scratch/gmail-resume-preparation-2026-10-17/issues/12-candidate-material-workspace.md) · [正式发布导航](../../tomorrowstar-ticket-consolidation-2026-10-17/README.md)。

不得因本票Status为closed将承接工作视为已完成；当前活动依赖全部改指承接票。真实申请继续暂停。
