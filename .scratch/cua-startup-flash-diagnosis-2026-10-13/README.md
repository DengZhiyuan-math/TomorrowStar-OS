# Cua 启动闪现：诊断、最小修复与应用更新

日期：2026-10-13。所有行为实验使用临时自有 Chrome/Cua 会话、`about:blank` 或已有离线合成夹具。
真实 ATS 请求 **0**；新增真实模型调用 **0**。

## 结果

**当前启动闪现已自然复现，并找到可控制的触发边界。**
旧代码以 `Target.createTarget(windowState="minimized")` 创建首个原生窗口。
在 Chrome 155.0.8059.40 上，该操作可以在应用报告 `hidden=true` 时仍产生屏幕窗口动画。
负载组还捕获到 `alpha=1`、约 1095×828 的 Chrome 窗口。
因此，`hidden=true` 不是窗口创建期间不展示的充分证据。

最小修复只移除创建时的 `windowState` 参数。
新顺序是在已经隐藏的应用中创建后台无焦点窗口，再通过既有接口最小化并核验。
后续最小化、原生身份、精确绑定、原页面与附件、未知结果停止、发送守卫及人工 Submit 均保持。
没有新增延迟、重试、依赖或可见 fallback。见[最小差异](change.diff)。

修复后的 checkout 与应用包源码各 **4/4** 次启动采样通过。
最终针对性回归 **30 passed、0 skipped**，其中 5 项执行实际原生 MCP 合成场景。
修复已安装到 [TomorrowStar.app](/Users/zhdeng/Applications/TomorrowStar.app)。
原包[完整备份](/Users/zhdeng/Applications/.TomorrowStar-backups/2026-10-13-114437-d6094b54/TomorrowStar.app)；现有实例没有重启。

## 历史前置阻断的边界

原[失败记录](../cua-locator-timeout-diagnosis-2026-10-13/replay-before-v2.log)在
`windowless_before` 检查拒绝 `is_on_screen=true`，返回 `cua_visibility_unknown`。
**它发生在工作 context 和首个窗口创建前，不能直接由后面的创建时 minimized 参数解释。**
旧封存包没有保存该次原始窗口条目，也没有该次 WindowServer 轨迹。
本轮缩小到原前置阶段：启动隐藏 Chrome、建立只读私有 Cua、检查窗口，然后在 CDP 连接前主动结束。
12 次并行负载采样均通过该前置检查，未发现屏幕窗口。

因此，历史单次阻断的具体窗口与底层原因仍未确认。
没有把本轮闪现机制误当成其已证实根因，也没有放宽窗口守卫或把旧失败改算通过。
详见[12 次前置专项日志](precreation.log)和 `precreation/` 中的原始窗口记录。
专项主动结束会使普通 runtime 记录的 `closed` 字段为 false；它不是完整启动样本。
Chrome 和私有 Cua 仍通过 context manager 清理，[进程身份核对](diagnostic-process-check.json)确认本次自有进程均退出。
一个旧 PID 已被 Siri XPC 复用，没有对该不同进程执行清理操作。

## 假设与对照

| 假设 | 可检验预测 | 结果 |
|---|---|---|
| 重复最小化是唯一原因 | 跳过已最小化窗口的重复请求应消除闪现 | 否。2 次负载样本仍有 1 次屏幕动画，并捕获不透明窗口。 |
| 首窗口创建时的 minimized 参数触发动画 | 去掉该参数，保留创建后的最小化，应消除同类采样信号 | 支持。候选 6 次、最终 checkout 4 次、应用包源码 4 次均未检测到屏幕窗口。 |
| 并行负载独立导致窗口显示 | 保持请求顺序不变时，负载组应更易暴露 | 旧请求在负载组出现动画，未增加负载组没有出现。样本有限，未测 CPU 利用率，不能给出独立因果效应。负载不是修复对象。 |
| Cua 自身界面闪现 | 屏幕窗口的 owner 应为本次 Cua PID | 本轮屏幕窗口归属 Chrome PID；没有捕获 Cua 屏幕窗口。 |

