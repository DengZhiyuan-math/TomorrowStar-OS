# 核验浏览器生命周期与故障恢复的原生边界

Type: research
Label: wayfinder:research
Status: closed
Interaction: AFK
Assignee: worker_lifecycle_research
Parent: [申请 worker 下一阶段：稳定性、普适性与效率决策地图](../map.md)
Blocked by: none

## Question

现有 Python / Playwright 模型能以哪些原生事件、进程事实和磁盘检查点区分页面局部关闭、浏览器关闭、worker 退出和控制失联？在不增加常驻浏览器服务的前提下，哪些恢复保证成立，哪些不能承诺？

核验 context / browser 的关闭、崩溃和断连事件，persistent profile 与 DOM 的区别，连接已有浏览器的能力与约束，待发送、已发送但未回读、已核验三种结果的处理边界。检查当前轮询和异常传播可能影响其他页面的路径，但不从 `TargetClosedError` 单独断定历史退出原因。

## Evidence and assets

- [当前生命周期实现](../../../src/career_evidence_graph/application_worker_browser.py)
- [当前进程与检查点实现](../../../src/career_evidence_graph/application_worker.py)
- [运行状态与验证边界](../../../docs/application-worker-workflow.md)

## Resolution requirements

先领取。使用 research 技能，核验官方文档与已安装源码版本。只读当前代码；不连接真实招聘页、不读取个人运行目录、不启动模型或真实请求。
产出一份引用完整的研究报告。区分已证事实、候选最小方案、未验证边界和需要人决定的保证等级。
报告保存到研究分支，记录当前未提交实现的哈希上下文。不要切换或清理主工作区，不提交运行代码。
以 resolution comment 记录报告、分支、revision 和结论，完成后关闭研究票；HITL 票保持开放。

## Resolution comment

2026-10-11，worker_lifecycle_research 完成官方文档和安装源码核验。

- 报告：[申请 worker：浏览器生命周期与恢复边界](../../../research/application-worker-lifecycle-2026-10-11.md)。主工作区副本与提交报告逐字节一致。
- 分支：`D_m/research/application-worker-lifecycle-20261011`；revision：`789cc433dcc19eb726200357e5d8422c1f4a8714`。仅提交报告。隔离工作区：`/private/tmp/tomorrowstar-application-worker-lifecycle-20261011`。没有切换主分支、push 或 PR。
- 实现绑定：`source-hashes.json` 的 worker、browser 和 Ashby 三份源码哈希重算一致。安装运行时为 CPython 3.13.14 / Playwright 1.63.0；报告记录安装源码指纹。
- 已证事实：原生事件可区分 Page close/crash、Context close、Browser disconnected 的观察范围；Popen 可证明受管 worker 退出。TargetClosedError 和过期心跳不能唯一证明历史根因。
- 已证源码路径：首 Page 的轮询等待和命令页面操作在 per-job catch 外；局部关闭竞态可能结束整个 worker。尚未通过浏览器实验复现，也不据此断定历史退出原因。
- 恢复边界：profile / 检查点不等于原 DOM；CDP 只能连接仍存活的 Chromium。当前 intent 不能可靠区分未发送与已发送未回读；未知上传无通用自动重传保证。
- 候选最小方案：保留单 worker 与现有 store；补原生事件和运行身份，收紧局部异常边界，验证 context 级同步事件等待，保留不确定动作。恢复保证等级、重开/重填和未知上传交接仍由 HITL 票决定。
- 验证：3 份主源码哈希、11 个本地链接实例、报告副本一致、仅报告入提交及 staged diff 检查通过。没有读取个人运行目录或真实 trace；没有启动浏览器、worker、模型或真实招聘请求。
