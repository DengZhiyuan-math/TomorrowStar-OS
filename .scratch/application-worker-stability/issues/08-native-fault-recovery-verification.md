# 验证真实故障恢复

Type: task
Label: wayfinder:task
Execution: verification
Interaction: AFK with bounded HITL observations
Status: closed
Assignee: root
Parent: [申请 worker 稳定性开发票](../README.md)
Blocked by: none
Created: 2026-10-13

## What to execute

用本次自有 worker、真实浏览器进程和 loopback 合成 ATS，在实际单页关闭/crash、
context/browser 断连及 worker 退出后，验证故障隔离、未知 intent 保留、
检查点核验、人工原页交接和明确继续。合成异常回调不替代真实进程故障证据。

## Existing contract

复用 [稳定性阶段规格](../../application-worker-next-stage/assets/stability-contract.md)、
[从检查点核验后恢复申请](06-checkpoint-recovery.md)及
[当前故障交接规格](../../application-worker-next-stage/issues/07-recovery-handoff-prototype.md)。
不重建恢复系统，不把检查点、PID 或 `page_open` 当成当前 DOM 的证据。

## Execution limits

- 按用户顺序，在冷启动票之后推进。本票没有由冷启动根因决定的技术依赖。
- 现有 worker、浏览器、页面和附件不参与故障注入、接管或重启。
- 故障只作用于本次记录的自有进程、页面和临时记录；真实 ATS、模型和 Submit 为零。
- 原页可用时保持同一 DOM、填写值和 File 对象；不可用时核验历史，再建立新运行。
- 未知保存/上传不重传；仅同步不触发浏览器动作；暂停批次须明确继续。
- 不让本机全局 sleep/wake 干扰现有资源。真实系统休眠/唤醒只能在隔离主机或
  后续明确适合的窗口验证；缺少该条件时记为 unobserved，不能以模拟 sleep 充当通过。

## Acceptance

- [x] 固定自有进程与源码身份；保留其他运行和私人文件的前后保护记录。
- [x] 原生单页故障只暂停该岗位；其他自有岗位继续。
- [x] 共同故障暂停整批，不自动重连或重复发送。
- [x] 带未知动作的检查点保留 intent、核验结论与原 attempt，只有明确继续才恢复。
- [x] 原页人工交接保留 DOM、字段和 File；原页丢失时不声称已恢复历史 DOM。
- [x] 系统 sleep/wake 的 passed/failed/unobserved 单独记录。
- [x] 报告实际故障、回读、失败、中止与人工观察；不从合成通过数推导真实 ATS 成功。

## Claim — 2026-10-13

当前会话领取本票。用户已授权在隔离 worker、浏览器和合成 ATS 中注入真实进程故障。
所有注入限定为本轮新建资源。现有运行保持原状。

## Execution comment — 2026-10-13

执行证据：[真实故障恢复验证 — 隔离执行记录](../../native-fault-recovery-verification-2026-10-13/README.md)。
五类实际故障已有通过证据：单页关闭、renderer crash、worker 上传前 SIGKILL、
ATS 接收后 worker SIGKILL、ATS 接收后浏览器主进程 SIGKILL。
原页交接、未知上传不重传、检查点核验及明确继续均有合成请求账本回读。
79 个离线检查点回归通过；现有私人状态/附件、进程启动身份及历史包保留。

**Status 保持 open。** 原 native 回归首轮有 13 passed、2 crash failed。
之后原用例 1 次最小复验及 4 次追加复验通过，不能覆盖最初失败。
独立 worker 的 renderer 场景通过，但原 crash 事件期限失败原因仍未知，
因此单页故障验收项暂不关闭。本轮仅修改诊断探针与本地执行记录，未改 production 源码。
原页可用时保留同一 DOM 和 File；进程退出后建立新页，不声称恢复历史 DOM。
系统 sleep/wake 与真人 Acceptance 均为 unobserved。真实 ATS、模型和自动 Submit 为零。

后续从新目录继续鉴别首次 crash 事件及命令期限边界，保持原 1500 ms/2 s 标准。
冷启动票及其封存结果未修改。

## Continuation claim — 2026-10-13

用户已授权继续复现、定位并修复首轮两次 crash 回归失败。
仍由 root 领取。沿用原 1500 ms 事件和 2 s 诊断期限。
本轮使用新的隔离资源及后继证据目录，保留原失败、旧证据和现有运行。

## Resolution comment — 2026-10-13

修复与完整证据：[Crash 回归根因与夹具修复](../../crash-regression-rootcause-2026-10-13/README.md)。
首轮两种错误已在原双岗位 contract 中通过真实自有 renderer 故障复现。
旧 `chrome://crash` 的 fatal 退出路径延迟真实 crash 事件；快速 `ERR_ABORTED`
不能证明故障已到达。动作中的等待超时还会被 worker 的 Error 兜底捕获，
在没有事件事实时保留 `browser_result_unknown`，或掩盖已经超出的事件期限。

修复限定为两份测试文件：使用原生 renderer 终止入口，仍以真实 Page crash
事件确认故障，并在 worker catch 外独立检查 1500 ms 事件期限。
新增有界 renderer 暂停回归先红后绿。原 1 s 命令和 2 s 诊断期限不变。
修复后 20 个相关 native 检查、16 次原函数重复及 79 个相关离线检查通过。
单页故障后其他岗位继续，原页及 File 保留，未知结果不重传；worker 行为未修改。

本票按隔离合成验证范围关闭。首轮失败与 1082 个历史包文件保持原字节；
现有私人状态、附件、设置与进程启动身份回读保持，本轮资源均退出。
一轮新增诊断逐例 JSON 曾被后轮覆盖；原日志、JUnit、覆盖前读回及完整后继对照
均在修复报告中说明，不冒充恢复的原 JSON。
未追补首轮当时的系统级调度细节，未宣称历史生产 TargetClosedError 底层原因已解决。
真实 ATS / 模型 / 自动 Submit 为零；真人 Acceptance、真实 sleep/wake 及冷启动根因仍未观察。
