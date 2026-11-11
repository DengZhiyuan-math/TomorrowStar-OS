# 交付 DOM 优先的受控浏览器效率改进

> 当前规范与唯一执行计划（2026-10-20）：[产品规范](../../docs/single-job-flow.md) · [开发计划](../../docs/development-plan.md) · [系统审计](../../docs/system-audit-2026-10-20.md)。
> 已有DOM/Cua快速路径和成对测量继续复用，平台/控件支持名单不再是运行准入。通用浏览器fallback、登录复用、人工编辑一次继续由单岗18/37承接；09保留用户实际体验判断，不把旧审批体验固化到新产品。 本次仅重规划，未改Status/Assignee、未执行真实申请。

Label: wayfinder:map
Status: open
Created: 2026-10-17

## Destination

交付现有受控浏览器的DOM优先操作、可靠解析与可测量的效率改进。常见控件尽量走原生浏览器能力，Cua只承担确需它的已支持动作；按同输入、同终点证明收益，保留身份、授权、结果回读和未知停止。

## Notes

2026-10-20：全部开放票现按[并行执行分组](../open-ticket-parallel-plan-2026-10-20/README.md)组织；规范子票身份、原领取、依赖及验收保持，真实申请继续暂停。


- 2026-10-18 最新工程结论：07组合及08独立安装合成复验已结案；必要UI修复后unknown停止结论跨App冷重开保留，原页/intent无重放。见[最终报告](../browser-efficiency-release-2026-10-18/branches-authorized/README.md)与08独立终审。09人工体验接受保持延期，真实审核/申请暂停；以下较早部分进度保留为历史。

