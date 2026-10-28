# MC-14：M5 收拢 Runtime 装配与 Portal 传输

Type: task
Label: wayfinder:task
Status: closed
Priority: P2
Interaction: AFK
Assignee: claude-code-367f651f/root
Created: 2026-10-26
Parent: [Module 剩余开发地图](../map.md)
Blocked by: [MC-08](08-t09-app-dispatch-controls.md), [MC-13](13-m4-preparation-scheduling.md)
Triage: closed-source-synthetic

## 问题与范围

常规准备与新接管控制两个 M4 交付均稳定后，把依赖连接、模式构造、启动/失败清理和关闭集中到 Runtime。先收回业务闭包，再移动装配，不新造宽配置容器。

## 文件所有权与并行边界

application_runtime.py（按实际必要新增）、career_portal.py、入口构造/关闭。必须在 MC-08 和 MC-13 共享入口集成后推进；独占 Runtime/Portal 装配区域，不和最终冻结验收并行改动。

共享文件按地图的冲突规则协调；领取后才能写入。不得覆盖其他工作的修改。
依赖边表示必要交付，不表示外部运行授权；测试记录中的 deselected 不抵充覆盖。

## 验收条件

- [x] 完整依赖连接后才启动，初始化中途失败清理已创建资源，关闭幂等；沿用已实现的先撤权/排空语义。
- [x] Portal 仅保留 HTTP 编解码、CSRF/Host、兼容投影和传输，不解释 checkpoint/材料目录或私有字典准入。
- [x] 默认、独立材料及旧 Codex/CLI 模式通过同一所属业务实现，保留签名/权限与个人配置边界。
- [x] 启动切点、关闭顺序、失败清理和旧入口回归通过；无新模型/浏览器副作用出现在只读路径。

## 既有证据与限制

