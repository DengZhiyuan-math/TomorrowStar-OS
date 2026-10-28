# 原生重开来源调查

2026-10-14，Europe/Zurich。所属票：[调查 Cua 冷启动前置窗口阻断](../application-worker-stability/issues/07-cold-start-prewindow-investigation.md)。领取人 root，Status 保持 open。证据目录沿用本次调查启动日。

## 已确认的来源

**既有自然失败的直接发送者已确认是 Dock 进程 717。** 本轮找到原生发送与接收记录，而不仅是此前的置前客户端映射。

| 原生日志时间 | 进程与事件 |
| --- | --- |
| 2026-10-13 23:14:18.684336 | Dock PID 717，真实映像 `/System/Library/CoreServices/Dock.app/Contents/MacOS/Dock`，发送 `aevt/rapp`，target 为 Google Chrome，returnID 20001 |
| 2026-10-13 23:14:18.739609 | 自有 Chrome PID 81129 收到 `aevt/rapp`，returnID 20001，接收描述含 `target=Dock` |

间隔约 55.273 ms。[发送/接收证据](historical-send-receive-pair.json)保存进程映像、事件类别和精确 returnID。Chrome PID、启动代次、Space 与 New Tab 已在[前一封存调查](../cua-fixed-space-investigation-2026-10-13/README.md)绑定。本轮没有重跑或修改旧包。新读取的三秒原始日志留在私有目录，其他应用的两条事件未复制到本包。

这条记录将本次自然链定位为：初始隐藏成功 → Dock 后续发出重开 → 同代 Chrome 收到事件 → New Tab → 原前置守卫拒绝。该条 `rapp` 的立即发送进程是 Dock；本次证据没有指向 Cua 进程直接发送此事件。是否有其他请求间接触发 Dock，仍未确认。

## Dock 上游的证明边界

[目标时间窗](historical-upstream-boundary.json)保留本轮 Chrome 的置前消息、Dock 发送记录及发送后的 `Performing event <private>`。该队列消息位于发送之后，内容被系统隐去，不能把它认定为触发来源。发送与接收的 `activityIdentifier=0`，没有提供可继续绑定的请求活动链。

用户此前回答“不确定”，保持为未知。现有日志没有明确输入事件、调用栈或上游请求参数，不能认定用户点击了 Dock，也不能区分点击、菜单动作或其他请求。

