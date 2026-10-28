# 启动注册竞态与完整快照超时：隔离复现和后继修复

本轮修复两个已复现路径：主队列身份暂不可读导致启动提前失败，以及完整快照中的两条
全应用目录扫描。最终本地候选通过后台 worker、scope 刷新、完整快照和未知点击回执复验。
这不表示已安装应用或真实 ATS 验收完成。原票保持 open，安装版准入不变。

## 交付及版本

- [最终候选](candidate-03.json)：SHA-256 `9860ccc23f9064024dd76b8ee4137590fb4b1f711852a6276703a3acb70f2e9a`。
- 上游 `trycua/cua`，固定 base `c6cb386cf371fed3580ea1c5a238940ce4911641`，MIT。
- [相对上一轮的最小补丁](upstream-successor.patch)：5 个 Rust 文件。
  [相对固定 base 的完整补丁](upstream-full.patch)：包含之前生命周期修复，共 12 个文件。
  两个补丁均通过只读 reverse apply 检查，见 [源码绑定](source-changes.json)。
- [checkout 差异](checkout-change.patch)只更新显式候选的 SHA；没有全局启用候选。
  `docs/cua-worker.md` 增加后继指针，`CONVENTIONS.md` 澄清离线测试 marker 选择。
- Cargo.lock 保持，没有新增依赖。编译使用记录中的 Homebrew Rust/Cargo 1.98.1。
  候选为独立私有目录中的本地 debug 构建，未安装、签发、推送或发布。
- 原版 0.35.2/0.35.4 的准入阻断、Guardian 配置、发送守卫、来源上限及 owner TTL 保持。

## 启动身份路径

旧实现收到 LaunchServices completion 后，会在 AppKit 主队列重新读取
`NSRunningApplication`。任一次没有对象或 launchDate 就立即拒绝并进入清理。
这把“本轮注册快照尚不可读”与永久身份失败合并，绕过了原有的 3 秒就绪窗口。

本轮先保留 `final-worker` 自然失败，再在 `final02-slow-catalog` 自然复现相同拒绝。
新增的清理前诊断记录：PID 的 signal-0 检查成功，参数仍匹配本轮唯一 profile，
主队列却没有原生应用对象。系统日志、原始 RPC、预期 launchDate 均持久私有保存。
signal-0 和 profile 锁不能各自证明活性；系统日志的时间分辨率也不足以单独确定清理因果。

为检验这个实际失败分支，增加[原生 lookup 故障夹具](registration_fault.m)和
[public MCP 回归脚本](registration_fault_test.py)。它只注入新建的私有 daemon，
先确认真实 lookup 成功、可执行文件为系统 Chrome、参数匹配本轮 profile，再令主队列
的一次查询返回 nil。没有修改系统库、Chrome、已安装 driver 或现有进程。

| 同一故障输入 | 结果 |
| --- | --- |
| 旧 candidate-02，一次不可读 | 已复现拒绝，prepare 1 次；[红测](registration-fault-red-01-verification.json)。 |
| 修复 candidate-03，一次不可读 | 等待同一身份后成功，prepare 1 次；[绿测](registration-fault-green-01-verification.json)。 |
| 修复 candidate-03，持续不可读 | 在原 3 秒 posture 窗口拒绝；整体 prepare 3.33 秒含 LaunchServices 启动与清理；[期限对照](registration-fault-deadline-01-verification.json)。 |
| 修复 candidate-03，真实 SIGTERM | 精确核对本轮新 profile 后发送一次信号；拒绝且不重启，清理前 kernel/profile 检查均为 false。原文在私有 `startup-exit-control03.log`。 |

修复只把“原生对象/代次暂不可读”标为 WouldBlock，原 3 秒窗口内进行只读状态轮询。
最终仍必须匹配原 PID 和原 launchDate，并同时满足 hidden、未激活和 finishedLaunching。
启动代次不同、确认终止、激活或期限耗尽仍拒绝。没有重新 pin 身份、第二次 prepare、
重新启动、后置 hide 或 foreground fallback。

