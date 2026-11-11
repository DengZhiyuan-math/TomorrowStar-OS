# Cua 冷启动前置阻断：后继根因调查

2026-10-13。所属票：[调查 Cua 冷启动前置窗口阻断](../application-worker-stability/issues/07-cold-start-prewindow-investigation.md)。领取人 root；票保持 open。

## 结论

**历史单次冷启动阻断的根因仍未确认。** 本轮执行了 18 次无窗口注入的自然启动，均未复现原错误。
另执行 10 次真实原生窗口对照，确认守卫和首次拒绝采集链有效，并定位两次对照断言失败的原因：取消隐藏的窗口仍在其他 Space。
不能将受控窗口的触发机制认定为历史冷启动根因。

没有修改生产启动参数、隐藏控制、窗口守卫、超时或 worker 源码。没有应用更新、共享服务重启或真实 ATS 操作。
真实 ATS 请求、模型调用、自动最终 Submit 均为 0。

## 输入与范围

[原始失败](../cua-locator-timeout-diagnosis-2026-10-13/replay-before-v2.log)发生于首次 `windowless_before` 守卫，早于 CDP、context 和工作页。
原日志没有保存当次窗口条目；[原诊断](../cua-locator-timeout-diagnosis-2026-10-13/before/load-2/diagnostic.json)没有原生窗口句柄。
历史缺失条目不能追溯补造。更晚的首窗口最小化动画修复不能直接解释这个前置拒绝。

当前输入先固定：[121 个执行输入](execution-inputs-before.json)、[原生版本与摘要](native-inputs.json)、历史代码副本 `inputs/historical_cua_driver.py`。
实际版本为 Chrome 155.0.8059.40、CuaDriver 0.21.0、macOS 27.2。
历史启动代码与当前代码使用同一组 LaunchServices 参数和同一隐藏控制。主要差异为新增阶段记录和拒绝后的只读快照。
历史 replay 使用历史模块副本；其他依赖、原生应用和系统环境为本轮版本。这不是完整历史环境重建。

一次只启动一个新 Chrome。使用唯一临时 profile、SingletonLock PID、AppKit 启动日期、loopback 端点和私有 Cua socket。
原生 Cua 发现权限只绑定该 PID。额外负载最多两个自有离线 pytest 进程组。
诊断采样器只保存该 profile 的 Chrome PID 与窗口元数据，不保存现有窗口标题或屏幕像素。
所有调试工具都属于本目录，不进入产品运行时。

## 实际执行结果

| cohort | 范围 | 样本 | pytest 结果 | 原守卫拒绝 | 耗时 |
| --- | --- | ---: | --- | ---: | ---: |
| [当前启动](cohort-01-native.log) | 无额外负载 / 两个离线套件，各 3 次 | 6 | 6 passed | 0 | 66.34 s |
| [历史启动副本](cohort-02.log) | 相同交错负载，各 3 次 | 6 | 6 passed | 0 | 64.72 s |
| [原生窗口对照](cohort-03.log) | 后台创建 / 创建时最小化 / 取消隐藏，各 2 次 | 6 | 4 passed、2 failed | 0 | 62.50 s |
| [激活对照](cohort-04.log) | 取消隐藏 / 再激活自有 Target，各 2 次 | 4 | 4 passed | 4，预期拒绝 | 57.11 s |
| [完整响应采样](cohort-05.log) | 自然启动，相同交错负载，各 3 次 | 6 | 6 passed | 0 | 62.96 s |

[28 次索引](trial-index.json)保存结果指针、首次窗口字段、错误、独立采样与盲点。
18 次自然启动都在正式 `connect_over_cdp` 调用点主动结束。没有连接 CDP、创建 context 或工作页。
10 次窗口对照显式连接本轮 Chrome 的 CDP 并创建 `about:blank`。它们是原生注入，不属于自然启动样本。
正式启动路径仍在首次守卫之后停止，未继续创建 worker context 或执行 ATS 动作。

首个命令遗漏显式 `-m worker_browser`，被默认 marker 排除：6 deselected，退出码 5。
[日志](cohort-01.log)和 [JUnit](cohort-01-junit.xml)保留；不计为启动尝试或通过。

离线负载在每次启动前使用相同 5 s 准备时间；实际生产启动路径没有新等待。
负载组 CPU、系统 load average 与所属进程记录保存在各 trial 的 `load-samples.json`。
这些负载套件按本轮所属进程组停止，其日志不计为完整离线回归通过。

## 新定位的复现边界

cohort-03 的两次失败是诊断断言失败。原守卫没有返回错误。
当次 `about:blank` 窗口在 Space 1，Cua 的 `current_space_id=73`、`on_current_space=false`、`is_on_screen=false`。
独立 WindowServer 也没有报告该窗口在屏幕上。
`AppKit hidden=false` 不足以推出窗口在当前屏幕，因此原“取消隐藏就必然拒绝”的阳性对照不成立。
两次原始失败、源码和结果均保留，未改算通过。

下一 cohort 加入只对本轮 Target 的 `Target.activateTarget` 操作。
这组 4 次读取均观察到 Space 1 上的原生窗口，原守卫均返回原 `cua_visibility_unknown / 无窗口启动出现了意外窗口。`。
取消隐藏组也观察到同样的拒绝。Space 在两组之间没有被固定，不能由此认定激活操作独立造成了 Space 变化。
可确认的是：实际屏幕标记与拒绝一致；取消隐藏的 AppKit 状态与屏幕标记不是同一个概念。
[检验前候选解释](controlled-failure-hypotheses.md)与[真实拒绝读回](native-guard-readback.json)保存排序、预测和结果。

