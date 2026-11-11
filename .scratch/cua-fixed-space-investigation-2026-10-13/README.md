# 固定 Space 冷启动对照

2026-10-13。所属票：[调查 Cua 冷启动前置窗口阻断](../application-worker-stability/issues/07-cold-start-prewindow-investigation.md)。领取人 root，票保持 open。

## 结论

**已在固定普通 Space 中自然复现一次原前置阻断，并定位本次故障机制：Chrome 隐藏后收到原生 `aevt/rapp` 重开事件，产生真实 New Tab，守卫随后拒绝。** 两次精确 PID 的原生重开注入均复现同一错误；相邻无注入对照均通过。

自然日志的事件元数据含 `target=Dock`，系统置前请求也涉及 Dock 客户端。用户回答“不确定”，保留为未知。不能认定用户点击了 Dock，也不能确认是谁触发重开。历史失败缺失窗口条目，不能把本次机制直接追溯为历史单次原因。

生产启动、隐藏逻辑、守卫和超时均未修改。本轮所有有效启动都在 CDP 连接前结束，没有创建 worker context、ATS 页面或上传附件。注入创建的是 Chrome 原生 New Tab。真实 ATS、模型调用、自动最终 Submit 为 0。

## 自然失败证据

[原始结果](cohort-02-app-anchor/trials/regular/01-load-0/result.json)、[首次调用与清理日志](cohort-02-app-anchor/trials/regular/01-load-0/cua.log)、[独立 WindowServer 轨迹](cohort-02-app-anchor/trials/regular/01-load-0/windows.jsonl)全部保留。这一例使用当前生产启动路径、无额外负载、独立空 profile，没有窗口或重开注入。

| 苏黎世时间 | 观察 |
| --- | --- |
| 23:14:16.712779 | LaunchServices 应用 `hideAfter=1, dontMakeFrontmost=1`，随后 `HideOnLaunch` |
| 23:14:17.156118 | AppKit 确认本轮 PID 81129、启动代次绑定，hidden=true、active=false |
| 23:14:18.678588 | 系统执行对本轮 Chrome 的后续置前 |
| 23:14:18.739609 | 同一 Chrome 的 AppleEvents 接收日志记录 `RECEIVED:(aevt,rapp)` |
| 23:14:18.935269 | WindowServer 观察同 PID 的窗口 3127 在屏幕上；先 alpha=0，后 alpha=1 |
| 23:14:21.292392 | 原守卫返回 `cua_visibility_unknown / 无窗口启动出现了意外窗口。` |
| 23:14:23.658445 | 身份绑定清理完成 |

首次 Cua 响应报告 New Tab、window ID 3127、Space 1、1200×905、`is_on_screen=true`。第二次只读响应报告相同窗口。独立采样的 PID、window ID、首次读取时间区间一致。Space 全程为 1，未在启动中重新激活控制器。

[脱敏原生事件摘录](natural-native-event-evidence.json)保留同一自有 Chrome 的真实接收事件、初始隐藏标记及私有原始日志摘要。[当前客户端映射](activation-client-current-lookup.json)只证明读回时客户端指向 Dock；它单独不能证明历史发送链或人的操作。系统原始日志留在私有临时目录，未复制其他应用活动到本包。

日志中首次 `application` 字段是先前 hide 的确认回执；后来的 `failure_appkit_complete` 才是拒绝后的读取。不能将旧回执的 hidden=true 当作拒绝时状态。后者记录 hidden=false。[三例原生拒绝核对](native-guard-confirmations.json)保存了这一时间区别。

## 对照与完整分母

[50 次试验索引](trial-index.json)包含完整结果指针、首次 Cua 响应、Space 检查、错误和采样间隙。共计划 80 次，实际执行 50 次；前两组遇失败按 `-x` 停止，30 次未执行。

