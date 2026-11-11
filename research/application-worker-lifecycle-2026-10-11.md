# 申请 worker：浏览器生命周期与恢复边界

日期：2026-10-11，Europe/Zurich。研究票：[核验浏览器生命周期与故障恢复的原生边界](../.scratch/application-worker-next-stage/issues/01-browser-recovery-research.md)。

本报告核验原生能力及当前源码路径。没有读取个人运行目录、认证资料或真实 trace。没有启动浏览器、worker、模型或招聘请求。候选方案未实施；研究结论不关闭 HITL 恢复决策。

## 结论

**现有单 worker 可以增加局部故障诊断和检查点恢复，不需要先增加常驻浏览器服务。** 页面关闭或崩溃、context 关闭、浏览器断连、worker 退出和控制租约过期是不同事实。原生事件可以说明观察到的对象和影响范围，通常不能唯一证明退出原因。`TargetClosedError` 单独不能证明用户关闭、浏览器崩溃或 worker 退出。[Page 事件](https://playwright.dev/python/docs/api/class-page#page-event-close)、[Context 事件](https://playwright.dev/python/docs/api/class-browsercontext#browser-context-event-close)、[Browser 事件](https://playwright.dev/python/docs/api/class-browser#browser-event-disconnected)、安装源码 `_errors.py:52–54` / `_connection.py:369–383`。

**可以保留动作意图和已核验结果，不能承诺重启后恢复原 DOM，也不能承诺未知上传的 exactly-once 效果。** 当前代码在动作前保存 `intent`，在回读后清除；这能留下需核验的动作，却不能区分“尚未发出”与“已发出但未记下响应”。[当前 authorize 与动作回读](../src/career_evidence_graph/application_worker_browser.py)，`398–424`、`517–578`、`585–642`；[HTTP 重试语义](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.2)。

## 固定证据上下文

研究分支从 `e4a26d0c24311d014d478f7f92e58a88e6709b4b` 创建：`D_m/research/application-worker-lifecycle-20261011`。主工作区没有切换分支。报告分支只提交此报告；下列实现是在主工作区只读核验的未提交源码，不在该 HEAD 中。相对源码链接供主工作区报告副本使用。

依据：[2026-10-11 源码清单](../validation/application-automation/2026-10-11/workflow-consolidation/source-hashes.json)。本研究重算下列三个文件，均与清单一致。

| 文件 | SHA-256 |
| --- | --- |
| `src/career_evidence_graph/application_worker.py` | `18674c22d0e2da7b0019587fdabaea4fe73b1810d79c8ef7c5674afe353c22dc` |
| `src/career_evidence_graph/application_worker_browser.py` | `166f3d9daeb3cc5c4625f026c420d9440c2160f81ce8f60fa3cc94523ff4c587` |
| `src/career_evidence_graph/ashby_drafts.py` | `9c9e55b2b81cf892465c802e21911447fa0dbcd77377517d95ced65510549829` |

本地 `.venv/pyvenv.cfg` 为 CPython **3.13.14**。`pyproject.toml`、`uv.lock`、安装包 `METADATA` 和 driver `package.json` 均为 Playwright **1.63.0**。官方在线文档在研究时包含较新 API，例如 `Page.content(include_shadow)` 标记 1.64；本报告只采用已在 1.63.0 安装源码核验的接口。源码来自 Microsoft Playwright，Apache-2.0；本研究没有复制或改写上游代码。[Playwright 仓库](https://github.com/microsoft/playwright)、[Python binding 仓库](https://github.com/microsoft/playwright-python)。

## 原生事件与可证明的事实

| 观察 | 可以证明 | 不能单独证明 |
| --- | --- | --- |
| `page.on("close")`、`page.is_closed()` | 此 Page 已关闭 | 谁关闭；是否由 context 或浏览器关闭引起 |
| `page.on("crash")` | 此 Page 报告崩溃；页面操作会失败 | 精确崩溃原因；其他 Page 是否仍可操作 |
| `context.on("close")`、`context.is_closed()` | context 正在关闭或已关闭；其页面不可继续使用 | 主动关闭与浏览器退出/崩溃的唯一原因 |
| `context.on("pageclose")` | context 中具体哪一 Page 关闭；1.63 已安装 | 页面关闭原因 |
| `context.browser.on("disconnected")`、`is_connected()` | 控制连接已断开 | 浏览器主动关闭、崩溃或调用 close 的唯一原因 |
| 当前父进程的 `Popen.poll()` / `wait()` | 此受管 child 是否终止及 return code；POSIX 负值表示信号 | 浏览器 PID/退出码；新父进程对旧 worker 的历史退出事实 |
| `worker_heartbeat` 过期 | 最近没有完成检查点心跳 | 死亡、卡住、休眠、磁盘失败或排队中的具体原因 |
| 控制 `heartbeat_at` 超租约 | 控制许可已过期 | worker 或浏览器已退出 |

事件语义来自 [Page close/crash](https://playwright.dev/python/docs/api/class-page#page-event-crash)、[Context close/pageclose/is_closed](https://playwright.dev/python/docs/api/class-browsercontext#browser-context-event-close)、[Browser disconnected/is_connected](https://playwright.dev/python/docs/api/class-browser#browser-event-disconnected)；进程语义来自 [Python Popen](https://docs.python.org/3.13/library/subprocess.html#subprocess.Popen.poll)。`context.browser` 是可选属性，应先检查；正常 Chromium context 有所属 Browser。[Context.browser](https://playwright.dev/python/docs/api/class-browsercontext#browser-context-browser)

安装源码 `_page.py:354–363` 只在 close 处理器设置 `_is_closed`，crash 处理器另发事件。因此仅轮询 `is_closed()` 会漏掉空闲页面崩溃。`_errors.py` 将 Page、Context、Browser 关闭归入同一错误类型；`_connection.py` 在控制连接清理时也用该类型释放待响应调用。候选实现应使用公开 `Error` / `TimeoutError` 和原生事件，不依赖 `_impl` 的私有类型接口。

当前 `WorkerService.process` 是 portal 实例内的 `Popen` 句柄。`snapshot()` 不调用 `poll()`，持久化 PID 也不在正常退出时清空。portal 重启后重新构造服务没有旧 child 句柄。现有 `.worker.lock` 说明锁是否仍占用，不能证明 worker 正常处理页面。[当前进程与状态实现](../src/career_evidence_graph/application_worker.py)，`274–315`、`316–359`。

当前租约用 `time.time()`，时钟倒退或间隔超限均暂停；这不是休眠诊断。单次运行内部耗时可用 `time.monotonic()`，但它没有跨重启的持久身份，也不能从间隔唯一判断休眠。macOS 的休眠识别仍需另行核验。[Python 时钟](https://docs.python.org/3.13/library/time.html#time.monotonic)、[当前 tick / authorize](../src/career_evidence_graph/application_worker_browser.py)，`332–346`、`398–411`。

## Profile、DOM 与已有浏览器连接

`launch_persistent_context(user_data_dir)` 返回唯一 persistent context；关闭它会关闭浏览器。profile 保存 cookies、local storage 等浏览器数据；同一目录不能并发启动多个浏览器。其 API 没有承诺恢复完整 DOM、JS 堆、未保存表单、内存映射或未完成请求。storage-state 的认证复用也不是页面快照。[Persistent context](https://playwright.dev/python/docs/api/class-browsertype#browser-type-launch-persistent-context)、[认证状态](https://playwright.dev/python/docs/auth#reusing-signed-in-state)

当前 worker 是 **Python → Playwright driver → 启动的 Chromium** 所有权链。`sync_playwright().__exit__` 停止 pipe；安装 driver 的 `runDriver()` 在 pipe 关闭后执行退出清理，process launcher 清理已启动的浏览器。它没有将浏览器生存期交给 CDP 客户端。正常退出会进入清理；强杀、OS 故障等仍不能承诺同样时序。[上游 driver](https://github.com/microsoft/playwright/blob/v1.63.0/packages/playwright-core/src/cli/driver.ts)、安装 `sync_api/_context_manager.py:83–99`、`coreBundle.js:9260–9297,9365–9402,69932–69954`。

| 连接方式 | 原生能力 | 当前项目边界 |
| --- | --- | --- |
| `connect()` | 连接 Node `launchServer` 的 Playwright endpoint；major/minor 要匹配 | 当前 Python launcher 未创建这种 server；现在引入会增加运行结构 |
| `connect_over_cdp()` | 连接已存在 Chromium；可以枚举默认 context/pages；协议能力低于 Playwright 连接 | 仅当该 Chromium 仍活着、endpoint 可用时成立；不能复活已关闭 Page |
| 重启 persistent context | 用旧 profile 启动新 context | 新实例需要身份与结果核验；不能把 profile 复用称为原 DOM 恢复 |

连接约束来自 [connect / CDP](https://playwright.dev/python/docs/api/class-browsertype#browser-type-connect-over-cdp)。当前 `--cdp-port` 只是启动 Chromium 的附加参数，worker 没有调用连接接口或将旧 Page 重新绑定岗位。[当前 main](../src/career_evidence_graph/application_worker_browser.py)，`729–742`。连接存活浏览器后，仍须重新建立岗位绑定、路由、事件、答案/PDF 版本和人工交接状态；这是当前内存状态分布的推论，不是 CDP 自动恢复保证。

## 当前局部异常扩大为批次异常的路径

| 当前路径 | 已证源码行为 | 推导出的故障风险 |
| --- | --- | --- |
| `tick()` 的 `process(job)` | `Error` 等转为此岗位 `needs_recheck`，继续后续岗位 | 局部 catch 已存在，可复用 |
| `commands(state)` | `close`、`unroute`、`bring_to_front` 在 per-job catch 之外 | 关闭竞态或命令操作失败可到 main catch，影响整批 |
| main 的 `context.pages[0].wait_for_timeout(250)` | 在 per-job catch 之外；1.63 driver 的 timer 与 Page open scope 竞争 | 首页面在等待中关闭/崩溃可以退出 worker，即使其他页面仍存活 |
| main 的无页面 `time.sleep(0.25)` | 未切回 sync Playwright dispatcher | context 关闭事件可能延迟；缓存状态不能当实时诊断 |
| main catch | 保存 `control=paused` 和异常类名，然后退出 `with sync_playwright()` | 清理可能关闭其他页面；旧 `page_open` 仍留在检查点，直到下次启动处理 |

依据：[当前浏览器实现](../src/career_evidence_graph/application_worker_browser.py)，`271–330`、`332–378`、`743–760`。安装 `_page.py:1143–1144` 将等待转给主 Frame；`coreBundle.js:24257–24267` 将 timer 与关闭 scope 竞争。同步 dispatcher 在 `_sync_base.py:96–113` 切换；官方说明 `time.sleep` 会阻止内部异步处理。[Sync library 已知问题](https://playwright.dev/python/docs/library#known-issues)

这证明当前代码存在扩大故障范围的路径，**没有复现某次真实退出，也没有定位历史根因**。本轮没有运行浏览器。`context.pages[0]` 也可能是人工新开的页面，不能用列表位置代替岗位身份。

## 待发送、结果未知、已核验的边界

Playwright 的 `request` 表示页面发出请求；`response` 表示收到响应头；`requestfinished` 表示响应体下载完成。HTTP 4xx/5xx 也可能产生 `requestfinished`。这些事件不是业务成功证明；断连、`requestfailed` 或没收到响应，也不能证明服务端没有应用请求。[Request 生命周期](https://playwright.dev/python/docs/api/class-request)

| 动作状态 | 最低证据 | 故障后可保留的结论 |
| --- | --- | --- |
| 待发送 | 持久化 prepared intent，尚未观测发出 | 有计划执行的动作；因发出与记录之间存在窗口，不能仅据此确认未发送 |
| 已发送但未回读 | 观测 request / 传输阶段，未完成业务回读 | 结果未知；不转为成功，也不自动重传未知上传 |
| 已核验 | 精确岗位/字段/答案 revision/PDF 内容绑定，满足该路径的页面及必要服务端回读，保存检查点 | 曾在该时刻核验通过；重开页面后仍须复核新状态；不代表人工 Submit 或 employer receipt |

当前检查点没有持久化请求发出阶段。`DraftSession.pending/active/handle/uploaded/linked` 均在内存中。其 response parser 已核验字段保存、上传和挂接，但中途退出会丢失这些阶段事实；`intent` 可以保留未知动作。[当前 DraftSession](../src/career_evidence_graph/ashby_drafts.py)，`65–79`、`114–127`、`152–292`、`301–327`。因此“三状态”是候选诊断模型，不是当前已具备的可靠发送分类。

当前 `run.json` 通过同目录临时文件、flush/fsync、`os.replace` 保存；目录 fsync 是尽力执行。这保护单个文件替换，不能将浏览器网络效果、服务端写入与磁盘检查点组成事务，也不能补录 worker 被强杀后未保存的事件。[现有 helper](../src/career_evidence_graph/_vendor/job_apply_store.py)，`68–110`；[Python replace](https://docs.python.org/3.13/library/os.html#os.replace)、[fsync](https://docs.python.org/3.13/library/os.html#os.fsync)。

当前重新启动会暂停批次，将旧 `page_open` 或 `intent` 岗位改为 `needs_recheck`，清除 one-use 命令并重新 launch；不重建旧 `ApplicationRunner.pages`。同步重试走独立 `pending_sync`，不重复浏览器动作，可继续复用。[启动恢复](../src/career_evidence_graph/application_worker_browser.py)，`713–728`；[同步实现](../src/career_evidence_graph/application_worker.py)，`232–253`。

## 候选最小方案与后续验收

以下是进入 HITL 讨论的技术候选，不是用户已选择的保证等级。

1. 先保留单 worker、现有文件 store 和锁。增加 run 身份、源码版本、原生事件与父进程退出事实；保存稳定事件码和岗位标识，不保存答案值或请求正文。浏览器 PID/退出码没有当前 Python 公开 `Browser` 接口可直接替代，缺少时明确写 unknown。
2. 先修复 batch 外的页面操作边界。命令按岗位处理异常；page close/crash 只标记受影响岗位。context close/browser disconnected 标记共同故障。事件 handler 先收集事实，由 tick 串行写检查点，减少回调中的嵌套页面操作。
3. 用 context 级原生事件等待作为同步循环候选，例如有界 `context.wait_for_event("close", timeout=250)`，只将预期 `TimeoutError` 视为无事件。它可泵送 dispatcher，不绑定首 Page；context 已关闭时先停止动作。不要仅改成 `time.sleep`。此方案必须先通过合成浏览器验证。
4. 复用 `intent` / `observations` / `pending_sync`。为动作增加 attempt 身份和 observed transport 阶段；任何未持久化核验仍为 unknown。事件记录不能消除 crash window。只有明确幂等语义或可核验未应用时，才有自动重试依据。[RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.2)
5. 本阶段先按“存活页面保留 + 不确定结果暂停 + 检查点复核”验收。是否需要浏览器独立于 worker 存活、自动 CDP 重连或重开后重填，由恢复 HITL 票决定；本研究不增加 daemon，也不替用户确认重传。

| 待执行合成用例 | 要观察的事实 |
| --- | --- |
| 两页存在；第一 Page 在轮询期间 close / crash | 另一 Page 保留；仅该岗位停；worker 存活；关闭与崩溃分码 |
| 命令 close / unroute / bring-to-front 出现竞态 | 命令错误不结束无关页面；intent 保留 |
| 没有 Page 或批次 paused 时关闭 context/browser | native event 得到处理；状态及时更新；不只依赖旧心跳 |
| 关闭控制页、worker 在忙等待、系统时钟跳变 | 租约事实与进程事实分开；不将超时判为崩溃 |
| 动作前、发出后、业务响应后、检查点前强制中断 | unknown 不提升成功；未知上传不重传；已核验历史保留 |
| 仅同步失败后恢复 | 只重试笔记同步，浏览器 fill/upload 次数不增加 |
| 若 HITL 选择 CDP：连接专用合成浏览器 | 存活条件、页面重新绑定、路由/WS 阻断、handoff 状态完整核验 |

这些用例尚未执行。旧回归数不能作为此切片已通过的证明。

## 未验证边界与需要人决定的事项

- 历史退出原因：没有读取私人日志或 OS crash 记录，保持 unknown。
- macOS sleep/wake：没有进行系统休眠试验；不能从租约过期唯一归因。
- 浏览器强杀、driver 强杀与 Python 强杀的清理时序：只核验源码，未做进程试验。
- CDP 重连：未启动浏览器或连接 endpoint；本地路由、WebSocket 与手动交接兼容性未验证。
- 网站草稿保留期、服务端幂等键、附件重传规则：没有新的站点证据，不能给跨站保证。
- 用户取舍：需要保留到哪种故障层级、允许何时重开/重填、未知上传如何交接、诊断和暂停时限。研究建议不能替代这些决定。

## 安装源码指纹

相对于 `.venv/lib/python3.13/site-packages/playwright/`，用于绑定本轮安装源码观察。它们是公开软件字节，不包含个人数据。

| 文件 | SHA-256 |
| --- | --- |
| `_impl/_errors.py` | `49407bd6164ab563f82b2bf37863a265555071544dcabedbf7beba8be1b618cd` |
| `_impl/_connection.py` | `7a1fe6c84e5108024b58d2afa4f2d8323ca86d76adecde5e8a747c3bab2bd49b` |
| `_impl/_page.py` | `3b79b620022bb32786a39fe6338b3f7fdc84f1c8cc5699a95c0eea278d0d0fdd` |
| `_impl/_browser_context.py` | `595800a63fa0b9901b46e30a5a8defca46f746b8c2a20bd7e8cb02193151e494` |
| `_impl/_browser.py` | `49ab46355ff642472f46f07c6708d1bb965cc2b01eedd67fbcfd38e3d3414d41` |
| `_impl/_sync_base.py` | `f9924a820f7e74ddd71514598142363f3484c364178935eefbe80f9db8998997` |
| `sync_api/_context_manager.py` | `4ad37eb82b50490219069bb3fd755e74947adf57b64acc9a49a20568c10e6e3f` |
| `driver/package/lib/coreBundle.js` | `549070af3acabb3efcc4f55bfe6210f9f7c2fcf633cf7eaa59bfe60719969171` |
