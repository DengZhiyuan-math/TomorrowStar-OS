# 申请 worker 下一阶段：稳定性、普适性与效率决策地图

> 当前规范与唯一执行计划（2026-10-20）：[产品规范](../../docs/single-job-flow.md) · [开发计划](../../docs/development-plan.md) · [系统审计](../../docs/system-audit-2026-10-20.md)。
> 旧稳定性、普适性和效率决策保留其当时范围。当前产品优先单岗闭环；未知结果先识别再询问、一次继续、通用浏览器和结果观察以现行规范为准，原覆盖矩阵和隐私/逐请求准入不再是日常门槛。 本次仅重规划，未改Status/Assignee、未执行真实申请。

Label: wayfinder:map
Status: closed
Created: 2026-10-11

## Destination

形成下一阶段可交付开发的规格、实施顺序与验收标准：在保留人工最终 Submit、原申请记录和确认答案范围的前提下，提高 worker 的故障恢复能力、通用表单覆盖和处理效率。
地图完成意味着开发前决策已齐备，不意味着代码已实现或真实申请已通过。

## Notes

- [2026-10-13 后继队列整理](../open-ticket-audit-2026-10-13-followup/README.md)链接当前开放票与未验收边界。下列日期记录保留当时背景；票据状态和 resolution comment 决定当前状态。
- 用户在 2026-10-11 确认优先顺序：稳定性 → 普适性 → 效率。效率基线须在改动前采集；优化实施仍排在后面。
- 2026-10-11 的 wayfinder 规划轮不开发运行代码、不重启招聘浏览器、不生成新简历、不上传个人资料。2026-10-12 用户另行授权 CuaDriver 最小 worker 接入与合成回归；交付见[集成验收](../cua-worker-integration-2026-10-12/README.md)，没有启动真实申请。
- 沿用[首版决策地图](../independent-application-worker/map.md)已确认的范围答案、仅暂停受影响岗位、符合条件的等待岗位自动恢复、批次暂停需明确继续、逐岗位简历复核与人工 Submit。默认方案由系统提出，用户只修改例外。
- 新阶段复用现有 worker、答案 helper、原生控件、PDF 内容绑定和原记录同步。不先增加平台队列、数据库、向量库或代理框架。
- 用户在 2026-10-12 明确补充混合方向：复用 Playwright 与现成 Codex computer use/ChatGPT 浏览器能力，减少陌生界面对专属脚本的依赖。支持等级与执行方式分开；工具接入和效率证据见[通用覆盖推荐草案](assets/form-coverage-proposal.md)，当时尚未定案；后续已由[确定通用表单支持等级与首批覆盖范围](issues/04-coverage-contract.md)解决，见下方索引。
- 用户进一步提出直接接入 CuaDriver。[原生 MCP 合成接入验证](../cua-direct-probe-2026-10-12/README.md)已完成；推荐驱动直接进入现有 worker 的执行边界，Hermes 仅作环境参考，不建立第二套 agent runtime。完整支持规格仍由通用覆盖票决定。
- 用户随后授权常驻隐藏与原页人工交接；见[后台窗口实现与验收](../cua-worker-hidden-2026-10-12/README.md)。工作页默认最小化，人工复核恢复原页和附件；首次驱动初始化的空白窗口仍为明确边界。
- 2026-10-13 用户继续授权消除首次初始化空白窗口。见[无窗口启动与原生验收](../cua-worker-windowless-startup-2026-10-13/README.md)：全新 Chrome 从启动起隐藏，Cua 只精确 attach；私有会话刷新保留浏览器，人工复核显示原页和附件。当时完整覆盖票仍为 open；其后规划决策已结案，真实覆盖验收仍独立。
- 2026-10-13 已按授权[更新本机应用](../cua-app-update-2026-10-13/README.md)，下次从应用启动 worker 默认采用后台 Cua。原应用备份、现有状态与附件保留，没有重启应用、worker 或浏览器。截图中的两次崩溃分别保留已匹配与尚未确认触发来源的结论。
- 每个 HITL 票使用 [grilling](/Volumes/Codex-Workspace/live/home/zhdeng/.codex/skills/grilling/SKILL.md) 和 [domain-modeling](/Volumes/Codex-Workspace/live/home/zhdeng/.codex/skills/domain-modeling/SKILL.md)，一次讨论一个问题。不重复询问已确认偏好。
- 研究使用 [research](/Users/zhdeng/.agents/skills/research/SKILL.md)，仅用官方文档、规范和源码；研究分支采用 `D_m/research/` 前缀。研究建议不是 HITL 决策。
- 实现验收和真实试点分开。合成回归、真实草稿保存、人工提交、接收回执不得合并计数。
- 个人记录、答案值、简历、认证与真实 trace 保持私有。本地图不改变职业图、Grill-Me 或 Skill 评分的主里程碑。
- 本地 tracker 规则及 frontier 查询见[规划入口](README.md#wayfinding-operations)。研究、票与地图的状态是唯一状态来源；阶段草案不保存第二份完成状态。

事实基线：

- [当前运行流程与测试总览](../../docs/application-worker-workflow.md)
- [最近回归与版本记录](../../validation/application-automation/2026-10-11/workflow-consolidation/README.md)
- [固定源码哈希](../../validation/application-automation/2026-10-11/workflow-consolidation/source-hashes.json)：当前实现包含未提交文件，不能仅以 Git HEAD 表示这份实现。
- [通用控件与发送契约](../../docs/generic-application-worker.md)
- [个人数据边界](../../docs/data-boundaries.md)

## Decisions so far

<!-- 仅索引已解决票。详细结论只保存在相应票的 resolution comment。 -->

- [核验浏览器生命周期与故障恢复的原生边界](issues/01-browser-recovery-research.md)：原生事件可区分影响范围；先收紧局部异常边界，检查点与 profile 不保证 DOM 恢复，未知上传不能自动重传。
- [确定故障隔离、恢复保证与诊断验收标准](issues/02-recovery-contract.md)：用户确认先交付单页隔离与检查点恢复；故障矩阵、恢复条件和 17 组验收用例已定，未知动作不自动重传。
- [核验通用控件与草稿传输契约的复用边界](issues/03-generic-contract-research.md)：标准控件操作可复用；岗位身份、条件字段、服务端值、草稿保存与附件发送仍须按表单能力核验。

- [确定效率基线、人工干预与模型成本的测量口径](issues/05-measurement-contract.md)：用户接受完整就绪终点、互斥计时、介入/模型/工具分计与 unknown 保留；授权最小计量及 16 个零真实 ATS、零新增真实模型调用的合成场景。

- [确定通用表单支持等级与首批覆盖范围](issues/04-coverage-contract.md)：用户接受三等级与六个不同企业/岗位槽位；当前仅合成验证，真实槽位未执行，最终 Submit 人工。

- [确定缓存失效与低风险效率优化的实施边界](issues/06-efficiency-contract.md)：用户确认本轮止于正确性修补；新性能候选须五对可比运行并超过观测波动，不新增模型、并发或常驻进程。

- [确定故障说明与人工恢复的最短交接流程](issues/07-recovery-handoff-prototype.md)：用户选择 A，并要求原页停在故障点等人工核验；复用原页交接，未知结果先记录结论，仅同步与继续分开。

- [确定阶段验收、停止条件与可执行开发顺序](issues/08-stage-acceptance.md)：用户确认四切片的范围、用例与停止条件；规格齐备，真实槽位、因果收益和历史阻断根因继续未验收。

## Not yet specified

- 新真实样本将暴露哪些尚未出现的控件与传输变体；只对实际需要补充最小契约。
- 故障夹具运行后是否出现新的组合故障；只有能具体描述影响与恢复条件时，才增加决策票。
- 完整耗时分布可能暴露目前无法指认的瓶颈；具体优化候选须由测量结果产生。

## Out of scope

- 自动最终 Submit、替代最终投递 HTTP、绕过 CAPTCHA/MFA 或复制日常浏览器认证资料。
- 承诺所有平台、所有公司表单均可自动完成，或长期完全无人值守。
- 默认实现多 worker、云浏览器基础设施、分布式队列、新数据库或从零构建通用 LLM 点击代理框架。复用现成浏览器/computer use 的有界混合流程在本轮范围内。
- worker 崩溃后仍保留原页面的独立浏览器保证；本阶段采用[确定故障隔离、恢复保证与诊断验收标准](issues/02-recovery-contract.md)中的单页隔离与检查点恢复。
- 本阶段之后的扩大并发、长期运行与安装包交付；这些需要新的目标与实测需求。
- 未确认资格、薪资、授权或个人经历自动推断；模型输出不能建立个人事实或 Skill 评分。
- 本轮真实岗位填值、重复上传、真实投递与新模型调用。
- 以进程或控制服务重启来证明历史 DOM 已恢复；以测试通过数推导真实投递成功率。

## Resolution comment

2026-10-13，八张开发前决策票均已定案。最新支持、效率、原页交接和阶段验收由用户逐票确认，详细结论分别保存于所属 resolution comment。
地图关闭仅表示本阶段可执行规格齐备；未执行真实槽位、未知根因、人工可用性和因果效率收益继续按已接受的验收规格报告，不把本次合成实现推成全部验收。
