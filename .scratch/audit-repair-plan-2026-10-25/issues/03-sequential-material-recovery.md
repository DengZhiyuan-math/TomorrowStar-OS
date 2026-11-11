# R03：约束旧岗材料恢复的跨岗执行

Type: bug
Label: wayfinder:task
Status: closed
Priority: P2
Interaction: AFK
Assignee: queue_repairs
Created: 2026-10-25
Parent: [审计修复计划](../map.md)
Blocked by: 无
Triage: verified

## 已确认问题

审计身份：S1。独立材料准备模式及公开程序入口可在新岗作者仍运行时排入旧岗一致性检查。
证据以[原审计报告](../../work-audit-2026-10-25/README.md)为准，原实验补丁已撤回。

## 文件所有权与最小范围

`application_flow.py` 的作者预留、取消后成功回执复用及一致性重试；`test_cover_letter_pair_cancellation.py` 和既有 Flow 测试。

复用现有作者预留路径的跨岗 pending 规则，保持唯一 Implementation；在采用旧回执、修改状态、保存或排队前应用。

## 验收条件

- [x] 两个入口分别验证：取消后迟到成功信件的显式复用、取消／未开始的一致性检查重试。
- [x] 另一岗位的信件或一致性检查为 queued、running 或 needs_recheck 时，旧岗恢复不得启动模型或排入检查。
- [x] 拒绝后旧岗快照、成功回执、人工内容和新岗状态不变。
- [x] 无其他岗位占用时，精确绑定的已知成功回执仍零作者调用复用；未知结果不重放，正常同岗恢复仍可用。

## 状态与执行范围

2026-10-25 已按用户 implement 授权实施。仅修改所属源码与合成回归；未提交、未发布、未更新 App。
独立复审与最终冻结组合回归由 R07 记录。旧审计及原票历史不变。

## 本轮证据

- 失败先行：原源码定向回归 14 failed / 22 passed；真实 loopback HTTP 将旧岗 A 的刷新错误返回 200。
- 最终测试对照：隔离复制当前源码，仅用实施前备份替换 Flow/Pipeline 两文件，最终同组用例为 17 failed / 22 passed。
- 当前修复定向验证：最终 91 passed（包含先行 Flow 回归；早期最小组 39 passed），含其他岗两种材料分支 × 三种 pending 状态 × 两个恢复入口；真实新岗作者屏障、无新调用、完整快照/回执保留及释放后合法恢复。
- HTTP 组合：A 以公开 Skip 保留材料，B 合成等待；A 刷新/两材料入口均拒绝。凭证、Origin、task revision 与 request_id 重复请求已覆盖；公开 Return A 后合法刷新仅调用一次匹配器。
- 实施精确补丁与日志：`/private/tmp/tomorrowstar-audit-repairs-2026-10-25/r02-r03/changes.patch`、`red.log`、`http-red.log`、`final-tests-baseline-red.log`、`green.log`。
- 所有模型/网页/编译边界使用现有合成替身；没有真实模型、Prism、ATS 或私人配置/材料操作。最终 Submit 保持手动。

测试修正说明：广回归曾因 B 简历正常完成而改变树快照，两个并发测试误报。现先等待 B 简历完成，同时继续阻塞 B 信件作者，再验证拒绝零写入；产品实现未变化。该失败日志 `affected.log` 保留，最终受影响回归另记 `affected-final.log`。

最终受影响回归：十个 Flow/Pipeline/匹配/HTTP 文件 **284 passed，77.81 秒**，日志 `affected-final.log`。最终五个源码/测试文件 Ruff 与格式检查通过。

## 最终收尾 — 2026-10-25

本票通过本轮源码验证及独立复审，随 R07 关闭。最终版本、组合回归、安装差异及真实验收边界见[实施与交接](../implementation.md)与[机器摘要](../verification.json)。原规划段落及中间状态保留为历史。