[Apple 文档](https://developer.apple.com/documentation/appkit/nsrunningapplication)
说明动态属性跟随主 run loop 刷新；这支持缓存/注册时序机制，不独立证明某一历史事件。
原 `native-06` 没有同等清理前探针，不能将其唯一归因于本轮已修复分支。

## 完整快照路径

真实 daemon 的一秒只读 sample 显示，等待不全在 CDP 内。两条路径查询了无关应用：

1. 授权资源的应用元数据补全调用全量 `list_apps`，扫描安装目录并启动多次 plutil。
2. 浏览器端点重新核验时，`classify_browser(pid)` 通过全量运行应用列表读取无关 plist。

最小复现只包含离线合成 combobox、本地合成 PDF、一次已完成展开点击和第二次完整快照。
子进程专用 PATH shim 在一次无关 plist 调用暂停 16 秒；没有修改系统 plutil。
`slow-catalog-red-02` 在原 MCP 15 秒期限失败，原 Page/同一 File 保持，后续五次请求不派发。
仅修补第一条路径仍失败，保留在 `slow-catalog-green`，随后定位并修补第二条路径。

现在两条路径都只查询目标 PID 的可执行文件与对应 bundle 元数据。原 fingerprint、
精确 PID、授权 bundle、窗口和来源校验保持；读取错误仍 fail closed。公开 `list_apps`
接口不变，不支持该私有适配器的平台仍保留旧路径。没有引入元数据缓存或新依赖。

同一延迟输入在最终 candidate-03 下不再触及无关目录，12 次完整快照全部通过，约
80–233 毫秒，见 [最终结果](final03-slow-catalog-result.json)。这里的延迟门没有触发，
证明无关依赖被移除，不能说“在真正等待 16 秒后仍于 15 秒内完成”。
原 `native-10` 没有阶段探针，因此它与已复现路径一致，但不能唯一归因。

## 验证及边界

[逐轮汇总](verification.json)保留 96 个混合诊断/复现 cohort 的原始结果。
这些轮次使用不同候选与输入，不能合并为 96 次成功或可靠性统计。

| 检查 | 结果 |
| --- | --- |
| core 最终快照修复回归 | 985 passed，1 ignored；含拒绝全目录 pending、错误 PID/bundle 和元数据读取错误的控制。 |
| 最终 macOS 库 | 569 passed，6 ignored。 |
| 最终 checkout 受影响测试 | 28 passed，12 deselected；[日志](checkout-candidate-03.log)。 |
| 完整 Python 离线套件 | 本轮较早候选 945 passed，119 deselected；[日志](offline-final.log)。最终 Python 变更仍仅为候选 SHA，随后通过上述 28 项。 |
| 无缓存、排除封存输入的 Ruff | lint 通过，168 文件格式通过；[lint](ruff-candidate03.log)、[format](format-candidate03.log)。 |
| 完整真实 worker + 强制 scope 刷新 | [通过](final03-scope-result.json)。同一 transport/daemon、原 Page/同一 File 保持，旧绑定退休，越界来源拒绝。 |
| 已完成真实点击的回执丢失 | [通过](final03-unknown-result.json)。原 15 秒期限；选择发生一次，未知 intent 保留，后续五次 tick 和强制刷新没有再派发。 |
| 完整快照与慢目录对照 | [通过](final03-slow-catalog-result.json)。12 次 complete semantic_v2，原 Page/File 保持。 |

原生通过场景均固定 Space，自有浏览器激活与窗口上屏采样为零。采样不等于逐帧证明。
页面完全离线并拦截到合成来源；真实 ATS、模型、网络上传和最终 Submit 为零。
没有更新已安装应用或改变现有运行。未知结果后跨 owner 到期、跨 daemon 保页和授权续期仍未验证。

## 保留的失败和执行事故

- 原封存失败、所有中间候选、无效 manifest、初版无效 shim 和第一版不完整修复均保留。
- `macos-final-02.log` 有一次测试子进程多继承一个监听端口的断言失败。该精确测试串行通过，
  后续完整默认并发 macOS 套件也通过；未改写原失败，未修改该测试来获得绿色结果。
- 用户提供的 PID 33842 报告精确匹配上一轮 Playwright 沙箱启动失败；见
  [对应关系](user-crash-correlation.json)。它与本轮原生系统 Chrome 属于不同版本/进程。
- 本轮负载复现误用 `-m not browser`，覆盖仓库默认排除，误选 worker_browser。
  在沙箱内产生 18 个 Chromium 启动失败，140 项已通过后中止精确 pytest PID 79747。
  [事故记录](sandbox-load-incident.json)与完整[失败日志](offline-startup-load.log)保留。
  用户提供的 PID 81448 也精确匹配此轮；[对应关系](user-crash-81448-correlation.json)。
  18 份匹配 crash 报告已复制到持久私有目录，原件未改。这些失败不算验收通过。
  `CONVENTIONS.md` 已明确离线回归沿用默认 marker，不传覆盖排除条件的 `-m`。
- 首次最终保全检查发现早期 `final-worker` 留下两层空的 DeferredBrowserMetrics 目录。
  先记录原路径，确认没有文件或匹配进程，再仅用 rmdir 清理。原失败 runtime 的 closed=false
  没有改写。首次失败[日志](finalize.log)保留，后继检查见下文。

## 保全及证据位置

[最终保全回读](preservation.json)核对现有私有 worker/页面/附件/配置、原有进程身份、
历史封存全树、此前持久私有原始诊断、已安装 TomorrowStar、CuaDriver 与 rollback，
以及之前冻结的候选与源码。自有进程、socket 和 profile 均须清理完成。

原始 RPC、system log、sample、crash、故障收据、构建日志和二进制保存在独立 0700
持久私有目录，见 [逐文件私有绑定](private-raw-binding.json)。独立 source 和 target 缓存
不作为原始诊断全树扫描；相关源码与冻结二进制已有单独哈希绑定。
[artifact-hashes.json](artifact-hashes.json)最后封存本目录；历史 seal 没有重写。

没有安装或启用桌面代理。本地修复及限定合成验收完成，票继续保留发布、安装和历史归因边界。
