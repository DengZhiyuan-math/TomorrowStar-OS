# MC-04：收拢 CoverLetter 与材料一致性契约

Type: task
Label: wayfinder:task
Status: closed
Priority: P2
Interaction: AFK
Assignee: 01a17906-845c-7d91-8bde-c11810886142/root/letter_contracts
Created: 2026-10-26
Parent: [Module 剩余开发地图](../map.md)
Blocked by: [MC-00](00-r6-source-baseline.md)
Triage: source-and-synthetic-verified
Closure reason: verified

## 问题与范围

核对并迁移 M3 尚未收拢的信件正文/版本/按需 PDF 及一致性调用。复用 M2 已有人工后继和 journal，不重做既有通用 Cover Letter 功能。

## 文件所有权与并行边界

application_cover_letter.py、application_materials.py、application_material_consistency.py；Flow 拥有一致性预留与采用。可与 MC-02/MC-03 主文件并行；application_flow.py、career_portal.py、application_material_edit.py 同段修改串行。

共享文件按地图的冲突规则协调；领取后才能写入。不得覆盖其他工作的修改。
依赖边表示必要交付，不表示外部运行授权；测试记录中的 deselected 不抵充覆盖。

## 验收条件

- [x] M2 已提供人工信件后继的所属采用和历史保护。
- [x] 逐个核对默认消费者的 prepare/read/edit/build/reconcile 归属；仅迁移真实缺口，正文版本决定不留在 supplemental/Portal。
- [x] 文本优先且按需 PDF，正文读取不编译；原构建回读无新调用，构建失败保留正文与具体重试项。
- [x] 一致性输入绑定确切简历/信件版本，预留与采用归 Flow；换版本不复用错误检查，不改兄弟材料。
- [x] 覆盖正常生成等待、可选/必需变化、明确失败/unknown、人工正文、旧 renderer 与响应丢失，保留内部来源/责任和历史；相关回归及审查通过。

## 既有证据与限制

[正式材料接口](../../../docs/module-interfaces-and-migration-design.md#coverletter)、[M2 后继提交](../../m2-cancel-and-edit-2026-10-26/journal-owners.md)。旧 Cover Letter 七张决策票仍保持原已关闭状态。

需求以[正式设计](../../../docs/module-interfaces-and-migration-design.md)为准。R6 只证明原冻结源码与合成测试范围；本票如有新实现，
须记录实际改动、对应回归和审查，不能复用 R6 关闭新行为。未知结果、人工内容、原页、
原 journal 和历史记录保留，最终 Submit 手动。

## Comments

### 2026-10-26 并发认领与实施（Europe/Zurich）

用户调用 implement，授权本票与 Prism 人工后继、另一路材料/职责票并发执行。
收回默认消费者中的正文/版本/PDF和精确版本对检查，保持Flow预留与采用。Portal四个信件闭包及MaterialEdit._edit_letter_content分配给信件线；Worker接线由父会话协调。
详细记录见[并发实施记录](../../mc01-mc02-mc04-implementation-2026-10-26/README.md)。

Prism远端更新按用户决定搁置，仅在具体相关缺陷后重新评估。产品范围和本票原验收保持；
本次认领不表示验收已满足，后续统一冻结回归与独立审查后再记录结论。

### 2026-10-26 Resolution：源码与相关合成验收完成（Europe/Zurich）

作者输入、attempt/retry/结果读取、正文选择及固定文本人工编辑已收回 CoverLetter
所属操作，Portal 保留装配和 Flow 许可。MaterialConsistency 绑定当前 draft 与
Flow 预留的准确材料版本对，修复历史 adopted 简历误选。Worker 原文件核对调用
所属恢复操作；本地完整结果直接只读返回，缺证才核对原构建，无编译重放。

受影响最终组合 356 项通过，独立组合 56 项通过。正常等待、optional/required、
明确失败/unknown、人工正文、legacy renderer 与响应丢失按原验收分别核对。
逐项证据见[本票实施记录](../../mc01-mc02-mc04-implementation-2026-10-26/mc04/implementation.md)及
[独立审查](../../mc01-mc02-mc04-implementation-2026-10-26/reviews/mc04-review.md)。

同一 665 文件最终快照：完整默认离线 **7,722 passed、2 skipped**，随后相关隔离
合成浏览器 **89 passed**；零失败/错误。JUnit 精确覆盖两个不相交清单，运行前后
源码一致；Ruff、格式与差异空白检查通过。两项跳过为未启用的显式 PDF 性能基准。
最终结果见[统一验收](../../mc01-mc02-mc04-implementation-2026-10-26/final-verification.json)。
此前两个中断批次不作通过证明，原失败与修复记录保留。

本票按当前源码/合成范围结案；未执行真实模型、Prism 服务、安装 App 或 ATS
接受，不扩大为全部 Module 或最终 AC 验收。未提交、发布或更新安装版。