| cohort | 实际 / 计划 | pytest | 有效自然样本 | 其他结果 |
| --- | ---: | --- | --- | --- |
| [01 原控制器](cohort-01.log) | 9 / 24 | 8 passed，1 failed | 8 通过 | 1 次启动前 Space 漂移 |
| [02 标准 AppKit 控制器](cohort-02.log) | 1 / 16 | 1 failed | **1 次自然目标拒绝** | 首次失败即停止 |
| [03 去除准备等待](cohort-03.log) | 4 / 4 | 4 passed | 4 通过 | 未自然复现 |
| [04 恢复原准备时序](cohort-04.log) | 4 / 4 | 4 passed | 4 通过 | 未自然复现 |
| [05 直接启动对照](cohort-05.log) | 12 / 12 | 3 passed，9 failed | 3 通过 | 2 次 Chrome 未确认身份；另 7 次 Space 无效 |
| [06 LaunchServices / NSWorkspace](cohort-06.log) | 16 / 16 | 16 passed | 16 通过 | 普通 / 自有全屏各 8 次，全部有效 |
| [07 原生重开](cohort-07.log) | 4 / 4 | 4 passed | 2 次无注入通过 | **2 次预期重开拒绝** |

合计 38 次有效无注入启动：37 次通过、1 次自然目标拒绝；2 次原生重开注入；10 次准备/身份失败。10 次失败原样保留，不计入自然故障或通过。其中一次身份失败同时存在 Space 漂移。控制器两次单独入场检查也保留于 [入场结果](anchor-admission.log)，不计为 Chrome 启动。

cohort-01 的 CLI 空白窗口没有稳定保持前台。cohort-05 无条件重激活全屏控制器造成入场漂移，六个全屏样本均在 Chrome 启动前停止。后继入口改用标准 `NSApplication.run`；当前 Space 已正确时不重激活，只在启动前检查稳定状态。没有改已执行源码或失败记录。

cohort-06 中普通 Space 1、自有全屏 Space 177 各执行 stock / NSWorkspace 启动及 0 / 1 个离线负载套件对照。16 次均通过，不能由此认定 NSWorkspace 修复故障。直接 Chrome 二进制启动没有达到原身份前置条件，不能作为等价启动证明。

cohort-01/02/04 使用启动前 5 s 准备；03/06/07 去除该准备。05 保留 5 s 准备。准备发生在诊断入口，生产启动没有新增等待。历史路径名 `load-2` 表示第二次负载试验，旧脚本实际只有一个离线套件；cohort-06 对齐的是负载时序，不是完整历史环境。

## 最小机制与排除结果

[事前预测](hypotheses-before-reopen-control.md)先于原生重开对照保存。cohort-07 在普通 Space 1、零额外负载、空 profile 下运行两组无注入 / 重开试验。发送前再次核验精确 PID、AppKit 启动日期和唯一 profile 参数。

`OwnedReopen.swift` 用原生 Carbon AppleEvent 地址 `typeKernelProcessID`，只发 `aevt/rapp`，没有 URL。权限检查不提示，发送禁用交互。两次返回 permission=0、send=0，没有新授权弹窗。首次守卫读取前发送；独立 WindowServer 确认真实窗口，两次均触发原守卫。没有 CDP、人工构造目标或后续 ATS 动作。

这使“原生重开可使已隐藏无窗口 Chrome 创建 New Tab，并导致原守卫拒绝”成为有独立对照的机制结论。自然日志直接出现同类接收事件，支持本次自然失败的解释。零负载仍可触发，不能把负载认定为必要条件。

四次成功样例也记录 AppKit `shouldRestoreState=1 / hasPersistentStateToRestore=1`。这些恢复标记不是足够原因，不能据此删除共享保存状态或使用 `open -F`。本轮没有执行这些操作。

Cua 与 WindowServer 的 PID/window ID 一致，不支持本例为虚假窗口或错 owner。Space 没有变化，不支持本例仅由跨 Space 标记差异造成。Cua 服务启动早于故障，不足以证明 Cua 发送了重开事件。发送源和历史同因仍未确认，未进行猜测性修补。

