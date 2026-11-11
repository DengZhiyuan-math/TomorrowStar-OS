# 审计修复导航

[优先级、依赖、并行安排与完成条件](map.md)。
[原三轮审计及证据摘要](../work-audit-2026-10-25/README.md)。

本计划的七张修复票均已关闭：六张对应原确认发现，一张为组合验证。源码修复、回归和独立复审见[实施交接](implementation.md)；
后续获明确授权的唯一主 App 同步及安装后验证见[安装记录](installation.md)。历史规划状态另见
[规划时验证快照](planning-verification.json)，不代表当前待办状态。

[后续审计](../post-repair-audit-2026-10-25/README.md)另确认当前格式复用、大小限额恢复、运行中匹配跨 Skip、并发配置保存及本导航旧表述问题。
这些后继问题由[本轮修复记录](../post-audit-repairs-2026-10-25/README.md)单独持有，不把原票状态当成所有相邻路径均正确的证据。

从 checkout 查询：

```sh
uv run --locked --offline --no-sync python -B scripts/query_tickets.py --json
```

按 `.scratch/audit-repair-plan-2026-10-25/issues/` 过滤本计划。依赖关系无环不等于已执行修复；当前关闭依据见各票及实施交接。
