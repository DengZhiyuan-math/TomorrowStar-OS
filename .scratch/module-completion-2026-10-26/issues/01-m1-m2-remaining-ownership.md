# MC-01：核对并补齐 M1/M2 剩余职责迁移

Type: verification
Label: wayfinder:task
Status: closed
Priority: P2
Interaction: AFK
Assignee: 01a17906-845c-7d91-8bde-c11810886142/root/m1_m2
Created: 2026-10-26
Parent: [Module 剩余开发地图](../map.md)
Blocked by: [MC-00](00-r6-source-baseline.md)
Triage: source-and-synthetic-verified
Closure reason: verified

## 问题与范围

逐条核对正式 M1 引用/进度与 M2 条件提交/恢复要求，只修复实际缺少的默认调用迁移。不能因一个已验切片关闭整个阶段，也不重复实现已闭环的 Worker 或 journal。

## 文件所有权与并行边界

application_contracts.py、application_flow.py、application_worker.py、application_bound_materials.py、application_material_edit.py 和必要默认消费者。先只读列差异；Flow/Worker 修改与 MC-05/MC-08/MC-03 按方法串行；已冻结切片的审查不能直接覆盖随后改动。

共享文件按地图的冲突规则协调；领取后才能写入。不得覆盖其他工作的修改。
依赖边表示必要交付，不表示外部运行授权；测试记录中的 deselected 不抵充覆盖。

## 验收条件

- [x] Worker 准备/引用/控制/选择已接默认 Flow/Portal；整岗取消、编辑排空及三方 journal 所属提交已落地。
- [x] 按正式设计列出每个引用/进度/提交操作的实际调用者、所有者及已有证据；确认缺口后才改代码，无缺口项直接复用证据。
- [x] 所有迁移后的只读查询不建目录、不写业务、不派发；保留旧两键/六键交付及精确错误兼容。
- [x] 所有条件采用、部分取消/提交恢复、信件人工后继均由所属操作处理；无外部宽字典覆盖、无第二份主状态/事务系统。
- [x] 保留未知、人工内容、原 journal 和迟到幂等语义；完成受影响回归和剩余项独立审查，逐项给出 M1/M2 的关闭或明确转交结论。

## 既有证据与限制

[M1 实现](../m1-worker/implementation.md)、[M1 审查](../m1-worker/review-closed.md)、[M2 实现](../../m2-cancel-and-edit-2026-10-26/README.md)、[journal 所属提交](../../m2-cancel-and-edit-2026-10-26/journal-owners.md)。T09 新接管下的编辑前统一协调由 MC-08 承接，不在此重复。

需求以[正式设计](../../../docs/module-interfaces-and-migration-design.md)为准。R6 只证明原冻结源码与合成测试范围；本票如有新实现，
须记录实际改动、对应回归和审查，不能复用 R6 关闭新行为。未知结果、人工内容、原页、
原 journal 和历史记录保留，最终 Submit 手动。

## Comments

### 2026-10-26 并发认领与实施（Europe/Zurich）

用户调用 implement，授权本票与 Prism 人工后继、另一路材料/职责票并发执行。
先逐项核对并复用已有证据，仅对确认的执行材料条件采用残留做公开回归和最小修复。Flow/Worker/MaterialEdit 的共享区域由父会话按方法分配。
详细记录见[并发实施记录](../../mc01-mc02-mc04-implementation-2026-10-26/README.md)。

Prism远端更新按用户决定搁置，仅在具体相关缺陷后重新评估。产品范围和本票原验收保持；
本次认领不表示验收已满足，后续统一冻结回归与独立审查后再记录结论。

### 2026-10-26 Resolution：源码与相关合成验收完成（Europe/Zurich）

已逐项清点引用、进度、取消和原 journal 的实际消费者/所有者；现有已验路径复用，
附稿人工后继的预检与条件提交收回 Worker。协调器沿同一所属校验恢复，不再另维持
完整候选规则。独立审查发现的候选正文绑定 P2 已先复现再修复；最终独立正确性
复核 51 项通过，规范复核通过。

本票剩余控制/派发与准备调度已按具体方法承接到
「T09 App 自动派发与统一控制」及「M4 收拢剩余准备与岗位调度职责」原票，
未计为本轮已实施。完整清点、失败/修复和逐项证据见
[本票实施记录](../../mc01-mc02-mc04-implementation-2026-10-26/mc01/implementation.md)，
[正确性最终复核](../../mc01-mc02-mc04-implementation-2026-10-26/reviews/mc01-final-review.md)和
[规范最终复核](../../mc01-mc02-mc04-implementation-2026-10-26/reviews/standards-final-review.md)。

同一 665 文件最终快照：完整默认离线 **7,722 passed、2 skipped**，随后相关隔离
合成浏览器 **89 passed**；零失败/错误。JUnit 精确覆盖两个不相交清单，运行前后
源码一致；Ruff、格式与差异空白检查通过。两项跳过为未启用的显式 PDF 性能基准。
最终结果见[统一验收](../../mc01-mc02-mc04-implementation-2026-10-26/final-verification.json)。
此前两个中断批次不作通过证明，原失败与修复记录保留。

本票按当前源码/合成范围结案；未执行真实模型、Prism 服务、安装 App 或 ATS
接受，不扩大为全部 Module 或最终 AC 验收。未提交、发布或更新安装版。