## 采样与输入边界

使用本轮空白 AppKit 窗口建立普通 / 自有全屏 Space；每个有效试验连续检查全局 Space、控制窗口所属 Space 与该显示器当前 Space，首个 Cua 响应另行核对。系统仍有其他桌面与并发应用；这不是隔离登录会话。最大采样间隙约 742 ms，自然失败样例约 118 ms。有限采样可能漏掉更短事件；屏幕标记不等于逐帧像素证明。

实际原生输入为 Chrome 155.0.8059.40、Cua 0.21.0；[二进制摘要](native-inputs-after.json)全部一致。[执行输入读回](input-readback.json)与[归档副本读回](frozen-input-copy-readback.json)均通过。118 个源码/测试/launcher 与锁文件摘要未变。

诊断 Space SPI 签名适配自 [trycua/cua 固定提交](https://github.com/trycua/cua/blob/70db98d1bcd92890d778f4978e0eb107a4b66c1b/libs/cua-driver/rust/crates/platform-macos/src/input/skylight.rs)，MIT [许可证](upstream-LICENSE.md)。本地新增 Swift 的只读 Space 查询、空白控制窗口和连续采样；未改或重编译 Cua。安装二进制是否来自这个 tag 未独立证明，运行结论来自实际调用。

## 核验与保全

[既有失败采集回归](boundary-regressions.log)：4 passed、21 deselected。它们是合成替身测试；与上面的真实原生事件对照分开。[现有资源核对](existing-protection-summary.json)确认私人记录/PDF/设置摘要相同，原进程启动身份全部保持。没有向原有 worker、浏览器、页面或附件发送命令。

[历史后核验](history-check-after.json)：2,742 个文件没有新增、删除或字节变化。所有准备失败、自然失败与注入结果都保存为后继输出。私有明细留在 `/private/tmp`。

[自有资源核对](resource-check.json)：43 个新 Chrome、41 个私有发现服务、50 个采样器、16 个负载组均无存活标记；9 个试验控制器及两次入场控制器退出。临时 profile/socket 与新工具路径无剩余匹配。`cua-runtime.json` 的 closed=false 是前置专项结束记录，清理由 context manager、退出码和独立进程读回确认。

清理核对脚本初次 lint 有 5 处超长行，见 [原输出](final-diagnostic-lint.log)。先保存[已执行版本](inputs/resource_check-executed.py)与[摘要绑定](resource-check-input.json)，再仅整理未来入口格式。[最终诊断 lint](final-diagnostic-lint-clean.log)与 `git diff --check` 通过；格式整理没有新增原生验收结论。

票保持 open：本次自然故障机制已定位，但自然事件触发来源和历史失败同因尚未证明。后续有价值的调查是绑定下一次重开事件的发送来源与时间链；继续无差别重复启动不能填补这个证据缺口。

## 后继复跑

必须把诊断入口、Swift 原生工具和 `SyntheticSpaceAnchor.app` 复制到新的空白后继目录，再运行；不得向本封存目录重跑。入口的试验目录使用 `exist_ok=False`，每次只启动一个新 Chrome，额外离线进程组最多两个，总预算 480 s。

自然固定 Space 对照使用 checkout launcher：

```sh
PYTHONDONTWRITEBYTECODE=1 TS_CUA_NATIVE_TEST=0 uv --cache-dir /private/tmp/ts-fixed-space-uv run --locked --offline python -B scripts/run_pytest.py -q -p no:cacheprovider -m worker_browser "$NEW_EVIDENCE_DIR/debug_workspace_controls.py"
```

原生重开机制对照将末尾入口改为 `debug_native_reopen_probe.py`。它只绑定新建 Chrome 的精确 PID；没有自动化授权时跳过发送，不请求新权限。后继必须再次建立私人保护快照、绑定输入与独立清理，不把注入通过计为自然稳定性通过。
