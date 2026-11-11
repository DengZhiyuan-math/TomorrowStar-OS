# 浏览器效率与自动化能力执行导航

> 当前规范与唯一执行计划（2026-10-20）：[产品规范](../../docs/single-job-flow.md) · [开发计划](../../docs/development-plan.md) · [系统审计](../../docs/system-audit-2026-10-20.md)。
> 速度优化服从同一产品主线；09仍需真实用户体验，适配器只是优化路径。旧跨图并行排程、固定支持/未知即人工的契约保留历史，不阻止当前通用浏览器路线。 本次仅重规划，未改Status/Assignee、未执行真实申请。

2026-10-17：用户批准的纵向拆分已正式发布。当前规范导航为[23张正式交付票](../tomorrowstar-ticket-consolidation-2026-10-17/README.md)，原子票路径与领取状态保留；以下直接链接各正式子票。

本路线父地图保持原字节，作为范围与历史保留。本轮只迁移票据，不执行开发，不恢复真实申请。

上述是2026-10-17发布轮边界。2026-10-18后续执行以各子票最新状态及[当前总导航](../tomorrowstar-delivery-2026-10-17/README.md)为准：组合07与独立安装合成复验08均已完成，正式总进度20/23；DOM/manual/unknown和必要UI修复、停止记录冷重开证据见[最终报告](../browser-efficiency-release-2026-10-18/branches-authorized/README.md)。09真实体验仍待用户接受，真实材料审核和真实申请继续暂停；3项HITL集中在[审核清单](../tomorrowstar-delivery-2026-10-17/review-queue.md)。

| 发布序号 | 正式子票（原身份） | 交互 | 直接前置 |
| --- | --- | --- | --- |
| 14 | [让字段流程按忙闲状态调度](issues/05-bounded-waits-readback.md) | AFK | 无 |
| 15 | [让一个不可编辑下拉框走DOM完成选择](issues/03-dom-first-controls.md) | AFK | 无 |
| 16 | [验证并复用一个有价值的重复观察](issues/02-dom-observation-references.md) | AFK | 无 |
| 17 | [取得隔离原生Cua的真实操作证据](issues/11-native-cua-baseline.md) | AFK | 无 |
| 18 | [减少一个昂贵的Cua观察步骤](issues/04-cua-binding-snapshot-overhead.md) | AFK | [取得隔离原生Cua的真实操作证据](issues/11-native-cua-baseline.md) |
| 19 | [在派发前选择已支持的执行路线](issues/06-hybrid-browser-routing.md) | AFK | [让一个不可编辑下拉框走DOM完成选择](issues/03-dom-first-controls.md) |
| 20 | [验证已选浏览器候选的组合收益](issues/07-paired-efficiency-regression.md) | AFK | [让字段流程按忙闲状态调度](issues/05-bounded-waits-readback.md)、[在派发前选择已支持的执行路线](issues/06-hybrid-browser-routing.md) |
| 21 | [在安装版复验已选浏览器快速路径](issues/08-installed-browser-efficiency.md) | AFK | [验证已选浏览器候选的组合收益](issues/07-paired-efficiency-regression.md) |
| 22 | [确认浏览器速度与人工接管体验](issues/09-browser-efficiency-acceptance.md) | HITL | [在安装版复验已选浏览器快速路径](issues/08-installed-browser-efficiency.md) |
| 23 | [补齐一个确有HTTP缺口的只读JD来源](issues/10-readonly-browser-job-source.md) | AFK | [将候选转成可核验的完整岗位](../gmail-resume-preparation-2026-10-17/issues/04-job-source-checkpoints.md) |

## 2026-10-18 后继依赖

[确认浏览器速度与人工接管体验](issues/09-browser-efficiency-acceptance.md)新增[唯一真实单岗验收](../single-job-application-flow-2026-10-16/issues/11-gmail-real-job.md)为前置，承接已记录的真实流程要求。上表为批准时依赖，不代替当前子票；安装合成已完成，真实体验未接受。

[当前开放票及跨图查询](../open-ticket-audit-2026-10-18/README.md)。

## 当前执行规则

状态和领取只保存在子票；读取Status、Triage、Assignee与Blocked by，全部实际前置完成且未领取才可开工。HITL必须由用户实际参与。superseded表示行政承接，不是工程完成，禁止作为已完成前置。

[迁移清单](../tomorrowstar-ticket-consolidation-2026-10-17/publication.json) · [批准前导航](../tomorrowstar-ticket-consolidation-2026-10-17/history/pre-publication/.scratch/browser-efficiency-2026-10-17/README.md) · [原父地图](map.md)。

整体预算参见[合并估算](../../research/tomorrowstar-combined-delivery-estimate-2026-10-17.md)：45–80主动小时，风险情景总计65–105，不与独立材料预算相加。真实申请继续暂停。

## 已完成证据

- [定位浏览器控制的分段耗时与重复调用](issues/01-browser-performance-baseline.md)：原票、领取、报告与资产保持不变。
- [研究事件等待与 CDP 控制的可复用机制](issues/12-event-wait-references.md)：原票、领取、报告与资产保持不变。
- [研究语义视觉代理与替代浏览器的适用边界](issues/13-hybrid-agent-references.md)：原票、领取、报告与资产保持不变。
- [研究浏览器评测与独立结果校验机制](issues/14-evaluation-references.md)：原票、领取、报告与资产保持不变。
