# MC-18：依赖棘轮测试，禁止新增循环导入与跨模块私有访问

Type: task
Label: wayfinder:task
Status: closed
Priority: P2
Interaction: AFK
Assignee: claude-code-367f651f/root
Created: 2026-10-27
Parent: [Module 剩余开发地图](../map.md)
Blocked by: none
Triage: closed

## 问题与范围

[2026-10-27 架构审计](../../work-audit-2026-10-27/architecture-audit.md) D3：`src/career_evidence_graph/` 有 20 对模块互相导入，
约 600 处函数内导入，多处跨模块导入私有名（例如 `application_full_latex` 的私有函数被三个模块导入）。
目前没有任何自动检查阻止这些情况继续增加。

本票只加一个离线测试：记录当前的循环导入对和跨模块私有名导入作为基线，**只禁止新增**，
不要求消除现有项。基线随有意的改动更新，并在提交说明中写明理由。

## 文件所有权与并行边界

新增一个测试文件及其基线数据；不修改 src。可与实现票并行；实现票若有意新增或消除基线项，在同一改动中更新基线。
共享文件按地图的冲突规则协调；领取后才能写入。不得覆盖其他工作的修改。

## 验收条件

- [x] 测试使用标准库 `ast` 读取本包导入，不新增依赖，在默认离线套件中运行。
- [x] 基线与当前代码一致：现有循环对与跨模块私有导入全部列出，测试在当前快照上通过。
- [x] 人为新增一个循环导入或跨模块私有导入时测试失败，并指出具体模块对；消除一项时提示更新基线。
- [x] 不检查测试文件对私有方法的使用（由 MC-19 处理），不把函数内导入本身判为错误。

## 既有证据与限制

证据见[架构审计](../../work-audit-2026-10-27/architecture-audit.md)的 D3 与 E.4。本票不拆除任何现有循环。

## Comments

### 2026-10-27 wayfinder 认领（Europe/Zurich）

经 `scripts/query_tickets.py` 核对：本票 open/unassigned、无硬前置、`mechanical_frontier: true`。
全库当前机械前沿只有 MC-17 与 MC-18；两票文件所有权不相交（MC-17 只写文档，MC-18 只新增
测试与基线），按用户“接手最前沿票据、准备并发执行”认领，由 root 分派为两个并行执行单元。
尚未写入任何交付文件；MC-06 仍由其原认领者持有，本次不触碰其区域。

### Resolution（2026-10-27）

新增 `tests/test_dependency_ratchet.py` 与基线 `tests/fixtures/dependency-ratchet-v1.json`；未改 src。

- 用标准库 `ast` 扫描 `src/career_evidence_graph/` 全部 110 个模块（含 `_vendor/` 与函数内导入），
  相对导入解析为绝对模块名，`from pkg import 子模块` 记为对子模块的依赖。不扫描 tests/，函数内导入本身不判错；
  测试无 marker，在默认离线套件（`-m "not live and not live_model and not worker_browser"`）中运行。
- 基线：直接互相导入的模块对 **20** 对（与审计 D3 的 20 对一致，且包含审计点名的四对）；
  跨模块私有名导入 **87** 项（按“导入方、来源模块、名字”去重，排除 dunder）。
  审计举例中 `application_full_latex` → `application_experience_latex` 7 个、`application_group_review` 6 个一致；
  `application_writing` 去重后 6 个（审计写 7）、`application_resume` 从 `application_group_review` 去重后 5 个
  （审计写 7），差异来自审计按导入语句出现次数计数。函数内导入语句计得 476 条（审计“约 600”为粗估，本票不使用）。
- 新增项失败并指出 `new mutual_import_pairs: A <-> B` 或 `new private_cross_module_imports: X imports M._name`；
  消除项同样失败（`resolved ...: ... -- remove it from dependency-ratchet-v1.json (update the baseline)`），
  采用棘轮惯例，保证基线随有意的改动同步收紧。
- 失败路径永久覆盖：合成内存模块的单测覆盖新环、私有导入、子包相对导入与陈旧基线；另一测试在真实快照的内存副本上
  给 `jd` 注入 `from .cli import _not_public`、给 `cli` 注入函数内 `from . import jd`，断言报出
  `cli <-> jd` 与 `jd imports cli._not_public`。未临时修改 src。
- 验证：`uv run --locked pytest tests/test_dependency_ratchet.py -q` 4 passed；
  `uv run --locked ruff check` 与 `ruff format --check` 该文件通过。