- 用户在材料准备版建图后明确指出浏览器自动化仍有用，当前computer use慢、效率低；本图把这条能力路线补入[当前交付总导航](../tomorrowstar-delivery-2026-10-17/README.md)。这不代表恢复旧真实申请或启用自动投递。
- **执行扩展**：本图覆盖性能诊断、必要实现、隔离对照和安装验收。初始建图轮全部新票open/none、未执行；后续按用户明确指令领取frontier并遵守Wayfinder会话规则。
- 2026-10-17 用户授权先执行隔离合成性能基线、确定优化顺序和合并工期；[基线报告](baseline-report-2026-10-17.md)已完成。初始轮仅基线票关闭；后续执行结论见下方索引。真实Cua操作基线有明确缺口，新建后继票承接，旧申请仍暂停。
- 当前普通字段、select及已支持附件主要已走Playwright，不能把“全改Playwright”重复开发。非可编辑combobox在live+Cua情况下选Cua路线，源码见[动作选择](../../src/career_evidence_graph/application_worker_browser.py#L1246)。
- [CuaDriver.fill](../../src/career_evidence_graph/cua_driver.py#L1131)正常driver-owned路径包括绑定state、两份语义快照和两次click；字段执行期间还有多次DOM全观察。它们是待测成本，不是已确认的唯一慢因；已选File重复摘要也应纳入基线。
- 复用同一owner/browser/page、现有Playwright、CuaDriver和MeasurementLog。优先标准接口与已安装依赖，不引入browser-use/Stagehand等第二套执行runtime。
- DOM主路径是工程建议，必须逐控件证明能力和事件／回读语义。派发前选路线；动作unknown后不得切路线重做。截图、模型或坐标代理不会被隐式扩权。
- 实现前需有实际基线；沿用[测量口径](../application-worker-next-stage/issues/05-measurement-contract.md)及[既有效率边界](../application-worker-next-stage/issues/06-efficiency-contract.md)的至少五对同输入对照和收益超过波动要求。原票“当轮仅缓存正确性”是历史范围，本图承接本次新性能需求，不回写其历史结论。
- 解析快照／refs／摘要的复用与答案授权、材料批准、动作许可分别处理。文档、控件、选项、文件、owner或输入变化时按对应契约失效，不能因缓存命中跳过核验。
- 只读浏览器JD取源是可选适配：只有明确HTTP缺口与完整来源证据才接入；不能把受保护页面、登录墙或摘要变成完整JD。
- 与[材料准备版](../gmail-resume-preparation-2026-10-17/map.md)并行，独立验收。材料入口默认不启动填写器；新浏览器线不成为所有岗位材料生成的硬前置。
- 旧[原页观察](../single-job-application-flow-2026-10-16/issues/24-owned-page-observation.md)、[请求诊断](../single-job-application-flow-2026-10-16/issues/25-request-diagnostics-readback.md)、[Chrome启动调查](../single-job-application-flow-2026-10-16/issues/26-native-chrome-startup-crash.md)与其他旧票保留原状态和唯一根因归属。只对实际影响新路径的结果添加精确依赖，不复制整组ATS前置。
- 计量记录工具/RPC/快照/扫描/等待/回读，机器与人类等待分开；冷暖、失败／取消及unknown保留。不给未经实测的“快几倍”承诺。两线去重后的[整体预算](../../research/tomorrowstar-combined-delivery-estimate-2026-10-17.md)为45–80主动小时，风险情景总计65–105，含基线及本次参考研究预算，不与原材料版25–45相加。
- 沿用[Wayfinder](/Users/zhdeng/.agents/skills/wayfinder/SKILL.md)及[开发约定](../../CONVENTIONS.md)，状态／领取／依赖使用本地tracker；见[执行导航](README.md)。真实个人内容、截图、答案、文件与trace留私有，遵守[数据边界](../../docs/data-boundaries.md)。

- 2026-10-17补充规划：将固定等待优化细化为忙闲调度、事件分发、单变量成对验证；另开三项公开源码研究，比较事件/CDP、语义视觉和独立评测。研究结果只落到现有票，研究不等于安装或实现，不阻塞已可实施的等待优化。详细资料见[研究导航](../../research/browser-automation-reference-supplement-2026-10-17.md)。

## Decisions so far

- 2026-10-18 原DOM合成PDF已按用户明确授权完成测试确认；修复仅合成子进程CLI身份遗漏，后继完整离线2555通过，安装三字段DOM与原页接管通过。App冷重开保留原页与动作且无重放，但新后台控制连接未知。manual/unknown的新PDF已准备，未确认、未准备批次；08保持open，人工接受仍待审。见[后继安装报告](../browser-efficiency-release-2026-10-18/continuation-authorized/README.md)。

- [定位浏览器控制的分段耗时与重复调用](issues/01-browser-performance-baseline.md)：生产pump固定等待是当前合成路径主要成本；原生启动15秒unknown，真实Cua操作补测独立承接。

- [研究事件等待与 CDP 控制的可复用机制](issues/12-event-wait-references.md)：先订阅后触发、总deadline与清理可借鉴；保留已装Playwright公共API，不引入新runtime。

- [研究语义视觉代理与替代浏览器的适用边界](issues/13-hybrid-agent-references.md)：参考document generation与观察分段；新增视觉框架／引擎不进入本轮执行链。

- [研究浏览器评测与独立结果校验机制](issues/14-evaluation-references.md)：借鉴独立validator、版本与成本记录；拒绝会改变原页的现场验证／回放。

- [取得隔离原生Cua的真实操作证据](issues/11-native-cua-baseline.md)：全新归属runtime的5个独立页面完成真实helper绑定、语义快照、dom_event点击和回读，分段计量及清理通过；不代表trusted鼠标、完整worker或历史unknown已解决。

- [验证并复用一个有价值的重复观察](issues/02-dom-observation-references.md)：正常完整流程未达预设稳健收益门槛，保留生命周期及压力证据，不引入生产缓存。

- [减少一个昂贵的Cua观察步骤](issues/04-cua-binding-snapshot-overhead.md)：真实5对query候选收益未超波动，候选归档并撤销，当前驱动与基线字节一致。

- [补齐一个确有HTTP缺口的只读JD来源](issues/10-readonly-browser-job-source.md)：当前无具体HTTP缺口URL，条件性不新增适配；出现确切缺口即可重开做有界只读探测。

- [让一个不可编辑下拉框走DOM完成选择](issues/03-dom-first-controls.md)：显式关联listbox的精确选择、动态许可/原节点与独立回读通过，最终默认离线2516通过；安装与体验另验。

- [让字段流程按忙闲状态调度](issues/05-bounded-waits-readback.md)：已核验进度后5ms、idle/paused/fault250ms；完整5对收益超波动，暂停及最终回归通过。

- [在派发前选择已支持的执行路线](issues/06-hybrid-browser-routing.md)：DOM/既有Cua/人工预检与跨批次旧动作守卫通过，合成入口及完整2554离线/86浏览器验证；原生组合和安装另验。

- [验证已选浏览器候选的组合收益](issues/07-paired-efficiency-regression.md)：245文件冻结候选、五对真实helper合成组合及六个诊断通过，独立复核30字段及清理；完整字段中位2934.44→729.53ms，安装和体验另验。

## Not yet specified

- 实测可能出现尚未指认的启动／系统／传输组合瓶颈；有具体事件后再建最小修复，而非预设所有慢都来自Cua。
- 同一候选的实际收益与适用页面范围；由成对结果决定保留或撤销，不先承诺全平台。
- 新真实页面可能暴露尚未出现的交互变体；看到确切控件与问题再补适配，不预先制造平台大全。

## Out of scope

- 本轮恢复旧申请、真实字段写入／上传、自动最终Submit、批量投递、联系人消息、改变隐私或资格答案。
- 删除安全检查、把回执当保存成功、unknown后盲重试、静默重开原页、重传附件或延长owner权限。
- 默认跨iframe/shadow全覆盖、任意视觉点击、新模型操作循环、多worker／分布式队列和新浏览器运行时；它们属于另行确定的扩展。
- 把普通HTTP可完整读取的JD全部改为浏览器获取，或复制日常浏览器凭据。

