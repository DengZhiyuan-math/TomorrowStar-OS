# Cua MCP 退出稳定性开发

2026-10-14，Europe/Zurich。用户要求继续系统开发；按稳定性优先推进
[修复 Cua MCP 后端退出后的传输关闭阻塞](../application-worker-stability/issues/09-cua-mcp-exit-lifecycle.md)，root 领取。

本轮使用合成 MCP 后端和真实 OS 管道；没有启动 Chrome、CuaDriver、桌面代理或真实 ATS。已有运行及未提交工作保留。修复只在 checkout 交付，不重装或更新应用。

**已完成最小修复与完整离线验收：939 passed、119 deselected，新增 9 项全部通过。**

## 实际失败与原因

当合成后端确认退出 0、另一写端仍持有 stdout 管道时，原 `CuaMcpClient.close()` 在 **2 秒内不能结束**。[真实失败](red-close-held-output-v2.log)记录该断言；释放写端后测试才结束。[因果对照](control-eof-before-fix.log)为 1 passed / 1 failed：仅增加 EOF 的组通过，仍保持写端开放的组失败。关闭前两个短初始化回执均已消费，后端已由 `wait()` 确认退出；没有关闭请求或后端等待可以解释这个阻塞。

原读取线程通过 `TextIOWrapper` 的行读取阻塞等待 EOF，关闭线程尝试关闭同一缓冲流。另一个写端使读者不能退出，流关闭等待读取释放。该问题属于客户端传输清理，不证明真实 CuaDriver 出现过这一精确输出持有情况，也不解释 Dock 上游的重开触发来源。

[实现原件](cua_driver-before.py)保存改动前源码。[红测输入来源](red-binding.json)明确：执行前没有保存当时测试的独立副本，现用准备脚本加已记录补丁重建；不将重建副本表述为原始预存文件。真实失败日志保持原件。首次测试准备因内存日志句柄没有 `fileno()` 而失败，保存在 [准备失败](red-close-held-output.log)和[准备版本](repro-preparation-v1.py)，不计为关闭故障。

## 最小修复

[补丁](cua-mcp-fix.patch)仅修改响应读取与资源关闭：

- 使用标准库 selector 和 `os.read` 读取 stdout，按换行组装完整 UTF-8 帧；EOF 时仍交付最后无换行的一帧。
- 读取线程每 100 ms 检查停止事件；退出时发送原断线标记。
- 客户端关闭先停止并 join 读取线程，然后关闭 stdout 和 stdin。线程不再是 daemon。

原 JSON-RPC 解析、请求 ID、调用期限、Playwright owner-thread pumping、回执/未知计量和未知结果不重发逻辑保持。原后端 stdin EOF、wait、terminate、kill 顺序及等待期限保持。读取/解码失败进入原 `cua_result_unknown` 处理，不增加重试、备用输入路线或后台进程。

[相同复现的绿色结果](green-close-held-output.log)：2 passed。后端已退出而写端仍开放时，close 在 2 秒内结束；测试保持写端开放直到断言结束，不能通过提前 EOF 掩盖缺陷。重复 close 和流关闭也核对通过。

## 回归状态

首轮 [传输与 Cua 专项](transport-and-cua.log)：21 passed、12 deselected，2.52 s。包含新增 8 项管道/协议检查与既有 Cua 离线回归；其后增加一项 owner-thread pumping 回归。未选择的浏览器用例不是 passed。

最终输入含 9 项新增测试：持有输出写端 / EOF 对照、跨字节 UTF-8 + CRLF、最后无换行帧、残缺 JSON / 无效 UTF-8 / 无输出 EOF 后的未知结果不重发、初始化能力失败清理、owner-thread pumping。

完整离线套件：[日志](offline.log)及 [JUnit](offline.xml)为 **939 passed、119 deselected，394.95 s**，命令退出 0。[结构化结果](verification.json)记录新增 9 项全部通过；通过数与前面的专项有重叠，不相加。127 个[执行输入](offline-inputs.json)在启动前固定，[运行后回读](offline-inputs-after.json)全部保持；[命令绑定](execution-binding.json)确认实际测试版与交付副本相同。未选择的真实模型及浏览器用例不记为通过或 skipped。

当前代码 [Ruff](ruff-active.log) 与 [格式](format-active.log)检查通过，167 个文件格式保持；历史 `.scratch` 包按既有规则排除，不改写它们来消除历史 lint。新增测试最初的 import/行长问题保存在 [原检查](lint-before-format.log)，完成格式修正后再固定完整套件输入。

## 保全与交付边界

执行前保护基线包括 3,617 个历史文件，包含上轮真实 app-server 复验的 37 个封存成员及摘要文件。旧红测、旧代理和全部前代证据不覆盖。私人 worker/页面记录与附件的原件只作摘要核对，不复制到本包。

[现有资源回读](existing-protection-summary.json)确认原进程身份、私人记录、页面记录和附件/设置摘要保持。没有导航原页面，记录与进程保全不升级成新 DOM 验收。[历史回读](history-check-after.json)确认 3,617 个旧文件无新增、删除或字节变化。118 个既有源文件中仅 `cua_driver.py` 改动；127 个完整套件输入运行后全部保持。

[自有资源检查](resource-check.json)未见本轮测试目录标记的合成 MCP 子进程存活；完整 pytest 进程正常退出，客户端关闭回收非 daemon 读取线程。原 worker、浏览器、Cua、页面或附件的控制命令为 0。

[交付副本](delivery/src/career_evidence_graph/cua_driver.py)、[新增测试](delivery/tests/test_cua_mcp_lifecycle.py)和[文档](delivery/docs/cua-worker.md)经过[字节读回](delivery-readback.json)，与 checkout 的已测版本相同。本轮没有提交、推送、部署、应用安装或现有实例重启。

本次独立缺陷不增加冷启动自然阻断的分母；[调查 Cua 冷启动前置窗口阻断](../application-worker-stability/issues/07-cold-start-prewindow-investigation.md)保持 open。真实原生 Cua、浏览器、ATS、Guardian 决策和新模型调用均未执行。

复现与回归命令使用 checkout launcher：

```sh
PYTHONDONTWRITEBYTECODE=1 uv --cache-dir /private/tmp/ts-fixed-space-uv run --locked --offline python -B scripts/run_pytest.py -q -p no:cacheprovider tests/test_cua_mcp_lifecycle.py tests/test_cua_worker.py
```

本包封存后只读；后继检查写入新目录。
