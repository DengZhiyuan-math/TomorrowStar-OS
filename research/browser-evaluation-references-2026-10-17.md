# 浏览器评估与可复现性参考补充 — 2026-10-17

本报告补充五个此前清单未包含的项目；BrowserGym 是已有参考，不重复计入新增数量。只读取官方仓库和固定版本源文件，没有安装评测环境、执行浏览器、调用模型或接触真实申请。本轮没有复制上游代码。

## 结论与本地依据

优先借鉴 AgentLab 的分段时间戳／版本清单、WebArena-Verified 的确定性结果分类，以及 WorkArena 的独立结果核验。保持本仓库 pytest 与合成页面，不引入整套评测运行时。

[本地真实主循环基线](../.scratch/browser-efficiency-2026-10-17/baseline-report-2026-10-17.md)：五轮各十二次已核验字段动作，中位数3775.15ms；每轮 pump 约3.06秒，占总时长68.3%–81.8%。这是优化前分解。终点仍为 filling / fields_verified_before_upload，不包括附件、ready_for_review 或真实提交。公开基准的成功率、模型延迟、录制回放均不能替代本地至少五对同输入、同终点的因果对照；真实 Cua 快照／点击延迟仍未知。

## 固定来源与许可证

API 查询于2026-10-17核验规范仓库名与 archived 字段，以下五项均未归档。固定 SHA 以官方 GitHub commit API 获取，许可证按实际根文件读取；AgentLab／WorkArena 的 GitHub 自动识别为 Other，根文件明确指向 Apache-2.0。

