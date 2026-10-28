# MC-20：补齐 worker 运行身份对材料核验代码的覆盖

Type: task
Label: wayfinder:task
Status: closed
Priority: P2
Interaction: AFK
Assignee: claude-code-4ca66ce5/root
Created: 2026-10-28
Parent: [Module 剩余开发地图](../map.md)
Blocked by: none
Triage: closed-source-synthetic

## 问题与范围

[MC-15 复审 r2](../../remaining-tickets-2026-10-26/mc15-mc19-joint/acceptance/review-mc15-r2.md) 留下的 P2，
MC-15 按“只改记录”结案并移入 fog（见 [2026-10-28 工作审计](../../work-audit-2026-10-28/README.md) 问题 2、4）。

worker 进程在填写时经 `store.material_inputs` / `store.verify_material`（`application_worker.py`）惰性导入
`application_match`、`application_resume`、`application_material_sources`，三者不在 worker 角色内，
worker 启动时记录的运行身份因此不覆盖材料核验代码。该缺口早于 MC-15。

同时：`application_preparation_fixtures`（合成模式由 `macos/server.py` 载入控制器）既不在角色内也未豁免；
`tests/test_loaded_role_coverage.py:233-235` 注释称 worker“从不加载”这些路径，说法过宽。

## 文件所有权与并行边界

`loaded_code.py`、`application_worker.py` 中材料核验的导入位置、`tests/test_loaded_role_coverage.py`。
须在 MC-11 更新安装 App 之前完成；与 MC-21、MC-22 不共享文件时可并行。
共享文件按地图的冲突规则协调；领取后才能写入。不得覆盖其他工作的修改。
依赖边表示必要交付，不表示外部运行授权；测试记录中的 deselected 不抵充覆盖。

## 验收条件

- [x] 先写失败回归：worker 实际执行材料核验后加载的模块都属于 worker 角色或有理由豁免。
- [x] worker 启动时预加载上述三模块并纳入 worker 角色（或给出等价方案），启动身份覆盖材料核验代码。
- [x] `application_preparation_fixtures` 按 `application_worker_fixtures` 同理豁免并写明理由。
- [x] 改正 `test_loaded_role_coverage.py` 的过宽注释与文档字符串，使其只陈述测试实际证明的内容。
- [x] 新冻结后完整默认离线通过，受影响隔离浏览器与 native 用例复跑通过，独立审查 READY；MC-17 清单与 MC-18 基线同步。

## 既有证据与限制

不改变产品行为与身份格式之外的契约。安装版 App 经 MC-11 更新后才生效；本票不安装 App。最终 Submit 手动。

## Comments

### 2026-10-28 认领（Europe/Zurich）

由 `claude-code-4ca66ce5/root` 按用户“开始执行最前沿的票”认领（frontier 首张）。只读核对发现缺口比票面三模块更宽：
worker 的材料核验路径 `WorkerStore.material_inputs` → `application_single_binding.read_delivered_material_inputs` →
`verify_material_lineage` / `check_single_qualification` 还惰性导入 `application_job_brief`、`application_writing`、
`application_explanations`、`application_pdf_reuse`、`public_site.Profile`。本票按“worker 材料核验路径实际可导入的模块”处理，
以代码推导的入口调用图测试锁定，而不是只补三个名字。

### 2026-10-28 首轮实现与审查 NOT-READY（Europe/Zurich）

首轮：以 WorkerStore/WorkerService 调用图遍历推导惰性导入（先 RED：10 个模块不在 worker 角色），加入 worker 角色并新增
`loaded_code.load_worker_modules()` 在记录身份前预载；冻结 `4cc1c04b…` 离线 8388 passed / 3 skipped / 0 failed
（[offline-r1](../../remaining-tickets-2026-10-26/mc20-worker-role/acceptance/offline-r1/offline-result.json)）。

独立审查 NOT-READY：P1 调用图只跟随裸名与 `self.` 调用，漏掉经其他对象的调用——普通路径
`check_single` → `verify_material_lineage` → `store.read_export` / `store.draft` 仍惰性导入 `application_resume_versions`、
`application_proofread`、`application_content_reconcile`；P2 文档与注释因此言过其实，且缺少运行时身份与构建测量的跨进程核对。
浏览器 r1 因源码将改而中止（[保留](../../remaining-tickets-2026-10-26/mc20-worker-role/acceptance/browser-r1-aborted/)，不计入）。

改为可靠规则（替换遍历，不叠加）：**每个角色须包含其模块的全部静态包导入闭包**（模块级与函数内）。先 RED（worker 缺 22 个模块，含上述三者），
补齐后 GREEN；worker 因此也预载控制器侧准备路径（覆盖而不执行，代价是身份随这些代码变化）。
`test_worker_startup_loaded_identity` 原断言“worker 不加载 application_preparation”改为断言已加载（其审计钩子仍禁止启动时 socket/子进程）；
`test_loaded_runtime_identity` 改为先 `load_worker_modules()`；新增跨进程测试：worker 运行时记录的身份 = `measure_packaged_roles`（两种顺序）。

### 2026-10-28 结案（Europe/Zurich，`claude-code-4ca66ce5/root`）

**Resolution：** 每个 loaded role 须包含其模块的全部静态包导入闭包（模块级与函数内）；worker 角色补齐 36 个模块，
`loaded_code.load_worker_modules()` 在 worker 记录启动身份前预载整个角色，启动身份因此覆盖材料核验及其余可惰性导入的代码
（控制器侧准备路径无论 worker 是否执行都被覆盖，代价是 worker 身份随这些代码变化）。`application_preparation_fixtures` 豁免；
过宽的注释与文档字符串已改为只陈述测试证明的内容；新增跨进程测试核对运行时身份与 `measure_packaged_roles` 两种顺序一致。

**验收**（[记录](../../remaining-tickets-2026-10-26/mc20-worker-role/acceptance/README.md)）：冻结 r2 `d32a552d…`（1828 文件，含 MC-10 准备的 12 个文件）
离线 8388 passed / 3 skipped / 0 failed，隔离浏览器 380 passed / 8 native opt-in skips / 0 failed，运行前后无漂移；
Ruff 与 MC-18 棘轮通过（基线不变）。审查 r1 NOT-READY → 改为闭包规则；[审查 r2](../../remaining-tickets-2026-10-26/mc20-worker-role/acceptance/review-r2.md) READY-TO-CLOSE，无 P1/P2。

**范围说明（criterion 5）：** native 未运行——无驱动层改动；安装版 Cua 用例在 MC-11 前运行的是旧安装 App，`--cua` 路径在身份写入后才分叉。
MC-17 清单（`docs/codebase-responsibilities.md`）已同步；MC-18 基线无需变化。

**留给后续（冻结字节内未改，记入地图 fog）：** 闭包扫描未识别 `from career_evidence_graph import X` 形式（当前源码无此用法）；
`loaded_code.py` 注释“covered, not executed”应为“无论是否执行”；`application_preparation_fixtures` 豁免理由漏写 `--synthetic-mail`；
跨进程测试未覆盖带岗位启动。另审查发现既有问题：worker 解析但从不校验 `--expected-worker-revision`，`require_packaged_worker_identity` 无生产调用方——与 MC-11 安装身份相关。

安装版 App 经 MC-11 更新后生效；未运行真实模型、native、安装 App 或真实 ATS；未提交 git（其后已提交为 `d87f6cd`）。最终 Submit 手动。
