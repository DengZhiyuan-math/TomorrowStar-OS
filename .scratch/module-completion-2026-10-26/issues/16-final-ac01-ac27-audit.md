# MC-16：最终 AC01–AC27 证据审计与整体验收

Type: verification
Label: wayfinder:task
Status: open
Priority: P2
Interaction: AFK
Assignee: none
Created: 2026-10-26
Parent: [Module 剩余开发地图](../map.md)
Blocked by: [MC-09](09-t10-synthetic-chain.md), [MC-12](12-t11-real-ats.md), [MC-15](15-m6-ui-compatibility-identity.md), [MC-19](19-narrow-flow-resume-surface.md)
Triage: dependency-pending

## 问题与范围

逐条对照最终实现建立 AC01–AC27 证据矩阵，并完成新快照全量验证和独立标准/需求审计。可先只读整理已有证据；未完前置或外部层未验不能关闭整票。

## 文件所有权与并行边界

最终证据矩阵、现有测试/审查记录和正式状态文档；验收期间所有受验 src/tests/config 冻结，其他票不得并行改动同一快照。审计发现交所属实现票，修复后只重验必要范围并生成新基线。

共享文件按地图的冲突规则协调；领取后才能写入。不得覆盖其他工作的修改。
依赖边表示必要交付，不表示外部运行授权；测试记录中的 deselected 不抵充覆盖。

## 验收条件

- [ ] 每条 AC 对应实际新 Interface/消费者、通过/未验/不适用理由、准确来源及证据层，不用方法存在或 R6 绿测关闭后来新功能。
- [ ] 最终同一源码完整默认离线与相关隔离浏览器清单精确覆盖，分组无重/漏，skip/失败/中断保留；离线与浏览器顺序执行。
- [ ] 标准与需求独立审计的实质问题已修复并闭环；真实模型/GUI/ATS 各层单列，未验项保持未验。
- [ ] 核对 MC-10–12 的真实分层证据适用于最终候选；后续装配、配置、入口、工具或运行身份变化影响原证明时补验相应层，不把历史 closed 状态当作当前候选通过。
- [ ] 核对所有本轮票与 M1–M6/T06–T11 的状态一致，仅实际满足的范围关闭，不改旧研究接受或自然 Submit 票结论。

## 既有证据与限制

[AC01–AC27](../../../docs/module-interfaces-and-migration-design.md#验收标准)和[R6 汇总](../serial-r6-verification-summary.md)。R6 原记录封存，未来完整验收产生新证据，不覆盖原结果。

需求以[正式设计](../../../docs/module-interfaces-and-migration-design.md)为准。R6 只证明原冻结源码与合成测试范围；本票如有新实现，
须记录实际改动、对应回归和审查，不能复用 R6 关闭新行为。未知结果、人工内容、原页、
原 journal 和历史记录保留，最终 Submit 手动。

## 2026-10-27 架构审计补充

[架构审计](../../work-audit-2026-10-27/architecture-audit.md)建议最终审计同时复核接口层面的状态。本票原验收保持不变，追加：

- [ ] MC-17 的公开入口清单与最终代码一致；计划收回的内部入口均已收回或记录保留理由。
- [ ] MC-18 依赖棘轮测试在最终快照通过，并记录剩余循环导入与跨模块私有导入的数量。
- [ ] 复核 Flow、Resume、Worker、Pipeline 实际被外部使用的方法数，与审计时的基线对照。

为此新增硬前置 [MC-19](19-narrow-flow-resume-surface.md)。
