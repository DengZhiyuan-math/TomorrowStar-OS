# 前置窗口核验阻断：失败采集与有界负载复现

日期：2026-10-13。真实 ATS 请求 **0**；新增真实模型调用 **0**。

## 结论

**历史前置阻断的根因仍未确认。**
本轮先补齐 checkout 的失败采集，再完成 24 次交错负载对照。
没有自然复现 `cua_visibility_unknown / 无窗口启动出现了意外窗口`。
并行负载的因果关系尚未建立，也没有被排除。

原失败发生在 `windowless_before` 守卫，早于 CDP 连接、context 和工作窗口创建。
原[错误日志](../cua-locator-timeout-diagnosis-2026-10-13/replay-before-v2.log)及
[当次诊断](../cua-locator-timeout-diagnosis-2026-10-13/before/load-2/diagnostic.json)保留。
原封存包缺少该次窗口条目，不能追溯补齐，也不能把更晚阶段的最小化动画认定为这次阻断的原因。

## 已补齐的采集

复用私有 runtime 的 `cua.log`，使用标准库 JSONL，不增加依赖或新存储。
`event=cua_startup` 每条记录保存 UTC 纳秒、单调时钟纳秒、相对启动时间和自有 PID。
阶段记录包含：

| 阶段 | 保存的证据 |
|---|---|
| 隐藏启动请求与返回 | 调用时间边界 |
| SingletonLock、隐藏确认、DevTools 端口 | 首次观察时间；隐藏重试的错误码；已核验的 PID、启动日期、hidden、active |
| loopback 端点、只读 Cua 就绪 | 端口绑定结果、私有发现 daemon PID |
| 首次 `list_windows` | 请求和返回时间；全部原始窗口字段；之前的隐藏确认回执 |
| 窗口守卫拒绝 | 首次拒绝记录；随后读取同一启动代次的当前 AppKit 状态及一次新窗口列表 |
| 快照读取失败 | 错误类型与错误码；继续保留原 `cua_visibility_unknown` 拒绝 |
| 清理 | 自有启动代次的清理开始和退出确认 |

拒绝后的读取只用于采集。没有再次隐藏、延迟放行、重新启动或放宽 `is_on_screen` 判定。
这两个只读快照仍受既有 AppKit / MCP 超时限制。它们不能代替首次窗口读取，也不能恢复历史缺失的窗口。
见[最小差异](change.diff)。

[四份失败采集样例](native-final/)为 `injected-prewindow-rejection-*.json`。
它们由永久回归在真实守卫调用点注入合成原生边界结果，明确标记 `synthetic_native_boundary_double`。
覆盖正常快照、快照读取失败、隐藏调用期间端口出现，以及身份登记晚于 SingletonLock。
原拒绝保持，未连接 CDP，未创建页面，快照先于清理。
这些样例没有自然窗口或历史根因的证明力。

## 假设及预测

| 排序 | 假设 | 可检验预测 | 本轮结论 |
|---:|---|---|---|
| 1 | AppKit 隐藏已确认，WindowServer 尚未收敛 | 同一窗口首次报告在屏幕上，随后消失；负载可能延长时间 | 未捕获同类窗口，未确认 |
| 2 | Chrome 在工作页创建前产生内部弹窗 | 有持续窗口及可辨认标题、尺寸、层级 | 首次 Cua 窗口列表均为空，未确认 |
| 3 | Cua 与 WindowServer 的读取时点或结果不同 | 同一 PID / window ID 在重叠时间段有不同屏幕标记 | 无拒绝样本；采样有间隙，未确认 |
| 4 | 进程代次或窗口 owner 不一致 | PID、启动日期或窗口 owner 出现不一致 | 本轮身份核验和清理通过；不能解释历史缺失条目 |

## 有界负载对照

最初矩阵为 24 次，固定交错顺序，每组 8 次。
一次只启动一个自有 Chrome/Cua；额外并行负载最多为两个离线 pytest 套件及其子进程。
所有组在开始 Chrome 启动前等待相同的 5 s，生产启动路径没有新增等待。
每个样本在 `BrowserType.connect_over_cdp` 调用点主动结束，已执行实际前置守卫，未连接 CDP 或创建 context / target。
首批总时间 **282.66 s**，小于预设 480 s 上限。

| 新增离线套件 | 样本 | 前置拒绝 | 捕获屏幕窗口的样本 | 启动至窗口核验中位数 | 启动区间负载 CPU 峰值 |
|---:|---:|---:|---:|---:|---:|
| 0 | 8 | 0 | 0 | 4.006 s | 0% 新增负载 |
| 1 | 8 | 0 | 0 | 3.831 s | 135.3% |
| 2 | 8 | 0 | 0 | 4.594 s | 376.4% |

