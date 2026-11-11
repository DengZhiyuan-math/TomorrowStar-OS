# MC-00：登记已交付切片与 R6 源码基线

Type: verification
Label: wayfinder:task
Status: closed
Priority: P2
Interaction: AFK
Assignee: Codex /root
Created: 2026-10-26
Parent: [Module 剩余开发地图](../map.md)
Blocked by: none
Triage: source-and-synthetic-verified
Closure reason: verified

## 问题与范围

本票只登记已经完成的源码与隔离合成验收，不重开实现，也不把完整 M1/M2/M3 或 T06–T11 标记完成。T01–T05 的已实现契约和后续动作复验边界分别保留。

## 文件所有权与并行边界

仅维护本票与地图。既有 src/tests/config、冻结清单、失败日志和审查记录均不改。历史实现负责人保留在原记录中，本票负责人只负责本次证据归档。

共享文件按地图的冲突规则协调；领取后才能写入。不得覆盖其他工作的修改。
依赖边表示必要交付，不表示外部运行授权；测试记录中的 deselected 不抵充覆盖。

## 验收条件

- [x] R6 默认离线 7,458 passed、2 skipped，7,460 项完整覆盖；隔离浏览器 594 passed、21 skipped，615 项完整覆盖；零失败/错误。
- [x] 同一 652 文件快照，先离线后浏览器且无重叠；Ruff、格式和 diff 检查通过；跳过均未启用显式 opt-in。
- [x] M1 Worker 固定执行接口的 396 项定向记录与独立审查保留；M2 取消、原 journal/信件后继和迟到提交修复记录保留。
- [x] M3 Analysis 默认消费者迁移及三项审计修复已闭环；Resume 作者执行/无新调用核对的 66 项切片及 ID-selector 限制明确。
- [x] T04/T05 停止、失联和原页只读恢复的定向/独立复核通过；T06 动作竞争、T08 可靠交回和真实模型/GUI/ATS 仍未验。

## 既有证据与限制

[最终机器记录](../final-verification.json)、[R6 汇总](../serial-r6-verification-summary.md)、[M1 审查](../m1-worker/review-closed.md)、[M2 审查](../../m2-cancel-and-edit-2026-10-26/review-closed.md)、[Analysis 审查](../../m3-analysis-module-2026-10-26/review-closed.md)、[Resume 作者审查](../../m3-resume-author-2026-10-26/review-closed.md)、[T04/T05](../../codex-assist-t04-t05-2026-10-26/implementation.md)。未更新已安装 App，未运行真实模型或申请。

需求以[正式设计](../../../docs/module-interfaces-and-migration-design.md)为准。R6 只证明原冻结源码与合成测试范围；本票如有新实现，
须记录实际改动、对应回归和审查，不能复用 R6 关闭新行为。未知结果、人工内容、原页、
原 journal 和历史记录保留，最终 Submit 手动。
