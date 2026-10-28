# Cua worker：后台窗口与原页人工交接

实施与验收：2026-10-12 至 2026-10-13，Europe/Zurich。
范围：checkout Cua worker、本机 CuaDriver 0.21.0、隔离系统 Chrome、合成表单。

## 交付行为

| 行为 | 当前实现 |
| --- | --- |
| 常驻后台 | 同一浏览器和 context 复用后台标签。使用原生 CDP `background=true`、`focus=false`；导航前核验窗口已最小化。暂停或等待答案期间保留浏览器。 |
| 人工复核 | 只在用户发出的 `review` 命令中恢复工作窗口，然后沿用原人工接管流程。重新核验唯一 Cua 页面绑定，保留原 Chrome target、DOM 和附件文件对象。 |
| 显示失败 | 标记 `handoff=unknown`，暂停该岗位。显示成功前不释放自动层发送守卫。 |
| 人工窗口保留 | 存在人工接管页面时，新后台页使用 `keep_visible`。不再次最小化用户正在复核的窗口。 |
| 状态与提交 | 继续使用原 WorkerStore、许可、intent、答案引用、文件版本和发送守卫。自动层没有最终 Submit 动作。 |

实现见[操作说明](../../docs/cua-worker.md)与[固定交付指纹](delivery-source-hashes.json)。
没有新增依赖、Hermes runtime、答案库或模型控制循环。启用 `--worker-cua` 后默认生效。

## 验证结果

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 完整默认离线回归 | **904 passed，97 deselected** | [日志](offline.log)、[JUnit](offline.xml) |
| 完整无窗口 browser 回归 | **92 passed，4 skipped，905 deselected** | [日志](browser.log)、[JUnit](browser.xml)。4 个原生场景按 opt-in 规则跳过。 |
| Cua 模块，原生 opt-in | **16 passed，其中 4 个本机原生场景 passed** | [日志](cua-final.log)、[JUnit](cua-final.xml)。此后只扩充非原生交接回归；生产模块未再改变。 |
| 当前交接与守卫重点回归 | **2 passed** | [日志](handoff-final-green.log)、[JUnit](handoff-final-green.xml)。纳入最终完整 browser 回归。 |
| 维护目录 Ruff lint / format | **passed，114 files formatted** | [lint](ruff-maintained.log)、[format](ruff-maintained-format.log) |
| 历史证据与输入完整性 | **passed** | [完整性核验](integrity-check.json)：123 个验证输入未变；此前 3 个封存包共 116 个文件未变。 |

本机原生场景：

| 场景 | 独立回读与结果 |
| --- | --- |
| 隐藏填表与原页交接 | 每步采样 `windowState=minimized`，Chrome 非前台；WindowServer 窗口不在屏幕上。Cua 完成确认选项选择，达到 `ready_for_review`。用户复核命令恢复原窗口；同一 Playwright Page、真实 Chrome target 和同一 File 对象均保留。见[原生记录](native-final/native-review.json)。 |
| 未知发送 | Cua 选择操作触发合成 POST。原守卫拦截 **1** 次，放行 **0** 次；保留 intent，状态为 `needs_recheck/unverified_send_path`。见[记录](native-final/native-blocked_send.json)。 |
| 选项歧义 | 两个同名选项时停止，保留 intent，状态为 `needs_recheck/cua_control_ambiguous`；发送放行 **0** 次。见[记录](native-final/native-ambiguous_option.json)。 |
| 独立 worker 生命周期 | 一次合成附件传输，自动最终提交 **0** 次；SIGTERM 后本次 Chrome、daemon 和 socket 全部清理。见[记录](native-final/native-process.json)。 |

三个表单场景共用一个浏览器、context 和窗口；最终验收只在交接场景主动恢复一次。
生命周期测试另用一个后台实例。全套后续 browser 回归使用 headless，没有重复原生可见实验。
原生实例的清理由[共享运行记录](native-final/resident-runtime.json)及独立进程核验确认；不关闭日常 Chrome 或共享 Cua 服务。

非原生交接回归还验证：显示拒绝后 POST 仍被拦截；第一个岗位人工接管后重开另一个页面时传入 `keep_visible=true`，原页和附件保留。
第二个页面的旧已验证结果无法回读时，仍按原规则暂停，未放宽恢复守卫。

## 实际边界

当前采用 Chrome 原生最小化，Dock 图标仍可见。驱动的首次隔离初始化可能短暂显示空白窗口；接入后关闭该空白页。
当前证据确认工作页填表期间隐藏，不声明启动全过程零帧可见，也不是完全无窗口执行。

原页面和附件保证限于同一仍存活的运行。停止 worker 会关闭本次浏览器；磁盘检查点不恢复旧 DOM 或 File 对象，未知动作继续禁止自动重放。
本机隐藏 Cua 操作使用显式 `dom_event` 路线。0.21.0 的后台 `trusted` click 拒绝保持原行为，没有静默降级。
本次真实 ATS 调用、模型调用和自动最终提交均为 **0**。安装包重新构建与真实岗位覆盖未执行。

## 保留的失败与修正

[初始交接失败](review-red.log)证明原路径未调用 Cua 显示入口。
[原生隐藏尝试](hidden-native-first.log)、[诊断](hidden-native-diagnostic.log)及[方法调用诊断](hidden-native.log)保留本机 AppKit 整应用隐藏拒绝。
最终实现删除该调用，复用 Chrome 原生 CDP，不扩展权限。

[初始 CDP 回归](hidden-cdp-native.log)、[异步状态失败](hidden-shared-native.log)、[后台标签诊断](visibility-diagnostic/visibility-blocked_send.json)保留窗口状态回读与新增标签恢复窗口的事实。
修正为后台打开、禁止焦点激活、导航前明确最小化并等待实际状态；不会把一次发送请求当作隐藏成功。

[交接身份断言失败](hidden-green-native.log)来自把 Cua 的不透明绑定 handle 当作永久 Chrome 身份。
最终验收检查真实 Chrome target、Page 和 File 对象，并在恢复后重新取得 Cua 绑定。
前几轮非原生交接夹具错误见 `handoff-*.log`；仅修正合成场景，未放宽批次保留、已验证结果恢复或发送规则。

仓库全范围 Ruff 会扫描历史 scratch 重建副本和已封存探针，产生 **122 lint errors、15 files unformatted**，记录见[全范围 lint](ruff-check.log)与[全范围 format](ruff-format.log)。
这些证据副本按原字节保留；维护目录检查通过。没有用格式化或清理改写旧封存包。

## 原生接口依据

[本机 createTarget 契约](installed-cdp-contract.json)来自本次测试专属 Chrome 的实时 `/json/protocol`，包含 `background`、`focus` 和 `windowState`。
字段定义亦见 [Chrome 官方 CDP Target](https://chromedevtools.github.io/devtools-protocol/tot/Target/) 与 [Browser 窗口接口](https://chromedevtools.github.io/devtools-protocol/tot/Browser/)。
安装驱动的原生 MCP 契约沿用[此前固定快照](../cua-direct-probe-2026-10-12/tools.json)。

[验证输入](verification-inputs.json)与[最终交付指纹](delivery-source-hashes.json)分别记录可执行输入和相关文档。
本目录以 `artifact-hashes.json` 封存；失败记录保持失败状态。