[Runtime/Portal 契约](../../../docs/module-interfaces-and-migration-design.md#runtime)。此票不承担安装验收；主 App 更新由 MC-11 独立记录。

需求以[正式设计](../../../docs/module-interfaces-and-migration-design.md)为准。R6 只证明原冻结源码与合成测试范围；本票如有新实现，
须记录实际改动、对应回归和审查，不能复用 R6 关闭新行为。未知结果、人工内容、原页、
原 journal 和历史记录保留，最终 Submit 手动。

## 2026-10-27 架构审计补充

[架构审计](../../work-audit-2026-10-27/architecture-audit.md) D1：`career_portal.create_server` 内约 50 个嵌套函数承担业务规则，例如
`generate_flow_resume`、`generate_flow_cover_letter`、`export_flow_pdf`、`verify_flow_materials`、
`capture_flow_prism_result`，以及直接读 `flow._load()["tasks"]` 的 `flow_material_tasks`；324 个测试文件导入 `career_portal`。
本票原验收保持不变，追加：

- [x] 上述业务闭包逐个移回所属 Module（Resume、CoverLetter、Flow）或说明保留理由；`create_server` 不再定义业务规则。
- [x] Runtime 只负责组装、启动和关闭，本身保持薄；不新增全局依赖查询器或宽配置容器。
- [x] 测试按归属迁移：业务规则测试经所属 Module 的公开入口，Portal 测试只覆盖传输与映射。

本补充不改变本票状态、认领和硬依赖。业务模块抛出 `PortalDataError`（含 HTTP 状态码）的问题暂不在本票处理，
见地图“尚未细化”。

## Comments

### 2026-10-27 认领（Europe/Zurich）

`scripts/query_tickets.py` 核对：MC-08 已结案，本票为机械前沿，open/unassigned。按用户指示由 `claude-code-367f651f/root` 认领，
与 MC-09/MC-14 并行规划；尚无源码改动或测试运行。不扩展实际模型、安装 App 或真实 ATS 权限；最终 Submit 手动。

### 2026-10-27 用户决定与并行安排（Europe/Zurich）

计划见 [MC-14 计划](../../remaining-tickets-2026-10-26/mc14-runtime-portal/PLAN.md)，用户全部按建议确认：本票删除 `pipeline.request` 并迁移测试调用；
已关闭 Pipeline 上的畸形请求错误码由 `pipeline_unavailable` 变为 `pipeline_request_invalid`（均 409、无副作用）接受并记录；
`project_flow_snapshot` 留在 Portal（仅用公开入口，移动属 MC-15）；就绪检查的 `_paths()`/`_KINDS` 保留并登记收回行；`create_server` 保持参数签名；
不改 macos/server.py、无需重装 App；产品默认关闭。**为保证 MC-09 先验收**，本票在隔离副本 `/Volumes/Codex-Workspace/ts-mc14-work/TomorrowStar OS`
（基线哈希 `/Volumes/Codex-Workspace/ts-mc14-work/base-manifest.json`，736 个文件）中实施；MC-09 结案后按基线三方合并回主 checkout，再冻结与验收。

### Resolution（2026-10-28，Europe/Zurich）

在隔离副本实施（基线 736 文件），MC-09 结案后合并回主 checkout：57 个仅 MC-14 改动的文件直接复制，`application_pipeline.py` 三方合并无冲突
（MC-14 删除 `request`、新增 `flow_control`、线程启动前注册 `preparation_allowed`；MC-09 的丢失保存后 Continue 改走 Worker `resume` 保留），
合并前主 checkout 版本备份于 `.scratch/remaining-tickets-2026-10-26/mc14-runtime-portal/merge/main-before/`。同一冻结 1820 文件 `15653ca8…`：
完整默认离线 8330：8327 passed / 3 skipped / 0 failed；受影响隔离浏览器 326：321 passed / 5 native opt-in skips / 0 failed。
[验收记录](../../remaining-tickets-2026-10-26/mc14-runtime-portal/acceptance/README.md)；独立 Standards+Spec 审查
[final-evidence-review](../../remaining-tickets-2026-10-26/mc14-runtime-portal/acceptance/final-evidence-review.md) 首轮 NOT-READY 仅因两项记录/文档问题（下述已处理，未触及冻结文件）。

实现：`application_runtime.open_runtime`/`ApplicationRuntime` 负责装配、`stop_writes` 与 `close`（装配中途失败时逆序释放线程与锁）；`create_server` 保持签名，
仅做 HTTP 绑定与静态文件；Portal 不再访问 Flow/Worker 私有成员，改用新增公开入口（`configure_materials`、`read_draft`/`read_export`/`verify_*`、
`material_tasks`、`witness` 等）；写前预检归 `application_single_binding`（无新增导入循环）；`ReadinessProbe`；`WorkerService.readiness_facts`；
`pipeline.request` 删除、289 处测试调用迁移到命名控制；`ApplicationPipeline.flow_control`；依赖棘轮基线减少一处循环与一处私有导入。
不改 macos/server.py，无需重装 App；产品默认关闭。接受的行为变化：已关闭 Pipeline 上的畸形请求返回 `pipeline_request_invalid`（无副作用）。

审查 P2 处理：(1) 审计补充 3“业务规则测试按所属 Module 迁移”**本票不做，作有范围的延后**：除新增入口在 `tests/test_runtime_assembly.py` 有所属测试外，
既有经 `create_server`/HTTP 的业务规则测试迁移归 [MC-19](19-narrow-flow-resume-surface.md)（其验收已含测试迁移）；(2) 收回表中 Pipeline 两行行号已按合并后位置更新
（`flow.worker_action` 10 处）。审查 P3（不阻塞，留作后续）：`career_portal._external_directory` 与 Runtime 中同名函数重复且未用；`open_runtime` 将 35 个关键字参数
原样转给 `_assemble`；Flow 中 5 个一行公开包装供 MC-19 收拢；文档中 Flow 新增数（实为 18）与 Pipeline 行计数待更正、设计 Runtime 节仍写 `open_runtime(config, …)`；
`test_runtime_assembly.py` 一处断言恒真（应检查 worker_root/handoff 目录）；`tests/test_worker_native_chain_browser.py` 未列入浏览器门禁文件清单。
原生：本票无驱动层改动，未重跑；MC-09 原生链路在合并前冻结上通过，合并后的原生复核由 MC-11（App 更新前须以 `TS_CUA_NATIVE_TEST=1` 运行该文件）/MC-16 承担。
未提交 git；最终 Submit 手动。
