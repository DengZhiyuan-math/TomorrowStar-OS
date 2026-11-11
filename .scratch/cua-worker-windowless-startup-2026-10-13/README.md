# Cua worker：无窗口初始化与原页人工复核

实施与验收：2026-10-13，Europe/Zurich。范围：checkout worker、CuaDriver 0.21.0、系统 Chrome、隔离合成表单。

## 交付行为

| 行为 | 当前实现 |
| --- | --- |
| 首次初始化 | Worker 创建全新临时 profile。LaunchServices 使用 `open -n -g -j`，Chrome 使用 `--no-startup-window`。确认原生应用隐藏、无页面目标后才创建工作窗口。没有先启动可见空白页再关闭的步骤。 |
| 精确绑定 | 先用只读、仅本次 PID 的私有 Cua 服务发现隐藏窗口。再用 bounded manifest 批准准确 PID / window ID 和站点来源。`browser_prepare` 只 attach，不启动或修改浏览器。 |
| 常驻后台 | 同一 Chrome、context 和原生窗口复用后台标签。保留一个隐藏 anchor，维持窗口身份。等待、暂停和后续批次不重建浏览器。 |
| 会话刷新 | 新站点或会话接近 24 小时期限时，仅刷新私有 Cua 会话，并重绑原窗口。未知 transport 不重建重试。 |
| 人工复核 | 只在用户 `review` 请求中显示原窗口。原 Page、真实 Chrome target、DOM 与附件 File 对象均保留。已有人工窗口不会因后续后台页再次隐藏。 |
| 发送与状态 | 复用同一 WorkerStore、intent、许可、答案、PDF 核验和 HTTP / WebSocket 守卫。Cua 回执后处理排队的守卫事件，再独立回读。最终 Submit 仍由用户操作。 |
| 退出 | 停止私有 Cua 服务，再按 PID 和原生 launch date 关闭本次 Chrome。没有关闭日常 Chrome 或共享 daemon。 |

启用已有 `--worker-cua` 选项后默认生效，无新增依赖或 Hermes runtime。
详见[操作说明](../../docs/cua-worker.md)和[交付指纹](delivery-source-hashes.json)。

## 验证结果

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 完整默认离线回归 | **905 passed，98 deselected** | [日志](offline-full.log)、[JUnit](offline-full.xml) |
| 完整 headless browser 回归 | **92 passed，5 skipped，906 deselected** | [日志](browser-full.log)、[JUnit](browser-full.xml)。5 项原生场景按 opt-in 规则跳过。 |
| Cua 模块，原生 opt-in | **19 passed，含 5 项本机原生场景** | [日志](native-final.log)、[JUnit](native-final.xml) |
| 启动源码身份与清理补充 | **1 passed，全程隐藏** | [日志](native-process-final.log)、[JUnit](native-process-final.xml)、[实际启动源码](native-process-final/native-process.json) |
| 最终离线边界 | **8 passed，11 deselected** | [日志](offline-unit-final.log)、[JUnit](offline-unit-final.xml)。协议替身使用合成二进制与临时目录，不读取本机 Cua 二进制。 |
| 维护目录 Ruff lint / format | **passed，114 files formatted** | [lint](ruff.log)、[format](format.log) |
| 私有进程、socket、历史封存 | **passed** | [进程核验](private-process-check.json)、[旧包核验](prior-seal-check.json)；旧四包共 184 个文件未变。 |

原生场景独立回读：

| 场景 | 结果 |
| --- | --- |
| 初始化与资源范围 | `startup_target_count=0`；应用隐藏、启动窗口均不在屏幕上。错误 PID 和错误 window ID 均被 Cua 拒绝。见[启动记录](native-final/startup.json)。 |
| 隐藏操作与复核 | 8 次工作采样均为应用隐藏、非前台、窗口最小化；WindowServer 窗口不在屏幕上。复核显示后，同一 Page、Chrome target 和 File 对象保留。见[记录](native-final/native-review.json)。 |
| 未知 POST | 拦截 **1** 次，放行 **0** 次；保留 fill intent，状态为 `needs_recheck/unverified_send_path`。见[记录](native-final/native-blocked_send.json)。 |
| 选项歧义 | 保留 intent，状态为 `needs_recheck/cua_control_ambiguous`，发送放行 **0** 次。见[记录](native-final/native-ambiguous_option.json)。 |
| 下一批新来源 | 新站点触发私有会话刷新，在同一浏览器与窗口完成确认选项选择，达到 `ready_for_review`，没有显示窗口。见[岗位记录](native-final/native-later_batch.json)与[共享运行记录](native-final/resident-runtime.json)。 |
| 独立 worker | 合成附件上传 **1** 次，自动最终提交 **0** 次；SIGTERM 后 Chrome、两次私有 daemon 与 socket 均清理。Cua 模块出现在实际 worker 启动源码清单内，并与当前源码一致。见[补充记录](native-process-final/native-process.json)。 |