| 组别 | 样本 | 屏幕窗口采样 | 不透明窗口采样 |
|---|---:|---|---|
| 原请求，无新增负载 | 2 | 0/2 | 0/2 |
| 原请求，并行离线负载 | 2 | 2/2 | 0/2；记录的窗口 alpha 为 0，不能仅凭此断言可见画面 |
| 原请求，仅跳过重复最小化，并行负载 | 2 | 1/2 | 1/2，含约 1095×828 窗口 |
| 原请求，创建后的最小化前等待 200 ms，无新增负载 | 2 | 0/2 | 0/2 |
| 去掉初始 minimized，保留后续最小化 | 6 | 0/6 | 0/6 |
| 最终 checkout 实际代码，无诊断行为替换 | 4 | 0/4 | 0/4 |
| 最终应用包实际引擎源码 | 4 | 0/4 | 0/4 |
| 前置守卫专项，在 context / 页面创建前结束 | 12 | 0/12 | 0/12 |

[逐次索引](trial-index.json)保留 34 个原生专项样本。
原请求和候选组只有诊断用 monkeypatch；最终 checkout / 包源码组没有改变生产请求，只增加计时观察。
离线负载在每个样本结束时按所属进程组停止，其部分日志不计为完整回归通过。

原生 Swift 采样器只记录新 Chrome/Cua 的窗口元数据，不记录现有窗口或屏幕像素。
请求间隔为 10 ms，实际平均采样率为约 **35–45 Hz**。
原两次负载样本记录了约 0.6 s 的窗口变换。
采样不是逐帧录屏，不能据此承诺所有环境绝对零帧闪现。
`debug_*.py` 与 `debug_window_sampler.swift` 明确属于诊断工具，不是产品运行时。

## 回归与包核验

- [永久边界回归 RED](regression-red.log)：旧创建请求触发原生动画边界故障；0.21 s 内失败。
- [回归 GREEN](regression-green.log)：同一故障边界及既有隐藏启动配置通过。
- [最终回归](targeted-final.log)：30 passed；确认选项、许可失效、控件替换、未知 POST、歧义停止、同页同 File 交接及私有进程退出均通过。
- [高频最终采样](probe-after.log)与[包内源码采样](package-native.log)：各 4 passed。
- Ruff 检查与格式检查通过；[核验索引](verification.json)保留失败及通过结果。

快速回归使用 checkout launcher：

```sh
uv --cache-dir /private/tmp/ts-measurement-uv run --locked \
  python scripts/run_pytest.py -q tests/test_cua_worker.py \
  -k 'first_hidden_page or startup_attaches_only'
```

CDP 的 `windowState` 是窗口创建参数；协议字段本身不承诺隐藏状态下无动画。
参见[官方 Target 协议](https://chromedevtools.github.io/devtools-protocol/tot/Target/#method-createTarget)
与[官方 Browser 窗口接口](https://chromedevtools.github.io/devtools-protocol/tot/Browser/#method-setWindowBounds)。
上述动画机制和修复效果来自本机对照，不是协议文档的保证。

## 应用安装与保存

应用包从原已安装包复制，只应用已授权的首窗口修复与上轮同节点检查修复。
没有带入仓库其他未提交改动，也没有把新计量模块或新依赖加入该包。
[暂存清单](staged-package.json)确认两处修复方法的 AST 与已测试 checkout 相同。
[整包差异](whole-package-diff.json)核对 1420 文件：只有两份引擎代码、清单和签名变更。
原生可执行文件去除签名后保持同一摘要。

[搬移与内置运行时验收](bundle-acceptance-v2.json)通过；没有启动用户应用实例、真实 ATS 或模型。
[安装回执](installation.json)确认 52 个引擎文件、依赖、严格签名、原包备份，以及暂停批次、私人状态与已有进程身份保持。
现有实例保留；下次新 worker 使用已安装的修复代码。

包复制中的元数据权限警告未改变文件内容，逐文件校验与严格签名均通过。
首次包验收命令的参数错误保留在 `bundle-acceptance.log`。
包源码测试产生的临时字节码已移除，签名复验通过；测试 launcher 已禁用字节码，见[清理记录](package-cache-cleanup.json)。

[历史前核验](historical-check-before.json)与[历史后核验](historical-check-after.json)确认：
旧定位诊断、16 场景计量基线及两份旧 Cua 包，合计 **765 文件和四份封存清单原字节保持**。
原定位失败与原前置启动阻断均未删除或替换。
本轮 [126 个执行输入](fixed-execution-inputs-before.json)与[运行后指纹](fixed-execution-inputs-after.json)相同。
本目录由新的 `artifact-hashes.json` 封存。
