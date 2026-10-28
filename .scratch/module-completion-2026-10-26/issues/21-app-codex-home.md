# MC-21：正式 App 的 Codex 使用专用目录而非用户本人 HOME

Type: task
Label: wayfinder:task
Status: open
Priority: P2
Interaction: HITL
Assignee: none
Created: 2026-10-28
Parent: [Module 剩余开发地图](../map.md)
Blocked by: none
Triage: needs-implementation

## 问题与范围

MC-10 规划时发现（见 [MC-10 计划](../../remaining-tickets-2026-10-26/mc10-live-model/PLAN.md) B2、
[2026-10-28 工作审计](../../work-audit-2026-10-28/README.md) 问题 4）：`macos/server.py` 组装 Codex 接管配置时
以 `"home": str(Path.home())` 作为 Codex `HOME`，用户 `~/.codex` 下的个人 AGENTS.md、skills、memories、rules、config.toml
可能进入模型上下文，违反只用申请所需数据的边界。MC-10 只在测试中改用隔离目录，正式 App 未改。

## 文件所有权与并行边界

`macos/server.py` 的 Codex 配置组装及其测试；必要时 `application_codex_assist.py` 的目录检查。
须在 MC-11 更新安装 App 之前完成；与 MC-20、MC-22 不共享文件时可并行。
共享文件按地图的冲突规则协调；领取后才能写入。不得覆盖其他工作的修改。
依赖边表示必要交付，不表示外部运行授权；测试记录中的 deselected 不抵充覆盖。

## 验收条件

- [ ] 正式 App 使用 `~/Library/Application Support/TomorrowStar/` 下的专用 Codex 目录（与 MC-10 的隔离目录约定一致或说明差异），不再使用 `Path.home()`。
- [ ] 目录不存在或未登录时，接管按“能力不可用”停止并给出用户可执行的登录说明，不回退到用户本人 HOME。
- [ ] 回归覆盖：配置中的 HOME 不是用户 HOME；专用目录中出现 AGENTS.md/skills/memories 等个人配置时按 MC-10 隔离检查处理。
- [ ] 用户本人在专用目录中登录（HITL）；agent 不读取凭据。
- [ ] 离线与受影响隔离浏览器通过，独立审查 READY；MC-17 清单同步。

## 既有证据与限制

测试侧隔离检查已在 MC-10 准备中实现（`tests/codex_live_guards.py`），可复用。本票不安装 App、不调用真实模型。最终 Submit 手动。

## Comments
