# 阻止空选材简历并核验 PDF 输出质量

Type: task
Label: wayfinder:task
Status: closed
Closure reason: superseded
Completion: not-implemented-by-migration
Superseded by: [生成并审阅单岗简历草稿](08-source-bound-fact-findings.md)、[导出可信PDF并单独重试导出](09-draft-checkpoint-pdf-retry.md)
Priority: P1
Interaction: AFK
Assignee: none
Created: 2026-10-17
Parent: [交付 Gmail 岗位筛选与专用简历稳定版](../map.md)
Blocked by: [增加逐来源的简历事实变化提示](08-source-bound-fact-findings.md)、[保存已验证草稿并支持仅重试 PDF 导出](09-draft-checkpoint-pdf-retry.md)

## Question

怎样保证输出是有来源支持的岗位专用材料，而不是只有个人信息或版面不可读的成功文件？

## Work and reuse

- 空items／没有合适来源时给insufficient_material，不把PDF头有效当作内容完成。
- 沿用英文A4模板，验证文字可读、分页、长文本／链接／姓名、空白与裁切；不新做模板编辑器。
- 审阅内容与最终PDF分开，内部状态文字不泄漏，真实责任与scope保留。

## Ownership

application_resume.py、tests/test_application_resume.py 与必要合成PDF夹具；像素／文字验收留明确证据。 多人执行时先协调共享文件；不得回退其他人的工作。

## Acceptance criteria

- [ ] 空模型items和缺相关资料均不能发布成功的岗位专用简历。
- [ ] 合成输出覆盖长短材料、中英文姓名和长URL，PDF文字与渲染像素可核验。
- [ ] 使用真实headless renderer专项与mock测试分别报告；无法启动明确失败。
- [ ] 质量状态、finding与人工批准分开，最终字节绑定具体材料版本。

## Verification and boundaries

先读[执行导航](../README.md)及依赖当前状态。共用约束见[地图](../map.md)、[开发约定](../../../CONVENTIONS.md)和[数据边界](../../../docs/data-boundaries.md)。源码、合成、安装、真实内容人审分别留证；无最终投递动作。该票只在后续明确领取后执行，本轮仅建票。

## Resolution comment

尚未领取或执行；此处不是完成结论。


## Comments

### 2026-10-17 — Administrative migration only

用户已批准23张纵向交付票及迁移。此票的工作由[生成并审阅单岗简历草稿](08-source-bound-fact-findings.md)、[导出可信PDF并单独重试导出](09-draft-checkpoint-pdf-retry.md)承接。仅行政关闭避免重复领取，不表示实现完成、通过验收或已取得用户接受；原Assignee保留。

[迁移前完整原文](../../tomorrowstar-ticket-consolidation-2026-10-17/history/pre-publication/.scratch/gmail-resume-preparation-2026-10-17/issues/10-resume-output-quality.md) · [正式发布导航](../../tomorrowstar-ticket-consolidation-2026-10-17/README.md)。

不得因本票Status为closed将承接工作视为已完成；当前活动依赖全部改指承接票。真实申请继续暂停。
