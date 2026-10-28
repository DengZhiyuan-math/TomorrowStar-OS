# 浏览器自动化补充参考与优化规划

日期：2026-10-17。范围：公开仓库、固定源码与许可证研究，以及现有Wayfinder规划更新。没有安装依赖、运行候选浏览器／模型、实施优化或恢复真实申请。

## 当前结论

继续使用现有Playwright和受控Cua。先修合成基线已定位的固定等待，再逐控件优化。新项目提供可借鉴机制，不按项目数量增加执行框架。

[已测基线](../.scratch/browser-efficiency-2026-10-17/baseline-report-2026-10-17.md)中，12字段生产循环中位3.775秒，每轮pump累计约3.06秒，占68.3%–81.8%。这是优化优先级依据，不是已取得的提速。原生Cua启动15.02秒unknown，真实快照／点击成本仍缺。

## 新增参考范围

已有[43项历史目录](open-source-job-application-browser-tools-2026-10-17.md)和[固定源码复用分析](tomorrowstar-open-source-reuse-analysis-2026-10-17.md)保留。本轮新增核验15个不同仓库，另对Playwright、browser-use、Stagehand、BrowserGym作有明确版本边界的对照；不把重命名、bindings或复核项重复计数，也不将所有候选统称为已选开源依赖。

| 组别 | 新增仓库 | 具体研究用途 | 详细来源与取舍 |
| --- | --- | --- | --- |
| 事件等待与直接控制 | go-rod/rod、chromedp/chromedp、ultrafunkamsterdam/nodriver、cdpdriver/zendriver、webdriverio/webdriverio、getgauge/taiko | 先订阅后触发、取消与deadline、busy/idle调度、精确定位 | [6项固定源码报告](browser-event-waits-2026-10-17.md) |
| 语义／视觉代理与替代引擎 | magnitudedev/browser-agent、lightpanda-io/browser、bytebot-ai/bytebot、simular-ai/Agent-S | 观察与执行分离、页面稳定信号、模型轮次、运行时／渲染差异 | [4项固定源码报告](browser-hybrid-references-2026-10-17.md) |
| 评测与独立校验 | ServiceNow/AgentLab、ServiceNow/WorkArena、web-arena-x/webarena、ServiceNow/webarena-verified、xlang-ai/OSWorld | 任务成功validator、重放与失败分类、机器成本、环境／数据版本 | [5项固定源码报告](browser-evaluation-references-2026-10-17.md) |

每份报告记录canonical仓库、完整SHA、许可证原文、源码定位、维护状态及本地适用限制。主目录不批量改写旧52份仓库快照；当前三份报告承载本次新增证据。

## 如何进入现有任务

| 顺序 | 现有任务 | 本次补充的具体要求 |
| --- | --- | --- |
| P0 | [优化等待与回读并保留必要结果核验](../.scratch/browser-efficiency-2026-10-17/issues/05-bounded-waits-readback.md) | busy/idle区别；保持同步Playwright事件分发；先做单变量调度改动；至少5对完整生产循环；监测CPU和停止响应 |
| 并行P0 | [核验原生启动并补齐 Cua 真实操作基线](../.scratch/browser-efficiency-2026-10-17/issues/11-native-cua-baseline.md) | 先取得真实原生操作数据，再决定快照成本优化；源码研究不替代原生就绪 |
| P1 | [为已支持控件实现 DOM 优先的快速操作](../.scratch/browser-efficiency-2026-10-17/issues/03-dom-first-controls.md) | 借鉴actionability、精确locator及事件顺序；复用当前字段身份，不等待通用refs体系 |
| P1 | [减少 Cua 路径的重复绑定与快照开销](../.scratch/browser-efficiency-2026-10-17/issues/04-cua-binding-snapshot-overhead.md)／[接通 DOM 主路径与有界 Cua 兜底](../.scratch/browser-efficiency-2026-10-17/issues/06-hybrid-browser-routing.md) | 观察／执行分开；派发前确定路线；不自动引入视觉模型、云session或第二引擎 |
| P1 | [验证浏览器优化的因果收益与正确性](../.scratch/browser-efficiency-2026-10-17/issues/07-paired-efficiency-regression.md) | 独立结果validator、失败计入、AB/BA顺序和成本拆分；公开榜单不代表本机性能 |
| P2 | [复用 DOM 解析并建立可失效的控件引用](../.scratch/browser-efficiency-2026-10-17/issues/02-dom-observation-references.md) | document/frame/选项变化失效；只有实测扫描瓶颈才增建缓存，不重复实现现有观察 |

三项研究只提供信息，不增加等待优化的硬前置。原生就绪补测与窄DOM候选可并行；共享模块改动必须协调。

## 明确不从上游直接继承的行为

- 不把某个框架仍有的固定sleep／idle窗口照搬为“事件驱动优化”。Playwright `wait_for_event(timeout=0)`是禁用超时，不是非阻塞调用；`wait_for_timeout(0)`也须实测事件分发和CPU行为。
- 不通过更换浏览器引擎推断Chrome渲染、控件、File和Cua兼容性；也不把视觉代理README的速度或覆盖声明当作本地结果。
- 不继承上游自动登录、自动提交、反检测、未知后重试或新session接管。模型轮次、数据外发与runtime依赖必须明示。
- 根代码许可证不自动覆盖数据集、网站素材、容器镜像、模型和子目录依赖；当前研究没有复制代码，未来adapt必须记录上游pin、许可证和本地差异。

## 本轮筛选结果

- 优先复用已安装Playwright公共事件API，借鉴Rod／chromedp的订阅与取消模式、WebdriverIO／Taiko的总预算与清理；nodriver／zendriver也有固定等待，不能作为直接加速替代。
- Magnitude也有100ms轮询／500ms idle；Lightpanda的文档槽位会复用，裸index不能当稳定refs。Bytebot已归档，Agent-S需要额外grounding模型；这些信息只改变参考优先级，不增加本轮依赖。
- AgentLab的计量、WorkArena的目标／非目标字段断言、WebArena-Verified的确定性分类进入合成验收设计。WebArena／OSWorld部分验证与回放会改变环境，不用于未知结果后的现场回读。

以上判断与来源均在三份固定源码报告；当前没有上游运行性能或真实ATS成功率的实验结论。

## 任务与工期

浏览器地图增为14张票，其中3张新增公开源码研究；材料线16张，合计30张。研究完成状态以各票resolution为准，不能代表实现、安装或用户验收完成。

[合并预算](tomorrowstar-combined-delivery-estimate-2026-10-17.md)增加2–4主动小时的参考核验与回填预算；整体从40–75取整更新为45–80小时，风险情景总计65–105小时。包括已完成基线和本轮研究，不是精确剩余时长，也不是6.1 Sol Fast实测生产率。事件等待研究报告中的40–75小时是其调研输入的旧预算；本导航与合并估算文件记录增加研究成本后的修订。若新增运行时／视觉模型／完整benchmark部署，另行估算。

## 研究保全

三项研究票已完成并关闭；工程实现票保持原状态。三项研究均在独立的`D_m/research/*-20261017`本地分支完成；主工作区没有切换分支。报告复制回当前research目录，commit指针与领取归属保存在对应研究票。未推送、未创建PR，未提交主工作区既有更改。

[当前交付总导航](../.scratch/tomorrowstar-delivery-2026-10-17/README.md) · [浏览器地图](../.scratch/browser-efficiency-2026-10-17/map.md) · [完整任务与依赖](../.scratch/browser-efficiency-2026-10-17/README.md)
