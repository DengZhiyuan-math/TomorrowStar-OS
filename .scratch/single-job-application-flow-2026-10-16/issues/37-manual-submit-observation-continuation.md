# 一次继续人工交接并观察Submit结果和可恢复跳过

Type: feature
Label: wayfinder:task
Status: closed
Priority: P2
Interaction: AFK
Assignee: none
Created: 2026-10-20
Updated: 2026-10-21
Parent: [申请主流程](../map.md)
Blocked by: [完成单岗位链路与故障恢复整体验证](09-integration-verification.md)、[独立限制最终Submit并退役请求批准](38-independent-submit-boundary.md)
Triage: done
Closure reason: completed

## 当前结论 — 2026-10-21

已复用30、34、27和同一主App安装/隔离验收，当前8项按本票工程/合成范围满足，按该范围结案。[逐项证据、适用性与保留限度](../../ticket37-evidence-reconciliation-2026-10-21/README.md)。原Assignee=none及依赖保持，没有补造领取人；下方发布时的open/none声明及历史原文保留其时点。

一次Continue保留人工字段和附件，未知intent不被解锁；原页合成人工Submit有真实本地接收端证据，自动最终动作仍0。结果按原Page/run/target和匹配人工请求/响应归属，成功本地记录保存后才交34续岗；拒绝/unknown不推进。skip返回及重开恢复分别由现成组合和27证据支持，不新建调度或状态库。

8项的合成要求不等于真实雇主接受：34仍claimed，真实自然人工Submit→系统明确结果→下一岗仍未验。G3仅显式暂停/空intent同页重开；任意SSO、非空未知intent安装恢复、真实编译器原生在途故障注入未新测，历史根因及readiness/旧compatibility的unknown保留。它们不扩成37新矩阵门槛。

本轮没有新代码、测试、App或真实申请操作，不重跑旧矩阵。未知结果、fill intent、原owner、材料及接受记录不改；真实申请继续暂停，最终Submit人工。

## Question

如何在人工介入后一次继续剩余步骤、观察用户Submit结果，并支持保留进度的跳过和返回？

## 当前范围

依据[规范](../../../docs/single-job-flow.md)的 APP-10/11/12/13/14/16/18 和[统一计划](../../../docs/development-plan.md)。保留当前任务、页面、材料和用户编辑。人工介入时自动写暂停，一次继续后读取现状再推进；最终Submit仅用户操作，系统只观察结果。明确结果自动记录给34决定下一岗；结果不明才问。skip不是取消，后续能回到原岗。

## 精简职责分工

本票拥有人工介入的一次继续、当前页结果观察、skip/返回；消费[统一岗位主控并派生浏览器执行状态](39-single-orchestrator-derived-state.md)和[独立限制最终Submit并退役请求批准](38-independent-submit-boundary.md)的接口。最终动作判定/grant退役、全局岗位调度和UI轮询清理分别由对应票实现，不再由本票重复建设。

## Acceptance criteria

- [x] 人工介入或用户暂停后自动层停止写当前页；一次继续会重新读取当前页面和必要状态，不要求另外保存来源、重新接管、再次resume三连操作。
- [x] 用户已修改的字段、材料选择和当前页进度保留；只补实际还缺的工作，不自动恢复旧答案覆盖人工值。重要事实冲突交36/23处理。
- [x] 消费独立Submit限制，集成验证人工接管后原页可实际提交、自动最终动作仍为零；本票不再实现动作分类或请求grant退役。
- [x] 用户Submit后系统观察当前成功/失败页或可靠响应；明确结果自动保存本地申请记录及来源，向34报告可推进状态，不再要求“我已提交”及另填回执两次确认。
- [x] 无法确定提交/上传/保存结果时保留原动作，先只读识别当前状态；仍不明才问用户，不重开或重发来猜结果，也不把本地显示当雇主接收。
- [x] skip持久保存原岗材料、进度、停止原因、答案、人工修改及未决事项，页面尽量保留但不新增永久占页门槛；向34允许下一岗，回来继续原任务，不记取消/成功，不丢进度或自动重放未决动作。
- [x] 正常运行重开后自动继续可确定的剩余步骤；主动暂停或等待保持等待，一次继续即可；控制端更新后能回到同一任务；失效页面说明实际可恢复方式，不要求历史全部Chrome/包/权限证明矩阵通过。
- [x] 合成覆盖人工编辑继续、明确提交成功/拒绝、未知结果、skip回来、冷重开与零自动最终Submit；34只在明确结果或用户skip后才处理下一岗，产品没有并发。

## Ownership and reuse

`application_worker.py`、`application_worker_browser.py`、`portal_static/worker.js` 和 `portal_static/application_flow.js` 的现有控制、观察和结果入口；复用24所属页观察、25诊断及27恢复。18负责浏览器操作能力，34是唯一队列编排，不另造调度器。

