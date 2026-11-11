# MC-19：收回 Flow / Resume 的外部私有访问并迁移内部状态测试

Type: task
Label: wayfinder:task
Status: closed
Priority: P2
Interaction: AFK
Assignee: claude-code-367f651f/root
Created: 2026-10-27
Parent: [Module 剩余开发地图](../map.md)
Blocked by: [MC-14](14-m5-runtime-portal.md), [MC-17](17-public-entry-index.md)
Triage: closed-source-synthetic

## 问题与范围

[2026-10-27 架构审计](../../work-audit-2026-10-27/architecture-audit.md) D2：Flow 与 Resume 的内部状态已成为事实上的接口。
源码中 `flow._load` 被外部调用 23 次、`store._read_version_file` 45 次、`store._draft_document` 24 次；
测试中 `pipeline._tick` 144 次、`flow._load` 91 次、`flow._save` 70 次、`flow._task` 58 次。

在 MC-14 把 Portal 业务闭包收回所属 Module 之后，对仍存在的外部私有访问逐项处理：
有实际需要的提供所属 Module 的正式入口（例如由 Flow 拥有锁和投影的 `flow.material_tasks()`），
再把调用者和对应测试迁到该入口，删除旧用法（替换，不叠加）。没有调用者的公开方法按 MC-17 清单收窄。

## 文件所有权与并行边界

application_flow.py、application_resume.py、application_resume_versions.py 及其外部调用者和相关测试。
必须在 MC-14 完成 Portal 装配迁移后进行；与 MC-15 共享文件时串行集成。
共享文件按地图的冲突规则协调；领取后才能写入。不得覆盖其他工作的修改。
依赖边表示必要交付，不表示外部运行授权；测试记录中的 deselected 不抵充覆盖。

## 验收条件

- [x] 源码中对 Flow / Resume 私有方法的外部调用为零，或逐项记录保留理由。
- [x] 新入口只表达调用者实际需要的结果，不暴露内部 JSON 结构；每个新入口有经公开接口的测试。
- [x] 迁移的测试经公开入口断言可观察结果；被替代的内部状态测试删除，不并存两套。
- [x] 行为不变：相关离线与隔离浏览器回归通过；未知结果、人工内容、原 journal 和历史记录保留。
- [x] MC-17 的入口清单和 MC-18 的基线随本票更新。

## 既有证据与限制

证据见[架构审计](../../work-audit-2026-10-27/architecture-audit.md)的 D2 与 E.7。本票不改变产品行为，
不为名称与设计一致而批量改名或加转发层。Worker 的接口收窄由 MC-06/07/08 在各自范围内处理。

## Comments

### 2026-10-28 认领（Europe/Zurich）

`scripts/query_tickets.py` 核对：MC-14 已结案，本票为机械前沿，open/unassigned。按用户指示由 `claude-code-367f651f/root` 认领，
与 MC-15/MC-19 并行规划；尚无源码改动或测试运行。不扩展实际模型、安装 App 或真实 ATS 权限；最终 Submit 手动。

### 2026-10-28 用户决定（Europe/Zurich）

计划见 [MC-19 计划](../../remaining-tickets-2026-10-26/mc19-narrow-surface/PLAN.md)，用户全部按建议确认：由 Flow / Resume 方法传入 `self`
调用的拆分文件计作所属 Module 内部，其私有调用登记理由而不改写；`_validate_export_pdf` 因冻结的 v1 生产者副本保持原名；约 67 处 `flow._save`
重放与 145 处 `pipeline._tick` 暂留，只迁移读取内部状态的断言；新增源码与测试私有调用计数棘轮；不重命名 `_fresh`/`_checked`。
与 MC-15 在主 checkout 并行开发，最后同一冻结共同验收、分别独立审查；共享文档由 root 最后统一更新。

### 2026-10-28 验收与延后记录（结案前，供复审核对）

首轮联合冻结 `a179bbef…` 经独立审查 NOT-READY（P2：收回表缺行/无决定/行号过时；另有内部状态断言读取未迁移；入口表未更新）。已处理并重新冻结：
1825 文件 `2374b341…`；完整默认离线 8365 passed / 3 skipped / 0 failed；受影响隔离浏览器 374 passed / 8 native opt-in skips / 0 failed
（[联合验收](../../remaining-tickets-2026-10-26/mc15-mc19-joint/acceptance/README.md)，首轮审查 [review-mc19](../../remaining-tickets-2026-10-26/mc15-mc19-joint/acceptance/review-mc19.md)）。

修复：补登 `getattr(flow, "_owner", True)`（保留：测试替身默认值、Pipeline 内部归属检查）、`self.flow._queue.put`（保留：Flow 内部拆分文件）与
`_content_template`（保留：Resume 内部）三行；按当前代码更正全部过时行号；入口表 Flow 行补 `valid_material_acceptance` 与 `writable_task(task_id, task_revision=None)`，
Resume 行补 `read_completed` 与 `FEEDBACK_KEY`；以其他写法出现的内部状态断言读取（`test_flow_match_execution_admission`、`test_flow_worker_interface`、
`test_p06_flow_edit`、`test_installed_readiness_browser`）改用 `witness`/`snapshot`/`task_snapshot`，私有调用计数相应下降并记录。棘轮说明已改为如实描述其计数范围。

**延后（未分配后续票，理由）：** 约 67 处 `flow._save` 状态重放（持久恢复契约，多数状态无法经公开操作到达）、145 处 `pipeline._tick`（Pipeline 单步测试接缝）、
full-LaTeX/group-review/reviewed-LaTeX/renderer/unknown-manifest HTTP 链（多所有者回归链）——即 MC-14 延后的审计补充 3 中除已迁移的草稿/导出规则外的部分；
无外部调用的 Flow 公开方法未删除（需逐方法核对路由/页面/App/测试，不属不改行为的本票）；计数棘轮只覆盖指定接收者名，其他接收者（如 `service`、`case.flow`）留待审查。
审查 P3：`bound_materials.begin`、`current_inputs` 仍为一行转调；`_existing_mismatch` 与 `_invalid` 重复一个小的错误构造；`test_bound_material_commit_recovery.py`
手写的 `material_update` JSON 与 `_stage_material_update` 写出的 `old` 字段略有差异；`test_bound_preparation_owner` 私有调用由 2 增至 4（经 `flow._queue` 交接排队项）。

### Resolution（2026-10-28，Europe/Zurich）

冻结 1825 文件 `2374b341…`：离线 8365 passed / 3 skipped / 0 failed；浏览器 374 passed / 8 native opt-in skips / 0 failed；r2 改动的
`tests/test_installed_readiness_browser.py` 补跑 6 passed（[补充记录](../../remaining-tickets-2026-10-26/mc15-mc19-joint/acceptance/browser-r2-supplement/pytest.log)，已加入浏览器门禁清单）。
复审 [review-mc19-r2](../../remaining-tickets-2026-10-26/mc15-mc19-joint/acceptance/review-mc19-r2.md)：首轮全部 P2 已解决，余下 P2（未跑的浏览器文件）已补跑，P3 记录项已更正
（README、`_owner` 理由、Flow 方法计数口径）。延后项（含 MC-14 审计补充 3 剩余的 HTTP 规则链与无外部调用的 Flow 公开方法收窄）见上方延后记录，已记入地图 fog，未分配后续票。
私有调用计数基线 566 处 / 96 文件。未提交 git。
