# 减少一个昂贵的Cua观察步骤

Type: task
Label: wayfinder:task
Status: closed
Triage: resolved
Completion: conditional-no-cua-optimization-admitted
Priority: P1
Interaction: AFK
Assignee: 01a14a95/root
Created: 2026-10-17
Updated: 2026-10-18
Parent: [交付 DOM 优先的受控浏览器效率改进](../map.md)
Publication order: 18
Blocked by: [取得隔离原生Cua的真实操作证据](11-native-cua-baseline.md)

**What to build:** 对真实测得昂贵的一次绑定或快照做局部优化，保持同一受管页面与结果核验。

## Acceptance criteria

- [x] 只在原生就绪且已测成本后选一个步骤；没有API支持或收益则记录不实施。
- [x] 覆盖相同URL双tab、owner失效、文档变化、展开后新选项和快照不完整。
- [x] 同输入原生对照与未知停止边界保持；不默认升级、替换驱动或引入新模型。
- [x] 复制/改写上游机制前记录固定版本、许可和本地差异；本轮研究本身不是接入许可。

## Standing boundaries

复用已有能力和已完成研究；每票形成可独立演示或验证的用户行为。先做本票必要的最小整理，不引入推测性框架。个人材料留私有；保持真实申请暂停、未知动作停止及人工最终Submit。规划发布不授权真实邮箱／模型／ATS执行。任何代码变更均需本切片的有效验证。

## Ownership

沿用票头Status和Assignee；本次仅发布，未领取或执行。先核对frontier并写入唯一领取人，再做工作；多人共享模块时协调，不回退其他人的改动。HITL必须由用户实际参与，不能由代理代答。

## Comments

### 2026-10-18 — Conditional resolution: query candidate withdrawn

前置11真实helper基线已关闭。只选第一combobox语义快照的公开query参数，固定既有helper/许可/owner，不复制上游或更换驱动。[正式生产候选测量](../../browser-efficiency-execution-2026-10-18/native-query/production/README.md)含2次独立预热与5对原生AB/BA：第一快照中位71.828→68.036ms，最小节约1.551ms低于同臂12.091ms范围；整次fill亦未达到稳健收益门槛。响应载荷下降不冒充延迟收益，也不宣称零收益。

撤销前候选与既有Cua/MCP/owner回归55 passed，含相同URL双tab、owner失效、文档变化、展开后新选项、快照不完整及unknown不重试。12次原生目标/非目标回读通过，正式owned Chrome/helper与早先API探针精确PID退出回查通过，socket/profile已清理。候选源码/测试/原始RPC精确归档后只撤销其自身改动；当前cua_driver与冻结baseline字节一致c27fe44fa282f15f8bbad4c337b82643b7bc4fc57bf5f9f882c60adc024e615a，原有测试未改。独立审查无阻断，按无稳健收益不实施分支结案。最终保留源码完整回归由root另记；本票不宣称安装、trusted鼠标或真实ATS通过。真实申请继续暂停。

### 2026-10-18 — Execution claim

用户授权继续全部剩余票；前置已回读，由 `01a14a95/root` 领取。先以当前证据检验必要性和公共API；条件不成立时明确记录不实施，不引入推测性能力。只运行新归属合成资源，真实申请继续暂停。

### 2026-10-17 — Approved ticket migration

用户已批准23张拆分及迁移。此票沿用原路径和身份，采用批准后的纵向交付契约；此前内容保存在不可覆盖的历史快照中，不丢失原问题、依赖、评论或验收记录。

- [批准的逐票草案](../../tomorrowstar-ticket-consolidation-2026-10-17/drafts/18-bounded-cua-observation.md)。
- [迁移前完整原文](../../tomorrowstar-ticket-consolidation-2026-10-17/history/pre-publication/.scratch/browser-efficiency-2026-10-17/issues/04-cua-binding-snapshot-overhead.md)。
- [当前正式导航与全部承接关系](../../tomorrowstar-ticket-consolidation-2026-10-17/README.md)。

本次迁移不是实现完成或用户产品接受；真实申请继续暂停。
