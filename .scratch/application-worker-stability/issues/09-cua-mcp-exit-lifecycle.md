# 修复 Cua MCP 后端退出后的传输关闭阻塞

Type: task
Label: wayfinder:task
Execution: development
Interaction: AFK
Status: closed
Assignee: root
Parent: [申请 worker 稳定性开发票](../README.md)
Blocked by: none
Created: 2026-10-14

## What to build

复验 Cua MCP 后端先退出、stdout 管道仍被持有时，客户端关闭是否阻塞。
若复现，最小修复响应读取线程的停止与回收，保留协议、Unicode、
原调用期限、Playwright owner-thread pumping 和未知结果不重发语义。
这是独立传输生命周期缺陷，不解释 Dock 上游或冷启动窗口阻断来源。

## Execution limits

- 用户要求继续系统开发，沿用稳定性优先及本地 tracker；root 已领取。
- 仅使用新建合成 MCP 后端和真实 OS 管道，不启动浏览器、CuaDriver 或桌面代理。
- 保留现有 worker、浏览器、页面、附件、未提交工作与所有封存包。
- 不执行真实 ATS、模型轮次、自动提交、部署或应用更新。
- 封存失败与后继证据；不改写旧故障记录。

## Acceptance

- [x] 真实管道复现并保存关闭超时；后端已确认退出。
- [x] 相同场景在 2 秒内关闭，读取线程与管道回收；无重发。
- [x] 分块 UTF-8、半帧、EOF/断线、初始化失败与重复 close 的相关回归通过。
- [x] 相关 worker/Cua 离线回归及要求的检查通过。
- [x] 原有资源与封存包回读保持，所有本轮子进程退出。

## Claim

2026-10-14：root 从系统稳定性开发中识别该边界，先测试后修复。
执行与失败保存在 [后继开发包](../../cua-mcp-exit-stability-2026-10-14/README.md)。

## Resolution comment

2026-10-14：后端 exit=0、stdout 另一写端仍开放时，实际公共 `close()` 超过2秒；EOF 对照通过。修复以标准库 selector/os.read 读取响应，停止事件与非 daemon 线程 join 先于流关闭，保留原调用/进程等待期限、owner-thread pumping 和未知结果不重发。

完整离线 939 passed、119 deselected，新增9项全部通过；Ruff/格式通过。127个输入及交付副本回读匹配，3,617个旧封存文件与原私人记录/附件、进程身份保持。本轮合成子进程退出，不启动真实 Cua/浏览器，不操作真实 ATS或模型，不启用桌面代理或安装应用。

实际失败、准备阶段日志句柄错误、EOF 对照与输入重建来源均保留。此票关闭的是 checkout 的传输修复及合成验收；真实原生 Cua 对该边界尚未复验，Dock 上游触发来源与冷启动票继续开放。

## 原生复验后继 — 2026-10-15

用户随后授权真实 CuaDriver 复验，并明确要求升级驱动。安装版本已更新到0.35.2，原有服务未重启，0.21.0回退包完整保留。
[新版原生后继](../../cua-mcp-native-verification-2026-10-15/README.md)的4项纯传输检查通过：后端先退出、持有输出写端、原样响应与丢失成功只读回执后的不重复派发；持有写端时close约0.099秒，原2秒期限保持。真实变更回执丢失未执行。

0.21.0首轮的2项关闭通过和1项ref绑定失败保留；0.35.2浏览器预检又被前台风险守卫拒绝，记录在[后台附着兼容性票](10-cua-035-background-attach.md)。没有把纯传输通过升级成完整浏览器验收。旧临时原始诊断现不可读的留存缺口明确记录，新数据改用持久私有目录。