最终模块回归中的四个表单场景共用一个浏览器、context 和窗口。只有复核场景显示一次。
生命周期检查与其补充检查全程隐藏。完整 browser 回归使用 headless，没有执行复核显示。
本轮真实 ATS 调用、模型调用、自动最终 Submit 和最终请求放行均为 **0**。

## 保留的失败与修正

- [启动 RED](startup-red.log)：原实现调用驱动启动浏览器，不能消除初始化空白窗口。
- [范围刷新 RED](scope-red.log)：固定启动来源不能覆盖常驻浏览器的下一批新站点。
- [启动探针](native-probe/cua.log)、[最初无窗口探针](launch-probe.json)：bounded 服务需显式期限；原生窗口含多个辅助窗口，长标题可能被截断。最终按受控短标题绑定。最初探针的 WindowServer JXA 转换失败，未用该失败结果声称窗口验收通过。
- [初始原生回归](native-initial.log)：13 passed、2 failed、4 errors。包含协议替身缺少 `pump` 参数，以及 Chrome 锁先于 LaunchServices 注册的竞态。后者发生在创建工作窗口前；[两个残留私有实例](registration-failure-cleanup.json)按准确 profile 与原生身份清理。最终等待应用注册后才创建页面。
- [显示回读回归](native-readback-failure.log)：17 passed、2 failed。AppKit 桥接返回 false，但[无窗口探针](native-windowless-probe/switch.json)回读显示状态实际已改变。最终依据原生状态回读判断成功。另一次失败确认 Cua 回执可能先于守卫事件到达；最终在回执后泵送事件再回读，未知发送保持待核验。
- [受限沙箱 browser 回归](browser-sandbox-failure.log)：本机 MachPortRendezvous `bootstrap_check_in` 被沙箱拒绝，69 failed、5 skipped、22 errors 后中止。最终用本机 browser 测试所需权限运行 headless 套件，结果见上表。

显示回读失败轮执行过一次复核显示请求；最终轮另执行一次。不能把最终一轮只显示一次套用到全部诊断轮。
其余启动探针没有执行工作页复核；显示/隐藏方法诊断使用无页面、无窗口实例。
最初无窗口方法探针退出时曾遇到临时目录清理竞态；后续先保存诊断并等待准确进程退出。最终核验没有任务探针残留。

## 依据与界限

上游：`trycua/cua`，tag `cua-driver-rs-v0.21.0`，revision **70db98d1bcd92890d778f4978e0eb107a4b66c1b**，MIT。
保存了[许可证](v021-LICENSE.md)、[启动实现](v021-cua-driver-core_src_browser_prepare.rs)和[资源授权实现](v021-session_manifest.rs)。
原始来源：[固定版启动源码](https://github.com/trycua/cua/blob/70db98d1bcd92890d778f4978e0eb107a4b66c1b/libs/cua-driver/rust/crates/cua-driver-core/src/browser/prepare.rs)。该路径固定创建 `about:blank`；本地改为 worker 原生隐藏启动，再精确 attach。
没有复制上游 runtime 源码到生产模块，也没有升级或重新打包 CuaDriver。二进制 SHA-256 见原生运行记录。

这是原生状态与 WindowServer 的采样验收，没有逐帧录屏。Dock 中仍可能显示独立应用图标。
同一仍存活的运行保留 DOM 和 File；停止 worker 后，磁盘检查点不能重建这些对象。
后台 Cua 点击仍为显式 `dom_event`；真实站点可能忽略合成事件，没有静默降级。
未重启已有运行实例，未替换 TomorrowStar.app 安装包；本改动在下一次启动 checkout Cua worker 时生效。
真实覆盖票仍为 open，没有执行真实岗位试点或效率比较。

[验证汇总](verification-summary.json)记录 123 个维护输入。
[模块验收输入](verification-inputs-before-source-export.json)与[最终输入](verification-inputs.json)只差测试中的源码身份导出、断言与离线协议替身配置；生产代码未变。
[源码快照](inputs/src/career_evidence_graph/cua_driver.py)与相关测试按字节保存。
本目录以 `artifact-hashes.json` 封存，历史失败保持失败状态。
