# R01：保护保存模板时的已有配置

Type: bug
Label: wayfinder:task
Status: closed
Priority: P2
Interaction: AFK
Assignee: config_repair
Created: 2026-10-25
Parent: [审计修复计划](../map.md)
Blocked by: 无
Triage: verified

## 已确认问题

审计身份：N1。保存模板路径时整体重建配置，可能删除材料目录、邮件处理及扩展设置。优先保护已持久化的用户设置。
证据以[原审计报告](../../work-audit-2026-10-25/README.md)为准，原实验补丁已撤回。

## 文件所有权与最小范围

`career_portal.py` 的 CLI 配置保存；`tests/test_career_portal_cli.py`。

复用现有配置校验及已导入的原子写入 Interface。只更新本次适用字段，保留其他有效字段；保持坏配置与符号链接的拒绝行为。

## 验收条件

- [x] 旧配置的材料目录、邮件设置、未知字段和未指定的模板／manifest 字段均保留。
- [x] 显式参数按现有语义保存；首次配置保存与正常重新读取仍可用。
- [x] 坏 JSON、错误结构及符号链接不会被静默覆盖。
- [x] 原子替换失败保留旧文件原字节，临时文件清理；测试只使用合成配置。

## 状态与执行范围

本轮已实施并完成定向红绿回归；组合验收与独立复审由 R07 收尾。技术前置依赖为无。
新增 9 项公共 CLI 回归在本轮原始源码上失败（9 failed / 14 passed），修复后该文件 23 passed。
配置加载与保存共用已有路径校验，保存合并指定字段，并使用已导入的 atomic_write_json。
测试覆盖未指定模板／manifest、材料目录、邮件设置、嵌套未知字段保留，坏 JSON／结构及符号链接拒绝，
原子替换失败保持原字节并清理临时文件。首次保存、重开及模板轮转的原测试继续通过。
Ruff check 与 format 通过；原实验补丁未复用。
日志：`/private/tmp/tomorrowstar-audit-repairs-2026-10-25/r01/red.log`、`green.log`。
不改真实私人配置／材料，不运行真实模型、Prism 或 ATS，不更新 App；最终 Submit 保持手动。

## 最终收尾 — 2026-10-25

本票通过本轮源码验证及独立复审，随 R07 关闭。最终版本、组合回归、安装差异及真实验收边界见[实施与交接](../implementation.md)与[机器摘要](../verification.json)。原规划段落及中间状态保留为历史。