## Publication boundary

仅发布待实施后继，Status=open、Assignee=none。最终Submit权保持用户，未执行真实表单或读取真实提交结果。

## Comments

### 2026-10-20 精简方案入票

当前实现职责和前置依赖按本次方案收敛；原Status、Assignee及历史验收未改。原依赖如下，仅作历史，不参与当前前沿查询：

原 Blocked by: [支持已观察到的通用 ATS 自定义必填控件](18-generic-ats-controls.md)


## Notes — 当前岗继续与事实材料后继 2026-10-21

实现一次Continue原页回读、人工有效字段和附件保留、可恢复skip/return与人工Submit结果观察。提交缺少当前岗归属或最终结果未知时保持等待且不恢复fill/upload；成功记录后才推进。合成真实Chromium证据仅证明本地夹具，真实申请仍暂停。

完整默认离线：4349 passed, 2 skipped, 432 deselected in 676.79s (0:11:16)；[本轮工程、复核与原日志](../../linear-continuation-2026-10-21/README.md)。初轮完整运行因发现缺陷主动中止，旧失败/修复/绿色结果分别保留。Status、Assignee、依赖与原勾选不变，不新增票、不关闭本票。App未更新，真实申请继续暂停，最终Submit始终人工。


## Notes — 必要材料、路由与恢复后继 2026-10-21

Continue 沿当前岗、原 Worker/Page 与当前字段材料恢复，补充真实必要 PDF 后仍暂停；同 SHA 的不同附件分别核验。恢复关闭门、期限及未知状态不得靠 Continue 清除。最终 Submit 仍仅人工，本轮没有最终提交或真实申请。

完整默认离线：4440 passed, 2 skipped, 460 deselected in 718.67s (0:11:58)；受影响离线 1097 项、本地浏览器 164 项均通过。[工程记录、失败历史及冻结输入](../../product-completion-2026-10-21/README.md)。Status、Assignee、依赖及既有勾选均不变，不新增或关闭票。App 未更新或启动，真实申请继续暂停，最终 Submit 始终人工。


## Notes — 原页材料安全更新后继 2026-10-21

已暂停原页在材料更正后用一次 Continue 续填；每轮绑定新材料身份与原 Page，保留人工字段和其他附件。未知上传、原 owner 遗失或超时不能被 Continue 清除。最终 Submit 仍人工，本轮未发送最终提交。

完整默认离线：4450 passed, 2 skipped, 497 deselected in 727.15s (0:12:07)；受影响离线 1358 项、本地浏览器 217 项均通过。[工程记录、失败历史及冻结输入](../../bound-material-update-2026-10-21/README.md)。Status、Assignee、依赖及既有勾选均不变，不新增或关闭票。App 未更新或启动，真实申请继续暂停，最终 Submit 始终人工。


## Notes — 精准等待前必要材料与人工附稿修复 2026-10-21

人工精调保存只改变独立本地版本，继续填写须一次 Continue。跳过后返回原岗可只读核验已导出候选再采用，不重复导出；原页、授权及人工字段保留，缺失/变更结果仍停止，最终 Submit 全程人工。

完整默认离线：4462 passed, 2 skipped, 532 deselected in 968.76s (0:16:08)；受影响离线 1370 项、本地浏览器 252 项均通过。[工程记录、失败历史及冻结输入](../../precision-material-preparation-2026-10-21/README.md)。Status、Assignee、依赖及既有勾选均不变，不新增或关闭票。App 未更新或启动，真实申请继续暂停，最终 Submit 始终人工。


## Notes — 浏览器、材料与默认入口后继 2026-10-21

原Page跨文档普通步骤及同文档本人验证后一次Continue已有合成回归，旧intent与未知结果不重放。最终Submit仍人工；真实SSO、自然Submit结果归属及自动下一岗闭环未由此完成。

完整默认离线：4487 passed、2 skipped；本地合成浏览器：372 passed。受影响集合已包含在最终完整默认/浏览器运行，重叠结果不累加。[工程、原日志与最终冻结输入](../../browser-material-entry-engineering-2026-10-21/README.md)。早期统一失败、独立审查和修复均原样保留。Status、Assignee、依赖和既有验收勾选不变，不新增或关闭票。App未更新或启动，真实申请继续暂停，最终Submit始终人工。


## Notes — 可用优先重排 2026-10-21

已有一次Continue/skip/Submit结果组合；新reload/SSO交接以浏览器具体复现追加，不等所有控件与状态清理。

Priority/Triage/票头依赖按本次重排更新；旧边与原字节见[审计及变更账本](../../usable-first-wayfinder-audit-2026-10-21/README.md)。原 Status、Assignee、Interaction、既有验收勾选及全部旧正文保持，不领取、不关闭、不替用户接受。源码接口依赖不等于安装或真实操作许可；App 未更新，真实申请继续暂停。