真实拒绝读回逐例确认：

- 首次 Cua 窗口 PID 与本轮 profile 的 owner 一致。
- 同一 window ID 在首次 Cua 调用区间与独立 WindowServer `is_on_screen` 观察一致。
- AppKit 与第二次窗口快照先于清理完成；保持首次拒绝，没有再次隐藏、启动重试或延迟放行。
- 日志中的首次 `application` 字段是之前的隐藏确认回执；拒绝后的 AppKit 快照才是后来的读取。两者时间含义不能混用。
- 正式启动的 CDP 连接没有发生；Chrome 清理完成，采样器退出。

cohort-05 保存完整 Cua 窗口响应，包括窗口列表为空时的顶层 `current_space_id`。
6 个样本均返回 `current_space_id=73, windows=[]`。它们没有提供 Space 1 上的自然冷启动证据。
该采集只位于诊断入口 `debug_space_observed_probe.py`，未改变产品字段或守卫。

## 原生字段与证明边界

Cua 0.21.0 的[窗口枚举源码](https://github.com/trycua/cua/blob/70db98d1bcd92890d778f4978e0eb107a4b66c1b/libs/cua-driver/rust/crates/platform-macos/src/windows.rs)
从 WindowServer 的 `kCGWindowIsOnscreen` 读取 `is_on_screen`。
[工具源码](https://github.com/trycua/cua/blob/70db98d1bcd92890d778f4978e0eb107a4b66c1b/libs/cua-driver/rust/crates/platform-macos/src/tools/list_windows.rs)
按 PID 过滤 layer-0 窗口，并返回 Space 元数据。
本轮只读下载固定 tag 源码，附 [MIT 许可证](upstream-LICENSE.md)与[来源记录](upstream-evidence.json)。没有编译、适配或升级 Cua。
已安装二进制是否由该 tag commit 构建，未独立证明；实际行为结论来自本轮原生调用。

屏幕标记不等于画面逐帧证明。受控窗口的 WindowServer 轨迹包含 alpha 0 和 alpha 1 的状态。
没有截图或逐帧录像，不能仅凭 `is_on_screen=true` 断言每个时刻的可见像素。
实际平均采样率与每个最大采样间隙见索引；本轮最大间隙约 303 ms。
短暂状态仍可能漏采。零自然拒绝不能证明问题已消失，也不能建立负载的独立因果关系。

## 核验、保全与后续

[既有失败采集边界回归](boundary-regressions.log)：4 passed、21 deselected，0.36 s。
它们是合成原生边界替身；与上面的 4 次真实原生拒绝区分。
诊断入口 Ruff 初次发现历史 replay 的 3 项导入问题，见 [初次输出](probe-lint-final.log)。
执行版先按原字节归档到 `inputs/debug_historical_probe-executed.py`，再整理未来入口导入位置。
[整理记录](diagnostic-import-tidy.json)、[最终 lint](probe-lint-clean.log)及[各 cohort 输入读回](cohort-input-readback.json)保留。
整理不产生新原生验收结论。`git diff --check` 通过。

[运行后输入](execution-inputs-after.json)与原 121 项相同。
[历史后核验](history-check-after.json)确认 2,410 个文件无新增、删除或字节变化。
[现有资源核对](existing-protection-summary.json)确认私人 worker 记录、PDF、设置摘要相同，原进程身份全部保留。
私人明细仅保存在 `/private/tmp`，未复制到本目录。
[自有资源核对](resource-check.json)确认 28 个新 Chrome、28 个采样器和 18 个离线负载进程组均无存活匹配项。
私有 profile/socket 标记在进程参数中也无剩余匹配项。
没有向现有 worker、浏览器、页面或附件发送命令。

普通 `cua-runtime.json` 的 `closed=false` 是前置专项主动结束的记录，不是完整启动通过。
清理由启动 context manager、原生退出记录、sampler wait 与独立进程核对确认。

票保持 open。仍缺少一次自然拒绝的首窗口、Space、owner、AppKit 启动代次与时间重叠证据。
获得该样本后，先缩小到仍触发同一守卫的最小场景，再检验机制与独立对照。
本轮不提交猜测性运行时修复。

## 后继复跑

必须复制诊断工具、`window-sampler` 和 `inputs/` 到新的后继目录；不得向本封存目录重跑。
每个 trial 用 `mkdir(exist_ok=False)` 防止覆盖。
在仓库根目录使用 checkout launcher，例如把 `NEW_EVIDENCE_DIR` 设置为新的目录后执行：

```sh
PYTHONDONTWRITEBYTECODE=1 TS_CUA_NATIVE_TEST=0 uv --cache-dir /private/tmp/ts-cold-rootcause-uv run --locked --offline python -B scripts/run_pytest.py -q -p no:cacheprovider -m worker_browser "$NEW_EVIDENCE_DIR/debug_space_observed_probe.py"
```

该命令执行自然前置守卫和完整只读响应采集，仍在 CDP 前主动结束。
保持单个新 Chrome、最多两个自有离线负载进程组、独立清理、私人保护快照和新输入封存。
