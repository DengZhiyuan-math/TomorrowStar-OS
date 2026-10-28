# 核验现有答案库能否支持补充后复用与任务恢复

Type: research
Label: wayfinder:research
Status: resolved
Interaction: AFK
Assignee: independent_runner_sources
Parent: [独立申请 worker 开发决策地图](../map.md)
Blocked by: none

## Question

固定版本 Job Apply 存储 helper 能直接提供哪些能力？独立 worker 要实现“未知问题
由用户补充、保存、后续复用”，还缺哪些最小能力？

核验问题规范化、scope、别名、确认状态、敏感值、更新和撤销、并发写入、session
答案引用及 revision。区分存储机制和调用方必须执行的复用规则。
检查是否能通过现有 helper 使用数据，避免第二份资料库或重复哈希算法。

## Evidence and assets

- 固定基线：neonwatty/job-apply-plugin `370204c58b1137d08c5a7e7449538ae6447be0b9`，版本 1.1.0，MIT。
- 上游 `scripts/job-apply-store.py`、`skills/answer-memory/SKILL.md`、`skills/answer-memory/references/storage-contract.md`。
- [可行性研究](../../../research/independent-application-runner-feasibility-2026-10-09.md)。

## Resolution requirements

使用官方源码与文档。只用显式临时 root 的合成输入，禁止读取或初始化实际申请者存储。
报告应给出直接复用 / 调用方补齐 / 尚待人决定的边界，并提供版本化源码链接。
先 claim，再研究。使用独立 `D_m/research/application-answer-library` 分支；保留报告和 context pointer。
答案以 resolution comment 追加，随后关闭本票并更新地图索引。

## Resolution comment

2026-10-09 — independent_runner_sources

已核验固定 pin `370204c58b1137d08c5a7e7449538ae6447be0b9`。安装源码与干净 clone 的五个关键文件相同。报告：[申请答案库复用：固定源码核验](../../../research/application-answer-library-reuse-2026-10-09.md)。

研究分支：`D_m/research/application-answer-library`；初始 checkpoint：`1333e9934555c6c471e01a5b5de18a95facdc611`，仅提交报告。worktree：`/private/tmp/tomorrowstar-answer-library-research-20261009`。context pointer：本票、[独立申请 worker 开发决策地图](../map.md)及报告的研究保留章节；基线 `e4a26d0c24311d014d478f7f92e58a88e6709b4b`，不包含当前主 checkout 的未提交实现。

最新 checkpoint：`8fbbac6daf790b646fbf228630ca348ddd84f518`，只将报告中的票链接标签改为完整标题。主 checkout 的报告副本与此 commit 相同；研究 worktree 干净。

验证：16 项显式临时 root 的合成 CLI 检查通过；24 次并发 helper 写入均成功，但只保留 21 条，丢失 3 条。另一个 scope probe 证实显式 key 可存入不匹配 scope，lookup fallback 会返回该记录。未访问默认或 legacy 个人存储，未改插件、源码或其他票。

## Answer

直接复用现有 helper 和一份申请答案库。未知普通问题由用户补充后保存 confirmed；后续等价题目和匹配 scope 可复用，避免重问。

调用方仍须检查返回记录的 scope、状态、敏感规则和题目语义。helper 查询不 enforce 填表资格。答案无 revision；session 只有 key 引用且不自动失效。应在私人 worker 状态绑定记录内容 digest，更新或 missing/null 撤回后重查并令旧任务准备失效。复用项目现有 canonical JSON / SHA-256 helpers，不能重写上游 question key 算法。

普通 answer/profile 的原子 replace 不是并发事务；所有写入者必须遵循同一串行入口或锁协议。policy 的 QA lease 锁不覆盖答案库，也不能当 worker 锁。

敏感值的保存和后续复用规则留给 [确定申请答案库的复用范围与更新规则](02-answer-library-contract.md)，helper 的安装/固定版本和写入所有权留给 [确定独立运行时与浏览器生命周期](04-runtime-browser-lifecycle.md)。本研究完成，不替这些 HITL 票作决定。
