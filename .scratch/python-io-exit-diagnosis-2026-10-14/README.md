# Python 退出 I/O 锁崩溃：来源追查与隔离修复

2026-10-14，Europe/Zurich。用户授权追查 PID 12530、隔离复现并修复，保留现有运行、附件与封存包。

## 来源与置信度

**PID 12530 高置信关联到 chat「解释当前问题」中的隔离过滤代理**：[原脚本](</Volumes/Codex-Workspace/live/home/zhdeng/Documents/Codex/2026-10-13/new-chat/outputs/codex-filter-prototype/codex_filter_proxy.py>)。它使用 Homebrew Python 3.14.5，含阻塞读取 stdin 的 `feed` 守护线程。

该 chat 的原始命令记录显示：2026-10-14 00:05:04.768 至 00:05:09.105，运行直接后端与代理后端的顺序探针。代理通过 `work/reproduce_codex_warnings.py` 启动；报告中 Python 12530 于 00:05:05.9361 启动、00:05:09.0917 中止，处于该命令窗口中。直接基线耗时 1.117 s，代理探针耗时 3.154 s，与进程时间链匹配。

从该 chat 的 4 次文件变更重建了当时实际代理源码，最后一次修改早于探针。重建文件与当前原型相同：9,393 bytes，SHA-256 `37869ad811a70a6bb4a0dac3bb44824e28afaefdf943f2c207b37b9db9755fcf`。[来源绑定](historical-source-binding.json)保存命令身份、源路径、版本与摘要。历史原始命令和文件变更记录只保存在私有目录。

原报告的父 PID 是 12430，但历史 OS argv/exec 事件没有留存。因此，这是时间链、精确执行版源码、线程与栈特征共同支持的高置信归因，不把它表述为已有 OS argv 直接证明。此前封存报告中的“未确认”原样保留；本报告是后继结论。

## 实际红测与因果对照

复现使用重建的实际代理、Python 3.14.5 和新建假后端。父进程保持输入管道开放；假后端打印就绪后退出 0。没有运行真实 Codex 后端、浏览器、Cua 或 ATS。仅对新子进程设置 core dump 上限 0，没有修改系统崩溃报告设置。

已运行的红测命令：

```sh
PYTHONDONTWRITEBYTECODE=1 uv --cache-dir /private/tmp/ts-fixed-space-uv run --locked --offline python -B .scratch/python-io-exit-diagnosis-2026-10-14/run_exit_case.py .scratch/python-io-exit-diagnosis-2026-10-14/inputs/prototype-executed/codex_filter_proxy.py .scratch/python-io-exit-diagnosis-2026-10-14/red-input-open
```

输出为子进程 exit=-6、`io_lock_fatal=true`，断言命令退出 1。[完整红测](red-input-open.log)保留了 `_enter_buffered_busy`、stdin 缓冲锁与 `finalizing`。本轮只故意触发这一次 SIGABRT。

| 执行输入 | 输入在后端结束前关闭 | 代理退出码 | I/O fatal |
| --- | --- | ---: | --- |
| 历史执行版，实际红测 | 否 | -6 | 是 |
| 相同源码、解释器和假后端，仅增加输入 EOF | 是 | 0 | 否 |
| 修复版，同一开放输入场景 | 否 | 0 | 否 |

[EOF 对照](control-input-closed.log)和[修复复验](green-input-open.log)均通过。[事前假设](hypotheses-before-controls.md)保存预测及排除方式。这不是通过升级 Python 或放宽退出断言得到的绿色。

用户随后贴的系统报告截图显示 PID **25292**、启动 00:23:13.8892，与本轮红测 PID/时间相同；这是本轮隔离复现产生的弹窗。[截图绑定](user-screenshot-repro-binding.json)保存摘要，原截图保持私有。该子进程已退出；未点击 Reopen 或重启原有应用。

## 根因与修复

后端先退出时，原代理主线程返回 `relay()` 并进入解释器 finalization；`feed` 守护线程仍阻塞在 `sys.stdin.buffer.readline()`，持有缓冲读取锁。原测试通常通过 `communicate()` 提前关闭输入，未覆盖这一退出次序。原探针会在输入仍开放时调用 terminate/wait，关闭次序与复现一致；旧探针没有保存代理/后端退出码或该 fatal stderr，不能仅凭探针父进程退出 0 推导代理正常退出。

实际红测的 fatal 与原用户报告的 finalize → buffered close → `_enter_buffered_busy` 栈一致。[CPython 3.14.5 实现](https://github.com/python/cpython/blob/v3.14.5/Modules/_io/bufferedio.c)在 finalization 时限时等待该锁；无法取得就触发 fatal。EOF 对照验证了尚未结束的输入读取是本场景的必要条件。

[修复补丁](proxy-io-fix.patch)仅改变代理输入读取和线程结束方式：

- 用标准库 selector 与 `os.read` 读取 stdin 文件描述符，按原上限组装/转发帧。
- 输入线程检查停止标记，selector 轮询间隔 100 ms。
- 后端退出或主转发失败后，主线程通知停止并 join，再关闭输出；输入线程不再是 daemon。

没有使用 `os._exit` 绕过清理，没有改过滤目标、Guardian/审批字段、信号或后端退出码语义，也没有新增依赖。原型的 macOS stdio 管道环境是本轮验证范围。

## 回归与交付

[Python 3.14.5 完整合成回归](fixed-suite-python314.log)：**25 passed，0 failed，3.255 s**。包括原 21 项边界测试与 4 项新增真实管道退出回归：输入仍开放时后端退出 0、退出 37、收到 SIGTERM 后正常退出、半帧输入时后端先退出。

原双向背压、超长帧、EOF、stderr、信号转发、后端回收、Guardian/审批字段及数字 token 精度测试保持通过。[定向 Python lint](fix-lint.log)通过。

修复交付到独立后继：[可用修复目录](</Volumes/Codex-Workspace/live/home/zhdeng/Documents/Codex/2026-10-13/new-chat/outputs/codex-filter-prototype-io-fixed-20261014/README.md>)。[发布字节回读](publication-readback.json)确认 6 个文件与已测副本相同。相邻 manifest 仍绑定原 CLI 摘要；本轮没有启用桌面 `CODEX_CLI_PATH`，没有重启客户端或更改其 Guardian/用户配置。旧原型、旧 assessment 和旧真实 app-server 证据保持；旧真实后端结果不算修复版验收。

完整真实桌面代理、真实 Guardian 决策及长期运行未验证。当前交付是已复验的隔离修复后继。

## 保全

[资源核对](resource-check.json)未发现本轮代理、假后端或合成测试标记的存活匹配。各退出回归还检查了对应后端已回收。[现有资源回读](existing-protection-summary.json)确认原进程身份、私人记录/PDF/设置摘要保持；现有 worker、浏览器、页面或附件的控制命令为 0。

[历史回读](history-check-after.json)：3,526 个旧文件无新增、删除或字节变化，包括前一来源调查及摘要文件。[旧原型回读](original-prototype-after.json)确认其 6 个原文件摘要保持。118 个 TomorrowStar 源码/测试/launcher/锁文件未变。用户原始 PID 12530 报告和本轮截图保持私有原件。

真实 ATS 请求、模型调用、自动最终 Submit、真实客户端代理启用均为 0。Python 崩溃已作为独立来源调查处理；它不增加冷启动自然拒绝数，也不解释 Dock 更上游的触发来源。

后继复跑应复制工具与输入到新的空白目录。`run_exit_case.py` 用 `exist_ok=False` 防止覆盖；不得向本封存包重跑红测。