CPU 数值为所属离线进程组的 `ps pcpu` 之和，包含子进程。100% 约为一个逻辑核。
它是间隔采样，不是 CPU 时间加权结果。`load-samples.json` 另保存系统 load average、逻辑核数量和负载存活状态。
“0 新增负载”不表示整台机器空闲。不同样本进入的离线测试阶段不同，不能由这三个中位数推断独立因果效应。
30 次采样均未出现隐藏确认重试；边界回归另验证了身份未登记时的记录。

首批发现一个采集缺口：DevTools 端口在隐藏确认调用期间出现时，首次观察里程碑会漏记。
首批 24 个样本均缺这条事件；后续端点核验记录完整。
新增迟到端口回归先失败，再把端口观察放在隐藏确认之后；现有启动条件保持。
首批结果保留，另以最终代码追加每组 2 次，**6/6** 通过，耗时 **80.76 s**。
最终 6 个样本全部记录端口里程碑。
见[30 次索引](trial-index.json)、[分组统计](trial-summary.json)、[首批日志](parallel-probe.log)与[最终复验日志](final-probe.log)。

原生 Swift 采样器从 Chrome 启动前运行，记录新 Chrome/Cua 的 AppKit 状态和 WindowServer 元数据。
已有应用、窗口标题和屏幕像素不进入采样器记录。Chrome 的原始 Cua 窗口字段仍保存在其私有启动日志中。
本轮捕获了注册初期 `hidden=false`、随后 `hidden=true` 的状态变化，未同时捕获屏幕窗口。
从首次注册观察到首次隐藏观察的采样间隔为约 **0.176–1.992 s**；这是采样时间界限，不是精确转换时间。
实际平均采样率约 **32–52 Hz**，最大采样间隙约 **391 ms**。
早于 AppKit 注册的窗口和采样间隙内的短暂状态可能漏采。
因此，未捕获屏幕窗口不是逐帧零闪现证明，也不能证明 Cua 与 WindowServer 在历史失败时一致。

专项主动结束使普通 `cua-runtime.json` 的 `closed` 为 false；这些是前置专项，不是完整启动样本。
`cleanup_complete`、采样器停止及独立 PID 核对确认退出。离线负载按自有进程组停止，部分套件日志计为中断，不计为完整回归通过。

## 针对性回归与保全

- [最初失败采集 RED](capture-red-v2.log)：2 failed，缺少启动记录；0.43 s。
- [首次采集 GREEN](capture-green.log)：4 passed。
- [迟到端口 RED](port-milestone-red.log)：2 failed、2 passed；0.48 s。
- [最终边界 GREEN](capture-final-green.log)：6 passed；0.44 s。
- [最终针对性回归](targeted-final.log)：**34 passed、0 skipped**；121.12 s。包含 5 项实际原生 MCP 合成场景。
- [Ruff](lint-final.log)与[格式检查](format-final.log)通过。

原生场景仍验证同页同 File 人工交接、未知 POST 拦截、歧义停止、未结动作保留、精确绑定和私有 runtime 退出。
它们是合成验证，不接受真实 ATS 覆盖或真实投递效率。

[进程核对](process-check.json)记录 66 个自有原生 PID 和 30 个新增离线负载进程组，均无存活匹配项。
完整原生回归的两个 runtime 均 `closed=true`，私有 socket 均消失。
未对已有用户进程或被复用的 PID 执行额外清理。

首批 [129 个输入](fixed-execution-inputs-before.json)与[运行后](fixed-execution-inputs-after.json)相同。
最终复验与回归使用 [130 个输入](final-execution-inputs-before.json)，[运行后](final-execution-inputs-after.json)相同。
`execution-inputs/` 和 `final-inputs/` 保存两个采集版本，`before/` 保存本轮前的源码。
所有 `debug_*` 工具和 WindowServer 采样器只用于本目录诊断，不进入产品运行时。

[历史前核验](historical-check-before.json)与[历史后核验](historical-check-after.json)确认：五份旧封存包的 **1312 文件和清单原字节保持**。
原 16 场景基线仍为 15 passed、1 failed；原定位失败与本次关注的原前置拒绝均没有改算通过。
本目录以新的 `artifact-hashes.json` 封存。

本轮采集变更位于 checkout。
[已安装源码读回](installed-source-readback.json)确认本机应用仍保持上轮两处修复，没有新增本轮诊断代码或重启批次。
覆盖票继续 open。

## 重复命令

快速失败采集回归：

```sh
uv --cache-dir /private/tmp/ts-measurement-uv run --locked \
  python scripts/run_pytest.py -q tests/test_cua_worker.py -k prewindow_rejection
```

前置专项需复制本目录诊断工具到新的后继目录，并重新编译采样器；不要向本封存目录重跑或覆盖。
保持相同离线 marker、最多两个负载套件、单个自有原生启动及 CDP 前主动结束的约束。
