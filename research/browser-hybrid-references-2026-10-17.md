# 混合浏览器／视觉自动化参考补充 — 2026-10-17

本报告回答：新增视觉代理、独立浏览器引擎或桌面代理，是否能改善当前 DOM／Cua 路线？结论是**借鉴机制，不替换现有运行链**。这是固定源码阅读，没有安装、模型调用、浏览器试跑或实际ATS成功率测量。

## 输入与固定来源

当前合成生产循环的主要耗时来自每轮约255ms的 `pump()`；5轮12字段动作总中位3.775s，pump占68.3%–81.8%。原生Cua仅测到权限通过后 `browser_prepare` 15.02s返回unknown，没有真实点击延迟。此事实来自主工作区 `.scratch/browser-efficiency-2026-10-17/baseline-report-2026-10-17.md`，不由上游README推导。

主工作区只读上下文：`/Volumes/Codex-Workspace/live/home/zhdeng/Documents/TomorrowStar OS`。研究分支：`D_m/research/browser-hybrid-references-20261017`。截至本次GitHub官方API读取（2026-10-17），四个仓库均不在原43项目目录；SHA固定的是默认分支提交，push时间只是仓库元数据，不等于质量或持续维护承诺。

| 仓库 | 固定 SHA | 许可范围 | 维护快照 |
| --- | --- | --- | --- |
| [magnitudedev/browser-agent](https://github.com/magnitudedev/browser-agent) | `f1b587c4173d8242bdb551991de54e70c4d2faf3` | [Apache-2.0](https://github.com/magnitudedev/browser-agent/blob/f1b587c4173d8242bdb551991de54e70c4d2faf3/LICENSE)，根代码许可 | 未归档；最后 push `2026-02-08T20:51:06Z` |
| [lightpanda-io/browser](https://github.com/lightpanda-io/browser) | `2ad38773fd674d3c9cea26a263b814ee46f6ba84` | [AGPL-3.0](https://github.com/lightpanda-io/browser/blob/2ad38773fd674d3c9cea26a263b814ee46f6ba84/LICENSE)，根代码许可 | 未归档；最后 push `2026-10-17T10:07:27Z` |
| [bytebot-ai/bytebot](https://github.com/bytebot-ai/bytebot) | `3d37894ce07ef8d8b40adc7fd309ad96c2a71313` | [Apache-2.0](https://github.com/bytebot-ai/bytebot/blob/3d37894ce07ef8d8b40adc7fd309ad96c2a71313/LICENSE)，根代码许可 | 已归档；最后 push `2025-09-12T19:35:46Z` |
| [simular-ai/Agent-S](https://github.com/simular-ai/Agent-S) | `15776a8dc659658b1963816ea006f7af1978e595` | [Apache-2.0](https://github.com/simular-ai/Agent-S/blob/15776a8dc659658b1963816ea006f7af1978e595/LICENSE)，根代码许可 | 未归档；最后 push `2026-10-08T22:27:33Z` |

元数据来源分别为 [Magnitude API](https://api.github.com/repos/magnitudedev/browser-agent)、[Lightpanda API](https://api.github.com/repos/lightpanda-io/browser)、[Bytebot API](https://api.github.com/repos/bytebot-ai/bytebot)、[Agent-S API](https://api.github.com/repos/simular-ai/Agent-S)。代码根许可不自动覆盖模型权重、商业服务和依赖许可；本轮未复制代码。

## 逐项结论

### Magnitude：inspired-by；不引入代理运行时

官方API和网页canonical为 `magnitudedev/browser-agent`；固定版本的package repository仍指向 `magnitudedev/magnitude`，属于旧元数据，不应计成两个项目。[package.json](https://github.com/magnitudedev/browser-agent/blob/f1b587c4173d8242bdb551991de54e70c4d2faf3/packages/magnitude-core/package.json#L14)

可借鉴：截图与tab信息并行采集、截图记忆去重，拆分“观察／执行／核验”计量。此并行仅限独立只读操作，不允许并行发出字段写入。[browserConnector.ts](https://github.com/magnitudedev/browser-agent/blob/f1b587c4173d8242bdb551991de54e70c4d2faf3/packages/magnitude-core/src/connectors/browserConnector.ts#L122)

不能直接复用其稳定性等待：源码仍以100ms周期轮询网络，另有500ms idle及5s超时，视觉稳定又需要反复截图。网络安静、图像稳定均不证明字段保存成功；照搬可能给本地新增等待。[stability.ts](https://github.com/magnitudedev/browser-agent/blob/f1b587c4173d8242bdb551991de54e70c4d2faf3/packages/magnitude-core/src/web/stability.ts#L252)

新增成本：TypeScript/BAML、Patchright（包名伪装为playwright）、Sharp和PostHog；README要求视觉模型。PostHog实现写入本机ID并发送事件，不能按“本地浏览器”推断无数据外发。[依赖](https://github.com/magnitudedev/browser-agent/blob/f1b587c4173d8242bdb551991de54e70c4d2faf3/packages/magnitude-core/package.json#L55)、[telemetry](https://github.com/magnitudedev/browser-agent/blob/f1b587c4173d8242bdb551991de54e70c4d2faf3/packages/magnitude-core/src/telemetry/index.ts#L61)、[模型说明](https://github.com/magnitudedev/browser-agent/blob/f1b587c4173d8242bdb551991de54e70c4d2faf3/README.md)。其 `getFullPageContent` 会用div替换iframe，**不用于本地只读JD采集或身份观察**。[browserAgent.ts](https://github.com/magnitudedev/browser-agent/blob/f1b587c4173d8242bdb551991de54e70c4d2faf3/packages/magnitude-core/src/agent/browserAgent.ts#L63)。README缓存仍标in progress，不能视为成熟可复用缓存。

### Lightpanda：inspired-by；当前拒绝替换Chrome

源码可作为document生命周期和frame/shadow遍历的设计对照。`DocumentRegistry`释放后槽位会复用，裸index不能作为本地跨导航持久引用，必须加document generation／frame身份核验。[DocumentRegistry.zig](https://github.com/lightpanda-io/browser/blob/2ad38773fd674d3c9cea26a263b814ee46f6ba84/src/browser/DocumentRegistry.zig#L49)、[RenderTree.zig](https://github.com/lightpanda-io/browser/blob/2ad38773fd674d3c9cea26a263b814ee46f6ba84/src/browser/RenderTree.zig#L126)

当前固定版并非完全无渲染：已有text-only PNG/PDF与RenderTree。这仍不证明Chrome布局、截图、输入事件或Cua坐标等价。CDP/BiDi兼容也不等于全部API一致，独立引擎先不进入真实表单链。[README](https://github.com/lightpanda-io/browser/blob/2ad38773fd674d3c9cea26a263b814ee46f6ba84/README.md#L110)、[RenderTree](https://github.com/lightpanda-io/browser/blob/2ad38773fd674d3c9cea26a263b814ee46f6ba84/src/browser/RenderTree.zig)

运行成本为另一个Zig/browser二进制；基础脚本可无LLM，agent模式另有模型端点；默认发送telemetry，可用环境变量关闭。本地只读JD若确有缺口，可另立隔离兼容性实验，须保存原HTML与解析差异；不以README速度宣传给工期打折。AGPL代码仅借鉴设计，本轮不复制。[运行／telemetry](https://github.com/lightpanda-io/browser/blob/2ad38773fd674d3c9cea26a263b814ee46f6ba84/README.md#L186)

### Bytebot：inspired-by诊断；reject当前集成

它提供容器化Ubuntu桌面、独立动作服务与模型代理，**当前已归档**。Docker Compose另起PostgreSQL、desktop、agent和UI；不能当成现有macOS Cua驱动的小依赖。[部署](https://github.com/bytebot-ai/bytebot/blob/3d37894ce07ef8d8b40adc7fd309ad96c2a71313/docker/docker-compose.yml)、[说明](https://github.com/bytebot-ai/bytebot/blob/3d37894ce07ef8d8b40adc7fd309ad96c2a71313/README.md#L112)

可借鉴输入捕获时把截图和动作关联成同一条诊断事件，供人工检查“观察时页面”和“操作落点”。此代码把图像写入消息，真实资料必须经本地既有隐私和保留规则，不能直接接通。[input-capture.service.ts](https://github.com/bytebot-ai/bytebot/blob/3d37894ce07ef8d8b40adc7fd309ad96c2a71313/packages/bytebot-agent/src/agent/input-capture.service.ts#L60)

服务的application操作含fire-and-forget进程／窗口动作；返回不证明窗口已就绪。动作内部也有固定延迟，不能用它解决本地pump证据。当前只参考动作schema与时序诊断，不迁移Linux桌面或后台agent。[computer-use.service.ts](https://github.com/bytebot-ai/bytebot/blob/3d37894ce07ef8d8b40adc7fd309ad96c2a71313/packages/bytebotd/src/computer-use/computer-use.service.ts#L249)

### Agent-S：inspired-by能力分层；reject当前完整接入

Agent-S3把任务worker和视觉grounding分开，值得在计量中区分规划、定位、动作与核验；但这不是现有确定性DOM路径必须增加的模型步骤。[agent_s.py](https://github.com/simular-ai/Agent-S/blob/15776a8dc659658b1963816ea006f7af1978e595/gui_agents/s3/agents/agent_s.py#L54)

grounding每次用当前截图和指令调用模型，并解析坐标；坐标本身不证明是原字段。需保留本地owner/page/document身份、动作前核验和动作后实际值检查。上游独立grounding模型／端点、OCR和多provider SDK增加推理与数据路径；其根Apache许可不许可模型权重。[grounding.py](https://github.com/simular-ai/Agent-S/blob/15776a8dc659658b1963816ea006f7af1978e595/gui_agents/s3/agents/grounding.py#L229)、[requirements](https://github.com/simular-ai/Agent-S/blob/15776a8dc659658b1963816ea006f7af1978e595/requirements.txt)、[模型配置](https://github.com/simular-ai/Agent-S/blob/15776a8dc659658b1963816ea006f7af1978e595/README.md#L157)。不把README研究基准或商业Sai成绩转述为本地ATS效率。

## 与既有参考的关系

此前固定源码报告 `research/tomorrowstar-open-source-reuse-analysis-2026-10-17.md` 已读browser-use、Stagehand；**本轮未重新核验它们的HEAD**。沿用该固定结论：browser-use `ccd22fef47a1a36e0c4596fef5db73a5117b9d06` 有独立BrowserSession／模型／telemetry和Pydantic pin差异；Stagehand v4增加独立运行时和AX／URL云缓存数据路径。四个新项目没有推翻“保留现有Playwright，窄适配”的选择。

## 回填规划的具体建议

| 现有任务 | 本次增量 | 不新增的依赖 |
| --- | --- | --- |
| 优化等待与回读并保留必要结果核验 | busy可推进路径与idle事件泵分开；保留取消、守卫、owner保活；至少五对同输入完整主循环验证；避免移植Magnitude固定idle | 不等待视觉框架选型 |
| 复用DOM解析并建立可失效的控件引用 | refs绑定owner、page、frame、document generation、schema/options版本；裸index和截图坐标不作为稳定授权 | 不引入新引擎 |
| 减少Cua路径重复绑定与快照开销 | 待原生启动可用后再测；可比较截图/tab独立只读并发，动作与其依据快照绑定 | 不以模型grounding替代启动诊断 |
| 接通DOM主路径与有界Cua兜底 | 已支持且核验唯一的DOM控件优先；只在派发前确定不支持时转Cua；派发后unknown先记needs_recheck，禁止换路重做 | 不引入完整桌面agent |
| 核验并补充确需浏览器的只读JD获取 | Chrome/现有Playwright先解决真实缺口；Lightpanda仅条件实验候选 | 不自动迁移申请引擎 |

这四项是源码机制参考，不是已实现优化或新产品承诺。排序保持：已测pump → 原生Cua可用性 → 窄DOM控件 → 必要refs／快照复用 → 配对验证。真实申请保持暂停。
