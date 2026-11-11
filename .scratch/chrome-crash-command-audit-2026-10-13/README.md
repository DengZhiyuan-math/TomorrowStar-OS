# 09:10 Chrome 崩溃：触发命令审计

已定位到另一个无关私人项目会话中的直接 Chrome 启动尝试（会话名、工作目录与调用/turn 标识已从公开记录移除）。

## 原始命令

日志中的 shell 命令如下。本报告没有执行它。

```sh
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9223 --user-data-dir=/private/tmp/football-kaggle-chrome --no-first-run --no-default-browser-check about:blank
```

它直接运行 Chrome 可执行文件，使用独立临时 profile、调试端口 9223 和 `about:blank`。调用没有请求沙盒权限覆盖，采用默认沙盒。

## 证据链

| 证据 | 本地时间（UTC+02:00） | 结果 |
| --- | --- | --- |
| Rollout 第 102 行 | 09:10:45.465 | 保存上述工具调用 |
| Chrome 系统报告 | 启动 09:10:45.4817；捕获 09:10:46.0373 | PID 10104；parent codex 56125；Chrome 155.0.8059.40；SIGABRT |
| Crashpad 系统报告 | 启动 09:10:45.6152；捕获 09:10:45.9942 | PID 10113；相同 Chrome 版本和安装路径 |
| 命令错误输出 | 09:10:45.734069 | `child_port_handshake.10113...` 的 Mach bootstrap 注册被拒绝 |
| 命令错误输出 | 09:10:45.758867 | Crashpad `settings.dat` 访问被拒绝 |
| Rollout 第 105、106 行 | 09:10:45.911、09:10:45.930 | 命令退出码 134；工具输出保存相同错误 |

Chrome 报告本身没有 argv。命令归因依据是：同一秒、同一可执行文件、相同异常退出、以及命令输出与独立系统报告完全相同的 Crashpad PID 10113。工具事件时间与系统捕获时间不等同；系统报告负责进程时间。`CommandExecution.process_id=31382` 是工具会话标识，不作为 OS PID。

这个直接启动尝试来自该无关私人项目会话。当前 TomorrowStar 应用更新会话在该时段记录的是构建、Ruff 和离线测试。不能仅凭共同父进程 codex 56125 把崩溃归给 TomorrowStar worker。

触发命令已定位。底层失败范围是默认沙盒中的直接 Chrome 启动和应用注册：stderr 保存 Mach bootstrap / Crashpad 文件权限拒绝，Chrome 栈保存 `_RegisterApplication` 中的 `abort()`。具体是哪条 macOS 权限规则导致主进程 abort，现有日志没有证明。

## 检索和保留

只读检索了 2026-10-12、2026-10-13 的 143 个会话文件，时间窗口为 07:09–07:12 UTC。窗口内有 25 个工具调用和 29 个命令事件，发现上述一条直接调用系统 Chrome 的命令事件。补查当天桌面日志和只读运行日志数据库，未找到额外的 Chrome argv 或 PID 命令记录。

本轮没有启动浏览器、做复现、调用 Cua/UI、重启 worker、操作现有页面或附件、修改实现或旧证据包。仅写入本次独立审计目录。原始日志和崩溃报告保留原位。`evidence.json` 保存最小相关摘录、原始记录行号及 SHA-256；排除了无关工具输出和设备标识。
