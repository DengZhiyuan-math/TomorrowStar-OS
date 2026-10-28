# MC-13：M4 收拢剩余准备与岗位调度职责

Type: task
Label: wayfinder:task
Status: closed
Priority: P2
Interaction: AFK
Assignee: 01a179dd-5d36-7390-b987-ffc07cb4d702/root
Created: 2026-10-26
Parent: [Module 剩余开发地图](../map.md)
Blocked by: [MC-01](01-m1-m2-remaining-ownership.md), [MC-03](03-resume-lifecycle-interface.md), [MC-04](04-letter-material-contracts.md)
Triage: source-and-synthetic-verified
Closure reason: verified

## 问题与范围

在 M1/M2 与材料接口交付后，收拢常规 Flow 准备/Pipeline 队列职责；新接管派发/编辑停写仍由 MC-08 唯一承接。本票与 MC-08 是 M4 的两部分，不互相形成整阶段依赖。

## 文件所有权与并行边界

application_flow.py、application_pipeline.py 与对应 career_portal.py 消费者。可与 T06–T08 在不同文件/方法推进；与 MC-08 的控制/入口同段修改必须串行，固定交付后再集成。

共享文件按地图的冲突规则协调；领取后才能写入。不得覆盖其他工作的修改。
依赖边表示必要交付，不表示外部运行授权；测试记录中的 deselected 不抵充覆盖。

## 验收条件

- [x] Flow 只协调分析到材料及准备取消，Pipeline 拥有当前岗、路由、暂停/继续/Skip/Return；无旧/新控制器同时调度。
- [x] 稳定后端进度保留实际准备/执行区别；等待仅收录邮件，重要缺失/冲突/unknown 不进入下一岗。
- [x] 当前任务与固定输入准入、局部恢复、人工候选、一次 Continue 和旧 HTTP/CLI 兼容保持。
- [x] 列明新接管职责由 MC-08 承接，常规准备职责无遗漏；实际默认消费者回归与独立审查通过。

## 既有证据与限制

[迁移顺序 M4](../../../docs/module-interfaces-and-migration-design.md#迁移顺序)。旧 39 号票为已交付上游，不重开、不扩张。

需求以[正式设计](../../../docs/module-interfaces-and-migration-design.md)为准。R6 只证明原冻结源码与合成测试范围；本票如有新实现，
须记录实际改动、对应回归和审查，不能复用 R6 关闭新行为。未知结果、人工内容、原页、
原 journal 和历史记录保留，最终 Submit 手动。

## 后继接口清点 — 2026-10-26

并发「核对并补齐 M1/M2 剩余职责迁移」确认
`application_bound_materials.paused_job/current_inputs/begin/prepare` 和 Flow 内部
准备候选协调仍由本票收敛。保留原候选、当前 Worker 许可和同一 journal；
共享 Flow/Pipeline 区域按方法串行集成，不建立第二份任务或事务主状态。

实际调用、范围判断及证据索引见[归属清点](../../mc01-mc02-mc04-implementation-2026-10-26/mc01/implementation.md#明确转交的后续协调)。
这是本票原有调度范围的具体接续点；尚未在并发三票中实施，不改变本票状态、认领和硬依赖。


## Comments

### 2026-10-26 认领并开始实施（Europe/Zurich）

用户明确要求继续执行本票。实时 tracker 显示三个硬前置均关闭，本票为未认领前沿；
本会话先保存认领，再实施。基线捕获当前含已有改动的源码，不以 Git HEAD 覆盖工作。
实施与验证见[本轮记录](../../mc13-preparation-scheduling-2026-10-26/)。
新接管派发、原页控制及停写仍由「T09 App 自动派发与统一控制」承接；
本票只收拢常规准备与岗位调度，不新增任务/事务主状态，不扩大真实运行或安装范围。


### 2026-10-26 Resolution：常规准备与岗位调度源码/合成验收完成（Europe/Zurich）

Flow 现提供只读准备进度、必要步骤推进、明确失败接续和原回执核对，分别交付分析、
简历、信件、一致性及候选状态。Pipeline 消费业务结果，继续独占当前岗、路由和
暂停/Continue/Skip/Return；等待仅收录邮件，重要缺失、冲突和未知不推进下一岗。
原阶段、attempt 与 Pipeline 既有接续记录继续使用，未新增队列或任务主状态。

绑定材料的固定输入、候选准备与编辑协调收回 Flow；Worker 核验准确的申请/任务/
batch 并提供只读准备许可。Portal 只装配所属入口，Resume 保留真实材料规则。
原候选、材料历史和三方 journal 不重建；未知导出只核对原尝试。
取消、失去许可或固定输入变化后不再派发候选准备；迟到材料保留为未采用历史，
不激活已取消任务、不替换原 PDF。第二个只读控制器不能调度准备。

已有 Flow→Worker 兼容桥继续只核任务/材料并采用执行引用；Worker 拥有执行操作。
默认 Pipeline 实际路径已验证只建立一个执行记录，并调用 Worker 准备和启动接口。
旧 HTTP/CLI、局部恢复、人工材料和一次 Continue 保持。原页检查派发、编辑前停写/
排空及新接管统一控制仍由「T09 App 自动派发与统一控制」承接，不外推为完整 M4。

独立审查发现与修复、原始反例和中间验证记录见
[实施报告](../../mc13-preparation-scheduling-2026-10-26/README.md)。最终同一 672
文件快照先执行完整默认离线 **7,804 passed、2 skipped**，随后相关隔离浏览器 **152 passed**，
零失败/错误。JUnit 精确覆盖两份互不相交清单，运行前后源码不变，静态检查通过。
两项离线跳过为既有未启用的 PDF 性能基准；见
[最终验证](../../mc13-preparation-scheduling-2026-10-26/final-verification.json)。

本票按源码/合成范围结案。未提交、发布、更新安装 App 或 Prism 上游，未运行真实
模型/Prism/ATS 验收；最终 Submit 手动。其余票据负责人和依赖保持，Runtime/Portal
后继仍等待新接管控制票，全部 Module 与 AC 整体验收未完成。
