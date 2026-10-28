# 在派发前选择已支持的执行路线

Type: task
Label: wayfinder:task
Status: closed
Triage: resolved
Completion: source-and-isolated-browser-verified
Priority: P1
Interaction: AFK
Assignee: 01a14a95/root
Created: 2026-10-17
Updated: 2026-10-18
Parent: [交付 DOM 优先的受控浏览器效率改进](../map.md)
Publication order: 19
Blocked by: [让一个不可编辑下拉框走DOM完成选择](03-dom-first-controls.md)

**What to build:** 同一worker在动作派发前决定DOM或已支持的Cua路线，不支持或不可用时明确交人工。

## Acceptance criteria

- [x] 记录选路理由、实际执行器、intent、动作及回读；保留原owner/browser/page，不双执行或重开。
- [x] unknown禁止换路重做；仅可证实not_sent且重新核验后按明确规则改路线。
- [x] 不等待Cua性能优化；宣称真实Cua路线可用前必须另有本轮原生就绪证据，否则只交付DOM与人工接管范围。
- [x] 合成用户入口可演示成功、不可用与接管；默认材料入口不因此启动填写器。

## Standing boundaries

复用已有能力和已完成研究；每票形成可独立演示或验证的用户行为。先做本票必要的最小整理，不引入推测性框架。个人材料留私有；保持真实申请暂停、未知动作停止及人工最终Submit。规划发布不授权真实邮箱／模型／ATS执行。任何代码变更均需本切片的有效验证。

## Ownership

沿用票头Status和Assignee；本次仅发布，未领取或执行。先核对frontier并写入唯一领取人，再做工作；多人共享模块时协调，不回退其他人的改动。HITL必须由用户实际参与，不能由代理代答。

## Comments

### 2026-10-18 — Pre-dispatch routing verified

[路由切片](../../browser-efficiency-execution-2026-10-18/routing/README.md)按动态控件能力选择DOM、既有Cua或人工，在原intent/结果保留executor/input_route/reason及独立回读。人工预检只记录proposed_fill未派发，不建立假fill intent；public review/handoff/recheck保留原页/owner。旧unknown及not_applied不能证明not_sent；executor/input_route缺失或改变均交人工。跨批次归档的同岗动作也参与守卫，20项最终真实浏览器路由回归通过，独立审查无阻断。

[严格合成入口](../../browser-efficiency-execution-2026-10-18/synthetic-browser/README.md)复用隔离root、固定GET、本地WS mock/drop、固定source-owned CLI和当前Python；默认材料入口不构造worker。成功/人工/unknown及真实handoff 4项Chrome回归通过。新synthetic同步WS close导致本机Playwright回调重入挂起的有效RED保留，复用原有本地drop后同场景GREEN；HTTP/WS无远端连接，旧mode字节契约不变。

[最终完整门槛](../../browser-efficiency-execution-2026-10-18/routing-gate/verification.json)：2554默认离线通过、269显式排除；86受影响真实浏览器通过、5原生opt-in跳过；Ruff/format/JS/diff与DEBUG清理通过，245公共文件集合/哈希前后无漂移。原生就绪证据只限前置11固定helper的dom_event；trusted mouse、组合收益和实际安装留后继，未用double冒充。真实申请继续暂停，HITL统一待审。

### 2026-10-18 — Execution claim

前置03已关闭且最终默认离线通过，由01a14a95/root领取，继续用户授权全部剩余工程票。最小派发前选路与显式人工接管，保留unknown；第四项合成用户入口需现有App→worker真实live链，因此仅在严格合成模式复用既有隔离root/假CLI/无Gmail，补最小原生验证入口。普通入口不能隔离真实support，不能用它做测试；准备模式继续不启动填写器。真实Cua证据当前限固定helper的dom_event，trusted mouse与安装行为不冒称通过。真实申请继续暂停，HITL集中留待审核。

### 2026-10-17 — Approved ticket migration

用户已批准23张拆分及迁移。此票沿用原路径和身份，采用批准后的纵向交付契约；此前内容保存在不可覆盖的历史快照中，不丢失原问题、依赖、评论或验收记录。

- [批准的逐票草案](../../tomorrowstar-ticket-consolidation-2026-10-17/drafts/19-dispatch-route-selection.md)。
- [迁移前完整原文](../../tomorrowstar-ticket-consolidation-2026-10-17/history/pre-publication/.scratch/browser-efficiency-2026-10-17/issues/06-hybrid-browser-routing.md)。
- [当前正式导航与全部承接关系](../../tomorrowstar-ticket-consolidation-2026-10-17/README.md)。

本次迁移不是实现完成或用户产品接受；真实申请继续暂停。
