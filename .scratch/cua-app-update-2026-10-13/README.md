# 本机应用更新：默认后台 Cua

日期：2026-10-13，Europe/Zurich。用户授权更新当前应用，保留现有实例、页面、附件与人工最终 Submit。

## 安装结果

- 当前应用：[TomorrowStar.app](/Users/zhdeng/Applications/TomorrowStar.app)。
- 原包完整备份：[备份](/Users/zhdeng/Applications/.TomorrowStar-backups/2026-10-13-f1992244cfe5/TomorrowStar.app)。
- 新构建位于 `build/macos/cua-background-final-2026-10-13/TomorrowStar.app`，197 MiB。未发布或推送远程。
- [安装回执](installation.json)记录 manifest 摘要、52 个引擎文件、依赖版本和严格签名结果。
- 安装没有启动应用、worker 或浏览器，没有停止任何进程。

## 默认行为

`macos/server.py` 为新 worker 设置 `live=true`、`generic=true`、`cua=true`、`click_route=dom_event`。
打开应用只创建服务，批次 prepare / resume 才启动 worker。
默认目录是 `~/Library/Application Support/TomorrowStar/application-worker`；现有目录为 live、paused。本轮未重置历史 worker PID 或旧检查点。

应用内置原有 worker 启动器、Playwright 1.63.0、pyee 13.0.1、greenlet 3.5.6。没有新增项目依赖。
依赖沿用已安装 wheel 的运行文件；外部 console script 和开发头文件不进入包，站内路径越界校验保留。
没有复制 Chromium 下载缓存、CuaDriver、系统 Chrome 或个人记录进应用。

Cua 执行核心与[无窗口启动验收](../cua-worker-windowless-startup-2026-10-13/README.md)保持原字节，见[核验](core-identity-check.json)。
浏览器由 worker 通过 LaunchServices 隐藏启动，无启动页面，再精确 attach。人工复核显示原页面并保留附件对象。
原 WorkerStore、确认答案、PDF 核验、发送守卫与人工最终 Submit 保持。
缺少外部运行时或权限时停止，没有可见浏览器 fallback。

## 验证

| 检查 | 结果 | 记录 |
| --- | --- | --- |
| 相关离线回归 | 97 passed，11 deselected | [日志](focused.log)、[JUnit](focused.xml) |
| 完整默认离线回归 | 905 passed，98 deselected | [日志](offline-final.log)、[JUnit](offline-final.xml) |
| 应用后端默认配置 | 2 passed | [日志](backend-final.log)、[JUnit](backend-final.xml)；HTTP 回读确认后台 Cua 默认配置、worker 未自动启动、父管道 EOF 退出。 |
| 最终包搬移验收 | passed | [报告](bundle-final-acceptance.json)、[日志](bundle-final-acceptance.log)；从 `/` 启动内置 Python，Playwright Node 初始化与 worker `--help` 通过，未启动浏览器。数据 API、证据读取、Host/CSRF、只准备任务与退出通过。 |
| 签名与安装回读 | passed | 安装前、暂存包、安装后均 `codesign --verify --deep --strict` 通过；安装后所有引擎摘要匹配。 |
| Ruff lint / format | passed，117 files formatted | [lint](ruff.log)、[format](format-final.log) |
| 现有数据 | unchanged | [之前](existing-state-before.json)、[之后](existing-state-after.json)；5 个状态、答案及附件文件的聚合摘要一致，不导出内容或文件名。 |
| 现有进程 | retained | [安装后记录](retained-processes-after.txt)；Chrome for Testing PID 24328 与共享 Cua PID 54490 的 PID、启动时间保持；未停止或重启它们。 |

最终完整离线结果见 `offline-final.log` 与 `offline-final.xml`，汇总在 `verification-summary.json`。
本轮没有重新执行当前 Chrome 的 Cua 浏览器行为测试，也没有人工复核显示实验、真实 ATS 调用、模型调用或最终 Submit。
此前执行核心的原生结果只适用于其已记录的运行时，不能作为当前 Chrome 155.0.8059.40 已完成行为验收的声明。

## 崩溃截图核对

[限量摘要](crash-summary.json)按用户提供的两个 PID 核对系统 `.ips` 报告，未导出设备标识或完整私人诊断文件。

- **PID 35146，00:54:46，Chrome for Testing 153.0.8010.12**：匹配此前封存的 `browser-sandbox-failure.log`。SIGABRT 栈停在 macOS `_RegisterApplication / TransformProcessType`。前一轮在受限沙箱启动浏览器造成了这些失败；该轮中止后，已改为本机允许环境完成 headless 回归。
- **PID 10104，09:10:46，Chrome 155.0.8059.40**：SIGABRT 栈停在 macOS `_RegisterApplication / NSApplication`，父进程为 Codex。现有证据不足以确认具体触发命令；本次与前次应用包日志未找到该 PID。没有把父进程信息当成 worker 发起的证明，也没有声称该崩溃已修复。

本轮根据截图转为后端、依赖初始化、入口和签名验收，不重新打开浏览器来重现错误，也不修改系统崩溃报告设置。
现有崩溃报告窗口未操作。

## 保留失败

- [后端 RED](backend-red.log)：旧桌面入口没有 worker 目录参数与默认 Cua 配置。
- [wheel 安装布局失败](build-record-layout-failure.log)：Playwright console script 和 greenlet 开发头文件位于 site-packages 外；最终只复制运行文件。
- [旧验收夹具失败](bundle-fixture-routing-failure.log)：旧合成记录未明确批量路由，被当前准备守卫拒绝。最终补齐夹具的明确 batch 路由，未修改产品准入规则。

第一次构建保留在 `build/macos/cua-background-2026-10-13/`；最终构建固定了更新后的验收器。
本目录以 `artifact-hashes.json` 封存。历史 Cua 验收包不改写。
