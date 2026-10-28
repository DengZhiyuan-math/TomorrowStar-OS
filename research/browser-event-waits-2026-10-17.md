# 事件等待与 CDP 控制：开源补充研究

核验日期：2026-10-17。研究票：**研究事件等待与 CDP 控制的可复用机制**。研究分支：`D_m/research/browser-event-waits-20261017`。

## 结论

新增 **6 个项目**；Playwright 是既有项目复核，不重复计数。优先复用已安装 Playwright 的事件 API，并借鉴“先订阅、后触发、按结果结束、统一清理”的机制。没有源码证据支持为当前约255ms的固定pump成本更换浏览器runtime。nodriver和zendriver也有固定等待或静默窗口，不能根据“async/CDP”名称推定更快。

本地依据是[隔离合成基线](../.scratch/browser-efficiency-2026-10-17/baseline-report-2026-10-17.md)：5轮各12次字段动作，实际tick→pump总时长中位数3775.15ms，每轮pump约3056.5–3063.6ms，占68.3%–81.8%。这是现状分解，尚未实现节省。当前`ApplicationRunner.pump()`等待context close事件250ms，外层每次tick后无条件调用。该等待同时服务事件派发，不能直接删除。[本地实现](../src/career_evidence_graph/application_worker_browser.py#L254)

只读公开源码和本地上下文；未安装依赖、启动浏览器、运行模型、连接ATS或读取个人状态。真实申请保持暂停。以下是机制研究，不是功能、性能、维护承诺或许可证法律意见。GitHub `pushed_at` 是仓库任意分支推送时间，不等于默认分支最近修改，也不能证明功能维护质量。

## 固定源码与许可证

默认分支SHA与状态取自各仓库官方API；许可证原文逐一读取。所有候选在本次快照均未归档。固定SHA限定本文结论；不随默认分支自动升级。

| 新增项目 | 固定 SHA | 根许可证原文 / SPDX | 最近 push UTC / archived |
| --- | --- | --- | --- |
| [go-rod/rod](https://github.com/go-rod/rod) | `d38c75327872c72a1cf2010dad7527f9e52eebf3` | [MIT](https://github.com/go-rod/rod/blob/d38c75327872c72a1cf2010dad7527f9e52eebf3/LICENSE) | 2026-08-11T02:18:57Z / false |
| [chromedp/chromedp](https://github.com/chromedp/chromedp) | `7862adfd3424d6f379af01f4276a87019b08c507` | [MIT](https://github.com/chromedp/chromedp/blob/7862adfd3424d6f379af01f4276a87019b08c507/LICENSE) | 2026-10-11T04:29:07Z / false |
| [ultrafunkamsterdam/nodriver](https://github.com/ultrafunkamsterdam/nodriver) | `219a60d65d82fb3d137d0c2c5b1fb285a9f837d0` | [AGPL-3.0](https://github.com/ultrafunkamsterdam/nodriver/blob/219a60d65d82fb3d137d0c2c5b1fb285a9f837d0/LICENSE.txt) | 2026-10-08T15:08:29Z / false |
| [cdpdriver/zendriver](https://github.com/cdpdriver/zendriver) | `6740d62cfa86d2245ecd4dbba7ed00ffd43977c2` | [AGPL-3.0](https://github.com/cdpdriver/zendriver/blob/6740d62cfa86d2245ecd4dbba7ed00ffd43977c2/LICENSE) | 2026-10-02T02:07:42Z / false |
| [webdriverio/webdriverio](https://github.com/webdriverio/webdriverio) | `be0d4d4fc98e9f86bd287cd319013a104982780e` | [MIT](https://github.com/webdriverio/webdriverio/blob/be0d4d4fc98e9f86bd287cd319013a104982780e/LICENSE) | 2026-10-17T14:20:07Z / false |
| [getgauge/taiko](https://github.com/getgauge/taiko) | `9f3cba6c1098d7bdc9862fb6526712ec60f7aa2c` | [MIT](https://github.com/getgauge/taiko/blob/9f3cba6c1098d7bdc9862fb6526712ec60f7aa2c/LICENSE) | 2026-10-12T09:23:01Z / false |

## 逐项采用判断

### go-rod/rod — inspired-by

Go CDP驱动。[browser.go的`waitEvent`/`eachEvent`](https://github.com/go-rod/rod/blob/d38c75327872c72a1cf2010dad7527f9e52eebf3/browser.go#L328-L388)在返回等待闭包前创建事件订阅，等候结束后取消context、恢复原先domain启用状态；[context.go](https://github.com/go-rod/rod/blob/d38c75327872c72a1cf2010dad7527f9e52eebf3/context.go#L18-L86)把总超时和主动取消附在context上。可借鉴订阅生命周期和单次消费约束，落到**优化等待与回读并保留必要结果核验**。本地保留Python/Playwright；不移植Go事件循环、不增加第二CDP owner。事件到达只提供观察事实，仍需本地授权和落值核验。

### chromedp/chromedp — inspired-by

[chromedp.go](https://github.com/chromedp/chromedp/blob/7862adfd3424d6f379af01f4276a87019b08c507/chromedp.go#L981-L1009)先检查条件，再在未完成时可取消地等待；同步事件回调明确不能阻塞。[poll.go](https://github.com/chromedp/chromedp/blob/7862adfd3424d6f379af01f4276a87019b08c507/poll.go#L120-L160)区分raf、指定间隔和DOM mutation触发，均有独立超时；[query.go](https://github.com/chromedp/chromedp/blob/7862adfd3424d6f379af01f4276a87019b08c507/query.go#L237-L259)仍使用5ms轮询，不能称所有等待均无轮询。可借鉴“状态已满足立即推进、仅缺条件才等待”的调度，与现有回调只收集事实的约束相容。Mutation只覆盖相关DOM变化；不会替代网络守卫、取消、lease或文件结果核验。拒绝直接照搬5ms作为本地默认值。

### ultrafunkamsterdam/nodriver — inspired-by；不复制实现、不替换runtime

[connection.py](https://github.com/ultrafunkamsterdam/nodriver/blob/219a60d65d82fb3d137d0c2c5b1fb285a9f837d0/nodriver/core/connection.py#L454-L484)通过WebSocket读循环按command id完成future，连接关闭或取消时使pending futures失败；事件处理与命令响应分开。[tab.py](https://github.com/ultrafunkamsterdam/nodriver/blob/219a60d65d82fb3d137d0c2c5b1fb285a9f837d0/nodriver/core/tab.py#L454-L464)的sleep仍等待指定时长，`wait(t=0.5)`再调用sleep（同文件L1283）；async不是消除固定等待的证据。借鉴请求身份和终止语义的通用设计，检查本地超时/取消后的未知状态处理。AGPL-3.0根许可证；本轮不复制代码、不引入依赖，反检测功能不纳入研究采用范围。

### cdpdriver/zendriver — inspired-by；不复制实现、不替换runtime

canonical仓库是`cdpdriver/zendriver`，不是同名推测路径。[expect.py](https://github.com/cdpdriver/zendriver/blob/6740d62cfa86d2245ecd4dbba7ed00ffd43977c2/zendriver/core/expect.py#L13-L110)在进入context时注册request/response/loading-finished监听，按request id关联，并在退出时清理。[connection.py](https://github.com/cdpdriver/zendriver/blob/6740d62cfa86d2245ecd4dbba7ed00ffd43977c2/zendriver/core/connection.py#L554-L604)的wait可等待listener idle，给出显式t时仍保证等待t；[Listener实现](https://github.com/cdpdriver/zendriver/blob/6740d62cfa86d2245ecd4dbba7ed00ffd43977c2/zendriver/core/connection.py#L854-L938)以无消息窗口标记idle，本pin实际阈值非交互0.10秒、交互0.75秒，与附近旧注释的1秒不一致。可借鉴关联与清理，不能把传输静默当作表单已保存。AGPL-3.0；不复制或引入反检测路径。

### webdriverio/webdriverio — inspired-by

[waitUntil.ts](https://github.com/webdriverio/webdriverio/blob/be0d4d4fc98e9f86bd287cd319013a104982780e/packages/webdriverio/src/commands/browser/waitUntil.ts#L51-L101)使用leading=true先检查条件，在session删除时触发AbortController，最终移除监听；[Timer.ts](https://github.com/webdriverio/webdriverio/blob/be0d4d4fc98e9f86bd287cd319013a104982780e/packages/webdriverio/src/utils/Timer.ts#L118-L158)在成功、取消、超时分别清理timer，并用绝对起点核算剩余时间。可借鉴“先检查再等待、取消即结束、总预算不因多轮重试延长”，用于**优化等待与回读并保留必要结果核验**及**验证浏览器优化的因果收益与正确性**。不引入Node/WebDriver runner。条件轮询重试不等于重发有副作用的动作。

### getgauge/taiko — inspired-by

[doActionAwaitingNavigation.js](https://github.com/getgauge/taiko/blob/9f3cba6c1098d7bdc9862fb6526712ec60f7aa2c/packages/taiko/lib/doActionAwaitingNavigation.js#L10-L88)先安装导航/网络/目标事件监听，再调用action；无导航等待时直接执行；finally清理timer、listener与promise状态。同文件L96-L141仍有waitForStart窗口与间隔等待，因此不能当成零等待方案。可借鉴按动作选择等待条件和清理完整性。Taiko的多事件/网络结束聚合不等于本地字段落值证据，不应把每次fill都升级为全页network idle等待。

## 复核现有 Playwright：reuse公共API，拒绝私有调度补丁

本地锁定`playwright==1.63.0`。官方tag固定到`8cb967b3e4199bef5ce38e1cf34df1bf79cb8a8d`，根[Apache-2.0许可证](https://github.com/microsoft/playwright-python/blob/8cb967b3e4199bef5ce38e1cf34df1bf79cb8a8d/LICENSE)。本次读取的默认分支HEAD是`3e7abc4edba4dee1e1553a02c437f5b45e22a8ed`，与安装版内部实现不同，因此实施依据必须以安装版为准。

安装文件与该tag的`_sync_base.py`、`_waiter.py`、`_browser_context.py`原始字节逐一相同。`_sync_base.py` SHA256=`f9924a820f7e74ddd71514598142363f3484c364178935eefbe80f9db8998997`；`_waiter.py` SHA256=`a3666070cfb04dce7306eefc6a9aaef9253e3c06087becfb931f16824cce2023`。

- 官方[事件指南](https://playwright.dev/python/docs/events)展示`expect_request`/`expect_popup`先进入context再触发动作，以及on/remove_listener/once。有预期结果的动作优先用现成expect API，避免晚订阅漏事件；监听器必须绑定本轮page/context身份。
- 固定版本[_sync_base.py](https://github.com/microsoft/playwright-python/blob/8cb967b3e4199bef5ce38e1cf34df1bf79cb8a8d/playwright/_impl/_sync_base.py#L98-L117)通过同步API调用交回dispatcher处理任务；普通`time.sleep`不会产生同样的事件循环让出行为。不能把Python睡眠、Playwright等待、私有greenlet switch视作可互换。
- 固定版本[_waiter.py](https://github.com/microsoft/playwright-python/blob/8cb967b3e4199bef5ce38e1cf34df1bf79cb8a8d/playwright/_impl/_waiter.py#L90-L133)中`timeout=0`关闭超时，并不是一次非阻塞pump。`context.wait_for_event("close", timeout=0)`可能无限等close；禁止把它作为优化候选。
- 复用公共expect/on/off与正值有界等待；不要导入私有`_loop`、`_dispatcher_fiber`或直接切greenlet。当前API是否可在短有界等待内可靠派发所有守卫事件，仍需隔离合成验证，源码阅读不能代替验收。

## 应补进规划的明确内容

| 现有任务 | 增补的设计和验收 |
| --- | --- |
| 优化等待与回读并保留必要结果核验 | 区分可立即推进的busy状态与无任务/等待人工的idle状态。每次只读事实回收和授权不可跳过；busy候选缩短正值有界事件等待，idle保留可取消、有上限的等待。具体毫秒值由配对测量选择，不先冻结。先采取最小同步API方案；只有证明公共API不足时再单列async迁移研究。 |
| 优化等待与回读并保留必要结果核验 | 有预期事件先订阅再动作；事件按run/page/request关联；finally清理listener/timer；deadline使用总预算。动作派发后timeout/transport unknown仍needs_recheck，不切换DOM/Cua重做。 |
| 验证浏览器优化的因果收益与正确性 | 至少五对同输入12字段、同终点tick→pump对照；固定生产模块指纹与浏览器版本，交换执行顺序，比较同版重复波动。同时覆盖idle CPU/循环次数、取消延迟、lease/heartbeat、page/context关闭、网络拦截、超时未知和事件恰在动作前后到达。不能只比tick-only或删除pump后得出的理想值。 |
| 核验原生启动并补齐 Cua 真实操作基线 | 保持独立路线。CDP/async项目的营销、源码或DOM合成数据不能补齐browser_prepare unknown后的真实Cua快照/点击耗时。 |

本研究无需成为等待优化的前置阻断；其已确认模式可直接补充当前任务。六套新runtime全部列为参考，不安装或加入依赖。研究成本按一次有界源码审查计，不按六套集成累加工期。未测得任何本地加速倍数；不据公开README更新40–75主动小时的既有交付估算。

## 来源与范围说明

新增项目的仓库状态、SHA与license元数据均使用`https://api.github.com/repos/{owner}/{repo}`、`/commits/{default_branch}`及`/git/trees/{sha}?recursive=1`；源码与许可证使用固定SHA的官方raw内容。状态值和完整pin已逐项嵌入上表，无外部临时缓存依赖。既有43项与52仓库快照只作去重上下文，未改写原目录或重算其历史状态。所有机制判断已提供固定源码链接；未核验新增项目所有依赖的许可证或兼容性，因此均不构成可直接集成结论。
