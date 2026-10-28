# 修复代理：真实 app-server 隔离复验

2026-10-14，Europe/Zurich。领取人 root。用户授权使用真实 app-server 验证修复版代理；桌面代理保持未启用，现有运行与旧封存证据保持。

**本轮 9 项真实 app-server 检查全部通过。** 其中 4 项直接让后端先退出，父端 stdin 始终开放，包含未完成 JSON 半帧。后端与代理的独立退出记录均为 0，代理在 0.053–0.113 秒内退出；没有 `_enter_buffered_busy` 或 Python fatal。所有退出均在事先设置的 2 秒期限内。

## 固定执行输入

- 代理：SHA-256 `d92e8f3b5cd302aab3c3726c5869de721b0021aebedcb61c68fb4d731375a364`，10,455 bytes；与[上轮修复交付](</Volumes/Codex-Workspace/live/home/zhdeng/Documents/Codex/2026-10-13/new-chat/outputs/codex-filter-prototype-io-fixed-20261014/README.md>)一致。
- 相邻 manifest：`8700013ba41d0f6171192492042ac5e00ddf30fa234e6510bb03217ae29a6398`；未修改后端绑定或过滤设置。
- 真实后端：桌面捆绑 Codex CLI `0.162.0-alpha.17.2`；二进制 SHA-256 `0d5ac7aae20c4eda6242428d5e218c55ba96d8763fda2a271088ff37104b9d28`，运行前后核对一致。
- 解释器：原故障使用的 Homebrew Python 3.14.5。代理文件未加入测试插桩，直接通过原 shebang 执行。
- [准入记录](admission.json)、[命令与输入绑定](execution-binding.json)、[完整判据脚本](verify_real_appserver.py)保存本轮边界。

每项使用独立空白 Codex home 与空目录作为 cwd。仅向新子进程环境传递配置路径；没有修改全局环境或原配置。环境未复制认证变量或认证文件。模型 provider 固定到 `http://127.0.0.1:9`，关闭 remote plugin；不发送 `turn/start`。

协议使用官方 OpenAI Docs 的 [app-server 握手与配置读取约定](https://learn.chatgpt.com/docs/app-server)：初始化后确认 `initialized`，再读取配置和创建本轮 ephemeral 合成 thread。仅测试 `initialize`、`initialized`、`config/read`、`thread/start` 和无效方法的错误响应；没有模型轮次、工具执行或真实 ATS 请求。

## 本轮结果

| 场景 | 结束方式 / 输入状态 | 后端 / 代理退出码 | 结果 |
| --- | --- | --- | --- |
| 直接后端，RPC 配置基线 | 后端 SIGTERM；stdin 开放 | 0 / 无代理 | 通过 |
| 修复代理，RPC 配置 | 后端 SIGTERM；stdin 开放 | 0 / 0 | 通过，0.098 s |
| 修复代理，RPC 半帧 | 后端 SIGTERM；半帧未完成、stdin 开放 | 0 / 0 | 通过，0.053 s |
| 直接后端，CLI scalar 配置基线 | 后端 SIGTERM；stdin 开放 | 0 / 无代理 | 通过 |
| 修复代理，CLI scalar 配置 | 后端 SIGTERM；stdin 开放 | 0 / 0 | 通过，0.113 s |
| 修复代理收到 SIGTERM | 代理转发信号；stdin 开放 | 0 / 0 | 通过，0.090 s |
| 修复代理输入 EOF | 关闭本轮输入管道 | 0 / 0 | 通过，0.017 s |
| 直接后端，Guardian false 基线 | 后端 SIGTERM；stdin 开放 | 0 / 无代理 | 通过 |
| 修复代理，Guardian false | 后端 SIGTERM；stdin 开放 | 0 / 0 | 通过，0.089 s |

[完整复验收据](integration-evidence.json)与[执行输出](native-run-v2.log)保存 9 项结果；未重试或丢弃真实 app-server 失败。准备阶段有 **1 次观察器校准失败**，发生于任何 app-server 启动前：误用 `kqueue` 的上下文管理协议。[原失败输出](native-run.log)与[当时脚本](observer-preparation-v1.py)保留。改用显式关闭观察器后继续；没有修改代理。

后端 PID 通过本轮代理的直接子进程、精确 CLI 路径和启动时间绑定。发信号前再次核对完整身份。macOS `kqueue` 的 `EVFILT_PROC / NOTE_EXIT / NOTE_EXITSTATUS` 独立记录后端原始 wait status；代理退出码由父进程 `Popen.wait()` 获取。观察器先用本轮子进程退出 37 与 `Popen.wait()` 做[独立校准](observer-calibration.json)，避免把代理退出码当成后端证据。检查在父端输入关闭前完成，因而实际覆盖原故障的退出次序。

## 协议与 Guardian 配置

三组直接后端 / 修复代理配对均完成握手，并核对配置关键字段和错误响应。`config/read` 的整数 ID **9007199254740993** 与中文字符串 ID 保持，未丢失精度。无效方法返回相同 JSON-RPC error；本轮无关特性警告仍转发。

RPC 配置和 CLI scalar 配置中的两个旧项 `features.code_mode_tool_description_first`、`features.guardianv2.thread_context` 不再产生对应警告；原预期过滤范围保持。`Guardian enabled=true` 和 `enabled=false` 的有效配置分别读回相同布尔值。直接基线 scalar 配置的 `thread_context=true` 在代理后继配置中被移除，符合既有过滤目标。

三组配对的完整线程控制字段相同：`approvalPolicy=on-request`、`approvalsReviewer=auto_review`、`sandbox.type=workspaceWrite`，包括 sandbox 的网络和路径字段。[定向脚本检查](harness-lint.log)通过。

本轮验证的是配置、传输和退出。真实 Guardian 审批决策、模型请求、长期运行及桌面代理启用没有观察。上轮 25 项合成测试属于上轮证据，不并入本轮 9 项分母；也没有重跑旧崩溃源码产生新的故意 SIGABRT。

## 保全与后继使用

[现有资源回读](existing-protection-summary.json)确认：原 worker、浏览器与 Cua 进程身份保持；私人记录、页面记录、附件 PDF 和设置摘要保持；原桌面配置摘要及父进程代理环境保持。本轮向现有 worker、浏览器、页面或附件发送的控制命令为 0。该检查没有导航原页面；页面记录与进程保全不表述为新 DOM 验收。

[资源清理核对](resource-check.json)确认本轮 9 个后端、6 个代理均已退出，后端均已回收。[历史回读](history-check-after.json)确认 **3,579 个旧封存文件**无新增、缺失或字节变化，含上轮 Python 调查及其摘要文件；118 个 TomorrowStar 源码、测试、launcher 和锁文件不变。原代理 6 文件与已交付修复后继 6 文件分别核对不变。

完整配置响应、stderr、请求与私人保全快照只保存在本轮私有临时目录；[私有证据绑定](private-evidence-binding.json)保存摘要。公开结果仅记录合成字段及本轮自有进程身份。

真实 app-server 对该修复的隔离验收通过。冷启动票仍 open：本次独立 Python 问题不证明 Dock 上游触发来源，也不增加冷启动自然复现数。桌面代理未启用，真实 ATS 和模型轮次均为 0。

本目录封存后只读。实际已运行命令如下；后继复跑必须复制输入与工具到新空白目录，并为脚本设置新的 `PRIVATE` 目录，不能向本包或其私有目录重跑。

```sh
PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/opt/python@3.14/bin/python3.14 -B .scratch/real-appserver-io-fixed-verification-2026-10-14/verify_real_appserver.py
```