Apple 将 Dock 图标点击列为 [kAEReopenApplication 的一个例子](https://developer.apple.com/documentation/coreservices/1556377-kaeqdnotor/kaereopenapplication)。这是接口语义说明，不能替代本次动作证据。[Apple 的重开处理说明](https://developer.apple.com/documentation/appkit/nsapplicationdelegate/applicationshouldhandlereopen(_:hasvisiblewindows:))也说明无可见窗口时可以创建窗口。本轮机制结论以实际 Chrome 原生对照为依据。

初次日志查询使用小数秒 CLI 边界，工具返回 64。保留[失败记录](upstream-time-boundary-attempt.log)与私有空输出；后继使用同一事件的一秒查询窗口，得到 14 条记录。没有改变系统日志或 Dock 设置。

## 固定 Space 的来源对照

复用已封存的实际拒绝路径，所有试验使用新建空 profile、精确 PID、AppKit 启动日期、私有 Cua socket；固定普通 Space 1，零额外离线负载。首次正式 CDP 连接被检查点拦截，未连接 CDP、创建 worker context 或 ATS 页面。

[事前预测](hypotheses-before-source-controls.md)与[输入清单](cohort-01-inputs.json)先于执行保存。[原始 pytest 输出](cohort-01.log)：**5 passed，1 failed，59.91 s**。6 次试验全部完成，Space 全程有效，无漂移；没有省略失败样本。

| 组 | 次数 | 实际行为与结果 |
| --- | ---: | --- |
| 无注入 | 2 | 到达 CDP 前检查点；目标/私有服务 AppleEvents 查询没有 `rapp` |
| 精确 PID 原生重开 | 2 | 发送工具返回 permission=0、send=0，无提示；两次均触发原 `cua_visibility_unknown / 无窗口启动出现了意外窗口。` |
| 精确 PID 单纯激活 | 1 | 请求被系统拒绝，返回 false；AppKit 始终未观察到 active。断言失败原样保留，不能用作有效激活对照 |
| 精确 PID 单纯激活 | 1 | 返回 true，独立采样观察到 Chrome active；没有 `rapp` 或屏幕窗口，前置守卫通过 |

[逐例索引](trial-index.json)区分 2 个自然无注入通过、2 个预期重开拒绝、1 个有效激活通过与1 个无效激活请求。激活读取在 0.5 s 后已 active=false，但连续采样观察到 earlier active=true；不得用单次后读抹掉该变化。

无注入样本只限定这两次环境，不能证明所有启动都不会产生重开。系统拒绝的一例说明激活请求返回值和实际激活必须核验；不是目标冷启动拒绝。

## 地址字段与已知发送者

`OwnedSourceAction.swift` 只接收自有 Chrome PID、预期启动日期和固定测试 returnID。调用前核验当前 profile 参数；原生工具再次核验启动代次。重开使用 Carbon `typeKernelProcessID`，没有 bundle-wide open、URL 或权限提示。激活使用 `NSRunningApplication.activate`，不主动发送重开 AppleEvent。

[原生事件读回](native-appleevent-source-readback.json)包含两组完整发送/接收记录：

| 发送者 | 接收 Chrome | returnID | 接收描述中的地址 |
| ---: | ---: | ---: | --- |
| 84855 | 84671 | 29001 | `psn (8/$01000000774b0100)` |
| 98978 | 98821 | 29002 | `psn (8/$01000000a2820100)` |

两次发送日志均显示发送工具真实 PID，目标为新 Chrome；接收日志的进程 PID 为该 Chrome。接收地址字节分别匹配已知发送者的 `[1, sender_pid]` 描述，而不是接收者 PID。[独立断言](sender-control-assertions.json)绑定发送者、接收者、returnID、地址字节以及原生窗口重叠。

因此，不能仅凭接收文本的 `target` 一词把 Dock 当作接收方。历史 Dock 来源由同事件发送日志直接证明；已知发送者对照进一步验证了这个字段的解释。Apple 的[属性说明](https://developer.apple.com/documentation/coreservices/1542920-keyword_attribute_constants)将地址描述为目标或客户端地址，也提供 sender PID 与原始来源属性；本次 Chrome 的历史日志没有这些完整事件属性。

两次拒绝的首次 Cua 窗口 PID/window ID 与独立 WindowServer 在首次读取区间一致，均为真实 New Tab。没有在失败后重新隐藏、自动重试或延迟放行。激活成功的一例没有窗口，说明本次程序化激活与重开不同；不将单例推广到所有激活入口。

## 用户补充的 Python 崩溃

用户在调查中贴入 Python 报告。原件复制到私有目录并保存摘要，本包仅含[脱敏分析](user-crash-triage.json)。

该报告记录 Python 3.14.5、PID 12530、父 PID 12430，于 2026-10-14 00:05:09.0917 中止。栈为解释器 finalize → buffered close → `_enter_buffered_busy` → fatal error，同时 `Thread-1 (feed)` 仍阻塞读取。这符合退出时缓冲 I/O 锁未释放的错误模式。[CPython 3.14.5 源码](https://github.com/python/cpython/blob/v3.14.5/Modules/_io/bufferedio.c)在 finalize 时等待该锁；宽限期后仍无法取得则触发 fatal error。

主试验实际使用锁定 Python 3.13.14。这个 PID 不匹配本轮记录的 Chrome/Cua PID；本轮最后原生清理早于该 Python 启动，原生日志没有该 fatal 信息。它可能属于其他辅助进程，但具体脚本和责任链未确认。相关六秒系统日志查询为零条记录；不能以零记录或 Codex coalition 字段认定归属。

本轮没有重现该退出崩溃，也没有据此修改 worker、共享 Python、Cua 或客户端。该报告不计为新的自然冷启动拒绝。

## 保全与复跑

[自有资源核对](resource-check.json)：6 个新 Chrome、6 个私有发现服务、6 个采样器和1 个空白 Space 控制器退出，独立进程查询无剩余 profile/socket/工具标记。本轮没有负载进程组。

[现有资源核对](existing-protection-summary.json)：原进程启动身份、私人记录/PDF/设置摘要保持；没有向现有 worker、浏览器、页面或附件发送命令。[历史后核验](history-check-after.json)确认 3,412 个旧文件无新增、删除或字节变化，包括前一包的 669 个封存成员及摘要文件。

[输入读回](input-readback.json)确认本轮执行文件与归档副本相同，118 个源码/测试/launcher/锁文件未变。[诊断 lint](diagnostic-lint.log)通过。所有原始失败与无效样本保留；生产启动、隐藏逻辑、守卫及超时没有改动。真实 ATS、模型调用、自动最终 Submit 为 0。

[原生输入回读](native-inputs-after.json)绑定 Chrome 155.0.8059.40、Cua 0.21.0 及实际驱动摘要。Space 工具沿用前一封存包：只读 SPI 签名适配自 [trycua/cua 固定提交](https://github.com/trycua/cua/blob/70db98d1bcd92890d778f4978e0eb107a4b66c1b/libs/cua-driver/rust/crates/platform-macos/src/input/skylight.rs)，[MIT 许可证](upstream-LICENSE.md)。本轮只增加精确 PID 原生动作与事件采集，没有改或重编译 Cua。

票保持 open：本次自然重开的直接发送者已经确认，Dock 上游触发动作及更早历史失败的同因尚未证明。没有足够依据实施运行修补。

后继复跑必须把 `debug_source_probe.py`、`owned-source-action`、`window-sampler` 与 `SyntheticSpaceAnchor.app` 复制到新的空白证据目录并重新建立保护基线；不得在本包重跑。入口按 `exist_ok=False` 创建 trial，一次一个新 Chrome，预算 480 s。

```sh
PYTHONDONTWRITEBYTECODE=1 TS_CUA_NATIVE_TEST=0 uv --cache-dir /private/tmp/ts-fixed-space-uv run --locked --offline python -B scripts/run_pytest.py -q -p no:cacheprovider -m worker_browser "$NEW_EVIDENCE_DIR/debug_source_probe.py"
```

原生权限缺失时跳过发送，不提示授权。系统日志收集只绑定 trial 记录的自有 PID，原始内容留在私有目录；另以 `collect_owned_events.py PRIVATE_OUTPUT_DIRECTORY` 回读事件并绑定摘要。
