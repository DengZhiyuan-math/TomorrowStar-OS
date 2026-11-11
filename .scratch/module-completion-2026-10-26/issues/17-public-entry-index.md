# MC-17：登记核心 Module 公开入口与当前有效索引

Type: task
Label: wayfinder:task
Status: closed
Priority: P1
Interaction: AFK
Assignee: claude-code-367f651f/root
Created: 2026-10-27
Parent: [Module 剩余开发地图](../map.md)
Blocked by: none
Triage: closed

## 问题与范围

[2026-10-27 架构审计](../../work-audit-2026-10-27/architecture-audit.md)发现两处使 agent 修改不可靠的文档缺口：
核心 Module 实际被外部调用的方法远多于设计（D2），以及“当前有效”的约定分散在多份带日期的段落里（D6）。
本票只补文档，不改代码：

1. 在 [职责审计](../../../docs/codebase-responsibilities.md) 中，为 Pipeline、Flow、Worker、Resume、CoverLetter、
   Analysis、Intake 各列出“允许外部调用的入口”，并单列“当前仍被外部使用、但计划收回的内部入口”
   （例如 `flow._load`、`store._read_version_file`），注明负责收回的票。
2. 新增一页当前有效索引：当前产品入口约定、各 Module 接口契约所在章节、已被取代的段落及取代它们的段落。

## 文件所有权与并行边界

`docs/codebase-responsibilities.md` 和新增的索引文档；不触碰 src/tests，可与 MC-06 等实现票并行。
共享文件按地图的冲突规则协调；领取后才能写入。不得覆盖其他工作的修改。

## 验收条件

- [x] 七个核心 Module 各有允许外部调用的入口清单，来源为当前代码的实际定义和调用，而不是设计目标名。
- [x] 计划收回的内部入口逐项列出现有外部调用位置和负责票（MC-08、MC-14 或 MC-19）。
- [x] 当前有效索引能回答：日常入口是什么、某 Module 的契约在哪一节、10-22 与 10-26 两处入口说法以哪处为准。
- [x] 每张 MC 票结案时更新清单的约定写进地图的 Notes。

## 既有证据与限制

证据见[架构审计](../../work-audit-2026-10-27/architecture-audit.md)的 B、D2、D6 与 E.1、E.2。
本票不收窄任何接口，不改变既有票状态或依赖。最终 Submit 手动。

## Comments

### 2026-10-27 wayfinder 认领（Europe/Zurich）

经 `scripts/query_tickets.py` 核对：本票 open/unassigned、无硬前置、`mechanical_frontier: true`。
全库当前机械前沿只有 MC-17 与 MC-18；两票文件所有权不相交（MC-17 只写文档，MC-18 只新增
测试与基线），按用户“接手最前沿票据、准备并发执行”认领，由 root 分派为两个并行执行单元。
尚未写入任何交付文件；MC-06 仍由其原认领者持有，本次不触碰其区域。

### Resolution（2026-10-27）

只改文档，未改 src/tests：[职责审计](../../../docs/codebase-responsibilities.md#public-entry-points)新增
“核心 Module 当前公开入口”与“计划收回的内部入口”两节；新增[当前有效索引](../../../docs/current-index.md)，
仅从职责审计链接。

- 入口清单来自对 `src/career_evidence_graph/` 的 AST 扫描（含函数内导入，按接收者名过滤同名方法后人工剔除误报），
  不含 tests/。允许外部调用的入口：Pipeline 9 个方法；Flow 32 个方法 + 10 个模块函数；Worker `WorkerService` 21、
  `WorkerStore` 16、`ApplicationRunner` 5 个方法 + 8 个模块函数/1 常量 + 进程入口 `main`；Resume 34 个方法 + 13 个模块函数；
  CoverLetter 2 个方法 + 10 个模块函数；Analysis 7 个方法 + 3 个模块级名；Intake 10 个方法（另 1 个仅夹具用的邮件函数）。
  同时登记“公开但无外部调用者”（Flow 44、Resume 5、WorkerService 5、WorkerStore 9、Pipeline 2、Analysis 1）。
- 计划收回项逐项列 file:line：MC-14 6 行（Portal 内 10 个 Flow 私有方法、Worker 私有方法与进程属性），
  MC-08 4 行（`pipeline._task` 与 `pipeline.flow/worker` 穿透、`flow.worker_action` 9 处、`flow.applications` 26 处、
  `_unresolved_write_failure` 导入），MC-19 19 行（Flow 21 个私有名、Resume 6 个私有名）。
  `flow._load` 源码外部 23 处与审计一致；`_read_version_file`/`_draft_document` 只计 Resume 之外 18/16 处
  （审计 45/24 含 `application_resume_versions.py` 内部调用）。Analysis 周边与 Worker 夹具的跨文件私有使用不分配收回票，由 MC-18 基线防增。
- 10-22 与 10-26 入口说法：以 2026-10-26 设计文首“日常用户入口是 App”段为准；10-22 两处段落（开发计划、workflows）
  只在入口说法上被取代，其保护规则仍有效。默认页面写入与自动接管仍关闭，归 MC-08。
- 地图 Notes 写明每张 MC 票结案时更新入口清单、收回表、当前有效索引和 MC-18 基线。

限制：计数为静态扫描，行号属本次快照；未运行测试（纯文档变更）。