| 规范仓库 | 固定 SHA | archived | 源码根许可证 |
| --- | --- | --- | --- |
| [ServiceNow/AgentLab](https://github.com/ServiceNow/AgentLab) | `8488c564eea0525aaff5dea189bb03a9b529546e` | false | [Apache-2.0，根 LICENSE](https://github.com/ServiceNow/AgentLab/blob/8488c564eea0525aaff5dea189bb03a9b529546e/LICENSE) |
| [ServiceNow/WorkArena](https://github.com/ServiceNow/WorkArena) | `e885130962f61fb64ac305497996a46cfc7d18f0` | false | [Apache-2.0，根 LICENSE](https://github.com/ServiceNow/WorkArena/blob/e885130962f61fb64ac305497996a46cfc7d18f0/LICENSE) |
| [web-arena-x/webarena](https://github.com/web-arena-x/webarena) | `dce04686a56253aefba7b18a4fa0937cf1dc987b` | false | [Apache-2.0，根 LICENSE](https://github.com/web-arena-x/webarena/blob/dce04686a56253aefba7b18a4fa0937cf1dc987b/LICENSE) |
| [ServiceNow/webarena-verified](https://github.com/ServiceNow/webarena-verified) | `6473f72db5dcefc97b5725b59e734504edc28a21` | false | [Apache-2.0，根 LICENSE](https://github.com/ServiceNow/webarena-verified/blob/6473f72db5dcefc97b5725b59e734504edc28a21/LICENSE) |
| [xlang-ai/OSWorld](https://github.com/xlang-ai/OSWorld) | `b138d348256078fa634fc3b73567a7337c793e6b` | false | [Apache-2.0，根 LICENSE](https://github.com/xlang-ai/OSWorld/blob/b138d348256078fa634fc3b73567a7337c793e6b/LICENSE) |

范围：这里核验的是仓库根代码许可，未据此授予第三方网站、VM镜像、演示视频、模型权重或外部数据集的权利。各树仅找到根 LICENSE，没有逐资产权利清单；任何实际复制资产前仍需单独核验。WorkArena 的实例获取另有条款与审批，不能由根源码许可推断可自由部署实例。[官方实例获取说明](https://github.com/ServiceNow/WorkArena/blob/e885130962f61fb64ac305497996a46cfc7d18f0/README.md#L35)

## 可借鉴机制与边界

### AgentLab — adapt：计量与复现实验记录

[StepTimestamps](https://github.com/ServiceNow/AgentLab/blob/8488c564eea0525aaff5dea189bb03a9b529546e/src/agentlab/experiments/loop.py#L139)区分 agent、环境、动作、加载等待、验证和观察；[make_stats](https://github.com/ServiceNow/AgentLab/blob/8488c564eea0525aaff5dea189bb03a9b529546e/src/agentlab/experiments/loop.py#L247)分别计算 step_elapsed 与 agent_elapsed。本地沿用已有跨度，补明确的 busy/idle pump、取消响应和 CPU 指标，不把嵌套跨度相加。上游使用 wall clock；本地耗时应继续使用单调时钟。

[get_reproducibility_info / assert_compatible](https://github.com/ServiceNow/AgentLab/blob/8488c564eea0525aaff5dea189bb03a9b529546e/src/agentlab/experiments/reproducibility_util.py#L180)记录版本、Git修改、平台和Python／Playwright，并检验兼容性；借鉴不可混合版本的比较门槛，继续保存本地源码哈希。[summarize](https://github.com/ServiceNow/AgentLab/blob/8488c564eea0525aaff5dea189bb03a9b529546e/src/agentlab/analyze/inspect_results.py#L242)将 n_err、终止／截断和reward分开；“完成”可包含出错，不能直接视作成功。

回放不是新推理：[RecordedChatModel](https://github.com/ServiceNow/AgentLab/blob/8488c564eea0525aaff5dea189bb03a9b529546e/src/agentlab/agents/generic_agent/reproducibility_agent.py#L43)复用旧响应，且默认模拟延迟1秒。其默认延迟不得纳入本地调度收益；借鉴输入／观察差异报告，拒绝将这种回放称作真实模型或浏览器性能证明。整套AgentLab运行时本轮不引入。

### WorkArena — inspired-by：限定字段与独立结果

[form.validate](https://github.com/ServiceNow/WorkArena/blob/e885130962f61fb64ac305497996a46cfc7d18f0/src/browsergym/workarena/tasks/form.py#L827)检查越界字段变化，再查询实际创建记录并核对任务字段；无记录与错误记录有不同终止语义。可借鉴为合成夹具：目标字段正确、非目标字段未变、派发计数和本地服务接收状态分别核验。其代码自身注明不能覆盖所有额外字段；这不是完整无副作用证明。

这里的任务成功通常包含提交后数据库记录。本地验收停在提交前，必须重写判据，不能照搬其提交、重试、清库或等待十秒的实现。实例条款、服务端状态和环境规模不适合当前微基准；不运行其真实ServiceNow环境。

### WebArena — inspired-by：任务结果独立于动作返回

[评估器与组合器](https://github.com/web-arena-x/webarena/blob/dce04686a56253aefba7b18a4fa0937cf1dc987b/evaluation_harness/evaluators.py#L25)按任务配置区分答案、URL和页面内容等结果，再组合判据。借鉴配置化期望与执行器分离；不采纳其全部匹配语义作为简历／字段真值。

[HTMLContentEvaluator 的页面访问](https://github.com/web-arena-x/webarena/blob/dce04686a56253aefba7b18a4fa0937cf1dc987b/evaluation_harness/evaluators.py#L270)会为验证导航，并有固定3秒sleep；还可执行配置中的JS／辅助函数。因此不能用于未知结果的原页面恢复，不能作为消除固定等待的范例。保留本地只读独立核验；不启动Docker网站或导入任意评估配置代码。

### WebArena-Verified — adapt：结构化记录和确定性分类

[NetworkEventEvaluator](https://github.com/ServiceNow/webarena-verified/blob/6473f72db5dcefc97b5725b59e734504edc28a21/src/webarena_verified/core/evaluation/evaluators/network_event_evaluator.py#L25)从记录中筛选URL、方法、事件及请求数据，再规范化、比较结果。[去掉LLM judge](https://github.com/ServiceNow/webarena-verified/blob/6473f72db5dcefc97b5725b59e734504edc28a21/docs/evaluation/removing_llm_based_evaluation.md#L1)说明其改用确定性的类型化匹配。[结果格式](https://github.com/ServiceNow/webarena-verified/blob/6473f72db5dcefc97b5725b59e734504edc28a21/docs/evaluation/evaluation_results.md#L119)区分 success、failure、partial_match、error，并记录版本与校验信息。借鉴本地合成动作的结构化结果与只读离线oracle，无需增加模型judge。

[网络记录的限制](https://github.com/ServiceNow/webarena-verified/blob/6473f72db5dcefc97b5725b59e734504edc28a21/docs/evaluation/network_event_based_evaluation.md#L183)明确网络轨迹不能证明视觉或客户端状态。对本地字段必须同时核对DOM落地值；请求已发出／HTTP成功均不是字段正确或提交成功。轨迹重评只能验证保存的证据，不测新的端到端时延。仅记录自有合成端点的必要字段，不采集真实会话HAR。

### OSWorld — inspired-by：独立getter/metric；reject现场动作回放

[DesktopEnv.evaluate](https://github.com/xlang-ai/OSWorld/blob/b138d348256078fa634fc3b73567a7337c793e6b/desktop_env/desktop_env.py#L458)分离结果getter、期望getter和metric，并支持多项判据、文件缺失及不可完成任务。借鉴“失败原因不抹掉”和多层证据，避免只按动作无异常判成功。

同一评估器可先执行postconfig，[get_replay](https://github.com/xlang-ai/OSWorld/blob/b138d348256078fa634fc3b73567a7337c793e6b/desktop_env/evaluators/getters/replay.py#L4)甚至通过controller实际执行键盘动作；不具备默认只读属性。不能把它用作未知动作后的安全回读，也不能在原页面回放。整套VM与桌面环境不引入；该源码审阅不构成原生Cua可用性证据。

## 与已有 BrowserGym 的关系

[此前固定版本研究](tomorrowstar-open-source-reuse-analysis-2026-10-17.md#8-深读browsergym)已核验 BrowserGym `e71419aef5759a11cb7896a26c36e5f7e92d82b2`：action／observation／task.validate分离，根Apache-2.0；validate可能导航，open-ended done不是success。新增研究提供版本审计、回放差异和网络结果证据，不能变成第二套执行器。上述 BrowserGym 版本与许可证沿用已有固定报告，本轮未重新获取该仓库。没有新增第六个项目。

## 纳入规划的最小增量

| 本地任务 | 具体补充 | 是否阻塞当前等待优化 |
| --- | --- | --- |
| 优化等待与回读并保留必要结果核验 | 记录busy/idle等待、取消延迟、CPU占用；保持事件泵、guard、owner保活；禁止直接pump=0忙轮询 | 否，已有基线足以开始窄方案 |
| 验证浏览器优化的因果收益与正确性 | 至少五对同输入／同终点，候选与对照交错；固定源码和浏览器版本；收益超过同版重复噪声；保留每轮数值和所有失败，比较完整tick→pump而非tick-only | 作为本票研究产出进入验收，不增加运行时依赖 |
| 验证浏览器优化的因果收益与正确性 | 目标／非目标DOM值、动作派发和合成请求计数独立断言；取消、迟到事件、unknown不重发、idle不忙转；区分失败、部分完成、评估错误 | 同上 |
| 核验原生启动并补齐Cua真实操作基线 | 记录真实RPC阶段；保持unknown暂停；合成替身与历史回放另列 | 否，与DOM路线并行 |

研究本身不支持追加“运行全部公共benchmark”的开发任务。若未来需要大规模跨网站成功率评估，应另立契约、资源与数据许可，不计入当前等待优化验收或当前版本工期。当前仅补文档和验收设计，没有已实现提速的结论。
